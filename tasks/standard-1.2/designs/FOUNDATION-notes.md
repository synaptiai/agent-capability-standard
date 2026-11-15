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
