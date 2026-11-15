# S2b progress: host protocol and executor conformance

Design: `tasks/standard-1.2/designs/S2b.md`. Base: tag `round3/S2b-base`
(8ee3533). Branch `round3/b` in the worktree `/home/user/acs-b`.

## Findings (part 1)

- [x] ACS-37 host protocol in the Standard (§5.19, schema, class EX, audit of pinned members, `decision_id`, fixture schema)
- [x] ACS-31 host obligations (§5.19.4, unique `run_id`, `run_id` on actions, `tick` bool, `Host.withdraw`, runner `save=`/`key=`)
- [x] ACS-32 cancel (R408, `cancelled` records by step state, deferred runs)
- [x] ACS-34 wake-up time (`wake_at`, tick boundaries, `advance`, recipe)
- [x] ACS-33 snapshot size (`take_trace`, `take_records`, chain heads, derived terminal, snapshot version 2)
- [x] ACS-14 triggers (§5.10.2, `next_fire`, `triggers` module, runner `start(trigger=…)`, vectors)
- [x] ACS-15 parallel groups (§5.2.3, W618, W619)
- [x] ACS-30 audit records (§6.4, record mode `actions`, `audit` record of its own, alignment)
- [x] ACS-20 capture failure (`require_record`, run record, §8.4, collector `required=`, hook reports)
- [x] ACS-45 protocol traffic (§5.19.6)
- [x] ACS-62 error reasons (§5.19.7, guide)

## Standard text (part 2)

- [x] §1 item 11
- [x] §1.1 RFC 5545 (foundation; verify)
- [x] §2 five rows
- [x] §4.3 paragraph
- [x] §5.2 three rows (`parallel_group`, `join`, `retry`)
- [x] §5.2.3 Parallel Groups
- [x] §5.6 `end` bullet sentence
- [x] §5.10 `attendance` row and sentence
- [x] §5.10.2 Evaluating Triggers
- [x] §5.13 two edits
- [x] §5.19 Host Protocol (§5.19.1–§5.19.8); EXEMPT_RUNS entry removed
- [x] §6.1 sentence (foundation; verify)
- [x] §6.3 sentence
- [x] §6.4 Audit Records
- [x] §8.4 Manual Overrides
- [x] §9 rows (foundation; verify)
- [x] §10.1 row EX and sentence (foundation; verify)
- [x] §10.3 paragraph
- [x] §10.5 Executor Conformance
- [x] Appendix D.3

## Schemas (part 3)

- [x] Ontology `audit` (foundation; verify)
- [x] `world_state_schema.yaml` (foundation; verify)
- [x] `authority_trust_model.yaml` comments (foundation; verify)
- [x] `workflow_catalog.schema.json` `parallel_group`/`join` (foundation; verify)
- [x] `host_protocol.schema.json` (foundation; `run_id` into `head.required`)
- [x] `fixture.schema.json` (foundation; verify entry kinds)
- [x] Trigger vector files (3.7)

## Implementation (part 5)

- [x] `core/Cargo.toml` chrono
- [x] `core/src/trigger.rs`, `cron.rs` iterators
- [x] `core/src/exec/mod.rs` (run_id, RecordMode, StepState, State, Terminal/End, SNAPSHOT_VERSION 2, CancelError, next/tick/wake_at/cancel/take_*/run_record, check_state)
- [x] `core/src/exec/machine.rs` (trace seq, record members, decision_id, checkpoint_id, mode `actions`, side records, started, require_record, tick bool, cancel)
- [x] `core/src/validate/mod.rs` W618, W619
- [x] `core/src/python.rs`
- [x] `grounded_agency/_core.pyi`
- [x] `grounded_agency/workflows/protocol.py`
- [x] `grounded_agency/workflows/triggers.py`
- [x] `grounded_agency/workflows/runner.py`
- [x] `grounded_agency/trust.py` `manual_override`
- [x] `grounded_agency/coordination/audit.py`, `orchestrator.py`
- [x] `grounded_agency/hooks/evidence_collector.py` `required=`
- [x] `hooks/posttooluse_log_tool.sh`, `tools/verify_audit_log.py`, `hooks/README.md`
- [x] `skills/audit/SKILL.md`
- [x] TypeScript binding `records.ts` `actionRecord`
- [x] `scripts/gen_trigger_vectors.py`, CI, CLAUDE.md
- [x] `scripts/gen_runtime_fixtures.py` helpers, `NORMATIVE_MEMBERS`
- [x] Harnesses (`core/tests/runtime.rs`, `core/tests/triggers.rs`, `tests/runtime_replay.py`)
- [x] `grounded_agency/errors.py` (foundation; verify)

## Tests (part 6)

- [x] Runtime fixtures (`scripts/runtime_fixtures/s2b.py`)
- [x] Trigger vectors
- [x] Workflow fixtures (W618, W619, `require_record`) + EXPECTATIONS.json
- [x] Rust unit tests (exec, trigger, validate)
- [x] Python: test_runner, test_triggers, test_host_protocol_schema, test_audit_records, test_trust, hooks, verify_audit_log, coordination
- [x] TypeScript `records.test.ts`

## Documentation (part 7)

- [x] `docs/guides/RUNNING_WORKFLOWS.md`
- [x] `docs/guides/ORCHESTRATION_EXTENSIONS.md`
- [x] `docs/guides/MODALITY_HANDLING.md`
- [x] `docs/GLOSSARY.md`
- [x] `docs/GROUNDED_AGENCY.md`
- [x] `docs/TUTORIAL.md`
- [x] `docs/integrations/standard_agents.md`
- [x] `docs/integrations/claude_agent_sdk.md`
- [x] `spec/SECURITY.md`
- [x] `spec/CONFORMANCE.md`
- [x] `schemas/workflow_catalog.yaml` recovery texts, example catalog

## Other

- [x] RFC-0006 header, summary and Part B
- [x] CHANGELOG `[Unreleased]` entries with Upgrading notes
- [x] Findings statuses and resolutions
- [x] Full F6 set green

## Deviations

1. **Workflow fixture names.** The design's `warn_unknown_join` and
   `warn_group_mate_read` follow the repository's convention instead:
   `pass_join_unknown_warns` and `pass_group_mate_read_warns` (a passing
   fixture with `expected_warning_codes`), beside
   `pass_audit_require_record` and `fail_audit_require_record_type`.
2. **A quorum starts its step.** `started` (§5.19.5) is also set when the
   executor evaluates a step's quorum itself, so a non-compliant quorum in
   record mode `actions` has a `failed` record like any step that failed
   after it started. §5.19.5's definition and RFC-0006 B4 say so.
3. **Where the Rust tests are.** `core/src/exec` has no unit-test module and
   the operations are public, so the exec tests of design 6.4 are in
   `core/tests/host_protocol.rs`, beside `core/tests/runtime.rs` (harness,
   drain and EX replays) and `core/tests/triggers.rs`; the validator's are
   in `core/src/validate/groups.rs` (W618/W619 live there, called once from
   `validate/mod.rs`, to keep S3's file change to one line).
4. **A finished run's last record is settled.** `take_records` treats the
   record of the step a finished run ended at as settled (no step is in
   progress) and clears that stale reference, so a host can take every
   record of an ended run; `check_state` stays strict.
5. **The verifier's 1.2 generation** is an action record's required members
   (`action_id`, `timestamp`, `actor`, `intent`, `status`) rather than the
   hook line's `{action_id, timestamp, status, tool}`, so the audit skill's
   own chain (`.claude/audit/records.jsonl`, records without `tool`)
   verifies with the same tool.
6. **`runner.Action` stays `dict[str, Any]`.** The design makes it the
   TypedDict union of `protocol.py`; with it, every `Host` method that reads
   a kind-specific key fails mypy. The typed shapes are in
   `grounded_agency/workflows/protocol.py` and checked against the schema.
7. **Test locations.** The `manual_override` and the evidence collector's
   `required` tests are in `tests/test_audit_records.py` (S2b's file) rather
   than `tests/test_trust.py` (S6) and `tests/test_hooks_unit.py`.
8. **`recorded_by` content (C14).** S1 has not merged on this track: the
   hook line's `recorded_by` is `{"name": ...}` (the hook), and the
   binding's `actionRecord` takes `recordedBy` (default
   `standardagent-acs-binding`). S1 adds `version`, `config_sha256` and
   `settings` when it merges.
9. **One more event vector**, `source_kind_matches`, beside the design's five.
10. **Design bookkeeping left out of the Standard**: the parentheticals
    "(Merged text of S2b, S3, S4, S5 and S6; RECONCILIATION C3.)" and "(Rows
    merged from S2b, S5 and S6; RECONCILIATION C5.)" of design 2.11.
11. **§5.13's paragraph split.** "... since the wait had already lapsed." ends
    mid-paragraph in 1.1, so the paragraph is split there and the new
    paragraph goes between; the site's `wait-replay` slot index moves from 5
    to 7 (and its test's message from paragraph 6 to 8).
12. **A version-1 terminal action** is compared with the derived one after
    `check_state`, so a malformed state is refused before it is read.
13. **`run()` saves after the start** when given `save=`, so the reference
    host meets "save before acting" for the first action too; `drive` and
    `advance` save after each change, as the design says.
14. **The orchestrator's `audit` step** fails (R402, `not_recorded`) itself
    when the log raises and the step binds `require_record: true`: it runs
    workflows on its own engine, where the executor's check does not apply.
15. **Site figures.** With S2b's text written, the figure-gap sweep (1800px
    at 1440px) measures it, and S2b's text put seven runs of the Standard
    and one of the audit capability page over the limit. They are met with
    figures drawn from the text and the tested data, no exemption:
    replays of S2b fixtures (`protocol-replay`, `response-replay`,
    `wake-replay`, `cancel-replay`, `reason-replay` in §5.19,
    `audit-replay` in §6.4; the site's fixture reader skips `tick`,
    `wake_at` and `cancel` entries and the action pending at a cancel), and
    five figures in `site/src/lib/spec-host-figures.ts`: a run between an
    executor and its host (§2, from the protocol schema and §5.19.1),
    overlap decisions (§5.10.2, from the overlap vectors), §5.19.1's action
    table enriched with diagnostic tiles, the run record each end leaves
    (§5.19.8, from the fixtures' `run_record`) and the runtime fixtures by
    script entry (§10.5). A figure title strips a chapter's trailing dot
    ("from §2").
16. **The audit skill's record shape** is in its Field Definitions (`record`
    row) and the example line in Example 1, not in procedure step 6, which
    keeps one short bullet: the record's members are output contract
    content, and step 6 had made the procedure run 990px over the limit.

## Checks (2026-11-15, before the last commit)

- Validators: `validate_workflows --strict` and every catalog, profiles,
  skill refs, ontology, canonical schemas, RFCs, constraints, doc links,
  YAML util sync, transform refs, benchmark deps: pass.
- Generators `--check`: `sync_skill_schemas`, `gen_runtime_fixtures` (254
  fixtures), `gen_standard_agents_binding`, `gen_capability_json_schemas`,
  `gen_trigger_vectors`: no drift.
- `pytest`: 2652 passed. `ruff check` and `ruff format --check` (CI's paths),
  `mypy grounded_agency`: clean.
- Rust (1.99.1): `fmt --check`, `clippy --all-targets` with and without
  `--features python`, `cargo test --locked`: pass.
- `packages/acs-core`: check, 61 tests, build. `examples/standard_agents`:
  check, 61 tests.
- `site/`: `npm run check`, `npm test` (1148 tests), `npm run build`,
  `check-runs` (0 enforced pages over 1800px), `check-axe` on the 15 pages
  S2b changed: pass.
