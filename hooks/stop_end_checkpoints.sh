#!/usr/bin/env bash
# End the checkpoint marker's validity when a turn ends, as a Stop command
# hook (see hooks.json): the end of a turn is an execution boundary, after
# which an earlier checkpoint authorises nothing (STANDARD 1.2.0 §5.18.6).
#
# It files .claude/checkpoint.ok under .claude/checkpoints/ended/ (or removes
# it, when it is not a regular file or cannot be moved), and keeps
# .claude/checkpoints/used/ and ended/, the history that a rollback reads: a
# checkpoint whose validity ended can still be restored. It always exits 0: a
# Stop hook that exits 2 would stop Claude from stopping.
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
