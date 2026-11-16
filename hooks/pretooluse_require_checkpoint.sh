#!/usr/bin/env bash
# Apply the checkpoint and approval rules of STANDARD 1.2.0 §5.18 to the tool
# calls Claude Code routes here (hooks.json: Write, Edit, MultiEdit,
# NotebookEdit and Bash), as a PreToolUse command hook.
#
# Claude Code passes the tool call as a JSON object on stdin:
# {"tool_name", "tool_input", "permission_mode", "tool_use_id", ...}. For manual
# use, a payload given as the first argument is read instead. Only that JSON
# object is read: anything else, or a system without jq, is blocked with
# R407 SAFETY_CHECK_FAILED.
#
# Exit codes follow Claude Code's hook contract:
#   0  allow the tool call (with an "ask" decision on stdout for a gated call)
#   2  block it; the reason on stderr is shown to Claude
#
# Each reason opens with the Standard's code and name (§9.8), for example
# "F501 CHECKPOINT_REQUIRED: ...".
#
# Classification (§5.18.3). The read-only list and the git stash table are a
# subset of the SDK mapper's (grounded_agency/capabilities/mapper.py:
# _READ_ONLY_COMMANDS, _GIT_STASH_CLASSES, _writes); a test keeps them so.
#   - Write, Edit, MultiEdit, NotebookEdit: mutate.
#   - Bash: a command with any of ; & | < > $ ` ( ) { } \ or a line break may
#     be more than one simple command or expand something: mutate. Otherwise
#     its words are read as bash reads them, as exactly one simple command
#     (split_words: '...' and "..." quote, and the quotes are removed, so
#     "--output=x" is --output=x; an unbalanced quote, or a line over 4096
#     bytes, is mutate):
#       - an option that writes: for git, --output or any abbreviation of it
#         (--out, --outp, ...); for file, -C in any short option cluster, -p,
#         or --compile or --preserve-date or any abbreviation of them
#         (--compi); and, for git and file, a word with an unquoted *, ? or
#         [, which bash replaces with file names, options included: mutate;
#       - git stash create: checkpoint (allowed; posttooluse_take_checkpoint.sh
#         writes the marker once it succeeded); git stash list|show: observe;
#         git stash pop|apply <commit>: rollback when <commit> is the full id
#         of a commit a checkpoint recorded (the marker's, or one
#         posttooluse_take_checkpoint.sh entered in
#         .claude/checkpoints/commits/, a lookup of one file however many
#         checkpoints were taken); any other pop or apply, a bare one
#         included, is mutate, since git applies any merge commit as if it
#         were a stash; any other git stash form: mutate;
#       - a command on READ_ONLY: observe (allowed, nothing used);
#       - anything else: mutate.
#
# Rules.
#   - rollback: restores a checkpoint this project recorded, so a checkpoint
#     was taken; allowed, and it uses none. (F503 ROLLBACK_FAILED cannot
#     arise: a restore of anything else is mutate.)
#   - mutate: the marker (.claude/checkpoint.ok, a JSON object with
#     checkpoint_id, created_at, expires_at) must exist, be a regular file,
#     have times that are whole seconds of at most 12 digits, a created_at
#     not in the future and an expires_at at most 1800 seconds (30 minutes,
#     the Standard's cap) after it, and not have expired (F501
#     CHECKPOINT_REQUIRED; an expired marker is filed under
#     .claude/checkpoints/ended/, so its commit can still be restored, and a
#     malformed one is removed). Unless ACS_HOOK_APPROVAL is
#     "off", the permission mode must be one that puts the call to a person,
#     default, acceptEdits or plan (F502 APPROVAL_REQUIRED otherwise, with the
#     marker left in place). Then the call takes the marker: it is renamed
#     into .claude/checkpoints/used/, atomically, so two calls never both pass
#     on one marker (F501 for the one that loses). Unless ACS_HOOK_APPROVAL is
#     "off", the hook then answers permissionDecision "ask" with an F502
#     reason, so Claude Code puts the call to the person.
#
# It fails closed: Claude Code treats any exit code other than 2 as a
# non-blocking error and runs the call, so an unexpected failure here blocks
# the call with R407 instead of exiting with that command's status.
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
# line, so a long one could hold the hook past Claude Code's 60-second limit,
# after which the call runs unchecked.
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

case "$tool_name" in
  Write | Edit | MultiEdit | NotebookEdit)
    capability=mutate
    ;;
  Bash)
    command=$(printf '%s' "$payload" | jq -r '.tool_input.command | strings' 2>/dev/null) || command=""
    capability=$(classify_bash "$command")
    ;;
  *)
    # Not routed here by hooks.json: nothing this hook gates.
    exit 0
    ;;
esac

if [ "$capability" = "observe" ] || [ "$capability" = "checkpoint" ]; then
  exit 0
fi

# SEC-006: Use absolute path via CLAUDE_PROJECT_DIR, fall back to CLAUDE_PLUGIN_ROOT, then pwd
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  claude_dir="${CLAUDE_PROJECT_DIR}/.claude"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  claude_dir="${CLAUDE_PLUGIN_ROOT}/.claude"
else
  claude_dir="$(pwd)/.claude"
fi
marker="${claude_dir}/checkpoint.ok"
used_dir="${claude_dir}/checkpoints/used"
# Markers whose validity ended unused (expired, the turn ended, or a newer
# checkpoint replaced them), kept like used/.
ended_dir="${claude_dir}/checkpoints/ended"
# One empty file per commit a checkpoint recorded, named by the commit:
# posttooluse_take_checkpoint.sh enters each before it writes the marker.
commits_dir="${claude_dir}/checkpoints/commits"

# Whether a checkpoint of this project recorded the commit $1 (a full commit
# id, so a safe file name) as its restore point: the current marker's
# "commit", or an entry in commits/. One lookup, however many checkpoints
# were taken. A checkpoint can be restored valid or not (§5.18.6).
recorded_commit() {
  if [ -f "$commits_dir/$1" ] && [ ! -L "$commits_dir/$1" ]; then
    return 0
  fi
  if [ -f "$marker" ] && [ ! -L "$marker" ] \
    && [ "$(jq -r 'if type == "object" then (.commit // "" | strings) else "" end' "$marker" 2>/dev/null)" = "$1" ]; then
    return 0
  fi
  return 1
}

if [[ "$capability" == "rollback "* ]]; then
  # Restoring a recorded checkpoint uses none. Applying any other commit
  # changes the tree like any write.
  if recorded_commit "${capability#rollback }"; then
    exit 0
  fi
  capability=mutate
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
if ((now > expires_at)); then
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
  reason="F502 APPROVAL_REQUIRED: ${tool_name} (capability 'mutate') requires approval; it runs only if this call is approved."
  jq -c -n --arg reason "$reason" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason}}'
fi
exit 0
