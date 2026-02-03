# Standard: Agent Capability Ontology + Workflow DSL

**Version:** 1.0.0
**Status:** Candidate Standard
**Date:** 2026-01-24

---

## 1. Scope

This standard specifies:

1. A canonical **capability ontology** for agent systems
2. A **workflow DSL** for composing capabilities with safety and recovery semantics
3. Canonical **world state** and **event** schemas for grounded reasoning
4. **Identity** and **authority trust** policies for reliable data fusion
5. An **error model** for validation and runtime failures
6. A **conformance model** and validation requirements
7. **Versioning** and backward compatibility policy

### 1.1 Normative References

- JSON Schema Draft 2020-12
- YAML 1.2
- Semantic Versioning 2.0.0

### 1.2 Notation

- **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**: Absolute requirements
- **SHOULD**, **SHOULD NOT**: Recommended but not mandatory
- **MAY**: Optional

---

## 2. Terms

| Term | Definition |
|------|------------|
| **Capability** | An atomic primitive with single purpose, composable with explicit I/O contracts |
| **Workflow** | An ordered, conditional, or parallel composition of capabilities |
| **Observation** | Append-only event grounded in evidence anchors |
| **World State** | Derived snapshot from observations and transition rules |
| **Provenance** | Traceability record for claims and transformations |
| **Trust Score** | Authority-weighted, confidence-weighted, recency-decayed score |
| **Binding** | A reference from one step to another step's output |
| **Gate** | A conditional check that can halt or redirect workflow execution |
| **Checkpoint** | A saved state that enables rollback |
| **Grounding** | Anchoring claims to evidence references |

---

## 3. Design Principles

These principles are non-negotiable. An implementation that violates them is non-conformant.

### 3.1 Grounded Claims
Every claim MUST be evidence-backed or explicitly marked as inferred. Ungrounded claims MUST include an `inference_method` and `confidence` score.

### 3.2 Auditable Transforms
Every transformation MUST be either:
- Deterministic (same input produces same output)
- Documented with explicit loss (what information is discarded)

### 3.3 Safety by Construction
- Mutation REQUIRES checkpoints
- Actions REQUIRE plans
- Rollback MUST be possible for any mutation

### 3.4 Composable Atoms
- Workflows orchestrate; capabilities do one thing
- Each capability has a single responsibility
- Capabilities communicate through typed contracts

### 3.5 Explicit Contracts
- Input and output schemas are first-class
- Type mismatches MUST be detected at validation time
- Schema evolution follows semantic versioning

---

## 4. Capability Ontology

### 4.1 Capability Definition

A capability MUST define:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (lowercase, hyphens allowed) |
| `layer` | enum | Yes | Classification layer |
| `description` | string | Yes | Human-readable purpose |
| `input_schema` | object | Yes | JSON Schema for inputs |
| `output_schema` | object | Yes | JSON Schema for outputs |
| `requires` | array | No | Hard prerequisites (MUST be satisfied) |
| `soft_requires` | array | No | Soft prerequisites (SHOULD be satisfied) |
| `edges` | array | No | Semantic dependencies and relationships |

### 4.2 Layers

Capabilities are classified into 9 cognitive layers:

| Layer | Purpose | Mutation | Count |
|-------|---------|----------|-------|
| **PERCEIVE** | Acquire information from the world | No | 4 |
| **UNDERSTAND** | Make sense of information | No | 6 |
| **REASON** | Plan and analyze | No | 4 |
| **MODEL** | Represent the world | No | 5 |
| **SYNTHESIZE** | Create content | No | 3 |
| **EXECUTE** | Change the world | Yes | 3 |
| **VERIFY** | Ensure correctness | Varies | 5 |
| **REMEMBER** | Persist state | Varies | 2 |
| **COORDINATE** | Multi-agent and user interaction | Varies | 4 |

### 4.3 Edge Types and Dependency Semantics

The ontology supports 7 edge types for expressing relationships between capabilities:

| Edge Type | Enforcement | Description |
|-----------|-------------|-------------|
| `requires` | MUST | Hard prerequisite that must be satisfied |
| `soft_requires` | SHOULD | Recommended prerequisite when available |
| `enables` | Informational | Capability flow and composition pattern |
| `precedes` | MUST | Temporal ordering constraint |
| `conflicts_with` | MUST | Mutual exclusivity (symmetric) |
| `alternative_to` | Informational | Substitutable capabilities (symmetric) |
| `specializes` | Informational | Parent-child inheritance |

**Enforcement semantics:**
- `requires`: MUST be satisfied earlier in workflow execution order. Validator MUST reject workflows that violate this.
- `soft_requires`: SHOULD be satisfied when available. Validator SHOULD warn if not satisfied.
- `precedes`: MUST complete before the target capability begins. Validator MUST reject workflows that violate temporal ordering.
- `conflicts_with`: Both capabilities MUST NOT appear in the same workflow. Validator MUST reject workflows containing both.
- `enables`, `alternative_to`, `specializes`: Informational only, used for workflow design and capability selection.

See [EDGE_TYPES.md](EDGE_TYPES.md) for full edge type documentation.

### 4.4 Safety-Critical Capabilities

The following capabilities have special requirements:

| Capability | Requires | Notes |
|------------|----------|-------|
| `mutate` | `checkpoint` | Cannot mutate without prior checkpoint |
| `send` | `checkpoint` | Cannot send without prior checkpoint |
| `rollback` | `checkpoint` | Must have checkpoint to revert to |
| `verify` | _(none)_ | `alternative_to` constrain; verify checks post-hoc, constrain checks pre-execution |

---

## 5. Workflow DSL

### 5.1 Workflow Definition

A workflow MUST define:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `goal` | string | Yes | Intended outcome |
| `risk` | enum | Yes | Risk level: low, medium, high |
| `inputs` | object | Yes | External input schema |
| `steps` | array | Yes | Ordered list of capability invocations |
| `success` | array | No | Success criteria |

### 5.2 Step Definition

Each step MUST define:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `capability` | string | Yes | Capability ID to invoke |
| `purpose` | string | Yes | Why this step exists |
| `store_as` | string | Yes | Output identifier for later reference |

Each step MAY define:

| Field | Type | Description |
|-------|------|-------------|
| `input_bindings` | object | References to prior step outputs |
| `condition` | string | Conditional execution expression |
| `skip_if_false` | boolean | Skip step if condition is false |
| `gates` | array | Conditional checks that can halt execution |
| `failure_modes` | array | Documented failure scenarios with recovery |
| `timeout` | string | Maximum execution time (e.g., "5m") |
| `retry` | object | Retry configuration (max, backoff) |
| `parallel_group` | string | Group ID for parallel execution |
| `join` | string | How to wait for parallel completion |
| `mapping_ref` | string | Reference to transform mapping |
| `output_conforms_to` | string | Schema the output must match |
| `mutation` | boolean | Whether this step modifies external state |
| `requires_checkpoint` | boolean | Whether checkpoint is required before this step |
| `requires_approval` | boolean | Whether human approval is required |

### 5.3 Binding Syntax

Bindings reference prior step outputs and workflow inputs:

```
${store_as.field.path}
${store_as.field.path: type_annotation}
```

Examples:
```yaml
${observe_out.observation}
${state_out.entities: array<object>}
${integrate_out.merged.observations: array<object>}
```

### 5.4 Typed Binding Rules

1. Untyped bindings infer type from the producer's output schema
2. Typed annotations MUST match the schema node type
3. Typed annotations are REQUIRED when inference is ambiguous:
   - Union schemas (`oneOf`, `anyOf`)
   - Missing type metadata
   - Unknown array item types
   - `additionalProperties: true` with no constraints

### 5.5 Consumer Contract Checking

For each binding, the validator MUST check:
1. The referenced `store_as` exists in a prior step
2. The field path is valid in the producer's output schema
3. The inferred/annotated type is compatible with the consumer's input schema

### 5.6 Gate Semantics

Gates define conditional checks:

```yaml
gates:
  - when: ${checkpoint_out.checkpoint_id} == null
    action: stop
    message: "No checkpoint created. Do not mutate."
```

| Field | Type | Description |
|-------|------|-------------|
| `when` | string | Condition expression |
| `action` | enum | `stop`, `rollback`, `skip`, `warn` |
| `message` | string | Explanation for the action |

### 5.7 Failure Modes

Failure modes document expected failure scenarios:

```yaml
failure_modes:
  - condition: Verdict == FAIL
    action: rollback
    recovery:
      goto_step: plan
      inject_context:
        failure_evidence: ${verify_out.violations}
      max_loops: 3
```

| Field | Type | Description |
|-------|------|-------------|
| `condition` | string | When this failure mode applies |
| `action` | enum | `stop`, `rollback`, `request_more_context`, `pause_and_checkpoint` |
| `recovery` | object | Recovery loop configuration |

---

## 6. Canonical Schemas

### 6.1 Required Schema Files

| Schema | Purpose |
|--------|---------|
| `world_state_schema.yaml` | World state structure |
| `event_schema.yaml` | Event and observation structure |
| `entity_taxonomy.yaml` | Entity type hierarchy |
| `authority_trust_model.yaml` | Trust scoring configuration |
| `identity_resolution_policy.yaml` | Identity resolution rules |

### 6.2 Observation Requirements

All observations MUST record:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique observation ID |
| `timestamp` | datetime | Yes | When observed |
| `source` | object | Yes | Where observed |
| `raw_payload` | any | Yes | Original unmodified data |
| `canonical_payload` | object | Yes | Normalized data |
| `evidence_anchors` | array | Yes | Links to original evidence |
| `provenance` | object | Yes | Traceability record |

### 6.3 World State Requirements

World state snapshots MUST record:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version_id` | string | Yes | Unique snapshot ID |
| `parent_version_id` | string | No | Previous snapshot (null for initial) |
| `timestamp` | datetime | Yes | When snapshot was created |
| `entities` | array | Yes | Current entity states |
| `relationships` | array | No | Entity relationships |
| `lineage` | object | Yes | How this state was derived |
| `uncertainty` | object | No | Confidence and uncertainty information |
| `retention_policy` | object | No | How long to retain |

---

## 7. Identity Resolution Policy

### 7.1 Entity Identification

Entities MUST have hierarchical namespaces:
```
namespace:type:id
example: org.company:user:12345
```

### 7.2 Alias Confidence Scoring

Alias matching MUST use weighted feature scoring:

| Feature | Weight Range | Description |
|---------|--------------|-------------|
| Exact match | 1.0 | Identical identifiers |
| Fuzzy match | 0.0-0.9 | Similar but not identical |
| Cross-reference | 0.5-1.0 | Linked by another source |
| Temporal proximity | 0.0-0.5 | Close in time |

### 7.3 Merge/Split Rules

- Merge: Combine two entity records into one
- Split: Divide one entity record into multiple

Hard constraints that MUST NOT be violated:
- Never merge entities with conflicting unique identifiers
- Never merge across incompatible entity types
- Always record merge/split in lineage

---

## 8. Authority Trust Model

### 8.1 Trust Score Calculation

Trust scores MUST support:

| Factor | Description |
|--------|-------------|
| Source ranking | Static authority weight per source |
| Time decay | Score decreases over time (configurable half-life) |
| Field authority | Sources may be authoritative for specific fields |
| Confidence weight | Self-reported confidence from source |

### 8.2 Conflict Resolution

When sources disagree, resolution strategies include:

| Strategy | Description |
|----------|-------------|
| `prefer_authoritative_sources` | Highest authority wins |
| `prefer_recent` | Most recent wins |
| `prefer_high_confidence` | Highest confidence wins |
| `merge_with_uncertainty` | Keep both with uncertainty |
| `escalate_to_human` | Require human decision |

---

## 9. Error Model

### 9.1 Error Categories

| Category | Code Range | Description |
|----------|------------|-------------|
| Validation | V1xx | Static validation failures |
| Binding | B2xx | Binding resolution failures |
| Schema | S3xx | Schema validation failures |
| Runtime | R4xx | Runtime execution failures |
| Safety | F5xx | Safety constraint violations |

### 9.2 Validation Errors

| Code | Name | Description |
|------|------|-------------|
| V101 | UNKNOWN_CAPABILITY | Capability ID not found in ontology |
| V102 | MISSING_PREREQUISITE | Required capability not executed before |
| V103 | INVALID_STEP | Step definition missing required fields |
| V104 | DUPLICATE_STORE_AS | Same store_as used by multiple steps |
| V105 | CIRCULAR_DEPENDENCY | Workflow contains circular dependencies |

### 9.3 Binding Errors

| Code | Name | Description |
|------|------|-------------|
| B201 | INVALID_BINDING_PATH | Referenced path does not exist |
| B202 | MISSING_PRODUCER | Referenced store_as not found |
| B203 | TYPE_MISMATCH | Binding type incompatible with consumer |
| B204 | AMBIGUOUS_TYPE | Type cannot be inferred, annotation required |
| B205 | INVALID_ANNOTATION | Type annotation does not match schema |

### 9.4 Schema Errors

| Code | Name | Description |
|------|------|-------------|
| S301 | SCHEMA_NOT_FOUND | Referenced schema file not found |
| S302 | INVALID_REF | $ref cannot be resolved |
| S303 | SCHEMA_VALIDATION_FAILED | Data does not match schema |
| S304 | MISSING_REQUIRED_FIELD | Required field not present |

### 9.5 Runtime Errors

| Code | Name | Description |
|------|------|-------------|
| R401 | EXECUTION_TIMEOUT | Step exceeded timeout |
| R402 | EXECUTION_FAILED | Step execution failed |
| R403 | GATE_BLOCKED | Gate condition blocked execution |
| R404 | RECOVERY_EXHAUSTED | Max recovery loops exceeded |

### 9.6 Safety Errors

| Code | Name | Description |
|------|------|-------------|
| F501 | CHECKPOINT_REQUIRED | Mutation without checkpoint |
| F502 | APPROVAL_REQUIRED | Action requires approval |
| F503 | ROLLBACK_FAILED | Could not restore checkpoint |
| F504 | CONSTRAINT_VIOLATED | Policy constraint violated |
| F505 | PROVENANCE_MISSING | Claim without provenance |

### 9.7 Error Response Format

Errors MUST be returned in this format:

```json
{
  "error": {
    "code": "V101",
    "name": "UNKNOWN_CAPABILITY",
    "message": "Capability 'unknown-cap' not found in ontology",
    "location": {
      "workflow": "my_workflow",
      "step": 3,
      "field": "capability"
    },
    "suggestion": "Did you mean 'detect' (with domain: 'anomaly')?"
  }
}
```

---

## 10. Conformance

### 10.1 Conformance Levels

| Level | Requirements |
|-------|--------------|
| **L1** | Validate capability existence and prerequisites |
| **L2** | Resolve $ref schemas and infer binding types |
| **L3** | Validate binding types against consumer contracts |
| **L4** | Emit patch suggestions using coercion registry |

### 10.2 Conformance Requirements

An implementation is conformant at a given level if it:

**L1 (Basic)**
- Validates all capabilities exist in the ontology
- Validates all prerequisites are satisfied
- Validates all store_as identifiers are unique

**L2 (Schema)**
- Resolves all $ref schema references
- Infers binding types from producer schemas
- Reports ambiguous types requiring annotation

**L3 (Contracts)**
- Validates inferred types against consumer input schemas
- Reports type mismatches with suggested fixes
- Validates gate and condition expressions

**L4 (Patches)**
- Emits JSON patch suggestions for fixable errors
- Uses coercion registry for type conversions
- Generates diff patches on request

### 10.3 Conformance Testing

Conformance tests MUST include:
- Positive fixtures (valid workflows that MUST pass)
- Negative fixtures (invalid workflows that MUST fail with specific error codes)
- Patch fixtures (invalid workflows with expected patch suggestions)

---

## 11. Versioning and Compatibility

### 11.1 Semantic Versioning

This standard follows Semantic Versioning 2.0.0:

| Change Type | Version Bump | Example |
|-------------|--------------|---------|
| Breaking changes | MAJOR | Removing capability, changing required fields |
| New features | MINOR | Adding optional fields, new capabilities |
| Bug fixes | PATCH | Clarifications, typo fixes |

### 11.2 Deprecation Policy

1. Features are deprecated in a MINOR release with warnings
2. Deprecated features are removed in the next MAJOR release
3. Deprecation notices MUST include migration path
4. Minimum deprecation period: 6 months

### 11.3 Compatibility Guarantees

**Forward Compatibility**
- Validators SHOULD ignore unknown fields
- New optional fields MUST have sensible defaults
- New capabilities MUST NOT break existing workflows

**Backward Compatibility**
- Existing workflows MUST continue to validate
- Existing capabilities MUST NOT change semantics
- Removed features MUST be deprecated first

### 11.4 Schema Evolution

| Change | Compatibility |
|--------|---------------|
| Add optional field | Compatible |
| Add required field | Breaking |
| Remove field | Breaking |
| Change field type | Breaking |
| Rename field | Breaking |
| Add enum value | Compatible |
| Remove enum value | Breaking |

### 11.5 Version Header

All workflow files SHOULD include a version header:

```yaml
# Standard version: 1.0.0
workflow_name:
  goal: ...
```

Validators SHOULD warn if version header is missing.

---

## 12. Decision Frameworks

This section provides guidance for common decisions when applying the standard.

### 12.1 When to Use Checkpoints

Use this decision tree:

```
Does the step modify external state?
├── No → Checkpoint not required
└── Yes → Is the modification reversible by other means?
    ├── Yes (idempotent, can retry) → Checkpoint recommended but optional
    └── No → Checkpoint REQUIRED
```

**Examples:**

| Operation | Checkpoint Required? | Reason |
|-----------|---------------------|--------|
| Read file contents | No | No mutation |
| Write to database | Yes | State change, may not be reversible |
| Send HTTP GET | No | Read-only |
| Send HTTP POST | Yes | May cause side effects |
| Rename file | Yes | May overwrite existing file |
| Append to log | Optional | Append-only, can ignore duplicate |

### 12.2 When to Require Typed Bindings

Typed annotations are REQUIRED when:

| Scenario | Example | Solution |
|----------|---------|----------|
| Union schemas | `anyOf: [string, object]` | Add `: string` or `: object` |
| Open schemas | `additionalProperties: true` | Add explicit type |
| Array item ambiguity | `items: {}` | Add `: array<object>` |
| Cross-workflow references | Dynamic binding | Always annotate |

Typed annotations are OPTIONAL when:
- Producer schema has explicit, unambiguous type
- Single possible type interpretation exists

### 12.3 Choosing Conflict Resolution Strategy

| Scenario | Recommended Strategy |
|----------|---------------------|
| Hardware sensor vs. derived inference | `prefer_authoritative_sources` |
| Recent data vs. stale data | `prefer_recent` |
| High-confidence vs. low-confidence | `prefer_high_confidence` |
| Both sources equally valid | `merge_with_uncertainty` |
| Critical decision, ambiguous data | `escalate_to_human` |

### 12.4 Selecting Conformance Level

| Your situation | Start with | Target |
|----------------|------------|--------|
| New to the standard | L1 | L2 within 1 month |
| Existing workflows, want validation | L2 | L3 within 1 quarter |
| Production system, high reliability needed | L3 | L4 for auto-fix |
| Compliance/audit requirements | L3 minimum | L4 recommended |

### 12.5 Common Patterns

**Pattern: Safe Mutation**
```yaml
- capability: plan
  store_as: plan_out
- capability: checkpoint
  store_as: checkpoint_out
- capability: mutate
  requires_checkpoint: true
  input_bindings:
    plan: ${plan_out}
  store_as: mutate_out
- capability: verify
  store_as: verify_out
- capability: audit
  store_as: audit_out
```

**Pattern: Multi-Source Integration**
```yaml
- capability: retrieve
  store_as: source_a
- capability: retrieve
  store_as: source_b
- capability: integrate
  input_bindings:
    sources: [${source_a}, ${source_b}]
  store_as: integrated
```

**Pattern: Recovery Loop**
```yaml
- capability: verify
  store_as: verify_out
  failure_modes:
    - condition: verdict == FAIL
      action: rollback
      recovery:
        goto_step: plan
        inject_context:
          failure_evidence: ${verify_out.violations}
        max_loops: 3
```

---

## 13. References

### 13.1 Normative References

- [JSON Schema](https://json-schema.org/)
- [YAML 1.2](https://yaml.org/spec/1.2.2/)
- [Semantic Versioning](https://semver.org/)

### 13.2 Informative References

- [RFC-0001: Agent Capability Ontology](RFC-0001-agent-capability-ontology-and-workflow-dsl.md)
- [Whitepaper: Grounded Agency](WHITEPAPER.md)
- [Conformance Guide](CONFORMANCE.md)
- [Security Model](SECURITY.md)

---

## Appendix A: Layer Reference

| Layer | Count | Capabilities |
|-------|-------|-------------|
| PERCEIVE | 4 | retrieve, search, observe, receive |
| UNDERSTAND | 6 | detect, classify, measure, predict, compare, discover |
| REASON | 4 | plan, decompose, critique, explain |
| MODEL | 5 | state, transition, attribute, ground, simulate |
| SYNTHESIZE | 3 | generate, transform, integrate |
| EXECUTE | 3 | execute, mutate, send |
| VERIFY | 5 | verify, checkpoint, rollback, constrain, audit |
| REMEMBER | 2 | persist, recall |
| COORDINATE | 4 | delegate, synchronize, invoke, inquire |

## Appendix B: Reserved Identifiers

The following identifiers are reserved and MUST NOT be used for custom capabilities:

- All identifiers starting with `_` (underscore)
- All identifiers starting with `system-`
- All identifiers starting with `internal-`

---

**End of Standard**
