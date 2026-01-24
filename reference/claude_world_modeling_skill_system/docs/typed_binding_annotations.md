# Typed binding annotations

Workflow bindings can optionally annotate types:

- `${step_out.field}` (untyped)
- `${step_out.field: <type>}` (typed)

Examples:
- `${verify_out.failures: array<string>}`
- `${inspect_out.confidence: number}`
- `${world_state_out.entities: array<object>}`

## Purpose
- Enables static validation and autocomplete.
- Allows workflows to declare expected shapes even when schema is partial.
- Improves error messages (type mismatch vs missing field).
