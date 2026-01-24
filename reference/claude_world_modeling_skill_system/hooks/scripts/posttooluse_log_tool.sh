#!/usr/bin/env bash
# Append a tool usage line to .claude/audit.log
set -euo pipefail
payload="${1:-}"
mkdir -p .claude
ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$ts] $payload" >> .claude/audit.log
exit 0
