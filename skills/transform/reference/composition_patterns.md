# Composition Patterns

Documented workflow patterns showing how capabilities chain together. Extracted from `workflow_catalog.json`.

---

## Overview

Capabilities are designed to compose. This document provides:
1. **Common workflows** - Tested sequences of capabilities
2. **Data flow patterns** - How outputs feed into subsequent inputs
3. **Anti-patterns** - Combinations that should never occur
4. **Recovery patterns** - How to handle failures in sequences

---

## Workflow 1: Debug Code Change

**Goal:** Safely diagnose and fix a bug/regression in a codebase.

**Risk:** high (due to act-plan step)

### Sequence

```
inspect → search → map-relationships → model-schema → critique → plan → checkpoint → act-plan → verify → (PASS: audit) | (FAIL: rollback → critique)
```

### Detailed Steps

| Step | Capability | Purpose | Stores As | Risk |
|------|------------|---------|-----------|------|
| 1 | `inspect` | Observe failing behavior, logs, code paths | inspect_out | low |
| 2 | `search` | Find related code, configs, error patterns | search_out | low |
| 3 | `map-relationships` | Build dependency graph around failing component | map_relationships_out | low |
| 4 | `model-schema` | Define invariants/spec expectations | model_schema_out | low |
| 5 | `critique` | List likely failure modes + edge cases | critique_out | low |
| 6 | `plan` | Produce minimal fix plan with checkpoints | plan_out | low |
| 7 | `checkpoint` | Create safety checkpoint before mutation | checkpoint_out | medium |
| 8 | `act-plan` | Apply fix, run tests, produce diff | act_plan_out | **high** |
| 9 | `verify` | Run targeted verification, return PASS/FAIL | verify_out | medium |
| 10a | `audit` | (if PASS) Record what changed and why | audit_out | medium |
| 10b | `rollback` | (if FAIL) Revert safely to checkpoint | rollback_out | medium |

### Data Flow

```yaml
inspect_out.signals → search.query
search_out.matches → map-relationships.targets
map_relationships_out.graph → model-schema.entities
model_schema_out.invariants → critique.expectations
critique_out.findings → plan.constraints
plan_out.steps → act-plan.plan
checkpoint_out.id → act-plan.checkpoint_ref
act_plan_out.changes → verify.targets
verify_out.passed → (audit | rollback)
```

### Success Criteria

- Bug fixed or root cause isolated
- Verification PASS
- Audit trail produced

---

## Workflow 2: World Model Build

**Goal:** Construct a structured world model for a domain with dynamics and uncertainty.

**Risk:** low

### Sequence

```
retrieve → inspect → identity-resolution → world-state → state-transition → causal-model → uncertainty-model → provenance → grounding → simulation → summarize
```

### Detailed Steps

| Step | Capability | Purpose | Stores As | Risk |
|------|------------|---------|-----------|------|
| 1 | `retrieve` | Collect authoritative domain sources | retrieve_out | low |
| 2 | `inspect` | Observe system artifacts (docs, logs, sensors) | inspect_out | low |
| 3 | `identity-resolution` | Define entities and resolve aliases | identity_resolution_out | low |
| 4 | `world-state` | Define state variables and current estimates | world_state_out | low |
| 5 | `state-transition` | Define dynamics: transitions, triggers, guards | state_transition_out | low |
| 6 | `causal-model` | Define causal assumptions and intervention effects | causal_model_out | low |
| 7 | `uncertainty-model` | Attach uncertainty types and confidence | uncertainty_model_out | low |
| 8 | `provenance` | Establish lineage for claims and transformations | provenance_out | low |
| 9 | `grounding` | Anchor each model element to evidence references | grounding_out | low |
| 10 | `simulation` | Run scenarios to stress-test model | simulation_out | low |
| 11 | `summarize` | Produce decision-ready world model brief | summarize_out | low |

### Data Flow

```yaml
retrieve_out.sources → inspect.targets
inspect_out.entities → identity-resolution.candidates
identity_resolution_out.resolved → world-state.entities
world_state_out.variables → state-transition.state_space
state_transition_out.transitions → causal-model.edges
causal_model_out.graph → uncertainty-model.nodes
uncertainty_model_out.distributions → provenance.claims
provenance_out.lineage → grounding.targets
grounding_out.anchors → simulation.model
simulation_out.results → summarize.content
```

### Success Criteria

- Model is structured (YAML/JSON)
- Every claim is grounded
- Uncertainty explicitly represented
- Scenario results provided

---

## Workflow 3: Digital Twin Sync Loop

**Goal:** Synchronize digital twin state with incoming signals, detect drift, decide and execute safe actions.

**Risk:** high

### Sequence

```
receive → transform → integrate → identity-resolution → world-state → diff-world-state → state-transition → detect-anomaly → estimate-risk → forecast-risk → plan → constrain → checkpoint → act-plan → verify → (PASS: audit → summarize) | (FAIL: rollback → plan)
```

### Detailed Steps

| Step | Capability | Purpose | Risk |
|------|------------|---------|------|
| 1 | `receive` | Ingest new signals/events | low |
| 2 | `transform` | Normalize raw signals to canonical events | low |
| 3 | `integrate` | Merge events with existing twin snapshot | low |
| 4 | `identity-resolution` | Resolve entity aliases | low |
| 5 | `world-state` | Produce updated canonical snapshot | low |
| 6 | `diff-world-state` | Compute diff from previous snapshot | low |
| 7 | `state-transition` | Apply transition rules | low |
| 8 | `detect-anomaly` | Detect drift/anomalies | low |
| 9 | `estimate-risk` | Estimate risk impact | low |
| 10 | `forecast-risk` | Forecast near-term risk | low |
| 11 | `plan` | Plan safe actions to reduce risk | low |
| 12 | `constrain` | Enforce policy and least privilege | low |
| 13 | `checkpoint` | Create checkpoint before mutation | medium |
| 14 | `act-plan` | Execute action plan | **high** |
| 15 | `verify` | Verify outcome | medium |
| 16a | `audit` + `summarize` | (if PASS) Record and report | medium |
| 16b | `rollback` | (if FAIL) Revert to checkpoint | medium |

### Gates and Conditions

```yaml
act-plan:
  condition: ${constrain_out.compliant} == true
  gate: ${checkpoint_out.checkpoint_id} != null
  skip_if_false: true

verify:
  gate: ${verify_out.passed} == false → rollback
```

### Recovery Pattern

```yaml
on_verify_fail:
  action: rollback
  then: goto plan
  inject_context:
    failure_evidence: ${verify_out.violations}
  max_loops: 3
```

---

## Workflow 4: Capability Gap Analysis

**Goal:** Assess a project to identify missing capabilities and propose new skills.

**Risk:** medium

### Sequence

```
inspect → map-relationships → discover-relationship → compare-plans → prioritize → generate-plan → audit
```

### Detailed Steps

| Step | Capability | Purpose | Risk |
|------|------------|---------|------|
| 1 | `inspect` | Read project docs and current skill coverage | low |
| 2 | `map-relationships` | Map existing workflows vs capabilities | low |
| 3 | `discover-relationship` | Find hidden dependencies | low |
| 4 | `compare-plans` | Compare alternative skill architectures | low |
| 5 | `prioritize` | Rank missing capabilities by leverage | low |
| 6 | `generate-plan` | Generate implementation plan for new skills | low |
| 7 | `audit` | Record rationale + decision lineage | medium |

### Success Criteria

- Missing capability list produced
- Prioritized backlog created
- Proposed skill specs generated

---

## Workflow 5: Digital Twin Bootstrap

**Goal:** Initialize a digital twin from scratch then run a first sync loop.

**Risk:** high

### Sequence

```
invoke-workflow(world_model_build) → invoke-workflow(digital_twin_sync_loop)
```

### Detailed Steps

| Step | Capability | Purpose | Condition |
|------|------------|---------|-----------|
| 1 | `invoke-workflow` | Build initial world model baseline | ${world_state_out} == null |
| 2 | `invoke-workflow` | Run initial sync loop using baseline | always |

---

## Common Patterns

### Pattern: Checkpoint-Act-Verify-Rollback (CAVR)

Standard safety pattern for any mutating workflow:

```
checkpoint → act-plan → verify → (PASS: continue) | (FAIL: rollback)
```

**Rules:**
- NEVER call act-plan without prior checkpoint
- ALWAYS verify after act-plan
- rollback if verify returns FAIL

### Pattern: Observe-Model-Act (OMA)

Standard agentic loop:

```
inspect/detect/search → identify/estimate/forecast → plan → act-plan
```

### Pattern: Enrichment Pipeline

Parallel data gathering:

```
[retrieve || inspect || search] → integrate → identity-resolution
```

### Pattern: Risk Assessment

Sequential risk analysis:

```
detect-anomaly → estimate-risk → forecast-risk → plan → constrain
```

---

## Anti-Patterns

### CRITICAL: Never Do These

| Anti-Pattern | Risk | Why | Correct Pattern |
|--------------|------|-----|-----------------|
| `act-plan` without `checkpoint` | CRITICAL | No recovery possible | `checkpoint → act-plan` |
| `rollback` without `checkpoint` | CRITICAL | Nothing to rollback to | Ensure checkpoint exists |
| `send` without `constrain` | HIGH | No policy enforcement | `constrain → send` |
| `act-plan` without `verify` | HIGH | No validation of outcome | `act-plan → verify` |
| `verify` without evidence | MEDIUM | Ungrounded verification | Populate evidence_anchors |
| Direct mutations after `verify` FAIL | CRITICAL | State may be corrupted | `rollback` first |

### Warning Patterns

| Pattern | Risk | When Acceptable |
|---------|------|-----------------|
| Skipping `critique` before `plan` | MEDIUM | Only for trivial, well-understood changes |
| Skipping `audit` after `act-plan` | MEDIUM | Only for reversible, low-impact changes |
| Multiple `act-plan` without intermediate `checkpoint` | HIGH | Never acceptable |

---

## Capability Dependencies

### Hard Dependencies (requires)

```yaml
act-plan:
  requires: [plan, checkpoint]

causal-model:
  requires: [world-state]

diff-world-state:
  requires: [world-state]

digital-twin:
  requires: [world-state, state-transition, provenance]

rollback:
  requires: [checkpoint, audit]

send:
  requires: [constrain, checkpoint]

state-transition:
  requires: [world-state]

verify:
  requires: [model-schema]
```

### Soft Dependencies (soft_requires)

```yaml
act-plan:
  soft_requires: [verify, constrain]

diff-world-state:
  soft_requires: [provenance]

digital-twin:
  soft_requires: [uncertainty-model, detect-anomaly]

integrate:
  soft_requires: [provenance, identity-resolution]

invoke-workflow:
  soft_requires: [audit]

simulation:
  soft_requires: [causal-model, state-transition]

verify:
  soft_requires: [plan]
```

---

## Usage in Skills

Reference this document in the Composition Patterns section of each skill:

```markdown
## Composition Patterns

**Commonly follows:**
- `checkpoint` - Required before any mutation (see CAVR pattern)
- `plan` - Provides the execution blueprint

**Commonly precedes:**
- `verify` - Must verify outcomes (see CAVR pattern)
- `audit` - Record what was done

**Anti-patterns:**
- Never call without prior `checkpoint` (CRITICAL)
- Never skip `verify` after execution

**Workflow references:**
- See `composition_patterns.md#debug-code-change` for usage in debug context
- See `composition_patterns.md#digital-twin-sync-loop` for twin sync context
```
