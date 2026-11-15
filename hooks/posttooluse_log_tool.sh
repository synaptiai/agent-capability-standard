#!/usr/bin/env bash
# Append one line per tool call to .claude/audit.log with an HMAC integrity chain.
#
# Claude Code runs this as a PostToolUse and a PostToolUseFailure command hook
# for every tool (see hooks.json) and passes the tool call as JSON on stdin:
# {"hook_event_name": ..., "tool_name": ..., "tool_input": ...}. PostToolUse
# fires after a call that succeeded and PostToolUseFailure after one that
# failed. A call that a PreToolUse hook or a permission rule refused did not
# run and is not logged.
#
# Each log entry is a single-line JSON object containing:
#   - ts: ISO 8601 timestamp (UTC)
#   - event: the hook event, "PostToolUse" or "PostToolUseFailure"
#     ("PostToolUse" when the input names none)
#   - tool: tool name
#   - skill: skill name (on a Skill call only)
#   - input_sha256: SHA-256 of the tool input, taken over its compact JSON
#     with sorted keys (jq -cS .tool_input), or "unavailable" when it cannot
#     be computed
#   - prev_hmac: HMAC of the previous entry (chain link)
#   - hmac: HMAC of this entry's content
#
# The tool input itself is never written: a command, a file's content or a
# skill's arguments can hold a credential. The digest lets a reader who holds
# an input confirm that it is the one that ran.
#
# The HMAC chain ensures tamper detection: modifying or deleting
# any entry invalidates all subsequent HMACs.
#
# The hook records; it does not block (the tool has already run). It exits 0,
# also when it refuses a symlinked log (SEC-006, below), and exits non-zero
# when the log directory or file cannot be written, which Claude Code reports
# as a non-blocking hook error.
#
# SEC-005: Audit log integrity via HMAC chaining.
# NOTE: The default HMAC key (derived from hostname) provides integrity
# against accidental corruption only. For adversarial tamper resistance,
# set AUDIT_HMAC_KEY to a proper secret.

# SEC-006: Consistent path resolution (matches pretooluse_require_checkpoint.sh)
set -euo pipefail

# Read JSON from stdin (Claude Code hooks receive data via stdin). Not
# $(</dev/stdin): on Linux a hook's stdin is a socket, which cannot be opened
# by path.
input=$(cat)

# Without jq the tool call cannot be read, so nothing is logged
if ! command -v jq &> /dev/null; then
  exit 0
fi

# Input that is not JSON, or names no tool, is not a tool call: nothing is
# logged. jq fails on invalid JSON (what it printed before failing, for a JSON
# value followed by other text, is discarded), and `strings` drops a
# non-string value.
tool_name=$(printf '%s' "$input" | jq -r '.tool_name | strings' 2>/dev/null) || tool_name=""
if [[ -z "$tool_name" ]]; then
  exit 0
fi

event=$(printf '%s' "$input" | jq -r '.hook_event_name | strings' 2>/dev/null || echo "")
event="${event:-PostToolUse}"

# The skill name is recorded for a Skill call only
skill=""
if [[ "$tool_name" == "Skill" ]]; then
  skill=$(printf '%s' "$input" | jq -r '.tool_input.skill | strings' 2>/dev/null || echo "")
  skill="${skill:-unknown}"
fi

# SHA-256 (hex) of stdin, by whichever tool the system has
sha256_hex() {
  if command -v sha256sum &> /dev/null; then
    sha256sum | awk '{print $1}'
  elif command -v shasum &> /dev/null; then
    shasum -a 256 | awk '{print $1}'
  elif command -v openssl &> /dev/null; then
    openssl dgst -sha256 -hex | awk '{print $NF}'
  else
    cat > /dev/null
    return 1
  fi
}

# The digest stands in for the tool input. It is taken over the input's compact
# JSON with sorted keys, so the same input always gives the same digest; a call
# with no tool_input is digested as `null`. A digest that cannot be computed
# (the input cannot be serialized, no SHA-256 tool, a tool that fails or prints
# something other than 64 hex digits) is recorded as `unavailable`: the line is
# still written, and the input is still left out.
input_sha256="unavailable"
if input_canonical=$(printf '%s' "$input" | jq -cS '.tool_input' 2>/dev/null); then
  digest=$(printf '%s' "$input_canonical" | sha256_hex 2>/dev/null || true)
  if [[ "$digest" =~ ^[0-9a-f]{64}$ ]]; then
    input_sha256="$digest"
  fi
fi

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

# SEC-006: Reject symlinked audit log to prevent log redirection attacks
if [ -L "$log_file" ]; then
  echo "WARNING: audit.log is a symlink — refusing to write." >&2
  exit 0
fi

# Build log entry with timestamp
ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# HMAC key: use AUDIT_HMAC_KEY env var, or derive from hostname.
# WARNING: The default hostname-derived key provides integrity against
# accidental corruption ONLY. It is trivially discoverable and does NOT
# provide adversarial tamper resistance. For production/adversarial
# environments, set the AUDIT_HMAC_KEY environment variable to a proper
# cryptographic secret (e.g., 32+ random hex characters).
hmac_key="${AUDIT_HMAC_KEY:-grounded-agency-audit-$(hostname -s 2>/dev/null || echo 'default')}"

_do_append() {
  # Get previous entry's HMAC for chaining (empty string for first entry)
  local prev_hmac=""
  if [ -f "$log_file" ] && [ -s "$log_file" ]; then
    local last_line
    last_line=$(tail -1 "$log_file" 2>/dev/null || echo "")
    if [ -n "$last_line" ]; then
      prev_hmac=$(printf '%s' "$last_line" | jq -r '.hmac // ""' 2>/dev/null || echo "")
    fi
  fi

  # Build compact single-line JSON for the entry content. The verifier
  # (tools/verify_audit_log.py) recomputes the HMAC over every field but
  # `hmac`, in the order written here and in the compact form jq -c prints.
  local entry_content
  entry_content=$(jq -c -n \
    --arg ts "$ts" \
    --arg event "$event" \
    --arg tool "$tool_name" \
    --arg skill "$skill" \
    --arg input_sha256 "$input_sha256" \
    --arg prev_hmac "$prev_hmac" \
    '{ts: $ts, event: $event, tool: $tool}
     + (if $skill == "" then {} else {skill: $skill} end)
     + {input_sha256: $input_sha256, prev_hmac: $prev_hmac}' 2>/dev/null)

  # Guard: if jq failed, skip logging rather than corrupt the chain
  if [ -z "$entry_content" ]; then
    return 0
  fi

  # Compute HMAC over entry content. Requires openssl (available on Linux + macOS).
  local entry_hmac
  if command -v openssl &> /dev/null; then
    entry_hmac=$(printf '%s' "$entry_content" | openssl dgst -sha256 -hmac "$hmac_key" -hex 2>/dev/null | awk '{print $NF}')
  else
    entry_hmac="no-hmac-available"
  fi

  # Build final compact JSON entry with HMAC
  local final_entry
  final_entry=$(printf '%s' "$entry_content" | jq -c --arg hmac "$entry_hmac" '. + {hmac: $hmac}' 2>/dev/null)

  # Guard: don't append empty/broken entries
  if [ -z "$final_entry" ]; then
    return 0
  fi

  echo "$final_entry" >> "$log_file"
}

# Serialize read + append, so that concurrent hook runs (tool calls made in
# parallel) do not read the same prev_hmac and break the HMAC chain.
#
# The lock is flock(2) on the log file itself, opened for append (never
# truncated) as file descriptor 9 of the subshell that appends: writable,
# because NFS emulates flock(2) with byte-range locks, which need it. There
# is no lock file to plant, replace or make unwritable, and the kernel
# releases the lock when that subshell exits, however it exits. perl takes it
# where installed, since it tells a lock another run holds from one that
# cannot be taken here; flock(1) elsewhere (any flock(1): only -x and -n are
# used). Both are flock(2), so sessions using either exclude each other. A
# run tries every 0.05 s for at most AUDIT_LOCK_WAIT seconds (default 40, at
# most 55: Claude Code stops a hook after 60), then appends without the lock,
# as it does at once where the lock cannot be taken at all. An entry out of
# chain order is reported by the verifier, a missing one is not, so a held
# lock cannot silence the log.
lock_wait="${AUDIT_LOCK_WAIT:-40}"
[[ "$lock_wait" =~ ^[0-9]{1,2}$ ]] || lock_wait=40
(( 10#$lock_wait <= 55 )) || lock_wait=55

# One attempt at flock(2) on descriptor 9. Returns 0 when taken, 1 when
# another run holds it, 2 when it cannot be taken here.
_try_lock_fd9() {
  local rc=0
  if command -v perl &> /dev/null; then
    perl -MFcntl=:flock -e '
      open(my $fd, ">>&=", 9) or exit 2;
      exit 0 if flock($fd, LOCK_EX | LOCK_NB);
      exit(($!{EWOULDBLOCK} || $!{EAGAIN} || $!{EINTR}) ? 1 : 2);
    ' 2>/dev/null || rc=$?
  elif command -v flock &> /dev/null; then
    flock -x -n 9 2>/dev/null || rc=$?
    (( rc <= 1 )) || rc=2
  else
    rc=2
  fi
  return "$rc"
}

_lock_fd9() {
  # SECONDS counts whole seconds: one more, so the wait is never shorter.
  local deadline=$((SECONDS + 10#$lock_wait + 1)) rc
  while true; do
    rc=0
    _try_lock_fd9 || rc=$?
    (( rc == 1 )) || return "$rc"
    (( SECONDS < deadline )) || return 1
    sleep 0.05 2>/dev/null || sleep 1 2>/dev/null || true
  done
}

# Lock only a regular file that descriptor 9 can open (not a FIFO, which
# would block, and not past a very low open-file limit).
if [[ ! -e "$log_file" || -f "$log_file" ]] && (: 9>>"$log_file") 2>/dev/null; then
  (_lock_fd9 || true; _do_append) 9>>"$log_file"
else
  _do_append
fi

exit 0
