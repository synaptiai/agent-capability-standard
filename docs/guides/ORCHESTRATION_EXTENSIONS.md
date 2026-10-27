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
| `wait@1` | Waiting for an event | Not yet |
| `approval@1` | Structured, bound approval | Not yet |
| `delegation@1` | Delegation hints and sender filtering | Not yet |
| `quorum@1` | Independent review quorums | Not yet |

The reference validator refuses a workflow that declares an extension it
does not validate yet (V106), and reports that extension's fields as unknown
(W604) when they are used without the declaration.

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
- kind: event
  event:
    event_type: deploy.finished
    source_kind: agent           # log | api | sensor | message_bus | human | agent
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

## Durations

Durations appear in schedules (`every`) and in later extensions. Write
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
