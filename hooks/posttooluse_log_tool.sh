#!/usr/bin/env bash
# Append a skill usage line to .claude/audit.log
# Only logs when the Skill tool is invoked

# Read JSON from stdin (Claude Code hooks receive data via stdin)
input=$(cat)

# Check if jq is available
if ! command -v jq &> /dev/null; then
  exit 0
fi

# Extract tool name - skip if not a Skill invocation
tool_name=$(echo "$input" | jq -r '.tool_name // empty' 2>/dev/null)
if [[ "$tool_name" != "Skill" ]]; then
  exit 0
fi

# Extract skill details
skill=$(echo "$input" | jq -r '.tool_input.skill // "unknown"' 2>/dev/null)
args=$(echo "$input" | jq -r '.tool_input.args // ""' 2>/dev/null)

# Determine output directory using CLAUDE_PROJECT_DIR or pwd
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  log_dir="${CLAUDE_PROJECT_DIR}/.claude"
else
  log_dir="$(pwd)/.claude"
fi
mkdir -p "$log_dir"

# Build log entry with timestamp
ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
if [[ -n "$args" ]]; then
  echo "[$ts] Skill: $skill (args: $args)" >> "$log_dir/audit.log"
else
  echo "[$ts] Skill: $skill" >> "$log_dir/audit.log"
fi

exit 0
