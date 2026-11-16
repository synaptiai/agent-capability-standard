# RFC-0010: Domain Profiles, Trust, Versioning and Schema Dialect
**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary

This RFC records the decisions of Standard 1.2.0 on domain profiles, the
scoring of evidence and the resolution of conflicts (§8), versioning, the
schema dialect of capability contracts and entity ids, and the packaging
decisions of the reference implementation that go with them. It answers findings ACS-05, ACS-25, ACS-28, ACS-42,
ACS-56, ACS-59 and ACS-64 of the
[Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
It is Accepted by the maintainer's instruction that every remaining finding be
implemented in 1.2.0; `spec/STANDARD-v1.2.0.md` carries the text.

## Motivation

Standard 1.1.0 mentioned domain profiles twice and said neither how a run
selects one nor what its settings change; no shipped component read
`schemas/profiles/profile_schema.yaml`'s members, and the compliance documents
had called `block_autonomous` enforced. `require_human` admitted `critical`,
a level the Standard does not define, `checkpoint_policy` keys were free
labels, and none of the shipped profiles' 29 `required_anchor_types` was an
anchor kind.

§4.1 called capability contracts "JSON Schema" while the ontology writes
`type: any` and `a|b` unions, which a JSON Schema importer refuses. §7.1 and
`schemas/entity_taxonomy.yaml` gave two incompatible entity id forms. §8
required a half-life and named the factors of a trust score but left their
composition, a negative age, a floor above 0.5, unknown weights, field
authority and the conflict strategies without arithmetic; the only decay code
was a benchmark's private function. Four version lines existed, and §11 did
not say how the ontology is versioned or what a classification made elsewhere
cites. A catalog's version header is a comment, so it never reached the
executor, which takes parsed catalogs: a rule for 1.2 targets would apply in
the validator and not in a run of the same file. The skills mixed frontmatter
keys of three owners, two of them under names other than their directories. A TypeScript host had no published
package and no way to run the reference core.

## Goals

- Give domain profiles one defined effect wherever they are applied, which
  tightens flags, checks, evidence, confidence and destinations (trust
  weights replace), with diagnostics and vectors, and refuse malformed rules.
- Define the schema dialect of contracts and its Draft 2020-12 rendering.
- Choose one entity id form.
- State the trust arithmetic completely and make its vectors normative.
- Say how the ontology is versioned, how documents cite it, and what a
  Standard version consists of.
- Make the executor apply the rules of the version a catalog declares by
  its header, as the validator does.
- Record which skill frontmatter keys belong to whom.
- Publish the host-neutral TypeScript pieces and a JSON interface to the core.

## Non-goals

- Selecting a profile from a workflow: a workflow's `profile` field stays
  descriptive.
- Profiles that loosen the ontology's flags.
- New capabilities, or changes to capability flags.
- §7.2 and §7.3 (alias scoring, merge and split): unchanged and still not
  implemented.
- A Rust crate on crates.io, or bindings for languages other than TypeScript.
- Changing the repository's catalogs to a 1.2 header.

## Key decisions

### 1) Profiles are applied by hosts, layers and validators, and tighten

A host gives profiles to the executor when it starts a run (§5.21.1); they
cover nested runs and are saved with the run. A safety layer applies the
profiles its configuration names; a validator may be given them. Several
profiles combine by taking the strictest. For flags, checks, evidence,
confidence and destinations a profile only tightens; its `trust_weights`
replace the trust model's weights, higher or lower, as §8.3 always allowed
(bounded by §8.3's lower-of rule; the lowest per key across profiles).
Thresholds are sets of risk levels (`none` covers none); `auto_approve`,
`require_review`, `require_human`, `block_autonomous` and
`checkpoint_policy` raise effective flags, except that a `checkpoint` step
is never given `requires_checkpoint` (it would need a checkpoint before
itself, and `"*": always` would make every workflow invalid). A person is
required for the step itself: the request and the decision are those of an
always-ask item, so no standing mandate covers the step and an unattended
run does not ask, but the requirement is not a mark and does not pass to
the data, the steps that read it or nested runs; its records carry
`person_required`. A composite tool whose approval covers a nested call a
profile requires a person for (§5.18.4) is itself asked of a person.
`evidence_policy` becomes a grounding policy and a
minimum confidence (F504, `below_minimum_confidence`, and
`invalid_confidence` for a `confidence` that is not a number from 0 to 1);
`allowed_destinations` a destination policy; `trust_weights` the overrides
of §8.3. Keys are capability ids or `*`, anchor kinds, trust classes.
Loading uses S303 (malformed members, any member of the closed
`risk_thresholds` and `evidence_policy` mappings this version does not
define, the key `checkpoint`, a repeated anchor kind or grounding id, a
member that is not I-JSON), S304, V101 (any unknown capability id,
`checkpoint_policy` keys included), V109, W602, W603 and W604 (unknown
top-level members only); no misspelled rule is ignored. `critical` is
deprecated and read as `none`. The shipped profiles are migrated to 2.0.0.
The executor, the validator (`--profile`), the Python adapter and runner
implement it; TypeScript reaches the same implementation through the
WebAssembly core, and so does the Standard Agents binding
(`groundedTool({profiles})`, with what `bindingProfiles` computes through
it); `tests/conformance/profiles/load.json` and
`tests/conformance/profiles/effective.json` are normative.

An executor or safety layer that does not put one of these rules in force
refuses a profile that sets it, as it refuses a profile with an error
(§5.21.4), rather than apply the rest and act as if the rule were absent. A
validator applies only the flags (§5.21.1), so it refuses no profile for
the other rules: it reports what a run under the profile would need. The
reference executor checks a profile's grounding policy with the grounding
check of §5.20 (RFC-0008), as a host's policy, in every frame and before
the minimum confidence; the Python adapter and the Standard Agents binding
apply it, and the minimum confidence, to the call outputs they see (§5.20's
hosts outside a workflow). That puts both rules in force for a safety layer
(§5.21.4): one whose host returns some covered calls' results in forms of
its own (Claude Code's tools, for the Python adapter) names those calls in
its conformance statement and reports, for each tool whose calls a rule
would check, that the rule checks nothing for them; one that receives no
capability output refuses a profile with either rule. A profile's
destination policy is checked once the destination check of §4.4.2 lands
with its own workstream (S5); until
then the executor refuses to start or restore a run under a profile that
sets `allowed_destinations`, the Python adapter and the Standard Agents
binding refuse it too, and the Python adapter, with `strict_mode=False`
(which only logs a missing checkpoint), refuses a `checkpoint_policy` that
raises a flag. No shipped profile sets
`allowed_destinations`, so every one applies as it is.

### 2) The schema dialect is defined, with a normative rendering

§4.1.2 lists the Draft 2020-12 keywords contracts use and defines `type:
any`, `type: "a|b"`, `$ref` to a repository path with sibling keywords merged
over the target, `nullable`, and `x-` annotations; `x-acs-` is reserved. A
`$ref` that names nothing, a cycle and an over-deep chain are outside the
dialect, and an implementation refuses an ontology whose contract holds one
when it loads it. The rendering rules are normative and exact on values;
§5.4 reads a rendered `"null"` but not `nullable`, a divergence the text
states and a test pins. `schemas/generated/capability_contracts.schema.json`
is the generated rendering, keeping `x-acs-type` for `any`. A dialect
metaschema in `schemas/capability_ontology.schema.json` checks the ontology.

### 3) Entity ids are `<class>:<namespace>/<local_id>`

§7.1 takes the taxonomy's form, states its grammar (the namespace outermost
first, the taxonomy's `namespace_components` the recommended order) and
gives the examples of both files; `schemas/entity_taxonomy.yaml` 1.1.0 adds
the pattern;
`grounded_agency/entities.py` parses ids; `tests/conformance/entities/ids.json`
is normative.

### 4) The arithmetic of §8 is complete

`score = weight × confidence × decay`; confidence 1 when none is reported; an
age below zero counts as zero; a floor above 0.5 applies; evidence without a
static weight has no score; field authority ranks sources in §8.2 and is not
a factor. §8.2 defines six strategies (the default, `highest_score`, is new)
and tie-breaking by the model's `tie_breakers`; the authorities are the
trust model's new `field_authority.fields` (the 1.1 `examples` stay,
illustrative). The trust vectors are normative, with
`tests/conformance/trust/resolve.json` added; `grounded_agency/trust.py` is
the reference, and the benchmark resolves its conflicts with it, with
unchanged results.

### 5) The ontology's version and what documents cite

§11.6: the ontology's own SemVer with a change table, which also classifies
constraint changes (an input constraint added or tightened is MAJOR; item or
member constraints on an output field that left them open are MINOR) and
records that 2.1.0's widening of `transform.output` predates the rule.
Every 2.2.0 change is MINOR or PATCH under it. An ontology MAJOR only with a
Standard MAJOR, a MINOR with the Standard version that names it, a PATCH
alone. A document outside a workflow that names capabilities cites
`standard` and `ontology` where its format puts them; another ontology major
or an unsupported standard is V109, checked by the profile loader and the
OASF adapter through one core function; an id the consumer's ontology lacks
(one a later MINOR added) is V101 where the document uses it, so the OASF
adapter refuses to translate an entry that names one rather than compute
its risk without it. §11.7 lists the artifacts of 1.2.0
with their versions. §11.5 adds 1.2, generalises W616 to any feature newer
than a workflow's target, and makes the catalog's header an explicit value
of the start operation (a version or an explicit none), so the executor and
the validator apply the same target's rules to the same catalog. W616 reads
one table of features; the 1.2 features belong to other workstreams (S2a,
S2b, S3, S4, S5), and each adds its rows, and S3 the S303 for `agents`
before 1.2, with the feature itself.

### 5a) The header reaches the executor

A comment header is gone once a catalog is parsed, and the executor takes
parsed catalogs. In the first draft the header was an optional start
option defaulting to none; a host that left it out ran a catalog targeting
1.2 by its header under 1.1 rules, so S2a's approver `sender_check` and
`accept_trust_classes` (1.2-target fields) were ignored and the identity
requirement failed open. The start operation now takes the header as a
required value; a host that loaded the catalog from a file passes the
file's header version. The Rust `StartOptions` has no default, the host
protocol schema, the fixture format, the WebAssembly `run.start` and
TypeScript's `StartArgs` require the member, `_core.Run.start` requires the
keyword, and `WorkflowRunner` carries each file's header into its
workflows' `spec_version`. Two runtime fixtures pin the 1.2-header case
with the approver `sender_check` of §5.17 (S2a):
`header_1_2_sender_check_needs_identities` and
`header_null_sender_check_not_read`.

### 6) Skill frontmatter follows the Agent Skills format plus Claude Code's keys

Frontmatter `name` equals the directory; `layer` is removed; ACS keeps any
data of its own under `metadata` keys `acs-*`; `skills/README.md` lists each
key's owner; a test enforces it. The Agent Skills reference validator refuses
the Claude Code keys, which the plugin's skills need. The two renamed skills
are user-invocable, so their slash commands change; the plugin release that
carries the change is a MAJOR version, 3.0.0.

### 7) A TypeScript package and a WebAssembly JSON interface

`packages/acs-core/package.json` declares `@synaptiai/acs-core`: the ontology
table, effective flags, canonical JSON and the approval digest in plain
TypeScript, and the reference validator and executor, domain profiles
included, through a WebAssembly module built from the core's `wasm` feature
(three C-ABI exports over buffers of one layout, a length-prefixed result,
JSON requests, no new dependency). There is no second, TypeScript
implementation of the profile loader. CI replays the validator, runtime and
expression fixtures through it; a job publishes it from a tag on `main`
(a hand run from `main` builds the tag, never the branch) when the
repository enables publishing.

## Backward compatibility

Profiles are opt-in: nothing changes for a run, a call or a validation
unless a profile is applied, and an applied profile only tightens flags,
checks, evidence, confidence and destinations (its trust weights replace, as
in 1.1's §8.3). No 1.1 component applied a profile, so refusing malformed
or misspelled profile rules changes no behaviour. The schema dialect, the
entity id form and the trust arithmetic clarify text that was open or
contradictory; nothing checked the entity id, and the reference trust
function changes only for a negative age. W616 is a warning and fires only
for a workflow that declares 1.0 or 1.1 and uses a 1.2 feature; rules for
1.2 targets apply only to workflows that declare 1.2. The canonical schema
changes are additive (§11.4), `ActionRecord.person_required` and
`field_authority.fields` included. The repository's catalogs keep their 1.1
header and validate as before.

**Changed.** The start operation takes the catalog's header version as a
required value (a 1.1 host passes none for a catalog without a header, and
a 1.1 workflow then runs exactly as before); direct callers of the private
`_core.Run.start` must pass the `header` keyword. An ontology whose contract
holds an unresolvable `$ref`, kept silently before, is refused at load.

**Breaking (plugin).** Two user-invocable skills are renamed to their
directory names (`/gap-analysis-workflow` → `/capability-gap-analysis`,
`/digital-twin-sync-workflow` → `/digital-twin-sync-loop`), so the plugin
release is a MAJOR version, 3.0.0. No workflow, ontology or schema is
affected.

## Conformance test updates

- `tests/conformance/profiles/load.json` and `effective.json` (new,
  normative).
- `tests/conformance/trust/decay.json`, `weight.json`, `score.json` (now
  normative, open cases decided), `resolve.json` (new).
- `tests/conformance/entities/ids.json` (new, normative).
- Runtime fixtures `profile_*` with a `profiles` member, among them
  `profile_person_does_not_mark_readers`,
  `profile_person_not_passed_to_nested_run`,
  `profile_person_not_passed_to_recovery`, `profile_star_always_starts`,
  `profile_minimum_confidence_not_a_number` and
  `profile_minimum_confidence_waited_delegate`; `profile_grounding_*`
  (§5.20: required, met, wrong kind, in a nested run, before the minimum
  confidence); for the header `header_1_2_sender_check_needs_identities` and
  `header_null_sender_check_not_read` (§5.17). With the workstream whose
  check it exercises: `profile_destinations_refuse` (§4.4.2, S5).
- The runtime fixture format requires `header` (a version or `null`); every
  existing fixture gains `"header": null`, with unchanged expectations. A
  script entry may list `absent` members, which the pending action must not
  hold (a person's request names no `mandate_ref`), since the subset rule of
  `expect` cannot say that a member is absent.
- Validator fixtures with profiles (`tests/fixtures/EXPECTATIONS.json` gains
  `profiles`), among them `pass_profile_star_always`, and for `spec_version`
  1.2 and 1.3. W616 for a 1.2 feature is pinned by
  `warn_version_feature_1_2` (the `audit` input `require_record` under a 1.1
  header); each workstream adds its features' rows to the table W616 reads.
- The TypeScript package replays the validator, runtime and expression
  fixtures and the profile vectors through the WebAssembly core; its
  interface takes only I-JSON requests, so the profile vector whose member
  is not I-JSON is refused there before the loader reports S303.

## Alternatives considered

- *Profiles informative only*: leaves the compliance controls unenforced.
- *The workflow selects its profile*: a profile is deployment policy, and a
  workflow can declare its own flags.
- *Profiles that may loosen*: contradicts §3.3.
- *Unknown `checkpoint_policy` keys and nested members as warnings*: a
  misspelled rule would be dropped silently; errors instead.
- *A person requirement that marks data, as an always-ask item does*: it
  would spread to steps no profile covers and misstate the records.
- *An optional header start option*: fails open for 1.2-target rules.
- *A pure-TypeScript profile loader beside the core's*: a third
  implementation with no consumer.
- *Removing `critical`*: deprecated instead, so existing profiles load.
- *Rewriting the ontology in strict JSON Schema*: churn for every consumer of
  the YAML; the dialect is defined and rendered instead.
- *§7.1's entity form*: changes the canonical schema and its examples; the
  taxonomy's is machine-readable and hierarchical.
- *Refusing a negative age; forbidding a floor above 0.5*: brittle under
  clock skew; the floor's meaning is unambiguous.
- *Versioning the ontology in lockstep with the Standard*: description fixes
  should not need a Standard release.
- *wasm-bindgen*: two version-locked dependencies and generated glue for what
  a JSON interface over three exports provides.

## Open questions

1. Should Standard 2.0 drop the deprecated profile threshold `critical`, and
   make an unknown top-level profile member an error rather than W604 (this
   version already refuses unknown `checkpoint_policy` keys and unknown
   members of `risk_thresholds` and `evidence_policy`)?
2. Should a domain profile be able to carry its own grounding `attested`
   flag (§5.20), which this version leaves at its default?
3. Should the repository's reference catalogs move to a 1.2 header in the
   next release, together with the migrations that the 1.2-only warnings of
   other workstreams would require?
4. The skills write `allowed-tools` comma-separated and name `Git` and `Web`,
   which are not Claude Code tool names; should the plugin's tool lists be
   corrected, which would change what the skills may run?
5. Should the TypeScript package also carry the trust arithmetic and entity
   ids, which today only the Python package implements?
6. If a TypeScript safety layer comes to apply profiles without
   WebAssembly, should the package then carry a plain-TypeScript profile
   loader, held to the same vectors?
7. Should a later version define recursive types in the schema dialect
   (`$ref` cycles rendered as Draft 2020-12 `$defs`), and should §5.4 then
   read `nullable` so that a contract and its rendering infer the same
   types (at the cost of W610 on workflows that order on such members)?
