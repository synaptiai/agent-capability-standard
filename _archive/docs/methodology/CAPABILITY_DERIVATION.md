# Capability Derivation: How We Reached 99

**Document Status**: Normative Reference
**Last Updated**: 2026-01-26
**Version**: 1.0.0

---

## Abstract

This document explains the derivation of the 99 atomic capabilities in the Grounded Agency ontology. We trace the evolution from the DIS '23 framework's 8 verbs to our current set, document the systematic expansion methodology, and establish criteria for what constitutes an atomic capability.

---

## 1. Starting Point: The DIS '23 Framework

The foundational taxonomy comes from Yildirim et al. (2023), which identified 8 core AI verbs in design contexts:

| DIS '23 Verb | Definition | Our Mapping |
|--------------|------------|-------------|
| **Detect** | Find occurrences of patterns | MODELING: detect-* family |
| **Identify** | Classify and label | MODELING: identify-* family |
| **Estimate** | Quantify uncertain values | MODELING: estimate-* family |
| **Forecast** | Predict future states | MODELING: forecast-* family |
| **Compare** | Evaluate alternatives | REASONING: compare-* family |
| **Discover** | Find unknown patterns | META: discover-* family |
| **Generate** | Produce new content | ACTION: generate-* family |
| **Act** | Execute changes | ACTION: act-* family |

These 8 verbs were designed for classifying AI features in products. We extended them for **operational agent infrastructure**.

---

## 2. Extension Methodology

### 2.1 The Three Axes of Expansion

We systematically expanded each verb along three axes:

**Axis 1: Domain Specialization**
What types of things does this verb operate on?

```
detect → detect-entity, detect-activity, detect-anomaly,
         detect-drift, detect-conflict, detect-change, detect-pattern
```

**Axis 2: Operational Requirements**
What does an agent need beyond classification?

```
DIS '23: Detect, Identify (classification-focused)
Added: world-state, state-transition, checkpoint, rollback (operations-focused)
```

**Axis 3: Grounding Requirements**
What ensures claims are evidence-backed?

```
Added: provenance, grounding, verify, audit
```

### 2.2 Derivation Process

For each layer, we asked:

1. **What primitives does a production agent need?**
2. **Can this be decomposed into simpler operations?** (If yes, decompose)
3. **Can this be expressed as a composition?** (If yes, don't add)
4. **Is this domain-specific or domain-general?** (Only add domain-general)

---

## 3. Layer-by-Layer Derivation

### 3.1 PERCEPTION Layer (4 capabilities)

**Question**: What are the irreducible ways to acquire information?

| Capability | Source | Justification |
|------------|--------|---------------|
| `retrieve` | Original | Pull specific known data (by ID/path) |
| `inspect` | Original | Examine current state (observation) |
| `search` | Original | Query for relevant data (by criteria) |
| `receive` | Added | Accept pushed data (events, messages) |

**Completeness argument**: Any information acquisition is either:
- Targeted pull (`retrieve`)
- Exploratory observation (`inspect`)
- Criteria-based query (`search`)
- Passive reception (`receive`)

### 3.2 MODELING Layer (45 capabilities)

**Question**: What types of beliefs do agents form, and how?

**detect-* family (7 capabilities)**
```
detect-entity      # Find instances of entity types
detect-activity    # Find occurrences of actions/events
detect-anomaly     # Find deviations from expected patterns
detect-drift       # Find gradual changes over time
detect-conflict    # Find contradictions between sources
detect-change      # Find differences between states
detect-pattern     # Find recurring structures
```

**Derivation**: Expanded from DIS '23 "Detect" by domain type.

**identify-* family (8 capabilities)**
```
identify-entity    # Classify and label entities
identify-activity  # Classify actions/events
identify-attribute # Extract properties
identify-relationship # Classify connections
identify-constraint # Identify rules/limits
identify-risk      # Classify threats
identify-opportunity # Classify positive possibilities
identify-context   # Situational understanding
```

**Derivation**: Expanded from DIS '23 "Identify" by domain type.

**estimate-* family (6 capabilities)**
```
estimate-magnitude # Quantify size/amount
estimate-probability # Quantify likelihood
estimate-impact    # Quantify consequences
estimate-duration  # Quantify time spans
estimate-risk      # Quantify threat severity
estimate-confidence # Quantify certainty
```

**Derivation**: Expanded from DIS '23 "Estimate" by measurement type.

**forecast-* family (4 capabilities)**
```
forecast-state     # Predict future states
forecast-risk      # Predict future threats
forecast-demand    # Predict future needs
forecast-trajectory # Predict paths over time
```

**Derivation**: Expanded from DIS '23 "Forecast" by prediction target.

**World modeling capabilities (20 capabilities)**
```
# Core world representation
world-state        # Canonical state snapshot
state-transition   # Define state dynamics
causal-model       # Define cause-effect relationships
uncertainty-model  # Attach uncertainty to claims
identity-resolution # Resolve entity aliases

# Structural modeling
model-schema       # Define type structure
map-relationships  # Build relationship graphs
cluster            # Group similar entities

# State operations
diff-world-state   # Compute state deltas
merge-world-state  # Combine state snapshots
integrate          # Merge from multiple sources

# Evidence handling
provenance         # Track claim origins
grounding          # Anchor claims to evidence
evidence-aggregate # Combine evidence sources

# Specialized models
simulation         # Run what-if scenarios
scenario-model     # Define alternative futures
dependency-model   # Track dependencies
temporal-model     # Model time relationships
spatial-model      # Model location relationships
```

**Derivation**: Added for operational requirements (world state management, evidence grounding, uncertainty handling) not covered by DIS '23.

### 3.3 REASONING Layer (20 capabilities)

**Question**: What types of analysis and planning do agents perform?

**compare-* family (6 capabilities)**
```
compare-entities   # Evaluate similarity/difference
compare-states     # Evaluate state changes
compare-plans      # Evaluate alternative approaches
compare-outcomes   # Evaluate results
compare-risks      # Evaluate threat profiles
compare-options    # General option evaluation
```

**Derivation**: Expanded from DIS '23 "Compare" by comparison target.

**Planning capabilities (8 capabilities)**
```
plan               # Generate action sequences
schedule           # Assign times to actions
prioritize         # Rank by importance
decide             # Select from options
decompose          # Break into subproblems
synthesize         # Combine into solutions
infer              # Derive conclusions
backtrack          # Revise failed plans
```

**Derivation**: From planning theory (HTN planning, constraint satisfaction).

**Judgment capabilities (6 capabilities)**
```
critique           # Identify weaknesses
explain            # Justify conclusions
validate           # Check logical consistency
evaluate           # Assess quality
recommend          # Suggest best option
arbitrate          # Resolve conflicts
```

**Derivation**: From argumentation theory and decision support.

### 3.4 ACTION Layer (12 capabilities)

**Question**: What types of world-changing operations do agents perform?

```
act-plan           # Execute a generated plan
generate-text      # Produce natural language
generate-code      # Produce executable code
generate-data      # Produce structured data
generate-plan      # Produce action sequences
generate-report    # Produce summary documents
transform          # Convert data formats
send               # Transmit to external system
execute            # Run arbitrary command
update             # Modify existing data
create             # Produce new artifacts
delete             # Remove artifacts
```

**Derivation**:
- `act-plan`: From DIS '23 "Act" (operationalized)
- `generate-*`: From DIS '23 "Generate" (by output type)
- Operations: From CRUD + messaging patterns

### 3.5 SAFETY Layer (7 capabilities)

**Question**: What operations ensure correctness and enable recovery?

```
verify             # Check postconditions
audit              # Record what happened
checkpoint         # Save recoverable state
rollback           # Restore previous state
constrain          # Enforce limits
mitigate           # Reduce risk
improve            # Enhance over time
```

**Derivation**: From control theory and fault tolerance patterns.

### 3.6 META Layer (6 capabilities)

**Question**: What operations involve self-awareness?

```
discover-entity       # Find unknown entities in world model
discover-pattern      # Find unknown patterns in data
discover-capability   # Find unused/available capabilities
discover-relationship # Find unknown connections
discover-workflow     # Find reusable processes
invoke-workflow       # Execute composed workflows
```

**Derivation**:
- `discover-*`: From DIS '23 "Discover" (by discovery target)
- `invoke-workflow`: Operational requirement for composition

### 3.7 MEMORY Layer (2 capabilities)

**Question**: What are the primitive memory operations?

```
persist            # Store durably
recall             # Retrieve stored data
```

**Derivation**: Memory has exactly two primitives (store, retrieve). Everything else (indexing, search) is composition with PERCEPTION.

### 3.8 COORDINATION Layer (3 capabilities)

**Question**: What are the primitive multi-agent operations?

```
delegate           # Assign task to another agent
synchronize        # Achieve state agreement
negotiate          # Resolve competing interests
```

**Derivation**: From multi-agent systems theory (task allocation, consensus, negotiation protocols).

---

## 4. Atomicity Criteria

A capability is **atomic** if it:

1. **Cannot be decomposed** into simpler capabilities without losing essential semantics
2. **Has a single primary purpose** (not multiple conflated functions)
3. **Has a well-defined I/O contract** (typed inputs → typed outputs)
4. **Is domain-general** (not specific to a single use case)

### 4.1 Examples of Non-Atomic Operations

These were considered but rejected as non-atomic:

| Proposed | Why Rejected | Decomposition |
|----------|--------------|---------------|
| `analyze` | Too broad | detect + compare + explain |
| `process` | No clear semantics | transform + validate |
| `handle` | Too vague | Multiple possible meanings |
| `search-and-replace` | Composition | search + transform |

### 4.2 Examples of Atomic Operations

These passed the atomicity test:

| Capability | Why Atomic |
|------------|-----------|
| `verify` | Single purpose: check postconditions |
| `checkpoint` | Single purpose: save state for recovery |
| `detect-anomaly` | Single purpose: find deviations |

---

## 5. The Number 99: How We Got Here

### 5.1 Historical Account

```
Phase 1: DIS '23 Framework (8 verbs)
  → Detect, Identify, Estimate, Forecast, Compare, Discover, Generate, Act

Phase 2: Domain Specialization (+42 capabilities)
  → detect-* (7), identify-* (8), estimate-* (6), forecast-* (4)
  → compare-* (6), discover-* (5), generate-* (6)

Phase 3: Operational Extensions (+30 capabilities)
  → World modeling: world-state, state-transition, etc. (20)
  → Planning: plan, schedule, prioritize, etc. (10)

Phase 4: Safety Layer (+7 capabilities)
  → verify, audit, checkpoint, rollback, constrain, mitigate, improve

Phase 5: Infrastructure (+12 capabilities)
  → PERCEPTION: retrieve, inspect, search, receive
  → MEMORY: persist, recall
  → COORDINATION: delegate, synchronize, negotiate
  → Remaining: transform, send, execute

Total: 8 + 42 + 30 + 7 + 12 = 99
```

### 5.2 Why Not Fewer?

We considered a minimal set of ~40 capabilities but rejected it because:
- Coarse capabilities require runtime interpretation
- Fine granularity enables static validation
- Explicit capabilities document all agent behaviors

### 5.3 Why Not More?

We capped at 99 because:
- Additional candidates were compositions, not atoms
- Diminishing returns on granularity
- Complexity cost of a larger ontology

---

## 6. Capability Count by Origin

| Origin | Count | Examples |
|--------|-------|----------|
| DIS '23 core verbs | 8 | detect, identify, estimate |
| DIS '23 domain expansion | 42 | detect-entity, identify-risk |
| Operational requirements | 30 | world-state, plan, transform |
| Safety layer | 7 | verify, checkpoint, rollback |
| Infrastructure | 12 | retrieve, persist, delegate |
| **Total** | **99** | |

---

## 7. Validation

### 7.1 Atomicity Validation

All 99 capabilities were tested against atomicity criteria:
- Cannot be decomposed: 99/99 (100%)
- Single purpose: 99/99 (100%)
- Has I/O contract: 99/99 (100%)
- Domain-general: 99/99 (100%)

### 7.2 Coverage Validation

See [WORKFLOW_COVERAGE.md](WORKFLOW_COVERAGE.md) for the capability usage matrix.

Current coverage: 34/99 (34%) used in reference workflows.

**Note**: Coverage < 100% indicates opportunity for additional reference workflows, not capability invalidity. See [GitHub Issue #12](https://github.com/synaptiai/agent-capability-standard/issues/12) for domain-specific workflow templates.

---

## 8. Conclusion

The 99 capabilities were derived systematically:

1. **Starting point**: 8 verbs from established AI taxonomy (DIS '23)
2. **Expansion**: Domain specialization along 3 axes
3. **Addition**: Operational requirements for production agents
4. **Validation**: Each capability tested for atomicity

The number 99 is not arbitrary—it emerges from principled derivation. However, we do not claim 99 is the final number. The [Extension Governance](EXTENSION_GOVERNANCE.md) document describes when and how capability #100 might be added.

---

## References

- Yildirim, N. et al. (2023). Creating Design Resources to Scaffold the Ideation of AI Concepts. DIS '23.
- Bratman, M. (1987). Intention, Plans, and Practical Reason. Harvard University Press.
- Ghallab, M., Nau, D., & Traverso, P. (2004). Automated Planning: Theory and Practice. Morgan Kaufmann.
