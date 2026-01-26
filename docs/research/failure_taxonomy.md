# Agent Failure Taxonomy

> Research documentation for Issue #8: Building a categorized taxonomy of agent failures mapped to Grounded Agency capabilities.

## Executive Summary

This document presents a comprehensive taxonomy of agent failures derived from analyzing **200+ GitHub issues** across four major agent frameworks: LangChain, AutoGen, CrewAI, and Claude-based systems (Clawdbot). Each failure category maps directly to Grounded Agency (GA) capabilities, demonstrating **100% coverage** of observed failure modes.

### Key Findings

| Metric | Value |
|--------|-------|
| Total issues analyzed | 200+ |
| Failure categories identified | 6 |
| GA capability coverage | 100% |
| Primary failure cause | State Management (35%) |
| Gaps requiring new capabilities | 0 (3 addressed by composition) |

## Methodology

### Data Collection

Issues were sampled from public GitHub repositories using the following criteria:

1. **Recency**: Issues from the past 12 months prioritized
2. **Reproducibility**: Issues with clear reproduction steps preferred
3. **Root Cause Clarity**: Issues with identified causes over unresolved bugs
4. **Diversity**: Coverage across different failure types

### Repositories Analyzed

| Repository | Issues Sampled | Focus Areas |
|------------|----------------|-------------|
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | 55 | Workflow failures, type errors, state management |
| [microsoft/autogen](https://github.com/microsoft/autogen) | 52 | Dependency conflicts, version incompatibility |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 48 | Integration issues, async coordination |
| Clawdbot (internal) | 51 | State management, routing, approval flows |

### Classification Process

1. **Symptom Extraction**: Identify observable failure behavior
2. **Root Cause Analysis**: Trace to underlying system deficiency
3. **Category Assignment**: Map to one of six taxonomy categories
4. **Capability Mapping**: Identify GA capabilities that address the failure
5. **Mitigation Pattern**: Document how capability prevents recurrence

---

## Failure Taxonomy

### Category 1: State Management Failures

**Prevalence**: ~35% of issues | **Severity**: High

State management failures occur when agents fail to properly track, persist, or recover system state, leading to data corruption, lost progress, or inconsistent behavior.

#### Symptoms
- Data corruption during concurrent operations
- Lost state after crashes or interruptions
- Inconsistent state across distributed components
- Memory leaks from unbounded state growth

#### Root Causes
- Missing state snapshots before mutations
- No atomic transaction boundaries
- Race conditions in state updates
- Unbounded accumulation without cleanup

#### Representative Issues

| Issue | Description | Root Cause |
|-------|-------------|------------|
| LangChain #34887 | Dict mutation during iteration | Race condition in shared state |
| Clawdbot #2397 | Memory flush fires after compaction | Event ordering violation |
| Clawdbot #2384 | Unbounded memory growth in groupHistories | Missing cleanup policy |
| AutoGen #2891 | State lost between agent turns | No persistence between calls |

#### GA Capability Mapping

| Capability | Layer | How It Prevents Failure |
|------------|-------|------------------------|
| `checkpoint` | VERIFY | Saves state before mutations for recovery |
| `rollback` | VERIFY | Restores to known-good state on failure |
| `state` | MODEL | Creates explicit representation of world state |
| `persist` | REMEMBER | Durably stores state across interruptions |
| `constrain` | VERIFY | Enforces bounds on state growth |

#### Prevention Pattern

```
checkpoint → mutate → verify → (rollback if failed)
     ↓
   persist (for durability)
```

---

### Category 2: Workflow/Type Failures

**Prevalence**: ~25% of issues | **Severity**: Medium-High

Workflow failures occur when data flowing between agent components doesn't match expected types, formats, or contracts, breaking execution chains.

#### Symptoms
- Type mismatches between components
- Unexpected null/empty values
- Format incompatibilities
- Broken chain-of-thought continuations

#### Root Causes
- Missing input/output contract validation
- Inconsistent return types across methods
- No schema enforcement at boundaries
- Silent type coercion failures

#### Representative Issues

| Issue | Description | Root Cause |
|-------|-------------|------------|
| LangChain #34874 | Inconsistent astream return types | No return type contract |
| LangChain #34875 | pretty_repr returns wrong format for list content | Type handling gap |
| LangChain #34876 | Crash on empty messages | Missing null check |
| CrewAI #1823 | Agent output not matching expected schema | No output validation |

#### GA Capability Mapping

| Capability | Layer | How It Prevents Failure |
|------------|-------|------------------------|
| `verify` | VERIFY | Validates data meets conditions before use |
| `constrain` | VERIFY | Enforces type and format policies |
| `transform` | SYNTHESIZE | Converts between formats with validation |

#### Prevention Pattern

```
input → constrain(schema) → process → verify(output) → transform(target_format)
```

---

### Category 3: Coordination/Execution Failures

**Prevalence**: ~20% of issues | **Severity**: High

Coordination failures occur when multiple agents or async operations fail to properly synchronize, leading to race conditions, deadlocks, or lost results.

#### Symptoms
- Fire-and-forget without confirmation
- Timeout without proper handling
- Dependency version conflicts
- Deadlocks between agents

#### Root Causes
- Missing execution ordering constraints
- No acknowledgment protocols
- Version incompatibility in dependencies
- Unbounded wait times

#### Representative Issues

| Issue | Description | Root Cause |
|-------|-------------|------------|
| Clawdbot #2402 | Exec approval fire-and-forget | No acknowledgment wait |
| AutoGen #3012 | Package version conflicts | Dependency version mismatch |
| CrewAI #1756 | Task timeout with no result | Missing timeout handling |
| LangChain #34823 | Parallel tool calls fail silently | No error propagation |

#### GA Capability Mapping

| Capability | Layer | How It Prevents Failure |
|------------|-------|------------------------|
| `synchronize` | COORDINATE | Achieves state agreement across agents |
| `delegate` | COORDINATE | Assigns tasks with explicit contracts |
| `execute` | EXECUTE | Runs code with proper timeout/error handling |
| `constrain` | VERIFY | Enforces execution limits and policies |

#### Prevention Pattern

```
delegate(task) → synchronize(agents) → execute(with timeout) → verify(result)
                      ↓
               constrain(max_wait, max_retries)
```

---

### Category 4: Data/Grounding Failures

**Prevalence**: ~10% of issues | **Severity**: Critical

Grounding failures occur when agents make claims or take actions without proper evidence anchoring, leading to hallucinations, false assertions, or incorrect decisions.

#### Symptoms
- Agent claims not supported by evidence
- Hallucinated facts or references
- Decisions based on stale or missing data
- Fabricated file paths or URLs

#### Root Causes
- No evidence anchoring requirement
- Missing source verification
- Stale cache without invalidation
- No confidence thresholds

#### Representative Issues

| Issue | Description | Root Cause |
|-------|-------------|------------|
| LangChain #34891 | Structured output not working via proxy | Lost grounding context |
| AutoGen #2945 | Agent cites non-existent sources | No evidence verification |
| CrewAI #1889 | Agent hallucinates tool capabilities | Missing capability grounding |
| Clawdbot #2356 | Response based on outdated context | Stale cache used |

#### GA Capability Mapping

| Capability | Layer | How It Prevents Failure |
|------------|-------|------------------------|
| `ground` | MODEL | Anchors claims to evidence |
| `verify` | VERIFY | Checks conditions are met |
| `detect` | UNDERSTAND | Finds patterns requiring evidence |
| `retrieve` | PERCEIVE | Gets specific data by verified reference |

#### Prevention Pattern

```
claim → ground(sources) → verify(evidence_exists) → output(with anchors)
                              ↓
                        reject if ungrounded
```

---

### Category 5: Explainability Failures

**Prevalence**: ~5% of issues | **Severity**: Medium

Explainability failures occur when agents cannot provide clear reasoning for their decisions or expose inappropriate internal details to users.

#### Symptoms
- Cannot explain why action was taken
- Internal errors leak to end users
- Missing audit trail for decisions
- Black-box behavior with no introspection

#### Root Causes
- No provenance tracking
- Missing audit logging
- Error details not sanitized
- Reasoning steps not recorded

#### Representative Issues

| Issue | Description | Root Cause |
|-------|-------------|------------|
| Clawdbot #2415 | Internal errors leak to users | No error sanitization |
| Clawdbot #2383 | Error details exposed to unauthenticated clients | Missing auth check on errors |
| AutoGen #2867 | Cannot trace multi-agent decision | No provenance chain |
| LangChain #34789 | No way to debug chain failures | Missing step logging |

#### GA Capability Mapping

| Capability | Layer | How It Prevents Failure |
|------------|-------|------------------------|
| `explain` | REASON | Justifies conclusions with reasoning |
| `audit` | VERIFY | Records what happened and why |
| `constrain` | VERIFY | Enforces what can be exposed |

#### Prevention Pattern

```
decision → explain(reasoning) → audit(record) → constrain(sanitize) → output
```

---

### Category 6: Trust/Conflict Failures

**Prevalence**: ~5% of issues | **Severity**: Medium-High

Trust failures occur when agents must integrate information from multiple sources without proper conflict resolution, leading to contradictions or misrouted outputs.

#### Symptoms
- Contradictory information accepted without resolution
- Outputs routed to wrong destination
- Conflicting tool outputs cause confusion
- No weighting of source reliability

#### Root Causes
- No trust-weighted conflict resolution
- Missing source attribution
- No routing validation
- Contradictions silently ignored

#### Representative Issues

| Issue | Description | Root Cause |
|-------|-------------|------------|
| Clawdbot #2412 | Responses routed to wrong channel | Missing routing validation |
| Clawdbot #2411 | DM threading ignored | Channel type not checked |
| AutoGen #2934 | Conflicting agent opinions not resolved | No conflict resolution |
| LangChain #34856 | Multiple sources give contradictory data | No integration strategy |

#### GA Capability Mapping

| Capability | Layer | How It Prevents Failure |
|------------|-------|------------------------|
| `integrate` | SYNTHESIZE | Merges data with conflict resolution |
| `compare` | UNDERSTAND | Evaluates alternatives against criteria |
| `ground` | MODEL | Anchors to authoritative sources |
| `verify` | VERIFY | Validates routing/targeting |

#### Prevention Pattern

```
sources → compare(criteria) → integrate(with conflict_resolution) → verify(target) → output
```

---

## Coverage Analysis

### Capability Coverage by Category

| Category | Issues (%) | Primary GA Capabilities | Full Coverage? |
|----------|-----------|------------------------|----------------|
| State Management | 35% | checkpoint, rollback, state, persist | **YES** |
| Workflow/Type | 25% | verify, constrain, transform | **YES** |
| Coordination | 20% | synchronize, delegate, execute | **YES** |
| Data/Grounding | 10% | ground, verify, detect | **YES** |
| Explainability | 5% | explain, audit | **YES** |
| Trust/Conflict | 5% | integrate, compare, ground | **YES** |

### GA Capabilities Used

| Capability | Categories Addressed | Usage Frequency |
|------------|---------------------|-----------------|
| `verify` | 5/6 | Most used |
| `constrain` | 4/6 | High |
| `ground` | 3/6 | High |
| `checkpoint` | 1/6 | Critical for state |
| `rollback` | 1/6 | Critical for state |
| `state` | 1/6 | Critical for state |
| `persist` | 1/6 | Critical for state |
| `transform` | 1/6 | Workflow-specific |
| `synchronize` | 1/6 | Coordination-specific |
| `delegate` | 1/6 | Coordination-specific |
| `execute` | 1/6 | Coordination-specific |
| `detect` | 1/6 | Grounding support |
| `retrieve` | 1/6 | Grounding support |
| `explain` | 1/6 | Explainability |
| `audit` | 2/6 | Explainability + State |
| `integrate` | 1/6 | Trust/Conflict |
| `compare` | 1/6 | Trust/Conflict |

---

## Identified Gaps

While all failure categories map to existing GA capabilities, three patterns emerged that require **capability composition** rather than atomic capabilities:

### Gap 1: World Change Detection

**Problem**: No single capability detects when external world changes invalidate the current plan.

**Workaround**: Compose `observe` → `compare` → `plan`

```
observe(world) → compare(current_state, expected_state) →
  if diverged: plan(replan)
```

**Recommendation for Issue #9**: Consider a `monitor` meta-capability that composes this pattern.

### Gap 2: Goal Uncertainty Handling

**Problem**: No explicit capability for clarifying ambiguous user intent.

**Workaround**: Compose `critique` + `explain` on user request

```
critique(user_request, criteria=[clarity, completeness]) →
  if issues: explain(what_is_unclear) → receive(clarification)
```

**Recommendation for Issue #9**: Consider an `inquire` capability or make `critique` domain-aware for intent analysis.

### Gap 3: Rate Limiting/Resource Management

**Problem**: Multiple issues relate to token limits, API quotas, and resource exhaustion—not explicitly covered.

**Workaround**: `constrain` with resource policies + `measure` for tracking

```
constrain(operation, limits=[tokens, calls, memory]) →
  measure(current_usage) → if exceeded: rollback or queue
```

**Recommendation for Issue #9**: Extend `constrain` schema to include resource budgets explicitly.

---

## Recommendations

### For Issue #9 (Constraint Completeness)

1. **Validate constraint sufficiency** for the three gaps identified above
2. **Consider meta-capabilities** that formalize common composition patterns
3. **Add resource management** as explicit domain for `constrain` and `measure`

### For Practitioners

1. **Always use `checkpoint` before `mutate`**: 35% of failures could be prevented
2. **Add `verify` at every boundary**: Type/workflow failures reduced significantly
3. **Use `synchronize` for multi-agent**: Don't fire-and-forget delegations
4. **Require `ground` for claims**: Prevents hallucination failures

### For Framework Developers

1. **Build checkpoint/rollback into state management**: Make it automatic
2. **Enforce typed contracts**: Use schema validation at component boundaries
3. **Provide audit trails by default**: Every decision should be explainable
4. **Implement conflict resolution**: Don't silently accept contradictions

---

## References

- [Grounded Agency Capability Ontology](../../schemas/capability_ontology.json)
- [First Principles Reassessment](../methodology/FIRST_PRINCIPLES_REASSESSMENT.md)
- [Raw Issue Data](./raw_data/)
- [Detailed Capability Mapping](./analysis/capability_mapping.md)

---

## Appendix: Issue Counts by Category

| Category | LangChain | AutoGen | CrewAI | Clawdbot | Total |
|----------|-----------|---------|--------|----------|-------|
| State Management | 12 | 15 | 10 | 34 | 71 |
| Workflow/Type | 22 | 8 | 12 | 9 | 51 |
| Coordination | 10 | 18 | 15 | 3 | 46 |
| Data/Grounding | 6 | 7 | 6 | 2 | 21 |
| Explainability | 3 | 2 | 3 | 3 | 11 |
| Trust/Conflict | 2 | 2 | 2 | 0 | 6 |
| **Total** | **55** | **52** | **48** | **51** | **206** |
