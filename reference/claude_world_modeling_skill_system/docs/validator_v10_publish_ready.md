# Validator v10 (publish-ready)

v10 upgrades the validator into a workflow "compiler":

## Features
1. $ref resolution for workflow inputs (`inputs.*.ref`)
2. Type inference for untyped references from schema nodes
3. Typed annotations required only on ambiguity
4. Consumer-side input type checking:
   - Compare each step's `input_bindings` against the capability's `input_schema`
5. Patch suggestions:
   - Writes `tools/validator_suggestions.json`
   - Can emit a unified diff patch via `--emit-patch`
   - Patch inserts `transform` coercion steps and rewires bindings

## Running
```bash
python3 tools/validate_workflows.py
python3 tools/validate_workflows.py --emit-patch
```

## Outputs
- `tools/validator_suggestions.json`
- `tools/validator_patch.diff` (optional)

## Coercion registry
The validator uses:
- `docs/schemas/transform_coercion_registry.yaml`

Add more coercions to expand auto-fix coverage.
