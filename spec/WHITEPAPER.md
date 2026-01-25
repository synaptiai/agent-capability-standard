# Grounded Agency: Building Agent Systems That Survive Production

**A Framework for Reliable AI Agent Architecture**

---

## Executive Summary

**For decision-makers evaluating this framework:**

### The Problem

AI agents fail in production—not because the AI can't do the task, but because the *architecture* can't support reliable execution. Specifically:

- **No contracts**: Capabilities compose through natural language, not typed interfaces. Type mismatches surface at runtime.
- **No provenance**: When agents make mistakes, there's no trail to debug or explain.
- **No recovery**: Failed mutations leave systems in inconsistent states requiring manual cleanup.
- **No trust model**: Conflicting data sources are resolved arbitrarily or not at all.

### The Solution

The Agent Capability Standard provides structural reliability:

| Problem | Solution |
|---------|----------|
| Implicit composition | 99 capabilities with typed I/O schemas |
| Ungrounded claims | Evidence anchors and provenance tracking |
| Undefined conflict resolution | Trust-weighted, time-decayed source ranking |
| Retrofitted safety | Checkpoints required before mutations |

### Business Impact

| Metric | Expected Improvement |
|--------|---------------------|
| Debug time for agent issues | 50-80% reduction |
| Data corruption from failed workflows | Near elimination |
| Compliance audit preparation | Automatic decision lineage |
| Integration bugs caught pre-production | 90%+ with L3 conformance |

### Adoption Recommendation

- **Start small**: Run the validator on existing workflows (1 day)
- **Add safety**: Implement checkpoints for high-risk mutations (1 week)
- **Expand**: Progress to full conformance as value is demonstrated (1 quarter)

The standard is framework-agnostic and modular. Adopt what you need; expand as complexity grows.

---

## Abstract

Most AI agent systems fail in production because they lack three essential properties: compositional contracts between capabilities, grounded state representations with provenance, and safety semantics that make dangerous actions structurally difficult. We present the Agent Capability Standard—a specification for atomic agent capabilities and a workflow DSL with typed bindings, recovery semantics, and world-model schemas that integrate provenance, uncertainty, trust, and identity resolution. We also provide a compiler-grade validator that can automatically propose deterministic transform patches. This paper describes the motivation, design rationale, architecture, and evaluation approach for the standard.

---

## 1. Introduction

### 1.1 The Promise and Peril of AI Agents

AI agents—systems that can perceive, reason, and act autonomously—represent one of the most exciting frontiers in artificial intelligence. From debugging code to managing infrastructure to orchestrating complex business processes, agents promise to automate tasks that previously required human judgment.

But there's a problem: most agent systems fail in production.

The failures are not in the AI's raw capabilities. Modern language models can write code, analyze documents, and generate plans. The failures are *architectural*—in how agent capabilities compose, how state is represented, and how safety is enforced.

### 1.2 Why Agent Systems Fail

Through analysis of agent system deployments, we've identified four recurring failure patterns:

**1. Implicit Composition**
Agent capabilities are typically composed through natural language prompting. There are no formal contracts between capabilities. When one capability produces output that another cannot handle, the system fails silently or produces incorrect results.

**2. Ungrounded State**
Agent systems often maintain internal state without explicit provenance. When asked "why did you do that?", the system cannot trace its reasoning to source evidence. This makes debugging impossible and trust erosion inevitable.

**3. Undefined Conflict Resolution**
When information from multiple sources conflicts, most agent systems have no principled way to resolve it. They may use whichever source was queried last, or attempt to merge inconsistent data, or simply hallucinate a resolution.

**4. Retrofitted Safety**
Safety in agent systems is typically added as an afterthought—a list of things the agent "shouldn't do." But without structural enforcement, safety properties are easily violated through prompt engineering, edge cases, or system bugs.

### 1.3 The Grounded Agency Approach

This paper introduces **Grounded Agency**—an approach to agent architecture that makes reliability a structural property rather than a behavioral aspiration.

The core insight is that reliable agent systems require:
- **Explicit contracts** between capabilities (what each produces and consumes)
- **Grounded claims** with provenance (where information came from)
- **Trust-aware fusion** for conflict resolution (which sources to believe)
- **Safety by construction** (dangerous actions are structurally difficult)

We implement this approach through the Agent Capability Standard, which provides:
1. A capability ontology with typed I/O schemas
2. A workflow DSL with bindings, gates, and recovery semantics
3. World state schemas with uncertainty and provenance
4. A trust model with authority ranking and time decay
5. A validator that enforces contracts at definition time

---

## 2. Background and Related Work

### 2.1 Agent Architectures

The field of AI agents has evolved through several architectural paradigms:

**Reactive Agents** (Brooks, 1986) respond directly to stimuli without internal state. While robust, they cannot handle tasks requiring memory or planning.

**BDI Agents** (Bratman, 1987; Rao & Georgeff, 1995) maintain beliefs, desires, and intentions. They provide a framework for goal-directed behavior but leave composition and safety to the implementer.

**Cognitive Architectures** (Soar, ACT-R) provide unified theories of cognition but are complex to implement and not designed for modern LLM-based systems.

**LLM-based Agents** (AutoGPT, LangChain, etc.) leverage language models for planning and execution. They are flexible but typically lack formal contracts and safety guarantees.

### 2.2 Workflow Languages

Our workflow DSL draws on prior work in:

**Business Process Languages** (BPEL, BPMN) provide formal semantics for process composition but are designed for human-readable documentation rather than machine validation.

**Dataflow Languages** (TensorFlow, Apache Beam) provide typed dataflow graphs but lack the conditional execution and recovery semantics needed for agent workflows.

**Orchestration Systems** (Temporal, Airflow) provide workflow execution with recovery but don't address the semantic contracts between steps.

### 2.3 Knowledge Representation

Our world state model builds on:

**Provenance** (PROV-O, W3C) provides vocabulary for describing provenance but leaves interpretation to the application.

**Uncertainty Representation** (Bayesian networks, Dempster-Shafer) provides formal frameworks for reasoning under uncertainty but requires domain-specific modeling.

**Entity Resolution** (record linkage, deduplication) addresses identity matching but typically assumes batch processing rather than streaming updates.

### 2.4 Our Contribution

The Agent Capability Standard synthesizes these approaches into a cohesive framework specifically designed for LLM-based agent systems. Our key contributions are:

1. **Capability ontology with layered classification** organizing 99 atomic capabilities by function
2. **Typed workflow DSL** with static validation of bindings and contracts
3. **World state schema** with integrated provenance, uncertainty, and trust
4. **Safety invariants** enforced at validation time, not just runtime
5. **Compiler-grade validator** that produces actionable error messages and patch suggestions

---

## 3. The Capability Ontology

### 3.1 Design Principles

We designed the capability ontology around four principles:

**Atomicity**: Each capability does exactly one thing. Complex behaviors emerge from composition, not from monolithic capabilities.

**Layer Classification**: Capabilities are organized by their relationship to the world (observe vs. modify) and their cognitive function (perceive vs. reason vs. act).

**Explicit Contracts**: Every capability has typed input and output schemas. The types are not just documentation—they are enforced by the validator.

**Dependency Semantics**: Some capabilities require others. These dependencies are first-class and enforced structurally.

### 3.2 Layer Organization

We organize capabilities into 8 layers:

| Layer | Purpose | Mutation | Count |
|-------|---------|----------|-------|
| PERCEPTION | Observe the world | No | 4 |
| MODELING | Build understanding | No | 45 |
| REASONING | Think and decide | No | 20 |
| ACTION | Change things | Yes | 12 |
| SAFETY | Protect and verify | Varies | 7 |
| META | Self-reflection | No | 6 |
| MEMORY | Persistence | Varies | 2 |
| COORDINATION | Multi-agent | Varies | 3 |

This organization provides several benefits:
- **Risk assessment**: ACTION layer capabilities are inherently higher risk
- **Dependency ordering**: PERCEPTION typically precedes MODELING, which precedes REASONING, which precedes ACTION
- **Safety integration**: SAFETY capabilities can be required before ACTION capabilities

### 3.3 Key Capability Families

**Detection and Identification** (MODELING layer)
Capabilities like `detect-anomaly`, `detect-drift`, `identify-entity`, and `identify-cause` build understanding from observations. They produce typed outputs with confidence scores and evidence anchors.

**Planning and Decision** (REASONING layer)
Capabilities like `plan`, `decide`, `compare-options`, and `prioritize` produce structured decisions. Critically, `plan` produces a plan object that `act-plan` can execute.

**Action Execution** (ACTION layer)
The `act-plan` capability is the primary mutation point. It requires:
- A `plan` from the REASONING layer
- A `checkpoint` from the SAFETY layer
- Optionally, `verify` to confirm the outcome

**Safety Primitives** (SAFETY layer)
- `checkpoint`: Save state for potential rollback
- `rollback`: Restore to a checkpoint
- `verify`: Check outcomes against invariants
- `audit`: Record what happened and why
- `constrain`: Enforce policy limits

### 3.4 Dependency Semantics

We distinguish hard and soft dependencies:

**Hard dependencies** (`requires`) MUST be satisfied. The validator rejects workflows that violate them.

```json
{
  "id": "act-plan",
  "requires": ["plan", "checkpoint"]
}
```

**Soft dependencies** (`soft_requires`) SHOULD be satisfied. The validator warns but does not reject.

```json
{
  "id": "act-plan",
  "soft_requires": ["verify"]
}
```

This distinction allows flexibility while ensuring critical safety properties.

---

## 4. The Workflow DSL

### 4.1 Design Goals

We designed the workflow DSL to support:

**Static Validation**: Catch errors at definition time, not runtime
**Typed Composition**: Ensure outputs match expected inputs
**Safety by Default**: Make dangerous patterns require explicit opt-in
**Recovery Semantics**: Define what happens when things go wrong

### 4.2 Workflow Structure

A workflow consists of:

```yaml
workflow_name:
  goal: What this workflow achieves
  risk: low | medium | high
  inputs: External input schema
  steps: Ordered list of capability invocations
  success: Criteria for successful completion
```

Each step invokes a capability and stores its output:

```yaml
- capability: detect-anomaly
  purpose: Find unusual patterns
  store_as: anomaly_out
  input_bindings:
    context: ${inspect_out.findings}
```

### 4.3 The Binding System

Bindings connect steps by referencing prior outputs:

**Basic binding**: `${step_out.field.path}`
**Typed binding**: `${step_out.field.path: array<object>}`

The validator checks:
1. The referenced `store_as` exists in a prior step
2. The field path is valid in the producer's output schema
3. The type is compatible with the consumer's input schema

Typed annotations are required when type inference is ambiguous (union types, missing metadata, open schemas).

### 4.4 Gates and Conditions

Gates provide conditional control flow:

```yaml
gates:
  - when: ${checkpoint_out.created} == false
    action: stop
    message: "Cannot proceed without checkpoint"
```

Conditions enable step-level branching:

```yaml
- capability: act-plan
  condition: ${approval_out.approved} == true
  skip_if_false: true
```

### 4.5 Failure Modes and Recovery

Steps can declare expected failure scenarios:

```yaml
failure_modes:
  - condition: verdict == FAIL
    action: rollback
    recovery:
      goto_step: plan
      inject_context:
        failure_evidence: ${verify_out.failures}
      max_loops: 3
```

This creates a recovery loop: if verification fails, roll back and try re-planning with the failure evidence, up to 3 times.

### 4.6 Parallel Execution

Steps can execute concurrently:

```yaml
- capability: search
  parallel_group: gather

- capability: retrieve
  parallel_group: gather
  join: all_complete

- capability: integrate
  input_bindings:
    sources: [${search_out}, ${retrieve_out}]
```

---

## 5. World State and Trust

### 5.1 The World State Model

Agent systems maintain a model of the world. Our schema makes this model explicit:

**Observations**: Append-only events from sources
**Entities**: Current state of things in the world
**Relationships**: Connections between entities
**Lineage**: How the current state was derived

Every observation records:
- `timestamp`: When observed
- `source`: Where it came from
- `raw_payload`: Original data
- `canonical_payload`: Normalized form
- `evidence_anchors`: Links to source
- `provenance`: Traceability chain

### 5.2 Uncertainty Representation

We distinguish three types of uncertainty:

**Epistemic** (reducible): Uncertainty from incomplete knowledge
**Aleatoric** (irreducible): Uncertainty from inherent randomness
**Mixed**: Both types present

Each claim can carry:
- `confidence`: How certain are we (0.0-1.0)
- `uncertainty_type`: Which type
- `evidence_strength`: How strong is the evidence

### 5.3 The Trust Model

When sources disagree, we need principled conflict resolution:

**Source Authority**: Static ranking of source trustworthiness
**Time Decay**: Older information is less trusted (configurable half-life)
**Field Authority**: Sources may be authoritative for specific fields
**Confidence Weighting**: Self-reported confidence affects trust

Resolution strategies:
- `prefer_authoritative_sources`: Highest authority wins
- `prefer_recent`: Most recent wins
- `prefer_high_confidence`: Highest confidence wins
- `merge_with_uncertainty`: Keep both with explicit uncertainty
- `escalate_to_human`: Require human decision

### 5.4 Identity Resolution

Entity matching across sources requires:

**Hierarchical Namespaces**: `namespace:type:id`
**Alias Scoring**: Weighted confidence for potential matches
**Merge/Split Rules**: When to combine or divide records
**Hard Constraints**: Never merge incompatible types

---

## 6. Safety by Construction

### 6.1 The Safety Philosophy

Traditional safety approaches focus on what agents *shouldn't do*. We focus on making *unsafe actions structurally difficult*.

Instead of: "Don't modify files without permission"
We enforce: "Modification requires checkpoint, which requires file access"

### 6.2 Safety Invariants

**Invariant 1: Mutation requires checkpoint**
Any step with `mutation: true` must be preceded by a checkpoint. The validator rejects workflows that violate this.

**Invariant 2: Actions require plans**
The `act-plan` capability requires a `plan` from an earlier step. This ensures deliberate rather than impulsive action.

**Invariant 3: Claims require grounding**
Outputs should include evidence anchors. Ungrounded claims must explicitly state their inference method.

**Invariant 4: Merges are constrained**
Entity merges cannot violate hard constraints (conflicting IDs, incompatible types). Merges are recorded in lineage.

### 6.3 Enforcement Mechanism

Safety is enforced through:

**Static Validation**: The validator checks prerequisites before execution
**Gates**: Runtime checks that can halt unsafe execution
**Hooks**: Shell scripts that intercept and potentially block actions
**Audit**: All actions are recorded for accountability

---

## 7. The Validator

### 7.1 Validation Levels

The validator operates at four conformance levels:

**L1 (Basic)**: Capability existence and prerequisites
**L2 (Schema)**: $ref resolution and type inference
**L3 (Contracts)**: Binding types vs. consumer schemas
**L4 (Patches)**: Coercion registry and patch suggestions

### 7.2 Error Model

Errors are categorized:

| Category | Code Range | Description |
|----------|------------|-------------|
| Validation | V1xx | Static validation failures |
| Binding | B2xx | Binding resolution failures |
| Schema | S3xx | Schema validation failures |
| Runtime | R4xx | Runtime execution failures |
| Safety | F5xx | Safety constraint violations |

Each error includes:
- Code and name for programmatic handling
- Human-readable message
- Location (workflow, step, field)
- Suggestion for fixing

### 7.3 Patch Generation

For fixable errors, the validator can generate patches:

```json
{
  "operation": "add",
  "path": "/steps/5",
  "value": {
    "capability": "checkpoint",
    "purpose": "Save state before mutation",
    "store_as": "checkpoint_out"
  }
}
```

This enables semi-automated workflow repair.

---

## 8. Evaluation Approach

### 8.1 Validation Coverage

We evaluate the validator by:
- **Positive fixtures**: Valid workflows that must pass
- **Negative fixtures**: Invalid workflows that must fail with specific error codes
- **Patch fixtures**: Invalid workflows with expected patch suggestions

### 8.2 Trust Model Evaluation

To evaluate conflict resolution:
- Inject conflicting observations from sources with known authority
- Verify resolution matches expected outcome
- Measure time decay accuracy

### 8.3 Reproducibility

To evaluate determinism:
- Run replay against recorded observation streams
- Diff world state snapshots
- Verify identical inputs produce identical outputs

### 8.4 Safety Validation

To evaluate safety properties:
- Attempt to create workflows that violate invariants
- Verify validator rejects them
- Test gate blocking at runtime

---

## 9. Use Cases

### 9.1 Digital Twin Synchronization

A digital twin maintains a model of a real-world system. The `digital_twin_sync_loop` workflow:

1. Receives signals from sensors/APIs
2. Transforms to canonical format
3. Integrates with existing world state
4. Detects drift and anomalies
5. Plans corrective actions
6. Checkpoints before mutation
7. Executes and verifies
8. Records audit trail

### 9.2 Production Incident Triage

The `debug_code_change` workflow:

1. Inspects failing behavior
2. Searches for related patterns
3. Maps component dependencies
4. Models expected behavior
5. Critiques potential causes
6. Plans minimal fix
7. Checkpoints
8. Applies and verifies
9. Rolls back if needed

### 9.3 Capability Gap Analysis

The `capability_gap_analysis` workflow:

1. Inspects current skill coverage
2. Maps existing workflows to capabilities
3. Discovers hidden dependencies
4. Compares alternative architectures
5. Prioritizes missing capabilities
6. Generates implementation plan

---

## 10. Limitations and Future Work

### 10.1 Current Limitations

**Runtime Execution**: The standard focuses on validation and specification. Runtime execution is implementation-dependent.

**Semantic Validation**: We validate structural correctness, not semantic correctness. A syntactically valid workflow can still do the wrong thing.

**Prompt Injection**: The standard provides structure but not content filtering. Prompt injection defense requires additional runtime measures.

### 10.2 Future Directions

**Cryptographic Checkpoints**: Sign checkpoints for tamper detection
**Role-Based Authorization**: Restrict capability access by role
**Automated Anomaly Detection**: Learn normal patterns and flag deviations
**Multi-Party Approval**: Require multiple approvals for high-risk actions
**Cross-Agent Coordination**: Protocols for agent-to-agent workflows

---

## 11. Conclusion

AI agents are powerful but fragile. Most failures are not capability failures—the AI can do the task—but architectural failures in composition, state representation, and safety enforcement.

The Agent Capability Standard addresses these failures through:
- Explicit contracts between capabilities (typed I/O schemas)
- Grounded state with provenance (observations, not hallucinations)
- Trust-aware conflict resolution (principled, not arbitrary)
- Safety by construction (prerequisites, not prohibitions)

The result is a framework where reliability is structural. Workflows are validated before execution. Dependencies are explicit. Recovery is built in. Audit trails are automatic.

Production agents require architecture, not vibes. This standard provides that architecture.

---

## References

1. Brooks, R. A. (1986). A robust layered control system for a mobile robot. IEEE Journal on Robotics and Automation.

2. Bratman, M. (1987). Intention, Plans, and Practical Reason. Harvard University Press.

3. Rao, A. S., & Georgeff, M. P. (1995). BDI agents: From theory to practice. ICMAS.

4. PROV-O: The PROV Ontology. W3C Recommendation.

5. Semantic Versioning 2.0.0. https://semver.org/

6. JSON Schema. https://json-schema.org/

---

## Appendix A: Capability Count by Layer

| Layer | Count | Examples |
|-------|-------|----------|
| PERCEPTION | 4 | inspect, search, retrieve, receive |
| MODELING | 45 | detect-*, identify-*, estimate-*, world-state |
| REASONING | 20 | compare-*, plan, decide, critique |
| ACTION | 12 | act-plan, generate-*, transform, send |
| SAFETY | 7 | verify, checkpoint, rollback, audit, constrain, mitigate, improve |
| META | 6 | discover-*, prioritize |
| MEMORY | 2 | persist, recall |
| COORDINATION | 3 | delegate, synchronize, invoke-workflow |
| **Total** | **99** | |

## Appendix B: Workflow Catalog

| Workflow | Goal | Risk | Steps |
|----------|------|------|-------|
| `debug_code_change` | Fix bugs safely | High | 11 |
| `world_model_build` | Construct world model | Low | 11 |
| `capability_gap_analysis` | Find missing capabilities | Medium | 7 |
| `digital_twin_sync_loop` | Sync digital twin | High | 20 |
| `digital_twin_bootstrap` | Initialize twin | High | 2 (nested) |

---

*Agent Capability Standard v1.0.0*
*Copyright 2026 Synapti.ai*
*Licensed under Apache 2.0*
