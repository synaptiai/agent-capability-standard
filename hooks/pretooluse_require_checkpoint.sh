#!/usr/bin/env bash
# Require a checkpoint marker before mutation commands.
# This assumes your workflow writes a marker file `.claude/checkpoint.ok`
# before risky operations. Adapt as needed.
set -euo pipefail
payload="${1:-}"
# Determine if payload suggests mutation (Edit/Bash/Git)
if echo "$payload" | grep -E -i "(Edit\b|Bash\b|Git\b|rm\b|mv\b|sed\b|perl\b)" >/dev/null; then
  if [ ! -f ".claude/checkpoint.ok" ]; then
    echo "Blocked: missing checkpoint marker (.claude/checkpoint.ok). Create a checkpoint first."
    exit 1
  fi
fi
exit 0
