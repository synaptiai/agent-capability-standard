#!/usr/bin/env bash
# Deterministic helper: validate JSON file(s)
set -e
for f in "$@"; do
  python - <<'PY'
import json, sys
p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as fh:
    json.load(fh)
print("OK:", p)
PY
  "$f"
done
