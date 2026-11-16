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
