# Validator v9 upgrades: type inference + ambiguity gating

v9 adds:
- Automatic type inference for untyped bindings using resolved schema nodes
- Typed annotations are only required when ambiguity exists:
  - unknown type
  - unions (type lists, oneOf/anyOf/allOf)
  - arrays with unknown items type
- Failure messages include the inferred type and a suggested annotation format

Run:
```bash
python3 tools/validate_workflows.py
```
