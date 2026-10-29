# RFC-0004: Agent identity
**Status:** Accepted
**Target:** Standard v1.1.0
**Date:** 2026-10-28
**Tracking issue:** [#114](https://github.com/synaptiai/agent-capability-standard/issues/114)

## Summary
This RFC defines a minimal **agent identity** object and a must-understand
extension, `identity@1`, that lets a workflow say how the senders it accepts
must be authenticated and which trust classes it accepts them from. It
meets the prerequisite RFC-0002 names (decision 2: "the blocking prerequisite
is agent identity") without defining any reliability score, and it completes
the part of #114's E2 that RFC-0003 left open: `sender_check` and
`trust_class`.

## Motivation
Standard v1.1 §5.15 (`delegation@1`) filters received items by principal:
`accept_from` lists the opaque strings the host maps its identities to, and a
kept item carries its `sender`. Two things an orchestrator needs cannot be
said with that alone:

1. **How the sender was authenticated.** An owner's answer that arrives over
   an authenticated chat session and one that arrives by a forwarded e-mail
   can carry the same principal string. #114's E2 asked for `sender_check`:
   the identity field that must match before the data is used.
2. **What kind of party the sender is.** The owner, a decision maker, a
   system of record, the orchestrator's own sub-agent, a peer agent, a
   colleague and an outsider deserve different trust, and §8 ranks sources
   by authority but has no notion of who an agent or person is.

RFC-0002 found the same gap from the other side: a reliability profile has
nothing to attach to, because `ActionRecord.actor` and
`ProvenanceRecord.agent` are bare strings of different kinds, and the
reference implementation's `AgentDescriptor.trust_score` is a third,
disjoint notion.

## Goals
- One identity object that the host reports, the world state records, and
  the reference implementation's agent registry can produce.
- Workflow-side checks on how a sender was authenticated and on its trust
  class, enforced by the executor and checked by the validator.
- An "always ask" rule: a step that requires approval and uses an item
  from a named trust class is asked of a person, whatever mandate would
  cover it.
- A default mapping from trust class to §8 source weight.
- No breaking change: existing string fields stay, and every new field is
  optional.

## Non-goals
- Behavioural reliability scores (`delivery_score`, `calibration_delta`,
  `adaptation_score`): RFC-0002 stays a Draft for them.
- Attestation, credentials or key formats. How a host authenticates a party
  is a deployment concern; the identity only records the mechanism.
- A session primitive (RFC-0002 decision 4 stays open).

## Key decisions

### 1) The identity is small and host-reported
`schemas/agent_identity_schema.yaml` defines `agent_identity`:

| Field | Required | Meaning |
|-------|----------|---------|
| `principal` | yes | The opaque string of §5.15, compared by exact match |
| `kind` | yes | `agent`, `human` or `service` |
| `role` | no | The role it acts in (e.g. `reviewer`) |
| `model_family` | no | For an agent: the model family it ran on |
| `owner` | no | The principal of the person or organisation it acts for |
| `authenticated_by` | no | How the host authenticated it: `session_id`, `chat_user_id`, `code_host_login`, `directory_id`, `api_key`, `signed_token`, or an `x-` vendor value |
| `trust_class` | no | `owner`, `decision_person`, `system_of_record`, `own_subagent_report`, `peer_agent`, `colleague` or `external` |

The host fills it in from whatever it authenticated; the standard does not
say how. `kind` makes `ActionRecord.actor`'s "agent/human" explicit, which
RFC-0002's open question on type discrimination asked for, following the
precedent of `event.source.kind`.

### 2) `identity@1` filters by mechanism and trust class
`receive`, `synchronize` and a waiting `delegate` (for its result) gain
three inputs, bound only with `identity@1` declared (V106 otherwise). The
first two filter:

- `sender_check`: the `authenticated_by` values accepted;
- `accept_trust_classes`: the `trust_class` values accepted.

On a wait, the host reports an `identity` with each event; its `principal`
is the item's principal. A response that names a different principal
beside it, or whose identity is malformed, is rejected and changes
nothing. When either check is bound, an item whose identity is missing, or
whose mechanism or class is not listed, is dropped and counted, exactly as
`accept_from` drops other principals. Each kept item carries `sender` (its
principal) and `sender_identity` (the whole identity); a `synchronize` wait
carries them beside the agreed state. On a step that does not wait, the
host gets the inputs with the step and applies them to what it returns, as
for `accept_from`, and each item it returns must carry the
`sender_identity` it applied them to. `accept_from` stays the list of
principals, which is what E2's `also_accept` asked for.

A literal value that is not a list of known values is S303; a reference
that resolves to anything else (null, say) fails the step (R402) rather
than turning a check off. A workflow that does not declare
`identity@1` ignores any identity a host sends, so it runs exactly as
before.

### 3) Some trust classes always need a person
The third input, `always_ask_trust_classes`, marks instead of filtering. An item
kept from one of those classes, or with no identity or no trust class
(failing closed), marks the step's output, and the mark follows the data:
a later step that reads a marked store, directly or through other steps (a
reference in any executable field: bindings, condition, gates, approval,
wait, and context a recovery loop injects), is marked too, and so is an
`invoke` whose nested run was. Every step of a nested run invoked by a
marked step is marked. A mark is never removed during a run, even when a
recovery loop runs the marking step again.

A marked step that requires approval is asked of a person even when its
`approval` names a `standing_mandate`: a mandate never covers an action on
such an item. The approval request names a `human` approver with
`always_ask: true` (keeping `role` and `min_approvers`), and the approval
record names no mandate. In an unattended run, that step follows its
`when_unattended` plan; the validator warns (W606) when a step whose only
unattended plan is a mandate uses, through bindings, a step that binds
`always_ask_trust_classes`. Every action record of a marked step carries
`always_ask: true`, and the trace records `always_ask`. A marked step that
does not require approval runs as it otherwise would.

The mark follows references only. A host that carries an item's content
into a later step by other means (its own memory, a side channel) is
outside what the executor can see; the RFC records this as a limit, not a
guarantee.

### 4) Trust classes map to §8 weights
`authority_trust_model.yaml` gains `trust_classes`, a default weight per
class, so evidence that a kept item contributes is weighed by who sent it.
When the evidence also has a source type, the lower of the two weights
applies. A domain profile overrides a class with a `trust_weights` key
`trust_class:<class>`, apart from source keys of the same name (there is a
`system_of_record` of each). The classes are exactly those of
`agent_identity.trust_class`, which the canonical-schema validator checks.

### 5) The world state records identities beside the strings
`ActionRecord.actor_identity` and `ProvenanceRecord.agent_identity` are
optional `agent_identity` objects (`world_state_schema.yaml` 1.1.0, still
unreleased, holds a copy of the identity type, so its vendored copies stay
self-contained; the canonical-schema validator keeps the two equal). The
strings stay, and an implementation MUST NOT infer from the string fields
alone that `ProvenanceRecord.agent` and `ActionRecord.actor` denote the
same principal (RFC-0002's recommended
prohibition); with identities present, two records denote the same
principal exactly when their identities' `principal` values are equal.
Removing the strings is left to a future MAJOR, per §11.2.

### 6) The reference implementation produces identities
`AgentDescriptor.identity()` returns the identity of a registered agent
(its id as principal, identity fields from its metadata, refusing values
outside the vocabularies), and a run can be
started with an actor identity that every action record then carries, with
`actor` set to the identity's `kind`. A malformed actor identity refuses
the start. `AgentDescriptor.trust_score` is unchanged: it orders discovery
results and says nothing about who an agent is.

## Backward compatibility
Every addition is optional: three new inputs gated by a new extension, new
optional fields in the world state and the trust model, a new schema file.
A workflow that does not declare `identity@1` validates and runs exactly as
before; per §11.4 this is a MINOR change, made in the v1.1.0 candidate.

## Conformance test updates
- Static fixtures: binding `sender_check`, `accept_trust_classes` or
  `always_ask_trust_classes` without `identity@1` is V106; values outside
  the vocabularies are S303 (`fail_identity_undeclared`,
  `fail_identity_vocabulary`, `pass_identity_senders`).
- Runtime fixtures: a step reading, directly or transitively, an item from
  an always-ask class is asked of a person despite a standing mandate, and
  follows `when_unattended` in an unattended run; an unmarked step still
  uses the mandate.
- Runtime fixtures: items whose mechanism or trust class is not accepted
  are dropped and counted; a kept item carries `sender_identity`; an item
  without an identity is dropped when either check is bound
  (`identity_sender_check`, `identity_synchronize`). The executor's tests
  refuse a response whose `principal` contradicts its `identity`, or whose
  identity is malformed.
- Runtime fixtures for "always ask": `always_ask_overrides_mandate`,
  `always_ask_unattended`, `always_ask_unmarked_item`,
  `always_ask_fails_closed`, `always_ask_through_recovery`,
  `always_ask_through_invoke`, `always_ask_invoke_condition`; and
  `identity_input_unresolved` for an input that resolves to no list. The
  validator's tests cover W606 for a mandate-only step that uses an
  always-ask item.
- Not yet tested: the MUST NOT on joining `actor` and `agent` strings is a
  world-state property, which workflow fixtures cannot exercise.

## Alternatives considered
- **E2's `agent_ref` block as proposed**: a separate block on `delegate`,
  `receive` and `synchronize`. Rejected because v1.1 already models these
  as inputs (`delegation@1`), and a second place to say the same thing would
  invite contradictions.
- **Principals only**: leave authentication to the host entirely. Rejected:
  a principal string cannot tell a session-authenticated owner from a
  forwarded message that names the owner.
- **Record `trust_class` without filtering**: cheaper, but then a workflow
  cannot refuse a peer agent's report where only the owner may answer.
- **"Always ask" by inspecting a step's inputs** for marked items: simpler,
  but a step that acts on a summary of the item (a `generate` in between)
  would escape it. Following the data through stores catches that.

## Amendment: the delegate's identity

Asked for by the #114 author (E2's `agent_id`) and internally. Without it a
workflow could not bind a delegation's result to the party that took it:
`agent` is a target name, not a principal; a quorum counted reviewers by
name and self-reported `reviewer_id`, so two names one host maps to one
agent counted twice; and a result from a misrouted delegate was kept
unless an `accept_from` happened to name the right principal.

- With `identity@1`, a delegation may attest `effective.identity` (an
  `agent_identity`); a malformed one, or one whose `model_family` or
  `role` contradicts `effective`'s, is R402.
- A waiting delegate keeps only results whose principal is the attested
  one; others are dropped and counted (`delegate_identity`), like
  `accept_from`, so a peer that injects a correlated event cannot end the
  step. A retry binds its new delegation's identity.
- `quorum.require_distinct_identities` counts a verdict only if it is read
  from its reviewer's own result (the reviewer waits for it; `verdicts`
  may reference nothing else) and the reviewer has an attested principal no
  other counted reviewer has. Fail-closed, like `require_read_only`.
- A quorum's model families count only as attested (`effective`, or the
  identity's), no longer as requested.

Host attestation detects an honest host's error (fallback routing, a name
mapped to the wrong session, a retry sent elsewhere) and a peer answering
in the delegate's place, and makes the host accountable for what it
reports. It does not protect against a host that lies: that needs a
host-signed delegation receipt and results signed by a key bound to the
principal, which stay out of scope (Non-goals). "Distinct principals" is
not "distinct models or operators".

## Open questions
- Whether a future MAJOR replaces `ActionRecord.actor` and
  `ProvenanceRecord.agent` with identities outright.
- Whether a delegation should be refused up front when the assignee's
  attested `trust_class` is not acceptable (an `accept_trust_classes` for
  the assignee, at delegation time).
