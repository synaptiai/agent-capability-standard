#!/usr/bin/env bash
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
# .claude/settings.local.json, repository content, over the user's settings:
# while either file names one of them, or cannot be read, every call is
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
#         runs in the project's repository (its cwd) and the repository's
#         own configuration and hooks name no program git runs; any other
#         pop or apply, a bare one included, is mutate, since git applies
#         any merge commit as if it were a stash; any other git stash form:
#         mutate;
#       - a first word holding a blank (a quoted "git status") or a slash:
#         bash runs the program of that name, which is on no list: mutate;
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
#     through a symbolic link, a ~ the shell expands or a path attached to a
#     short option: each path a text of at most 4096 bytes names is resolved
#     as the system resolves a path), or the directory that holds them (the
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
# or reach a host.
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

if [ "$#" -gt 0 ]; then
  payload="$1"
else
  payload="$(cat)"
fi

unreadable="R407 SAFETY_CHECK_FAILED: cannot read the tool call (a JSON payload and jq are required)"
if ! command -v jq > /dev/null 2>&1; then
  block "$unreadable"
fi
tool_name=$(printf '%s' "$payload" | jq -r 'if type == "object" then (.tool_name | strings) else error("not an object") end' 2>/dev/null) || tool_name=""
if [ -z "$tool_name" ]; then
  block "$unreadable"
fi

# SEC-006: Use absolute path via CLAUDE_PROJECT_DIR, fall back to CLAUDE_PLUGIN_ROOT, then pwd
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  project_dir="${CLAUDE_PROJECT_DIR}"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  project_dir="${CLAUDE_PLUGIN_ROOT}"
else
  project_dir="$(pwd)"
fi

# The layer's settings (ACS_HOOK_APPROVAL, ACS_CHECKPOINT_MAX_AGE,
# AUDIT_HMAC_KEY, AUDIT_LOCK_WAIT) that the project's own settings files,
# .claude/settings.json and .claude/settings.local.json in the project
# directory $1, name in their env, in any letter case, one to a line; for a
# file jq cannot read, its name. Claude Code applies those files' env, which
# is repository content, to every hook, over the user's settings and the
# environment it started in, so a hook cannot tell the person's value of
# such a setting from the repository's (ACS_HOOK_APPROVAL=off, an
# AUDIT_HMAC_KEY the repository knows, a longer maximum age). The three
# hooks that read a setting hold the same function; a test keeps them so,
# and keeps every setting a hook reads named in it.
project_layer_settings() {
  local file
  for file in "$1/.claude/settings.json" "$1/.claude/settings.local.json"; do
    if [ -e "$file" ] || [ -L "$file" ]; then
      jq -r 'if type == "object" and (.env | type) == "object" then .env | keys[] | select(test("^(acs_hook_approval|acs_checkpoint_max_age|audit_hmac_key|audit_lock_wait)$"; "i")) else empty end' "$file" 2>/dev/null \
        || printf '%s\n' ".claude/${file##*/} (unreadable)"
    fi
  done
}

# A setting the repository may have chosen configures nothing: every call is
# refused until it is set where the repository cannot reach (§5.18.8: the
# layer cannot complete its checks, nor sign the call's record, with a value
# it cannot trust).
named=$(project_layer_settings "$project_dir") || named="(unreadable)"
# Shown in the reason: the first 400 characters, one line, plain.
named="${named:0:400}"
named="${named//$'\n'/ }"
named="${named//[^A-Za-z0-9_.\/() ]/?}"
if [ -n "$named" ]; then
  block "R407 SAFETY_CHECK_FAILED: the project's settings files name the layer's settings in env, or cannot be read: ${named% }. Claude Code applies a project's env, which is repository content, over yours, so the call is blocked. Remove them from .claude/settings.json and .claude/settings.local.json, and set them in ~/.claude/settings.json, in managed settings or in the environment Claude Code starts in."
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
# secret_in TEXT: status 0 when TEXT holds a credential-shaped value (STANDARD 1.2.0 §6.7).
SECRET_ERE='-----BEGIN [A-Z ]*PRIVATE KEY-----|(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|[Bb]earer[[:space:]]+[A-Za-z0-9._~+/=-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
SECRET_KEY='(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key)'
# A quote, or an escaped one (\" in JSON text inside a JSON string)
SECRET_Q="\\\\*[\"']"
# A command's option named for a credential (--password, --api-key), and a user option (curl -u user:password)
SECRET_OPT="(^|[^A-Za-z0-9_-])--([A-Za-z0-9]+[_-])*$SECRET_KEY"
SECRET_SEP="([[:space:]]+($SECRET_Q)?|=($SECRET_Q)?|($SECRET_Q)?[[:space:]]*,[[:space:]]*$SECRET_Q)"
SECRET_USER="(^|[^A-Za-z0-9_-])(-[uU]$SECRET_SEP?|--(proxy-)?user$SECRET_SEP)[^[:space:]:\"'\\\\]*:"
secret_in() {
  printf '%s' "$1" | grep -Eq -- "$SECRET_ERE" && return 0
  # A quoted value with no whitespace, 8 or more characters, assigned or given to a credential option
  printf '%s' "$1" | grep -Eiq -- "$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[^[:space:]\"']{8,}[\"']|$SECRET_OPT([[:space:]]+|($SECRET_Q)?[[:space:]]*,[[:space:]]*)$SECRET_Q[^-[:space:]\"'][^[:space:]\"']{7,}[\"']" && return 0
  # The password of a URL's userinfo, unless it is a placeholder
  printf '%s' "$1" | grep -Eo -- '[A-Za-z][A-Za-z0-9+.-]*://[^[:space:]/:@]*:[^[:space:]/@]+@' |
    sed -E 's#^[^/]*//[^:]*:##; s#@$##' | grep -Eivq -- '^([$<{*[].*|password|passwd|pwd|pass|secret|token)$' && return 0
  # An Authorization header's value, 8 or more characters with letters and digits
  printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}" |
    sed -E "s/^[^:=]*[:=][[:space:]]*(\\\\*[\"'])?//" |
    sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
    grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
  # A header's or credential's value given as a name/value pair, or a tuple of exactly two, in text: 8 or more characters with letters and digits
  printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
    sed -E "s/\\\\*[\"'][[:space:]]*[])]\$//; s/^.*[:=,][[:space:]]*\\\\*[\"']//" |
    sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
    grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
  # A user option's password (curl -u user:password), 8 or more characters with letters and digits
  printf '%s' "$1" | grep -Eo -- "$SECRET_USER[^[:space:]\"'\\\\]{8,}" |
    sed -E 's/^[^:]*://' | grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
  # An unquoted value of 12 or more characters with letters and digits, assigned or given to a credential option
  printf '%s' "$1" | grep -Eio -- "$SECRET_OPT[[:space:]]+[^-[:space:]\"'][^[:space:]\"']{11,}" |
    sed -E 's/^.*[[:space:]]//' | grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
  printf '%s' "$1" | grep -Eio -- "$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*[^[:space:]\"']{12,}" |
    sed -E 's/^[^:=]*[:=][[:space:]]*//' | grep -E '[0-9]' | grep -Eq '[A-Za-z]'
}
# END secret-scan


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
# the index, and hooks) and no object fetched from a promisor remote, so no
# repository content makes this hook run a program or reach a host.
# posttooluse_take_checkpoint.sh holds the same function.
hgit() {
  GIT_NO_LAZY_FETCH=1 git -c core.fsmonitor=false -c core.hooksPath=/dev/null "$@"
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

# The directory the call runs in: its cwd, else the project directory.
# Fails when the payload cannot be read.
call_dir() {
  local dir
  dir=$(printf '%s' "$payload" | jq -r '.cwd // "" | strings' 2>/dev/null) || return 1
  printf '%s' "${dir:-${CLAUDE_PROJECT_DIR:-$PWD}}"
}

# Whether the git directory git finds where this call runs is repository
# content (not one git made for a work tree, git_dir_is_made): there git
# reads that directory's config and hooks, and runs what they name
# (core.fsmonitor for git status, git ls-files and git stash,
# diff.<driver>.textconv for git log -p, git show and git diff). No
# repository there: no. The SDK mapper asks the same (git_dir_may_be_content).
git_dir_is_content() {
  local dir git_dir
  dir=$(call_dir) || return 0
  command -v git > /dev/null 2>&1 || return 0
  git_dir=$(hgit -C "$dir" rev-parse --absolute-git-dir 2>/dev/null) || return 1
  ! git_dir_is_made "$git_dir"
}

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
  dir=$(call_dir) || return 0
  command -v git > /dev/null 2>&1 || return 0
  hgit -C "$dir" rev-parse --absolute-git-dir > /dev/null 2>&1 || return 1
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
  hooks=$(GIT_NO_LAZY_FETCH=1 git -c core.fsmonitor=false -C "$dir" rev-parse --git-path hooks 2>/dev/null) || return 0
  [ -n "$hooks" ] || return 0
  case "$hooks" in /*) ;; *) hooks="$dir/$hooks" ;; esac
  [ -e "$hooks/post-index-change" ] || [ -L "$hooks/post-index-change" ]
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
  dir=$(call_dir) || return 0
  command -v git > /dev/null 2>&1 || return 0
  git_dir=$(hgit -C "$dir" rev-parse --absolute-git-dir 2>/dev/null) || git_dir=""
  if [ -n "$git_dir" ] && ! git_dir_is_made "$git_dir"; then return 0; fi
  if git_runs_configured; then return 0; fi
  found=$(hgit -C "$dir" config --get-regexp '^(remote\..+\.promisor|extensions\.partialclone)$' 2>/dev/null) || status=$?
  if [ "$status" != 1 ] || [ -n "$found" ]; then return 0; fi
  if [ -n "$git_dir" ]; then
    common=$(hgit -C "$dir" rev-parse --git-common-dir 2>/dev/null) || return 0
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
        elif [ "${#words[@]}" -eq 4 ] && [[ "${words[3]}" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]] && ! git_runs_configured; then
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
# redaction replaces that is not a placeholder: the SDK redactor's rule for
# data (grounded_agency/state/redaction.py, _secret_member_value; a test
# keeps the two in agreement). A member is secret when its name ends in a
# credential's name or names a header that carries one (Authorization,
# Cookie), when it is the value of a name/value pair whose name is such a
# name ({"name": "Authorization", "value": ...}), the second of a [name,
# value] tuple, or inside a secret member. Its value counts when it is a
# number, or a string of 4 or more characters other than [REDACTED] that is
# not a placeholder (<...>, ${...}, ****, password, token, ...). jq's case
# folding is Unicode's where the SDK's is ASCII's, so the hook finds a name
# the SDK does not in rare spellings, never the reverse.
SECRET_MEMBER_JQ='
def acs_name: test("\\A[\\s\\S]*(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|authorization|cookies?)\\z"; "i");
def acs_scalar: (type == "string" and length >= 4 and . != "[REDACTED]") or type == "number";
def acs_placeholder: type == "string" and test("\\A([$<{*\\[][^\\n]*|password|passwd|pwd|pass|secret|token)\\z"; "i");
def acs_held($secret):
  if $secret and acs_scalar then (acs_placeholder | not)
  elif type == "object" then
    (($secret | not) and any(to_entries[]; (.key | test("\\A(name|key|header)\\z"; "i")) and (.value | type == "string" and acs_name))) as $pair
    | any(to_entries[]; .key as $k | .value | acs_held($secret or ($k | acs_name) or ($pair and ($k | test("\\Avalue\\z"; "i")))))
  elif type == "array" then
    (($secret | not) and length == 2 and (.[0] | type == "string" and acs_name)) as $tuple
    | any(to_entries[]; .key as $i | .value | acs_held($secret or ($tuple and $i == 1)))
  else false end;
'

# persist: the data the call would store holds no secret the layer
# recognises (§5.18.10, §6.7), as the SDK adapter decides it
# (Redactor.holds_credential): a credential-shaped value in any string of
# the input or in the input's JSON text (secret_in), or a value in a member
# named for a credential (SECRET_MEMBER_JQ). NUL bytes, which a shell
# variable cannot hold, are read as blanks. The scan runs without pipefail:
# a grep -q that stops at a match ends the printf feeding it, and with
# pipefail that would read as no match.
for entry in "${PERSIST_TOOLS[@]}"; do
  if [ "$tool_name" = "$entry" ]; then
    unread="R407 SAFETY_CHECK_FAILED: cannot read the data $tool_name would store, so the call is blocked."
    held=$(printf '%s' "$payload" | jq -r "$SECRET_MEMBER_JQ"' .tool_input | acs_held(false)' 2>/dev/null) || block "$unread"
    stored=$(printf '%s' "$payload" | jq -r '.tool_input | ([.. | strings] | join("\n")) + "\n" + tojson | split("\u0000") | join(" ")' 2>/dev/null) || block "$unread"
    if [ "$held" = "true" ] || { [ "$held" = "false" ] && (set +o pipefail; secret_in "$stored"); }; then
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

# The git directory of the repository a directory is in (absolute), or
# nothing.
git_dir_of() {
  command -v git > /dev/null 2>&1 || return 1
  hgit -C "$1" rev-parse --absolute-git-dir 2>/dev/null
}

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
  local git_dir ran_in cwd entry sig have
  git_dir=$(git_dir_of "$project_dir") || return 1
  [ -n "$git_dir" ] && git_dir_is_made "$git_dir" || return 1
  # The call restores into the repository it runs in (its cwd): the
  # project's, or the commit is another repository's state.
  cwd=$(printf '%s' "$payload" | jq -r '.cwd // "" | strings' 2>/dev/null) || return 1
  if [ -n "$cwd" ]; then
    ran_in=$(git_dir_of "$cwd") || return 1
    [ "$ran_in" = "$git_dir" ] || return 1
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
# for paths below: more than 65536 bytes of them in one call is refused,
# rather than hold the hook past its time limit.
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
  | if any($t[]; records or (length <= 4096 and (lexical | records))) then "named"
    elif ([$t[] | utf8bytelength | select(. <= 4096)] | add // 0) > 65536 then "over"
    else "no" end' 2>/dev/null) || block "R407 SAFETY_CHECK_FAILED: cannot read the tool call's arguments, so the call is blocked."
records_refusal="F504 CONSTRAINT_VIOLATED: ${tool_name} names the checkpoint records (.claude/checkpoint.ok, .claude/checkpoints/, the git directory's acs/checkpoints/) or the audit log's head (.claude/audit.head), which only the plugin's hooks write"
case "$records_named" in
  no) ;;
  over) block "F504 CONSTRAINT_VIOLATED: ${tool_name}'s input holds more than 65536 bytes of strings of at most 4096 bytes, more than this hook reads for paths into the layer's records (.claude/checkpoint.ok, .claude/checkpoints/, the git directory's acs/checkpoints/, .claude/audit.head) in its time limit, so the call is blocked." ;;
  *) block "${records_refusal}." ;;
esac

# The words of a text the shell would pass as arguments, into PATH_WORDS:
# split at blanks, line breaks and ; & | < > ( ) { } ` $ = outside quotes,
# with '...' and "..." quoting, a backslash keeping the character after it,
# and the quotes removed. A text over 4096 bytes is not read (as
# split_words).
path_words() {
  local line="$1" ch quote="" word="" esc=0 i
  PATH_WORDS=()
  if [ "${#line}" -gt 4096 ]; then return 1; fi
  for ((i = 0; i < ${#line}; i++)); do
    ch="${line:i:1}"
    if [ "$esc" = 1 ]; then
      word+="$ch"
      esc=0
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
        ' ' | $'\t' | $'\n' | $'\r' | \; | \& | \| | \< | \> | \( | \) | \{ | \} | \` | \$ | =)
          if [ -n "$word" ]; then PATH_WORDS+=("$word"); fi
          word=""
          ;;
        *) word+="$ch" ;;
      esac
    fi
  done
  if [ -n "$word" ]; then PATH_WORDS+=("$word"); fi
  return 0
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
      target=$(readlink -- "$out/$comp" 2>/dev/null) || return 1
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
# at every blank, quote and operator.
add_words() {
  local word inner piece flat
  local -a top nested pieces
  path_words "$1" || return 0
  top=(${PATH_WORDS[@]+"${PATH_WORDS[@]}"})
  for word in ${top[@]+"${top[@]}"}; do
    READ_WORDS+=("$word")
    # shellcheck disable=SC2053
    [[ "$word" == $NESTED ]] || continue
    path_words "$word" || continue
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
# second character to the first that is not a letter or digit). Fails (2)
# for ~- and ~N, ~+N, ~-N, which name a directory the hook cannot know (the
# shell's previous directory, its directory stack), and for ~ followed by a
# name no user can have.
word_candidates() {
  local word="$1" prefix rest home run k
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
      for ((k = 2; k <= ${#run} + 1; k++)); do
        [ -z "${word:k}" ] || CANDIDATES+=("${word:k}")
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
# call that names more than 262144 bytes of paths to resolve, and a ~ form
# the hook cannot expand are refused too. Not seen: a path a command builds
# when it runs, a pattern the shell expands, or a link a command reaches
# without naming it (copying a directory that holds one); such a call is
# still a mutate a person approves.
LINKS_LEFT=200
RESOLVE_LEFT=262144
READ_WORDS=()
if base=$(call_dir) && resolve_path / "$base"; then
  base="$RESOLVED"
else
  block "R407 SAFETY_CHECK_FAILED: cannot read the directory the call runs in, so the call is blocked."
fi
texts_read=0
while IFS= read -r -d '' text; do
  case "$text" in
    E) texts_read=1 ;;
    P*) READ_WORDS+=("${text:1}") ;;
    W*) add_words "${text:1}" ;;
    B*) READ_WORDS+=("${text:1}"); add_words "${text:1}" ;;
  esac
done < <(printf '%s' "$payload" | jq -j "$RECORD_TEXTS_JQ"'
  mode as $m | (texts[] | select(utf8bytelength <= 4096) | $m + (split("\u0000") | join(" ")) + "\u0000"), "E\u0000"' 2>/dev/null)
if [ "$texts_read" != 1 ]; then
  block "R407 SAFETY_CHECK_FAILED: cannot read the tool call's arguments, so the call is blocked."
fi
# Each path as the system resolves it (an array: appending to one string
# copies it whole each time).
resolved=()
for word in ${READ_WORDS[@]+"${READ_WORDS[@]}"}; do
  if ! word_candidates "$word"; then
    block "${records_refusal}, or names a path that opens with ~-, ~N or another ~ form this hook cannot expand (the shell's previous directory, its directory stack), so it cannot tell where the path leads."
  fi
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
if [ "${#resolved[@]}" -gt 0 ] && printf '%s\n' "${resolved[@]}" | grep -Eiq '(^|/)(checkpoint\.ok|audit\.head)(/|$)|(^|/)(\.claude|acs)/checkpoints(/|$)'; then
  block "${records_refusal}: one of its paths leads there, through a symbolic link, a ~ the shell expands or a path attached to an option."
fi
# The directories that hold the records: the project's .claude, and the
# project's git directory's acs/ (both as the system resolves them).
holders=()
if resolve_path / "${project_dir}/.claude"; then holders+=(-e "$RESOLVED"); fi
if records_git_dir=$(git_dir_of "$project_dir") && [ -n "$records_git_dir" ] && resolve_path / "${records_git_dir}/acs"; then
  holders+=(-e "$RESOLVED")
fi
if [ "${#holders[@]}" -gt 0 ] && [ "${#resolved[@]}" -gt 0 ] && printf '%s\n' "${resolved[@]}" | grep -Fxiq "${holders[@]}"; then
  block "F504 CONSTRAINT_VIOLATED: ${tool_name} names the directory that holds the layer's records (the project's .claude, its git directory's acs/), which only the plugin's hooks write: moving or removing it, or writing into it, removes or replaces the checkpoint marker and the audit log's head."
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
if command -v git > /dev/null 2>&1 && marker_git=$(git_dir_of "$claude_dir"); then
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
  reason="F502 APPROVAL_REQUIRED: ${tool_name} (unbound: treated as a mutation, STANDARD 1.2.0 §5.18.2) requires approval; it runs only if this call is approved."
elif [ "$unseen" = 1 ]; then
  reason="F502 APPROVAL_REQUIRED: ${tool_name} (capability 'mutate': the shell commands a skill's file embeds, and the hooks and MCP servers a subagent's definition names, run with no hook seeing them) requires approval; it runs only if this call is approved."
else
  reason="F502 APPROVAL_REQUIRED: ${tool_name} (capability 'mutate') requires approval; it runs only if this call is approved."
fi
ask_person "$reason"
exit 0
