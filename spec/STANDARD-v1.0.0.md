# Standard: Agent Capability Ontology + Workflow DSL
**Version:** 1.0.0  
**Status:** Candidate Standard  
**Date:** 2026-01-24

## 1. Scope
This standard specifies:
1) A canonical **capability ontology** for agent systems  
2) A **workflow DSL** for composing capabilities with safety and recovery semantics  
3) Canonical **world state** and **event** schemas for grounded reasoning  
4) **Identity** and **authority trust** policies for reliable data fusion  
5) A **conformance model** and validation requirements

## 2. Terms
- **Capability**: an atomic primitive (single purpose, composable)
- **Workflow**: an ordered/conditional/parallel composition of capabilities
- **Observation**: append-only event grounded in evidence anchors
- **World State**: derived snapshot from observations + transition rules
- **Provenance**: traceability record for claims and transformations
- **Trust Score**: authority-weighted, confidence-weighted, recency-decayed score

## 3. Design principles (non-negotiable)
1) **Grounded claims**: every claim is evidence-backed or explicitly inferred
2) **Auditable transforms**: deterministic or documented loss
3) **Safety by construction**: mutation requires checkpoints; actions require plans
4) **Composable atoms**: workflows orchestrate; capabilities do one thing
5) **Explicit contracts**: I/O schemas are first-class

## 4. Capability Ontology
A capability MUST define:
- `id`
- `layer` ∈ {PERCEPTION, MODELING, REASONING, ACTION, SAFETY, META}
- `input_schema`
- `output_schema`
- `requires` and `soft_requires`
- `edges` describing key semantic dependencies

### 4.1 Dependency semantics
- `requires`: MUST be satisfied earlier in workflow execution order
- `soft_requires`: SHOULD be satisfied when available, but not mandatory

## 5. Workflow DSL
A workflow MUST define:
- `goal`
- `risk`
- `inputs` (external schema)
- `steps[]` where each step defines:
  - `capability`
  - `purpose`
  - `input_bindings`
  - `store_as`
  - optional: `condition`, `skip_if_false`
  - optional: `gates[]`
  - optional: `failure_modes[]` with recovery loops
  - optional: `mapping_ref`
  - optional: `output_conforms_to`

### 5.1 Binding syntax
Bindings reference prior step outputs and workflow inputs:
- `${store.field.path}`
- optional typed annotation: `${store.field.path: array<string>}`

### 5.2 Typed binding rules
- Untyped bindings infer type from schema node
- Typed annotations MUST match schema node type
- Typed annotations are REQUIRED when inference is ambiguous:
  - union schemas
  - missing type metadata
  - array items unknown

### 5.3 Consumer input contract checking
For each step binding, the validator MUST check:
- inferred/annotated binding type is compatible with the capability `input_schema` expectation

## 6. Canonical schemas
- `world_state_schema.yaml`
- `event_schema.yaml`
- `entity_taxonomy.yaml`

All observations MUST record:
- `timestamp`
- `source`
- `raw_payload`
- `canonical_payload`
- `evidence_anchors`
- `provenance`

World state snapshots MUST record:
- `version_id`
- `parent_version_id`
- `lineage`
- retention policy

## 7. Identity resolution policy
A standard policy defines:
- hierarchical namespaces for entity IDs
- alias confidence scoring (weighted features)
- merge/split rules with hard constraints

## 8. Authority trust model
Trust scoring MUST support:
- source ranking weights
- time decay (half-life)
- field-specific authority preferences
- conflict resolution strategies

## 9. Conformance
An implementation is conformant if it:
- validates workflows against capability schemas and dependencies
- enforces binding existence and consumer input contracts
- supports `$ref` schema resolution
- records provenance and evidence anchors per schema requirements

## 10. Backward compatibility
SemVer governs changes. Breaking changes require MAJOR bump.

