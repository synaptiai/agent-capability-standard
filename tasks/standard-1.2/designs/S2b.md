# S2b design: host protocol and executor conformance (ACS 1.2.0)

> **Reconciled (cross-stream pass).** Final codes: R408 `CANCELLED`, W618
> `UNKNOWN_JOIN`, W619 `GROUP_MATE_READ`, renumbered from the provisional
> numbers everywhere in this file (C2). Edited
> here: the §5.19.2 start item holds every workstream's start members (C3);
> §5.19.7's table holds S5's and S6's reasons (C5); the §5.2 retry row
> takes S3's parenthesis (C6); §10.1, §10.3 and §10.5 are merged with S1,
> S3–S6 (C7, C8); the status description keeps S2a's sentence (C13);
> `recorded_by` gains `settings` (C14); (`run_id`, `id`) is a *delivery
> key*, distinct from S5's idempotency key (C28); the statements that the
> executor never sees the header are removed (C4); `require_record` joins
> the W616 list (C12); the §9.8 sentence is dropped for S3's table (C30).
> The reason plumbing of ACS-62 and `refs::executable_roots` land in the
> foundation (C23); merged schema members are in FOUNDATION.md part B.
> Merge order: third, in the chain (C35).

Workstream S2b. Findings: ACS-14, ACS-15, ACS-20, ACS-30, ACS-31, ACS-32,
ACS-33, ACS-34, ACS-37, ACS-45, ACS-62.
RFC: RFC-0006 (host protocol, approval and runs), shared with S2a; S2b
writes the header, the summary and Part B (host protocol, runs, audit
records), section 9 below.

Base: main 6b3e40b. Standard 1.1.0 stays unchanged; every normative change
below is text for `spec/STANDARD-v1.2.0.md`. Section numbers marked *(new)*
are final (FOUNDATION.md part D): S1 adds §5.2.2, §5.18 and §10.4, S2a adds §5.14.1. This
design adds §5.2.3, §5.10.2, §5.19 (the host protocol; S2a's "§HP" is
§5.19; §5.19.1–§5.19.7 keep the numbers other workstreams cite, and the
run record is the new §5.19.8), §6.4, §8.4 and §10.5.

Revision 2 (after adversarial review): the run record (§5.19.8) is an
`ActionRecord` every host keeps, implemented in the core and the runner; the
retry backoff, the executor-composed step outputs and `Completed.outputs`
are stated, and every member a runtime fixture pins is audited against
normative text (6.1a); unknown response members and an undefined `reason`
are ignored as in 1.1; `run_id` MUST be unique; restored-state integrity is
worded to what a digest and a MAC can do; cancellation records follow the
step's state; taken records and trace stay committed to by the state; an
`audit` step can no longer forge records; §6.4 allows exporting; event
triggers accept per sender policy and start at most one run per `event_id`;
`OverlapGate.resumed()`; the plugin hook reports every capture failure;
§5.2.3's loop wording; the B9 rationale, `grounded_agency/errors.py` and two
informative docs.

## 0. Summary

| Finding | Decision | Kind of change |
|---|---|---|
| ACS-37 protocol only in a guide | New §5.19 Host Protocol (every action, response and run operation named; the members the executor computes, the step outputs it composes and `Completed.outputs` defined; the retry backoff stated in §5.2), `schemas/host_protocol.schema.json` (supporting schema), new conformance class **EX** (§10.5) for which the runtime fixtures become normative (except `trace_kinds`) after an audit of every member they pin (6.1a); response members the protocol does not define are ignored, as in 1.1; `ActionRecord.approval.decision_id`, a fixture-format schema | Compatible additions and statements of 1.1 behaviour; no workflow and no run changes |
| ACS-31 host obligations | §5.19.4: one writer, save before acting, at-least-once delivery keyed by (`run_id`, `id`), interrupted turns; integrity: the executor detects corruption and, given a key, refuses a state whose MAC fails, and a host whose stored states others can change MUST use a key; §5.19.2: `run_id` MUST be unique among the runs whose records or keys the host keeps; `run_id` on every action; `tick` reports whether it changed the run; Python `Host.withdraw`; the runner refuses a reused `run_id` | New host duties (MINOR); executor output gains `run_id` (compatible addition) |
| ACS-32 cancel | `cancel(reason, now)`: ends the run with `Failed` R408 `CANCELLED`, no retry, failure mode, recovery, handler or rollback; open records become `cancelled` (new `ActionRecord.status` value); in record mode `actions` every step that has started and has no record gets a `cancelled` one (by the step's state, not the pending action's kind), and a pending failure-mode checkpoint or rollback its own; a run that ended `deferred` can be cancelled; no automatic rollback, the terminal action names the latest checkpoint | New operation, opt-in by the host; new code R408; new enum value (§11.4 compatible) |
| ACS-34 wake-up time | §5.19.3 states the tick boundaries (Sleep at `until`; time-out after the deadline) and that liveness is the host's; `wake_at()` in core and Python; `WorkflowRunner.advance()` turn function; event-driven recipe in the guide; fixtures check `wake_at` and tick results | Clarification of 1.1 behaviour + new operation |
| ACS-33 snapshot size | Core: `take_trace()`, `take_records()` (offsets keep `seq`, record indices and `action_id` sound; a SHA-256 chain head per kind keeps the signed state committed to everything taken), terminal action derived from state instead of stored twice; snapshot version 2; size model in the guide; §5.19.4: an executor that lets a host take records MUST keep such a commitment | Implementation + one executor MUST for an optional feature |
| ACS-14 triggers | §5.10.2: the host evaluates triggers; attendance; event triggers start a run per event the host accepts under its sender policy, at most one per `event_id`; fire times in the declared time zone with RFC 5545 §3.3.5 for clock changes; `every` anchored at the Unix epoch; `overlap` (with resumed runs) and missed fire times defined; `_core.next_fire`, Python `triggers` module (`OverlapGate` with `resumed()`, `EventGate`), runner `start(trigger=…)`; normative trigger vectors, pinned to a tzdata release | New host duties and clarifications (MINOR); no workflow changes |
| ACS-15 parallel groups | New §5.2.3: members unordered, MAY run in any order or concurrently, the §5.19 executor runs them in list order; group complete when every member finished; on escalation or end unfinished members are abandoned, on a loop execution continues from the target; `join` has one defined value `all_complete`; W618 for any other value; W619 for a read of a group mate's store | Clarification + two warnings (warning-first); no repository catalog hits either |
| ACS-30 audit record | New §6.4: an audit record is an `ActionRecord` or a canonical event, written or exported in those shapes; `ActionRecord` 1.2.0 gains correlation and integrity fields; `rejected` covers refusals by an executor or a safety layer; executor record mode `actions` (opt-in by the host) records every step that runs, every failure-mode checkpoint and every rollback; `audit` records its `event` inside a record of its own (`recorded_by` and chain fields are the implementation's, never the event's); `audit` gains optional `require_record` input and `record` output; the trace is declared informative; audit skill, orchestrator, plugin hook line, `CoordinationEvent` and the TypeScript `TraceEntry` aligned | Ontology and canonical schema additive; record mode opt-in |
| ACS-20 capture failure | §6.4: required vs best-effort capture, and no capture fails silently; `require_record: true` fails an `audit` step that did not record (R402, reason `not_recorded`); §5.19.8: every host keeps every run's **run record**, an `ActionRecord` derived from the terminal action (failed and cancelled runs included), with the run's action records; core `Run.run_record()`, `RunResult.run_record`, `WorkflowRunner(archive=…)`; §8.4 defines `allow_manual_override`, `requires_anchors`, `audit_required`; SDK evidence collector `required=`; the plugin hook reports every call it does not log or cannot sign | Opt-in per step; new host duty; trust-model descriptions; plugin behaviour |
| ACS-45 protocol traffic | §5.19.6: what a host transmits to perform a protocol action is not a `send` step, provided it carries only the action's values | Clarification + one host MUST NOT |
| ACS-62 unsupported domain | §5.19.7: optional `reason` on an `Error` response, three defined tokens (`unsupported_capability`, `unsupported_domain`, `not_recorded`) and `x-` vendor tokens; any other value is ignored (treated as absent, traced), as 1.1 ignored the member; carried to the `Failed` action and the record's `reason_code`; modality guide updated | Optional response member (compatible) |

New codes: R408 `CANCELLED`, W618 `UNKNOWN_JOIN`, W619 `GROUP_MATE_READ`.
No new schema-error code is needed (final allocation: FOUNDATION.md part C).

---

## 1. Per finding: decision, rationale, how it fixes the finding

### ACS-37 — The host protocol is defined only in a guide

**Decision.**

1. A new §5.19 *Host Protocol* in the Standard names every action, every
   response, the run operations (start, next, submit, tick, wake at, cancel,
   save/restore, resume), the time rules, the host's obligations, protocol
   traffic and error reasons.
2. A new **supporting schema** `schemas/host_protocol.schema.json` (JSON
   Schema 2020-12, hand-written, tested) defines each action and response
   exactly, plus, marked informative, the reference executor's snapshot
   envelope and trace event. It is listed in §6.1 beside
   `review_verdict_schema.yaml` and `agent_identity_schema.yaml`: required of
   an executor (class EX), not of every implementation.
3. A new conformance class **EX** (§10.5), separate from validator levels
   L1–L4 and from S1's class SL (§10.4). The runtime fixtures become
   normative for EX, except `trace_kinds`; executor-written prose
   (`message`/`reason` strings the executor composes, a quorum's
   `violations` texts) is not compared.
4. Before the fixtures become normative, every member they pin was audited
   against the Standard's text (6.1a). Four gaps were found and are closed
   by stating the reference executor's behaviour, so no fixture changes:
   the retry backoff schedule (§5.2: `linear` attempt × 1 s,
   `exponential` 2^(attempt−1) s), when `Sleep.until`, `deadline` and
   `expires_at` fall (§5.19.1), what `Completed.outputs` holds (the root
   workflow's stores by `store_as`), and the outputs the executor composes
   for wait, `invoke` and quorum steps (§5.19.1). The generator then refuses
   a fixture that pins a member outside the audited list.
5. Responses: a member the protocol does not define is ignored, as the
   reference executor does on 1.1 (serde without `deny_unknown_fields`), and
   the schema allows such members; a host MUST likewise ignore an action
   member it does not know, so later versions can add members.
6. `ActionRecord.approval.decision_id` (optional) in `world_state_schema.yaml`
   1.2.0; the reference executor writes it on every decided approval.
7. A fixture-format schema, `tests/conformance/runtime/schema/fixture.schema.json`,
   so another executor's harness can be built from it.

**Options considered.**
- Schema generated from the Rust types (`schemars`) vs hand-written: a
  generator adds a dependency and its output follows Rust names (`Option`
  members as `null`, flattened enums) that the Standard should state on its
  own terms. Hand-written, validated in tests against every action the
  executor issues and every response in the 175+ fixtures, catches drift both
  ways at lower cost. Chosen: hand-written and tested.
- A required §6.1 schema vs a supporting one: a validator-only implementation
  has no use for it. Supporting, required for class EX.
- Normative trace: pinning trace kinds would freeze the reference executor's
  internal decision log (`checkpoint_consumed`, `event_dropped`, …). What a
  host and an auditor need is in actions, responses, terminal actions and
  action records, which are normative. The trace stays informative (ACS-30
  also asked).
- Normative prose: a second executor cannot be required to word reasons
  identically; the codes, statuses and machine-readable `reason_code` carry
  the meaning.
- Strict responses (`additionalProperties: false`, refuse unknown members)
  vs lenient: strict would refuse responses a 1.1 host sends today (the
  reference executor accepts and ignores extra members), and a refused
  response stalls the run (`WorkflowRunner` raises). Lenient, stated, and
  the schema matches.
- Making the fixtures normative for what they pin as-is vs auditing first:
  four fixtures pin five `Sleep.until` values (four from a backoff schedule
  found only in the code and the guide, one from a delay), and 38 pin
  `Completed.outputs`, which the 1.1 text never defines. A second executor following the text alone would fail
  them. Auditing and stating the behaviour (a clarification: the reference
  executor is the only one, and the guide already described it) keeps the
  fixtures and makes them fair.

**How it fixes the finding.** Every action and response is named in the
Standard and defined by a schema an implementation can build against;
every member a normative fixture checks is stated in the text;
`decision_id` is on the canonical approval record; executors have a class to
claim and a normative test suite to pass; host-binding statements (how a
binding names the operations) stay informative, as the finding asked.

### ACS-31 — Host obligations

**Decision.** §5.19.4 states four obligations of a host that saves runs:
(1) one writer per run; (2) save the state after every operation that changed
it and before acting on the action it left pending; (3) delivery is at least
once, so side effects are idempotent under (`run_id`, `id`); (4) an
interrupted turn leaves the run unchanged, and the host continues from the
latest saved state or cancels. Then integrity, worded to what each mechanism
can do: the executor MUST detect a corrupted state (a digest saved with it),
and, given a key, MUST refuse a state whose MAC does not verify; a digest
alone cannot show who wrote a state (anyone who can change it can recompute
it), so a host that keeps states where parties other than the run's writer
can change them MUST use a key. An executor that lets the host take records
or trace events out of the state (ACS-33) MUST keep a commitment to them in
the state. Every host, saving or not, keeps every run's record (§5.19.8,
ACS-20).

§5.19.2: `run_id` MUST be unique among the runs whose records, run records
or idempotency keys the host keeps. With a SHOULD, two runs under one
`run_id` (a cancelled run restarted under its old id, say) share keys, and a
host following item 3 would give run B the response it kept for run A under
the same (`run_id`, `id`): wrong data, undetected. The reference runner keeps
its `uuid4` default, documents that a caller-supplied `run_id` must be fresh,
and refuses one it has already started.

Supporting changes: every action carries `run_id` (so a host need not compose
the key); `tick` returns whether it changed the run, so a host knows when to
save and that a pending action it was performing has timed out; §5.19.3 says a
time-out is not announced otherwise; the Python `Host` gains `withdraw(action,
why)`, called when an action it was polled for times out or the run is
cancelled; `WorkflowRunner.drive`/`advance` gain `save=` and `key=` so the
reference host saves after every change.

**Options.** A per-action idempotency token minted by the executor vs the
pair (`run_id`, `id`): `id` is already unique within a run and is re-issued
unchanged after a restore (verified at 968 of 968 replay points), so the pair
is the key; no new member beyond `run_id`, which must then be unique.
Integrity: "MUST refuse a changed state" (the first draft) promised tamper
detection that a keyless digest cannot give (the core's own comment: "the
digest only proves the snapshot was not corrupted, not who made it"); the
wording now matches the mechanism and puts the key duty where tampering is
possible.

**How it fixes the finding.** Single writer, snapshot persistence,
idempotency (with a key that cannot collide across runs), the at-least-once
nature of a restored action, the silent time-out, aborted executions and
state integrity are all stated; `run_id` is on every action; the reference
runner implements the save points, the time-out notice and the `run_id`
check.

### ACS-32 — No way to end a run as cancelled

**Decision.** A run operation `cancel(reason, now)`:

- ends the run with a `Failed` action, code **R408 `CANCELLED`**, `message` =
  the reason, `step` = where it was, and `checkpoint_id` = the latest
  checkpoint the run knows of (if any);
- runs no retry, failure mode, recovery loop, handler or rollback;
- withdraws the pending action (a later response is refused: the run ended);
- sets every `approved` or `planned` record to the new status `cancelled`,
  with code R408 and the reason;
- in record mode `actions`, by the step's state, not the pending action's
  kind: every step that has **started** in its current pass (the executor
  issued a `CreateCheckpoint`, `InvokeCapability` or `AwaitEvent` for it,
  or, for an `invoke`, started its nested run) and has no record of the
  pass gets a `cancelled` record, in every frame of the run. That covers a
  step waiting out a retry's backoff (its first attempt ran) and a waiting
  delegate whose delegation was sent (§5.13). A pending failure-mode
  checkpoint (`pause_and_checkpoint`) or rollback gets its own `cancelled`
  record, as it gets its own `executed` or `failed` one when it completes;
- may also be applied to a run that ended `deferred`: its queued actions will
  never be carried out (and the run is no longer resumable, §5.14.1).

**Options.** (a) A dedicated `Failed` code vs a new `Completed` outcome
`cancelled`: hosts already treat `Failed` as "the run did not complete", and
`Completed { outcome: cancelled }` reads as a contradiction. (a) chosen.
(b) Per-action-kind responses (the finding's alternative) were rejected: they
trigger retries, failure modes and recovery, which is exactly what a stop
must not do. (c) Roll back automatically: rejected. A host that cancels may
have lost the means to roll back (a client stop, a shutdown), a rollback is
itself a world-changing action needing a round trip, and the workflow's own
rollback policy lives in failure modes that cancellation deliberately skips.
The terminal action names the latest checkpoint so a host can restore it
itself. (d) Which steps get a `cancelled` record: by the kind of the pending
action (the first draft: `InvokeCapability`, `CreateCheckpoint`, `Rollback`)
missed a waiting delegate whose task was sent (`AwaitEvent` pending) and a
step waiting out its backoff (`Sleep` pending), so a cancelled run lost the
evidence that a task was delegated or an attempt made, and the same step was
recorded if it failed but not if it was cancelled. By the step's state
(started, no record of the pass) chosen; it also covers the `invoke` steps of
the frames above a cancelled nested run.

**How it fixes the finding.** A run can be ended as cancelled, with a cause
recorded in the terminal action, the trace, the open records and, in record
mode `actions`, a record of every step that had started, without recovery;
§9.5 has the code; the rollback question is answered.

### ACS-34 — No call for the next wake-up time; no event-driven recipe

**Decision.** `Run.wake_at()`: `until` for a pending `Sleep`; the deadline
(or `expires_at`) plus 1 ms for an action that has one; none otherwise (and
none once the run ended, or when the deadline is the maximum time). Liveness
is never a wake-up: §5.19.3 says liveness is the host's to watch. §5.19.3
states the tick boundaries (`>= until`; `> deadline`) as normative. The
Python runner gains `advance(run, host)`, one turn of an event-driven host
(tick, perform what can be performed, return the wake time or the result),
and `drive` becomes a loop over it that uses `wake_at` instead of
`deadline + 1`. The guide gains an event-driven host recipe. Fixtures check
`wake_at` explicitly, and every harness checks, at every `tick` entry of
every fixture, that the tick changed the run exactly when its time reached
the wake time.

**How it fixes the finding.** A turn-based host can ask the run when to wake
it, the boundaries are stated and tested, liveness is assigned to the host,
and a recipe exists.

### ACS-33 — Snapshots grow with the run

**Decision.** In the reference core:

- `take_trace()` returns and removes the trace recorded so far; `trace_base`
  in the state keeps `seq` continuous;
- `take_records()` returns and removes the longest prefix of *settled*
  records (status not `planned`/`approved`, and referred to by no step,
  deferral or queued action); `records_base` keeps record indices and
  `action_id` numbering sound;
- the terminal action is no longer stored with copies of the records,
  outputs and deferrals: the state stores its head (`kind`, outcome or code,
  …) and `next()` derives the rest. A finished run's snapshot no longer
  holds the records and outputs twice;
- the state keeps a running SHA-256 chain head over what was taken,
  `records_taken_sha256` and `trace_taken_sha256` (each step:
  `h = sha256_hex(h ‖ canonical_json(item))`, starting from the empty
  string), so a state whose digest or HMAC verifies also commits to every
  record and trace event taken from it, in order; the host checks its
  archive against the heads;
- `SNAPSHOT_VERSION` 2 (shared with S2a); version 1 states still restore.

In 1.1 every record was inside the authenticated snapshot. Without the chain
heads, a host that adopts `take_records` would lose that: records in host
storage could be dropped or edited unseen. With them, the signed state keeps
vouching for the taken records (two 64-digit hex strings of fixed
overhead, not growth). §5.19.4 makes such a commitment a MUST for any executor that offers
taking, and §5.19.1 defines `action_records` as the run's records less those
taken, while the run's record (§5.19.8) includes them. The guide documents
the size model and the measured figures, and the turn-based recipe takes the
trace each turn.

**Options.** `snapshot(without_trace=True)` was rejected: a restored run
could not tell whether its trace was complete, and the trace would still grow
in memory. Records by index offset vs re-keying records by `action_id`:
offsets are a smaller change to the executor. A count of taken items vs a
hash chain: a count detects a dropped record but not an edited one; the
chain detects both at the same cost.

**How it fixes the finding.** A host can move the trace and settled records
out of the run state while digest checks stay sound and the state still
authenticates what was moved; the duplicate terminal copy is gone; the size
model is documented.

### ACS-14 — Trigger evaluation unassigned; no shared fire-time function

**Decision.** New §5.10.2 *Evaluating Triggers*:

- The host evaluates triggers; the executor never reads them.
- A host that starts runs from triggers MUST apply the trigger's attendance
  (declared, else the kind's default), start event-trigger runs with the
  event as the `delivers_to` input, and start schedule runs at their fire
  times as `overlap` allows.
- **Event triggers** start one run per event the host *accepts*: the event
  matches the trigger (`event_type`, `source_kind`) and the host's sender
  policy admits its sender (§5.17's checks where the workflow declares
  `identity@1`); and at most one run per (trigger, `event_id`), so an event
  delivered again (at-least-once delivery) starts nothing new. A host MAY
  drop an event its policy does not admit and SHOULD record the drop. (The
  first draft said "for each event whose `event_type` equals the
  trigger's", which forbade a host from dropping unauthenticated events,
  so anyone able to post such an event could start unattended runs with
  its own input, and a redelivered event started a second run.)
- **Fire times.** `cron` fires at each matching local minute of `timezone`;
  local times map to instants by RFC 5545 §3.3.5 (a repeated time is its
  first occurrence; a skipped time is read with the offset before the change);
  times that map to one instant fire once. `every` fires at the multiples of
  its interval (whole milliseconds, rounded up) since the Unix epoch; its
  `timezone` does not affect it.
- **Overlap.** Defined against the runs *this trigger* started: `skip`
  drops a fire while one is in progress; `buffer_one` holds one fire until
  none is; `allow_all` starts runs alongside. A run that ended `deferred`
  and is resumed is in progress again. Missed fire times (host not
  evaluating) count, together, as one fire time when it resumes.
- The core gets `trigger::next_fire(schedule, after_ms)` (exposed as
  `_core.next_fire`), the Python package a `triggers` module (attendance;
  `OverlapGate` with `fire`, `missed`, `ended` and `resumed`; `EventGate`,
  which matches events and admits each `event_id` once, with an optional
  sender policy and a pluggable store of seen ids) and
  `WorkflowRunner.start(trigger=…, event=…)`, which passes the event
  through the trigger's `EventGate` and refuses a redelivered one.
- Language-neutral vectors `tests/conformance/triggers/{fire_times,overlap,attendance,events}.json`,
  generated by `scripts/gen_trigger_vectors.py` from an independent oracle
  (Python `zoneinfo`), normative for §5.10.2. The fire-time file names the
  tzdata release it was computed with; a host conforms with that release or
  any release that agrees with it on the vector dates (a tzdata correction
  for a past date must not make a conformant host fail).

**Options.**
- DST: skip the nonexistent time; fire at the gap end; RFC 5545 (offset
  before). RFC 5545 chosen: it is a published normative rule (no new
  semantics to invent), keeps the spacing of a `*/15` schedule through the
  gap, and still fires a daily job on the change day.
- `every` anchor: the trigger's activation time; the end of the previous run;
  the Unix epoch. Activation and previous-run anchors depend on host state,
  so two hosts (or one host after a restart) would compute different times.
  The epoch is the only anchor every host computes identically. A host that
  wants a local-time grid uses `cron`. No new `anchor` field (it would be a
  1.2 workflow feature for no capability `cron` lacks).
- Overlap scope: per workflow vs per trigger. Per trigger, since `overlap` is
  declared per trigger; a manual run does not suppress a schedule.
- The TypeScript binding hosts no workflows (the integration guide explains
  it needs a JavaScript build of the executor), so it gets no `next_fire`;
  the vectors are language-neutral for a future JavaScript build.

- Event deduplication: per workflow, per trigger, or none. Per trigger,
  keyed by the canonical event's required `event_id`: two triggers of one
  workflow may both match an event and each starts its run, as each would
  for a distinct event. The runner keeps the seen ids in memory by default;
  `EventGate(seen=…)` takes any set-like store a host persists.

**How it fixes the finding.** The component is named, attendance, time zone,
event acceptance and overlap are host obligations, the three `overlap`
values (resumed runs included) and the `every` anchor (and DST) are defined,
and one fire-time function with vectors is shared by every binding of the
core.

### ACS-15 — Run-time meaning of `parallel_group` and `join`

**Decision.** New §5.2.3 *Parallel Groups*:

- Members of a group are unordered relative to each other (as §4.3 already
  says for the static rules); an executor MAY run them one at a time in any
  order, or concurrently. An executor that speaks the §5.19 protocol issues
  one action at a time and runs them in list order. (Concurrent dispatch, a
  separate action shape, is left to a later version.)
- A group is complete when every member has finished (completed, skipped or
  deferred). A member's failure is handled by its own failure modes; a
  recovery that escalates or ends the run abandons unfinished members; a
  recovery loop abandons the current pass and continues from the loop's
  target, so members at or after the target run again (the first draft said
  "a member that has not started does not run" for loops too, which is not
  what the executor does: `recover` clears the stores from the target on and
  runs again in list order).
- `join`: one defined value, `all_complete` (default). Any other value, or a
  `join` on a step with no `parallel_group`, is **W618** and ignored. The
  glossary's `any_complete` is withdrawn: under one-action-at-a-time dispatch
  it would mean "run only the first member", and a race needs concurrent
  dispatch; a later version may define it with that.
- A member that reads a group mate's store is **W619**: the value exists
  only if the executor ran that mate first. (The audit found this gap.)

**Options.** Removing `join` (MAJOR, or deprecation W603 with a migration of
20+ vendored catalogs and a contributed fixture kept as sent) vs keeping it
with one value: keeping it costs nothing, every repository use is
`all_complete`, and a later version can add values. Making the group-mate
read an error (B202) would invalidate 1.1 workflows: warning-first.

**How it fixes the finding.** Serial execution in list order is stated to
conform; `join` values are enumerated and defined; what happens to
unfinished members is defined; concurrent dispatch is deferred as the
finding proposed. No repository catalog, example or fixture raises W618 or
W619 (scanned: 343 workflows in tracked YAML, all runtime and contributed
fixtures).

### ACS-30 — No canonical audit record

**Decision.** New §6.4 *Audit Records*:

1. An **audit record** is an `ActionRecord` (`world_state_schema.yaml`) for
   an action, or a canonical event (`event_schema.yaml`) for an observation.
   Every implementation that writes audit records writes them in, or
   exports them as, these shapes: a binding may keep its own internal form
   (the TypeScript `TraceEntry`, the Python adapter's call records,
   `CoordinationEvent`) provided it can give each as an audit record.
2. `ActionRecord` 1.2.0 gains optional `run_id`, `frame`, `step`,
   `capability` (correlation), `tool`, `call_id` (tool calls, S1),
   `checkpoint_id`, `code`, `reason_code`, `details`, `recorded_by`
   (`name`, `version`, `config_sha256`), and the chain fields `prev_hmac` and
   `hmac`; `status` gains `cancelled`; `rejected` covers a refusal by the
   executor or a safety layer (with `code`) as well as by approvers;
   `approval` gains `decision_id`.
3. Executor records: as in 1.1 for approval steps (now with the correlation
   fields and `decision_id`), and, in **record mode `actions`** (a start
   option, default `approvals`), one record per pass of every step that runs,
   plus one per failure-mode checkpoint and one per `Rollback`, each with the
   step's `purpose` as its `intent` like every other record. The default
   keeps 1.1 runs' records identical except for the added members.
4. `audit` (ontology 2.2.0): the implementation performing an `audit` step
   writes a record **of its own**: an action record (capability `audit`,
   status `executed`) whose `details.event` holds the event as given,
   whatever its shape. It sets `recorded_by` to itself and computes any
   chain fields itself; nothing in the event can set them, or claim the
   record's `actor_identity`, `approval` or status. New optional input
   `require_record`; new optional output `record`.
5. The executor trace is not an audit record and stays informative.
6. Alignment: the audit skill writes `ActionRecord` lines in that form; the
   orchestrator's `audit` step writes through `CoordinationAuditLog` and
   returns the contract's `recorded`/`record` output; the plugin hook's line
   becomes an `ActionRecord` with the chain fields (and `hooks/README.md`
   stops saying it implements `audit`); `CoordinationEvent.to_action_record()`;
   the TypeScript binding's `actionRecord(entry, scope)`, which maps a
   refused call to `rejected` with its code.

**Options.** Typing `audit.event` as `oneOf[ActionRecord, event]` would make
about 25 reference audit steps and §12.5's example B203 (MAJOR); keeping
`event` an object and defining how it is recorded is compatible. Recording a
record-shaped event "as it is" (the first draft) let a workflow step write
records that claim another writer (`recorded_by` of the executor or a
safety layer), a human `actor_identity`, an approved `approval` with a
`decision_id`, or chain fields: forged records indistinguishable from real
ones. Always wrapping the event in the implementation's own record (the
event keeps its shape under `details.event`) closes that and is simpler than
a flag. Records for every step by default would change the `action_records`
of every 1.1 run (and break the exact-length arrays in the fixtures), so the
full record is opt-in by the host. Opting in by `spec_version: "1.2"` was
rejected too: the executor does receive a workflow's target (its
`spec_version`, and the catalog header the start operation passes, §11.5),
but the version is the author's statement while the audit trail is the
operator's need: an operator must be able to record every step of a 1.1
workflow as well. Changing the bindings to store `ActionRecord`s internally
vs allowing export: export keeps their internal forms (and their tests) and
gives the same records at the boundary; the normative text says so.

**How it fixes the finding.** One canonical record type (two shapes, by
purpose), with correlation and integrity; `audit.event` has a defined
meaning that cannot forge records; the six shapes are reduced to the
canonical two (the trace is declared informative, the hook, skill and
orchestrator write `ActionRecord`s, the coordination log and the binding
export them, as the reworded §6.4 allows); the hook no longer claims to
implement `audit`.

### ACS-20 — Capture failure; failed runs end without audit

**Decision.**

1. §6.4 *Required and best-effort capture*: the records the Standard
   requires (an executor's records in the run state; a safety layer's call
   records, S1 §5.18.8, refused with R407 when unwritable; every run's run
   record, §5.19.8) are required; any other capture (evidence collection
   from tool results, a host's own logs, the plugin's tool-call log) is
   best-effort unless the host states it is required; a required capture
   that fails is reported where the action's result goes: for a step, R402
   with reason `not_recorded`; a best-effort capture that fails MUST still
   be reported where the operator sees it. No capture fails silently.
2. `audit` steps: a step that binds `require_record: true` fails with R402,
   reason `not_recorded`, when its output's `recorded` is not `true`
   (retryable, matchable with `on_error: R402`). Without it the step
   completes as in 1.1, and an after-gate may stop on `recorded == false`.
   So a workflow *may* ignore `recorded: false`, and the Standard says so.
3. Failed runs: new §5.19.8 *The Run's Record*. Every run has a **run
   record**, an `ActionRecord` derived from its terminal action:
   `action_id` and `run_id` the run's `run_id`; `frame`; `step` (of a
   `Failed`); `timestamp` the run's clock at its end; the run's actor;
   `intent` `run <workflow>`; `status` `executed` (`Completed`), `planned`
   (ended `deferred`, still resumable), `cancelled` (R408) or `failed`;
   `code`, `reason_code`, `checkpoint_id` from a `Failed`; `details`
   `{kind, outcome, cause, ended, message, deferred, records}` (`records`:
   how many action records the run wrote, taken ones included, so a missing
   one shows). **Every host that runs workflows** MUST keep it, with the
   run's action records (those it took included), where it keeps its audit
   records, before it discards the run's state; a run resumed after
   `deferred` replaces its record when it ends again (same `action_id`). In
   the default record mode, a run with no approval steps that fails now
   leaves a record: this is the part of the finding the first draft did not
   fix (its duty sat in the list for hosts that save state, and its record
   was a terminal action, which §6.4 does not count as an audit record).
   Reference: core `Run::run_record()` (`_core.Run.run_record()`),
   `RunResult.run_record`, and `WorkflowRunner(archive=…)`, which hands every
   ended run's result (run record and records) to the host's archive before
   `run`, `drive`, `advance` or `cancel` returns. The nine reference recovery
   texts that say "no audit is recorded" point at the run record.
4. §8.4 *Manual Overrides*: `allow_manual_override`, `requires_anchors` and
   `audit_required` are defined; with `audit_required`, an override takes
   effect only after its audit record is written. `grounded_agency/trust.py`
   gains `manual_override(...)` and `TrustModel.manual_override(...)` (5.11).
5. SDK `create_evidence_collector(..., required=False)`: with `required=True`
   a capture failure is reported to the model in the hook result
   (`R402 EXECUTION_FAILED: … (not_recorded)`) and logged at error level.
6. Plugin hook `posttooluse_log_tool.sh`: its log is best-effort, but it
   reports every capture failure. On every path where a tool call is not
   logged, or is logged without a valid HMAC or chain link, it prints why to
   standard error and exits 1 (a non-blocking hook error the user sees):
   no `jq`; a symlinked `audit.log` (refused, as now, but no longer exit 0);
   a failed entry build; no `openssl` (no line is written, rather than one
   with the placeholder `no-hmac-available`, which made the rest of the log
   fail verification); an unreadable `hmac` on the log's last line; a digest
   that could not be computed (the line is written with `input_sha256:
   "unavailable"`). It exits 0 only for a call it logged and for input that
   is not a tool call. `hooks/README.md` says so.
7. `spec/SECURITY.md` §1.1: "Audit trail exists for all changes" is made
   accurate (which records, under which mode).

**Options.** "Let a workflow declare an audit step that runs on failure" (a
`finally` step) vs a host-side record: the host-side record needs no DSL
construct and covers every failure, including ones before any audit step; a
`finally` construct would add executor states and interactions with
deferral, escalation and cancellation. Host-side record chosen; a later
version may still add a construct. Who derives the run record: the host, by
the stated rule (any host can, from the terminal action, the `run_id`, the
clock and the actor it gave), with the executor MAY offer it; the reference
core does, so every binding of it derives the same record. A new code for
"not recorded" vs R402 with a reason: reusing R402 keeps §5.2's retry rule
and §5.12's `on_error` list unchanged. For the hook without `openssl`:
write the line without a valid MAC (and break verification of everything
after it) vs write nothing and report: a log that verifies is worth more
than one line, and the report makes the loss visible.

**How it fixes the finding.** Best-effort vs required is stated, and no
capture failure is silent; a required capture failure fails the step with a
defined diagnostic; `audit_required` obliges something definite; a workflow
knows whether it may ignore `recorded: false`; every run, failed or
cancelled, has a run record every host keeps, in the canonical shape, and the
reference runner hands it over; the SDK collector and the hook no longer
fail silently.

### ACS-45 — Is protocol traffic a `send`?

**Decision.** §5.19.6: what a host transmits to perform `RequestApproval`,
`RecheckSource`, `AwaitEvent` (probes included) and the terminal action is
protocol traffic, not a step; the flags of `send` do not apply, provided it
carries only the action's values. A host MUST NOT add other values of the run
to it; anything else a workflow means to transmit is a `send` or `inquire`
step. A tool-calling host that delivers protocol traffic through a tool
classifies the tool as a host action under S1's §5.18.3.

**How it fixes the finding.** The line is drawn in the Standard, with the
proviso the finding proposed, and connected to RFC-0005's classification so
a tool used for an approval prompt is not itself an unbound `send`.

### ACS-62 — No machine-readable place for `unsupported_domain`

**Decision.** `Error` gains an optional `reason` (§5.19.7): a token the
Standard defines (`unsupported_capability`, `unsupported_domain`,
`not_recorded`) or an `x-` vendor token. Any other value (another string, a
number, an object) is **ignored**: the executor treats the `Error` as having
no reason, records the value it ignored in the step's trace event
(`reason_ignored`), and goes on. The code still decides what the run does
(`unsupported_domain` fails the step with R402, retries apply). The reason
travels to the step's trace event, the run's `Failed` action (`reason`) and
the step's record (`reason_code`). `docs/guides/MODALITY_HANDLING.md` §1.3
uses it. A fixed message prefix was rejected: messages are prose, and
parsing prose is what the finding is about. Refusing an `Error` whose
`reason` is outside the grammar (the first draft) was rejected: a 1.1 host
that sends a free-text `reason` (accepted and ignored today, as any extra
member) would have every `Error` refused, and its runs would stall
(`WorkflowRunner` raises on a refused submit). The reference executor reads
`reason` as any JSON value for the same reason (a non-string `reason` must
not make serde refuse the response).

**How it fixes the finding.** `unsupported_domain` has a defined,
machine-readable place, the guide shows it, and the earlier part of the
finding (guide cites §5.2, anchor kinds) was already fixed.

---

## 2. Normative text for `spec/STANDARD-v1.2.0.md`

Section numbers are those of 1.1.0 unless marked *(new)*.

### 2.1 §1 Scope — add an item (after S1's item 10)

```markdown
11. A **host protocol** between an executor and its host, the run operations,
    audit records, and conformance for executors
```

### 2.2 §1.1 Normative References — add

```markdown
- RFC 5545, Internet Calendaring and Scheduling (iCalendar), §3.3.5: local
  times that a clock change repeats or skips (§5.10.2)
```

### 2.3 §2 Terms — add rows (after S1's rows)

```markdown
| **Executor** | What runs a workflow step by step, with no input or output of its own (§5.19) |
| **Host** | What performs the actions an executor asks for and gives it the time (§5.19) |
| **Run** | One execution of a workflow, from its start to its terminal action (§5.19) |
| **Action** | What a run asks its host to do next, or how it ended (§5.19.1) |
| **Audit record** | An action record or a canonical event that says what happened (§6.4) |
```

### 2.4 §4.3 — replace the paragraph "A step *runs before* another …"

```markdown
A step *runs before* another when it comes earlier in the step list **and
is not in the same `parallel_group`**: the steps of one group are not
ordered relative to each other (§5.2.3), so neither is known to complete
before the other starts.
```

### 2.5 §5.2 Step Definition — replace three table rows

```markdown
| `parallel_group` | string | Group ID: the steps of one group are not ordered relative to each other (§5.2.3) |
| `join` | string | When the group is complete: `all_complete` (the default and the one value defined, §5.2.3) |
| `retry` | object | `{max, backoff}`: up to `max` further attempts after R401, R402 or R406 (not after an R402 the executor raises itself before asking the host, such as an `invoke` input the target refuses or a `delegate` target it refuses (§5.15.2): another attempt would be refused the same way; nor after an accepted delegation whose host did not attest the `read_only` the step relied on (§5.15.2): another attempt would hand the delegate's host another unchecked delegation); `max` an integer from 0 to 1000 and `backoff` one of `none` (also when absent or null), `linear`, `exponential` (else S303). After attempt *n* fails, the next attempt starts once the run's clock (§5.19.3) has passed the time it failed by: nothing for `none`; *n* × 1000 ms for `linear`; 2^min(*n*−1, 32) × 1000 ms for `exponential`; the wait ends no later than the maximum time |
```

(The `retry` row keeps 1.1's text, takes S3's extension of the "not after"
parenthesis (RECONCILIATION C6) and adds the last sentence, the reference
executor's schedule, which only the guide stated: a clarification, Appendix
D. F505 and F504 are not retried because they are not R401, R402 or R406.)

### 2.6 §5.2.3 Parallel Groups *(new, after S1's §5.2.2)*

```markdown
#### 5.2.3 Parallel Groups

The steps that declare one `parallel_group` form a group. Their order in the
step list does not order them: no member runs before another (§4.3), and an
executor MAY run them one at a time, in any order, or concurrently. An
executor that speaks the host protocol (§5.19) has one action pending at a
time, so it runs the members one after another, in list order.

A group is complete when every member has finished: completed, been skipped
or been deferred (§5.14). A step after the group runs only once it is
complete. Each member's failure is handled by its own failure modes (§5.12).
When a failure's recovery escalates or ends the run, the members that have
not finished are abandoned: a member that has not started does not run, the
result of one that has is discarded, and an action pending for one is
withdrawn. When it loops, the current pass is abandoned and execution
continues from the loop's target (§5.12): the members at or after the
target run again, and an action pending for one is withdrawn.

`join` says when the group is complete. This version defines one value,
`all_complete`, the default: when every member has finished. A `join` with
another value, or on a step that declares no `parallel_group`, is W618
(`UNKNOWN_JOIN`) and is ignored: the group joins as `all_complete`.

A member whose executable fields read a group mate's store (a reference
whose root is the `store_as` of another member) is W619 (`GROUP_MATE_READ`):
that value exists only when the executor has run the mate first, which this
section does not promise. An executor that runs the group in list order
resolves a reference to an earlier mate.
```

### 2.7 §5.6 Gate Semantics — in the `end` bullet, replace the last sentence

Replace "A step in a `parallel_group` cannot have an `end` gate (S303): its
group mates run at the same time and would be left half done." with:

```markdown
A step in a `parallel_group` cannot have an `end` gate (S303): its group
mates may run at the same time (§5.2.3) and would be left half done.
```

### 2.8 §5.10 Triggers — replace the `attendance` table row, append a sentence

```markdown
| `attendance` | `attended` or `unattended`: the attendance of the runs the trigger starts (§5.10.2). Default: `manual` → attended, `invoke` → the invoker's, `schedule`/`event` → unattended |
```

After the paragraph that ends "Unknown trigger fields are W604.", add:

```markdown
Who evaluates triggers, and when a schedule fires, is §5.10.2.
```

### 2.9 §5.10.2 Evaluating Triggers *(new, after §5.10.1)*

```markdown
#### 5.10.2 Evaluating Triggers

The host evaluates triggers (§5.19); the executor neither reads nor
evaluates them. A host that starts runs of a workflow from its triggers
MUST:

- start each run with the trigger's attendance: its `attendance`, else the
  default of its kind (§5.10). A run that an `invoke` step starts has its
  invoker's attendance; the executor applies that itself;
- for an `event` trigger, start one run for each event it accepts, with the
  event (a canonical event, §6.2) as the input that `delivers_to` names,
  and at most one run per `event_id` for the trigger: an event delivered
  again starts no other run. The host accepts an event whose `event_type`
  equals the trigger's, whose `source.kind` equals the trigger's
  `source_kind` when it names one, and whose sender its sender policy
  admits: where the workflow declares `identity@1`, a sender it has
  authenticated as §5.17 says;
- for a `schedule` trigger, start runs at its fire times as its `overlap`
  allows (below).

A host MAY drop an event its sender policy does not admit, and SHOULD keep
an audit record of the drop (§6.4). A host MAY also start a run by other
means, such as a test or an operator's request; it then gives the run's
attendance itself.

**Fire times.** A `cron` schedule fires at each local time of its
`timezone` whose minute, hour, day of month, month and day of week match
(§5.10), at second 0. A local time maps to an instant as RFC 5545 §3.3.5
says: a local time that occurs twice, because clocks were set back, is its
first occurrence; one that does not occur, because clocks were set forward,
is read with the UTC offset in effect before the change. Local times that map
to the same instant fire once. An `every` schedule fires at each instant,
counted in whole milliseconds from 1970-01-01T00:00:00Z, that is a multiple
of its interval, the interval rounded up to a whole millisecond; its
`timezone` does not change its fire times.

**Overlap.** A run that a trigger started is *in progress* from its start
until it ends (a run that ended `deferred` and is resumed, §5.14.1, is in
progress again until it ends again). At a fire time when a run this trigger
started is in progress:

- `skip` (default): no run starts for that fire time;
- `buffer_one`: a run starts as soon as no run this trigger started is in
  progress; a fire time while one run is already waiting adds no other;
- `allow_all`: a run starts at the fire time, beside those in progress.

When no run this trigger started is in progress, a fire time starts a run.
Fire times that pass while the host is not evaluating the trigger (it was
stopped) count, together, as one fire time at the moment it resumes.

The trigger vectors of §10.3 fix fire times, attendance, event acceptance
and overlap decisions for representative cases, clock changes, resumed runs
and redelivered events included.
```

### 2.10 §5.13 Waiting for Events — two edits

In the `liveness` table row, replace "`probe`: the runtime polls it" with:

```markdown
`probe`: the host polls it (§5.19.3)
```

After the paragraph that ends "… since the wait had already lapsed." (before
"To re-check a silent source"), insert:

```markdown
The host watches liveness and reports a loss (§5.19.3); a result or event
that arrives at the deadline is in time, one after it is late.
```

### 2.11 §5.19 Host Protocol *(new, after §5.18)*

```markdown
### 5.19 Host Protocol

An **executor** runs a workflow and does no input or output of its own; a
**host** performs what the run needs from the world. The executor says what
it needs next (an **action**), the host performs it and answers (a
**response**), and time enters only through the times the host gives. The
same catalog, inputs, responses and times give the same actions.
`schemas/host_protocol.schema.json` defines every action and response; an
executor of class EX (§10.5) issues exactly those actions, and takes every
response the schema allows as §5.19.1 says.

#### 5.19.1 Actions and Responses

A run has, at any time, one **pending** action, or it has **ended** with a
terminal action (`Completed` or `Failed`). Every action carries:

- `run_id`: the run's identifier (§5.19.2);
- `id`: an integer. A run's first action has id 1 and each later action,
  the terminal one included, the next integer; a restored run issues its
  pending action again with the same `id` (§5.19.4);
- `frame`: the workflows of the nested runs (§5.12), root first;
- `kind`, and the members of its kind:

| Action | The host | Responses |
|--------|----------|-----------|
| `InvokeCapability` | performs `capability` with `inputs` for `step`, for the step's `domain` (null when it declares none, §5.2), by `deadline` when it is not null; `attempt` counts attempts from 1 (§5.2), and `replaces` names a delegation this one replaces (§5.13) | `Output` (`value`: the capability's output, an object with the fields its contract requires, else the step fails R402), `Error` |
| `CreateCheckpoint` | takes a checkpoint before `step` | `Checkpoint` (`checkpoint_id`), `Error` (the step fails F501) |
| `Rollback` | restores `checkpoint_id` | `RolledBack`, `Error` (the run ends F503) |
| `RequestApproval` | asks `approver`, in `mode`, about `shown`, by `expires_at` when it is not null (§5.14) | `Decision` (`decision_id`, `decision`, `approvers`, `digest`) |
| `RecheckSource` | reads `source` again, to compare by `compare` (§5.14) | `Current` (`value`), `Error` (the step fails F502) |
| `AwaitEvent` | waits for an event that matches `event_type`, `source_kind`, `correlate` and the sender checks (§5.13, §5.15, §5.17), by `deadline`, and watches `liveness` | `Event` (`event`, optional `principal` and `identity`), `LivenessLost` (R406), `Error` |
| `Sleep` | lets time pass until `until` (a retry's backoff, §5.2; a delay, §5.13) | none: the host gives the run the time (§5.19.3) |
| `Completed` | none: the run ended with `outcome` (`completed`, `escalated`, `deferred` or `replan_required`), `cause`, `ended` (§5.6), `outputs`, `action_records` and `deferred` (§5.14) | none |
| `Failed` | none: the run ended with `code` (§9) at `step`, with `message`, `action_records` and `deferred`, and `reason` (§5.19.7) and `checkpoint_id` (§5.19.5) where they apply | none |

The executor computes these members:

- `inputs`: the step's `input_bindings` with every reference resolved
  (§5.3, §5.4).
- `attempt`: 1 for the first attempt of a pass of the step, one more for
  each retry (§5.2); a recovery loop starts a new pass (§5.12).
- `deadline`: when the step declares a `timeout`, the run's clock when the
  attempt's action was issued plus the timeout; for the wait of a waiting
  `delegate`, the deadline of its delegation (one timeout bounds both,
  §5.13); else null.
- `expires_at`: the run's clock when the approval was requested plus the
  approval's `expires` (§5.14); else null.
- `Sleep.until`: for a retry, the run's clock when the attempt failed plus
  the backoff of §5.2; for a delay, the run's clock when the step reached it
  plus `delay` (§5.13).
- `correlate`: the step's `correlate`, and, for a waiting `delegate`, the
  `task_id` its delegation returned (§5.13); `accept_from`, `sender_check`
  and `accept_trust_classes`: the step's bound inputs of those names, or
  null (§5.15, §5.17); `RecheckSource.source`: the `recheck.source`
  reference as written (§5.14); `shown` and `digest`: as §5.14 says.
- Every time is at most the maximum time (§5.19.3).

The terminal action's members:

- `outputs`: the root workflow's stores at the end: for each of its steps
  whose output is current (it completed, and no skip, deferral or recovery
  loop has since cleared it, §5.12, §5.14), that output under the step's
  `store_as`.
- `cause`: for `escalated`, and for `deferred` that kept an escalation, the
  code that caused the escalation, or R404 (§5.11); else null.
- `action_records`: the run's action records (§6.4), in the order first
  written, less any the host has taken from the run's state (§5.19.4).
- `deferred`: the deferred steps (§5.14), in the order deferred.

A step's output is the `value` of the host's `Output`, except for the steps
the executor runs itself, whose outputs it composes:

| Step | Output |
|------|--------|
| a wait on `receive` (§5.13) | `data`: a one-item list, the event with `sender` and `sender_identity` added when the host gave them (§5.17); `source`: the event's `source.kind`, and `timestamp`: its `timestamp` (each null when the event lacks it); `evidence_anchors`: the event's `anchors` (`[]` when the event has no such member) |
| a wait on `synchronize` | `synchronized: true`; `agreed_state`: the event's `canonical` (`{}` when absent); `participants`: the step's `agents`; `evidence_anchors` as above; `sender` and `sender_identity` when given |
| a waiting `delegate` | the delegation's `Output`, with the matching event (as in `data` above) as `result` |
| an `invoke` of a catalog workflow (§5.12) | `result`: the nested run's stores, as `outputs` above; `steps_executed`: the `store_as` names of its steps whose output is current, in step order; `evidence_anchors: []` |
| a quorum (§5.16) | `compliant`; `tally`; `violations`: in verdict order, `{reviewer_id, ignored}` for each verdict not counted, `{reviewer_id, note}` for a counted verdict whose `scope` is neither `full` nor `delta`, then `{quorum}` for each requirement not met, where `ignored`, `note` and `quorum` are text; `evidence_anchors: []`. `tally.voters` lists the counted reviewers sorted |

A response answers the pending action, named by its `id`. A response for
another action, of a kind the pending action does not take, or holding a
value that is not I-JSON (§5.14) is refused, and the run is unchanged. A run
that has ended takes no response. A response member this protocol does not
define is ignored, as in 1.1: a host may send members a later version
defines. Likewise, a host MUST ignore an action member it does not know:
later versions may add members to actions.

An `Error` carries a `code` and a `message`, and may carry a `reason`
(§5.19.7). To `InvokeCapability`, an `Error` with code R401 keeps it and any
other code is R402; to `AwaitEvent`, R401 and R406 keep theirs and any other
is R402.

The action records an executor writes (§6.4) have the `action_id`
`<run_id>/<frame>/<step>/<n>`, where `<frame>` is the frame's workflows
joined with `/` and `<n>` is the number of records the run wrote before
this one, taken ones included.

#### 5.19.2 Run Operations

An executor offers these operations on a run; each binding names them in
its own way, and its conformance statement says how (§10.5):

- **start**: with a catalog that validates (§10.5) and, for a catalog
  set, its other catalogs (§5.1.1); for each catalog, the version its
  header declares or none (§11.5: always given, and a host that loaded the
  catalog from a file passes the version of the file's header); the
  workflow, its inputs, the run's attendance (§5.10.2), its `run_id`, the
  time and, optionally, its actor (§5.17), its record mode (§6.4), the
  agent manifests it gives (§5.15.1), its destination policies (§4.4.2),
  the grounding policies it applies to the run and its nested runs (§5.20)
  and the domain profiles it applies (§5.21). The executor refuses to start
  a run whose destination policies hold an invalid pattern (§4.4.2), whose
  grounding policies name a capability the ontology lacks (V101, §5.20), or
  whose profiles have an error (§5.21.2). The run then has its first
  action. (Merged text of S2b, S3, S4, S5 and S6; RECONCILIATION C3.)
- **next**: the pending action, or the terminal one. It changes nothing.
- **submit**: a response to the pending action, with the time.
- **tick**: the time, with no response (§5.19.3). It says whether it changed
  the run.
- **wake at**: the earliest time at which a tick changes the run, or none
  (§5.19.3). It changes nothing.
- **cancel**: ends the run, with a reason and the time (§5.19.5).
- **save** and **restore**: the run's state as a value the host keeps, and
  a run continued from such a value (§5.19.4).
- **resume**: continues a run that ended `deferred` (§5.14.1).

An executor MAY also offer **take** (the settled records and the trace,
§5.19.4) and **run record** (§5.19.8).

The `run_id` is the host's choice. It MUST differ from the `run_id` of every
other run whose action records, run record (§5.19.8), delivery keys
(§5.19.4) or idempotency keys (§4.4.2) the host keeps: they are keyed by it, and two runs under one
`run_id` would share keys, so a host would give one run a response it kept
for the other. A run continued from a saved state, restored or resumed,
keeps its `run_id`.

#### 5.19.3 Time

Times are integers of milliseconds since 1970-01-01T00:00:00Z. A run's clock
is the latest time the host has given it; an earlier time leaves the clock
where it is, and a time after 253402300799999 (the last millisecond of the
year 9999) counts as that time.

- A `Sleep` ends at a tick whose time is at or after its `until` (when it
  falls is §5.19.1).
- An action with a `deadline` (`InvokeCapability`, `AwaitEvent`) or an
  `expires_at` (`RequestApproval`) times out at a tick whose time is after
  it. An answer submitted at the deadline is in time; one submitted after it
  is late: a late output or event is R401, a late decision has lapsed
  (F502).
- So the **wake-up time** of a run is `until` for a pending `Sleep`, the
  `deadline` or `expires_at` plus one millisecond for an action that has
  one, and none for any other pending action or an ended run.
- The executor has no clock of its own: it acts only when the host submits,
  ticks, cancels or resumes. A host that waits on a run sets its own timer
  for the wake-up time and ticks when it fires.
- A time-out is not announced: the next action shows what followed (a
  retry, a failure mode, the end). A host still performing the action
  SHOULD stop, since a response to it is now refused.
- Liveness (§5.13) is the host's to watch: the executor does not schedule
  heartbeats or probes. The host answers `LivenessLost` once the source has
  missed `failure_threshold` heartbeats or probes, `interval` apart.

#### 5.19.4 Saving and Continuing a Run

A run's **state** is all an executor needs to continue it. A host that keeps
a run across turns, processes or machines saves the state and restores it
later. Such a host:

1. **One writer.** MUST let only one party at a time submit to, tick,
   cancel or resume a run, and only from the latest state: it serialises the
   operations on one run, and MUST NOT continue two copies of one saved state
   (each would perform the same pending action, and resuming a deferred run
   twice could carry out a queued action twice, §5.14.1).
2. **Save before acting.** MUST save the state after each operation that
   changed it (start, submit, a tick that changed it, cancel, resume) and
   before it performs the action that operation left pending; a host that
   cannot save MUST NOT perform the action.
3. **At least once.** A restored run's pending action is the one pending
   when the state was saved, with the same `run_id` and `id`, though the host
   may already have performed it (it acted, then stopped before it could
   submit or save). The host MUST make what it does for an action idempotent
   under its **delivery key** (`run_id`, `id`): it keeps the response it gave
   for each delivery key it acted on and, given the key again, submits that
   response instead of acting again. Where an effect cannot be made
   idempotent, the host SHOULD record the key with the effect, so a repeat
   can be found. (A delivery key names one action; the idempotency key of
   §4.4.2 names a pass, every attempt of a step, and keeps a retry from
   repeating an effect.)
4. **Interrupted turns.** When the host's own execution stops between
   performing an action and submitting the response (its process ends, a
   client stops it), the run is unchanged: on its next turn the host
   restores the latest state and goes on as item 3 says. To end the run
   instead, it cancels it (§5.19.5).

Every host, whether or not it saves states, keeps each run's record
(§5.19.8).

**Integrity.** An executor MUST detect, when it restores a state, that the
state was corrupted (the reference executor saves a SHA-256 digest with it),
and, when the host gives a key, MUST refuse a state whose MAC under that key
does not verify (the reference executor: HMAC-SHA-256). A digest alone does
not show who wrote a state: whoever can change the state can recompute it.
So a host that keeps states where any party other than the run's writer can
change them MUST have the executor use a key, and MUST keep the key from
those parties. An executor SHOULD also refuse a state it could not have
produced (the reference executor checks the state's consistency). Saving
and restoring changes nothing: a restored run issues the same actions, and
reaches the same end, as the run it was saved from (§10.5).

**Taking records out.** An executor MAY let the host take settled action
records, and its trace, out of a run's state, so the state stays small; the
host then keeps what it takes (records as audit records, §6.4). An executor
that does MUST keep in the state a commitment to everything taken, in
order, so that a state that verifies also vouches for what was taken: the
reference executor keeps, for records and for trace events, a chain head
`h`, starting from the empty string and replaced, for each item taken, by
the lowercase hexadecimal SHA-256 of `h` followed by the item's canonical
JSON (RFC 8785).

#### 5.19.5 Cancelling a Run

A host MAY **cancel** a run that has not ended, or one that ended
`deferred`, with a reason. Cancelling:

- ends the run at once with a `Failed` action of code R408 (`CANCELLED`):
  its `message` is the reason, its `step` the step the run was at (null for
  a run that had ended), and its `checkpoint_id` the latest checkpoint the
  run knows of, if it knows of one;
- runs no retry, failure mode, recovery loop, handler or rollback: they
  answer failures of steps, and a host that stops a run may no longer be
  able to perform them. The executor does not roll back; a host that wants
  the run's effects undone restores `checkpoint_id` itself;
- withdraws the pending action: a response to it is refused. A host
  performing it SHOULD stop;
- sets each of the run's action records that is `approved` or `planned` to
  `cancelled`, with code R408 and the reason: an approved action may or may
  not have been carried out, and a queued one will not be;
- in record mode `actions` (§6.4), writes a `cancelled` record, with code
  R408 and the reason, for each step, in any of the run's nested runs, that
  has started its current pass and has no record of it. A step has
  **started** its pass once the executor has issued, in that pass, a
  `CreateCheckpoint`, `InvokeCapability` or `AwaitEvent` for it, or, for an
  `invoke`, started its nested run; so a step waiting out a retry's backoff
  and a waiting `delegate` whose delegation was sent have started, and one
  waiting for its approval, its recheck or its delay has not. A pending
  `CreateCheckpoint` of a failure mode, or a pending `Rollback`, also gets
  its own `cancelled` record (capability `checkpoint` or `rollback`), as it
  would have had one had it completed;
- ends the nested runs with it. A cancelled run cannot be resumed.

A run that ended any other way cannot be cancelled. Nothing else ends a run
early: an `Error` that a host gives to stop a run is a failure of the step,
and the step's retries, failure modes and recovery apply.

#### 5.19.6 Protocol Traffic

What a host transmits to perform an action that is not `InvokeCapability`
(to the approvers for `RequestApproval`, to the source for `RecheckSource`
and `AwaitEvent`, liveness probes included, and to whoever started the run
for a terminal action) is **protocol traffic**, not a step. The safety flags
of `send` (§4.4) do not apply to it, and it needs no checkpoint or approval,
provided it carries only values the action holds: for `RequestApproval`, its
approver, mode, shown values, digest and expiry; for a terminal action, its
members. A host MUST NOT add other values of the run (stores, inputs,
outputs) to it. Anything else a workflow means to transmit is a step: a
`send`, or an `inquire` for a question to a person. A tool-calling host that
delivers protocol traffic through a tool treats that tool as a host action
(§5.18.3), not as a call of `send`.

#### 5.19.7 Error Reasons

An `Error` response MAY carry a `reason`, a token that says why without a
reader having to parse the message. The code still decides what the run
does (§5.19.1). This version defines:

| Reason | Meaning |
|--------|---------|
| `unsupported_capability` | The host does not perform the capability |
| `unsupported_domain` | The host performs the capability, but not for the step's `domain` (§5.2.4) |
| `not_recorded` | A record that was required was not written (§6.4) |
| `outcome_unknown` | An earlier attempt under the same idempotency key may have taken effect, and the host cannot tell; it did not act again (§4.4.2) |
| `key_conflict` | The idempotency key was first used with another capability or other inputs, so a `run_id` was reused; the host did not act (§4.4.2) |
| `destination_not_allowed` | The destination is not one the destination policies in force allow (§4.4.2) |
| `unsupported_scope` | The host does not provide the memory scope asked for, or did not use it (§4.5) |
| `unsupported_ttl` | The host cannot parse the `ttl`, or cannot end entries (§4.5) |
| `over_capacity` | The host refused to store for size or capacity; the message names the limit (§4.5) |
| `secret_in_data` | The data or key a `persist` would store holds a secret the host recognises; nothing was stored (§4.5, §6.7) |
| `below_minimum_confidence` | The output's `confidence` is below the minimum an applied domain profile sets (§5.21.3) |
| `invalid_confidence` | A minimum confidence applies and the output's `confidence` is not a number from 0 to 1 (§5.21.3) |

(Rows merged from S2b, S5 and S6; RECONCILIATION C5.)

A host MAY also send a vendor reason: `x-`, then a lowercase letter or a
digit, then at most 61 lowercase letters, digits, `_`, `.` or `-`. A
`reason` that is neither (another string, or a value that is not a string)
is ignored: the `Error` is taken as if it carried no `reason`, as 1.1 took
any member it did not define, and the executor MAY note the ignored value
in its trace. A step that fails with a reason keeps it: the run's `Failed`
action carries it as `reason` when the run ends with that failure, and the
step's action record as `reason_code` (§6.4). The executor raises
`not_recorded` itself for an `audit` step (§6.4),
`destination_not_allowed` with F504 for a `send` step (§4.4.2),
`unsupported_scope` with R402 for a `persist` or `recall` step whose output
does not echo its scope (§4.5), and `below_minimum_confidence` and
`invalid_confidence` with F504 for an output an applied profile's minimum
confidence covers (§5.21.3).

#### 5.19.8 The Run's Record

Every run has a **run record**: an action record (§6.4) derived from its
terminal action, so that a run that failed or was cancelled before any step
wrote a record still leaves one. Its members are:

| Member | Value |
|--------|-------|
| `action_id`, `run_id` | the run's `run_id` |
| `frame` | the terminal action's `frame` |
| `step` | for `Failed`, its `step` when not null; absent otherwise |
| `timestamp` | the run's clock (§5.19.3) when it ended, as an RFC 3339 UTC time with milliseconds |
| `actor`, `actor_identity` | the run's actor when it ended (§5.17, §5.14.1): `actor` is its `kind`; without one, `actor` is `agent` and `actor_identity` is absent |
| `intent` | `run ` followed by the root workflow's name |
| `status` | `executed` for `Completed`, except `planned` when its outcome is `deferred` (the run can still be resumed or cancelled); `cancelled` for `Failed` with code R408; `failed` for any other `Failed` |
| `code`, `reason_code`, `checkpoint_id` | the `Failed` action's `code`, `reason` and `checkpoint_id`, when it has them |
| `details` | `kind`; `outcome`, `cause` and `ended` (for `Completed`); `message` (for `Failed`); `deferred`; and `records`, the number of action records the run wrote, taken ones included |

Every host that runs workflows MUST keep, when a run ends, its run record
and the run's action records (those in the terminal action and those it
took, §5.19.4) where it keeps its audit records, before it discards the
run's state. A run that ended `deferred` and is resumed (§5.14.1) or
cancelled (§5.19.5) ends again; the host then replaces its run record, which
keeps its `action_id`. An executor MAY derive the run record for the host.
```

### 2.12 §6.1 Required Schema Files — replace the paragraph after the table

```markdown
Supporting schemas that specific sections use, not required of every
implementation: `review_verdict_schema.yaml` (§5.16),
`agent_identity_schema.yaml` (§5.17) and `host_protocol.schema.json`
(§5.19, required for class EX, §10.5).
```

(S1 adds `interop/tool_binding.schema.json` to the same sentence.)

### 2.13 §6.3 World State Requirements — append to S2a's replacement paragraph

```markdown
An action record is also an audit record (§6.4).
```

### 2.14 §6.4 Audit Records *(new)*

```markdown
### 6.4 Audit Records

An **audit record** says what happened. It is one of:

- an **action record** (`world_state_schema.yaml#/types/ActionRecord`): an
  action an agent took, was refused, or deferred, whether a step of a run or
  a call on a tool-calling host (§5.18); or
- a **canonical event** (`event_schema.yaml#/event`, §6.2): something
  observed.

An implementation that writes audit records (an executor's action records,
a safety layer's records of calls, §5.18.8, the record an `audit` step
writes, a run record, §5.19.8, a host's log of what it did) writes them in,
or exports them as, one of these shapes: it may keep its own form
internally, provided it can give each record in one of these shapes. An
executor's trace of its own decisions is not an audit record; its form is
the executor's own.

**An executor's records.** An executor writes an action record for each step
that requires approval (§5.14). Started in record mode `actions`, it also
writes one for each pass of each step that runs, whatever its flags (a
retry is the same pass; a recovery loop that runs the step again starts
another): `executed` when the step has its output, `failed` when it fails
after it started, or when the checkpoint it needs cannot be taken (F501),
and `cancelled` when the run is cancelled after the step started (§5.19.5);
and one for each checkpoint a failure mode takes (`pause_and_checkpoint`,
`capability: checkpoint`) and each `Rollback` it asks for (`capability:
rollback`), `executed`, `failed` (F501, F503) or `cancelled`. The default
mode, `approvals`, writes only the first kind. An executor MUST offer both
modes. Each record an executor writes carries `run_id`, `frame`, `step` and
`capability`; as `intent`, the step's `purpose`; as `timestamp`, the run's
clock when the record was first written; `checkpoint_id`, when the action
used, took or restored a checkpoint; `code` (§9) and, where the failure had
one, `reason_code` (§5.19.7), when the action failed or was refused or
cancelled; and, in its `approval`, the `decision_id` of the decision.

**The `audit` capability.** An `audit` step records its `event`. The
implementation performing the step writes an action record of its own:
`capability: audit`, status `executed`, `intent` the event's `intent` or
`event_type` when it is a string, else `audit`, and the event, whatever its
shape, as `details.event` (with the step's `context` and `retention`, when
bound, as `details.context` and `details.retention`). When it performs the
step for a run it SHOULD set `run_id`, `frame` and `step` from the action.
It MUST set `recorded_by` to itself, replacing any value the event offers,
and MUST compute any chain fields (below) itself; no member of the event
becomes a member of the record. So an event that has the shape of an action
record or a canonical event is kept as given, but under `details.event`: it
is what the step reported, not a record the implementation vouches for, and
it cannot claim another writer, an actor, an approval or a place in a
chain. The step's output `record` is the record written, and `recorded`
says whether it was written. A step that binds `require_record: true` fails
with R402, reason `not_recorded`, unless its output's `recorded` is `true`.
Without it the step completes when the record was not written, and a later
gate or failure mode may read `recorded`.

**Required and best-effort capture.** The records this Standard requires are
required: an executor keeps its records in the run's state (§5.19.4), a host
keeps each run's record (§5.19.8), and a safety layer that cannot write the
record of a call refuses the call (§5.18.8). Any other capture a host makes,
such as evidence anchors taken from tool results or a log of tool calls, is
best-effort unless the host states that it is required. A host that
requires a capture and cannot make it reports the failure where the
action's result goes: for a step, R402 with reason `not_recorded`; for a
call that has already run, in what the caller is told of the call. A
best-effort capture that fails MUST still be reported where the host's
operator sees it, such as an error the host shows: it may miss a record,
but never silently.

**Who wrote it.** A record MAY name the implementation that wrote it and the
configuration it applied: `recorded_by`, with `name`, `version` and
`config_sha256`. An implementation sets `recorded_by` only to itself.

**Integrity.** A store that keeps audit records as an append-only log SHOULD
chain them: each record carries `prev_hmac`, the `hmac` of the record before
it (the empty string for the first), and `hmac`, the HMAC-SHA-256 under the
store's key of the record without `hmac`, as 64 lowercase hexadecimal
digits. The store computes both when it appends the record, whatever the
record offered. The store documents how it serialises the record for the
MAC.
```

### 2.15 §8.4 Manual Overrides *(new, after §8.3)*

```markdown
### 8.4 Manual Overrides

A **manual override** replaces, by a person's or an agent's decision, what
§8.1–§8.3 computed: a trust score, or which value won a conflict.
`authority_trust_model.yaml` `overrides` governs it:

- `allow_manual_override`: when false, an implementation refuses every
  override;
- `requires_anchors`: when true, an override MUST cite at least one evidence
  anchor for the value it sets, and one that cites none is refused;
- `audit_required`: when true, an override MUST be recorded as an audit
  record (§6.4) before it takes effect: an action record whose `intent`
  names the override, whose `actor_identity` (or `actor`) is who made it,
  whose `details` hold what was overridden, the value it had and the value
  set, and whose `anchors` are the anchors cited. An override whose record
  cannot be written does not take effect.
```

### 2.16 §9 Diagnostic Model — table edits

§9.5 Runtime Errors (replace R402's description, add one row):

```markdown
| R402 | EXECUTION_FAILED | Step execution failed; an `Error` may say why (`reason`, §5.19.7) |
| R408 | CANCELLED | The host cancelled the run (§5.19.5); no retry, failure mode, recovery or handler ran |
```

§9.7 Warnings (add two rows):

```markdown
| W618 | UNKNOWN_JOIN | A `join` other than `all_complete`, or a `join` on a step with no `parallel_group`; it is ignored (§5.2.3) |
| W619 | GROUP_MATE_READ | A step reads the store of a step in its own `parallel_group`, which need not have run yet (§5.2.3) |
```

§9.8 — no sentence: W619's `ref` and `mate` are rows of S3's merged
location table (RECONCILIATION C30).

### 2.17 §10 Conformance

§10.1 — add a row to the table, and a sentence after it (beside S1's
sentence about SL):

```markdown
| **EX** | An executor: runs validated workflows by the host protocol, records as §6.4 says, and passes the runtime fixtures (§10.5) |

Levels L1–L4 rank validators; SL (§10.4) and EX (§10.5) are separate
classes: a layer validates no catalog, a validator checks no call and runs
no workflow, and an implementation claims each level or class it meets.
(Merged with S1's SL sentence; RECONCILIATION C7.)
```

§10.3 — replace the last sentence of the paragraph ("Runtime fixtures
(`tests/conformance/runtime/*.json`) script runs … informative for
implementations that execute workflows.") with:

```markdown
Runtime fixtures (`tests/conformance/runtime/*.json`) script runs: the
actions an executor must issue, the responses it gets, the ticks,
cancellations and resumptions it is given, and the end it must reach, for
the runtime semantics of §4.4–§4.5, §5.2, §5.6–§5.21 and §6.4. They are normative for class
EX (§10.5), except their `trace_kinds`, which name kinds of the reference
executor's trace and are informative. The trigger vectors
(`tests/conformance/triggers/`) are normative for §5.10.2: an implementation
that computes fire times, a trigger's attendance, which events start runs,
or overlap decisions MUST give each vector's result. The fire-time vectors
depend on the time zone database: each file names the tzdata release it was
computed with, and the vectors are normative with that release, or with any
release that agrees with it on the vectors' dates.
```

New §10.5:

```markdown
### 10.5 Executor Conformance

An executor conforms to class EX when it:

- starts a run only when the catalog has no error under a validator that
  conforms at L3 or above (its own or another), and refuses to start it
  otherwise;
- implements each extension a workflow it starts declares (§5.9), and
  refuses a workflow that declares one it does not implement;
- offers the run operations of §5.19.2 and issues exactly the actions of
  `schemas/host_protocol.schema.json`;
- takes every response that schema allows as §5.19.1 says: it refuses the
  responses §5.19.1 refuses, and ignores the members the protocol does not
  define and a `reason` outside §5.19.7;
- keeps time, saves and restores, and cancels as §5.19.3–§5.19.5 say, and
  writes action records as §6.4 says, in both record modes;
- passes every runtime fixture whose declared extensions it implements.

**Runtime fixtures.** A fixture
(`tests/conformance/runtime/schema/fixture.schema.json`) holds a `catalog`,
the version of its header or null (`header`), the `workflow` to run, its
`inputs`, its `attendance`, optionally its `actor_identity`, `records` (the
record mode, default `approvals`), further catalogs of its set with their
headers (`catalogs`), agent manifests (`agents`), destination policies
(`destinations`), grounding policies (`grounding`) and domain profiles
(`profiles`), which the run is started with (§5.19.2), the `start` time, a
`script`, the `end` and, optionally, the `run_record`. The
run starts with `run_id` `"run-1"`. Each script entry is one of:

- `{"expect": A, "respond": R, "at": T}`: the pending action matches `A`;
  then `R`, when given, is submitted for it at time `T` (default: the
  latest time used). In `R`, the string `"{{digest}}"` stands for the
  pending action's `digest`, and `"{{digest_upper}}"` for the same in
  uppercase;
- `{"tick": T, "changed": C}`: the time `T` is given with no response; when
  `changed` is given, the tick changed the run exactly when `C` is true;
- `{"wake_at": W}`: the run's wake-up time is `W` (null: none);
- `{"cancel": {"reason": S, "at": T}}`: the run is cancelled;
- `{"resume": {"attendance": …, "at": T, "actor_identity": …}}`: the run is
  resumed (§5.14.1).

After the script, the run's next action matches `end`, and, when the
fixture gives a `run_record`, the run record derived from that end
(§5.19.8, with the run's clock and actor) matches it. An actual value
**matches** an expected one when they are equal; when both are objects and
the actual one has every member the expected one names, each matching; or
when both are arrays of the same length whose elements match in order. Text
the executor composes is not compared: a `message` member (except
`ended.message`, a gate's message, §5.6, which the workflow wrote), the
`reason` member of an action record or of a deferral, and the `ignored`,
`note` and `quorum` members of an item of a quorum's `violations`
(§5.19.1). (`reason` on a `Failed` action is a token, §5.19.7, and is
compared.) An executor passes a fixture when every expectation matches,
both when it runs the script as it is and when its state is saved and
restored before every entry. `description` and `trace_kinds` are not part
of the test. Every other member a fixture pins is one this Standard
defines (§4.4.1, §4.4.2, §4.5, §5.2, §5.6, §5.11–§5.17, §5.19.1, §5.20,
§5.21, §6.4).

**Conformance statement.** An executor that claims class EX names its
version, the Standard version it implements, the extensions it implements,
how its binding names the operations of §5.19.2, and whether it restores
states saved by its earlier versions.
```

### 2.18 Appendix D (Changes from 1.1.0) — entries for the foundation

Under **Clarifications of 1.1 semantics**:

```markdown
| Parallel groups at run time | "steps of one group run concurrently" | Members are not ordered; an executor may run them in any order or concurrently, and a §5.19 executor runs them in list order; a group is complete when every member has finished; unfinished members are abandoned when a recovery escalates or ends the run, and a loop continues from its target (§5.2.3) |
| `join` | Free string | One defined value, `all_complete`; any other is W618 and ignored (§5.2.3) |
| Tick boundaries | Not stated | A `Sleep` ends at `until`; an action times out after its deadline, and an answer at the deadline is in time (§5.19.3) |
| Liveness probes | "the runtime polls it" | The host polls and reports `LivenessLost` (§5.13, §5.19.3) |
| Protocol traffic | Not stated | Not a `send` step, when it carries only the action's values (§5.19.6) |
| Retry backoff | `none`, `linear`, `exponential` named, schedule not stated | `linear` waits attempt × 1 s, `exponential` 2^(attempt−1) s (exponent at most 32), from the failure (§5.2), as the reference executor did |
| Executor-computed members | Not stated | `deadline`, `expires_at`, `Sleep.until`, `correlate`, `Completed.outputs`, `cause`, and the outputs the executor composes for waits, `invoke` and quorums (§5.19.1), as the reference executor did |
| Unknown response members | Ignored by the reference executor, not stated | Ignored (§5.19.1); a host ignores unknown action members |
```

Under **New in 1.2.0**:

```markdown
- The host protocol (§5.19): actions, responses, run operations, time,
  saving and continuing a run (one writer, save before acting, at-least-once
  delivery keyed by `run_id` and `id`, a unique `run_id`, state integrity
  and a key where others can change stored states), cancellation (R408),
  protocol traffic, error reasons, and the run record every host keeps
  (§5.19.8); `schemas/host_protocol.schema.json`
- Trigger evaluation (§5.10.2): the host's duties, event acceptance and one
  run per `event_id`, fire times in the declared time zone (RFC 5545 for
  clock changes), the `every` anchor, the meaning of `overlap`, missed fire
  times
- Audit records (§6.4): action records and canonical events, written or
  exported; the executor's record mode `actions`; `audit` records its event
  in a record of its own; `require_record`; required and best-effort
  capture, and no silent capture failure
- Manual trust overrides (§8.4)
- Class EX (§10.5): the runtime fixtures are normative for executors; the
  trigger vectors are normative (§10.3)
- Codes R408, W618, W619
- `world_state_schema.yaml` 1.2.0: `ActionRecord` `run_id`, `frame`,
  `step`, `capability`, `tool`, `call_id`, `checkpoint_id`, `code`,
  `reason_code`, `details`, `recorded_by`, `prev_hmac`, `hmac`; status
  `cancelled`; `approval.decision_id`
- Ontology 2.2.0: `audit` input `require_record` and output `record`
```

---

## 3. Ontology, canonical and supporting schema deltas, new schema files

### 3.1 Ontology (`schemas/capability_ontology.yaml`, 2.1.0 → 2.2.0, one bump shared with every workstream)

Replace the `audit` node's `input_schema` and `output_schema` (the comment
and flags above them are unchanged):

```yaml
  input_schema:
    type: object
    required:
    - event
    properties:
      event:
        type: object
        description: What happened, as the step reports it. The implementation records it,
          whatever its shape, as details.event of an action record of its own (capability
          audit), whose recorded_by and chain fields it sets itself; no member of the
          event becomes a member of that record (Standard v1.2 §6.4).
      context:
        type: object
        description: Event context
      retention:
        type: string
        description: How long to retain
      require_record:
        type: boolean
        description: The record must be written. When true, the step fails (R402, reason
          not_recorded) unless the output's recorded is true (Standard v1.2 §6.4). Default
          false.
  output_schema:
    type: object
    required:
    - recorded
    - evidence_anchors
    properties:
      recorded:
        type: boolean
        description: Whether the record was written.
      audit_id:
        type: string
        description: Audit record ID
      record:
        type: object
        description: The action record written for the event (Standard v1.2 §6.4).
      timestamp:
        type: string
        format: date-time
      evidence_anchors:
        type: array
```

Every change is an optional property or a description (§11.4: compatible).
Regenerate: `python tools/sync_skill_schemas.py` (the audit skill's
`schemas/output_schema.yaml`), `python scripts/gen_capability_json_schemas.py`,
`python scripts/gen_standard_agents_binding.py`.

### 3.2 Canonical: `schemas/world_state_schema.yaml` (1.1.0 → 1.2.0, one bump shared with S1 and S2a)

In `types.ActionRecord.properties`, add after `action_id`:

```yaml
      run_id:
        type: string
        description: The run the record belongs to (Standard v1.2 §5.19) or, for a
          record of a tool call, the scope its safety layer keeps records for (§5.18.5).
      frame:
        type: array
        items:
          type: string
        description: For a step of a run, the workflows of its nested runs, root first.
      step:
        type: integer
        minimum: 0
        description: For a step of a run, its index in the last workflow of frame.
      capability:
        type: string
        description: The ontology capability the action performs.
      tool:
        type: string
        description: For a tool call, the name the host offers the tool under (§5.18).
      call_id:
        type: string
        description: For a tool call, the host's identifier of the call, if it has one.
      checkpoint_id:
        type: string
        description: The checkpoint the action used, took or restored.
      code:
        type: string
        description: The diagnostic code (Standard v1.2 §9) of an action that failed,
          was refused or was cancelled.
      reason_code:
        type: string
        description: Why, as a token (Standard v1.2 §5.19.7), such as unsupported_domain.
      details:
        type: object
        description: Other data the record carries, such as the event an audit step
          recorded (details.event) or how a run ended (a run record, Standard v1.2
          §5.19.8, §6.4).
      recorded_by:
        type: object
        required:
        - name
        properties:
          name:
            type: string
          version:
            type: string
          config_sha256:
            type: string
            description: SHA-256 of the configuration the implementation applied.
          settings:
            type: object
            description: The settings that decided the action, listed where they are
              few (Standard v1.2 §5.18.8), such as a safety layer's approval mode
              and checkpoint maximum age.
        description: The implementation that wrote the record, set by that
          implementation only, never taken from what it records (Standard v1.2 §6.4).
      prev_hmac:
        type: string
        description: In an append-only log of records, the hmac of the record before
          this one; empty for the first (Standard v1.2 §6.4).
      hmac:
        type: string
        description: In such a log, the HMAC-SHA-256 of this record without hmac, under
          the log's key, as lowercase hexadecimal. The log computes prev_hmac and hmac
          when it appends the record, never taking them from what it records.
```

Replace `status` (S2a's description is merged in; the enum gains
`cancelled`):

```yaml
      status:
        type: string
        enum:
        - planned
        - approved
        - rejected
        - expired
        - executed
        - failed
        - rolled_back
        - cancelled
        description: rejected, an action that was refused before it ran, by its
          approvers (Standard v1.1 §5.14) or by an executor or a safety layer
          (Standard v1.2 §5.18), with code saying why; expired, an approval that
          lapsed; an action deferred to a queue stays planned (its approval, if
          any, says why it was not approved now) until its run is resumed, which
          updates this record in place and keeps its action_id (Standard v1.2
          §5.14.1), and a run record is planned while its run can be resumed
          (§5.19.8); a planned record in the terminal action of a run that did
          not end deferred is abandoned and never carried out; cancelled, an action that was approved or queued when its
          run was cancelled, or had started and may have been carried out
          (Standard v1.2 §5.19.5).
```

In `approval.properties`, add after `decision`:

```yaml
          decision_id:
            type: string
            description: The identifier the host gave the decision; single-use
              within the run (Standard v1.2 §5.14, §5.19.1). Absent when no decision
              arrived (expired).
```

Also replace `reason`'s description:

```yaml
      reason:
        type: string
        nullable: true
        description: Why the action did not go ahead or failed, in words (rejected,
          expired, refused in an unattended run, cancelled); reason_code says it as
          a token.
```

All additions are optional properties, an enum value and descriptions
(§11.4: compatible). `schema.version: 1.2.0`.

### 3.3 Canonical: `schemas/authority_trust_model.yaml` (descriptions only)

Replace the `overrides` block with the same values and comments (the file is
a YAML document of values; descriptions go in comments, as elsewhere in the
file):

```yaml
# Manual overrides (Standard v1.2 §8.4): a person or agent replacing a trust
# score or a conflict's winner by hand.
overrides:
  # When false, every override is refused.
  allow_manual_override: true
  # An override cites at least one evidence anchor for the value it sets.
  requires_anchors: true
  # An override is recorded as an audit record (§6.4) before it takes
  # effect; one whose record cannot be written does not take effect.
  audit_required: true
```

(If S6 bumps this file's version, these comments ride on that bump; no value
changes.)

### 3.4 Supporting: `schemas/workflow_catalog.schema.json`

Replace the two step properties:

```json
"parallel_group": {
  "type": "string",
  "description": "Group ID (STANDARD v1.2 §5.2.3): the steps of one group are not ordered relative to each other; an executor may run them in any order or concurrently."
},
"join": {
  "type": "string",
  "description": "When the group is complete (STANDARD v1.2 §5.2.3). The one value defined is 'all_complete', the default; any other value is W618 and ignored."
},
```

(`join` stays `type: string`, not an enum: a 1.1 value other than
`all_complete` must stay schema-valid; the warning carries the rule.)

### 3.5 New: `schemas/host_protocol.schema.json` (full content)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://acs.synapti.ai/schemas/host_protocol.schema.json",
  "title": "Agent Capability Standard host protocol",
  "description": "The actions an executor issues to its host and the responses it accepts (Agent Capability Standard 1.2.0, section 5.19). Every value is I-JSON (RFC 7493). An executor of class EX (section 10.5) issues exactly these actions (a host ignores action members it does not know) and takes every response this schema allows as section 5.19.1 says: response members the protocol does not define are ignored, and a response that validates may still be refused or fail its step. $defs.run_options, $defs.snapshot and $defs.trace_event describe the reference executor's forms and are informative.",
  "oneOf": [
    { "$ref": "#/$defs/action" },
    { "$ref": "#/$defs/response" }
  ],
  "$defs": {
    "time": {
      "type": "integer",
      "minimum": 0,
      "maximum": 253402300799999,
      "description": "Milliseconds since 1970-01-01T00:00:00Z (section 5.19.3)."
    },
    "time_or_null": { "oneOf": [{ "$ref": "#/$defs/time" }, { "type": "null" }] },
    "step": { "type": "integer", "minimum": 0, "description": "Index of the step in the last workflow of frame." },
    "strings": { "type": "array", "items": { "type": "string" } },
    "strings_or_null": { "oneOf": [{ "$ref": "#/$defs/strings" }, { "type": "null" }] },
    "digest": { "type": "string", "pattern": "^[0-9A-Fa-f]{64}$" },
    "reason": {
      "type": "string",
      "pattern": "^(x-[a-z0-9][a-z0-9_.-]{0,61}|unsupported_capability|unsupported_domain|not_recorded)$",
      "description": "Section 5.19.7: a token the Standard defines, or an x- vendor token."
    },
    "agent_identity": {
      "type": "object",
      "required": ["principal", "kind"],
      "properties": {
        "principal": { "type": "string" },
        "kind": { "enum": ["agent", "human", "service"] }
      },
      "description": "schemas/agent_identity_schema.yaml#/agent_identity (section 5.17)."
    },
    "action_record": {
      "type": "object",
      "required": ["action_id", "timestamp", "actor", "intent", "status"],
      "properties": {
        "status": { "enum": ["planned", "approved", "rejected", "expired", "executed", "failed", "rolled_back", "cancelled"] }
      },
      "description": "schemas/world_state_schema.yaml#/types/ActionRecord (section 6.4)."
    },
    "deferral": {
      "type": "object",
      "required": ["frame", "step", "store_as", "reason", "action_id"],
      "additionalProperties": false,
      "properties": {
        "frame": { "$ref": "#/$defs/strings" },
        "step": { "$ref": "#/$defs/step" },
        "store_as": { "type": ["string", "null"] },
        "reason": { "type": "string" },
        "action_id": { "type": ["string", "null"] }
      },
      "description": "A deferred step (section 5.14)."
    },
    "head": {
      "type": "object",
      "required": ["run_id", "id", "frame", "kind"],
      "properties": {
        "run_id": { "type": "string" },
        "id": { "type": "integer", "minimum": 1 },
        "frame": { "type": "array", "items": { "type": "string" }, "minItems": 1 },
        "kind": { "type": "string" }
      }
    },
    "action": {
      "oneOf": [
        { "$ref": "#/$defs/InvokeCapability" },
        { "$ref": "#/$defs/CreateCheckpoint" },
        { "$ref": "#/$defs/Rollback" },
        { "$ref": "#/$defs/RequestApproval" },
        { "$ref": "#/$defs/RecheckSource" },
        { "$ref": "#/$defs/AwaitEvent" },
        { "$ref": "#/$defs/Sleep" },
        { "$ref": "#/$defs/Completed" },
        { "$ref": "#/$defs/Failed" }
      ]
    },
    "InvokeCapability": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["step", "capability", "store_as", "domain", "inputs", "deadline", "attempt"],
      "properties": {
        "kind": { "const": "InvokeCapability" },
        "step": { "$ref": "#/$defs/step" },
        "capability": { "type": "string" },
        "store_as": { "type": ["string", "null"] },
        "domain": { "type": ["string", "null"] },
        "inputs": { "type": "object" },
        "deadline": { "$ref": "#/$defs/time_or_null" },
        "attempt": { "type": "integer", "minimum": 1 },
        "replaces": { "description": "The task_id of the delegation this one replaces (section 5.13)." }
      },
      "unevaluatedProperties": false
    },
    "CreateCheckpoint": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["step"],
      "properties": { "kind": { "const": "CreateCheckpoint" }, "step": { "$ref": "#/$defs/step" } },
      "unevaluatedProperties": false
    },
    "Rollback": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["step", "checkpoint_id"],
      "properties": {
        "kind": { "const": "Rollback" },
        "step": { "$ref": "#/$defs/step" },
        "checkpoint_id": { "type": "string" }
      },
      "unevaluatedProperties": false
    },
    "RequestApproval": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["step", "approver", "mode", "shown", "digest", "expires_at"],
      "properties": {
        "kind": { "const": "RequestApproval" },
        "step": { "$ref": "#/$defs/step" },
        "approver": {
          "type": "object",
          "required": ["kind"],
          "properties": {
            "kind": { "enum": ["human", "standing_mandate"] },
            "role": { "type": "string" },
            "min_approvers": { "type": "integer", "minimum": 1 },
            "mandate_ref": { "type": "string" },
            "always_ask": { "const": true },
            "sender_check": { "$ref": "#/$defs/strings" },
            "accept_trust_classes": { "$ref": "#/$defs/strings" }
          }
        },
        "mode": { "enum": ["in_session", "out_of_band"] },
        "shown": { "type": "array" },
        "digest": { "$ref": "#/$defs/digest" },
        "expires_at": { "$ref": "#/$defs/time_or_null" },
        "queued_action_id": { "type": "string", "description": "Section 5.14.1: the queued action a resumed run asks about." }
      },
      "unevaluatedProperties": false
    },
    "RecheckSource": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["step", "source", "compare"],
      "properties": {
        "kind": { "const": "RecheckSource" },
        "step": { "$ref": "#/$defs/step" },
        "source": { "type": "string" },
        "compare": { "enum": ["version", "digest"] }
      },
      "unevaluatedProperties": false
    },
    "AwaitEvent": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["step", "event_type", "source_kind", "correlate", "accept_from", "sender_check", "accept_trust_classes", "liveness", "deadline"],
      "properties": {
        "kind": { "const": "AwaitEvent" },
        "step": { "$ref": "#/$defs/step" },
        "event_type": { "type": "string" },
        "source_kind": { "type": ["string", "null"] },
        "correlate": { "type": "object" },
        "accept_from": { "$ref": "#/$defs/strings_or_null" },
        "sender_check": { "$ref": "#/$defs/strings_or_null" },
        "accept_trust_classes": { "$ref": "#/$defs/strings_or_null" },
        "delegate_principal": { "type": "string" },
        "liveness": {
          "oneOf": [
            {
              "type": "object",
              "required": ["mode", "interval"],
              "properties": {
                "mode": { "enum": ["push", "probe"] },
                "interval": { "type": "string" },
                "failure_threshold": { "type": "integer", "minimum": 1 }
              }
            },
            { "type": "null" }
          ]
        },
        "deadline": { "$ref": "#/$defs/time_or_null" }
      },
      "unevaluatedProperties": false
    },
    "Sleep": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["until"],
      "properties": { "kind": { "const": "Sleep" }, "until": { "$ref": "#/$defs/time" } },
      "unevaluatedProperties": false
    },
    "Completed": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["outcome", "cause", "outputs", "action_records", "deferred"],
      "properties": {
        "kind": { "const": "Completed" },
        "outcome": { "enum": ["completed", "escalated", "deferred", "replan_required"] },
        "cause": { "type": ["string", "null"] },
        "ended": {
          "type": "object",
          "required": ["step", "message"],
          "properties": { "step": { "$ref": "#/$defs/step" }, "message": { "type": ["string", "null"] } }
        },
        "outputs": { "type": "object" },
        "action_records": { "type": "array", "items": { "$ref": "#/$defs/action_record" } },
        "deferred": { "type": "array", "items": { "$ref": "#/$defs/deferral" } }
      },
      "unevaluatedProperties": false
    },
    "Failed": {
      "allOf": [{ "$ref": "#/$defs/head" }],
      "required": ["code", "step", "message", "action_records", "deferred"],
      "properties": {
        "kind": { "const": "Failed" },
        "code": { "type": "string", "pattern": "^[RF][0-9]{3}$" },
        "step": { "oneOf": [{ "$ref": "#/$defs/step" }, { "type": "null" }] },
        "message": { "type": "string" },
        "reason": { "$ref": "#/$defs/reason" },
        "checkpoint_id": { "type": "string" },
        "action_records": { "type": "array", "items": { "$ref": "#/$defs/action_record" } },
        "deferred": { "type": "array", "items": { "$ref": "#/$defs/deferral" } }
      },
      "unevaluatedProperties": false
    },
    "response": {
      "description": "A response. Members the protocol does not define are allowed and ignored (section 5.19.1), as in 1.1, so no response sets additionalProperties to false.",
      "oneOf": [
        { "$ref": "#/$defs/Output" },
        { "$ref": "#/$defs/Error" },
        { "$ref": "#/$defs/Checkpoint" },
        { "$ref": "#/$defs/RolledBack" },
        { "$ref": "#/$defs/Decision" },
        { "$ref": "#/$defs/Current" },
        { "$ref": "#/$defs/Event" },
        { "$ref": "#/$defs/LivenessLost" }
      ]
    },
    "Output": {
      "type": "object",
      "required": ["kind", "value"],
      "properties": { "kind": { "const": "Output" }, "value": { "description": "The capability's output: an object with the fields its contract requires, else the step fails R402." } }
    },
    "Error": {
      "type": "object",
      "required": ["kind", "code"],
      "properties": {
        "kind": { "const": "Error" },
        "code": { "type": "string" },
        "message": { "type": "string", "default": "" },
        "reason": { "description": "Section 5.19.7: a defined token or an x- vendor token ($defs.reason); any other value is ignored, as if absent." }
      }
    },
    "Checkpoint": {
      "type": "object",
      "required": ["kind", "checkpoint_id"],
      "properties": { "kind": { "const": "Checkpoint" }, "checkpoint_id": { "type": "string" } }
    },
    "RolledBack": {
      "type": "object",
      "required": ["kind"],
      "properties": { "kind": { "const": "RolledBack" } }
    },
    "Decision": {
      "type": "object",
      "required": ["kind", "decision_id", "decision", "digest"],
      "properties": {
        "kind": { "const": "Decision" },
        "decision_id": { "type": "string" },
        "decision": { "type": "string", "description": "approved, rejected or unavailable; any other value refuses the step (F502)." },
        "approvers": { "$ref": "#/$defs/strings", "default": [] },
        "digest": { "type": "string" },
        "approver_identities": {
          "oneOf": [{ "type": "array", "items": { "$ref": "#/$defs/agent_identity" } }, { "type": "null" }],
          "description": "identity@1 (section 5.17)."
        }
      }
    },
    "Current": {
      "type": "object",
      "required": ["kind", "value"],
      "properties": { "kind": { "const": "Current" }, "value": {} }
    },
    "Event": {
      "type": "object",
      "required": ["kind", "event"],
      "properties": {
        "kind": { "const": "Event" },
        "event": {},
        "principal": { "type": ["string", "null"] },
        "identity": { "oneOf": [{ "$ref": "#/$defs/agent_identity" }, { "type": "null" }] }
      }
    },
    "LivenessLost": {
      "type": "object",
      "required": ["kind"],
      "properties": { "kind": { "const": "LivenessLost" } }
    },
    "run_options": {
      "type": "object",
      "required": ["workflow", "inputs", "attendance", "run_id", "now_ms"],
      "additionalProperties": false,
      "properties": {
        "workflow": { "type": "string" },
        "inputs": { "type": "object" },
        "attendance": { "enum": ["attended", "unattended"] },
        "run_id": { "type": "string" },
        "now_ms": { "$ref": "#/$defs/time" },
        "actor_identity": { "$ref": "#/$defs/agent_identity" },
        "records": { "enum": ["approvals", "actions"], "default": "approvals" }
      },
      "description": "Informative: what start takes (section 5.19.2)."
    },
    "snapshot": {
      "type": "object",
      "required": ["state", "sha256", "hmac"],
      "additionalProperties": false,
      "properties": {
        "state": { "type": "string", "description": "The run state as canonical JSON (RFC 8785); its form is the executor's own." },
        "sha256": { "$ref": "#/$defs/digest" },
        "hmac": { "oneOf": [{ "$ref": "#/$defs/digest" }, { "type": "null" }] }
      },
      "description": "Informative: the reference executor's saved state (section 5.19.4)."
    },
    "trace_event": {
      "type": "object",
      "required": ["seq", "at", "kind", "frame", "step", "detail"],
      "additionalProperties": false,
      "properties": {
        "seq": { "type": "integer", "minimum": 0 },
        "at": { "$ref": "#/$defs/time" },
        "kind": { "type": "string" },
        "frame": { "$ref": "#/$defs/strings" },
        "step": { "oneOf": [{ "$ref": "#/$defs/step" }, { "type": "null" }] },
        "detail": { "type": "object" }
      },
      "description": "Informative: one event of the reference executor's trace (docs/guides/RUNNING_WORKFLOWS.md)."
    }
  }
}
```

Checked while designing: with `run_id` added to each action (not yet
emitted on 6b3e40b), this schema accepts all 1,143 actions (all nine kinds),
every `respond` value, every trace event and every snapshot of a replay of
the 175 runtime fixtures on the current executor, and the fixture schema of
3.6 accepts all 175 fixture files (script:
`/tmp/claude-0/-home-user-agent-capability-standard/df1990d1-4c24-56ea-adb1-a7db50a2bac3/scratchpad/s2b/check_schema.py`,
run with `.venv/bin/python`; it is the seed of
`tests/test_host_protocol_schema.py`).

Notes for the implementer: `Error.code` is any string (a host may send
other codes; they are read as R402). `InvokeCapability.replaces`,
`AwaitEvent.delegate_principal`, `RequestApproval.queued_action_id`,
`Completed.ended`, `Failed.reason` and `Failed.checkpoint_id` are optional
because the executor omits them when they do not apply. The S2a members
(`queued_action_id`, `approver_identities`, approver `sender_check` and
`accept_trust_classes`) are included here so one schema covers both parts of
RFC-0006. The `action_record` definition intentionally checks only the
required members and the status: the full definition is the canonical YAML.
Responses allow members they do not define (§5.19.1), so the schema alone no
longer catches a typo in a fixture's `respond`; `tests/test_host_protocol_schema.py`
therefore also checks every fixture `respond` against a strict copy of the
response definitions (the same with `additionalProperties: false` and
`Error.reason` as `$defs.reason`), except in the two fixtures that test
leniency (`response_extra_members_ignored`, `error_reason_outside_grammar_ignored`).

### 3.6 New: `tests/conformance/runtime/schema/fixture.schema.json` (full content)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Runtime fixture (Agent Capability Standard 1.2.0, section 10.5)",
  "type": "object",
  "required": ["description", "catalog", "workflow", "inputs", "attendance", "start", "script", "end", "trace_kinds"],
  "additionalProperties": false,
  "properties": {
    "description": { "type": "string", "minLength": 1 },
    "catalog": { "type": "object" },
    "workflow": { "type": "string" },
    "inputs": { "type": "object" },
    "attendance": { "enum": ["attended", "unattended"] },
    "actor_identity": { "type": "object" },
    "records": { "enum": ["approvals", "actions"] },
    "start": { "$ref": "#/$defs/time" },
    "script": { "type": "array", "items": { "$ref": "#/$defs/entry" } },
    "end": { "type": "object", "required": ["kind"], "properties": { "kind": { "enum": ["Completed", "Failed"] } } },
    "run_record": {
      "type": "object",
      "description": "Optional: what the run record derived from the end (section 5.19.8) must match, by the subset rule of section 10.5."
    },
    "trace_kinds": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Informative: kinds the reference executor's trace must hold. Not part of class EX."
    }
  },
  "$defs": {
    "time": { "type": "integer", "minimum": 0, "maximum": 253402300799999 },
    "entry": {
      "oneOf": [
        { "$ref": "#/$defs/act" },
        { "$ref": "#/$defs/tick" },
        { "$ref": "#/$defs/wake" },
        { "$ref": "#/$defs/cancel" },
        { "$ref": "#/$defs/resume" }
      ]
    },
    "act": {
      "type": "object",
      "required": ["expect"],
      "additionalProperties": false,
      "properties": {
        "expect": { "type": "object", "required": ["kind"] },
        "respond": {
          "type": "object",
          "required": ["kind"],
          "description": "A host_protocol.schema.json response, in which the string \"{{digest}}\" stands for the pending action's digest and \"{{digest_upper}}\" for it in uppercase. Members the protocol does not define are ignored by the executor (section 5.19.1)."
        },
        "at": { "$ref": "#/$defs/time" }
      }
    },
    "tick": {
      "type": "object",
      "required": ["tick"],
      "additionalProperties": false,
      "properties": { "tick": { "$ref": "#/$defs/time" }, "changed": { "type": "boolean" } }
    },
    "wake": {
      "type": "object",
      "required": ["wake_at"],
      "additionalProperties": false,
      "properties": { "wake_at": { "oneOf": [{ "$ref": "#/$defs/time" }, { "type": "null" }] } }
    },
    "cancel": {
      "type": "object",
      "required": ["cancel"],
      "additionalProperties": false,
      "properties": {
        "cancel": {
          "type": "object",
          "required": ["reason"],
          "additionalProperties": false,
          "properties": { "reason": { "type": "string", "minLength": 1 }, "at": { "$ref": "#/$defs/time" } }
        }
      }
    },
    "resume": {
      "type": "object",
      "required": ["resume"],
      "additionalProperties": false,
      "properties": {
        "resume": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "attendance": { "enum": ["attended", "unattended"] },
            "at": { "$ref": "#/$defs/time" },
            "actor_identity": { "type": "object" }
          }
        }
      }
    }
  }
}
```

The `schema/` subdirectory is outside every glob that reads fixtures
(`*.json` in the directory itself, non-recursive in the generator, the cargo
harness and pytest).

### 3.7 New trigger vector files (format)

`tests/conformance/triggers/fire_times.json`:

```json
{
  "description": "Fire times of schedule triggers (STANDARD 1.2.0 §5.10.2), normative under §10.3. Each case gives a schedule, an instant 'after' (exclusive) and the next fire times, as RFC 3339 UTC and as milliseconds. Computed by scripts/gen_trigger_vectors.py with Python zoneinfo, independently of the reference core.",
  "standard": "1.2.0",
  "status": "normative",
  "tzdata": "<the IANA release the generator ran with, e.g. 2026a; the vectors are normative with it or any release that agrees on these dates (section 10.3)>",
  "cases": {
    "<name>": {
      "schedule": {"cron": "30 2 * * *", "timezone": "America/New_York"},
      "after": "2026-03-07T12:00:00Z",
      "after_ms": 1772884800000,
      "next": ["2026-03-08T07:30:00Z", "2026-03-09T06:30:00Z"],
      "next_ms": [1772955000000, 1773037800000],
      "note": "02:30 does not occur on 8 March: read with the offset before the change (-05:00)"
    }
  }
}
```

`tests/conformance/triggers/overlap.json`:

```json
{
  "description": "Overlap decisions (§5.10.2). 'events' is a sequence: 'fire' (a fire time), 'end' (a run this trigger started ends, including one that ends deferred), 'resume' (a run this trigger started that ended deferred is resumed, §5.14.1, and is in progress again), 'missed' (fire times passed while the host was stopped). 'expect' gives, per event, 'start', 'buffered', 'skipped' or, for 'end', 'start' (a buffered run starts) or 'none', and for 'resume', 'none'.",
  "standard": "1.2.0",
  "status": "normative",
  "cases": {
    "skip_while_running": {"overlap": "skip", "events": ["fire", "fire", "end", "fire"], "expect": ["start", "skipped", "none", "start"]},
    "buffer_one_holds_one": {"overlap": "buffer_one", "events": ["fire", "fire", "fire", "end", "end"], "expect": ["start", "buffered", "skipped", "start", "none"]},
    "allow_all_starts_each": {"overlap": "allow_all", "events": ["fire", "fire", "end", "end"], "expect": ["start", "start", "none", "none"]},
    "missed_counts_once": {"overlap": "skip", "events": ["missed"], "expect": ["start"]},
    "missed_while_running_buffers": {"overlap": "buffer_one", "events": ["fire", "missed", "end"], "expect": ["start", "buffered", "start"]},
    "default_is_skip": {"overlap": null, "events": ["fire", "fire"], "expect": ["start", "skipped"]},
    "resumed_run_is_in_progress": {"overlap": "skip", "events": ["fire", "end", "resume", "fire", "end", "fire"], "expect": ["start", "none", "none", "skipped", "none", "start"]},
    "resumed_run_holds_buffer": {"overlap": "buffer_one", "events": ["fire", "end", "resume", "fire", "end"], "expect": ["start", "none", "none", "buffered", "start"]}
  }
}
```

`tests/conformance/triggers/events.json`:

```json
{
  "description": "Which events start a run of an event trigger (§5.10.2). Each case gives a trigger and a sequence of events delivered to the host, all admitted by its sender policy (the policy is the host's and is not a vector); 'expect' gives, per event, 'start' (a run starts, with the event as the delivers_to input), 'no_match' (event_type or source_kind differs) or 'duplicate' (an event with this event_id already started a run of this trigger).",
  "standard": "1.2.0",
  "status": "normative",
  "cases": {
    "type_matches": {"trigger": {"event_type": "deploy.finished", "delivers_to": "ev"}, "events": [{"event_id": "e1", "event_type": "deploy.finished", "source": {"kind": "agent", "name": "ci"}}], "expect": ["start"]},
    "type_differs": {"trigger": {"event_type": "deploy.finished", "delivers_to": "ev"}, "events": [{"event_id": "e1", "event_type": "deploy.started", "source": {"kind": "agent", "name": "ci"}}], "expect": ["no_match"]},
    "source_kind_differs": {"trigger": {"event_type": "deploy.finished", "source_kind": "agent", "delivers_to": "ev"}, "events": [{"event_id": "e1", "event_type": "deploy.finished", "source": {"kind": "human", "name": "ops"}}], "expect": ["no_match"]},
    "redelivered_starts_once": {"trigger": {"event_type": "deploy.finished", "delivers_to": "ev"}, "events": [{"event_id": "e1", "event_type": "deploy.finished", "source": {"kind": "agent", "name": "ci"}}, {"event_id": "e1", "event_type": "deploy.finished", "source": {"kind": "agent", "name": "ci"}}, {"event_id": "e2", "event_type": "deploy.finished", "source": {"kind": "agent", "name": "ci"}}], "expect": ["start", "duplicate", "start"]},
    "no_match_does_not_consume_id": {"trigger": {"event_type": "deploy.finished", "delivers_to": "ev"}, "events": [{"event_id": "e1", "event_type": "deploy.started", "source": {"kind": "agent", "name": "ci"}}, {"event_id": "e1", "event_type": "deploy.finished", "source": {"kind": "agent", "name": "ci"}}], "expect": ["no_match", "start"]}
  }
}
```

(The events are abbreviated to the members the decision reads; the
generator writes complete canonical events, `timestamp`, `raw`,
`canonical`, `anchors` and `provenance` included, so each validates against
`event_schema.yaml`.)

`tests/conformance/triggers/attendance.json`:

```json
{
  "description": "The attendance of a run a trigger starts (§5.10, §5.10.2).",
  "standard": "1.2.0",
  "status": "normative",
  "cases": {
    "manual_default": {"trigger": {"kind": "manual"}, "expect": "attended"},
    "schedule_default": {"trigger": {"kind": "schedule", "schedule": {"every": "1h"}}, "expect": "unattended"},
    "event_default": {"trigger": {"kind": "event", "event": {"event_type": "e", "delivers_to": "ev"}}, "expect": "unattended"},
    "invoke_follows_invoker_attended": {"trigger": {"kind": "invoke"}, "invoker": "attended", "expect": "attended"},
    "invoke_follows_invoker_unattended": {"trigger": {"kind": "invoke"}, "invoker": "unattended", "expect": "unattended"},
    "declared_overrides": {"trigger": {"kind": "schedule", "schedule": {"every": "1h"}, "attendance": "attended"}, "expect": "attended"},
    "declared_overrides_manual": {"trigger": {"kind": "manual", "attendance": "unattended"}, "expect": "unattended"}
  }
}
```

Fire-time cases (computed with the oracle sketch at
`/tmp/claude-0/-home-user-agent-capability-standard/df1990d1-4c24-56ea-adb1-a7db50a2bac3/scratchpad/s2b/fire.py`; the generator recomputes all of them):

| Name | Schedule | After | Next (UTC) | Pins |
|---|---|---|---|---|
| `utc_weekdays` | `0 6 * * MON-FRI`, UTC | 2026-11-13T07:00Z (Fri) | 2026-11-16T06:00Z, 11-17T06:00Z | basic, weekday range |
| `strictly_after` | `0 6 * * *`, UTC | 2026-11-16T06:00Z | 2026-11-17T06:00Z | `after` is exclusive |
| `every_15m` | `every: 15m` | 1000 ms | 900000, 1800000 | epoch anchor |
| `every_ignores_timezone` | `every: 1d`, `timezone: America/New_York` | 2026-11-15T12:00Z | 2026-11-16T00:00Z | `timezone` has no effect |
| `every_rounds_up` | `every: PT0.0005S` | 5 ms | 6, 7 | sub-millisecond interval rounds up |
| `every_7m` | `every: 7m` | 0 | 420000, 840000 | interval not dividing an hour |
| `step_list_range` | `5/20 0 1 jan,Jul *`, UTC | 2026-01-01T00:30Z | 2026-01-01T00:45Z, 2026-07-01T00:05Z | `a/step`, names |
| `vixie_or` | `0 0 13 * FRI`, UTC | 2026-11-15T00:00Z | 2026-11-20, 11-27, 12-04 (00:00Z) | both day fields restricted |
| `leap_day` | `0 0 29 2 *`, UTC | 2026-03-01T00:00Z | 2028-02-29T00:00Z | sparse schedule |
| `lisbon_spring` | `0 6 * * MON-FRI`, Europe/Lisbon | 2026-03-27T12:00Z | 2026-03-30T05:00Z, 03-31T05:00Z | offset change between fires |
| `new_york_gap` | `30 2 * * *`, America/New_York | 2026-03-07T12:00Z | 2026-03-08T07:30Z, 03-09T06:30Z | skipped local time, offset before |
| `new_york_fold` | `30 1 * * *`, America/New_York | 2026-10-31T12:00Z | 2026-11-01T05:30Z, 11-02T06:30Z | repeated local time fires once, first |
| `new_york_gap_dedup` | `*/30 2-3 * * *`, America/New_York | 2026-03-08T06:00Z | 2026-03-08T07:00Z, 07:30Z, 2026-03-09T06:00Z | gap times collide with later ones: one fire each |
| `apia_skipped_day` | `0 12 * * *`, Pacific/Apia | 2011-12-28T00:00Z | 2011-12-28T22:00Z, 12-29T22:00Z, 12-30T22:00Z, 12-31T22:00Z | a whole skipped day (30 Dec 2011) |
| `lord_howe_half_hour` | `15 2 * * *`, Australia/Lord_Howe | 2026-10-03T00:00Z | 2026-10-03T15:45Z, 10-04T15:15Z | a 30-minute clock change |
| `kolkata_offset` | `0 9 * * *`, Asia/Kolkata | 2026-11-15T00:00Z | 2026-11-15T03:30Z | half-hour offset |
| `none_before_max` | `0 0 1 1 *`, UTC | 253402300799999 | (empty) | nothing after the maximum time |

(The generator asserts its own computed values; values above are from the
oracle and are the generator's regression check. Vectors use dates up to
2027 only, so a tzdata update for later years cannot change them; a
correction for a past date could, which is why §10.3 makes them normative
with the named release or any that agrees on these dates. The cargo test
reads the file with chrono-tz's bundled tzdata and the pytest with the
system's or the `tzdata` package's; both must agree on these dates, and the
test message names both releases when they do not.)

---

## 4. New diagnostic codes

| Code | Name | Severity | Meaning | Raised by |
|---|---|---|---|---|
| R408 | CANCELLED | error | The host cancelled the run (§5.19.5); no retry, failure mode, recovery or handler ran | The executor's `cancel` operation (`core/src/exec`), as the `Failed` action's `code` and the `code` of the records it sets `cancelled`. Never matched by `on_error` (§5.12's list is unchanged, so `on_error: R408` stays S303) |
| W618 | UNKNOWN_JOIN | warning | A `join` other than `all_complete`, or a `join` on a step with no `parallel_group`; it is ignored (§5.2.3) | The validator (`core/src/validate/mod.rs`), once per step, `location.field: "join"` |
| W619 | GROUP_MATE_READ | warning | A step reads the store of a step in its own `parallel_group`, which need not have run yet (§5.2.3) | The validator, once per (step, mate), `location`: `field` (the first executable field holding the reference), `ref` (the reference text), `mate` (the mate's step index) |

Add to `core/src/diag.rs` in the `codes!` table (R408 after R406, W618/W619
after S2a/S1's last warnings, keeping the list in code order):

```rust
    Cancelled = "R408", "CANCELLED", Error;
    UnknownJoin = "W618", "UNKNOWN_JOIN", Warning;
    GroupMateRead = "W619", "GROUP_MATE_READ", Warning;
```

(Final numbers allocated in FOUNDATION.md part C.)

---

## 5. Implementation plan per file

### 5.1 `core/Cargo.toml`

Add `chrono = { version = "0.4.45", default-features = false }` (already in
the lock file as chrono-tz's dependency; no new crate). `NaiveDate`,
`NaiveDateTime`, `TimeZone`, `LocalResult`, `Datelike`, `Timelike` are
available without default features.

### 5.2 `core/src/trigger.rs` (new; `pub mod trigger;` in `lib.rs`)

```rust
//! Trigger evaluation helpers (STANDARD v1.2 §5.10.2): fire times of a
//! schedule. The host evaluates triggers; this is the shared function.

/// The first fire time strictly after `after_ms`, or None when there is none
/// up to MAX_TIME. `schedule` is a validated `triggers[].schedule` mapping.
pub fn next_fire(schedule: &serde_json::Value, after_ms: u64) -> Result<Option<u64>, String>;
```

Behaviour:
- `after_ms >= MAX_TIME` → `Ok(None)`.
- `every`: `duration::parse` → nanos; `ms = ceil(nanos / 1_000_000)`; zero →
  `Err("every must be longer than zero")`; `next = (after_ms / ms + 1) * ms`
  (checked arithmetic); `> MAX_TIME` → `None`.
- `cron`: `Cron::parse`; `tz = timezone.unwrap_or("UTC").parse::<Tz>()` (error
  → `Err`). Search:
  1. `start_day` = the local date of `after_ms` minus 2 days (a gap time can
     map up to ~24 h forward, Pacific/Apia 2011).
  2. For each local date `d` from `start_day` (at most 3000 days + 3, enough
     for a leap-day schedule across a non-leap century year), skip unless
     `cron.matches_day(d.day(), d.month(), weekday)`; for each matching hour
     and minute (bit iteration over `Cron` fields; add `pub(crate)` iterators
     `hours()`, `minutes()` and `matches_day()` to `cron.rs`), compute
     `instant(tz, local)`; keep the minimum instant `> after_ms`.
  3. Stop when `best.is_some()` and the date's local midnight read as UTC
     minus 14 h (the largest UTC offset) is after `best`: no later local time
     can map earlier.
  4. Return `best` if `<= MAX_TIME`.
- `fn instant(tz: Tz, local: NaiveDateTime) -> u64`:
  `match tz.from_local_datetime(&local)`: `Single(t)` → t; `Ambiguous(a, b)`
  → the earlier; `None` (a gap) → walk back minute by minute (at most 48 h)
  to the latest existing local minute `p`, take its offset `o` (`p` resolved
  `Single`, or the later of an `Ambiguous`), return `local - o` as UTC.
  Times before 1970 cannot occur (`after_ms >= 0` and the 2-day margin is
  clamped at the epoch).
- Unit tests: one per row of the fire-time table in 3.7, plus
  `instant_gap_uses_offset_before`, `instant_fold_takes_first`,
  `every_zero_is_an_error`, `bad_timezone_is_an_error`, and
  `matches_day_vixie`.

`core/src/cron.rs`: add `pub(crate) fn matches_day(&self, dom, month, dow) -> bool`
(the day part of `matches`, which then calls it), and
`pub(crate) fn hours(&self) -> impl Iterator<Item = u32>` and
`minutes(&self)`. Doc comment: point to `trigger::next_fire`.

### 5.3 `core/src/exec/mod.rs`

Types:
- `Action`: add `pub run_id: String` (`#[serde(default)]`), set by `emit` and
  `finish` from `st.run_id`.
- `Response::Error`: add `#[serde(default, skip_serializing_if = "Option::is_none")] reason: Option<Value>`
  (any JSON value: a non-string `reason` must not make serde refuse the
  response, §5.19.7; the machine reads it with `reason_token`, 5.4 item 7).
  No `deny_unknown_fields` on `Response` (unchanged): unknown members stay
  ignored. A unit test `response_unknown_members_ignored` deserialises an
  `Output` and an `Error` with extra members and pins that.
- `pub enum RecordMode { Approvals, Actions }` (`Serialize`, `Deserialize`,
  `snake_case`, `Default` = `Approvals`).
- `StartOptions`: add `pub records: RecordMode`. Update every constructor
  (python.rs, `core/tests/runtime.rs` `opts()` and `play()`).
- `StepError`: add `#[serde(default)] reason: Option<String>`.
- `StepState`: add `#[serde(default)] checkpoint_id: Option<String>` (the
  checkpoint the step used or, for a `checkpoint` step, took) and
  `#[serde(default)] started: bool` (§5.19.5: the executor issued a
  `CreateCheckpoint`, `InvokeCapability` or `AwaitEvent` for the step in this
  pass, or started its nested run). `begin()` resets `cur`, so a new pass
  starts unstarted.
- `State`: add `#[serde(default)] records_mode: RecordMode`,
  `#[serde(default)] trace_base: u64`, `#[serde(default)] records_base: usize`,
  `#[serde(default)] records_taken_sha256: String`,
  `#[serde(default)] trace_taken_sha256: String` (chain heads, §5.19.4;
  empty until something is taken).
  Replace `finished: Option<Action>` by `finished: Option<Terminal>`:
  ```rust
  #[derive(Debug, Clone, Serialize, Deserialize)]
  pub(crate) struct Terminal { pub id: u64, pub frame: Vec<String>, #[serde(flatten)] pub end: End }
  #[derive(Debug, Clone, Serialize, Deserialize)]
  #[serde(tag = "kind")]
  pub(crate) enum End {
      Completed { outcome: Outcome, cause: Option<String>, #[serde(default, skip_serializing_if = "Option::is_none")] ended: Option<Value> },
      Failed { code: String, step: Option<usize>, message: String,
               #[serde(default, skip_serializing_if = "Option::is_none")] reason: Option<String>,
               #[serde(default, skip_serializing_if = "Option::is_none")] checkpoint_id: Option<String> },
  }
  ```
- `Body::Failed`: add `#[serde(default, skip_serializing_if = "Option::is_none")] reason: Option<String>` and
  `#[serde(default, skip_serializing_if = "Option::is_none")] checkpoint_id: Option<String>`.
- `SNAPSHOT_VERSION = 2` (shared with S2a). `restore` accepts 1 and 2. For a
  version-1 state: `finished` holds a full action: deserialize it as
  `Action`, convert to `Terminal` (drop `outputs`, `action_records`,
  `deferred`), and refuse (`Malformed`) when the derived terminal action
  differs from the stored one; set `run_id` on the pending action when empty.
- `pub enum CancelError { Ended(String) }` with Display "the run has ended
  ({kind/outcome or code}); only a run that has not ended, or one that ended
  deferred, can be cancelled".

`Run` API:
- `pub fn next(&self) -> Action` (owned): the pending action (clone), or the
  terminal one built by `State::terminal_action()`: `Completed` with
  `outputs = frames[0].stores`, `action_records = records.clone()`,
  `deferred = deferred_report()`, or `Failed` likewise. Move
  `deferred_report` from `Machine` to `impl State` so `next()` can call it.
- `pub fn tick(&mut self, now_ms: u64) -> bool`: true when the pending action
  or the end changed (compare `next_id` before and after, or have
  `Machine::tick` return the bool).
- `pub fn wake_at(&self) -> Option<u64>`: `None` when finished; `Sleep` →
  `until`; else `pending.deadline` → `d.checked_add(1).filter(|t| *t <= MAX_TIME)`;
  else `None`.
- `pub fn cancel(&mut self, reason: &str, now_ms: u64) -> Result<(), CancelError>`
  → `self.machine().cancel(reason, now_ms)`.
- `pub fn take_trace(&mut self) -> Vec<Value>`: `trace_base += trace.len()`;
  for each event in order, `trace_taken_sha256 = chain(&trace_taken_sha256, &ev)`;
  return `std::mem::take(&mut trace)`.
- `pub fn take_records(&mut self) -> Vec<Value>`: referenced = every frame's
  `cur.record` and (S2a) `cur.queued`, every parked frame's (S2a), every
  `deferrals[].record`; `k` = length of the prefix of `records` whose status
  is not `planned`/`approved` and whose absolute index is not referenced;
  `records_base += k`; fold each drained record into `records_taken_sha256`
  the same way; return the drained prefix.
- `pub(crate) fn chain(head: &str, item: &Value) -> String`:
  `canonical::sha256_hex(&(head.to_owned() + &canonical::canonical(item)))`
  (in `core/src/exec/canonical.rs`, beside `sha256_hex`). Public read access:
  `pub fn taken_heads(&self) -> (&str, &str)` (records, trace), so a host can
  check its archive; Python `Run.taken_sha256` → `{"records": …, "trace": …}`.
- `pub fn run_record(&self) -> Option<Value>`: `None` until the run has
  ended; else the §5.19.8 record built from `terminal_action()`,
  `st.run_id`, `iso(st.now)`, `st.actor_identity` (its `kind` as `actor`,
  else `"agent"`), `intent: format!("run {}", st.root)`, `status` by the
  §5.19.8 table, `code`/`reason_code`/`checkpoint_id` from `End::Failed`,
  `details: {kind, outcome?, cause?, ended?, message?, deferred, records:
  records_base + records.len()}` (members that do not apply omitted, `null`
  kept where the terminal action has `null`). Unit tests:
  `run_record_completed`, `run_record_failed_without_records`,
  `run_record_cancelled`, `run_record_deferred_is_planned`,
  `run_record_counts_taken_records`, `run_record_none_while_running`.
- `pub fn run_id(&self) -> &str`.
- `pub fn records(&self) -> &[Value]` stays `action_records()` (unchanged
  name), now "the records not yet taken".

`check_state` additions: every record index (`cur.record`, `deferrals[].record`,
S2a's `queued`) is `>= records_base` and `< records_base + records.len()`;
`trace_base` and `records_base` at most `MAX_TIME`; each chain head is empty
or 64 lowercase hexadecimal digits, and empty exactly when its base is 0; a
`Terminal` with `Failed.code == "R408"` is allowed only with
`pending == None`; a finished state is consistent with `finished` (as now).

`restore` (integrity, §5.19.4): unchanged in behaviour (digest always; HMAC
when a key is given; a signed snapshot without a key refused). The doc
comment on `restore` and on `check_state` says what each check proves: the
digest detects corruption, the HMAC who wrote it, `check_state` that this
executor could have produced it.

All indexing of `st.records[r]` in `machine.rs` goes through two helpers on
`State`: `fn rec(&self, r: usize) -> &Value` and `fn rec_mut(&mut self, r) -> &mut Value`
(`&records[r - records_base]`).

### 5.4 `core/src/exec/machine.rs`

1. **`trace()`**: `"seq": self.st.trace_base + self.st.trace.len() as u64`.
2. **`record(status, approval)`**: `n = records_base + records.len()`; add
   `"run_id"`, `"frame"` (`self.names()`), `"step"`, `"capability"`
   (`step_ref().capability`), and `"checkpoint_id"` when `cur.checkpoint_id`
   is set. (S2a's in-place update path sets the same members.)
3. **`emit`/`finish`**: set `run_id`. `finish` takes an `End`, stores
   `Terminal { id, frame, end }`.
4. **`decide`**: the approval sub-record gets `"decision_id": decision_id`
   (also for `unavailable`). Refused records (`record_refused` for F502
   cases) get `"code": "F502"`; the `when_unattended: skip` record gets no
   code.
5. **`checkpoint()`**: when consuming a checkpoint, set `cur.checkpoint_id`
   and, if `cur.record` is set, `rec_mut(r)["checkpoint_id"]`.
   **`output()`** for a `checkpoint` step: set `cur.checkpoint_id` to the id
   it took.
6. **Record mode `actions`** (`st.records_mode == Actions`):
   - `after()`: before `set_record_status("executed")`, if `cur.record` is
     `None`, `let r = self.record("executed", None); cur.record = Some(r)`.
   - `step_error(code, message, reason)`: if `cur.record` is `None` and
     `cur.started` (which covers `attempt >= 1` and a refused pre-step
     checkpoint, F501), write a `failed` record with `code` and
     `reason_code`; if `cur.record` is `Some(r)` and the record's status is
     `approved`, set `code`/`reason_code` on it (the existing
     `record_failed` later sets `failed`).
   - Failure-mode checkpoint (`respond` for `FailureCheckpoint`): on
     `Checkpoint`, push a record `{capability: "checkpoint", status:
     "executed", checkpoint_id}`; on `Error`, `{capability: "checkpoint",
     status: "failed", code: "F501"}`. Rollback (`GateRollback`,
     `FailureRollback`): on `RolledBack`, `{capability: "rollback", status:
     "executed", checkpoint_id}`; on `Error`, the same with `status:
     "failed"`, `code: "F503"`. All four through one helper
     `side_record(capability, status, checkpoint_id, code)`, which calls
     `record()` and overrides `capability`, so each has `intent` = the
     step's `purpose`, `step`, `frame`, `run_id` and `timestamp` like every
     other record (no executor-composed intent). These records are not
     `cur.record` (they do not change the step's record).
   - Retries keep `cur.record` (one record per pass); `begin()` resets `cur`,
     so a recovery loop's next pass writes a new record.
   - `started` (all modes, since cancellation reads it only in mode
     `actions` but the flag costs nothing): set in `emit` when the body is
     `CreateCheckpoint` with `Purpose::Checkpoint`, `InvokeCapability` or
     `AwaitEvent`, and in `invoke` when the nested frame is pushed (on the
     parent frame's `cur`).
   In mode `approvals` none of the record writing runs, except items 2, 4
   and 5, which add members to records that exist in 1.1.
7. **Error reasons**: `respond` passes `reason` from `Response::Error` through
   `fn reason_token(v: Option<Value>) -> (Option<String>, Option<Value>)`:
   a string that is one of the §5.19.7 tokens or matches
   `^x-[a-z0-9][a-z0-9_.-]{0,61}$` is the reason; anything else is
   `(None, Some(v))`, the value ignored. `exec_error(code, message, reason,
   ignored)` carries `reason` (or `reason_ignored`: the ignored value) in the
   `retry` trace detail and into `step_error`; `step_error` stores the
   reason in `StepError.reason` and adds `"reason"` (or `"reason_ignored"`)
   to the `step_failed` detail. The failure that ends the run carries the
   reason to `End::Failed.reason` (change `end_frame`'s
   `Err((code, message))` to a small struct `Fail { code, message, reason }`;
   executor-made failures pass `None`).
8. **`submit`**: no new refusal. A `reason` outside the grammar is ignored
   (item 7), never `SubmitError::Malformed`; unknown members of any response
   are ignored by serde as before. Unit tests: `reason_outside_grammar_is_ignored`
   (`"Unsupported"`, `"x-"`, a 65-character token, `5`, `{"a": 1}`: the
   submit succeeds, the step fails R402 as without a reason, `Failed` has
   no `reason`, the `step_failed` trace detail has `reason_ignored`) and
   `reason_grammar` (accepted: the three tokens, `x-acme.audio`).
9. **`audit` `require_record`**: in `output()`, after the contract check:
   ```rust
   if step.capability == "audit"
       && self.frame_ref().cur.inputs.get("require_record") == Some(&Value::Bool(true))
       && value.get("recorded") != Some(&Value::Bool(true))
   {
       return self.exec_error("R402", "the audit step did not write its record (recorded is not true)", Some("not_recorded".into()), None);
   }
   ```
10. **`tick`** returns `bool` (true in each branch that changes the run).
11. **`cancel(reason, now)`** (new):
    ```rust
    pub(crate) fn cancel(&mut self, reason: &str, now: u64) -> Result<(), CancelError> {
        match &self.st.finished {
            Some(Terminal { end: End::Completed { outcome: Outcome::Deferred, .. }, .. }) | None => {}
            Some(t) => return Err(CancelError::Ended(describe(t))),
        }
        self.st.now = self.st.now.max(now.min(MAX_TIME));
        let pending = self.st.pending.take();
        let was_finished = self.st.finished.take().is_some();
        // Open records first: approved or queued actions are cancelled.
        for r in self.st.records.iter_mut() {
            if matches!(r["status"].as_str(), Some("approved" | "planned")) {
                r["status"] = json!("cancelled"); r["code"] = json!("R408"); r["reason"] = json!(reason);
            }
        }
        if !was_finished && self.st.records_mode == RecordMode::Actions {
            // By the step's state (5.19.5): every frame's current step that
            // started this pass and has no record of it, root first.
            for i in 0..self.st.frames.len() {
                let cur = &self.st.frames[i].cur;
                if cur.started && cur.record.is_none() {
                    self.record_in(i, "cancelled", None, |r| {
                        r["code"] = json!("R408"); r["reason"] = json!(reason);
                    });
                }
            }
            // A pending failure-mode checkpoint or rollback has its own record.
            if let Some(p) = &pending {
                match (&p.action.body, &p.purpose) {
                    (Body::CreateCheckpoint { .. }, Purpose::FailureCheckpoint { .. }) =>
                        self.side_record_cancelled("checkpoint", None, reason),
                    (Body::Rollback { checkpoint_id, .. }, _) =>
                        self.side_record_cancelled("rollback", Some(checkpoint_id.clone()), reason),
                    _ => {}
                }
            }
        }
        let checkpoint_id = self.st.checkpoints.last().map(|c| c.id.clone());
        let step = (!was_finished).then(|| self.frame_ref().step);
        self.trace("run_cancelled", step, json!({"reason": reason}));
        for f in &mut self.st.frames { f.parked.clear(); f.resume = None; }   // S2a fields
        self.finish(End::Failed { code: "R408".into(), step, message: reason.into(), reason: None, checkpoint_id });
        Ok(())
    }
    ```
    `record_in(frame_index, status, approval, edit)` is `record()`
    generalised to a frame below the top (its `names()[..=i]`, its step, its
    step's `purpose` and capability); `record()` becomes
    `record_in(top, …)`. A step that has a record of its pass (an approved
    one, cancelled above, or an `executed`/`failed` one whose failure mode's
    checkpoint or rollback is pending) gets no second record. The terminal
    action keeps the deferrals (`deferred_report`), so a host sees which
    queued actions were dropped. A cancelled pending approval leaves no
    record (no decision was made; the step had not started); the trace and
    the `Failed` action's `step` show it. Unit tests:
    `cancel_records_started_steps_in_every_frame`,
    `cancel_does_not_record_unstarted_step` (pending approval, pending
    delay), `cancel_backoff_records_once`, `cancel_failure_checkpoint_records_it`.
12. **`invoke` frames**: nothing to do for cancellation (frames stay in the
    finished state; `next()` reports the top frame's names as now).

### 5.5 `core/src/validate/mod.rs` (W618, W619)

After `groups` is built (the existing loop over steps, which excludes
handlers):

- For each step (normal or handler) with a `join` that is a string: if it
  has no `parallel_group`, or `join != "all_complete"`, push W618 at
  `field: "join"`, message `"join '{v}' is not defined (only 'all_complete'); it is ignored"`
  or `"join without a parallel_group is ignored"`. (A non-string `join` is
  already S303.)
- For each normal step `i` in group `g`: `mates` = the `store_as` of the
  other normal members of `g` (with their indices). Collect the step's
  reference roots in its executable fields with the same rule as
  `exec::program` (`purpose`, `description`, failure-mode `condition` and
  prose `recovery` excluded); move that root collection into one function
  (`crate::refs::executable_roots(step: &Map<String, Value>) -> Vec<(String /*field*/, String /*root*/, String /*ref text*/)>`)
  and call it from both `program.rs` and here. For each mate store read,
  once per mate, push W619 with `field`, `ref`, `mate`.
- Unit tests: `join_other_value_warns`, `join_without_group_warns`,
  `join_all_complete_is_silent`, `mate_read_warns_once_per_mate`,
  `read_of_earlier_non_member_is_silent`, `quorum_reviewer_mate_not_w624`
  (quorum reviewers keep their own rule).

### 5.6 `core/src/python.rs`

- `#[pyfunction] fn next_fire(schedule: &Bound<PyAny>, after_ms: u64) -> PyResult<Option<u64>>`
  (`from_py`, `trigger::next_fire`; `Err` → `ValueError`); `m.add_function`.
- `PyRun::start(..., records = "approvals")`: parse `"approvals"`/`"actions"`,
  else `ValueError`.
- `PyRun::tick` returns `bool`.
- `PyRun::wake_at(&self) -> Option<u64>`.
- `PyRun::cancel(&mut self, reason: &str, now_ms: u64)`: `CancelError` →
  `ValueError`.
- `PyRun::take_trace`, `PyRun::take_records` → lists.
- `#[getter] taken_sha256` → `{"records": str, "trace": str}`.
- `PyRun::run_record(&self) -> Option<dict>` (`None` while running).
- `#[getter] run_id`.
- `next()` adapts to the owned `Action`.

### 5.7 `grounded_agency/_core.pyi`

```python
def next_fire(schedule: dict[str, Any], after_ms: int) -> int | None: ...

@final
class Run:
    @staticmethod
    def start(
        validator: Validator,
        catalog: Any,
        workflow: str,
        inputs: dict[str, Any] | None = None,
        *,
        attendance: str = "attended",
        run_id: str,
        now_ms: int,
        actor_identity: dict[str, Any] | None = None,
        records: str = "approvals",
    ) -> Run: ...
    # restore / resume as S2a specifies
    @property
    def run_id(self) -> str: ...
    def next(self) -> dict[str, Any]: ...
    def submit(self, action_id: int, response: dict[str, Any], now_ms: int) -> None: ...
    def tick(self, now_ms: int) -> bool: ...
    def wake_at(self) -> int | None: ...
    def cancel(self, reason: str, now_ms: int) -> None: ...
    @property
    def finished(self) -> bool: ...
    def trace(self) -> list[dict[str, Any]]: ...
    def take_trace(self) -> list[dict[str, Any]]: ...
    def action_records(self) -> list[dict[str, Any]]: ...
    def take_records(self) -> list[dict[str, Any]]: ...
    @property
    def taken_sha256(self) -> dict[str, str]: ...
    def run_record(self) -> dict[str, Any] | None: ...
    def snapshot(self, key: bytes | None = None) -> dict[str, Any]: ...
```

### 5.8 `grounded_agency/workflows/protocol.py` (new)

`TypedDict`s for every action and response of the schema
(`InvokeCapabilityAction`, …, `CompletedAction`, `FailedAction`,
`OutputResponse`, …, `LivenessLostResponse`), unions `Action` and
`Response`, and `RECORD_MODES = ("approvals", "actions")`. `runner.py` uses
them in its annotations (`Action = dict[str, Any]` becomes the union; host
methods keep returning plain dicts at run time).
`tests/test_host_protocol_schema.py` checks each `TypedDict`'s keys against
the schema's `properties` for that kind.

### 5.9 `grounded_agency/workflows/triggers.py` (new)

```python
def trigger_attendance(trigger: Mapping[str, Any], invoker: str | None = None) -> str
    # declared attendance, else manual/invoke(invoker, default attended)/schedule/event defaults
def next_fire(schedule: Mapping[str, Any], after_ms: int) -> int | None
    # _core.next_fire
class OverlapGate:
    def __init__(self, overlap: str | None = None) -> None   # None -> "skip"; ValueError otherwise
    in_progress: int; waiting: bool
    def fire(self) -> Literal["start", "buffered", "skipped"]
    def missed(self) -> Literal["start", "buffered", "skipped"]   # = fire()
    def ended(self) -> Literal["start", "none"]   # a run ended; "start" when a buffered one starts now
    def resumed(self) -> Literal["none"]   # a run that ended deferred was resumed: in progress again
def matches_event(trigger: Mapping[str, Any], event: Mapping[str, Any]) -> bool
class EventGate:
    def __init__(self, trigger: Mapping[str, Any], *,
                 accept: Callable[[Mapping[str, Any]], bool] | None = None,
                 seen: MutableSet[str] | None = None) -> None
    def offer(self, event: Mapping[str, Any]) -> Literal["start", "no_match", "refused", "duplicate"]
```

`OverlapGate.fire`: `in_progress == 0` → `start` (count it); `skip` →
`skipped`; `buffer_one` → `buffered` if not `waiting` (set it) else
`skipped`; `allow_all` → `start`. `ended`: decrement; if `waiting` and
`in_progress == 0` → clear `waiting`, count, `start`; else `none`.
`resumed`: increment `in_progress`; `none` (a resumed run does not consume
a buffered fire; the buffer waits until no run is in progress).

`EventGate.offer`: not `matches_event` → `no_match` (the id is not
consumed); `accept` given and false → `refused` (the host's sender policy;
the caller records the drop); `event_id` in `seen` → `duplicate`; else add
it to `seen` and `start`. `seen` defaults to an in-memory set; a host that
must deduplicate across restarts passes a persistent set-like store. An
event without a string `event_id` is `no_match` (not a canonical event).
Export both from `grounded_agency/workflows/__init__.py`.

### 5.10 `grounded_agency/workflows/runner.py`

- `Host.withdraw(self, action: Action, why: str) -> None`: default no-op.
  Docstring: the run no longer waits for this action (it timed out, or the
  run was cancelled); stop performing it; a response would be refused.
- `class HostCannotServe(Exception)`: `__init__(self, reason: str, message: str = "")`.
  `_dispatch` turns it, raised from `invoke_capability` or `await_event`,
  into `{"kind": "Error", "code": "R402", "reason": e.reason, "message": ...}`.
  The `Host` docstrings name `unsupported_capability` and `unsupported_domain`.
- `RunResult`: add `run_id: str | None = None`, `reason: str | None = None`
  (from `Failed.reason`), `checkpoint_id: str | None = None`,
  `run_record: dict[str, Any] | None = None` (`run.run_record()`, §5.19.8),
  property `cancelled` (`code == "R408"`), and a docstring note that
  `action_records` holds the records not taken with `take_records`.
- `WorkflowRunner.__init__(..., archive: Callable[[RunResult], None] | None = None)`:
  when a run the runner drives ends (`run`, `drive`, `advance` returning a
  result, `cancel`), the runner calls `archive(result)` before returning
  it, so the host keeps the run record and the records (§5.19.8). An
  exception from `archive` is raised as `RunArchiveError(RunIncomplete)`,
  which carries `run` and `result`: the state was not discarded, so the host
  can archive again. A run that is restored after it ended and driven again
  is archived again; the run record's `action_id` (the `run_id`) makes that
  idempotent for a keyed store. Docstring of `run`/`drive`: without
  `archive`, the caller keeps `result.run_record` itself.
- `run_id` (§5.19.2): `start` keeps the `uuid4().hex` default; the
  docstring says a caller-supplied `run_id` must be fresh. The runner keeps
  the `run_id`s it has started (`self._run_ids: set[str]`) and raises
  `RunStartError("run_id 'x' was already used by this runner; a run_id must
  be unique among the runs whose records or idempotency keys the host keeps
  (STANDARD §5.19.2)")` for a repeat. `restore` does not add to or check the
  set (a restored run keeps its id).
- `start(..., attendance: str | None = None, records: str = "approvals", trigger: int | None = None, event: Mapping | None = None)`:
  - With `trigger`: read `catalog[workflow]["triggers"][trigger]` (else
    `RunStartError`); `kind == "invoke"` → `RunStartError` ("an invoke
    trigger starts nested runs only"); effective attendance =
    `trigger_attendance(t)`; an explicit `attendance` that differs →
    `RunStartError` (§5.10.2: MUST apply the trigger's); `kind == "event"`:
    `event` required and offered to the trigger's `EventGate` (one per
    (workflow, trigger index), kept by the runner): `no_match` →
    `RunStartError("the event does not match the trigger")`, `duplicate` →
    `RunStartError("event 'e1' already started a run of this trigger
    (STANDARD §5.10.2)")`; on `start`, `inputs[delivers_to] = event` (an
    input already given under that name → `RunStartError`). The runner uses
    `gate.check(event)` (the decision, no side effect) before starting and
    `gate.commit(event)` once the core start succeeded, so an event whose
    run could not start is not consumed (`offer` = `check` then `commit`).
    The runner applies no sender policy (it does not see the sender); a host
    applies its own before calling `start`, or builds its own
    `EventGate(accept=…)`. Other kinds: `event` must be `None`.
  - Without `trigger`: attendance defaults to `"attended"` (as before).
- `run(...)` gains `records=`, `trigger=`, `event=` and passes them through;
  its `attendance` default also becomes `None` (the trigger's, else
  attended).
- `advance(self, run, host, *, save=None, key=None) -> Turn` (new) and
  `@dataclass(frozen=True) class Turn: result: RunResult | None; wake_at: int | None; pending: Action | None`:
  ```
  now = host.now_ms(); _check_ms(now)
  before = run.next()
  if run.tick(now):
      if before["kind"] not in TERMINAL | {"Sleep"}: host.withdraw(before, "timed out")
      save and save(run.snapshot(key))
  answered = 0
  while answered < self._max_actions:
      action = run.next()
      if terminal: return Turn(self._result(run, action), None, None)
      if action["kind"] == "Sleep": return Turn(None, run.wake_at(), action)
      response = self._dispatch(host, action)
      if response is None: return Turn(None, run.wake_at(), action)
      self._submit(run, action, response, host.now_ms()); answered += 1
      save and save(run.snapshot(key))
  raise RunIncomplete(...)
  ```
- `drive(self, run, host, *, save=None, key=None)`: loop of `advance`;
  keeps the `max_actions` and `max_polls` semantics (a `Sleep` turn counts as
  one answered action; a `None` turn as one poll of that action id);
  between turns `host.sleep_until(min(now + poll_interval_ms, turn.wake_at))`
  (for a `Sleep`, `turn.wake_at`). The hand-computed `deadline + 1` goes.
- `cancel(self, run, reason, *, now_ms=None, host=None) -> RunResult`:
  `before = run.next()`; `run.cancel(reason, now)`; `host.withdraw(before,
  "cancelled")` when a host is given and `before` was not terminal or Sleep;
  returns `_result`.
- `_result`: fills `run_id`, `reason`, `checkpoint_id`, `run_record`.

### 5.11 `grounded_agency/trust.py` (§8.4; coordinate with S6)

```python
class OverrideRefused(ValueError): ...

def manual_override(model: Mapping[str, Any], *, target: str, previous: Any, value: Any,
                    actor_identity: Mapping[str, Any] | None, anchors: Sequence[Mapping[str, Any]],
                    record: Callable[[dict[str, Any]], None], now: str | None = None) -> dict[str, Any]:
```
Reads `model["overrides"]`: refuses (`OverrideRefused`) when
`allow_manual_override` is false, or `requires_anchors` and no anchors;
builds the action record (`action_id` uuid4 hex, `timestamp`, `actor` =
identity kind or `"agent"`, `actor_identity`, `intent: "manual trust override of <target>"`,
`status: "executed"`, `details: {target, previous, value}`, `anchors`); if
`audit_required`, calls `record(rec)` and lets its exception propagate (the
caller applies the value only after `manual_override` returns). Also a
method `TrustModel.manual_override(...)` delegating with the model's loaded
data.

### 5.12 `grounded_agency/coordination/audit.py`

`CoordinationEvent.to_action_record(self, recorded_by: Mapping[str, str] | None = None) -> dict[str, Any]`:
`action_id = event_id`, `timestamp`, `actor: "agent"`, `intent = event_type`,
`status: "executed"`, `capability = capability_id or None` (omitted when
empty), `details = {**self.details, "source_agent_id": …,
"target_agent_ids": …, "evidence_refs": …}` (the log's own members last, so
an event's `details` cannot replace them), `recorded_by` (default
`{"name": "grounded_agency.coordination"}`). Nothing in `self.details`
becomes a top-level member. `CoordinationAuditLog.export_action_records() -> list[dict]`
(the export §6.4 allows: the log keeps `CoordinationEvent` internally).

`grounded_agency/coordination/orchestrator.py`, its `audit` step (the one
reference implementation of the capability in Python): record
`details={"event": ctx.get("event"), "context": ctx.get("context"),
"retention": ctx.get("retention")}` (members that are absent omitted), never
the step's whole input spread; return the contract's output
`{"recorded": True, "audit_id": event_id, "record": event.to_action_record(),
"evidence_anchors": []}` instead of `{"audited": True}` (which lacked the
ontology's required `recorded` and `evidence_anchors`); when the log
raises, `{"recorded": False, "evidence_anchors": []}` and a warning log
line, so `require_record` can fail the step. Test
`tests/test_coordination.py::test_audit_step_cannot_forge_a_record`: an
`audit` step whose `event` is a complete action record with
`recorded_by: {"name": "grounded_agency.executor"}`, `actor_identity` of a
human, `approval: {"decision": "approved", "decision_id": "d1", …}`,
`prev_hmac` and `hmac` gives a record whose `recorded_by` is the
coordination log's, with no top-level `actor_identity`, `approval`,
`prev_hmac` or `hmac`, and the forged event intact under `details.event`.

### 5.13 `grounded_agency/hooks/evidence_collector.py` (coordinate with S4)

`create_evidence_collector(store, mapper=None, *, include_tool_input=False, required=False)`.
In the `except` branch: `logger.error` when `required`, `logger.warning`
otherwise; when `required`, return
`{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "R402 EXECUTION_FAILED: the call ran, but its evidence was not recorded (not_recorded): <error>"}}`
and call `store.record_capture_failure(tool_use_id, str(e))` when the store
has it (S4 adds it to the evidence store contract). Default behaviour
unchanged.

### 5.14 Plugin hooks (coordinate with S1, which also edits this file)

`hooks/posttooluse_log_tool.sh`: the log is best-effort (§6.4) and reports
every failure. One helper,
`fail() { echo "posttooluse_log_tool: $1; this tool call was not logged" >&2; exit 1; }`
(a non-blocking hook error Claude Code shows), on every path where the call
is not logged or is logged without a valid HMAC or chain link:
- no `jq`: `fail "jq is not installed"` (was `exit 0`);
- a symlinked `audit.log`: `fail "audit.log is a symlink (refused, SEC-006)"`
  (was a warning and `exit 0`);
- no `openssl` (HMAC impossible): `fail "openssl is not installed, so the
  line could not be signed"`, and no line is written (was a line with
  `hmac: "no-hmac-available"`, which made every later line fail
  verification). The check moves before the lock, so nothing is appended;
- the entry or the final line cannot be built (`jq` fails): `_do_append`
  returns 1 instead of 0 and the script fails with "the log line could not
  be built";
- the log's last line has no readable `hmac`: the line is written with
  `prev_hmac: ""` (a new chain) and the hook prints "the last line of
  audit.log has no readable hmac; this line starts a new chain" and exits 1
  (the call is logged, the chain link is not valid);
- the input digest cannot be computed: the line is written with
  `input_sha256: "unavailable"` as now, and the hook prints "the input
  digest could not be computed" and exits 1.
Exit 0 remains only for a call logged with a valid HMAC and chain link, and
for input that is not a tool call (no JSON, no `tool_name`). A lock that
cannot be taken in time still appends without it, prints a warning and
exits 0: the line is written and signed, and a chain-order break, if one
results, is what the verifier reports. The file's header comment says so.
- The line becomes an `ActionRecord` (§6.4) with the chain fields. Field
  order (the HMAC is over the line as written, minus `hmac`, as before):
  `action_id` (`.tool_use_id` when present, else `<ts>-<pid>-<4 random hex bytes>`),
  `timestamp` (the former `ts`), `actor: "agent"`, `intent: "<tool> call"`,
  `status` (`executed` for PostToolUse, `failed` for PostToolUseFailure),
  `tool`, `call_id` (`.tool_use_id`, when present), `details`
  (`{"event": <hook event>, "skill": <on Skill calls>, "input_sha256": ...}`),
  `recorded_by` (S1's `layer` object, renamed: `name`, `version`,
  `config_sha256`, `settings`; RECONCILIATION C14), `prev_hmac`, `hmac`.
`tools/verify_audit_log.py`: accept three generations (legacy `{ts, skill,
args}`, 1.1 `{ts, event, tool, input_sha256}`, 1.2 `{action_id, timestamp,
status, tool}`), each with `prev_hmac`/`hmac`; the chain check is unchanged.
`hooks/README.md` "Audit Trail": "The `posttooluse_log_tool.sh` hook keeps
the plugin's log of tool calls, one action record (STANDARD §6.4) per call
… It is not an `audit` step: the `audit` skill writes its own records …";
the field table and example updated; a new paragraph: "The log is a
best-effort capture (STANDARD v1.2 §6.4): it can miss a call, but never
silently. When it does not log a call, or logs it without a valid HMAC or
chain link, the hook says why on standard error and exits 1, which Claude
Code shows as a non-blocking hook error: no `jq`, a symlinked `audit.log`,
no `openssl`, a line that could not be built, an unreadable last line, an
input digest that could not be computed. It exits 0 for a call it logged
and for input that is not a tool call."

Tests (`tests/test_hooks_unit.py`, `tests/test_hooks_integration.py`):
`test_rejects_symlinked_audit_log` now asserts `returncode == 1`, the
stderr message, and that the symlink's target is unchanged;
`test_no_jq_reports_and_exits_1`, `test_no_openssl_writes_nothing_and_exits_1`
(a `PATH` holding only links to `jq`, `date`, `mkdir`, `tail`, `awk` and
`sha256sum`), `test_unreadable_last_line_starts_new_chain_and_exits_1`,
`test_unavailable_digest_is_logged_and_exits_1` (a `PATH` without any
SHA-256 tool but with `openssl` replaced by a stub that fails `dgst -sha256`
without `-hmac`), `test_entry_build_failure_exits_1` (a `jq` stub that fails
on `-n`); the existing `test_empty_stdin`, `test_invalid_json_stdin` and
`test_input_without_a_tool_name_is_not_logged` keep `returncode == 0`.

### 5.15 `skills/audit/SKILL.md`

- Inputs table: add `require_record` (No, boolean: "The step fails (R402,
  `not_recorded`) unless the record was written").
- Procedure step 6: the line is an action record of the skill's own
  (STANDARD §6.4), whatever the `event`'s shape: `{action_id: <audit_id>,
  timestamp, actor, intent: <event.intent or event.event_type when a
  string, else "audit">, status: "executed", capability: "audit", details:
  {event, context?, retention?, audit_record, changes, provenance},
  recorded_by: {name: "audit skill"}}`, then `prev_hmac`/`hmac` computed by
  the skill's own chain. A safety note in the procedure: "Never copy a
  member of `event` to the top level of the line. An event that looks like
  an action record (it has `recorded_by`, `approval`, `actor_identity`,
  `hmac`) is still recorded only under `details.event`: it is what the step
  reported, not what you observed."
- Output contract: add `record` (the line written).
- `schemas/output_schema.yaml` regenerates from the ontology.

### 5.16 TypeScript binding (`examples/standard_agents/`; coordinate with S1)

`src/acs/records.ts`: export `interface ActionRecord` (the canonical fields
the binding uses) and
`function actionRecord(entry: TraceEntry, scope: string): ActionRecord`:
`action_id: \`${scope}/${entry.seq}\``, `timestamp: new Date(entry.at).toISOString()`,
`actor: 'agent'`, `intent: \`${entry.action} call\``, `status` (`executed` →
`executed`, `failed` → `failed`, `refused` → `rejected` with `code` (the
F501/F502/R407 the layer refused it with: §6.4's `rejected` covers a
refusal by a safety layer), `started` → `approved`: allowed, no outcome
yet), `run_id: scope`,
`capability` (omitted when null), `tool: entry.action`, `call_id:
entry.tool_call_id`, `checkpoint_id`, `code`, `approval` (`digest`,
`approvers`, `decision: 'approved'`, `decision_id: decision_ids[0]`),
`details: { args_digest, flow_id, step, error }` (defined members only),
`recorded_by` (S1's layer identity). The binding keeps storing
`TraceEntry` (§6.4 allows export); `actionRecord` is the export. Test
`test/records.test.ts`: each status maps, a refused entry is `rejected` with
its `code`, required members present, no `undefined` members. No trigger or
host-protocol code: the binding hosts no workflows.

### 5.17 Generators and CI

- `scripts/gen_trigger_vectors.py` (new): defines the cases of 3.7 as
  Python data; computes `next` with an independent oracle (`zoneinfo`, a
  small five-field cron matcher of its own, RFC 5545 mapping as in
  `/tmp/claude-0/-home-user-agent-capability-standard/df1990d1-4c24-56ea-adb1-a7db50a2bac3/scratchpad/s2b/fire.py`, day-level iteration); computes overlap and event decisions
  with small reference functions of its own (not `grounded_agency`'s);
  writes the four files; records `tzdata` as the IANA release (the `tzdata`
  package's `IANA_VERSION` when zoneinfo uses it, else the `# version` line
  of the system's `tzdata.zi`, else refuses to write); `--check` fails on a
  drift in any value, but not on a different `tzdata` name alone when every
  value agrees (§10.3: any release that agrees on the dates). CI step beside
  the runtime fixture check; add to the `ruff format --check` list;
  `CLAUDE.md` "Commands" gets "Regenerate the trigger vectors".
- `scripts/gen_runtime_fixtures.py`: `add(..., records=None)` writes
  `"records"` when given; helpers `cancel(reason, at=None)`,
  `wake(at)`, `tick(t, changed=None)`, `add(..., run_record=None)`;
  `FIXTURE_KEYS`' optional set gains `records` and `run_record` for
  contributed fixtures; after rendering, validate every fixture against
  `tests/conformance/runtime/schema/fixture.schema.json` with `jsonschema`
  (dev dependency).
- **Pinned-member check** (6.1a) in `scripts/gen_runtime_fixtures.py`:
  `NORMATIVE_MEMBERS`, a table keyed by action kind (and `action_records[]`,
  `deferred[]`, `run_record`) of the member names a fixture may pin, each
  with the section that defines it (the table of 6.1a). After rendering,
  every member an `expect`, `end` or `run_record` names must be in the
  table (below `outputs`, `inputs`, `shown`, `correlate`, `event`,
  `details`, `approver`, `liveness` and `actor_identity`, whose contents
  the Standard defines by reference, any member is allowed), else the
  generator fails naming the fixture and the member. A future fixture
  cannot pin something unstated without a deliberate table edit.
- `.github/workflows/ci.yml`: `python scripts/gen_trigger_vectors.py --check`.

### 5.18 Harnesses

`core/tests/runtime.rs` `play()`:
- `StartOptions.records` from `f["records"]` (default approvals).
- `fill()`: `"{{digest_upper}}"` (shared with S2a).
- Entries: `tick` → `let w = run.wake_at(); let changed = run.tick(t);`
  assert `changed == w.is_some_and(|w| t >= w)` for every tick of every
  fixture, and `changed == entry["changed"]` when given; `wake_at` →
  assert `run.wake_at() == entry["wake_at"]`; `cancel` → `run.cancel(reason,
  at.unwrap_or(now))` (must succeed); `resume` → S2a.
- `run_record`: when the fixture gives one, `run.run_record()` must match
  it (both matchers).
- Matching for the end and expectations: the EX rule (skip `message`
  except `ended.message`; `reason` inside `action_records[]` and
  `deferred[]`; `ignored`, `note` and `quorum` inside an item of a
  `violations` array under `outputs`) in a second matcher used by a new test
  `runtime_fixtures_ex_matching` (the existing strict matcher stays for the
  reference executor, which must also match its own prose).
- Replays: the existing restore-before-every-entry replay; a new **drain**
  replay that calls `take_trace()` and `take_records()` before every entry,
  accumulates them, and asserts that the accumulated trace plus the final
  `trace()` equals the plain run's trace (canonical JSON), that the
  accumulated records plus the end's `action_records` equal the plain run's
  `action_records`, that the run record's `details.records` equals the
  plain run's record count, that folding the accumulated records and trace
  events with `chain` from the empty string gives exactly the state's
  `taken_heads()` (checked after every entry, and in the final snapshot's
  state, which a keyed snapshot then authenticates), that dropping or
  editing any one accumulated item makes the fold differ, and that every
  action's `run_id` is `"run-1"`.

`core/tests/triggers.rs` (new): reads
`tests/conformance/triggers/fire_times.json` and checks
`trigger::next_fire` for every case (each `next_ms[i]` from
`after = next_ms[i-1]`), so the vectors run in cargo as in pytest; on a
mismatch it names the file's `tzdata` and chrono-tz's bundled release.

`tests/test_runner.py::test_runtime_fixture`: the same entry kinds, the
`tick`/`wake_at` property and the `run_record` check.
`tests/test_trace_kinds_doc.py::recorded`: the same entry kinds (S2a
shares; consider one helper module `tests/runtime_replay.py` used by both).

### 5.19 `grounded_agency/errors.py`

`tests/test_errors.py::test_codes_match_the_core` requires `ErrorCode` to
equal `_core.CODES`, so the three new codes go in the Python list too, in
code order: `CANCELLED = "R408"` (after S1's `SAFETY_CHECK_FAILED = "R407"`), `UNKNOWN_JOIN = "W618"` and
`GROUP_MATE_READ = "W619"` (after the last W62x before them); the member
name is the canonical name, and `ErrorCode.severity` derives the severity
from the prefix (error; warning; warning), as the core gives it. The module
docstring's "Standard (v1.1.0)" becomes "v1.2.0" (shared with the
foundation). Without this, `test_codes_match_the_core` fails as soon as
`diag.rs` gains the codes.

---

## 6. Tests and conformance fixtures

### 6.1 Runtime fixtures (generated, `tests/conformance/runtime/`)

Abbreviations as in the generator: `st`, `CP`, `POLICY`, `mutate`, `inv`,
`out`, `approve`.

| Name | Catalog / script | Pins |
|---|---|---|
| `parallel_group_list_order` | `[retrieve a (g), search b (g, join all_complete), transform c reads a, b]` | `InvokeCapability` for steps 0, 1, 2 in that order, one at a time; completes (ACS-15) |
| `parallel_group_unknown_join` | as above, `join: any_complete` on both | Every member still runs (W618 at validation; join ignored) |
| `parallel_group_member_fails` | `[retrieve a (g, failure mode on_error R402 action stop), search b (g)]`; a answers `Error R402` | Run fails R402 at step 0; no action for step 1 (abandonment) |
| `action_has_run_id` | one retrieve | `expect` includes `run_id: "run-1"`; the end too (ACS-31) |
| `wake_at_backoff` | retrieve with `retry {max 1, backoff linear}`; Error R402 → `{wake_at: 1000}`, `{tick: 999, changed: false}`, `{tick: 1000, changed: true}` | Sleep ends at `until` (ACS-34) |
| `wake_at_deadline` | retrieve `timeout: 10s` → `{wake_at: 10001}`, `{tick: 10000, changed: false}`, `{tick: 10001, changed: true}` | Time-out after the deadline |
| `wake_at_in_time_at_deadline` | same; respond `Output` with `at: 10000` | Completes: an answer at the deadline is in time |
| `wake_at_approval_expiry` | `[CP, POLICY, mutate(approval {approver human, expires 1h})]` → at `RequestApproval`: `{wake_at: 3600001}`; `{tick: 3600001, changed: true}` | F502, `expired` record (approval boundary) |
| `wake_at_none_without_expiry` | approval with no `expires` → `{wake_at: null}` | No wake-up |
| `wake_at_ignores_liveness` | `receive` wait, `timeout: 2h`, liveness `{mode: probe, interval: 10m}` → `{wake_at: 7200001}` | Liveness is not a wake-up |
| `cancel_pending_capability` | `records: actions`; `[retrieve r (retry max 3; failure mode on_error [R401, R402], action request_more_context, recovery {goto_step: r, max_loops: 2})]`; `{cancel: {reason: "operator stop", at: 5}}` | End `Failed` R408, `message` "operator stop", `step` 0; `action_records`: one `cancelled` record (capability retrieve, code R408); no retry, no loop, no further action; `run_record`: `{action_id: "run-1", status: "cancelled", code: "R408", step: 0}` (ACS-32) |
| `cancel_after_checkpoint_names_it` | `[CP, POLICY, mutate(approval)]`: checkpoint `cp1`, approve, cancel at `InvokeCapability` for mutate | `Failed` R408 with `checkpoint_id: "cp1"`; the `approved` record becomes `cancelled`; no rollback |
| `cancel_pending_approval` | cancel at `RequestApproval` | `Failed` R408; `action_records: []` (no decision, no record) |
| `cancel_deferred_run` | unattended; mutate with `when_unattended: defer_to_queue`; `expect Completed deferred` is reached → `{cancel: {reason: "queue dropped"}}` | `Failed` R408, `step: null`; the `planned` record `cancelled`; `deferred` kept |
| `cancel_nested` | parent `invoke` child `[retrieve]`; cancel during the child's `InvokeCapability` | `Failed` R408, `frame: ["w", "child"]` |
| `cancel_nested_records_actions` | the same with `records: actions` | Two `cancelled` records, root first: the parent's `invoke` step (`frame: ["w"]`, `capability: invoke`) and the child's `retrieve` (`frame: ["w", "child"]`): every frame's started step |
| `cancel_waiting_delegate` | `records: actions`; waiting `delegate` (`wait@1`, `delegation@1`); the delegation answers `Output {task_id: "t1", accepted: true}`; at the `AwaitEvent`, cancel | One `cancelled` record (capability delegate, code R408): the delegation was sent (review finding) |
| `cancel_during_backoff` | `records: actions`; retrieve with `retry {max 2, backoff linear}`; `Error R402`; at the `Sleep`, cancel | One `cancelled` record (capability retrieve): the first attempt ran; the run does not wait out the backoff |
| `cancel_pending_delay` | `records: actions`; a step with `delay: 1m` (`wait@1`); at its `Sleep`, cancel | `action_records: []`: the step had not started |
| `cancel_failure_checkpoint` | `records: actions`; retrieve with failure mode `on_error R402, action pause_and_checkpoint, recovery {goto_step: r, max_loops: 1}`; `Error R402`; at the failure mode's `CreateCheckpoint`, cancel | Records: retrieve `failed` (R402), then a `checkpoint` record `cancelled` (R408) |
| `records_actions_failure_checkpoint` | the same, the host answers `Checkpoint cp2`, then `Output` on the loop's pass | Records: retrieve `failed`; `checkpoint` `executed` with `checkpoint_id: "cp2"`; retrieve `executed` (the loop's pass) |
| `run_record_failed_no_records` | default mode; one retrieve; `Error R402` | `action_records: []`, `run_record`: `{action_id: "run-1", run_id: "run-1", intent: "run w", status: "failed", code: "R402", step: 0, details: {kind: "Failed", records: 0}}`: a failed run with no approval step still has a record (ACS-20) |
| `run_record_deferred_planned` | unattended; mutate with `when_unattended: defer_to_queue` | End `Completed` `deferred`; `run_record`: `{status: "planned", details: {outcome: "deferred", records: 1}}` |
| `response_extra_members_ignored` | retrieve with `retry {max 1}`; respond `Error {code: R402, message: "m", x_trace: "abc"}`, then `Output {value: {...}, x_meta: {"n": 1}}` | Neither response is refused; the run retries and completes (§5.19.1: unknown members ignored, as in 1.1) |
| `error_reason_outside_grammar_ignored` | retrieve; `Error {code: R402, reason: "Unsupported Domain"}` | Not refused: the next action is `Failed` R402 (the absence of `reason` on it is a unit test, since subset matching cannot assert absence) |
| `records_actions_steps` | `records: actions`; `[retrieve r, CP, POLICY, mutate(approval)]` | Four records: retrieve `executed`; checkpoint `executed` with its `checkpoint_id`; constrain `executed`; mutate `executed` with `checkpoint_id` and `approval.decision_id`; each with `run_id`, `frame`, `step`, `capability` (ACS-30); `run_record`: `{status: "executed", details: {outcome: "completed", records: 4}}` |
| `records_actions_failed_once_per_pass` | `records: actions`; retrieve with `retry {max 1}`; two `Error R402` | One `failed` record, `code: R402` |
| `records_actions_loop_new_pass` | `records: actions`; step with a recovery loop to itself (`max_loops: 1`); Error then Output | Two records: `failed` then `executed` |
| `records_actions_rollback` | `records: actions`; `[CP, POLICY, mutate (failure mode on_error R402 action rollback)]` | A `rollback` record `executed` with `checkpoint_id` and the mutate step's `step` (its `intent` is the step's `purpose`, not compared) |
| `records_actions_checkpoint_refused` | `records: actions`; `[CP, retrieve a (requires_checkpoint: true), retrieve b (requires_checkpoint: true)]`: `a` uses the checkpoint, `b` needs a new one and the host answers its `CreateCheckpoint` with `Error` | `a` `executed` with `checkpoint_id`; `b` `failed`, `code: F501`; run fails F501 |
| `records_default_unchanged` | the catalog of `records_actions_steps`, no `records` | One record (mutate), as in 1.1, with the new correlation members |
| `approval_record_decision_id` | `approval_case` approve with `decision_id: "d1"` | Record `approval.decision_id: "d1"` (ACS-37) |
| `error_reason_unsupported_domain` | retrieve with `domain: audio`; host `Error {code: R402, reason: unsupported_domain}` | `Failed` R402 with `reason: unsupported_domain` (ACS-62) |
| `error_reason_with_retry` | the same with `retry {max 1}`; first Error with reason, then Output | Completes (a reason does not stop retries) |
| `audit_require_record_fails` | `audit` with `require_record: true`; host `Output {recorded: false}` | `Failed` R402, `reason: not_recorded` (ACS-20) |
| `audit_require_record_retries` | same with `retry {max 1}`; `recorded: false` then `true` | Completes |
| `audit_recorded_false_completes` | `audit` without `require_record`; `recorded: false` | Completes (1.1 behaviour pinned) |
| `audit_recorded_false_gate` | without `require_record`, after-gate `when ${a.recorded} == false, phase after, action stop` | `Failed` R403 (the opt-in pattern) |

### 6.1a Members the runtime fixtures pin, and where the Standard defines them

Every member path that an `expect` or an `end` of the 175 fixtures on
6b3e40b pins was enumerated (script:
`/tmp/claude-0/-home-user-agent-capability-standard/df1990d1-4c24-56ea-adb1-a7db50a2bac3/scratchpad/s2b/pinned.py`, the seed of the generator's
`NORMATIVE_MEMBERS` check, 5.17). Each is defined by 1.1, by S2a, or by
this design; the rows marked **gap** were found by the audit and are closed
here by stating 1.1 behaviour.

| Pinned (count) | Defined by |
|---|---|
| every action's `kind`, `frame`, `step` (all), `run_id` (new fixtures) | §5.19.1 |
| `InvokeCapability.capability` (771), `inputs.*` (≈80) | §5.19.1 (`inputs`: the resolved bindings, §5.3–§5.4) |
| `InvokeCapability.attempt` (25), `replaces` (11) | §5.2, §5.13 |
| `InvokeCapability.deadline` (3), `AwaitEvent.deadline` (23), `RequestApproval.expires_at` (3) | **gap**: when they fall: §5.19.1 |
| `Sleep.until` (5: `retry_backoff`, `retry_linear`, `liveness_retry`, `delay_waits`; new `wake_at_backoff`) | **gap**: the backoff schedule, §5.2; the delay, §5.13 and §5.19.1 |
| `AwaitEvent.event_type`, `source_kind`, `correlate.*`, `liveness.*` | §5.13, §5.19.1 (`correlate` gains `task_id`) |
| `AwaitEvent.accept_from`, `sender_check`, `accept_trust_classes`, `delegate_principal` | §5.15, §5.17, §5.19.1 |
| `RequestApproval.approver.*`, `mode`, `shown[]`, `digest` | §5.14 (S2a states the shown array: `[inputs]` without `shows`, the `recheck` element on a re-ask) |
| `RecheckSource.source`, `compare` | §5.14, §5.19.1 (`source` is the reference as written) |
| `CreateCheckpoint.step`; `Rollback.step`, `checkpoint_id` | §5.6, §5.12 (the latest checkpoint), §5.19.1 |
| `Completed.outcome` (106), `ended.step`, `ended.message` | §5.6, §5.11, §5.14 |
| `Completed.cause` (14) | §5.11 ("the code that caused the escalation (or R404) is still recorded"), now named in §5.19.1 |
| `Completed.outputs.*` (38 fixtures) | **gap**: §5.19.1 (`outputs` = the root workflow's current stores) |
| outputs of a wait on `receive` (`data[]`, `source`, …), on `synchronize` (`synchronized`, `agreed_state`, `participants`, `sender*`), of a waiting `delegate` (`task_id`, `result.*`) | §5.13, §5.17 in part; **gap** for `receive`'s `source`/`timestamp` and `synchronize`'s members: §5.19.1 table |
| outputs of an `invoke` (`result`, `steps_executed`) | **gap**: §5.19.1 table (1.1 said only "completes with what that run stored") |
| outputs of a quorum (`compliant`, `tally.*`, `violations[].reviewer_id`) | §5.16; `violations` items: §5.19.1 table; their `ignored`/`note`/`quorum` text is not compared (§10.5) |
| `Failed.code` (69), `step` (38) | §9, §5.19.1 |
| `Failed.message` (14), `action_records[].reason` (14), `deferred[].reason` (21), `violations[].note` (1) | executor prose: not compared under EX (§10.5) |
| `action_records[].status`, `actor`, `actor_identity.*`, `always_ask`, `approval.*` | §5.14, §5.17, §6.4 |
| `deferred[].frame`, `step`, `store_as` | §5.14 |

No fixture pins a trace member outside `trace_kinds` (informative), and no
fixture changes: the gaps are closed in the text.

### 6.2 Trigger vectors (`tests/conformance/triggers/`, generated)

`fire_times.json` (the 17 cases of 3.7), `overlap.json` (8 cases, two with
`resume`), `attendance.json` (7 cases), `events.json` (5 cases, one a
redelivered event).

### 6.3 Workflow fixtures (`tests/fixtures/`, `EXPECTATIONS.json`)

| File | Expect | Pins |
|---|---|---|
| `warn_unknown_join.workflow_catalog.yaml` | valid; warnings `[W618]` | `join: any_complete` in a group, and `join: all_complete` on a step with no group (one workflow each; two W618 total, the code set is `[W618]`) |
| `warn_group_mate_read.workflow_catalog.yaml` | valid; warnings `[W619]` | a member binding `${a.data}` of a group mate |
| `pass_audit_require_record.workflow_catalog.yaml` | valid; no warnings | `require_record: true` is a known input |
| `fail_audit_require_record_type.workflow_catalog.yaml` | errors `[B203]` | `require_record: "yes"` |

### 6.4 Unit and integration tests

Rust (`core/`):
- `trigger.rs` tests (5.2).
- `exec/mod.rs`: `tick_reports_change`, `wake_at_per_action`,
  `wake_at_max_deadline_is_none`, `cancel_refuses_completed_run`,
  `cancel_twice_refused`, `cancel_deferred_then_resume_refused` (with S2a),
  `submit_after_cancel_refused`, `reason_grammar` (taken: the three
  tokens, `x-acme.audio`), `reason_outside_grammar_is_ignored`
  (`Unsupported`, `x-`, 65 characters, `foo`, `5`, `{"a": 1}`: accepted,
  no `reason` on `Failed`, `reason_ignored` in the trace),
  `response_unknown_members_ignored`, the cancel tests of 5.4 item 11,
  `take_trace_keeps_seq`, `take_records_keeps_referenced`
  (a `planned` deferral record and an `approved` in-flight record stay),
  `taken_heads_chain` (heads empty at start; after taking, equal to the
  fold of what was taken; a snapshot after taking restores with the same
  heads; editing a head in the state breaks the digest, and with a key the
  HMAC), the `run_record_*` tests of 5.3,
  `action_id_counts_taken_records`, `snapshot_v1_restores`
  (a recorded version-1 snapshot of a finished run restores and `next()`
  equals the stored terminal action), `snapshot_v1_tampered_terminal_refused`,
  `finished_snapshot_has_no_duplicate_records` (the state JSON holds each
  record once).
- `validate`: 5.5 tests; `diag.rs` code table test picks up the three codes.

Python (`tests/`):
- `test_runner.py`: fixture runner extensions; `test_advance_returns_wake_at`;
  `test_drive_uses_wake_at` (fake clock records `sleep_until` targets);
  `test_drive_saves_after_every_change` (count `save` calls = answered
  actions + changing ticks); `test_withdraw_on_timeout`;
  `test_withdraw_on_cancel`; `test_cancel_result`;
  `test_host_cannot_serve_reason`; `test_start_from_schedule_trigger_is_unattended`;
  `test_start_from_trigger_refuses_conflicting_attendance`;
  `test_start_from_event_trigger_delivers_event`;
  `test_start_from_event_trigger_refuses_mismatched_event`;
  `test_start_from_event_trigger_redelivery_refused` (the same `event_id`
  twice: the second start raises `RunStartError` and no second run exists;
  a different `event_id` starts);
  `test_event_not_consumed_when_start_fails` (bad inputs: the start fails,
  then a corrected start with the same event succeeds);
  `test_start_from_invoke_trigger_refused`;
  `test_restore_reissues_same_id_and_run_id` (ACS-31 at-least-once);
  `test_run_id_reuse_refused` (a second `start` with the same caller-given
  `run_id` raises `RunStartError`; two default starts get distinct ids;
  `restore` of a saved run is not a reuse);
  `test_run_result_has_run_record` (completed, failed without records,
  cancelled); `test_archive_called_once_per_end` (`run`, `drive`,
  `advance`, `cancel`; the archived result's `run_record.action_id` is the
  `run_id`); `test_archive_failure_keeps_run` (`archive` raises:
  `RunArchiveError` carries the live `run`, which still snapshots and can be
  archived again).
- `test_triggers.py`: `_core.next_fire` against every `fire_times.json` case
  (first `next` only, then iterating `after = previous` for the rest);
  `OverlapGate` against `overlap.json` (including `resume`);
  `trigger_attendance` against `attendance.json`; `EventGate` against
  `events.json`; `test_event_gate_policy_refuses` (`accept` false →
  `refused`, the id not consumed); `test_event_gate_persistent_seen` (a
  `seen` set shared by two gates: the second sees the duplicate); the
  generator's `--check`, and that it ignores a different `tzdata` name when
  every value agrees.
- `test_host_protocol_schema.py`: the schema is valid 2020-12; replay every
  runtime fixture and validate every action `next()` returns, every
  `respond` (after `fill`), every trace event (against `$defs.trace_event`)
  and every snapshot (against `$defs.snapshot`); validate every fixture file
  against `fixture.schema.json`; every fixture `respond` also against the
  strict copy of the responses (3.5), except the two leniency fixtures; each
  kind in the schema occurs in some fixture and vice versa; the `TypedDict`
  key check; every `run_record` a replay derives validates as an
  `ActionRecord`.
- `test_audit_records.py`: executor records (mode `actions`, a run of
  `records_actions_steps`), run records (a completed, a failed and a
  cancelled run), a hook line (run the hook with `AUDIT_HMAC_KEY` and a
  fake payload), `CoordinationEvent.to_action_record()`, the orchestrator's
  `audit` record, `trust.manual_override` records, and the audit skill's
  documented line example, each validated against `ActionRecord` converted
  from `world_state_schema.yaml` (a test helper turns `nullable` and
  `#/types/...` into JSON Schema 2020-12); `test_audit_event_cannot_forge`
  (the forged event of 5.12 through the orchestrator: `recorded_by` is the
  log's, no top-level `approval`, `actor_identity`, `prev_hmac`, `hmac`).
- `test_trust.py`: `manual_override` refuses without permission or anchors,
  records before returning, and does not return when `record` raises.
- `tests/test_hooks_unit.py` (evidence collector tests live there):
  `required=True` returns the additional context and logs at error; the
  default still swallows the failure.
- `tests/test_hooks_unit.py` and `tests/test_hooks_integration.py`: the
  failure-path tests of 5.14 (no `jq`, symlink, no `openssl`, build
  failure, unreadable last line, unavailable digest: each exit 1 with its
  stderr message); the line is an `ActionRecord` with `recorded_by`.
  `tests/test_verify_audit_log.py`: the new line shape verifies; a log
  mixing 1.1 and 1.2 lines verifies; a changed 1.2 line breaks the chain.
- `tests/test_coordination.py`: `to_action_record()` (an event `details`
  key named `source_agent_id` does not replace the log's),
  `export_action_records()`, the orchestrator's `audit` output (`recorded`,
  `record`, `evidence_anchors`), and `test_audit_step_cannot_forge_a_record`.
- `tests/test_errors.py`: unchanged; passes once 5.19 adds the codes.
- `test_approval_vectors.py` and digest vectors: unchanged by S2b.

TypeScript: `test/records.test.ts` (5.16).

---

## 7. Informative documentation changes

- `docs/guides/RUNNING_WORKFLOWS.md`:
  - Links to STANDARD v1.2.0; "The contract is §5 and the host protocol of
    §5.19".
  - "Actions and responses": the table gains `run_id` and `id` (envelope),
    `Error.reason` (`unsupported_capability`, `unsupported_domain`,
    `not_recorded`, `x-`), `Failed.reason` and `checkpoint_id`; point to
    `schemas/host_protocol.schema.json`; `HostCannotServe`.
  - New "Protocol traffic" paragraph (§5.19.6), with the example of an
    approval prompt and the run's result.
  - New "Parallel groups" bullet under "What the executor enforces":
    list order, `join`, W618/W619.
  - New "Records" subsection: modes `approvals` and `actions`, the members
    every record carries, `decision_id`, `cancelled` (by the step's state),
    failure-mode checkpoint and rollback records, `audit`
    `require_record`; the run record (§5.19.8) as every run's own record,
    failed and cancelled runs included, with `RunResult.run_record` and
    `WorkflowRunner(archive=…)`.
  - "Actions and responses": the members the executor computes and the
    outputs it composes (§5.19.1), the retry backoff schedule (now cited
    from §5.2 instead of stated only here), unknown response members
    ignored.
  - New "Host obligations" section (§5.19.4 in practice): one writer
    (a lock per run key), save after every change (`save=`), idempotency by
    (`run_id`, `id`) with a small example of a performed-responses map,
    a fresh `run_id` per run (the runner refuses a reused one),
    the runner's repeated calls while a method returns `None`,
    `Host.withdraw`, interrupted turns, and integrity: what the digest
    proves (no corruption) and what only a key proves (who wrote it), so a
    key wherever others can write the stored states.
  - New "Cancelling a run" section with `WorkflowRunner.cancel`.
  - New "Time and wake-ups": the boundaries, `wake_at()`, liveness is the
    host's.
  - New "An event-driven host" section: the recipe (restore under a
    per-run lock, `runner.advance(run, host, save=…)`, append
    `run.take_trace()` to the host's log (events carry `seq`, so a repeat
    after a crash is detectable), `take_records()` into the audit store,
    check the archive against `run.taken_sha256` when auditing, save, set a
    timer for `turn.wake_at`, treat inbound messages, approval decisions and
    timers as wake-ups; archive the run record and the records when the run
    ends), with a Mermaid sequence diagram (with `accDescr`).
  - New "Snapshot size" section: what a snapshot holds (fixed ≈0.5 kB; per
    stored step its output and the inputs it ran with; ≈0.3 kB per record,
    ≈0.6 kB with an approval; ≈0.15 kB per trace event, 3–6 per step; the
    pending action), the 1.1 measurements (175 fixtures: 1.3 kB to 41 kB,
    median 3.3 kB; trace 43 %; terminal copy median 13 %, up to 26 %), the
    1.2 change (no terminal copy) with re-measured figures from a script run
    by the implementer, and the guidance for capped stores (take the trace
    each turn; keep large values out of stores by passing references).
  - "Triggers": `start(trigger=…)` (event triggers deduplicated by
    `event_id`; the sender policy is the host's), `next_fire`,
    `OverlapGate` (with `resumed`), `EventGate`, pointing to §5.10.2.
  - "The trace": kinds table gains `run_cancelled` (`reason`); `step_failed`
    and `retry` gain `reason` when the host gave one; `seq` continues after
    `take_trace`; S2a's kinds. Keep "this section is informative" and add
    "The trace is not an audit record (STANDARD §6.4)".
  - "Driving a run yourself": `tick` returns whether it changed the run;
    `wake_at`; `cancel`; `take_trace`/`take_records`.
  - "Conformance": class EX, the fixture schema, the entry kinds, the EX
    matching rule, the trigger vectors.
- `docs/guides/ORCHESTRATION_EXTENSIONS.md` "Triggers": who evaluates;
  attendance; event triggers: the host's sender policy (`identity@1`), one
  run per `event_id`; "Schedules": fire times in the time zone with the
  clock-change rule and an example; `every` anchored at the epoch; the
  three `overlap` values as §5.10.2 defines them, resumed runs, missed fire
  times; link `next_fire`.
- `docs/guides/MODALITY_HANDLING.md` §1.3: the host answers
  `{"kind": "Error", "code": "R402", "reason": "unsupported_domain", "message": "..."}`
  (STANDARD v1.2 §5.19.7); the step fails R402 and the reason is on the
  `Failed` action and the record. Version line 1.2.0.
- `docs/GLOSSARY.md`: "Parallel Group" rewritten (not ordered; list order in
  the reference executor; `join` `all_complete` only; figure text updated);
  new entries Executor, Host, Run, Action, Audit Record, Run Record, Host
  Protocol, Wake-up Time.
- `docs/GROUNDED_AGENCY.md` §7.3 "Advanced Features" (line 592): "Steps with
  the same `parallel_group` execute concurrently" becomes "Steps with the
  same `parallel_group` are not ordered relative to each other: an executor
  may run them in any order or at the same time (the reference executor
  runs them in list order), and the group joins when all have finished
  (`[STANDARD v1.2.0 §5.2.3](../spec/STANDARD-v1.2.0.md#523-parallel-groups)`)".
- `docs/TUTORIAL.md` §4.1 "Parallel Execution": "Some steps can run
  concurrently" becomes "Steps in one `parallel_group` are not ordered
  relative to each other, so an executor may run them in any order or at
  the same time (the reference executor runs them one after another, in
  list order):"; the figure's `accDescr` "The log search and the code
  search run together in the gather_context group, which joins when both
  are complete, …" becomes "The log search and the code search form the
  gather_context group, in no fixed order; the group joins when both are
  complete, …". Exercise 2 ("searches three different sources in
  parallel") becomes "in one parallel group".
- `docs/integrations/standard_agents.md` "Running ACS workflows": the
  handler-as-host rows: `Sleep`, deadlines → `scheduleEffect(…, wake_at -
  now)`; "The run between turns" → one writer per thread (the runtime runs
  one execution per thread), save after every change; a client stop is an
  interrupted turn (restore next turn) unless the handler cancels;
  `RequestApproval` and `Completed`/`Failed` delivery is protocol traffic
  (§5.19.6); the trace via `take_trace()` into thread storage, records via
  `take_records()` within the value-size cap.
- `docs/integrations/claude_agent_sdk.md`: evidence collector `required=`.
- `hooks/README.md`, `skills/audit/SKILL.md`: 5.14, 5.15.
- `spec/SECURITY.md` §1.1: replace "Audit trail exists for all changes" with
  "An audit trail can cover every change: a run started with `records:
  actions` records every step that ran (STANDARD §6.4), every host keeps
  every run's run record (§5.19.8), and the plugin's hook logs every tool
  call it can, reporting any it cannot".
- `spec/CONFORMANCE.md`: "Executor conformance (class EX)" section (what a
  fixture holds, the entry kinds, the EX matching rule, the two replays, how
  another executor runs them, the statement); the "Runtime fixtures" bullet
  says normative for EX; "Trigger vectors" (normative) beside the approval
  vectors; the running-the-suite table gains the trigger vectors row.
- `schemas/workflow_catalog.yaml`: the nine recovery texts — replace
  "and no audit is recorded." with "and the audit step does not run: the
  run record the host keeps (STANDARD v1.2 §5.19.8) records the failure.";
  at line 1730, "are not merged and no audit is recorded;" → "are not
  merged, and the audit step does not run (the run record the host keeps,
  STANDARD v1.2 §5.19.8, records the failure);"; the same three texts in
  `examples/digital_twin_sync_loop.workflow_catalog.yaml`; vendored copies
  regenerate with `tools/sync_skill_schemas.py`.
- `CLAUDE.md`: the trigger-vector command.

No new public Markdown file: everything extends existing guides; RFC-0006
gets its page automatically.

---

## 8. Backward compatibility

| Change | Kind | Effect on a valid 1.1 workflow and run |
|---|---|---|
| §5.2.3 parallel groups, §4.3 wording | Clarification | None: the reference executor already runs groups in list order |
| W618 (`join`) | New warning (warning-first) | Valid stays valid; no repository hit |
| W619 (group-mate read) | New warning (warning-first) | Valid stays valid; no repository hit |
| §5.10.2 trigger duties, fire times, overlap | New host duties; definitions of values 1.1 named | No workflow changes; hosts that evaluated triggers differently must align (MINOR host obligation) |
| §5.19 protocol, §5.19.3 boundaries | Statement of existing behaviour | None |
| `run_id` on actions | Compatible addition | Actions gain a member; fixtures match by subset |
| `tick` returns bool | Compatible API change | Callers ignoring the result are unaffected |
| `wake_at`, `take_trace`, `take_records`, `advance` | New operations | Opt-in by the host |
| `cancel`, R408, `cancelled` status | New operation, code, enum value | Opt-in by the host; §11.4 compatible enum value |
| Terminal action derived; snapshot version 2 | Implementation | Version-1 snapshots restore; actions identical |
| `Error.reason` | Optional response member | Responses without it behave as before; a `reason` outside §5.19.7 (a 1.1 host's free text) is ignored, as 1.1 ignored the member: no response that 1.1 accepted is refused |
| Unknown response members ignored; host ignores unknown action members | Statement of 1.1 behaviour | None: the reference executor already ignored them; the schema allows them |
| Retry backoff, executor-computed members, composed outputs, `Completed.outputs` stated | Clarification (statement of 1.1 behaviour) | None: the text now says what the reference executor did; no fixture changes |
| `run_id` MUST be unique | New host duty (MINOR) | The reference runner's default (`uuid4`) already met it; a caller that reused an id on one runner now gets `RunStartError` (it was wrong before: keys collided) |
| Key required where others can change stored states | New host duty (MINOR) | Hosts with private storage unaffected; the executor's checks are unchanged |
| Run record kept by every host | New host duty (MINOR) | No workflow change; `RunResult.run_record` and `archive=` are additions |
| Event triggers: sender policy, one run per `event_id` | New host duty and permission (MINOR) | A host may now drop events it cannot authenticate; a redelivered event no longer starts a second run |
| `audit` records its event in a record of its own | Implementation behaviour (skill, orchestrator) | The step's output gains `record`; `recorded` unchanged; a record-shaped event is no longer written as if it were the implementation's own record (it was a forgery path) |
| `take_records`/`take_trace` chain heads | Implementation (state members) | Version-1 snapshots restore with empty heads |
| Cancel records by step state | Part of the new `cancel` (opt-in) | None for runs not cancelled |
| Record correlation members, `decision_id`, `code` | Compatible additions to existing records | Same records, more members |
| Record mode `actions` | Opt-in (start option) | Default `approvals` keeps the 1.1 record set |
| `audit.require_record` | Optional ontology input | Not bound: behaviour unchanged |
| `audit.record` output, descriptions | Optional output, descriptions | None |
| §6.4, §8.4 | New text; §8.4 defines existing fields | `overrides` values unchanged |
| Hook line shape; exit 1 on every unlogged or unsigned call | Plugin behaviour | Old logs still verify; the new line verifies; a symlinked log or a missing `jq`/`openssl` now shows a non-blocking hook error instead of passing silently, and no `no-hmac-available` line is written |
| Trace informative | Clarification | None |

Migration: none needed under `--strict`. W618 and W619 hit nothing in the
343 workflows of tracked YAML (`schemas/`, `schemas/workflows/`, `examples/`,
`tests/fixtures/`, `skills/*/reference/`, docs) nor in any runtime or
contributed fixture (scanned on 6b3e40b). The nine recovery texts are prose
(no validation effect). Existing runtime fixtures pass unchanged: matching
is by subset, and in mode `approvals` no record is added or removed.

---

## 9. RFC text: RFC-0006 (header, summary and Part B)

File `spec/RFC-0006-host-protocol-approval-and-runs.md`. S2a supplies Part A
under the same headings; merge each section as "Part A …" then "Part B …"
(Key decisions numbered A1… and B1…).

```markdown
# RFC-0006: Host protocol, approval and runs
**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary

Standard 1.1.0 places duties on "the host" in several sections but never
defines the protocol between an executor and its host: the actions, the
responses and the run operations existed only as the reference executor's
Rust types and a guide. This RFC brings that protocol into the Standard and
settles what depends on it.

Part A (approval, deferral and run identity) is summarised in its own
section below. Part B (host protocol, runs and audit records) adds §5.19 Host
Protocol, with a schema for every action and response
(`schemas/host_protocol.schema.json`), the time rules, the host's
obligations for saving and continuing a run, cancellation (R408), protocol
traffic, error reasons and the run record every host keeps; a conformance
class EX for executors, for which the runtime fixtures become normative once
every member they pin is stated in the text; §5.10.2, which assigns trigger
evaluation to the host and defines event acceptance, fire times, the
`every` anchor and `overlap`; §5.2.3, the run-time meaning of
`parallel_group` and `join`; §6.4, the canonical audit record, with the
executor's record mode `actions`; and §8.4, manual trust overrides. It answers findings ACS-14, ACS-15,
ACS-20, ACS-30, ACS-31, ACS-32, ACS-33, ACS-34, ACS-37, ACS-45 and ACS-62 of
the [Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
By the maintainer's decision it is Accepted and ships in Standard 1.2.0.

## Motivation

The reference executor is sans-IO: it names the next action, the host
performs it and answers. That design is what lets a run be saved, carried
across processes and replayed, and it is why a Standard Agents handler or a
queue worker can host a run. But a second executor had nothing to build
against, and a host had nothing to conform to. The action and response names
occurred in the Standard once (`AwaitEvent`); conformance covered validators
only, and the runtime fixtures were "informative for implementations that
execute workflows".

The gaps showed up as soon as a turn-based host was considered. Nothing said
that a run has one writer, when its state must be saved, or that a restored
run issues its pending action again, so a host could perform a side effect
twice without knowing it should guard against that. A run could not be
stopped from outside except by answering an action with an error, which runs
the step's retries and recovery. The host had to compute its own wake-up
time from three action kinds with two different boundaries. Snapshots grew
with every trace event and held the records twice once the run ended.
Triggers were validated but no component was assigned to evaluate them, and
`overlap`, the `every` anchor and clock changes had no defined meaning.
`parallel_group` was said to run "concurrently" while the only executor ran
members in list order, and `join` was a free string. The repository held six
shapes of audit record, `audit.event` was untyped, an audit that did not
record completed silently, and a failed run left no defined record. Whether
an approval prompt is a `send`, and where a host says that it cannot serve a
step's `domain`, were left to each binding.

## Goals

- A second executor can be built from the Standard and the schema, and
  claim a class with a normative test suite.
- A host knows its duties: one writer, save before acting, idempotency under
  a key the actions carry, what an interrupted turn means, and how to cancel.
- A turn-based host can ask a run when to wake it, and keep its saved state
  small.
- Hosts compute identical fire times, apply attendance and overlap the same
  way.
- Serial execution of a parallel group is stated to conform.
- One audit record shape set, used by the executor, safety layers, the
  `audit` capability and hosts' logs, with correlation and integrity, that
  a workflow step cannot forge.
- Every run, failed or cancelled included, leaves an audit record that
  every host keeps; no capture fails silently.
- No workflow valid under 1.1 becomes invalid, and no 1.1 run behaves
  differently unless its host opts in.

## Non-goals

- Concurrent dispatch of a parallel group's members (several pending
  actions). §5.2.3 allows it; the action shape for it is left to a later
  version.
- A transport for the protocol (HTTP, queues): bindings choose.
- A normative trace: the executor's decision log stays its own.
- A `finally` construct in the DSL for steps that run on failure: every
  host keeps the run record (§5.19.8) instead.
- A conformance class for hosts: host obligations are stated as
  requirements, but not tested by fixtures, until a second host binding
  exists.
- Trigger evaluation in the TypeScript binding, which hosts no workflows.

## Key decisions

### B1) The host protocol is a section of the Standard, with a schema

§5.19 names every action and response, the run operations (start, next,
submit, tick, wake at, cancel, save and restore, resume) and the rules a
response must follow; `schemas/host_protocol.schema.json` defines each
exactly. The schema is a supporting schema (§6.1): required of executors,
not of every implementation. It is hand-written and tested against every
action the reference executor issues and every response in the fixtures.
§5.19.1 also states the members the executor computes (`deadline`,
`expires_at`, `Sleep.until`, `correlate`), what `Completed.outputs` holds
and the outputs the executor composes for waits, `invoke` and quorums, and
§5.2 the retry backoff schedule: behaviour the reference executor had and
the 1.1 text did not state. Response members the protocol does not define
are ignored, as in 1.1, and the schema allows them; a host ignores action
members it does not know. `ActionRecord.approval.decision_id` is added.

### B2) Class EX, with normative runtime fixtures

§10.5 defines class EX: an executor that starts only validated workflows,
implements the extensions it accepts, speaks the protocol, keeps time,
saves, restores, cancels and records as the Standard says, and passes every
runtime fixture whose extensions it implements, also with a save and restore
before every entry. Fixture `trace_kinds` and executor prose (messages,
record and deferral reasons, a quorum's violation texts) are excluded. Every
other member the fixtures pin was audited against the text first, and the
fixture generator refuses a fixture that pins a member outside the audited
list. The fixture format has a schema.

### B3) Host obligations

§5.19.4: one writer; save after every change and before acting; at-least-once
delivery after a restore, with idempotency under (`run_id`, `id`); an
interrupted turn leaves the run unchanged. Integrity is worded to what each
mechanism proves: the executor detects corruption (a digest) and, given a
key, refuses a state whose MAC fails; since a digest cannot show who wrote a
state, a host whose stored states others can change MUST use a key.
§5.19.2: `run_id` MUST be unique among the runs whose records or keys the
host keeps, or (`run_id`, `id`) would collide across runs. Every action
carries `run_id`, and `tick` reports whether it changed the run.

### B4) Cancellation ends a run without recovery and without rollback

`cancel(reason, now)` ends a run (or a run that ended `deferred`) with
`Failed` R408, runs no retry, failure mode, recovery, handler or rollback,
withdraws the pending action, and sets open records to the new status
`cancelled`. In record mode `actions`, every step that had started its pass
(a checkpoint, call or wait issued for it, or a nested run started) and has
no record gets a `cancelled` one, in every frame, so a waiting delegate or a
step in its backoff is not lost; a pending failure-mode checkpoint or
rollback gets its own. The terminal action names the latest checkpoint so
the host can restore it if it wants.

### B5) Time is the host's; the run says when to wake it

§5.19.3 states that a `Sleep` ends at `until` and an action times out after
its deadline (an answer at the deadline is in time). `wake at` gives the
earliest time a tick changes the run. Liveness is the host's to watch. The
reference runner's `advance` is one turn of an event-driven host.

### B6) Saved state can shed what the host keeps

The reference executor lets a host take the trace and settled records out of
the run state, and no longer stores the terminal action's records and
outputs twice. The state keeps a SHA-256 chain head over everything taken,
so a signed state still vouches for the records the host now holds.
Normative only in one respect: an executor that offers taking MUST keep such
a commitment in the state (§5.19.4); otherwise other executors keep state
their own way.

### B7) The host evaluates triggers; fire times follow RFC 5545

§5.10.2 assigns trigger evaluation to the host, which applies the trigger's
attendance, starts one run per event it accepts under its sender policy
(§5.17 where the workflow declares `identity@1`) and at most one per
`event_id`, and starts schedule runs at fire times as `overlap` allows.
Local times map to instants by RFC 5545 §3.3.5; `every` is anchored at the
Unix epoch; `skip`, `buffer_one` and `allow_all` are defined per trigger,
a resumed run counting as in progress again; missed fire times count once.
The core exports `next_fire`, the Python package `OverlapGate` and
`EventGate`, and normative vectors are computed by an independent oracle,
pinned to the tzdata release they name or any that agrees on their dates.

### B8) Parallel groups are unordered; the protocol executor runs them in list order

§5.2.3: members are not ordered and may run in any order or concurrently; an
executor with one pending action runs them in list order. The group is
complete when every member has finished; a recovery that escalates or ends
the run abandons the rest, and one that loops continues from its target, so
members at or after it run again. `join` has one defined value,
`all_complete`; another value is W618. Reading a group mate's store is
W619.

### B9) One audit record: an action record or a canonical event

§6.4 makes `ActionRecord` and the canonical event the two audit record
shapes. `ActionRecord` gains correlation (`run_id`, `frame`, `step`,
`capability`, `tool`, `call_id`), `checkpoint_id`, `code`, `reason_code`,
`details`, `recorded_by` and the chain fields `prev_hmac` and `hmac`;
`rejected` covers a refusal by an executor or a safety layer. An
implementation writes audit records in, or exports them as, these shapes.
An executor started in record mode `actions` records every step that runs,
every failure-mode checkpoint and every rollback. The `audit` capability
records its event, whatever its shape, under `details.event` of a record of
its own, whose `recorded_by` and chain fields it sets itself, so a step
cannot forge another writer's record. The trace is not an audit record. The
audit skill, the orchestrator and the plugin hook write action records; the
coordination log and the TypeScript binding export them.

### B10) Required capture fails the step; failed runs keep their record

§6.4 separates required records (the Standard's) from best-effort capture,
gives a failed required capture a defined diagnostic (R402 with reason
`not_recorded`), and requires that a failed best-effort capture be reported
too: none fails silently. An `audit` step that binds `require_record: true`
fails when it did not record. §5.19.8: every run has a run record, an action
record derived from its terminal action, and every host keeps it with the
run's records; the reference core derives it and the runner hands it to the
host's archive. The plugin hook reports every call it does not log or
cannot sign. §8.4 defines `allow_manual_override`, `requires_anchors` and
`audit_required`.

### B11) Protocol traffic is not a `send`

§5.19.6: what a host transmits to perform an approval request, a recheck, a
wait or a terminal action is not a step, provided it carries only the
action's values; anything else is a `send` or `inquire` step.

### B12) An `Error` may say why

§5.19.7: an optional `reason` token on `Error` (`unsupported_capability`,
`unsupported_domain`, `not_recorded`, or `x-` vendor tokens), carried to the
`Failed` action and the record's `reason_code`; any other value is ignored,
as 1.1 ignored the member, so no 1.1 host's response is refused. The code
still decides what the run does.

## Backward compatibility

Part B adds no error to any workflow. W618 and W619 are new warnings; no
workflow in the repository (343 in tracked YAML) and no runtime fixture
raises either, so CI's strict validation needs no migration. The ontology
change (2.2.0) adds an optional `audit` input and output and descriptions;
`world_state_schema.yaml` 1.2.0 adds optional members and the `cancelled`
status (§11.4: compatible). A 1.1 run on the 1.2 reference executor issues
the same actions and reaches the same end; its actions gain `run_id`, its
records gain correlation members and `decision_id`, and no record is added
unless the host starts the run in record mode `actions`. Cancellation,
`wake at`, taking the trace and records, error reasons and trigger helpers
are operations a host opts into. Responses are taken as 1.1 took them:
members the protocol does not define, and a `reason` outside §5.19.7, are
ignored, never refused. Snapshots of version 1 restore. The plugin's audit
log changes its line shape; logs that mix old and new lines still verify;
the hook now reports, as a non-blocking error, the calls it could not log or
sign. The trigger duties, a unique `run_id`, a key where others can change
stored states, and the run record are new obligations on hosts, a MINOR
change; §5.2.3, §5.19.1's computed members and composed outputs, §5.2's
backoff schedule, §5.19.3 and §5.19.6 state what the reference executor
already does.

## Conformance test updates

- Runtime fixtures become normative for class EX, after an audit of every
  member they pin against the text; the generator refuses a fixture that
  pins an unlisted member. New fixtures for parallel groups, `run_id`,
  wake-up times and tick boundaries, cancellation (pending call, backoff,
  waiting delegate, delay, failure-mode checkpoint, nested runs), record
  modes, `decision_id`, error reasons (an ignored one included), unknown
  response members, run records and `require_record`; the fixture format
  schema `tests/conformance/runtime/schema/fixture.schema.json`, with
  `tick`/`changed`, `wake_at`, `cancel` and `resume` entries and the
  `records` and `run_record` members.
- Every harness checks, at every tick of every fixture, that the tick
  changed the run exactly when its time reached the wake-up time, and
  replays every fixture with the trace and records taken before every
  entry, checking the state's chain heads against what was taken.
- Trigger vectors `tests/conformance/triggers/` (fire times, overlap with
  resumed runs, attendance, event acceptance with a redelivered event),
  normative for §5.10.2 with the tzdata release they name or any that agrees
  on their dates, generated from an oracle independent of the core.
- Plugin hook tests for every failure path (exit 1 with a message).
- The host protocol schema is checked against every action, response, trace
  event and snapshot in a replay of all runtime fixtures.
- Workflow fixtures for W618 and W619 and for `require_record`.

## Alternatives considered

- **A schema generated from the Rust types.** Rejected: it would follow the
  implementation's names and nullability rather than the Standard's, and add
  a dependency; a hand-written schema tested against every fixture catches
  drift in both directions.
- **A normative trace.** Rejected: it would freeze the reference executor's
  internal log; actions, terminal actions and records carry what hosts and
  auditors need.
- **Cancelling by answering each action kind with an error.** Rejected: it
  runs retries, failure modes and recovery, and `Sleep` and
  `RequestApproval` cannot take an error at all.
- **A `cancelled` outcome of `Completed`.** Rejected in favour of `Failed`
  R408: the run did not complete.
- **Rolling back on cancel.** Rejected: a host that stops a run may not be
  able to roll back, and the workflow's rollback policy lives in failure
  modes that cancellation skips; the terminal action names the checkpoint.
- **Skipping a local time that a clock change skips, or firing at the end of
  the gap.** Rejected for RFC 5545's rule, an existing normative reference
  that keeps a schedule's spacing.
- **Anchoring `every` at the trigger's activation or the previous run.**
  Rejected: hosts would disagree; the epoch is the one anchor every host
  computes the same way.
- **Removing `join`, or making it an enum.** Rejected as breaking; one
  defined value and a warning keep 1.1 workflows valid.
- **Defining `any_complete` now.** Rejected: with one action at a time it
  could only mean "run the first member"; a race needs concurrent dispatch.
- **Typing `audit.event` as an action record or event.** Rejected as
  breaking about 25 reference audit steps; defining how any object is
  recorded is compatible.
- **Recording a record-shaped `audit` event as it is.** Rejected: a step
  could then write records claiming another writer, a human actor, an
  approval or a place in a chain. The event is kept, whatever its shape,
  under `details.event` of the implementation's own record.
- **Recording every step by default, or for 1.2 workflows only.** Rejected:
  the first changes every 1.1 run's records. The second would work
  mechanically (the executor receives a workflow's target: its
  `spec_version` and the header the start operation passes), but it asks
  the wrong party:
  the version is the author's statement, while the audit trail is the
  operator's need, and an operator must be able to record every step of a
  1.1 workflow too. The host opts in.
- **Refusing responses with members the protocol does not define, or an
  `Error` whose `reason` is outside the grammar.** Rejected: the reference
  executor accepts and ignores them today, and refusing them would stall
  1.1 hosts' runs. Ignored, as in 1.1.
- **Keeping the host's run record as its terminal action.** Rejected: a
  terminal action is not an audit record (§6.4), and the duty sat with hosts
  that save state only. The run record is an action record, and every host
  keeps it.
- **Cancellation records by the kind of the pending action.** Rejected: it
  missed a waiting delegate and a step in its backoff. By the step's state.
- **A count of taken records instead of a chain head.** Rejected: it detects
  a dropped record but not an edited one.
- **A `finally` step for failed runs.** Rejected for now in favour of the
  run record every host keeps, which covers every failure, before any audit
  step or after, and adds no executor state.
- **A new code for an unwritten record.** Rejected: R402 with a reason keeps
  the retry and `on_error` rules unchanged.
- **A message prefix for `unsupported_domain`.** Rejected: messages are
  prose.

## Open questions

1. Should a later version add concurrent dispatch (several pending actions
   with a join), and with it `any_complete` and a way to withdraw a running
   member's action?
2. Should the default record mode become `actions` in the next major
   version?
3. Should `require_record` default to true in the next major version, so an
   audit that did not record fails unless the author says otherwise?
4. Should failure modes be able to match an error `reason` (for example, to
   fall back to another domain on `unsupported_domain`)?
5. Should a host conformance class, with fixtures for trigger evaluation and
   the save-and-act order, be defined once a second host binding exists?
6. Should a schedule be able to name its own `every` anchor, or a host its
   policy for missed fire times (no catch-up)?
7. Should the audit-record chain fix one serialisation (RFC 8785) for its
   MAC, so any reader can verify any store's chain with the key?
8. How long must a host remember the `event_id`s that started runs of an
   event trigger? This version says "at most one run per `event_id`" with
   no window; a later version may bound it (for example, by the event's
   `timestamp`) once hosts report what their stores can keep.
9. Should the run record carry the chain heads of the records the host took,
   so an auditor holding only the archive can check it without the run's
   final state?
```

---

## 10. Dependencies on other workstreams

- **S2a (approval/deferral, RFC-0006 Part A).**
  - "§HP" is §5.19; the text on saving and continuing a run is §5.19.4 (one
    writer covers "MUST NOT resume the same saved state twice"); the run
    operations, `resume` and `restore(..., actor_identity)` included, are
    §5.19.2.
  - The host protocol schema carries S2a's shapes (`RequestApproval.queued_action_id`,
    `Decision.approver_identities`, approver `sender_check` and
    `accept_trust_classes`); the fixture schema admits `{"resume": …}` and
    `"{{digest_upper}}"`.
  - One `SNAPSHOT_VERSION` bump to 2 for both parts; the derived terminal
    action must include anything S2a adds to `Completed`.
  - `take_records` treats S2a's `cur.queued` and parked frames' records as
    referenced; `cancel` clears `Frame.parked`/`resume`/`pending_escalation`
    and a cancelled run is not resumable (`ResumeError::NotDeferred`).
  - S2a's in-place record updates keep the correlation members and set
    `code`/`checkpoint_id` consistently with 5.4.
  - The pinned-member audit (6.1a) relies on S2a's §5.14 statement of the
    shown array (`[inputs]` without `shows`, the `recheck` element on a
    re-ask), which `approval_shows` and `recheck_reask` pin.
  - The run record's actor is the run's actor when it ended, so after S2a's
    resume with another `actor_identity`, the resumed actor; a resumed run
    replaces its `planned` run record when it ends again.
  - One `world_state_schema.yaml` 1.2.0 bump: S2a's `approver_identities`,
    status description and `mode` descriptions beside S2b's members.
  - Harness changes in `core/tests/runtime.rs`, `tests/test_runner.py` and
    `tests/test_trace_kinds_doc.py` are merged (proposed shared helper
    `tests/runtime_replay.py`).
- **S1 (tool-calling hosts, RFC-0005).**
  - Section numbers: S1's §5.2.2, §5.18 and §10.4 come before S2b's §5.2.3,
    §5.19 and §10.5.
  - §5.18.3 must classify a tool used only to deliver protocol traffic
    (§5.19.6) as a host action, not `send`.
  - Records: S1's "names the layer and its configuration" uses the
    `ActionRecord.recorded_by` member (`name`, `version`, `config_sha256`)
    instead of `layer`; S1's adapter `call_records` and the TypeScript
    `TraceEntry` export as `ActionRecord`s (`tool`, `call_id`, `capability`,
    `checkpoint_id`, `code`, `approval`, `recorded_by`), which §6.4 now
    allows ("writes them in, or exports them as"); a refused call is status
    `rejected` with its diagnostic code in `code` (the extended `rejected`
    description covers a safety layer's refusal).
  - `hooks/posttooluse_log_tool.sh` is edited by both: S1's `layer` object
    becomes `recorded_by` in the new `ActionRecord` line; S2b adds the
    no-`jq` exit 1. `tools/verify_audit_log.py` and `hooks/README.md` are
    shared too.
  - Restoring an executor run is not an execution boundary for the
    executor's checkpoints (a save and restore must change nothing, §10.5);
    S1's boundaries apply to tool-calling scopes.
- **S4 (evidence, grounding, secrets).** The evidence store contract
  (ACS-40) gains `record_capture_failure` for the collector's `required`
  mode; secrets must not appear in `ActionRecord.details` (a run record's
  `details.message` and an `audit` record's `details.event` included),
  `Error.message`, `reason` or protocol traffic (S4's secrets rule applies
  to records and to §5.19.6). S4's `Output.evidence_seen` is a member the
  schema defines; the "unknown response members are ignored" rule covers
  only members no version defines.
- **S5 (checkpoint, rollback, send, memory).** The executor's `rollback`
  and failure-mode `checkpoint` records (mode `actions`, `intent` the step's
  `purpose`) and `checkpoint_id` on records must agree with S5's rollback
  semantics (ACS-26) and with whatever S5 says about `rolled_back`; S5's
  idempotency key builds on (`run_id`, `id`), which the now-mandatory unique
  `run_id` makes collision-free across runs; S5's reason tokens join the
  §5.19.7 table (any token not in the table an executor knows is ignored,
  not refused); §5.19.6's protocol-traffic rule must agree with S5's `send`
  destination policy (ACS-52): protocol traffic is outside it.
- **S6 (profiles, trust, versioning, dialect, packaging).** Validator
  support for `spec_version: "1.2"`; the §11.5 list gains the `audit` input
  `require_record`, which the executor itself reads, so by §11.5's criterion
  a 1.1 consumer would run it differently (W616 in a 1.0/1.1 target;
  RECONCILIATION C12); W618/W619 apply to every version; §8.4 sits in S6's trust chapter
  and `grounded_agency/trust.py` is shared; the version matrix (ACS-25)
  lists `schemas/host_protocol.schema.json`, class EX and the trigger
  vectors; the ontology 2.2.0 and `world_state_schema.yaml` 1.2.0 bumps are
  shared.
- **S3 (validator, delegation, catalogs).** W618/W619 live in
  `core/src/validate/mod.rs`, which S3 also edits; the shared
  `refs::executable_roots` helper; §9.8 location keys `ref` and `mate`; the
  nine recovery-text edits in `schemas/workflow_catalog.yaml` merge with
  S3's catalog changes.
- **Foundation.** `spec/STANDARD-v1.2.0.md` base; the three codes in
  `core/src/diag.rs` and §9; version lines.
