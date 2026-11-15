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
