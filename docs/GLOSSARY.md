# Glossary

Key terms used in the Agent Capability Standard.

---

## Core Concepts

### Capability
An atomic primitive that does one thing well. Capabilities have:
- A unique `id`
- A `layer` classification (PERCEPTION, MODELING, REASONING, ACTION, SAFETY, META, MEMORY, COORDINATION)
- `input_schema` and `output_schema` defining typed contracts
- `requires` (hard prerequisites) and `soft_requires` (recommended prerequisites)

Example: `detect-anomaly`, `checkpoint`, `act-plan`

### Workflow
An ordered, conditional, or parallel composition of capabilities. Workflows define:
- A `goal` describing the intended outcome
- A `risk` level (low, medium, high)
- A sequence of `steps`, each invoking a capability
- `inputs` schema for external data

Example: `debug_code_change`, `digital_twin_sync_loop`

### Skill
A self-contained unit that implements a capability. Each skill has a `SKILL.md` file with:
- YAML frontmatter (name, description)
- Instructions for execution
- Examples

Skills are organized by layer in the `skills/` directory.

---

## World Modeling

### Observation
An append-only event grounded in evidence. Observations record:
- `timestamp`: When the observation was made
- `source`: Where the observation came from
- `raw_payload`: Original data
- `canonical_payload`: Normalized data
- `evidence_anchors`: Links to original evidence
- `provenance`: Traceability record

### World State
A derived snapshot from observations and transition rules. World state includes:
- Current state variables and estimates
- Uncertainty information
- Lineage (how this state was derived)
- `version_id` and `parent_version_id` for versioning

### Provenance
Traceability record for claims and transformations. Provenance answers:
- Where did this data come from?
- What transformations were applied?
- Who or what made this claim?

### Grounding
Anchoring claims to evidence. A grounded claim has explicit references to the observations or sources that support it. Ungrounded claims are explicitly marked as inferred.

### Evidence Anchor
A reference to the original source of information. Evidence anchors enable verification by pointing to:
- Source documents
- API responses
- Log entries
- Sensor readings

---

## Trust and Identity

### Trust Score
Authority-weighted, confidence-weighted, recency-decayed score for a source or claim. Trust scores consider:
- Source ranking weights (authoritative sources score higher)
- Time decay (older information scores lower)
- Field-specific authority preferences

### Identity Resolution
Defining entities and resolving aliases across sources. Identity resolution:
- Assigns unique IDs to entities
- Scores alias confidence
- Applies merge/split rules with hard constraints

### Authority Trust Model
A model for ranking sources by trustworthiness. The model supports:
- Source ranking weights
- Time decay (half-life)
- Field-specific authority preferences
- Conflict resolution strategies

---

## Workflow DSL

### Binding
A reference from one step to another step's output. Bindings use the syntax:
- `${store_as.field.path}` — reference a field
- `${store_as.field.path: type}` — typed annotation

Example: `${inspect_out.findings}`, `${world_state_out.entities: array<object>}`

### Gate
A conditional check that can halt or redirect workflow execution. Gates define:
- `when`: Condition expression
- `action`: What to do if condition matches (stop, rollback, skip)
- `message`: Explanation for the action

Example: Stop if no checkpoint exists before mutation.

### Recovery Loop
Logic for handling failures and retrying. Recovery loops define:
- `condition`: When to trigger recovery
- `goto_step`: Where to resume
- `inject_context`: Additional context for retry
- `max_loops`: Maximum retry attempts

### Failure Mode
A documented way a step can fail, with recovery instructions:
- `condition`: What triggers the failure mode
- `action`: Immediate response (stop, rollback, request_more_context)
- `recovery`: How to recover

### Store As
The identifier used to store a step's output for later reference. Other steps can use this identifier in their bindings.

Example: `store_as: inspect_out` allows later steps to use `${inspect_out.findings}`

### Parallel Group
Steps that can execute concurrently. Parallel groups define:
- `parallel_group`: Group identifier
- `join`: How to wait for completion (all_complete, any_complete)

---

## Safety Concepts

### Checkpoint
A saved state that enables rollback. Checkpoints are required before:
- Any step with `mutation: true`
- Any step that may cause side effects

### Rollback
Reverting to a previous checkpoint. Rollback is triggered when:
- Verification fails
- Unexpected side effects are detected
- Gates block execution

### Mutation
A change to external state (files, databases, APIs). Steps with `mutation: true`:
- Require a prior checkpoint
- May require approval
- Should have rollback plans

### Audit
Recording what changed, why, and by whom. Audit trails include:
- Tool usage logs
- Decision rationale
- Diff records
- Provenance links

### Verify
Checking that outcomes match expectations. Verification:
- Returns PASS or FAIL with evidence
- May trigger rollback on failure
- Requires `model-schema` to define expectations

### Constrain
Enforcing policy and least privilege. Constraints check:
- Whether actions comply with policies
- Whether permissions are sufficient
- Whether rate limits are respected

---

## Schema Concepts

### Input Schema
The expected structure of data a capability accepts. Input schemas are defined using JSON Schema and may include:
- Required properties
- Property types
- Constraints

### Output Schema
The guaranteed structure of data a capability produces. Output schemas enable:
- Type checking for bindings
- Contract verification
- Documentation

### Type Coercion
Converting data from one type to another. Coercion is used when:
- Source and target types are compatible but different
- Transformation is deterministic
- Loss is documented

### Transform Mapping
A declarative specification for converting between schemas. Transform mappings:
- Define field-by-field conversions
- Specify coercion functions
- Document any loss of information

---

## Layers

### PERCEPTION
Capabilities that observe the world without modifying it.
Examples: `inspect`, `search`, `retrieve`, `receive`

### MODELING
Capabilities that build understanding and representations.
Examples: `detect-*`, `identify-*`, `estimate-*`, `world-state`, `model-schema`

### REASONING
Capabilities that think, compare, and decide.
Examples: `compare-*`, `plan`, `decide`, `critique`, `explain`

### ACTION
Capabilities that cause changes in the world.
Examples: `act-plan`, `generate-*`, `transform`, `send`

### SAFETY
Capabilities that protect, verify, and enable recovery.
Examples: `verify`, `checkpoint`, `rollback`, `audit`, `constrain`

### META
Capabilities for self-reflection and discovery.
Examples: `discover-*`, `prioritize`

### MEMORY
Capabilities for persistence and recall.
Examples: `recall`

### COORDINATION
Capabilities for multi-agent and workflow orchestration.
Examples: `delegate`, `synchronize`, `invoke-workflow`

---

## Conformance

### Conformance Level
The degree to which an implementation satisfies the standard:
- **L1**: Validates capability existence and prerequisites
- **L2**: Resolves schemas and infers types
- **L3**: Validates binding types against consumer contracts
- **L4**: Emits patch suggestions and uses coercion registry

### Prerequisite
A capability that must be executed before another. Prerequisites are defined in the capability ontology:
- `requires`: Hard prerequisite (must be satisfied)
- `soft_requires`: Recommended but not mandatory

---

## Related Terms

### Grounded Agency
The philosophy behind the Agent Capability Standard. Grounded Agency emphasizes:
- Evidence-backed claims
- Auditable transformations
- Safety by construction
- Composable primitives

### Digital Twin
A synchronized model of a real-world system. The standard includes workflows for:
- Building initial world models
- Synchronizing with incoming signals
- Detecting drift
- Executing safe corrective actions

---

See also: [STANDARD-v1.0.0.md](../spec/STANDARD-v1.0.0.md) for formal definitions.
