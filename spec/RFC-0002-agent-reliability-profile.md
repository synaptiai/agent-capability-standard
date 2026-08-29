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
Production*. Recorded honestly: that record is an unreviewed preprint uploaded
the same day the issue was filed, authored by the person who filed it; its
claim of "independent schema convergence across three teams" rests in part on
substantially identical proposals the same author opened across six
repositories; and the acronym expands three different ways across the author's
own primary sources. This RFC adopts the axes on their technical merits, not on
that record's authority, and the standard should not present it as validating
evidence.

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
| `delivery_score` | `ActionRecord.status` (`planned`/`approved`/`executed`/`failed`/`rolled_back`) keyed by `actor` | **Derivable now** |
| `calibration_delta` | `Uncertainty.confidence` on claims, and `ActionRecord.status` as outcome | **Blocked on a join** |
| `adaptation_score` | none | **Requires new telemetry** |

`calibration_delta` compares predicted confidence against realised outcome, but
nothing joins the two: `ProvenanceRecord` carries `agent` and `claim_id`,
`ActionRecord` carries `actor` and `status`, and no relation connects a claim to
the action it informed. Whether `agent` and `actor` even denote the same
identity is undefined — which decision 2 would settle.

`adaptation_score` ("consistency under instruction variation or substrate
change") has no corresponding record anywhere in the schemas. Standardising a
field the standard cannot compute would be a claim without evidence, which is
the failure mode §3.1 exists to prevent.

### 4) A session boundary must be defined or the window dropped
The proposal's `measurement_window_sessions: 30` presupposes a *session*
primitive. The standard defines none, and neither does the reference
implementation. Either the standard defines a session boundary, or the window is
expressed in terms it already has — observation count, or an ISO-8601 duration
consistent with §8's `decay_model`.

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
- Should `adaptation_score` be specified now as a reserved optional field, or
  omitted until the telemetry to compute it exists?
- Is regression detection (a rolling decline over successive windows) a
  standard-level field or a deployment-level alert?
