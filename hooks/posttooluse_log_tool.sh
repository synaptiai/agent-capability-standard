#!/usr/bin/env bash
# Append a skill usage line to .claude/audit.log with HMAC integrity chain.
#
# Each log entry is a single-line JSON object containing:
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
# NOTE: The default HMAC key (derived from hostname) provides integrity
# against accidental corruption only. For adversarial tamper resistance,
# set AUDIT_HMAC_KEY to a proper secret.

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

# HMAC key: use AUDIT_HMAC_KEY env var, or derive from hostname.
hmac_key="${AUDIT_HMAC_KEY:-grounded-agency-audit-$(hostname -s 2>/dev/null || echo 'default')}"

# Get previous entry's HMAC for chaining (empty string for first entry)
prev_hmac=""
if [ -f "$log_file" ] && [ -s "$log_file" ]; then
  last_line=$(tail -1 "$log_file" 2>/dev/null || echo "")
  if [ -n "$last_line" ]; then
    prev_hmac=$(echo "$last_line" | jq -r '.hmac // ""' 2>/dev/null || echo "")
  fi
fi

# Build compact single-line JSON for entry content (matches Python verifier format).
# Using jq -c produces {"ts":"...","skill":"...","args":"...","prev_hmac":"..."} which
# matches json.dumps(d, separators=(",", ":")) in the Python verifier.
entry_content=$(jq -c -n \
  --arg ts "$ts" \
  --arg skill "$skill" \
  --arg args "$args" \
  --arg prev_hmac "$prev_hmac" \
  '{ts: $ts, skill: $skill, args: $args, prev_hmac: $prev_hmac}' 2>/dev/null)

# Guard: if jq failed, skip logging rather than corrupt the chain
if [ -z "$entry_content" ]; then
  exit 0
fi

# Compute HMAC over entry content. Requires openssl (available on Linux + macOS).
if command -v openssl &> /dev/null; then
  entry_hmac=$(printf '%s' "$entry_content" | openssl dgst -sha256 -hmac "$hmac_key" -hex 2>/dev/null | awk '{print $NF}')
else
  entry_hmac="no-hmac-available"
fi

# Build final compact JSON entry with HMAC
final_entry=$(echo "$entry_content" | jq -c --arg hmac "$entry_hmac" '. + {hmac: $hmac}' 2>/dev/null)

# Guard: don't append empty/broken entries
if [ -z "$final_entry" ]; then
  exit 0
fi

echo "$final_entry" >> "$log_file"

exit 0
