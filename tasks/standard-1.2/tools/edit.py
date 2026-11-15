"""Exact-string edits of design files: edit.py FILE <<< JSON list of [old, new] (each old must occur exactly once unless 'all' flag)."""
import json, sys, pathlib
path = pathlib.Path(sys.argv[1])
edits = json.load(sys.stdin)
text = path.read_text()
for e in edits:
    old, new = e[0], e[1]
    allow_many = len(e) > 2 and e[2] == "all"
    n = text.count(old)
    if n == 0 or (n > 1 and not allow_many):
        sys.exit(f"{path.name}: {n} occurrences of: {old[:120]!r}")
    text = text.replace(old, new)
path.write_text(text)
print(f"{path.name}: {len(edits)} edits applied")
