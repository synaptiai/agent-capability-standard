# S2b progress: host protocol and executor conformance

Design: `tasks/standard-1.2/designs/S2b.md`. Base: tag `round3/S2b-base`
(8ee3533). Branch `round3/b` in the worktree `/home/user/acs-b`.

## Findings (part 1)

- [ ] ACS-37 host protocol in the Standard (§5.19, schema, class EX, audit of pinned members, `decision_id`, fixture schema)
- [ ] ACS-31 host obligations (§5.19.4, unique `run_id`, `run_id` on actions, `tick` bool, `Host.withdraw`, runner `save=`/`key=`)
- [ ] ACS-32 cancel (R408, `cancelled` records by step state, deferred runs)
- [ ] ACS-34 wake-up time (`wake_at`, tick boundaries, `advance`, recipe)
- [ ] ACS-33 snapshot size (`take_trace`, `take_records`, chain heads, derived terminal, snapshot version 2)
- [ ] ACS-14 triggers (§5.10.2, `next_fire`, `triggers` module, runner `start(trigger=…)`, vectors)
- [ ] ACS-15 parallel groups (§5.2.3, W618, W619)
- [ ] ACS-30 audit records (§6.4, record mode `actions`, `audit` record of its own, alignment)
- [ ] ACS-20 capture failure (`require_record`, run record, §8.4, collector `required=`, hook reports)
- [ ] ACS-45 protocol traffic (§5.19.6)
- [ ] ACS-62 error reasons (§5.19.7, guide)

## Standard text (part 2)

- [ ] §1 item 11
- [ ] §1.1 RFC 5545 (foundation; verify)
- [ ] §2 five rows
- [ ] §4.3 paragraph
- [ ] §5.2 three rows (`parallel_group`, `join`, `retry`)
- [ ] §5.2.3 Parallel Groups
- [ ] §5.6 `end` bullet sentence
- [ ] §5.10 `attendance` row and sentence
- [ ] §5.10.2 Evaluating Triggers
- [ ] §5.13 two edits
- [ ] §5.19 Host Protocol (§5.19.1–§5.19.8); EXEMPT_RUNS entry removed
- [ ] §6.1 sentence (foundation; verify)
- [ ] §6.3 sentence
- [ ] §6.4 Audit Records
- [ ] §8.4 Manual Overrides
- [ ] §9 rows (foundation; verify)
- [ ] §10.1 row EX and sentence (foundation; verify)
- [ ] §10.3 paragraph
- [ ] §10.5 Executor Conformance
- [ ] Appendix D.3

## Schemas (part 3)

- [ ] Ontology `audit` (foundation; verify)
- [ ] `world_state_schema.yaml` (foundation; verify)
- [ ] `authority_trust_model.yaml` comments (foundation; verify)
- [ ] `workflow_catalog.schema.json` `parallel_group`/`join` (foundation; verify)
- [x] `host_protocol.schema.json` (foundation; `run_id` into `head.required`)
- [ ] `fixture.schema.json` (foundation; verify entry kinds)
- [x] Trigger vector files (3.7)

## Implementation (part 5)

- [x] `core/Cargo.toml` chrono
- [x] `core/src/trigger.rs`, `cron.rs` iterators
- [x] `core/src/exec/mod.rs` (run_id, RecordMode, StepState, State, Terminal/End, SNAPSHOT_VERSION 2, CancelError, next/tick/wake_at/cancel/take_*/run_record, check_state)
- [x] `core/src/exec/machine.rs` (trace seq, record members, decision_id, checkpoint_id, mode `actions`, side records, started, require_record, tick bool, cancel)
- [x] `core/src/validate/mod.rs` W618, W619
- [x] `core/src/python.rs`
- [ ] `grounded_agency/_core.pyi`
- [x] `grounded_agency/workflows/protocol.py`
- [x] `grounded_agency/workflows/triggers.py`
- [x] `grounded_agency/workflows/runner.py`
- [x] `grounded_agency/trust.py` `manual_override`
- [x] `grounded_agency/coordination/audit.py`, `orchestrator.py`
- [x] `grounded_agency/hooks/evidence_collector.py` `required=`
- [ ] `hooks/posttooluse_log_tool.sh`, `tools/verify_audit_log.py`, `hooks/README.md`
- [ ] `skills/audit/SKILL.md`
- [ ] TypeScript binding `records.ts` `actionRecord`
- [x] `scripts/gen_trigger_vectors.py`, CI, CLAUDE.md
- [x] `scripts/gen_runtime_fixtures.py` helpers, `NORMATIVE_MEMBERS`
- [x] Harnesses (`core/tests/runtime.rs`, `core/tests/triggers.rs`, `tests/runtime_replay.py`)
- [ ] `grounded_agency/errors.py` (foundation; verify)

## Tests (part 6)

- [x] Runtime fixtures (`scripts/runtime_fixtures/s2b.py`)
- [x] Trigger vectors
- [ ] Workflow fixtures (W618, W619, `require_record`) + EXPECTATIONS.json
- [x] Rust unit tests (exec, trigger, validate)
- [ ] Python: test_runner, test_triggers, test_host_protocol_schema, test_audit_records, test_trust, hooks, verify_audit_log, coordination
- [ ] TypeScript `records.test.ts`

## Documentation (part 7)

- [ ] `docs/guides/RUNNING_WORKFLOWS.md`
- [ ] `docs/guides/ORCHESTRATION_EXTENSIONS.md`
- [ ] `docs/guides/MODALITY_HANDLING.md`
- [ ] `docs/GLOSSARY.md`
- [ ] `docs/GROUNDED_AGENCY.md`
- [ ] `docs/TUTORIAL.md`
- [ ] `docs/integrations/standard_agents.md`
- [ ] `docs/integrations/claude_agent_sdk.md`
- [ ] `spec/SECURITY.md`
- [ ] `spec/CONFORMANCE.md`
- [ ] `schemas/workflow_catalog.yaml` recovery texts, example catalog

## Other

- [ ] RFC-0006 header, summary and Part B
- [ ] CHANGELOG `[Unreleased]` entries with Upgrading notes
- [ ] Findings statuses and resolutions
- [ ] Full F6 set green

## Deviations

(none yet)
