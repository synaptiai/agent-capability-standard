# Specification Changelog

This changelog tracks changes to the **Agent Capability Standard specification** itself. For plugin and project-level changes, see the [root CHANGELOG](../CHANGELOG.md).

## v1.0.0 — 2026-01-24

### Specification
- Initial publication candidate
- Capability ontology: 36 atomic capabilities across 9 cognitive layers
- I/O contracts with typed schemas and explicit dependencies
- Workflow DSL spec v2: bindings, conditions, gates, recovery loops, parallel groups
- Canonical world state and event schemas (provenance, uncertainty, retention, lineage)
- Identity taxonomy and identity resolution policy
- Authority trust model (weights, decay, field-specific authority)
- Conformance levels L1–L4 with validation rules

### Validation
- Compiler-grade validator with $ref resolution and type inference
- Consumer input schema checking
- Patch suggestions and optional diff output
- 5 conformance test fixtures
