#!/bin/sh
# Claude Code starts this hook with the env of the project's settings files
# applied (repository content, project_layer_settings below): it runs under
# bash -p, which reads no BASH_ENV or ENV file, imports no shell function and
# ignores SHELLOPTS, BASHOPTS, CDPATH and GLOBIGNORE, and starts itself so
# when started another way (as /bin/sh, bash reads none of them either).
case $- in *p*) ;; *) exec bash -p "$0" "$@" ;; esac
# Apply the checkpoint and approval rules of STANDARD 1.2.0 §5.18 to every
# tool call, as a PreToolUse command hook (hooks.json routes every tool here,
# with onFailure "block": a run that fails, or gives no verdict in time,
# blocks the call where Claude Code supports that setting).
#
# Claude Code passes the tool call as a JSON object on stdin:
# {"tool_name", "tool_input", "permission_mode", "tool_use_id", "cwd", ...}.
# For manual use, a payload given as the first argument is read instead. Only
# that JSON object is read: anything else, or a system without jq, is blocked
# with R407 SAFETY_CHECK_FAILED.
#
# Its settings (ACS_HOOK_APPROVAL, ACS_CHECKPOINT_MAX_AGE; the log hook's
# AUDIT_HMAC_KEY and AUDIT_LOCK_WAIT) come from its environment, where Claude
# Code also puts the env of the project's .claude/settings.json and
# .claude/settings.local.json, repository content, over the user's settings,
# as it does for every command it runs: while either file sets a variable
# there that is not Claude Code's own (one of the layer's settings, or one
# that changes what a hook or a command runs: BASH_ENV, SHELLOPTS, PATH,
# HOME, LD_PRELOAD, GIT_CONFIG_*, ...), or cannot be read, every call is
# blocked with R407 SAFETY_CHECK_FAILED (project_layer_settings).
#
# Exit codes follow Claude Code's hook contract:
#   0  allow the tool call (with an "ask" decision on stdout for a gated call)
#   2  block it; the reason on stderr is shown to Claude
#
# Each reason opens with the Standard's code and name (§9.8), for example
# "F501 CHECKPOINT_REQUIRED: ...".
#
# Classification (§5.18.3). The lists below are subsets of the SDK mapper's
# (grounded_agency/capabilities/mapper.py: _TOOL_MAPPINGS, _READ_ONLY_COMMANDS,
# _GIT_STASH_CLASSES, _writes); a test keeps them so.
#   - A tool on UNGATED_TOOLS (the mapper's tools whose capability needs
#     neither a checkpoint nor approval: Read, Grep, TodoWrite, ...):
#     allowed, nothing used; except that a tool on PERSIST_TOOLS (the
#     mapper's tools whose capability is persist: TodoWrite, TaskCreate,
#     TaskUpdate) whose input holds a secret the layer recognises is refused
#     (below).
#   - Write, Edit, MultiEdit, NotebookEdit: mutate.
#   - Skill, Agent, Task: mutate. Claude Code runs the shell commands a
#     skill's file embeds (!`cmd` and ```! blocks, with the call's arguments
#     substituted into them) when the skill loads, under the skill's
#     allowed-tools, and the hooks and MCP servers a subagent's definition
#     names when the subagent runs, with no PreToolUse or PostToolUse event:
#     no hook sees those commands, and any skill or agent name may be a
#     project's (a project's definition replaces a built-in one of the same
#     name), so the call takes the worst case (§5.18.3).
#   - Bash: a command over 4096 bytes is not read: mutate (checked first, so
#     no reading of it can run long). A command with any of ; & | < > $ ` ( )
#     { } \ or a line break may be more than one simple command or expand
#     something: mutate. Otherwise its words are read as bash reads them, as
#     exactly one simple command (split_words: '...' and "..." quote, and the
#     quotes are removed, so "--output=x" is --output=x; an unbalanced quote
#     is mutate):
#       - an option that writes: for git, --output or any abbreviation of it
#         (--out, --outp, ...); for file, -C in any short option cluster, -p,
#         or --compile or --preserve-date or any abbreviation of them
#         (--compi); for printf, any option (a first argument starting with
#         -: printf -v NAME sets a shell variable); and, for git, file and
#         printf, a word with an unquoted *, ? or [, which bash replaces with
#         file names, options included: mutate;
#       - any git stash form where the git directory git finds is not one git
#         made for a work tree (git_dir_is_content: git runs what that
#         directory's configuration names): mutate;
#       - git stash create: checkpoint (allowed; posttooluse_take_checkpoint.sh
#         writes the marker once it succeeded), but where the repository's
#         own configuration or hooks name a program git runs
#         (git_runs_configured): checkpoint-ask, put to a person with no
#         marker asked for (only this command makes one; F502 in a mode that
#         asks no one); git stash list|show: observe (mutate where a git
#         read may do more, below);
#         git stash pop|apply <commit>: rollback when <commit> is the full id
#         of a commit posttooluse_take_checkpoint.sh entered, signed, in the
#         project's git directory (<git dir>/acs/checkpoints/commits/, a
#         lookup of one file however many checkpoints were taken), the call
#         runs in the project's repository (its cwd), the repository's
#         own configuration and hooks name no program git runs, and no
#         scope configures a filter's smudge or process command (but the
#         two `git lfs install --skip-smudge` writes) that writing the tree
#         would run (git_filter_runs: git-lfs's asks the LFS server the
#         repository names for each object its store lacks); any other
#         pop or apply, a bare one included, is mutate, since git applies
#         any merge commit as if it were a stash; any other git stash form:
#         mutate;
#       - a first word holding a blank (a quoted "git status") or a slash:
#         bash runs the program of that name, which is on no list: mutate;
#       - a first word whose program, as bash finds it on the PATH the
#         agent's commands run with, may be the repository's own (found
#         under an empty or relative entry, in a file in the project, or
#         nowhere: command_may_be_content): mutate, before any class below;
#       - a command on READ_ONLY (a one-word entry the first word, a two-word
#         entry the first word and the second): observe (allowed, nothing
#         used), except a
#         git command where a git read may do more than read the repository's
#         own state (git_read_gated: the git directory is not one git made
#         for a work tree, the repository's own configuration or hooks name
#         a program git runs, a partial clone, a repository with submodules,
#         or git cannot say): mutate;
#       - anything else: mutate.
#   - Any other tool (Monitor, PowerShell, ExitWorktree, every MCP tool, a
#     tool this hook does not know): unbound, so mutate (§5.18.2: a layer
#     cannot know that an unknown tool only reads).
#
# Rules.
#   - persist (§5.18.10, §6.7): the data a call of a tool on PERSIST_TOOLS
#     would store holds no secret the layer recognises: the shared scan's
#     credential shapes (hooks/secret_scan.sh, copied below), read in every
#     string of its input and in the input's JSON text, and the SDK
#     redactor's rule for data (SECRET_MEMBER_JQ: a value under a member
#     named for a credential). Refused, not redacted, since memory is read
#     back as fact (F504 CONSTRAINT_VIOLATED), whatever the permission mode;
#     the SDK adapter refuses the same calls.
#   - rollback: restores a checkpoint this project recorded, so a checkpoint
#     was taken; allowed, and it uses none. (F503 ROLLBACK_FAILED cannot
#     arise: a restore of anything else is mutate.) The commits are entered
#     in the git directory, outside the work tree, so no clone, checkout or
#     applied stash can ship an entry; and each entry holds an HMAC of its
#     commit under a key the take hook drew at random and keeps there
#     (<git dir>/acs/checkpoints/key), so a file a command creates there,
#     through a link the repository ships for instance, is no entry.
#   - mutate: a call whose arguments name the layer's own records
#     (checkpoint.ok, .claude/checkpoints/, acs/checkpoints/, audit.head, in
#     any letter case and with //, ./ and x/../ read as a path reads them, or
#     through a symbolic link, a ~ the shell expands, a brace group it
#     expands, a $'...' it decodes or a path attached to a short option: each
#     path a text of at most 4096 bytes names is resolved as the system
#     resolves a path), or the directory that holds them (the
#     project's .claude, its git directory's acs/), is refused (F504
#     CONSTRAINT_VIOLATED): only these hooks write them. The texts read are
#     a file tool's path, a Bash command and a Skill call's arguments, and
#     every string and member name of any other tool's input but Agent's
#     and Task's (an MCP filesystem server's path, a shell server's
#     command). Then the
#     marker (.claude/checkpoint.ok, a JSON object with checkpoint_id,
#     created_at, expires_at) must exist, be a regular file that git does not
#     track (a repository can ship a tracked one) in a directory whose git
#     directory is one git made for a work tree, have times that are whole
#     seconds of at most 12 digits, a created_at not in the future and an
#     expires_at at most 1800 seconds (30 minutes, the Standard's cap) after
#     it, and be within both its expires_at and the layer's maximum age,
#     ACS_CHECKPOINT_MAX_AGE (1 to 1800 seconds, default 1800) after its
#     created_at (F501 CHECKPOINT_REQUIRED; a marker past either is filed
#     under .claude/checkpoints/ended/, and a malformed one is removed).
#     Unless ACS_HOOK_APPROVAL is "off", the permission mode must be one that
#     puts the call to a person, default, acceptEdits or plan (F502
#     APPROVAL_REQUIRED otherwise, with the marker left in place). Then the
#     call takes the marker: it is renamed into .claude/checkpoints/used/,
#     atomically, so two calls never both pass on one marker (F501 for the
#     one that loses). Unless ACS_HOOK_APPROVAL is "off", the hook then
#     answers permissionDecision "ask" with an F502 reason, so Claude Code
#     puts the call to the person.
#
# git runs here as hgit runs it: with core.fsmonitor and hooks turned off and
# no object fetched, so no repository content makes this hook run a program
# or reach a host, and for at most 5 seconds (bounded), so none holds it
# past its time limit: a git that did not answer cannot say, which blocks
# the call or gates it, never reads as "no repository".
#
# Scope (§5.18.5): the project directory, every session in it (one marker).
# Its execution boundaries are the ends and starts of turns and sessions
# (stop_end_checkpoints.sh, on Stop, StopFailure, UserPromptSubmit,
# SessionStart and SessionEnd).
#
# It fails closed: Claude Code treats any exit code other than 2 as a
# non-blocking error and runs the call unless onFailure is "block", so an
# unexpected failure here blocks the call with R407 instead of exiting with
# that command's status.
#
# The plugin's hooks do not claim class SL (spec/SECURITY.md §5.5).
#
# SEC-001: Prevents stale checkpoint.ok bypass
# SEC-006: Uses CLAUDE_PROJECT_DIR for absolute path resolution
set -euo pipefail
# Read the command as bytes, alike in every locale: a multibyte locale makes
# each character read in split_words several times slower.
export LC_ALL=C

block() {
  echo "$1" >&2
  exit 2
}
trap 'block "R407 SAFETY_CHECK_FAILED: the checkpoint hook failed at line $LINENO, so the call is blocked."' ERR

# SEC-006: Use absolute path via CLAUDE_PROJECT_DIR, fall back to CLAUDE_PLUGIN_ROOT, then pwd
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  project_dir="${CLAUDE_PROJECT_DIR}"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  project_dir="${CLAUDE_PLUGIN_ROOT}"
else
  project_dir="$(pwd)"
fi

# The PATH the agent's commands run with, before the block below narrows it
# for this hook's own programs: Claude Code gives each hook and each command
# it runs the same environment (command_may_be_content reads it).
agent_path="${PATH-}"

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

if [ "$#" -gt 0 ]; then
  payload="$1"
else
  payload="$(cat)"
fi

unreadable="R407 SAFETY_CHECK_FAILED: cannot read the tool call (a JSON payload and jq are required)"
if ! type -P jq > /dev/null 2>&1; then
  block "$unreadable"
fi
tool_name=$(printf '%s' "$payload" | jq -r 'if type == "object" then (.tool_name | strings) else error("not an object") end' 2>/dev/null) || tool_name=""
if [ -z "$tool_name" ]; then
  block "$unreadable"
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

# A setting, or any other variable, the repository may have chosen: every
# call is refused until it is set where the repository cannot reach
# (§5.18.8: the layer cannot complete its checks, nor sign the call's
# record, with a value it cannot trust, nor tell what a command does in an
# environment the repository chose).
named=$(project_layer_settings "$project_dir") || named="(unreadable)"
# Shown in the reason: the first 400 characters, one line, plain.
named="${named:0:400}"
named="${named//$'\n'/ }"
named="${named//[^A-Za-z0-9_.\/() ]/?}"
if [ -n "$named" ]; then
  block "R407 SAFETY_CHECK_FAILED: the project's settings files set variables in env that are not Claude Code's own (the layer's settings, or ones that change what a hook or a command runs: BASH_ENV, SHELLOPTS, PATH, HOME, LD_PRELOAD, GIT_CONFIG_*, ...), or cannot be read: ${named% }. Claude Code applies a project's env, which is repository content, over yours, to every hook and command it runs, so the call is blocked. Remove them from .claude/settings.json and .claude/settings.local.json, and set them in ~/.claude/settings.json, in managed settings or in the environment Claude Code starts in."
fi

# Tools whose calls need nothing from this hook: the SDK mapper's static
# mappings (_TOOL_MAPPINGS) whose capability needs neither a checkpoint nor
# approval (retrieve, search, observe, recall, persist, inquire). Every other
# tool but Bash is classified mutate, Skill, Agent and Task included (below).
UNGATED_TOOLS=(Read Glob Grep LS WebFetch WebSearch AskUser AskUserQuestion TodoRead TodoWrite TaskList TaskGet TaskCreate TaskUpdate ToolSearch BashOutput TaskOutput ListMcpResourcesTool ReadMcpResourceTool ExitPlanMode)

# The tools of UNGATED_TOOLS whose capability is persist (the mapper's
# _TOOL_MAPPINGS; a test keeps them so): what they store is scanned for
# secrets (§5.18.10).
PERSIST_TOOLS=(TodoWrite TaskCreate TaskUpdate)

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


# Commands that only read, unless given an option that writes (writes below).
# A subset of the SDK mapper's _READ_ONLY_COMMANDS.
READ_ONLY=(ls cat head tail wc pwd grep stat file du df which whoami uname echo printf "git status" "git log" "git diff" "git show" "git rev-parse" "git ls-files")

# git stash <sub>=<class>, for a line of exactly one command: the mapper's
# _GIT_STASH_CLASSES. A rollback form counts only as `git stash pop|apply
# <commit>` with a full commit id (classify_bash), and only for a commit a
# marker recorded (recorded_commit). (A plain array: bash 3.2, as macOS ships
# it, has no associative arrays.)
GIT_STASH_CLASSES=(create=checkpoint list=observe show=observe pop=rollback apply=rollback)

# Read a line that holds none of ; & | < > $ ` ( ) { } \ (refused before, so
# nothing in it expands but a pathname pattern) into WORDS, as bash splits
# and dequotes it: '...' and "..." quote literally, and unquoted blanks
# separate words. GLOBBED is 1 when a word holds an unquoted *, ? or [,
# which bash replaces with file names. Fails on an unbalanced quote, and on
# a line over 4096 bytes: each character read costs time that grows with the
# line, so a long one could hold the hook past its time limit, after which
# Claude Code runs the call unchecked unless onFailure is "block".
# posttooluse_take_checkpoint.sh holds the same function; a test keeps them so.
split_words() {
  local line="$1" ch quote="" word="" inword=0 i
  WORDS=()
  GLOBBED=0
  if [ "${#line}" -gt 4096 ]; then return 1; fi
  for ((i = 0; i < ${#line}; i++)); do
    ch="${line:i:1}"
    if [ -n "$quote" ]; then
      if [ "$ch" = "$quote" ]; then quote=""; else word+="$ch"; fi
      continue
    fi
    case "$ch" in
      \' | \") quote="$ch"; inword=1 ;;
      ' ' | $'\t')
        if [ "$inword" = 1 ]; then WORDS+=("$word"); fi
        word=""
        inword=0
        ;;
      \* | \? | \[) GLOBBED=1; word+="$ch"; inword=1 ;;
      *) word+="$ch"; inword=1 ;;
    esac
  done
  if [ -n "$quote" ]; then return 1; fi
  if [ "$inword" = 1 ]; then WORDS+=("$word"); fi
  return 0
}

# Whether $1 is a long option that is, or abbreviates, one of the names that
# follow (getopt_long and git take any prefix of an option's name).
long_option_of() {
  local name="${1#--}" option
  if [[ "$1" != --?* ]]; then return 1; fi
  name="${name%%=*}"
  for option in "${@:2}"; do
    if [ -n "$name" ] && [[ "$option" == "$name"* || "$name" == "$option"* ]]; then return 0; fi
  done
  return 1
}

# git as these hooks run it: with what a repository's own configuration
# could make git run turned off (core.fsmonitor, which git runs to refresh
# the index, and hooks), no object fetched from a promisor remote, so no
# repository content makes this hook run a program or reach a host, and for
# at most 5 seconds (bounded: status 124 when stopped, which every caller
# reads as git cannot say). posttooluse_take_checkpoint.sh holds the same
# function.
hgit() {
  GIT_NO_LAZY_FETCH=1 bounded git -c core.fsmonitor=false -c core.hooksPath=/dev/null "$@"
}

# BEGIN call-place (the same in the pre-tool-use hook and the take hook; tests/test_hook_lists_match_mapper.py keeps them so)
# The git directory git finds from the directory $1, into GIT_DIR_FOUND:
# absolute, and exactly as git prints it (a command substitution strips the
# line breaks that end its output, and a directory's name may end in one, so
# an x is printed after git's line and taken off with git's line break).
# Status 0: found; 1: no repository there (git exits 128: there is none, or
# git refuses it, as it refuses the agent's commands there); 2: git cannot
# say (no git, stopped at its time bound, or any other answer).
git_dir_at() {
  local status=0
  GIT_DIR_FOUND=""
  command -v git > /dev/null 2>&1 || return 2
  GIT_DIR_FOUND=$(hgit -C "$1" rev-parse --absolute-git-dir 2> /dev/null && printf x) || status=$?
  case "$status" in
    0) ;;
    128) GIT_DIR_FOUND="" && return 1 ;;
    *) GIT_DIR_FOUND="" && return 2 ;;
  esac
  GIT_DIR_FOUND="${GIT_DIR_FOUND%x}"
  GIT_DIR_FOUND="${GIT_DIR_FOUND%$'\n'}"
  [ -n "$GIT_DIR_FOUND" ] || return 2
}

# git's one-line answer ($@: hgit's arguments), into GIT_LINE, exactly as
# git_dir_at reads it. Fails with git's status, or 1 for no line.
git_line() {
  GIT_LINE=$(hgit "$@" 2> /dev/null && printf x) || return $?
  GIT_LINE="${GIT_LINE%x}"
  [[ "$GIT_LINE" == *$'\n' ]] || return 1
  GIT_LINE="${GIT_LINE%$'\n'}"
}

# The physical path of the directory $1, into PHYSICAL, exactly (the x keeps
# the line breaks that may end a name from the command substitution).
physical_dir() {
  PHYSICAL=$(cd -P -- "$1" 2> /dev/null && pwd -P && printf x) || return 1
  PHYSICAL="${PHYSICAL%x}"
  [[ "$PHYSICAL" == *$'\n' ]] || return 1
  PHYSICAL="${PHYSICAL%$'\n'}"
}

# Whether the program the agent's shell runs for the command name $1 may be
# repository content (§5.18.3: a call is classified by its effect, and a
# layer that cannot tell which program runs takes the worst case). bash runs
# a name with no slash as the first executable file of that name in a
# directory of its PATH (agent_path): the repository's own git, cat or ls
# runs in place of the system's when PATH holds an empty or relative entry
# (bash reads it from the working directory: PATH=node_modules/.bin:$PATH,
# or a leading colon) under which the name is found, or an entry in the
# project directory (an activated virtual environment, direnv's PATH_add)
# whose file of that name lies, links followed, in the project (as
# hook_path reads the project: not where it is the user's home directory, or
# holds it). Yes then, when no such file is found, and when anything here
# cannot be read. Not seen: the entries Claude Code's Bash tool adds to PATH
# from the user's shell startup files (its shell snapshot), which reach no
# hook. The SDK mapper asks the same (command_may_be_content).
# The target of link $1 exactly, with an x after it: a target may end in a
# line break, which GNU readlink prints with one more after it but BSD
# readlink (macOS) prints without one, so a target and the same name
# without its last line break read alike there. Perl's readlink returns it
# as stored; without perl, GNU readlink's output is read.
link_target() {
  local t
  if command -v perl > /dev/null 2>&1; then
    perl -e 'defined(my $t = readlink $ARGV[0]) or exit 1; print $t, "x"' -- "$1"
    return
  fi
  t=$(readlink -- "$1" && printf x) || return 1
  t="${t%x}"
  [[ "$t" == *$'\n' ]] || return 1
  printf '%sx' "${t%$'\n'}"
}
command_may_be_content() {
  local name="$1" rest found="" entry dir target links=0 project="" home=""
  case "$name" in "" | */*) return 0 ;; esac
  [ -n "$agent_path" ] || return 0
  call_dir || return 0
  rest="${agent_path}:"
  while [ -n "$rest" ]; do
    entry="${rest%%:*}"
    rest="${rest#*:}"
    case "$entry" in
      /*) found="${entry%/}/$name" ;;
      *) found="${CALL_DIR%/}/${entry:+${entry%/}/}$name" ;;
    esac
    if [ -f "$found" ] && [ -x "$found" ]; then
      case "$entry" in /*) break ;; *) return 0 ;; esac
    fi
    found=""
  done
  [ -n "$found" ] || return 0
  # The file it names, each link followed.
  while :; do
    dir="${found%/*}"
    physical_dir "${dir:-/}" || return 0
    found="${PHYSICAL%/}/${found##*/}"
    [ -L "$found" ] || break
    links=$((links + 1))
    [ "$links" -le 40 ] || return 0
    target=$(link_target "$found" 2> /dev/null) || return 0
    target="${target%x}"
    case "$target" in /*) found="$target" ;; *) found="${PHYSICAL%/}/$target" ;; esac
  done
  physical_dir "$project_dir" || return 0
  project="$PHYSICAL"
  # The home directory as the password database gives it, not HOME.
  if home=$(unset HOME && cd -P ~ 2> /dev/null && pwd -P && printf x); then
    home="${home%x}"
    home="${home%$'\n'}"
  else
    home=""
  fi
  # A project that is the home directory, or holds it, is no repository's.
  case "$home/" in "$project"/*) [ -z "$home" ] || return 1 ;; esac
  case "$found" in "$project"/*) return 0 ;; esac
  return 1
}

# Whether $1, an absolute git directory, is one git makes for a work tree: a
# .git directory, or a linked worktree's or a submodule's under one. git
# refuses a path with a .git component in a repository, so no clone or
# checkout writes one; but a repository can ship a directory holding HEAD,
# objects/ and refs/, which git takes for a git directory (an embedded bare
# repository) and whose config and hooks are then repository content.
git_dir_is_made() {
  case "$1" in
    */.git | */.git/worktrees/* | */.git/modules/*) return 0 ;;
  esac
  return 1
}

# The payload's cwd, into PAYLOAD_CWD, exactly as given (empty when there is
# none): a command substitution strips the line breaks that end its output,
# and a directory's name may end in one (`cd $'d\n'` is not d), so an x is
# printed after the cwd and taken off. Fails when the payload cannot be read.
payload_cwd() {
  PAYLOAD_CWD=$(printf '%s' "$payload" | jq -j '(.cwd // "" | strings), "x"' 2>/dev/null) || return 1
  PAYLOAD_CWD="${PAYLOAD_CWD%x}"
}

# The directory the call runs in, into CALL_DIR: its cwd, else the project
# directory. Fails when the payload cannot be read.
call_dir() {
  payload_cwd || return 1
  CALL_DIR="${PAYLOAD_CWD:-${CLAUDE_PROJECT_DIR:-$PWD}}"
}

# Whether the git directory git finds where this call runs is repository
# content (not one git made for a work tree, git_dir_is_made): there git
# reads that directory's config and hooks, and runs what they name
# (core.fsmonitor for git status, git ls-files and git stash,
# diff.<driver>.textconv for git log -p, git show and git diff). No
# repository there: no. The SDK mapper asks the same (git_dir_may_be_content).
git_dir_is_content() {
  local found=0
  call_dir || return 0
  git_dir_at "$CALL_DIR" || found=$?
  case "$found" in
    0) ! git_dir_is_made "$GIT_DIR_FOUND" ;;
    1) return 1 ;;
    *) return 0 ;;
  esac
}
# END call-place

# The configuration keys that name a program git runs: core.fsmonitor (to
# refresh the index: git status, git diff, git stash; true and false name
# git's own), a diff driver's textconv or command and diff.external (git
# diff, git log -p, git show), a filter's clean, smudge or process (git
# status and git diff hash a changed file through clean; a restore writes
# through smudge), a merge driver (a restore merges), a signature program
# (git log and git show with log.showSignature) and a pager. The SDK mapper
# holds the same pattern (_PROGRAM_CONFIG).
GIT_PROGRAM_KEYS='^(core\.fsmonitor|core\.pager|pager\..+|diff\.external|diff\..+\.(textconv|command)|filter\..+\.(clean|smudge|process)|merge\..+\.driver|gpg\.program|gpg\..+\.program)$'

# Whether git, run where this call runs, may run a program the repository
# itself names: its own configuration (the local and worktree scopes, with
# the files they include) sets one of GIT_PROGRAM_KEYS, or its hooks
# directory holds post-index-change, which git runs when a read such as git
# status writes the index. A repository delivered with its .git (an archive,
# a copied checkout) brings that configuration and those hooks, and one
# approved `git config core.fsmonitor ./x` writes it; the user's own
# settings (global, system, the command line) are not repository content.
# No repository there: no. Anything git does not answer: yes. The SDK
# mapper asks the same (git_config_may_run).
git_runs_configured() {
  local dir found status=0 hooks
  call_dir || return 0
  dir="$CALL_DIR"
  git_dir_at "$dir" || status=$?
  case "$status" in
    0) ;;
    1) return 1 ;;
    *) return 0 ;;
  esac
  found=$(hgit -C "$dir" config --show-scope --get-regexp "$GIT_PROGRAM_KEYS" 2>/dev/null) || status=$?
  case "$status" in
    0) ;;
    1) found="" ;;
    *) return 0 ;;
  esac
  if printf '%s\n' "$found" | awk -F '\t' '
    $1 == "local" || $1 == "worktree" {
      key = $2; value = ""; blank = index(key, " ")
      if (blank) { value = substr(key, blank + 1); key = substr(key, 1, blank - 1) }
      if (key == "core.fsmonitor" && tolower(value) ~ /^(true|false|yes|no|on|off|1|0)?$/) next
      named = 1
    }
    END { exit named ? 0 : 1 }'; then
    return 0
  fi
  # Where git looks for hooks (core.hooksPath, else <git dir>/hooks): asked
  # without hgit, which points it at /dev/null.
  hooks=$(GIT_NO_LAZY_FETCH=1 bounded git -c core.fsmonitor=false -C "$dir" rev-parse --git-path hooks 2> /dev/null && printf x) || return 0
  hooks="${hooks%x}"
  [[ "$hooks" == *$'\n' ]] || return 0
  hooks="${hooks%$'\n'}"
  [ -n "$hooks" ] || return 0
  case "$hooks" in /*) ;; *) hooks="$dir/$hooks" ;; esac
  [ -e "$hooks/post-index-change" ] || [ -L "$hooks/post-index-change" ]
}

# The configuration keys of a filter git runs when it writes a file of the
# work tree from an object: a filter driver's smudge or process command. The
# SDK mapper holds the same pattern (_SMUDGE_CONFIG).
GIT_SMUDGE_KEYS='^filter\..+\.(smudge|process)$'

# Whether git, writing files of the work tree where this call runs (a
# restore), may run a filter that reaches another host: a filter driver's
# smudge or process command configured in any scope, the user's own
# included. git runs it for each file whose attributes name the driver,
# which the repository chooses (its .gitattributes, or those of the commit
# written), and git-lfs, whose `git lfs install` writes its filter to the
# global configuration, asks the LFS server the repository's .lfsconfig or
# remote names for each object its store lacks, sending the object's id: a
# restore of a checkpoint holding such a pointer did (security round 5).
# Only the two commands `git lfs install --skip-smudge` writes, exactly,
# count as none (they ask no server). No repository there: no. Anything git
# does not answer: yes. The SDK mapper asks the same (git_filter_may_run).
git_filter_runs() {
  local dir status=0 found
  call_dir || return 0
  dir="$CALL_DIR"
  git_dir_at "$dir" || status=$?
  case "$status" in
    0) ;;
    1) return 1 ;;
    *) return 0 ;;
  esac
  # -z: each entry is the key, a line break, the value, then a NUL; as lines
  # of the key, a tab and the value (a value holding a tab or a line break
  # is then no command listed below).
  found=$(hgit -C "$dir" config -z --get-regexp "$GIT_SMUDGE_KEYS" 2> /dev/null | tr '\n\0' '\t\n') || status=$?
  case "$status" in
    0) ;;
    1) return 1 ;;
    *) return 0 ;;
  esac
  printf '%s\n' "$found" | awk '
    $0 == "" { next }
    { value = substr($0, index($0, "\t") + 1) }
    index($0, "\t") == 0 || (value != "git-lfs smudge --skip -- %f" && value != "git-lfs filter-process --skip") { runs = 1 }
    END { exit runs ? 0 : 1 }'
}

# Whether a git command that only reads, run where this call runs, may do
# more than read this repository's own state; anything git does not answer
# counts as yes:
#   - the git directory there is repository content (git_dir_is_content);
#   - the repository's own configuration or hooks name a program git runs
#     (git_runs_configured);
#   - a partial clone (a promisor remote, or extensions.partialClone naming
#     one): git fetches each object it lacks from the promisor remote, so a
#     read such as `git show <id>` or `git log -p` reaches that host, and the
#     object id the agent chose goes to it (§5.18.3: a request to another
#     system);
#   - a repository with submodules (<common git dir>/modules/, or a gitlink
#     in the index): a read that looks into a submodule (`--submodule=diff`,
#     the diff.submodule setting, `git status`) reads its object store,
#     where a partial clone fetches the same way.
# The SDK mapper asks the same (git_may_fetch, git_dir_may_be_content,
# git_config_may_run).
git_read_gated() {
  local dir found status=0 git_dir common links
  call_dir || return 0
  dir="$CALL_DIR"
  git_dir_at "$dir" || status=$?
  case "$status" in
    0) git_dir="$GIT_DIR_FOUND" ;;
    1) git_dir="" && status=0 ;;
    *) return 0 ;;
  esac
  if [ -n "$git_dir" ] && ! git_dir_is_made "$git_dir"; then return 0; fi
  if git_runs_configured; then return 0; fi
  found=$(hgit -C "$dir" config --get-regexp '^(remote\..+\.promisor|extensions\.partialclone)$' 2>/dev/null) || status=$?
  if [ "$status" != 1 ] || [ -n "$found" ]; then return 0; fi
  if [ -n "$git_dir" ]; then
    git_line -C "$dir" rev-parse --git-common-dir || return 0
    common="$GIT_LINE"
    case "$common" in /*) ;; *) common="$dir/$common" ;; esac
    if [ -e "$common/modules" ] || [ -L "$common/modules" ]; then return 0; fi
    links=$(hgit -C "$dir" ls-files --stage -- ':/' 2>/dev/null | awk 'substr($0, 1, 7) == "160000 " { n++ } END { print n + 0 }') || return 0
    [ "$links" = 0 ] || return 0
  fi
  return 1
}

# Whether one simple command, given as its words, has an option that writes:
# the mapper's _writes rules for the commands on READ_ONLY. GLOBBED (set by
# split_words): a word bash expands may be any option.
writes() {
  local word
  if [ "$1" = "git" ]; then
    if [ "$GLOBBED" = 1 ]; then return 0; fi
    for word in "$@"; do
      if long_option_of "$word" output; then return 0; fi
    done
  elif [ "$1" = "file" ]; then
    if [ "$GLOBBED" = 1 ]; then return 0; fi
    for word in "${@:2}"; do
      if long_option_of "$word" compile preserve-date; then return 0; fi
      if [[ "$word" == -* && "$word" != --* && "${word:1}" == *[Cp]* ]]; then return 0; fi
    done
  elif [ "$1" = "printf" ]; then
    # printf -v NAME assigns a shell variable (an array element's subscript
    # is evaluated as arithmetic, which runs a $(...) the format wrote): any
    # option, so any first argument starting with -, and any word bash
    # expands, which may be one.
    if [ "$GLOBBED" = 1 ] || [[ "${2:-}" == -* ]]; then return 0; fi
  fi
  return 1
}

classify_bash() {
  local command="$1" entry
  local -a words
  # A line over 4096 bytes is not read: mutate. Checked before the trims
  # below, whose cost grows with the line times its run of blanks (a gated
  # command padded with 50,000 blanks took a minute to trim).
  if [ "${#command}" -gt 4096 ]; then
    echo mutate
    return
  fi
  # Trim, then any character that can join or expand commands: mutate.
  command="${command#"${command%%[![:space:]]*}"}"
  command="${command%"${command##*[![:space:]]}"}"
  if [ -z "$command" ] || [[ "$command" == *[\;\&\|\<\>\$\`\(\)\{\}\\]* ]] || [[ "$command" == *$'\n'* ]] || [[ "$command" == *$'\r'* ]]; then
    echo mutate
    return
  fi
  if ! split_words "$command"; then
    echo mutate
    return
  fi
  words=("${WORDS[@]}")
  if writes "${words[@]}"; then
    echo mutate
    return
  fi
  # Every class below but mutate names the program the first word names:
  # where that may be the repository's own, mutate.
  if command_may_be_content "${words[0]}"; then
    echo mutate
    return
  fi
  if [ "${words[0]}" = "git" ] && [ "${words[1]:-}" = "stash" ]; then
    # git stash create refreshes the index (core.fsmonitor) and a restore
    # writes the tree (filters): in a git directory the repository ships,
    # each runs what its config names.
    if git_dir_is_content; then
      echo mutate
      return
    fi
    for entry in "${GIT_STASH_CLASSES[@]}"; do
      if [ "${entry%%=*}" = "${words[2]:-}" ]; then
        if [ "${entry#*=}" = "observe" ] && git_read_gated; then
          echo mutate
        elif [ "${entry#*=}" = "checkpoint" ] && git_runs_configured; then
          # It refreshes the index, running what the repository's own
          # configuration names: a person approves it. No marker is asked
          # for: only this command makes one.
          echo checkpoint-ask
        elif [ "${entry#*=}" != "rollback" ]; then
          echo "${entry#*=}"
        elif [ "${#words[@]}" -eq 4 ] && [[ "${words[3]}" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]] && ! git_runs_configured && ! git_filter_runs; then
          echo "rollback ${words[3]}"
        else
          echo mutate
        fi
        return
      fi
    done
    echo mutate
    return
  fi
  # bash runs the program the first word names, looked up as it stands: a
  # word holding a blank ("git status", quoted) or a slash names a program
  # that is on no list, whatever the list's entries spell.
  case "${words[0]}" in
    *[[:space:]/]*)
      echo mutate
      return
      ;;
  esac
  for entry in "${READ_ONLY[@]}"; do
    # A one-word entry is the program; a two-word one, the program and its
    # subcommand, each one word.
    if [ "$entry" = "${words[0]}" ] || { [ "${entry%% *}" != "$entry" ] && [ "${entry%% *}" = "${words[0]}" ] && [ "${entry#* }" = "${words[1]:-}" ]; }; then
      if [ "${words[0]}" = "git" ] && git_read_gated; then
        echo mutate
      else
        echo observe
      fi
      return
    fi
  done
  echo mutate
}

# Whether JSON data holds, in a member named for a credential, a value
# redaction replaces that is not a placeholder: the shared rule
# (hooks/secret_member.jq, copied below; tests/test_skill_hooks.py keeps
# every copy equal, and tests/test_pretooluse_hooks.py keeps it in
# agreement with the SDK redactor).
SECRET_MEMBER_JQ='
# BEGIN secret-member (source: hooks/secret_member.jq; tests/test_skill_hooks.py keeps every copy equal)
# acs_held(false): whether JSON data holds, in a member named for a
# credential, a value redaction replaces that is not a placeholder: the rule
# the SDK redactor applies to data (grounded_agency/state/redaction.py,
# _secret_member_value; STANDARD 1.2.0 §6.7). A member is secret when its
# name ends in a credential name or names a header that carries one
# (Authorization, Cookie), when it is the value of a name/value pair whose
# name is such a name ({"name": "Authorization", "value": ...}), the second
# of a [name, value] tuple, or inside a secret member. Its value counts when
# it is a number, or a string of 4 or more characters other than [REDACTED]
# that is not a placeholder (<...>, ${...}, ****, password, token, ...).
# Names are compared in ASCII lower case, as the SDK compares them (re.ASCII,
# IGNORECASE), with string functions: jq compiles a regular expression at
# each test, about 0.4 ms a member, so a record of 1 MB took 22 s. A name
# outside ASCII (utf8bytelength differs from length) is also tested with
# Unicode case folding, so this rule finds a name the SDK does not in rare
# spellings, never the reverse; a placeholder is matched in ASCII only, so
# no rare spelling hides a value. A copy sits in a single-quoted shell
# string, so this text holds no single quote.
def acs_names: ["password", "passwd", "passphrase", "pwd", "secret", "secret_key", "secret-key", "secretkey", "token", "api_key", "api-key", "apikey", "access_key", "access-key", "accesskey", "client_secret", "client-secret", "clientsecret", "private_key", "private-key", "privatekey", "account_key", "account-key", "accountkey", "signing_key", "signing-key", "signingkey", "encryption_key", "encryption-key", "encryptionkey", "hmac_key", "hmac-key", "hmackey", "master_key", "master-key", "masterkey", "credential", "authorization", "cookie", "cookies"];
def acs_name: (ascii_downcase as $n | any(acs_names[]; . as $s | $n | endswith($s)))
  or (utf8bytelength != length and test("\\A[\\s\\S]*(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|account[_-]?key|signing[_-]?key|encryption[_-]?key|hmac[_-]?key|master[_-]?key|credential|authorization|cookies?)\\z"; "i"));
def acs_is($words): (ascii_downcase | IN($words[])) or (utf8bytelength != length and test("\\A(" + ($words | join("|")) + ")\\z"; "i"));
def acs_scalar: (type == "string" and length >= 4 and . != "[REDACTED]") or type == "number";
def acs_placeholder: type == "string"
  and (((.[0:1] | IN("$", "<", "{", "*", "[")) and (contains("\n") | not))
       or (ascii_downcase | IN("password", "passwd", "pwd", "pass", "secret", "token")));
def acs_held($secret):
  if $secret and acs_scalar then (acs_placeholder | not)
  elif type == "object" then
    (($secret | not) and any(to_entries[]; (.key | acs_is(["name", "key", "header"])) and (.value | type == "string" and acs_name))) as $pair
    | any(to_entries[]; .key as $k | .value | acs_held($secret or ($k | acs_name) or ($pair and ($k | acs_is(["value"])))))
  elif type == "array" then
    (($secret | not) and length == 2 and (.[0] | type == "string" and acs_name)) as $tuple
    | any(to_entries[]; .key as $i | .value | acs_held($secret or ($tuple and $i == 1)))
  else false end;
# END secret-member
'

# persist: the data the call would store holds no secret the layer
# recognises (§5.18.10, §6.7), as the SDK adapter decides it
# (Redactor.holds_credential): a credential-shaped value in any string of
# the input or in the input's JSON text, or a value in a member named for a
# credential (SECRET_MEMBER_JQ). Each string is read on its own (as the
# adapter reads each), line by line and again with its line breaks read as
# blanks (a value on the line after its name), and the JSON text after them
# (secret_lines). NUL bytes, which a shell variable cannot hold, are read as
# blanks. The scan runs without pipefail: a grep -q that stops at a match
# ends the printf feeding it, and with pipefail that would read as no match.
# The credentials the layer holds itself count as registered values (§6.7:
# a host recognises at least those): AUDIT_HMAC_KEY's value (secret_held
# reads it) and the project's checkpoint key, <git dir>/acs/checkpoints/key
# where git names the project's git directory (SECRET_HELD; a git that
# cannot say where it is reads none, as the take hook could have drawn none
# there).
for entry in "${PERSIST_TOOLS[@]}"; do
  if [ "$tool_name" = "$entry" ]; then
    unread="R407 SAFETY_CHECK_FAILED: cannot read the data $tool_name would store, so the call is blocked."
    SECRET_HELD=""
    if git_dir_at "$project_dir" && git_dir_is_made "$GIT_DIR_FOUND" \
      && [ -f "$GIT_DIR_FOUND/acs/checkpoints/key" ] && [ ! -L "$GIT_DIR_FOUND/acs/checkpoints/key" ]; then
      SECRET_HELD=$(head -c 128 "$GIT_DIR_FOUND/acs/checkpoints/key" 2>/dev/null) || block "$unread"
      [[ "$SECRET_HELD" =~ ^[0-9a-f]{64}$ ]] || SECRET_HELD=""
    fi
    held=$(printf '%s' "$payload" | jq -r "$SECRET_MEMBER_JQ"' .tool_input | acs_held(false)' 2>/dev/null) || block "$unread"
    stored=$(printf '%s' "$payload" | jq -r '
      # join, in time linear in the text (the builtin join copies what it has built at each piece)
      def joined($s): (.[0:1] + (.[1:] | map($s + .))) | add // "";
      def blanked: split("\r") | joined(" ") | split("\n") | joined(" ");
      .tool_input | [.. | strings] as $s
      | $s + [$s[] | select(index("\n") != null or index("\r") != null) | blanked] + [tojson]
      | joined("\n") | split("\u0000") | joined(" ")' 2>/dev/null) || block "$unread"
    if [ "$held" = "true" ] || { [ "$held" = "false" ] && (set +o pipefail; secret_lines "$stored"); }; then
      block "F504 CONSTRAINT_VIOLATED: $tool_name (persist): the data it would store holds what looks like a credential; persist where the secret is kept, or cite it by reference, not the secret (STANDARD 1.2.0 §5.18.10, §6.7)"
    fi
    [ "$held" = "false" ] || block "$unread"
  fi
done

for entry in "${UNGATED_TOOLS[@]}"; do
  if [ "$tool_name" = "$entry" ]; then
    exit 0
  fi
done

# The tool's name as the refusals and approval requests below show it
# (plain_name): a diagnostic holds no secret (§6.7).
shown_tool=$(plain_name "$tool_name")

# Unbound: a tool this hook does not know, MCP tools included, is a mutate
# (§5.18.2), and its refusals and its approval request name no capability.
unbound=0
unseen=0
case "$tool_name" in
  Write | Edit | MultiEdit | NotebookEdit)
    capability=mutate
    ;;
  Skill | Agent | Task)
    # The commands the skill's file or the subagent's definition runs reach
    # no hook: the worst case.
    capability=mutate
    unseen=1
    ;;
  Bash)
    command=$(printf '%s' "$payload" | jq -r '.tool_input.command | strings' 2>/dev/null) || command=""
    capability=$(classify_bash "$command")
    ;;
  *)
    capability=mutate
    unbound=1
    ;;
esac

if [ "$capability" = "observe" ] || [ "$capability" = "checkpoint" ]; then
  exit 0
fi

# Approval needs a person (§5.18.7): unless ACS_HOOK_APPROVAL is "off", a
# call that requires it is blocked in a permission mode that puts no call to
# a person.
approval="${ACS_HOOK_APPROVAL:-ask}"
require_person() {
  local mode
  [ "$approval" != "off" ] || return 0
  mode=$(printf '%s' "$payload" | jq -r '.permission_mode // "default" | if type == "string" then . else "(not a string)" end' 2>/dev/null) || mode="(unreadable)"
  case "$mode" in
    default | acceptEdits | plan) ;;
    *)
      block "F502 APPROVAL_REQUIRED: permission mode '$mode' does not put this call to a person; set ACS_HOOK_APPROVAL=off to leave approval to Claude Code's permission rules."
      ;;
  esac
}

# Put the call to the person, with the reason $1 (unless ACS_HOOK_APPROVAL is
# "off").
ask_person() {
  [ "$approval" != "off" ] || return 0
  jq -c -n --arg reason "$1" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason}}'
}

# A checkpoint whose taking runs a program the repository's own git
# configuration or hooks name (git_runs_configured): a person approves it,
# and it needs no marker, since only this command makes one.
if [ "$capability" = "checkpoint-ask" ]; then
  require_person
  ask_person "F502 APPROVAL_REQUIRED: Bash (capability 'checkpoint'): git stash create runs the programs this repository's own git configuration names (core.fsmonitor, a filter, a diff or merge driver) or its post-index-change hook; it runs only if this call is approved."
  exit 0
fi

claude_dir="${project_dir}/.claude"
marker="${claude_dir}/checkpoint.ok"
used_dir="${claude_dir}/checkpoints/used"
# Markers whose validity ended unused (expired, the turn ended, or a newer
# checkpoint replaced them), kept like used/.
ended_dir="${claude_dir}/checkpoints/ended"

# What posttooluse_take_checkpoint.sh writes in the entry of commit $2 in
# git directory $1: the HMAC-SHA-256, in hex, of "acs-checkpoint-commit:<commit>"
# under the project's checkpoint key (<git dir>/acs/checkpoints/key, 64 hex
# digits the take hook drew at random). Fails with no valid key or no
# openssl.
commit_signature() {
  local key_file="$1/acs/checkpoints/key" key sig
  [ -f "$key_file" ] && [ ! -L "$key_file" ] || return 1
  key=$(head -c 128 "$key_file" 2>/dev/null) || return 1
  [[ "$key" =~ ^[0-9a-f]{64}$ ]] || return 1
  command -v openssl > /dev/null 2>&1 || return 1
  sig=$(printf 'acs-checkpoint-commit:%s' "$2" | openssl dgst -sha256 -hmac "$key" 2>/dev/null | awk '{print $NF}') || return 1
  [[ "$sig" =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s' "$sig"
}

# Whether a checkpoint of this project recorded the commit $1 (a full commit
# id, so a safe file name) as its restore point, for a call that runs in the
# project's repository: posttooluse_take_checkpoint.sh enters each such
# commit as a file named by it, in <git dir>/acs/checkpoints/commits/,
# holding its commit_signature, before it writes the marker. That directory
# is outside the work tree: a clone, a checkout or an applied stash can put
# files in the work tree, .claude/ included, but none in it; and a file a
# command creates there (through a symbolic link the repository ships, say)
# holds no signature, which only a holder of the key can make. The git
# directory must be one git made for a work tree (git_dir_is_made): a
# directory the repository ships could hold a key and entries of its own.
# One lookup, however many checkpoints were taken. A checkpoint can be
# restored valid or not (§5.18.6).
recorded_commit() {
  local git_dir cwd entry sig have
  git_dir_at "$project_dir" || return 1
  git_dir="$GIT_DIR_FOUND"
  git_dir_is_made "$git_dir" || return 1
  # The call restores into the repository it runs in (its cwd): the
  # project's, or the commit is another repository's state.
  payload_cwd || return 1
  cwd="$PAYLOAD_CWD"
  if [ -n "$cwd" ]; then
    git_dir_at "$cwd" || return 1
    [ "$GIT_DIR_FOUND" = "$git_dir" ] || return 1
  fi
  entry="${git_dir}/acs/checkpoints/commits/$1"
  [ -f "$entry" ] && [ ! -L "$entry" ] || return 1
  sig=$(commit_signature "$git_dir" "$1") || return 1
  have=$(head -c 128 "$entry" 2>/dev/null) || return 1
  [ "$have" = "$sig" ]
}

if [[ "$capability" == "rollback "* ]]; then
  # Restoring a recorded checkpoint uses none. Applying any other commit
  # changes the tree like any write.
  if recorded_commit "${capability#rollback }"; then
    exit 0
  fi
  capability=mutate
fi

# The layer's records are written by these hooks alone. The texts a call
# names paths in are read: a Write, Edit, MultiEdit or NotebookEdit call's
# path (P: read whole), a Bash command and a Skill call's arguments (which
# Claude Code substitutes into the shell commands a skill's file embeds) (W:
# read as words), and, for every other tool but Agent and Task (Monitor and
# PowerShell, which run commands, every MCP tool, a tool this hook does not
# know), every string of its input and every member name (B: read whole and
# as words), since the hook cannot know which of them the tool takes for a
# path or a command (a filesystem server's path, a shell server's command).
# Agent and Task are not read: a subagent's own calls come here. A text that
# names the marker, the checkpoint directories (the key included) or the
# audit log's head is refused (a written entry or key would be a pass for a
# restore, a written marker a checkpoint no call took, a written or removed
# head a log cut short that verifies). The text is read as a path is: in any
# letter case (a case-insensitive file system opens CHECKPOINT.OK as
# checkpoint.ok), with a run of slashes and ./ segments as one slash, and, in
# a text of at most 4096 bytes, each x/../ resolved (a longer path cannot be
# opened, and a longer command is a mutate already; the resolution's cost
# grows faster than the text). The texts of at most 4096 bytes are then read
# for paths below: more than 65536 bytes of them in one call, or more than
# 4096 texts of any length (an empty one counts no byte, yet costs time to
# read), is refused, rather than hold the hook past its time limit.
RECORD_TEXTS_JQ='
  def file_tool: .tool_name == "Write" or .tool_name == "Edit" or .tool_name == "MultiEdit" or .tool_name == "NotebookEdit";
  def texts:
    if .tool_name == "Bash" then [.tool_input.command | strings]
    elif .tool_name == "Skill" then [.tool_input.args | strings]
    elif file_tool then [(.tool_input.file_path // .tool_input.notebook_path) | strings]
    elif .tool_name == "Agent" or .tool_name == "Task" then []
    else [.tool_input | .. | (strings, (objects | keys[]))]
    end;
  def mode: if .tool_name == "Bash" or .tool_name == "Skill" then "W" elif file_tool then "P" else "B" end;
  def records: test("checkpoint\\.ok|audit\\.head|\\.claude/+(\\./+)*checkpoints|acs/+(\\./+)*checkpoints"; "i");
  def lexical: ascii_downcase | split("/")
    | reduce .[] as $s ([]; if $s == "" or $s == "." then . elif $s == ".." then (if length > 0 then .[:-1] else . end) else . + [$s] end)
    | join("/");
'
records_named=$(printf '%s' "$payload" | jq -r "$RECORD_TEXTS_JQ"'
  texts as $t
  | if ($t | length) > 4096 or ([$t[] | utf8bytelength | select(. <= 4096)] | add // 0) > 65536 then "over"
    elif any($t[]; records or (length <= 4096 and (lexical | records))) then "named"
    else "no" end' 2>/dev/null) || block "R407 SAFETY_CHECK_FAILED: cannot read the tool call's arguments, so the call is blocked."
records_refusal="F504 CONSTRAINT_VIOLATED: ${shown_tool} names the checkpoint records (.claude/checkpoint.ok, .claude/checkpoints/, the git directory's acs/checkpoints/) or the audit log's head (.claude/audit.head), which only the plugin's hooks write"
case "$records_named" in
  no) ;;
  over) block "F504 CONSTRAINT_VIOLATED: ${shown_tool}'s input holds more than 4096 strings and member names, or more than 65536 bytes of strings of at most 4096 bytes, more than this hook reads for paths into the layer's records (.claude/checkpoint.ok, .claude/checkpoints/, the git directory's acs/checkpoints/, .claude/audit.head) in its time limit, so the call is blocked." ;;
  *) block "${records_refusal}." ;;
esac

# The character $'...' gives for the escape just after the backslash at $2
# in $1, into ANSI_CHAR (as bash decodes it: \a \b \e \E \f \n \r \t \v \\
# \' \" \?, \nnn octal, \xHH, \uHHHH and \UHHHHHHHH, the last two in UTF-8,
# \cx a control character, any other kept with its backslash), and the
# characters it takes after the backslash, into ANSI_LEN. ANSI_NUL is 1 for
# a NUL, which ends what bash keeps of that $'...'.
ansi_escape() {
  local c="${1:$2:1}" digits v=0 k
  ANSI_LEN=1
  ANSI_CHAR=""
  ANSI_NUL=0
  case "$c" in
    a) ANSI_CHAR=$'\a' ;;
    b) ANSI_CHAR=$'\b' ;;
    e | E) ANSI_CHAR=$'\e' ;;
    f) ANSI_CHAR=$'\f' ;;
    n) ANSI_CHAR=$'\n' ;;
    r) ANSI_CHAR=$'\r' ;;
    t) ANSI_CHAR=$'\t' ;;
    v) ANSI_CHAR=$'\v' ;;
    \\ | \' | \" | \?) ANSI_CHAR="$c" ;;
    [0-7] | x | u | U)
      case "$c" in
        [0-7]) digits="${1:$2:3}"; digits="${digits%%[!0-7]*}"; v=$((8#$digits)); ANSI_LEN=${#digits} ;;
        *)
          k=2
          [ "$c" = u ] && k=4
          [ "$c" = U ] && k=8
          digits="${1:$(($2 + 1)):k}"
          digits="${digits%%[!0-9A-Fa-f]*}"
          if [ -z "$digits" ]; then
            ANSI_CHAR="\\$c"
            return 0
          fi
          v=$((16#$digits))
          ANSI_LEN=$((${#digits} + 1))
          ;;
      esac
      if [ "$v" -eq 0 ]; then
        ANSI_NUL=1
      elif [ "$c" != u ] && [ "$c" != U ] || [ "$v" -lt 128 ]; then
        ansi_byte "$((v & 255))"
      elif [ "$v" -lt 2048 ]; then
        ansi_byte "$((192 | v >> 6))"
        ansi_byte "$((128 | (v & 63)))"
      elif [ "$v" -lt 65536 ]; then
        ansi_byte "$((224 | v >> 12))"
        ansi_byte "$((128 | (v >> 6 & 63)))"
        ansi_byte "$((128 | (v & 63)))"
      elif [ "$v" -lt 1114112 ]; then
        ansi_byte "$((240 | v >> 18))"
        ansi_byte "$((128 | (v >> 12 & 63)))"
        ansi_byte "$((128 | (v >> 6 & 63)))"
        ansi_byte "$((128 | (v & 63)))"
      fi
      ;;
    c)
      if [ -n "${1:$(($2 + 1)):1}" ]; then
        printf -v v '%d' "'${1:$(($2 + 1)):1}"
        v=$((v & 31))
        if [ "$v" -eq 0 ]; then ANSI_NUL=1; else ansi_byte "$v"; fi
        ANSI_LEN=2
      else
        ANSI_CHAR='\c'
      fi
      ;;
    "") ANSI_CHAR='\'; ANSI_LEN=0 ;;
    *) ANSI_CHAR="\\$c" ;;
  esac
}

# The byte $1 (0 to 255) added to ANSI_CHAR (no subshell).
ansi_byte() {
  local oct byte
  printf -v oct '%03o' "$1"
  printf -v byte "\\$oct"
  ANSI_CHAR+="$byte"
}

# The marks of a word path_words reads (unquoted braces and commas are
# marked \001 ({), \003 (}) and \002 (,)): BM_POS, their offsets, and
# BM_TYPE, each one's kind ({, }, , or . for a .. that no } follows, which
# bash counts as a comma when it looks for a group's end). Each character
# read is charged to BRACE_SCAN_LEFT; fails past it. The word is read 64
# characters at a time: bash measures the whole string at each ${w:i:1}, so
# a character at a time costs the word's length squared.
brace_marks() {
  local w="$1" n="${#1}" base j chunk
  BM_POS=()
  BM_TYPE=()
  BRACE_SCAN_LEFT=$((BRACE_SCAN_LEFT - n))
  [ "$BRACE_SCAN_LEFT" -ge 0 ] || return 1
  for ((base = 0; base < n; base += 64)); do
    chunk="${w:base:66}"
    case "${chunk:0:64}" in
      *[$'\001\002\003.']*) ;;
      *) continue ;;
    esac
    for ((j = 0; j < 64 && base + j < n; j++)); do
      case "${chunk:j:1}" in
        $'\001') BM_POS+=($((base + j))) && BM_TYPE+=("{") ;;
        $'\003') BM_POS+=($((base + j))) && BM_TYPE+=("}") ;;
        $'\002') BM_POS+=($((base + j))) && BM_TYPE+=(",") ;;
        .)
          if [ "${chunk:j+1:1}" = . ] && [ "${chunk:j+2:1}" != $'\003' ]; then
            BM_POS+=($((base + j)))
            BM_TYPE+=(".")
          fi
          ;;
      esac
    done
  done
}

# The group bash expands first in the marked word $1, as bash finds it: the
# first { (but a {} that opens the word) from which a } closes a group, that
# is the first } at the group's own level after a , or .. at that level (no
# group closes at a } before its first comma: {a},b} is a} and b). Sets
# BG_OPEN and BG_CLOSE, the braces' offsets, and BG_CUTS, the offsets in the
# group's text of its commas at its own level. Fails (1) when there is none,
# and (2) past BRACE_SCAN_LEFT, to which each mark read is charged.
brace_group() {
  local w="$1" k j l c nm
  brace_marks "$w" || return 2
  nm="${#BM_POS[@]}"
  for ((k = 0; k < nm; k++)); do
    [ "${BM_TYPE[k]}" = "{" ] || continue
    if [ "${BM_POS[k]}" -eq 0 ] && [ "${w:1:1}" = $'\003' ]; then continue; fi
    l=0
    c=0
    BG_CUTS=()
    for ((j = k + 1; j < nm; j++)); do
      BRACE_SCAN_LEFT=$((BRACE_SCAN_LEFT - 1))
      [ "$BRACE_SCAN_LEFT" -ge 0 ] || return 2
      case "${BM_TYPE[j]}" in
        "}")
          if [ "$l" -eq 0 ] && [ "$c" -gt 0 ]; then
            BG_OPEN="${BM_POS[k]}"
            BG_CLOSE="${BM_POS[j]}"
            return 0
          fi
          if [ "$l" -gt 0 ]; then l=$((l - 1)); fi
          ;;
        "{") l=$((l + 1)) ;;
        *)
          if [ "$l" -eq 0 ]; then
            c=$((c + 1))
            if [ "${BM_TYPE[j]}" = , ]; then BG_CUTS+=($((BM_POS[j] - BM_POS[k] - 1))); fi
          fi
          ;;
      esac
    done
  done
  return 1
}

# The words bash makes of the marked word $1 by brace expansion, into
# BRACED (marks kept), as bash makes them: the first group (brace_group)
# gives, if it is a list, the words of each of its parts (split at its own
# commas, each expanded again), else, if it is a sequence ({a..e},
# {1..10..3}, {01..10}, {a..e..+2}: a sign and leading zeros as bash takes
# them), each of its elements; the text before it is kept, and the text
# after it is expanded again. Bash versions differ on the rest, and
# BRACE_MODE, which brace_words sets, says which reading is read. Bash 5.2
# (BRACE_MODE 5.2) reads a group as a list when a comma is anywhere in it,
# nested included ({a..b{c,d}}: one part, a..b{c,d}, so a..bc and a..bd),
# and keeps a group with no comma that is no sequence as written. Bash 5.3
# reads a group as a list only when a comma is at its own level, and of a
# group that is neither expands the text inside its braces, keeping them
# ({a..bc} and {a..bd}: the one word of bash 5.3's seen, on a runner,
# without its source). Two readings give that word, and both are read:
# keeping the { as written and expanding all that follows it, the rest of
# the word included (5.3a), or keeping the group's two braces around the
# words of its own text, then expanding the text after it (5.3c). Reading
# as 5.2, it sets BRACE_SPLIT to 1 at a group 5.3 reads otherwise. Each word made is charged to the call's budgets,
# BRACE_LEFT words and RESOLVE_LEFT bytes; fails (2) past either, past
# BRACE_SCAN_LEFT, or at a sequence with a number of more than 9 digits (an
# increment of more than 18), leading zeros aside, which bash versions may
# print otherwise and bash arithmetic cannot always hold, rather than hold
# the hook past its time limit or guess.
brace_expand() {
  local w="$1" pre amble post part m t from to step width n e x start cut status=0
  local -a mid=() tail=() cuts=()
  brace_group "$w" || status=$?
  case "$status" in
    0) ;;
    1) BRACED=("$w") && return 0 ;;
    *) return 2 ;;
  esac
  pre="${w:0:BG_OPEN}"
  amble="${w:BG_OPEN+1:BG_CLOSE-BG_OPEN-1}"
  post="${w:BG_CLOSE+1}"
  cuts=(${BG_CUTS[@]+"${BG_CUTS[@]}"})
  if [[ "$amble" == *$'\002'* ]] && { [ "$BRACE_MODE" = 5.2 ] || [ "${#cuts[@]}" -gt 0 ]; }; then
    [ "${#cuts[@]}" -gt 0 ] || BRACE_SPLIT=1
    start=0
    for cut in ${cuts[@]+"${cuts[@]}"} "${#amble}"; do
      part="${amble:start:cut-start}"
      start=$((cut + 1))
      brace_expand "$part" || return 2
      mid+=("${BRACED[@]}")
    done
  elif [[ "$amble" =~ ^([+-]?[0-9]+)\.\.([+-]?[0-9]+)(\.\.[+-]?([0-9]+))?$ ]] || [[ "$amble" =~ ^([A-Za-z])\.\.([A-Za-z])(\.\.[+-]?([0-9]+))?$ ]]; then
    from="${BASH_REMATCH[1]}"
    to="${BASH_REMATCH[2]}"
    # The increment's digits, leading zeros aside: its sign does not count
    # (bash steps from the first toward the second), 0 is 1.
    step="${BASH_REMATCH[4]}"
    step="${step#"${step%%[!0]*}"}"
    [ "${#step}" -le 18 ] || return 2
    step=$((10#${step:-0}))
    [ "$step" -gt 0 ] || step=1
    width=0
    if [[ "$from" =~ ^-?0[0-9] || "$to" =~ ^-?0[0-9] ]]; then
      width=${#from}
      [ "${#to}" -le "$width" ] || width=${#to}
    fi
    if [[ "$from" == [A-Za-z] ]]; then
      printf -v from '%d' "'$from"
      printf -v to '%d' "'$to"
      width=-1
    else
      for x in "$from" "$to"; do
        x="${x#[+-]}"
        x="${x#"${x%%[!0]*}"}"
        [ "${#x}" -le 9 ] || return 2
      done
      case "$from" in -*) from=$((-10#${from#-})) ;; *) from=$((10#${from#+})) ;; esac
      case "$to" in -*) to=$((-10#${to#-})) ;; *) to=$((10#${to#+})) ;; esac
    fi
    n=$(((from > to ? from - to : to - from) / step + 1))
    BRACE_LEFT=$((BRACE_LEFT - n))
    [ "$BRACE_LEFT" -ge 0 ] || return 2
    for ((x = from; from <= to ? x <= to : x >= to; x += (from <= to ? step : -step))); do
      if [ "$width" -lt 0 ]; then
        ANSI_CHAR=""
        ansi_byte "$x"
        e="$ANSI_CHAR"
      elif [ "$x" -lt 0 ]; then
        printf -v e -- "-%0$((width > 0 ? width - 1 : 0))d" "$((-x))"
      else
        printf -v e "%0${width}d" "$x"
      fi
      mid+=("$e")
    done
  elif [ "$BRACE_MODE" = 5.2 ]; then
    # A group bash 5.2 leaves as it is: its braces as written.
    BRACE_SPLIT=1
    mid=("{${amble}}")
  elif [ "$BRACE_MODE" = 5.3c ]; then
    # Bash 5.3, read the second way: the group's braces as written around
    # the words of its own text.
    brace_expand "$amble" || return 2
    for t in "${BRACED[@]}"; do mid+=("{$t}"); done
  else
    # Bash 5.3, read the first way: the { as written, then the words of
    # what follows it.
    brace_expand "${w:BG_OPEN+1}" || return 2
    tail=("${BRACED[@]}")
    BRACED=()
    for t in "${tail[@]}"; do
      BRACE_LEFT=$((BRACE_LEFT - 1))
      RESOLVE_LEFT=$((RESOLVE_LEFT - ${#pre} - 1 - ${#t}))
      [ "$BRACE_LEFT" -ge 0 ] && [ "$RESOLVE_LEFT" -ge 0 ] || return 2
      BRACED+=("$pre{$t")
    done
    return 0
  fi
  brace_expand "$post" || return 2
  tail=("${BRACED[@]}")
  BRACED=()
  for m in "${mid[@]}"; do
    for t in "${tail[@]}"; do
      BRACE_LEFT=$((BRACE_LEFT - 1))
      RESOLVE_LEFT=$((RESOLVE_LEFT - ${#pre} - ${#m} - ${#t}))
      [ "$BRACE_LEFT" -ge 0 ] && [ "$RESOLVE_LEFT" -ge 0 ] || return 2
      BRACED+=("$pre$m$t")
    done
  done
}

# The words $@ joined by \001 into JOINED. No word brace_words makes holds
# a \001 (each, a mark or not, is read back as a {), so two lists of words
# join alike only when they are the same words in the same order.
join_words() {
  local IFS=$'\001'
  JOINED="$*"
}

# The words bash makes of the word $1 by brace expansion (brace_expand),
# with their marks read back as the characters, appended to PATH_WORDS: the
# words of each reading, bash 5.2's and the two of bash 5.3's (the hook runs
# under whichever bash the user has, and a word any of them makes may name
# the records). Each reading is a whole pass charged to the call's budgets;
# those after the first run only when the first met a group 5.3 reads
# otherwise (BRACE_SPLIT), since with none each is the first again. A
# reading adds its words unless a reading before it made the same words in
# the same order; a word two readings make otherwise is added twice. In
# bash, with no process started.
brace_words() {
  local w mode joined BRACE_MODE BRACE_SPLIT=0
  local -a words=() seen=()
  for mode in 5.2 5.3a 5.3c; do
    BRACE_MODE="$mode"
    brace_expand "$1" || return 2
    words=()
    for w in "${BRACED[@]}"; do
      w="${w//$'\001'/\{}"
      w="${w//$'\002'/,}"
      words+=("${w//$'\003'/\}}")
    done
    join_words "${words[@]}"
    joined="${#words[@]}:$JOINED"
    for w in ${seen[@]+"${seen[@]}"}; do
      [ "$w" != "$joined" ] || continue 2
    done
    seen+=("$joined")
    PATH_WORDS+=("${words[@]}")
    [ "$BRACE_SPLIT" = 1 ] || return 0
  done
}

# The words of a text the shell would pass as arguments, into PATH_WORDS:
# split at blanks, line breaks and ; & | < > ( ) ` $ = outside quotes, with
# '...' and "..." quoting, $'...' decoded as bash decodes it (ansi_escape),
# $"..." read as "...", a backslash keeping the character after it, the
# quotes removed, and a word with an unquoted brace expanded as bash
# expands it (brace_words). A text over 4096 bytes is not read (as
# split_words): fails (1). Past the call's budgets for brace expansion,
# fails (2).
path_words() {
  local line="$1" ch quote="" word="" esc=0 i
  PATH_WORDS=()
  if [ "${#line}" -gt 4096 ]; then return 1; fi
  for ((i = 0; i < ${#line}; i++)); do
    ch="${line:i:1}"
    if [ "$esc" = 1 ]; then
      word+="$ch"
      esc=0
    elif [ "$quote" = A ]; then
      # $'...'
      if [ "$ch" = "'" ]; then
        quote=""
      elif [ "$ch" = '\' ]; then
        ansi_escape "$line" "$((i + 1))"
        word+="$ANSI_CHAR"
        i=$((i + ANSI_LEN))
        [ "$ANSI_NUL" = 0 ] || quote=Z
      else
        word+="$ch"
      fi
    elif [ "$quote" = Z ]; then
      # What follows a NUL in $'...', up to its end, which bash drops.
      if [ "$ch" = "'" ]; then quote=""; elif [ "$ch" = '\' ]; then i=$((i + 1)); fi
    elif [ -n "$quote" ]; then
      if [ "$ch" = "$quote" ]; then
        quote=""
      elif [ "$ch" = '\' ] && [ "$quote" = '"' ]; then
        esc=1
      else
        word+="$ch"
      fi
    else
      case "$ch" in
        \' | \") quote="$ch" ;;
        \\) esc=1 ;;
        \$)
          case "${line:i+1:1}" in
            \') quote=A; i=$((i + 1)) ;;
            \") quote='"'; i=$((i + 1)) ;;
            *) path_word || return 2 ;;
          esac
          ;;
        \{) word+=$'\001' ;;
        ,) word+=$'\002' ;;
        \}) word+=$'\003' ;;
        ' ' | $'\t' | $'\n' | $'\r' | \; | \& | \| | \< | \> | \( | \) | \` | =)
          path_word || return 2
          ;;
        *) word+="$ch" ;;
      esac
    fi
  done
  path_word || return 2
  return 0
}

# The word path_words has read so far, added to PATH_WORDS (brace-expanded
# when it holds an unquoted brace), and begun again. Fails past the call's
# budgets for brace expansion.
path_word() {
  if [[ "$word" == *$'\001'* ]]; then
    brace_words "$word" || return 2
  elif [ -n "$word" ]; then
    word="${word//$'\002'/,}"
    PATH_WORDS+=("${word//$'\003'/\}}")
  fi
  word=""
}

# The path $2 names, read from the physical directory $1 ("/" or a path with
# no trailing slash), with each symbolic link on it followed as the system
# follows it (like realpath -m: a part that does not exist is kept as
# written), into RESOLVED. Fails past 40 links on the path, past the call's
# budget of LINKS_LEFT links in all (one readlink each, so a command that
# names a long chain of links many times cannot hold the hook past its time
# limit), past its budget of RESOLVE_LEFT bytes of paths, or for a link it
# cannot read. No subshell.
resolve_path() {
  local out="${1%/}" comp target links=0 i=0 IFS=/
  local -a parts more
  RESOLVE_LEFT=$((RESOLVE_LEFT - ${#2}))
  [ "$RESOLVE_LEFT" -ge 0 ] || return 1
  case "$2" in /*) out="" ;; esac
  set -f
  parts=($2)
  set +f
  while [ "$i" -lt "${#parts[@]}" ]; do
    comp="${parts[i]}"
    i=$((i + 1))
    case "$comp" in
      "" | .) continue ;;
      ..) out="${out%/*}"; continue ;;
    esac
    if [ -L "$out/$comp" ]; then
      links=$((links + 1))
      LINKS_LEFT=$((LINKS_LEFT - 1))
      [ "$links" -le 40 ] && [ "$LINKS_LEFT" -ge 0 ] || return 1
      # The target exactly: a target may end in a line break (a link to
      # $'evil\n' does not lead to evil), which a command substitution
      # would strip, so link_target prints an x after it.
      target=$(link_target "$out/$comp" 2> /dev/null) || return 1
      target="${target%x}"
      [ -n "$target" ] || return 1
      case "$target" in /*) out="" ;; esac
      set -f
      more=($target)
      set +f
      parts=("${more[@]}" "${parts[@]:i}")
      i=0
    else
      out="$out/$comp"
    fi
  done
  RESOLVED="${out:-/}"
}

# The characters that make a word, once dequoted, more than one word to a
# shell that reads it again (sh -c '...', ssh, an alias, find -exec sh -c)
# or a text that holds a quote or an escape.
NESTED='*[[:space:]\;\&\|\<\>\(\)\{\}\`\$=\"\\'\'']*'

# Add the paths a text names to READ_WORDS, as the shell would read them:
# its words (path_words), the words of each word a shell may read again
# (one that holds a blank, a quote or an operator: `sh -c 'cp x notes/k'`
# names notes/k), and, a level below that, the pieces of such a word split
# at every blank, quote and operator. Fails (2) past the call's budgets for
# brace expansion.
add_words() {
  local word inner piece flat status=0
  local -a top nested pieces
  path_words "$1" || status=$?
  case "$status" in 0) ;; 1) return 0 ;; *) return 2 ;; esac
  top=(${PATH_WORDS[@]+"${PATH_WORDS[@]}"})
  for word in ${top[@]+"${top[@]}"}; do
    READ_WORDS+=("$word")
    # shellcheck disable=SC2053
    [[ "$word" == $NESTED ]] || continue
    status=0
    path_words "$word" || status=$?
    case "$status" in 0) ;; 1) continue ;; *) return 2 ;; esac
    nested=(${PATH_WORDS[@]+"${PATH_WORDS[@]}"})
    for inner in ${nested[@]+"${nested[@]}"}; do
      READ_WORDS+=("$inner")
      # shellcheck disable=SC2053
      [[ "$inner" == $NESTED ]] || continue
      flat="${inner//[[:space:]\;\&\|\<\>\(\)\{\}\`\$=\"\\\']/ }"
      set -f
      pieces=($flat)
      set +f
      for piece in ${pieces[@]+"${pieces[@]}"}; do READ_WORDS+=("$piece"); done
    done
  done
}

# The paths a word may name, into CANDIDATES: the word as written; for one
# that opens with ~, what the shell expands it to as well (~ and ~/: $HOME;
# ~+: the call's directory; ~name: that user's home directory); and for one
# that opens with a single - (a cluster of short options), each text that
# may follow an option there as its value (-tdir, -ofile, -rtdir: from the
# second character to the first that is not a letter or digit) and can name
# a file: one whose first component exists in the call's directory (as a
# file, a directory or a link) or that is absolute. A first component that
# does not exist cannot be opened through (and a .. after it cannot be
# followed), and one of more than 255 characters exists on no file system,
# so a long cluster gives at most 256 texts to look at, not one per
# position, each read again in full. Each text added is charged to the
# call's budget, RESOLVE_LEFT bytes (one with a slash when resolve_path
# reads it). Fails (2) for ~- and ~N, ~+N, ~-N,
# which name a directory the hook cannot know (the shell's previous
# directory, its directory stack), and for ~ followed by a name no user can
# have; fails (3) past the budget.
word_candidates() {
  local word="$1" prefix rest home run k end slash first
  CANDIDATES=("$word")
  case "$word" in
    "~"*)
      prefix="${word%%/*}"
      prefix="${prefix#"~"}"
      rest="${word:$((${#prefix} + 1))}"
      case "$prefix" in
        "") CANDIDATES+=("${HOME:-/}$rest") ;;
        +) CANDIDATES+=("$base$rest") ;;
        - | [+-][0-9]* | [0-9]*) return 2 ;;
        *)
          [[ "$prefix" =~ ^[A-Za-z0-9._][A-Za-z0-9._-]*$ ]] || return 2
          # The name holds only those characters: the shell's own lookup.
          eval "home=~$prefix"
          [ "$home" = "~$prefix" ] || CANDIDATES+=("$home$rest")
          ;;
      esac
      ;;
    -[!-]*)
      run="${word:1}"
      run="${run%%[!A-Za-z0-9]*}"
      # Just past the run, and where a text from there has its first slash.
      end=$((${#run} + 1))
      rest="${word:end}"
      rest="${rest%%/*}"
      slash=$((end + ${#rest}))
      k=$((slash - 255))
      [ "$k" -ge 2 ] || k=2
      for (( ; k <= end; k++)); do
        first="${word:k:slash-k}"
        if [ -n "$first" ] && [ ! -e "${base%/}/$first" ] && [ ! -L "${base%/}/$first" ]; then
          continue
        fi
        [ -n "${word:k}" ] || continue
        if [ "$slash" -ge "${#word}" ]; then
          # No slash: resolved below without resolve_path, which charges
          # the others.
          RESOLVE_LEFT=$((RESOLVE_LEFT - ${#word} + k))
          [ "$RESOLVE_LEFT" -ge 0 ] || return 3
        fi
        CANDIDATES+=("${word:k}")
      done
      ;;
  esac
  return 0
}

# ...and through a symbolic link, a ~ the shell expands, or a path attached
# to a short option: each path a text of at most 4096 bytes names (READ_WORDS:
# a file tool's path whole; a command's or a skill's arguments as the shell
# would pass them; both for other tools) is resolved from the call's
# directory (word_candidates, resolve_path), each link on it followed, and
# one that resolves to the records is refused the same way, as is one that
# resolves to the directory that holds them (the project's .claude, the
# project's git directory's acs/): removing or moving it removes the marker
# and the audit log's head with it. A link the repository ships can lead
# there: `touch notes/todo.md`, where notes/todo.md is a link to <git
# dir>/acs/checkpoints/key, writes the key. A link a word cannot be resolved
# through (a loop, a path past 40 links, a call past 200 links in all), a
# call that names more than 262144 bytes of paths to resolve (the texts
# after an option letter included) or whose brace expansions make more than
# 8192 words, and a ~ form the hook cannot expand are refused too. Not seen: a path a command builds
# when it runs, a pattern the shell expands, or a link a command reaches
# without naming it (copying a directory that holds one); such a call is
# still a mutate a person approves.
LINKS_LEFT=200
RESOLVE_LEFT=262144
BRACE_LEFT=8192
BRACE_SCAN_LEFT=65536
READ_WORDS=()
if call_dir && resolve_path / "$CALL_DIR"; then
  base="$RESOLVED"
else
  block "R407 SAFETY_CHECK_FAILED: cannot read the directory the call runs in, so the call is blocked."
fi
texts_read=0
over_budget="${records_refusal}, or names more paths than this hook resolves in its time limit (brace expansions that make more than 8192 words or read more than 65536 braces, commas and characters, more than 262144 bytes of paths, or a cluster of short options whose values cannot be read in time), so it cannot tell where they lead."
while IFS= read -r -d '' text; do
  case "$text" in
    E) texts_read=1 ;;
    P*) READ_WORDS+=("${text:1}") ;;
    W*) add_words "${text:1}" || block "$over_budget" ;;
    B*) READ_WORDS+=("${text:1}"); add_words "${text:1}" || block "$over_budget" ;;
  esac
done < <(printf '%s' "$payload" | jq -j "$RECORD_TEXTS_JQ"'
  mode as $m | (texts[] | select(utf8bytelength <= 4096 and length > 0) | $m + (split("\u0000") | join(" ")) + "\u0000"), "E\u0000"' 2>/dev/null)
if [ "$texts_read" != 1 ]; then
  block "R407 SAFETY_CHECK_FAILED: cannot read the tool call's arguments, so the call is blocked."
fi
# Each path as the system resolves it (an array: appending to one string
# copies it whole each time).
resolved=()
for word in ${READ_WORDS[@]+"${READ_WORDS[@]}"}; do
  status=0
  word_candidates "$word" || status=$?
  case "$status" in
    0) ;;
    2) block "${records_refusal}, or names a path that opens with ~-, ~N or another ~ form this hook cannot expand (the shell's previous directory, its directory stack), so it cannot tell where the path leads." ;;
    *) block "$over_budget" ;;
  esac
  for candidate in "${CANDIDATES[@]}"; do
    # A name with no slash that is no link resolves to itself (most words).
    case "$candidate" in
      */* | . | .. | "") ;;
      *)
        if [ ! -L "${base%/}/$candidate" ]; then
          resolved+=("${base%/}/$candidate")
          continue
        fi
        ;;
    esac
    if ! resolve_path "$base" "$candidate"; then
      block "${records_refusal}, or a symbolic link on one of its paths could not be followed (a loop, more than 40 links on one path, or more than 200 in the call), or it names more paths than this hook resolves in its time limit."
    fi
    resolved+=("$RESOLVED")
  done
done
# Whether a line of the resolved paths matches grep's options and pattern
# ($@): status 0 yes, 1 no. grep -c reads every line: grep -q stops at the
# first match, and printf, with more paths than a pipe holds still to
# write, then fails (SIGPIPE), which pipefail reads as the pipeline's status,
# a match read as none. Any other answer of grep blocks the call.
resolved_match() {
  local count status=0
  count=$(printf '%s\n' "${resolved[@]}" | grep -c "$@") || status=$?
  case "$status:$count" in
    0:[1-9]*) return 0 ;;
    1:0) return 1 ;;
  esac
  block "R407 SAFETY_CHECK_FAILED: the checkpoint hook could not compare the call's paths with the layer's records (grep exited $status), so the call is blocked."
}
if [ "${#resolved[@]}" -gt 0 ] && resolved_match -Ei -- '(^|/)(checkpoint\.ok|audit\.head)(/|$)|(^|/)(\.claude|acs)/checkpoints(/|$)'; then
  block "${records_refusal}: one of its paths leads there, through a symbolic link, a ~ the shell expands or a path attached to an option."
fi
# The directories that hold the records: the project's .claude, and the
# project's git directory's acs/ (both as the system resolves them).
# Where git cannot say which git directory is the project's, the call is
# blocked: its acs/ cannot be told apart from the call's paths.
holders=()
if resolve_path / "${project_dir}/.claude"; then holders+=(-e "$RESOLVED"); fi
if command -v git > /dev/null 2>&1; then
  found=0
  git_dir_at "$project_dir" || found=$?
  case "$found" in
    0) if resolve_path / "${GIT_DIR_FOUND}/acs"; then holders+=(-e "$RESOLVED"); fi ;;
    1) ;;
    *) block "R407 SAFETY_CHECK_FAILED: git did not say in time which git directory is the project's (one whose configuration includes a FIFO or a terminal holds git), so the call's paths cannot be compared with the layer's records and the call is blocked." ;;
  esac
fi
if [ "${#holders[@]}" -gt 0 ] && [ "${#resolved[@]}" -gt 0 ] && resolved_match -Fxi "${holders[@]}"; then
  block "F504 CONSTRAINT_VIOLATED: ${shown_tool} names the directory that holds the layer's records (the project's .claude, its git directory's acs/), which only the plugin's hooks write: moving or removing it, or writing into it, removes or replaces the checkpoint marker and the audit log's head."
fi

# mutate: a valid marker for this call alone.
f501() {
  block "F501 CHECKPOINT_REQUIRED: $1"
}

if [ ! -e "$marker" ]; then
  f501 "missing checkpoint marker ($marker). Take a checkpoint first (git stash create); each gated call needs its own."
fi

# SEC-006: Reject symlinks to prevent bypass via symlink to always-existing file
if [ -L "$marker" ]; then
  f501 "checkpoint marker is a symlink. Remove it and take a proper checkpoint."
fi

if [ ! -f "$marker" ]; then
  f501 "checkpoint marker is not a regular file."
fi

# A marker git tracks came with the repository (a clone or a checkout can
# ship one), not from a checkpoint taken here: it authorises nothing, and is
# left as it is. git is asked from the marker's own directory, so a .claude
# that is a symbolic link or a submodule is read where it leads; but only
# where the git directory git finds there is one git made for a work tree
# (git_dir_is_made): a repository can ship .claude, or a directory above it,
# as a git directory of its own (HEAD, objects/, refs/), whose index would
# answer for the marker and whose config names programs git runs (hgit runs
# none). git answers yes (0) or no (1); any other answer authorises nothing
# either.
found=0
if command -v git > /dev/null 2>&1; then git_dir_at "$claude_dir" || found=$?; else found=1; fi
case "$found" in
  0 | 1) ;;
  *) f501 "git did not say in time which git directory holds the checkpoint marker (one whose configuration includes a FIFO or a terminal holds git): it authorises nothing." ;;
esac
if [ "$found" = 0 ]; then
  marker_git="$GIT_DIR_FOUND"
  if ! git_dir_is_made "$marker_git"; then
    f501 "the checkpoint marker is in a git directory that git did not make for a work tree ($marker_git, which a repository can ship): it authorises nothing. Remove that directory's HEAD, objects/ and refs/ from the repository and take a checkpoint (git stash create)."
  fi
  tracked=0
  hgit -C "$claude_dir" ls-files --error-unmatch -- checkpoint.ok > /dev/null 2>&1 || tracked=$?
  case "$tracked" in
    0) f501 "the checkpoint marker is tracked by git, so a repository shipped it: it authorises nothing. Remove it from the repository and take a checkpoint (git stash create)." ;;
    1) ;;
    *) f501 "git cannot say whether the checkpoint marker is tracked (git ls-files exited $tracked): it authorises nothing." ;;
  esac
fi

# SEC-001: Validate timestamp freshness
content=$(cat "$marker" 2>/dev/null || echo "")
if [ -z "$content" ]; then
  rm -f "$marker"
  f501 "checkpoint marker is empty. Take a new checkpoint."
fi

# A marker that is not a JSON object (plain text, a string, an array) makes jq
# fail: that is a block, like a marker without the fields.
if ! checkpoint_id=$(printf '%s' "$content" | jq -r 'if type == "object" then (.checkpoint_id // empty | tostring) else error("not an object") end' 2>/dev/null) \
  || ! created_at=$(printf '%s' "$content" | jq -r '.created_at // empty' 2>/dev/null) \
  || ! expires_at=$(printf '%s' "$content" | jq -r '.expires_at // empty' 2>/dev/null); then
  rm -f "$marker"
  f501 "checkpoint marker is not a JSON object. Take a new checkpoint."
fi
if [ -z "$checkpoint_id" ] || [ -z "$created_at" ] || [ -z "$expires_at" ]; then
  rm -f "$marker"
  f501 "checkpoint marker missing required fields. Take a new checkpoint."
fi
# Whole seconds of at most 12 digits, so the arithmetic below cannot
# overflow: a value it cannot compare must not pass as unexpired.
if ! [[ "$created_at" =~ ^[0-9]{1,12}$ ]] || ! [[ "$expires_at" =~ ^[0-9]{1,12}$ ]]; then
  rm -f "$marker"
  f501 "checkpoint marker has invalid times. Take a new checkpoint."
fi
now=$(date +%s)
if ! [[ "$now" =~ ^[0-9]{1,12}$ ]]; then
  block "R407 SAFETY_CHECK_FAILED: the checkpoint hook could not read the clock, so the call is blocked."
fi
created_at=$((10#$created_at))
expires_at=$((10#$expires_at))
if ((created_at > now || expires_at > created_at + 1800)); then
  rm -f "$marker"
  f501 "checkpoint marker's times are not possible: taken in the future, or valid for more than 30 minutes (STANDARD 1.2.0 §5.18.6). Take a new checkpoint."
fi
# The layer's maximum age (§5.18.6), as the take and log hooks read it: a
# marker written under a longer one (another writer, an earlier setting)
# authorises nothing past it.
max_age="${ACS_CHECKPOINT_MAX_AGE:-1800}"
if ! [[ "$max_age" =~ ^[0-9]{1,4}$ ]] || ((10#$max_age < 1 || 10#$max_age > 1800)); then
  max_age=1800
fi
max_age=$((10#$max_age))
if ((now > expires_at || now > created_at + max_age)); then
  # Its validity has ended, not its record: file it under ended/, so that a
  # rollback can still restore its commit. Removed only if that fails.
  mkdir -p "$ended_dir" 2>/dev/null || true
  if ! { ended=$(mktemp "${ended_dir}/expired.XXXXXX" 2>/dev/null) && mv -f "$marker" "$ended" 2>/dev/null; }; then
    rm -f "$marker" "${ended:-}" 2>/dev/null || true
  fi
  f501 "checkpoint has expired. Take a new checkpoint."
fi

# Approval needs a person (§5.18.7): checked before the marker is taken, so a
# block here uses nothing.
require_person

# Take the marker: one rename into a directory this run alone created, atomic
# on one filesystem, so of two calls that both read the marker only one can
# move it. Then it is filed under used/ (the rollback history). Names are kept
# to a safe character set, so a marker cannot name a path elsewhere.
safe() {
  printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-120
}
call_id=$(printf '%s' "$payload" | jq -r '.tool_use_id // empty | strings' 2>/dev/null) || call_id=""
call_id="${call_id:-$(date +%s)-$$}"
mkdir -p "$used_dir"
claim=$(mktemp -d "${used_dir}/.claim.XXXXXX")
if ! mv "$marker" "${claim}/marker" 2>/dev/null || [ ! -e "${claim}/marker" ]; then
  rmdir "$claim" 2>/dev/null || true
  f501 "the checkpoint marker was taken by another call. Take a new checkpoint."
fi
mv "${claim}/marker" "${used_dir}/$(safe "$checkpoint_id").$(safe "$call_id").${claim##*.}"
rmdir "$claim"

if [ "$unbound" = 1 ]; then
  reason="F502 APPROVAL_REQUIRED: ${shown_tool} (unbound: treated as a mutation, STANDARD 1.2.0 §5.18.2) requires approval; it runs only if this call is approved."
elif [ "$unseen" = 1 ]; then
  reason="F502 APPROVAL_REQUIRED: ${shown_tool} (capability 'mutate': the shell commands a skill's file embeds, and the hooks and MCP servers a subagent's definition names, run with no hook seeing them) requires approval; it runs only if this call is approved."
else
  reason="F502 APPROVAL_REQUIRED: ${shown_tool} (capability 'mutate') requires approval; it runs only if this call is approved."
fi
ask_person "$reason"
exit 0
