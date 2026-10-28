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

The contract is [STANDARD-v1.1.0 §5](../../spec/STANDARD-v1.1.0.md#5-workflow-dsl);
[design-114 §16](../../tasks/design-114.md#16-executor-sans-io) is
background on the executor's design.

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
a run. Inputs or an `actor_identity` that do not fit the workflow, or are not
JSON data, also raise `RunStartError` (with no diagnostics).

## Actions and responses

| Action | Your host | Respond with |
|--------|-----------|--------------|
| `InvokeCapability` | runs `capability` with `inputs` (a waiting `delegate` that delegates again names the delegation it replaces in `replaces`) | `{"kind": "Output", "value": {...}}`, or `{"kind": "Error", "code": "R401"/"R402", "message": ...}` (any other code is read as R402) |
| `CreateCheckpoint` | takes a checkpoint before `step` | `{"kind": "Checkpoint", "checkpoint_id": ...}` |
| `Rollback` | restores `checkpoint_id` | `{"kind": "RolledBack"}` |
| `RequestApproval` | asks `approver` about `shown` | `{"kind": "Decision", "decision_id", "decision", "approvers", "digest"}`; `decision` is `approved`, `rejected` or `unavailable` |
| `RecheckSource` | re-reads `source` now | `{"kind": "Current", "value": ...}` |
| `AwaitEvent` | waits for a matching event until `deadline` | `{"kind": "Event", "event": {...}, "principal": ..., "identity": {...}}` (the authenticated party that delivered it, §5.15, and its `agent_identity`, §5.17; both optional, and a `principal` beside an `identity` must be the identity's), `{"kind": "LivenessLost"}` (R406), or `{"kind": "Error", "code": "R401"/"R402"/"R406", "message": ...}` (any other code is read as R402) |
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
  did not go ahead. A step that uses, directly or through other steps, an
  item from one of the `always_ask_trust_classes` of `identity@1` (or with
  no trust class) is asked of a person (`approver.kind: human`,
  `always_ask: true`) even when its approval names a standing mandate, and
  its records carry `always_ask: true`; unattended, it follows
  `when_unattended`. An `identity@1` input that resolves to anything but a
  list of known values fails its step (R402). A step with `identity@1`
  inputs that does not wait is your host's to filter: put the sender's
  `sender_identity` on each item you return, since an item without one
  counts as always-ask when `always_ask_trust_classes` is bound.
- **Waits.** `AwaitEvent` has a deadline from the step's `timeout`. Events
  that don't match (`event_type`, `source_kind`, `correlate`,
  `accept_from`, `sender_check`, `accept_trust_classes`) are dropped and
  the wait goes on. A lapse is R401;
  `LivenessLost` (or an `Error` with code R406) is R406, unless it comes
  after the deadline, which is R401.
- **Retries, deadlines.** `retry.max` (at most 1000) extra attempts for
  R401/R402/R406, with `none`, `linear` (1 s × n) or `exponential`
  (1 s × 2^(n−1)) backoff. A result after the step's deadline is R401. A
  step the executor itself refuses (an invocation whose inputs do not fit
  the workflow) is not retried: another attempt would be refused the same
  way. Times are milliseconds since the epoch, capped at the end of year
  9999.
- **Failure modes and recovery.** The first failure mode that matches the
  step's error code (`on_error`) or whose `when` is true applies. Its
  `action` runs first: `rollback` sends `Rollback`, `pause_and_checkpoint`
  sends `CreateCheckpoint`. Then it can loop back with injected
  `${_recovery.*}` context (up to `max_loops`, then `on_exhausted` or
  R404); when a loop runs a waiting `delegate` again (it is the target,
  or comes after it), that delegation names the one it replaces in
  `replaces`. It can also escalate to a handler (the run ends `escalated`), or end the run
  with the step's code — R402 when `when` fired on a step that did not fail
  ([STANDARD §5.12](../../spec/STANDARD-v1.1.0.md#512-recovery-and-escalation)).
- **Invocations.** An `invoke` step runs its workflow as a nested run, at
  most four deep, with `input_bindings.input` as its inputs; inputs the
  workflow does not declare, or a missing required one, fail the step
  (R402). The validator catches this before the run when `input` is
  literal. Any step whose resolved inputs are not I-JSON (nested deeper
  than the core's limit, say) fails with R402 rather than reaching the
  host.
- **Quorums.** A `constrain` step with a `quorum` counts the verdicts
  itself: one per reviewer whose delegate step ran, pinned to `pinned_to`,
  using the vocabulary, from fresh-context reviewers when required. Any
  blocking verdict, too few passes, too few full-sweep passes (`min_full`)
  or uncovered model families fail the step with F504.

Start a run with `actor_identity=` (an `agent_identity`, such as
`AgentDescriptor.identity()` of a registered agent) to say who runs it:
every action record then carries it as `actor_identity`, and `actor` is its
`kind`.

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
from, and a signed snapshot only with its key; `restore` raises
`RunStartError` for a state that is not well formed or a snapshot that fails
its HMAC check. A response that does not answer the pending action is
refused, and the run is left unchanged. Under `drive`, a refused answer to
an `InvokeCapability` fails that step (R402), as a host exception does; a
refused answer to any other action raises `HostResponseError`, carrying the
`.action` and the host's `.response`, with the run still waiting on that
action. If a run needs more than `max_actions` answers in one `drive`, or a
host returns `None` (nothing yet) for one action more than `max_polls`
times (default 100,000, about 28 hours at the default 1 s
`poll_interval_ms`; each action has its own count),
`RunIncomplete` is raised with the live run in `.run`, so you can snapshot
it or drive it on. `HostResponseError` is a `RunIncomplete`.

## Conformance

`tests/conformance/runtime/*.json` are scripted runs. Each one has a
catalog, inputs, a script of expected actions and responses, and the
expected end and trace. They are generated by
`scripts/gen_runtime_fixtures.py`: edit them there and regenerate (CI runs
it with `--check`). `cargo test --test runtime` runs them, replaying
each one with a snapshot and restore before every step, and
`tests/test_runner.py` runs them through Python.
