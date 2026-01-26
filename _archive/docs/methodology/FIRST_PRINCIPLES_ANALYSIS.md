# First-Principles Ontology Analysis

**Document Status**: Critical Analysis
**Last Updated**: 2026-01-26
**Version**: 1.0.0
**Purpose**: Rigorous examination of every capability to determine the correct atomic set

---

## Executive Summary

This document conducts a first-principles analysis of the capability ontology to answer:

1. **What is truly atomic?** (Cannot be decomposed)
2. **What is redundant?** (Semantically equivalent to another)
3. **What is a composition?** (Should be a workflow pattern, not a capability)
4. **What is the right organizing principle?** (DIS verbs vs. Layers)

**Key Finding**: The current 99 capabilities contain significant redundancy and composition. A rigorous first-principles derivation yields a smaller, cleaner set.

---

## 1. Current Ontology Structure

### 1.1 The Two Taxonomic Dimensions

The current ontology conflates two different organizational principles:

| Dimension | Principle | Example |
|-----------|-----------|---------|
| **DIS Verbs** (8) | Semantic operation type | detect, identify, estimate, forecast, compare, discover, generate, act |
| **Layers** (8) | Architectural position | PERCEPTION, MODELING, REASONING, ACTION, SAFETY, META, MEMORY, COORDINATION |

**Problem**: These are orthogonal dimensions. The same capability could be classified differently depending on which dimension you prioritize.

Example: Is `compare` a REASONING capability (Layer view) or a DIS verb (semantic view)?

### 1.2 Capability Counts by Layer

| Layer | Count | Capabilities |
|-------|-------|--------------|
| MODELING | 45 | detect-*, identify-*, estimate-*, forecast-*, world-state, etc. |
| REASONING | 20 | compare-*, plan, decide, critique, etc. |
| ACTION | 12 | act-*, generate-*, transform, send |
| SAFETY | 7 | verify, checkpoint, rollback, audit, etc. |
| META | 6 | discover-* |
| PERCEPTION | 4 | retrieve, inspect, search, receive |
| COORDINATION | 3 | delegate, synchronize, invoke-workflow |
| MEMORY | 2 | persist, recall |

### 1.3 Capability Counts by Origin

| Origin | Count | Examples |
|--------|-------|----------|
| DIS.Level4Verb (base) | 8 | detect, identify, estimate, forecast, compare, discover, generate, act |
| DIS domain specializations | 45 | detect-entity, identify-person, estimate-risk, etc. |
| Operational additions | 46 | plan, checkpoint, rollback, world-state, etc. |
| **Total** | **99** | |

---

## 2. Fundamental Question: DIS Verbs or Layers?

### 2.1 The Case for DIS Verbs

The DIS '23 framework identified 8 verbs as the **core semantic operations** AI systems perform:

| Verb | Semantic Meaning | Distinguishing Property |
|------|------------------|------------------------|
| **Detect** | Find occurrences of a pattern | Input → existence + location |
| **Identify** | Classify what something is | Input → label + confidence |
| **Estimate** | Quantify an uncertain value | Input → quantity + uncertainty |
| **Forecast** | Predict future state | Present → future |
| **Compare** | Evaluate alternatives | Options → ranking/recommendation |
| **Discover** | Find unknown patterns | Data → new knowledge |
| **Generate** | Produce new content | Specification → artifact |
| **Act** | Execute change | Plan → world state change |

**Strengths:**
- Derived from empirical research on AI products
- Each verb has a clear, distinct semantic meaning
- Verbs are mutually exclusive (no overlap)
- Verbs compose naturally (detect → identify → estimate → forecast)

### 2.2 The Case for Layers

The 8 layers organize capabilities by **cognitive/architectural function**:

| Layer | Function | Analogy |
|-------|----------|---------|
| PERCEPTION | Acquire external information | Sensory input |
| MODELING | Form internal representations | World model |
| REASONING | Analyze and decide | Deliberation |
| ACTION | Execute changes | Motor output |
| SAFETY | Ensure correctness | Control systems |
| META | Self-reflection | Metacognition |
| MEMORY | Persistence | Long-term storage |
| COORDINATION | Multi-agent | Social cognition |

**Strengths:**
- Grounded in cognitive architecture theory (BDI, SOAR)
- Clear ordering (PERCEPTION → MODELING → REASONING → ACTION)
- Safety as cross-cutting concern

### 2.3 The Problem: Current Hybrid

The current ontology tries to use **both** dimensions simultaneously:
- DIS verbs are capabilities (detect, identify, etc.)
- BUT they're also assigned to layers (detect → MODELING)
- AND specialized by domain (detect → detect-entity, detect-anomaly)

This creates confusion:
- Is `detect-anomaly` a DIS verb specialization or a MODELING capability?
- Is `plan` a REASONING capability or should it be `generate-plan` (an ACTION)?
- Is `verify` a SAFETY capability or is it `compare` + `decide`?

### 2.4 Recommendation: DIS Verbs as Primary, Layers as Secondary

**Proposal**: Use DIS verbs as the **primary organizing principle** (what the capability does), with layers as a **secondary classification** (where it sits architecturally).

```
Primary: DIS Verb (semantic operation)
  └── Secondary: Layer (architectural position)
        └── Tertiary: Domain (optional specialization)
```

This means:
1. The 8 DIS verbs are the **true atomic capabilities**
2. Domain specializations become **parameters**, not separate capabilities
3. Layers classify verbs, not replace them

---

## 3. Capability-by-Capability Analysis

### 3.1 Analysis Framework

For each capability, we assess:

| Criterion | Question |
|-----------|----------|
| **Atomic?** | Can it be decomposed into simpler operations? |
| **Distinct?** | Is it semantically different from all other capabilities? |
| **Necessary?** | Is there a use case that requires this specifically? |
| **DIS Mapping** | Does it map to a DIS verb (possibly specialized)? |

Verdicts:
- **KEEP**: Truly atomic, distinct, necessary
- **MERGE**: Redundant with another capability
- **DEMOTE**: Actually a composition (should be workflow pattern)
- **PARAMETERIZE**: Domain specialization that should be a parameter

### 3.2 DIS Base Verbs (8)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `detect` | ✓ | ✓ | **KEEP** | Core DIS verb |
| `identify` | ✓ | ✓ | **KEEP** | Core DIS verb |
| `estimate` | ✓ | ✓ | **KEEP** | Core DIS verb |
| `forecast` | ✓ | ✓ | **KEEP** | Core DIS verb |
| `compare` | ✓ | ✓ | **KEEP** | Core DIS verb |
| `discover` | ✓ | ✓ | **KEEP** | Core DIS verb |
| `generate` | ✓ | ✓ | **KEEP** | Core DIS verb |
| `act` | ✓ | ✓ | **KEEP** | Core DIS verb |

**Result**: All 8 DIS verbs are kept.

### 3.3 DIS Domain Specializations (45)

#### detect-* family (6)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `detect-person` | ✗ | ✗ | **PARAMETERIZE** | = `detect(domain: person)` |
| `detect-entity` | ✗ | ✗ | **PARAMETERIZE** | = `detect(domain: entity)` |
| `detect-activity` | ✗ | ✗ | **PARAMETERIZE** | = `detect(domain: activity)` |
| `detect-anomaly` | ✓ | ✓ | **KEEP** | Distinct: finding deviations is semantically different |
| `detect-attribute` | ✗ | ✗ | **PARAMETERIZE** | = `detect(domain: attribute)` |
| `detect-world` | ✗ | ✗ | **PARAMETERIZE** | = `detect(domain: world)` |

**Analysis**: Most `detect-*` variants are just domain parameters. Exception: `detect-anomaly` has distinct semantics (deviation detection vs. pattern matching).

#### identify-* family (7)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `identify-person` | ✗ | ✗ | **PARAMETERIZE** | = `identify(domain: person)` |
| `identify-entity` | ✗ | ✗ | **PARAMETERIZE** | = `identify(domain: entity)` |
| `identify-human-attribute` | ✗ | ✗ | **PARAMETERIZE** | = `identify(domain: human-attribute)` |
| `identify-anomaly` | ✓ | ✗ | **MERGE** | Redundant with `detect-anomaly` + `identify` |
| `identify-attribute` | ✗ | ✗ | **PARAMETERIZE** | = `identify(domain: attribute)` |
| `identify-activity` | ✗ | ✗ | **PARAMETERIZE** | = `identify(domain: activity)` |
| `identify-world` | ✗ | ✗ | **PARAMETERIZE** | = `identify(domain: world)` |

#### estimate-* family (7)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `estimate-relationship` | ✗ | ✗ | **PARAMETERIZE** | = `estimate(target: relationship)` |
| `estimate-risk` | ✓ | ✓ | **KEEP** | Risk estimation has distinct semantics (probability × impact) |
| `estimate-activity` | ✗ | ✗ | **PARAMETERIZE** | = `estimate(target: activity)` |
| `estimate-outcome` | ✗ | ✗ | **PARAMETERIZE** | = `estimate(target: outcome)` |
| `estimate-world` | ✗ | ✗ | **PARAMETERIZE** | = `estimate(target: world)` |
| `estimate-attribute` | ✗ | ✗ | **PARAMETERIZE** | = `estimate(target: attribute)` |
| `estimate-impact` | ✓ | ✗ | **MERGE** | Component of `estimate-risk` |

#### forecast-* family (6)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `forecast-time` | ✗ | ✗ | **PARAMETERIZE** | = `forecast(target: time)` |
| `forecast-impact` | ✗ | ✗ | **PARAMETERIZE** | = `forecast(target: impact)` |
| `forecast-outcome` | ✗ | ✗ | **PARAMETERIZE** | = `forecast(target: outcome)` |
| `forecast-attribute` | ✗ | ✗ | **PARAMETERIZE** | = `forecast(target: attribute)` |
| `forecast-world` | ✗ | ✗ | **PARAMETERIZE** | = `forecast(target: world)` |
| `forecast-risk` | ✓ | ✗ | **MERGE** | = `forecast(target: risk)`, not distinct enough |

#### compare-* family (6)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `compare-entities` | ✗ | ✗ | **PARAMETERIZE** | = `compare(target: entities)` |
| `compare-plans` | ✗ | ✗ | **PARAMETERIZE** | = `compare(target: plans)` |
| `compare-attributes` | ✗ | ✗ | **PARAMETERIZE** | = `compare(target: attributes)` |
| `compare-people` | ✗ | ✗ | **PARAMETERIZE** | = `compare(target: people)` |
| `compare-impact` | ✗ | ✗ | **PARAMETERIZE** | = `compare(target: impact)` |
| `compare-documents` | ✗ | ✗ | **PARAMETERIZE** | = `compare(target: documents)` |

#### discover-* family (5)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `discover-relationship` | ✗ | ✗ | **PARAMETERIZE** | = `discover(target: relationship)` |
| `discover-anomaly` | ✗ | ✗ | **MERGE** | = `detect-anomaly` + `discover` |
| `discover-outcome` | ✗ | ✗ | **PARAMETERIZE** | = `discover(target: outcome)` |
| `discover-activity` | ✗ | ✗ | **PARAMETERIZE** | = `discover(target: activity)` |
| `discover-human-attribute` | ✗ | ✗ | **PARAMETERIZE** | = `discover(target: human-attribute)` |

#### generate-* family (7)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `generate-audio` | ✗ | ✗ | **PARAMETERIZE** | = `generate(modality: audio)` |
| `generate-image` | ✗ | ✗ | **PARAMETERIZE** | = `generate(modality: image)` |
| `generate-text` | ✗ | ✗ | **PARAMETERIZE** | = `generate(modality: text)` |
| `generate-numeric-data` | ✗ | ✗ | **PARAMETERIZE** | = `generate(modality: numeric)` |
| `generate-attribute` | ✗ | ✗ | **PARAMETERIZE** | = `generate(target: attribute)` |
| `generate-world` | ✗ | ✗ | **PARAMETERIZE** | = `generate(target: world)` |
| `generate-plan` | ✗ | ✗ | **MERGE** | Redundant with `plan` |

#### act-* family (1)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `act-plan` | ✓ | ✓ | **KEEP** | Execute a plan (distinct from raw `act`) |

### 3.4 Operational Capabilities (46)

#### PERCEPTION Layer

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `retrieve` | ✓ | ✓ | **KEEP** | Pull specific data by ID/path |
| `inspect` | ✓ | ✓ | **KEEP** | Examine current state |
| `search` | ✓ | ✓ | **KEEP** | Query by criteria |
| `receive` | ✓ | ✓ | **KEEP** | Accept pushed data |

**Result**: All 4 PERCEPTION capabilities are kept.

#### SAFETY Layer

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `verify` | ✓ | ✗ | **REVIEW** | Overlaps with `compare` + criteria |
| `checkpoint` | ✓ | ✓ | **KEEP** | Save state for recovery |
| `rollback` | ✓ | ✓ | **KEEP** | Restore to checkpoint |
| `audit` | ✓ | ✓ | **KEEP** | Record what happened |
| `constrain` | ✓ | ✓ | **KEEP** | Enforce limits |
| `mitigate` | ✗ | ✗ | **DEMOTE** | = `identify-risk` + `plan` + `act` |
| `improve` | ✗ | ✗ | **DEMOTE** | = `critique` + `plan` + `act` |

#### REASONING Layer (non-compare)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `plan` | ✓ | ✓ | **KEEP** | Create action sequence |
| `schedule` | ✗ | ✗ | **MERGE** | = `plan` with time constraints |
| `prioritize` | ✗ | ✗ | **MERGE** | = `compare` + `rank` |
| `decide` | ✗ | ✗ | **MERGE** | = `compare` + select |
| `decompose` | ✓ | ✓ | **KEEP** | Break into subproblems |
| `optimize` | ✗ | ✗ | **DEMOTE** | = `compare` loop + `decide` |
| `critique` | ✓ | ✓ | **KEEP** | Identify weaknesses |
| `explain` | ✓ | ✓ | **KEEP** | Justify conclusions |
| `evaluate` | ✗ | ✗ | **MERGE** | = `compare` against criteria |
| `summarize` | ✗ | ✗ | **MERGE** | = `generate(modality: text, style: summary)` |
| `translate` | ✗ | ✗ | **MERGE** | = `generate(modality: text, transform: translate)` |
| `validate` | ✗ | ✗ | **MERGE** | = `verify` (same semantics) |
| `generalize` | ✗ | ✗ | **MERGE** | = `discover` + `generate` |

#### MODELING Layer (non-DIS)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `world-state` | ✓ | ✓ | **KEEP** | Canonical state snapshot |
| `state-transition` | ✓ | ✓ | **KEEP** | Define dynamics |
| `causal-model` | ✓ | ✓ | **KEEP** | Define cause-effect |
| `uncertainty-model` | ✗ | ✗ | **MERGE** | Part of all estimates |
| `grounding` | ✓ | ✓ | **KEEP** | Anchor claims to evidence |
| `provenance` | ✗ | ✗ | **MERGE** | Part of `grounding` |
| `identity-resolution` | ✓ | ✓ | **KEEP** | Resolve entity aliases |
| `temporal-reasoning` | ✗ | ✗ | **PARAMETERIZE** | = reasoning with `domain: temporal` |
| `spatial-reasoning` | ✗ | ✗ | **PARAMETERIZE** | = reasoning with `domain: spatial` |
| `simulation` | ✓ | ✓ | **KEEP** | Run what-if scenarios |
| `digital-twin` | ✗ | ✗ | **DEMOTE** | = `world-state` + `simulation` + `state-transition` |
| `map-relationships` | ✗ | ✗ | **MERGE** | = `discover(target: relationships)` |
| `model-schema` | ✓ | ✓ | **KEEP** | Define type structure |
| `diff-world-state` | ✗ | ✗ | **MERGE** | = `compare(target: world-states)` |
| `integrate` | ✓ | ✓ | **KEEP** | Merge from multiple sources |

#### ACTION Layer (non-generate)

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `transform` | ✓ | ✓ | **KEEP** | Convert data formats |
| `send` | ✓ | ✓ | **KEEP** | Transmit to external system |

#### COORDINATION Layer

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `delegate` | ✓ | ✓ | **KEEP** | Assign task to another agent |
| `synchronize` | ✓ | ✓ | **KEEP** | Achieve state agreement |
| `invoke-workflow` | ✓ | ✓ | **KEEP** | Execute composed workflow |

#### MEMORY Layer

| Capability | Atomic? | Distinct? | Verdict | Notes |
|------------|---------|-----------|---------|-------|
| `persist` | ✓ | ✓ | **KEEP** | Store durably |
| `recall` | ✓ | ✓ | **KEEP** | Retrieve stored data |

---

## 4. Summary of Verdicts

### 4.1 Capabilities to KEEP (Truly Atomic)

| Category | Capabilities | Count |
|----------|--------------|-------|
| DIS Verbs | detect, identify, estimate, forecast, compare, discover, generate, act | 8 |
| DIS Distinct Specializations | detect-anomaly, estimate-risk, act-plan | 3 |
| PERCEPTION | retrieve, inspect, search, receive | 4 |
| SAFETY | checkpoint, rollback, audit, constrain, verify | 5 |
| REASONING | plan, decompose, critique, explain | 4 |
| MODELING | world-state, state-transition, causal-model, grounding, identity-resolution, simulation, model-schema, integrate | 8 |
| ACTION | transform, send | 2 |
| COORDINATION | delegate, synchronize, invoke-workflow | 3 |
| MEMORY | persist, recall | 2 |
| **TOTAL ATOMIC** | | **39** |

### 4.2 Capabilities to PARAMETERIZE (Domain Parameters)

These 37 capabilities should become parameters of their base verb:

- detect-person, detect-entity, detect-activity, detect-attribute, detect-world
- identify-person, identify-entity, identify-human-attribute, identify-attribute, identify-activity, identify-world
- estimate-relationship, estimate-activity, estimate-outcome, estimate-world, estimate-attribute
- forecast-time, forecast-impact, forecast-outcome, forecast-attribute, forecast-world
- compare-entities, compare-plans, compare-attributes, compare-people, compare-impact, compare-documents
- discover-relationship, discover-outcome, discover-activity, discover-human-attribute
- generate-audio, generate-image, generate-text, generate-numeric-data, generate-attribute, generate-world
- temporal-reasoning, spatial-reasoning

### 4.3 Capabilities to MERGE (Redundant)

| Capability | Merge Into | Reason |
|------------|------------|--------|
| identify-anomaly | detect-anomaly + identify | Composition |
| estimate-impact | estimate-risk | Component |
| forecast-risk | estimate-risk + forecast | Composition |
| discover-anomaly | detect-anomaly + discover | Composition |
| generate-plan | plan | Same semantics |
| schedule | plan | Plan with time constraints |
| prioritize | compare | Compare + rank |
| decide | compare | Compare + select |
| evaluate | compare | Compare against criteria |
| validate | verify | Same semantics |
| summarize | generate | Generate text summary |
| translate | generate | Generate translated text |
| generalize | discover + generate | Composition |
| uncertainty-model | (implicit) | Part of all estimates |
| provenance | grounding | Part of grounding |
| map-relationships | discover | Discover relationships |
| diff-world-state | compare | Compare world states |

### 4.4 Capabilities to DEMOTE (Compositions → Workflow Patterns)

| Capability | Composition | Should Be |
|------------|-------------|-----------|
| mitigate | identify-risk → plan → act | Workflow pattern |
| improve | critique → plan → act | Workflow pattern |
| optimize | compare → decide (loop) | Workflow pattern |
| digital-twin | world-state + simulation + state-transition | Workflow pattern |

---

## 5. Proposed Refined Ontology

### 5.1 The 39 Atomic Capabilities

Based on first-principles analysis, the correct set is **39 atomic capabilities**:

```
TIER 1: DIS VERBS (8)
├── detect          # Find occurrences
├── identify        # Classify/label
├── estimate        # Quantify uncertain values
├── forecast        # Predict future
├── compare         # Evaluate alternatives
├── discover        # Find unknown patterns
├── generate        # Produce content
└── act             # Execute change

TIER 2: DISTINCT SPECIALIZATIONS (3)
├── detect-anomaly  # Find deviations (semantically distinct)
├── estimate-risk   # Quantify probability × impact
└── act-plan        # Execute a structured plan

TIER 3: PERCEPTION (4)
├── retrieve        # Pull specific data
├── inspect         # Examine current state
├── search          # Query by criteria
└── receive         # Accept pushed data

TIER 4: SAFETY (5)
├── verify          # Check postconditions
├── checkpoint      # Save state for recovery
├── rollback        # Restore to checkpoint
├── audit           # Record what happened
└── constrain       # Enforce limits

TIER 5: REASONING (4)
├── plan            # Create action sequence
├── decompose       # Break into subproblems
├── critique        # Identify weaknesses
└── explain         # Justify conclusions

TIER 6: WORLD MODELING (8)
├── world-state     # Canonical state snapshot
├── state-transition # Define dynamics
├── causal-model    # Define cause-effect
├── grounding       # Anchor claims to evidence
├── identity-resolution # Resolve entity aliases
├── simulation      # Run what-if scenarios
├── model-schema    # Define type structure
└── integrate       # Merge from multiple sources

TIER 7: ACTION (2)
├── transform       # Convert data formats
└── send            # Transmit to external

TIER 8: COORDINATION (3)
├── delegate        # Assign to another agent
├── synchronize     # Achieve state agreement
└── invoke-workflow # Execute composition

TIER 9: MEMORY (2)
├── persist         # Store durably
└── recall          # Retrieve stored
```

### 5.2 Domain Parameterization

Instead of 45 domain-specialized capabilities, we use parameters:

```yaml
# Old: 45 separate capabilities
detect-entity:
  ...
detect-person:
  ...
detect-activity:
  ...

# New: 1 capability with domain parameter
detect:
  input_schema:
    domain:
      type: string
      enum: [entity, person, activity, attribute, world, anomaly]
    target: ...
```

### 5.3 Workflow Patterns (Demoted Capabilities)

These become documented workflow patterns, not capabilities:

```yaml
# Pattern: mitigate
mitigate_pattern:
  steps:
    - capability: estimate-risk
    - capability: plan
    - capability: constrain
    - capability: act-plan

# Pattern: improve
improve_pattern:
  steps:
    - capability: critique
    - capability: plan
    - capability: act-plan
    - capability: verify

# Pattern: digital-twin
digital_twin_pattern:
  steps:
    - capability: world-state
    - capability: state-transition
    - capability: simulation
```

---

## 6. Organizing Principle Decision

### 6.1 Recommendation: DIS Verbs as Primary

Based on this analysis, we recommend:

**Primary Axis: DIS Semantic Verbs (8)**
- detect, identify, estimate, forecast, compare, discover, generate, act

**Secondary Axis: Architectural Function (simplified)**
- PERCEPTION: How we acquire information
- MODELING: How we represent the world
- REASONING: How we analyze and plan
- ACTION: How we change the world
- SAFETY: How we ensure correctness
- COORDINATION: How we work with others
- MEMORY: How we persist state

**Why this is better:**
1. DIS verbs are **empirically derived** from AI product analysis
2. Each verb has **clear, distinct semantics**
3. Domain specialization becomes **parameter**, reducing redundancy
4. Layers become **architectural tags**, not primary organization

### 6.2 Alternative: Keep Both but Clarify

If we want to keep the layer organization:

1. **Remove domain specializations** (37 capabilities → parameters)
2. **Merge redundant capabilities** (17 capabilities)
3. **Demote compositions** (4 capabilities → patterns)
4. **Keep distinct atoms** (39 capabilities)

---

## 7. Conclusion

### What We Found

| Category | Current | After Analysis |
|----------|---------|----------------|
| Total capabilities | 99 | 39 atomic |
| DIS verbs | 8 | 8 (primary) |
| Domain specializations | 45 | 0 (→ parameters) |
| Redundant | 0 identified | 17 (→ merge) |
| Compositions | 0 identified | 4 (→ patterns) |
| Truly atomic | ? | 39 |

### Recommendation

**Reduce from 99 to 39 capabilities** by:
1. Keeping the 8 DIS verbs as primary atoms
2. Parameterizing domain specializations
3. Merging redundant capabilities
4. Demoting compositions to workflow patterns

This gives us a **defensible, first-principles-derived** ontology where:
- Every capability is truly atomic
- No redundancy exists
- The count (39) emerges from analysis, not arbitrary expansion

---

## Next Steps

1. **Review this analysis** with stakeholders
2. **Decide** whether to adopt the 39-capability ontology
3. **If yes**: Update schemas, documentation, workflows
4. **If no**: Document which contested capabilities should remain and why

---

## References

- DIS '23: Yildirim, N. et al. (2023). Creating Design Resources to Scaffold the Ideation of AI Concepts.
- BDI: Rao, A.S. & Georgeff, M.P. (1995). BDI Agents: From Theory to Practice.
- SOAR: Laird, J.E. (2012). The Soar Cognitive Architecture.
