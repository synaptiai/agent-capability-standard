#!/usr/bin/env bash
# Append a skill usage line to .claude/audit.log with HMAC integrity chain.
#
# Each log entry is a JSON object containing:
#   - ts: ISO 8601 timestamp
#   - skill: skill name
#   - args: skill arguments (if any)
#   - prev_hmac: HMAC of the previous entry (chain link)
#   - hmac: HMAC of this entry's content
#
# The HMAC chain ensures tamper detection: modifying or deleting
# any entry invalidates all subsequent HMACs.
#
# SEC-005: Audit log integrity via HMAC chaining.

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
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  log_dir="${CLAUDE_PLUGIN_ROOT}/.claude"
else
  log_dir="$(pwd)/.claude"
fi
mkdir -p "$log_dir"

log_file="$log_dir/audit.log"

# Build log entry with timestamp
ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# HMAC key: use AUDIT_HMAC_KEY env var, or derive from a stable machine secret
# In production, this should be set to a proper secret via environment config.
hmac_key="${AUDIT_HMAC_KEY:-grounded-agency-audit-$(hostname -s 2>/dev/null || echo 'default')}"

# Get previous entry's HMAC for chaining (empty string for first entry)
prev_hmac=""
if [ -f "$log_file" ] && [ -s "$log_file" ]; then
  last_line=$(tail -1 "$log_file" 2>/dev/null || echo "")
  if [ -n "$last_line" ]; then
    prev_hmac=$(echo "$last_line" | jq -r '.hmac // ""' 2>/dev/null || echo "")
  fi
fi

# Build the entry content (everything except the hmac field itself)
entry_content=$(jq -n \
  --arg ts "$ts" \
  --arg skill "$skill" \
  --arg args "$args" \
  --arg prev_hmac "$prev_hmac" \
  '{ts: $ts, skill: $skill, args: $args, prev_hmac: $prev_hmac}' 2>/dev/null)

# Compute HMAC over entry content
if command -v openssl &> /dev/null; then
  entry_hmac=$(printf '%s' "$entry_content" | openssl dgst -sha256 -hmac "$hmac_key" -hex 2>/dev/null | awk '{print $NF}')
elif command -v shasum &> /dev/null; then
  # Fallback: use shasum with key prepended (not true HMAC but provides basic integrity)
  entry_hmac=$(printf '%s%s' "$hmac_key" "$entry_content" | shasum -a 256 2>/dev/null | awk '{print $1}')
else
  # Last resort: no HMAC available, use a hash of content only
  entry_hmac="no-hmac-available"
fi

# Build final entry with HMAC
final_entry=$(echo "$entry_content" | jq --arg hmac "$entry_hmac" '. + {hmac: $hmac}' 2>/dev/null)

# Append to log (atomic-ish: single echo to avoid partial writes)
echo "$final_entry" >> "$log_file"

exit 0
