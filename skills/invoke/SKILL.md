---
name: invoke
description: Execute a composed workflow by name. Use when running predefined workflows, orchestrating multi-step processes, or delegating to workflow templates.
argument-hint: "[workflow] [input] [options]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash, Edit, Write
context: fork
agent: general-purpose
layer: COORDINATE
---

## Intent

Invoke a predefined workflow by name, passing input parameters and receiving aggregated results. This enables reuse of common capability compositions and supports hierarchical workflow organization.

**Success criteria:**
- Workflow executed according to definition
- All steps completed or gracefully failed
- Results aggregated and returned
- Execution trace available for debugging

**Compatible schemas:**
- `schemas/output_schema.yaml`
- `reference/workflow_catalog.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `workflow` | Yes | string | Workflow name from workflow catalog |
| `input` | No | object | The workflow's inputs: only names it declares in its `inputs`, and every required one |
| `options` | No | object | Execution options (timeout, retry, etc.) |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Resolve workflow**: Find workflow definition
   - Look up workflow in workflow_catalog.yaml
   - Validate workflow exists
   - Load workflow specification

2) **Validate inputs**: Check input against the workflow's declared `inputs`
   - Pass only inputs the workflow declares: an undeclared name fails the step (R402; S303 when the validator sees a literal `input`)
   - Verify required inputs are provided (a missing one is R402; S304 statically)
   - The executor checks input names only, not their types: a value of the wrong type reaches the nested run's steps as given

3) **Initialize execution**: Set up workflow context
   - Run the workflow as a nested run (at most four deep) with `input` as its inputs
   - Set up data flow context (the nested run has its own stores)

4) **Execute steps**: Run workflow steps in order
   - Execute each capability in sequence
   - Handle step dependencies
   - Propagate data between steps via store_as

5) **Handle failures**: Respond to step failures
   - The nested run's failure modes, recovery loops and rollbacks apply inside it
   - If the nested run fails, the invoke step fails with R402 ("invoked workflow '<id>' failed with <code>: <message>"); its own failure modes apply to that R402
   - If the nested run escalates, the invoke step also fails with R402
   - If the nested run ends `deferred` (some of its steps were queued for approval), the invoke step is deferred too, and so is each later step that depends on it; the invocation's own record, if any, is `executed`, and the nested run's records are the queued actions
   - If the nested run ends `replan_required` (an approved source changed before a step acted, with `recheck.on_change: replan`), the whole run ends `replan_required`: the invoke step produces no output and no later step runs

6) **Aggregate results**: Collect workflow outputs
   - `result` holds the nested run's stores, keyed by `store_as`: `{<store_as>: <that step's output>}`
   - A step that was skipped has no entry, so reading it (`${out.result.<store_as>}`) gives null: guard it
   - `steps_executed` lists the `store_as` names of the steps that produced output, in step order

7) **Return results**: Provide the execution record
   - Return `result`, `steps_executed` and `evidence_anchors`
   - Later steps read a nested output as `${<invoke store_as>.result.<store_as>.<field>}`

## Output Contract

Return a structured object (the ontology's `invoke` output):

```yaml
result:                     # the invoked workflow's stores, keyed by store_as
  <store_as>: object        # that step's output, as its capability's output contract defines it
steps_executed:             # store_as names of the steps that ran, in step order
  - string
duration: string            # Total execution time (optional; a host may report it)
evidence_anchors: array     # The reference executor returns []; a host may add anchors
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `result` | object | The nested run's stores: each executed step's output under its `store_as`. Skipped steps are absent |
| `result.<store_as>` | object | One step's output (e.g. `result.state_out.state` is the world state the `state_out` step built) |
| `steps_executed` | array of string | The `store_as` names of the steps that produced output, in step order |
| `duration` | string | Total execution time (optional) |
| `evidence_anchors` | array | References supporting the result (empty from the reference executor) |

A failed or escalated nested run produces no output: the invoke step fails
with R402, and the message names the nested code. A deferred nested run
defers the invoke step, which also produces no output; a nested run that
needs a replan ends the whole run `replan_required`.

## Examples

### Example 1: Invoke World Model Build

`world_model_build` declares `user_input` (with `domain` and `constraints`),
so the step passes that and nothing else.

**Input:**
```yaml
workflow: "world_model_build"
input:
  user_input:
    domain: "user authentication"
    constraints:
      scope: "backend services"
```

**Output:**
```yaml
result:
  retrieve_out:
    data: {sources: ["docs/auth/architecture.md", "docs/auth/sessions.md"]}
    evidence_anchors: ["file:docs/auth/architecture.md"]
    confidence: 0.9
  # ... observe_out, detect_out, classify_out, integrate_out ...
  state_out:
    state:
      world_id: "auth-model-001"
      entities: [{id: "session_service"}, {id: "token_store"}]
    entities: [{id: "session_service"}, {id: "token_store"}]
    evidence_anchors: ["file:docs/auth/sessions.md:12"]
    confidence: 0.85
  # ... transition_out, attribute_out, measure_out, audit_out, ground_out, simulate_out ...
  explain_out:
    explanation: "Authentication model with 12 entities and 18 relationships"
    evidence_anchors: ["workflow:world_model_build:state_out"]
    confidence: 0.85
steps_executed:
  - retrieve_out
  - observe_out
  - detect_out
  - classify_out
  - integrate_out
  - state_out
  - transition_out
  - attribute_out
  - measure_out
  - audit_out
  - ground_out
  - simulate_out
  - explain_out
evidence_anchors: []
```

A later step reads the baseline world state as
`${world_model_out.result.state_out.state}`.

### Example 2: A Nested Step Skipped, or the Nested Run Failing

`digital_twin_sync_loop` declares `user_input`, `previous_world_state` and
`world_state_out`.

**Input:**
```yaml
workflow: "digital_twin_sync_loop"
input:
  user_input:
    domain: "warehouse robots"
  previous_world_state: "${world_state_out: object}"
```

**Output (the planned change was not compliant, so `mutate` was skipped):**
```yaml
result:
  receive_out: {data: [{type: "battery_low", robot: "r-17"}], source: "fleet-events", evidence_anchors: []}
  # ... search_out through plan_out ...
  constrain_out: {compliant: false, violations: ["change_policy"], evidence_anchors: []}
  checkpoint_out: {checkpoint_id: "chk-0042", evidence_anchors: []}
  audit_out: {recorded: true, evidence_anchors: []}
  explain_out: {explanation: "Drift detected; the planned change was blocked by policy", evidence_anchors: [], confidence: 0.8}
steps_executed:
  - receive_out
  - search_out
  # ...
  - constrain_out
  - checkpoint_out
  - audit_out
  - explain_out
evidence_anchors: []
```

With no mutation applied, the verification suite (`execute`), `verify` and
`rollback` were skipped too, so `mutate_out`, `execute_out`, `verify_out` and
`rollback_out` are absent and `${sync_out.result.mutate_out}` reads null.
Nothing was rolled back: there was nothing to undo.

Had the change been compliant and applied, and a later nested step failed
(say the verification suite timed out: `execute`'s failure mode rolls the twin
back to the checkpoint taken before the mutation, then the nested run ends
with that code and records no audit), the invoke step would fail with
`R402: invoked workflow 'digital_twin_sync_loop' failed with R401: ...`.

### Example 3: Nested Workflow Invocation

**Input:**
```yaml
workflow: "digital_twin_bootstrap"
input:
  user_input:
    domain: "payment processing"
```

**Output:**
```yaml
result:
  world_model_out:            # bootstrap's own invoke of world_model_build
    result: {state_out: {state: {world_id: "payments-001"}, evidence_anchors: [], confidence: 0.8}}
    steps_executed: [retrieve_out, observe_out, state_out]   # abbreviated
    evidence_anchors: []
  sync_out:                   # its invoke of digital_twin_sync_loop
    result: {verify_out: {passed: true, evidence_anchors: [], confidence: 0.9}}
    steps_executed: [receive_out, verify_out]                 # abbreviated
    evidence_anchors: []
steps_executed:
  - world_model_out
  - sync_out
evidence_anchors: []
```

No world state was passed in, so `sync_existing_out` was skipped and is not
listed.

## Verification

- [ ] Workflow name resolves to valid definition
- [ ] All required inputs provided
- [ ] Each step executed or skipped with reason
- [ ] Failures handled according to failure_modes
- [ ] Success criteria evaluated

**Verification tools:** Read (to verify workflow catalog)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- Workflow must exist in workflow_catalog.yaml
- Respect step-level safety constraints
- Propagate checkpoint requirements to mutating steps
- Do not modify workflow definitions at runtime
- Log all step executions for audit

## Composition Patterns

**Commonly follows:**
- `plan` - Invoke workflow to execute plan
- `decompose` - Invoke sub-workflows for sub-problems

**Commonly precedes:**
- `verify` - Verify workflow results
- `audit` - Record workflow execution
- `explain` - Explain workflow results

**Anti-patterns:**
- Avoid deeply nested invocations (the executor allows at most four levels)
- Never invoke workflows recursively
- Do not invoke without understanding workflow effects

**Workflow references:**
- See `reference/workflow_catalog.yaml#digital_twin_bootstrap` for nested invocation
- This capability is the entry point for all workflow execution
