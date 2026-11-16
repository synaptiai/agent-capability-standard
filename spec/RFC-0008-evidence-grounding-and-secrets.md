# RFC-0008: Evidence, grounding and secrets
**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary

Standard 1.1.0 says every claim must be evidence-backed or marked as
inferred (§3.1), and gives that sentence nothing to stand on: the 36
capability outputs require `evidence_anchors` with no item schema, the
repository holds three anchor vocabularies, `inference_method` is in no
schema, F505 is reserved and never raised, nothing ties a citation to what
its producer saw, no rule keeps secrets out of evidence and records, the
evidence store has no contract, retention ignores where records live,
`confidence` is undefined and contradicted by the ontology's own
principle, and no notification exists for recorded evidence.

This RFC records the decisions Standard 1.2.0 makes on findings ACS-06,
ACS-21, ACS-22, ACS-23, ACS-40, ACS-51, ACS-53 and ACS-58 of the
[Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
It takes over decision 8 of [RFC-0005](RFC-0005-tool-calling-hosts.md)
(one anchor item, one kind vocabulary), withdrawn there, and answers its
open question 5. It is Accepted by the maintainer's instruction that every
remaining finding is implemented in 1.2.0; the text is in
[STANDARD-v1.2.0](STANDARD-v1.2.0.md) §3.1, §4.1.1, §5.20, §6.5, §6.6 and
§6.7.

## Motivation

- A consumer cannot check an anchor whose shape each producer chooses. The
  event schema allows seven kinds, the world state schema six, the Python
  SDK writes five others, a profile's `required_anchor_types` matches none,
  and the skills write bare strings. No schema has a digest, so a consumer
  cannot tell whether the cited content changed.
- §3.1 is called non-negotiable, but an output with `evidence_anchors: []`
  runs through the reference executor unremarked, and `inference_method`,
  the field §3.1 requires of an ungrounded claim, exists nowhere. A naive
  check would misfire: the executor builds `invoke` outputs with empty
  anchors itself.
- On a host that assembles a model's context for each request, a model can
  cite a stored item it never received. §5.17 says the executor cannot see
  content carried by other means; nothing asks the host to.
- §6.2 requires an event's `raw` to be "original unmodified data", so a host
  that redacts a credential contradicts the Standard and one that does not
  writes it into evidence. The rules existed only as model instructions in
  skills.
- A binding in another language has no evidence store interface to
  implement, and no way to say whether its evidence outlives the session; a
  retention period written to session-scoped storage cannot be kept, and
  nothing reports it.
- `meta.principles` says every capability returns confidence; 13 outputs do
  not declare it, and nowhere says what it measures.
- A host that pushes records to clients, as Standard Agents does, has the
  transport and no payload.

## Goals

- One evidence anchor type for capability outputs, events and records, in
  the canonical schemas, the ontology, the Python SDK and the TypeScript
  binding.
- A definition of grounded and inferred outputs, and a check (F505) that a
  workflow or a host opts into, implemented by the reference executor, the
  SDK and the binding, with language-neutral vectors.
- A rule tying a citation to the evidence its producer had, checkable for
  workflow values and attestable by the host for the rest.
- A normative rule keeping secrets out of evidence, records, diagnostics,
  traces and persisted memory, with a redaction marker.
- A small, storage-neutral contract for evidence stores with a stated
  durability, and an optional notification.
- Definitions of `confidence`, `inference_method` and `uncertainty`, and an
  ontology principle that matches the contracts.
- No 1.1-valid workflow becomes invalid; no 1.1 run behaves differently
  unless it opts in.

## Non-goals

- How a domain profile is selected and applied to a run (ACS-05, RFC-0010).
  This RFC states what a profile's `evidence_policy` means as a grounding
  policy; the host start option is the interface.
- Which anchor supports which field of an output: grounding is per output.
- Calibration of confidence, and thresholds: gates, conditions and profiles
  set those.
- A secret detector: the host decides what is secret. The reference
  implementations ship an informative default pattern set.
- Audit records (§6.4, RFC-0006 Part B) and the host protocol (§5.19), which
  this RFC only extends with `evidence_seen`, a start option (a list of
  grounding policies), and the optional notification of a stored audit
  record (`action_ids`).
- Privacy of personal data: the redaction mechanism applies, the policy is
  the deployment's.

## Key decisions

### 1) One evidence anchor (ACS-06)

`event_schema.yaml#/types/Anchor` 1.2.0, repeated by
`world_state_schema.yaml`: `ref` and `kind` required; `timestamp`,
`excerpt`, `digest` (`sha256:` + 64 hex, of the content as read; RFC 8785
canonical JSON for a JSON value) optional. Kinds: the event schema's seven,
`record` (the agent system's own records and workflow values), and vendor
kinds `x-…`. `ref` is opaque except the reserved `acs:` scheme.

### 2) Output items are anchors; other forms are deprecated, not refused (ACS-06, RFC-0005 OQ5)

All 36 outputs' `evidence_anchors` items are `anyOf [Anchor, string,
object]`. The anchor is the form. A bare string, and an object that is not
an evidence anchor (no kind, a kind such as `tool_output`), are the
deprecated legacy forms of 1.1 producers: accepted, never counted toward a
grounding policy, and removed in 2.0. No implementation refuses an output
because of the shape of its items unless a grounding policy applies, and
under one a legacy item only does not count. For workflows the union keeps
every annotation valid in 1.1 valid (verified on every repository catalog);
an unannotated element reference stays B204 until 2.0. An empty list
grounds nothing.

### 3) Grounded, inferred, and the evidence a producer had (ACS-21, ACS-22)

§3.1: an output is grounded when it holds an anchor to evidence its
producer had; otherwise it MUST carry `inference_method` and `confidence`.
§6.5 says what a producer had: what it obtained while it ran, received as
input, or was given in the request a model answered. An output that reports an action its producer performed is a
claim too, grounded by a `record` anchor to the action's record
(`checkpoint:<id>`, `audit:<id>`) or by what the action read or wrote; the
reference producers emit one. A host MUST NOT return an anchor it knows its
producer did not have. Outputs the executor builds itself, including a
waiting delegation's acceptance and result, are not checked.

`inference_method` is a plain string in the contracts, because 1.1 asked
for it with no vocabulary; §4.1.1 gives a vocabulary (with `x-` values) a
producer SHOULD use, and a grounding policy requires it of an output that
relies on being marked inferred.

### 4) `grounding@1` and F505 (ACS-21)

A must-understand extension with a workflow policy (`require`, `kinds`,
`attested`), host run policies of the same shape (a list given at start,
covering the steps of nested runs), and the same policies on a safety layer
for calls. Every host-side policy is checked against the ontology: an
unknown capability id is refused, never silently ignored. The executor
checks each host `Output` of a required capability: an `acs:` citation that
is not of kind `record` or that no reference the step binds covers (same
root, the bound path a segment prefix of the cited one, an index within a
bound slice counting), and an anchor missing from the host's
`evidence_seen`, fail with F505; otherwise the output passes when an anchor
counts or when it is marked inferred with a vocabulary method and a
confidence. F505 is not retried and can fire a failure mode. With
`grounding@1`, an `invoke` step carries its nested run's anchors. In a
workflow that targets 1.2, `grounding` without the extension is V106; in a
1.0 or 1.1 workflow it stays an unknown key (W604).

### 5) Attestation on the response (ACS-22)

`evidence_seen` is an optional member of the `Output` response, not of the
output: it is the host's statement about one answer, like `principal` and
`identity` on `Event`. It lists what the producer received for that answer
and nothing from stored history. Absent, it attests nothing; empty, it
attests that nothing was seen. A host that does not know the request (a
hook that sees only the tool call) omits it. `attested: true` counts only
established anchors, so an unattested output counts as inferred.

### 6) Common output fields (ACS-51)

§4.1.1 defines `confidence` (a self-reported probability that the output's
claim is correct; no threshold in the Standard), `inference_method` and
`uncertainty`. Every output declares all three; the event schema's
`Uncertainty` gains `interval` and `distribution`; `measure.uncertainty`
keeps `lower`/`upper` and gains the `Uncertainty` members. The ontology
principle is reworded, and every capability skill's `confidence` gloss
states what it is a probability of.

### 7) Evidence records and stores, and a notification (ACS-40, ACS-58)

§6.6: an evidence record is an anchor with its correlation (`run_id`,
`frame`, `step`, `capability`, `tool`, `call_id`). An implementation that
offers a store appends only, never reuses an id, reads by id and by
capability, kind and run, exports JSON Lines, states its durability
(`memory`, `session`, `durable`) and whether it is bounded, and counts the
records it removes other than by retention. Evidence records are not audit
records. A host MAY send `acs.evidence_recorded` when it stores evidence
records, a canonical event or audit records (named by `record_ids`,
`event_id` or `action_ids`); it is not a record and may be delivered at
most once. `schemas/interop/evidence.schema.json` defines the four shapes.

### 8) Retention follows the store (ACS-53)

Retention applies to the store records are written to; a session-scoped
store cannot keep a record longer. `audit.retention` is a §5.10.1 duration
(W614 for a literal outside it), and `audit` reports its `store`, so a
workflow can stop when the record will not outlive the session.

### 9) Secrets stay out of records (ACS-23)

§6.7 defines a secret and lists where it never goes: evidence, records and
notifications, events, world-state and audit records, diagnostics and host
error messages, traces, persisted data. Redaction replaces a secret with
`[REDACTED]`, a documented-loss transform (§3.2); an event's `raw` may be
the redacted original and MAY list `redactions`. A record MAY hold the
digest of a whole value that contains a secret, never the digest of a
secret alone; an implementation that cannot tell the two apart (a tool's
whole response) keeps no digest of a value in which it recognises a secret.
Persisting a secret is refused, not redacted. Workflows
carry no secrets: a host adds credentials where they are used. In the
reference implementations the rule is enforced by code: the SDK's stores,
collector, coordination log and runner, the binding's trace and
notifications (always), and the plugin's `persist` and `audit` skills,
whose command hooks share one scan and block credential-shaped content with
F504. The SDK adapter and the binding, as safety layers, refuse a `persist`
or `audit` call whose data holds a credential-shaped value or a registered
secret (F504, §5.18.10) by the same rule, narrower than the redactors': a
refusal of prose such as `token: rotate monthly` would block ordinary
memory, while redacting a word of prose in evidence costs little.

## Backward compatibility

- Opt-in: `grounding@1`, a host's grounding policies, `evidence_seen`, the
  filled `invoke` anchors. A 1.1 validator refuses the extension (V106).
  V106 for `grounding` without the extension applies only to workflows that
  declare 1.2; a 1.0 or 1.1 workflow with that key keeps its 1.1 W604.
- Compatible additions (§11.4): the optional ontology fields
  (`inference_method` as a plain string, `uncertainty`, `confidence` on 13
  outputs, `audit.store`, `measure.uncertainty` members); the canonical
  `Anchor`'s kind widened from an enum to a pattern (every 1.1 value still
  valid), the optional `digest` and event `redactions`; F505 accepted in
  `on_error`. Required output fields are unchanged, so the executor's
  contract check and its snapshot digest are unchanged.
- A deprecation, not a §11.4 addition for producers: `evidence_anchors`
  items now name the anchor form. Bare strings and objects that are not
  anchors stay accepted until 2.0 and are never counted; no implementation
  refuses an output for its item shape outside a grounding policy; only
  item values that are neither strings nor objects fall outside the
  contract. For workflows the union is compatible.
- Clarification: §3.1's 1.1 MUST already covered every claim; 1.2 says an
  action report is one and how it is grounded, and the reference producers
  emit `record` anchors. Nothing checks it without a policy.
- Warning-first: W614 for an `audit` `retention` literal outside the
  duration grammar; no repository catalog is affected.
- New duties of implementations (MINOR): the available-evidence and secrets
  rules, and the duties of an implementation that offers an evidence store.
- Python SDK (0.x): anchor kinds become canonical; the old names are
  accepted with a `DeprecationWarning`, and queries by them return what they
  returned in 1.1; kept anchors are frozen and ids are never reused.
  TypeScript binding: `fileAnchor` carries `digest` instead of
  `metadata.sha256`; the default output check is unchanged, and the new
  checks run only under the `grounding` option; trace redaction is always
  on.

## Conformance test updates

- `tests/conformance/grounding/check.json`: normative vectors for §5.20's
  check of one output, run by the Rust core, the Python package and the
  TypeScript package (`@synaptiai/acs-core`), including bound-path coverage (sibling, parent,
  index in and outside a bound slice), `acs:` kind, absent vs empty
  `evidence_seen`, legacy forms that do not count, a free
  `inference_method` on a grounded output, and an action's `record` anchor.
- Runtime fixtures `tests/conformance/runtime/grounding_*.json`: the check
  inside runs, host policies (a list, applied to nested runs), a workflow
  policy that does not reach a nested run, `evidence_seen`, failure-mode
  loops on F505, filled `invoke` anchors, the waiting-`delegate` exemption
  and the check of a delegation that does not wait, other exemptions.
- Workflow fixtures for `grounding` (V106 in a 1.2 target, W604 in a 1.1
  one, S303, S304, V101, a passing policy) and for W614 on
  `audit.retention`.
- `tests/conformance/secrets/redact.json`: informative vectors for the
  reference redactors.
- Schema tests: the two canonical `Anchor`s and `Uncertainty`s equal; the
  interop schema agrees with them; every output declares the common fields;
  the 23 outputs that require `confidence` are pinned; skill-local schemas
  are self-contained.

## Alternatives considered

- **Object-only anchor items, or `anyOf [Anchor, string]`.** Typed element
  references, but 1.1 workflows that annotate anchors as strings would
  become invalid (object-only), and 1.1 producers' objects without a kind
  would violate the contract with no opt-in (both). Rejected for 1.x.
- **No item schema at all.** Leaves the anchor type out of every contract
  and generator, which is the finding.
- **Forbid bare strings now.** The SDK and 42 skills write them. Deprecated
  instead.
- **A closed `inference_method` vocabulary in the contract.** Would make a
  1.1 producer's free value a contract violation without opting in. A
  SHOULD, enforced under a policy.
- **Opt in by `spec_version: "1.2"`.** Which capabilities to check is a
  deployment's choice, not a property of a catalog's target version; the
  executor does not see a header-declared version. Rejected for an
  extension.
- **Profile-only opt-in.** The Standard does not yet say how a profile is
  applied; a workflow extension and a host option do not wait for it.
- **Root-only availability of `acs:` citations.** A step that binds one
  element could cite another; the bound path is the unit.
- **Check a waiting delegate's result when it arrives.** Needs a second,
  event-shaped rule for an output the executor composes; exempt, as other
  wait outputs are (open question 6).
- **Attestation in the output.** It would be stored, snapshotted and bound;
  the protocol response is where hosts already attest. Attestation from a
  stored trace is rejected: it is the failure the rule is meant to stop.
- **Fail unattested citations by default.** Every host that cannot attest
  would fail; `attested` makes it the workflow's choice.
- **A digest of a secret as the redaction marker.** Low-entropy secrets
  would be recoverable by guessing.
- **A validator warning for secret-looking literals.** A heuristic needing a
  pattern engine in the core; the catalog rule stays the author's.
- **Model instructions only in the plugin skills.** The finding; code
  checks in both skills that write records instead.
- **An informative-only store interface.** Leaves durability, which
  retention depends on, unstated.
- **A separate notification type for audit records.** One payload with an
  id member per kind of store is simpler for clients.
- **Retype `measure.uncertainty` as `Uncertainty`.** Changes a required
  output shape (MAJOR).

## Open questions

1. **Secret inputs.** Should 1.3 let a workflow mark an input `secret`, so
   the executor keeps it out of its trace, records and snapshots, instead of
   relying on hosts to add credentials where they are used?
2. **Indefinite retention.** Should `audit.retention` accept a keyword for
   "keep until removed by hand", or is a durable store without retention
   enough?
3. **Calibration.** Should a host be able to state, in a machine-readable
   field, how its confidences are calibrated, so a profile's
   `minimum_confidence` can require calibrated ones?
4. **Per-field grounding.** Should an anchor be able to say which output
   field it supports, for outputs that combine grounded and inferred parts?
5. **Typed anchors in 2.0.** When the legacy forms are removed, should
   `evidence_anchors` become `minItems: 1` for capabilities whose outputs
   are always about external evidence, or stay grounding-policy driven?
6. **Waiting delegations.** Should a later version check the result of a
   waiting `delegate` against the delegate's own anchors (the event's
   `anchors`), now that a policy requiring `delegate` covers only
   delegations that do not wait?
7. **Plugin scan reach.** The `audit` skill's hook scans the command that
   appends the record; a record copied from an intermediate file is outside
   it, and the skill's procedure forbids that path. Should the plugin's
   global `PreToolUse` hook refuse any write to `.claude/audit/records.jsonl`
   that does not carry the record as a literal?
