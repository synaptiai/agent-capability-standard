#!/usr/bin/env bash
# Append one action record (STANDARD v1.2 §6.4) per tool call to
# .claude/audit.log, with an HMAC integrity chain.
#
# Claude Code runs this as a PostToolUse and a PostToolUseFailure command hook
# for every tool (see hooks.json) and passes the tool call as JSON on stdin:
# {"hook_event_name": ..., "tool_name": ..., "tool_use_id": ...,
# "tool_input": ...}. PostToolUse fires after a call that succeeded and
# PostToolUseFailure after one that failed. A call that a PreToolUse hook or a
# permission rule refused did not run and is not logged.
#
# Each line is a single-line JSON action record, in this order:
#   - action_id: the call's tool_use_id, or <timestamp>-<pid>-<8 hex digits>
#   - timestamp: ISO 8601 (UTC)
#   - actor: "agent"
#   - intent: "<tool> call"
#   - status: "executed" (PostToolUse) or "failed" (PostToolUseFailure)
#   - tool: the tool's name
#   - call_id: the call's tool_use_id, when the input names one
#   - details: {"event": the hook event, "skill": the skill name (on a Skill
#     call only), "input_sha256": SHA-256 of the tool input, taken over its
#     compact JSON with sorted keys (jq -cS .tool_input), or "unavailable"}
#   - recorded_by: the layer and the configuration that decided the call
#     (STANDARD 1.2.0 §5.18.8): {name: "agent-capability-standard plugin
#     hooks", version: the plugin.json version (or "unknown"), config_sha256:
#     SHA-256 of hooks/hooks.json (or "unavailable"), settings: {approval:
#     "ask"|"off" (ACS_HOOK_APPROVAL), checkpoint_max_age_s: the effective
#     ACS_CHECKPOINT_MAX_AGE, 1 to 1800, default 1800}}
#   - prev_hmac: the hmac of the line before (chain link; empty for the first)
#   - hmac: HMAC-SHA-256 of the line without hmac, as written
#
# The tool input itself is never written: a command, a file's content or a
# skill's arguments can hold a credential. The digest lets a reader who holds
# an input confirm that it is the one that ran.
#
# The HMAC chain makes a change detectable: changing or removing an entry
# breaks the link of the entry after it. Removing the last entries breaks no
# link, so the hook also keeps the chain's end in .claude/audit.head, one
# line of JSON: {"entries": the number of lines in the log, "hmac": the last
# line's hmac, "head_hmac": HMAC-SHA-256 of "acs-audit-head:<entries>:<hmac>"
# under the same key}. Before it appends, the hook checks that the log still
# holds the entry the head records, at its place; tools/verify_audit_log.py
# checks the same, so a log cut short, or removed, fails verification. When
# the log no longer holds that entry, or the head is not one this key signed,
# the hook says so, appends the line, and leaves the head as it is: it is
# the evidence of the cut. The pre-tool-use hook refuses a call that names
# the head (F504). To start a new log, move audit.log and audit.head aside
# together.
#
# The hook records; it does not block (the tool has already run). The log is
# a best-effort capture (STANDARD v1.2 §6.4): it can miss a call, but never
# silently. When it does not log a call, or logs it without a valid HMAC or
# chain link, it says why on standard error and exits 1, which Claude Code
# shows as a non-blocking hook error: no jq, input jq cannot parse (nested
# past jq's depth limit, a lone surrogate escape, or not JSON at all: such
# input may be a tool call), a symlinked audit.log (refused, SEC-006), no
# openssl, a line that could not be built, a last line whose hmac cannot be
# read (the line starts a new chain), an input digest that could not be
# computed (the line says "unavailable"), a head the log no longer matches
# or that cannot be written (the line is written; see above). It exits 0 for a call it logged
# and for JSON that is not a tool call (no input, or a value that is not an
# object with a string tool_name); a log directory or file that cannot be
# written exits non-zero too. A lock that cannot be taken in
# time does not stop the line: it is appended without the lock, with a
# warning, and the verifier reports any chain-order break.
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

# Every path on which a tool call is not logged, or not logged with a valid
# HMAC and chain link, ends here: the reason on standard error, exit 1.
fail() {
  echo "posttooluse_log_tool: $1; this tool call was not logged" >&2
  exit 1
}

# Without jq the tool call cannot be read, so nothing is logged
if ! command -v jq &> /dev/null; then
  fail "jq is not installed"
fi

# Input jq cannot parse is reported, not taken for "no tool call": Claude
# Code passes a call's input and result as they are, so a tool call nested
# deeper than jq's limit, or holding a lone surrogate escape (a string cut in
# the middle of an emoji), fails to parse, and would otherwise be dropped
# silently. Valid JSON that names no tool (no input, a value that is not an
# object, a tool_name that is not a string) is not a tool call: nothing is
# logged.
if ! tool_name=$(printf '%s' "$input" | jq -r 'if type == "object" then (.tool_name | strings) else empty end' 2>/dev/null); then
  reason=$(printf '%s' "$input" | jq empty 2>&1 | head -n 1 | cut -c1-200 || true)
  fail "the hook input could not be parsed (${reason:-jq failed}), and may be a tool call"
fi
if [[ -z "$tool_name" ]]; then
  exit 0
fi

event=$(printf '%s' "$input" | jq -r '.hook_event_name | strings' 2>/dev/null || echo "")
event="${event:-PostToolUse}"
status="executed"
[[ "$event" == "PostToolUseFailure" ]] && status="failed"
call_id=$(printf '%s' "$input" | jq -r '.tool_use_id | strings' 2>/dev/null || echo "")

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

# The layer and its configuration, as every line names it (§5.18.8): what a
# reader needs to know which rules the call was held to. The settings are
# the effective values, after defaults and the cap, of the two environment
# settings that change the hooks' decisions.
plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd || echo .)}"
plugin_version=$(jq -r '.version | strings' "${plugin_root}/.claude-plugin/plugin.json" 2>/dev/null || true)
plugin_version="${plugin_version:-unknown}"
config_sha256=$(sha256_hex < "${plugin_root}/hooks/hooks.json" 2>/dev/null || true)
[[ "$config_sha256" =~ ^[0-9a-f]{64}$ ]] || config_sha256="unavailable"
approval_setting="ask"
[ "${ACS_HOOK_APPROVAL:-ask}" = "off" ] && approval_setting="off"
max_age="${ACS_CHECKPOINT_MAX_AGE:-1800}"
if ! [[ "$max_age" =~ ^[0-9]{1,4}$ ]] || (( 10#$max_age < 1 || 10#$max_age > 1800 )); then
  max_age=1800
fi
max_age=$((10#$max_age))

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
head_file="$log_dir/audit.head"

# SEC-006: Reject symlinked audit log to prevent log redirection attacks
if [ -L "$log_file" ]; then
  fail "audit.log is a symlink (refused, SEC-006)"
fi

# Without openssl no line can be signed; an unsigned line would make every
# later line fail verification, so none is written.
if ! command -v openssl &> /dev/null; then
  fail "openssl is not installed, so the line could not be signed"
fi

# Build log entry with timestamp
ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
action_id="$call_id"
if [[ -z "$action_id" ]]; then
  rand=$(od -An -N4 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n' || true)
  action_id="${ts}-$$-${rand:-00000000}"
fi

# HMAC key: use AUDIT_HMAC_KEY env var, or derive from hostname.
# WARNING: The default hostname-derived key provides integrity against
# accidental corruption ONLY. It is trivially discoverable and does NOT
# provide adversarial tamper resistance. For production/adversarial
# environments, set the AUDIT_HMAC_KEY environment variable to a proper
# cryptographic secret (e.g., 32+ random hex characters).
hmac_key="${AUDIT_HMAC_KEY:-grounded-agency-audit-$(hostname -s 2>/dev/null || echo 'default')}"

# HMAC-SHA-256 (hex) of stdin under the key
hmac_hex() {
  openssl dgst -sha256 -hmac "$hmac_key" -hex 2>/dev/null | awk '{print $NF}'
}

# Append the line. Returns 0 when it was written with a valid chain link and
# the head moved to it, 3 when it was written but starts a new chain (the
# last line's hmac could not be read), 4 when it was written but the head
# was not moved (said on standard error), and 1 when nothing was written (the
# line could not be built or signed).
_do_append() {
  # Get previous entry's HMAC for chaining (empty string for first entry)
  local prev_hmac="" broken=0 entries=0
  if [ -f "$log_file" ]; then
    entries=$(awk 'END { print NR }' "$log_file" 2>/dev/null) || entries=""
    [[ "$entries" =~ ^[0-9]{1,12}$ ]] || entries=""
  fi

  # The head: does the log still hold the entry it records, at its place?
  # ok: yes, or no head and no entry yet; new: no head for a log that has
  # entries (begun before the hook kept one); cut: no, or a head this key did
  # not sign, or one that cannot be read; held: the head cannot be written.
  local head_state="ok" head_entries="" head_hmac_recorded=""
  if [ -L "$head_file" ] || { [ -e "$head_file" ] && [ ! -f "$head_file" ]; }; then
    head_state="held"
  elif [ -f "$head_file" ]; then
    local head_line head_sig
    IFS= read -r -n 4096 head_line < "$head_file" 2>/dev/null || true
    head_entries=$(printf '%s' "$head_line" | jq -r '.entries | numbers | tostring' 2>/dev/null) || head_entries=""
    head_hmac_recorded=$(printf '%s' "$head_line" | jq -r '.hmac | strings' 2>/dev/null) || head_hmac_recorded=""
    head_sig=$(printf '%s' "$head_line" | jq -r '.head_hmac | strings' 2>/dev/null) || head_sig=""
    head_state="cut"
    if [[ "$head_entries" =~ ^[1-9][0-9]{0,11}$ && "$head_hmac_recorded" =~ ^[0-9a-f]{64}$ ]] \
      && [ "$head_sig" = "$(printf 'acs-audit-head:%s:%s' "$head_entries" "$head_hmac_recorded" | hmac_hex)" ] \
      && [[ -n "$entries" ]] && (( 10#$entries >= 10#$head_entries )); then
      local held_hmac
      held_hmac=$(awk -v n="$head_entries" 'NR == n { print; exit }' "$log_file" 2>/dev/null | jq -r '.hmac | strings' 2>/dev/null) || held_hmac=""
      [ "$held_hmac" = "$head_hmac_recorded" ] && head_state="ok"
    fi
  elif [[ "$entries" != "0" ]]; then
    head_state="new"
  fi

  if [ -f "$log_file" ] && [ -s "$log_file" ]; then
    local last_line
    last_line=$(tail -1 "$log_file" 2>/dev/null || echo "")
    if [ -n "$last_line" ]; then
      prev_hmac=$(printf '%s' "$last_line" | jq -r '.hmac | strings' 2>/dev/null || echo "")
      if [[ ! "$prev_hmac" =~ ^[0-9a-f]{64}$ ]]; then
        prev_hmac=""
        broken=1
      fi
    fi
  fi

  # Build compact single-line JSON for the entry content. The verifier
  # (tools/verify_audit_log.py) recomputes the HMAC over every field but
  # `hmac`, in the order written here and in the compact form jq -c prints.
  local entry_content
  entry_content=$(jq -c -n \
    --arg action_id "$action_id" \
    --arg ts "$ts" \
    --arg status "$status" \
    --arg tool "$tool_name" \
    --arg call_id "$call_id" \
    --arg event "$event" \
    --arg skill "$skill" \
    --arg input_sha256 "$input_sha256" \
    --arg version "$plugin_version" \
    --arg config_sha256 "$config_sha256" \
    --arg approval "$approval_setting" \
    --argjson max_age "$max_age" \
    --arg prev_hmac "$prev_hmac" \
    '{action_id: $action_id, timestamp: $ts, actor: "agent",
      intent: ($tool + " call"), status: $status, tool: $tool}
     + (if $call_id == "" then {} else {call_id: $call_id} end)
     + {details: ({event: $event}
                  + (if $skill == "" then {} else {skill: $skill} end)
                  + {input_sha256: $input_sha256}),
        recorded_by: {name: "agent-capability-standard plugin hooks",
                      version: $version, config_sha256: $config_sha256,
                      settings: {approval: $approval, checkpoint_max_age_s: $max_age}},
        prev_hmac: $prev_hmac}' 2>/dev/null) || entry_content=""
  if [ -z "$entry_content" ]; then
    return 1
  fi

  local entry_hmac
  entry_hmac=$(printf '%s' "$entry_content" | openssl dgst -sha256 -hmac "$hmac_key" -hex 2>/dev/null | awk '{print $NF}') || entry_hmac=""
  if [[ ! "$entry_hmac" =~ ^[0-9a-f]{64}$ ]]; then
    return 1
  fi

  # Build final compact JSON entry with HMAC
  local final_entry
  final_entry=$(printf '%s' "$entry_content" | jq -c --arg hmac "$entry_hmac" '. + {hmac: $hmac}' 2>/dev/null) || final_entry=""
  if [ -z "$final_entry" ]; then
    return 1
  fi

  echo "$final_entry" >> "$log_file" || return 1

  # Move the head to the line just written, unless it is the evidence of a
  # cut. Written whole to a file this run creates (noclobber: never one
  # already there, nor through a link), then renamed over the old one.
  local head_problem=0
  case "$head_state" in
    cut)
      echo "posttooluse_log_tool: audit.log no longer holds the entry its head records (entry ${head_entries:-?} of the log, hmac ${head_hmac_recorded:-?}; the log had ${entries:-?} lines), or audit.head is not one this key signed: entries were removed or changed. The head is kept as the evidence; to start a new log, move audit.log and audit.head aside together" >&2
      head_problem=1
      ;;
    held)
      echo "posttooluse_log_tool: audit.head is a symlink or not a regular file (refused, SEC-006); the log's end is not anchored" >&2
      head_problem=1
      ;;
    *)
      # The log's end as it is now: its last line, which is this one unless a
      # run that could not take the lock appended after it.
      local written last_hmac sig="" head_tmp="$log_dir/.audit.head.$$"
      written=$(awk 'END { print NR }' "$log_file" 2>/dev/null) || written=""
      last_hmac=$(tail -1 "$log_file" 2>/dev/null | jq -r '.hmac | strings' 2>/dev/null) || last_hmac=""
      if [[ "$written" =~ ^[1-9][0-9]{0,11}$ && "$last_hmac" =~ ^[0-9a-f]{64}$ ]]; then
        sig=$(printf 'acs-audit-head:%s:%s' "$written" "$last_hmac" | hmac_hex) || sig=""
      fi
      if [[ "$sig" =~ ^[0-9a-f]{64}$ ]] \
        && (set -C; printf '{"entries":%s,"hmac":"%s","head_hmac":"%s"}\n' "$written" "$last_hmac" "$sig" > "$head_tmp") 2>/dev/null \
        && mv -f "$head_tmp" "$head_file" 2>/dev/null; then
        if [[ "$head_state" == "new" ]]; then
          echo "posttooluse_log_tool: audit.log had no head (audit.head), so the end of its first ${entries} entries was not anchored; its end is anchored from this line on" >&2
          head_problem=1
        fi
      else
        rm -f "$head_tmp" 2>/dev/null || true
        echo "posttooluse_log_tool: audit.head could not be written; the log's end is not anchored past its last head" >&2
        head_problem=1
      fi
      ;;
  esac
  if (( broken )); then
    return 3
  fi
  if (( head_problem )); then
    return 4
  fi
  return 0
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
rc=0
if [[ ! -e "$log_file" || -f "$log_file" ]] && (: 9>>"$log_file") 2>/dev/null; then
  (
    lock=0
    _lock_fd9 || lock=$?
    if (( lock == 1 )); then
      echo "posttooluse_log_tool: warning: audit.log stayed locked for ${lock_wait}s; appending without the lock" >&2
    fi
    _do_append
  ) 9>>"$log_file" || rc=$?
else
  _do_append || rc=$?
fi

case "$rc" in
  0) ;;
  3)
    echo "posttooluse_log_tool: the last line of audit.log has no readable hmac; this line starts a new chain" >&2
    exit 1
    ;;
  4) exit 1 ;;
  *) fail "the log line could not be built or written" ;;
esac

if [[ "$input_sha256" == "unavailable" ]]; then
  echo "posttooluse_log_tool: the input digest could not be computed; the line says \"unavailable\"" >&2
  exit 1
fi

exit 0
