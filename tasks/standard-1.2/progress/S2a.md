# S2a progress: approval, deferral and run identity

Design: `tasks/standard-1.2/designs/S2a.md`. Base: tag `round3/S2a-base`
(692f632). Branch `round3/b` in the worktree `/home/user/acs-b`.

## Findings (part 1)

- [x] ACS-10 default request (§5.14 text; fixture `approval_defaults_partial`)
- [x] ACS-11 digest input (§5.14 text, §10.3 normative vectors, `kind`, `unresolved_reference`, `approval_digest_any_case`, `approval_shows_unresolved`)
- [x] ACS-44 `mode` meanings (§5.14 text, schema descriptions, `approval_out_of_band_unattended`)
- [x] ACS-12 approver identities (executor, validator, fixtures, binding)
- [x] ACS-13 resumption (§5.14.1, executor `resume`, fixtures)
- [x] ACS-35 actor continuity (§5.17, `restore` actor, `resume` actor, handoff docs)

## Standard text (part 2)

- [x] §5.9 `identity@1` row
- [x] §5.14 replaced
- [x] §5.14.1 Resuming a Deferred Run
- [x] §5.17 (a) sentence, (b) **Approvers**, (c) Always ask, (d) **Actor**
- [x] §6.3 last paragraph
- [x] §10.3 digest-vector paragraph
- [x] Appendix D.2 entries

## Schemas (part 3)

- [x] `world_state_schema.yaml` 1.2.0 members and descriptions (foundation landed them; verify)
- [x] `workflow_catalog.schema.json` approver fields, `mode`, `expires` (foundation; verify)
- [x] `host_protocol.schema.json` `queued_action_id`, `approver_identities` (foundation; verify)

## Implementation (part 5)

- [x] `core/src/exec/mod.rs`: `RequestApproval.queued_action_id`, `Decision.approver_identities`, `Frame.{resume,parked,pending_escalation,ahead,queued}` (`Queued`; was `StepState.queued`, review round 1), `ResumeOptions`, `ResumeError`, `RestoreOptions`, `RestoreError::Actor`, `restore_with`, `resume`, `not_kept`, `check_state` additions
- [x] `core/src/exec/machine.rs`: identities in `submit`, `record` in place, `approval` (person, queued id), `decide` (counting, `meets`), `begin`, `settle_queued`, `next_step`, `resume`/`reopen`, `end_frame` park, `end_run`, `escalate`, `undefer_from`, `deferred_cause`, `defer_step`, `undefer_nested`, `invalidate_checkpoints` returns ids
- [x] `core/src/exec/program.rs`: `Workflow.targets_1_2`
- [x] `core/src/exec/canonical.rs`: doc comment, `same_digest_ignores_case`
- [x] `core/src/validate/approval.rs`: `APPROVER_KEYS_1_2`, V106/S303 in 1.2 targets, unit tests
- [x] `core/src/validate/semantics.rs`: W616 `FEATURES` entries for the two approver fields
- [x] `core/src/python.rs`: `restore(..., actor_identity)`, `resume(...)`
- [x] `grounded_agency/_core.pyi`
- [x] `grounded_agency/workflows/runner.py`: docstrings, `RunResult.resumable`, `restore(actor_identity)`, `resume`
- [x] Harnesses: `core/tests/runtime.rs`, `tests/runtime_replay.py` (`resume` entry, `{{digest_upper}}`), `scripts/runtime_fixtures/helpers.py` `resume()`
- [x] `scripts/gen_standard_agents_binding.py`: `unresolved_reference`, `numbers` note, normative header
- [x] TypeScript binding: `records.ts`, `approval.ts`, `grounded.ts`

## Tests (part 6)

- [x] Runtime fixtures (`scripts/runtime_fixtures/s2a.py`): approval_*, approver_*, resume_*
- [x] Rust tests: resume errors, NotKept, restore actor, decision identities, version-1 snapshots, resume twice, read_json
- [x] Validator fixtures: pass/fail/warn approver identity + EXPECTATIONS.json
- [x] Python tests: `tests/test_runner.py` additions, `tests/test_approval_vectors.py`
- [x] TypeScript tests: `grounded.test.ts` case, updated expectations

## Documentation (part 7)

- [x] `docs/guides/RUNNING_WORKFLOWS.md`
- [x] `docs/guides/ORCHESTRATION_EXTENSIONS.md`
- [x] `spec/CONFORMANCE.md`
- [x] `docs/integrations/standard_agents.md`
- [x] `schemas/interop/standard_agents_mapping.yaml` handoff notes

## Other

- [x] RFC-0006 Part A (`spec/RFC-0006-host-protocol-approval-and-runs.md`)
- [x] CHANGELOG `[Unreleased]` entries with Upgrading notes
- [x] Findings ACS-10, -11, -12, -13, -35, -44 status `fixed` with resolutions
- [x] Full F6 set green (validators, generators `--check`, pytest, Rust, npm package/binding/site, check-runs, axe)

## Deviations

1. **Snapshot version (C34).** `SNAPSHOT_VERSION` stays 1: RECONCILIATION C34
   bumps it once, in S2b. Every member S2a adds to the saved state
   (`Frame.resume`, `Frame.parked`, `Frame.pending_escalation`,
   `Frame.ahead`, `Frame.queued`) is optional and left out while it has
   its default, and `Frame.ahead` is `None` while nothing of the frame is
   deferred, so the state of a run that never deferred is byte for byte what
   it was (checked over the 175 earlier fixtures: only the snapshots of runs
   with deferrals differ, by `ahead` and `parked`). A state with deferrals
   saved before S2a has no `ahead`, which is how `Run::resume` tells it
   (`ResumeError::NotKept`), instead of the design's "version 1". The Rust
   test `resume_refuses_states_it_did_not_keep` strips the members rather
   than rewriting the version; `version_1_snapshots_restore` became
   `states_without_resumption_members_restore`.
2. **`Program::build` takes the header.** `Workflow.targets_1_2` needs the
   catalog header's version, so `Program::build(ctx, catalog, root, header)`
   gains it (the only caller, `Run::prepare`, has it). `semantics::target`
   lost its `dead_code` allowance.
3. **A parked frame reopened but not continued keeps its list.** The
   design's `reopen` emptied a parked child's `deferred` list when its
   parent was reopened; when the invoke step was deferred again before the
   child continued, a later resumption would have found nothing to run in
   it. `reopen` now leaves a frame that already has a resumption list as it
   is (nothing it reads has changed since). A re-entered invoke step's
   `nested_caps` entry is dropped when its nested run continues, not at
   re-entry, so a re-deferral keeps the ontology ordering; `check_state`
   accepts `nested_caps` keys of the resumption list.
4. **`queued_action_id` while the record is planned.** *Withdrawn in review
   round 1 (issues 1 and 5):* a re-entered step now keeps its queued action
   until it goes on (`Frame.queued`), so every request of the step names it
   and is put to a person when attended, and every decision updates the
   queued record in place, as §5.14.1 said all along.
5. **`checkpoints_invalidated` at a resumption** has `step: null` (the
   resumption is not a step); the trace guide says so.
6. **Validator fixture name.** `warn_approver_identity_1_1` is
   `pass_approver_identity_1_1_warn`: the conformance suite and the site
   count validator fixtures by their `pass_`/`fail_` prefix
   (`pass_soft_requires_warn` is the existing pattern).
7. **The digest vectors' `unresolved_reference`** uses the design's first
   choice, `${current.data.absent}`; the validator accepts it.
8. **Binding endpoint.** `approvals.post.ts` passes the thread owner
   (`ownerId: state.userId`) so that the owner's decisions carry
   `trust_class: owner`, as the identity map says.
9. **Site figures.** The 1.2.0 page's figure-gap sweep failed on three runs
   in §5.14/§5.14.1, one in §5.17 and one through §10.3. Five figures were
   added (no exemptions): replays of `approval_out_of_band_unattended`
   (§5.14, after the modes), `resume_reruns_read_ahead` and
   `resume_skipped_supersedes` (§5.14.1), "Who counts as an approver" from
   `approver_identity_role` (§5.17) and "The approval digest vectors"
   (§10.3). The replay reads `resume` entries and a run's end before a
   resumption (`loadRuntimeFixture`, `run-replay.ts`); `approvalPlans`
   finds the plans list rather than taking §5.14's first list; the
   `deferral-replay` slot names list 3.
10. **W616 names.** The two features are reported as "approver
    'sender_check'" and "approver 'accept_trust_classes'" at
    `steps[i].approval.approver.<key>`.
11. **Orphaned deferrals across two resumptions.** The design's orphan rule
    ("a path through a step not in its frame's `deferred`") would supersede
    the queued actions of a kept nested run that an earlier resumption had
    reopened but not continued (its steps are in its resumption list, not
    in `deferred`): a resumption that escalates before the invoke step
    continues, and ends deferred again through its handler. A step still
    in the resumption list counts as deferred; fixture
    `resume_nested_queue_after_escalation` pins it (it fails without the
    rule).
12. **A recovery loop during a resumption (review round 1, issue 6).** The
    design's item 7 returned the run to normal flow from the loop's target,
    superseding every queued step not yet re-entered and the deferred
    handler. Every step after the target then ran again, so a step that ran
    ahead (`after_deferral: run`, a mandate-approved `send`, an `audit`)
    acted twice. Now the loop runs again the steps from its target to the
    step that looped (prepended to `Frame.resume`, handlers left out), and
    the resumption goes on with its list: only what the loop runs again is
    undeferred or superseded, the queued steps after it keep their actions,
    and a deferred handler still runs last with its cause. Outside a
    resumption loops are unchanged. Fixtures `resume_loop_supersedes` (now
    a loop over a step deferred again) and `resume_deferred_handler_loop`
    changed; the old `resume_loop_supersedes` became `resume_loop_goes_on`.
    Recorded in FOUNDATION-notes for S2b (`Frame.queued`).
13. **Digest vectors say what a step shows from (review round 1, issue 4).**
    A `step` vector with `shows` gives `bindings` (the workflow input
    `setting` and the store `current`), and the recheck vector
    `recheck_read`; §10.3's executor MUST is stated against them.

## Review round 1

1. **High: a re-asked resumed step went to the mandate, named no
   `queued_action_id`, and ran under a new record.** Real (reproduced with
   the reviewer's script). Root cause: `record()` took the link
   (`cur.queued.take()`) at the first decision and `approval()` named it
   only while the record was `planned`. Fixed: the link is `Frame.queued`
   (`Queued {step, record}`), set when a resumption re-enters the step,
   kept through a re-ask and a retry, closed when the step goes on, is
   deferred again or the run leaves it (`settle_queued`); `approval()`
   asks a person and names the action on every request; `record()` updates
   the queued record in place whatever its status (dropping `reason` and
   `reason_code`). §5.14.1 items 5 and 6 now say "until the step goes on"
   and that every decision lands on that record (the trace keeps each).
   Fixture `resume_recheck_reask` (mandate approver, attended: the re-ask
   is `{kind: human}`, names `run-1/w/2/0`, one `executed` record); test
   `test_a_queued_step_names_its_action_until_it_goes_on`; Rust test
   `a_resumed_step_keeps_its_queued_action_in_the_state`. Both fail on the
   previous executor.
2. **Low: two superseding rules had no fixture.** Real (coverage only; the
   behaviour was right). Fixtures `resume_nested_failure_supersedes` (a
   nested run that deferred and failed under an `after_deferral: run`
   invoke whose escalation's handler was deferred: "superseded: the nested
   run it was queued in failed") and `resume_escalation_supersedes_handler`
   (a re-entered step escalates while a deferred handler holds a queued
   action: "superseded: another escalation took precedence", and the
   handler runs as a new action), plus `resume_replan_keeps_queue` for the
   replan half of item 7. `test_superseded_records_say_why` is
   parametrised and pins each fixture's exact reasons.
3. **Low: ACS-13 said sixteen `resume_*` fixtures.** Real. The resolution
   now says twenty-three (this round adds six), as do RFC-0006 and the
   CHANGELOG (37 S2a runtime fixtures).
4. **Low: §10.3's executor MUST could not be checked from the vector file
   for `shows` vectors.** Real: the replay read the resolved values back
   from `shown`. Fixed at the generator: each `step` vector with `shows`
   has `bindings` and the recheck vector `recheck_read`, described in the
   file's `fields`; §10.3 and spec/CONFORMANCE.md state the MUST against
   them; `tests/test_approval_vectors.py` replays from them alone and
   `test_a_step_vector_says_what_its_step_shows_from` checks every vector
   has the members its step needs.
5. **Medium: a recheck re-ask or a retry of a re-entered queued step broke
   the queue link.** Same root cause as 1, fixed with it. Retry fixture
   `resume_retry_keeps_queue`: both requests name `run-1/w/2/0`, are put
   to a person, and the record ends `executed` (it ended `failed` beside a
   new `executed` record before). `resume_deferred_handler_loop` now pins
   the retry naming the same action too.
6. **Medium: a recovery loop during a resumption re-ran what ran ahead.**
   Real (the reviewer's script delegated twice). Fixed as the reviewer
   proposed: `undefer_from` and `recover` work on `rerun(target)`, the
   steps from the target to the step that looped, during a resumption,
   and prepend them to the resumption list instead of clearing it. §5.14.1
   item 7 rewritten (and item 2 points to it); RFC-0006 A5 and Alternatives
   updated; deviation 12. `resume_retry_keeps_queue` pins a single
   `delegate` invocation (the script is exact, and
   `test_a_loop_during_a_resumption_does_not_repeat_what_ran_ahead` checks
   the run ends with nothing more asked); `resume_loop_goes_on` pins that
   the queued step after the loop keeps its action.
7. **Low: the binding recorded approvers whose approvals no longer
   counted.** Real. `countedDecisions(record, now)` in
   `src/acs/approval.ts` is now the one rule: `approvalState` counts with
   it, and `grounded.ts` builds `approvers`, `approver_identities` and
   `decision_ids` from it at the time the request was found approved.
   Vitest case "records only the approvers whose approvals still count
   when the call runs" (alice at 0, bob at 50, call at 70: only bob).
8. **Low: the approval endpoint refused an uppercase digest.** Real.
   `approvals.post.ts` accepts `[0-9a-fA-F]{64}` and lowercases it before
   `decideApproval` and `readApproval`. Vitest case "takes a digest in
   either case, as §5.14 compares them" (and a repeat in uppercase). Kept
   in S2a: tool-call approval is not reassigned, and S2a's text is what
   requires it.


F6 after review round 1: every CI validator and generator `--check`,
ruff check and format, mypy, pytest `tests/` (2421) and `benchmarks/tests/`
(68), `run_conformance.py`, cargo fmt, both clippy runs and cargo test
(1.99.1), `packages/acs-core` check, test and build, the binding's check and
test, and the site's check, test, build, `check-runs.mjs` (no enforced run
over 1800px; §5.14.1 was tightened to stay under it) and axe on
`/spec/1.2.0/`, `/rfcs/0006/`, `/spec/conformance/`,
`/guides/running-workflows/`, `/guides/standard-agents/` and
`/community/release-notes/`: all green.
