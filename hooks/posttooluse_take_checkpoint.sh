#!/usr/bin/env bash
# Write the checkpoint marker after a successful `git stash create`
# (STANDARD 1.2.0 §5.18.6: the call that saves the state takes the
# checkpoint), as a PostToolUse command hook for Bash (see hooks.json).
#
# Claude Code passes the call as a JSON object on stdin. When its command is
# exactly one `git stash create` (no character that joins or expands
# commands, no option that writes: the same reading as
# pretooluse_require_checkpoint.sh, whose split_words this hook holds too)
# and the response shows no error, the hook enters the printed commit in the
# project's git directory, <git dir>/acs/checkpoints/commits/ (an empty file
# named by it, which the pre-tool-use hook and the rollback skill look up to
# restore it; outside the work tree, so no clone, checkout or applied stash
# can ship one) and writes .claude/checkpoint.ok atomically:
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
# run in another repository than the project's (the payload's cwd), for
# output that is neither a commit id nor empty, or for empty output while the
# project's tree or index differs from HEAD: HEAD would not restore that
# state.
# MAX_AGE is ACS_CHECKPOINT_MAX_AGE when it is an integer from 1 to 1800,
# else 1800 seconds (30 minutes, the Standard's cap). A marker the new one
# replaces is filed under .claude/checkpoints/ended/ first; its commit, entered
# in commits/, can still be restored. A commit is entered only in a git
# repository: with no git directory to enter it in, no marker is written.
# A failed call reaches PostToolUseFailure, where this hook is not
# registered.
#
# It always exits 0: the call has already run, and this hook only records.
set -uo pipefail
# Read the command as bytes, alike in every locale (as the pre-tool-use hook).
export LC_ALL=C

input=$(cat)
command -v jq > /dev/null 2>&1 || exit 0

command=$(printf '%s' "$input" | jq -r 'if type == "object" then (.tool_input.command | strings) else empty end' 2>/dev/null) || exit 0
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
skip=$(printf '%s' "$input" | jq -r '(.tool_response.is_error == true) or (.tool_response.interrupted == true) or (.tool_input.run_in_background == true)' 2>/dev/null) || exit 0
[ "$skip" = "false" ] || exit 0

if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  project="${CLAUDE_PROJECT_DIR}"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  project="${CLAUDE_PLUGIN_ROOT}"
else
  project="$(pwd)"
fi

# The call ran in the project's repository: Claude Code sends the cwd it
# ran in; a stash of another repository restores nothing here.
cwd=$(printf '%s' "$input" | jq -r '.cwd // "" | strings' 2>/dev/null) || exit 0
if [ -n "$cwd" ]; then
  command -v git > /dev/null 2>&1 || exit 0
  ran_in=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
  ours=$(git -C "$project" rev-parse --show-toplevel 2>/dev/null) || exit 0
  [ -n "$ran_in" ] && [ "$ran_in" = "$ours" ] || exit 0
fi

printed=$(printf '%s' "$input" | jq -r '.tool_response.stdout // "" | strings' 2>/dev/null) || printed=""
printed="${printed//[[:space:]]/}"
now=$(date +%s)
if [[ "$printed" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]]; then
  checkpoint_id="$printed"
  commit="$printed"
elif [ -z "$printed" ]; then
  # Nothing to save, so HEAD restores the state: only if the project's
  # tracked files and index are HEAD's now.
  command -v git > /dev/null 2>&1 || exit 0
  git -C "$project" diff --quiet HEAD -- 2>/dev/null || exit 0
  git -C "$project" diff --cached --quiet HEAD -- 2>/dev/null || exit 0
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
# work tree.
if [ "$commit" != "HEAD" ]; then
  command -v git > /dev/null 2>&1 || exit 0
  git_dir=$(git -C "$project" rev-parse --absolute-git-dir 2>/dev/null) || exit 0
  [ -n "$git_dir" ] || exit 0
  commits_dir="${git_dir}/acs/checkpoints/commits"
  mkdir -p "$commits_dir" 2>/dev/null || exit 0
  if [ -L "$commits_dir/$commit" ] || ! : > "$commits_dir/$commit" 2>/dev/null; then
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
