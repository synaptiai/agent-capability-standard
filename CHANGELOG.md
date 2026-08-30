# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
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
- Enhanced CLAUDE.md with workflow orchestration guidelines and core principles

- New `tools/validate_constraints.py`, run in CI, asserting that every pin in
  `constraints.txt` names a package `pyproject.toml` declares and falls inside
  the range declared for it. The two files state overlapping facts about the
  same packages; this is what makes disagreement fail loudly instead of
  surfacing as an opaque pip resolution error

### Fixed
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
