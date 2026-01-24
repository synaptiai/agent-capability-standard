#!/usr/bin/env bash
# Naive prompt-injection detector for tool calls.
# Block if payload contains high-risk meta-instructions.
set -euo pipefail
payload="${1:-}"
patterns=(
  "ignore previous instructions"
  "disable safety"
  "exfiltrate"
  "leak"
  "print all secrets"
  "system prompt"
  "sudo rm"
  "curl .*\|\s*sh"
)
for pat in "${patterns[@]}"; do
  if echo "$payload" | grep -E -i "$pat" >/dev/null; then
    echo "Blocked: possible prompt injection / dangerous instruction detected ($pat)."
    exit 1
  fi
done
exit 0
