# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- **Rust core (`core/`, #114).** The workflow validator now lives in a Rust
  crate compiled into `grounded_agency._core` (maturin build; Rust >= 1.86).
  It brings a hardened YAML 1.2 loader (size and depth limits, alias budget,
  no symlinks, unique string keys) with a PyYAML parity test, the condition
  expression language of Standard v1.1 §5.8, and the v1.1 edge, safety-flag,
  unknown-field and version rules. `tools/validate_workflows.py` and the
  Python `WorkflowEngine` both call it, so they can no longer disagree. CI
  gains a `rust-core` job (fmt, clippy, tests, MSRV) and a `cel-differential`
  job that checks the expression fixtures against cel-go
- **Orchestration extensions, first part (#114):** `workflow_extensions.requires`
  is validated (unknown extensions and undeclared extension fields are V106),
  `triggers` (schedule with 5-field cron or interval and IANA time zone,
  event, manual, invoke) are validated under `triggers@1`, and a step
  `timeout` outside the duration grammar warns (W614). Recovery is validated
  under `recovery@1`: `goto_step` resolves to a `store_as` (V107 otherwise;
  a capability id is deprecated, W603), `on_error` triggers, escalation to
  `handler: true` invoke steps through `action: escalate` and
  `on_exhausted`, injected `${_recovery.*}` context, untriggered recoveries
  (W609), unreachable handlers (W613), unknown invoke targets (W607) and
  invoke cycles (V105). `wait@1` validates waits on `receive` and
  `synchronize` (required duration timeout, liveness that can fire before
  it, W608 for a checkpoint taken before a wait), and `approval@1`
  validates structured approvals (approver, digest binding, recheck,
  expiry, unattended behaviour; W606 when an unattended run would reach an
  approval with no plan). `delegation@1` covers delegation hints
  (`fresh_context`, `model_family`, `role`) and sender filtering
  (`accept_from`), and `quorum@1` validates review quorums on blocking
  `constrain` steps: reviewers are earlier, distinct delegate steps,
  vocabulary and thresholds are consistent, and reviewers stay independent
  of forbidden inputs (checked transitively, including through context a
  recovery loop injects), fresh context and model families (F504). Declaring an extension the validator
  does not check is refused (V106). New guide:
  [docs/guides/ORCHESTRATION_EXTENSIONS.md](docs/guides/ORCHESTRATION_EXTENSIONS.md)
- **Reference executor (#114).** A deterministic, sans-IO executor in the
  Rust core runs validated workflows: conditions and gates, checkpoint
  authorisation and invalidation after waits, digest-bound approvals with
  expiry and rechecks, unattended behaviour, waits with event matching,
  retries with backoff, deadlines, failure modes, recovery loops,
  escalation to handlers, nested invocations and review quorums. Runs
  snapshot to canonical JSON (RFC 8785) with a SHA-256 and optional HMAC,
  and resume anywhere. Python drives it with
  `grounded_agency.workflows.WorkflowRunner` and a `Host`
  ([guide](docs/guides/RUNNING_WORKFLOWS.md)); runtime conformance fixtures
  in `tests/conformance/runtime/`
- `docs/research/analysis/validator-engine-disagreements-1.0.md`: minimal
  reproductions of the 22 cases where the 1.0 validator and engine judged
  the same workflow differently, and how each behaves now (#114, question 3)
- A step that raises `requires_checkpoint` above the ontology is now held to
  it: F501 when no checkpoint runs before it
- `world_state_schema.yaml` 1.1.0: action records gain status `rejected`
  and `expired`, an optional `approval` record (digest, decision,
  approvers) and an optional `reason`
- `schemas/review_verdict_schema.yaml` for quorum verdicts; ontology inputs
  and outputs for delegation and quorums (`delegate.fresh_context`,
  `.model_family`, `.role`, `.effective`; `receive`/`synchronize`
  `accept_from`; `constrain.tally`)
- `spec/STANDARD-v1.1.0.md` (Candidate Standard) and `spec/RFC-0003-orchestration-extensions.md`
  (Accepted) answering #114; see the [specification changelog](spec/CHANGELOG.md)
- Validator warnings: `tools/validate_workflows.py` reports warnings (W6xx)
  separately and passes unless `--strict` is given;
  `tools/validator_suggestions.json` gains `warnings` and
  `structured_warnings`, and hints such as "did you mean" are printed
- `WorkflowEngine.validate_report()`, `add_workflow()` and `effective_flags()`;
  `ErrorCode` gains the v1.1 codes and `Severity` is exported
- `python tools/sync_skill_schemas.py --check`, run in CI, fails when a
  generated skill file (output schemas, the 17 bundled workflow catalogs and
  their schema copies) has drifted from its source
- Conformance fixtures for the v1.1 edge, flag, unknown-field and version
  rules; `expected_warning_codes` in `tests/fixtures/EXPECTATIONS.json`
  (empty means none allowed); language-neutral expression fixtures under
  `tests/conformance/expressions/`
- `tools/validate_canonical_schemas.py` and a CI job covering the five canonical
  schemas designated by spec §6.1, which no validator checked before. It asserts
  §6.2/§6.3 required fields, trust-model internal consistency, alias-threshold
  ordering, and cross-file agreement with the benchmark fixture. Every defect
  from #105 and #106 is covered by a negative test proving the validator now
  catches it (#107)
- `spec/RFC-0002-agent-reliability-profile.md` proposing cross-session agent
  behavioural reliability as a first-class concept, and naming the prerequisite
  that blocks it: the standard has no agent identity object to attach a profile
  to (#104)
- `tools/validate_rfcs.py` and a CI job enforcing what `spec/GOVERNANCE.md`
  already required of RFCs — motivation, alternatives, backward-compatibility
  analysis and conformance test updates — plus header metadata, unique RFC
  numbers, and that cited repository paths exist. RFC-0001 was missing two of
  the required sections and now carries them (#104)
- `tools/validate_constraints.py` and a CI job asserting that every pin in
  `constraints.txt` names a package `pyproject.toml` declares and falls inside
  the range declared for it. The two files state overlapping facts about the
  same packages; this is what makes disagreement fail loudly instead of
  surfacing as an opaque pip resolution error
- `tools/validate_doc_links.py` and a CI job asserting that documentation
  cross-references resolve. Markdown links were the one reference kind nothing
  checked, which is how `docs/integrations/claude_agent_sdk.md` came to cite a
  `comparisons/` directory that has never existed. It reads every link form
  CommonMark allows — titles, angle brackets, images, and links whose text
  contains nested brackets — because anchoring on the opening `[` cannot see a
  badge, which had left the README's links to `LICENSE`, `spec/STANDARD-v1.0.0.md`
  and `CHANGELOG.md` unvalidated. Code-span paths are checked in `CLAUDE.md` and
  `README.md` only: repo-wide that check produces ~109 findings of which
  essentially none are defects (package-relative paths, tutorial placeholders,
  roadmap deliverables), and a validator that cries wolf gets ignored
- `CapabilityRegistry.all_edges()` public method for enumerating ontology edges
- Benchmark drift-prevention validator (`tools/validate_benchmark_deps.py`) and CI job
- Multi-agent coordination runtime with delegate, synchronize, and invoke patterns (#98)
- NIST AI RMF 1.0 profile with tier assessments and maturity roadmap (#59)
- EU AI Act conformity assessment preparation (#58, #97)
- ISO 42001 gap analysis and certification readiness documentation (#96)
- Workflow execution engine (TD-006) (#94)
- OASF GA extension mechanism for unmapped capabilities (TD-010) (#95)
- Comprehensive analysis documentation package (13 documents, ~570KB)

### Changed
- **Migration:** binding `fresh_context`, `model_family` or `role` on
  `delegate`, or `accept_from` on `receive`/`synchronize`, now needs
  `delegation@1` in `workflow_extensions.requires` (V106). These inputs were
  previously unknown to the ontology and silently ignored; a consumer that
  ignored them would reuse a reviewer's context or accept anyone's items
- **Workflow catalog (#114).** Declares `# Standard version: 1.1.0`; approval
  flags no longer understate the ontology; `clarify_intent` asks through
  `inquire` and receives the answer only when questions were asked;
  `model_deployment` checks artifacts with `constrain` before deploying;
  `monitor_and_replan` critiques the detected violations at major severity;
  gates that read their own step declare `phase: after`;
  `digital_twin_sync_loop`'s verification loop fires on
  `${verify_out.passed} == false` and targets `plan_out`
- **Ontology edges (#114).** Five follow-up edges are `enables` instead of
  `soft_requires`, a redundant one is removed, and `constrain` is the soft
  prerequisite of `execute`, `mutate` and `send`; `audit` is
  `mutation_overridable`
- **`WorkflowEngine` safety fields are effective values** (the stricter of the
  step's declaration and the ontology); what the source declared is in
  `WorkflowStep.declared`. `validate_*` methods return errors only; an unknown
  store reference maps to B202 (`MISSING_PRODUCER`) instead of B201
- **`schemas/workflow_catalog.schema.json`** requires only the fields Standard
  §5 requires, and describes gate `phase`, failure-mode `when` and
  `spec_version`
- The 17 bundled `skills/*/reference/workflow_catalog.yaml` copies are
  regenerated from `schemas/workflow_catalog.yaml`; they had drifted.
  `sync_skill_schemas.py` also maintains schema copies a skill vendors
  without a bundled catalog (`skills/receive/reference/event_schema.yaml`)
- `schemas/event_schema.yaml` 1.1.0: `source.kind` gains `agent`
- Development dependencies are version-bounded instead of open-ended, and each
  cap names the major this repo is verified against rather than the next
  unreleased one: `mypy>=1.0,<2`, `pytest>=7.0,<9`, `pytest-asyncio>=0.21,<1`.
  A cap set at the next unreleased major would not have changed what CI
  installs — `mypy>=1.0,<3` admits mypy 2.x, which is precisely the upgrade the
  bound exists to make deliberate. Raising a cap now means running the suite on
  that major first
- Exact tool versions moved to a new `constraints.txt`, installed via
  `pip install -e ".[dev]" -c constraints.txt`. `ruff` is pinned there rather
  than in the `dev` extra: formatting is not semver-safe (0.16.5 began
  formatting Python blocks inside Markdown and turned CI red on a commit
  touching only `.gitignore`), but an exact pin in package metadata would
  conflict with a consumer's own ruff. The bounds describe what the package
  supports; the constraints file describes what a green check attests to
- The `claude-agent-sdk` floor is `>=0.1.25`, the oldest release providing every
  symbol this package imports, rather than the newest release available. It was
  briefly `>=0.2.148`, which excluded working installs without cause
- `pyyaml` carries an upper bound (`>=6.0,<7`) like everything else, and the two
  CI jobs that installed it directly now install the package instead, so the
  constraint is declared once rather than in three places
- RFC-0002 downgrades `delivery_score` from "derivable now" to provisional. The
  original proposal and the RFC's first draft both overstated it: `actor` is a
  bare string documented as `agent/human` so the population cannot be restricted
  to agents, no terminal-status subset is defined, and `rolled_back` has no
  agreed sign — §3.3 requires rollback be possible and §4.4 requires a
  checkpoint before one, but neither says how a rollback should be scored, so
  counting it as failure marks an agent down for exercising a capability the
  standard requires it to have (#104)
- RFC-0002 makes it normative that an implementation MUST NOT infer that
  `ProvenanceRecord.agent` and `ActionRecord.actor` denote the same principal,
  with a conformance fixture required for the rule (#104)
- RFC-0002's citation of the *PDR in Production* preprint now records that its
  author has stated they do not have a reproducible dataset supporting the
  "6,342 cycles" or independent-convergence claims, replacing an unresolved
  caveat with the author's own agreement that it is design context, not
  validation evidence. The wording is deliberate: "I do not have one" is not
  "none exists", and a document whose argument rests on §3.1 must not convert
  the one into the other (#104)
- Enhanced CLAUDE.md with workflow orchestration guidelines and core principles

### Fixed
- **Mistyped `input_bindings` keys were silent (#114).** A key the
  capability does not define is now W604 with a did-you-mean hint, and an
  `invoke` step's literal `input` is checked against the invoked workflow's
  inputs (S303 undeclared, S304 missing required). This found
  `digital_twin_bootstrap` passing `inputs:` (which the executor ignores) with
  names its targets do not declare; it now passes `input` with
  `user_input` and `previous_world_state`. Catalog bindings outside the
  ontology were renamed to its inputs, and the ontology gained six optional
  inputs that catalogs relied on. The skill docs' input tables now match the
  ontology, and the tutorial and doc examples validate cleanly
- **Domain workflow catalogs.** The four catalogs under `schemas/workflows/`
  failed validation before this release (mostly untyped references, plus
  ordering and binding errors) and nothing checked them. They now pass in
  strict mode, and CI validates them
- **The Python PreToolUse checkpoint hook never blocked anything.** It
  returned a top-level `permissionDecision`, which the Claude Agent SDK
  ignores; it now denies through `hookSpecificOutput` (#114)
- **Checkpoint reservation race (SEC-007).** `validate_and_reserve()` did not
  reserve: two concurrent mutations could pass on one checkpoint. A
  reservation now belongs to one tool call (`tool_use_id`), is taken in
  PreToolUse (so pre-approved tools are covered too), is consumed on success
  and released by a new PostToolUseFailure hook on failure or interrupt, and
  lapses after `GroundedAgentConfig.checkpoint_reservation_seconds` (#114)
- `templates/SKILL_TEMPLATE_ENHANCED.md` nested a ```` ```markdown ```` block
  containing ```` ```yaml ```` blocks of the same fence length. Per CommonMark
  the outer block closes at the first bare fence, so the document's structure
  from that point on was not what it appeared to be. The outer fence is now four
  backticks. Found by the new link validator, which reported the resulting
  unclosed fence
- `grounded_query` now closes the SDK's generator when a caller breaks out of
  iteration. `async for` does not close its iterator on `break` (PEP 533 was
  deferred), so re-yielding from `sdk_query` without an explicit `aclose`
  deferred the SDK's `finally: await query.close()` — the call that terminates
  the CLI subprocess — to garbage collection, leaving the process alive past
  its consumer
- `test_grounded_query_callable` no longer drives an unbounded billable API
  call. It still exercises the real SDK with no mock and no skip, but stops
  after the first message and runs under a timeout. The timeout bounds the
  query, not total wall time: `wait_for` cancels the task and then awaits
  teardown, so the ceiling is the budget plus SDK cleanup
- `test_grounded_query_callable` can now fail. It previously had no assertion
  and caught `ValueError`, which is raised only when `wrap_options` produces a
  contradictory options object — a wrapper defect that read as an environment
  outcome. It now asserts that either a message arrived or a genuine
  environment error was raised, so a wrapper yielding nothing is a failure
- Trust decay is now a true half-life: `recency_factor` is `0.5 ** (age/half_life)`,
  which returns exactly 0.5 at `age == half_life`. The previous
  `exp(-age/half_life)` treated `half_life` as an exponential time constant and
  decayed 1/ln(2) ≈ 1.44x too fast. `decay_model.half_life` is correspondingly
  set to `P10D`, the value that reproduces the curve the benchmark suite
  actually validated — the former `P14D` was a mislabelled ~9.7-day half-life,
  not a 14-day one (#105)
- Benchmark metrics suffixed `_percent` are no longer scaled a second time by
  the reporter, which printed a +63% accuracy improvement as +6304.3% (#105)
- Documentation and compliance artifacts that asserted a 14-day trust half-life
  now state the value the schema implements (#105)
- Removed an unverified "85%+ GA accuracy" claim from the benchmark README in
  favour of the command that reports the measured figure (#105)
- Corrected NIST AI RMF profile reference to a trust source (`unverified: 0.20`)
  that does not exist in `authority_trust_model.yaml` (#105)
- `decay_model.min_trust` is now enforced: the recency factor is floored rather
  than decaying asymptotically to zero. It was declared in the schema and cited
  by the ISO 42001, EU AI Act and NIST AI RMF artifacts as an implemented
  control, but was read by nothing (#106)
- `tools/sync_skill_schemas.py` is idempotent and self-healing: its comment
  rewrite reapplied itself to already-rewritten text, so each run stacked
  another `(repo-level)` prefix onto the 17 bundled workflow catalogs. CLAUDE.md
  documents the command, so following the project's own instructions corrupted
  those files. The rewrite now strips every existing prefix before re-applying
  exactly one, so a tree a previous run had already doubled is repaired rather
  than left stable-but-corrupt (#107)
- `skills/receive/reference/event_schema.yaml` was an orphan copy that
  `sync_skill_schemas.py` could not reach, because the sync only bundles into
  skills that carry a `reference/workflow_catalog.yaml`. It is now resynced and
  the canonical-schema validator asserts every vendored copy matches its
  source (#107)
- Remediate benchmark suite drift from ontology and SDK (#100)
- Use public `all_edges()` API in benchmark validator instead of private `_loaded_edges` (#100)
- Install real SDK, remove all mock/skip patterns (#99)

## [v1.0.5] — 2026-01-29

### Added
- Perspective validation checklist (PVC) system (#34)
- OASF-to-Grounded-Agency capability mapping file (#32)
- OASF compatibility adapter with full test suite (#33)
- OASF-inspired workflow patterns added to catalog (#31)
- Modality handling guide for vision, audio, and multimodal domains (#30)
- Modality-specific domain profiles for vision, audio, and multi-modal (#28)
- OASF safety extensions proposal (#29)
- OASF coverage report and comparison documentation

### Fixed
- Skills made self-contained with bundled transitive dependencies (#36)

## [v1.0.4] — 2026-01-27

### Added
- Domain-specific workflow templates and default profiles (#12, #17)
- Automated validation for domain profiles (#18, #19)
- Claude Agent SDK integration with safety patterns (#11, #16)
- Benchmark suite for Grounded Agency validation (#10, #15)
- Agent failure taxonomy research (#8, #13)
- Replanning and goal uncertainty capabilities (#9, #14)
- Missing edge types to ontology (#2, #20)
- Comprehensive FAQ with rationale for rejected proposals

### Fixed
- Complete edge graph for 5 orphan capabilities (#1, #21)
- Flattened skills directory structure for Claude Code compatibility

### Changed
- Migrated capability ontology from JSON to YAML format
- Updated capability count references from 35 to 36
- Migrated from 99 to 36 atomic capabilities with domain parameterization

## [v1.0.0] — 2026-01-24

### Added
- Initial publication candidate
- Capability ontology with 36 atomic capabilities across 9 cognitive layers
- Typed I/O contracts and explicit dependencies for all capabilities
- Workflow DSL spec v2 with bindings, conditions, gates, recovery loops, parallel groups
- Canonical world state and event schemas (provenance, uncertainty, retention, lineage)
- Identity taxonomy and identity resolution policy
- Authority trust model (weights, decay, field-specific authority)
- Compiler-grade validator with $ref resolution, type inference, consumer input schema checking, and patch suggestions
- 12 reference workflows in workflow catalog
- Safety hooks (checkpoint enforcement, audit logging)
- Domain profiles for healthcare, manufacturing, data analysis, and personal assistant
- Conformance test suite with 5 fixture tests
