# Specification Changelog

This changelog tracks changes to the **Agent Capability Standard specification** itself. For plugin and project-level changes, see the [root CHANGELOG](../CHANGELOG.md).

## Unreleased

### Added — Standard v1.1.0 (Candidate Standard), RFC-0003 and RFC-0004 (#114)
- **[STANDARD-v1.1.0](STANDARD-v1.1.0.md)**,
  **[RFC-0003](RFC-0003-orchestration-extensions.md)** (Accepted) and
  **[RFC-0004](RFC-0004-agent-identity.md)** (Accepted; sender identity,
  listed under the remaining open items below). v1.0.0 remains supported;
  Appendix C of v1.1.0 lists every change. RFC-0001, which v1.0.0
  shipped, is marked Accepted.
- **Condition expression language (§5.8)** for `condition`, `gates[].when` and
  `failure_modes[].when`: a small grammar that is a strict subset of CEL, with
  fixed limits, fail-safe error handling per site, static type checks and null
  narrowing. Gates gain `phase: before|after` (§5.6).
- **Diagnostic severities (§9.1)** and warning codes W601–W616 (§9.7); new
  error codes V106–V109, B206, R405, R406.
- **`mutation_overridable` (§4.4)** for append-only capabilities (`audit`).
- **Orchestration extensions (§5.9–§5.17)** — triggers, handler steps,
  recovery and escalation, wait, approval, delegation, quorum, sender
  identity — opted into with `workflow_extensions.requires`.
  Extension fields are must-understand (V106 when used undeclared).
  The reference validator enforces all of them: declarations, `triggers@1`
  (§5.10, with the duration grammar of §5.10.1), `recovery@1` (§5.11,
  §5.12), `wait@1` (§5.13), `approval@1` (§5.14), `delegation@1` (§5.15),
  `quorum@1` (§5.16) and `identity@1` (§5.17). A validator must refuse a declared extension it does
  not check (V106).
- **Runtime conformance fixtures (§10.3)**: scripted runs of the reference
  executor covering gates, conditions, checkpoints, approvals, deferral,
  waits, retries, failure modes, recovery, escalation, invocation, quorums
  and sender identity (§5.6–§5.17).
- **Effective `requires_checkpoint` (§5.2.1)** raised by a step is enforced:
  F501 when no checkpoint runs before it.
- **`event_schema.yaml` 1.1.0:** `source.kind` gains `agent`, so events from
  other agents can trigger workflows (§5.10).
- **`world_state_schema.yaml` 1.1.0:** `ActionRecord.status` gains
  `rejected` and `expired`, an optional `approval` record binds the action
  to the decision, and an optional `reason` says why an action did not go
  ahead (§5.14).
- **Failure modes (§5.7, §5.12)** fire on the codes a step can fail with:
  `on_error` takes R401, R402, R403, R406, F501, F502 and F504. An expression
  error (R405) is fail-safe at its site and never fails a step. A recovery
  loop's `max_loops` is at most 1000.
- **Approval digests (§5.14)** are computed over I-JSON values (RFC 7493),
  so every implementation's RFC 8785 canonical JSON agrees.
- **`review_verdict_schema.yaml`** (1.1.0, with `scope`) for the verdicts a quorum counts,
  and ontology additions for delegation and quorums: `delegate` inputs
  `fresh_context`, `model_family`, `role` and output `effective`;
  `receive`/`synchronize` input `accept_from`; received items' `sender`;
  `constrain` output `tally` (§5.15, §5.16).

### Changed — clarifications of 1.0 semantics (#114)
- **Edges (§4.3, [EDGE_TYPES](EDGE_TYPES.md)).** `precedes` orders two
  capabilities only when both are present; `conflicts_with` forbids
  concurrency (a shared parallel group), not co-existence; `soft_requires` is
  any-of presence per target and warns. A step in the same parallel group
  does not run before another. Five follow-up edges became `enables`, one
  redundant edge was removed, and `constrain` became the soft prerequisite of
  `execute`, `mutate` and `send`.
- **Safety flags (§5.2.1)** inherit from the ontology; a weaker declaration
  has no effect and warns (W602).
- **Unknown fields (§11.3)** are reported (W604) and ignored; `x-` fields are
  vendor extensions. `inputs` is optional (§5.1).
- **Version declaration (§11.5):** `spec_version` or the file header; missing
  → W605, unsupported → V109.
- **B205** means "annotation names no type"; an annotation that contradicts
  the schema is B203 (§9.3).
- **Step fields 1.0 left unchecked (Appendix C).** `store_as` must be an
  identifier (S303); gate and failure-mode `action` values outside their
  enums are S303. A failure mode's `condition` is prose and never
  evaluated: its trigger is `when` or `on_error`. **Migration:** a 1.0
  failure mode whose trigger was written in `condition` must add a `when`
  (or `on_error`), or it never fires.
- **Capability ontology 2.1.0** records the edge changes above,
  `mutation_overridable` and the new inputs and outputs (Appendix C).

### Changed — remaining open items (#114)
- **Wait on `delegate` (§5.13):** a `delegate` step can wait for its
  delegate's result (matched by the delegation's required `task_id`; the
  output gains `result`; one `timeout` bounds both phases; `accept_from`
  and the `identity@1` sender inputs apply to the result). A `retry`
  delegates again, naming the replaced delegation (`replaces`), so one
  silent reviewer is replaced alone; a delegation not accepted is R402. A
  verdict in a reviewer step's `result` counts only for that reviewer. `quorum.verdicts` (§5.16) may be a list
  of references, one per reviewer step.
- **Read-only reviewers (§5.15, §5.16):** `delegate` input `read_only`,
  attested in `effective.read_only`; `quorum.require_read_only` requires it
  of every reviewer (F504 statically, and uncounted verdicts at run time).
- **Sender identity (§5.17, `identity@1`, RFC-0004).** An `agent_identity`
  (`schemas/agent_identity_schema.yaml`) the host reports with each event a
  wait receives. `receive`/`synchronize` inputs `sender_check` (accepted
  `authenticated_by` values) and `accept_trust_classes` drop other items;
  `always_ask_trust_classes` marks items of those classes (and, failing
  closed, items with no trust class); the mark follows the data through
  later steps, injected recovery context and nested runs, and a marked step
  that requires approval is asked of a person whatever mandate would cover
  it (W606 warns when an unattended run could reach one). Kept items carry
  `sender_identity`. `ActionRecord.actor_identity`, `.always_ask` and
  `ProvenanceRecord.agent_identity` (`world_state_schema.yaml` 1.1.0);
  trust-class weights in `authority_trust_model.yaml` 1.1.0 (§8.3). Binding
  the inputs needs `identity@1` (V106); a literal that is not a list is
  B203, a list of unknown values S303, and a reference resolving to either
  is R402.
- **Membership (§5.8):** `x in y`, as in CEL: an element of a list by `==`,
  or a key of a map (a non-string key is in no map); any other right
  operand is an evaluation error. It is a comparison operator, so it does
  not chain. Static checks: B204 for a right operand of unknown type, B206
  for one that is not a list or map, W610 when it may be null, W611 when
  the left operand can match nothing in a literal list or a map's keys.
- **Missing required inputs (§5.5)** are W615 `MISSING_INPUT`: a step that
  does not bind an input its capability requires. Waits and quorums are
  exempt: the executor runs them itself. The reference catalog now binds
  every required input, and the §12.5 patterns do too.
- **`retry` (§5.2):** `max` must be an integer from 0 to 1000 and `backoff`
  one of `none`, `linear`, `exponential`, or null for `none` (S303); both
  were silently ignored otherwise.

### Changed — gaps found by porting workflows to the candidate (#114)
The issue author ported nine production workflows to the v1.1.0 candidate
and reported five gaps; these close them.
- **Binding keys (§5.5).** An `input_bindings` key the capability's input
  schema does not define is W604, so a mistyped input is visible. The
  ontology gains the optional inputs catalogs were already binding:
  `retrieve.filter` and `retrieve.references`, `state.observations`,
  `plan.context`, `critique.context`, `explain.constraints`.
- **Invoke inputs (§5.12).** A literal `input_bindings.input` is checked
  against the invoked workflow's `inputs`: an undeclared name is S303 and a
  missing required input S304, as the executor refuses both (R402).
- **Principals (§5.15)** are opaque strings compared exactly; the host
  reports the authenticated party that delivered an item, not a sender the
  item claims.
- **Lost liveness is R406 `LIVENESS_LOST` (§5.13, §9.5)**, no longer the
  timeout's R401, so a workflow can re-check a silent source (a recovery
  loop back to the wait itself) and escalate only an expired wait.
  `on_error` and `retry` take R406; lost liveness reported after the
  deadline is still R401. **Migration:** a failure mode that handled lost
  liveness through `on_error: R401` must add R406. A failure mode that
  fires only on R406 where no wait has `liveness` is W609.
- **Per-reviewer independence and full sweeps (§5.16).**
  `quorum.forbidden_inputs` takes a mapping of reviewers to their own
  lists as well as one list for all, so a verifier can see earlier rounds
  that a fresh reviewer must not. Verdicts gain `scope: full | delta`
  (`review_verdict_schema.yaml` 1.1.0; absent means `delta`), and
  `quorum.min_full` requires that many passing full sweeps; the tally
  gains `full_passes`.
- **Standing mandates in unattended runs, and deferral that continues
  (§5.14).** A `standing_mandate` approver is asked even when the run is
  unattended; `when_unattended` applies only when it answers the new
  decision `unavailable` (`world_state_schema.yaml` 1.1.0), and W606 no
  longer fires for it. `defer_to_queue` now defers the step and every later
  step that depends on it (reads its output, may act on or wait on the
  world, or comes after it by an ontology `precedes` edge) and runs the
  steps that only read, reason or record; the run still ends `deferred`, and every terminal action
  lists the run's deferrals. Before, a mandate was never asked unattended
  and a deferral ended the whole run.

### Changed — from the orchestrator fixtures (#114)
Running the issue author's nine workflows as scripted fixtures showed four
gaps on the standard's side (RFC-0003, amendments):
- **Gate `action: end` (§5.6):** ends the run successfully; no later step
  runs; the terminal action records `ended: {step, message}`. In an
  invoked workflow it ends that run only. An after-gate `end` yields to a
  failure mode that fires; an `end` whose expression errors does not fire;
  it is S303 in a `parallel_group`, as is `delay`.
- **Step `delay` (§5.13, `wait@1`):** a positive duration to wait before
  the step's approval, checkpoint and execution; it invalidates earlier
  checkpoints like a wait (W608) and counts as acting after a deferral.
- **Wait filters fail fast (§5.13, §5.15):** a resolved `accept_from` that
  is not a non-empty list of strings, or a null `correlate` value, is
  R402 before the step waits or delegates. Before, the first dropped every
  sender, and the second matched every event lacking the key.
- **`after_deferral: run` (§5.14, `approval@1`):** exempts a step from the
  act-after and ordered-after deferral rules; reading a deferred output
  still defers it.
- **W616 `VERSION_FEATURE_MISMATCH` (§11.5, §9.7):** a workflow that
  targets 1.0 (by `spec_version` or the file header) but uses a feature
  new in 1.1 — `workflow_extensions.requires`, gate `phase` or
  `action: end`, the `in` operator, failure-mode `when` or `on_error` —
  warns once per feature. Before, the
  mismatch was silent.
- **`transform.output` is `object|array`** (ontology 2.1.0): a transform
  can return a list, such as CSV rows as records, without a wrapper
  object. A reference to it needs an annotation (B204), as for any union;
  this breaks a catalog that reads it unannotated.
- **`retrieve` and `search` are soft prerequisites of `ground`** (ontology
  2.1.0, §4.3): a retrieved source or a search result is evidence to
  ground a claim in, alongside observe, detect, predict, attribute and
  explain.
- **W608 through `invoke` (§5.13):** an `invoke` of a catalog workflow
  that can wait counts as a wait, since the run it invokes invalidates the
  caller's checkpoints.
- **Replacing delegations on a loop (§5.13)** is stated for every waiting
  delegate from the loop's target to the step whose failure mode loops,
  even one that finished; the reference executor named only the looping
  step's own. Replacement is per run: a parent loop that runs an `invoke`
  again starts a new child run, which names none of the old run's
  delegations.

### Changed — whole-branch review (#114)
- **Literal bindings are typed (§5.4).** A literal or template bound to a
  typed input is checked against it: a template is a string, a list or
  mapping literal its JSON type (a mapping also fits a `map<string, …>`),
  and an explicit null is null (the host receives it), so
  `threshold: "high"` on a number input is B203. `invoke`'s `input: null`
  still means no inputs. A whole reference keeps its annotation or
  inferred type.
- **Reference codes (§5.3, §5.8.1).** An empty annotation (`${x:}`) is
  B205; a reference that does not parse (`[01]`, `[-1]`, an unclosed `[`)
  is B201 in an expression as in a binding, not V108. B201's description
  covers both.
- **A literal of the wrong JSON type** for `invoke`'s `input` or an
  `identity@1` input is B203 (§5.4), like any other literal binding, not
  S303. **`retry` (§5.2)** does not repeat an R402 the executor raises
  itself before asking the host (a refused `invoke` input).
- **Fields that take a reference** (`correlate`, `approval.shows`,
  `recheck.source`, `quorum.verdicts`, `pinned_to`, `invoke`'s
  `input`) take exactly one `${...}`: a template around one is S303. An
  unquoted typed reference there gets the W612 quoting hint in its S303.
- **W606 through `invoke` (§5.10, §5.14):** a workflow invoked, directly or
  transitively, from one with an unattended trigger runs unattended, so its
  approval steps warn as its caller's would. `x-` vendor entries are never
  run, so they make nothing unattended.
- **Smaller rules made explicit, each S303:** a literal empty
  `accept_from` (§5.15); a `synchronize` wait whose `agents` repeat one
  (§5.13); an `invoke` that names different targets in `workflow_id` and
  `input_bindings.workflow` (§5.12); `retry.max` above 1000 (§5.2); a
  workflow `success` that is not a list of strings or a `description`
  that is not a string (§5.1); a cron that can never fire (§5.10).
- **W615 (§5.5)** is waived only for a wait on `receive` or `synchronize`
  and for a quorum: a waiting `delegate` delegates first, with its inputs,
  and a wait on any other capability is S303 with its inputs still checked.
- **`output_conforms_to` (§5.2)** describes the step's whole output.
- **Replacing a silent delegate (§5.13):** a recovery loop whose target is
  the waiting delegate or an earlier step makes the delegate's next call
  name the delegation it replaces.
- **The §12.5 Recovery Loop pattern** shows its loop target reading the
  injected `${_recovery.failure_evidence}`.
- **Quorum verdict `scope` (§5.16):** a value other than `full` or
  `delta`, which `review_verdict_schema.yaml` rejects, counts as `delta`
  and is noted in `violations`; the schema text says so.
- **Conformance (§10):** the workflows an adopter ported to the candidate
  are a static fixture (revision 1.1e) and fifteen scripted runs
  (`orchestrator_*`); twenty more runs the adopter wrote from the spec
  (`gap*`, standing mandates, verdict scope, liveness and deadlines, the
  principal) are kept as contributed in `tests/conformance/contrib/`. A fixture's expected codes are the exact set it
  must produce, so each fixture isolates what it tests; an absent warning
  list means none. Two runtime fixtures cover a before-gate `skip` and an
  after-gate with a failure mode on the same step.
- **`workflow_catalog.schema.json`** accepts an input `type` that is a list,
  bounds `retry.max` and enumerates `retry.backoff`, matching the
  validator.

### Fixed
- **Authority trust model — decay is now a true half-life.** `conflict_resolution_function.recency_factor`
  is `0.5 ** (age/half_life)`, which returns exactly 0.5 at `age == half_life`. The published
  `exp(-age/half_life)` returned 0.3679 there, treating `half_life` as an exponential time
  constant and decaying 1/ln(2) ≈ 1.44x too fast. `decay_model.half_life` is set to `P10D`,
  the value reproducing the curve the reference implementation actually exhibited; the former
  `P14D` was a mislabelled ~9.7-day half-life. Implementations that read `half_life` and
  applied a correct half-life curve were, in effect, decaying more slowly than the reference.
  (#105)

### Added
- **§8.1 now states the decay semantics normatively.** Time decay MUST be a true
  half-life (factor `0.5` at `age == half_life`), and `decay_model.min_trust` is
  defined as a floor on the *decay factor* — not on the composed §8.2 score and
  not on the static source weight. The floor was previously declared in
  `authority_trust_model.yaml`, cited by compliance artifacts as an implemented
  control, unenforced by the reference implementation, and undefined by the spec.
  (#106)

### Changed
- **§6.2 and §6.3 now name the fields the canonical schemas actually declare.**
  §6.2 described observations with `id` / `raw_payload` / `canonical_payload` /
  `evidence_anchors` — names that appear in no schema file. The canonical event
  in `event_schema.yaml` has always carried all seven fields as `event_id` /
  `raw` / `canonical` / `anchors`, and `transform_mapping_rawlog_to_observation.yaml`
  writes those names. §6.3 likewise placed snapshot identity at the top level
  when `world_state_schema.yaml` keeps it under `meta`. Both tables now match
  the schemas; §6.2 also states explicitly that the canonical-event namespace is
  distinct from the capability-I/O namespace of §4.1, so an event's `anchors`
  is not a capability's `evidence_anchors`. Clarification only — no field
  changed shape. (#107)
- **Three fields the spec marks MUST are now `required` in the schemas.**
  `event.provenance` (§6.2), and `world_state.meta.version_id` and
  `meta.lineage` (§6.3), were declared but optional. Per §11.4 adding a required
  field is breaking for producers that omitted them; no in-repo fixture did.
  (#107)

## v1.0.0 — 2026-01-24

### Specification
- Initial publication candidate
- Capability ontology: 36 atomic capabilities across 9 cognitive layers
- I/O contracts with typed schemas and explicit dependencies
- Workflow DSL spec v2: bindings, conditions, gates, recovery loops, parallel groups
- Canonical world state and event schemas (provenance, uncertainty, retention, lineage)
- Identity taxonomy and identity resolution policy
- Authority trust model (weights, decay, field-specific authority)
- Conformance levels L1–L4 with validation rules

### Validation
- Compiler-grade validator with $ref resolution and type inference
- Consumer input schema checking
- Patch suggestions and optional diff output
- 5 conformance test fixtures
