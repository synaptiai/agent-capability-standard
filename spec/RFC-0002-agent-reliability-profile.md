# RFC-0002: Cross-session agent behavioural reliability
**Status:** Draft
**Target:** Standard v1.2.0
**Date:** 2026-08-29
**Tracking issue:** [#104](https://github.com/synaptiai/agent-capability-standard/issues/104)

## Summary
The standard scores how authoritative a *data source* is (§8). It has no way to
express how reliably an *agent* has been delivering across sessions. This RFC
proposes agent behavioural reliability as a first-class concept, and identifies
the prerequisite that currently blocks it: the standard has no agent identity
object to attach such a profile to.

## Motivation
§8.1 factors source ranking, time decay, field authority, and self-reported
confidence. All four describe a claim's provenance. None answers "has this
agent been delivering consistently over its last N sessions?"

That question is load-bearing for two planned areas of work. Certification
(#84) grades an implementation against fixed criteria at a point in time; an
agent that certifies well and then degrades is exactly what certification is
supposed to exclude. Federated trust (#85) asks one organisation to accept
another's agent; a behavioural profile the receiving party can verify is what
makes that acceptance more than a leap of faith.

The roadmap already anticipates this: v1.2.0 lists "formal trust calibration
workflows" and "runtime telemetry and observability hooks".

**Prior art.** The three-axis framing below (delivery, calibration, adaptation)
was proposed to this project in #104, which cites
[10.5281/zenodo.19348539](https://doi.org/10.5281/zenodo.19348539), *PDR in
Production*. That record is an unreviewed preprint, and **its author has since
confirmed on #104 that no reproducible published dataset supports either the
"6,342 cycles" figure or the claim of independent schema convergence across
three teams**, agreeing that it is design context rather than validation
evidence.

It is cited here on that basis. This RFC adopts the axes on their technical
merits; the standard must not present the record as evidence that they are
validated in production. The distinction matters beyond courtesy — §3.1 forbids
claims without evidence, and a specification that cited unreproducible figures
as support would violate the rule it exists to impose.

## Goals
- Express agent behavioural reliability as an optional, orthogonal signal.
- Keep every axis derivable, in principle, from data the standard already
  defines — or say plainly that it is not.
- Give safety-critical capability execution (§4.4) an optional gate that
  reflects recent behaviour, not only source provenance.

## Non-goals
- Replacing or re-weighting the §8 source trust model. Source authority and
  agent behaviour are independent; an agent's reliability says nothing about
  whether a sensor reading is accurate.
- Mandating telemetry collection. Implementations without behavioural history
  omit the profile.
- Defining a scoring function that composes the axes into one number. Composition
  is a deployment policy decision, not a standard-level one.

## Key decisions

### 1) Agent reliability is a new concept, not a §8 subsection
§8 is the *Authority Trust Model*, and every factor in it grades a source.
Adding agent behaviour there conflates two subjects that vary independently: a
high-authority source consumed by a degraded agent, and a low-authority source
consumed by a reliable one, are different situations and must remain separately
expressible.

### 2) The blocking prerequisite is agent identity
The standard has **no agent identity object**. `ProvenanceRecord.agent` and
`ActionRecord.actor` are bare strings; `entity_taxonomy.yaml` defines no agent
class. Separately, the reference implementation carries an unrelated third
notion of trust: `AgentDescriptor.trust_score` in
`grounded_agency/coordination/registry.py`, a static self-declared float used
only to order capability-discovery results, never updated from observed
behaviour.

A reliability profile has nothing to attach to until an agent is a first-class
identity. This RFC therefore proposes, as a prerequisite, that the standard
define an agent identity object and that `AgentDescriptor` be reconciled with
it, rather than introducing a third disjoint trust concept.

### 3) The three axes are adopted, but graded by derivability
They are genuinely orthogonal — high delivery with poor calibration is an
overconfident agent; high delivery and calibration with low adaptation is an
agent brittle to substrate change — but they are **not equally grounded** in
what this standard can measure.

| Axis | Substrate today | Status |
|------|-----------------|--------|
| `delivery_score` | `ActionRecord.status` (`planned`/`approved`/`executed`/`failed`/`rolled_back`) keyed by `actor` | **Provisional** — closest to derivable, but not yet a comparable score |
| `calibration_delta` | `Uncertainty.confidence` on claims, and `ActionRecord.status` as outcome | **Blocked on a join** |
| `adaptation_score` | none | **Requires new telemetry** |

`delivery_score` was described as derivable in the original proposal, and an
earlier draft of this RFC repeated that. It is not, and the reasons are
structural rather than a matter of implementation effort. `ActionRecord`
supplies `timestamp`, so a *window* is expressible — but three things a score
needs are missing:

1. **The population cannot be restricted to agents.** `actor` is a bare string
   documented as `agent/human`, with no discriminator. An agent delivery rate
   cannot be computed from a field that also holds people.
2. **No terminal-status subset is defined.** `planned` and `approved` describe
   work in flight. Counting them in a denominator penalises an agent for work
   not yet done; excluding them is a decision the standard has not made.
3. **`rolled_back` has no agreed sign.** A rollback following a correct
   checkpoint decision is the safety model working, not a delivery failure.
   Scoring it as failure would penalise exactly the behaviour §4.4 rewards.

Until an agent identity object resolves (1) and the standard fixes (2) and (3),
any `delivery_score` is deployment-local and not comparable between
implementations — which is most of what a standardised score is for.

`calibration_delta` compares predicted confidence against realised outcome, but
nothing joins the two: `ProvenanceRecord` carries `agent` and `claim_id`,
`ActionRecord` carries `actor` and `status`, and no relation connects a claim to
the action it informed.

Nor may the gap be closed by assumption. An implementation **MUST NOT** infer
that `ProvenanceRecord.agent` and `ActionRecord.actor` denote the same
principal; the standard does not define them as the same identity space, and
treating them as one would silently attribute a human operator's outcomes to an
agent's calibration. Until decision 2 settles the identity object, and a
claim-to-action relation exists, `calibration_delta` is not computable.

`adaptation_score` ("consistency under instruction variation or substrate
change") has no corresponding record anywhere in the schemas. Standardising a
field the standard cannot compute would be a claim without evidence, which is
the failure mode §3.1 exists to prevent. **This RFC therefore does not specify
it.** Whether it is reserved now as an optional field or omitted until the
telemetry exists is left open below; what this RFC rules out is specifying it as
though it were measurable today. The proposal's author concurs.

### 4) A session boundary must be defined or the window dropped
The proposal's `measurement_window_sessions: 30` presupposes a *session*
primitive. The standard defines none, and neither does the reference
implementation. Either the standard defines a session boundary, or the window is
expressed in terms it already has — observation count, or an ISO-8601 duration
consistent with §8's `decay_model`.

Until one of those is chosen, **this RFC specifies no window field**. A window
measured in an undefined unit is not portable: two implementations could report
`measurement_window_sessions: 30` over populations differing by an order of
magnitude and both be conformant. The proposal's author concurs that the window
should stay open pending a session or observation-window primitive.

### 5) Gating is optional and belongs with existing policy
Where a deployment gates `mutate` or `send` (§4.4) on reliability, the threshold
belongs in a domain profile alongside `risk_thresholds` and
`evidence_policy.minimum_confidence`, not hard-coded in the ontology. Domain
profiles already carry exactly this kind of tunable.

## Backward compatibility
Every field proposed here is optional; implementations without behavioural
telemetry omit the block. Per §11.4 adding an optional field is compatible, and
per §11.1 this is a MINOR addition. No existing capability changes semantics and
no existing workflow stops validating.

The prerequisite in decision 2 is not compatible in the same way. Promoting
`agent` from a bare string to a structured identity would be breaking for
producers of `ProvenanceRecord` and `ActionRecord`, and must be staged: introduce
the identity object alongside the string form, deprecate the string per §11.2
with its six-month minimum, and remove it in the next MAJOR.

## Conformance test updates
Conformance levels L1–L4 (§10.1) validate workflows, not trust configuration, so
no existing level changes. If a reliability gate is added, it needs:
- positive fixtures where a profile satisfies a gate and execution proceeds;
- negative fixtures where it does not, failing with a specific error code
  registered in §9.6 alongside the other safety errors;
- a fixture where the profile is absent, asserting the gate is skipped rather
  than failing closed — otherwise "optional" is not optional.

Decision 3's prohibition needs its own negative fixture, independent of any
gate: a world state where a `ProvenanceRecord.agent` and an
`ActionRecord.actor` share a string value, asserting that a conformant
implementation does **not** thereby treat them as one principal and does not
emit a `calibration_delta`. A MUST NOT that nothing tests is a comment.

## Alternatives considered
- **Add `§8.3 Agent Reliability Gate` as proposed in #104.** Smallest diff, and
  rejected under decision 1: it files agent behaviour under source authority and
  deepens a split the codebase already suffers from.
- **Extend `AgentDescriptor.trust_score` in the reference implementation only.**
  Cheapest, and leaves the standard silent, so nothing is interoperable or
  verifiable across parties — which is the entire point for #85.
- **Adopt `delivery_score` alone.** Honest and immediately implementable, but
  discards the orthogonality argument that motivates the proposal: delivery
  alone cannot distinguish a reliable agent from a confidently wrong one.
- **Defer until #84 and #85 are designed.** Reasonable sequencing, but both
  depend on this signal existing, so deferring inverts the dependency.

## Open questions
- What is the minimal agent identity object, and does it reconcile with
  `AgentDescriptor` or supersede it?
- Does the standard define a session, or express windows in observations and
  durations it already has?
- What relation joins a claim to the action it informed, so calibration is
  computable?
- Which `ActionRecord.status` values constitute delivery? Specifically: are
  `planned` and `approved` excluded as non-terminal, and is `rolled_back` a
  failure or a successful safety response? Without an answer, `delivery_score`
  is not comparable between implementations.
- Does the agent identity object make `actor` type-discriminated, or does
  `ActionRecord` gain a separate field distinguishing agent actors from human
  ones?
- Should `adaptation_score` be specified now as a reserved optional field, or
  omitted until the telemetry to compute it exists?
- Is regression detection (a rolling decline over successive windows) a
  standard-level field or a deployment-level alert?
