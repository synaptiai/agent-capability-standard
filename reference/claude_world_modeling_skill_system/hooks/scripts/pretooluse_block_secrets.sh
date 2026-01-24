#!/usr/bin/env bash
# Block access to common secret locations/patterns.
# Exit non-zero to block.
set -euo pipefail
payload="${1:-}"
# Match common secret indicators
if echo "$payload" | grep -E -i "(\.env\b|id_rsa\b|/ssh/|aws(_|-)credentials|gcp(_|-)?key|azure(_|-)?secret|secrets?\.ya?ml|token\b|api[_-]?key\b)" >/dev/null; then
  echo "Blocked: potential secret path/token detected."
  exit 1
fi
exit 0
