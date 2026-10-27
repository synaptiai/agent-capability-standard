# Composition Patterns

Documented workflow patterns showing how capabilities chain together. The workflows are taken from `schemas/workflow_catalog.yaml` (the source of truth for step order, `store_as` names, bindings, gates and conditions); risk levels and dependency edges come from `schemas/capability_ontology.yaml`.

---

## Overview

Capabilities are designed to compose. This document provides:
1. **Common workflows** - Tested sequences of capabilities
2. **Data flow patterns** - How outputs feed into subsequent inputs
3. **Anti-patterns** - Combinations that should never occur
4. **Recovery patterns** - How to handle failures in sequences

**Reading the tables:**
- **Risk** is the capability's risk in the ontology. Where the workflow step declares a stricter level, it is shown as `low (step: medium)`; a stricter step value takes effect, a weaker one is ignored (W602).
- **Data flow** lists each step's `input_bindings` as `source → capability.input`. Type annotations in the catalog (`${x.y: array<object>}`) are omitted; quoted values are literals.
- Every step output is stored under its `store_as` name and may be referenced by any later step (`data_flow: step_outputs_are_addressable`), so an output that no binding below consumes is still available.

---

## Debug Code Change

Catalog id: `debug_code_change`

**Goal:** Safely diagnose and fix a bug/regression in a codebase.

**Risk:** medium declared; computed high (`risk_propagation: max_step_risk`, from the `execute` step)

**Inputs:** `bug` (required; `component`, `symptom`, `fix_command`), `user_input` (`domain`, `constraints`), `previous_world_state`, `world_state_out`

### Sequence

```
observe → search → attribute → constrain → critique → plan → checkpoint → execute → verify → audit → rollback (skipped when verify passed)
```

### Detailed Steps

| Step | Capability | Purpose | Stores As | Risk |
|------|------------|---------|-----------|------|
| 1 | `observe` | Observe failing behavior, logs, and relevant code paths | observe_out | low |
| 2 | `search` | Find related code, configs, and error patterns | search_out | low |
| 3 | `attribute` (domain: dependencies) | Build dependency graph and identify causal relationships around failing component | attribute_out | low |
| 4 | `constrain` | Define invariants/spec expectations for the component | constrain_out | low |
| 5 | `critique` | List likely failure modes + edge cases | critique_out | low |
| 6 | `plan` | Produce minimal fix plan with checkpoints | plan_out | low |
| 7 | `checkpoint` | Create checkpoint before mutation | checkpoint_out | low (step: medium) |
| 8 | `execute` | Apply fix, run tests, and produce diff summary | execute_out | medium (step: **high**) |
| 9 | `verify` | Run targeted verification and return PASS/FAIL | verify_out | low (step: medium) |
| 10 | `audit` | Record what changed and why | audit_out | low (step: medium) |
| 11 | `rollback` | If verify FAIL, revert safely (gated: skipped when verify passed) | rollback_out | medium |

**Safety flags:** the `execute` step raises the ontology's `mutation` and `requires_checkpoint` to `true` (`requires_approval: true` is the ontology's own), so the `checkpoint` at step 7 is mandatory (F501 without it). `rollback` requires a prior `checkpoint` through the ontology's `requires` edge. The `audit` step declares `mutation: false` (allowed: `audit` is `mutation_overridable`).

### Data Flow

```text
${bug.component}                                      → observe.target
${bug.symptom}                                        → search.query
${bug.symptom}                                        → attribute.effect
${bug.component}                                      → constrain.target
["existing_tests_pass", "public_interfaces_unchanged"] → constrain.constraints
${attribute_out.causes}                               → critique.target
"Fix ${bug.symptom} in ${bug.component}"              → plan.goal
${user_input.constraints}                             → plan.constraints
${bug.component}                                      → checkpoint.scope
${bug.fix_command}                                    → execute.code
${bug.component}                                      → verify.target
["tests_pass", "symptom_resolved"]                    → verify.conditions
{type: "debug_code_change", component: ${bug.component},
 plan: ${plan_out.steps}, verified: ${verify_out.passed}} → audit.event
${checkpoint_out.checkpoint_id}                       → rollback.checkpoint_id
```

### Gates and Conditions

```yaml
rollback:
  gates:
  - when: ${verify_out.passed} == true
    action: skip
    message: The fix passed verification. No rollback needed.
```

Timeouts: `execute` 5m, `verify` 5m. `verify` retries up to 3 times with exponential backoff.

### Recovery Pattern

```yaml
observe:
  failure_modes:
  - condition: No relevant signals found
    action: request_more_context
    recovery: Ask for reproduction steps or additional artifacts.

execute:
  failure_modes:
  - condition: Unexpected side effects
    action: pause_and_checkpoint
    recovery: Checkpoint and require human approval.

verify:
  failure_modes:
  - condition: Verdict == FAIL
    action: rollback
    recovery: Rollback, then return to critique/plan with new evidence.
```

### Success Criteria

- Bug fixed or root cause isolated
- Verification PASS
- Audit trail produced

---

## World Model Build

Catalog id: `world_model_build`

**Goal:** Construct a structured world model for a domain (real or digital) with dynamics and uncertainty.

**Risk:** low (computed low)

**Inputs:** `user_input` (`domain`, `constraints`), `previous_world_state`, `world_state_out`

### Sequence

```
retrieve → observe → detect → classify → integrate → state → transition → attribute → measure → audit → ground → simulate → explain
```

Identity resolution (a single v1 capability) is the composition `detect` (domain: entity) → `classify` → `integrate`.

### Detailed Steps

| Step | Capability | Purpose | Stores As | Risk |
|------|------------|---------|-----------|------|
| 1 | `retrieve` | Collect authoritative domain sources and constraints | retrieve_out | low |
| 2 | `observe` | Observe current system/world artifacts (docs, logs, sensors) | observe_out | low |
| 3 | `detect` (domain: entity) | Detect entities across sources | detect_out | low |
| 4 | `classify` | Classify detected entities and resolve types | classify_out | low |
| 5 | `integrate` | Merge entity data and resolve identity across sources | integrate_out | low |
| 6 | `state` | Define state variables and current estimates | state_out | low |
| 7 | `transition` | Define dynamics: transitions, triggers, guards | transition_out | low |
| 8 | `attribute` (domain: causation) | Define causal assumptions and intervention effects | attribute_out | low |
| 9 | `measure` (domain: uncertainty) | Attach uncertainty types and confidence | measure_out | low |
| 10 | `audit` | Establish lineage for claims and transformations | audit_out | low |
| 11 | `ground` | Anchor each model element to evidence references | ground_out | low |
| 12 | `simulate` | Run scenarios to stress-test model and identify fragility | simulate_out | low |
| 13 | `explain` | Produce a decision-ready world model brief | explain_out | low |

### Data Flow

```text
${user_input.domain}                          → retrieve.target
${user_input.domain}                          → observe.target
${retrieve_out.data}                          → detect.data
"entity"                                      → detect.pattern
${detect_out.matches}                         → classify.item
[${detect_out.matches}, ${classify_out.labels}] → integrate.sources
${user_input.domain}                          → state.scope
${integrate_out.merged}                       → state.observations
${state_out.state}                            → transition.from_state
${transition_out.effects}                     → attribute.effect
${state_out.state}                            → measure.target
"uncertainty"                                 → measure.metric
{type: "world_model_build", domain: ${user_input.domain},
 entities: ${state_out.entities}}             → audit.event
"The states, transitions and causes of the ${user_input.domain} model
 are supported by the retrieved sources"      → ground.claim
{state: ${state_out.state},
 rules: ${transition_out.rules}}              → simulate.scenario
{model: ${state_out.state}, grounded: ${ground_out.grounded},
 scenarios: ${simulate_out.outcomes}}         → explain.conclusion
```

### Gates and Conditions

None. The only failure mode is on `observe`: "No relevant signals found" → `request_more_context` (ask for reproduction steps or additional artifacts).

### Success Criteria

- Model is structured (YAML/JSON)
- Every claim is grounded
- Uncertainty explicitly represented
- Scenario results provided

---

## Digital Twin Sync Loop

Catalog id: `digital_twin_sync_loop`

**Goal:** Synchronize digital twin state with incoming signals, detect drift, decide and execute safe actions, and record provenance.

**Risk:** high

**Inputs:** `user_input` (`domain`, `constraints`), `previous_world_state`, `world_state_out`

### Sequence

```
receive → search → transform → integrate → detect(entity) → classify → state → compare(state_diff) → transition → detect(anomaly) → measure(risk) → predict(risk) → plan → constrain → checkpoint → mutate → execute → verify → audit → rollback (skipped when verify passed) → explain
```

### Detailed Steps

| Step | Capability | Purpose | Stores As | Risk |
|------|------------|---------|-----------|------|
| 1 | `receive` | Ingest new signals/events from sources (logs/APIs/messages) | receive_out | low |
| 2 | `search` | Parallel enrichment: search for existing twin snapshot or relevant context while ingesting events (`parallel_group: context_gathering`, `join: all_complete`) | search_out | low |
| 3 | `transform` | Normalize raw signals into canonical events compatible with state.observations | transform_out | low |
| 4 | `integrate` | Merge canonical events with existing twin snapshot; resolve conflicts via strategy | integrate_out | low |
| 5 | `detect` (domain: entity) | Detect entities in integrated data | detect_entity_out | low |
| 6 | `classify` | Classify and resolve entity identities | classify_out | low |
| 7 | `state` | Produce updated canonical world-state snapshot with uncertainty + provenance | state_out | low |
| 8 | `compare` (domain: state_diff) | Compute diff between previous snapshot and updated snapshot | compare_state_out | low |
| 9 | `transition` | Apply transition rules triggered by new observations; compute next states | transition_out | low |
| 10 | `detect` (domain: anomaly) | Detect drift/anomalies between expected and observed state | detect_anomaly_out | low |
| 11 | `measure` (domain: risk) | Estimate risk impact/probability from drift and transitions | measure_risk_out | low |
| 12 | `predict` (domain: risk) | Forecast near-term risk trajectory and triggers | predict_out | low |
| 13 | `plan` | Plan safe action(s) to reduce risk, with verification criteria and rollback plan | plan_out | low |
| 14 | `constrain` | Enforce policy and least privilege for planned actions | constrain_out | low |
| 15 | `checkpoint` | Create checkpoint marker before any mutation/side-effect step | checkpoint_out | low (step: medium) |
| 16 | `mutate` | Execute mutations from action plan (if approved) | mutate_out | **high** |
| 17 | `execute` | Run verification tests and commands | execute_out | medium |
| 18 | `verify` | Verify outcome: PASS/FAIL with evidence | verify_out | low (step: medium) |
| 19 | `audit` | Record provenance, tool usage, diffs, and decision rationale | audit_out | low (step: medium) |
| 20 | `rollback` | If verify FAIL or side effects detected, rollback to checkpoint (gated: skipped when verify passed) | rollback_out | medium |
| 21 | `explain` | Produce decision-ready sync report: drift, actions, verification, next steps | explain_out | low |

### Data Flow

```text
(no bindings)                                 → receive
${receive_out.source}                         → search.query
${receive_out.data}                           → transform.input
"canonical_event"                             → transform.target_format
[${transform_out.output}, ${previous_world_state}] → integrate.sources
"prefer_authoritative_sources"                → integrate.conflict_resolution
${integrate_out.merged}                       → detect(entity).data
"entity"                                      → detect(entity).pattern
${detect_entity_out.matches}                  → classify.item
${integrate_out.merged.observations}          → state.observations
${integrate_out.merged.meta.world_id}         → state.scope
[${previous_world_state}, ${state_out}]       → compare.options
${state_out.state}                            → transition.from_state
${state_out}                                  → detect(anomaly).data
"drift"                                       → detect(anomaly).pattern
${detect_anomaly_out}                         → measure.target
"risk"                                        → measure.metric
"near_term_risk"                              → predict.target
${predict_out}                                → plan.context
"Reduce the detected drift and risk"          → plan.goal
${plan_out.steps}                             → constrain.target
["least_privilege", "change_policy"]          → constrain.constraints
"twin_state"                                  → checkpoint.scope
"twin_state"                                  → mutate.target
{apply: ${plan_out.steps}}                    → mutate.operation
"run_verification_suite"                      → execute.code
["drift_resolved", "no_policy_violation"]     → verify.conditions
{type: "digital_twin_sync", mutated: ${mutate_out.success},
 verified: ${verify_out.passed}}              → audit.event
${checkpoint_out.checkpoint_id}               → rollback.checkpoint_id
{verified: ${verify_out.passed},
 rolled_back: ${rollback_out.restored}}       → explain.conclusion
```

`transform` uses `mapping_ref: schemas/transforms/transform_mapping_rawlog_to_observation.yaml` and its output conforms to `schemas/event_schema.yaml#/event`; `state` output conforms to `schemas/world_state_schema.yaml#/world_state`. `integrate` resolves conflicts with `prefer_authoritative_sources` (alternatives: `prefer_recent`, `prefer_high_confidence`, `merge_with_uncertainty`, `escalate_to_human`).

### Gates and Conditions

```yaml
mutate:
  condition: ${constrain_out.compliant} == true
  skip_if_false: true
  gates:
  - when: ${checkpoint_out.checkpoint_id} == null
    action: stop
    message: No checkpoint created. Do not mutate.

verify:
  gates:
  - when: ${verify_out.passed} == false
    phase: after
    action: rollback
    message: Verification failed. Rolling back.

rollback:
  gates:
  - when: ${verify_out.passed} == true
    action: skip
    message: The twin passed verification. No rollback needed.
```

Timeouts: `mutate`, `execute` and `verify` 5m. `receive` and `verify` retry up to 3 times with exponential backoff. The workflow declares `workflow_extensions` for input bindings, conditions, parallel groups, recovery loops and gates.

### Recovery Pattern

```yaml
verify:
  failure_modes:
  - condition: Verdict == FAIL
    when: ${verify_out.passed} == false
    action: rollback
    recovery:
      goto_step: plan_out
      inject_context:
        failure_evidence: ${verify_out.violations}
      max_loops: 3
```

Other failure modes: `receive` "No messages/events available" → `stop`; `integrate` "Conflicts exceed threshold" → `request_more_context`; `mutate` "Unexpected side effects" → `pause_and_checkpoint` (require human approval to proceed).

### Success Criteria

- Twin snapshot updated and grounded
- Drift assessed with risk score
- Any actions are approved/checkpointed/verified
- Audit trail produced

---

## Capability Gap Analysis

Catalog id: `capability_gap_analysis`

**Goal:** Assess a project/system to identify missing capabilities and propose new skills.

**Risk:** low declared; computed medium (`risk_propagation: max_step_risk`, from the `audit` step)

**Inputs:** `user_input` (`domain`, `constraints`), `previous_world_state`, `world_state_out`

### Sequence

```
observe → attribute → discover → compare(architecture) → compare(priority) → generate → audit
```

### Detailed Steps

| Step | Capability | Purpose | Stores As | Risk |
|------|------------|---------|-----------|------|
| 1 | `observe` | Read project docs and current skill coverage | observe_out | low |
| 2 | `attribute` (domain: dependencies) | Map existing workflows vs capabilities | attribute_out | low |
| 3 | `discover` | Find hidden dependencies or unmodeled interactions | discover_out | low |
| 4 | `compare` (domain: architecture) | Compare alternative skill architectures | compare_architecture_out | low |
| 5 | `compare` (domain: priority) | Rank missing capabilities by leverage and risk reduction | compare_priority_out | low |
| 6 | `generate` (domain: plan) | Generate an implementation plan for new skills | generate_out | low |
| 7 | `audit` | Record rationale + decision lineage | audit_out | low (step: medium) |

### Data Flow

```text
${user_input.domain}                          → observe.target
${observe_out.observation}                    → attribute.effect
${attribute_out.causes}                       → discover.data
${discover_out.patterns}                      → compare(architecture).options
${compare_architecture_out.ranking}           → compare(priority).options
["leverage", "risk_reduction"]                → compare(priority).criteria
{gaps: ${compare_priority_out.ranking},
 architecture: ${compare_architecture_out.recommendation}} → generate.specification
{type: "capability_gap_analysis", ranking: ${compare_priority_out.ranking},
 plan: ${generate_out.content}}               → audit.event
```

### Gates and Conditions

None. The only failure mode is on `observe`: "No relevant signals found" → `request_more_context`.

### Success Criteria

- Missing capability list
- Prioritized backlog
- Proposed skill specs

---

## Digital Twin Bootstrap

Catalog id: `digital_twin_bootstrap`

**Goal:** Initialize a digital twin from scratch then run a first sync loop.

**Risk:** high (each step is an `invoke` of risk medium; the invoked `digital_twin_sync_loop` is high)

**Inputs:** `user_input` (`domain`, `constraints`), `previous_world_state`, `world_state_out` (an existing world state; when given, the build is skipped)

### Sequence

```
${world_state_out} == null:  invoke(world_model_build) → invoke(digital_twin_sync_loop)
${world_state_out} != null:  invoke(digital_twin_sync_loop)
```

### Detailed Steps

| Step | Capability | Purpose | Stores As | Risk | Condition |
|------|------------|---------|-----------|------|-----------|
| 1 | `invoke` (`workflow_id: world_model_build`) | Build initial world model baseline | world_model_out | medium | `${world_state_out} == null` |
| 2 | `invoke` (`workflow_id: digital_twin_sync_loop`) | Run initial sync loop using the baseline just built | sync_out | medium | `${world_state_out} == null` |
| 3 | `invoke` (`workflow_id: digital_twin_sync_loop`) | Run initial sync loop from the world state passed in | sync_existing_out | medium | `${world_state_out} != null` |

All three conditions use `skip_if_false: true`, so exactly one branch runs: steps 1-2 or step 3.

### Data Flow

```text
${user_input}                                 → invoke(world_model_build).input.user_input
${user_input}                                 → invoke(sync_out).input.user_input
${world_model_out.result.state_out}           → invoke(sync_out).input.previous_world_state
${user_input}                                 → invoke(sync_existing_out).input.user_input
${world_state_out}                            → invoke(sync_existing_out).input.previous_world_state
```

`invoke` returns the invoked workflow's stores under `result`, so `${world_model_out.result.state_out}` is the `state_out` of the world model just built.

### Success Criteria

- World model built
- First sync completed
- Audit produced

---

## Common Patterns

### Checkpoint-Act-Verify-Rollback

**CAVR:** the standard safety pattern for any mutating workflow (see Debug Code Change and Digital Twin Sync Loop):

```
checkpoint → mutate | execute | send → verify → audit → rollback (gate: skip when ${verify_out.passed} == true)
```

**Rules (from the ontology):**
- `checkpoint` `requires`→ `mutate`, `send`, `rollback`: one of those without a prior `checkpoint` is rejected (V102). A step that raises `requires_checkpoint: true` (as `execute` does in Debug Code Change) with no checkpoint before it is F501.
- `mutate`, `execute`, `send` `precedes` `verify`, and `verify` `precedes` `audit`: when both are present, the order is enforced (V102). No edge forces `verify` to be present, so always add it after a side effect.
- `verify` `enables` `rollback`; gate the rollback on `${verify_out.passed}` so it runs only on FAIL.
- `mutate` and `rollback` `conflicts_with` each other: never in the same `parallel_group` (F504).

### Observe-Model-Act

Standard agentic loop:

```
observe | search | detect → classify | measure | predict → plan → constrain → execute | mutate
```

Edges: `observe` precedes `detect`; `detect` enables `classify`; `measure` enables `predict`; `plan` precedes `execute` and `mutate`; `constrain` precedes (and is a soft requirement of) `execute` and `mutate`. A `mutate` also needs `checkpoint` before it (see CAVR).

### Enrichment Pipeline

Parallel data gathering, then identity resolution:

```
[retrieve || observe || search] → integrate → detect (domain: entity) → classify
```

Steps that share a `parallel_group` (with `join: all_complete`) run concurrently; Digital Twin Sync Loop uses `parallel_group: context_gathering` for its `search` step. None of these capabilities `conflicts_with` another, so they may share a group.

### Risk Assessment

Sequential risk analysis (steps 10-14 of Digital Twin Sync Loop):

```
detect (domain: anomaly) → measure (domain: risk) → predict (domain: risk) → plan → constrain
```

Edges: `measure` enables `predict`; `plan` enables `constrain`.

---

## Anti-Patterns

### CRITICAL: Never Do These

| Anti-Pattern | Risk | Why | Correct Pattern |
|--------------|------|-----|-----------------|
| `mutate` or `send` without `checkpoint` | CRITICAL | `requires` edge: rejected (V102); no recovery possible | `checkpoint → mutate` |
| `rollback` without `checkpoint` | CRITICAL | `requires` edge: rejected (V102); nothing to roll back to | Ensure checkpoint exists |
| Step with `requires_checkpoint: true` and no prior `checkpoint` | CRITICAL | Rejected (F501) | `checkpoint` before the step |
| `mutate` and `rollback` in one `parallel_group` | CRITICAL | `conflicts_with` edge: rejected (F504) | Run them in sequence |
| `mutate`, `execute` or `send` before `constrain` | HIGH | `precedes` edge: rejected (V102) when both are present | `constrain → checkpoint → mutate` |
| `verify` before the `mutate`/`execute`/`send` it checks | HIGH | `precedes` edge: rejected (V102) | `mutate → verify` |
| `mutate` or `execute` without `verify` | HIGH | No validation of outcome | `mutate → verify` |
| `verify` without evidence | MEDIUM | Ungrounded verification | Populate evidence_anchors |
| Direct mutations after `verify` FAIL | CRITICAL | State may be corrupted | `rollback` first |

### Warning Patterns

| Pattern | Risk | When Acceptable |
|---------|------|-----------------|
| `mutate`, `execute` or `send` with no `constrain` in the workflow | HIGH | `soft_requires` edge: warning W601. Only for side effects already covered by policy |
| `ground` with no prior `observe`, `detect`, `predict`, `attribute` or `explain` | MEDIUM | `soft_requires` edge (any one satisfies it): warning W601 |
| Skipping `critique` before acting on a `plan` | MEDIUM | Only for trivial, well-understood changes (`plan` enables `critique`) |
| Skipping `audit` after `mutate`/`execute` | MEDIUM | Only for reversible, low-impact changes (`mutate`, `execute` enable `audit`) |
| Multiple `mutate` without intermediate `checkpoint` | HIGH | Never acceptable |

---

## Capability Dependencies

Taken from `edges` in `schemas/capability_ontology.yaml`. Each entry is keyed by the dependent capability and lists the capabilities that must (or should) run before it.

### Hard Dependencies (requires)

```yaml
# A `from` step must run before the target, else V102.
mutate:
  requires: [checkpoint]

send:
  requires: [checkpoint]

rollback:
  requires: [checkpoint]
```

### Soft Dependencies (soft_requires)

```yaml
# Any one source should run before the target, else warning W601.
execute:
  soft_requires: [constrain]

mutate:
  soft_requires: [constrain]

send:
  soft_requires: [constrain]

ground:
  soft_requires: [observe, detect, predict, attribute, explain]
```

### Ordering (precedes)

```yaml
# When both are present, the source must come before the target (V102).
# Neither needs to be present. Ordering follows only through steps that are present.
checkpoint: { precedes: [mutate, send] }
plan:       { precedes: [execute, mutate] }
constrain:  { precedes: [execute, mutate, send, generate] }
observe:    { precedes: [detect] }
detect:     { precedes: [classify, attribute] }
retrieve:   { precedes: [transform] }
search:     { precedes: [compare] }
state:      { precedes: [simulate] }
mutate:     { precedes: [verify] }
execute:    { precedes: [verify] }
send:       { precedes: [verify] }
verify:     { precedes: [audit] }
```

### Concurrency Conflicts (conflicts_with)

```yaml
# May not share a parallel_group (F504); running them in sequence is allowed.
rollback:
  conflicts_with: [mutate, persist]
```

`enables`, `alternative_to` and `specializes` edges carry no validation rule; they document composition flow, substitutes and inheritance (e.g. `rollback` specializes `mutate`, `classify` specializes `detect`).

---

## Usage in Skills

Reference this document in the Composition Patterns section of each skill:

```markdown
## Composition Patterns

**Commonly follows:**
- `checkpoint` - Required before any mutation (see CAVR pattern)
- `plan` - Provides the execution blueprint
- `constrain` - Checks policy before the side effect

**Commonly precedes:**
- `verify` - Must verify outcomes (see CAVR pattern)
- `audit` - Record what was done

**Anti-patterns:**
- Never call without prior `checkpoint` (CRITICAL)
- Never skip `verify` after execution

**Workflow references:**
- See `composition_patterns.md#checkpoint-act-verify-rollback` for the CAVR pattern
- See `composition_patterns.md#debug-code-change` for usage in debug context
- See `composition_patterns.md#digital-twin-sync-loop` for twin sync context
```
