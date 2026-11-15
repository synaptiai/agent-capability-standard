#!/usr/bin/env bash
# End the checkpoint marker's validity when a turn ends, as a Stop command
# hook (see hooks.json): the end of a turn is an execution boundary, after
# which an earlier checkpoint authorises nothing (STANDARD 1.2.0 §5.18.6).
#
# It removes .claude/checkpoint.ok and keeps .claude/checkpoints/used/, the
# history that a rollback reads. It always exits 0: a Stop hook that exits 2
# would stop Claude from stopping.
set -uo pipefail

cat > /dev/null 2>&1 || true

if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  claude_dir="${CLAUDE_PROJECT_DIR}/.claude"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  claude_dir="${CLAUDE_PLUGIN_ROOT}/.claude"
else
  claude_dir="$(pwd)/.claude"
fi
rm -f "${claude_dir}/checkpoint.ok" 2>/dev/null || true
exit 0
