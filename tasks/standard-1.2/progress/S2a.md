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

- [x] `core/src/exec/mod.rs`: `RequestApproval.queued_action_id`, `Decision.approver_identities`, `StepState.queued`, `Frame.{resume,parked,pending_escalation,ahead}`, `ResumeOptions`, `ResumeError`, `RestoreOptions`, `RestoreError::Actor`, `restore_with`, `resume`, `not_kept`, `check_state` additions
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
   `Frame.ahead`, `StepState.queued`) is optional and left out while it has
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
4. **`queued_action_id` while the record is planned.** A request names the
   queued action only while its record is still `planned`; the record is
   updated in place by the first decision, so a re-ask after a recheck (a
   new record, as in 1.1) names none.
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
