# Orchestration Extensions

Standard v1.1 adds optional, versioned **extensions** for what orchestrators
need beyond a sequence of steps: starting runs on a schedule or an event,
escalating when recovery runs out, waiting for an event, structured
approval, delegation hints, review quorums, and checks on who sent an item.
This guide shows how to use them. The normative text is
[STANDARD-v1.1.0 §5.9–§5.17](../../spec/STANDARD-v1.1.0.md#59-workflow-extensions);
the rationale is in [RFC-0003](../../spec/RFC-0003-orchestration-extensions.md)
and, for sender identity, [RFC-0004](../../spec/RFC-0004-agent-identity.md).

| Extension | What it adds | Validated today |
|-----------|--------------|-----------------|
| `triggers@1` | How runs start | Yes |
| `recovery@1` | Escalation to handler steps | Yes |
| `wait@1` | Waiting for an event | Yes |
| `approval@1` | Structured, bound approval | Yes |
| `delegation@1` | Delegation hints and sender filtering | Yes |
| `quorum@1` | Independent review quorums | Yes |
| `identity@1` | Sender identity, trust classes, "always ask" | Yes |

The reference validator checks all seven. A workflow that declares any other
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
        goal: Deploy the release to production
        constraints: ["${_recovery.failure_evidence: array<object>}"]
    # ... constrain, checkpoint ...
    - capability: execute
      store_as: deploy_out
      input_bindings:
        code: ./scripts/deploy.sh
      failure_modes:
        - condition: The deployment command failed or timed out.
          on_error: [R401, R402]
          action: escalate
          recovery: {goto_step: page_oncall_out}
    - capability: verify
      store_as: verify_out
      input_bindings:
        conditions: [health_checks_pass, error_rate_below_slo]
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

- **Firing.** `on_error` takes one code or a list of the codes a step can
  fail with (R401 timeout, R402 failure, R403 gate, R406 lost liveness,
  F501 checkpoint, F502
  approval, F504 quorum or constraint). Expression errors (R405) never fail
  a step: they are fail-safe where they occur. `when` is an
  expression that can read the step's own output. A structured recovery
  with neither never fires (W609).
- **Loops.** `goto_step` names the `store_as` of the current step or an
  earlier one. `max_loops` is at most 1000. Naming a capability still works when exactly one step uses
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
  that invoke each other are V105. A literal `input_bindings.input` must
  give the target's required inputs (S304) and nothing it does not declare
  (S303); a `${...}` reference is checked when the step runs (R402).

## Waiting for an event (`wait@1`)

A `receive` step with `wait` pauses the run until a matching event arrives
or the step's `timeout` lapses (R401), or its source stops answering
(R406, with `liveness`); the event arrives in the step's
output (`data`). A `synchronize` step can wait too, when its `agents` input
is a literal list of at least two agents, and so can a `delegate` step: it
delegates, then waits for that delegate's result (see
[Review quorums](#review-quorums-quorum1)).

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
  it would never fire first. Lost liveness is R406, not the timeout's R401,
  so you can re-check a silent source and escalate only an expired wait:

  ```yaml
  failure_modes:
    - condition: The source stopped answering probes.
      on_error: R406
      action: request_more_context
      recovery:
        goto_step: window_out          # the wait itself: wait again
        max_loops: 1
        on_exhausted: {goto_step: page_oncall_out}
    - condition: The change window never opened.
      on_error: R401
      action: escalate
      recovery: {goto_step: page_oncall_out}
  ```

  A `retry` on the step covers R406 too, before any failure mode. Each
  re-check or retry waits a full `timeout` again. Lost liveness reported
  after the deadline is R401: the wait had already lapsed.
- A wait can last hours, and the run may resume in another process, so a
  checkpoint taken before the wait no longer covers a later `mutate`,
  `send` or other step that requires a checkpoint (W608). Take the
  checkpoint after the wait, not alongside it in a parallel group. An
  `invoke` of a workflow that waits counts as a wait.
- A `correlate` value that resolves to null, or an `accept_from` that
  resolves to anything but a non-empty list of strings (`[null]`, say, from
  a delegation that returned no `task_id`), fails the step (R402) at once:
  a null key would match every event that lacks it, and such a filter
  would drop every sender.

To pause without an event, give the step a `delay` (`wait@1` too): it
waits that long after its condition and gates, then goes on. Sampling
twice, a minute apart:

```yaml
- capability: observe
  store_as: sample_b_out
  delay: 1m
  input_bindings: {target: queue}
```

A delay ends like a wait: checkpoints taken before it no longer count.

## Approval (`approval@1`)

A step that requires approval (`mutate`, `send` and `execute` do, and any
step can raise `requires_approval`) can say who approves, what they see,
and what the decision binds to:

```yaml
- capability: mutate
  # purpose, store_as ...
  input_bindings:
    target: deploy/release.yaml
    operation:
      apply: "${plan_out.steps: array<object>}"
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
  pre-approved routine actions. It needs no one present, so it is asked
  even in an unattended run; your host answers `approved`, or
  `unavailable` when no mandate covers the action.
- `approval` on a step that does not require approval is an error (S303);
  raise `requires_approval: true` if you mean it.
- If a schedule or event trigger can start the run unattended (or a
  trigger says `attendance: unattended`), say what to do when nobody is
  there to approve: without `when_unattended` or a standing mandate the
  step warns (W606) and an unattended run fails there.
- `defer_to_queue` queues the action (a `planned` record) and defers the
  step. Later steps that depend on it wait too: those that read its output
  (or a step that does), those that may act on or wait on the world (a
  checkpoint or approval requirement, a wait, an `invoke`, `delegate`,
  `synchronize` or `rollback`), and those the ontology orders after a
  deferred capability (`verify` after `mutate`, transitively). Steps that
  read, reason or record and depend on none of them run, and the run ends
  `deferred`, listing every deferral. A nightly sweep can thus finish its
  other work and leave one send for a person to approve:

  ```yaml
  - capability: send
    store_as: notify_out
    input_bindings:
      destination: ops-channel
      payload: Nightly sweep finished.
    approval:
      approver: {kind: standing_mandate, mandate_ref: mandates/nightly-notify}
      when_unattended: defer_to_queue   # if no mandate covers this send
  - capability: retrieve                # read-only, independent: runs
    store_as: status_out
    input_bindings:
      target: reports/nightly-status.json
  - capability: mutate                  # acts on the world: waits
    store_as: cleanup_out
    input_bindings:
      target: build/cache
      operation: {delete: stale_entries}
    approval:
      approver: {kind: human, role: build-owner}
      when_unattended: defer_to_queue   # queued too when the send ran
  ```

  The `mutate` needs its own `when_unattended`: when the mandate covers
  the send, nothing is deferred, and an unattended run reaches the
  `mutate` with no one to approve it.
- A step that must run whether or not an earlier action was deferred,
  such as an escalation to a person, can say so with
  `after_deferral: run`. It is then deferred only if it reads a deferred
  step's output. Use it only where running ahead of the queued action is
  safe:

  ```yaml
  - capability: invoke
    store_as: escalate_out
    after_deferral: run                 # ask the owner even if the reminder waits
    input_bindings:
      workflow: owner_decision
      input: {question: "${rows_out}"}
  ```
- A run that fails or escalates after a deferral still lists its
  deferrals; a recovery loop that runs a deferred step again supersedes
  its earlier `planned` record.
- Decisions are recorded on the world state's action record
  (`world_state_schema.yaml` 1.1.0): status `approved`, `rejected`,
  `expired` or `planned`, with an `approval` entry holding the digest,
  the decision (`approved`, `rejected`, `expired` or `unavailable`) and
  the approvers.

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
    read_only: true          # may read, must not change anything
```

How a host keeps a delegate read-only is up to it (a read-only token, a
sandbox); `effective.read_only` says whether it did.

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

A principal is an opaque string, matched exactly. Your host decides how its
identities (accounts, keys, agent sessions) map to principals, and reports
as an item's principal whoever authenticated delivering it, not a sender
named in the item. So when a peer relays the owner's answer, the principal
is the peer, and `accept_from: [owner]` drops it.

## Sender identity (`identity@1`)

A principal says *who* delivered an item; an **identity** also says how the
host authenticated them and what standing they have. Your host reports one
with each event a step waits for (`schemas/agent_identity_schema.yaml`):

```json
{"principal": "dana", "kind": "human",
 "authenticated_by": "session_id", "trust_class": "owner"}
```

`receive` and `synchronize` then take three more inputs:

```yaml
- capability: receive
  purpose: Wait for the owner's answer.
  store_as: answer
  timeout: 2h
  input_bindings:
    sender_check: [session_id, x-acme.sso]          # how they were authenticated
    accept_trust_classes: [owner, decision_person, colleague]  # who may answer
    always_ask_trust_classes: [colleague]  # whose answer needs a person in the loop
  wait:
    event_type: answer.given
```

- With `sender_check` or `accept_trust_classes` bound, an item whose sender
  has no identity, was authenticated some other way, or is of another trust
  class is dropped and counted, like `accept_from`. A kept item carries
  `sender` and `sender_identity`. A bound value must be a non-empty list of
  known values: a reference that resolves to anything else, including an
  optional input that was left out, fails the step (R402) rather than
  turning the check off.
- `authenticated_by` is one of `session_id`, `chat_user_id`,
  `code_host_login`, `directory_id`, `api_key`, `signed_token`, or your own
  `x-` value. Trust classes are `owner`, `decision_person`,
  `system_of_record`, `own_subagent_report`, `peer_agent`, `colleague` and
  `external`; `authority_trust_model.yaml` gives each a default evidence
  weight that a profile's `trust_weights` can override.
- **Always ask.** An item from a listed class, or one with no identity or
  no trust class, marks what is computed from it: a step that reads it,
  directly or through other steps (a `generate` that summarises it, context
  a recovery loop injects, an `invoke` that passes it on or runs because of
  it), is asked of a person if it needs approval, even when its `approval`
  names a standing mandate, and its action records say `always_ask: true`.
  An unattended run follows the step's `when_unattended` instead; the
  validator warns (W606) when that would leave only a mandate. The mark
  follows references: if your host carries an item's content into a later
  step by other means, the executor cannot see it.
- On a step that does not wait, your host receives the inputs, applies
  them to what it returns, and must put the `sender_identity` it applied
  them to on each item it returns: the executor marks from it.

To record who ran a workflow, start the run with an actor identity
(`WorkflowRunner.run(..., actor_identity=agent.identity())`); every action
record then carries it. See [Running workflows](RUNNING_WORKFLOWS.md).

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
  only if it is about the resolved `pinned_to` and uses the vocabulary. Its
  optional `scope` says whether it swept the whole change (`full`) or only
  what changed since an earlier round (`delta`, the default, also for any
  other value).
- Reviewers must be `delegate` steps that run before the quorum, to
  distinct agents (V107, F504).
- Independence is checked statically where the bindings are literal: a
  reviewer that reads a forbidden input, directly, through other steps or
  through context a recovery loop injects,
  one without `fresh_context: true` when it is required, or literal model
  families that cannot cover `require_model_families` are F504.
- At run time the step is compliant when no counted verdict blocks, at
  least `min_pass` pass, and at least `min_full` of the passes have scope
  `full`; its output gains a `tally` (with `full_passes`).

Reviewers can have different rules. Give `forbidden_inputs` a mapping to
keep one reviewer away from what another may read, for example a verifier
that sees the earlier rounds and a fresh reviewer that must not:

```yaml
  quorum:
    # ...
    reviewers: [verify_fixes, fresh_review]
    forbidden_inputs:
      verify_fixes: [author_notes]
      fresh_review: [author_notes, prior_rounds]
    min_full: 1                           # one pass must be a full sweep
```

To make sure reviewers only read, bind `read_only: true` on each reviewer
and set `require_read_only: true`: a reviewer that does not bind it is
F504, and a verdict from a reviewer the host did not attest read-only is
not counted.

**Replacing a reviewer that hangs.** Make each reviewer a `delegate` step
that waits for its own result, with a `retry`. If reviewer B goes silent
(R406) or runs out of time (R401), its step delegates again; reviewer A is
not asked again. Collect the results with a list of references:

```yaml
- capability: delegate
  purpose: Ask reviewer B for a review and wait for it.
  store_as: review_b
  timeout: 2h
  retry: {max: 1, backoff: none}     # a silent reviewer is replaced once
  input_bindings:
    task: {review: "${change}"}
    agent: reviewer-b
    read_only: true
  wait:
    event_type: review.done          # matched by the delegation's task_id
    liveness: {mode: push, interval: 10m, failure_threshold: 3}
# ... review_a alike, then:
- capability: constrain
  # ...
  quorum:
    verdicts: ["${review_a.result: object}", "${review_b.result: object}"]
    reviewers: [review_a, review_b]
    require_read_only: true
    # ...
```

The delegation must return a `task_id`: it is how the result is matched to
it, and a retry tells your host which delegation it replaces (`replaces` on
the new call) so you can cancel it. One `timeout` covers delegating and
waiting. A waiting delegate can also bind `accept_from` and, with
`identity@1`, the sender inputs, which apply to its result. A verdict in a
reviewer step's `result` counts only for that reviewer.

Placing a delegated step on a particular host or device is not part of
the standard; RFC-0003 records it as an open question.

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
