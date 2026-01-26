# Glossary

Key terms used in the Agent Capability Standard. Each term includes context on **why it matters** and **what problems it solves**.

---

## Core Concepts

### Capability
An atomic primitive that does one thing well. Capabilities have:
- A unique `id`
- A `layer` classification (PERCEIVE, UNDERSTAND, REASON, MODEL, SYNTHESIZE, EXECUTE, VERIFY, REMEMBER, COORDINATE)
- `input_schema` and `output_schema` defining typed contracts
- `risk` level and `mutation` flag for safety classification

Example: `detect`, `checkpoint`, `mutate`

**Why it matters:** Capabilities with explicit contracts enable static validation. You know before runtime whether outputs will match expected inputs.

**What it prevents:** Runtime type errors, silent failures from incompatible data, and debugging sessions that trace data through multiple steps

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

## Capability Theory

### Atomic Capability
A capability that cannot be decomposed into simpler operations without losing essential semantics. Atomicity criteria:
- **Irreducibility**: Cannot be expressed as a composition of other capabilities
- **Single purpose**: Does one thing well
- **Typed contract**: Has well-defined input and output schemas
- **Domain-general**: Not specific to one tool or framework

**Why it matters:** Atomic capabilities are the true primitives. If a capability can be decomposed, it's not atomic—it's a pattern or workflow.

**What it prevents:** Redundant capabilities, unclear boundaries, and explosion of capability count.

### Workflow Composition
The combination of multiple capabilities to achieve a goal. Workflows are "molecules" built from capability "atoms."

Example: `debug_code_change` composes:
```
observe → search → plan → checkpoint → execute → verify → rollback
```

**Why it matters:** Value comes from compositions, not from primitive count. The goal is better workflows, not more capabilities.

### Layer
A functional category grouping capabilities by their primary purpose. The 9 cognitive layers are:
- **PERCEIVE**: Acquire information from external sources (retrieve, search, observe, receive)
- **UNDERSTAND**: Make sense of information (detect, classify, measure, predict, compare, discover)
- **REASON**: Analyze and plan (plan, decompose, critique, explain)
- **MODEL**: Represent the world (state, transition, attribute, ground, simulate)
- **SYNTHESIZE**: Create content (generate, transform, integrate)
- **EXECUTE**: Change the world (execute, mutate, send)
- **VERIFY**: Ensure correctness (verify, checkpoint, rollback, constrain, audit)
- **REMEMBER**: Persistence across invocations (persist, recall)
- **COORDINATE**: Multi-agent interaction (delegate, synchronize, invoke)

Layers are derived from cognitive architecture theory (BDI, SOAR, ReAct) and control theory.

**Why it matters:** Layers provide cognitive organization and enable validation (e.g., PERCEIVE before UNDERSTAND).

### Capability Derivation
The systematic process by which capabilities are identified and justified. Grounded Agency derives capabilities from:
1. The DIS '23 AI Capabilities framework (8 foundational verbs)
2. Domain specialization (verb + domain → specific capability)
3. Operational requirements for production agents
4. Atomicity validation (ensure each is truly irreducible)

See [docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md](methodology/FIRST_PRINCIPLES_REASSESSMENT.md).

### Extension Governance
The rules and process for adding new capabilities to the ontology. New capabilities must:
- Be non-composable (cannot be built from existing capabilities)
- Pass atomicity tests
- Be used in at least one reference workflow
- Fit clearly into exactly one layer

See [docs/methodology/EXTENSION_GOVERNANCE.md](methodology/EXTENSION_GOVERNANCE.md).

### Capability Tier
A classification based on validation status:
- **Core Tier**: Capabilities validated in reference workflows (stable)
- **Extended Tier**: Capabilities designed but not fully validated (stable API, limited usage proof)
- **Experimental Tier**: New proposals under evaluation (no stability guarantees)

**Why it matters:** Tiers communicate maturity. Core capabilities are battle-tested; Extended are designed but less proven.

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

**Why it matters:** Without grounding, agents confidently state hallucinations. When asked "why did you conclude X?", there's no answer. Debugging requires manual verification of every claim.

**What it prevents:**
- Hallucinated facts propagating through workflows
- Untraceable decision reasoning
- Failed audits due to missing provenance
- Hours of debugging to find where bad data entered

### Evidence Anchor
A reference to the original source of information. Evidence anchors enable verification by pointing to:
- Source documents
- API responses
- Log entries
- Sensor readings

**Why it matters:** Evidence anchors make claims verifiable. Instead of "the error rate is 5%", you get "the error rate is 5% (source: Prometheus query at 2024-01-24T10:00:00Z)".

**What it prevents:** Unverifiable claims that erode trust over time, and audit failures when you can't prove where data came from

---

## Trust and Identity

### Trust Score
Authority-weighted, confidence-weighted, recency-decayed score for a source or claim. Trust scores consider:
- Source ranking weights (authoritative sources score higher)
- Time decay (older information scores lower)
- Field-specific authority preferences

**Why it matters:** When sources conflict, you need a principled way to decide which to believe. Trust scores make conflict resolution transparent and consistent instead of arbitrary.

**What it prevents:** Arbitrary "last source wins" resolution, inconsistent decisions about which data to trust, and unexplainable conflicts that require human intervention every time

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

Example: `${observe_out.observation}`, `${state_out.entities: array<object>}`

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

Example: `store_as: observe_out` allows later steps to use `${observe_out.observation}`

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

**Why it matters:** Checkpoints are your safety net. When step 7 fails after steps 1-6 modified state, a checkpoint lets you restore to a known-good state in seconds instead of hours of manual cleanup.

**What it prevents:** Corrupted state from partial execution, inconsistent data visible to users, and the nightmare of manually reversing changes across multiple systems

### Rollback
Reverting to a previous checkpoint. Rollback is triggered when:
- Verification fails
- Unexpected side effects are detected
- Gates block execution

**Why it matters:** Rollback makes failures recoverable. Instead of "the workflow failed, now what?", you get "the workflow failed, reverting to checkpoint, state is now consistent."

**What it prevents:** Permanent damage from failed mutations, manual recovery procedures that introduce new errors, and downtime while you figure out what state things are in

### Mutation
A change to external state (files, databases, APIs). Steps with `mutation: true`:
- Require a prior checkpoint
- May require approval
- Should have rollback plans

**Why it matters:** Explicitly marking mutations makes dangerous operations visible. The validator enforces checkpoints before mutations—you can't accidentally skip safety.

**What it prevents:** "Oops, I didn't realize that step modified the database" surprises, and the false confidence of thinking a workflow is read-only when it isn't

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
- Uses `constrain` to define expectations and policies

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

### PERCEIVE
Capabilities that acquire information from external sources without modifying it.
Examples: `retrieve`, `search`, `observe`, `receive`

### UNDERSTAND
Capabilities that make sense of information and form beliefs.
Examples: `detect`, `classify`, `measure`, `predict`, `compare`, `discover`

### REASON
Capabilities that analyze, plan, and decide.
Examples: `plan`, `decompose`, `critique`, `explain`

### MODEL
Capabilities that represent the world and its dynamics.
Examples: `state`, `transition`, `attribute`, `ground`, `simulate`

### SYNTHESIZE
Capabilities that create new content.
Examples: `generate`, `transform`, `integrate`

### EXECUTE
Capabilities that cause changes in the world.
Examples: `execute`, `mutate`, `send`

### VERIFY
Capabilities that protect, verify, and enable recovery.
Examples: `verify`, `checkpoint`, `rollback`, `constrain`, `audit`

### REMEMBER
Capabilities for persistence and recall.
Examples: `persist`, `recall`

### COORDINATE
Capabilities for multi-agent and workflow orchestration.
Examples: `delegate`, `synchronize`, `invoke`, `inquire`

---

## Conformance

### Conformance Level
The degree to which an implementation satisfies the standard:
- **L1**: Validates capability existence and prerequisites
- **L2**: Resolves schemas and infers types
- **L3**: Validates binding types against consumer contracts
- **L4**: Emits patch suggestions and uses coercion registry

**Why it matters:** Conformance levels let you adopt incrementally. Start with L1 (basic validation) and progress to L4 (full type safety with auto-fix suggestions) as your workflows mature.

**What it prevents:** All-or-nothing adoption that blocks progress, and uncertainty about what guarantees your implementation actually provides

### Prerequisite
A capability that must be executed before another. Prerequisites are defined in the capability ontology:
- `requires`: Hard prerequisite (must be satisfied)
- `soft_requires`: Recommended but not mandatory

---

## Capability Definitions

### Inquire
Request clarification when input is ambiguous. The `inquire` capability generates targeted clarifying questions to resolve uncertainty in user requests before proceeding. Located in the COORDINATE layer because it handles agent-user coordination.

**When to use:** When a user request has:
- Missing required parameters
- Conflicting interpretations
- Insufficient constraints for reliable execution

**Why it matters:** Agents that assume a single interpretation frustrate users who intended something different. Explicit clarification prevents wasted work and incorrect results.

**What it prevents:**
- Hallucinated assumptions about user intent
- Incorrect results from underspecified requests
- Frustrated users who expected different outcomes

**Output includes:**
- Clarifying questions targeting specific ambiguities
- Ambiguity analysis (missing parameters, conflicting interpretations)
- Confidence score indicating how certain the agent is that clarification is needed

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
