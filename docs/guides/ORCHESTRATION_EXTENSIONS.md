# Orchestration Extensions

Standard v1.1 adds optional, versioned **extensions** for what orchestrators
need beyond a sequence of steps: starting runs on a schedule or an event,
escalating when recovery runs out, waiting for an event, structured
approval, delegation hints, and review quorums. This guide shows how to use
them. The normative text is
[STANDARD-v1.1.0 §5.9–§5.16](../../spec/STANDARD-v1.1.0.md#59-workflow-extensions);
the rationale is in [RFC-0003](../../spec/RFC-0003-orchestration-extensions.md).

| Extension | What it adds | Validated today |
|-----------|--------------|-----------------|
| `triggers@1` | How runs start | Yes |
| `recovery@1` | Escalation to handler steps | Yes |
| `wait@1` | Waiting for an event | Yes |
| `approval@1` | Structured, bound approval | Yes |
| `delegation@1` | Delegation hints and sender filtering | Yes |
| `quorum@1` | Independent review quorums | Yes |

The reference validator checks all six. A workflow that declares any other
extension (or another major version) is refused (V106).

## Declaring the extensions you use

```yaml
# Standard version: 1.1.0
nightly_report:
  goal: Summarise the day's deployments.
  risk: low
  workflow_extensions:
    requires: [triggers@1]
  triggers:
    - kind: schedule
      schedule: {cron: "30 23 * * MON-FRI", timezone: Europe/Lisbon}
  steps: ...
```

Extensions are **must-understand**: a workflow that uses an extension's
fields without listing it in `workflow_extensions.requires` is rejected
(V106), and so is a workflow that lists an extension the validator does not
know. That is deliberate. A consumer built for 1.0 would otherwise run the
workflow and silently ignore, for example, a wait or an approval.

## Triggers (`triggers@1`)

`triggers` lists the ways a run can start. Each trigger has a `kind`:

| Kind | Starts a run | Extra fields | Default attendance |
|------|--------------|--------------|--------------------|
| `schedule` | On a cron schedule or an interval | `schedule` | unattended |
| `event` | When a matching event arrives | `event` | unattended |
| `manual` | When a person starts it | — | attended |
| `invoke` | When another workflow invokes it | — | the invoker's |

`attendance: attended | unattended` overrides the default. It matters for
approval steps: an unattended run cannot wait for a person in the session.

### Schedules

```yaml
- kind: schedule
  schedule:
    cron: "*/15 9-17 * * MON-FRI"   # or: every: PT15M
    timezone: America/New_York     # IANA name; default UTC
    overlap: skip                  # skip | buffer_one | allow_all
```

- `cron` has five fields: minute, hour, day of month, month (1–12 or
  JAN–DEC), day of week (0–7 or SUN–SAT; 0 and 7 are Sunday). Use `*`,
  lists (`1,15`), ranges (`9-17`) and steps (`*/15`, `5/20`). When both day
  fields are restricted, a day matching either fires (as in Vixie cron).
- Put the time zone in `timezone`, not as a `CRON_TZ=` prefix.
- `every` is an interval instead of a cron expression; give one or the
  other.
- `overlap` says what happens when a run is still going at the next fire
  time: `skip` it, keep at most one queued run (`buffer_one`), or start
  runs concurrently (`allow_all`).

### Events

```yaml
triggers:
  - kind: event
    event:
      event_type: deploy.finished
      source_kind: agent         # log | api | sensor | message_bus | human | agent
      delivers_to: deploy_event
inputs:
  deploy_event:
    type: object
    ref: schemas/event_schema.yaml#/event
```

The triggering event is delivered into the workflow input named by
`delivers_to`, which must hold a canonical event (its `ref` ends in
`event_schema.yaml#/event`); anything else is V107.

## Recovery and escalation (`recovery@1`)

Failure modes have been in the standard since 1.0. In 1.1 a failure mode
fires on something checkable: a runtime code (`on_error`) or an expression
evaluated after the step (`when`). Its `recovery` can loop back to an
earlier step and, with `recovery@1`, escalate to a **handler step** when the
loop runs out or the failure cannot be recovered.

```yaml
deploy_with_escalation:
  workflow_extensions:
    requires: [recovery@1]
  steps:
    - capability: plan
      store_as: plan_out
      input_bindings:
        constraints: ["${_recovery.failure_evidence: array<object>}"]
    # ... constrain, checkpoint ...
    - capability: execute
      store_as: deploy_out
      failure_modes:
        - condition: The deployment command failed or timed out.
          on_error: [R401, R402]
          action: escalate
          recovery: {goto_step: page_oncall_out}
    - capability: verify
      store_as: verify_out
      failure_modes:
        - condition: Verification failed.
          when: ${verify_out.passed} == false
          action: rollback
          recovery:
            goto_step: plan_out           # loop back (a store_as)
            inject_context:
              failure_evidence: ${verify_out.violations}
            max_loops: 2
            on_exhausted: {goto_step: page_oncall_out}
    - capability: invoke
      store_as: page_oncall_out
      handler: true                     # runs only when escalated to
      workflow_id: page_oncall
```

- **Firing.** `on_error` takes one code or a list (R401 timeout, R402
  failure, R403 gate, R405 expression error, F502 approval). `when` is an
  expression that can read the step's own output. A structured recovery
  with neither never fires (W609).
- **Loops.** `goto_step` names the `store_as` of the current step or an
  earlier one. Naming a capability still works when exactly one step uses
  it, but is deprecated (W603). `max_loops` defaults to 1.
- **Injected context.** Values in `inject_context` are readable as
  `${_recovery.<key>}` from the loop target onward. They are absent before
  the first loop and untyped, so guard them (`${_recovery.x} != null`) and
  annotate them where a type matters.
- **Escalation.** `action: escalate` runs a handler once and ends the run,
  so it takes no `max_loops`, `on_exhausted` or `inject_context`; the
  handler binds what it needs from the failed step's output.
- **Handlers.** A handler is an `invoke` step with `handler: true`. It is
  skipped in normal flow, runs only as the target of `action: escalate` or
  `on_exhausted`, and ends the run with outcome `escalated`, so its own
  failure modes cannot loop or escalate. It is checked in the scope of the
  earliest step that escalates to it, where that step's own output (and
  that of steps running alongside it in its `parallel_group`) may be
  missing; guard such references with `!= null`. A checkpoint it needs must
  run before that step. A handler nothing escalates to is W613.
- **Invocations.** An `invoke` target outside the catalog is W607; workflows
  that invoke each other are V105.

## Waiting for an event (`wait@1`)

A `receive` step with `wait` pauses the run until a matching event arrives
or the step's `timeout` lapses (R401); the event arrives in the step's
output (`data`). A `synchronize` step can wait too, when its `agents` input
is a literal list of at least two agents.

```yaml
- capability: receive
  purpose: Wait for the change window to open.
  store_as: window_out
  timeout: 2h                        # required, and must be a duration
  wait:
    event_type: change.window_opened # required
    source_kind: api                 # optional: log | api | sensor | message_bus | human | agent
    correlate:                       # each value must be a ${...} reference
      request: ${request_out.data}   # the event must carry this value
    liveness: {mode: probe, interval: 10m, failure_threshold: 3}
```

- `liveness` gives up early when the source goes quiet: after
  `failure_threshold` missed heartbeats (`push`) or failed probes (`probe`)
  one `interval` apart. That window must be shorter than the timeout, or
  it would never fire first.
- A wait can last hours, and the run may resume in another process, so a
  checkpoint taken before the wait no longer covers a later `mutate`,
  `send` or other step that requires a checkpoint (W608). Take the
  checkpoint after the wait, not alongside it in a parallel group.

## Approval (`approval@1`)

A step that requires approval (`mutate`, `send` and `execute` do, and any
step can raise `requires_approval`) can say who approves, what they see,
and what the decision binds to:

```yaml
- capability: mutate
  # purpose, store_as, input_bindings ...
  approval:
    approver: {kind: human, role: release-manager, min_approvers: 2}
    mode: out_of_band                # or in_session (the default)
    shows: ["${plan_out.steps}"]     # references; quote them inside [ ] and { }
    binds_to: digest
    recheck: {source: "${plan_out}", compare: digest, on_change: reask}
    expires: 24h
    when_unattended: defer_to_queue  # or skip, or fail (the default)
```

- The decision is bound to the SHA-256 digest of the shown values: if they
  change before the step runs, the approval no longer applies. `recheck`
  re-reads a source just before acting and asks again (`reask`), replans or
  stops when it changed.
- A `standing_mandate` approver names its mandate in `mandate_ref`, for
  pre-approved routine actions.
- `approval` on a step that does not require approval is an error (S303);
  raise `requires_approval: true` if you mean it.
- If a schedule or event trigger can start the run unattended (or a
  trigger says `attendance: unattended`), say what to do when nobody is
  there to approve: without `when_unattended` the step warns (W606) and an
  unattended run fails there.
- Decisions are recorded on the world state's action record
  (`world_state_schema.yaml` 1.1.0): status `approved`, `rejected` or
  `expired`, with an `approval` entry holding the digest and approvers.

## Delegation hints (`delegation@1`)

`delegate` can ask for the conditions a delegate runs under, and the host
reports what it actually used as `effective`:

```yaml
- capability: delegate
  purpose: Review the change independently.
  store_as: review_a
  input_bindings:
    task:
      review: "${diff_out.data: object}"
    agent: reviewer-a
    fresh_context: true      # start without this agent's context
    model_family: claude     # run on this model family
    role: reviewer
```

`receive` and `synchronize` take `accept_from`, a list of principals:
items from anyone else are dropped (and counted), and each kept item
carries the host-authenticated `sender`.

```yaml
- capability: receive
  purpose: Collect the reviewers' verdicts.
  store_as: verdicts_out
  input_bindings:
    accept_from: [reviewer-a, reviewer-b]
```

## Review quorums (`quorum@1`)

A blocking `constrain` step can require a quorum of independent reviews
before the run goes on:

```yaml
- capability: constrain
  purpose: Require two approvals and no request for changes.
  store_as: quorum_out
  input_bindings:
    target: ${verdicts_out.data}
    constraints: [two_independent_approvals]
    action_on_violation: block   # required: a failed quorum stops the run
  quorum:
    verdicts: ${verdicts_out.data}        # review_verdict items
    reviewers: [review_a, review_b]       # earlier delegate steps
    vocabulary: [approve, request_changes, abstain]
    pass_values: [approve]
    blocking_values: [request_changes]    # any one vetoes
    min_pass: 2
    pinned_to: ${change_ref}              # what every verdict must be about
    forbidden_inputs: [author_notes]      # reviewers must not see these
    require_fresh_context: true
    require_model_families: [claude, gpt]
```

- A verdict ([`review_verdict_schema.yaml`](../../schemas/review_verdict_schema.yaml))
  has `reviewer_id`, `value` and `pinned`. It counts once per reviewer, and
  only if it is about the resolved `pinned_to` and uses the vocabulary.
- Reviewers must be `delegate` steps that run before the quorum, to
  distinct agents (V107, F504).
- Independence is checked statically where the bindings are literal: a
  reviewer that reads a forbidden input, directly, through other steps or
  through context a recovery loop injects,
  one without `fresh_context: true` when it is required, or literal model
  families that cannot cover `require_model_families` are F504.
- At run time the step is compliant when no counted verdict blocks and
  at least `min_pass` pass; its output gains a `tally`.

## Durations

Durations appear in schedules (`every`), waits (`timeout`, liveness
`interval`) and approvals (`expires`). Write
`250ms`, `30s`, `5m`, `2h`, `1d`, or an ISO-8601 day-time duration such as
`PT1H30M`, `P1DT12H` or `PT0.5S`. Years, months and weeks are not allowed,
because their length varies. A step's `timeout` should use the same
grammar; free text such as `five minutes` is still accepted but cannot be
enforced, and is reported as W614.

## Checking your workflow

```bash
python tools/validate_workflows.py --catalog my_catalog.yaml
python tools/validate_workflows.py --catalog my_catalog.yaml --strict  # warnings fail too
```
