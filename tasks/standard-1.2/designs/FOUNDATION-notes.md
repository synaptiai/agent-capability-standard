# FOUNDATION notes

Changes made while implementing `FOUNDATION.md`, where the plan was wrong
about the repository, two parts disagreed, or the plan left a choice open.
Each note says what was done and why, so the workstreams start from the same
facts.

## 2026-11-15 — Parts A, B and F2 (ontology, schemas, contracts rendering)

**Ontology (Part A).**

- Applied by structure, written as a minimal text diff: only the entries the
  deltas change were re-serialised; every other line of
  `schemas/capability_ontology.yaml` keeps its text, comments included. The
  merged result equals the output of
  `tasks/standard-1.2/tools/merge_ontology.py` and FOUNDATION A3 node for
  node (checked by script), with `meta.generated_at`
  `2026-11-15T00:00:00.000Z` and the file's `# Version:` comment line at
  2.2.0. Checked against A5: no `required` list, edge, layer or flag changed;
  no existing property was removed or retyped.
- **Model identifier example.** The maintainer's rule for this round is that
  no model name or identifier appears in a file. The designs' example model
  identifier in `delegate.effective.model_id` (ontology),
  `agent_identity.model_id` and the world state's `AgentIdentity.model_id` is
  replaced by the fictional `acme-large-2`. S3's §5.15 text and vectors should
  use fictional identifiers in the same way (for example `acme-large-2`,
  family `acme`). The `model_family` description's "such as claude or gpt"
  (model lines, not identifiers) is kept as designed.

**Schemas (Part B).**

- `schemas/host_protocol.schema.json` (B8): `$id` is
  `https://github.com/synaptiai/agent-capability-standard/schemas/host_protocol.schema.json`,
  as every other schema of the repository, not S2b's `acs.synapti.ai` form;
  with it, `run_options.grounding`'s relative
  `workflow_catalog.schema.json#/$defs/grounding` resolves to the catalog
  schema's own `$id`. Per C33, `head.run_id` and
  `InvokeCapability.idempotency_key` are declared but not required: S2b adds
  `run_id` to `head.required` and S5 `idempotency_key` to
  `InvokeCapability.required` when their executors emit them. The
  `trace_event` description names the kinds added in 1.2 (`run_resumed`,
  `invoke_resumed`, `run_cancelled`, `grounding`, `person_required`).
- `schemas/workflow_catalog.schema.json` (B7): every member of B7's table
  lands except `"grounding@1"` in `workflow_extensions.requires`. The site
  (`site/src/lib/spec-dsl-figures.ts` `extensionTiles`) fails its build and
  tests when that enum names an extension the newest Standard's §5.9 table has
  no row for, and the validator does not know `grounding@1` yet; S4 adds the
  enum value with its §5.9 row and the validator support. `$defs.grounding`,
  `workflow.grounding` and `F505` in `fireable_code` land here
  (`host_protocol.schema.json` references `$defs.grounding`).
- `tests/conformance/runtime/schema/fixture.schema.json` (B9) requires
  `header`, as B9 says; the 175 generated and 20 contributed fixtures do not
  carry it yet. Every one of them validates against the schema once
  `"header": null` is added (checked), which F1 item 6 does with the start
  option. Nothing reads the schema before then.
- `schemas/interop/tool_binding.schema.json` (B10): the `destination`
  description drops S1 3.3's trailing "Added by S5." (design bookkeeping,
  not schema text).
- `schemas/profiles/profile_schema.yaml` (B12): S6 3.6 is the base, but its
  `allowed_destinations` ended with the placeholder "(S5's description and
  pattern rules apply.)". The member is S5 3.6's block instead (items
  `minLength: 1` and the full pattern description), which S6's sentence
  summarises. The shipped profiles are not migrated (S6 3.7) and do not all
  conform to the new schema (for example `required_anchor_types` values that
  are not anchor kinds); `tools/validate_profiles.py` checks its own
  constants, not this file, so CI is unaffected until S6 rewrites it.
- `tests/conformance/destinations/match.json` (B15): the design's
  Markdown holds the NFC and NFD `café` entries as literal characters; the
  file writes them as `\u` escapes (`caf\u00e9`, `cafe\u0301`), as its own
  description and S5 3.7 require. The Rust test that reads it lands with
  `core/src/destination.rs` (F1 item 13).
- `tests/conformance/approval/digests.json` (B15): every vector has
  `"kind": "step"`; `fields` documents `kind` and `call`, and `approval` and
  `inputs` say "for a `step` vector". The header (`standard`, `section`,
  `status`, description) is unchanged: S2a makes it normative. In
  `tests/test_approval_vectors.py` the executor replays step vectors only
  (`STEP_CASES`), and the field test accepts `step` and `tool_call` vectors.
  The binding's copy is still written; F3 deletes it.

**Version lines touched here.** Bumping the ontology to 2.2.0 fails
`tests/test_version_lines.py` unless the files it compares follow, so this
change sets the ontology (not the Standard) in the ROADMAP Versions table
(ontology row only), `schemas/interop/oasf_mapping.yaml`
(`ontology: "2.2.0"`, `standard` still 1.1.0) and the header of
`docs/integrations/oasf_coverage.md`. The Standard values follow with
`spec/STANDARD-v1.2.0.md` (Parts D, E).
`schemas/interop/standard_agents_mapping.yaml` still cites 1.1.0 / 2.1.0 (no
test compares it; the same major is valid under §11.6); Part E changes both
values together.

**Code (Part F2).**

- `_core.Validator.contracts()` returns
  `{capability: {"input": ..., "output": ...}}` in ontology order
  (`Context::contracts_json`). It does not yet refuse a contract whose `$ref`
  is left unresolved (S6's refinement, §4.1.2); both generators refuse one
  instead (`RenderError`; a sync problem).
- `core/src/types.rs`: when a `oneOf`/`anyOf`/`allOf` dedupes to a single
  member type, `schema_type` returns that type (still marked ambiguous, so a
  reference needs an annotation as before) rather than a one-member union,
  whose printed form `union<object>` would not parse back. Evidence anchors
  type as `union<object,string>` as designed. Validated with ontology 2.1.0
  and 2.2.0, the 89 catalogs of the repository give the same codes at the
  same steps; the one difference is the `actual_type` of
  `fail_type_mismatch_binding`'s B203 (`array<unknown>` became
  `array<union<object,string>>`), as S4 predicted.
- `scripts/gen_capability_json_schemas.py` resolves `$ref`s with the
  repository as schema root (`SCHEMA_ROOT`), so a test that moves `ROOT`
  still renders. `render_document(ontology, contracts)` now takes the
  resolved contracts. `tests/test_capability_json_schemas.py` compares the
  rendering with the resolved contracts (`nullable` left out), checks that
  every `nullable: true` member admits `null`, and builds the strict ontology
  with `nullable_as_null=False`.
- `tools/validate_canonical_schemas.py`: `validate_shared_types` (Anchor and
  Uncertainty equal without descriptions); the existing identity equality
  check now covers `model_id`; field authorities are checked in
  `field_authority.fields` as well as `examples`. Two test expectations moved
  with the data: `test_catches_malformed_schema_version` anchors on the
  taxonomy's `version: 1.1.0` (B3), and
  `test_catches_phantom_field_authority_source` now fails through `fields`,
  the first of the two identical lists. `tests/test_standard_agents_interop.py`
  reads the world state Anchor's kind `pattern` instead of its former `enum`
  (B1).
- `tools/sync_skill_schemas.py` writes the skill-local schemas with
  `allow_unicode`, so the contracts' `§` is written as itself, not as a YAML
  `\xA7` escape.
- `site/test/capability-figures.test.ts`: the hand-read `outputFields`
  expectation for `mutate` now lists the three optional fields every 2.2.0
  output gains (`confidence`, `inference_method`, `uncertainty`) as contract
  fields the skill's fence leaves out. When S4 adds them to the skills'
  Output Contract fences, it updates this expectation.
- `site/src/lib/repo.ts` gains `trackedIn` (the files directly in a
  directory); the site's runtime fixture counts (`index-figures.ts`,
  `spec-tail-figures.ts`) use it, so `tests/conformance/runtime/schema/` is
  not counted as a fixture, as S2b 3.6 intends for every reader.
- `site/src/lib/views.ts`: a field whose schema is a `$ref` shows the type's
  name (`Uncertainty`), `evidence_anchors` shows `array of Anchor (or
  deprecated string or object)`, and `pattern` is listed as a constraint; with
  a `views.test.ts` case.

**Pre-existing failure fixed.** `tools/validate_doc_links.py` failed on HEAD
on a quoted link in `S2b.md` (part 7, the GROUNDED_AGENCY.md sentence), which
resolves relative to `tasks/standard-1.2/designs/`. The quoted link is now a
code span; the text to write into `docs/GROUNDED_AGENCY.md` is unchanged.

## 2026-11-15 — Parts C, D, E and F1 item 16 (codes, Standard text, version lines, RFCs)

**Codes (Part C).** The 15 codes are in `core/src/diag.rs` and
`grounded_agency/errors.py` as C2 lists them, in code order; `_core.CODES`
has 61 entries and `tests/test_errors.py` holds.

**`spec/STANDARD-v1.2.0.md` (Part D).**

- Copied from 1.1.0 with the D1 header, except `**Date:**`: the design's
  `<the release date>` would be read by the site as the date `<the` (and put
  into the page's `datePublished`), so the file says `2026-11-15`, the date of
  this text; the release sets it.
- Every new heading of D2 is in place with one HTML comment naming its owner
  and design part (`<!-- owner: S4; text: S4.md part 2.5 -->`). D2 rows that
  edit existing sections (§1 items 10 to 12, §2 rows, §3.3 bullets, the §10.3
  paragraphs, §12.5 patterns) get no marker; their owners add the text where
  D2 says. §11.5 carries a comment that S6 replaces it. §5.19's comment names
  S4's and S5's edits and C3/C5.
- §11.7 holds FOUNDATION E2's table under a comment; S6 adds the two
  sentences of S6 2.20 above it.
- The D3 one-liners are in (§6.1, §10.1, §5.9). §1.1 and §13.1 gain RFC 3986,
  RFC 5545 and RFC 6901; §13.2 RFC-0005 to RFC-0010 and the Agent Skills
  specification; Appendix B S4's sentences and S6's last line.
- §9 is C3 exactly: the two §9.1 paragraphs (S1's, then S3's), the merged rows,
  W617 to W626 with C1's meanings, and S3's §9.8 with S1's refusal paragraph
  after the paragraph on `location`'s keys, before the wrapping sentence.
- Appendix D is D4's skeleton after Appendix C, which stays.
- `spec/EDGE_TYPES.md`'s header names STANDARD-v1.2.0 (D3); its body is S3's.

**RFCs (F1 item 16).** `spec/RFC-0006` to `RFC-0010` are Accepted, target
Standard v1.2.0, dated 2026-11-15. Each Summary is the design's part-9 summary
(RFC-0006: S2b's opening paragraph, S2a's Part A summary, S2b's Part B
summary); every other required section is one line pointing to the design's
part 9, so `tools/validate_rfcs.py` passes. RFC-0005 is unchanged (Draft) until
S1 replaces it. RFC-0002 stays Draft; its `**Target:**` now reads "A later
Standard 1.x, after 1.2.0" (C37).

**Version lines (Part E), with the maintainer's overrides.**

- The plugin stays 2.0.0 and the Python package 0.1.0 (versions change when a
  release is cut). `spec/ROADMAP.md`: the Standard row is 1.2.0; the Standard
  table lists 1.2.0 as "Candidate Standard, current" with the date
  "Unreleased", and 1.1.0 and 1.0.0 as Supported; a paragraph lists what 1.2.0
  adds and points to Appendix D; RFC-0002 moves to a later 1.x; the mermaid
  diagram follows. The introduction keeps "Plugin 2.0.0 implements Standard
  1.1.0" and adds "The unreleased work on `main` implements the Standard 1.2.0
  Candidate."
- `tests/test_version_lines.py`'s introduction test required the pair to be
  (plugin, current Standard), which the override makes false between releases.
  It now requires the declared plugin, a Standard no later than the current one
  that has its own file, and, when that is not the current one, a mention of
  the current Standard elsewhere in the introduction.
- **Not done here, and why:**
  - The TypeScript package row of the Versions table (0.1.0) and the test's
    fifth line: `packages/acs-core/package.json` does not exist until F3, and
    the row's link and the test's declaring file would point at nothing. F3
    adds the row and the fifth line together.
  - `SUPPORTED_VERSIONS` with `(1, 2)`: it lands with the other version
    helpers of F1 item 2 (`target`, `check_cited`), not alone; until then a
    workflow that declares 1.2 is V109, as before, so no validation result
    changes here.
  - TypeScript `STANDARD_VERSION`/`SPEC_VERSIONS`: they live in
    `packages/acs-core` (F3); the binding's `ontology.ts` still says 1.1.0,
    which its records cite, until the binding implements 1.2.
  - `schemas/interop/standard_agents_mapping.yaml` stays 1.1.0 / 2.1.0:
    `tests/test_standard_agents_interop.py` requires it to equal the versions
    the row-level mapping (`docs/research/analysis/standard_agents_mapping/index.yaml`)
    was made against, which are 1.1.0 / 2.1.0 at commit 3e4cd94. A citing
    document of the same major stays valid (§11.6). The workstream that revises
    the binding conventions for 1.2 (S1) moves both, or changes that test.
  - `CITATION.cff` and `spec/CITATION.cff` stay 1.1.0 / 2026-10-28: a citation
    names a released version and its release date; the release sets both.
- Changed as E1 says: `schemas/interop/oasf_mapping.yaml` (`standard:
  "1.2.0"`), `docs/integrations/oasf_coverage.md`, README (badge, Versioning
  note, the two Standard links, the status line), `spec/CONFORMANCE.md`,
  `spec/WHITEPAPER.md` (footer, the header example), and the docstrings of
  `grounded_agency/errors.py`, `grounded_agency/trust.py` and
  `scripts/gen_standard_agents_binding.py` (not the digest file's header,
  which S2a changes).

**Site.** With 1.2.0 the newest Standard file, the site makes it the current
page:

- `src/lib/runs.ts`: Appendix D is an exempt run (c), as Appendix C;
  `test/runs.test.ts` lists it.
- `src/lib/spec-slots.ts`: 1.2.0 draws `SPEC_SLOTS`. 1.1.0, now an older
  version, gets `SPEC_SLOTS_110`: the figures of `SPEC_SLOTS` that draw only
  from its own text, plus §9.1's categories in place of the code families, as
  1.0.0 has. The figures drawn from the ontology, the schemas, the diagnostics
  or the runtime fixtures (and §9's code tables, which are checked against
  `core/src/diag.rs`) show current data and stay on the current page.
- `src/lib/spec-tail-figures.ts` `conformanceLevels`: compares §10.2's levels
  with §10.1's L rows only, since §10.1 now also lists the classes SL and EX,
  whose requirements are §10.4 and §10.5. When S1 and S2b fill those sections,
  a figure for them is the site owner's choice.
- Tests that named 1.1.0 as the current Standard now read the newest file
  (`spec-figures.test.ts`, the F-S27 case and `SPEC_PAGES` in `dist.test.ts`)
  or name 1.2.0 (`routes.test.ts`, `twins-md.test.ts`); `data.test.ts`'s V101
  description follows the merged row.

## 2026-11-15 — Part F1 items 2 to 15 and Part F3 (code spine, TypeScript package)

**Start options and validator options fail closed (F1.5).** FOUNDATION says
the new members are "stored in the run's state and unused until their owner
merges". Stored and unused, a profile, a grounding policy or a destination
policy that a caller gives would be silently ignored, and the run would go
ahead as if it were absent. Instead every member whose behaviour is not
implemented yet is refused when it is given:

- `exec::StartOptions` has all nine members (`attendance, run_id, now_ms,
  actor_identity, header, records, profiles, grounding, destinations`), no
  `Default`. `Run::start` refuses `records: Actions` and a non-empty
  `profiles`, `grounding` or `destinations` with the new
  `StartError::Unsupported`; each workstream deletes its line of
  `StartOptions::unimplemented()` when it implements the member. The state
  has the five members (`header`, `records_mode`, `profiles`, `grounding`,
  `destinations`), each `#[serde(default)]` and left out of a snapshot while
  it has its default, so a 1.1 run's snapshot is byte for byte what it was;
  `restore` refuses a state that holds one this executor does not implement.
- `validate::Options { header, profiles, agents, catalogs }` (`Default`);
  `validate::validate_with(ctx, catalog, &options) -> Result<Report,
  LoadError>` refuses non-empty `profiles`, `agents` or `catalogs`
  (`Options::unimplemented()`, the same pattern). `validate_catalog` is
  unchanged. `catalogs` is `Vec<(Value, Option<String>)>` (a catalog and its
  header); S3 may change the type when it adds `validate_set`.
- Python `Run.start(..., *, header, ..., records="approvals", profiles=None,
  grounding=None, destinations=None, catalogs=None, agents=None)` and
  `Run.restore(..., *, catalogs=None, agents=None)`: an empty list is the same
  as None; a non-empty `catalogs` or `agents` raises `ValueError` (Rust has no
  member for them yet: S3 adds `start_set`/`restore_set`). `grounding` dicts
  are checked (`Policy::new`, `check_ids`) before the refusal, so a malformed
  policy is reported as such.
- `header` is required everywhere (Rust struct literal, Python keyword
  without default: `TypeError` names it). A header that is not a version
  (`MAJOR.MINOR[.PATCH]`) is refused at start (`StartError::Header`), even
  when the workflow's own `spec_version` would make validation ignore it,
  since the state keeps it and `restore` checks it.

**Version helpers and W616 (F1.2, F1.3).**

- `SUPPORTED_VERSIONS` has `(1, 2)`. The only validation result that changes
  in the repository's 111 catalogs (checked by script, before and after) is
  the text of `fail_unsupported_spec_version`'s V109, which now lists 1.2 as
  supported.
- `semantics` is `pub(crate) mod`; `parse_version`, `target` and
  `SUPPORTED_VERSIONS` are `pub(crate)`; `check_cited` and `Flags` are
  re-exported from `validate`. `target` is unused until a workstream calls
  it (`#[allow(dead_code)]` with that reason; remove the attribute with the
  first call). `check_cited` messages: S303 "'standard' must be a version
  string MAJOR.MINOR[.PATCH] ..."; V109 "the document cites standard 1.3,
  which is not supported (supported: 1.0, 1.1, 1.2)" and "... cites ontology
  3.0, but this implementation uses ontology 2.2.0; another major is not
  compatible (§11.6)". A value given as `None`/absent is not checked.
- `Ontology.version: Option<String>` (from `meta.version` when a string).
- W616 is table-driven: `semantics::FEATURES` (`Feature { since, name,
  first_use }`), reported in table order for every feature with `since >
  target`, for any supported target. The message keeps 1.1's wording,
  generalised ("the workflow targets standard 1.0 by its 'spec_version', but
  gate 'phase' is new in 1.1 and a 1.0 consumer does not know it";
  suggestion "declare spec_version \"1.1\"", or "... or a 1.1 header"), so no
  existing W616 message changed; S6's alternative wording in 5.1 was not
  used. `version_feature_diag(name, since, version, by_header, field)` takes
  `by_header` beside S6's arguments (the manifest check of S3 passes
  `true`). Table order equals the old discovery order except when the `in`
  operator is first used in a step's `condition` before a gate `phase`,
  `action: end` or failure-mode `when` of the same or a later step: the
  fields and codes are the same, the order of those W616s differs.

**Effective flags (F1.4).** `semantics::Flags { risk, mutation,
requires_checkpoint, requires_approval }` with `NONE`, `of`, `join` (S3's
type, here rather than in S3's `agents.rs`), `Effective { flags, person }`
and `effective(node, step, maxima, policy)`. Called in `validate/mod.rs` for
`Placed.requires_checkpoint` (which `wait.rs` and the handler checks of
`recovery.rs` read) and for W606, and in `exec/program.rs` for `Step`. The
`approval` block rule reads `effective(..., None, &Policy::default())`, so
it never depends on profiles (S3's review item 8). `core/src/profile.rs` is
a stub (`Policy` with `is_empty`, `raise` returning `Raise::default()`), for
S6 to replace.

**Error reasons (F1.8).** `Response::Error.reason: Option<Value>` (any
value deserialises); `machine::REASONS` (the 12 tokens of C5) and
`is_reason` (a token, or `x-` + a lowercase letter or digit + at most 61 of
`[a-z0-9_.-]`); `Reason { token, ignored }`. `exec_error_with` and
`step_error_with` carry it: `retry` and `step_failed` trace details get
`reason` (or `reason_ignored` with the value), `StepError.reason` keeps it,
the run's `Failed` action and `run_failed` trace get `reason`, and an
approved step's record that fails gets `reason_code`. `end_frame`'s error
is a small struct `Fail { code, message, reason }`. Every `Error` response
(capability, event, checkpoint, failure checkpoint, rollback, recheck)
passes its reason. Without a reason nothing changes: no 1.1 response carries
one (checked over every fixture). `Reason::of(token)` is for the reasons the
executor raises itself (S2b, S5, S6). The trace documentation
(`docs/guides/RUNNING_WORKFLOWS.md`) does not list `reason`/`reason_ignored`
yet: `tests/test_trace_kinds_doc.py` requires every documented detail
member to occur in a fixture's run, so the member is documented with the
first fixture that exercises it (S2b).

**Smaller items.**

- `exec::read_json` (F1.9) is public; `core/tests/runtime.rs` reads every
  fixture with it.
- `_core.canonical_json` and `_core.approval_digest` (F1.10) refuse values
  outside I-JSON (`exec::ijson`), not only those `from_py` refuses; a Rust
  test checks every vector of `digests.json`.
- `refs::executable_roots(step) -> Vec<StepRef { field, root, text }>`
  (F1.11), in document order (`shift_remove`, so removing `purpose` keeps the
  order); `program.rs` reads its roots.
- `extensions::literal_duration(step, key, Positive, why, at, report)`
  (F1.12) for `input_bindings.<key>`; the W614 `timeout` check calls the same
  body (`duration_text`), with its message unchanged. `_core.duration_ms`
  rounds up to whole milliseconds.
- `core/src/destination.rs` (F1.13) as S5 5.1, with its `vectors` unit test
  over `match.json`; `_core.check_destination_pattern` and
  `_core.destination_allowed`.
- `core/src/grounding.rs` (F1.14): `KINDS`, `vendor` (moved from
  `validate/identity.rs`), `is_kind`, and `Policy { require, kinds, attested }`
  with S4's `new` (shape) and `check_ids` (V101 with the closest id); FOUNDATION's
  "`Policy::new` (refusing an unknown capability id, V101)" is the pair.
- `_core.SPEC_VERSIONS` and `_core.check_cited_versions` (F1.2).

**Runtime fixtures (F1.6, F1.7).**

- Every fixture has `"header": null` right after `catalog`, generated and
  contributed alike (the 20 contributed files edited by hand, one line each;
  `tests/conformance/contrib/README.md` says why). No other fixture change.
- `scripts/gen_runtime_fixtures.py`: `add(..., header=None, **optional)`
  with `OPTIONAL = (actor_identity, catalogs, agents, records, destinations,
  grounding, profiles, run_record)`, written in that order after the
  required members when not None; it validates every fixture against
  `fixture.schema.json` (jsonschema) before writing. The 1.1 fixtures stay in
  the script; `scripts/runtime_fixtures/` holds `s2a.py` ... `s6.py` (each
  `register(add)`, empty) and `helpers.py`, the building blocks (`st`, `wf`,
  `out`, `inv`, `approve`, `CP`, `mutate`, `POLICY`) moved out of the script
  so the workstream modules can import them (`from runtime_fixtures.helpers
  import ...`). The CI `ruff format --check` list gains
  `scripts/runtime_fixtures/`.
- `tests/runtime_replay.py`: `load`, `matches`, `fill`, `start_options`
  (every start member a fixture states; `header` required), `start` and
  `play`; `tests/test_runner.py` and `tests/test_trace_kinds_doc.py` use it.
  The Rust harness (`fixture_options`) passes every member too and refuses a
  fixture with `catalogs` or `agents` until S3 adds them.

**Redaction (F1.15).** `grounded_agency/state/redaction.py` (`MARKER`,
`DEFAULT_PATTERNS`, `Redactor` with `add_secret`, `redact_text`, `redact`,
`holds_secret`; module functions `redact`, `redact_text`, `holds_secret` on
`DEFAULT_REDACTOR`) and `packages/acs-core/src/redact.ts` (`MARKER`,
`DEFAULT_PATTERNS`, `redactText`, `redactJson`, `holdsSecret`), with
`tests/conformance/secrets/redact.json` (25 vectors, informative), run by
`tests/test_redaction.py` and `packages/acs-core/test/redact.test.ts`.
`Redactor.redact_anchor` (S4) needs S4's `EvidenceAnchor` fields and is left
to S4. FOUNDATION B15 had the secrets vectors land with S4, F1.15 with the
foundation; F1.15 was followed. So that the two languages agree exactly,
the patterns avoid `\s` (whitespace is spelled out), are ASCII
(`re.ASCII`; no `u` flag in TypeScript, whose `\b` and `i` are then ASCII
too), and the TypeScript assignment rule counts a value's length in code
points as Python does; three vectors pin these choices. In a JSON value, a
string member whose name is a credential name (alone or after `_`/`-`) is
redacted whole (`api_key_json_member`); keys themselves are not redacted.

**TypeScript package (F3).**

- `packages/acs-core/` 0.1.0 without the WebAssembly parts (S6 adds
  `wasm.ts`, `core-types.ts`, the build scripts, the `./wasm` export and the
  publish job): `exports` is `.` only; scripts `build:ts`, `build`, `check`,
  `test`, `prepack`; dev dependencies `typescript` and `vitest` at the
  binding's versions (no `ajv` until a test needs it). `src/`: `index.ts`,
  `ontology.ts`, `ontology.gen.ts`, `flags.ts`, `canonical.ts` (moved with
  `git mv`), `redact.ts`. Tests read `tests/conformance/` in place (JSON
  imports), so the package needs no Node types.
- `ontology.gen.ts` gains `STANDARD_VERSION` (the newest
  `spec/STANDARD-v*.md`: 1.2.0), `SPEC_VERSIONS` (`_core.SPEC_VERSIONS`) and
  `TRUST_CLASSES` (from `agent_identity_schema.yaml`).
- The binding keeps `STANDARD_VERSION = '1.1.0'` in its own `ontology.ts`
  (the version it follows and its annotations and records cite, as the
  previous note recorded) and re-exports everything else from
  `@synaptiai/acs-core` (`file:../../packages/acs-core`, which imports the
  built `dist/`). `src/acs/ontology.gen.ts`, `src/acs/canonical.ts`,
  `test/canonical*.test.ts` and `test/fixtures/approval-digests.json` are
  gone from the binding; `gen_standard_agents_binding.py --check` fails if
  either generated one reappears, and writing deletes them.
- CI: a `typescript-package` job (`npm ci --ignore-scripts`, `check`,
  `test`, `build`); the binding job builds the package first. CLAUDE.md and
  AGENTS.md have the package's commands and the placement rule.
- The ROADMAP Versions table and `tests/test_version_lines.py` have the fifth
  line (TypeScript package 0.1.0, `packages/acs-core/package.json`).
- Site: `packages/acs-core/README.md` is public Markdown, so it has its route
  (S6 5.8's row, `/guides/typescript-package/`) and a page glyph
  (`page:typescript-package`, a parcel) — the site build refuses a guides
  card without one. `site/src/data/versions.ts`'s `typescriptPackage` (S6
  5.8) is left to S6.
- `docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml`
  ACS-11 cited the binding's deleted copy of the digest vectors; the
  reference now names `tests/conformance/approval/digests.json` and says
  where the copy went (`tests/test_standard_agents_mapping.py` resolves
  every cited path). `docs/integrations/standard_agents.md` still says the
  binding keeps "a private copy" of the ontology table and canonical JSON
  (under "Still open"); the in-repository package replaces that copy but is
  not published, so the sentence is left for S6 (publishing) or S1.

## 2026-11-15 — F6 from a clean state (the figure-gap sweep)

F6 lists the site's `npm run check`, `npm test` and `npm run build`, but CI
(`.github/workflows/site.yml`) also runs `npm run check:axe`: axe over every
page, then `scripts/check-runs.mjs`, the figure-gap sweep, which fails an
enforced page (every generated template and the current Standard) with a run
over two viewport heights that has no figure and is not exempt. Run against
the foundation, axe passed and the sweep failed on two enforced pages:

- `/spec/diagnostics/`: the warnings table, 26 rows with W617 to W626
  (Part C), is one 2762px run. Each family's table has a diagnostic tile in
  every row, which makes it an enriched table, an information figure
  (visual spec 4.2, as the page's own comment says: "each table a figure
  whose Code column holds the same tiles"); the page did not mark it. The
  table now carries `data-info-figure="enriched-table"` (the threshold is
  the prose plugin's `ENRICHED_TABLE_MIN_ROWS`), with a check in
  `test/dist.test.ts`. No visual change.
- `/spec/1.2.0/`, now the current Standard, had three runs over the limit.
  `site/src/lib/runs.ts` gains exempt runs for it, with the category and the
  reason, as the entries added at integration have (and `test/runs.test.ts`
  lists them):
  - `98-diagnostic-format` (c): §9.8 as merged in C3 is the format fence and
    a lookup table of the `location` keys, reference material as Appendix B
    is;
  - `117-artifacts-of-this-version` (c): §11.7 is the E2 file register;
  - `518-tool-calling-hosts`, `519-host-protocol`, `520-grounding`,
    `521-domain-profiles` (a), marked `unwritten: true`: the D2 skeleton
    sections, headings and owner comments only, nothing to draw from yet.
    `test/runs.test.ts` fails as soon as one of them holds anything but
    subheadings, one-line comments, blank lines and `---`, with the message
    "remove its unwritten entry from EXEMPT_RUNS". **S1 (§5.18), S2b
    (§5.19), S4 (§5.20) and S6 (§5.21) remove their entry when they write
    the section**; the sweep then measures it, so a long section needs a
    figure (a `SPEC_SLOTS` entry) or a justified exempt run of its own.
  - With these, the 1.2.0 page's longest net run is 1421px (§11.4's figure
    to §12.1's, through §11.5 and §11.6). S6's text for §11.5 and §11.6 adds
    to that run; S6 checks the sweep after writing them.

Workstreams should run `npm run check:axe` (or at least
`node scripts/check-runs.mjs`, with `ACS_CHROMIUM` naming a Chromium) after
`npm run build` whenever they change the Standard or the site, since CI does.

## 2026-11-15 — S1 review rounds 1 and 2 (affects S4 and S5)

- §10.4 now requires the capability checks of §5.18.10 of a class SL layer
  (a bullet beside §5.18.5–§5.18.9), and a conformance statement names any
  §5.18.10 check its layer does not apply. The statement schema
  (`tests/conformance/calls/schema/statement.schema.json`) gains
  `not_applied` for that.
- Both reference statements (`grounded_agency_adapter.json`,
  `standard_agents_binding.json`) list there (after S1 review round 2):
  the `persist` and `audit` secret checks (F504, §6.7); the `send`
  destination policy (F504, §4.4.2); the `transform` row and the
  every-capability redaction row (§6.7: records, evidence and trace entries
  the layer writes are not redacted); and, in the adapter's statement only,
  the every-capability output-contract row (R402: a Claude Code or MCP tool
  result is passed on unchecked). By §10.4 a layer that lists any row does
  not conform, so neither claims class SL yet. Every text says so the same
  way: the two layers "implement §5.18 and meet §10.4 except the §5.18.10
  rows their conformance statements list as not applied, and claim class SL
  once those are applied" (the Standard's Status line; SECURITY.md §5.5;
  CONFORMANCE.md's class SL section; RFC-0005 9.1; the SDK guide's and the
  Standard Agents guide's Conformance sections; the binding's README).
  - **S4**, when the adapter and the binding check `persist` data and
    `audit` records for secrets: remove the first `not_applied` line from
    both statements. When the adapter redacts what it writes
    (`call_records`, `diagnostics`, evidence anchors, a `transform` output
    it records) and the binding redacts its trace entries (an output's
    `evidence_anchors`), remove the redaction line too, and change the
    `transform` row of SECURITY.md §5.4 from "code where a layer applies
    §6.7" to name the redaction code. S1's `rollback` and `send` command
    hooks now open a refusal with the code and name (§5.18.8: `F503
    ROLLBACK_FAILED:`, `F504 CONSTRAINT_VIOLATED:`, `R407
    SAFETY_CHECK_FAILED:` for a call they cannot read); the `persist`
    command hook, S4's, should do the same (its test in
    `tests/test_skill_hooks.py` takes the prefix from `OPENS`).
  - **S5**, when both layers apply a destination policy to `send` calls
    (reading the binding's `destination`): remove the `send` line.
  - The adapter's output-contract line has no owning stream: Claude Code's
    tools return no capability output, and an MCP tool's result is the
    tool's own form. It stays until a host form for §5.18.9 exists there
    (for example an opt-in check of a grounded MCP tool's result), so the
    adapter claims SL only then; the binding claims it once S4 and S5 have
    removed its lines.
  - Whoever removes the last line of a statement drops `not_applied` from
    it (the member stays in the schema) and rewords that layer's claim in
    every text listed above to "claims class SL (§10.4)"; while either
    layer still lists a row, the Status line keeps the clause.
- The composed skills (`debug-workflow`, `capability-gap-analysis`,
  `digital-twin-bootstrap`) take their checkpoint with `/checkpoint`, whose
  state-saving command is what a layer counts; but `skills/checkpoint/SKILL.md`
  still runs `git stash push`, a gated `mutate` under S1 (it needs a
  checkpoint and approval and takes none: only a plain `git stash create`
  is `checkpoint`). **S5's** rewrite of the checkpoint skill (S5.md 5.4,
  `git stash create` as separate plain calls) is what makes those step 0s
  work: until it merges, following them takes no checkpoint under either
  layer. S5's rollback skill rewrite keeps S1's frontmatter command hook
  (a `git stash pop|apply` must name a commit a checkpoint marker recorded,
  F503), which its `git restore --source=<sha>` form does not trigger.
- The plugin keeps every marker whose validity ended under
  `.claude/checkpoints/` (`used/` for a marker a call used, `ended/` for one
  that expired, ended with its turn or was replaced), the history a
  `git stash pop|apply <commit>` rollback reads. The Python tracker drops a
  loaded checkpoint dated after the load and never counts one dated after
  the clock (S5's tracker work keeps that).
- I-JSON numbers in both languages (binding records, F502 arguments): an
  integer beyond ±2^53 or a float canonical JSON writes as one (1.8e16) has
  no I-JSON form; JSON text read for a check goes through
  `parseJsonExact` in TypeScript, which keeps 2^53 + 1 from rounding to
  2^53. S4 or S5 code reading JSON text in TypeScript for such a check
  should use it; Python's `grounded_agency.capabilities.bindings.i_json_problem`
  is the Python form of the rule.
- A tool binding record with a member that has no I-JSON form is S303 in
  both loaders (`iJsonProblem` in `packages/acs-core/src/ijson.ts`; the
  core's canonical JSON in Python). `iJsonProblem` is the TypeScript
  package's one I-JSON check: S4 or S5 code that needs one should use it.
