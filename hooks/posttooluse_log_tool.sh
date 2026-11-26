#!/bin/sh
# Claude Code starts this hook with the env of the project's settings files
# applied (repository content, project_layer_settings below): it runs under
# bash -p, which reads no BASH_ENV or ENV file, imports no shell function and
# ignores SHELLOPTS, BASHOPTS, CDPATH and GLOBIGNORE, and starts itself so
# when started another way (as /bin/sh, bash reads none of them either).
case $- in *p*) ;; *) exec bash -p "$0" "$@" ;; esac
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
#   - intent: "<tool> call", the tool's name as tool shows it
#   - status: "executed" (PostToolUse) or "failed" (PostToolUseFailure)
#   - tool: the tool's name, as plain_name shows it (below: the name when it
#     is plain and holds no credential the secret scan recognises, else
#     [REDACTED])
#   - call_id: the call's tool_use_id, when the input names one
#   - details: {"event": the hook event, "skill": the skill name (on a Skill
#     call only; the model chooses it, so plain_name shows it too),
#     "input_sha256": SHA-256 of the tool input, taken over its compact JSON
#     with sorted keys (jq -cS .tool_input), or "unavailable"}
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
# skill's arguments can hold a credential, and so can the skill's name, which
# is written only as plain_name shows it. The digest lets a reader who holds
# an input confirm that it is the one that ran.
#
# The HMAC chain makes a change detectable: changing or removing an entry
# breaks the link of the entry after it. Removing the last entries breaks no
# link, so the hook also keeps the chain's end in .claude/audit.head, one
# line of JSON: {"entries": the number of lines in the log, "hmac": the last
# line's hmac, "head_hmac": HMAC-SHA-256 of "acs-audit-head:<entries>:<hmac>"
# under the same key}, and the same line, the head's anchor, in the
# project's git directory (<git dir>/acs/audit.head), which a command that
# removes .claude whole (git clean -fdx, rm -rf .claude) leaves. Before it
# appends, the hook checks that the log still holds the entry the head and
# the anchor record, at its place; tools/verify_audit_log.py checks the
# same, so a log cut short, or removed, with its head or not, fails
# verification. When the log no longer holds that entry, or the head or the
# anchor is not one this key signed, the hook says so, appends the line, and
# leaves both as they are: they are the evidence of the cut. The pre-tool-use
# hook refuses a call that names the head, .claude or the git directory's
# acs/ (F504). To start a new log, move audit.log, audit.head and the anchor
# aside together. A head stays valid for as long as its key, and the agent's
# commands can read it and the anchor (and the key, from AUDIT_HMAC_KEY in
# their environment, or from a key file not denied to them): a
# cut written back with an earlier head, or with one the key signs anew, by
# a command a person approved that names neither, verifies. A witness, a
# copy of the head kept where the agent cannot write (verify_audit_log.py
# --witness), shows it.
#
# The hook records; it does not block (the tool has already run). The log is
# a best-effort capture (STANDARD v1.2 §6.4): it can miss a call, but never
# silently. When it does not log a call, or logs it without a valid HMAC or
# chain link, it says why on standard error and exits 1, which Claude Code
# shows as a non-blocking hook error: no jq, input jq cannot parse (nested
# past jq's depth limit, a lone surrogate escape, or not JSON at all: such
# input may be a tool call), project settings files that set a variable in
# env that is not Claude Code's own (one of the hooks' settings, or one that
# changes what this hook runs), or cannot be read (no key the repository may
# know signs a line: project_layer_settings), a symlinked audit.log (refused,
# SEC-006), no key or no openssl (the line is written unsigned, below), a
# line that could not be built, a last line whose
# hmac cannot be read (the line starts a new chain), an input digest that
# could not be computed (the line says "unavailable"), a head the log no
# longer matches or that cannot be written (the line is written; see
# above). It exits 0 for a call it logged
# and for JSON that is not a tool call (no input, or a value that is not an
# object with a string tool_name); a log directory or file that cannot be
# written exits non-zero too. A lock that cannot be taken in
# time does not stop the line: it is appended without the lock, with a
# warning, and the verifier reports any chain-order break.
#
# SEC-005: Audit log integrity via HMAC chaining.
#
# The key: the first line of ~/.config/acs/audit.key ($HOME/.config/acs/
# audit.key, HOME an absolute path), when that file exists; else the value
# of AUDIT_HMAC_KEY; else none. The file is used only when it is a regular
# file (not a symbolic link) owned by the user the hook runs as, with no
# permission for group or others (mode 600 or 400), with one link (a second
# hard link, made where a sandboxed command can read, would expose it), in
# a directory owned by that user, not a symbolic link, that group and
# others cannot write and that is not inside the project directory (which
# the agent's commands may write), and its first line is 32 to 4096 visible
# ASCII characters. A file that exists but fails one of these is refused,
# and AUDIT_HMAC_KEY is not used in its place. Without a key, or without openssl, the line is written unsigned
# (its hmac is empty), the head and the anchor are left as they are, and
# the hook says why and exits 1. tools/verify_audit_log.py reads the same
# key by the same rules (but the project directory's, which it does not
# know), and reports every unsigned line. The key is on no command line:
# hmac_hex builds the HMAC from SHA-256 (hooks/hmac_sha256.sh, copied below).

# SEC-006: Consistent path resolution (matches pretooluse_require_checkpoint.sh)
set -euo pipefail

# Determine the project directory using CLAUDE_PROJECT_DIR or pwd
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  project_dir="${CLAUDE_PROJECT_DIR}"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  project_dir="${CLAUDE_PLUGIN_ROOT}"
else
  project_dir="$(pwd)"
fi

# BEGIN hook-environment (the same in the three hooks that read a setting; tests/test_project_settings.py keeps them so)
# The env of the project's settings files, repository content, reaches this
# hook's programs too (project_layer_settings). Before any runs, PATH keeps
# only the absolute directories outside the project directory, each as the
# system resolves it: a relative entry, or one in the project, would put the
# repository's jq, git or openssl in place of the system's (with none left,
# PATH names /dev/null: an empty one would search the working directory).
# A project directory that is the user's home directory, or holds it (as
# the password database gives it, not HOME), is no repository's: there
# every absolute directory is kept. jq runs with no HOME: it loads
# $HOME/.jq as a library, whose definitions replace its own.
hook_path() {
  local entry rest="${PATH:-}:" out="" project="" home=""
  if cd -P -- "$project_dir" 2>/dev/null; then project="$PWD"; fi
  unset HOME
  if cd -P ~ 2>/dev/null; then home="$PWD"; fi
  case "$home/" in "$project"/*) [ -z "$home" ] || project="" ;; esac
  while [ -n "$rest" ]; do
    entry="${rest%%:*}"
    rest="${rest#*:}"
    case "$entry" in /*) ;; *) continue ;; esac
    cd -P -- "$entry" 2>/dev/null || continue
    case "$PWD/" in "${project:-//}"/*) continue ;; esac
    out="${out:+$out:}$PWD"
  done
  printf '%s' "${out:-/dev/null}"
}
PATH=$(hook_path)
export PATH
jq() { HOME= command jq "$@"; }
# A program ("$@", found on PATH: not a function) run with no input for at
# most 5 seconds: git reads the files a repository's configuration includes,
# and jq the project's settings files, and a FIFO or a terminal there
# (/dev/ptmx) holds the read until someone writes, past the hook's time
# limit, after which a Claude Code without onFailure "block" runs the call.
# Status 124 when it was stopped (or sleep, which times it, cannot run),
# else the program's.
bounded() {
  local pid watch status=0 stopped=0
  (exec "$@") < /dev/null &
  pid=$!
  (
    trap 'kill "${sleeper:-}" 2> /dev/null; exit 0' TERM
    sleep 5 &
    sleeper=$!
    wait "$sleeper" || true
    kill -KILL "$pid" 2> /dev/null && exit 124
    exit 0
  ) > /dev/null 2>&1 &
  watch=$!
  wait "$pid" || status=$?
  kill -TERM "$watch" 2> /dev/null || true
  wait "$watch" || stopped=$?
  [ "$stopped" != 124 ] || return 124
  return "$status"
}
# END hook-environment

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
if ! type -P jq &> /dev/null; then
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

# The variables that the project's own settings files, .claude/settings.json
# and .claude/settings.local.json in the project directory $1, set in their
# env and that are not Claude Code's own settings (the list below), one to a
# line; for a file jq cannot read, its name. Claude Code applies those
# files' env, which is repository content, to every hook and every command
# it runs, over the user's settings and the environment it started in. So a
# hook cannot tell the person's value of one of the layer's settings from
# the repository's (ACS_HOOK_APPROVAL=off, an AUDIT_HMAC_KEY the repository
# knows, a longer maximum age), and any other variable can change what a
# hook, or a command it lets pass, runs: BASH_ENV, ENV, SHELLOPTS and
# BASHOPTS (bash runs a repository script first, or nothing), PATH and HOME
# (a repository's jq, git or openssl, or jq's library), LD_* and DYLD_* (a
# repository's library in every program), GIT_CONFIG_* and the rest of
# git's command scope (GIT_CONFIG_PARAMETERS, GIT_CONFIG_GLOBAL,
# XDG_CONFIG_HOME: a program `git status` runs), a proxy, an exported
# function (BASH_FUNC_*). Only names on the list pass, as written (another
# letter case is another variable on most systems, the same one on
# Windows). The three hooks that read a setting hold the same function; a
# test keeps them so, keeps every setting a hook reads off the list, and
# keeps the list the SDK adapter's (grounded_agency/utils/project_settings.py).
project_layer_settings() {
  local file
  for file in "$1/.claude/settings.json" "$1/.claude/settings.local.json"; do
    if [ -e "$file" ] || [ -L "$file" ]; then
      # A file that is not a regular one (a FIFO, a link to /dev/ptmx) is
      # unreadable: a read of it waits for a writer.
      [ -f "$file" ] && HOME= bounded jq -r 'if type == "object" and (.env | type) == "object" then .env | keys[] | select(test("\\A(ANTHROPIC_[A-Z0-9_]+|OTEL_[A-Z0-9_]+|CLAUDE_CODE_(ENABLE_TELEMETRY|MAX_OUTPUT_TOKENS|USE_BEDROCK|USE_VERTEX|DISABLE_NONESSENTIAL_TRAFFIC)|DISABLE_(TELEMETRY|ERROR_REPORTING|AUTOUPDATER)|MAX_THINKING_TOKENS|MAX_MCP_OUTPUT_TOKENS|MCP_TIMEOUT|MCP_TOOL_TIMEOUT|BASH_DEFAULT_TIMEOUT_MS|BASH_MAX_TIMEOUT_MS|BASH_MAX_OUTPUT_LENGTH)\\z") | not) else empty end' "$file" 2>/dev/null \
        || printf '%s\n' ".claude/${file##*/} (unreadable)"
    fi
  done
}

# A key, setting or other variable the repository may have chosen signs,
# describes and runs nothing: no line is written (the pre-tool-use hook
# refuses every call meanwhile, R407), and the log's chain and head are left
# as they are. Checked before any program but jq runs.
named=$(project_layer_settings "$project_dir") || named="(unreadable)"
# Shown in the reason: the first 400 characters, one line, plain.
named="${named:0:400}"
named="${named//$'\n'/ }"
named="${named//[^A-Za-z0-9_.\/() ]/?}"
if [[ -n "$named" ]]; then
  fail "R407 SAFETY_CHECK_FAILED: the project's settings files set variables in env that are not Claude Code's own, or cannot be read: ${named% }; Claude Code applies a project's env, which is repository content, over yours, so no line is signed with it"
fi

event=$(printf '%s' "$input" | jq -r '.hook_event_name | strings' 2>/dev/null || echo "")
event="${event:-PostToolUse}"
status="executed"
[[ "$event" == "PostToolUseFailure" ]] && status="failed"
call_id=$(printf '%s' "$input" | jq -r '.tool_use_id | strings' 2>/dev/null || echo "")

# BEGIN secret-scan (source: hooks/secret_scan.sh; tests/test_skill_hooks.py keeps every copy equal)
# secret_in TEXT: status 0 when TEXT holds a credential-shaped value (STANDARD 1.2.0 §6.7), read line by line and again with
# its line breaks read as blanks, as the SDK's and the TypeScript rules read whitespace (password:<newline>value).
# secret_lines TEXT: the same rules, each line read on its own; a caller that joins texts read apart joins them with line
# breaks, each text given once as it is and once with its own line breaks read as blanks.
# secret_values TEXT: what the rules whose match may hold whitespace find in TEXT, one per line, each line read on its own:
# the match, or the value a rule reads out of it (a caller compares what two texts hold).
# Each reads TEXT with the JSON escapes some encoders write decoded (secret_decoded), and secret_lines first looks for a
# value the layer holds itself (secret_held).
# The shapes of keys and tokens (the first two may hold whitespace)
SECRET_SPACED='-----BEGIN [A-Z ]*PRIVATE KEY( BLOCK)?-----|[Bb]earer[[:space:]]+[A-Za-z0-9._~+/=-]{20,}'
SECRET_ERE="$SECRET_SPACED"'|(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
# ... and service tokens by their prefix (Stripe, Google, GitLab, npm, Vault, SendGrid) and a Slack webhook's path
SECRET_ERE="$SECRET_ERE"'|[rs]k_(live|test)_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{35}|glpat-[0-9A-Za-z_-]{20,}|npm_[A-Za-z0-9]{36}|hv[sbr]\.[A-Za-z0-9_-]{24,}|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}|hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]{16,}'
SECRET_KEY='(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|account[_-]?key|signing[_-]?key|encryption[_-]?key|hmac[_-]?key|master[_-]?key|credential)'
# A quote, or an escaped one (\" in JSON text inside a JSON string)
SECRET_Q="\\\\*[\"']"
# A command's option named for a credential (--password, --api-key), and a user option (curl -u user:password; a user of at most 256 characters, so no run is read again from each of its positions; written {0,255} and one more, since BSD grep refuses a count over 255)
SECRET_OPT="(^|[^A-Za-z0-9_-])--([A-Za-z0-9]+[_-])*$SECRET_KEY"
SECRET_SEP="([[:space:]]+($SECRET_Q)?|=($SECRET_Q)?|($SECRET_Q)?[[:space:]]*,[[:space:]]*$SECRET_Q)"
SECRET_USER="(^|[^A-Za-z0-9_-])(-[uU]$SECRET_SEP?|--(proxy-)?user$SECRET_SEP)[^[:space:]:\"'\\\\]{0,255}[^[:space:]:\"'\\\\]?:"
# curl's cookie option (-b, --cookie), up to its value, and up to the quote its value opens with
SECRET_COOKIE_OPT="(^|[^A-Za-z0-9_-])(-b$SECRET_SEP?|--cookie$SECRET_SEP)"
SECRET_COOKIE_OPTQ="(^|[^A-Za-z0-9_-])(-b([[:space:]]+|=|($SECRET_Q)?[[:space:]]*,[[:space:]]*)?|--cookie([[:space:]]+|=|($SECRET_Q)?[[:space:]]*,[[:space:]]*))$SECRET_Q"
# A quoted value with no whitespace, 8 or more characters, assigned or given to a credential option
SECRET_QUOTED="$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[^[:space:]\"']{8,}[\"']|$SECRET_OPT([[:space:]]+|($SECRET_Q)?[[:space:]]*,[[:space:]]*)$SECRET_Q[^-[:space:]\"'][^[:space:]\"']{7,}[\"']"
# The rules are ASCII, read byte by byte (LC_ALL=C, in a subshell): a multibyte locale sends some of them to a matcher whose time grows with the square of the text
# secret_held TEXT: status 0 when TEXT holds, as written, the value of AUDIT_HMAC_KEY (the key the plugin's audit log is
# signed with) or of SECRET_HELD (a value the calling hook holds itself), 4 characters or more: a host recognises the
# credentials it holds itself (STANDARD 1.2.0 §6.7)
secret_held() (
  for SECRET_VALUE in "${AUDIT_HMAC_KEY:-}" "${SECRET_HELD:-}"; do
    [ "${#SECRET_VALUE}" -ge 4 ] || continue
    case "$1" in *"$SECRET_VALUE"*) return 0 ;; esac
  done
  return 1
)
# secret_decoded TEXT: TEXT with the JSON escapes some encoders write for characters the rules read decoded, \u0022 and
# \u0027 as an escaped quote (\" and \'), \u0026, \u002b, \u003c, \u003d and \u003e (Go's, Gson's and .NET's HTML-safe
# escapes, in either case) as the character, and \/ (PHP's) as /; the SDK's and the TypeScript rules decode the same
secret_decoded() (
  LC_ALL=C
  export LC_ALL
  printf '%s' "$1" | sed -e 's/\\u0022/\\"/g' -e "s/\\\\u0027/\\\\'/g" -e 's/\\u0026/\&/g' -e 's/\\u002[bB]/+/g' \
    -e 's/\\u003[cC]/</g' -e 's/\\u003[dD]/=/g' -e 's/\\u003[eE]/>/g' -e 's#\\/#/#g'
)
secret_values() (
  LC_ALL=C
  export LC_ALL
  case "$1" in
    *'\u00'* | *'\/'*)
      SECRET_TEXT="$(secret_decoded "$1")" || { echo '(unread)'; return 0; }
      set -- "$SECRET_TEXT"
      ;;
  esac
  printf '%s' "$1" | grep -Eo -- "$SECRET_SPACED"
  printf '%s' "$1" | grep -Eio -- "$SECRET_QUOTED"
  # An Authorization header's value, 8 or more characters with letters and digits
  printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}" |
    sed -E "s/^[^:=]*[:=][[:space:]]*(\\\\*[\"'])?//" |
    sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
    grep -E '[0-9]' | grep -E '[A-Za-z]'
  # ... or after any other scheme (ApiKey, SSWS, Bot) and spaces: the first word may be the scheme or the credential, so both readings count
  printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?[A-Za-z][A-Za-z0-9._-]* +[A-Za-z0-9._~+/=-]{8,}" |
    sed -E 's/^.* //' | grep -E '[0-9]' | grep -E '[A-Za-z]'
  # A header's or credential's value given as a name/value pair, or a tuple of exactly two, in text: 8 or more characters with letters and digits
  printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"'\\\\]*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"'\\\\]*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
    sed -E "s/\\\\*[\"'][[:space:]]*[])]\$//; s/^.*[:=,][[:space:]]*\\\\*[\"']//" |
    sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
    grep -E '[0-9]' | grep -E '[A-Za-z]'
  # ... and the same after any other scheme
  printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"'\\\\]*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[A-Za-z][A-Za-z0-9._-]* +[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"'\\\\]*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q[A-Za-z][A-Za-z0-9._-]* +[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
    sed -E "s/\\\\*[\"'][[:space:]]*[])]\$//; s/^.* //" |
    grep -E '[0-9]' | grep -E '[A-Za-z]'
  # A user option's password (curl -u user:password), 8 or more characters with letters and digits
  printf '%s' "$1" | grep -Eo -- "$SECRET_USER[^[:space:]\"'\\\\]{8,}" |
    sed -E 's/^[^:]*://' | grep -E '[0-9]' | grep -E '[A-Za-z]'
  # An unquoted value of 12 or more characters with letters and digits, assigned or given to a credential option
  printf '%s' "$1" | grep -Eio -- "$SECRET_OPT[[:space:]]+[^-[:space:]\"'][^[:space:]\"']{11,}" |
    sed -E 's/^.*[[:space:]]//' | grep -E '[0-9]' | grep -E '[A-Za-z]'
  printf '%s' "$1" | grep -Eio -- "$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*[^[:space:]\"']{12,}" |
    sed -E 's/^[^:=]*[:=][[:space:]]*//' | grep -E '[0-9]' | grep -E '[A-Za-z]'
  # A .netrc entry's password (machine <host> login <user> password <value>), 8 or more characters with letters and digits
  printf '%s' "$1" | grep -Eo -- "(^|[^A-Za-z0-9_-])(machine|login|account|default)[[:space:]]+([^[:space:]]+[[:space:]]+)?password[[:space:]]+[^[:space:]\"']{8,}" |
    sed -E 's/^.*[[:space:]]//' | grep -E '[0-9]' | grep -E '[A-Za-z]'
  # A cookie (name=value) in a Cookie or Set-Cookie header's value (to the end of its line or its closing quote), or in
  # curl's cookie option's value (holding a name and = in its first 64 characters; quoted, or to a blank): a value of 8 or
  # more token characters with letters and digits, a Set-Cookie attribute aside
  {
    printf '%s' "$1" | grep -Eio -- "(set-)?cookie($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?[^[:space:]\"'\\\\][^[:cntrl:]\"'\\\\]*" |
      sed -E "s/^[^:=]*[:=][[:space:]]*(\\\\*[\"'])?//"
    printf '%s' "$1" | grep -Eo -- "$SECRET_COOKIE_OPTQ[^[:cntrl:]\"'\\\\=]{0,64}=[^[:cntrl:]\"'\\\\]*" |
      sed -E "s/^.?(-b|--cookie)([[:space:]]+|=|(\\\\*[\"'])?[[:space:]]*,[[:space:]]*)?\\\\*[\"']//"
    printf '%s' "$1" | grep -Eo -- "$SECRET_COOKIE_OPT[^[:space:]\"'\\\\=]{0,64}=[^[:space:]\"'\\\\]*" |
      sed -E "s/^(.?-b|.?--cookie)([[:space:]]+(\\\\*[\"'])?|=(\\\\*[\"'])?|(\\\\*[\"'])?[[:space:]]*,[[:space:]]*\\\\*[\"'])?//"
  } | tr ';, ' '\n\n\n' | grep -E '^[^=]*=' | grep -Eiv '^(path|domain|expires|max-age|samesite|secure|httponly|partitioned|priority)=' |
    sed -E 's/^[^=]*=//' | grep -Ex '[A-Za-z0-9._~+/=%-]{8,}' | grep -E '[0-9]' | grep -E '[A-Za-z]'
  return 0
)
secret_lines() (
  LC_ALL=C
  export LC_ALL
  secret_held "$1" && return 0
  SECRET_TEXT="$1"
  case "$1" in
    *'\u00'* | *'\/'*) SECRET_TEXT="$(secret_decoded "$1")" || return 0 ;;
  esac
  printf '%s' "$SECRET_TEXT" | grep -Eq -- "$SECRET_ERE" && return 0
  # The password of a URL's userinfo, unless it is a placeholder (its scheme read from the start of its run, once; its
  # slashes escaped or not)
  printf '%s' "$SECRET_TEXT" | grep -Eo -- '(^|[^A-Za-z0-9+.-])[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*:(\\*/){2}[^[:space:]/:@]*:[^[:space:]/@]+@' |
    sed -E 's#^.*/[^:]*:##; s#@$##' | grep -Eivq -- '^([$<{*[].*|password|passwd|pwd|pass|secret|token)$' && return 0
  # The rules that read a quoted value, or a value out of a match
  secret_values "$1" | grep -q .
)
secret_in() (
  secret_lines "$1" && return 0
  SECRET_FOLDED="$(printf '%s' "$1" | LC_ALL=C tr '\n\r' '  ')" || return 0
  [ "$SECRET_FOLDED" != "$1" ] && secret_lines "$SECRET_FOLDED"
)
# END secret-scan

# BEGIN plain-name (the same in the pre-tool-use hook and the log hook; tests/test_hooks_unit.py keeps them so)
# A tool's or a skill's name as a record or a diagnostic shows it (STANDARD
# 1.2.0 §6.7, §6.4, §9.8): the model chooses a skill's name (an MCP skill
# address is any text after a server's name), and an MCP server its tools'.
# The name itself when it is 1 to 128 ASCII letters, digits, `.`, `_`, `:`
# or `-` and the secret scan (secret_in) finds no credential in it; else
# [REDACTED], the whole name: a digest of a name that is a secret alone could
# be inverted by guessing. A scan that cannot answer (no grep: a status other
# than 0 or 1) counts as one that found a credential. Claude Code's own
# tools' names, which hold none, are shown without the scan's time.
plain_name() {
  local status=0
  case "$1" in
    Bash | Read | Write | Edit | MultiEdit | NotebookEdit | Glob | Grep | LS | WebFetch | WebSearch | Skill | Agent | Task | TodoRead | TodoWrite | TaskList | TaskGet | TaskCreate | TaskUpdate | TaskOutput | BashOutput | ToolSearch | ExitPlanMode | AskUserQuestion)
      printf '%s' "$1"
      return 0
      ;;
  esac
  if (LC_ALL=C; [[ "$1" =~ ^[A-Za-z0-9._:-]{1,128}$ ]]); then
    (set +o pipefail; secret_in "$1") || status=$?
    if [ "$status" = 1 ]; then
      printf '%s' "$1"
      return 0
    fi
  fi
  printf '%s' '[REDACTED]'
}
# END plain-name

# key_file_refusal FILE: why FILE cannot hold the audit key (the rules in
# the header), printed; nothing when it can. The owner, the permission bits
# and the link count come from stat, GNU's form tried first and BSD's next
# (PATH may hold either); an answer in neither form refuses the file.
key_file_refusal() {
  local file="$1" dir uid stats owner mode links kdir proj
  dir="${file%/*}"
  if [ -L "$file" ]; then
    printf 'it is a symbolic link'
    return 0
  fi
  if [ ! -f "$file" ]; then
    printf 'it is not a regular file'
    return 0
  fi
  uid=$(id -u 2>/dev/null) || uid=""
  if [[ ! "$uid" =~ ^[0-9]+$ ]]; then
    printf 'the user the hook runs as could not be read (id -u)'
    return 0
  fi
  stats=$(stat -c '%u %a %h' -- "$file" 2>/dev/null) \
    || stats=$(stat -f '%u %Lp %l' -- "$file" 2>/dev/null) || stats=""
  if [[ ! "$stats" =~ ^([0-9]+)\ ([0-7]{3,4})\ ([0-9]+)$ ]]; then
    printf 'its owner, mode and link count could not be read (stat)'
    return 0
  fi
  owner="${BASH_REMATCH[1]}"
  mode="${BASH_REMATCH[2]}"
  links="${BASH_REMATCH[3]}"
  if [ "$owner" != "$uid" ]; then
    printf 'it is owned by user %s, not by the user the hook runs as (%s)' "$owner" "$uid"
  elif [ "${mode: -2}" != "00" ]; then
    printf 'its mode is %s: group or others may read or write it (chmod 600)' "$mode"
  elif [ "$links" != 1 ]; then
    printf 'it has %s hard links: another name for it may be readable where the key is not denied' "$links"
  elif [ -L "$dir" ]; then
    # stat reports a link itself, not its directory, and a deny rule names
    # the path, not where the link leads.
    printf 'its directory is a symbolic link'
  elif [ ! -d "$dir" ]; then
    printf 'its directory is not a directory'
  else
    stats=$(stat -c '%u %a' -- "$dir" 2>/dev/null) \
      || stats=$(stat -f '%u %Lp' -- "$dir" 2>/dev/null) || stats=""
    if [[ ! "$stats" =~ ^([0-9]+)\ ([0-7]{3,4})$ ]]; then
      printf 'the owner and mode of its directory could not be read (stat)'
    elif [ "${BASH_REMATCH[1]}" != "$uid" ]; then
      printf 'its directory is owned by user %s, not by the user the hook runs as (%s)' "${BASH_REMATCH[1]}" "$uid"
    elif (( 8#${BASH_REMATCH[2]} & 8#022 )); then
      printf 'its directory'"'"'s mode is %s: group or others may replace the file (chmod 700)' "${BASH_REMATCH[2]}"
    else
      # The sandbox lets the agent's commands write the project directory:
      # a key there is one they can replace. Both as the system resolves
      # them, so a link on the way is seen.
      kdir=$(cd -P -- "$dir" 2>/dev/null && pwd) || kdir=""
      proj=$(cd -P -- "$project_dir" 2>/dev/null && pwd) || proj=""
      if [ -z "$kdir" ]; then
        printf 'its directory could not be resolved (cd -P)'
      elif [ -n "$proj" ]; then
        case "$kdir/" in
          "${proj%/}"/*) printf 'its directory is inside the project directory (%s), which the agent'"'"'s commands may write' "$proj" ;;
        esac
      fi
    fi
  fi
  return 0
}

# key_file_id FILE: FILE's device and inode, as stat prints them, GNU's
# form first; nothing when stat cannot say.
key_file_id() {
  stat -c '%d %i' -- "$1" 2>/dev/null || stat -f '%d %i' -- "$1" 2>/dev/null || true
}

# The HMAC key, and why there is none (key_note) when hmac_key is empty.
hmac_key=""
key_note=""
key_file=""
case "${HOME:-}" in
  /*) key_file="${HOME%/}/.config/acs/audit.key" ;;
esac
if ! command -v openssl &> /dev/null; then
  key_note="openssl is not installed"
elif [ -n "$key_file" ] && { [ -e "$key_file" ] || [ -L "$key_file" ]; }; then
  refusal=$(key_file_refusal "$key_file")
  if [ -z "$refusal" ]; then
    # The file read must be the file checked: its identity, and the rules,
    # are taken again after the read, and a file put in its place is
    # refused. (bash cannot check the file it opened, as the verifier does
    # with fstat, so a swap and a swap back within the read go unseen.)
    key_id=$(key_file_id "$key_file")
    file_key=""
    IFS= read -r file_key < "$key_file" 2>/dev/null || true
    if [ -z "$key_id" ] || [ "$(key_file_id "$key_file")" != "$key_id" ] \
      || [ -n "$(key_file_refusal "$key_file")" ]; then
      file_key=""
      refusal="it was replaced while it was read"
    fi
  fi
  if [ -z "$refusal" ]; then
    # (A count in the pattern: BSD's regcomp, macOS bash 3.2's, refuses one
    # over 255.)
    if (LC_ALL=C; [[ "$file_key" =~ ^[!-~]+$ ]] && (( ${#file_key} >= 32 && ${#file_key} <= 4096 ))); then
      hmac_key="$file_key"
    else
      refusal="its first line is not a key of 32 to 4096 visible ASCII characters"
    fi
    file_key=""
  fi
  if [ -n "$refusal" ]; then
    key_note="the key file $key_file is refused: $refusal (AUDIT_HMAC_KEY is not used in its place)"
  fi
elif [ -n "${AUDIT_HMAC_KEY:-}" ]; then
  hmac_key="$AUDIT_HMAC_KEY"
else
  key_note="no audit key: there is no ${key_file:-~/.config/acs/audit.key (HOME is not an absolute path)} and AUDIT_HMAC_KEY is not set (hooks/README.md says how to make the key file)"
fi

# The key read is a credential the hook holds (STANDARD 1.2.0 §6.7):
# plain_name redacts a tool or skill name that holds it, as it does one
# that holds AUDIT_HMAC_KEY, so the signed line never carries its own key.
if [ -n "$hmac_key" ]; then
  SECRET_HELD="$hmac_key"
fi

# The tool's name, and a Skill call's skill name (recorded for a Skill call
# only), as plain_name shows them: the line is signed, so a secret written
# into it could not be taken out without breaking the chain.
shown_tool=$(plain_name "$tool_name")
skill=""
if [[ "$tool_name" == "Skill" ]]; then
  skill=$(printf '%s' "$input" | jq -r '.tool_input.skill | strings' 2>/dev/null || echo "")
  if [ -n "$skill" ]; then
    skill=$(plain_name "$skill")
  else
    skill="unknown"
  fi
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
# still written, and the input is still left out. So is the digest of text that
# is no JSON: jq prints a value nested past its print limit as `<skipped: too
# deep>`, and a jq whose parser accepts deeper nesting than it prints (the
# limits differ between jq versions) would otherwise digest that cut text,
# which stands for no one input.
input_sha256="unavailable"
if input_canonical=$(printf '%s' "$input" | jq -cS '.tool_input' 2>/dev/null) &&
  printf '%s' "$input_canonical" | jq empty > /dev/null 2>&1; then
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

log_dir="${project_dir}/.claude"
mkdir -p "$log_dir"

log_file="$log_dir/audit.log"
head_file="$log_dir/audit.head"

# The head's anchor: the same head, kept in the project's git directory
# (<git dir>/acs/audit.head), outside the directory a project command removes
# whole (git clean -fdx, rm -rf .claude): a log and head removed together
# leave it, and it shows the cut. Only in a git directory git made for a
# work tree (a .git directory, or a linked worktree's or a submodule's under
# one: any other may be repository content), asked with core.fsmonitor and
# hooks turned off, for at most 5 seconds (a git that did not answer is
# said below), its answer read exactly (the x keeps the line breaks that may
# end a directory's name from the command substitution); none without git or
# a repository.
anchor_file=""
anchor_unkept=0
anchor_git_status=0
if command -v git &> /dev/null; then
  anchor_git=$(GIT_NO_LAZY_FETCH=1 bounded git -c core.fsmonitor=false -c core.hooksPath=/dev/null -C "$project_dir" rev-parse --absolute-git-dir 2>/dev/null && printf x) || anchor_git_status=$?
  if [ "$anchor_git_status" = 0 ]; then
    anchor_git="${anchor_git%x}"
    anchor_git="${anchor_git%$'\n'}"
  else
    # 128: no repository there. Any other answer (git stopped at its time
    # bound): said below.
    [ "$anchor_git_status" = 128 ] || anchor_unkept=2
    anchor_git=""
  fi
  case "$anchor_git" in
    */.git | */.git/worktrees/* | */.git/modules/*)
      if (umask 077 && mkdir -p "$anchor_git/acs") 2>/dev/null && [ ! -L "$anchor_git/acs" ]; then
        anchor_file="$anchor_git/acs/audit.head"
      else
        # A link there, or a directory that cannot be made: said below.
        anchor_unkept=1
      fi
      ;;
  esac
fi

# SEC-006: Reject symlinked audit log to prevent log redirection attacks
if [ -L "$log_file" ]; then
  fail "audit.log is a symlink (refused, SEC-006)"
fi

# Build log entry with timestamp
ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
action_id="$call_id"
if [[ -z "$action_id" ]]; then
  rand=$(od -An -N4 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n' || true)
  action_id="${ts}-$$-${rand:-00000000}"
fi

# BEGIN hmac-sha256 (source: hooks/hmac_sha256.sh; tests/test_hmac_sha256.py keeps every copy equal)
# HMAC-SHA-256 (RFC 2104) built on openssl's SHA-256, so that the key is on
# no command line: `openssl dgst -hmac KEY` would put the key in the process
# list, which any process of the user can read. The key and the pads reach
# od and openssl only through a pipe from the shell's builtin printf. It is
# POSIX sh (the rollback skill's hook runs under sh), so it has no local
# variables: every name it sets starts with hmac_.
# hmac_pads KEY: sets hmac_ipad and hmac_opad from KEY (hashed first when it
# is over 64 bytes, then padded with zero bytes to 64 bytes), XOR 0x36 and
# XOR 0x5c, as printf escapes (\ooo): a variable cannot hold a zero byte.
# Status 1, with both empty, for an empty key or when od, awk or openssl
# fails.
# hmac_hex: prints the HMAC-SHA-256, in hex, of standard input under the key
# hmac_pads was given last. Status 1, printing nothing, when openssl fails.
hmac_ipad=""
hmac_opad=""
hmac_pad_awk() {
  awk '
    function xor8(a, c, r, p) {
      r = 0
      for (p = 1; p < 256; p *= 2) if (int(a / p) % 2 != int(c / p) % 2) r += p
      return r
    }
    { for (f = 1; f <= NF; f++) b[n++] = $f + 0 }
    END {
      if (n > 64) { print "long"; exit }
      i = ""
      o = ""
      for (k = 0; k < 64; k++) {
        v = (k < n) ? b[k] : 0
        i = i sprintf("\\%03o", xor8(v, 54))
        o = o sprintf("\\%03o", xor8(v, 92))
      }
      print n + 0, i, o
    }'
}
hmac_pads() {
  hmac_ipad=""
  hmac_opad=""
  hmac_pad=$(printf '%s' "$1" | od -An -v -tu1 | hmac_pad_awk) || hmac_pad=""
  if [ "$hmac_pad" = long ]; then
    hmac_pad=$(printf '%s' "$1" | openssl dgst -sha256 -binary 2>/dev/null | od -An -v -tu1 | hmac_pad_awk) || hmac_pad=""
    case "$hmac_pad" in "32 "*) ;; *) hmac_pad="" ;; esac
  fi
  case "$hmac_pad" in
    "" | "0 "* | *[!0-9\ \\]*) hmac_pad="" ;;
  esac
  hmac_pad=${hmac_pad#* }
  hmac_ipad=${hmac_pad% *}
  hmac_opad=${hmac_pad#* }
  hmac_pad=""
  if [ "${#hmac_ipad}" != 256 ] || [ "${#hmac_opad}" != 256 ]; then
    hmac_ipad=""
    hmac_opad=""
    return 1
  fi
}
hmac_hex() {
  [ -n "$hmac_ipad" ] || return 1
  # shellcheck disable=SC2059 # the pads are escapes for printf to expand
  hmac_inner=$({ printf "$hmac_ipad"; cat; } | openssl dgst -sha256 -binary 2>/dev/null | od -An -v -tu1 | awk '{ for (f = 1; f <= NF; f++) printf "\\%03o", $f }') || hmac_inner=""
  [ "${#hmac_inner}" = 128 ] || return 1
  # shellcheck disable=SC2059
  hmac_out=$({ printf "$hmac_opad"; printf "$hmac_inner"; } | openssl dgst -sha256 -binary 2>/dev/null | od -An -v -tx1 | tr -d ' \n') || hmac_out=""
  case "$hmac_out" in *[!0-9a-f]*) return 1 ;; esac
  [ "${#hmac_out}" = 64 ] || return 1
  printf '%s' "$hmac_out"
}
# END hmac-sha256

if [ -n "$hmac_key" ] && ! hmac_pads "$hmac_key"; then
  hmac_key=""
  key_note="the key could not be prepared for signing (od or openssl failed)"
fi

# Append the line. Returns 0 when it was written with a valid chain link and
# the head moved to it, 3 when it was written but starts a new chain (the
# last line's hmac could not be read), 4 when it was written but the head
# was not moved (said on standard error), 5 when it was written unsigned (no
# key, or no openssl: key_note says which), and 1 when nothing was written
# (the line could not be built or signed).
_do_append() {
  # Get previous entry's HMAC for chaining (empty string for first entry)
  local prev_hmac="" broken=0 entries=0
  if [ -f "$log_file" ]; then
    entries=$(awk 'END { print NR }' "$log_file" 2>/dev/null) || entries=""
    [[ "$entries" =~ ^[0-9]{1,12}$ ]] || entries=""
  fi

  # The head and its anchor: does the log still hold the entry each
  # records, at its place? ok: yes, or no head, no anchor and no entry yet;
  # new: neither for a log that has entries (begun before the hook kept
  # one); cut: no, for either, or one this key did not sign, or one that
  # cannot be read (a log removed with its head, the anchor left); held:
  # one cannot be written.
  # Without a key (unsigned) neither is read nor moved: a head cannot be
  # checked or signed with no key.
  local head_state="ok" head_entries="" head_hmac_recorded="" kept=0 file
  [ -n "$hmac_key" ] || head_state="unsigned"
  for file in "$head_file" "$anchor_file"; do
    [ -n "$file" ] || continue
    [ "$head_state" != "unsigned" ] || break
    if [ -L "$file" ] || { [ -e "$file" ] && [ ! -f "$file" ]; }; then
      [ "$head_state" = "cut" ] || head_state="held"
    elif [ -f "$file" ]; then
      kept=1
      local head_line head_sig recorded_entries recorded_hmac file_state="cut"
      head_line=""
      IFS= read -r -n 4096 head_line < "$file" 2>/dev/null || true
      recorded_entries=$(printf '%s' "$head_line" | jq -r '.entries | numbers | tostring' 2>/dev/null) || recorded_entries=""
      recorded_hmac=$(printf '%s' "$head_line" | jq -r '.hmac | strings' 2>/dev/null) || recorded_hmac=""
      head_sig=$(printf '%s' "$head_line" | jq -r '.head_hmac | strings' 2>/dev/null) || head_sig=""
      if [[ "$recorded_entries" =~ ^[1-9][0-9]{0,11}$ && "$recorded_hmac" =~ ^[0-9a-f]{64}$ ]] \
        && [ "$head_sig" = "$(printf 'acs-audit-head:%s:%s' "$recorded_entries" "$recorded_hmac" | hmac_hex)" ] \
        && [[ -n "$entries" ]] && (( 10#$entries >= 10#$recorded_entries )); then
        local held_hmac
        held_hmac=$(awk -v n="$recorded_entries" 'NR == n { print; exit }' "$log_file" 2>/dev/null | jq -r '.hmac | strings' 2>/dev/null) || held_hmac=""
        [ "$held_hmac" = "$recorded_hmac" ] && file_state="ok"
      fi
      if [ "$file_state" = "cut" ]; then
        head_state="cut"
        head_entries="$recorded_entries"
        head_hmac_recorded="$recorded_hmac"
      fi
    fi
  done
  if [ "$head_state" = "ok" ] && [ "$kept" = 0 ] && [[ "$entries" != "0" ]]; then
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
    --arg tool "$shown_tool" \
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

  # Unsigned without a key: the hmac is empty (never an HMAC under an empty
  # key, which anyone could compute).
  local entry_hmac=""
  if [ -n "$hmac_key" ]; then
    entry_hmac=$(printf '%s' "$entry_content" | hmac_hex) || entry_hmac=""
    if [[ ! "$entry_hmac" =~ ^[0-9a-f]{64}$ ]]; then
      return 1
    fi
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
    unsigned) return 5 ;;
    cut)
      echo "posttooluse_log_tool: audit.log no longer holds the entry its head records, or the head's anchor (${anchor_file:-none}) does (entry ${head_entries:-?} of the log, hmac ${head_hmac_recorded:-?}; the log had ${entries:-?} lines), or one is not a head this key signed: entries, or the log with its head, were removed or changed. The head and the anchor are kept as the evidence; to start a new log, move audit.log, audit.head and the anchor aside together" >&2
      head_problem=1
      ;;
    held)
      echo "posttooluse_log_tool: audit.head or its anchor (${anchor_file:-none}) is a symlink or not a regular file (refused, SEC-006); the log's end is not anchored" >&2
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
      local anchor_tmp="" anchored=1
      if [ -n "$anchor_file" ]; then
        anchor_tmp="${anchor_file%/*}/.audit.head.$$"
        anchored=0
        if [[ "$sig" =~ ^[0-9a-f]{64}$ ]] \
          && (set -C; printf '{"entries":%s,"hmac":"%s","head_hmac":"%s"}\n' "$written" "$last_hmac" "$sig" > "$anchor_tmp") 2>/dev/null \
          && mv -f "$anchor_tmp" "$anchor_file" 2>/dev/null; then
          anchored=1
        else
          rm -f "$anchor_tmp" 2>/dev/null || true
        fi
      fi
      if (( anchor_unkept == 2 )); then
        echo "posttooluse_log_tool: git did not say in time which git directory is the project's (exit ${anchor_git_status}; one whose configuration includes a FIFO or a terminal holds git), so the head's anchor is not kept; a log removed with its head may not be seen" >&2
        head_problem=1
      elif (( anchor_unkept )); then
        echo "posttooluse_log_tool: the git directory's acs/ is a symlink or cannot be made, so the head's anchor is not kept; a log removed with its head may not be seen" >&2
        head_problem=1
      fi
      if (( ! anchored )); then
        echo "posttooluse_log_tool: the head's anchor (${anchor_file}) could not be written; a log removed with its head may not be seen" >&2
        head_problem=1
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
    echo "posttooluse_log_tool: the last line of audit.log has no readable hmac (it is unsigned, or was written before Standard 1.2); this line starts a new chain" >&2
    exit 1
    ;;
  4) exit 1 ;;
  5)
    echo "posttooluse_log_tool: ${key_note}; this tool call was logged unsigned, and the log's head was not moved" >&2
    exit 1
    ;;
  *) fail "the log line could not be built or written" ;;
esac

if [[ "$input_sha256" == "unavailable" ]]; then
  echo "posttooluse_log_tool: the input digest could not be computed; the line says \"unavailable\"" >&2
  exit 1
fi

exit 0
