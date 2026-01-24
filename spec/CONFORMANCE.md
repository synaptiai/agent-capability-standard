# Conformance

## Conformance levels
- **L1 Validator Conformance**
  - validates capability existence
  - validates prerequisites
  - validates binding path existence

- **L2 Type Conformance**
  - resolves `$ref` schemas
  - infers binding types
  - requires typed annotations only when ambiguous
  - validates typed annotations

- **L3 Contract Conformance**
  - validates binding types against consumer input_schema
  - emits coercion hints

- **L4 Patch Conformance**
  - emits patch suggestions JSON
  - emits optional diff patch (`--emit-patch`)
  - uses coercion registry when available

**v10 target:** L4

## Required artifacts
- Capability ontology file
- Workflow catalog file
- Schema bundle + policies
- Validator CLI

## Test suite requirements
- Positive fixtures: valid workflows
- Negative fixtures: invalid references, type mismatches, ambiguous nodes
- Patch fixtures: expected patch suggestions and diff output

