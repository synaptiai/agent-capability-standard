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
- [ ] Full F6 set green (including check-axe over the whole site), commit

## 1. Class SL: the adapter's output-contract row

`not_applied` after S4 and S5: the binding's statement had none (S4 removed
the secret and redaction lines, S5 the `send` line); the adapter's kept the
output-contract row, which no stream owned (FOUNDATION-notes, S1 review
rounds).

**Host form (§5.18.9, §5.18.10).** The adapter receives a capability output
from the tools `create_grounded_mcp_server` serves with a capability (with
`require_layer`, the default): their result carries it as
`structuredContent` (validated structure) or as the I-JSON text of the
output object, its one text content item.

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
manifest are reported by `invoke.rs` and `catalog.rs`, which need the
catalog set. The schema diff since `main` adds no other workflow field. Two
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
