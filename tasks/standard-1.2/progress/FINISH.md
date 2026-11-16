# FINISH progress: class SL for both layers, W616, pending items, CLAUDE.md, findings

Finishing work after every stream (S1, S2a, S2b, S3, S4, S5, S6) is merged
on `claude/gallant-hypatia-wbucn3`. Base: tag `round3/FINISH-base`
(3f30f6a, the fast-forward of `round3/a` to the integration branch).
Branch `round3/a`, worktree `/home/user/acs-a`.

## Checklist

- [x] 1. Class SL for both reference layers (§5.18.10, §10.4)
  - [x] Inventory the `not_applied` lines left after S4 and S5: only the
    adapter's output-contract row (R402); the binding's statement had none
  - [x] Adapter host form for §5.18.9 (output-contract row, R402)
  - [x] Tests and call fixtures for the new row
  - [x] Drop `not_applied` from both statements
  - [x] Reword every text that states the claims
- [x] 2. W616: a `FEATURES` row (or the catalog-set check) for every 1.2
  feature of every stream, each pinned by a validator fixture
- [x] 3. Every Pending integration item left in a progress file: wired, or
  recorded why not
- [x] 4. CLAUDE.md and AGENTS.md against what the streams changed
- [x] 5. Findings: every ACS finding fully implemented is `fixed` with an
  accurate resolution
- [x] Full F6 set green (including check-axe over the whole site), commit
- [x] Review round 1: eleven issues verified and fixed, full F6 set, commit

## 1. Class SL: the adapter's output-contract row

`not_applied` after S4 and S5: the binding's statement had none (S4 removed
the secret and redaction lines, S5 the `send` line); the adapter's kept the
output-contract row, which no stream owned (FOUNDATION-notes, S1 review
rounds).

**Host form (§5.18.9, §5.18.10).** The adapter receives a capability output
from the tools `create_grounded_mcp_server` serves with a capability (with
`require_layer`, the default): their result carries it as
`structuredContent` (validated structure) or as the I-JSON text of the
output object, its one text content item. (Review round 1 below: the SDK's
server drops `structuredContent`, so only the text is the output.)

- `grounded_agency/capabilities/output.py`: `check_capability_output`
  (contract check of validated structure: an object, every required field,
  `evidence_anchors` an array, `confidence` 0 to 1 where required, I-JSON)
  and `tool_result_output` (reads the output an MCP tool result carries;
  R402 for a result that is not a mapping, a `structuredContent` that is not
  an object, content that is not exactly one text item, or an output that
  fails the contract). Exported from `grounded_agency.capabilities`.
- `GroundedAgentAdapter.check_call_result(tool, args, result, call)`: with
  `config.check_outputs` (default True) R402 when the result carries no
  output that satisfies the contract, recorded against the call as the
  failure of the call that ran (`failed`, like F505), then
  `check_call_output` (grounding F505, minimum confidence F504), the
  executor's order. An `is_error` result is passed on; a tool with no
  capability has no contract. `_fail_call` is the shared tail.
- `grounded_agency/mcp.py`: the guarded handler calls
  `adapter.check_call_result` (the former `_grounding_refusal` is gone).
- `GroundedAgentConfig.check_outputs: bool = True`. `False` passes results
  on unchecked, as before 1.2.0, and is outside class SL; it is then in
  `recorded_by`'s settings (`config_sha256`), and the default leaves every
  existing digest unchanged.
- Claude Code's own tools and other MCP servers' tools return results in
  their own forms, which carry no capability output: no output check applies
  to them. §5.18.10 gains a paragraph that says so for the output-contract
  row, as §5.21.4 already says for the profiles' output rules: the row
  applies to each covered call's result the layer receives as a capability
  output, and the statement names the calls whose results come in other
  forms. The adapter's statement names them (its §5.20 host gap now covers
  the output-contract row too).

**Fixtures.** The call fixture format gains a call's `returns` (its tool's
output, in place of what the contract requires) and the expectation
`{"refuse_output": "R402"}` (the call ran, and the layer refused its
output): schema, `scripts/gen_call_fixtures.py` (`refuse_output`,
`returns=`, `extra=` bindings), §10.4's call-sequence paragraph and
CONFORMANCE.md. Three fixtures: `output_breaks_contract` (prose, a missing
field, a confidence of 2, then a full output and the default),
`output_not_i_json` (2^53 + 1 refused, 2^53 passes) and
`refused_output_uses_checkpoint` (the refused call used its checkpoint, so
the next `write` is F501). Both runners play them: the Python runner now
serves every bound tool through the adapter's guarded handler (`_guarded`),
returning its output as JSON text, and fires PostToolUse with the result;
the TypeScript runner's tool returns `returns`. 26 call fixtures.

**Tests.** `tests/test_mcp_integration.py` (R402 for seven malformed
results, recorded once and `failed`; three passing forms; an error result
passed on; R402 before F505; `check_outputs=False` passes and changes the
digest); `tests/test_call_fixtures.py` and
`examples/standard_agents/test/calls.test.ts` check that neither statement
has `not_applied`, and the adapter's names `check_outputs=False` as outside
the class.

**Texts reworded** to "claims class SL (§10.4)": the Standard's Status line
(both layers), §5.18.10 (above), §10.4 (fixture members), SECURITY.md §5.5,
CONFORMANCE.md (class SL section, call fixtures), RFC-0005 9.1 and its
fixture count, `hooks/README.md`, the SDK guide (output-contract paragraph
under `require_layer`, the example tool returning its output, grounding
paragraph, Conformance section), the Standard Agents guide (Conformance:
the binding's output check, 26 fixtures), the CHANGELOG (an Upgrading
entry for SDK users, the statement-schema entry, the fixtures count, an
Added entry), the MCP demo's printed example, findings ACS-01 and ACS-41.

## 2. W616

§11.5's 1.2 row and `semantics::FEATURES` agree: approver `sender_check`
and `accept_trust_classes` (S2a), the `audit` input `require_record` (S2b),
`grounding@1` with `grounding` and F505 in `on_error` (S4), the workflow
field `agents` and the `delegate` input `continues` (S3), the `persist` and
`recall` input `scope` (S5); S3's qualified `invoke` target and catalog
manifest are reported by `invoke.rs` (from the names of the invoker's
catalog) and `catalog.rs` (from the file's header). The schema diff since `main` adds no other workflow field. Two
1.2 features had no validator fixture; added:
`warn_version_feature_1_2_grounding` (W616 at
`workflow_extensions/requires/0` and at the F505 `on_error`, with a 1.2
twin that has none) and `warn_version_feature_1_2_trust_classes` (W616 and
W604 at the approver member). Every 1.2 feature now has one.
RFC-0010's and ACS-25's sentences that still said "the S303 for `agents`
before 1.2" say W616.

## 3. Pending integration items

- **S6 items 5, 6, 8** (destinations, W616 rows, documentation): wired by
  S5 and S3. Checked: `Policy::unenforced` and `unappliedRule` are gone; the
  adapter's `refuse_unapplied` keeps only the `strict_mode=False` checkpoint
  rule (a configuration that cannot apply a raised checkpoint requirement,
  not an unimplemented one); runtime fixtures `profile_destinations_refuse`
  and `profile_destinations_none` exist; no "no reference component checks
  a destination policy yet" sentence is left; ACS-05 is `fixed`. S6.md's
  ACS-05 line and its Pending section now say so.
- **S1**: the CLAUDE.md Hooks bullet (item 4 below); `index.yaml`'s status
  counts (item 5 below); the `persist` hook's `BLOCK:` prefix (S4 changed it
  to `F504`/`R407`).
- **S3, S5**: their Pending sections are marked done; nothing left.

## 4. CLAUDE.md and AGENTS.md

CLAUDE.md's Hooks bullets: the PreToolUse classification now reads
"`git stash pop|apply <commit>` restores a checkpoint a marker recorded and
needs nothing; any other restore is a gated call", and a used marker is
filed under `.claude/checkpoints/used/`; PostToolUse (Bash) files a
replaced marker under `ended/`; Stop files the marker under `ended/` (it no
longer removes it); the audit line is an action record (§6.4). The rest of
CLAUDE.md (commands, generators, safety model, skill structure, counts) and
AGENTS.md agree with the tree; no other edit.

## 5. Findings

All 64 ACS findings are `fixed`. Resolutions corrected: ACS-01 (both
layers claim SL; 26 call fixtures), ACS-41 (the adapter's host form),
ACS-25 (W616 rows and fixtures). `index.yaml`'s status counts (left by S1)
are 64 fixed, and `tests/test_standard_agents_mapping.py` now checks them.
ACS-49's last sentence (migrating the duplicated example to a qualified
invoke once the reference catalog has a manifest) is an optional follow-up,
not part of the finding's proposed change.

## Checks (F6, on the final tree)

All green:

- Python: every `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py
  --strict`, every domain catalog and example `--strict`; every generator
  with `--check` (`sync_skill_schemas`, `gen_runtime_fixtures` 350,
  `gen_call_fixtures` 33 + 26, `gen_trigger_vectors`,
  `gen_standard_agents_binding`, `gen_capability_json_schemas`); ruff check
  and format (CI's list); mypy; `pytest tests/` (4271 passed, 7 skipped);
  `pytest benchmarks/tests/` (69) and `benchmarks/runner.py --report`;
  `scripts/run_conformance.py`.
- Rust (`core/`, 1.99.1): fmt; clippy plain, `python`, `wasm`; `cargo test
  --locked` (`edge_checks_scale_linearly` failed once while axe ran, passed
  alone, as the task notes warn); `--features wasm --test wasm`; MSRV
  `cargo +1.88.0 check --locked --all-targets --features python`; the CEL
  differential (`go run .`, 155 cases and 92 expressions, 0 failures). No
  Rust changed here.
- TypeScript: `packages/acs-core` check, test (1784), build; the binding
  check and test (182, 1 skipped).
- Site: `npm run check`, `npm test` (1169; a run beside axe timed out two
  render tests at 5s, and passed alone), `npm run build` (check-dist),
  `scripts/check-runs.mjs` (0 enforced runs over 1800px), and
  `scripts/check-axe.mjs` over all 182 pages (728 runs, no violations).

A note on the harnesses: `expected_warning_codes` lists distinct codes (the
WebAssembly harness compares sets), so `warn_version_feature_1_2_grounding`
lists W616 once and pins its two findings with `expected_locations`.

## Review round 1

Eleven issues, numbered here in the order given; 1 and 7, and 4 and 11,
are the same defect reported twice. Each verified real, fixed at its root,
with a test that fails on the code before the fix.

1. and 7. **R402 on `structuredContent`, which the SDK drops (medium;
   high).** Real: `claude_agent_sdk.create_sdk_mcp_server`
   (0.2.182 here) builds the `CallToolResult` from `content` and
   `is_error` only, so the session read the unchecked text. Reproduced
   with the reviewers' scripts (prose beside grounded structure passed
   R402, F505 and F504). Fix: `tool_result_output` reads the output only
   from the one text item, the form this host delivers; a result that
   carries its output only as `structuredContent` is R402, with a message
   that says the structure is not delivered. `check_capability_output`,
   which nothing used once structure is not read, is removed.
   `check_call_result` applies grounding and the minimum confidence to the
   same text output. Tests (`tests/test_mcp_integration.py`): the R402
   cases moved to text, plus structure-only and prose-beside-structure
   cases; the passing cases are text, text beside structure, and text
   beside `structuredContent: None`; `test_the_session_receives_the_output_that_was_checked`
   runs the guarded tool through the SDK's own `run_tool` (captured from
   `build_tool_server`) and checks that the delivered result has no
   `structuredContent`, that grounded structure beside prose is R402, and
   that a passing result delivers the checked text. The old test case
   "Structured content is the output whatever the text says" now expects
   R402. Texts: the `mcp.py` docstring, `GroundedAgentConfig.check_outputs`,
   the statement (now under `calls_without_output`, item 3), the SDK guide
   (output-contract paragraph, grounding paragraph, Conformance), the
   CHANGELOG Upgrading and Added entries, CONFORMANCE.md, SECURITY.md,
   RFC-0005 9.1, ACS-41, FOUNDATION-notes. §5.18.10 gains the general rule:
   a layer checks the output in the form its host delivers the result; a
   member the host drops is not the output.
2. **§5.18.9 does not state the confidence check the normative fixture
   requires (low).** Real. §5.18.9's consumer sentence now lists every
   check: I-JSON (no member twice, no integer beyond ±2^53, §5.14), an
   object with every required field, `evidence_anchors` an array where
   present, a required `confidence` a number from 0 to 1 (§4.1.1); §5.18.10
   says validated structure is checked the same way; the R402 row in §9
   says "fails its output contract". `output_breaks_contract`'s description
   names each case, and it gains a step for an `evidence_anchors` that is
   not an array (R402) and one for `returns: null` (item 4). The codecs'
   module comments and the Standard Agents guide list the same checks.
3. **§5.18.10 points at a §10.4 statement member that does not exist; the
   adapter used `host_gaps` (low).** Real. §10.4's list gains "the covered
   calls whose results carry no capability output, to which no output check
   applies (§5.18.10, §5.21.4)"; `statement.schema.json` gains the optional
   `calls_without_output` (and `host_gaps` gets its §10.4 description). The
   adapter's statement moves the entry there; `tests/test_call_fixtures.py`
   checks it is there and not among the host gaps, and
   `tests/test_profiles.py` reads it there. CONFORMANCE.md, RFC-0005, the
   SDK guide, ACS-01 and the grounding finding name the member.
4. and 11. **`returns: null` (low).** Real: the Python runner read
   `step.get("returns")` and treated null as absent; the generator dropped
   `returns=None`. Fix: a sentinel in both (`_NO_RETURNS`), presence decides.
   `output_breaks_contract` now has a `returns: null` step (R402), which the
   old Python runner fails; the schema says null is a value and a present
   member replaces the contract's output.
5. **W616 fixture names and the catalog-set wording (low).** Real. RFC-0010,
   the CHANGELOG and ACS-25 now name `pass_approver_identity_1_1_warn`
   beside the `*_v11_warn` fixtures; ACS-25 and section 2 above say the
   qualified target is reported from the names of the invoker's catalog
   (`Resolver::is_qualified`) and the manifest from the file header
   (`catalog::check_manifest`), as the comment in `semantics.rs` already
   said.
6. **Two leftover texts (low).** Real. The SDK guide's opening now says the
   adapter claims class SL; CONFORMANCE.md's exact-integer note names
   `output_not_i_json`.
8. **`check_outputs=False` did not restore the earlier reading (low).**
   Real: a contract failure set the output to None, so a grounded partial
   `structuredContent` became F505. Fix: with `check_outputs` off,
   `_unchecked_output` reads as `_grounding_refusal` did at the base (a
   `structuredContent` object as it is, else the one text item decoded,
   else None), and a result that is not a mapping is passed on, as before.
   Test: `test_check_outputs_off_reads_outputs_as_before` (four cases; three
   failed before the fix).
9. **`structuredContent: null` made a valid text R402 (low).** Real; fixed
   by item 1 (structure is not read) and, with `check_outputs` off, by
   item 8 (a non-object is ignored). Tests: the passing case with
   `structuredContent: None`, and the second case of item 8's test.
10. **The TypeScript runner ignored a nested call's `returns`/`fails` and
   reused a stale top-level script (low).** Real. Fix: `Runner.scripted`
   sets a call's script for the time it runs (top-level and nested) and
   restores the previous one after. New fixture
   `nested_output_breaks_contract` (needs `nested_calls`): a nested call's
   own `returns` is refused, and a nested call after a top-level call of
   the same tool with `returns` runs; the old runner fails it. 27 call
   fixtures (counts updated in CONFORMANCE.md, RFC-0005, the CHANGELOG, the
   Standard Agents guide, ACS-01, both runners' count tests).

### Checks (F6) after review round 1

All green on the final tree:

- Python: every `tools/validate_*.py` of CLAUDE.md (benchmark deps
  included), `validate_workflows.py --strict`, every domain catalog and
  example `--strict`; every generator with `--check` (`sync_skill_schemas`
  107, `gen_runtime_fixtures` 350, `gen_call_fixtures` 33 + 27,
  `gen_trigger_vectors`, `gen_standard_agents_binding`,
  `gen_capability_json_schemas`); ruff check and format (CI's list); mypy;
  `pytest tests/` (4280 passed, 8 skipped); `pytest benchmarks/tests/` (69)
  and `benchmarks/runner.py --report`; `scripts/run_conformance.py`.
- Rust (`core/`, 1.99.1; no Rust changed): fmt; clippy plain, `python`,
  `wasm`; `cargo test --locked`; `--features wasm --test wasm` (12); MSRV
  `cargo +1.88.0 check --locked --all-targets --features python`; the CEL
  differential (155 cases, 92 expressions, 0 failures).
- TypeScript: `packages/acs-core` `build:wasm`, build, check, test (1784);
  the binding check and test (183, 1 skipped).
- Site: `npm run check`, `npm test` (1169), `npm run build` (check-dist),
  `scripts/check-runs.mjs` (0 enforced runs over 1800px), and
  `scripts/check-axe.mjs` over the pages this round changed (`/spec/`,
  `/spec/1.2.0/`, `/spec/conformance/`, `/spec/security/`, `/rfcs/0005/`,
  `/rfcs/0010/`, `/guides/claude-agent-sdk/`, `/guides/standard-agents/`,
  `/community/release-notes/`: 36 runs, no violations).

The site counts the call fixtures from the git index (`trackedIn`): a new
fixture is counted once it is added, so `npm test` and the build run after
`git add`.

