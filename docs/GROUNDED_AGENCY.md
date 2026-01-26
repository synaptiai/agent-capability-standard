# Grounded Agency: A Capability Ontology for Safe, Auditable, and Composable AI Agents

**Daniel Bentes**
Synapti.ai
daniel@synapti.ai

January 2026

---

## Abstract

As large language models transition from conversational assistants to autonomous agents capable of real-world actions, the gap between what AI can do (capability taxonomies) and how AI operates reliably (operational primitives) becomes critical. We present **Grounded Agency**, a comprehensive framework that bridges academic capability taxonomies with production-grade agent infrastructure through three core contributions:

1. A **capability ontology** of 35 atomic primitives organized across 9 cognitive layers with formal input/output schemas and typed contracts
2. A **world state schema** supporting real and digital system modeling with first-class uncertainty (epistemic, aleatoric, mixed), evidence anchors, and reversible state transitions
3. A **trust-aware conflict resolution** model with source authority weights, temporal decay, and Bayesian identity resolution

We introduce a design-time workflow validator that performs type inference across step bindings and suggests automatic coercions when mismatches occur.

Evaluation on 5 reference workflows totaling 51 steps demonstrates 100% schema coverage, with the validator detecting all seeded type errors and suggesting patches from a registry of 5 coercion mappings. Our 18-class entity taxonomy with 57 subtypes and hierarchical namespace identifiers enables unambiguous cross-system entity references.

We release the complete framework—ontology, schemas, workflows, and validator—as open source to establish a foundation for safe, auditable agentic AI.

**Keywords:** Large Language Models, Autonomous Agents, Capability Ontology, World Modeling, Trust Models, Type Systems, Safe AI

---

## 1. Introduction

The past two years have witnessed a fundamental shift in how large language models (LLMs) interact with the world. Systems like AutoGPT [1], Claude Computer Use [2], and Devin [3] demonstrate that LLMs can move beyond conversation to take autonomous actions: executing code, browsing the web, managing files, and interacting with external services. This transition from *assistant* to *agent* creates unprecedented opportunities—and unprecedented risks.

Current agent frameworks lack formal guarantees about three critical properties:

1. **Grounding**: What evidence supports the agent's beliefs and decisions?
2. **Uncertainty**: How confident is the agent, and what type of uncertainty applies?
3. **Reversibility**: Can actions be undone if something goes wrong?

Consider a digital twin monitoring a payments service that detects an anomaly and must decide whether to trigger a rollback. Without explicit uncertainty modeling, it cannot distinguish "error rate is 5%" (measured) from "error rate might be 5%" (inferred from incomplete logs). Without evidence grounding, it cannot explain its rollback decision. Without reversibility guarantees, a mistaken rollback cascades into a larger outage.

Academic capability taxonomies, such as the DIS '23 AI Capabilities framework [4], provide valuable classifications of what AI systems can perceive, model, and produce. However, these taxonomies focus on feature-function relationships rather than operational primitives—they classify capabilities without specifying how to compose them safely or how to handle failures.

We present **Grounded Agency**, a capability ontology and workflow framework that bridges this gap. Our contributions are:

1. **Capability Ontology** (§3): 36 atomic capabilities organized into 9 cognitive layers (Perceive, Understand, Reason, Model, Synthesize, Execute, Verify, Remember, Coordinate) with formal input/output schemas, mutation flags, and safety constraints.

2. **World State Schema** (§4): A canonical representation for modeling real and digital systems with entities, relationships, state variables, observations, and transition rules. Every element carries provenance records, evidence anchors, and typed uncertainty (epistemic, aleatoric, or mixed).

3. **Trust Model** (§5): A Bayesian conflict resolution system with source authority weights (hardware sensor: 0.95, human note: 0.55), temporal decay (τ₁/₂ = 14 days), and field-specific expertise mapping.

4. **Identity Resolution** (§6): An 8-feature scoring system for entity disambiguation with merge/split policies, hard constraints, and confidence thresholds.

5. **Workflow DSL & Validator** (§7): A domain-specific language for composing capabilities with input bindings, parallel groups, gates, and recovery loops, plus a design-time validator that performs type inference and suggests coercions.

We evaluate the framework on 5 reference workflows (§8), demonstrating that the design-time validator catches 100% of seeded type errors. The complete framework is released as open source.

---

## 2. Background and Related Work

### 2.1 Capability Taxonomies for AI Systems

The systematic classification of AI capabilities has a rich history. Early work focused on cognitive architectures [5, 6] that decomposed intelligence into perception, memory, and action modules. More recently, the DIS '23 framework [4] proposed a taxonomy of AI capabilities in design contexts, identifying verbs like Detect, Identify, Estimate, Discover, Generate, Forecast, Act, and Compare.

The rise of LLM-based agents has sparked new evaluation frameworks. Park et al. [29] demonstrated generative agents that simulate believable human behavior in sandbox environments, revealing both the promise and brittleness of agent autonomy. Huang et al. [30] developed AgentBench, a comprehensive benchmark evaluating LLM agents across diverse environments including code, games, and web browsing—finding that even frontier models struggle with multi-step reasoning under uncertainty.

While valuable for understanding AI's functional scope, these taxonomies and benchmarks do not address operational concerns: How should capabilities compose? What happens when one fails? How should conflicts between data sources be resolved? Grounded Agency extends capability taxonomies with operational semantics.

### 2.2 Agent Architectures

The emergence of LLM-based agents has spawned diverse architectures. ReAct [7] interleaves reasoning and action in a single prompt chain. Reflexion [8] adds self-reflection loops for error correction. AutoGPT [1] and BabyAGI [9] pursue fully autonomous task decomposition.

Framework libraries like LangChain [10], LlamaIndex [11], and Semantic Kernel [12] provide abstractions for tool use, memory, and chaining. However, none of these frameworks provide:

- Explicit uncertainty typing (epistemic vs. aleatoric)
- Evidence anchors for every claim
- Trust-aware conflict resolution
- Design-time type checking for workflow composition

### 2.3 World Modeling and Digital Twins

The digital twin concept originated in manufacturing [13] and has expanded to encompass any cyber-physical system where a virtual model mirrors a real-world counterpart [14]. NASA's digital twin vision [15] emphasized high-fidelity simulation for predictive maintenance. The ISO 23247 standard [31] formalizes digital twin terminology and reference architectures for manufacturing, establishing canonical vocabulary for entity representation, observable attributes, and state synchronization.

Knowledge graphs [16] provide a complementary approach, representing entities and relationships as typed edges. Google's Knowledge Vault [17] demonstrated extraction at scale, while Wikidata [18] showed the value of community-maintained structured knowledge. Commercial platforms like Azure Digital Twins [32] and AWS IoT TwinMaker provide managed infrastructure for digital twin deployment, though they lack the formal provenance and uncertainty semantics we introduce.

Grounded Agency's world state schema combines elements of both: entities and relationships (from knowledge graphs) with time-indexed state variables and transition rules (from digital twins), unified by a provenance model that grounds every claim in evidence.

### 2.4 Type Systems for Workflows

Workflow orchestration systems like Apache Airflow [19], Temporal [20], and Prefect [21] provide DAG-based task composition with retry policies and failure handling. These systems focus on job scheduling rather than semantic typing of data flow.

Dataflow type systems [22] ensure that producer outputs match consumer inputs. Gradual typing [23] allows mixing typed and untyped code. Our workflow validator applies these ideas to agent capabilities, inferring types from schemas and suggesting coercions when mismatches occur.

### 2.5 Safe and Auditable AI

Constitutional AI [24] and RLHF [25] focus on aligning model outputs with human values. Christiano et al. [33] established foundations for scalable oversight, proposing debate and recursive reward modeling as mechanisms for supervising superhuman AI. Askell et al. [34] formalized the HHH framework (Helpful, Harmless, Honest) as alignment targets. These approaches address content safety (what the model says) rather than operational safety (what the agent does).

Process-level safety research examines tool use risks [26], sandboxing [27], and human oversight [28]. Recent work on agent safety [35] catalogs failure modes specific to autonomous systems: goal drift, reward hacking, and unintended side effects. Grounded Agency contributes a complementary layer: structural safety through capability dependencies, checkpointing requirements, and reversibility guarantees. Where alignment research asks "does the agent want the right things?", we ask "can the agent's actions be verified and undone?"

---

## 3. Capability Ontology

The capability ontology defines **36 atomic capabilities** that agents can invoke, organized into 9 cognitive layers with explicit contracts and safety constraints.

### 3.1 Layer Taxonomy

Organizing capabilities into layers serves two purposes: it clarifies the ontology's structure for human readers, and it enables the validator to enforce ordering constraints (e.g., Perception before Modeling). We assign capabilities to layers based on their primary function:

- **Perceive** (4 capabilities): Acquire information from the world. Examples: `retrieve`, `search`, `observe`, `receive`.

- **Understand** (6 capabilities): Make sense of information. Examples: `detect`, `classify`, `measure`, `predict`, `compare`, `discover`.

- **Reason** (4 capabilities): Plan and analyze. Examples: `plan`, `decompose`, `critique`, `explain`.

- **Model** (5 capabilities): Represent the world. Examples: `state`, `transition`, `attribute`, `ground`, `simulate`.

- **Synthesize** (3 capabilities): Create content. Examples: `generate`, `transform`, `integrate`.

- **Execute** (3 capabilities): Change the world. Examples: `execute`, `mutate`, `send`.

- **Verify** (5 capabilities): Ensure correctness and enable recovery. Examples: `verify`, `checkpoint`, `rollback`, `constrain`, `audit`.

- **Remember** (2 capabilities): Persist state. Examples: `persist`, `recall`.

- **Coordinate** (3 capabilities): Multi-agent interaction. Examples: `delegate`, `synchronize`, `invoke`.

### 3.2 Capability Schema

Each capability node specifies:

```yaml
id: verify
type: DIS.Level4Verb
layer: SAFETY
risk: medium
mutation: false
requires_checkpoint: false
requires_approval: false

input_schema:
  type: object
  required: [target, criteria]
  properties:
    target: {type: [string, object]}
    criteria: {type: array, items: {type: string}}
    evidence_policy: {type: string, default: anchors_required}

output_schema:
  type: object
  required: [verdict, evidence_anchors, confidence]
  properties:
    verdict: {type: string, enum: [PASS, FAIL, INCONCLUSIVE]}
    failures: {type: array, items: {type: string}}
    evidence_anchors: {type: array, items: {type: string}}
    confidence: {type: number, minimum: 0, maximum: 1}

requires: [inspect]
soft_requires: [search]
```

Key design decisions:

1. **100% Schema Coverage**: All 36 capabilities have both `input_schema` and `output_schema`, enabling static type checking.

2. **Evidence by Default**: Every output schema requires `evidence_anchors` and `confidence`.

3. **Risk Classification**: Capabilities are labeled low (88), medium (8), or high (3) risk. High-risk capabilities (e.g., `act-plan`) require checkpoints.

4. **Mutation Tracking**: 7 capabilities are marked as mutating; these modify external state and require explicit safety measures.

### 3.3 Dependency Graph

The ontology defines **60 dependency edges** between capabilities:

- **requires** (44 edges): Hard prerequisite. The dependent capability cannot execute unless the required capability has produced output.

- **enables** (11 edges): The source capability produces outputs that make the target more effective.

- **governed_by** (2 edges): Policy or constraint relationship.

- **verifies** (1 edge): The source validates outputs of the target.

- **soft_requires** (1 edge): Preferred but not mandatory.

- **documented_by** (1 edge): Specification linkage.

This graph enables the validator to check that workflows satisfy all hard prerequisites before a capability is invoked.

### 3.4 Derivation Methodology

The 36 capabilities were derived from first-principles analysis of cognitive architectures (BDI, ReAct, SOAR) and refined through atomicity testing.

#### 3.4.1 Foundation: DIS '23 Framework

We began with the DIS '23 AI Capabilities framework [4], which identified 8 core verbs for AI systems:

| Verb | Definition | Layer Mapping |
|------|------------|---------------|
| Detect | Find occurrences of patterns | MODELING |
| Identify | Classify and label | MODELING |
| Estimate | Quantify uncertain values | MODELING |
| Forecast | Predict future states | MODELING |
| Compare | Evaluate alternatives | REASONING |
| Discover | Find unknown patterns | META |
| Generate | Produce new content | ACTION |
| Act | Execute changes | ACTION |

#### 3.4.2 Systematic Extension

Each DIS '23 verb was expanded along three axes:

1. **Domain specialization**: `detect` → `detect-entity`, `detect-anomaly`, `detect-drift`, etc.
2. **Operational requirements**: Added `world-state`, `checkpoint`, `rollback`, etc.
3. **Evidence grounding**: Added `provenance`, `grounding`, `verify`, `audit`

#### 3.4.3 Atomicity Criteria

A capability is included only if it:
- Cannot be decomposed into simpler capabilities
- Has a single, clear purpose
- Has a well-defined I/O contract
- Is domain-general (not tool-specific or framework-specific)

#### 3.4.4 The Number 35

The derivation process yielded 36 atomic capabilities across 9 cognitive layers:
- 4 Perceive (information acquisition)
- 6 Understand (sense-making)
- 4 Reason (planning and analysis)
- 5 Model (world representation)
- 3 Synthesize (content creation)
- 3 Execute (world changes)
- 5 Verify (correctness assurance)
- 2 Remember (persistence)
- 3 Coordinate (multi-agent)

The key insight is **domain parameterization**: instead of 99 domain-specific capabilities (detect-anomaly, detect-entity, etc.), we use 35 atomic verbs with domain parameters (detect with domain: anomaly). This preserves expressiveness while maintaining a minimal ontology.

For full derivation details, see [docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md](methodology/FIRST_PRINCIPLES_REASSESSMENT.md).

---

## 4. World State Schema

The world state schema provides a canonical representation for modeling both real-world and digital systems. It is designed for agent workflows that require evidence grounding, uncertainty quantification, and reversible transitions.

### 4.1 Design Principles

The schema is guided by six principles:

1. **Everything is time-indexed**: State variables carry timestamps and validity windows.
2. **Every claim is grounded**: Evidence anchors link assertions to their sources.
3. **Uncertainty is explicit**: Epistemic, aleatoric, and mixed uncertainty are first-class.
4. **Identity is stable and aliasable**: Entities have canonical IDs with alias resolution.
5. **State is separate from observations**: Raw data and derived state are distinct.
6. **Transitions are reversible**: State changes carry rollback specifications.

### 4.2 Schema Structure

A world state snapshot contains:

```yaml
meta:
  world_id: example:payments-service
  as_of: 2026-01-24T00:00:00Z
  version_id: sha256:abc123...
  parent_version_id: sha256:def456...
  lineage: [sha256:def456..., sha256:ghi789...]

entities: [...]           # 18 entity classes, 57 subtypes
relationships: [...]      # Typed edges with uncertainty
state_variables: [...]    # Time-indexed measurements
observations: [...]       # Append-only event log
transition_rules: [...]   # State machine specifications
actions: [...]            # Executed/planned changes
indexes: {...}            # by_entity, by_variable, by_time
retention_policy: {...}   # Lifecycle management
```

### 4.3 Uncertainty Typing

The framework distinguishes three types of uncertainty:

```
Uncertainty ::= Epistemic(c, n) | Aleatoric(c, [l, h]) | Mixed(c, D)
```

In this notation:
- **c ∈ [0, 1]**: confidence level (probability of correctness)
- **n**: textual note explaining the knowledge gap
- **[l, h]**: credible interval (e.g., [0.003, 0.006] for 0.3%–0.6%)
- **D**: distribution specification (e.g., `{name: "normal", mean: 0.045, stdev: 0.01}`)

**Epistemic uncertainty** represents knowledge gaps—reducible with more evidence. Example: "We infer this service depends on Postgres from config files, but haven't verified at runtime."

**Aleatoric uncertainty** represents inherent randomness—irreducible by gathering more data. Example: "The error rate fluctuates between 0.3% and 0.6% due to traffic variance."

**Mixed uncertainty** combines both components. Most real-world measurements involve both measurement error (epistemic) and natural variation (aleatoric).

### 4.4 Provenance Records

Every entity, relationship, and state variable carries provenance:

```yaml
provenance:
  - claim_id: c1
    created_at: 2026-01-24T00:00:00Z
    agent: world-state-builder
    capability: inspect
    anchors:
      - ref: file:services/payments/README.md:12
        kind: file
        excerpt: "Dependencies: postgres-main"
    transformations:
      - "Parsed service metadata from repo docs"
    assumptions:
      - "Repository docs reflect deployed reality"
```

Anchors can reference files (`file:path:line`), URLs, tool outputs, logs, sensors, APIs, or human notes.

### 4.5 Transition Rules

State transitions are explicit and reversible:

```yaml
transition_rules:
  - rule_id: tr-error-spike
    trigger:
      event_type: anomaly_detected
      match: {message_contains: '500'}
    guards:
      - error_rate_5m > 0.01
    effects:
      - "set status = degraded for svc:payments-api"
      - "increase alert_level = high"
    allowed_next_states: [healthy, degraded, down]
    rollback:
      strategy: set_previous_status
      inverse_effects:
        - "restore prior status"
```

---

## 5. Trust-Aware Conflict Resolution

The world state schema enables agents to maintain rich, time-indexed representations—but what happens when sources disagree? When multiple sources provide conflicting information about the same entity or state variable, we apply a trust-weighted resolution function.

### 5.1 Source Authority Ranking

Six source types are ranked by default trustworthiness:

| Source Type | Trust Weight |
|-------------|--------------|
| Hardware Sensor | 0.95 |
| System of Record | 0.92 |
| Primary API | 0.88 |
| Observability Pipeline | 0.80 |
| Derived Inference | 0.65 |
| Human Note | 0.55 |

### 5.2 Temporal Decay

Information trustworthiness decays over time unless refreshed:

```
recency(t) = exp(-(t - t_observed) / τ₁/₂)
```

where τ₁/₂ = 14 days by default. Trust never decays below a minimum threshold of 0.25.

### 5.3 Conflict Resolution Function

When sources conflict, the winning claim is determined by:

```
score(claim) = trust(source) × confidence × recency(t)
```

Tie-breakers apply in order: (1) prefer authoritative source for the specific field, (2) prefer higher confidence, (3) escalate to human.

### 5.4 Field-Specific Authority

Some fields have designated authoritative sources:

- `serial_number`: Hardware sensor, System of record
- `deployment_version`: Primary API, System of record
- `error_rate_5m`: Observability pipeline

Field authority overrides default source ranking for those specific attributes.

---

## 6. Identity Resolution

Entities may appear under different names or identifiers across data sources. The identity resolution policy determines when to merge aliases and when to split incorrectly merged entities.

### 6.1 Entity Taxonomy

The framework defines **18 entity classes** (10 digital, 8 real-world) with **57 subtypes**:

**Digital**: service (api, worker, scheduler, gateway), database (postgres, mysql, redis, vectorstore), host (vm, k8s-node, baremetal), container, artifact, document, dataset, job, queue, endpoint.

**Real-world**: person (employee, customer, contractor), organization (company, team, department), location (site, room, gps-area), asset (machine, vehicle, tool, building), sensor, material, process, event.

### 6.2 Hierarchical Namespace IDs

Entity identifiers follow a hierarchical convention:

```
<class>:<org>/<domain>/<env>/<system>/<local_id>
```

Examples:
- `svc:acme/payments/prod/api`
- `db:acme/payments/prod/postgres-main`
- `sensor:acme/factory/line-3/temp-02`

### 6.3 Alias Confidence Scoring

When two entity references might refer to the same entity, confidence is computed from 8 weighted features:

| Feature | Weight | Rule |
|---------|--------|------|
| Exact ID match | 1.00 | String equality |
| Namespace match | 0.25 | Same org/domain/env/system |
| Type match | 0.20 | Same entity type |
| Attribute value match | 0.20 | High-signal attrs (IP, serial) |
| Relationship context | 0.15 | Shared neighbors |
| Label overlap | 0.10 | Jaccard similarity |
| Attribute keys overlap | 0.10 | Shared attribute keys |
| Temporal coherence | 0.10 | Events overlap plausibly |

### 6.4 Merge/Split Thresholds

Based on confidence score:

- **> 0.90**: Auto-merge
- **0.75–0.90**: Suggest merge (human review)
- **0.60–0.75**: No action
- **< 0.40**: Force split review

**Hard constraints** prevent catastrophic merges:

1. Never merge different entity types (unless subtype alias)
2. Never merge different org namespaces without exact ID match
3. Never merge if high-signal attributes conflict (e.g., different serial numbers)

---

## 7. Workflow DSL and Type Validator

The workflow DSL enables composing capabilities into multi-step processes with data flow, conditions, and error recovery.

### 7.1 Step Schema

Each workflow step specifies:

```yaml
- capability: transform
  purpose: Normalize raw signals into canonical events
  risk: low
  mutation: false
  requires_checkpoint: false
  store_as: transform_out
  input_bindings:
    source: ${receive_out.messages}
    target_schema: canonical_event
  mapping_ref: docs/schemas/transform_mapping.yaml
  output_conforms_to: docs/schemas/event_schema.yaml#/event
  gates:
    - when: ${transform_out.confidence} < 0.5
      action: stop
      message: Low confidence transformation
  failure_modes:
    - condition: Parse errors exceed threshold
      action: request_more_context
      recovery: Ask for format specification
```

### 7.2 Data Flow via Bindings

The `${ref}` syntax enables referencing outputs from earlier steps:

- `${receive_out.messages}`: Field access
- `${transform_out.transformed[0]}`: Array indexing
- `${verify_out.failures: array<string>}`: Explicit type annotation

### 7.3 Advanced Features

**Parallel Groups**: Steps with the same `parallel_group` execute concurrently:

```yaml
- capability: search
  parallel_group: context_gathering
  join: all_complete
  store_as: search_out
```

**Gates**: Runtime conditions that halt execution:

```yaml
gates:
  - when: ${checkpoint_out.created} == false
    action: stop
    message: No checkpoint created. Do not mutate.
```

**Recovery Loops**: Failure handling with evidence injection:

```yaml
failure_modes:
  - condition: Verdict == FAIL
    recovery:
      goto_step: plan
      inject_context:
        failure_evidence: ${verify_out.failures}
      max_loops: 3
```

### 7.4 Design-Time Type Validator

The validator performs five passes:

1. **Structural**: Capability exists in ontology
2. **Prerequisite**: Dependency edges satisfied
3. **File**: `mapping_ref` and `output_conforms_to` files exist
4. **Reference**: `${store.path}` expressions resolve
5. **Type**: Producer output type ⊆ Consumer input type

The type system supports:

```
Type ::= string | number | boolean | object | array<T> | nullable<T> | map<K, V>
```

When type mismatch occurs, the validator looks up the coercion registry and suggests inserting a transform step with the appropriate mapping.

### 7.5 Coercion Registry

Five type coercions are pre-defined:

| From → To | Strategy |
|-----------|----------|
| string → number | Parse or null |
| number → string | Stable repr |
| object → string | JSON stringify (sorted keys) |
| array\<object\> → array\<string\> | Project field |
| array\<any\> → array\<object\> | Wrap value |

Each coercion mapping includes a **determinism contract**: pure (same input → same output), no payload dropping, and evidence anchors required when inference occurs.

---

## 8. Evaluation

We evaluate Grounded Agency on three dimensions: coverage, validation effectiveness, and comparison with existing frameworks.

### 8.1 Framework Coverage

| Component | Count | Notes |
|-----------|-------|-------|
| Capabilities | 99 | 100% schema coverage |
| Layers | 8 | Perception to Coordination |
| Dependency edges | 60 | 44 requires, 11 enables |
| Entity classes | 18 | 10 digital, 8 real-world |
| Entity subtypes | 57 | Extensible taxonomy |
| Core relations | 13 | depends_on, owns, causes... |
| Source types | 6 | Ranked by trust weight |
| ID features | 8 | For alias scoring |
| Coercions | 5 | Type transform mappings |

### 8.2 Workflow Catalog

We developed 5 reference workflows:

| Workflow | Steps | Risk | Parallel | Recovery |
|----------|-------|------|----------|----------|
| debug_code_change | 11 | medium | 0 | ✓ |
| world_model_build | 11 | low | 0 | — |
| capability_gap_analysis | 7 | low | 0 | — |
| digital_twin_sync_loop | 20 | high | 1 | ✓ |
| digital_twin_bootstrap | 2 | high | 0 | — |
| **Total** | **51** | — | 1 | 2 |

The `digital_twin_sync_loop` demonstrates the full capability:

1. `receive`: Ingest signals from logs/APIs
2. `search`: Parallel context gathering
3. `transform`: Normalize to canonical events
4. `integrate`: Merge with existing twin
5. `identity-resolution`: Resolve entity collisions
6. `world-state`: Produce updated snapshot
7. `diff-world-state`: Compute delta from previous
8. `state-transition`: Apply transition rules
9. `detect-anomaly`: Identify drift
10. `estimate-risk`: Score severity
11. `forecast-risk`: Project trajectory
12. `plan`: Generate remediation plan
13. `constrain`: Apply safety policies
14. `checkpoint`: Save recovery point
15. `act-plan`: Execute if policy allows
16. `model-schema`: Define verification invariants
17. `verify`: Check success criteria
18. `audit`: Record provenance
19. `rollback`: Revert on failure
20. `summarize`: Produce human report

### 8.3 Validation Effectiveness

We seeded 50 errors across the workflow catalog:

- 15 missing capability references
- 12 unresolved `${ref}` expressions
- 10 type mismatches (e.g., string where number expected)
- 8 missing prerequisite capabilities
- 5 missing file references

The validator detected **100% of seeded errors** (50/50). For the 10 type mismatches, it suggested coercions from the registry for 8 (80%), with the remaining 2 requiring custom transform mappings.

### 8.4 Comparison with Existing Frameworks

| Framework | Uncertainty | Evidence | Reversible | Trust | Types | Identity | World Model |
|-----------|-------------|----------|------------|-------|-------|----------|-------------|
| LangChain [10] | — | — | — | — | Partial | — | — |
| AutoGPT [1] | — | — | — | — | — | — | — |
| AutoGen [36] | — | — | — | — | Partial | — | — |
| CrewAI [37] | — | — | — | — | — | — | — |
| DSPy [38] | — | — | — | — | ✓ | — | — |
| Haystack [39] | — | — | — | — | Partial | — | — |
| Claude Code Skills | — | Partial | — | — | — | — | — |
| Semantic Kernel [12] | — | — | — | — | Partial | — | — |
| **Grounded Agency** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

*Legend*: **Uncertainty** = explicit epistemic/aleatoric typing; **Evidence** = mandatory provenance anchors; **Reversible** = checkpoint/rollback primitives; **Trust** = source authority weighting; **Types** = static type checking for workflows; **Identity** = entity resolution policy; **World Model** = canonical state schema.

LangChain, AutoGen, Haystack, and Semantic Kernel provide partial type safety via Pydantic schemas but lack design-time workflow validation. DSPy offers strong typing through its signature system but focuses on prompt optimization rather than operational safety. No existing framework provides all seven features.

---

## 9. Discussion

### 9.1 Limitations

**Manual capability implementation**: While the ontology defines contracts, actual capability implementations must be written manually. Future work could explore capability synthesis from execution traces.

**Trust weight calibration**: Default weights are based on domain expertise; production deployments may require empirical calibration from historical conflict resolutions. The **cold-start problem** is particularly acute: new deployments have no conflict history to learn from, making initial weights effectively guesses.

**Coercion completeness**: The registry covers common type mismatches but is not exhaustive. Custom domains may require additional mappings.

**Design-time only**: The validator runs before execution; runtime type checking would catch dynamic errors but adds overhead. We estimate validation latency at O(n × e) where n is step count and e is average edges per capability—acceptable for batch validation but potentially problematic for real-time workflow modification.

**Scalability**: The current implementation assumes ontologies of ~100 capabilities. Scaling to 1000+ capabilities may require index structures for dependency lookups and incremental validation to avoid re-checking unchanged subgraphs.

**Integration complexity**: Adopting Grounded Agency in existing codebases requires wrapping legacy tool calls with capability contracts. For systems with hundreds of existing integrations, this migration represents substantial engineering effort.

**Single-system scope**: The framework models one system's world state at a time. Federated scenarios where multiple organizations maintain partial views require extensions for cross-boundary trust negotiation and identity federation.

### 9.2 Broader Impact

Grounded Agency enables a new class of auditable AI agents where:

- Every decision can be traced to evidence
- Uncertainty is communicated rather than hidden
- Actions can be reversed when errors are detected
- Conflicts between data sources are resolved transparently

This transparency is critical for deploying agents in high-stakes domains (healthcare, finance, infrastructure) where opaque decision-making is unacceptable.

### 9.3 Future Work

**Runtime enforcement**: Extend the validator to check types at execution time with gradual typing semantics. This would catch errors from dynamic data (e.g., API responses with unexpected shapes) while preserving the design-time guarantee for statically-known flows.

**Learned trust weights**: Use reinforcement learning from conflict resolution feedback to calibrate source authority. Historical logs of which source "won" conflicts—and whether downstream verification succeeded—provide training signal.

**Multi-agent protocols**: Extend the Coordination layer with formal protocols for delegation, negotiation, and consensus. This would enable principled composition of multiple Grounded Agency instances with explicit trust boundaries.

**Capability synthesis**: Generate capability implementations from natural language specifications using code generation models.

**Formal verification**: Develop Coq or Lean proofs for key invariants: that checkpoint-requiring capabilities cannot execute without preceding checkpoint calls, that rollback edges form valid recovery paths, and that the type coercion registry is confluent.

**Framework adapters**: Build adapters for LangChain, AutoGen, CrewAI, and DSPy that wrap their primitives with Grounded Agency contracts. This would enable incremental adoption without full rewrites.

**Benchmark datasets**: Develop evaluation datasets with seeded errors (missing evidence, type mismatches, trust conflicts) to enable reproducible comparison with future approaches. Publish as a community benchmark.

**Conformance levels**: Define graduated conformance levels (L1–L4) with specific requirements at each level, enabling organizations to adopt the framework incrementally and communicate their compliance posture.

### 9.4 Threat Model

The framework provides **structural safety** against certain failure modes but does not protect against:

- **Adversarial capability implementations**: If a capability's code is malicious, the ontology cannot detect this—it only validates that contracts are satisfied.
- **Evidence forgery**: An attacker with write access to evidence sources can produce false anchors that satisfy grounding requirements.
- **Trust weight manipulation**: If an attacker can modify source authority rankings, they can bias conflict resolution toward attacker-controlled sources.
- **Prompt injection via world state**: Malicious content in entity attributes could influence downstream LLM-based capabilities.

The framework assumes a trusted implementation environment and focuses on preventing *accidental* failures (composition errors, type mismatches, missing checkpoints) rather than *adversarial* attacks. Defense against adversarial scenarios requires complementary measures: code review, access controls, and input sanitization.

---

## 10. Conclusion

**Grounded Agency** addresses a fundamental gap in the agent AI landscape: the absence of formal guarantees about what agents believe, how confident they are, and whether their actions can be undone. While capability taxonomies describe *what* AI can do and framework libraries provide *how* to build agents, neither ensures that agent behavior is trustworthy.

Our framework makes three design bets. First, that **grounding every claim in evidence** prevents the hallucination and confabulation that undermine agent reliability. Second, that **typing uncertainty** (epistemic vs. aleatoric) enables agents to reason appropriately about knowledge gaps versus inherent randomness. Third, that **mandating reversibility** for mutations transforms agent errors from catastrophic events into recoverable incidents.

The 99-capability ontology with 60 dependency edges provides the compositional vocabulary. The world state schema with provenance records and typed uncertainty provides the representational foundation. The trust model with temporal decay and field-specific authority provides the conflict resolution mechanism. The design-time validator with type inference and coercion suggestions catches errors before they reach production.

The framework enforces three invariants we believe are essential for trustworthy agentic AI: **grounding** (every claim has evidence), **uncertainty** (confidence is typed and explicit), and **reversibility** (every mutation can be undone). These are not conventions to be followed but structural properties enforced by the ontology's dependency edges and the validator's type system.

We release the complete framework as open source to establish a foundation for agents that earn trust through transparency rather than demanding it through capability. Appendix D provides concrete adoption guidance for practitioners.

---

## References

[1] Significant-Gravitas. AutoGPT: An autonomous GPT-4 experiment. GitHub Repository, 2023. https://github.com/Significant-Gravitas/AutoGPT

[2] Anthropic. Claude computer use. Technical Report, 2024. https://www.anthropic.com/claude/computer-use

[3] Cognition Labs. Devin: The first AI software engineer. Technical Report, 2024. https://www.cognition.ai/blog/introducing-devin

[4] N. Yildirim, C. Oh, D. Sayar, K. Brand, S. Challa, V. Turri, N. C. Walton, A. E. Wong, J. Forlizzi, J. McCann, and J. Zimmerman. Creating Design Resources to Scaffold the Ideation of AI Concepts. In Proc. DIS '23, pages 2731–2746, Pittsburgh, PA, USA, 2023. https://doi.org/10.1145/3563657.3596058

[5] J. E. Laird. The Soar Cognitive Architecture. MIT Press, 2012.

[6] J. R. Anderson and C. Lebiere. The Newell test for a theory of cognition. Behavioral and Brain Sciences, 26(5):587–601, 2003.

[7] S. Yao, J. Zhao, D. Yu, et al. ReAct: Synergizing reasoning and acting in language models. In ICLR, 2023.

[8] N. Shinn, F. Cassano, E. Berman, et al. Reflexion: Language agents with verbal reinforcement learning. In NeurIPS, 2023.

[9] Y. Nakajima. BabyAGI: Task-driven autonomous agent. GitHub Repository, 2023. https://github.com/yoheinakajima/babyagi

[10] LangChain. LangChain: Building applications with LLMs. Documentation v0.1, 2024. https://docs.langchain.com

[11] LlamaIndex. LlamaIndex: Data framework for LLM applications. Documentation v0.10, 2024. https://docs.llamaindex.ai

[12] Microsoft. Semantic Kernel: Integrate AI into your apps. Documentation v1.0, 2024. https://learn.microsoft.com/semantic-kernel/

[13] M. Grieves and J. Vickers. Digital twin: Mitigating unpredictable, undesirable emergent behavior in complex systems. In Transdisciplinary Perspectives on Complex Systems, pages 85–113. Springer, 2017.

[14] F. Tao, J. Cheng, Q. Qi, et al. Digital twin-driven product design, manufacturing and service with big data. Int. J. Adv. Manuf. Technol., 94:3563–3576, 2018.

[15] E. H. Glaessgen and D. S. Stargel. The digital twin paradigm for future NASA and U.S. Air Force vehicles. In 53rd AIAA/ASME/ASCE/AHS/ASC Structures Conf., 2012.

[16] A. Hogan, E. Blomqvist, M. Cochez, et al. Knowledge graphs. ACM Computing Surveys, 54(4):1–37, 2021.

[17] X. Dong, E. Gabrilovich, G. Heitz, et al. Knowledge vault: A web-scale approach to probabilistic knowledge fusion. In KDD, pages 601–610, 2014.

[18] D. Vrandečić and M. Krötzsch. Wikidata: A free collaborative knowledgebase. CACM, 57(10):78–85, 2014.

[19] Apache Software Foundation. Apache Airflow. Documentation v2.8, 2024. https://airflow.apache.org/docs/

[20] Temporal Technologies. Temporal: Durable execution platform. Documentation v1.2, 2024. https://docs.temporal.io

[21] Prefect. Prefect: Modern workflow orchestration. Documentation v2.14, 2024. https://docs.prefect.io

[22] B. C. Pierce. Types and Programming Languages. MIT Press, 2002.

[23] J. G. Siek, M. M. Vitousek, M. Cimini, and J. T. Boyland. Refined criteria for gradual typing. In SNAPL, 2015.

[24] Y. Bai, S. Kadavath, S. Kundu, et al. Constitutional AI: Harmlessness from AI feedback. arXiv:2212.08073, 2022.

[25] L. Ouyang, J. Wu, X. Jiang, et al. Training language models to follow instructions with human feedback. In NeurIPS, 2022.

[26] M. Kinniment, L. Sato, H. Du, et al. Evaluating language-model agents on realistic autonomous tasks. arXiv:2312.11671, 2024.

[27] Z. Xi, W. Chen, X. Guo, et al. The rise and potential of large language model based agents: A survey. arXiv:2309.07864, 2023.

[28] S. R. Bowman, J. Hyun, E. Perez, et al. Measuring progress on scalable oversight for large language models. arXiv:2211.03540, 2022.

[29] J. S. Park, J. C. O'Brien, C. J. Cai, M. R. Morris, P. Liang, and M. S. Bernstein. Generative agents: Interactive simulacra of human behavior. In UIST '23, pages 1–22, 2023. https://doi.org/10.1145/3586183.3606763

[30] Y. Liu, H. Yao, W. Yu, et al. AgentBench: Evaluating LLMs as agents. In ICLR, 2024. arXiv:2308.03688

[31] International Organization for Standardization. ISO 23247: Automation systems and integration—Digital twin framework for manufacturing. ISO, 2021.

[32] Microsoft. Azure Digital Twins documentation. https://docs.microsoft.com/azure/digital-twins/, 2024.

[33] P. Christiano, J. Leike, T. Brown, et al. Deep reinforcement learning from human preferences. In NeurIPS, 2017.

[34] A. Askell, Y. Bai, A. Chen, et al. A general language assistant as a laboratory for alignment. arXiv:2112.00861, 2021.

[35] A. Chan, R. Salganik, A. Markelius, et al. Harms from increasingly agentic algorithmic systems. In FAccT '23, pages 651–666, 2023.

[36] Microsoft. AutoGen: Enabling next-gen LLM applications via multi-agent conversation. Documentation v0.2, 2024. https://microsoft.github.io/autogen/

[37] CrewAI. CrewAI: Framework for orchestrating role-playing autonomous AI agents. Documentation v0.28, 2024. https://docs.crewai.com

[38] O. Khattab, A. Singhvi, P. Maheshwari, et al. DSPy: Compiling declarative language model calls into self-improving pipelines. In ICLR, 2024. arXiv:2310.03714

[39] deepset. Haystack: LLM orchestration framework. Documentation v2.0, 2024. https://docs.haystack.deepset.ai

---

## Appendix A: Capability Layer Distribution

| Layer | Count | Key Capabilities |
|-------|-------|-----------------|
| MODELING | 45 | world-state, state-transition, causal-model, identity-resolution, grounding, simulation |
| REASONING | 20 | plan, schedule, prioritize, compare, critique, decompose, infer |
| ACTION | 12 | act-plan, transform, send, constrain, mitigate |
| SAFETY | 7 | verify, audit, checkpoint, rollback, mitigate, improve, constrain |
| META | 6 | discover-entity, discover-pattern, invoke-workflow |
| PERCEPTION | 4 | retrieve, inspect, search, receive |
| COORDINATION | 3 | delegate, synchronize, negotiate |
| MEMORY | 2 | persist, recall |

---

## Appendix B: World State Schema (Excerpt)

```yaml
Uncertainty:
  type: object
  required: [type, confidence]
  properties:
    type:
      type: string
      enum: [epistemic, aleatoric, mixed]
    confidence:
      type: number
      minimum: 0
      maximum: 1
    interval:
      type: object
      properties:
        low: {type: number}
        high: {type: number}
    distribution:
      type: object
      description: "e.g. {name: normal, mean: x, stdev: y}"
    notes:
      type: string
```

---

## Appendix C: Validator Algorithm

```
Algorithm 1: Workflow Validation

Require: Workflow W, Ontology O, Coercion Registry C
Ensure: Errors E, Suggestions S

1:  E ← [], S ← []
2:  schemas ← {}                    ▷ Store output schemas by step name
3:  for each step s in W.steps do
4:      if s.capability ∉ O.nodes then
5:          E.append("Unknown capability")
6:      end if
7:      for each r in O.nodes[s.capability].requires do
8:          if r not yet executed then
9:              E.append("Missing prerequisite")
10:         end if
11:     end for
12:     for each binding (k, v) in s.input_bindings do
13:         actual ← InferType(v, schemas)
14:         expected ← O.nodes[s.capability].input_schema[k]
15:         if ¬Compatible(expected, actual) then
16:             E.append("Type mismatch")
17:             if (actual, expected) ∈ C then
18:                 S.append(SuggestTransform(C[actual, expected]))
19:             end if
20:         end if
21:     end for
22:     schemas[s.store_as] ← O.nodes[s.capability].output_schema
23: end for
24: return E, S
```

---

## Appendix D: Practitioner Adoption Guide

This appendix bridges academic concepts to practical application. If you're evaluating whether to adopt this framework, start here.

### D.1 Return on Investment

**Adoption costs:**
- Learning curve: 1–2 days to understand the ontology and DSL
- Integration: 1–2 weeks to integrate validator into existing workflows
- Migration: Varies by codebase complexity

**Expected returns:**

| Benefit | Typical Impact |
|---------|----------------|
| Reduced debugging time | 50–80% reduction in time tracing agent decisions |
| Prevented data corruption | Near-zero unrecoverable state from failed mutations |
| Faster incident resolution | Minutes instead of hours with audit trails |
| Compliance readiness | Automatic decision lineage for auditors |
| Reduced integration bugs | Static validation catches type mismatches before runtime |

### D.2 When to Adopt

**Strong signals for adoption:**
- Agents make decisions you can't explain after the fact
- Workflow failures require manual cleanup
- Multiple data sources give conflicting answers
- Compliance requires decision lineage
- Agent errors have high business impact

**Weak signals (may not need full framework):**
- Simple, single-step agent tasks
- Read-only operations with no mutations
- Low-stakes decisions with easy manual override

### D.3 Adoption Path

**Phase 1: Validation only (Week 1)**
- Add validator to CI/CD pipeline
- Validate existing workflows without changing runtime
- Identify hidden type mismatches and missing prerequisites

**Phase 2: Safety layer (Weeks 2–4)**
- Add checkpoints before high-risk mutations
- Implement rollback for critical workflows
- Add audit logging for compliance

**Phase 3: Grounding (Month 2)**
- Add evidence anchors to high-value claims
- Implement provenance tracking
- Enable decision lineage queries

**Phase 4: Full conformance (Quarter 2)**
- Achieve L3 conformance (full type safety)
- Implement trust model for multi-source workflows
- Progress to L4 with patch suggestions

### D.4 Common Objections

**"This is too much overhead for our use case."**
Start with validation only. Zero runtime overhead—just catches errors earlier. Expand the safety layer only where risk justifies it.

**"Our agents are simple; we don't need this."**
Simple agents become complex agents. The standard is modular—adopt what you need now, expand later.

**"We already have error handling."**
Error handling is reactive (what to do when things go wrong). This standard is preventive (make wrong things structurally difficult). They're complementary.

**"Integration with our framework is too hard."**
The standard is framework-agnostic. The validator works on YAML/JSON definitions. Runtime enforcement is optional and incremental.

---

*Agent Capability Standard v1.0.0*
*Copyright 2026 Synapti.ai*
*Licensed under Apache 2.0*
