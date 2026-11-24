# S2a design: approval, deferral and run identity (ACS 1.2.0)

> **Reconciled (cross-stream pass).** S2a adds no code; S2b's `CANCELLED`,
> which this file cites, is R408 (C2). Edited here: every "§HP" is a §5.19 subsection (C1); the
> merged `ActionRecord.status` description keeps this design's last
> sentence (C13); the binding's copy of the digest vectors is deleted and
> the `kind` member lands in the foundation (C36). `exec::read_json` lands in
> the foundation because S6's WebAssembly entry points use it (C23). Merge
> order: second, first of the chain S2a → S2b → S4 (C35). See
> RECONCILIATION.md and FOUNDATION.md.

Workstream S2a. Findings: ACS-10, ACS-11, ACS-12, ACS-13, ACS-35, ACS-44.
RFC: RFC-0006 (host protocol, approval and runs), shared with S2b; S2a writes
the approval part (Part A, section 9 below).

Base: main 6b3e40b. Standard 1.1.0 stays unchanged; everything normative
below is text for `spec/STANDARD-v1.2.0.md`.

Revision 2 answers the adversarial review of revision 1; section 0.1 lists
each required change and what this revision does about it.

## 0. Summary

| Finding | Decision | Kind of change (GOVERNANCE, task rules) |
|---|---|---|
| ACS-10 default request | §5.14 states the request for a step with no `approval` field (or a partial one): `{kind: human}`, `in_session`, `[resolved inputs]`, no expiry; `expires` runs from the request | Clarification of what 1.1 executors already do; no workflow or run changes |
| ACS-11 digest input | §5.14 states the shown array (shows in order, null for an unresolved reference, `[inputs]` without `shows`, the `recheck` element on a re-ask), RFC 8785, lowercase hex, case-insensitive comparison; the integer bound stated as applied (a number written without fraction or exponent, magnitude ≤ 2^53; other numbers binary64); §10.3 makes `tests/conformance/approval/digests.json` normative, with a `kind` per vector (`step`, or S1's `tool_call`) | Clarification + conformance (no behaviour change; the reference executor already passes every vector) |
| ACS-44 `mode` | §5.14 defines `in_session` and `out_of_band`; keeps "a human is never asked in an unattended run, in either mode"; points unattended out-of-band approval at `defer_to_queue` + resumption | Clarification (no behaviour change); descriptions added to two schemas |
| ACS-12 approver identity | With `identity@1`, a decision may carry `approver_identities` (agent_identity list; two different identities for one principal make it malformed); approvers counted by principal; an identity must match `kind: human` and `role`; the record lists the counted approvers and their identities. In a workflow that **targets 1.2**, the approver may declare `sender_check` / `accept_trust_classes`, which require attested identities. Tool-call approval records carry `approver_identities` too; the TypeScript binding fills them from the authenticated `ThreadUser` | `approver_identities`: opt-in by host + extension. Approver fields: opt-in by `spec_version` 1.2 (a 1.1 consumer refuses with V109, so the requirement fails closed); in a 1.0/1.1 target they stay unknown fields (W604, ignored), plus S6's W616 |
| ACS-13 deferred actions | New §5.14.1: a run that ended `deferred` is **resumed** as the same run: its deferred steps run again, with the steps that ran ahead of them that they read, and a checkpoint step whose invalidated checkpoint a re-entered mutation binds; nested deferred runs continue; a re-entered queued step is asked afresh (of a person when attended) naming `queued_action_id`; its `planned` record is updated in place. A run that ended any other way is not resumable and its queued actions are abandoned. States that lack what resumption needs (every state saved before 1.2) are refused | New executor operation, opt-in by the host (`Run.resume`); a 1.1 run is unchanged until a host resumes it |
| ACS-35 actor continuity | §5.17: a run keeps its actor while it continues; `restore` may name the actor and the executor then refuses a mismatch; at a handoff the host cancels the run (S2b §5.19.5) unless it ended `deferred`, which may be resumed under the new actor (recorded) or cancelled | New optional restore argument (opt-in), new resume argument; host obligation that uses S2b's opt-in cancel; no workflow change |

No ontology change. No new diagnostic code. No new warning, so no repository
catalog needs migrating.

### 0.1 Review response (revision 2)

| Review item | Done |
|---|---|
| 1. Resumption ran deferred steps against stale outputs | Accepted. §5.14.1 item 2 now re-runs, in step order, every step that **ran ahead** of a deferral (began after a step of its frame was deferred and was not deferred) whose store a later re-run or re-entered step reads; handlers and `after_deferral: run` steps keep their outputs. A `checkpoint` step is re-run when the resumption invalidated its checkpoint and a re-entered step that requires a checkpoint binds its store (the §12.5 Safe Mutation pattern). Refinement, with reasons: (a) the re-run step goes at its own place in step order, not "just before its first reader", so it runs between the same queued actions as in a run that never deferred; (b) the checkpoint re-run is limited to readers that require a checkpoint and to checkpoints the resumption invalidated, because a `rollback` that binds the id must still return to the original restore point, and a checkpoint an earlier step already used was stale in an unbroken run too. Implemented in `reopen`, which now computes the resume list from `Step.reads` and a new `Frame.ahead`. Fixtures `resume_reruns_read_ahead`, `resume_keeps_unread_ahead`, `resume_reruns_bound_checkpoint`; guides state the rule |
| 2. Approver fields made 1.1-valid workflows invalid and failed open | Accepted. The fields take effect only in a workflow that targets 1.2; in a 1.0/1.1 target they stay unknown fields (W604, ignored by validator and executor) and S6's W616 asks for `spec_version: "1.2"`. V106/S303 only in 1.2 targets. Validator fixture `warn_approver_identity_1_1`, runtime fixture `approver_fields_ignored_1_1` |
| 3. Version-1 snapshots restarted nested runs on resume | Accepted, broadened: `Run::resume` refuses (`ResumeError::NotKept`) any state that does not keep the nested run of a deferred `invoke` step **or** which steps ran ahead (item 1 needs it). Every version-1 state with deferrals is refused; it can be cancelled. Rust unit test; guide sentence replaced |
| 4. Integer bound contradicted the `numbers` vector | Accepted. §5.14 states the bound for numbers written without fraction or exponent; others are binary64; the vector's `about`, Appendix D and RFC A2 say why `1e+21` is valid. New `exec::read_json` makes the rule hold for JSON text the reference implementation reads (serde_json would otherwise read an over-long integer literal as binary64) |
| 5. §10.3 text did not fit S1's `tool_call` vectors | Accepted. Every vector has `kind` (`step` or `tool_call`); canonical text and digest are normative for all, the executor `shown` requirement for `step` vectors, and S1's layer requirement for `tool_call` vectors. `render_digests()` and `tests/test_approval_vectors.py` branch on it; shape in depends_on for S1 |
| 6. Runs that fail, escalate or replan after deferring | Accepted, option A: their queued actions are never carried out; records stay `planned` in the terminal action, the host treats them as abandoned and may start a new run. Extending cancel was rejected (it would replace the run's own failure code with R408). Open question 3 removed; Python test added |
| 7. Missing fixtures; `undefer_from` bug; exact-reason pins | Accepted. Fixtures `resume_failure_keeps_queue`, `resume_loop_supersedes`, `resume_deferred_handler_loop`, `approver_sender_check_mismatch`, `approver_trust_class_mismatch`. `undefer_from` and `escalate` now settle the remaining resume entries and the pending handler (section 5.2 items 11-12). Fixtures pin `status: rejected`; the "superseded" reasons are asserted in `tests/test_runner.py` |
| 8. Contradictory approver identities counted by order | Accepted. Two different identities for one principal make the decision malformed (`SubmitError::Malformed`); identical repeats collapse. The record lists only the counted approvers and their identities; the others appear in the refusal reason |
| 9. Handoff rule did not say what the host does | Accepted. §5.17: the host MUST NOT continue a run under the agent that took over; it cancels it (S2b §5.19.5) unless it ended `deferred`, which may be resumed under the new actor or cancelled. Mirrored in the integration guide, `RUNNING_WORKFLOWS.md` and the interop mapping |
| 10. `queued_action_id` text and code disagreed | Accepted. Every request for a re-entered queued step carries it, in either attendance; fixture `resume_unattended_mandate` pins it |
| 11. The cited host still recorded bare strings | Accepted. Tool-call approval records may carry `approval.approver_identities`; the TypeScript binding fills them per the interop identity map (principal `sa-user:<id>`, `kind: human` as the deployment's assertion, `role` when the caller holds the requested one, `authenticated_by: x-acs.sa-caller`), and its `approvers` become those principals. Vitest case added; Open question 2 removed |

---

## 1. Per finding: decision, rationale, how it fixes the finding

### ACS-10 — the request for a step with no `approval` field

**Decision.** State in §5.14 that a step whose effective `requires_approval`
is true and that declares no `approval` field is asked exactly as if it
declared `approval: {approver: {kind: human}}`: approver `{kind: human}` (one
approver, no role), mode `in_session`, shown values `[<resolved inputs>]`, no
`expires_at`, no recheck, `when_unattended: fail`. A partial `approval` field
takes the default of each member it omits. State that `expires` is measured
from the request (`expires_at` = request time + `expires`), which is what the
executor does (machine.rs 737-741) and what the TypeScript binding mirrors.

**Options considered.** (a) state the executor's behaviour; (b) make the
default request depend on the capability (e.g. `send` defaults to
`out_of_band`). (a) chosen: it is what every 1.1 run already does, so it is a
clarification with no behavioural change, and a guard for tools mapped to
these capabilities can now read the default from the Standard instead of
copying it from code.

**How it fixes the finding.** The Standard states approver, mode, shown
values, expiry and unattended plan for the no-field case; the fixture
`checkpoint_per_mutation` (already pinning approver, mode, shown, null
expiry) becomes a normative pin through S2b's executor class, and a new
fixture `approval_defaults_partial` pins the per-member defaults of a
partial field.

### ACS-11 — what the digest is computed over

**Decision.** State in §5.14:

1. The shown value is a JSON array. With `shows`: one element per reference,
   in order, each the referenced value when the request is made (`null` when
   the reference resolves to nothing; an array value is one element, never
   spliced). Without `shows`: `[<resolved inputs>]`, the inputs the capability
   is invoked with (`{}` when it binds none). Asked again after a recheck saw
   its source change: the same array plus one final element
   `{"recheck": {"previous": P, "current": C}}` (P: the source value the
   earlier decision was bound to; C: the value the recheck read).
2. Digest = SHA-256 of the UTF-8 bytes of the RFC 8785 canonical JSON of that
   array, written as 64 lowercase hexadecimal digits; a decision's digest is
   compared without regard to the case of hex letters (canonical.rs
   `same_digest`, unchanged).
3. The number rule, stated as the executor applies it: an **integer**, a
   number written without a fraction or an exponent, has a magnitude of at
   most 2^53, and an executor refuses one outside it (R402 for a step's
   resolved inputs; a response that carries one is malformed). Every other
   number is a finite binary64 value, written as RFC 8785 writes it. That is
   why `1e+21` in the `numbers` vector is valid. A host that parses JSON text
   keeps integers as integers: a parser that would read an over-long integer
   literal as binary64 refuses it instead. The reference implementation gets
   `exec::read_json`, which does this for JSON text it reads, because
   serde_json reads an integer literal too long for 64 bits as binary64.
4. §10.3 names `tests/conformance/approval/digests.json` as **normative**.
   Every vector gains `kind`: `step` (an approval request of a workflow step:
   `approval`, `inputs` without `shows`) or `tool_call` (S1: a tool call's
   approval, §5.18.7: `call`, with `shown == [call]`). The canonical text and
   digest are normative for every vector; an executor must reproduce `shown`
   for each `step` vector, and a layer for each `tool_call` vector.

**Options considered for the integer bound.** (a) keep the inclusive 2^53 and
state it exactly; (b) tighten to ±(2^53 − 1); (c) bound numbers by value, so
`1e+21` would be refused. (b) would make the executor refuse values a 1.1 run
accepts (2^53 in a run's data would now fail R402 / be refused). (c) would make
the normative `numbers` vector non-conformant and change what the executor
accepts. 2^53 is exactly representable in binary64, so every implementation
canonicalizes it to the same text. (a) chosen, with the rule phrased by how a
number is written, which is exactly what the executor checks (`ijson` tests
numbers that parse as integers).

**Options considered for the vector discriminator.** (a) a `kind` member;
(b) "a vector with an `approval` member describes a step". (b) leaves the
`no_approval_field` vector (`approval: null`) ambiguous between "a step with
no field" and "not a step". (a) chosen.

**How it fixes the finding.** Every input of the digest (the array shape, the
default without `shows`, the re-ask element, the encoding, the comparison, the
number rule) is in the Standard, and the vectors that pin it are normative and
cited in §10.3, in a form both step and tool-call approval can use.

### ACS-44 — the meaning of `in_session` and `out_of_band`

**Decision.** Define in §5.14:

- `in_session`: the request goes to the party attending the run, through the
  session the run is attended in (the host's permission prompt, the
  conversation), and is answered while the run waits in that session.
- `out_of_band`: the request goes through a channel separate from the run's
  session (ticket, message to an approver group, review queue); its approvers
  need not attend the run, and the decision may arrive after the session that
  asked has ended, so the host keeps the run's state while it waits.

The mode changes neither the shown values, the digest, nor which decisions are
valid; a host that cannot ask in the declared mode SHOULD answer
`unavailable`. The unattended question is answered explicitly: a `human`
approver is never asked in an unattended run, in either mode (the 1.1 rule,
unchanged); the way to get an unattended run's action approved out of band is
`when_unattended: defer_to_queue` followed by resumption (§5.14.1, ACS-13),
whose request carries the declared mode.

**Options considered.** (a) definitions only, unattended rule unchanged;
(b) let an unattended run put an `out_of_band` request to a human instead of
applying `when_unattended`. (b) changes what 1.1 catalogs do (F502, skip or
defer becomes a pending request), so it could only be opt-in, and resumption
already gives the same result without a second mechanism. (a) chosen.

**How it fixes the finding.** Both values have a meaning; the unattended
question is answered in the Standard; both enums get descriptions
(`world_state_schema.yaml`, `workflow_catalog.schema.json`); a fixture pins
that `out_of_band` does not change the unattended rule.

### ACS-12 — approver identity, role and authentication

**Decision.** Reuse `identity@1` and `agent_identity`:

1. With `identity@1` declared, a `Decision` may carry `approver_identities`,
   a list of `agent_identity`. Each element MUST be an `agent_identity`; two
   elements with one principal MUST be identical (an identical repeat counts
   once); when `approvers` is also non-empty, the set of `approvers` MUST
   equal the set of the identities' principals. Otherwise the response is
   malformed and changes nothing (the rule §5.17 already has for an event's
   identity). Without `identity@1` the member is ignored (as §5.17 ignores
   reported identities).
2. Approvers are then counted by **principal**. An identity counts toward
   `min_approvers` only if it meets the request: for a `human` approver its
   `kind` is `human`; when the request names a `role`, its `role` equals it;
   in a workflow that targets 1.2, when the approver declares `sender_check`,
   its `authenticated_by` is listed, and when it declares
   `accept_trust_classes`, its `trust_class` is listed.
3. New optional approver fields `sender_check` and `accept_trust_classes`,
   effective **only in a workflow that targets 1.2** (§11.5: `spec_version`
   1.2 or a 1.2 header). There they need `identity@1` (V106) and are each a
   non-empty literal list of values from the §5.17 vocabularies (S303), and
   they make attested identities required: a decision without identities
   counts no approvers (F502). In a workflow that targets 1.0 or 1.1 they are
   what they are in 1.1, unknown fields (W604, ignored by validator and
   executor), and S6's W616 tells the author to declare 1.2.
4. The record lists the **counted** approvers: their principals in
   `approval.approvers` and their identities in the new optional member
   `approval.approver_identities` of the canonical `ActionRecord`; a refused
   decision's `reason` names the others and why they did not count.
5. Without identities, 1.1 counting stands: distinct strings, and the host
   vouches for the role (SHOULD accept only approvers holding it).
6. Tool-call approval (S1, §5.18.7/§5.18.8) uses the same member: a layer that
   can attest its approvers records `approval.approver_identities`, with
   `approvers` their principals. The TypeScript binding, the host the finding
   cites, fills them from the authenticated `ThreadUser` per the interop
   identity map (`endpoint_caller`): principal `sa-user:<id>`, `kind: human`
   as the deployment's assertion, `role` when the caller holds the requested
   one, `authenticated_by: x-acs.sa-caller`, `trust_class: owner` when the
   caller is the thread's owner.

The `kind: human` check is a consistency check on the host's own attestation
(it rejects a host that says it routed the approval to an agent); the Standard
does not promise that the party is a person, as §5.17 already says of
delegation identities.

**Options considered.** (a) the proposed change (identities, principal count,
role check when both present); (b) (a) plus workflow-side requirements;
(c) a new extension (`approver_identity@1`) for the new fields; (d) `identity@2`;
(e) (b) with the fields effective in any target that declares `identity@1`
(revision 1). (b) chosen because the finding's summary also says "a workflow
cannot require an authenticated approver"; the role rule is strict (an
identity that does not attest the requested role does not count) because a
fail-open check would let an unattested party satisfy a role requirement.
(e) rejected: a 1.1 workflow with `approval@1` and `approver.sender_check`
validates today (W604, ignored) and would become V106; and a 1.1 consumer that
implements `identity@1` would accept the workflow and silently ignore the
authentication requirement, failing open. Tying the fields to a 1.2 target
makes a 1.1 consumer refuse the workflow (V109), which is the same treatment S3
gives `continues`. (c)/(d) rejected: the version declaration already gives the
must-understand protection, and a second extension name would split identity
semantics across two declarations. For contradictory identities: resolving by
order (revision 1) is fail-open when the favourable one comes first and adds
an ordering rule; rejecting the decision as malformed is what §5.17 does for a
contradictory event identity.

**How it fixes the finding.** Approvers have attested identities, are counted
by principal, are checked against the requested role and kind, a 1.2 workflow
can require authentication mechanisms and trust classes (and a 1.1 consumer
refuses it), the canonical record holds the counted identities, and the
Standard Agents binding records the attestation the finding says it had no
field for.

### ACS-13 — approving and carrying out a deferred action

**Decision.** Option (a) of the finding: **resumption**. A run that ended
`Completed` with outcome `deferred` can be resumed, as the same run (same
`run_id`, records, trace, stores, loop counts, used decision ids), with an
attendance the host names (default attended) and optionally a new actor:

1. Checkpoints taken before the resumption are invalidated (as after a wait);
   a resumed step that needs a checkpoint gets a new one.
2. What runs again, in step order, each from its beginning (condition, gates,
   delay, inputs, approval, checkpoint):
   - the deferred steps (re-entered);
   - each step that **ran ahead** (began after a step of its frame was
     deferred and was not deferred itself) whose store a later step that runs
     again reads, so a re-entered `verify` reads what is there after the
     `mutate` before it, as in a run that never deferred; handlers and
     `after_deferral: run` steps keep their outputs;
   - each `checkpoint` step whose checkpoint the resumption invalidated (no
     step had used it) and whose store a later re-entered step that requires a
     checkpoint reads, so a `mutate` that binds `${checkpoint_out.checkpoint_id}`
     (§12.5) binds and uses the new checkpoint.
   Every other step keeps its output.
3. A deferred `invoke` whose nested run ended `deferred` **continues** that
   nested run (the executor now keeps it), which resumes the same way; the
   invoke step then completes. No nested step runs again except as item 2
   says.
4. A run whose handler was deferred (ended `deferred` with a cause) runs its
   normal-flow resume list, then the handler with the cause; it then ends
   `escalated` (or `deferred` again).
5. A re-entered step that requires approval is asked afresh (new shown values,
   digest, `expires_at`; recheck after the decision). In an attended
   resumption it is asked of a person (a `human` approver keeping role,
   `min_approvers` and the identity checks, without `mandate_ref`). In an
   unattended resumption normal unattended rules apply (it may be deferred
   again). In either attendance, every request for a re-entered queued step
   names `queued_action_id`.
6. The `planned` record of a re-entered step is updated **in place**, same
   `action_id` (decision, outcome, timestamp, actor), so the host's queue
   entry closes on the record it already knows.
7. A recovery loop during a resumption returns to normal flow and supersedes
   the queued steps not yet re-entered and a deferred handler not yet run; a
   gate `end` supersedes the queued steps after it; another escalation
   supersedes the deferred handler's queued actions and leaves the other
   queued steps deferred; a re-entered step that is skipped or fails before
   its approval supersedes its own queued action; a failure or replan leaves
   unreached queued steps deferred (listed, `planned`).
8. A run that ended other than `deferred` (failed, escalated, needs a replan,
   cancelled) cannot be resumed, and its queued actions are never carried
   out: their records stay `planned` in its terminal action (`cancelled` when
   S2b's cancel ended it), a host treats them as abandoned, and it may start a
   new run, which is another run.
9. An executor refuses to resume a state that does not keep what resumption
   needs (the nested runs of deferred `invoke` steps, and which steps ran
   ahead): the reference executor refuses every state with deferrals saved by
   its versions before 1.2. Such a run can be cancelled (S2b).

A new run of the workflow is a different run and does not carry out or close
an earlier run's queued actions. A host MUST NOT resume one saved state twice
(single writer, S2b).

**Options considered.** (a) resumption; (b) "a queued action is carried out
by a new attended run" (the audit's PATCH option); (c) resumption with the
decision passed in up front. (b) rejected: a new run re-executes every
non-deferred step, so a workflow that sent a report under a mandate and
deferred a human-approved change would send the report again; the queued
`planned` record would never close; and nothing would bind what the approver
later approves to what was queued. (c) rejected: the host can answer the
resumed request at once with a decision it collected out of band (the digest
check makes that safe), so passing decisions in adds an API without adding
power. Within (a):

- *Steps that ran ahead.* Keeping their outputs (revision 1) runs a
  re-entered `verify` against observations taken before the `mutate` it
  verifies. Re-running every step that ran ahead repeats `audit`/`persist`
  records no step needs. Running a step just before its first reader changes
  its order relative to the other queued actions. Re-running, in step order,
  exactly the ones a later re-run step reads reproduces the order of a run
  that never deferred. Chosen.
- *Checkpoint steps.* Re-running a checkpoint step for every reader would
  make a re-entered `rollback` that binds it return to a later restore point
  than in an unbroken run; re-running one whose checkpoint an earlier step
  had already used would hand a later step a checkpoint it did not have in an
  unbroken run. The rule is therefore limited to readers that require a
  checkpoint and to checkpoints the resumption invalidated.
- *Nested runs.* Continued rather than restarted, for the same
  duplicate-effect reason as (a) over (b).
- *Records.* Updated in place rather than a new record with a back-link: no
  new record field, and the queue stays keyed by one `action_id`.
- *Runs that ended otherwise.* Abandoned by statement rather than closed by
  the executor at their end (that would change the `planned` records a 1.1
  run leaves, which `failure_after_deferral` pins) or by extending S2b's
  cancel to ended runs (that would replace the run's own failure code with
  R408).
- *Old states.* Refused rather than resumed with guesses: a version-1 state
  has no nested run to continue and does not say which steps ran ahead, so
  any guess repeats effects or verifies stale data.

The audit's extra gap (a human-approver deferral records no digest) is closed
by design: the approver is shown the values when the run resumes, and the
decision is bound to the digest of those values.

**How it fixes the finding.** The Standard says how a queued action is
approved (the resumed request), whether the digest and recheck are checked
again (yes, afresh), how dependants run (after the head, by the usual rules,
with what they read brought up to date), what happens to the record, and what
becomes of queued actions of runs that cannot be resumed; the reference
executor, Python package and fixtures implement it.

### ACS-35 — restore under a different actor; handoff

**Decision.** §5.17 "Actor" gains: a run keeps its actor while it continues;
when a host restoring a saved run names the actor it restores for, the
executor MUST refuse a principal that differs from the run's (or any actor for
a run started without one); a host SHOULD name it. At a **handoff** the host
MUST NOT continue the run under the agent that takes over: it cancels the run
(S2b §5.19.5, R408) if the run has not ended, and the new agent starts its own
run. A run that ended `deferred` may instead be resumed under the new actor
(§5.14.1), which the trace and the later records show, or cancelled.

**Options considered.** (a) refuse a mismatch on restore; (b) record a change
on restore; (c) both, by operation. (c) chosen: restoring is "continue the
same execution", where a change of party is the handoff bug the finding
describes; resuming a deferred run is "carry out the queue", where another
party (a person's agent, an operator) is the expected case. For the handoff,
cancelling is the one operation that ends a run early (S2b), so it is what the
host does; leaving the run open would keep its `approved` records open with no
one to drive it. Making the actor mandatory on every restore (MUST) was
rejected for 1.2 because it would break every existing `restore(snapshot,
key)` caller whose run has an actor; it is an open question for a major
version.

**How it fixes the finding.** The Standard states who may continue a run and
what the host does at a handoff; `restore` takes an actor and refuses a
mismatch; `resume` records the change; the integration guide, the guides and
the interop mapping state the handoff rule.

---

## 2. Normative text for `spec/STANDARD-v1.2.0.md`

Section numbers are those of 1.1.0, plus the final numbers of the new
sections (FOUNDATION.md part D). S2b's host protocol is §5.19: actions and
responses §5.19.1, run operations §5.19.2, saving and continuing §5.19.4,
cancelling §5.19.5.

### 2.1 §5.9 Workflow Extensions — table row (replace the `identity@1` row)

```markdown
| `identity@1` | bindings of `receive`/`synchronize`/`delegate` `sender_check`, `accept_trust_classes`, `always_ask_trust_classes`; approver identities on approval decisions; in a workflow that targets 1.2, `approval.approver` `sender_check` and `accept_trust_classes` (§5.14, §5.17) |
```

### 2.2 §5.14 Approval (replace the whole section)

````markdown
### 5.14 Approval

```yaml
approval:
  approver: {kind: human, role: release-manager, min_approvers: 2}
  mode: out_of_band
  shows: ["${plan_out.steps}"]
  binds_to: digest
  recheck: {source: "${plan_out}", compare: digest, on_change: reask}
  expires: 24h
  when_unattended: defer_to_queue
```

| Field | Description |
|-------|-------------|
| `approver` | Required (S304). `kind` (required): `human` or `standing_mandate`; `role`; `min_approvers` (integer ≥ 1, default 1); `mandate_ref`, required for and only for a standing mandate (S304 / S303); in a workflow that targets 1.2, with `identity@1`, `sender_check` and `accept_trust_classes` (§5.17) |
| `mode` | Where the approver is asked: `in_session` (default) or `out_of_band` (see **Modes**) |
| `shows` | References whose values the approvers see (each a `${...}` reference, else S303); absent, the step's resolved inputs (see **Shown values and digest**) |
| `binds_to` | `digest` (default): the decision binds to the shown values |
| `recheck` | `source` (required, a `${...}` reference re-read before acting, else S303), `compare`: `version` or `digest` (default), `on_change`: `reask` (default), `replan` or `stop` |
| `expires` | How long after the request a decision may arrive: a duration longer than zero; absent, no limit |
| `when_unattended` | `fail` (default), `skip` or `defer_to_queue` |

`approval` is allowed only where the effective `requires_approval` is true
(S303); other values above are S303 when malformed, and unknown fields W604.

**The request.** A step whose effective `requires_approval` is true asks for
approval once its inputs are resolved (after its condition, its gates and
any delay, §5.13) and before it uses a checkpoint. The executor puts a
request to the host (`RequestApproval`, §5.19.1) that names the approver (the
step's `approver` as declared), the mode, the shown values, their digest and,
when `expires` is set, `expires_at`: the time of the request plus `expires`.

A step that requires approval and has no `approval` field, in a workflow that
declares `approval@1` or not, is asked as if it declared
`approval: {approver: {kind: human}}`: a person (one approver, no role), in
session, shown its resolved inputs, with no expiry and no recheck, and with
`when_unattended: fail` (W606, F502). A member that an `approval` field leaves
out takes the default the table gives. Two steps are asked of a person even
when their approver is a standing mandate: a step marked always-ask (§5.17)
and a queued step that an attended resumption re-enters (§5.14.1).

**Modes.** The mode tells the host where to ask:

- `in_session`: the party attending the run is asked, through the session
  the run is attended in (such as the host's own permission prompt or the
  conversation), and answers while the run waits in that session.
- `out_of_band`: the approvers are asked through a channel separate from the
  run's session (such as a ticket, a message to an approver group or a review
  queue). They need not attend the run, and the decision may arrive after the
  session that asked has ended; a host that asks so keeps the run's state
  while it waits (§5.19.4).

The mode changes neither the shown values, nor the digest, nor which
decisions are valid. A host that cannot ask in the declared mode SHOULD
answer `unavailable` rather than ask elsewhere. A `human` approver is not
asked in an unattended run, in either mode (see **Attendance**): to have an
action of an unattended run approved out of band, declare
`when_unattended: defer_to_queue` and resume the run once its approvers can
be asked (§5.14.1).

**Shown values and digest.** The shown values are a JSON array:

1. With `shows`: one element per reference, in order, each the value the
   reference resolves to when the request is made; a reference that resolves
   to nothing gives `null`. An array value is one element: it is not spliced
   into the array.
2. Without `shows`: one element, the step's resolved inputs: its
   `input_bindings` with every reference resolved, the value its capability
   is invoked with (`{}` when the step binds none).
3. Asked again because a recheck saw its source change (`on_change: reask`):
   the array of item 1 or 2, then one more element,
   `{"recheck": {"previous": P, "current": C}}`, where `P` is the value of the
   source that the earlier decision was bound to and `C` the value the recheck
   read.

The shown values MUST be I-JSON (RFC 7493): no member name appears twice in
one object, and every **integer**, a number written without a fraction or an
exponent, has a magnitude of at most 2^53. An executor refuses a value that
breaks either rule: a step whose resolved inputs hold one fails with R402,
and a response that carries one is malformed and changes nothing (§5.19.1). A
host that reads values from JSON text keeps each integer an integer: where
its parser would read an integer too long for it as a binary64 value, it
refuses the value instead. Every other number is a finite binary64 value,
written as RFC 8785 writes it, so `1e+21` (the `numbers` vector of §10.3) is
valid although its value exceeds 2^53. (RFC 7493 §2.2 recommends integers of
magnitude at most 2^53 − 1; 2^53 is also exactly representable in binary64,
and 1.1 executors accept it.)

The **digest** is the SHA-256 of the UTF-8 encoding of the array's canonical
JSON (RFC 8785), written as 64 lowercase hexadecimal digits. The request
carries it and a decision repeats it; the two are compared without regard to
the case of the hexadecimal letters. The digest vectors of §10.3 fix the
canonical text and the digest for representative values.

**Decisions.** A decision is `approved`, `rejected`, or `unavailable`: no one
could decide (no standing mandate covers the action). An `approved` decision
is valid only if:

- its digest matches the request's;
- at least `min_approvers` distinct approvers agree: the distinct strings of
  its `approvers` or, with `identity@1` and attested approver identities, the
  distinct principals whose identities meet the request (§5.17);
- it arrives no later than the request's `expires_at`, where there is one;
- its `decision_id` has not been used before in the run.

A mandate's approval names the approvers it stands for, and `min_approvers`
counts them as for people. Every decision is single-use; an `unavailable` one
records no approvers. A `rejected` decision, and an `approved` one that is
not valid, refuse the step (F502) with a `rejected` record (`expired` when
the decision came too late). A request with no decision by its `expires_at`
lapses: an `expired` record, and F502.

**Attendance.** A `standing_mandate` approver needs no one present, so it is
asked in an unattended run too (except for a step that uses an always-ask
item, §5.17); `when_unattended` applies only when it answers `unavailable`. A
`human` approver is not asked in an unattended run, whatever the mode, and
`when_unattended` applies at once. In an attended run, `unavailable` is a
refusal (F502). The plans:

- `fail` (default) → F502.
- `skip` → the step is skipped.
- `defer_to_queue` → a `planned` action record, and the step is
  **deferred**: it does not run now.

Once a step of a workflow is deferred, each later step of that workflow is
deferred too if it depends on a deferred step:

1. it reads a deferred step's store (a reference in any executable field,
   i.e. not `purpose` or a failure mode's prose, or a quorum reviewer);
2. it may act on, or wait on, the world: its effective
   `requires_checkpoint` or `requires_approval` is true, it waits or
   delays (§5.13), or it is an `invoke`, `delegate`, `synchronize` or
   `rollback`;
3. ontology `precedes` edges, followed transitively, order its capability
   after a deferred step's (as `verify` after `mutate`), including a
   capability that a nested run deferred.

A handler (§5.11) is exempt from rules 2 and 3: it is the escalation path,
and deferring it would leave a failure unhandled. So is a step that
declares `after_deferral: run` (`approval@1`, else V106; the other value,
`defer`, is the default; anything else is S303): its author states that it
does not depend on what was deferred, such as an escalation to a person
that must happen whether or not a reminder went out. Rule 1 still
applies to both: a step that reads a deferred store is deferred, since
the value it reads does not exist. Declare it only where running ahead of
a deferred action is safe; rule 2 exists because a step that reads
nothing from a deferred "drain node" may still reboot an undrained node.

A step is checked before its condition, so it waits rather than running
on a missing value or an unchanged world; a deferred dependent is not
asked for approval and does not follow its own `when_unattended`. Other
steps, those that read, reason or record (`retrieve`, `observe`, `plan`,
`audit`, `persist`, `checkpoint`, …) and depend on nothing deferred, still
run: they **run ahead** of the deferred steps, and a resumption runs one
again when a step it runs again reads it (§5.14.1). A deferred step that
requires approval gets its own `planned` record. A nested run that ends
`deferred` defers its `invoke` step; the invocation itself ran, so its
record (if any) is `executed`, and the nested run's records are the queued
actions. A recovery loop whose target is a deferred step, or one before it,
runs the step again, and an invoke step that runs its workflow again (a
retry) starts it afresh; either way the records of the earlier deferrals
become `rejected` ("superseded"), so a queue never holds the same action
twice.

A run with deferred steps ends `deferred`, unless it fails, escalates or
needs a replan, which take precedence. Whatever the outcome, the terminal
action lists every deferral (`deferred`: frame, step, `store_as`, reason
and the `action_id` of its record), so the host knows which queued actions
belong to the run and what still waits for them. A handler that is
deferred (or whose nested run deferred steps) has not finished handling,
so that run ends `deferred`, keeping the escalation's cause; a nested run
that ends so is, for its invoke step, an escalated nested run (R402).

A queued action is put to its approvers, and carried out, by resuming its
run (§5.14.1). The queued actions of a run that did not end `deferred` are
never carried out (§5.14.1). A new run of the workflow is another run: it
neither carries out nor closes an earlier run's queued actions.

The decision is recorded on the action record (`world_state_schema.yaml`
1.2.0: `approval` with the digest, decision, the counted approvers and, with
`identity@1`, their identities; status `rejected` or `expired`, with a
`reason`, when it was refused, invalid or lapsed, or when an unattended run
did not ask; `planned`, with the reason, when it was deferred). A resumed run
updates the record of a queued action in place (§5.14.1).
````

### 2.3 §5.14.1 Resuming a Deferred Run (new subsection, after §5.14)

```markdown
#### 5.14.1 Resuming a Deferred Run

A run that ended with outcome `deferred` can be **resumed**: it continues, as
the same run, with the steps it deferred. This is how its queued actions are
put to their approvers and carried out. An executor that implements
`approval@1` MUST support resumption. The host resumes a run from its state
at the end (the `resume` operation, §5.19.2), names the run's attendance from then on (attended unless
it says otherwise), and may name a new actor (§5.17). A host MUST NOT resume
the same saved state twice: each resumption could carry out the same queued
action.

**Runs that did not end deferred.** A run that failed, escalated, needed a
replan or was cancelled (§5.19.5) cannot be resumed, and the queued actions it
lists are never carried out. Their records stay `planned` in its terminal
action (a cancelled run's become `cancelled`): a host treats them as
abandoned, closes whatever queue entries it keeps for them, and may start a
new run of the workflow, which is another run (§5.14).

When a run resumes:

1. **What it keeps.** Its stores, inputs, injected recovery context, loop
   counts, used decision ids, action records and trace are kept, and the
   trace records the resumption. No checkpoint taken before the resumption
   authorises a step after it, as after a wait (§5.13): a resumed step that
   requires a checkpoint gets a new one.
2. **What runs again.** These steps run again, in step order, each from its
   beginning (its condition, gates, delay, inputs, approval and checkpoint):
   - the deferred steps;
   - each step that **ran ahead**: it began after a step of its run was
     deferred and was not deferred itself (§5.14), and a later step that runs
     again under this item reads its store. It runs again so that the step
     that reads it sees what is there after the actions before it, as in a
     run that never deferred. A handler, and a step that declares
     `after_deferral: run`, keep their outputs;
   - each `checkpoint` step whose checkpoint the resumption invalidated (no
     step had used it) and whose store a later step that runs again under
     this item, and that requires a checkpoint, reads: its new checkpoint is
     then the one that step binds and uses (such as a `mutate` that binds
     `checkpoint_id`, §12.5), as W608's remedy takes a new checkpoint after a
     wait. A step that only binds the id, such as a `rollback`, does not
     cause this: it returns to the restore point it named.
   No other step runs again: a step that ran before the deferral, or ran
   ahead and is not read, keeps its output. The deferral rules of §5.14
   apply as in any run, so a step that depends on a step deferred again is
   deferred again. A deferred handler runs last (item 4).
3. **Nested runs.** A deferred `invoke` step whose nested run ended
   `deferred` continues that nested run, which resumes as this subsection
   says; when it ends, the step completes as any step whose nested run ended
   does (§5.12). The step's condition and gates are not evaluated again, and
   its inputs are not resolved again: they were when the invocation started.
   The queued actions of a nested run that failed are not carried out: the
   resumption supersedes them (`rejected`, "superseded").
4. **A deferred handler.** In a run whose handler was deferred (it ended
   `deferred` with an escalation's cause, §5.11), the steps of the normal
   flow that item 2 lists run first, in step order, and then the handler,
   with that cause; the run then ends as an escalation does.
5. **The approval.** A re-entered step that requires approval is asked
   afresh: its shown values and digest are computed now, a decision must
   match them, `expires` runs from the new request, and `recheck` re-reads
   its source after the decision. Every request for a re-entered queued step
   names its queued action (`queued_action_id`: the `action_id` of its
   `planned` record), in either attendance. In an attended resumption the
   request is put to a person, a `human` approver keeping `role`,
   `min_approvers`, `sender_check` and `accept_trust_classes` and dropping
   `mandate_ref`. In an unattended resumption the step is asked as in any
   unattended run, and its `when_unattended` applies again.
6. **The record.** A re-entered step continues its queued action: the
   `planned` record its deferral left is updated in place, keeping its
   `action_id`, with the decision, the outcome, the time and the actor. A
   step deferred again leaves the record `planned`. A re-entered step that
   ends without reaching its approval (its condition is false, a gate skips
   or stops it, or it fails first) supersedes its queued action (`rejected`,
   "superseded").
7. **Ending early.** A recovery loop during the resumption returns the run to
   normal flow from its target: the queued steps it has not re-entered, and a
   deferred handler it has not run, are superseded, as for any loop over a
   deferred step (§5.14), and the escalation that handler was to handle is
   dropped. A gate `end` ends the run before the queued steps after it and
   the deferred handler, whose queued actions are superseded. Another
   escalation takes precedence over the deferred handler's: its queued
   actions are superseded, the queued steps not yet re-entered stay deferred,
   and the new handler is judged against them (§5.14). When the resumed run
   fails, or needs a replan, the queued steps it did not reach stay deferred:
   listed among the run's deferrals, with their records `planned`, abandoned
   as above.

**Saved states.** An executor MUST refuse to resume a state that does not
keep what this subsection needs: the nested run of each deferred `invoke`
step, and which steps ran ahead. Such a run can be cancelled (§5.19.5). A host
whose executor saved the state before it implemented this subsection
cancels the run and starts a new one.

A resumed run ends as any run does; one that ends `deferred` can be resumed
again.
```

### 2.4 §5.17 Sender Identity

(a) In the paragraph "With `identity@1` declared, `receive`, `synchronize`
and a waiting `delegate` … accept three inputs", append one sentence at its
end:

```markdown
In a workflow that targets 1.2, the approver of an approval accepts two of
them as fields, `sender_check` and `accept_trust_classes` (see
**Approvers**).
```

(b) New paragraph, inserted after the **Always ask.** paragraph and before
**Actor.**:

```markdown
**Approvers.** With `identity@1` declared, a host may attest who decided an
approval (§5.14): a decision's `approver_identities`, a list of
`agent_identity`. Each MUST be one; two with the same principal MUST be
identical (a repeat counts once); and `approvers`, when not empty, MUST list
exactly their principals. A decision that breaks any of these is rejected as
malformed and changes nothing, as an event is. The approvers are then
counted by principal, and an identity counts toward `min_approvers` only if
it meets the request:

- for a `human` approver, including one asked in place of a standing mandate
  (§5.14.1, and **Always ask** above), its `kind` is `human`;
- when the request names a `role`, its `role` equals it;
- in a workflow that targets 1.2, when the approver declares `sender_check`,
  its `authenticated_by` is listed there;
- in a workflow that targets 1.2, when the approver declares
  `accept_trust_classes`, its `trust_class` is listed there.

The action record lists the approvers that counted: their principals in
`approval.approvers` and their identities in `approval.approver_identities`;
when the decision is refused, its `reason` names the others and why they did
not count. A layer that approves tool calls (§5.18.7) and can attest its
approvers records them the same way.

In a workflow that targets 1.2 (§11.5), `approval.approver` may declare
`sender_check` and `accept_trust_classes`: each a non-empty list of values
from the vocabularies above (else S303), with `identity@1` declared (else
V106). They make attested identities required: a decision without
`approver_identities` then counts no approvers. In a workflow that targets an
earlier version they are unknown fields (W604, and W616, §11.5), and neither
the validator nor the executor applies them; declare `spec_version: "1.2"` to
have them enforced, and a consumer of an earlier version then refuses the
workflow (V109) rather than ignore the requirement.

Without identities, the approvers are the distinct strings of `approvers`,
and the host vouches for them: it SHOULD accept a decision only from
approvers who hold the requested `role`. A workflow that does not declare
`identity@1` ignores `approver_identities`. As for a delegation, the
identities are the host's attestation: the executor checks that they are
consistent with the request, not that an approver is a person.
```

(c) In the **Always ask.** paragraph, replace "keeping the `role` and
`min_approvers` and dropping the `mandate_ref`" with:

```markdown
keeping the `role`, `min_approvers`, `sender_check` and
`accept_trust_classes` and dropping the `mandate_ref`
```

(d) Replace the **Actor.** paragraph with:

```markdown
**Actor.** A run may be started with the identity of the agent that runs
it; every action record then carries it as `actor_identity`, and `actor`
is its `kind`. `ActionRecord.actor_identity` and
`ProvenanceRecord.agent_identity` are optional in
`world_state_schema.yaml`. Two records denote the same party exactly when
their identities' principals are equal; an implementation MUST NOT infer it
from the `actor` or `agent` strings alone.

A run keeps its actor while it continues. A host that saves a run and
continues it later (§5.19.4) SHOULD name the actor it continues the run for; the
executor MUST then refuse to restore the run when that actor's principal
differs from the run's, or when the run was started without an actor.

At a **handoff**, when another agent takes over the conversation or thread a
run belongs to, the host MUST NOT continue the run under the agent that
takes over. It cancels the run (§5.19.5) if the run has not ended, and the agent
that takes over starts a new run under its own identity. A run that ended
`deferred` may instead be resumed under the new agent, or cancelled. The one
change of actor allowed is that resumption (§5.14.1): the host names the new
actor, the trace records the change, and the action records written from
then on, including the queued records the resumed run updates, carry the new
actor; earlier records keep theirs.
```

### 2.5 §6.3 World State Requirements (replace the last paragraph)

```markdown
An action record or a provenance record may carry the identity of who
acted (`actor_identity`, `agent_identity`; §5.17), and an action record's
approval the identities of the approvers that counted
(`approval.approver_identities`; §5.17).
```

### 2.6 §10.3 Conformance Testing (append a paragraph)

```markdown
The approval digest vectors (`tests/conformance/approval/digests.json`) are
normative for §5.14 and §5.18.7. Each vector has a `kind`. A `step` vector is
one approval request of a workflow step: the step's `approval` field (or
null for none), its resolved `inputs` where it declares no `shows`, and the
`shown` values. A `tool_call` vector is the approval of a tool call: the
`call` (`action`, `capability`, `args`) and the `shown` values `[call]`.
Every vector gives the RFC 8785 `canonical` text of `shown` and its `digest`.
An implementation that computes or checks approval digests MUST produce each
vector's `canonical` text and `digest` from its `shown` values. An executor
MUST show, for each `step` vector's step, that vector's `shown` values, and a
layer (§5.18) MUST show, for each `tool_call` vector's call, that vector's
`shown` values.
```

(Whether the runtime fixtures are normative for an executor class is S2b's
§10 text; the approval, deferral and resumption fixtures of section 6 belong
to that set.)

### 2.7 §11.5 Version Declaration (input to S6)

S6 owns the 1.2 rule for features new in 1.2 in a workflow that targets 1.0 or
1.1 (the generalisation of W616) and the rule that "rules this Standard applies
only to workflows that target 1.2 apply only when such a version is declared".
S2a's 1.2 workflow features for that list:

- `approval.approver.sender_check`
- `approval.approver.accept_trust_classes`

Both take effect only in a workflow that targets 1.2. In a workflow that
targets 1.0 or 1.1 they keep their 1.1 treatment (unknown fields: W604,
ignored by validator and executor) and get W616; their V106 and S303 checks
apply only in a 1.2 target. Nothing else S2a adds is a workflow feature: the
default request, the digest rules and the mode meanings clarify 1.1;
`approver_identities`, `resume`, `queued_action_id` and the restore actor are
host-protocol features.

### 2.8 Appendix D: Changes from 1.1.0 (S2a entries)

Under **Clarifications of 1.1 semantics** (apply to 1.0, 1.1 and 1.2
workflows), table rows:

```markdown
| Default approval request | Not stated | A step that requires approval and has no `approval` field is asked as `approval: {approver: {kind: human}}`: in session, shown its resolved inputs, no expiry; omitted members take their defaults; `expires` runs from the request (§5.14) |
| Approval digest input | "the canonical JSON of the shown values" | The array of resolved `shows` values in order (null when unresolved), `[inputs]` without `shows`, plus a `recheck` element on a re-ask; SHA-256 as lowercase hex, compared regardless of case (§5.14); normative vectors with a `kind` per vector (§10.3) |
| Numbers in shown values | "integers within ±2^53" | An integer, a number written without a fraction or an exponent, has magnitude at most 2^53 and is refused otherwise; every other number is a binary64 value, so `1e+21` is valid (§5.14) |
| `approval.mode` | Listed values only | `in_session` and `out_of_band` defined; a human approver is still never asked in an unattended run (§5.14) |
```

Under **New in 1.2.0**:

```markdown
- Resumption of a deferred run (§5.14.1): the deferred steps run again, with
  the steps that ran ahead of them that they read and a checkpoint step whose
  invalidated checkpoint a re-entered mutation binds; nested deferred runs
  continue; a queued step is asked afresh (of a person when attended), the
  request names `queued_action_id`, and its `planned` record is updated in
  place. The queued actions of a run that did not end `deferred` are never
  carried out
- With `identity@1`, approver identities on a decision
  (`approver_identities`), approvers counted by principal and checked against
  the requested kind and role, and, in a workflow that targets 1.2, the
  approver fields `sender_check` and `accept_trust_classes` (§5.17)
- A run keeps its actor while it continues: a restore for another actor is
  refused, a handoff cancels the run unless it ended `deferred`, and
  resumption may name a new actor (§5.17)
- `world_state_schema.yaml` 1.2.0: `ActionRecord.approval.approver_identities`,
  and descriptions of `approval.mode` and of `planned` records that a
  resumption updates
```

---

## 3. Ontology, canonical and supporting schema deltas

### 3.1 Ontology

None. (`capability_ontology.yaml` is not touched by S2a.)

### 3.2 Canonical: `schemas/world_state_schema.yaml` (1.1.0 → 1.2.0, one bump shared with S1, S2b and any other workstream that edits it)

All changes are additive under §11.4 (one optional property, descriptions).
Exact replacements inside `types.ActionRecord.properties`:

```yaml
      timestamp:
        type: string
        description: When the record was written. A record that a resumed run
          updates (Standard v1.2 §5.14.1) carries the time of its latest change.
```

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
        description: rejected and expired (Standard v1.1 §5.14) record an approval
          that was refused or lapsed; an action deferred to a queue stays planned
          (its approval, if any, says why it was not approved now) until its run
          is resumed, which updates this record in place and keeps its action_id
          (Standard v1.2 §5.14.1). A planned record in the terminal record of a
          run that did not end deferred is abandoned and never carried out.
```

(S2b adds `cancelled` to this enum in the same bump; the merged description,
which keeps this text's last sentence, is in FOUNDATION.md part B1.)

Inside `approval.properties` (replace `digest`, `approvers` and `mode`; add
`approver_identities` after `approvers`):

```yaml
          digest:
            type: string
            description: SHA-256 of the canonical JSON (RFC 8785) of the values
              shown to the approvers, as 64 lowercase hexadecimal digits
              (Standard v1.2 §5.14).
```

```yaml
          approvers:
            type: array
            items:
              type: string
            description: The distinct approvers that counted toward
              min_approvers. With attested approver identities, their principals
              (Standard v1.2 §5.17).
          approver_identities:
            type: array
            items:
              $ref: '#/types/AgentIdentity'
            description: The identities of the approvers that counted, as the host
              attested them (Standard v1.2 §5.17, identity@1), one per principal.
              Present only when the decision carried identities.
          mode:
            type: string
            enum:
            - in_session
            - out_of_band
            description: Where the approvers were asked (Standard v1.2 §5.14).
              in_session, the party attending the run, in its session;
              out_of_band, through a channel separate from the run's session,
              whose approvers need not attend the run.
```

`schema.version: 1.2.0`. S2b adds `approval.decision_id` (ACS-37) in the same
bump. `tools/sync_skill_schemas.py` regenerates the vendored copies.

### 3.3 Supporting: `schemas/workflow_catalog.schema.json` (not a §6.1 schema)

In `$defs.approval.properties.approver.properties`, add:

```json
"sender_check": {
  "type": "array",
  "minItems": 1,
  "items": {
    "type": "string",
    "pattern": "^(session_id|chat_user_id|code_host_login|directory_id|api_key|signed_token|x-[a-z0-9][a-z0-9_.-]*)$"
  },
  "description": "identity@1, in a workflow that targets 1.2 (STANDARD v1.2 §5.17): an approver counts only if the host attested an identity whose authenticated_by is listed; a decision without approver identities counts none. In an earlier target, an unknown field (W604, W616)."
},
"accept_trust_classes": {
  "type": "array",
  "minItems": 1,
  "items": {
    "type": "string",
    "enum": ["owner", "decision_person", "system_of_record", "own_subagent_report", "peer_agent", "colleague", "external"]
  },
  "description": "identity@1, in a workflow that targets 1.2 (STANDARD v1.2 §5.17): an approver counts only if the host attested an identity whose trust_class is listed; a decision without approver identities counts none. In an earlier target, an unknown field (W604, W616)."
}
```

(The schema validates shape only; it cannot see the target, so the
1.1-target W604 is the validator's.)

Replace `mode` and `expires`:

```json
"mode": {
  "type": "string",
  "enum": ["in_session", "out_of_band"],
  "default": "in_session",
  "description": "Where the approver is asked (STANDARD v1.2 §5.14): in_session, the party attending the run, in its session; out_of_band, through a separate channel whose approvers need not attend the run. A human approver is never asked in an unattended run, in either mode."
},
```

```json
"expires": {
  "$ref": "#/$defs/positive_duration",
  "description": "How long after the request a decision may arrive; longer than zero. Absent, no limit."
},
```

Update the step property `approval`'s description to cite "STANDARD v1.2
§5.14".

### 3.4 New schema files

None. The host-protocol shapes below go into S2b's host protocol schema
(`schemas/host_protocol.schema.json`):

| Shape | Change |
|---|---|
| `RequestApproval` | optional `queued_action_id` (string): present on every request of a queued step that a resumption re-entered, in either attendance |
| `Decision` | optional `approver_identities` (array of `agent_identity`, or null); read only with `identity@1`; two different identities for one principal make the response malformed |
| Run operations | `resume(attendance = "attended", now_ms, actor_identity?)` on a run that ended `deferred`; `restore(..., actor_identity?)` |
| Snapshot | `SNAPSHOT_VERSION` 2: `Frame.resume`, `Frame.parked`, `Frame.pending_escalation`, `Frame.ahead`, `StepState.queued` (all optional; version 1 still restores, but a version-1 state with deferrals cannot be resumed) |
| Trace kinds | `run_resumed` (`attendance`, `actor`, `previous_actor`; `step` null), `invoke_resumed` (`workflow`) |
| Runtime fixture script entry | `{"resume": {"attendance"?, "at"?, "actor_identity"?}}`; response placeholder `"{{digest_upper}}"` (both already in S2b's §10.5 list) |
| Approval digest vectors | every vector has `kind`: `step` (`approval`, `inputs`?) or `tool_call` (`call`); not a schema file, documented in the file's `fields` |

---

## 4. New diagnostic codes

None. Every rule reuses an existing code or an API error:

| Situation | Reported as |
|---|---|
| Approver field without `identity@1`, in a 1.2 target | V106 (existing) |
| Approver field malformed or outside vocabulary, in a 1.2 target | S303 (existing) |
| Approver field in a 1.0/1.1 target | W604 (existing; unchanged 1.1 behaviour) and S6's W616 |
| Decision whose identities do not meet the request, or too few counted | F502 with a `rejected` record (existing) |
| Malformed `approver_identities`, two different identities for one principal, or `approvers` that disagree with them | Submit refused (`SubmitError::Malformed`), run unchanged, as for a malformed event identity |
| Resuming a run that did not end `deferred` | API error (`ResumeError::NotDeferred`) |
| Resuming a state that does not keep nested runs or which steps ran ahead | API error (`ResumeError::NotKept`) |
| Restoring for another actor | API error (`RestoreError::Actor`) |
| JSON text with an integer literal beyond 2^53 | `exec::read_json` error (a malformed response at the host's boundary) |

(Final code allocation: FOUNDATION.md part C; S2a adds none.)

---

## 5. Implementation plan per file

### 5.1 `core/src/exec/mod.rs`

Types:

- `Body::RequestApproval`: add
  `#[serde(default, skip_serializing_if = "Option::is_none")] queued_action_id: Option<String>`.
- `Response::Decision`: add `#[serde(default)] approver_identities: Option<Value>`
  (validated in `submit`, see machine.rs).
- `StepState`: add `#[serde(default)] queued: Option<usize>`: the index of the
  `planned` record of a queued step that this pass re-entered. `record()`
  updates it in place only while its status is `planned`.
- `Frame`: add
  - `#[serde(default)] resume: Option<Vec<usize>>`: the steps of this frame a
    resumption still runs, in the order they run (step order; a deferred
    handler last). `None` outside a resumption.
  - `#[serde(default)] parked: BTreeMap<usize, Frame>`: for a deferred
    `invoke` step, the nested run that ended `deferred` under it, kept so a
    resumption can continue it.
  - `#[serde(default)] pending_escalation: Option<String>`: the cause of an
    escalation whose handler a resumption runs after the normal-flow list.
  - `#[serde(default)] ahead: Option<BTreeSet<usize>>`: the steps that began,
    and were not deferred, while a step of this frame was deferred (since the
    frame started or was last reopened). `None` only in a state saved before
    it existed (version 1): such a frame with deferrals cannot be resumed.
  - `Frame::new` initialises `resume`/`pending_escalation` to `None`, `parked`
    empty and `ahead` to `Some(empty)`.
- `SNAPSHOT_VERSION = 2`. `restore` accepts `version` 1 or 2 (a version-1
  state has no new fields; serde defaults fill them, `ahead` stays `None`).
  Writing always uses 2. (One bump shared with S2b if S2b changes the
  snapshot too.)
- New public helper (ACS-11):

```rust
/// Read JSON text as a host value (§5.14): an integer literal (no fraction
/// or exponent) of magnitude above 2^53 is refused, including one too long
/// for 64 bits, which serde_json would read as a binary64 value. The value
/// must also be I-JSON (`ijson`).
pub fn read_json(text: &str) -> Result<Value, String>
```

  Implementation: one pass over the bytes, skipping strings (with `\`
  escapes); each number token without `.`, `e` or `E` whose digits (after an
  optional `-`) are longer than 16, or are 16 and compare above
  `"9007199254740992"`, is an error naming it; then `serde_json::from_str`
  and `ijson`. Used wherever the reference implementation reads a host's
  JSON text: `core/tests/runtime.rs` (fixture responses) and S6's text entry
  points.
- New public API:

```rust
#[derive(Debug, Clone)]
pub struct ResumeOptions {
    pub attendance: Attendance,
    pub now_ms: u64,
    /// Who carries the run on (§5.17): None keeps the run's actor.
    pub actor_identity: Option<Value>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ResumeError {
    /// Only a run that ended `deferred` can be resumed (§5.14.1).
    NotDeferred(String),
    /// The new actor is not an `agent_identity`.
    Identity(String),
    /// The state does not keep what resumption needs: the nested run of a
    /// deferred invoke step, or which steps ran ahead (§5.14.1).
    NotKept(String),
}

#[derive(Debug, Clone, Default)]
pub struct RestoreOptions {
    /// The actor the host restores the run for (§5.17): its principal must
    /// be the run's.
    pub actor_identity: Option<Value>,
}
```

- `RestoreError::Actor(String)` with Display `actor_identity: {m}`.
- `Run::restore(ctx, catalog, snapshot, key)` becomes
  `Run::restore_with(ctx, catalog, snapshot, key, RestoreOptions::default())`.
  `restore_with` does what `restore` does, then, when
  `options.actor_identity` is `Some(a)`: `ijson(a)` and `identity_error(a)`
  (else `Actor`), then compares `a["principal"]` with
  `state.actor_identity.principal`: refuse when they differ or when the state
  has no actor (`Actor("the run was started without an actor")`).
- `Run::resume(&mut self, o: ResumeOptions) -> Result<(), ResumeError>`:
  1. `self.state.finished` must be `Body::Completed { outcome: Deferred, .. }`
     (else `NotDeferred` naming the outcome or failure code, or "the run has
     not finished").
  2. If `o.actor_identity` is `Some`, `ijson` and `identity_error` (else
     `Identity`).
  3. `not_kept(&self.program, &self.state)` (below) is `None` (else
     `NotKept(m)`).
  4. `self.machine().resume(o)`.
- `fn not_kept(program, st) -> Option<String>`: walk the top frame and,
  recursively, each parked frame, with the path prefix of steps above it:
  - a frame whose `deferred` is non-empty and whose `ahead` is `None` →
    "which steps of '{w}' ran after its first deferral";
  - for each `s` in a frame's `deferred` that is an `invoke` step and under
    which a deferral is listed (a `Deferral` whose path starts with
    prefix + `[s]` and is longer), with no `parked[s]` → "the nested run of
    step {s} of '{w}'".
  Every version-1 state with deferrals fails the first check; one with a
  nested deferral fails both.
- `check_state` additions (a restored state must be one the executor could
  produce):
  - `resume`: entries strictly ascending except a final handler step when
    `pending_escalation` is set; every entry `< steps.len()`; no entry in
    `f.deferred`; a non-final entry is not a handler.
  - `pending_escalation.is_some()` implies `escalation.is_none()` and
    `resume.is_some()`.
  - `ahead`: every entry `< steps.len()` and not in `f.deferred`.
  - `parked`: every key is in `f.deferred` or in `f.resume`, and names an
    `invoke` step; each parked frame recursively passes the per-frame checks,
    has `escalation == None`, a non-empty `deferred` or a `resume` list, and
    `stage == Begin`; depth: an active frame at index `i` with parked nesting
    `j` needs `i + j + 1 <= MAX_FRAMES`.
  - `cur.queued` is `None` or `< records.len()`.
  - Factor the existing per-frame loop body into `check_frame(program, st, f)`
    so parked frames reuse it.

### 5.2 `core/src/exec/machine.rs`

1. **`Asked`** gains `approver: &'s Value` (the request's approver, read from
   `pending.action.body` in `respond`) and `identities: Option<Vec<Value>>`.
2. **`submit`**: after the existing event-identity block, when the workflow
   declares `identity@1` and the response is `Decision` with
   `approver_identities: Some(v)` and `v` is not null:
   - `v` must be an array (else `Malformed("approver_identities must be a list")`);
   - each element: `ijson`, `identity_error` (else
     `Malformed(format!("approver_identities[{i}]: {e}"))`);
   - two elements with one principal must be equal as JSON values (else
     `Malformed(format!("approver_identities gives two different identities for '{p}'"))`);
   - if `approvers` is non-empty, `set(approvers) == set(principals)` (else
     `Malformed("the decision's approvers are not its approver_identities' principals")`).
   Without `identity@1`, the member is ignored and not validated.
3. **`record(status, approval)`**: if `cur.queued == Some(r)` and
   `records[r]["status"] == "planned"`, update record `r` in place and return
   `r`: set `status`, `timestamp = iso(now)`, `actor`/`actor_identity` from
   `st.actor_identity` (as for a new record), `always_ask` (set or remove),
   `approval` (set, or remove when `None`), remove `reason` (callers set it).
   Otherwise push a new record as today. Effect: `decide` (approved / refused),
   `unattended` (skip / fail / defer_to_queue) and `defer_step` (dependent
   that requires approval) all continue the queued record without further
   change.
4. **`approval()`**:
   - `let queued = self.frame_ref().cur.queued;`
     `let person = marked || (queued.is_some() && self.st.attendance == Attendance::Attended);`
   - `mandate = !person && approver.kind == standing_mandate`;
   - the approver transformation that today runs for `marked` runs for
     `person`: set `kind: human`, remove `mandate_ref`; insert
     `always_ask: true` only when `marked`;
   - `queued_action_id = queued.and_then(|r| records[r]["action_id"].as_str())`,
     put on the `RequestApproval` whenever it is `Some`, in either attendance
     (an unattended resumption that asks a mandate names it too).
   No other change (shown, digest, expiry, mode already follow §5.14 text).
5. **`decide()`**:
   - Read `mandate_ref` from the request's approver (`asked.approver`), not
     from the spec (covers always-ask and resumption uniformly); same change
     in `tick()`'s expiry branch, reading `pending.action.body`.
   - Counting:
     ```rust
     let declared = self.workflow().extension("identity@1");
     let v12 = self.workflow().targets_1_2;   // §11.5 target, program.rs
     let requires = v12 && (approver.get("sender_check").is_some()
         || approver.get("accept_trust_classes").is_some());
     match (declared, identities) {
         (true, Some(list)) => {
             // deduplicated by principal (submit made repeats identical),
             // ordered by principal
             let (counted, refused): (Vec<_>, Vec<_>) =
                 dedup(list).partition(|id| meets(approver, id, v12).is_ok());
             recorded_approvers = principals(counted);
             recorded_identities = Some(counted);
             notes = refused.map(|id| format!("{} ({})", principal, meets(..).unwrap_err()));
         }
         (true, None) if requires => counted = 0, note "the approver requires attested identities (sender_check, accept_trust_classes), and the decision carries none",
         _ => counted = distinct strings (today's rule),
     }
     ```
     `fn meets(approver: &Value, id: &Value, v12: bool) -> Result<(), String>`
     checks, in order: `approver.kind == "human"` ⇒ `id.kind == "human"`;
     `approver.role` ⇒ `id.role == role`; when `v12`: `approver.sender_check`
     (array) ⇒ `id.authenticated_by ∈ list`; `approver.accept_trust_classes`
     ⇒ `id.trust_class ∈ list`. Each failure returns a short reason. In a 1.0
     or 1.1 target the two fields are not read, whatever the request carries
     (it carries the approver as declared, as in 1.1).
   - The `(distinct.len() as u64) < min` test becomes `counted < min`, with
     the reason `"{counted} counted approver(s), {min} needed"` plus
     `"; not counted: bob (role 'ops' is not 'release-manager'), ..."`.
   - The approval sub-record: `approvers` = the counted principals (or the
     distinct strings without identities), and `approver_identities` = the
     counted identities, only when `declared` and the decision carried them
     (possibly `[]`). `unavailable` keeps `approvers: []` and no identities.
6. **`begin()`** (reordered):
   ```rust
   let index = self.frame_ref().step;
   // A resumption runs its list in order (§5.14.1): pop this step. A
   // deferred handler reached so restores the escalation it was deferred
   // under, before the handler-skip check below reads it.
   if self.frame_ref().resume.as_ref().and_then(|l| l.first()) == Some(&index) {
       let handler = self.step_ref().handler;
       let f = self.frame();
       f.resume.as_mut().expect("checked").remove(0);
       if handler && let Some(c) = f.pending_escalation.take() { f.escalation = Some(c); }
   }
   let escalating = self.frame_ref().escalation.is_some();
   // ... existing end-of-steps and handler-skip checks, `replaces`, f.cur ...
   let path: Vec<usize> = self.st.frames.iter().map(|f| f.step).collect();
   // A step that begins while a deferral of its own is listed is re-entered
   // by a resumption: it continues that queued action (§5.14.1).
   if let Some(pos) = self.st.deferrals.iter().position(|d| d.path == path) {
       let d = self.st.deferrals.remove(pos);
       let f = self.frame();
       f.nested_caps.remove(&index);
       f.cur.queued = d.record;
   }
   // ... existing step_started trace and deferred_cause check (defer_step
   // leaves a parked child parked) ...
   // Not deferred: while a step of the frame is deferred, it runs ahead.
   {
       let f = self.frame();
       if !f.deferred.is_empty() && let Some(a) = &mut f.ahead { a.insert(index); }
   }
   // A deferred invoke whose nested run ended deferred continues it (the
   // resumption already reopened it); its condition, gates and inputs were
   // settled when the invocation started.
   if let Some(child) = self.frame().parked.remove(&index) {
       self.frame().stage = Stage::Execute;
       self.trace_step("invoke_resumed", json!({"workflow": child.workflow}));
       self.st.frames.push(child);
       return Flow::Continue;
   }
   // ... existing condition, gates, delay ...
   ```
   In 1.1 flow no step ever begins while a deferral for its exact path is
   listed (loops and invoke retries remove them first), and no frame has a
   resume list or parked runs, so the new branches are no-ops for runs that
   are never resumed; `ahead` is bookkeeping only.
6a. **`settle_queued()`** (new helper): if `cur.queued.take()` is `Some(r)`
   and `records[r]["status"] == "planned"`, set it `rejected` with reason
   `"superseded: the step did not reach its approval when its run resumed"`.
   Call it at the top of `next_step`, in `end_frame` (for the ending frame's
   `cur`), in `recover` and in `escalate`. `defer_step` sets
   `cur.queued = None` after taking the record, so a step deferred again keeps
   its record `planned`. This closes the queued record of a re-entered step
   that is skipped, or fails, before its approval.
7. **`next_step()`**:
   ```rust
   let len = self.workflow().steps.len();
   if let Some(list) = self.frame_ref().resume.clone() {
       if let Some(&next) = list.first() {
           let f = self.frame(); f.step = next; f.stage = Stage::Begin;
           return Flow::Continue;
       }
       self.frame().resume = None;
       if self.frame_ref().escalation.is_none() {
           // The list is done: every later step ran before the deferral (or
           // a gate ended the run), and its output stands.
           let f = self.frame(); f.step = len; f.stage = Stage::Begin;
           return Flow::Continue;
       }
   }
   // existing escalation branch and f.step += 1
   ```
8. **`resume(&mut self, o)`** (new `Machine` method) and helper
   `reopen(program, f, invalidated)`:
   ```rust
   /// Reopen a frame that ended deferred (§5.14.1 item 2): its resume list
   /// is, in step order, the deferred steps; the steps that ran ahead and
   /// that a later listed step reads; and the checkpoint steps whose
   /// checkpoint the resumption invalidated and that a later listed step
   /// requiring a checkpoint reads. A deferred handler goes last. Parked
   /// nested runs are reopened too.
   fn reopen(program: &Program, f: &mut Frame, invalidated: &[String]) {
       let wf = &program.workflows[&f.workflow];
       let deferred = std::mem::take(&mut f.deferred);
       let ahead = f.ahead.replace(BTreeSet::new()).unwrap_or_default();
       let handler = f.escalation.take().map(|cause| {
           f.pending_escalation = Some(cause);
           f.step                                  // the deferred handler
       });
       let mut list: BTreeSet<usize> =
           deferred.iter().copied().filter(|&s| Some(s) != handler).collect();
       let reads = |s: usize, store: &str| wf.steps[s].reads.iter().any(|r| r == store);
       // Descending, so every later reader is already settled.
       for c in (0..wf.steps.len()).rev() {
           let step = &wf.steps[c];
           if list.contains(&c) || step.handler { continue; }
           let Some(store) = step.store_as.as_deref() else { continue };
           let later: Vec<usize> =
               list.range(c + 1..).copied().chain(handler).collect();
           let ran_ahead = ahead.contains(&c)
               && !step.after_deferral_runs
               && later.iter().any(|&s| reads(s, store));
           let stale_checkpoint = step.capability == "checkpoint"
               && f.stores.get(store)
                   .and_then(|o| o.get("checkpoint_id")).and_then(Value::as_str)
                   .is_some_and(|id| invalidated.iter().any(|i| i == id))
               && later.iter().any(|&s| wf.steps[s].requires_checkpoint && reads(s, store));
           if ran_ahead || stale_checkpoint { list.insert(c); }
       }
       let mut queue: Vec<usize> = list.into_iter().collect();
       queue.extend(handler);
       for child in f.parked.values_mut() { reopen(program, child, invalidated); }
       f.step = queue[0]; f.stage = Stage::Begin; f.cur = StepState::default();
       f.resume = Some(queue);
   }
   ```
   `nested_caps` is not cleared: `begin` removes a step's entry when it
   re-enters it, and `deferred_cause` reads only the entries of steps in
   `f.deferred` (item 13).

   `Machine::resume(o)`:
   1. remember the previous actor's principal; replace `st.actor_identity`
      when `o.actor_identity` is `Some`; set `st.attendance = o.attendance`,
      `st.now = max(st.now, min(o.now_ms, MAX_TIME))`, `st.finished = None`;
   2. supersede every **orphaned** deferral, one whose path runs through a
      step that is not in its frame's `deferred` (the queued actions of a
      nested run that failed under a step that was not deferred), reason
      `"superseded: the nested run it was queued in failed"`;
   3. trace `run_resumed` with `step: None` and detail
      `{"attendance", "actor": principal|null, "previous_actor": principal|null}`;
   4. `let invalidated = self.invalidate_checkpoints(None)` (the helper gains
      the trace step as an argument and returns the ids it invalidated);
   5. `reopen(self.program, &mut self.st.frames[0], &invalidated)`;
   6. `drive()`.
9. **`end_frame` (`Ok((Deferred, None))` branch)**: compute `caps` from
   references to `child.deferred` and the `child.nested_caps` entries of those
   steps (clone, do not move), then normalise and park the child before
   `defer_step`: `child.stage = Begin; child.step = len(child wf);
   child.cur = default; self.frame().parked.insert(step, child);`.
10. **`end_run()`** (gate `end`): before ending, supersede the frame's
    leftover list and the pending handler:
    ```rust
    if let Some(left) = self.frame().resume.take() {
        self.supersede_queued(&left, "superseded: a gate ended the resumed run before the step");
    }
    self.frame().pending_escalation = None;
    ```
    `supersede_queued(steps, reason)`: with `depth = frames.len() - 1` and
    `prefix` the steps of the frames above, supersede deferrals whose
    `path[..depth] == prefix && steps.contains(&path[depth])` (reuse
    `supersede`; this covers nested paths), and
    `parked.retain(|k, _| !steps.contains(k))`. Entries of the list that are
    re-run steps have no deferral and are unaffected.
11. **`escalate()`** during a resumption (§5.14.1 item 7): if the frame has a
    `resume` list, take it:
    - if `pending_escalation.take()` is `Some`, the list's last entry is the
      deferred handler: `supersede_queued(&[h], "superseded: another escalation took precedence")`;
    - every other entry with a listed deferral (a queued step not yet
      re-entered) is merged back into `f.deferred` (sorted); every other entry
      (a step listed to run again because it ran ahead, or a stale checkpoint
      step) is inserted into `f.ahead`, since it still holds its output from
      before the deferral.
    The new handler is then judged by rule 1 against the steps still deferred,
    as in a first run, and a later resumption re-runs what it reads.
12. **`undefer_from(target)`**: first, during a resumption, settle the list:
    ```rust
    if let Some(left) = self.frame().resume.take() {
        // The loop returns to normal flow: the queued steps not yet
        // re-entered (all at or after the target) and a deferred handler not
        // yet run (at any index) are superseded; the escalation is dropped.
        self.frame().pending_escalation = None;
        self.supersede_queued(&left, "superseded: a recovery loop ran from an earlier step");
    }
    ```
    then the existing code, plus `f.parked.retain(|k, _| *k < target)` and
    `if let Some(a) = &mut f.ahead { a.retain(|&k| k < target) }`. This fixes
    the case where a deferred handler below the target kept its deferral and
    the run ended `completed` while listing it.
13. **`deferred_cause()`**: rule 3 reads `f.nested_caps` only for steps in
    `f.deferred` (`f.deferred.iter().filter_map(|d| f.nested_caps.get(d)).flatten()`)
    instead of all entries. In a first run every key is in `f.deferred`, so
    nothing changes there; during a resumption the entries of queued invoke
    steps not yet re-entered no longer reach back to earlier steps.
14. **`defer_step()`**: when `f.deferred` is empty and `f.ahead` is `None`
    (a version-1 frame deferring for the first time after a restore), set
    `f.ahead = Some(empty)`: tracking is exact from the frame's first
    deferral. Then the existing body, and `cur.queued = None` after taking the
    record.
15. **`undefer_nested()`**: also `self.frame().parked.remove(&step)`.
16. Failure, replan: no change. Unreached queued entries stay in
    `st.deferrals` (listed) with `planned` records, which is the §5.14.1
    item 7 behaviour; the run is not resumable, so they are abandoned.

### 5.3 `core/src/exec/program.rs`

- `Workflow` gains `pub targets_1_2: bool`: S6's
  `semantics::target(raw, header) >= Some((1, 2))`, computed when the program
  is built (S6 passes the catalog header to `prepare`). `decide()` reads it.
- No change to `Step` (`reads`, `after_deferral_runs`, `requires_checkpoint`,
  `handler`, `store_as` already exist).

### 5.4 `core/src/exec/canonical.rs`

Doc comment: cite STANDARD v1.2 §5.14. Unit test
`same_digest_ignores_case` (upper vs lower of a real digest) if the existing
`digests` test does not already cover it.

### 5.5 `core/src/validate/approval.rs`

- `APPROVER_KEYS` stays; new `APPROVER_KEYS_1_2` = `APPROVER_KEYS` +
  `"sender_check"`, `"accept_trust_classes"`.
- `check(...)` gains the workflow's target (`semantics::target(wf, header)`,
  S6) and passes `v12: bool` and `declared` to `approver(...)`.
- `approver(value, at, report, declared, v12, loc)`:
  - `unknown_fields(ap, if v12 { APPROVER_KEYS_1_2 } else { APPROVER_KEYS }, …)`:
    in a 1.0/1.1 target (or none declared) the two keys are W604 exactly as
    in 1.1, and nothing else is checked (S6's `newer_features` adds W616);
  - in a 1.2 target, for each of the two keys present:
    `declared.require("identity@1", "'approval.approver.<key>'", |d| loc.locate(d).at("field", "approval.approver.<key>"), report)`;
    stop on V106; then S303 unless a non-empty array of strings, each
    `known_mechanism` (for `sender_check`) or in `TRUST_CLASSES` (for
    `accept_trust_classes`), with a message naming the bad value; reuse
    `identity::{known_mechanism, TRUST_CLASSES}`.
- Unit tests: 1.2, declared and valid → no code; 1.2 undeclared → V106; 1.2
  `[]`, `"x"`, `[1]`, `["robot"]` → S303; `["x-acme.sso"]` accepted; 1.1
  target (and no target) with either key → W604 only, with or without
  `identity@1`, and never V106 or S303.

### 5.6 `core/src/python.rs`

- `PyRun::restore(..., key=None, *, actor_identity=None)` → `restore_with`;
  `RestoreError::Actor` → `ValueError`.
- New `PyRun::resume(&mut self, py, *, attendance="attended", now_ms, actor_identity=None)`:
  parse attendance as in `start`; map `ResumeError` (all three variants) to
  `ValueError` with the variant's message.

### 5.7 `grounded_agency/_core.pyi`

```python
    @staticmethod
    def restore(
        validator: Validator,
        catalog: Any,
        snapshot: dict[str, Any],
        key: bytes | None = None,
        *,
        actor_identity: dict[str, Any] | None = None,
    ) -> Run: ...
    def resume(
        self,
        *,
        attendance: str = "attended",
        now_ms: int,
        actor_identity: dict[str, Any] | None = None,
    ) -> None: ...
```

### 5.8 `grounded_agency/workflows/runner.py`

- `Host.request_approval` docstring: the request's `mode` (meanings), the
  optional `queued_action_id` (present on every request for a queued step a
  resumption re-entered), and that with `identity@1` the response may carry
  `approver_identities` (each an `agent_identity`, one per principal;
  `approvers` then their principals or empty).
- `RunResult.resumable` property: `self.outcome == "deferred"`; docstring of
  `deferred` says the run can be resumed, and that the queued actions of a run
  with any other outcome are abandoned.
- `WorkflowRunner.restore(snapshot, key=None, *, actor_identity=None)`:
  passes it through; docstring states the §5.17 rule and the handoff rule
  (cancel, S2b's `cancel`).
- New `WorkflowRunner.resume(snapshot, key=None, *, attendance="attended", now_ms=None, actor_identity=None) -> _core.Run`:
  restores (no actor check: the resumer may differ), checks `_check_ms`,
  calls `run.resume(...)`; `TypeError`/`ValueError` → `RunStartError`
  (message names `NotDeferred` / `NotKept` cases in words). Docstring:
  resume a saved state once; drive the result with `drive()`; a state saved
  by an earlier version is refused: cancel it and start a new run.

### 5.9 Harnesses

- `core/tests/runtime.rs` `play()`: fixtures read with `exec::read_json`; a
  script entry with `resume` → snapshot with key, `Run::restore`,
  `run.resume(ResumeOptions{attendance (default attended), now_ms: entry.at
  or now, actor_identity})`; no `seen` push. `fill()`: `"{{digest_upper}}"` →
  `action["digest"].to_uppercase()`.
- `tests/test_runner.py::test_runtime_fixture` and
  `tests/test_trace_kinds_doc.py::recorded`: the same two additions. (Option:
  move the Python replay loop into one helper module under `tests/` used by
  both; coordinate with S2b, which changes the harness too.)
- `scripts/gen_runtime_fixtures.py`: helper
  `def resume(attendance="attended", at=None, actor=None)` returning the
  entry; the contributed-fixture key check is unaffected.

### 5.10 `scripts/gen_standard_agents_binding.py` (digest vectors)

- `DIGEST_FIELDS` gains `kind` ("`step`: an approval request of a workflow
  step, with `approval` and, without `shows`, `inputs`; `tool_call`: the
  approval of a tool call (STANDARD v1.2.0 §5.18.7), with `call`") and
  `call` ("For a `tool_call` vector: the call, `{action, capability, args}`;
  `shown` is `[call]`"); `approval` and `inputs` say "for a `step` vector".
- `render_digests()`:
  - each step vector is written `{"name", "kind": "step", "about",
    "approval", ("inputs"), "shown", "canonical", "digest"}`; the existing
    check `shown == [inputs]` runs only for step vectors without `shows`;
  - S1's call vectors (`CALL_VECTORS`) are written `{"name", "kind":
    "tool_call", "about", "call", "shown", "canonical", "digest"}`, with
    `shown = [call]`, `digest = _core.approval_digest(shown)` and the same
    `canonical_json`/SHA-256 cross-check; no executor run;
  - `"standard": "1.2.0"`, `"section": "5.14, 5.18.7"`, `"status":
    "normative"`, description rewritten: "Approval digests (STANDARD v1.2.0
    §5.14 and §5.18.7, normative under §10.3) …"; drop the sentence saying
    the Standard does not state the default and the re-ask object.
- `numbers` vector `about`: "Numbers are written as ECMAScript writes the
  binary64 value, so -0.0, 1.0, 1e+21 and 1e-07 in the JSON text of `shown`
  become 0, 1, 1e+21 and 1e-7. 9007199254740992 is 2^53, the largest
  magnitude section 5.14 allows for an integer, a number written without a
  fraction or an exponent. 1e+21 is written with an exponent, so it is a
  binary64 value and that bound does not apply to it."
- New vector `unresolved_reference` (step): approval
  `{"approver": HUMAN, "shows": ["${current.data.absent}", "${current.data}"]}`
  with value `{"present": 1}` → `shown == [null, {"present": 1}]`. (If the
  validator rejects the path, use a `shows` reference to a step skipped by a
  false condition; the point is the `null` element.)
- Regenerate `tests/conformance/approval/digests.json`. The binding's copy
  (`examples/standard_agents/test/fixtures/approval-digests.json`) is
  deleted by the foundation (S6, RECONCILIATION C21): the TypeScript tests
  read the canonical file in place. The `kind` member and the branching in
  `render_digests()`/`tests/test_approval_vectors.py` land in the foundation
  (FOUNDATION.md F); S2a adds the `unresolved_reference` vector and the
  normative header, S1 the `tool_call` vectors.

### 5.11 TypeScript binding (`examples/standard_agents/`)

- `src/acs/records.ts`:
  - `export interface AgentIdentity { principal: string; kind: 'agent' | 'human' | 'service'; role?: string; model_family?: string; owner?: string; authenticated_by?: string; trust_class?: 'owner' | 'decision_person' | 'system_of_record' | 'own_subagent_report' | 'peer_agent' | 'colleague' | 'external' }`
    (§5.17, `schemas/agent_identity_schema.yaml`).
  - `ApprovalDecision` gains `approver_identity?: AgentIdentity`.
  - `TraceEntry.approval` becomes
    `{ digest: string; approvers: string[]; approver_identities?: AgentIdentity[]; decision_ids: string[] }`;
    doc: `approvers` are the principals of the identities.
- `src/acs/approval.ts`:
  - `export interface ApproverOptions { kind?: AgentIdentity['kind']; ownerId?: string }`.
  - `export function approverIdentity(approver: Approver, request: Pick<ApprovalRecord, 'role'>, options: ApproverOptions = {}): AgentIdentity`
    per `schemas/interop/standard_agents_mapping.yaml` `identity.parties.endpoint_caller`:
    `{principal: 'sa-user:' + approver.id, kind: options.kind ?? 'human', authenticated_by: 'x-acs.sa-caller'}`,
    plus `role: request.role` when the caller's `roles` include it, plus
    `trust_class: 'owner'` when `options.ownerId === approver.id`.
  - `decideApproval(store, approver, digest, decision, now, round?, options?: ApproverOptions)`
    stores `approver_identity: approverIdentity(approver, record, options)` on
    the decision it writes (approvals and rejections).
- `src/acs/grounded.ts`: when a call uses an approval,
  `approvers` = the distinct principals `'sa-user:' + d.approver`, and
  `approver_identities` = the decisions' `approver_identity` values,
  deduplicated by principal (one decision per approver, so no
  contradiction), set only when every counted decision has one (decisions
  stored by an earlier version have none). `GroundedCall.approvers` carries
  the same principals.
- `test/grounded.test.ts`: new case "records who approved a call as attested
  identities": `user('alice', ['release-manager'])` approves a call whose
  binding requires role `release-manager`; the trace entry's `approval` equals
  `{approvers: ['sa-user:alice'], approver_identities: [{principal:
  'sa-user:alice', kind: 'human', role: 'release-manager', authenticated_by:
  'x-acs.sa-caller'}], ...}`; a second decision with `ownerId: 'alice'` adds
  `trust_class: 'owner'`; a caller without the requested role cannot decide
  (existing). Update the four existing expectations `approvers: ['alice']`
  (grounded.test.ts lines 533, 712, 743; interleaving.test.ts line 285) to
  `['sa-user:alice']`.

---

## 6. Tests and conformance fixtures

### 6.1 Runtime fixtures (`scripts/gen_runtime_fixtures.py` → `tests/conformance/runtime/`)

Abbreviations: `CP` checkpoint step, `POLICY` constrain step, `mutate(...)` as
in the generator; `human` = `{"kind": "human"}`; `defer` = approval
`{approver human, when_unattended defer_to_queue}`; `inputs` =
`{"target": "config", "operation": {"set": 1}}`; identities:
`alice = {principal: alice, kind: human, role: release-manager, authenticated_by: directory_id, trust_class: decision_person}`,
`carol` = alice with principal carol, `bob` = alice with principal bob and
role ops, `bot = {principal: bot, kind: agent}`. Catalogs target 1.1 unless a
row says 1.2 (resumption is a host operation and works on 1.1 workflows).
Record `reason` strings are never pinned (S2b's matching does not compare
them); `tests/test_runner.py` asserts the "superseded" reasons (6.4).

| Name | Catalog / script | Pins |
|---|---|---|
| `approval_defaults_partial` | `[CP, POLICY, mutate(approval {approver {kind human, role ops}, expires 1h})]` | Request approver `{kind: human, role: ops}`, `mode: in_session`, `shown: [inputs]`, `expires_at: 3600000`; executed; record `approval.mode` in_session (ACS-10) |
| `approval_out_of_band_unattended` | unattended; mutate approval `{approver human, mode out_of_band, when_unattended skip}` | No `RequestApproval`; record `rejected`; trace `approval_unattended`, `step_skipped` (ACS-44) |
| `approval_digest_any_case` | `approval_case`, decision digest `"{{digest_upper}}"` | Accepted: executed (ACS-11 comparison) |
| `approval_shows_unresolved` | inputs `{flag: boolean}` given false; `observe o` with `condition: "${flag}"`; `CP, POLICY`; mutate approval `{approver human, shows ["${o.observation}", "${flag}"]}` | `shown: [null, false]` (ACS-11 item 1) |
| `approver_identities_by_principal` | `identity@1`; approver `{kind human, min_approvers 2}`; decision `approvers []`, identities `[alice, alice]` (identical) | F502 `rejected`; record `approvers: [alice]`, `approver_identities` of length 1 (an identical repeat counts once) |
| `approver_identity_role` | approver `{kind human, role release-manager, min_approvers 2}`; identities `[alice, bob]` | F502 `rejected`; record `approvers: [alice]`, `approver_identities: [alice]` (only the counted one); bob's role named in the reason (asserted in test_runner.py) |
| `approver_identity_role_met` | same approver; identities `[alice, carol]` | executed; record `approvers [alice, carol]`, `approver_identities` both |
| `approver_identity_kind` | approver human; identities `[bot]` | F502 `rejected`; record `approvers: []`, `approver_identities: []` (ACS-12 kind) |
| `approver_sender_check_needs_identities` | spec 1.2; `identity@1`; approver `{kind human, sender_check [directory_id]}`; decision `approvers [alice]`, no identities | F502 (a 1.2 workflow can require authentication) |
| `approver_sender_check_met` | spec 1.2; approver `{kind human, sender_check [directory_id], accept_trust_classes [decision_person]}`; identities `[alice]` | executed |
| `approver_sender_check_mismatch` | spec 1.2; approver `{kind human, sender_check [directory_id]}`; identities `[alice with authenticated_by session_id]` | F502 `rejected`; record `approvers: []` |
| `approver_trust_class_mismatch` | spec 1.2; approver `{kind human, accept_trust_classes [decision_person]}`; identities `[alice with trust_class colleague]` | F502 `rejected`; record `approvers: []` |
| `approver_fields_ignored_1_1` | spec 1.1; `approval@1` only (no `identity@1`); approver `{kind human, sender_check [directory_id]}`; decision `approvers [alice]`, no identities | The catalog validates (W604, W616: warnings only) and runs; request approver carries `sender_check` as declared; executed (1.1 treatment kept) |
| `approver_identities_without_identity_ext` | only `approval@1`; decision `approvers [alice]`, identities `[bot]` | executed; record has no `approver_identities` (ignored without `identity@1`) |
| `resume_deferred_attended` | unattended; `[retrieve r, CP, POLICY, mutate m (defer)]`; script: retrieve, checkpoint, constrain, `expect Completed deferred` (deferred `[{step 3, action_id "run-1/w/3/0"}]`), `resume {at 3600000}`, `expect RequestApproval {queued_action_id "run-1/w/3/0", approver {kind human}, mode in_session, shown [inputs]}` → approve, `expect CreateCheckpoint {step 3}` → cp2, mutate | End completed; `action_records` exactly `[{action_id "run-1/w/3/0", status executed, approval {decision approved}}]`; `retrieve` not asked again (it ran before the deferral); trace `run_resumed`, `checkpoints_invalidated` (ACS-13 items 1, 5, 6) |
| `resume_deferred_rejected` | as above, decision rejected | Failed F502; record `run-1/w/3/0` `rejected` |
| `resume_reruns_read_ahead` | unattended; `[CP, POLICY, mutate m (defer), retrieve r (target config), verify v (target "${r.data}", conditions [applied])]`; first run: checkpoint, constrain, retrieve → `{data: "before"}`; v deferred (`mutate` precedes `verify`); resume attended: approval → CreateCheckpoint → mutate → `retrieve {step 3}` → `{data: "after"}` → `verify {inputs {target: "after"}}` | `retrieve` asked again after the mutate and before the verify; end completed, `outputs.r.data == "after"` (item 2, ran ahead and read) |
| `resume_keeps_unread_ahead` | `[CP, POLICY, mutate m (defer), observe o (target elsewhere), verify v (target "${m.success: boolean}")]`; first run: checkpoint, constrain, observe; resume: approval, CreateCheckpoint, mutate, verify | `observe` not asked again (no step reads it); `outputs.o` is the first run's; end completed (item 2, ran ahead and unread) |
| `resume_reruns_bound_checkpoint` | Safe Mutation: `[POLICY, CP cp, mutate m (inputs + checkpoint_id "${cp.checkpoint_id}", defer)]`; first run: constrain, checkpoint → `cp1`; resume attended: `InvokeCapability checkpoint {step 1}` → `cp2`, `RequestApproval {shown [{…, checkpoint_id: "cp2"}]}` → approve, `InvokeCapability mutate {inputs {checkpoint_id: "cp2"}}` (no `CreateCheckpoint`: cp2 is used) | End completed; trace `checkpoints_invalidated` (cp1), `checkpoint_created` (cp2), `checkpoint_consumed` (cp2) (item 2, checkpoint step) |
| `resume_unattended_defers_again` | first part as `resume_deferred_attended`; `resume {attendance unattended}` | No request; end deferred; `deferred[0].action_id == "run-1/w/3/0"`; one record, `planned` |
| `resume_unattended_mandate` | unattended; `[CP, POLICY, mutate m (approval {approver {kind standing_mandate, mandate_ref m/nightly}, when_unattended defer_to_queue})]`; first run: request → `unavailable` → deferred; `resume {attendance unattended}` | Request approver `{kind standing_mandate, mandate_ref m/nightly}` with `queued_action_id "run-1/w/2/0"`; approve `[nightly]`; CreateCheckpoint; mutate; record `run-1/w/2/0` executed, `approval.mandate_ref "m/nightly"` (item 5, either attendance) |
| `resume_asks_person_for_mandate` | as above, resume attended | Request approver `{kind: human}` with `queued_action_id`; approve `[alice]`; record `approval.mandate_ref: null`, `approvers [alice]` (item 5). `tests/test_runner.py` also asserts the approver has no `mandate_ref` (subset matching cannot) |
| `resume_nested_continues` | parent `[invoke i (child), observe o, verify v (target "${i.result: object}")]`; child `[retrieve r, CP, POLICY, mutate m (defer)]`; first run: child retrieve, checkpoint, constrain; parent observe; resume | Child `retrieve` and parent `observe` not run again; request `queued_action_id "run-1/w/child/3/0"`; CreateCheckpoint; mutate; then verify; end completed; trace `invoke_resumed` (item 3) |
| `resume_deferred_handler` | the `deferred_handler` catalog; resume; approve the mutate; checkpoint; mutate; handler's nested `inquire` | End completed, outcome `escalated`, cause `R402`; mutate record executed (item 4) |
| `resume_deferred_handler_loop` | the `deferred_handler_before_deferral` catalog (handler `page` at step 2 reads `m`) with a failure mode on `m` (`on_error R402`, `goto_step m`, `max_loops 1`); first run defers m (record n0) and the handler; resume attended: approve m (queued) → CreateCheckpoint → mutate `Error R402` → loop to step 3 → m asked again (new request, no `queued_action_id`) → approve → CreateCheckpoint → mutate → observe | End completed, outcome `completed`, no cause, `deferred: []` (the handler's deferral is superseded and its escalation dropped); records `[{status failed}, {status executed}]` (item 7, loop with a handler below its target) |
| `resume_loop_supersedes` | `[CP, POLICY, mutate m1 (defer), verify v (target "${m1.success: boolean}", failure mode on_error R402, goto_step m1, max_loops 1), mutate m2 (defer)]`; first run defers m1 (n0), v, m2 (n1); resume attended: m1 approved → checkpoint → mutate → verify `Error R402` → loop to 2: m1 asked again (no `queued_action_id`), approved, checkpoint, mutate, verify passes, m2 asked (no `queued_action_id`), approved, checkpoint, mutate | End completed, `deferred: []`; records `[{n0 executed}, {n1 rejected}, {executed}, {executed}]` (item 7, a loop to a step before a queued one); test_runner.py asserts the two later requests carry no `queued_action_id` |
| `resume_failure_keeps_queue` | `[CP, POLICY, mutate m1 (defer), mutate m2 (defer)]`; first run defers both (n0, n1); resume attended: m1 approved → CreateCheckpoint → mutate `Error R402` | End `Failed` R402 at step 2; records `[{n0 failed}, {n1 planned}]`; `deferred: [{step 3, action_id n1}]` (item 7; the run is not resumable, so n1 is abandoned) |
| `resume_new_actor` | `actor_identity {principal agent-a, kind agent}`; unattended defer; `resume {actor_identity {principal agent-b, kind agent}}`; approve | Record `actor_identity.principal == agent-b`; trace `run_resumed` (ACS-35) |
| `resume_skipped_supersedes` | unattended; `[CP, POLICY, mutate m1 (defer), mutate m2 (condition "${m1.success} == false", skip_if_false true)]`; first run defers m1 (n0) and m2 (rule 1; n1); resume; approve m1; CreateCheckpoint; m1 succeeds | m2's condition is now false: skipped, and its record `run-1/w/3/1` has `status: rejected`; m1's record executed; end completed (item 6) |
| `resume_gate_end_supersedes` | `[CP, POLICY, mutate m1 (defer, after-gate end), mutate m2 (defer)]`; resume; approve m1; after-gate `end` fires | End completed (ended at step 2); m2's record `status: rejected` (item 7) |

All are replayed by the Rust harness with snapshot/restore before every
entry, so resumption is also tested across a restore.

### 6.2 Rust unit tests (`core/tests/runtime.rs`, `core/src/exec/mod.rs`)

- `resume_needs_a_deferred_end`: resume on a pending run, a completed run, a
  failed run (the `failure_after_deferral` script, which has a `planned`
  record) → `ResumeError::NotDeferred`.
- `resume_refuses_a_malformed_actor` → `ResumeError::Identity`.
- `resume_refuses_states_it_did_not_keep`: play `deferral_continues` and
  `deferred_in_child` to their deferred end, snapshot, rewrite the state as
  version 1 (drop `ahead`, `parked`, `resume`, `pending_escalation`, `queued`;
  `version: 1`), restore (succeeds), resume → `ResumeError::NotKept` naming
  "ran after" (top-level) and "nested run of step" (child). With S2b, the same
  restored runs can be cancelled.
- `restore_checks_the_actor`: started as A; `restore_with(A)` ok,
  `restore_with(B)` → `RestoreError::Actor`, plain `restore` ok; started
  without an actor, `restore_with(A)` → `Actor`.
- `decision_identities_must_be_well_formed`: with `identity@1`, an element
  that is not an `agent_identity`, a non-list, two different identities for
  one principal, and `approvers` that differ from the principals →
  `SubmitError::Malformed`, and `run.next()` unchanged; two identical
  identities for one principal are accepted; without `identity@1` the same
  responses are accepted.
- `version_1_snapshots_restore`: a snapshot whose state has `version: 1` and
  none of the new fields restores and runs to the end; new snapshots carry
  version 2.
- `resume_twice_is_two_runs` (documentation test): resuming two copies of one
  state yields two identical requests; asserts nothing beyond determinism, and
  its comment points at the §5.14.1 MUST for hosts.
- `read_json_bounds_integer_literals` (`exec/mod.rs`): `[9007199254740992]`,
  `[-9007199254740992]`, `[1e21]`, `[1.5]`, `["123456789012345678901"]` read;
  `[9007199254740993]`, `[100000000000000000000000]` (beyond 64 bits),
  `{"a":-9007199254740993}` refused.

### 6.3 Validator tests

- `core/src/validate/approval.rs` unit tests (section 5.5).
- `tests/fixtures/pass_approver_identity.workflow_catalog.yaml`
  (`spec_version: "1.2"`, `approval@1` + `identity@1`, approver with both
  fields), no codes.
- `tests/fixtures/fail_approver_identity_undeclared.workflow_catalog.yaml`
  (`spec_version: "1.2"`, without `identity@1`) → `V106`.
- `tests/fixtures/fail_approver_identity_vocabulary.workflow_catalog.yaml`
  (`spec_version: "1.2"`, `sender_check: []` and
  `accept_trust_classes: [robot]`) → `S303`.
- `tests/fixtures/warn_approver_identity_1_1.workflow_catalog.yaml`
  (`spec_version: "1.1"`, `approval@1` only, approver with `sender_check`) →
  valid, warnings `[W604, W616]`, no error.
- `tests/fixtures/EXPECTATIONS.json` entries for the four.

### 6.4 Python tests

- `tests/test_runner.py`:
  - `test_resume_a_deferred_run` (a `Host` that approves;
    `runner.run(..., attendance="unattended")` → `resumable`; snapshot;
    `runner.resume(snapshot, attendance="attended")`; `drive` → completed, one
    record with the queued `action_id`);
  - `test_resume_refuses_other_outcomes`, including
    `test_resume_refuses_a_failed_run_with_planned_records`: a run that
    fails after deferring (the `failure_after_deferral` catalog) ends with a
    `planned` record; `runner.resume` raises `RunStartError` and the saved
    state is unchanged;
  - `test_resume_refuses_an_old_state` (a version-1 rewrite as in 6.2) →
    `RunStartError` naming what is not kept;
  - `test_restore_refuses_another_actor`;
  - `test_resumed_mandate_step_asks_a_person` (no `mandate_ref` on the
    request);
  - `test_superseded_records_say_why`: replays `resume_skipped_supersedes`,
    `resume_gate_end_supersedes`, `resume_loop_supersedes` and
    `deferral_superseded_by_loop` and asserts each `rejected` record's
    `reason` starts with `"superseded"`;
  - `test_requests_outside_the_queue_name_no_queued_action`: in
    `resume_loop_supersedes` and `resume_deferred_handler_loop`, the requests
    after the loop have no `queued_action_id`;
  - `test_refused_approvers_are_named`: in `approver_identity_role`, the
    record's `reason` names `bob` and the role.
- `tests/test_approval_vectors.py`: `test_every_vector_has_a_known_kind`;
  executor replay over `kind == "step"` vectors only; the independent
  RFC 8785 check over all vectors; for `tool_call` vectors,
  `shown == [call]` and `_core.approval_digest(shown) == digest` (S1);
  `test_the_vectors_are_normative_and_named` (`standard == "1.2.0"`,
  `status == "normative"`); docstring cites v1.2.0.
- `tests/test_trace_kinds_doc.py`: no code change beyond the replay entry; it
  fails until the guide lists `run_resumed` and `invoke_resumed`.

### 6.5 TypeScript tests

Section 5.11: the new `grounded.test.ts` case and the four updated
expectations; `canonical.test.ts` reads the regenerated
`approval-digests.json` (all vectors carry `canonical` and `digest`, so it
needs no change beyond ignoring `kind`).

---

## 7. Informative documentation

### 7.1 `docs/guides/RUNNING_WORKFLOWS.md`

- Actions table, `RequestApproval` row: "asks `approver` about `shown`, in
  `mode` (`in_session`: whoever attends the run, in its session;
  `out_of_band`: a separate channel whose approvers need not attend; keep the
  run's snapshot while you wait). `queued_action_id` names the queued action
  a resumed run is asking about, on every such request." Response column: add
  "with `identity@1`, optionally `approver_identities` (each an
  `agent_identity`, one per principal; `approvers` then empty or their
  principals)".
- "What the executor enforces" → **Approvals**: add the default request
  (person, in session, `[inputs]`, no expiry), the digest rule (array,
  RFC 8785, lowercase hex, any case accepted; integers, numbers written
  without fraction or exponent, at most 2^53), the identity counting and
  checks with `identity@1` (the record lists the approvers that counted), the
  approver fields that take effect in a workflow that declares
  `spec_version: "1.2"`, and "A run that ends `deferred` can be resumed:
  see [Resuming a deferred run](#resuming-a-deferred-run)."
- After the `actor_identity` paragraph: "A run keeps its actor: restore it
  with `actor_identity=` and the executor refuses another principal. When
  another agent takes over the conversation (a handoff), cancel the run
  (`run.cancel(...)`) if it has not ended, and start a new one under the new
  agent's identity; a run that ended `deferred` may instead be resumed under
  it."
- New subsection under **Driving a run yourself**: `### Resuming a deferred run`,
  with the code:
  ```python
  run = runner.start("nightly_sweep", inputs, attendance="unattended")
  result = runner.drive(run, host)
  if result.resumable:
      saved = run.snapshot(key=b"secret")   # keep it with the queue entries
  # ... later, when the approvers can be asked, once per saved state:
  run = runner.resume(saved, key=b"secret", attendance="attended",
                      actor_identity=operator_identity)
  result = runner.drive(run, host)
  ```
  and prose for §5.14.1 in host terms: which steps run (the deferred ones;
  a step that ran ahead of them is run again when one of them reads it, so a
  verify reads the world after the change; a checkpoint step a queued
  mutation binds is run again for a fresh restore point; everything else
  keeps its output); the person asked in place of a mandate; the request's
  `queued_action_id` and the record kept by `action_id`; checkpoints asked
  again; resume one saved state once; a run that failed, escalated or needs a
  replan cannot be resumed and its `planned` records are abandoned (close
  your queue entries; start a new run if the work is still wanted); and "a
  state saved by an executor before this release cannot be resumed (it did
  not keep the nested runs of deferred `invoke` steps or which steps ran
  ahead): `resume` refuses it; cancel the run and start a new one".
- Trace field table: `step` "null on `run_started`, `run_resumed` and
  `run_finished`". Trace kinds table rows:
  - `run_resumed` | A host resumes a run that ended `deferred` (§5.14.1); `actor` and `previous_actor` are principals or null | `attendance`, `actor`, `previous_actor`
  - `invoke_resumed` | A resumed run continues the nested run of a deferred `invoke` step | `workflow`
- Conformance section: the `resume` script entry and the `{{digest_upper}}`
  placeholder; the digest vectors paragraph says they are normative (§10.3),
  with a `kind` per vector.

### 7.2 `docs/guides/ORCHESTRATION_EXTENSIONS.md`

- Approval section: replace the `mode` comment with the two meanings; add
  bullets "With no `approval` field…" (the default), "What the digest covers"
  (the array; `[inputs]`; the re-ask element; the integer rule), and a new
  bullet **Carrying out a queued action**: "Resume the run (`runner.resume`):
  the deferred steps run again, each asked afresh (of a person when someone
  attends, even if its approver is a mandate), and its `planned` record
  becomes `executed`, `rejected` or `expired` under the same `action_id`.
  Steps that ran ahead of the deferral and that those steps read run again
  first, in step order, so a `verify` after the `mutate` reads the world
  after it; a `checkpoint` step whose id the `mutate` binds runs again too.
  A run that ended any other way cannot be resumed; a new run of the workflow
  does not touch the old run's queue." Extend the nightly sweep example's
  text with that step.
- Sender identity section: a short example of an approver that requires
  authenticated approvers, in a 1.2 workflow:
  ```yaml
  spec_version: "1.2"            # the approver fields need a 1.2 target
  workflow_extensions:
    requires: [approval@1, identity@1]
  # ...
  approval:
    approver:
      kind: human
      role: release-manager
      min_approvers: 2
      sender_check: [directory_id]
      accept_trust_classes: [decision_person]
  ```
  with sentences on counting by principal, on what the check does and does
  not prove, and on why the target matters (a 1.1 consumer would ignore the
  fields; it refuses a 1.2 workflow instead).

### 7.3 Other

- `spec/CONFORMANCE.md`: move the approval digest bullet from "Informative
  vectors" to the normative list (§10.3), mentioning `kind`; delete the
  paragraph that says §5.14 does not state the default request; mention the
  resumption fixtures. (S2b restructures this file for the executor class;
  merge.)
- `docs/integrations/standard_agents.md`:
  - `mode` row (line 534): "Decisions arrive through an authenticated
    endpoint, separate from the conversation: `out_of_band` (§5.14 of 1.2)".
  - Handoff row (line 186): "The end of one actor's run and the start of
    another's: the host cancels the source agent's ACS run if it has not
    ended (§5.17, §5.19.5 of 1.2); a run that ended `deferred` may instead be
    resumed under the agent that took over (§5.14.1). A saved run is never
    restored under it."
  - `approver.kind: human` row: "The authenticated caller of the endpoint,
    recorded as an approver identity per the identity map
    (`endpoint_caller`): principal `sa-user:<id>`, `kind: human` as the
    deployment's assertion, `role` when the caller holds the requested one,
    `authenticated_by: x-acs.sa-caller`. The trace entry's `approval` carries
    `approver_identities` and their principals in `approvers` (§5.17 of 1.2)".
- `schemas/interop/standard_agents_mapping.yaml` handoff `notes`: replace the
  last two sentences with "At a handoff the host cancels the source agent's
  ACS run if it has not ended (Standard v1.2 §5.17, §5.19.5), and a new run
  starts under the target's `actor_identity`; a run that ended deferred may
  instead be resumed under the target's identity (§5.14.1), which records the
  change. A saved run is never restored under the agent that took over."

---

## 8. Backward compatibility and migration

| Change | 1.1 workflows and runs | Classification |
|---|---|---|
| §5.14 default request, digest input, `expires` from request, number rule wording, mode meanings | Unchanged: the text states what the 1.1 reference executor does; no run changes | Clarification (applies to 1.0, 1.1, 1.2) |
| Digest vectors normative, `kind` per vector | The reference executor already passes all of them; `kind` is a new member of the vector file | Conformance addition |
| `approver_identities` on `Decision`; contradictory identities malformed; counted approvers recorded | Ignored without `identity@1`; with `identity@1`, only used when a host sends it (a 1.1 host never does) | Opt-in (host + extension) |
| Approver `sender_check` / `accept_trust_classes` | Take effect only in a workflow that targets 1.2. In a 1.0/1.1 target they keep their 1.1 treatment exactly (unknown field W604, ignored by validator and executor; the request still carries the approver as declared), plus S6's W616 (a warning). A 1.1-valid workflow stays valid and runs as before; a 1.1 consumer refuses a 1.2 workflow (V109), so the requirement fails closed | Opt-in (`spec_version` 1.2) + warning-first for 1.0/1.1 targets |
| `ActionRecord.approval.approver_identities`, descriptions | Optional member; descriptions only | Compatible addition (§11.4) |
| Resumption (`Run.resume`, `queued_action_id`, in-place record update, re-run of read steps that ran ahead) | A run behaves exactly as in 1.1 until a host resumes it; no field, record or action of a first run changes (`Frame.ahead` is bookkeeping in the state) | Opt-in (host operation) |
| Queued actions of runs that did not end `deferred` are abandoned | Statement only: 1.1 executors already leave them `planned` and offer no way to carry them out | Clarification |
| Nested deferred runs kept (`Frame.parked`), `Frame.ahead` | Snapshot content only; actions, records and outcome unchanged | Compatible (snapshot version 2; version 1 still restores and runs, but a version-1 state with deferrals cannot be resumed, which no 1.1 executor offered either) |
| `deferred_cause` reads nested caps of deferred steps only | Identical in every first run (every key is a deferred step) | No behaviour change |
| Restore actor check | Only when the host names an actor | Opt-in (new optional argument) |
| Handoff: cancel the run | Host obligation using S2b's opt-in cancel; no executor behaviour change | New host rule (1.2) |
| TypeScript binding: `approvers` become `sa-user:` principals, `approver_identities` added | Binding record content (example code), not a Standard artifact | Binding change, noted in CHANGELOG |

No new warning or error applies to an existing catalog, so no repository
catalog or example (`schemas/workflow_catalog.yaml`, `schemas/workflows/*.yaml`,
`examples/*.workflow_catalog.yaml`, `tests/fixtures/*`) needs migrating under
`--strict`. Existing runtime fixtures stay valid: matching is by subset, and
no first-run action, record or end changes. `tests/test_approval_vectors.py`
changes its metadata assertion (informative → normative) and gains the `kind`
branch.

---

## 9. RFC text: RFC-0006, Part A (approval, deferral and run identity)

S2b supplies the header and Part B (host protocol). The combined file is
`spec/RFC-0006-host-protocol-approval-and-runs.md` with
`**Status:** Accepted`, `**Target:** Standard v1.2.0`,
`**Date:** 2026-11-15`. Each required section below is Part A's contribution;
merge it under the same heading as S2b's.

```markdown
## Summary

Part A settles what an approval request is and how a deferred action is
carried out. It states the request for a step without an `approval` field,
the exact input and form of the approval digest, the number rule and the
meaning of `in_session` and `out_of_band` in §5.14; lets a host attest who
approved, with `identity@1`, and lets a workflow that targets 1.2 require
authenticated approvers (§5.17); defines resumption of a run that ended
`deferred`, including which steps run again so that nothing runs against
stale results, and what becomes of the queued actions of runs that cannot be
resumed (new §5.14.1); and states that a run keeps its actor while it
continues, that a host cancels it at a handoff, and that only a resumption may
change it (§5.17). It answers findings ACS-10, ACS-11, ACS-12, ACS-13, ACS-35
and ACS-44 of the
[Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
By the maintainer's decision it is Accepted and ships in Standard 1.2.0.

## Motivation

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

- How a host authenticates an approver or delivers an `out_of_band` request.
- A queue store, or a time limit on how long a deferred run stays resumable
  (Open question 1).
- Tool-call approval itself (RFC-0005 decision 5); Part A only supplies the
  record member and the vector shape it shares.
- The host protocol schema, the run snapshot format and host obligations such
  as a single writer per run and cancellation (Part B).

## Key decisions

### A1) The default request is stated (ACS-10)

A step that requires approval and has no `approval` field is asked as if it
declared `approval: {approver: {kind: human}}`: a person, in session, shown
its resolved inputs, with no expiry and no recheck, failing unattended. A
partial field takes each omitted member's default, and `expires` runs from
the request. Reason: this is what the reference executor does, so the text
changes no run.

### A2) The digest input is stated, and its vectors are normative (ACS-11)

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

### A3) The modes are defined (ACS-44)

`in_session` asks whoever attends the run, in its session; `out_of_band` asks
through a separate channel whose approvers need not attend, and the decision
may outlive the session. The mode changes nothing the executor checks. A human
is still never asked in an unattended run; defer and resume instead.

### A4) Approvers can be attested and, in 1.2 workflows, required (ACS-12)

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

### A5) A deferred run is resumed (ACS-13)

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

### A6) A run keeps its actor (ACS-35)

A host that restores a run may name the actor, and the executor refuses
another principal. At a handoff the host cancels the run (Part B) unless it
ended `deferred`, and the new agent starts its own; a deferred run may
instead be resumed under the new actor, which the trace and later records
show.

### A7) Conformance

Runtime fixtures pin the default request, the mode in an unattended run, the
digest comparison and an unresolved `shows` value, approver identity counting
and checks (including mismatched authentication and trust class, and the 1.1
treatment of the approver fields), and resumption (attended, rejected,
unattended, a mandate step in either attendance, nested, deferred handler, a
new actor, steps that ran ahead read and unread, a bound checkpoint, a loop, a
loop with a deferred handler, a gate `end`, a failure). The runtime fixture
format gains a `resume` entry.

## Backward compatibility

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
the executor's snapshot gains optional fields (version 2; version 1 still
restores, and a version-1 state with deferrals cannot be resumed, which no
earlier executor offered). A6 adds an optional argument to restore and a host
rule that uses Part B's opt-in cancel. No warning or error is added for any
existing catalog, so none needs migrating.

## Conformance test updates

- `tests/conformance/approval/digests.json`: status normative, Standard
  1.2.0, `kind` on every vector, a vector for an unresolved `shows`
  reference, the `numbers` vector's note on `1e+21` (and RFC-0005's
  `tool_call` vectors).
- Runtime fixtures: `approval_defaults_partial`,
  `approval_out_of_band_unattended`, `approval_digest_any_case`,
  `approval_shows_unresolved`, ten `approver_*` fixtures and sixteen
  `resume_*` fixtures; the `resume` script entry and the `{{digest_upper}}`
  placeholder in every replayer.
- Validator fixtures for the approver fields (pass, V106, S303 in 1.2
  targets; W604 and W616 in a 1.1 target).
- Unit tests for resumption errors (including a version-1 state), the restore
  actor check, malformed and contradictory approver identities, version-1
  snapshots and the integer-literal rule; Python tests for a failed run's
  abandoned queue and the "superseded" reasons; a TypeScript test for
  approver identities on tool-call records.

## Alternatives considered

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
  version-1 state by guessing what it did not keep. Repeats the nested run's
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
```

---

## 10. Dependencies on other workstreams

- **S2b (host protocol, RFC-0006 Part B).**
  - The host protocol section number (§5.19, final) in sections 2.2-2.4,
    and the text there on keeping and restoring a run's state, which
    `out_of_band` and §5.14.1 refer to.
  - **Cancel (§5.19.5, R408)**: the handoff rule (§5.17) and the refusal of
    states that do not keep what resumption needs both send the host to it;
    a cancelled run's `planned` records become `cancelled`, as §5.14.1 says.
    S2b's `cancel` clears the S2a frame fields (`parked`, `resume`; also
    `pending_escalation` and `ahead`, which this revision adds) and must
    accept a restored version-1 state that ended `deferred`.
  - The host protocol schema must carry: `RequestApproval.queued_action_id`;
    `Decision.approver_identities` (one identity per principal);
    the run operations `resume` and `restore(..., actor_identity)`; snapshot
    version 2 with `Frame.resume`, `Frame.parked`, `Frame.pending_escalation`,
    `Frame.ahead`, `StepState.queued` (a single version bump if S2b also
    changes the snapshot); trace kinds `run_resumed` and `invoke_resumed`.
  - The single-writer obligation (ACS-31) that §5.14.1's "MUST NOT resume the
    same saved state twice" relies on.
  - `ActionRecord.approval.decision_id` (ACS-37) and the `cancelled` status
    in the same `world_state_schema.yaml` 1.2.0 bump.
  - The executor conformance class that makes runtime fixtures normative, and
    the fixture format: the `resume` entry and the `{{digest_upper}}`
    placeholder (already in S2b's §10.5 list); record and deferral `reason`
    not compared (S2a's fixtures pin `status` only); harness changes in
    `core/tests/runtime.rs`, `tests/test_runner.py`,
    `tests/test_trace_kinds_doc.py` to be merged. If S2b adds a refused-
    response entry, S2a's malformed-decision tests move into fixtures (Open
    question 5).
  - `spec/CONFORMANCE.md` and RFC-0006 are shared files.
- **S6 (versioning).**
  - Support for `spec_version: "1.2"` in the validator; `semantics::target(wf,
    header)` and the header passed to `prepare` (S2a's
    `Workflow.targets_1_2` and `approval::check` use them).
  - The §11.5 rule that rules for 1.2 targets apply only when 1.2 is declared,
    and W616 listing `approval.approver.sender_check` and
    `.accept_trust_classes` as 1.2 features, with `first_use` at
    `steps[i].approval.approver.<key>`; in a 1.0/1.1 target S2a's validator
    still reports W604 for the same field.
  - S6's JSON-text entry points (WASM/TypeScript core, `catalog.parse` and
    response submission) read host values with `exec::read_json`.
- **S1 (RFC-0005, tool-calling hosts).**
  - Digest vector shape: S1's vectors carry `kind: "tool_call"` and
    `call: {action, capability, args}` with `shown == [call]` and no
    `approval`/`inputs`; `render_digests()` writes them after the step
    vectors; `tests/test_approval_vectors.py` branches on `kind`. §10.3's
    paragraph (section 2.6) covers both kinds.
  - Tool-call approval records (§5.18.8) may carry
    `approval.approver_identities` with `approvers` their principals (§5.17
    sentence in section 2.4(b)); §5.18.7's "distinct approvers, as the host
    authenticated them" reads "counted by principal when identities are
    attested". The TypeScript changes in section 5.11 (`records.ts`,
    `approval.ts`, `grounded.ts`) are merged with S1's edits to the same
    files.
  - `_core.approval_digest` (S1) is used by `render_digests()` for call
    vectors; one name if both add a canonicaliser binding.
  - RFC-0005 5.6 ("the host's own prompt … `in_session`") matches the
    `in_session` definition.
- **S5 (checkpoints).** A resumption is an execution boundary: checkpoints
  before it authorise nothing after it (§5.14.1 item 1), and a checkpoint
  step whose invalidated checkpoint a re-entered mutation binds runs again
  (item 2), consistent with S5's checkpoint validity rules and RFC-0005
  decision 4.3; a `rollback` keeps the restore point it binds.
- **S4 (secrets).** If S4 redacts secrets from records or requests, the
  approval digest stays over the unredacted shown values (§5.14), and a
  redacted `shown` must say so.
- **Foundation.** `spec/STANDARD-v1.2.0.md` base and the shared
  `world_state_schema.yaml` 1.2.0 version bump.
