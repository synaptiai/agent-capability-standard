# Refined Ontology Proposal: 39 Atomic Capabilities

**Document Status**: Proposal for Review
**Last Updated**: 2026-01-26
**Version**: 1.0.0
**Purpose**: Propose a principled, first-principles-derived capability ontology

---

## Executive Summary

Based on rigorous first-principles analysis, we propose reducing the capability ontology from **99 to 39 capabilities**.

| Metric | Current | Proposed | Change |
|--------|---------|----------|--------|
| Total capabilities | 99 | 39 | -60 |
| DIS verbs | 8 | 8 | 0 |
| Domain specializations | 45 | 3 | -42 (→ parameters) |
| Operational additions | 46 | 28 | -18 (redundancy/composition) |

**Key Changes:**
1. Domain specializations become **parameters** (detect-entity → detect with domain param)
2. Redundant capabilities are **merged** (validate → verify, decide → compare)
3. Compositions are **demoted** to workflow patterns (mitigate, improve, optimize)

**Result:** A defensible, derivable ontology where **every capability is truly atomic**.

---

## 1. Design Principles

### 1.1 DIS Verbs as Foundation

The 8 DIS verbs from Yildirim et al. (2023) form the semantic foundation:

| Verb | Operation | Output Type |
|------|-----------|-------------|
| **detect** | Find occurrences of a pattern | existence + location |
| **identify** | Classify what something is | label + confidence |
| **estimate** | Quantify an uncertain value | quantity + uncertainty |
| **forecast** | Predict future state | prediction + probability |
| **compare** | Evaluate alternatives | ranking + recommendation |
| **discover** | Find unknown patterns | new knowledge |
| **generate** | Produce new content | artifact |
| **act** | Execute change | state change |

### 1.2 Layers as Classification

Layers classify capabilities by **architectural function**, not as the primary organizing principle:

| Layer | Function | Capabilities |
|-------|----------|--------------|
| PERCEPTION | Acquire information | retrieve, inspect, search, receive |
| MODELING | Represent the world | DIS verbs, world modeling |
| REASONING | Analyze and plan | plan, decompose, critique, explain |
| ACTION | Change the world | act, act-plan, transform, send |
| SAFETY | Ensure correctness | verify, checkpoint, rollback, audit, constrain |
| COORDINATION | Work with others | delegate, synchronize, invoke-workflow |
| MEMORY | Persist state | persist, recall |

### 1.3 Parameterization over Specialization

Domain specializations become parameters:

```yaml
# OLD: 45 separate capabilities
detect-entity:
  layer: MODELING
  input: {target: entity_ref}
  output: {detected: boolean, location: string}

detect-person:
  layer: MODELING
  input: {target: person_ref}
  output: {detected: boolean, location: string}

# NEW: 1 capability with domain parameter
detect:
  layer: MODELING
  input:
    target: any
    domain:
      type: string
      enum: [entity, person, activity, attribute, world, relationship, pattern]
  output: {detected: boolean, location: string, evidence_anchors: array}
```

---

## 2. The 39 Atomic Capabilities

### 2.1 Complete List

```
TIER 1: DIS SEMANTIC VERBS (8)
┌─────────────────────────────────────────────────────────────┐
│ detect    │ Find occurrences of patterns/objects           │
│ identify  │ Classify and label what something is           │
│ estimate  │ Quantify uncertain values                      │
│ forecast  │ Predict future states                          │
│ compare   │ Evaluate and rank alternatives                 │
│ discover  │ Find previously unknown patterns               │
│ generate  │ Produce new content/artifacts                  │
│ act       │ Execute changes in the world                   │
└─────────────────────────────────────────────────────────────┘

TIER 2: SEMANTICALLY DISTINCT SPECIALIZATIONS (3)
┌─────────────────────────────────────────────────────────────┐
│ detect-anomaly │ Find deviations from expected patterns    │
│ estimate-risk  │ Quantify probability × impact             │
│ act-plan       │ Execute a structured plan (not raw act)   │
└─────────────────────────────────────────────────────────────┘

TIER 3: PERCEPTION (4)
┌─────────────────────────────────────────────────────────────┐
│ retrieve  │ Pull specific data by ID/path                  │
│ inspect   │ Examine current state                          │
│ search    │ Query by criteria                              │
│ receive   │ Accept pushed data/events                      │
└─────────────────────────────────────────────────────────────┘

TIER 4: SAFETY (5)
┌─────────────────────────────────────────────────────────────┐
│ verify     │ Check postconditions against criteria         │
│ checkpoint │ Save state for potential recovery             │
│ rollback   │ Restore to previous checkpoint                │
│ audit      │ Record what happened and why                  │
│ constrain  │ Enforce limits and policies                   │
└─────────────────────────────────────────────────────────────┘

TIER 5: REASONING (4)
┌─────────────────────────────────────────────────────────────┐
│ plan      │ Create action sequence to achieve goal         │
│ decompose │ Break problem into subproblems                 │
│ critique  │ Identify weaknesses and issues                 │
│ explain   │ Justify conclusions with reasoning             │
└─────────────────────────────────────────────────────────────┘

TIER 6: WORLD MODELING (8)
┌─────────────────────────────────────────────────────────────┐
│ world-state         │ Create canonical state snapshot       │
│ state-transition    │ Define state dynamics and rules       │
│ causal-model        │ Define cause-effect relationships     │
│ grounding           │ Anchor claims to evidence             │
│ identity-resolution │ Resolve entity aliases/duplicates     │
│ simulation          │ Run what-if scenarios                 │
│ model-schema        │ Define type structure for validation  │
│ integrate           │ Merge data from multiple sources      │
└─────────────────────────────────────────────────────────────┘

TIER 7: ACTION (2)
┌─────────────────────────────────────────────────────────────┐
│ transform │ Convert data between formats                   │
│ send      │ Transmit to external system                    │
└─────────────────────────────────────────────────────────────┘

TIER 8: COORDINATION (3)
┌─────────────────────────────────────────────────────────────┐
│ delegate        │ Assign task to another agent             │
│ synchronize     │ Achieve state agreement across agents    │
│ invoke-workflow │ Execute a composed workflow              │
└─────────────────────────────────────────────────────────────┘

TIER 9: MEMORY (2)
┌─────────────────────────────────────────────────────────────┐
│ persist │ Store data durably                               │
│ recall  │ Retrieve previously stored data                  │
└─────────────────────────────────────────────────────────────┘

TOTAL: 39 ATOMIC CAPABILITIES
```

### 2.2 Capability Details

#### DIS Verbs (8)

| ID | Layer | Input | Output | Parameterizable By |
|----|-------|-------|--------|-------------------|
| `detect` | MODELING | target, domain | detected, location, evidence | domain (entity, person, activity, etc.) |
| `identify` | MODELING | target, domain | label, confidence, evidence | domain (entity, person, activity, etc.) |
| `estimate` | MODELING | target, metric | value, uncertainty, evidence | metric (magnitude, duration, probability, etc.) |
| `forecast` | MODELING | target, horizon | prediction, probability, evidence | target (state, outcome, trajectory, etc.) |
| `compare` | REASONING | options, criteria | ranking, recommendation, tradeoffs | target (entities, plans, states, etc.) |
| `discover` | META | data, constraints | patterns, relationships, evidence | target (pattern, relationship, etc.) |
| `generate` | ACTION | specification | artifact, confidence | modality (text, code, image, audio, etc.) |
| `act` | ACTION | action, target | result, side_effects | (use act-plan for structured plans) |

#### Distinct Specializations (3)

| ID | Layer | Why Distinct |
|----|-------|--------------|
| `detect-anomaly` | MODELING | Deviation detection has distinct semantics from pattern matching |
| `estimate-risk` | MODELING | Risk = probability × impact; distinct calculation method |
| `act-plan` | ACTION | Executing structured plans differs from raw actions |

#### Perception (4)

| ID | Layer | Purpose |
|----|-------|---------|
| `retrieve` | PERCEPTION | Pull specific known data |
| `inspect` | PERCEPTION | Observe current state |
| `search` | PERCEPTION | Query by criteria |
| `receive` | PERCEPTION | Accept pushed data |

#### Safety (5)

| ID | Layer | Purpose |
|----|-------|---------|
| `verify` | SAFETY | Check against criteria |
| `checkpoint` | SAFETY | Save recovery point |
| `rollback` | SAFETY | Restore from checkpoint |
| `audit` | SAFETY | Record provenance |
| `constrain` | SAFETY | Enforce limits |

#### Reasoning (4)

| ID | Layer | Purpose |
|----|-------|---------|
| `plan` | REASONING | Create action sequences |
| `decompose` | REASONING | Break into subproblems |
| `critique` | REASONING | Find weaknesses |
| `explain` | REASONING | Justify conclusions |

#### World Modeling (8)

| ID | Layer | Purpose |
|----|-------|---------|
| `world-state` | MODELING | Canonical snapshot |
| `state-transition` | MODELING | Define dynamics |
| `causal-model` | MODELING | Cause-effect |
| `grounding` | MODELING | Evidence anchoring |
| `identity-resolution` | MODELING | Alias resolution |
| `simulation` | MODELING | What-if scenarios |
| `model-schema` | MODELING | Type definitions |
| `integrate` | MODELING | Multi-source merge |

#### Action (2)

| ID | Layer | Purpose |
|----|-------|---------|
| `transform` | ACTION | Format conversion |
| `send` | ACTION | External transmission |

#### Coordination (3)

| ID | Layer | Purpose |
|----|-------|---------|
| `delegate` | COORDINATION | Task assignment |
| `synchronize` | COORDINATION | State agreement |
| `invoke-workflow` | COORDINATION | Workflow execution |

#### Memory (2)

| ID | Layer | Purpose |
|----|-------|---------|
| `persist` | MEMORY | Durable storage |
| `recall` | MEMORY | Storage retrieval |

---

## 3. What Becomes Workflow Patterns

These are demoted from capabilities to documented workflow patterns:

### 3.1 Mitigation Pattern

```yaml
mitigate:
  description: Reduce risk through intervention
  pattern_type: workflow
  steps:
    - capability: estimate-risk
      purpose: Quantify the risk
    - capability: plan
      purpose: Create mitigation plan
    - capability: constrain
      purpose: Apply safety limits
    - capability: checkpoint
      purpose: Save state before action
    - capability: act-plan
      purpose: Execute mitigation
    - capability: verify
      purpose: Confirm risk reduced
```

### 3.2 Improvement Pattern

```yaml
improve:
  description: Make something better iteratively
  pattern_type: workflow
  steps:
    - capability: critique
      purpose: Identify weaknesses
    - capability: plan
      purpose: Create improvement plan
    - capability: checkpoint
      purpose: Save state
    - capability: act-plan
      purpose: Execute improvements
    - capability: verify
      purpose: Confirm improvement
```

### 3.3 Optimization Pattern

```yaml
optimize:
  description: Find best solution through iteration
  pattern_type: workflow
  steps:
    - capability: discover
      purpose: Find candidate solutions
    - capability: compare
      purpose: Evaluate alternatives
      loop: until_optimal_or_max_iterations
```

### 3.4 Digital Twin Pattern

```yaml
digital_twin:
  description: Synchronized digital replica
  pattern_type: workflow
  steps:
    - capability: world-state
      purpose: Create initial snapshot
    - capability: state-transition
      purpose: Define dynamics
    - capability: simulation
      purpose: Run scenarios
    - capability: integrate
      loop: continuous_sync
```

---

## 4. Migration Path

### 4.1 Schema Changes

```json
// OLD capability_ontology.json
{
  "nodes": [
    {"id": "detect-entity", "layer": "MODELING", ...},
    {"id": "detect-person", "layer": "MODELING", ...},
    {"id": "detect-activity", "layer": "MODELING", ...}
  ]
}

// NEW capability_ontology.json
{
  "nodes": [
    {
      "id": "detect",
      "layer": "MODELING",
      "type": "DIS.Level4Verb",
      "input_schema": {
        "target": {"type": "any"},
        "domain": {
          "type": "string",
          "enum": ["entity", "person", "activity", "attribute", "world", "pattern"]
        }
      }
    }
  ]
}
```

### 4.2 Workflow Updates

Existing workflows using domain-specialized capabilities need minor updates:

```yaml
# OLD
- capability: detect-entity
  store_as: entities

# NEW
- capability: detect
  input_bindings:
    domain: entity
  store_as: entities
```

### 4.3 Backward Compatibility

Option A: **Hard migration** — Update all at once
Option B: **Alias support** — `detect-entity` maps to `detect(domain: entity)` during transition

---

## 5. Benefits of This Approach

### 5.1 Intellectual Integrity

| Aspect | Current (99) | Proposed (39) |
|--------|--------------|---------------|
| Derivation | Accumulated pragmatically | First-principles derived |
| Atomicity | Many are compositions | All truly atomic |
| Redundancy | ~17 redundant pairs | None |
| Defensibility | "Why 99?" unanswerable | Every capability justified |

### 5.2 Practical Benefits

| Benefit | Description |
|---------|-------------|
| **Simpler mental model** | 39 capabilities vs 99 to understand |
| **No capability explosion** | Parameters instead of specializations |
| **Clear semantics** | Each capability does exactly one thing |
| **Easier validation** | Fewer capabilities = simpler validator |
| **Better documentation** | Document 39 things well vs 99 superficially |

### 5.3 Alignment with DIS '23

The proposed ontology **directly implements** the DIS '23 framework:
- 8 core verbs are preserved
- Semantic distinctions are honored
- Domain specialization via parameters (not capability explosion)

---

## 6. Open Questions

### 6.1 Keep or Merge?

Some capabilities have arguments for both:

| Capability | Keep? | Merge? | Decision Needed |
|------------|-------|--------|-----------------|
| `verify` | Distinct from compare | = compare + criteria | **Leaning KEEP** |
| `detect-anomaly` | Distinct semantics | = detect + pattern | **Leaning KEEP** |
| `estimate-risk` | probability × impact | = estimate(metric: risk) | **Leaning KEEP** |

### 6.2 Layer Simplification?

Could we simplify layers further?

| Current (8) | Possible (6) |
|-------------|--------------|
| PERCEPTION | PERCEPTION |
| MODELING | MODELING |
| REASONING | REASONING |
| ACTION | ACTION |
| SAFETY | SAFETY |
| META | (merge into MODELING) |
| MEMORY | (merge into PERCEPTION) |
| COORDINATION | COORDINATION |

**Decision**: Keep 8 for now; layers are secondary classification anyway.

### 6.3 Naming?

Should DIS verbs keep their names or use more descriptive alternatives?

| DIS Name | Alternative | Decision |
|----------|-------------|----------|
| detect | find | Keep `detect` (established) |
| identify | classify | Keep `identify` (established) |
| estimate | quantify | Keep `estimate` (established) |

---

## 7. Implementation Recommendation

### Phase 1: Documentation (Week 1)
- Finalize this proposal
- Update methodology docs
- Create migration guide

### Phase 2: Schema (Week 2)
- Update `capability_ontology.json` to 39 capabilities
- Add domain/target parameters to DIS verbs
- Create workflow pattern templates

### Phase 3: Skills (Weeks 3-4)
- Update skill files (39 skills vs 99)
- Migrate domain specializations to parameters
- Document workflow patterns

### Phase 4: Validation (Week 5)
- Update validator for new schema
- Run conformance tests
- Verify all workflows still pass

### Phase 5: Documentation Update (Week 6)
- Update README, FAQ, etc.
- Update "99" → "39" throughout
- Publish migration guide

---

## 8. Conclusion

The proposed **39-capability ontology** is:

1. **Principled**: Derived from first-principles analysis
2. **Atomic**: Every capability is truly irreducible
3. **Non-redundant**: No semantic overlap
4. **Defensible**: We can explain why each capability exists
5. **Aligned**: Directly implements DIS '23 framework

The reduction from 99 to 39 is not a loss—it's a clarification. We're not removing functionality; we're organizing it correctly:
- Domain specializations → parameters
- Redundancies → merged
- Compositions → workflow patterns

**Recommendation**: Adopt this proposal to create a world-class, intellectually rigorous capability ontology.

---

## References

- [FIRST_PRINCIPLES_ANALYSIS.md](FIRST_PRINCIPLES_ANALYSIS.md) — Full analysis
- [REJECTED_CANDIDATES.md](REJECTED_CANDIDATES.md) — What we didn't include
- DIS '23: Yildirim et al. (2023). Creating Design Resources to Scaffold the Ideation of AI Concepts.
