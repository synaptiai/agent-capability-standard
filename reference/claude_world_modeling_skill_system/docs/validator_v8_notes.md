# Validator v8 upgrades

This iteration adds:
- `$ref` resolution for workflow input schemas using `ref: <file>#<pointer>`
- Type compatibility checking for typed binding annotations:
  - `${x.y: array<string>}` checked against schema node types
- Type mismatch diagnostics + coercion hints:
  - suggests inserting a `transform` step

Run:
```bash
python3 tools/validate_workflows.py
```
