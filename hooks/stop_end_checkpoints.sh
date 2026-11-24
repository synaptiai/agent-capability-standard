#!/bin/sh
# Claude Code starts this hook with the env of the project's settings files
# applied (repository content): it runs under bash -p, which reads no
# BASH_ENV or ENV file, imports no shell function and ignores SHELLOPTS,
# BASHOPTS, CDPATH and GLOBIGNORE, and starts itself so when started another
# way (as /bin/sh, bash reads none of them either). While those files set
# any other variable, the pre-tool-use hook refuses every call.
case $- in *p*) ;; *) exec bash -p "$0" "$@" ;; esac
# End the checkpoint marker's validity at an execution boundary, after which
# an earlier checkpoint authorises nothing (STANDARD 1.2.0 §5.18.6). The
# boundaries are the end and the start of a turn and of a session: hooks.json
# runs this hook on Stop, on StopFailure (an API error ended the turn, and
# Stop does not run), on UserPromptSubmit (a new turn starts: this also ends
# a marker a turn left when it was interrupted or the session was killed),
# on SessionStart and on SessionEnd. The scope is the project directory, so a
# boundary of any session in it ends the marker.
#
# It files .claude/checkpoint.ok under .claude/checkpoints/ended/ (or removes
# it, when it is not a regular file or cannot be moved), and keeps
# .claude/checkpoints/used/ and ended/, and the commits a rollback looks up
# (<git dir>/acs/checkpoints/commits/): a checkpoint whose validity ended can
# still be restored. It always exits 0: a Stop hook that exits 2 would stop
# Claude from stopping, and a UserPromptSubmit hook that exits 2 would refuse
# the prompt.
set -uo pipefail

cat > /dev/null 2>&1 || true

if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  claude_dir="${CLAUDE_PROJECT_DIR}/.claude"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  claude_dir="${CLAUDE_PLUGIN_ROOT}/.claude"
else
  claude_dir="$(pwd)/.claude"
fi
marker="${claude_dir}/checkpoint.ok"
ended_dir="${claude_dir}/checkpoints/ended"
if [ -f "$marker" ] && [ ! -L "$marker" ]; then
  mkdir -p "$ended_dir" 2>/dev/null || true
  if ended=$(mktemp "${ended_dir}/turn-ended.XXXXXX" 2>/dev/null) && mv -f "$marker" "$ended" 2>/dev/null; then
    exit 0
  fi
  rm -f "${ended:-}" 2>/dev/null || true
fi
rm -f "$marker" 2>/dev/null || true
exit 0
