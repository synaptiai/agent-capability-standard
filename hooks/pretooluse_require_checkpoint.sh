#!/usr/bin/env bash
# Require a valid, non-stale checkpoint marker before mutation commands.
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

payload="${1:-}"

# Only check for mutation commands
if ! echo "$payload" | grep -E -i "(Edit\b|Bash\b|Git\b|rm\b|mv\b|sed\b|perl\b)" >/dev/null 2>&1; then
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
  echo "Blocked: missing checkpoint marker ($marker). Create a checkpoint first."
  exit 1
fi

# SEC-006: Reject symlinks to prevent bypass via symlink to always-existing file
if [ -L "$marker" ]; then
  echo "Blocked: checkpoint marker is a symlink. Remove it and create a proper checkpoint."
  exit 1
fi

# Ensure it is a regular file
if [ ! -f "$marker" ]; then
  echo "Blocked: checkpoint marker is not a regular file."
  exit 1
fi

# SEC-001: Validate timestamp freshness
# Read marker content — must be valid JSON with expires_at
content=$(cat "$marker" 2>/dev/null || echo "")
if [ -z "$content" ]; then
  echo "Blocked: checkpoint marker is empty. Create a new checkpoint."
  rm -f "$marker"
  exit 1
fi

# Check if jq is available for JSON parsing
if command -v jq &> /dev/null; then
  expires_at=$(echo "$content" | jq -r '.expires_at // empty' 2>/dev/null)
  if [ -z "$expires_at" ]; then
    echo "Blocked: checkpoint marker missing expiry. Create a new checkpoint."
    rm -f "$marker"
    exit 1
  fi

  # Compare expiry against current time
  now=$(date +%s)
  if [ "$now" -gt "$expires_at" ] 2>/dev/null; then
    echo "Blocked: checkpoint has expired. Create a new checkpoint."
    rm -f "$marker"
    exit 1
  fi
else
  # Fallback: without jq, check file age (max 30 minutes = 1800 seconds)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    file_age=$(( $(date +%s) - $(stat -f %m "$marker") ))
  else
    file_age=$(( $(date +%s) - $(stat -c %Y "$marker") ))
  fi

  if [ "$file_age" -gt 1800 ]; then
    echo "Blocked: checkpoint marker is stale (${file_age}s old, max 1800s). Create a new checkpoint."
    rm -f "$marker"
    exit 1
  fi
fi

exit 0
