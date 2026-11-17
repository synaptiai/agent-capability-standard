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
#     neither a checkpoint nor approval: Read, Grep, Skill, Agent, ...):
#     allowed, nothing used.
#   - Write, Edit, MultiEdit, NotebookEdit: mutate.
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
#         (--compi); and, for git and file, a word with an unquoted *, ? or
#         [, which bash replaces with file names, options included: mutate;
#       - git stash create: checkpoint (allowed; posttooluse_take_checkpoint.sh
#         writes the marker once it succeeded); git stash list|show: observe;
#         git stash pop|apply <commit>: rollback when <commit> is the full id
#         of a commit posttooluse_take_checkpoint.sh entered in the project's
#         git directory (<git dir>/acs/checkpoints/commits/, a lookup of one
#         file however many checkpoints were taken) and the call runs in the
#         project's repository (its cwd); any other pop or apply, a bare one
#         included, is mutate, since git applies any merge commit as if it
#         were a stash; any other git stash form: mutate;
#       - a command on READ_ONLY: observe (allowed, nothing used);
#       - anything else: mutate.
#   - Any other tool (Monitor, PowerShell, ExitWorktree, every MCP tool, a
#     tool this hook does not know): unbound, so mutate (§5.18.2: a layer
#     cannot know that an unknown tool only reads).
#
# Rules.
#   - rollback: restores a checkpoint this project recorded, so a checkpoint
#     was taken; allowed, and it uses none. (F503 ROLLBACK_FAILED cannot
#     arise: a restore of anything else is mutate.) The commits are entered
#     in the git directory, outside the work tree, so no clone, checkout or
#     applied stash can ship an entry.
#   - mutate: a call whose arguments name the layer's own records
#     (checkpoint.ok, .claude/checkpoints/, acs/checkpoints/) is refused
#     (F504 CONSTRAINT_VIOLATED): only these hooks write them. Then the
#     marker (.claude/checkpoint.ok, a JSON object with checkpoint_id,
#     created_at, expires_at) must exist, be a regular file that git does not
#     track (a repository can ship a tracked one), have times that are whole
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

# Tools whose calls need nothing from this hook: the SDK mapper's static
# mappings (_TOOL_MAPPINGS) whose capability needs neither a checkpoint nor
# approval (retrieve, search, observe, recall, persist, delegate, invoke,
# inquire). Every other tool but Bash is classified mutate.
UNGATED_TOOLS=(Read Glob Grep LS WebFetch WebSearch Task Agent Skill AskUser AskUserQuestion TodoRead TodoWrite TaskList TaskGet TaskCreate TaskUpdate ToolSearch BashOutput TaskOutput ListMcpResourcesTool ReadMcpResourceTool ExitPlanMode)

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
    for entry in "${GIT_STASH_CLASSES[@]}"; do
      if [ "${entry%%=*}" = "${words[2]:-}" ]; then
        if [ "${entry#*=}" != "rollback" ]; then
          echo "${entry#*=}"
        elif [ "${#words[@]}" -eq 4 ] && [[ "${words[3]}" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]]; then
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
  for entry in "${READ_ONLY[@]}"; do
    if [ "$entry" = "${words[0]}" ] || [ "$entry" = "${words[0]} ${words[1]:-}" ]; then
      echo observe
      return
    fi
  done
  echo mutate
}

for entry in "${UNGATED_TOOLS[@]}"; do
  if [ "$tool_name" = "$entry" ]; then
    exit 0
  fi
done

# Unbound: a tool this hook does not know, MCP tools included, is a mutate
# (§5.18.2), and its refusals and its approval request name no capability.
unbound=0
case "$tool_name" in
  Write | Edit | MultiEdit | NotebookEdit)
    capability=mutate
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

# SEC-006: Use absolute path via CLAUDE_PROJECT_DIR, fall back to CLAUDE_PLUGIN_ROOT, then pwd
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  project_dir="${CLAUDE_PROJECT_DIR}"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  project_dir="${CLAUDE_PLUGIN_ROOT}"
else
  project_dir="$(pwd)"
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
  git -C "$1" rev-parse --absolute-git-dir 2>/dev/null
}

# Whether a checkpoint of this project recorded the commit $1 (a full commit
# id, so a safe file name) as its restore point, for a call that runs in the
# project's repository: posttooluse_take_checkpoint.sh enters each such
# commit as an empty file named by it, in <git dir>/acs/checkpoints/commits/,
# before it writes the marker. That directory is outside the work tree: a
# clone, a checkout or an applied stash can put files in the work tree,
# .claude/ included, but none in it. One lookup, however many checkpoints
# were taken. A checkpoint can be restored valid or not (§5.18.6).
recorded_commit() {
  local git_dir ran_in cwd entry
  git_dir=$(git_dir_of "$project_dir") || return 1
  [ -n "$git_dir" ] || return 1
  # The call restores into the repository it runs in (its cwd): the
  # project's, or the commit is another repository's state.
  cwd=$(printf '%s' "$payload" | jq -r '.cwd // "" | strings' 2>/dev/null) || return 1
  if [ -n "$cwd" ]; then
    ran_in=$(git_dir_of "$cwd") || return 1
    [ "$ran_in" = "$git_dir" ] || return 1
  fi
  entry="${git_dir}/acs/checkpoints/commits/$1"
  [ -f "$entry" ] && [ ! -L "$entry" ]
}

if [[ "$capability" == "rollback "* ]]; then
  # Restoring a recorded checkpoint uses none. Applying any other commit
  # changes the tree like any write.
  if recorded_commit "${capability#rollback }"; then
    exit 0
  fi
  capability=mutate
fi

# The layer's records are written by these hooks alone: a Write, Edit,
# MultiEdit or NotebookEdit of a path, or a Bash command, that names the
# marker or the checkpoint directories is refused (a written entry would be
# a permanent pass for a restore, a written marker a checkpoint no call
# took). This reads the text: a path a command builds when it runs is not
# seen, and such a call is still a mutate a person approves.
records_named=$(printf '%s' "$payload" | jq -r '
  (if .tool_name == "Bash" then .tool_input.command
   elif .tool_name == "Write" or .tool_name == "Edit" or .tool_name == "MultiEdit" or .tool_name == "NotebookEdit"
   then (.tool_input.file_path // .tool_input.notebook_path)
   else null end) as $text
  | ($text | strings | test("checkpoint\\.ok|\\.claude/checkpoints|acs/checkpoints")) // false' 2>/dev/null) || records_named=true
if [ "$records_named" != "false" ]; then
  block "F504 CONSTRAINT_VIOLATED: ${tool_name} names the checkpoint records (.claude/checkpoint.ok, .claude/checkpoints/, the git directory's acs/checkpoints/), which only the plugin's hooks write."
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
# that is a symbolic link or a submodule is read where it leads.
if command -v git > /dev/null 2>&1 \
  && git -C "$claude_dir" ls-files --error-unmatch -- checkpoint.ok > /dev/null 2>&1; then
  f501 "the checkpoint marker is tracked by git, so a repository shipped it: it authorises nothing. Remove it from the repository and take a checkpoint (git stash create)."
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
approval="${ACS_HOOK_APPROVAL:-ask}"
if [ "$approval" != "off" ]; then
  mode=$(printf '%s' "$payload" | jq -r '.permission_mode // "default" | if type == "string" then . else "(not a string)" end' 2>/dev/null) || mode="(unreadable)"
  case "$mode" in
    default | acceptEdits | plan) ;;
    *)
      block "F502 APPROVAL_REQUIRED: permission mode '$mode' does not put this call to a person; set ACS_HOOK_APPROVAL=off to leave approval to Claude Code's permission rules."
      ;;
  esac
fi

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

if [ "$approval" != "off" ]; then
  if [ "$unbound" = 1 ]; then
    reason="F502 APPROVAL_REQUIRED: ${tool_name} (unbound: treated as a mutation, STANDARD 1.2.0 §5.18.2) requires approval; it runs only if this call is approved."
  else
    reason="F502 APPROVAL_REQUIRED: ${tool_name} (capability 'mutate') requires approval; it runs only if this call is approved."
  fi
  jq -c -n --arg reason "$reason" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason}}'
fi
exit 0
