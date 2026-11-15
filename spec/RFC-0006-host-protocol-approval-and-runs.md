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

Part A (approval, deferral and run identity) settles what an approval request
is and how a deferred action is carried out. It states the request for a step
without an `approval` field, the exact input and form of the approval digest,
the number rule and the meaning of `in_session` and `out_of_band` in §5.14;
lets a host attest who approved, with `identity@1`, and lets a workflow that
targets 1.2 require authenticated approvers (§5.17); defines resumption of a
run that ended `deferred`, including which steps run again so that nothing
runs against stale results, and what becomes of the queued actions of runs
that cannot be resumed (new §5.14.1); and states that a run keeps its actor
while it continues, that a host cancels it at a handoff, and that only a
resumption may change it (§5.17). It answers findings ACS-10, ACS-11, ACS-12,
ACS-13, ACS-35 and ACS-44.

Part B (host protocol, runs and audit records) adds §5.19 Host Protocol, with
a schema for every action and response (`schemas/host_protocol.schema.json`),
the time rules, the host's obligations for saving and continuing a run,
cancellation (R408), protocol traffic, error reasons and the run record every
host keeps; a conformance class EX for executors, for which the runtime
fixtures become normative once every member they pin is stated in the text;
§5.10.2, which assigns trigger evaluation to the host and defines event
acceptance, fire times, the `every` anchor and `overlap`; §5.2.3, the run-time
meaning of `parallel_group` and `join`; §6.4, the canonical audit record, with
the executor's record mode `actions`; and §8.4, manual trust overrides. It
answers findings ACS-14, ACS-15, ACS-20, ACS-30, ACS-31, ACS-32, ACS-33,
ACS-34, ACS-37, ACS-45 and ACS-62.

The findings are those of the
[Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
By the maintainer's decision this RFC is Accepted and ships in Standard 1.2.0.

Each section below gives each part's text under a heading of its own.

## Motivation

### Part A: approval, deferral and run identity

A guard for a tool mapped to `mutate` or `send` had to copy the default
approval request from executor code, and an implementation that checks a
digest had to read the reference executor to learn what is hashed: the
Standard said only "the canonical JSON of the shown values", and its integer
bound did not say which numbers it meant. The two values of `mode` were
enumerated, validated and copied to records without a meaning. Approvers were
bare strings: a host that could attest who approved, as a Standard Agents
endpoint can, had nowhere to say so, the requested `role` was never checked,
and a workflow could not require an authenticated approver.
`when_unattended: defer_to_queue` left a `planned` record and ended the run,
and nothing said how that queued action is later approved and carried out, so
each host chose between running the workflow again and acting on the record
itself. Finally a saved run carried its starting actor, `restore` took no
actor, and a Standard Agents handoff could continue another agent's run under
the wrong identity.

### Part B: host protocol, runs and audit records

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

### Part A: approval, deferral and run identity

- A host and a second executor can compute every approval request and digest
  from the Standard alone, and test it against normative vectors shared with
  tool-call approval.
- A queued action is approved against the values it will act on, carried out
  once, with what it reads brought up to date, and closed on the record the
  host already holds; a queued action that can never be carried out is known
  to be abandoned.
- Approver identity is attested, counted and checked with the identity model
  the Standard already has, and a requirement for it fails closed on older
  consumers.
- No 1.1 workflow becomes invalid, and no 1.1 run behaves differently unless
  its host opts in.

### Part B: host protocol, runs and audit records

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

### Part A: approval, deferral and run identity

- How a host authenticates an approver or delivers an `out_of_band` request.
- A queue store, or a time limit on how long a deferred run stays resumable
  (Open question 1).
- Tool-call approval itself (RFC-0005 decision 5); Part A only supplies the
  record member and the vector shape it shares.
- The host protocol schema, the run snapshot format and host obligations such
  as a single writer per run and cancellation (Part B).

### Part B: host protocol, runs and audit records

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

### Part A: approval, deferral and run identity

#### A1) The default request is stated (ACS-10)

A step that requires approval and has no `approval` field is asked as if it
declared `approval: {approver: {kind: human}}`: a person, in session, shown
its resolved inputs, with no expiry and no recheck, failing unattended. A
partial field takes each omitted member's default, and `expires` runs from
the request. Reason: this is what the reference executor does, so the text
changes no run.

#### A2) The digest input is stated, and its vectors are normative (ACS-11)

The shown value is an array: the resolved `shows` values in order (null when
unresolved), or `[inputs]` without `shows`, plus
`{"recheck": {"previous", "current"}}` when asked again after a recheck. The
digest is SHA-256 over its RFC 8785 text, written in lowercase hexadecimal and
compared regardless of case. An integer, a number written without a fraction
or an exponent, may reach a magnitude of 2^53 (one beyond RFC 7493's
recommendation, because 2^53 is exact and 1.1 runs accept it) and is refused
beyond it; every other number is a binary64 value, which is why `1e+21` is a
valid shown value. Whatever reads values from JSON text refuses a member name
twice in one object, which a parsed value can no longer show.
`tests/conformance/approval/digests.json` becomes normative under §10.3;
each vector has a `kind`, `step` or `tool_call`, so the same file pins
workflow and tool-call approval.

#### A3) The modes are defined (ACS-44)

`in_session` asks whoever attends the run, in its session; `out_of_band` asks
through a separate channel whose approvers need not attend, and the decision
may outlive the session. The mode changes nothing the executor checks. A human
is still never asked in an unattended run; defer and resume instead.

#### A4) Approvers can be attested and, in 1.2 workflows, required (ACS-12)

With `identity@1`, a decision may carry `approver_identities`; two different
identities for one principal make it malformed. Approvers are counted by
principal, and an identity counts only if its `kind` is `human` for a human
approver and its `role` equals the requested one. In a workflow that targets
1.2, the approver's new `sender_check` and `accept_trust_classes` filter the
identities and make them required; in an earlier target they stay unknown
fields (W604, ignored) and W616 asks for the 1.2 declaration, so a 1.1 consumer
refuses such a workflow instead of ignoring the requirement. The record lists
the approvers that counted, with their identities
(`approval.approver_identities`), and tool-call records use the same member:
the Standard Agents binding records the endpoint caller's identity. Reason: it
reuses `agent_identity`, its vocabularies and §5.17's rule for malformed
identities, and ties a security requirement to the version declaration that
makes older consumers refuse it.

#### A5) A deferred run is resumed (ACS-13)

A run that ended `deferred` continues as the same run. Its deferred steps run
again; so does each step that ran ahead of them and that a later step running
again reads, in step order, so a re-entered `verify` reads the world after
the `mutate` before it; and so does a `checkpoint` step whose checkpoint the
resumption invalidated and that a re-entered mutation binds. A nested
deferred run continues, a run whose handler was deferred runs it last,
checkpoints are taken anew, and a re-entered step is asked afresh (of a
person when attended), naming its queued `action_id` on every request until
it goes on or its action is carried out, a re-ask after a recheck and a
retry included; the record its deferral left is updated in place with each
decision and refusal, and no other record is written for the step. A
recovery loop during the resumption runs again the steps from its target to
the step that looped, a handler among them excepted, and the resumption then
goes on: the queued steps after it keep their queued actions, a deferred
handler keeps its nested run, and nothing that ran ahead runs twice. A loop
supersedes only the queued actions of the steps it runs again that were
deferred again; a gate `end` or another escalation supersedes the queued
actions it overtakes. A queued record the resumption decides or supersedes
takes the time and actor of then. A run that
ended any other way is not resumable, and its queued actions are abandoned.
An executor refuses a state that does not keep the nested runs and which
steps ran ahead. A new run of the workflow does not touch the old run's
queue. Reason: re-running the workflow, or every step after a loop's target,
repeats effects that were not deferred, and a new record for a re-ask or a
retry would leave the queue entry the host holds closed on an action that
did not run; resuming without bringing read results up to date would verify
an action against observations taken before it.

#### A6) A run keeps its actor (ACS-35)

A host that restores a run may name the actor, and the executor refuses
another principal. At a handoff the host cancels the run (Part B) unless it
ended `deferred`, and the new agent starts its own; a deferred run may
instead be resumed under the new actor, which the trace shows, as do the
records written from then on and the queued records the resumption decides
or supersedes.

#### A7) Conformance

Runtime fixtures pin the default request, the mode in an unattended run, the
digest comparison and an unresolved `shows` value, approver identity counting
and checks (including mismatched authentication and trust class, and the 1.1
treatment of the approver fields), and resumption (attended, rejected,
unattended, a mandate step in either attendance, nested, deferred handler, a
new actor, steps that ran ahead read and unread, a bound checkpoint, a retry
and a re-ask after a recheck that continue the queued action, a loop that
goes on with the resumption and one that supersedes what it runs again, a
retry with a deferred handler, a gate `end`, a failure, a replan, the queued
action of a nested run that failed, an escalation that overtakes a deferred
handler, a nested queue that waits through two resumptions, a loop whose
range holds a deferred handler, a loop back to a step whose queued action
was carried out, the time and actor of a superseded record, and `expires`
counted from the new request). The runtime fixture format gains a `resume`
entry.

### Part B: host protocol, runs and audit records

#### B1) The host protocol is a section of the Standard, with a schema

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

#### B2) Class EX, with normative runtime fixtures

§10.5 defines class EX: an executor that starts only validated workflows,
implements the extensions it accepts, speaks the protocol, keeps time,
saves, restores, cancels and records as the Standard says, and passes every
runtime fixture whose extensions it implements, also with a save and restore
before every entry. Fixture `trace_kinds` and executor prose (messages,
record and deferral reasons, a quorum's violation texts) are excluded. Every
other member the fixtures pin was audited against the text first, and the
fixture generator refuses a fixture that pins a member outside the audited
list. The fixture format has a schema.

#### B3) Host obligations

§5.19.4: one writer; save after every change and before acting; at-least-once
delivery after a restore, with idempotency under (`run_id`, `id`); an
interrupted turn leaves the run unchanged. Integrity is worded to what each
mechanism proves: the executor detects corruption (a digest) and, given a
key, refuses a state whose MAC fails; since a digest cannot show who wrote a
state, a host whose stored states others can change MUST use a key.
§5.19.2: `run_id` MUST be unique among the runs whose records or keys the
host keeps, or (`run_id`, `id`) would collide across runs. Every action
carries `run_id`, and `tick` reports whether it changed the run.

#### B4) Cancellation ends a run without recovery and without rollback

`cancel(reason, now)` ends a run (or a run that ended `deferred`) with
`Failed` R408, runs no retry, failure mode, recovery, handler or rollback,
withdraws the pending action, and sets open records to the new status
`cancelled`. In record mode `actions`, every step that had started its pass
(a checkpoint, call or wait issued for it, a nested run started, or a quorum
evaluated) and has
no record gets a `cancelled` one, in every frame, so a waiting delegate or a
step in its backoff is not lost; a pending failure-mode checkpoint or
rollback gets its own. The terminal action names the latest checkpoint so
the host can restore it if it wants.

#### B5) Time is the host's; the run says when to wake it

§5.19.3 states that a `Sleep` ends at `until` and an action times out after
its deadline (an answer at the deadline is in time). `wake at` gives the
earliest time a tick changes the run. Liveness is the host's to watch. The
reference runner's `advance` is one turn of an event-driven host.

#### B6) Saved state can shed what the host keeps

The reference executor lets a host take the trace and settled records out of
the run state, and no longer stores the terminal action's records and
outputs twice. The state keeps a SHA-256 chain head over everything taken,
so a signed state still vouches for the records the host now holds.
Normative only in one respect: an executor that offers taking MUST keep such
a commitment in the state (§5.19.4); otherwise other executors keep state
their own way.

#### B7) The host evaluates triggers; fire times follow RFC 5545

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

#### B8) Parallel groups are unordered; the protocol executor runs them in list order

§5.2.3: members are not ordered and may run in any order or concurrently; an
executor with one pending action runs them in list order. The group is
complete when every member has finished; a recovery that escalates or ends
the run abandons the rest, and one that loops continues from its target, so
members at or after it run again. `join` has one defined value,
`all_complete`; another value is W618. Reading a group mate's store is
W619.

#### B9) One audit record: an action record or a canonical event

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

#### B10) Required capture fails the step; failed runs keep their record

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

#### B11) Protocol traffic is not a `send`

§5.19.6: what a host transmits to perform an approval request, a recheck, a
wait or a terminal action is not a step, provided it carries only the
action's values; anything else is a `send` or `inquire` step.

#### B12) An `Error` may say why

§5.19.7: an optional `reason` token on `Error` (`unsupported_capability`,
`unsupported_domain`, `not_recorded`, or `x-` vendor tokens), carried to the
`Failed` action and the record's `reason_code`; any other value is ignored,
as 1.1 ignored the member, so no 1.1 host's response is refused. The code
still decides what the run does.


## Backward compatibility

### Part A: approval, deferral and run identity

A1, A2 and A3 state what 1.1 executors do and change no run; they apply to
1.0, 1.1 and 1.2 workflows as clarifications. A4 is opt-in: identities are
read only with `identity@1` and only when a host sends them; the two new
approver fields take effect only in a workflow that declares a 1.2 target,
and in a 1.0 or 1.1 target they keep exactly their 1.1 treatment (W604,
ignored), with W616 as a warning. The canonical schema change is one optional
member and descriptions (§11.4, compatible). A5 is a new host operation: a
run that is never resumed behaves as in 1.1, and its first-run records,
actions and deferral list are unchanged; the statement that the queued
actions of other runs are abandoned describes what 1.1 executors already do;
the executor's saved state gains optional members, left out while they
have their defaults, so the state of a run that never deferred is unchanged;
a state with deferrals that an earlier executor saved still restores, and
cannot be resumed, which no earlier executor offered. A6 adds an optional argument to restore and a host
rule that uses Part B's opt-in cancel. No warning or error is added for any
existing catalog, so none needs migrating.

### Part B: host protocol, runs and audit records

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

### Part A: approval, deferral and run identity

- `tests/conformance/approval/digests.json`: status normative, Standard
  1.2.0, `kind` on every vector, a vector for an unresolved `shows`
  reference, the `numbers` vector's note on `1e+21` (and RFC-0005's
  `tool_call` vectors).
- Runtime fixtures: `approval_defaults_partial`,
  `approval_out_of_band_unattended`, `approval_digest_any_case`,
  `approval_shows_unresolved`, ten `approver_*` fixtures and twenty-seven
  `resume_*` fixtures; the `resume` script entry and the `{{digest_upper}}`
  placeholder in every replayer.
- Validator fixtures for the approver fields (pass, V106, S303 in 1.2
  targets; W604 and W616 in a 1.1 target).
- Unit tests for resumption errors (including a state an earlier executor
  saved), the restore
  actor check, malformed and contradictory approver identities, version-1
  snapshots and the integer-literal rule; Python tests for a failed run's
  abandoned queue and the "superseded" reasons; a TypeScript test for
  approver identities on tool-call records.

### Part B: host protocol, runs and audit records

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

### Part A: approval, deferral and run identity

- **A queued action is carried out by a new attended run** (ACS-13). Simplest,
  but every step that was not deferred runs again, a report sent under a
  mandate is sent twice, and the `planned` record never closes.
- **Resume with the decisions passed in.** A host can answer the resumed
  request at once with a decision it collected out of band; the digest check
  makes that safe, so the extra argument adds nothing.
- **Keep the outputs of steps that ran ahead.** A re-entered `verify` would
  check observations taken before the `mutate` it verifies.
- **Re-run every step that ran ahead.** Repeats records (`audit`, `persist`)
  that no re-entered step needs.
- **Re-run a step just before its first reader.** Changes its order relative
  to the other queued actions compared with a run that never deferred.
- **Re-run a checkpoint step for any reader.** A `rollback` that binds it
  would return to a later restore point than in an unbroken run.
- **Restart a nested deferred run instead of continuing it**, or resume a
  state an earlier executor saved by guessing what it did not keep. Repeats the nested run's
  effects, or verifies stale data.
- **A new record that points back to the queued one**, for the first
  decision or for a re-ask or a retry. Needs a new record field and leaves
  the host two records for one action.
- **Return a recovery loop during a resumption to normal flow.** Every step
  after the loop's target runs again, so an `after_deferral: run` step, or a
  report sent under a mandate, that ran ahead acts twice.
- **Close a failed run's queued records at its end, or let cancel reach
  ended runs.** The first changes the records 1.1 runs leave; the second
  replaces the run's own failure code with R408.
- **Let an unattended run ask an `out_of_band` human** (ACS-44). Changes what
  1.1 catalogs do; deferral and resumption already give it.
- **Approver fields under `identity@1` in any target.** Makes 1.1-valid
  workflows invalid and lets a 1.1 consumer ignore the requirement.
- **A new extension, `approver_identity@1`, or `identity@2`** (ACS-12). The
  version declaration already keeps a 1.1 consumer from running a 1.2
  workflow; a second name would split the identity rules.
- **Resolve contradictory identities by order, or count an identity without a
  `role` toward a requested role.** Both fail open.
- **Tighten integers to ±(2^53 − 1), or bound numbers by value** (ACS-11).
  The first makes 1.1 runs that hold 2^53 fail; the second makes the
  normative `numbers` vector non-conformant.
- **Record, rather than refuse, a change of actor on restore** (ACS-35). A
  restore continues the same execution; a change there is the handoff bug.

### Part B: host protocol, runs and audit records

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

### Part A: approval, deferral and run identity

1. Should a queued action lapse when its run is not resumed within a bound
   (a queue expiry), given that `expires` runs from the resumed request?
2. Should naming the actor on restore become a MUST in the next major
   version?
3. Should an identity without `authenticated_by` count for a `human` approver
   when the workflow sets no `sender_check`?
4. Should a resumption refresh the inputs of a nested run it continues, such
   as a checkpoint id the calling workflow passed in? The nested step gets a
   new checkpoint from the host, but its input keeps the old id; today the
   advice is to take the checkpoint inside the workflow that mutates.
5. Should the runtime fixture format express a refused response, so that a
   malformed decision (contradictory approver identities) is pinned by a
   fixture rather than by unit tests?

### Part B: host protocol, runs and audit records

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
