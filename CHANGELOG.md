# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [v2.0.0] — 2026-10-29

Implements Standard v1.1.0 (Candidate Standard) with RFC-0003 and RFC-0004
(#114, #116) and replaces the 1.0 validator and engine with one Rust core
(#115). The Standard's version (v1.1.0; v1.0.0 still supported) is separate
from this plugin release.

**Upgrading from v1.2.0:**
- Building from source needs a Rust toolchain (rustc >= 1.86): the validator
  and executor are the `grounded_agency._core` extension, built by maturin
  with `pip install -e ".[dev]" -c constraints.txt`.
- `transform.output` is `object|array` (ontology 2.1.0); a reference to it
  without an annotation is now B204.
- Validation is stricter: catalogs that passed 1.0 may now get errors or
  warnings (unknown fields W604, unbound required inputs W615, literal type
  mismatches B203, among others listed below).
- A quorum's model families count only when the host attests them.

### Added
- **Release workflow.** `.github/workflows/release.yml` publishes a GitHub
  Release with the tag's CHANGELOG section as its notes, for a pushed `v*`
  tag or, run by hand on `main`, for a tag it creates there;
  `scripts/release_notes.py` refuses a tag that does not match `plugin.json`
  or has no section
- **Delegate identity (#114, RFC-0004 amendment).** With `identity@1` a
  host may attest who took a delegation (`effective.identity`); a waiting
  delegate keeps only results from that principal (others dropped as
  `delegate_identity`), a malformed or contradicting identity is R402, and
  `quorum.require_distinct_identities` counts one verdict per attested
  principal. Quorum model families now count only as attested. Validator,
  executor, schema, eleven runtime fixtures and docs
- **Standard changes from the orchestrator fixtures (#114).** Gates can
  `end` a run successfully (`RunResult.ended`); a step can `delay` before
  it goes on (`wait@1`), without a fake event to wait on; an `accept_from`
  or `correlate` built from a missing value fails the step at once (R402)
  instead of dropping every sender, or matching every event that lacks the
  key; and
  `after_deferral: run` (`approval@1`) lets a step that does not depend on
  a deferred one, such as an escalation, run anyway. Validator, executor,
  Python runner, schema, runtime fixtures and docs
- **W616 `VERSION_FEATURE_MISMATCH`.** A workflow that declares standard
  1.0 but uses a 1.1 feature (`workflow_extensions.requires`, gate
  `phase` or `end`, the `in` operator, failure-mode `when` or `on_error`)
  warns once per feature, so a forgotten version bump no longer passes
  silently
- **The #114 author's orchestrator workflows as conformance fixtures.** The
  nine workflows they ported to the v1.1 candidate (revision 1.1e, which
  uses gate `end`, `delay`, `after_deferral` and a waiting `delegate` per
  reviewer) are a static fixture (`pass_orchestrator_port`, kept as
  contributed), and fifteen runtime fixtures (`orchestrator_*`) script runs of
  them: routing into a nested delegation, a liveness recovery, a quorum
  that passes and one that loops after a RETHINK, a self-merge and a red
  base that escalates to incident triage, an owner-approved and an
  unattended (deferred) message, an owner answer with a foreign one
  dropped, a question ended for more research, a scheduled sweep where
  only the reminder is deferred, an escalation that interrupts the owner,
  a prod notice then an early end, and both kinds of daily report
- **Contributed runtime fixtures.** Twenty scripted runs the #114 author
  wrote from the spec (`gap1_*` standing mandates, `gap2_*` verdict scope
  and `min_full`, `gap3_*` R406 and R401 around the deadline, `gap5_*` the
  authenticated principal) are kept as sent in
  `tests/conformance/contrib/`; the generator checks and copies them
- **Read-only reviewers and per-reviewer waits (#114).** `delegate` takes
  `read_only` (attested in `effective`), and `quorum.require_read_only`
  requires it of every reviewer. `wait` is allowed on `delegate`: the step
  delegates, then waits for that delegation's result, so a `retry` replaces
  a reviewer that went silent without asking the others again; a quorum's
  `verdicts` may list one reference per reviewer step. Host or device
  placement of a delegated step is recorded as an open question in
  RFC-0003
- **Agent identity, `identity@1` (RFC-0004, #114).** A new
  `schemas/agent_identity_schema.yaml` says who a party is (principal, kind,
  role, model family, owner, how it was authenticated, trust class).
  `receive`/`synchronize` take `sender_check`, `accept_trust_classes` and
  `always_ask_trust_classes`: the executor drops items whose sender's
  identity fails a check, keeps the identity on each kept item, and asks a
  person (never a standing mandate) to approve any step that requires
  approval and uses, directly or through other steps, an item from an
  "always ask" class (or one with no trust class). Runs can carry an
  actor identity onto every action record (`WorkflowRunner.run(...,
  actor_identity=...)`), and `AgentDescriptor.identity()` produces one.
  `world_state_schema.yaml` 1.1.0 and `authority_trust_model.yaml` 1.1.0
  (default weights per trust class) follow; `validate_canonical_schemas.py`
  keeps the trust classes and the world state's identity type in step with
  the identity schema
- **`in` in condition expressions (#114).** `x in y` tests membership in a
  list or the keys of a map, as in CEL (STANDARD v1.1 §5.8); the cel-go
  differential covers it
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

### Changed
- **`transform.output` is `object|array`** (ontology 2.1.0), so a
  transform can return records as a list. **Breaking:** an unannotated
  reference to it is now B204, as for any union; the reference, domain,
  example and test catalogs annotate theirs.
- **`retrieve` and `search` are soft prerequisites of `ground`** (ontology
  2.1.0): a retrieved source or a search result is evidence to ground a
  claim in, so grounding generated text against them no longer warns
  W601.
- **Catalog failure modes all fire.** Of the 23 in the reference,
  manufacturing and digital-twin example catalogs that had neither `when`
  nor `on_error`, 15 gained a trigger (a step error, or an empty or
  failing output) and 8 were removed: they described a normal outcome (no
  vulnerabilities, nothing to decompose, conflicts `integrate` resolved),
  a check a later step or gate already makes (compliance, the cleaned
  data's quality), or a threshold the step does not have. An empty batch
  in the digital twin sync loop now ends the run early (gate `end`)
  instead. Runtime fixtures `domain_twin_no_events` and
  `domain_rag_no_passages` run two of them.
- **`schedule_management` with no free slot completes.** Ranking, planning
  and drafting are skipped, and the explanation (now given the slots and
  conflicts) and the audit still run; before, a `stop` gate ended the run
  R403 with neither. A runtime fixture (`domain_schedule_no_slot`) runs
  this path.
- **Unattended runs ask standing mandates, and deferral continues (#114).**
  A `standing_mandate` approver is asked even when nobody is present; the
  host answers `approved`, or `unavailable` when no mandate covers the
  action, and only then does `when_unattended` apply. `defer_to_queue`
  defers the step and every later step that depends on it (reads its
  output, may act on the world, or follows it in the ontology), runs the
  steps that only read, reason or record, and ends the run `deferred`, so a scheduled sweep
  finishes its other work. `RunResult.deferred` lists the deferrals, and the
  default `Host` answers `unavailable` for a standing mandate
- **Quorum independence per reviewer (#114).** `forbidden_inputs`
  takes a per-reviewer mapping, verdicts carry `scope: full | delta`,
  and `quorum.min_full` requires passing full sweeps
  (`review_verdict_schema.yaml` 1.1.0; `tally.full_passes`)
- **Lost liveness is R406, separate from the R401 timeout (#114).**
  Lost liveness is now R406 (`LIVENESS_LOST`); failure modes (`on_error`)
  and `retry` take it, so a workflow can re-check a quiet worker and
  escalate only when the wait expires. A failure mode that handled lost
  liveness through `on_error: R401` must add R406
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
- The `claude-agent-sdk` floor is `>=0.1.52`, the oldest release whose
  `ToolPermissionContext` carries the `tool_use_id` that keys the checkpoint
  reservation in `can_use_tool`, rather than the newest release available. It
  was briefly `>=0.2.148`, which excluded working installs without cause, and
  then `>=0.1.25`, which admitted releases where the permission callback
  could not name its own reservation
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

### Fixed
- **W608 sees waits in invoked workflows.** An `invoke` of a catalog
  workflow that can wait (any of its steps, handlers included, or one it
  invokes) counts as a wait, so a checkpoint taken before it no longer silently covers a later
  `mutate` or `send`. The #114 port's checkin_recovery mutate was the first
  case found; revision 1.1e checkpoints again after the escalation.
- **A recovery loop replaces every waiting delegate it runs again.** A loop
  from a later step (a blocked quorum, say) back to before the reviewers
  delegated them again without `replaces`, so the host could not cancel
  the earlier delegations; only a loop from the delegate itself named
  them. A pending replacement is kept until the delegate next delegates,
  also across a pass that skips it. Runtime fixtures
  `delegate_wait_replaced_by_later_loop` and
  `delegate_wait_replacement_survives_skip`.
- **Whole-branch review (#114): executor.** Forged snapshots that passed the
  state check and then panicked are refused at restore; resolved inputs
  deeper than I-JSON allows fail the step (R402) instead of breaking
  snapshots; a huge `min_approvers` still snapshots; `correlate` matches in
  a stable key order across restores; the executor's own refusals of an
  invocation are not retried; a recovery loop back to a waiting delegate
  carries `replaces`, also when the loop targets an earlier step or a
  retry's re-delegation failed first; clock values are capped at year 9999; a re-asked
  approval's record says why
- **Whole-branch review (#114): validator.** The YAML loader stops deep
  compact sequences at its nesting limit instead of overflowing the stack;
  same-file `#/...` `$ref`s and chains of refs resolve (only hops count
  toward the limit), and the schemas one validation resolves share a budget
  of 200,000 nodes, so refs that fan out are refused (S302) rather than
  exhausting memory; literal and template bindings are type-checked
  (B203), an explicit null included (except `invoke`'s `input`, where it
  means no inputs); reference syntax errors have one code everywhere (B201, B205 for
  an empty annotation); W606 follows `invoke`; an invoke cycle is reported
  once per workflow, not once per edge; diagnostics come in catalog order
  (workflow, then step); B202 has one wording. The stricter rules are
  listed in the [spec changelog](spec/CHANGELOG.md)
- **Whole-branch review (#114): catalogs.** `digital_twin_sync_loop` rolled
  back twice on a failed verification (an after-gate and a failure mode on
  the same condition); it rolls back once. `stop` gates that ended healthy
  cycles as failures are skips or conditions, so their audits run. Literal
  types (`plan.constraints`, `detect.threshold`, `search.scope`,
  `ground.claim`) match their inputs, steps bind the outputs they reason
  about, and failure modes on effectful steps have `on_error` triggers.
  The clarification workflows gate on what the analysis found, not on its
  confidence
- **The checkpoint hook did not block anything (#114).**
  `pretooluse_require_checkpoint.sh` read its payload from an argument,
  but Claude Code passes it on stdin, and it signalled a block with exit 1,
  which Claude Code treats as a non-blocking error. It reads stdin now (an
  argument still works), blocks with exit 2 and the reason on stderr, and
  still fails closed: every `Write`, `Edit`, `MultiEdit`, `NotebookEdit` and
  `Bash` call needs a valid marker
- **Whole-branch review (#114): catalogs, second pass.** Rollback steps no
  longer require a checkpoint of their own (the one before the mutation
  was spent, so the executor took a new one of the broken state first).
  A verify or verification step that errors rolls the mutation back;
  nothing is rolled back when nothing was mutated, and audits run after
  the rollback so they record it. `data_quality_pipeline` writes nothing,
  so it no longer checkpoints or rolls back and its risk is low
- **Whole-branch review (#114): skills.** Every capability skill's output
  contract, field table and examples use the ontology's field names and
  types (`verify` returns `passed`, `checkpoint` `checkpoint_id`, `detect`
  `matches`, and so on), and their safety constraints match the
  ontology's flags and risk
- **Whole-branch review (#114): Python.** The permission callback releases
  a denied call's checkpoint reservation, and without a `tool_use_id` only
  checks for a valid checkpoint. `WorkflowRunner` turns a host response the
  run refuses into R402 for a capability or `HostResponseError` otherwise,
  bounds the unanswered polls of each action (`max_polls`), and raises `RunStartError` from
  `restore` and for inputs that are not JSON data. The validator raises
  `FileNotFoundError` and the other `OSError` types for a missing or
  unreadable catalog or ontology, as `load_yaml` does. Boolean and NaN
  weights are rejected in profiles. The bundled ontology copies are kept in sync. The
  `acs` console script, which only worked inside a checkout, is removed:
  run `python tools/scaffold.py`
- **Whole-branch review (#114): tooling.** The conformance runner compares
  each fixture's codes exactly and gives each run its own suggestions file
  (`validate_workflows.py --suggestions-out`); four negative fixtures that
  were 780-line copies tripping unrelated checks are minimal now. CI runs
  the YAML-sync and transform-ref validators, installs with the
  constraints file everywhere, and checks the formatting of `tools/`
- **Unbound required inputs were silent (#114).** A step that does not
  bind an input its capability requires is W615. The reference catalog
  left 60 required inputs unbound across eight workflows; they are bound
  now, and `debug_code_change` gains a `bug` input to bind them from.
  Binding `checkpoint_id` exposed that the rollback steps of
  `debug_code_change` and `digital_twin_sync_loop` ran even when
  verification passed; they are skipped then, as in the other workflows.
  `digital_twin_bootstrap` read a skipped step's output when a world state
  was passed in; it now syncs from that state instead. `retry.max` and
  `retry.backoff` are validated (S303)
- **The example catalog used the v1 capability names (#114).**
  `examples/digital_twin_sync_loop.workflow_catalog.yaml` now holds the
  digital twin workflows of the reference catalog verbatim (a test keeps
  them identical) and is validated in CI with `--strict`
- **Runtime fixtures are generated in the repository.**
  `scripts/gen_runtime_fixtures.py` writes `tests/conformance/runtime/*.json`,
  and CI checks they are up to date
- **Skill docs named inputs the capabilities do not have.** The procedure
  text, examples and `argument-hint` lines of the capability skills now use
  the ontology's input names
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

## [v1.2.0] — 2026-02-04

The full list is in the
[v1.2.0 release](https://github.com/synaptiai/agent-capability-standard/releases/tag/v1.2.0);
v1.1.0 and v1.1.1 are documented in their GitHub releases.

### Added
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
- Enhanced CLAUDE.md with workflow orchestration guidelines and core principles

### Fixed
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
