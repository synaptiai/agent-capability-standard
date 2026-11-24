#!/bin/sh
# Claude Code starts this hook with the env of the project's settings files
# applied (repository content, project_layer_settings below): it runs under
# bash -p, which reads no BASH_ENV or ENV file, imports no shell function and
# ignores SHELLOPTS, BASHOPTS, CDPATH and GLOBIGNORE, and starts itself so
# when started another way (as /bin/sh, bash reads none of them either).
case $- in *p*) ;; *) exec bash -p "$0" "$@" ;; esac
# Write the checkpoint marker after a successful `git stash create`
# (STANDARD 1.2.0 §5.18.6: the call that saves the state takes the
# checkpoint), as a PostToolUse command hook for Bash (see hooks.json).
#
# Claude Code passes the call as a JSON object on stdin. When its command is
# exactly one `git stash create` (no character that joins or expands
# commands, no option that writes: the same reading as
# pretooluse_require_checkpoint.sh, whose split_words this hook holds too)
# and the response shows no error, the hook enters the printed commit in the
# project's git directory, <git dir>/acs/checkpoints/commits/ (a file named
# by it, which the pre-tool-use hook and the rollback skill look up to
# restore it; outside the work tree, so no clone, checkout or applied stash
# can ship one), holding the HMAC-SHA-256 of "acs-checkpoint-commit:<commit>"
# under the project's checkpoint key, <git dir>/acs/checkpoints/key (64 hex
# digits drawn from /dev/urandom the first time, readable by the user alone),
# so that a file a command creates there is no entry; and it writes
# .claude/checkpoint.ok atomically:
#
#   {"checkpoint_id": <the printed commit, or clean-<epoch>-<pid>>,
#    "commit": <the printed commit> | "HEAD",
#    "created_at": <now>, "expires_at": <now + MAX_AGE>,
#    "source": "git stash create"}
#
# `git stash create` prints the commit that saved the tracked state, or
# nothing when the tree is clean, in which case HEAD is the restore point.
# The hook writes no marker for a line over 4096 bytes (not read, nor
# trimmed: the trims' cost grows with the line times its run of blanks), for
# a call run in the background (its output is not yet the command's), for one
# the pre-tool-use hook classified the worst case where it ran (the
# payload's cwd: a git program or a git directory that may be repository
# content, the same functions), for one run in another repository than the
# project's (another git directory or work tree), for
# output that is neither a commit id nor empty, or for empty output while the
# project's tree or index differs from HEAD: HEAD would not restore that
# state (checked with each filter the repository's own configuration names
# turned off, so the check runs no program the repository chose).
# MAX_AGE is ACS_CHECKPOINT_MAX_AGE when it is an integer from 1 to 1800,
# else 1800 seconds (30 minutes, the Standard's cap). While the project's
# .claude/settings.json or .claude/settings.local.json sets a variable in env
# that is not Claude Code's own (one of the hooks' settings, or one that
# changes what git or this hook runs), or cannot be read, no marker is
# written, and nothing else is run: Claude Code applies that env, repository
# content, over the user's settings (project_layer_settings). A marker the new one
# replaces is filed under .claude/checkpoints/ended/ first; its commit, entered
# in commits/, can still be restored. A commit is entered only in a git
# repository whose git directory git made for a work tree (a .git directory,
# or a linked worktree's or a submodule's under one; a repository can ship a
# git directory of its own, with a key and entries in it), and only with
# openssl to sign it: otherwise no marker is written. git runs with
# core.fsmonitor and hooks turned off, so no repository content makes this
# hook run a program.
# A failed call reaches PostToolUseFailure, where this hook is not
# registered.
#
# It always exits 0: the call has already run, and this hook only records.
set -uo pipefail
# Read the command as bytes, alike in every locale (as the pre-tool-use hook).
export LC_ALL=C

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

payload=$(cat)
type -P jq > /dev/null 2>&1 || exit 0

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

# A variable the repository may have chosen sets no expiry and may run a
# program in the git commands below: no marker, and nothing run (the
# pre-tool-use hook refuses every call meanwhile, R407).
named=$(project_layer_settings "$project_dir") || exit 0
[ -z "$named" ] || exit 0

command=$(printf '%s' "$payload" | jq -r 'if type == "object" then (.tool_input.command | strings) else empty end' 2>/dev/null) || exit 0
# Not read past 4096 bytes, before the trims (as the pre-tool-use hook).
[ "${#command}" -le 4096 ] || exit 0
command="${command#"${command%%[![:space:]]*}"}"
command="${command%"${command##*[![:space:]]}"}"
if [ -z "$command" ] || [[ "$command" == *[\;\&\|\<\>\$\`\(\)\{\}\\]* ]] || [[ "$command" == *$'\n'* ]] || [[ "$command" == *$'\r'* ]]; then
  exit 0
fi
# Read the line as bash splits and dequotes it: the pre-tool-use hook's
# function, kept the same by a test.
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

# git with what a repository's own configuration could make it run turned
# off, for at most 5 seconds (the pre-tool-use hook's function, kept the same
# by a test).
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
    target=$(readlink -- "$found" 2> /dev/null && printf x) || return 0
    target="${target%x}"
    [[ "$target" == *$'\n' ]] || return 0
    target="${target%$'\n'}"
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

split_words "$command" || exit 0
words=("${WORDS[@]}")
if [ "$GLOBBED" = 1 ] || [ "${words[0]}" != "git" ] || [ "${words[1]:-}" != "stash" ] || [ "${words[2]:-}" != "create" ]; then
  exit 0
fi
for word in "${words[@]}"; do
  name="${word#--}"
  name="${name%%=*}"
  if [[ "$word" == --?* && ( "output" == "$name"* || "$name" == output* ) ]]; then exit 0; fi
done

# A failed or interrupted call saved nothing; a background one has not
# finished.
skip=$(printf '%s' "$payload" | jq -r '(.tool_response.is_error == true) or (.tool_response.interrupted == true) or (.tool_input.run_in_background == true)' 2>/dev/null) || exit 0
[ "$skip" = "false" ] || exit 0

project="$project_dir"

# The call took a checkpoint only where the pre-tool-use hook classified it
# `checkpoint` (§5.18.6), in the directory it ran in (Claude Code sends that
# cwd; else the project directory): the git the agent's shell ran is the
# system's (command_may_be_content), and the git directory git finds there
# is one git made for a work tree (git_dir_is_content). Otherwise it was the
# worst case, and what it printed restores nothing: a shipped git directory
# whose core.worktree is the project stashes into its own object store.
command_may_be_content git && exit 0
git_dir_is_content && exit 0
# And it ran in the project's repository: the same git directory (which
# stores the commit) and the same work tree; a stash of another repository
# restores nothing here. The cwd and git's answers are read exactly: a
# command substitution strips the line breaks that end its output, and a
# directory's name may end in one (d and $'d\n' are two directories), so an
# x is printed after each and compared with it.
call_dir || exit 0
git_dir_at "$CALL_DIR" || exit 0
ran_in_git="$GIT_DIR_FOUND"
git_dir_at "$project" || exit 0
[ "$ran_in_git" = "$GIT_DIR_FOUND" ] || exit 0
ran_in=$(hgit -C "$CALL_DIR" rev-parse --show-toplevel 2>/dev/null && printf x) || exit 0
ours=$(hgit -C "$project" rev-parse --show-toplevel 2>/dev/null && printf x) || exit 0
[ "$ran_in" != x ] && [ "$ran_in" = "$ours" ] || exit 0

printed=$(printf '%s' "$payload" | jq -r '.tool_response.stdout // "" | strings' 2>/dev/null) || printed=""
printed="${printed//[[:space:]]/}"
now=$(date +%s)
if [[ "$printed" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]]; then
  checkpoint_id="$printed"
  commit="$printed"
elif [ -z "$printed" ]; then
  # Nothing to save, so HEAD restores the state: only if the project's
  # tracked files and index are HEAD's now.
  command -v git > /dev/null 2>&1 || exit 0
  # Each filter the repository's own configuration (local or worktree
  # scope) names is turned off (an empty command is no filter), so hashing
  # a changed file runs no program the repository chose; a name that cannot
  # be passed so, or a listing git cannot give, writes no marker.
  filters_off=()
  filters_status=0
  filters=$(hgit -C "$project" config --show-scope --name-only --get-regexp '^filter\..+\.(clean|smudge|process)$' 2>/dev/null) || filters_status=$?
  case "$filters_status" in 0 | 1) ;; *) exit 0 ;; esac
  while IFS=$'\t' read -r scope key; do
    case "$scope" in local | worktree) ;; *) continue ;; esac
    case "$key" in "" | *=*) exit 0 ;; esac
    filters_off+=(-c "${key}=")
  done <<< "$filters"
  hgit ${filters_off[@]+"${filters_off[@]}"} -C "$project" diff --quiet --no-ext-diff --no-textconv HEAD -- 2>/dev/null || exit 0
  hgit ${filters_off[@]+"${filters_off[@]}"} -C "$project" diff --cached --quiet --no-ext-diff --no-textconv HEAD -- 2>/dev/null || exit 0
  checkpoint_id="clean-${now}-$$"
  commit="HEAD"
else
  exit 0
fi

max_age="${ACS_CHECKPOINT_MAX_AGE:-1800}"
if ! [[ "$max_age" =~ ^[0-9]{1,4}$ ]] || (( 10#$max_age < 1 || 10#$max_age > 1800 )); then
  max_age=1800
fi

claude_dir="${project}/.claude"
mkdir -p "$claude_dir" 2>/dev/null || exit 0
marker="${claude_dir}/checkpoint.ok"
if [ -L "$marker" ]; then
  exit 0
fi

# Enter the commit before the marker names it, so no marker records a
# commit the lookup misses: in the project's git directory, outside the
# work tree, signed with the project's checkpoint key.
if [ "$commit" != "HEAD" ]; then
  command -v git > /dev/null 2>&1 || exit 0
  command -v openssl > /dev/null 2>&1 || exit 0
  git_dir=$(hgit -C "$project" rev-parse --absolute-git-dir 2>/dev/null && printf x) || exit 0
  git_dir="${git_dir%x}"
  [[ "$git_dir" == *$'\n' ]] || exit 0
  git_dir="${git_dir%$'\n'}"
  case "$git_dir" in
    */.git | */.git/worktrees/* | */.git/modules/*) ;;
    *) exit 0 ;;
  esac
  records="${git_dir}/acs/checkpoints"
  commits_dir="${records}/commits"
  key_file="${records}/key"
  (umask 077 && mkdir -p "$commits_dir") 2>/dev/null || exit 0
  [ ! -L "$records" ] && [ ! -L "$commits_dir" ] || exit 0
  # The key: drawn once, entered with ln, which fails when another run has
  # entered one first (that one is used). One that is not 64 hex digits in
  # a regular file is replaced.
  key=$(head -c 128 "$key_file" 2>/dev/null) || key=""
  if [ -L "$key_file" ] || [ ! -f "$key_file" ] || ! [[ "$key" =~ ^[0-9a-f]{64}$ ]]; then
    new_key=$(head -c 32 /dev/urandom 2>/dev/null | od -An -tx1 | tr -d ' \n') || exit 0
    [[ "$new_key" =~ ^[0-9a-f]{64}$ ]] || exit 0
    key_tmp=$(umask 077 && mktemp "${records}/key.XXXXXX") || exit 0
    if ! printf '%s' "$new_key" > "$key_tmp"; then
      rm -f "$key_tmp"
      exit 0
    fi
    if [ -L "$key_file" ] || { [ -e "$key_file" ] && ! [[ "$key" =~ ^[0-9a-f]{64}$ ]]; }; then
      rm -f "$key_file"
    fi
    ln "$key_tmp" "$key_file" 2>/dev/null || true
    rm -f "$key_tmp"
    key=$(head -c 128 "$key_file" 2>/dev/null) || exit 0
    [ ! -L "$key_file" ] && [[ "$key" =~ ^[0-9a-f]{64}$ ]] || exit 0
  fi
  sig=$(printf 'acs-checkpoint-commit:%s' "$commit" | openssl dgst -sha256 -hmac "$key" 2>/dev/null | awk '{print $NF}') || exit 0
  [[ "$sig" =~ ^[0-9a-f]{64}$ ]] || exit 0
  entry_tmp=$(mktemp "${commits_dir}/.entry.XXXXXX") || exit 0
  if ! printf '%s' "$sig" > "$entry_tmp" || ! mv -f "$entry_tmp" "${commits_dir}/${commit}"; then
    rm -f "$entry_tmp"
    exit 0
  fi
fi

tmp=$(mktemp "${claude_dir}/checkpoint.XXXXXX") || exit 0
if jq -c -n \
  --arg id "$checkpoint_id" \
  --arg commit "$commit" \
  --argjson created "$now" \
  --argjson expires "$((now + 10#$max_age))" \
  '{checkpoint_id: $id, commit: $commit, created_at: $created, expires_at: $expires, source: "git stash create"}' > "$tmp"; then
  # The marker this one replaces ends unused: keep its record (ended/).
  if [ -f "$marker" ] && [ ! -L "$marker" ]; then
    ended_dir="${claude_dir}/checkpoints/ended"
    mkdir -p "$ended_dir" 2>/dev/null || true
    if ended=$(mktemp "${ended_dir}/replaced.XXXXXX" 2>/dev/null); then
      mv -f "$marker" "$ended" 2>/dev/null || rm -f "$ended"
    fi
  fi
  mv -f "$tmp" "$marker" || rm -f "$tmp"
else
  rm -f "$tmp"
fi
exit 0
