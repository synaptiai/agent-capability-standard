# Ontology Decision Matrix

**Document Status**: Decision Support
**Last Updated**: 2026-01-26
**Purpose**: Compare finalized options for capability ontology

---

## The Decision

We must choose the capability ontology for Grounded Agency. This document presents the refined options after research.

---

## Option Comparison

### Option 1: Current 99 Capabilities (Status Quo)

**Philosophy**: Keep existing structure with minor documentation improvements.

| Metric | Value |
|--------|-------|
| Capability count | 99 |
| Layers | 8 |
| Validated in workflows | 34 (34%) |
| Redundant pairs | ~17 |
| Domain specializations | 45 |

**Pros**:
- No migration required
- All documentation exists

**Cons**:
- 65% never tested
- "Why 99?" unanswerable
- Known redundancies
- Defensibility: LOW

---

### Option 2: First-Principles 39 (DIS-Derived)

**Philosophy**: Derive from DIS verbs with strict atomicity.

| Metric | Value |
|--------|-------|
| Capability count | 39 |
| Foundation | DIS '23 8 verbs |
| Specializations | 3 (detect-anomaly, estimate-risk, act-plan) |
| Parameterization | Domain as parameter |

**Structure**:
```
DIS VERBS (8): detect, identify, estimate, forecast, compare, discover, generate, act
SPECIALIZATIONS (3): detect-anomaly, estimate-risk, act-plan
PERCEPTION (4): retrieve, inspect, search, receive
SAFETY (5): verify, checkpoint, rollback, audit, constrain
REASONING (4): plan, decompose, critique, explain
WORLD MODELING (8): world-state, state-transition, causal-model, grounding, identity-resolution, simulation, model-schema, integrate
ACTION (2): transform, send
COORDINATION (3): delegate, synchronize, invoke-workflow
MEMORY (2): persist, recall
```

**Pros**:
- Principled derivation
- No redundancy
- Smaller, cleaner set
- Good documentation exists (from our work)

**Cons**:
- DIS verbs not industry standard
- 3 exceptions (specializations) feel arbitrary
- Names like "identify" and "estimate" less clear than alternatives
- Defensibility: MEDIUM (DIS '23 is not a recognized agent standard)

---

### Option 3: Tool-Aligned 35 (Research-Derived)

**Philosophy**: Align with how agents actually work (MCP, LangChain, ReAct).

| Metric | Value |
|--------|-------|
| Capability count | 35 |
| Foundation | Industry tool patterns |
| Specializations | 0 (no exceptions) |
| Parameterization | Domain as context only |

**Structure**:
```
PERCEPTION (4): retrieve, search, inspect, receive
UNDERSTANDING (6): detect, classify, measure, predict, compare, discover
REASONING (4): plan, decompose, critique, explain
WORLD MODELING (6): world-state, state-transition, causal-model, ground, resolve-identity, simulate
SYNTHESIS (3): generate, transform, integrate
EXECUTION (2): act, send
SAFETY (5): verify, checkpoint, rollback, constrain, audit
MEMORY (2): persist, recall
COORDINATION (3): delegate, synchronize, invoke
```

**Key Name Changes from Option 2**:
- `identify` → `classify` (clearer)
- `estimate` → `measure` (clearer)
- `forecast` → `predict` (standard)
- `grounding` → `ground` (verb form)
- `identity-resolution` → `resolve-identity` (verb-first)
- `invoke-workflow` → `invoke` (simpler)
- Remove: `model-schema` (tool-specific)
- Remove: `detect-anomaly`, `estimate-risk`, `act-plan` (no exceptions)

**Pros**:
- Aligned with industry (MCP, LangChain)
- No special-case exceptions
- Clearer naming
- Defensibility: HIGH (based on empirical patterns)

**Cons**:
- Departs from DIS foundation (but DIS wasn't a strong foundation anyway)
- 35 is also "arbitrary" (but defensible as "what agents actually do")

---

### Option 4: Minimal Core 25 (Most Aggressive Reduction)

**Philosophy**: Absolute minimum for agentic behavior.

| Metric | Value |
|--------|-------|
| Capability count | 25 |
| Foundation | Essential operations only |
| Specializations | 0 |

**Structure**:
```
PERCEPTION (4): retrieve, search, inspect, receive
UNDERSTANDING (4): detect, classify, measure, predict
REASONING (3): plan, compare, explain
WORLD MODELING (3): world-state, ground, simulate
SYNTHESIS (3): generate, transform, integrate
EXECUTION (2): act, send
SAFETY (3): verify, checkpoint, rollback
MEMORY (2): persist, recall
COORDINATION (1): delegate
```

**What's removed from Option 3**:
- `discover` (= detect with exploration)
- `decompose` (= plan with hierarchy)
- `critique` (= compare against ideal)
- `state-transition`, `causal-model`, `resolve-identity` (advanced modeling)
- `constrain`, `audit` (can be workflows)
- `synchronize`, `invoke` (can be workflows)

**Pros**:
- Smallest defensible set
- Every capability is clearly necessary
- Easy to implement

**Cons**:
- May be too minimal for complex workflows
- Loses some useful abstractions
- Defensibility: HIGH but INCOMPLETE

---

## Decision Matrix

| Criterion | Option 1 (99) | Option 2 (39) | Option 3 (35) | Option 4 (25) |
|-----------|---------------|---------------|---------------|---------------|
| **Defensibility** | Low | Medium | High | High |
| **Industry alignment** | Low | Medium | High | High |
| **Completeness** | Unknown | Good | Good | Minimal |
| **Clarity** | Low | Medium | High | High |
| **No exceptions** | No | No (3) | Yes | Yes |
| **Migration effort** | None | High | High | High |
| **Risk of missing capability** | Low | Low | Low | Medium |

---

## Recommendation

### Primary: Option 3 (Tool-Aligned 35)

**Rationale**:
1. **Highest defensibility**: Based on empirical research of how agents work
2. **Industry-aligned**: Matches MCP, LangChain, ReAct patterns
3. **No exceptions**: Every capability follows the same rules
4. **Clear naming**: Verb-first, common terminology
5. **Complete enough**: Covers all known agent behaviors

### Secondary: Option 4 (Minimal 25)

If you want maximum rigor and are willing to accept that some behaviors are workflow patterns rather than capabilities.

### Not Recommended: Option 1 or 2

- Option 1: Known problems, no defensibility
- Option 2: Better than 1, but DIS foundation is weak and special cases feel arbitrary

---

## The 35 Capabilities (Recommended)

```yaml
PERCEPTION:
  - retrieve    # Pull specific data by ID/path
  - search      # Query by criteria
  - inspect     # Examine current state
  - receive     # Accept pushed data/events

UNDERSTANDING:
  - detect      # Find patterns/occurrences
  - classify    # Categorize and label
  - measure     # Quantify uncertain values
  - predict     # Forecast future states
  - compare     # Evaluate alternatives
  - discover    # Find unknown patterns

REASONING:
  - plan        # Create action sequence
  - decompose   # Break into subproblems
  - critique    # Identify weaknesses
  - explain     # Justify conclusions

WORLD_MODELING:
  - world-state       # Create state snapshot
  - state-transition  # Define dynamics
  - causal-model      # Cause-effect relationships
  - ground            # Anchor to evidence
  - resolve-identity  # Deduplicate entities
  - simulate          # Run what-if scenarios

SYNTHESIS:
  - generate    # Produce new content
  - transform   # Convert formats
  - integrate   # Merge sources

EXECUTION:
  - act         # Execute changes
  - send        # Transmit externally

SAFETY:
  - verify      # Check conditions
  - checkpoint  # Save state
  - rollback    # Restore state
  - constrain   # Enforce limits
  - audit       # Record provenance

MEMORY:
  - persist     # Store durably
  - recall      # Retrieve stored

COORDINATION:
  - delegate    # Assign to agent
  - synchronize # Achieve agreement
  - invoke      # Execute workflow
```

---

## Layer Renaming Consideration

The current layers could be renamed for clarity:

| Current | Proposed | Rationale |
|---------|----------|-----------|
| PERCEPTION | PERCEPTION | Keep (clear) |
| MODELING | UNDERSTANDING + WORLD_MODELING | Split for clarity |
| REASONING | REASONING | Keep (clear) |
| ACTION | EXECUTION + SYNTHESIS | Split for clarity |
| SAFETY | SAFETY | Keep (clear) |
| META | (merged into UNDERSTANDING) | "Meta" is vague |
| MEMORY | MEMORY | Keep (clear) |
| COORDINATION | COORDINATION | Keep (clear) |

This gives us **8 layers** still, but with clearer names:
1. PERCEPTION
2. UNDERSTANDING (was: part of MODELING)
3. REASONING
4. WORLD_MODELING (was: part of MODELING)
5. SYNTHESIS (was: part of ACTION)
6. EXECUTION (was: part of ACTION)
7. SAFETY
8. MEMORY
9. COORDINATION

Actually that's 9. Let's keep it at 8 by merging:

**Final 8 Layers**:
1. PERCEPTION (4 capabilities)
2. UNDERSTANDING (6 capabilities) - analysis operations
3. REASONING (4 capabilities) - planning operations
4. WORLD_MODELING (6 capabilities) - state representation
5. SYNTHESIS (3 capabilities) - content creation
6. EXECUTION (2 capabilities) - world changes
7. SAFETY (5 capabilities) - correctness guarantees
8. STATE (5 capabilities) - memory + coordination

Wait, that's 35 capabilities but the numbers don't add up. Let me recount:
- PERCEPTION: 4
- UNDERSTANDING: 6
- REASONING: 4
- WORLD_MODELING: 6
- SYNTHESIS: 3
- EXECUTION: 2
- SAFETY: 5
- MEMORY: 2
- COORDINATION: 3

Total: 35 ✓

So 9 layers. We could merge MEMORY + COORDINATION into STATE_MANAGEMENT:

**Final 8 Layers (35 capabilities)**:
1. PERCEPTION (4)
2. UNDERSTANDING (6)
3. REASONING (4)
4. WORLD_MODELING (6)
5. SYNTHESIS (3)
6. EXECUTION (2)
7. SAFETY (5)
8. STATE_MANAGEMENT (5) = persist, recall, delegate, synchronize, invoke

---

## Next Steps

If you approve **Option 3 (35 capabilities)**:

1. **Create new capability_ontology.json** with 35 capabilities
2. **Update layer names** to the proposed 8
3. **Create migration guide** from 99 → 35
4. **Update all documentation** with new structure
5. **Update skills/** directory with new capability names
6. **Run validation** to ensure workflows still work

If you want to discuss further, we can:
- Deep dive on any specific capability
- Debate any naming choice
- Consider hybrid approaches
- Validate against more workflows

---

## Appendix: Full Mapping from 99 to 35

| Old Capability | New Capability | Change Type |
|----------------|----------------|-------------|
| detect-entity | detect | PARAMETERIZE |
| detect-person | detect | PARAMETERIZE |
| detect-activity | detect | PARAMETERIZE |
| detect-attribute | detect | PARAMETERIZE |
| detect-world | detect | PARAMETERIZE |
| detect-anomaly | detect | PARAMETERIZE (no exception) |
| identify-* (all) | classify | RENAME + PARAMETERIZE |
| estimate-* (all) | measure | RENAME + PARAMETERIZE |
| estimate-risk | measure | PARAMETERIZE (no exception) |
| forecast-* (all) | predict | RENAME + PARAMETERIZE |
| compare-* (all) | compare | PARAMETERIZE |
| discover-* (all) | discover | PARAMETERIZE |
| generate-* (all) | generate | PARAMETERIZE |
| act-plan | act | MERGE (no exception) |
| validate | verify | MERGE (redundant) |
| decide | compare | MERGE (redundant) |
| prioritize | compare | MERGE (redundant) |
| grounding | ground | RENAME (verb form) |
| identity-resolution | resolve-identity | RENAME (verb-first) |
| invoke-workflow | invoke | RENAME (simpler) |
| model-schema | (removed) | REMOVE (tool-specific) |
| mitigate | (workflow) | DEMOTE |
| improve | (workflow) | DEMOTE |
| optimize | (workflow) | DEMOTE |
| digital-twin | (workflow) | DEMOTE |
