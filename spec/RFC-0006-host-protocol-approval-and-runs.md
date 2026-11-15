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

## Non-goals

### Part A: approval, deferral and run identity

- How a host authenticates an approver or delivers an `out_of_band` request.
- A queue store, or a time limit on how long a deferred run stays resumable
  (Open question 1).
- Tool-call approval itself (RFC-0005 decision 5); Part A only supplies the
  record member and the vector shape it shares.
- The host protocol schema, the run snapshot format and host obligations such
  as a single writer per run and cancellation (Part B).

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
valid shown value. `tests/conformance/approval/digests.json` becomes normative
under §10.3; each vector has a `kind`, `step` or `tool_call`, so the same file
pins workflow and tool-call approval.

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
checkpoints are taken anew, a re-entered step is asked afresh (of a person
when attended) with its queued `action_id`, and its `planned` record is
updated in place. A loop, a gate `end` or another escalation during the
resumption supersedes what it overtakes. A run that ended any other way is
not resumable, and its queued actions are abandoned. An executor refuses a
state that does not keep the nested runs and which steps ran ahead. A new run
of the workflow does not touch the old run's queue. Reason: re-running the
workflow repeats every effect that was not deferred and never closes the
queued record, and resuming without bringing read results up to date would
verify an action against observations taken before it.

#### A6) A run keeps its actor (ACS-35)

A host that restores a run may name the actor, and the executor refuses
another principal. At a handoff the host cancels the run (Part B) unless it
ended `deferred`, and the new agent starts its own; a deferred run may
instead be resumed under the new actor, which the trace and later records
show.

#### A7) Conformance

Runtime fixtures pin the default request, the mode in an unattended run, the
digest comparison and an unresolved `shows` value, approver identity counting
and checks (including mismatched authentication and trust class, and the 1.1
treatment of the approver fields), and resumption (attended, rejected,
unattended, a mandate step in either attendance, nested, deferred handler, a
new actor, steps that ran ahead read and unread, a bound checkpoint, a loop, a
loop with a deferred handler, a gate `end`, a failure, a nested queue that
waits through two resumptions). The runtime fixture
format gains a `resume` entry.

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

## Conformance test updates

### Part A: approval, deferral and run identity

- `tests/conformance/approval/digests.json`: status normative, Standard
  1.2.0, `kind` on every vector, a vector for an unresolved `shows`
  reference, the `numbers` vector's note on `1e+21` (and RFC-0005's
  `tool_call` vectors).
- Runtime fixtures: `approval_defaults_partial`,
  `approval_out_of_band_unattended`, `approval_digest_any_case`,
  `approval_shows_unresolved`, ten `approver_*` fixtures and seventeen
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
- **A new record that points back to the queued one.** Needs a new record
  field and leaves the host two records for one action.
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
