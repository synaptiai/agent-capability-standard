#!/usr/bin/env bash
# Write the checkpoint marker after a successful `git stash create`
# (STANDARD 1.2.0 §5.18.6: the call that saves the state takes the
# checkpoint), as a PostToolUse command hook for Bash (see hooks.json).
#
# Claude Code passes the call as a JSON object on stdin. When its command is
# exactly one `git stash create` (no character that joins or expands
# commands, no option that writes: the same reading as
# pretooluse_require_checkpoint.sh) and the response shows no error, the hook
# writes .claude/checkpoint.ok atomically:
#
#   {"checkpoint_id": <the printed commit, or clean-<epoch>-<pid>>,
#    "commit": <the printed commit> | "HEAD",
#    "created_at": <now>, "expires_at": <now + MAX_AGE>,
#    "source": "git stash create"}
#
# `git stash create` prints the commit that saved the tracked state, or
# nothing when the tree is clean, in which case HEAD is the restore point.
# MAX_AGE is ACS_CHECKPOINT_MAX_AGE when it is an integer from 1 to 1800,
# else 1800 seconds (30 minutes, the Standard's cap). A marker the new one
# replaces is filed under .claude/checkpoints/ended/ first, so its commit can
# still be restored. A failed call reaches PostToolUseFailure, where this
# hook is not registered.
#
# It always exits 0: the call has already run, and this hook only records.
set -uo pipefail

input=$(cat)
command -v jq > /dev/null 2>&1 || exit 0

command=$(printf '%s' "$input" | jq -r 'if type == "object" then (.tool_input.command | strings) else empty end' 2>/dev/null) || exit 0
command="${command#"${command%%[![:space:]]*}"}"
command="${command%"${command##*[![:space:]]}"}"
if [ -z "$command" ] || [[ "$command" == *[\;\&\|\<\>\$\`\(\)\{\}\\]* ]] || [[ "$command" == *$'\n'* ]] || [[ "$command" == *$'\r'* ]]; then
  exit 0
fi
read -r -a words <<< "$command"
if [ "${words[0]}" != "git" ] || [ "${words[1]:-}" != "stash" ] || [ "${words[2]:-}" != "create" ]; then
  exit 0
fi
for word in "${words[@]}"; do
  if [[ "$word" == --output* ]]; then exit 0; fi
done

failed=$(printf '%s' "$input" | jq -r '(.tool_response.is_error == true) or (.tool_response.interrupted == true)' 2>/dev/null) || exit 0
[ "$failed" = "false" ] || exit 0

printed=$(printf '%s' "$input" | jq -r '.tool_response.stdout // "" | strings' 2>/dev/null) || printed=""
printed="${printed//[[:space:]]/}"
now=$(date +%s)
if [[ "$printed" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]]; then
  checkpoint_id="$printed"
  commit="$printed"
else
  checkpoint_id="clean-${now}-$$"
  commit="HEAD"
fi

max_age="${ACS_CHECKPOINT_MAX_AGE:-1800}"
if ! [[ "$max_age" =~ ^[0-9]{1,4}$ ]] || (( 10#$max_age < 1 || 10#$max_age > 1800 )); then
  max_age=1800
fi

if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  claude_dir="${CLAUDE_PROJECT_DIR}/.claude"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  claude_dir="${CLAUDE_PLUGIN_ROOT}/.claude"
else
  claude_dir="$(pwd)/.claude"
fi
mkdir -p "$claude_dir" 2>/dev/null || exit 0
marker="${claude_dir}/checkpoint.ok"
if [ -L "$marker" ]; then
  exit 0
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
