# RFC-0003: Orchestration extensions and validation semantics
**Status:** Accepted
**Target:** Standard v1.1.0
**Date:** 2026-10-27
**Tracking issue:** [#114](https://github.com/synaptiai/agent-capability-standard/issues/114)

## Summary

Issue #114 asks for six optional workflow fields that orchestrators need —
waiting for an event (E1), naming the agent a step delegates to (E2),
structured approval (E3), review verdicts (E4), escalation (E5) and triggers
(E6) — and asks how such additions should be made (Q1), how E2 relates to
the identity work of RFC-0002 (Q2), and why the reference validator and
workflow engine disagree (Q3).

This RFC answers all three and specifies Standard v1.1.0
([STANDARD-v1.1.0](STANDARD-v1.1.0.md)):

1. **Mechanism (Q1).** Extensions are optional fields grouped into named,
   versioned extensions. A workflow that depends on one declares it in
   `workflow_extensions.requires`, so a consumer that does not know it
   refuses the workflow instead of silently ignoring a safety-relevant field.
2. **One validator (Q3).** The validator and the engine disagreed because
   they were two implementations of under-specified rules. The rules are now
   specified (edges, safety flags, expressions, diagnostics) and there is one
   reference implementation, a Rust core used by both the CLI and the Python
   engine.
3. **E2 split (Q2).** The parts of E2 that do not need agent identity
   (fresh context, model family, role, sender filtering) ship now; naming a
   specific agent waits for RFC-0002's identity object.

## Motivation

Orchestrators built on the standard need to pause for external events,
gate actions on human approval, combine independent reviews, escalate to a
handler when recovery is exhausted, and start runs on a schedule or an
event. Each of these is expressible today only as prose in `purpose` or
`failure_modes[].condition`, which no validator or executor can check.

Investigating the issue also showed that the standard's existing rules
were not precise enough to implement twice consistently:

- `precedes` was read as "must be present"; `conflicts_with` forbade two
  capabilities in one workflow, which outlaws the normal
  mutate-then-rollback recovery.
- Safety flags were per-step booleans that a workflow could set to `false`
  on `mutate`, and the catalog itself did so for approval.
- Conditions and gate expressions had no grammar; the catalog compared an
  object with a string and read references YAML had turned into mappings.
- There was no notion of a warning, so validators either failed workflows
  for recommendations or ignored them.

## Goals

- Specify E1–E6 so that a validator can check them statically and an
  executor can run them.
- Make adding such fields safe: a consumer never runs a workflow while
  ignoring a field it does not understand that changes what is safe.
- Make the existing semantics precise enough that independent
  implementations agree, and give them a shared conformance suite.
- Keep every valid 1.0 workflow valid unless it relied on a rule this RFC
  identifies as a defect.

## Non-goals

- Agent identity, attestation of who an agent is, and cross-session
  reliability (RFC-0002).
- A general-purpose expression language: expressions stay comparisons and
  boolean logic over JSON values.
- Transport, storage or UI for approvals and events; the executor is
  sans-IO and leaves those to the host.

## Key decisions

### 1) Extensions are optional fields with a must-understand declaration

Each extension adds optional fields and is named `name@major` (`triggers@1`,
`recovery@1`, `wait@1`, `approval@1`, `delegation@1`, `quorum@1`). Using an
extension's widening fields requires listing it in
`workflow_extensions.requires`; an unknown name or major is V106. Unknown
fields outside extensions are W604 and ignored; `x-` fields are vendor data.

### 2) Edges are specified, and concurrency counts

`precedes` constrains order only when both capabilities are present.
`conflicts_with` forbids concurrency (a shared `parallel_group`), not
co-existence. `soft_requires` is any-of presence per target and yields a
warning. A step in the same parallel group as another does not run before
it. New edges make `constrain` a soft prerequisite of `execute`, `mutate`
and `send`; six edges that described follow-ups rather than prerequisites
became `enables`. A pre-flight check is `constrain`; an early `verify` is an
ordering error.

### 3) Safety flags inherit and cannot be weakened

Omitted flags inherit from the ontology; the effective flag is the stricter
of declaration and ontology, and a weaker declaration is W602 and has no
effect. `mutation_overridable` lets `audit` (append-only, low risk, no
checkpoint or approval) declare `mutation: false`.

### 4) Diagnostics have fixed severities

V/B/S/R/F codes are errors and the new W6xx codes are warnings; strict mode
promotes warnings. New error codes: V106–V109, B206, R405, R406.

### 5) An ACS expression language that is a CEL subset

Conditions, gates and failure-mode `when` share one small grammar
(comparisons, `!`, `&&`, `||`, literals, references) with fixed limits and
fail-safe error handling per site. We evaluated adopting CEL wholesale and
chose an ACS-owned grammar that is a strict subset of CEL: every valid ACS
expression is valid CEL with the same result wherever CEL produces one,
which the conformance suite checks against cel-go. Gates gain `phase:
before|after`.

### 6) E1–E6

- **E1 wait** on `receive` (or multi-agent `synchronize`): event type,
  correlation, liveness probing, a mandatory timeout, and checkpoints that
  do not survive a wait.
- **E2 delegation**, split: `fresh_context`, `model_family`, `role` and
  `accept_from` now; agent identity later (RFC-0002).
- **E3 approval**: structured approver, digest binding of what was shown
  (RFC 8785 canonical JSON over I-JSON values),
  recheck before acting, expiry, single use, and fail-closed handling of
  unattended runs.
- **E4 quorum** on `constrain`: typed review verdicts, explicit reviewers,
  vocabulary, pass and blocking values, minimum passes, pinning, and
  reviewer independence checks.
- **E5 escalation**: `on_exhausted` and `action: escalate` route to an
  `invoke` step marked `handler: true`. Failure modes fire on the code a
  step failed with (`on_error`: R401–R403, R406, F501, F502, F504) or on a
  `when` expression; recovery loops are bounded (`max_loops` ≤ 1000)
  because a loop needs no host call.
- **E6 triggers**: a `triggers[]` list of schedule (cron or interval with
  IANA time zone), event, manual and invoke triggers, with attendance.

### 7) One reference implementation

The validator and a sans-IO executor live in a Rust crate compiled into the
Python package; `tools/validate_workflows.py` and the Python
`WorkflowEngine` both call it, so they cannot disagree.

## Backward compatibility

- New fields are optional, and workflows that use extensions must declare
  them, so 1.0 consumers refuse rather than misread them.
- `inputs` becomes optional; a required field becoming optional is
  compatible.
- The edge, flag and unknown-field changes are clarifications applied to
  1.0 and 1.1 workflows alike. They can reject a 1.0 workflow only where it
  relied on a defect: a `to` capability before its `precedes` source, a
  prerequisite running concurrently with its dependant, or two conflicting
  capabilities in one parallel group. Safety-flag downgrades now warn
  instead of passing silently, and have no effect.
- Validators for 1.1 support 1.0 and 1.1 (GOVERNANCE: last two minors).
- B205's meaning narrows to "annotation names no type"; an annotation that
  contradicts the schema is B203, as the 1.0 reference validator already
  reported.

## Conformance test updates

- Workflow fixtures for each rule (`tests/fixtures/EXPECTATIONS.json`),
  including warning expectations, where an empty list means no warnings.
- Language-neutral expression fixtures: `tests/conformance/expressions/eval.json`
  (evaluation) and `tests/conformance/expressions/check.json` (static
  checks), run against the reference core and cel-go.
- Extension fixtures (`tests/fixtures/*`: triggers, recovery and
  escalation, waits, approvals, delegation, quorums) and runtime fixtures
  for the reference executor (`tests/conformance/runtime/*.json`).

## Alternatives considered

- **New capabilities instead of fields** (e.g. an `await` capability):
  rejected; waiting, approval and escalation qualify how a step runs rather
  than adding a primitive, and a new capability would need its own
  ontology edges.
- **Ignore unknown fields silently** (1.0 behaviour): rejected for
  safety-relevant fields, which a consumer must not drop; kept, with a
  warning, for everything else.
- **Adopt CEL directly**: rejected for now; CEL's breadth (macros,
  functions, type system) is more than conditions need and harder to
  implement conformantly in every language. Staying a strict subset keeps
  the option open.
- **Make safety flags required on every step**: rejected; it adds noise
  and invites the downgrades it would be meant to catch. Inheritance with a
  downgrade warning gives the same guarantee.
- **Keep two validators and test them against each other**: rejected; a
  single core removes the class of disagreement instead of detecting it.

## Amendments from porting feedback

The issue author ported nine production workflows to the candidate; all
validated, and the validator found two real defects in them (an invoke
cycle, and a checkpoint taken before a wait that authorised a mutation).
They reported five gaps, closed in the candidate before it is final:

- **Mistyped binding keys** were silent. An `input_bindings` key outside
  the capability's input schema is now W604 (§5.5), and a literal invoke
  `input` is checked against the target's `inputs` (S303 / S304, §5.12).
- **Principals** had no defined form. They are opaque strings compared
  exactly, naming the authenticated deliverer of an item (§5.15).
- **Lost liveness and timeout** were both R401, so a silent worker could
  not be re-checked while an expired wait escalated. Lost liveness is now
  R406; a re-check is a recovery loop back to the wait itself. A failure
  mode that handled lost liveness through R401 must add R406. A failure
  action that warns and continues was considered and not added: it would
  let later steps run on the output of a step that failed.

## Open questions

- How agent identity (RFC-0002) will extend E2 with a named agent and
  attestation of `fresh_context`.
- None further for the domain catalogs: the four under `schemas/workflows/`,
  which failed validation before this RFC, now pass in strict mode and are
  validated in CI.
