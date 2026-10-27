# Running Workflows

The reference executor runs a validated workflow step by step and enforces
the standard's runtime rules: conditions and gates, checkpoints before
mutations, approvals, waits, retries, failure modes, recovery loops,
escalation and review quorums. It lives in the Rust core, next to the
validator, and Python drives it through
`grounded_agency.workflows.WorkflowRunner`.

The executor does no I/O. It tells your code what to do next (an
*action*); your code does it and reports back (a *response*). Time only
enters through the timestamps you pass. So the same catalog, inputs,
responses and times always produce the same actions, the same trace and
the same snapshot, and a run can be saved and resumed anywhere.

The contract is [design-114 §16](../../tasks/design-114.md#16-executor-sans-io);
the semantics are [STANDARD-v1.1.0 §5](../../spec/STANDARD-v1.1.0.md#5-workflow-dsl).

## Quick start

```python
from grounded_agency.workflows import Host, WorkflowEngine, WorkflowRunner

engine = WorkflowEngine("schemas/capability_ontology.yaml")
engine.load_catalog("my_catalog.yaml")


class MyHost(Host):
    def invoke_capability(self, action):
        # action["capability"], action["inputs"], action["step"], ...
        value = my_tools[action["capability"]](**action["inputs"])
        return {"kind": "Output", "value": value}

    def request_approval(self, action):
        # Show action["shown"] to a person; bind the answer to its digest.
        ok = ask_a_person(action["shown"])
        return {
            "kind": "Decision",
            "decision_id": new_id(),
            "decision": "approved" if ok else "rejected",
            "approvers": ["alice"],
            "digest": action["digest"],
        }


result = WorkflowRunner(engine).run("my_workflow", {"topic": "x"}, MyHost())
if result.ok:
    print(result.outputs)
else:
    print(result.code, result.message)   # e.g. F502 approval was rejected
```

A run starts only if the catalog validates. Otherwise `RunStartError` is
raised, with the error diagnostics in `.diagnostics`. Warnings do not block
a run.

## Actions and responses

| Action | Your host | Respond with |
|--------|-----------|--------------|
| `InvokeCapability` | runs `capability` with `inputs` | `{"kind": "Output", "value": {...}}`, or `{"kind": "Error", "code": "R401"/"R402", "message": ...}` |
| `CreateCheckpoint` | takes a checkpoint before `step` | `{"kind": "Checkpoint", "checkpoint_id": ...}` |
| `Rollback` | restores `checkpoint_id` | `{"kind": "RolledBack"}` |
| `RequestApproval` | asks `approver` about `shown` | `{"kind": "Decision", "decision_id", "decision", "approvers", "digest"}`; `decision` is `approved`, `rejected` or `unavailable` |
| `RecheckSource` | re-reads `source` now | `{"kind": "Current", "value": ...}` |
| `AwaitEvent` | waits for a matching event until `deadline` | `{"kind": "Event", "event": {...}, "principal": ...}` (the authenticated party that delivered it, §5.15) or `{"kind": "LivenessLost"}` (R406) |
| `Sleep` | waits until `until` (retry backoff) | — (the runner calls `tick`) |
| `Completed` / `Failed` | — | the run is over |

`Host` has a method for each, plus `now_ms()` and `sleep_until()` (wall
clock by default). A method may return `None` when there is nothing yet
(no event, no decision): the runner waits `poll_interval_ms` (or until the
action's deadline) and asks again. An exception from `invoke_capability`
fails that step (R402); the step's retries and failure modes then apply.
`NotImplementedError` instead stops the runner, since the host cannot run
that capability at all. Give `Host` a `CheckpointTracker` and checkpoints
are recorded in it.

Values you hand the run must be I-JSON: integers within ±2^53 and at most
100 levels deep. Anything else is refused, so that snapshots and approval
digests represent every value exactly.

Every action carries `id` and `frame`: the workflows of the nested runs,
root first. A capability's output must be an object with the fields its
ontology contract requires, or the step fails (R402).

## What the executor enforces

- **Conditions and gates.** A false condition skips the step, unless
  `skip_if_false: false`, which makes it R403. Gate actions: `stop` → R403,
  `skip` → skip the step, `rollback` → roll back, then R403, `warn` → a trace
  event. An expression that errors (R405) is fail-safe: a gate fires, a
  condition is false, and a failure mode does not fire.
- **Checkpoints.** One checkpoint authorises one step that requires one,
  and is used only once the step is approved and about to run. When none
  is valid, the executor asks for a new one (`CreateCheckpoint`). A
  completed wait invalidates earlier checkpoints.
- **Approvals.** Every step that requires approval asks for it, unless it
  is deferred. The
  decision must match the digest of what was shown, have enough distinct
  approvers, arrive before `expires`, and not be reused. A run that is
  unattended asks only a standing mandate; when there is none, or it
  answers `unavailable`, the run follows `approval.when_unattended`:
  `fail` (F502, the default), `skip`, or `defer_to_queue`. A deferral
  holds back the step and every later step that depends on it (reads its
  output, may act on the world, or comes after it in the ontology), runs
  the steps that only read, reason or record, and ends the run `deferred`.
  In an attended run
  `unavailable` is F502. The default `Host` holds no mandates: it answers
  `unavailable` for one. `recheck` re-reads a source before acting, then
  asks again (showing what changed), replans or stops if it changed.
  Every approval leaves an action record, with a `reason` when the action
  did not go ahead.
- **Waits.** `AwaitEvent` has a deadline from the step's `timeout`. Events
  that don't match (`event_type`, `source_kind`, `correlate`,
  `accept_from`) are dropped and the wait goes on. A lapse is R401;
  `LivenessLost` (or an `Error` with code R406) is R406, unless it comes
  after the deadline, which is R401.
- **Retries, deadlines.** `retry.max` extra attempts for R401/R402/R406, with
  `none`, `linear` (1 s × n) or `exponential` (1 s × 2^(n−1)) backoff. A
  result after the step's deadline is R401.
- **Failure modes and recovery.** The first failure mode that matches the
  step's error code (`on_error`) or whose `when` is true applies. It can
  loop back with injected `${_recovery.*}` context (up to `max_loops`,
  then `on_exhausted` or R404), escalate to a handler (the run ends
  `escalated`), or end the run.
- **Invocations.** An `invoke` step runs its workflow as a nested run, at
  most four deep, with `input_bindings.input` as its inputs; inputs the
  workflow does not declare, or a missing required one, fail the step
  (R402). The validator catches this before the run when `input` is
  literal.
- **Quorums.** A `constrain` step with a `quorum` counts the verdicts
  itself: one per reviewer whose delegate step ran, pinned to `pinned_to`,
  using the vocabulary, from fresh-context reviewers when required. Any
  blocking verdict, too few passes, too few full-sweep passes (`min_full`)
  or uncovered model families fail the step with F504.

`RunResult` gives the `outcome` (`completed`, `escalated`, `deferred`,
`replan_required`) or the failure `code`, plus the outputs, the action
records (world state `ActionRecord`s for every step that required
approval), the deferrals (`deferred`: each deferred step, why, and the
`action_id` of its queued action) and the trace (every decision the
executor took).

## Driving a run yourself

`WorkflowRunner.start()` returns the underlying `_core.Run` without
driving it. Use it to run actions asynchronously, across processes, or
across days:

```python
run = runner.start("my_workflow", inputs, run_id="run-42")
action = run.next()                  # same action until it is answered
run.submit(action["id"], response, now_ms)
run.tick(now_ms)                     # ends a due Sleep, times out a late action

snapshot = run.snapshot(key=b"secret")       # canonical JSON + SHA-256 + HMAC
run = runner.restore(snapshot, key=b"secret")  # refuses tampered snapshots
result = runner.drive(run, host)
```

A snapshot only restores against the catalog (and ontology) it was taken
from, and a signed snapshot only with its key; a state that is not well
formed is refused. A response that does not answer the pending action is
refused, and the run is left unchanged. If a run needs more than
`max_actions` answers, `RunIncomplete` is raised with the live run in
`.run`, so you can snapshot it or drive it on.

## Conformance

`tests/conformance/runtime/*.json` are scripted runs. Each one has a
catalog, inputs, a script of expected actions and responses, and the
expected end and trace. They are generated by
`scripts/gen_runtime_fixtures.py`: edit them there and regenerate (CI runs
it with `--check`). `cargo test --test runtime` runs them, replaying
each one with a snapshot and restore before every step, and
`tests/test_runner.py` runs them through Python.
