# RFC-0007: Delegation, catalogs and validator diagnostics
**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary
This RFC records the decisions behind eleven changes in Standard 1.2.0, made
on the maintainer's instruction to implement every remaining finding of the
Standard Agents mapping
(`docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml`:
ACS-04, ACS-09, ACS-16, ACS-17, ACS-24, ACS-29, ACS-46, ACS-47, ACS-49,
ACS-50, ACS-54). It adds an agent manifest (`schemas/agent_manifest_schema.yaml`)
and a workflow field `agents`, with which a `delegate` step takes the safety
flags of what its target may do, is not delegated without its target's
manifest, and has its task checked; enforcement of `read_only` in 1.2
workflows; a `delegate` input `continues`; a catalog manifest with qualified
workflow ids for `invoke`; a grammar and a host selection rule for a step's
`domain`; typed answers to `inquire`; a defined diagnostic `location` with an
RFC 6901 `path`; the scope of `conflicts_with`; and the comparison and
derivation of model families. Four warnings are new (W620–W623); no error
code is. Every behaviour change is opt-in or a warning; the text is in
`spec/STANDARD-v1.2.0.md` §4.3, §5.1, §5.1.1, §5.2, §5.2.4, §5.13.1,
§5.15–§5.17 and §9.

## Motivation
Mapping ACS against the Standard Agent Specification found places where a
host had to guess or where the Standard knew less than a binding needed:

1. A `delegate` step validates and runs with `risk: medium` and no checkpoint
   or approval, whatever the target agent does (ACS-04). Nothing describes
   what an agent may do (ACS-29), so a validator cannot know, and a task is
   checked only when the host refuses it (ACS-54).
2. A workflow cannot declare the agents it delegates to, which a host that
   composes agents statically needs (ACS-46), and cannot continue an earlier
   delegation, so the validator cannot see that a reviewer is not fresh
   (ACS-47). Model families are compared exactly by the reference
   implementation, but no text says so or says how a host names one (ACS-17).
3. A catalog is a flat mapping; an `invoke` names a workflow by bare name in
   the one loaded catalog, so a workflow cannot call one from another catalog
   and nothing says which workflows a catalog offers (ACS-49).
4. A step's `domain` has no grammar and no matching rule, so two hosts can
   dispatch one workflow differently (ACS-24).
5. `inquire`'s questions have no required key and no typed answer (ACS-50).
6. §9.8 shows `location` only by example; a consumer that needs one path
   string guesses the projection (ACS-09).
7. §4.3 says conflicting capabilities "may not run concurrently" and
   enforces one parallel group, while the Standard itself offers concurrent
   runs (`overlap: allow_all`) and delegates that run beside their delegator
   (ACS-16).

## Goals
- A delegation carries the checkpoint and approval requirements of what its
  target may do, when the workflow author opts in, without changing any 1.1
  workflow.
- One descriptor of an agent's capabilities and task, used by the validator,
  the executor, the Python SDK and the Standard Agents binding.
- Catalogs that can be published and invoked from other catalogs, with
  stated visibility.
- Deterministic domain dispatch and a stated meaning for every diagnostic
  location key.
- Language-neutral vectors for every rule a host implements.

## Non-goals
- Dependency declarations and version resolution between catalogs (open
  question 1); finding catalogs is the host's.
- Enforcing `conflicts_with` across runs (no fixture can express two runs;
  "same state" is host knowledge).
- A registry of model families.
- What a delegator's checkpoint covers across a delegation (RFC-0009,
  ACS-18).
- Tool-call delegation scopes (RFC-0005).

## Key decisions

### 1) An agent manifest is a supporting schema, and context
`agent_manifest` has `agent`, `standard` and `ontology` (the versions it
cites, per §11.6), `capabilities` (everything the agent may exercise, also
through its own delegates and invoked workflows) and an optional `task` in
the form of workflow `inputs`. Its maxima are derived from the ontology: the
highest risk and the OR of `mutation`, `requires_checkpoint` and
`requires_approval`; read-only maxima use only the capabilities whose
`mutation` is false; a manifest listing a capability the ontology lacks has
none, and that id is V101 where the manifest is used. Manifests are given to
the validator and executor beside the catalogs, like the ontology; a
malformed one, one citing another ontology major or an unsupported standard,
and a duplicate are refused when loaded. Stored maxima, a canonical (§6.1)
schema and workflow-side manifest references were rejected (see
Alternatives).

### 2) `agents` is the author's explicit opt-in, and applies from 1.2
A workflow field `agents` lists the agents its delegate steps may delegate
to. It applies only in a workflow that targets 1.2 or later, so a workflow
that relies on it declares 1.2 and a 1.1 consumer refuses it (V109) instead
of ignoring the field and running its delegates without the raised
checkpoint and approval. In a workflow that targets an earlier version, the
executor ignores the field as a 1.1 consumer does, and W616 tells the author
to declare 1.2 (W605 when the workflow declares no version). In a 1.2
workflow, declaring it: restricts targets
(V107 static, R402 at run time; a static host reports a listed agent it does
not provide as V107); raises a delegate step's ontology baseline to its
target maxima (a literal agent's, or the join of every listed agent's for a
computed one; read-only maxima with a literal `read_only: true`), so F501,
approval, W602, W606 and W608 follow; stops the executor from delegating for
a step whose target maxima are unknown (R402, fail-closed); allows an
`approval` block on any of its delegate steps, so validity does not depend
on the manifests given; and checks tasks (S303/S304 static, R402 at run
time). A field, rather than the version alone, because raising flags needs
manifests: making every 1.2 workflow subject to them would refuse every 1.2
delegation a host has no manifest for. The field is the author's statement
that the host can supply them.

### 3) `read_only` is enforced in 1.2 workflows
Read-only maxima, and W621's `read_only` remedy, rest on the host honouring
`read_only`. A host that cannot enforce it refuses the delegation. In a
workflow that targets 1.2, an accepted delegation whose resolved `read_only`
is true fails unless the host attests `effective.read_only: true`; the
failure is a step error that `retry` does not repeat, because the delegate
has already run and a retry would hand the same host another unchecked
delegation. The executor knows the target from `spec_version` or the header
it is given (the start option `header`, §5.19.2).

### 4) Two warnings for 1.2 workflows only
In a workflow that targets 1.2, W621 reports a delegate step whose target
maxima are unknown: always where the workflow declares `agents` (the
executor will not delegate there), and otherwise when it binds no literal
`read_only: true` and requires no approval. W622 reports one whose target is
computed in a workflow without `agents`. Their remedies are 1.2 features, so
they do not apply to 1.1 workflows.

### 5) `continues` is a base input, and every call has its own `task_id`
In a workflow that targets 1.2, a delegation that continues an earlier one
never has a fresh context: S303
with a literal `fresh_context: true` (so such a reviewer never satisfies
`require_fresh_context`, which already requires the literal), R402 when the
host attests a fresh context; null delegates anew. Every delegation call,
a continuation included, returns its own `task_id`, so a waiting delegate's
correlation and `replaces` name one call; `continues` may name any earlier
call of the chain. It is not governed by `delegation@1`: that would make a
1.1 workflow that bound it (W604) invalid (V106), and a 1.1 consumer of
`delegation@1` does not know it anyway; W616 reports it in a workflow that
targets an earlier version (§11.5), where the executor passes it on unread,
as 1.1 did, so none of these rules applies there.

### 6) Model families: exact, lowercase, derived by one rule
Families compare by exact code-point equality everywhere. A host derives a
family from the model's identifier: after the last `/`, after the last `.`
or `:` before the first digit or `-`, the leading ASCII letters, lowercased
(`acme-large-2` → `acme`, `z3-mini` → `z`). The rule needs no list of
lines and is pinned by vectors; a literal outside `[a-z][a-z0-9_-]*` is
W620. An identity (and the world state's copy of it) and `effective` may
carry the `model_id`, checked against each other under `identity@1` in a
workflow that targets 1.2. Below 1.2 the identity is schema 1.0.0's, where
`model_id` is an unknown member, so the executor reads it neither for its
type nor for agreement, as 1.1 did.

### 7) Catalog manifests and qualified ids
A top-level `catalog` mapping without `steps` is the manifest (`id`,
`version`, `ontology`, `exports`; its Standard version is the file header);
with `steps` it stays a workflow. A qualified id `<catalog id>/<name>` names
a workflow of another catalog of the set an implementation is given; only
exported workflows resolve from outside their catalog, and a bare name
always means the invoker's own catalog. A qualified id of the invoking or
another loaded catalog that lacks the workflow, or hides it, is V107; every
other unresolved target, a bare name included, stays W607, so no 1.1 target
changes code. Cycles, triggers, inputs, waits and unattended propagation work
across the set. The executor resolves computed targets the same way.
Workflow names SHOULD be identifiers (W620), but a qualified id's name is
whatever follows its first `/`, any workflow name, so an exported workflow
whose name is not an identifier is still reachable. A 1.1 consumer resolves names
in one catalog only, so an `invoke` target that is a qualified id and names
no workflow of its own catalog (whether or not a catalog given has its id,
so the warning does not depend on the set validated), and a catalog manifest
in a file whose header targets 1.0 or 1.1, get W616 (§11.5). Like every
W616 about a step member, the first is reported at its step (§9.8).

### 8) Domain ids and selection
A domain id is lowercase segments joined by dots, underscores inside a
segment (one spelling per domain), digits allowed first (`image.3d`). A host
selects the exact implementation, else the longest prefix at a dot, else the
domain-less one, else fails the step with R402 and reason
`unsupported_domain`; a step without `domain` takes the domain-less one. The
workflow-level `domain` is descriptive.

### 9) Answers to `inquire`
The ontology adds `inquiry_id`, a question `id` and `answer_type`, and
`receive` items' `inquiry_id` and `answers` (`{question_id, value}`). A host
that produces `inquire` output MUST give ids; answers are keyed by `id` (or
`parameter`), typed by `answer_type`, never for an unasked question or twice.
Requiring `parameter` was rejected as a MAJOR change.

### 10) Diagnostic locations
§9.8 defines every location key, those of the other 1.2 workstreams
included: `step` is a zero-based index in list order; `field` is relative to
the step, else the workflow, else the document the finding is about; a
finding about a profile or a tool names it (`profile`, `tool`) and has no
`path`; `path` is an RFC 6901 pointer from the catalog root, present on
every finding about the catalog; `catalog` names the set member; `column`
counts code points. The reference builds `field` and `path` from the same
segments where a diagnostic is made, so `path` is exact even for keys that
contain `.`. Implementation-defined codes may not take the standard form
(§9.1).

### 11) `conflicts_with` is per workflow
The rule keeps conflicting steps out of one `parallel_group`; it does not
reach across runs or agents. §4.3 names the cases, a host SHOULD serialise a
`rollback` with `mutate` and `persist` on the same state, and W623 flags an
`allow_all` trigger on a workflow that exercises both capabilities of a pair,
through its steps, a `rollback` action, or the workflows it invokes. Event
triggers are left to the host: they declare no overlap policy.

## Backward compatibility
Standard 1.2.0 is a MINOR release. No workflow valid under 1.1 becomes
invalid, and no 1.1 workflow runs differently, unless it opts in:

- by declaring 1.2 (W621, W622, the `read_only` attestation, an identity's
  `model_id` typed and compared with `effective.model_id`) and, in such a
  workflow, `agents` (target maxima, V107, no delegation without manifests,
  task checks, executor refusals); `agents` in a workflow that does not
  declare 1.2 is ignored, as a 1.1 consumer ignores it, and reported W616
  where 1.1 reported W604;
- by binding `continues` in such a workflow (its S303 and R402), a new
  optional input (§11.4); below 1.2 it is W616 where 1.1 reported W604, and
  the executor passes it on unread, as before;
- by being given with other catalogs or using a qualified id (catalog sets);
  a single catalog validates and runs exactly as before, a bare name that
  does not resolve stays W607, and a `catalog` mapping with `steps` is still
  a workflow.

W620 and W623 are new warnings for every version, phased in before any
error. A W616 about a step member (a 1.1 feature included) now carries its
step's `step` and `capability`, with `field` relative to the step, so it is
reported with that step's other findings (§9.8); its code and `path` are
unchanged. A host that cannot enforce `read_only` refuses the delegation, which
states 1.1's "must not change anything" as a host rule; a host derives model
families by the rule of §5.15. The ontology (2.2.0),
`agent_identity_schema.yaml` (1.1.0) and the canonical
`world_state_schema.yaml` (1.2.0, whose `AgentIdentity` copies the identity
schema and gains the same optional `model_id`) change only by optional
members and descriptions. The executor's snapshot digest is unchanged for a
single catalog without manifests. The one repository change a new warning
requires is the step domain `plan-invalidation` in
`schemas/workflow_catalog.yaml`, renamed `plan_invalidation` with its bundled
copies. The Python SDK's `AgentDescriptor.identity()` now refuses a
non-canonical model family, `DelegationProtocol.delegate()` refuses a task
that does not fit the agent's declaration, and `effective_flags` raises for
a delegate step whose target maxima are unknown.

## Conformance test updates
- Validator fixtures (`tests/fixtures/`): 38 new fixtures, with agent
  manifests under `tests/fixtures/agents/` and catalogs of sets under
  `tests/fixtures/catalogs/`; every fixture that uses a 1.2 feature has a
  1.2 header, except the four that pin its W616 under a 1.1 header
  (`agents`, `continues`, a catalog manifest and a qualified `invoke`
  target), and each states its exact
  error and warning sets; expectations gain `catalogs`, `agents` and
  `expected_locations` (a `code` and its `path`, or, for a finding with no
  `path`, its `catalog`, `workflow` and `field`), and two existing fixtures
  pin locations. The Rust,
  Python and WebAssembly harnesses pass the catalogs and manifests alike.
- Runtime fixtures (`tests/conformance/runtime/`): twenty new runs for
  raised flags, target, unknown-manifest and task refusals, `read_only`
  attestation (not retried; 1.2 without `agents`; 1.1 unchanged),
  `continues` (fresh, null, its own `task_id`, a stale result not matched;
  1.1 unchanged), catalog sets (a qualified id whose name is not an
  identifier included), `model_id` consistency (1.1 unchanged), exact family
  comparison, and target maxima with an applied profile
  (`agents_maxima_with_profile_person`,
  `agents_read_only_maxima_with_profile_checkpoint`); the format gains
  `catalogs` and `agents`.
- New language-neutral vectors, normative for what they state:
  `tests/conformance/domains/match.json`,
  `tests/conformance/agents/maxima.json`,
  `tests/conformance/families/derive.json`,
  `tests/conformance/inquiry/answers.json`, run by the Rust core, the Python
  package and the Standard Agents binding as each implements the rule.
- Unit tests for the grammars, the resolver, the pointer (colliding keys,
  findings about other documents) and every new rule;
  `tests/test_errors.py` checks the four codes against the core.

## Alternatives considered
- **Raising every `delegate` step's flags whenever a manifest is available.**
  Rejected: a host supplying manifests would make 1.1 workflows fail F501 or
  ask for approval they did not ask for before.
- **Raising flags in every workflow that declares 1.2, with no field.**
  Rejected: the executor sees the header (the start option `header`), so the version
  alone would work mechanically, but target maxima need manifests, and
  every 1.2 delegation a host has none for would then be refused. `agents`
  is the author's explicit opt-in that the host can supply them; the 1.2
  declaration it applies under is what makes older consumers refuse it. The
  `read_only` attestation and the two warnings do key on the version alone.
- **`agents` applied under any target, with W616 for a 1.1 target.**
  Rejected: a 1.1 consumer would ignore the field (W604) and run the
  delegates with 1.1 flags, so the same workflow would run with different
  flags on different consumers.
- **`agents` as S303 in a workflow that does not target 1.2.** Rejected: 1.1
  reports an unknown workflow field as W604, so a valid 1.1 workflow that
  carried the key would become invalid, and the error would protect nothing,
  since the executor ignores the field below 1.2 as a 1.1 consumer does.
  W616 tells the author the field needs 1.2.
- **Delegating with the `delegate` node's flags when manifests are missing
  at run time.** Rejected: it fails open.
- **Retrying a delegation whose `read_only` was not attested.** Rejected:
  every retry is another unchecked delegation to a host that ignored it.
- **A new extension (`agents@1`, `delegation@2`) for `agents` and
  `continues`.** Rejected: the 1.2 declaration under which they apply already
  makes an older consumer refuse the workflow, and a second declaration
  would split delegation semantics.
- **A continuation that reuses the `task_id` it continues.** Rejected: a
  waiting delegate correlates on `task_id`, so the earlier call's result
  would match the continuation's wait, and `replaces` would name two calls.
- **A quorum F504 for a reviewer that binds `continues`.** Rejected: such a
  reviewer is already S303 or F504, so the rule could never add a finding.
- **A canonical agent schema in §6.1, stored maxima, or manifests referenced
  from the workflow.** Rejected: not every implementation delegates; two
  sources of truth; the workflow author does not own the host's agents.
- **A separate package manifest file, `exports` defaulting to all, or a
  merge tool for catalogs.** Rejected: a catalog file should describe
  itself; the safe default is explicit; a merge loses catalog-scoped names
  and exact locations.
- **Dependency declarations with version ranges.** Deferred (open question
  1).
- **Hyphens in domain ids; an error for a bad domain; exact domain matching
  only.** Rejected: two spellings; invalidates 1.1 workflows; prevents a
  generic implementation serving a specific domain.
- **Case-insensitive family comparison, a family registry, or a table of
  lines with a fallback.** Rejected: changes what the executor counts; goes
  stale; two editions of a table could disagree on one model id, which a
  rule over the id alone cannot.
- **Requiring `inquire.parameter`.** Rejected: a MAJOR change to an output
  contract.
- **A top-level `path` member, or a re-escaped `field`.** Rejected: changes
  the §9.8 object or existing output; `location` already admits keys.
- **Deriving `path` by resolving `field` against the document.** Rejected:
  sibling keys `a` and `a.b` make it wrong; segments make it exact.
- **Hosts MUST serialise conflicting steps across runs.** Rejected: not
  testable, and "same state" is host knowledge.
- **W623 for event triggers.** Rejected: they declare no overlap policy, so
  the warning would report what the author cannot change in the workflow.

## Open questions
1. Should a catalog manifest declare the catalogs it depends on, with version
   ranges, and how would a host resolve them (the domain-profile marketplace
   on the roadmap)?
2. Should W621 and W622 become errors in a later MAJOR, and should a host's
   agent manifests be published somewhere a validator can fetch them?
3. Does `answer_type` need more types (a score on a scale, several choices),
   and should a question carry a JSON Schema for its answer?
4. Should a host conformance class (RFC-0006) make cross-run serialisation of
   `rollback` against `mutate` and `persist` a MUST with a stated scope, once
   runs and their scopes are part of the host protocol?
5. Should the step `domain` grammar become S303 in Standard 2.0, and should a
   domain registry accompany the ontology?
6. Should event triggers gain an `overlap` policy, so that W623 can cover the
   runs they start?
7. (Resolved.) The start operation always takes the header's version or an
   explicit none (§11.5, §5.19.2), and a host that loaded the catalog from a
   file MUST pass it, so a workflow that declares 1.2 only by its header is
   never run as one that declares no version.
8. Should the model family rule be revisited when a provider names a line
   whose identifiers do not start with its name (none of the lines in the
   vectors does)?
