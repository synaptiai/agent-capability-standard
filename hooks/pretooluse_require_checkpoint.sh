#!/usr/bin/env bash
# Require a valid, non-stale checkpoint marker before mutation commands.
#
# Claude Code runs this as a PreToolUse command hook (see hooks.json) and
# passes the tool call as JSON on stdin: {"tool_name": ..., "tool_input": ...}.
# For manual use and older callers, a payload given as the first argument is
# read instead of stdin.
#
# Exit codes follow Claude Code's hook contract:
#   0  allow the tool call
#   2  block it; the reason on stderr is shown to Claude
#
# The marker file (.claude/checkpoint.ok) must contain a JSON object with:
#   { "checkpoint_id": "...", "created_at": <unix_timestamp>, "expires_at": <unix_timestamp> }
#
# This hook validates:
#   1. The marker file exists and is a regular file (not a symlink)
#   2. The marker contains valid JSON with a timestamp
#   3. The checkpoint has not expired
#
# SEC-001: Prevents stale checkpoint.ok bypass
# SEC-006: Uses CLAUDE_PROJECT_DIR for absolute path resolution
set -euo pipefail

if [ "$#" -gt 0 ]; then
  payload="$1"
else
  payload="$(cat)"
fi

block() {
  echo "Blocked: $1" >&2
  exit 2
}

# Mutation patterns: tool names, and commands that change files, push data or
# install software. Matched against the whole payload, so every call of the
# tools hooks.json routes here (Write, Edit, MultiEdit, NotebookEdit, Bash)
# needs a checkpoint: a Bash command cannot be shown to be read-only, so it
# is not trusted to be. The marker itself is written outside these tools
# (CheckpointTracker, or by a person).
mutation_re='(Write\b|Edit\b|MultiEdit\b|NotebookEdit\b|Bash\b|Git\b|rm\b|mv\b|sed\b|perl\b|curl\b|docker\b|kubectl\b|scp\b|rsync\b|npm\b|pip\b|chmod\b|chown\b|shred\b|unlink\b|ln\b)'

# Only check for mutation commands
if ! printf '%s' "$payload" | grep -E -i "$mutation_re" >/dev/null 2>&1; then
  exit 0
fi

# SEC-006: Use absolute path via CLAUDE_PROJECT_DIR, fall back to CLAUDE_PLUGIN_ROOT, then pwd
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  marker="${CLAUDE_PROJECT_DIR}/.claude/checkpoint.ok"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  marker="${CLAUDE_PLUGIN_ROOT}/.claude/checkpoint.ok"
else
  marker="$(pwd)/.claude/checkpoint.ok"
fi

# Check marker exists
if [ ! -e "$marker" ]; then
  block "missing checkpoint marker ($marker). Create a checkpoint first."
fi

# SEC-006: Reject symlinks to prevent bypass via symlink to always-existing file
if [ -L "$marker" ]; then
  block "checkpoint marker is a symlink. Remove it and create a proper checkpoint."
fi

# Ensure it is a regular file
if [ ! -f "$marker" ]; then
  block "checkpoint marker is not a regular file."
fi

# SEC-001: Validate timestamp freshness
# Read marker content — must be valid JSON with expires_at
content=$(cat "$marker" 2>/dev/null || echo "")
if [ -z "$content" ]; then
  rm -f "$marker"
  block "checkpoint marker is empty. Create a new checkpoint."
fi

# Check if jq is available for JSON parsing
if command -v jq &> /dev/null; then
  checkpoint_id=$(echo "$content" | jq -r '.checkpoint_id // empty' 2>/dev/null)
  expires_at=$(echo "$content" | jq -r '.expires_at // empty' 2>/dev/null)
  if [ -z "$checkpoint_id" ] || [ -z "$expires_at" ]; then
    rm -f "$marker"
    block "checkpoint marker missing required fields. Create a new checkpoint."
  fi

  # Validate expires_at is numeric
  if ! [[ "$expires_at" =~ ^[0-9]+$ ]]; then
    rm -f "$marker"
    block "checkpoint marker has invalid expiry. Create a new checkpoint."
  fi

  # Compare expiry against current time
  now=$(date +%s)
  if [ "$now" -gt "$expires_at" ]; then
    rm -f "$marker"
    block "checkpoint has expired. Create a new checkpoint."
  fi
else
  # Fallback: without jq, check file age (max 30 minutes = 1800 seconds)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    file_age=$(( $(date +%s) - $(stat -f %m "$marker") ))
  else
    file_age=$(( $(date +%s) - $(stat -c %Y "$marker") ))
  fi

  if [ "$file_age" -gt 1800 ]; then
    rm -f "$marker"
    block "checkpoint marker is stale (${file_age}s old, max 1800s). Create a new checkpoint."
  fi
fi

exit 0
