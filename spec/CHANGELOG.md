# Specification Changelog

This changelog tracks changes to the **Agent Capability Standard specification** itself. For plugin and project-level changes, see the [root CHANGELOG](../CHANGELOG.md).

## Unreleased

### Added — Standard v1.1.0 (draft) and RFC-0003 (#114)
- **[STANDARD-v1.1.0](STANDARD-v1.1.0.md)** and
  **[RFC-0003](RFC-0003-orchestration-extensions.md)** (Accepted). v1.0.0
  remains supported; Appendix C of v1.1.0 lists every change. Sections marked
  *pending reference implementation* are normative but not yet enforced by the
  reference validator.
- **Condition expression language (§5.8)** for `condition`, `gates[].when` and
  `failure_modes[].when`: a small grammar that is a strict subset of CEL, with
  fixed limits, fail-safe error handling per site, static type checks and null
  narrowing. Gates gain `phase: before|after` (§5.6).
- **Diagnostic severities (§9.1)** and warning codes W601–W614 (§9.7); new
  error codes V106–V109, B206, R405.
- **`mutation_overridable` (§4.4)** for append-only capabilities (`audit`).
- **Orchestration extensions (§5.9–§5.16)** — triggers, handler steps,
  recovery and escalation, wait, approval, delegation, quorum — opted into
  with `workflow_extensions.requires`.
  Extension fields are must-understand (V106 when used undeclared).
  Enforced so far: declarations, `triggers@1` (§5.10, with the duration
  grammar of §5.10.1), `recovery@1` (§5.11, §5.12), `wait@1` (§5.13) and
  `approval@1` (§5.14). A validator must
  refuse a declared extension it does not check (V106).
- **Effective `requires_checkpoint` (§5.2.1)** raised by a step is enforced:
  F501 when no checkpoint runs before it.
- **`event_schema.yaml` 1.1.0:** `source.kind` gains `agent`, so events from
  other agents can trigger workflows (§5.10).
- **`world_state_schema.yaml` 1.1.0:** `ActionRecord.status` gains
  `rejected` and `expired`, and an optional `approval` record binds the
  action to the decision (§5.14).

### Changed — clarifications of 1.0 semantics (#114)
- **Edges (§4.3, [EDGE_TYPES](EDGE_TYPES.md)).** `precedes` orders two
  capabilities only when both are present; `conflicts_with` forbids
  concurrency (a shared parallel group), not co-existence; `soft_requires` is
  any-of presence per target and warns. A step in the same parallel group
  does not run before another. Five follow-up edges became `enables`, one
  redundant edge was removed, and `constrain` became the soft prerequisite of
  `execute`, `mutate` and `send`.
- **Safety flags (§5.2.1)** inherit from the ontology; a weaker declaration
  has no effect and warns (W602).
- **Unknown fields (§11.3)** are reported (W604) and ignored; `x-` fields are
  vendor extensions. `inputs` is optional (§5.1).
- **Version declaration (§11.5):** `spec_version` or the file header; missing
  → W605, unsupported → V109.
- **B205** means "annotation names no type"; an annotation that contradicts
  the schema is B203 (§9.3).

### Fixed
- **Authority trust model — decay is now a true half-life.** `conflict_resolution_function.recency_factor`
  is `0.5 ** (age/half_life)`, which returns exactly 0.5 at `age == half_life`. The published
  `exp(-age/half_life)` returned 0.3679 there, treating `half_life` as an exponential time
  constant and decaying 1/ln(2) ≈ 1.44x too fast. `decay_model.half_life` is set to `P10D`,
  the value reproducing the curve the reference implementation actually exhibited; the former
  `P14D` was a mislabelled ~9.7-day half-life. Implementations that read `half_life` and
  applied a correct half-life curve were, in effect, decaying more slowly than the reference.
  (#105)

### Added
- **§8.1 now states the decay semantics normatively.** Time decay MUST be a true
  half-life (factor `0.5` at `age == half_life`), and `decay_model.min_trust` is
  defined as a floor on the *decay factor* — not on the composed §8.2 score and
  not on the static source weight. The floor was previously declared in
  `authority_trust_model.yaml`, cited by compliance artifacts as an implemented
  control, unenforced by the reference implementation, and undefined by the spec.
  (#106)

### Changed
- **§6.2 and §6.3 now name the fields the canonical schemas actually declare.**
  §6.2 described observations with `id` / `raw_payload` / `canonical_payload` /
  `evidence_anchors` — names that appear in no schema file. The canonical event
  in `event_schema.yaml` has always carried all seven fields as `event_id` /
  `raw` / `canonical` / `anchors`, and `transform_mapping_rawlog_to_observation.yaml`
  writes those names. §6.3 likewise placed snapshot identity at the top level
  when `world_state_schema.yaml` keeps it under `meta`. Both tables now match
  the schemas; §6.2 also states explicitly that the canonical-event namespace is
  distinct from the capability-I/O namespace of §4.1, so an event's `anchors`
  is not a capability's `evidence_anchors`. Clarification only — no field
  changed shape. (#107)
- **Three fields the spec marks MUST are now `required` in the schemas.**
  `event.provenance` (§6.2), and `world_state.meta.version_id` and
  `meta.lineage` (§6.3), were declared but optional. Per §11.4 adding a required
  field is breaking for producers that omitted them; no in-repo fixture did.
  (#107)

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
