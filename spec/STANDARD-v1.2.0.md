# Standard: Agent Capability Ontology + Workflow DSL

**Version:** 1.2.0
**Status:** Candidate Standard — accepted by
[RFC-0005](RFC-0005-tool-calling-hosts.md),
[RFC-0006](RFC-0006-host-protocol-approval-and-runs.md),
[RFC-0007](RFC-0007-delegation-catalogs-and-diagnostics.md),
[RFC-0008](RFC-0008-evidence-grounding-and-secrets.md),
[RFC-0009](RFC-0009-checkpoint-rollback-send-memory.md) and
[RFC-0010](RFC-0010-profiles-trust-versioning-and-dialect.md); the reference
validator and executor implement §4, §5 and §9–§11 and claim class EX
(§10.5); the Python SDK adapter and the Standard Agents binding implement
§5.18 and meet §10.4 except the §5.18.10 rows their conformance statements
list as not applied, and claim class SL once those are applied; the
executor and both layers check grounding (§5.20) and apply domain profiles
(§5.21); `grounded_agency` implements §7.1's entity ids and §8's
arithmetic; §7.2 and §7.3 are not implemented
**Date:** 2026-11-15
**Supersedes:** [STANDARD-v1.1.0](STANDARD-v1.1.0.md) (still supported; see §11.5)

---

## 1. Scope

This standard specifies:

1. A canonical **capability ontology** for agent systems
2. A **workflow DSL** for composing capabilities with safety and recovery semantics
3. A **condition expression language** for gates, conditions and failure modes
4. Canonical **world state** and **event** schemas for grounded reasoning
5. **Identity** and **authority trust** policies for reliable data fusion
6. A **diagnostic model** (errors and warnings) for validation and runtime failures
7. A **conformance model** and validation requirements
8. **Versioning** and backward compatibility policy
9. **Orchestration extensions** (triggers, recovery and escalation, waiting,
   approval, delegation, quorum, sender identity) that a workflow opts into
10. **Tool-calling hosts**: the ontology applied to the tool calls a model
    chooses (§5.18)
11. A **host protocol** between an executor and its host, the run operations,
    audit records, and conformance for executors
12. **Domain profiles** that tighten the rules for one domain (§5.21)

Changes from 1.1.0 are listed in [Appendix D](#appendix-d-changes-from-110).

### 1.1 Normative References

- JSON Schema Draft 2020-12
- YAML 1.2
- Semantic Versioning 2.0.0
- RFC 3986, Uniform Resource Identifier (URI): Generic Syntax (§7.1)
- RFC 5545, Internet Calendaring and Scheduling (iCalendar), §3.3.5: local
  times that a clock change repeats or skips (§5.10.2)
- RFC 6901, JavaScript Object Notation (JSON) Pointer (§4.1.2, §6.2, §9.8)
- RFC 7493, The I-JSON Message Format (§5.14)
- RFC 8785, JSON Canonicalization Scheme (JCS) (§5.14)
- ISO 8601, date and time representations (§5.10.1, §6)
- IANA Time Zone Database (§5.10, §6.3)
- Common Expression Language (CEL) — informative for §5.8; ACS expressions
  are a compatible subset

### 1.2 Notation

- **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**: Absolute requirements
- **SHOULD**, **SHOULD NOT**: Recommended but not mandatory
- **MAY**: Optional

---

## 2. Terms

| Term | Definition |
|------|------------|
| **Capability** | An atomic primitive with single purpose, composable with explicit I/O contracts |
| **Workflow** | An ordered, conditional, or parallel composition of capabilities |
| **Catalog** | A YAML document mapping workflow names to workflows |
| **Observation** | Append-only event grounded in evidence anchors |
| **World State** | Derived snapshot from observations and transition rules |
| **Provenance** | Traceability record for claims and transformations |
| **Trust Score** | The weight of a piece of evidence: source weight × confidence × age decay (§8.1) |
| **Binding** | A reference from one step to another step's output |
| **Gate** | A conditional check that can halt or redirect workflow execution |
| **Checkpoint** | A saved state that enables rollback |
| **Grounding** | Anchoring a claim to evidence its producer had (§3.1) |
| **Evidence anchor** | A reference to one piece of evidence: `ref`, `kind` and optional `timestamp`, `excerpt`, `digest` (§6.5) |
| **Inferred** | Said of an output not grounded in evidence that carries `inference_method` and `confidence` (§3.1, §4.1.1) |
| **Evidence store** | Where an implementation keeps evidence records, with a stated durability (§6.6) |
| **Secret** | A value that grants access or proves identity, or that the host classifies as secret (§6.7) |
| **Diagnostic** | An error or warning reported by a validator or executor (§9) |
| **Effective flag** | The safety flag a step is treated as: the stricter of its declaration and the ontology (§5.2.1) |
| **Executor** | What runs a workflow step by step, with no input or output of its own (§5.19) |
| **Host** | What performs the actions an executor asks for and gives it the time (§5.19) |
| **Run** | One execution of a workflow, from its start to its terminal action (§5.19) |
| **Action** | What a run asks its host to do next, or how it ended (§5.19.1) |
| **Audit record** | An action record or a canonical event that says what happened (§6.4) |

Terms of domain profiles, contracts, entities, ordering and tool-calling hosts:

| Term | Definition |
|------|------------|
| **Domain profile** | Rules for one domain that a host, a safety layer or a validator applies to tighten what steps and calls require (§5.21) |
| **Schema dialect** | The JSON Schema subset, and the forms it adds, that capability contracts are written in (§4.1.2) |
| **Entity id** | The identifier of a world-state entity, `<class>:<namespace>/<local_id>` (§7.1) |
| **Runs before** | Step A runs before step B when A comes earlier in the step list and is not in B's parallel group (§4.3) |
| **Tool-calling host** | A runtime in which a model chooses each tool call and its arguments, and no workflow's step list determines the next action (§5.18) |
| **Call** | One invocation of one tool on a tool-calling host |
| **Tool binding** | A record that states which capability a tool performs and which safety flags it declares (§5.18.1) |
| **Safety layer** | Code that decides, before a call's effect, whether the call may run under §5.18: a pre-call hook, a permission callback, or a wrapper around the tool's own code |
| **Layer scope** | The sequence of calls a safety layer orders and keeps records for, such as one session or thread (§5.18.5); in §5.18, *scope* means a layer scope |
| **Execution boundary** | A point where work stops and later resumes, after which earlier checkpoints authorise nothing: for a workflow, the end of a wait or delay (§5.13) and the resumption of a deferred run (§5.14.1), but not the restoring of a saved run (§5.19.4); on a tool-calling host, a point its safety layer names, such as a turn that ends while a person decides (§5.18.6) |

---

## 3. Design Principles

These principles are non-negotiable. An implementation that violates them is non-conformant.

### 3.1 Grounded Claims

Every claim MUST be evidence-backed or explicitly marked as inferred. The
output of a capability is the claim its step or call makes:

- It is **grounded** when its `evidence_anchors` (§4.1.1) holds an evidence
  anchor to evidence its producer had (§6.5). An output that reports an
  action its producer performed is grounded by the action's record.
- It is **marked inferred** when it carries `inference_method` and
  `confidence` (§4.1.1). An output that is not grounded MUST be marked
  inferred.
- An empty `evidence_anchors` grounds nothing.

F505 (`PROVENANCE_MISSING`) reports an output that breaks this section.
Checking is opt-in (§5.20); where no grounding policy applies, this section
is its producer's obligation.

### 3.2 Auditable Transforms
Every transformation MUST be either:
- Deterministic (same input produces same output)
- Documented with explicit loss (what information is discarded)

Redacting a secret (§6.7) is a transform of the second kind: the marker it
leaves documents the loss.

### 3.3 Safety by Construction
- A `checkpoint` MUST run before every `mutate`, `send` and `rollback` (the
  ontology's `requires` edges, V102) and before any step whose effective
  `requires_checkpoint` is true (F501), so a mutation that needs one has a
  restore point (§4.3, §4.4, §5.2.1)
- A plan is not required. Where a workflow has `plan`, it MUST run before
  `execute` and `mutate`; where it has `constrain`, before `execute`,
  `mutate`, `send` and `generate` (`precedes`: ordering only, V102). A
  `constrain` before `execute`, `mutate` and `send` is recommended (W601)
- A workflow cannot weaken a capability's safety flags (§5.2.1)
- A domain profile only tightens flags, checks, evidence, confidence and
  destination rules: applied to a run or a call, it can raise a step's flags
  and add checks, never lower them or remove one (§5.21). Its trust weights
  replace source weights, in either direction (§8.3)
- On a tool-calling host, a safety layer applies the same effective flags,
  `requires` edges, checkpoint rule and approval to each call (§5.18)

### 3.4 Composable Atoms
- Workflows orchestrate; capabilities do one thing
- Each capability has a single responsibility
- Capabilities communicate through typed contracts

### 3.5 Explicit Contracts
- Input and output schemas are first-class
- Type mismatches MUST be detected at validation time
- Schema evolution follows semantic versioning

---

## 4. Capability Ontology

This Standard is published with capability ontology 2.2.0
(`schemas/capability_ontology.yaml`); §11.6 says how the ontology is
versioned.

### 4.1 Capability Definition

A capability MUST define:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (lowercase, hyphens allowed) |
| `layer` | enum | Yes | Classification layer |
| `description` | string | Yes | Human-readable purpose |
| `input_schema` | object | Yes | The inputs a step may bind, in the schema dialect (§4.1.2) |
| `output_schema` | object | Yes | The output a host returns, in the schema dialect (§4.1.2) |
| `risk` | enum | No | `low` (default), `medium`, `high` |
| `mutation` | boolean | No | Whether the capability changes persistent state (default false) |
| `requires_checkpoint` | boolean | No | A checkpoint must precede each use (default false) |
| `requires_approval` | boolean | No | Each use needs approval (default false) |
| `mutation_overridable` | boolean | No | A step may declare `mutation: false` (§4.4) |

Relationships between capabilities are edges (§4.3), listed in the
ontology's `edges` array as `{from, to, type, rationale?}`.

#### 4.1.1 Common Output Fields

Every capability's output contract declares these fields, with the same
meaning in each:

| Field | Type | In the contract | Meaning |
|-------|------|-----------------|---------|
| `evidence_anchors` | array of evidence anchors (§6.5) | Required | What the output is based on (§3.1) |
| `confidence` | number from 0 to 1 | Required where the capability's contract requires it, optional elsewhere | The producer's probability that the output's claim is correct |
| `inference_method` | string | Optional | How an output not grounded in evidence was reached (§3.1) |
| `uncertainty` | `Uncertainty` (`event_schema.yaml#/types/Uncertainty`) | Required for `measure`, optional elsewhere | The uncertainty of the output's principal value |

**`confidence`** is a probability, from 0 to 1, that the output's principal
claim is correct: for `classify`, that its labels are right; for `predict`,
that its prediction holds. A capability's contract MAY say what it is a
probability of more precisely, as `inquire`'s does (that clarification is
needed). It is self-reported: this Standard requires no calibration, and a
host that calibrates the confidences it reports SHOULD document how. It is
not a trust score; §8.1 uses it as one factor of one. This Standard sets no
threshold on it: a workflow sets one in a gate or a condition (§5.6, §5.8),
and a domain profile states one in `minimum_confidence`.

**`inference_method`** says how an output not grounded in evidence was
reached. A producer SHOULD use one of `model_knowledge` (from what the
producer already knew, with no evidence consulted), `deduction`,
`induction`, `abduction`, `analogy`, `statistical` (the estimate of a
statistical or learned model), `simulation`, `assumption` (taken as given
without evidence), or a vendor value: `x-` followed by a lower-case letter
or digit, then lower-case letters, digits, `_`, `.` or `-`. With
`confidence`, it marks the output inferred (§3.1); a grounded output MAY
carry one too. The contracts declare it as a string; under a grounding policy (§5.20), an output that relies on
being marked inferred MUST use a value of this vocabulary.

**`uncertainty`**, when present, is an `Uncertainty` describing the output's
principal value; when an output has both, `uncertainty.confidence` equals
`confidence`. A `measure` output's `uncertainty` keeps the members `lower`
and `upper` of 1.1, the bounds of the value, and MAY carry the members of an
`Uncertainty` beside them; `interval.low` and `interval.high` then equal
`lower` and `upper`.

The ontology's `meta.principles` say the same: every output carries
evidence anchors or is marked inferred, and a capability whose output
contract requires a confidence returns one in every output.

#### 4.1.2 Schema Dialect

A capability's `input_schema` and `output_schema`, and the definitions in the
canonical and supporting schemas (§6.1) that a contract reaches through
`$ref`, are written in the **schema dialect**. A workflow's `inputs`
declarations and the files they and `output_conforms_to` reference (§5.1,
§5.2) SHOULD be written in it too; a validator reads a keyword outside it as
an annotation.

These keywords have their JSON Schema Draft 2020-12 meaning: `type` (one
type name or a list of them), `enum`, `const`, `properties`, `required`,
`additionalProperties` (a boolean or a schema), `items` (one schema),
`minimum`, `maximum`, `minLength`, `maxLength`, `pattern`, `format`,
`minItems`, `maxItems`, `uniqueItems`, `oneOf`, `anyOf`, `allOf`,
`description`, `title`, `default` and `examples`. No other Draft 2020-12
keyword is used. The dialect adds:

| Form | Meaning | Rendering | Code |
|------|---------|-----------|------|
| `type: any` | Every JSON value. It MAY stand only beside `description`, `title`, `default`, `examples`, `nullable` and `x-` keys. For §5.4 it is missing type metadata, and paths below it are open | No `type`, and the annotation `"x-acs-type": "any"`, which keeps it apart from a schema that states no type | B204: a reference to it needs an annotation |
| `type: "a\|b"` | Two or more distinct type names other than `null`, joined by `\|`: the same as `type: [a, b]` | The list `["a", "b"]` | — |
| `$ref: "<path>#<pointer>"`, `$ref: "#<pointer>"` | The schema the JSON Pointer (RFC 6901) names in the file at `<path>`, a path relative to the schema root (the repository root) that does not leave it, or in the same file. The keywords beside `$ref` replace the target's keywords of the same name | The rendering of its target, with the keywords beside it merged | S302: in a workflow's `inputs`, a reference that names nothing |
| `nullable: true` | The value MAY also be `null`. Type inference (§5.4) does not read it | `"null"` added to `type` (to its list, or making a list of a single name; nothing where there is no `type`), and `nullable` dropped | W610 can differ: a reference to the member is nullable in the rendering only |
| keys starting with `x-` | Annotations, never assertions. Keys starting with `x-acs-` are this Standard's (Appendix B) | Kept | — |

A `$ref` is resolved before any other rule reads the schema. A `$ref` that
names nothing, a `$ref` that reaches itself again (a cycle: the dialect has
no recursive types), and a chain of `$ref`s deeper than an implementation's
limit are outside the dialect; an implementation refuses an ontology whose
contract holds one when it loads the ontology.

**Rendering.** The Rendering column renders a schema of the dialect in
Draft 2020-12, keeping every other keyword. A schema and its rendering
accept the same values, but need not give §5.4 the same types.
`schemas/generated/capability_contracts.schema.json` is the rendering of
every contract of the ontology, `$defs` `<capability>.input` and
`<capability>.output`; it is generated, and the ontology stays the source.

### 4.2 Layers

Capabilities are classified into 9 cognitive layers:

| Layer | Purpose | Mutation | Count |
|-------|---------|----------|-------|
| **PERCEIVE** | Acquire information from the world | No | 4 |
| **UNDERSTAND** | Make sense of information | No | 6 |
| **REASON** | Plan and analyze | No | 4 |
| **MODEL** | Represent the world | No | 5 |
| **SYNTHESIZE** | Create content | No | 3 |
| **EXECUTE** | Change the world | Varies | 3 |
| **VERIFY** | Ensure correctness | Varies | 5 |
| **REMEMBER** | Persist state | Varies | 2 |
| **COORDINATE** | Multi-agent and user interaction | Varies | 4 |

### 4.3 Edge Types and Dependency Semantics

The ontology supports 7 edge types:

| Edge Type | Enforcement | Description |
|-----------|-------------|-------------|
| `requires` | MUST | Hard prerequisite |
| `soft_requires` | SHOULD | Recommended prerequisite |
| `enables` | Informational | Capability flow: `from` makes `to` useful afterwards |
| `precedes` | MUST | Temporal ordering when both are present |
| `conflicts_with` | MUST | May not run concurrently (symmetric) |
| `alternative_to` | Informational | Substitutable capabilities (symmetric) |
| `specializes` | Informational | Parent-child inheritance |

A step *runs before* another when it comes earlier in the step list **and
is not in the same `parallel_group`**: the steps of one group are not
ordered relative to each other (§5.2.3), so neither is known to complete
before the other starts.

**Enforcement semantics:**

| Edge | Rule | Diagnostic |
|------|------|------------|
| `requires` | For every `to` step, some `from` step runs before it | V102 per `to` step |
| `precedes` | If the workflow contains both, every `to` step has a `from` step running before it. It never requires `from` to be present. | V102, once per edge, at the first offending `to` |
| `soft_requires` | Every `to` step has at least one of its incoming `soft_requires` sources running before it (any-of per target) | W601 per step |
| `conflicts_with` | The two capabilities never share a `parallel_group`; in sequence they are allowed (a rollback after a mutation is the normal recovery pattern) | F504, once per (group, pair) |
| `enables`, `alternative_to`, `specializes` | None | — |

Validators SHOULD implement these checks in time linear in the number of steps.

A check before a mutation is expressed with `constrain`, which the
ontology orders before `execute`, `mutate`, `send` and `generate`. `verify`
checks results after the fact: `{execute, mutate, send} precedes verify`,
so a `verify` placed before the mutation it would check is V102.

See [EDGE_TYPES.md](EDGE_TYPES.md) for the full edge list and rationale.

### 4.4 Safety-Critical Capabilities

| Capability | Requires | Notes |
|------------|----------|-------|
| `mutate` | `checkpoint` | Cannot mutate without prior checkpoint |
| `send` | `checkpoint` | Cannot send without prior checkpoint |
| `rollback` | `checkpoint` | Must have checkpoint to revert to |
| `verify` | _(none)_ | `alternative_to` constrain; verify checks post-hoc, constrain checks pre-execution |

`mutation_overridable: true` lets a step declare `mutation: false` for a
capability whose writes are append-only (in the reference ontology: `audit`).
It is allowed only on capabilities with `mutation: true`, `risk: low`, and
neither `requires_checkpoint` nor `requires_approval`; an ontology that sets
it elsewhere MUST be rejected when loaded.

#### 4.4.1 Checkpoints and Rollback

<!-- owner: S5; text: S5.md part 2.4 -->

#### 4.4.2 Transmissions

<!-- owner: S5; text: S5.md part 2.5 -->

### 4.5 Memory

<!-- owner: S5; text: S5.md part 2.6 -->

---

## 5. Workflow DSL

### 5.1 Catalog and Workflow Definition

A catalog is a YAML mapping of workflow name to workflow. A top-level key
starting with `x-` is vendor data and is not a workflow. Any other
top-level value that is not a mapping is S303.

A workflow MUST define:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `goal` | string | Yes | Intended outcome |
| `risk` | enum | Yes | Risk level: low, medium, high |
| `steps` | array | Yes | Ordered list of capability invocations |

A workflow MAY define:

| Field | Type | Description |
|-------|------|-------------|
| `inputs` | object | External input declarations (default `{}`) |
| `success` | array of strings | Success criteria |
| `description` | string | Long description |
| `spec_version` | string | Standard version targeted (§11.5) |
| `workflow_extensions` | object | Extension declarations (§5.9) |
| `triggers` | array | How runs start (§5.10) |
| `grounding` | object | Grounding policy (`grounding@1`, §5.20) |
| `domain`, `risk_propagation`, `data_flow` | — | Recognised descriptive fields |
| `profile` | string | The domain profile written for (its `domain` or a path); applies nothing (§5.21) |

A missing required field is S304; `goal`, `risk`, `success` or
`description` of another type is S303. An unrecognised field is W604 and is
otherwise ignored; fields whose name starts with `x-` are vendor extensions
and are never reported (§11.3).

#### 5.1.1 Catalog Manifests and Qualified Names

<!-- owner: S3; text: S3.md part 2.5 -->

### 5.2 Step Definition

Each step MUST define:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `capability` | string | Yes | Capability ID to invoke (missing or not a string: V103) |
| `purpose` | string | Yes | Why this step exists (missing: S304) |
| `store_as` | string | Yes | Output identifier for later reference (missing: S304) |

`store_as` MUST be an identifier (`[A-Za-z_][A-Za-z0-9_-]*`), else S303, and
unique within the workflow, else V104.

Each step MAY define:

| Field | Type | Description |
|-------|------|-------------|
| `input_bindings` | object | References to prior step outputs (§5.3) |
| `condition` | string | Expression (§5.8); the step runs only if it is true |
| `skip_if_false` | boolean | `condition` false skips the step (default true); false fails the run with R403 |
| `gates` | array | Checks that can halt or redirect execution (§5.6) |
| `failure_modes` | array | Failure scenarios with recovery (§5.7) |
| `timeout` | string | Maximum execution time, a duration (§5.10.1) |
| `retry` | object | `{max, backoff}`: up to `max` further attempts after R401, R402 or R406 (not after an R402 the executor raises itself before asking the host, such as an `invoke` input the target refuses or a `delegate` target it refuses (§5.15.2): another attempt would be refused the same way; nor after an accepted delegation whose host did not attest the `read_only` the step relied on (§5.15.2): another attempt would hand the delegate's host another unchecked delegation); `max` an integer from 0 to 1000 and `backoff` one of `none` (also when absent or null), `linear`, `exponential` (else S303). After attempt *n* fails, the next attempt starts once the run's clock (§5.19.3) has passed the time it failed by: nothing for `none`; *n* × 1000 ms for `linear`; 2^min(*n*−1, 32) × 1000 ms for `exponential`; the wait ends no later than the maximum time |
| `parallel_group` | string | Group ID: the steps of one group are not ordered relative to each other (§5.2.3) |
| `join` | string | When the group is complete: `all_complete` (the default and the one value defined, §5.2.3) |
| `mapping_ref` | string | Transform mapping file (missing file: S301) |
| `output_conforms_to` | string | `file#/pointer` the step's whole output must match (S301/S302) |
| `domain` | string | Domain parameter for the capability |
| `workflow_id` | string | For `invoke`: the workflow to run |
| `risk`, `mutation`, `requires_checkpoint`, `requires_approval` | — | Safety flags (§5.2.1) |
| `handler` | boolean | Escalation target only (§5.11) |
| `wait` | object | Wait for an event (§5.13) |
| `approval` | object | How approval is obtained and bound (§5.14) |
| `quorum` | object | Review quorum (§5.16) |

Unrecognised step, gate, failure-mode, recovery and retry fields are W604.

#### 5.2.1 Safety Flags

`risk`, `mutation`, `requires_checkpoint` and `requires_approval` default
to the capability's ontology values. A step's **effective** flags are the
stricter of its declaration and the ontology: booleans are OR-ed, `risk` is
the higher level. A declaration weaker than the ontology has no effect and
is reported as W602 (`SAFETY_FLAG_DOWNGRADE`), with one exception:
`mutation: false` on a `mutation_overridable` capability (§4.4) is honoured.

Validators, executors and safety layers (§5.18) MUST act on effective
flags. A declaration stricter than the ontology (e.g. `requires_approval: true` on
`observe`) is allowed and takes effect: a step whose effective
`requires_checkpoint` is true needs a `checkpoint` step running before it
(§4.3), else F501 — reported as V102 instead where the ontology's
`requires` edge from `checkpoint` already demands it.

Domain profiles applied to a run, or to a safety layer's calls, raise
effective flags further (§5.21): with profiles, a step's effective flags are
those above with the profiles' raises applied, and every rule that reads
effective flags reads those.

#### 5.2.2 Checkpoint Use

A checkpoint authorises one step whose effective `requires_checkpoint` is
true; two such steps never share one. The same rule holds for calls
(§5.18.6).

- **When it is used up.** Once everything that can stop the step before it
  acts has passed (its condition, before-gates, delay and approval),
  immediately before the capability is called. A step that is skipped,
  deferred, refused approval or stopped by a gate uses nothing. A step that
  started uses it whatever its outcome; a `retry` of the step runs under the
  checkpoint the step used.
- **Which one.** The most recently taken of the run's valid checkpoints:
  once the latest is used, an earlier one that is still valid authorises
  the next step.
- **None valid.** When a step that requires a checkpoint is about to act and
  no valid checkpoint exists (each was used up, or a wait or delay ended
  after it), the executor has its host take one and uses it; if the host
  fails, the step fails with F501. The static rule still applies: a
  `checkpoint` step must run before the step (§4.3, §5.2.1). A catalog with
  one `checkpoint` step before two `mutate` steps is therefore valid, and at
  run time a restore point is taken before the second.
- **Validity.** A checkpoint stops authorising anything when a wait or delay
  ends (§5.13) or its run is resumed (§5.14.1), and is never valid again.
  Saving and restoring a run (§5.19.4) changes nothing.
- **Rollback.** A gate action `rollback` (§5.6) or a failure-mode action
  `rollback` (§5.7) restores the latest checkpoint taken in the run, valid
  or not, and uses none up; with none, the run fails with F503, as when the
  host fails the rollback. A `rollback` step is a capability call like any
  other: it restores the checkpoint its `checkpoint_id` input names, valid,
  expired or used, and uses none up; what happens when that checkpoint
  cannot be restored is the capability's output and the host's error
  (§5.19). Validity limits what a checkpoint authorises, not what it
  restores.

These rules state the reference executor's behaviour since 1.1.0 and apply
to workflows of every version.

#### 5.2.3 Parallel Groups

The steps that declare one `parallel_group` form a group. Their order in the
step list does not order them: no member runs before another (§4.3), and an
executor MAY run them one at a time, in any order, or concurrently. An
executor that speaks the host protocol (§5.19) has one action pending at a
time, so it runs the members one after another, in list order.

A group is complete when every member has finished: completed, been skipped
or been deferred (§5.14). A step after the group runs only once it is
complete. Each member's failure is handled by its own failure modes (§5.12).
When a failure's recovery escalates or ends the run, the members that have
not finished are abandoned: a member that has not started does not run, the
result of one that has is discarded, and an action pending for one is
withdrawn. When it loops, the current pass is abandoned and execution
continues from the loop's target (§5.12): the members at or after the
target run again, and an action pending for one is withdrawn.

`join` says when the group is complete. This version defines one value,
`all_complete`, the default: when every member has finished. A `join` with
another value, or on a step that declares no `parallel_group`, is W618
(`UNKNOWN_JOIN`) and is ignored: the group joins as `all_complete`.

A member whose executable fields read a group mate's store (a reference
whose root is the `store_as` of another member) is W619 (`GROUP_MATE_READ`):
that value exists only when the executor has run the mate first, which this
section does not promise. An executor that runs the group in list order
resolves a reference to an earlier mate.

#### 5.2.4 Domain Parameter

<!-- owner: S3; text: S3.md part 2.7 -->

### 5.3 Binding Syntax

Bindings reference prior step outputs and workflow inputs:

```
${root(.field | [index] | [start:end])*}
${root(.field | [index] | [start:end])* : type_annotation}
```

- `root` is an earlier step's `store_as`, else a workflow input, else
  `_recovery` (§5.7) — identifiers `[A-Za-z_][A-Za-z0-9_-]*`.
- Index segments are non-negative integers without leading zeros; slices
  clamp to the array.
- Whitespace is allowed around the `:` of an annotation.

Examples:
```yaml
${observe_out.observation}
${state_out.entities: array<object>}
${search_out.results[0:5]}
```

A YAML plain scalar containing `: ` is read as a mapping, so a typed
reference that is a whole list item MUST be quoted:
`- "${violations_out.matches: array<object>}"`. Validators SHOULD report the
unquoted form as W612 (`MANGLED_REFERENCE`).

**Annotation grammar:** `unknown`, `any`, `null`, `string`, `number`,
`integer`, `boolean`, `object`, `array<T>`, `map<K,V>`, `nullable<T>`,
`union<T,…>`. `integer` is a subtype of `number`. An annotation that names
no type, empty included (`${x:}`), is B205. A reference that does not parse
otherwise (an unclosed `[`, an index such as `[01]` or `[-1]`, a missing
`}`) is B201, in a binding and in an expression alike.

### 5.4 Typed Binding Rules

1. Untyped bindings infer type from the producer's output schema.
2. An annotation MUST be compatible with the schema node's type, else B203.
3. Annotations are REQUIRED where inference is ambiguous (B204):
   - Union schemas (`oneOf`, `anyOf`, type lists)
   - Missing type metadata, including `type: any` (§4.1.2)
   - Unknown array item types
   - `additionalProperties: true` with no constraints

**Paths:** a field segment MUST name a declared property, unless the object
allows undeclared keys (`additionalProperties`) or declares no properties.
There is no implicit projection: a field segment applied to an array is B201
(select an element with `[n]`). A node of type `any` is open below.

### 5.5 Consumer Contract Checking

For each binding, the validator MUST check:
1. The root names a prior `store_as` or an input, else B202
2. The path is valid in the producer's output schema, else B201
3. The inferred or annotated type is compatible with the consumer's input
   schema, else B203 (with a coercion suggestion at L4)

A value that is not exactly one reference is checked by its own type: a
string (a template around references included) is a string, a list an
array, a mapping an object (which also fits a `map<string, …>` input), a
number or boolean its kind, and an explicit null is null, since the host
receives it. An incompatible one is B203. `invoke`'s `input: null` is the
exception: it passes no inputs (§5.12).

An `input_bindings` key that the capability's input schema does not define
is W604, unless the schema sets `additionalProperties: true` or the key
starts with `x-`. The host still receives it, but it is outside the
capability's contract, so it is usually a typo or a parameter that belongs
in another input.

An input the schema requires that the step does not bind is W615: the host
would get no value for it. An `invoke` step's `workflow_id` gives its
`workflow`. A wait on `receive` or `synchronize` (§5.13) and a quorum
(§5.16) are exempt, since the executor runs them itself and no host
receives their inputs. A waiting `delegate` is not: it delegates first,
with its inputs.

### 5.6 Gate Semantics

```yaml
gates:
  - when: ${checkpoint_out.checkpoint_id} == null
    action: stop
    message: "No checkpoint created. Do not mutate."
  - when: ${verify_out.confidence} < 0.5
    phase: after
    action: warn
    message: "Low-confidence verification."
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `when` | string | Yes | Expression (§5.8) |
| `action` | enum | Yes | `stop`, `rollback`, `skip`, `warn`, `end` (else S303) |
| `message` | string | No | Explanation for the action |
| `phase` | enum | No | `before` (default) or `after` the step |

- Order: `condition` → before-gates in declaration order → the step →
  after-gates.
- A before-gate cannot read the step's own output (B202). A gate that
  reads it without declaring `phase` is treated as `after` and reported as
  W603 (`DEPRECATED_FORM`).
- An after-gate cannot `skip` (S303): the step has already run.
- Actions at runtime: `stop` → R403; `skip` → the step is skipped;
  `rollback` → roll back to the latest checkpoint (none: the run ends
  F503), then R403; `warn` → a trace warning. R403 goes to the step's
  failure modes (§5.7) like any step error.
- `end` ends the run successfully: no later step runs, as if the run had
  reached its end, so it completes (or ends `escalated` while a handler
  runs, or `deferred` when a step was deferred, §5.14). A before-gate's
  step does not run. An after-gate keeps the step's output, and the run
  ends once the step's failure modes are checked: one whose `when` holds
  fires instead, so a failed step is not reported a success. The end
  records the step and the gate's `message`, or null (`ended`). Use it
  where nothing more needs doing ("no change", "report only"), which
  `stop`, a failure, cannot express. In an invoked workflow it ends that
  run only: the `invoke` step completes with what that run stored. A step
  in a `parallel_group` cannot have an `end` gate (S303): its group mates
  may run at the same time (§5.2.3) and would be left half done.
- Do not pair a `rollback` gate with a failure mode that rolls back on the
  same condition: the gate rolls back and raises R403, then the failure
  mode's `when` holds too and it rolls back again. To roll back and retry,
  use the failure mode alone (§5.7).

A step is **skippable** when its `condition` can skip it (`skip_if_false`
absent or true) or a before-gate has `action: skip`. A skippable step's
output may be absent for later steps (§5.8.3).

### 5.7 Failure Modes

```yaml
failure_modes:
  - condition: Verdict == FAIL
    when: ${verify_out.passed} == false
    action: rollback
    recovery:
      goto_step: plan_out
      inject_context:
        failure_evidence: ${verify_out.violations}
      max_loops: 3
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `condition` | string | Yes | Prose description of the failure |
| `action` | enum | Yes | `stop`, `rollback`, `request_more_context`, `pause_and_checkpoint`, `escalate` |
| `when` | string | No | Expression (§5.8), evaluated after the step; it can read the step's own output |
| `on_error` | code or list | No | Fires on a code the step failed with: R401, R402, R403, R406, F501, F502, F504, F505 (§5.12) |
| `recovery` | string or object | No | Prose, or a recovery loop (§5.12) |

A failure mode fires when the step raised a matching `on_error` code or its
`when` is true; the first match in declaration order applies. `condition`
is never evaluated: a failure mode with neither `when` nor `on_error` is
documentation only. What a fired failure mode does is §5.12.
`recovery.inject_context` values are references checked like bindings and
may read the step's own output.

### 5.8 Condition Expressions

`condition`, `gates[].when` and `failure_modes[].when` hold expressions.
They MUST be YAML strings (else S303).

#### 5.8.1 Grammar

```ebnf
expr      = or_expr ;
or_expr   = and_expr { "||" and_expr } ;
and_expr  = cmp_expr { "&&" cmp_expr } ;
cmp_expr  = unary [ cmp_op unary ] ;            (* non-associative *)
cmp_op    = "==" | "!=" | "<=" | ">=" | "<" | ">" | "in" ;
unary     = "!" unary | primary ;
primary   = reference | literal | "(" expr ")" ;
literal   = "null" | "true" | "false" | number | string | list | map ;
list      = "[" [ literal { "," literal } ] "]" ;
map       = "{" [ string ":" literal { "," string ":" literal } ] "}" ;
number    = ["-"] int [ "." digits ] [ ("e"|"E") ["+"|"-"] digits ] ;
string    = '"' { char | escape } '"' ;   (* \" \\ \b \f \n \r \t \uXXXX, no surrogates *)
```

`reference` is the binding syntax of §5.3. Limits: 4096 UTF-8 bytes,
nesting depth 32, integer literals of magnitude at most 2^53, finite
numbers, no duplicate map keys. A violation of the grammar or a limit is
V108; a malformed reference is B201 and a malformed annotation B205, as in a
binding (§5.3).

#### 5.8.2 Evaluation

- Values are JSON values. `==` and `!=` are total, deep and structural;
  numbers compare by binary64 value; values of different kinds are unequal.
- Ordering (`<`, `<=`, `>`, `>=`) is defined for number/number,
  string/string (by code point) and boolean/boolean (`false < true`); any
  other pair is an evaluation error.
- `x in y` is membership, as in CEL: when `y` is a list, whether some
  element equals `x` (by `==` above); when `y` is a map, whether `x` is one
  of its keys (a non-string `x` is no map's key, so the result is `false`).
  Any other `y`, null included, is an evaluation error. Like the other
  comparison operators it does not chain: `x in y == true` is V108; write
  `(x in y) == true`, and `!(x in y)` for "not in".
- `!`, `&&`, `||` require booleans. `&&` and `||` absorb errors as CEL does:
  a determining operand (`false` for `&&`, `true` for `||`) decides the
  result even if the other operand is an error.
- The result MUST be a boolean.
- An absent path, an out-of-range index, or the output of a skipped step is
  `null`.

An evaluation error is R405 (`EXPRESSION_ERROR`) and is recorded in the
trace. Its effect is fail-safe by site: a **gate** whose `when` errors
fires, except an `end` gate, which does not (firing would report the run a
success); a **condition** that errors is false; a **failure-mode** `when`
that errors does not fire.

**CEL compatibility.** Every valid ACS expression, with each reference
replaced by an opaque variable bound to the referenced value, MUST be a
valid CEL expression, and wherever CEL evaluates it to a value that value
MUST equal the ACS result. The conformance suite checks this against
cel-go (§10.3).

#### 5.8.3 Static Checks

| Check | Code |
|-------|------|
| Syntax or limit violation | V108 |
| Malformed annotation | B205 |
| Malformed reference | B201 |
| Unknown root / bad path | B202 / B201 |
| Annotation incompatible with the schema | B203 |
| Ordering, logic or `in` on a value of unknown type with no annotation (for `in`, the right operand) | B204 |
| Operator applied to kinds it does not accept (for `in`, a right operand that is not a list or map); non-boolean result | B206 |
| An ordering operand, or the right operand of `in`, may be null (optional field, skippable producer) | W610 |
| Equality between kinds that can never be equal; `in` whose left operand matches nothing on the right (a literal list's members, or a map's keys, which are strings) | W611 |

After a B202 or B201 no further diagnostic is reported for that operand.

**Null narrowing.** After `${x} != null` in an `&&` chain, or `${x} == null`
in an `||` chain, later operands treat that reference as present, and with
it every reference it is a prefix of: `${x}` present makes `${x.f}` non-null
when `f` is required. Optional segments below stay nullable, and below a
node of unknown type every segment may be null unless that exact prefix was
narrowed.

### 5.9 Workflow Extensions

```yaml
workflow_extensions:
  supports_gates: true            # advisory, as in 1.0
  requires: [triggers@1, recovery@1]
```

`requires` lists the extensions (`name@major`) a workflow depends on. A
consumer that does not implement a listed extension MUST reject the
workflow rather than run it with the extension's fields ignored. An unknown
name or unsupported major is V106 (`UNSUPPORTED_EXTENSION`); a `requires`
that is not a list of strings, or lists an extension twice, is S303.

An extension's fields are **must-understand**: a workflow MUST declare the
extension to use them, else V106 at the field. This is what lets an older
consumer refuse a workflow instead of running it without, say, its
waiting or approval semantics.

| Extension | Fields it governs |
|-----------|-------------------|
| `triggers@1` | workflow `triggers` (§5.10) |
| `recovery@1` | step `handler`; recovery `on_exhausted`; failure-mode `action: escalate` (§5.11, §5.12) |
| `wait@1` | step `wait` and `delay` (§5.13) |
| `approval@1` | step `approval` and `after_deferral` (§5.14) |
| `delegation@1` | bindings of `delegate.fresh_context`, `.model_family`, `.role`, `.read_only` and `receive`/`synchronize`/`delegate` `accept_from` (§5.15) |
| `quorum@1` | step `quorum` (§5.16) |
| `identity@1` | bindings of `receive`/`synchronize`/`delegate` `sender_check`, `accept_trust_classes`, `always_ask_trust_classes`; approver identities on approval decisions; in a workflow that targets 1.2, `approval.approver` `sender_check` and `accept_trust_classes` (§5.14, §5.17) |
| `grounding@1` | workflow `grounding`; the check of host outputs (§5.20) |

`failure_modes[].when` and `.on_error` are part of base 1.1, not an
extension: a consumer that ignores them only loses an optional trigger.

A validator MUST NOT accept a declaration of an extension it does not
check: listing one is V106, as for an unknown extension. *(The reference
validator implements all of them.)*

### 5.10 Triggers

```yaml
triggers:
  - kind: schedule
    schedule: {cron: "0 6 * * MON-FRI", timezone: Europe/Lisbon, overlap: skip}
  - kind: event
    event: {event_type: deploy.finished, source_kind: agent, delivers_to: deploy_event}
```

| Field | Description |
|-------|-------------|
| `kind` | `schedule`, `event`, `manual`, `invoke` |
| `schedule` | Required iff `kind: schedule`: exactly one of `cron` (5 fields) or `every` (a duration); `timezone` (IANA name, default `UTC`); `overlap`: `skip` (default), `buffer_one`, `allow_all` |
| `event` | Required iff `kind: event`: `event_type` and `delivers_to` (required; an input whose `ref` ends `event_schema.yaml#/event`, else V107), `source_kind` (an `event_schema` source kind; 1.1 adds `agent`) |
| `attendance` | `attended` or `unattended`: the attendance of the runs the trigger starts (§5.10.2); it has no effect on an `invoke` trigger, since a run an `invoke` step starts always has its invoker's. Default: `manual` → attended, `invoke` → the invoker's, `schedule`/`event` → unattended |

**Cron:** minute 0–59, hour 0–23, day-of-month 1–31, month 1–12 or JAN–DEC,
day-of-week 0–7 or SUN–SAT (0 and 7 are Sunday); `*`, lists, ranges and
`/` steps. When both day fields are restricted, a day matches either (Vixie
semantics). `CRON_TZ=`/`TZ=` prefixes are not allowed; use `timezone`.

A `triggers` that is not a list, a trigger without a valid `kind`, a
`schedule` or `event` that is missing for its kind or present for another
kind, a malformed cron or one that can never fire (`0 0 31 2 *`), a
malformed duration or time zone, and an unknown `overlap` or
`attendance` are S303 or S304 (missing). Unknown trigger fields are W604.

Who evaluates triggers, and when a schedule fires, is §5.10.2.

An `invoke` step whose target declares triggers but none of kind `invoke`
is V107. A step whose effective `requires_approval` is true, in a workflow
with an unattended trigger, with no `approval.when_unattended` and no
`standing_mandate` approver is W606: an unattended run fails there (F502).
(With a mandate and no `when_unattended`, an `unavailable` answer still
fails it, and so does an item from an always-ask trust class, §5.17.)

#### 5.10.1 Durations

A duration is `<digits>(ms|s|m|h|d)` or an ISO-8601 day-time duration
`P[nD][T[nH][nM][n[.n]S]]` with at least one component, a `T` followed by at
least one time component, and a fraction (up to 9 digits) on seconds only.
Years, calendar months and weeks are not allowed: their length varies. An
invalid duration in an extension field is S303; an invalid legacy step
`timeout` is W614 (1.0 allowed any string, so it stays accepted but cannot
be enforced).

#### 5.10.2 Evaluating Triggers

The host evaluates triggers (§5.19); the executor neither reads nor
evaluates them. A host that starts runs of a workflow from its triggers
MUST:

- start each run with the trigger's attendance: its `attendance`, else the
  default of its kind (§5.10). A run that an `invoke` step starts has its
  invoker's attendance, whatever its `invoke` trigger declares; the
  executor applies that itself;
- for an `event` trigger, start one run for each event it accepts, with the
  event (a canonical event, §6.2) as the input that `delivers_to` names,
  and at most one run per `event_id` for the trigger: an event delivered
  again starts no other run. The host accepts an event whose `event_type`
  equals the trigger's, whose `source.kind` equals the trigger's
  `source_kind` when it names one, and whose sender its sender policy
  admits: where the workflow declares `identity@1`, a sender it has
  authenticated as §5.17 says;
- for a `schedule` trigger, start runs at its fire times as its `overlap`
  allows (below).

A host MAY drop an event its sender policy does not admit, and SHOULD keep
an audit record of the drop (§6.4). A host MAY also start a run by other
means, such as a test or an operator's request; it then gives the run's
attendance itself.

**Fire times.** A `cron` schedule fires at each local time of its
`timezone` whose minute, hour, day of month, month and day of week match
(§5.10), at second 0. A local time maps to an instant as RFC 5545 §3.3.5
says: a local time that occurs twice, because clocks were set back, is its
first occurrence; one that does not occur, because clocks were set forward,
is read with the UTC offset in effect before the change. Local times that map
to the same instant fire once. An `every` schedule fires at each instant,
counted in whole milliseconds from 1970-01-01T00:00:00Z, that is a multiple
of its interval, the interval rounded up to a whole millisecond; its
`timezone` does not change its fire times.

**Overlap.** A run that a trigger started is *in progress* from its start
until it ends (a run that ended `deferred` and is resumed, §5.14.1, is in
progress again until it ends again). At a fire time when a run this trigger
started is in progress:

- `skip` (default): no run starts for that fire time;
- `buffer_one`: a run starts as soon as no run this trigger started is in
  progress; a fire time while one run is already waiting adds no other;
- `allow_all`: a run starts at the fire time, beside those in progress.

When no run this trigger started is in progress, a fire time starts a run.
Fire times that pass while the host is not evaluating the trigger (it was
stopped) count, together, as one fire time at the moment it resumes.

The trigger vectors of §10.3 fix fire times, attendance, event acceptance
and overlap decisions for representative cases, clock changes, resumed runs
and redelivered events included.

### 5.11 Handler Steps

`handler: true` (a boolean, else S303) marks an `invoke` step (else S303,
and the step stays in the normal flow) that runs only as an escalation
target: normal flow skips it. Running a handler ends the run with outcome
`escalated`; the code that caused the escalation (or R404) is still
recorded. Because it ends the run, a handler's own failure modes cannot
loop or escalate (a `goto_step` or `on_exhausted` there is V107).

Because a handler runs after the step that escalated to it, it is checked
in that step's scope: it sees the stores of the steps up to and including
its earliest targeting step, but the targeting step's own output, and that
of steps in the targeting step's `parallel_group`, may be absent (the step
may have failed before producing it, and its group mates may not have
finished). A handler's `requires` edges and effective `requires_checkpoint`
(§5.2.1) are checked against the steps that run before its earliest
targeting step; it takes no part in the other ontology edges (§4.3), and no
other step sees its output. A handler no escalation targets is W613.
Duplicate `store_as` names (V104) are judged in list order, wherever a
handler is listed.

### 5.12 Recovery and Escalation

A failure mode fires when the step raised a code listed in `on_error` (one
code or a list: R401, R402, R403, R406, F501, F502, F504, F505; anything else is S303 —
an expression error, R405, is fail-safe at its site and never fails a step)
or its
`when` is true after the step. A structured recovery whose failure mode has
neither can never fire and is W609, as is a failure mode that fires only on
R406 (without `when`) on a step that has no wait with `liveness`.

`recovery` is a description (a string, for people) or a recovery object;
anything else is S303. A recovery object has `goto_step`, `inject_context`
(a mapping of keys to references, else S303), `max_loops` (integer from 1
to 1000, default 1, else S303) and `on_exhausted: {goto_step}`. `max_loops` and
`on_exhausted` need a `goto_step` loop (S304). `on_error` is checked
whether or not the failure mode's action is allowed.

- `goto_step` names a `store_as`. A capability id held by exactly one
  non-handler step is accepted as a legacy form (W603). Anything else —
  including a capability several steps use — is V107.
- A loop (any action but `escalate`) goes back to the current step or an
  earlier one in the normal flow; a later step or a handler is V107.
- With `action: escalate`, `recovery.goto_step` is required (S304) and —
  like `on_exhausted.goto_step` in any case — MUST name a handler step
  (§5.11), else V107. An escalation runs its handler once and ends the run,
  so `max_loops`, `on_exhausted` and `inject_context` do not apply to it
  (S303); the handler binds what it needs from the failed step's output.
- Injected context is readable as `${_recovery.<key>}` from the loop target
  onward. It may be absent (no loop has run yet) and is untyped: guard it
  with `!= null` and annotate it where a type matters. `_recovery` is
  reserved: a `store_as` or input with that name is S303.
- `invoke` steps name their target with `workflow_id` (or a literal
  `input_bindings.workflow`); a step that sets both to different values is
  S303, since `workflow_id` would win unseen. A target that is not in the catalog is W607
  (it cannot be checked); invoke cycles among catalog workflows, including a
  workflow invoking itself, are V105. The step passes the target's inputs
  as `input_bindings.input`: a mapping, or a `${...}` reference whose value
  is one. Absent or null, it passes no inputs; any other value (a list, or
  a string that is not exactly one reference) is B203 against `input`'s
  object type (§5.4). When the target is in the catalog and the input is a
  literal mapping, a
  name the target does not declare is S303 (with no `x-` exemption: these
  are the target's inputs, not fields of the step) and a required input it
  does not give is S304. The executor refuses both when the step runs
  (R402), so a reference is checked then.

**At runtime.** Failure modes are checked after the step and its
after-gates, or after the step failed. The first that fires (§5.7) runs its
action, then its recovery:

| `action` | Effect before recovery |
|----------|------------------------|
| `stop`, `request_more_context` | None; the name tells people the intent |
| `rollback` | Roll back to the latest checkpoint; with none, or if the host fails it, the run ends F503 |
| `pause_and_checkpoint` | Take a new checkpoint; if the host fails it, the run ends F501 |
| `escalate` | Run the handler `recovery.goto_step` (§5.11); the run ends `escalated` with the cause recorded |

| Recovery | Outcome |
|----------|---------|
| `goto_step` loop, fewer than `max_loops` loops taken | Back to the target, with `inject_context` |
| Loops exhausted | `on_exhausted` handler, cause R404; without one the run ends R404 |
| No loop (prose or absent `recovery`) | The run ends with the step's code; a failure mode fired by `when` on a step that did not fail ends it R402 ("failure mode N fired") |

Loops are counted per failure mode of a step, and a count is never reset
during the workflow's run. When no failure mode fires, a failed step ends
the run with its code, and a step that did not fail goes on to the next.

### 5.13 Waiting for Events

```yaml
- capability: receive
  store_as: approval_event
  timeout: 2h
  wait:
    event_type: approval.granted
    source_kind: human
    correlate: {request_id: "${request_out.id}"}
    liveness: {mode: probe, interval: 10m, failure_threshold: 3}
```

| Field | Description |
|-------|-------------|
| `event_type` | Required (S304): the event type to wait for |
| `source_kind` | Only events from this kind of source match: an `event_schema.yaml` `source.kind` (else S303) |
| `correlate` | A mapping of event keys to references (each a `${...}` reference, else S303); the event's values must equal theirs |
| `liveness` | `mode` (`push`: the source sends heartbeats; `probe`: the host polls it (§5.19.3)) and `interval` (a duration longer than zero), both required (S304); `failure_threshold` (integer ≥ 1, default 3) |

A `correlate` value that resolves to null when the step runs fails it
(R402), before a waiting `delegate` delegates: an event that lacks the key
reads as null too, so the wait would accept every such event.

`wait` is allowed only on `receive`, on `delegate`, or on `synchronize`
whose literal `agents` list has at least two entries, all distinct (else S303). The step MUST declare a
`timeout` (S304) that parses as a duration (S303; the W614 leniency for
legacy timeouts does not apply to a wait, which must end). Liveness MUST
be able to fail before the timeout: `interval × failure_threshold` less than
the timeout, else S303. The matching event is delivered in the step's
output (`data`, under the capability's output contract); a lapse raises
R401. Lost liveness (`failure_threshold` missed heartbeats or failed probes)
raises R406 (`LIVENESS_LOST`), so failure modes can tell a silent source
from an expired wait; lost liveness reported after the deadline is R401,
since the wait had already lapsed.

The host watches liveness and reports a loss (§5.19.3); a result or event
that arrives at the deadline is in time, one after it is late.

To re-check a silent source, loop back
to the wait itself (`goto_step` naming its own `store_as`, §5.12) with a
bounded `max_loops`, and escalate on R401 or `on_exhausted`. A wait run
again by a loop or a `retry` starts a new `timeout`. Loops are counted per
failure mode (§5.12), so the wait's own failure modes let it last up to
`timeout` × (`retry.max` + 1) × (1 + Σ `max_loops`), the sum over its
failure modes that loop; a later step's loop back past the wait runs it
again too. On a waiting `delegate`, one `timeout` bounds both phases.

For a wait stored as `result_out` and a handler
stored as `page_out`:

```yaml
failure_modes:
  - condition: The worker stopped sending heartbeats.
    on_error: R406
    action: request_more_context
    recovery: {goto_step: result_out, max_loops: 1, on_exhausted: {goto_step: page_out}}
  - condition: The worker did not finish in time.
    on_error: R401
    action: escalate
    recovery: {goto_step: page_out}
```

A `delegate` step that waits first delegates (an ordinary capability call),
then waits for that delegate's result. The delegation MUST return a string
`task_id` (else R402), and the wait's `correlate` gains it, so only that
delegation's result matches; the author may not correlate on `task_id`
(S303). One `timeout` bounds both phases. A waiting delegate may bind
`accept_from` (§5.15) and, with `identity@1`, the sender inputs of §5.17,
which apply to its result; on a delegate that does not wait they are S303.
The step's output is the delegation's output with the matching event as
`result`. A delegation the host did not accept (`accepted` not `true`) is
R402. A `retry` of the step delegates again, and the new capability call
names the delegation it replaces (`replaces`, its `task_id`) so the host
can cancel it; a delegate that went silent (R406) or ran out of time (R401)
is replaced, and only that one: give each reviewer of a quorum (§5.16) its
own waiting `delegate` step to replace a hung reviewer without asking the
others again. A retry does not ask for approval again, as for any step. A
recovery loop also replaces: every waiting delegate from the loop's target
to the step whose failure mode loops (a quorum's, say) runs again, and
when it next delegates, its call names the delegation it replaces, even
one that finished. Replacement is per run: a loop in a calling workflow
that runs an `invoke` again starts a new run of the invoked workflow,
whose delegations name none of the earlier run's; the host ends those
with the run they belong to. For W608, a
waiting delegate acts (delegates) before its own wait.

A step that requires a checkpoint (`mutate`, `send`, or a raised
`requires_checkpoint`) whose latest checkpoint runs before a `wait` is
W608: a wait can last hours and the run may resume elsewhere, so a
checkpoint taken before it no longer authorises the step. Take a new
checkpoint after the wait; otherwise the executor has one taken when the
step acts (§5.2.2). "Runs before" is as in §4.3: a wait in the
checkpoint's parallel group counts (the checkpoint may finish first), one
in the step's own group does not. A step that waits itself acts after its
wait, so any earlier checkpoint is stale for it; a handler (§5.11) is
judged at its earliest targeting step, including that step's own wait. An
`invoke` of a catalog workflow that can wait (any of its steps, handlers
included, waits or delays, or invokes one that can) counts as a wait: the
run it invokes shares the caller's checkpoints, so its waits invalidate
them too. This is conservative: a checkpoint the invoked workflow takes
after its last wait would cover the caller's next step.

**Delays.** A step may declare `delay`, a duration longer than zero (else
S303; `wait@1`, else V106): after its condition and before-gates pass, the
executor waits that long, then the step goes on to its approval,
checkpoint and execution. Use it to sample something twice, a while
apart, without a fake event to wait on. A delay is a wait on time: when
it ends, earlier checkpoints no longer authorise anything (W608 applies as
to a `wait`, with the step acting after its own delay), and after a
deferral the step counts as acting on the world (§5.14). A `retry` of the
step does not delay again; a recovery loop that runs the step again does.
A step in a `parallel_group` cannot delay (S303): whether its group mates
wait would be unclear.

#### 5.13.1 Answers to an Inquiry

<!-- owner: S3; text: S3.md part 2.11 -->

### 5.14 Approval

```yaml
approval:
  approver: {kind: human, role: release-manager, min_approvers: 2}
  mode: out_of_band
  shows: ["${plan_out.steps}"]
  binds_to: digest
  recheck: {source: "${plan_out}", compare: digest, on_change: reask}
  expires: 24h
  when_unattended: defer_to_queue
```

| Field | Description |
|-------|-------------|
| `approver` | Required (S304). `kind` (required): `human` or `standing_mandate`; `role`; `min_approvers` (integer ≥ 1, default 1); `mandate_ref`, required for and only for a standing mandate (S304 / S303); in a workflow that targets 1.2, with `identity@1`, `sender_check` and `accept_trust_classes` (§5.17) |
| `mode` | Where the approver is asked: `in_session` (default) or `out_of_band` (see **Modes**) |
| `shows` | References whose values the approvers see (each a `${...}` reference, else S303); absent, the step's resolved inputs (see **Shown values and digest**) |
| `binds_to` | `digest` (default): the decision binds to the shown values |
| `recheck` | `source` (required, a `${...}` reference re-read before acting, else S303), `compare`: `version` or `digest` (default), `on_change`: `reask` (default), `replan` or `stop` |
| `expires` | How long after the request a decision may arrive: a duration longer than zero; absent, no limit |
| `when_unattended` | `fail` (default), `skip` or `defer_to_queue` |

`approval` is allowed only where the effective `requires_approval` is true
(S303); other values above are S303 when malformed, and unknown fields W604.

**The request.** A step whose effective `requires_approval` is true asks for
approval once its inputs are resolved (after its condition, its gates and
any delay, §5.13) and before it uses a checkpoint. The executor puts a
request to the host (`RequestApproval`, §5.19.1) that names the approver (the
step's `approver` as declared), the mode, the shown values, their digest and,
when `expires` is set, `expires_at`: the time of the request plus `expires`.

A step that requires approval and has no `approval` field, in a workflow that
declares `approval@1` or not, is asked as if it declared
`approval: {approver: {kind: human}}`: a person (one approver, no role), in
session, shown its resolved inputs, with no expiry and no recheck, and with
`when_unattended: fail` (W606, F502). A member that an `approval` field leaves
out takes the default the table gives. Three steps are asked of a person even
when their approver is a standing mandate: a step marked always-ask (§5.17),
a step an applied domain profile requires a person for (§5.21), and a queued
step that an attended resumption re-enters (§5.14.1).

**Modes.** The mode tells the host where to ask:

- `in_session`: the party attending the run is asked, through the session
  the run is attended in (such as the host's own permission prompt or the
  conversation), and answers while the run waits in that session.
- `out_of_band`: the approvers are asked through a channel separate from the
  run's session (such as a ticket, a message to an approver group or a review
  queue). They need not attend the run, and the decision may arrive after the
  session that asked has ended; a host that asks so keeps the run's state
  while it waits (§5.19.4).

The mode changes neither the shown values, nor the digest, nor which
decisions are valid. A host that cannot ask in the declared mode SHOULD
answer `unavailable` rather than ask elsewhere. A `human` approver is not
asked in an unattended run, in either mode (see **Attendance**): to have an
action of an unattended run approved out of band, declare
`when_unattended: defer_to_queue` and resume the run once its approvers can
be asked (§5.14.1).

**Shown values and digest.** The shown values are a JSON array:

1. With `shows`: one element per reference, in order, each the value the
   reference resolves to when the request is made; a reference that resolves
   to nothing gives `null`. An array value is one element: it is not spliced
   into the array.
2. Without `shows`: one element, the step's resolved inputs: its
   `input_bindings` with every reference resolved, the value its capability
   is invoked with (`{}` when the step binds none).
3. Asked again because a recheck saw its source change (`on_change: reask`):
   the array of item 1 or 2, then one more element,
   `{"recheck": {"previous": P, "current": C}}`, where `P` is the value of the
   source that the earlier decision was bound to and `C` the value the recheck
   read.

The shown values MUST be I-JSON (RFC 7493): no member name appears twice in
one object, and every **integer**, a number written without a fraction or an
exponent, has a magnitude of at most 2^53. An executor refuses an integer
beyond that: a step whose resolved inputs hold one fails with R402, and a
response that carries one is malformed and changes nothing (§5.19.1). A host
(or an executor) that reads values from JSON text refuses a value with a
member name twice in one object, or an integer too long for its parser,
rather than keep one of the members or read the integer as a binary64
value: once parsed, the value no longer shows either. Every other number is
a finite binary64 value, written as RFC 8785 writes it, so `1e+21` (the
`numbers` vector of §10.3) is valid although its value exceeds 2^53. (RFC
7493 §2.2 recommends integers of magnitude at most 2^53 − 1; 2^53 is also
exactly representable in binary64, and 1.1 executors accept it.)

The **digest** is the SHA-256 of the UTF-8 encoding of the array's canonical
JSON (RFC 8785), written as 64 lowercase hexadecimal digits. The request
carries it and a decision repeats it; the two are compared without regard to
the case of the hexadecimal letters. The digest vectors of §10.3 fix the
canonical text and the digest for representative values.

**Decisions.** A decision is `approved`, `rejected`, or `unavailable`: no one
could decide (no standing mandate covers the action). An `approved` decision
is valid only if:

- its digest matches the request's;
- at least `min_approvers` distinct approvers agree: the distinct strings of
  its `approvers` or, with `identity@1` and attested approver identities, the
  distinct principals whose identities meet the request (§5.17);
- it arrives no later than the request's `expires_at`, where there is one;
- its `decision_id` has not been used before in the run.

A mandate's approval names the approvers it stands for, and `min_approvers`
counts them as for people. Every decision is single-use; an `unavailable` one
records no approvers. A `rejected` decision, and an `approved` one that is
not valid, refuse the step (F502) with a `rejected` record (`expired` when
the decision came too late). A request with no decision by its `expires_at`
lapses: an `expired` record, and F502.

**Attendance.** A `standing_mandate` approver needs no one present, so it is
asked in an unattended run too (except for a step that uses an always-ask
item, §5.17); `when_unattended` applies only when it answers `unavailable`. A
`human` approver is not asked in an unattended run, whatever the mode, and
`when_unattended` applies at once. In an attended run, `unavailable` is a
refusal (F502). The plans:

- `fail` (default) → F502.
- `skip` → the step is skipped.
- `defer_to_queue` → a `planned` action record, and the step is
  **deferred**: it does not run now.

Once a step of a workflow is deferred, each later step of that workflow is
deferred too if it depends on a deferred step:

1. it reads a deferred step's store (a reference in any executable field,
   i.e. not `purpose` or a failure mode's prose, or a quorum reviewer);
2. it may act on, or wait on, the world: its effective
   `requires_checkpoint` or `requires_approval` is true, it waits or
   delays (§5.13), or it is an `invoke`, `delegate`, `synchronize` or
   `rollback`;
3. ontology `precedes` edges, followed transitively, order its capability
   after a deferred step's (as `verify` after `mutate`), including a
   capability that a nested run deferred.

A handler (§5.11) is exempt from rules 2 and 3: it is the escalation path,
and deferring it would leave a failure unhandled. So is a step that
declares `after_deferral: run` (`approval@1`, else V106; the other value,
`defer`, is the default; anything else is S303): its author states that it
does not depend on what was deferred, such as an escalation to a person
that must happen whether or not a reminder went out. Rule 1 still
applies to both: a step that reads a deferred store is deferred, since
the value it reads does not exist. Declare it only where running ahead of
a deferred action is safe; rule 2 exists because a step that reads
nothing from a deferred "drain node" may still reboot an undrained node.

A step is checked before its condition, so it waits rather than running
on a missing value or an unchanged world; a deferred dependent is not
asked for approval and does not follow its own `when_unattended`. Other
steps, those that read, reason or record (`retrieve`, `observe`, `plan`,
`audit`, `persist`, `checkpoint`, …) and depend on nothing deferred, still
run: they **run ahead** of the deferred steps, and a resumption runs one
again when a step it runs again reads it (§5.14.1). A deferred step that
requires approval gets its own `planned` record. A nested run that ends
`deferred` defers its `invoke` step; the invocation itself ran, so its
record (if any) is `executed`, and the nested run's records are the queued
actions. An invoke step that runs its workflow again (a retry) starts it
afresh, and, outside a resumption, a recovery loop whose target is a
deferred step, or one before it, runs the step again; either way the
records of the earlier deferrals become `rejected` ("superseded"), so a
queue never holds the same action twice. During a resumption, a loop runs
again only the steps from its target to the one that looped, and supersedes
as §5.14.1 item 7 says.

A run with deferred steps ends `deferred`, unless it fails, escalates or
needs a replan, which take precedence. Whatever the outcome, the terminal
action lists every deferral (`deferred`: frame, step, `store_as`, reason
and the `action_id` of its record), so the host knows which queued actions
belong to the run and what still waits for them. A handler that is
deferred (or whose nested run deferred steps) has not finished handling,
so that run ends `deferred`, keeping the escalation's cause; a nested run
that ends so is, for its invoke step, an escalated nested run (R402).

A queued action is put to its approvers, and carried out, by resuming its
run (§5.14.1). The queued actions of a run that did not end `deferred` are
never carried out (§5.14.1). A new run of the workflow is another run: it
neither carries out nor closes an earlier run's queued actions.

The decision is recorded on the action record (`world_state_schema.yaml`
1.2.0: `approval` with the digest, decision, the counted approvers and, with
`identity@1`, their identities; status `rejected` or `expired`, with a
`reason`, when it was refused, invalid or lapsed, or when an unattended run
did not ask; `planned`, with the reason, when it was deferred). A resumed run
updates the record of a queued action in place (§5.14.1).

#### 5.14.1 Resuming a Deferred Run

A run that ended with outcome `deferred` can be **resumed**: it continues, as
the same run, with the steps it deferred. This is how its queued actions are
put to their approvers and carried out. An executor that implements
`approval@1` MUST support resumption. The host resumes a run from its state
at the end (the `resume` operation, §5.19.2), names the run's attendance from then on (attended unless
it says otherwise), and may name a new actor (§5.17). A host MUST NOT resume
the same saved state twice: each resumption could carry out the same queued
action.

**Runs that did not end deferred.** A run that failed, escalated, needed a
replan or was cancelled (§5.19.5) cannot be resumed, and the queued actions it
lists are never carried out. Their records stay `planned` in its terminal
action (a cancelled run's become `cancelled`): a host treats them as
abandoned, closes whatever queue entries it keeps for them, and may start a
new run of the workflow, which is another run (§5.14).

When a run resumes:

1. **What it keeps.** Its stores, inputs, injected recovery context, loop
   counts, used decision ids, action records and trace are kept, and the
   trace records the resumption. No checkpoint taken before the resumption
   authorises a step after it, as after a wait (§5.13): a resumed step that
   requires a checkpoint gets a new one.
2. **What runs again.** These steps run again, in step order, each from its
   beginning (its condition, gates, delay, inputs, approval and checkpoint):
   - the deferred steps;
   - each step that **ran ahead**: it began after a step of its run was
     deferred and was not deferred itself (§5.14), and a later step that runs
     again under this item reads its store. It runs again so that the step
     that reads it sees what is there after the actions before it, as in a
     run that never deferred. A handler, and a step that declares
     `after_deferral: run`, keep their outputs;
   - each `checkpoint` step whose checkpoint the resumption invalidated (no
     step had used it) and whose store a later step that runs again under
     this item, and that requires a checkpoint, reads: its new checkpoint is
     then the one that step binds and uses (such as a `mutate` that binds
     `checkpoint_id`, §12.5), as W608's remedy takes a new checkpoint after a
     wait. A step that only binds the id, such as a `rollback`, does not
     cause this: it returns to the restore point it named.
   No other step runs again, except under a recovery loop (item 7): a step
   that ran before the deferral, or ran ahead and is not read, keeps its
   output. The deferral rules of §5.14
   apply as in any run, so a step that depends on a step deferred again is
   deferred again. A deferred handler runs last (item 4).
3. **Nested runs.** A deferred `invoke` step whose nested run ended
   `deferred` continues that nested run, which resumes as this subsection
   says; when it ends, the step completes as any step whose nested run ended
   does (§5.12). The step's condition, gates and inputs are not evaluated
   again: they were when the invocation started. The queued actions of a
   nested run that failed are not carried out: the resumption supersedes
   them (`rejected`, "superseded").
4. **A deferred handler.** In a run whose handler was deferred (it ended
   `deferred` with an escalation's cause, §5.11), the steps of the normal
   flow that item 2 lists run first, in step order, and then the handler,
   with that cause; the run then ends as an escalation does.
5. **The approval.** A re-entered step that requires approval is asked
   afresh: its shown values and digest are computed now, a decision must
   match them, `expires` runs from the new request, and `recheck` re-reads
   its source after the decision. Every request for a re-entered queued step
   names its queued action (`queued_action_id`: the `action_id` of the
   record its deferral left), in either attendance, while the step continues
   it (item 6), after a recheck or in a retry too. In an attended resumption
   each such request is put to a person, a `human` approver keeping `role`,
   `min_approvers`, `sender_check` and `accept_trust_classes` and dropping
   `mandate_ref`. In an unattended resumption the step is asked as in any
   unattended run, and its `when_unattended` applies again.
6. **The record.** A re-entered step continues its queued action until it
   goes on to another step, carries the action out, is deferred again, or
   its run leaves it; a recovery loop that runs it again before then keeps
   it (item 7). Meanwhile each decision and refusal of the step updates in
   place the record its deferral left, keeping its `action_id`, with the
   time and actor of then (carrying the action out sets only its status);
   no other record is written for it, and the trace keeps every decision. A
   step deferred again leaves the record `planned`. A queued action whose
   step goes on, or is left, before reaching its approval (its condition is
   false, a gate skips or stops it, or it fails first) is superseded
   (`rejected`, "superseded"); any record the resumption supersedes takes
   the time and actor of then.
7. **Ending early.** A recovery loop during the resumption runs again the
   steps from its target to the step that looped, as in normal flow (a
   handler among them does not run); the resumption then goes on with the
   rest of its list, a deferred handler last. Of the queued steps it runs
   again, one still continuing its queued action keeps it (item 6), one that
   had gone on or carried it out runs as a new action, and one deferred
   again in the resumption has its queued action superseded (§5.14). The
   steps after the one that looped keep their queued actions and outputs, so
   nothing that ran ahead runs twice. A gate `end` ends the run before the
   queued steps after it and the deferred handler, whose queued actions are
   superseded. Another escalation takes precedence over the deferred
   handler's: its queued actions are superseded, the queued steps not yet
   re-entered stay deferred, and the new handler is judged against them
   (§5.14). When the resumed run fails, or needs a replan, the queued steps
   it did not reach stay deferred: listed among the run's deferrals, with
   their records `planned`, abandoned as above.

**Saved states.** An executor MUST refuse to resume a state that does not
keep what this subsection needs: the nested run of each deferred `invoke`
step, and which steps ran ahead. Such a run can be cancelled (§5.19.5). A host
whose executor saved the state before it implemented this subsection
cancels the run and starts a new one.

A resumed run ends as any run does; one that ends `deferred` can be resumed
again.

### 5.15 Delegation

```yaml
- capability: delegate
  store_as: review_a
  input_bindings:
    task: {review: "${diff_out.data: object}"}
    agent: reviewer-a
    fresh_context: true
    model_family: claude
    role: reviewer
```

`delegate` accepts `fresh_context` (start the delegate without the
delegator's context), `model_family`, `role` and `read_only` (the delegate
may read but must not change anything: files, repositories, external
state), and reports the values the host actually used as `effective`; the
standard does not say how a host enforces `read_only`, only that
`effective.read_only` attests it. With `identity@1`, `effective` may also
attest who took the delegation, as `identity` (§5.17). `receive` and `synchronize` accept
`accept_from` (a list of principals): received items from other principals
are dropped and counted, and each kept item's `sender` is the
host-authenticated principal. A literal empty `accept_from` accepts no one
and is S303; leave the input out to accept every sender. A reference that
resolves, when the step runs, to anything but a non-empty list of strings
fails the step (R402): an empty list would drop every sender, and a null
in it (from a missing value) would be dropped silently.

A **principal** is an opaque string, compared by exact (code-point)
equality; the standard gives it no structure. The host maps its own
identities (accounts, keys, agent sessions) to principals, and reports as
the principal of an item the authenticated party that delivered it to the
run, never a sender the item's content claims. So an item a peer relays on
behalf of the owner has the peer as its principal, and `accept_from: [owner]`
drops it. The identity behind a principal, and checks on it, are §5.17
(`identity@1`). Binding any of these inputs needs
`delegation@1` (V106); they are typed by the ontology like any other input.

#### 5.15.1 Agent Manifests

<!-- owner: S3; text: S3.md part 2.13 -->

#### 5.15.2 Delegation Targets

<!-- owner: S3; text: S3.md part 2.14 -->

#### 5.15.3 Continuing a Delegation

<!-- owner: S3; text: S3.md part 2.15 -->

#### 5.15.4 Checkpoints Across a Delegation

<!-- owner: S5; text: S5.md part 2.7 -->

### 5.16 Quorum

```yaml
- capability: constrain
  store_as: quorum_out
  input_bindings:
    target: ${verdicts_out.data}
    constraints: [two_independent_approvals]
    action_on_violation: block
  quorum:
    verdicts: ${verdicts_out.data}
    reviewers: [review_a, review_b]
    vocabulary: [approve, request_changes, abstain]
    pass_values: [approve]
    blocking_values: [request_changes]
    min_pass: 2
    pinned_to: ${change_ref}
    forbidden_inputs: [author_notes]   # or per reviewer: {review_b: [prior_rounds]}
    require_fresh_context: true
    require_model_families: [claude, gpt]
    min_full: 1
```

`quorum` is allowed only on `constrain` with literal
`action_on_violation: block` (S303), so a failed quorum stops the run:

| Field | Description |
|-------|-------------|
| `verdicts` | Required: reference to the reviews (`review_verdict_schema.yaml#/review_verdict` items), or a non-empty list of references, each to a verdict or a list of them (e.g. the `result` of each reviewer's waiting `delegate` step, §5.13) |
| `reviewers` | Required: `store_as` names of `delegate` steps that run before this one (else V107), delegating to distinct agents when the agents are literal (else F504) |
| `vocabulary` | Required: at least two distinct verdict values |
| `pass_values` | Required: a non-empty subset of the vocabulary |
| `blocking_values` | A subset of the vocabulary, disjoint from `pass_values`, that vetoes |
| `min_pass` | Required: 1 ≤ `min_pass` ≤ number of reviewers |
| `pinned_to` | Required: reference every counted verdict must be pinned to (e.g. the commit reviewed) |
| `forbidden_inputs` | Stores or inputs a reviewer may not depend on, directly or transitively through bindings — including context a recovery loop injects (`${_recovery.*}`). A list applies to every reviewer; a mapping gives each reviewer its own list (keys that are not reviewers: V107; a reviewer it omits has none). Names that are neither inputs nor stores of steps running before the quorum step: V107; a dependency: F504 |
| `require_fresh_context` | Every reviewer binds `fresh_context: true` (F504 otherwise) |
| `require_read_only` | Every reviewer binds `read_only: true` (F504 otherwise) |
| `require_distinct_identities` | `identity@1` (else V106): every reviewer waits for its own result and every `verdicts` reference reads a reviewer's own result (else S303: a verdict from a shared inbox or an input could claim any reviewer's name), and a verdict counts only if it was read so and its reviewer's host attested an identity (`effective.identity`, §5.17) whose principal no other counted reviewer has |
| `require_model_families` | Families the reviewers must cover; F504 when every reviewer binds a literal family and they do not cover the set (otherwise checked at runtime). Only an attested family covers one: `effective.model_family`, or the attested identity's; a family a reviewer asks for that its host does not attest covers nothing |
| `min_full` | Passing verdicts whose `scope` is `full` needed: 1 ≤ `min_full` ≤ number of reviewers. These are passes too, so a `min_full` above `min_pass` raises the passes needed |

A missing required field is S304; a malformed value is S303; `verdicts` and
`pinned_to` must be references; unknown fields are W604.

A verdict counts once per reviewer: only if its `reviewer_id` is a
reviewer delegate's agent, its `pinned` equals the resolved `pinned_to`,
its value is in the vocabulary, it is the first from that reviewer, and
(when required) the delegate's `effective` settings show a fresh context
and read-only and, with `require_distinct_identities`, an attested
identity whose principal is not another counted reviewer's (the first
counted keeps it): distinct agent names may be one party. A verdict read
through a reference to a reviewer step's own
output (its `result`) is that reviewer's: it counts only if its
`reviewer_id` is that step's agent.
A verdict's `scope` (`review_verdict_schema.yaml` 1.1.0) is `full` (it
swept the whole pinned change) or `delta` (only what changed since an
earlier round). Absent, it counts as `delta`; any other value (which the
schema rejects) counts as `delta` too and is noted in `violations`, so the
verdict still passes or blocks but is never a full sweep.
The step is compliant iff no counted verdict is blocking, passes ≥
`min_pass`, passes with scope `full` ≥ `min_full` (when set), and
model-family coverage holds; otherwise F504. The output gains `tally`
(`passes`, `blocks`, `abstains`, `full_passes`, `voters`).

### 5.17 Sender Identity

```yaml
- capability: receive
  purpose: Wait for the owner's answer.
  store_as: answer
  timeout: 2h
  input_bindings:
    sender_check: [session_id, x-acme.sso]
    accept_trust_classes: [owner, decision_person, colleague]
    always_ask_trust_classes: [colleague]
  wait: {event_type: answer.given}
```

An **agent identity** (`schemas/agent_identity_schema.yaml#/agent_identity`)
says who a party is, as the host authenticated it: its `principal` (§5.15),
its `kind` (`agent`, `human` or `service`), and optionally its `role`,
`model_family`, `owner` (the principal it acts for), `authenticated_by` (how
the host authenticated it: `session_id`, `chat_user_id`, `code_host_login`,
`directory_id`, `api_key`, `signed_token`, or an `x-` vendor value) and
`trust_class` (`owner`, `decision_person`, `system_of_record`,
`own_subagent_report`, `peer_agent`, `colleague` or `external`). The host
fills it in; the standard does not say how a party is authenticated or
classified. It records no reliability: that is RFC-0002's subject.

With `identity@1` declared, `receive`, `synchronize` and a waiting `delegate`
(for its result, §5.13) accept three inputs,
each a list of values from the vocabularies above (`sender_check` and
`accept_trust_classes` non-empty). Binding any of them without
`identity@1` declared is V106, and on a `delegate` that does not wait it
is S303 (§5.13); a literal that is not a list is B203 against the input's
type (§5.4), and a list holding anything but values of the vocabulary is
S303; a reference
that resolves to anything else (null, say) fails the step (R402), so a
check is never silently off. A workflow that does not declare `identity@1`
ignores any identity a host reports. In a workflow that targets 1.2, the approver of an approval accepts two of
them as fields, `sender_check` and `accept_trust_classes` (see
**Approvers**).

| Input | Effect on an item |
|-------|-------------------|
| `sender_check` | Kept only if its sender's identity has an `authenticated_by` listed here |
| `accept_trust_classes` | Kept only if its sender's identity has a `trust_class` listed here |
| `always_ask_trust_classes` | Kept; but if its sender's identity has a `trust_class` listed here, or no identity or no `trust_class`, the item is **always-ask** |

On a wait (§5.13), the host reports the sender's identity with each event
(the response's `identity`); its `principal` is the item's principal. A
response whose `principal` names someone other than its identity, or whose
identity is not an `agent_identity`, is rejected as malformed and changes
nothing. When `sender_check` or `accept_trust_classes` is bound, an item
with no identity, or whose identity fails a bound check, is dropped and
counted (by reason, as for `accept_from`), and the wait goes on. A kept
item carries `sender` and `sender_identity`; a `synchronize` wait carries
them beside the agreed state. On a step that does not wait, the host
receives these inputs with the step and applies them to what it returns,
and each item it returns MUST carry the `sender_identity` it applied them
to: the executor reads the always-ask classes from it.

**Delegation.** A delegation's host may attest who took it:
`effective.identity`, an `agent_identity`. Read only with `identity@1`
declared, it MUST be one (else R402, and the delegation fails as any
step does), and its `model_family` and `role`, where given, MUST equal
`effective.model_family` and `effective.role` (else R402). A waiting
`delegate` (§5.13) then keeps only results whose principal is that
identity's: any other is dropped and counted (reason `delegate_identity`),
and the wait goes on; the wait's `AwaitEvent` names the principal as
`delegate_principal`. A retry's new delegation binds its own. A host that
attests no identity is not bound, as before. This catches a host that
routes the task to another party than it reports, and a peer that answers
in the delegate's place; it does not protect against a host that lies,
since the identity is the host's attestation, not a credential (§8.3).

**Always ask.** A step is *marked* when its output holds an always-ask
item, when it reads a marked store or input (a reference in any of its
executable fields, as for deferral in §5.14), or when it is an `invoke`
whose nested run marked anything; a nested run invoked by a marked step
has every step marked. Context a recovery loop injects from a marked
value is marked (§5.12). A mark is never removed during a run. A
marked step that requires approval is asked of a person even when its
`approval` names a standing mandate (§5.14): the approval request names a
`human` approver with `always_ask: true`, keeping the `role`, `min_approvers`, `sender_check` and
`accept_trust_classes` and dropping the `mandate_ref`, and its action records
carry `always_ask: true`. In an unattended run the step follows its
`when_unattended` plan, and the action record's `reason` says why; a step whose only plan for an unattended run is a standing
mandate and that uses, through bindings, a step that binds
`always_ask_trust_classes` is W606. A marked step that does not require
approval runs as it would otherwise. The mark follows references only:
content a host carries into a later step by other means is beyond what the
executor can see.

**Approvers.** With `identity@1` declared, a host may attest who decided an
approval (§5.14): a decision's `approver_identities`, a list of
`agent_identity`. Each MUST be one; two with the same principal MUST be
identical (a repeat counts once); and `approvers`, when not empty, MUST list
exactly their principals. A decision that breaks any of these is rejected as
malformed and changes nothing, as an event is. The approvers are then
counted by principal, and an identity counts toward `min_approvers` only if
it meets the request:

- for a `human` approver, including one asked in place of a standing mandate
  (§5.14.1, and **Always ask** above), its `kind` is `human`;
- when the request names a `role`, its `role` equals it;
- in a workflow that targets 1.2, when the approver declares `sender_check`,
  its `authenticated_by` is listed there;
- in a workflow that targets 1.2, when the approver declares
  `accept_trust_classes`, its `trust_class` is listed there.

The action record lists the approvers that counted: their principals in
`approval.approvers` and their identities in `approval.approver_identities`;
when the decision is refused, its `reason` names the others and why they did
not count. A layer that approves tool calls (§5.18.7) and can attest its
approvers records them the same way.

In a workflow that targets 1.2 (§11.5), `approval.approver` may declare
`sender_check` and `accept_trust_classes`: each a non-empty list of values
from the vocabularies above (else S303), with `identity@1` declared (else
V106). They make attested identities required: a decision without
`approver_identities` then counts no approvers. In a workflow that targets an
earlier version they are unknown fields (W604, and W616, §11.5), and neither
the validator nor the executor applies them; declare `spec_version: "1.2"` to
have them enforced, and a consumer of an earlier version then refuses the
workflow (V109) rather than ignore the requirement.

Without identities, the approvers are the distinct strings of `approvers`,
and the host vouches for them: it SHOULD accept a decision only from
approvers who hold the requested `role`. A workflow that does not declare
`identity@1` ignores `approver_identities`. As for a delegation, the
identities are the host's attestation: the executor checks that they are
consistent with the request, not that an approver is a person.

**Actor.** A run may be started with the identity of the agent that runs
it; every action record then carries it as `actor_identity`, and `actor`
is its `kind`. `ActionRecord.actor_identity` and
`ProvenanceRecord.agent_identity` are optional in
`world_state_schema.yaml`. Two records denote the same party exactly when
their identities' principals are equal; an implementation MUST NOT infer it
from the `actor` or `agent` strings alone.

A run keeps its actor while it continues. A host that saves a run and
continues it later (§5.19.4) SHOULD name the actor it continues the run for; the
executor MUST then refuse to restore the run when that actor's principal
differs from the run's, or when the run was started without an actor.

At a **handoff**, when another agent takes over the conversation or thread a
run belongs to, the host MUST NOT continue the run under the agent that
takes over. It cancels the run (§5.19.5) if the run has not ended, and the agent
that takes over starts a new run under its own identity. A run that ended
`deferred` may instead be resumed under the new agent, or cancelled. The one
change of actor allowed is that resumption (§5.14.1): the host names the new
actor, the trace records the change, and the action records written from
then on, including the queued records the resumed run decides, refuses or
supersedes (§5.14.1 item 6), carry the new actor; earlier records keep
theirs.

### 5.18 Tool-Calling Hosts

On a tool-calling host (§2) a model chooses each call, and no step list is
known in advance. This section states how the capability ontology applies
to calls. §5.18.1–§5.18.8 and §5.18.10 bind a **safety layer**: a host that
runs none has no obligation under them, and a layer's conformance is claimed
under §10.4. §5.18.9 binds every producer and consumer of a capability
output carried as a string, whether or not a safety layer runs, a host that
answers an executor's capability call included. When a host performs a
workflow step by making calls (the executor's capability call), those calls
are part of the step: §5.2–§5.17 govern the step, and the step's approval
and checkpoint cover its calls as a composite's cover its nested calls
(§5.18.4).

#### 5.18.1 Tool Bindings

A **tool binding** is a record (`schemas/interop/tool_binding.schema.json`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool` | string | Yes | The name the host offers the tool under |
| `ontology` | string | Yes | The ontology version the record was written against (`MAJOR.MINOR[.PATCH]`, §11.6) |
| `standard` | string | No | The Standard version the record was written against (`MAJOR.MINOR[.PATCH]`, §11.6) |
| `capability` | string | No | The capability the tool performs; required unless `control` is true |
| `domain` | string | No | The capability's domain parameter |
| `flags` | object | No | Declared safety flags: `risk`, `mutation`, `requires_checkpoint`, `requires_approval` (§5.2.1) |
| `additional_capabilities` | array | No | Other capabilities the same call performs (§5.18.3) |
| `classifier` | string | No | Names the classifier a layer applies to each call (§5.18.3) |
| `invokes` | array | No | Names of the bindings the tool may call while it runs (§5.18.4) |
| `approval` | object | No | `min_approvers` (integer ≥ 1, default 1), `role` (a non-empty string), `expires` (a duration, §5.10.1, of at most 2^53 − 1 ms) for calls that require approval (§5.18.7) |
| `control` | boolean | No | `true`: the tool only signals the host (§5.18.3) |
| `destination` | string | No | For a tool that performs `send`: an RFC 6901 pointer to the argument that holds the destination, which a layer checks against the destination policies in force (§4.4.2) |

Members whose name starts with `x-` are vendor data. A **carrier** is a
host's own form of the record (tool metadata, an annotation): it states the
same members under its own names and is read as the record.

- A `capability`, or an entry of `additional_capabilities`, that the
  ontology does not define is V101, and the record is not loaded. A member
  of the wrong type or value, or an unknown member whose name does not
  start with `x-`, is S303, a missing required one S304, and the record is
  not loaded: a record a layer cannot read in full could declare something
  stricter, so its tool is treated as unbound rather than read in part.
- A record's **effective flags** are the strictest, flag by flag, of its
  declared `flags` and the ontology's flags of `capability` and of each
  entry of `additional_capabilities` (booleans OR-ed, `risk` the highest
  level), and of each binding in `invokes` (§5.18.4). A declared flag
  weaker than the ontology's has no effect and is W602, except
  `mutation: false` on a `mutation_overridable` capability (§4.4) in a
  record that names no other capability. A layer MAY refuse to load a
  record with a W602, as strict validation treats a warning as an error.
- A call's **prerequisites** are the `from` capabilities of the `requires`
  edges (§4.3) of every capability its record names.
- A record whose `ontology` major version the layer does not support, or
  that cites a `standard` the layer does not support, is V109 and is not
  loaded. Any other is read against the layer's own ontology.
- Two records for one `tool` in one set are V110, and neither is loaded.
- A record describes; it does not enforce. A layer computes effective flags
  from its own ontology and the record's members, and ignores copies a
  carrier holds (such as an annotation's `layer` or effective flags). A
  record is not evidence that any layer enforces it.
- A tool whose record is not loaded is unbound (§5.18.2).

#### 5.18.2 Unbound Tools

A call of a tool with no loaded binding is treated as a call of no
capability with `risk: high`, and `mutation`, `requires_checkpoint` and
`requires_approval` true: a layer cannot know that an unknown tool only
reads.

A host that knows the tools it offers a model SHOULD check them before the
model runs, and report each of these:

| Offered tool or host action | Code |
|-----------------------------|------|
| An offered tool with no binding | W617 |
| A binding whose `tool` is not the name the host offers it under | V111 |
| A tool that requires a capability no offered tool can perform, through a prerequisite or through its effective `requires_checkpoint`: its calls could never run | V102 |
| A host action tied to a tool that is not control-only and is unbound, has a prerequisite, or has an effective `requires_checkpoint` or `requires_approval` (§5.18.3) | F506 |

An offered tool with a `classifier` counts as able to perform any
capability, and a host that takes checkpoints itself (§5.18.6) counts as
performing `checkpoint`.

#### 5.18.3 Classification

A binding classifies a tool by its effect, not by its transport or its name:

| What the call does | Capability |
|--------------------|------------|
| Reads, looks up or queries without changing anything, whatever the protocol (an HTTP POST that only queries included) | `retrieve`, `search` or `observe` |
| Changes a resource that can be read back: a file, a database row, a configuration, an issue's state, a remote record through an API, a pushed branch | `mutate` (`domain`: the system changed) |
| Delivers a message, notification or event to a recipient outside the scope: an e-mail, a chat or issue comment, a webhook, a published event; and any request to another system whose effect the binding does not know | `send` |
| Both of the above in one call | `capability` the primary effect, the other in `additional_capabilities` |
| Writes the store the host provides for the agent's own memory, which `recall` reads | `persist`; a write anywhere else is `mutate` |
| Restores a checkpoint taken in the scope | `rollback`; restoring other state is `mutate` |
| Gives an agent a task, or further instructions on a task already delegated to it | `delegate` |
| Only signals the host (ends a turn or a session, reports a status) and has no other effect | Control-only (`control: true`) |
| Carries only the values of an executor's host-protocol action to the party that performs or decides it (§5.19.6) | Not a `send`: protocol traffic, covered by the step whose action it performs |

**Several capabilities.** A tool that performs several capabilities in one
call names the others in `additional_capabilities`; its effective flags and
prerequisites are those of all of them (§5.18.1). The same holds for one
call a classifier reads as several actions (a shell line of several
commands): its classification is the strictest flags and the union of the
prerequisites of every action it recognises.

**Classifiers.** A layer MAY classify each call of a tool from its
arguments (`classifier` names how), as a shell command may only read. The
record's `capability`, `additional_capabilities` and `flags` are then the
tool's worst case, which applies to any argument the classifier does not
recognise and whenever it fails. A classification it returns is a
capability and declared flags, subject to §5.18.1: never weaker than that
capability's ontology flags, though it may be weaker than the worst case.

**Control-only tools.** A record with `control: true` has no member but
`tool`, `ontology`, `standard`, `control` and `x-` members (else S303). Its
calls return no capability output and are never refused: no check of this
section, no host policy such as a rate limit, applies to them, and a layer
that cannot write the record of one reports the failure and does not refuse
the call (§5.18.8). They are recorded. A tool that signals the host and also
has an effect is not control-only: bind it by its effect.

A host action that takes effect whenever a tool is called, whatever the
call's result (such as ending the turn or the session, or reporting a
status), MUST NOT be tied to a tool that is not control-only and is
unbound, has a prerequisite, or has an effective `requires_checkpoint` or
`requires_approval`: the action would follow a call the layer refused
(F506). A host SHOULD tie such an action to a control-only tool: a bound
tool without those gates can still be refused by a host policy (F504) or a
failure of the layer (R407).

#### 5.18.4 Composite Tools

A tool that calls other tools while it runs (a **composite**) names the
bindings it may call in `invokes`. Its effective flags include, transitively,
those of each binding listed (§5.18.1).

| Composite | Code |
|-----------|------|
| A name in `invokes` that no binding of the set has: the composite is not loaded | V107 |
| A cycle through `invokes`: the composite is not loaded | V105 |
| A nested call the layer attributes to the composite, to a binding it does not list: the call is refused | F504 |

- A call the composite's own code makes while it runs, to a binding it
  lists, is a **nested call**. The composite's approval and checkpoint
  cover it: a layer that attributes it to the running composite applies no
  further checkpoint or approval to it, and records it with the call that
  covered it. Every other check still applies to it, its prerequisites
  (§5.18.5) included. A layer that cannot attribute it checks it as a call
  of its own. A composite that lists a binding a profile requires a person
  for is asked of a person (§5.21.3).
- A layer attributes a call to a composite only on evidence that the
  composite's own code made it, such as an invocation the layer itself
  passed to the composite. That a call comes from the same thread, session
  or execution while the composite runs is not such evidence: other code
  (an endpoint, an effect, a parallel call of the same step) can make the
  call at the same moment. Each invocation covers at most one call.
- A layer that attributes a nested call to a binding the composite does not
  list refuses it with F504. A host that can enforce the list (a runtime
  that rejects an invocation outside a declared list) SHOULD.
- `invokes` bounds named invocation only. A composite's own code can still
  write storage or reach the network directly, so the flags it takes from
  `invokes` are a lower bound: declare `flags` or `additional_capabilities`
  for what it does itself.

#### 5.18.5 Scope, Order and Concurrency

- **Scope.** A layer keeps its records per scope, the sequence of calls it
  orders, and names its scope in its conformance statement (§10.4). A
  delegate's calls are another scope, unless the layer orders them with the
  delegator's against one set of records, which it states. Records of one
  scope never authorise a call of another.
- **History.** A call ran before another only if it completed before the
  other started. History counts over the scope's lifetime; a checkpoint's
  power to authorise ends sooner (§5.18.6).

The edge types (§4.3) apply to calls as follows:

| Edge | Over calls | Code |
|------|------------|------|
| `requires` | A call is refused unless each of its prerequisites (§5.18.1) has run earlier in the scope: for `checkpoint`, a checkpoint was taken in the scope (§5.18.6); for any other capability, a call of it completed successfully | F501 for a missing checkpoint, F503 for a call of `rollback`; V102 (§9.1) for any other missing prerequisite |
| `soft_requires` | Never refuses a call; a layer MAY report it | W601 |
| `precedes` | Neither enforced nor reported. At a call the layer cannot know whether a call that must come first will follow, and when one does, the earlier call has had its effect | — |
| `conflicts_with` | Not enforced: it forbids two capabilities only in one `parallel_group` (§4.3) | — |

- **Concurrency.** A layer's check of a call and its use of a checkpoint or
  a decision (§5.18.6, §5.18.7) MUST be one atomic step for the scope: two
  calls that overlap never both pass on one checkpoint or one decision. A
  layer achieves this with a lock or a reservation, or relies on its host
  running the scope's calls one at a time, and states which (§10.4).

#### 5.18.6 Checkpoints for Calls

- **Taking one.** A checkpoint is taken in the scope by a call classified
  `checkpoint` that completed successfully, or by the host's own checkpoint
  operation, which the layer records in the scope. A call that failed takes
  none. A call that only leads to one, such as loading a skill's
  instructions, takes none: the call that saves the state does. The layer
  counts the call; it does not verify what the restore point holds.
- **One per call.** A checkpoint authorises one call whose effective
  `requires_checkpoint` is true (§5.2.2). The layer uses the most recently
  taken of the valid checkpoints no other call holds, as the executor does
  for steps.
- **When it is used up.** When every check of this section has passed and
  the call is allowed to start, before its effect. A call that started uses
  it whatever its outcome: a layer may never learn the outcome, a call that
  reports an error may still have changed something, and a failure between
  the effect and the layer's record must not leave the checkpoint valid for
  a second change.
- **Holds.** A call the layer refuses uses nothing up. Where the host can
  still refuse a call after the layer checked it (a permission prompt the
  layer does not run), the layer holds the checkpoint for the call until the
  call is allowed or refused, and releases it on a refusal it learns of. When
  the call is allowed, the layer checks again, in one atomic step with its
  use, that the hold is still the call's and the checkpoint still valid; if
  not, the call is refused with F501. A hold lapses when its checkpoint
  reaches the maximum age, or after a shorter time the layer states. A hold
  the layer cannot resolve, because it never learns what became of the call
  (the hold lapses, the layer restarts, the host does not report a
  refusal), counts as used.
- **Validity.** A checkpoint authorises a call only before the scope's next
  execution boundary, and only within the layer's maximum age: a duration
  the layer states, of at most 30 minutes. The layer names the boundaries
  it observes (§10.4). A permission prompt answered while the call waits is
  not a boundary, but the maximum age keeps running while it is open.
- **None valid.** A call is refused when it lacks what the table below
  names. A layer does not take a checkpoint on the call's behalf: it cannot
  know what the call will change, and the model takes one with a
  `checkpoint` call.

| Call | Refused without | Code |
|------|-----------------|------|
| A call whose effective `requires_checkpoint` is true | A valid checkpoint for it alone | F501 |
| A call of `rollback` | A checkpoint taken earlier in the scope, valid or not; it uses none up | F503 |

#### 5.18.7 Approval for Calls

A call whose effective `requires_approval` is true runs only on a valid
decision; otherwise it is refused with F502.

- **Shown and hashed.** Approvers are shown, and a decision binds to, the
  array `[{"action": <tool>, "capability": <capability>, "args": <the
  arguments the call will run with>}]`: the shown values of §5.14, with its
  digest (SHA-256 of the RFC 8785 canonical JSON). `capability` is null for
  an unbound tool. The arguments MUST be I-JSON (§5.14); a call whose
  arguments are not is refused with F502.
- **Validity.** As in §5.14: the digest matches; at least `min_approvers`
  (the binding's `approval`, default 1) distinct approvers, as the host
  authenticated them (counted by principal when it attests their
  identities, which the record then carries as
  `approval.approver_identities`, §5.17), agree; it has not expired (the binding's
  `approval.expires`, else the period the layer states); and it has not
  been used. Once any approver rejects, the request is rejected: a
  rejection is never lost to a concurrent approval.
- **One decision per call.** The call that runs under a decision uses it
  up when the call is allowed to start, as for a checkpoint (§5.18.6); an
  identical later call needs a new decision. A call refused for another
  reason uses no decision.
- **Order.** A layer checks approval and the checkpoint in the order it
  chooses, and reports the code of a check the call failed. *(Approval
  first suits decisions recorded while the call waits: the restore point is
  then taken after the wait for a person. The checkpoint first suits a
  prompt answered within the call: a call that would be refused for want of
  a checkpoint does not ask a person first.)*
- **A host's own prompt.** A permission prompt that shows a person the tool
  and the arguments the call will run with, and decides that call alone, is
  a valid `in_session` decision with one approver, bound to the call in
  place of the digest; the layer still records the digest (§5.18.8). Every
  call that requires approval goes to the prompt, even one an allow-list or
  a remembered choice would pass. A prompt that is skipped, cannot be shown,
  is answered by anything but a person (the host itself, an automatic mode,
  a classifier), or shows other arguments than those that run decides
  nothing (F502). A layer relies on a host's prompt only in the host
  configurations it knows to put the prompt to a person, names them in its
  statement (§10.4), and refuses with F502 in any other. Such a prompt
  cannot meet a `min_approvers` above 1, nor a `role` unless the host
  authenticates the person's role to the layer (F502).
- **Changed arguments.** Where the host can answer a prompt with arguments
  other than those the call was checked with, the layer classifies the
  call again with the new arguments, and refuses it if the new
  classification requires approval (F502: the decision was on other
  arguments) or a checkpoint or prerequisite the call does not already hold
  (F501, F503 or V102), or if a check of §5.18.10 fails with them (F504).
  Otherwise the call runs with the new arguments, and the layer records
  their digest.
- **No one to ask.** With no one who can decide, the call is refused with
  F502, as under `when_unattended: fail`. Standing mandates, `skip` and
  `defer_to_queue` (§5.14) are not defined for calls.

#### 5.18.8 Refusals, Records and Failure

- **Refusals.** A refusal is a §9.8 diagnostic. Its `location` holds `tool`
  (the name the host offers the tool under), `capability` (absent for an
  unbound tool) and, where the host gives calls an identifier, `call`; it
  holds no `workflow` or `step`. Where the channel to the model or the host
  carries only text, the text opens with the code and the name:
  `F501 CHECKPOINT_REQUIRED: ...`. The codes a layer refuses a call with:

| Code | The call is refused because |
|------|-----------------------------|
| F501 | It requires a checkpoint and has no valid one (§5.18.6), or no checkpoint was taken in the scope (§5.18.5) |
| F502 | It requires approval and has no valid decision (§5.18.7) |
| F503 | It is a call of `rollback` and no checkpoint was taken in the scope (§5.18.6) |
| V102 | A prerequisite other than `checkpoint` has not run in the scope (§5.18.5) |
| F504 | A host's own policy refuses it, such as a rate limit or a destination policy (§5.18.10), or a composite made it to a binding it does not list (§5.18.4) |
| R407 | The layer cannot complete a check or write the call's record (below) |
- **Records.** A layer records each call it allows or refuses: the tool,
  its capability, the digest of its shown value (§5.18.7) when it requires
  approval, the decision and its approvers, the checkpoint it used, any
  nested call with the call that covered it, and, for a refusal, the
  diagnostic. Each record names the layer and its configuration in its
  `recorded_by` member (§6.4): a name, a version, and a digest of the
  bindings and settings it applied (`config_sha256`), with the settings
  themselves listed where they are few (`settings`), so a reader can tell
  which rules a call was held to.
- **Fail closed.** A layer that cannot classify a call applies §5.18.2 or
  §5.18.3. A layer that cannot read its records, complete a check, or write
  the record of a call it is about to allow refuses the call with R407; for
  a control-only call it reports the failure and lets the call run
  (§5.18.3). A host that claims a conforming layer MUST NOT run a call the
  layer covers without the layer's decision: if the layer is missing, fails to load,
  fails or does not answer, the call is refused, by the host or by the tool
  itself (a tool that refuses to run, with R407, unless the layer allowed
  this call). Where the host cannot guarantee this, the conformance
  statement names the gap (§10.4). A mode that only logs, or that lets a
  call run when a check fails, is outside class SL.

#### 5.18.9 Text-Only Results

This rule binds every producer and consumer of a capability output that a
host carries as a string, whether or not a safety layer runs: a tool's
result, a sub-prompt's or a model's reply, and the string a host turns into
the output of an executor's capability call.

Where a host carries a capability output as a string, it travels as the
I-JSON text (RFC 7493) of the output object, with nothing before or after
it. A consumer parses the text and checks that it is an object with every
field the capability's output contract requires; otherwise the output is
refused with R402. A host that answers an executor's capability call from
such a string decodes it by this rule before it answers; a string that
fails is the step's failure (R402). A producer checks the I-JSON limits of
§5.14 before it sends; a value outside them is R402. Where a host carries
validated structure instead (a submit tool's arguments, a structured
result), that structure is the output and this rule does not apply.

#### 5.18.10 Capability Checks

These checks belong to the capabilities, whatever implements them. A check
this Standard requires MUST be decided by code, from the layer's records and
the call's arguments. A model's judgement (a prompt-based hook, a classifier
model) MAY add a refusal; it never satisfies or replaces a required check.

| Capability | Check | Code |
|------------|-------|------|
| `checkpoint` | A checkpoint counts once the call that saves the state completed successfully; a call that only leads to one takes none (§5.18.6) | — |
| `mutate`, `send` | A valid checkpoint for this call alone, and a valid decision (§5.18.6, §5.18.7) | F501, F502 |
| `execute` | A valid decision (§5.18.7) | F502 |
| `rollback` | A checkpoint taken earlier in the scope, valid or not, expired or used (§5.18.6) | F503 |
| `persist` | Its target is the store the host provides for the agent's memory; a call that writes anywhere else is classified `mutate` (§5.18.3) | — |
| `persist` | Its data holds no secret the layer recognises (§6.7) | F504 |
| `audit` | It appends records and changes no other state (§4.4) | — |
| `audit` | The record it appends holds no secret the layer recognises (§6.7) | F504 |
| `send` | Its destination is one every destination policy in force allows (§4.4.2), checked before approval and the checkpoint; a layer that cannot tell a call's destination under a policy refuses it | F504 |
| `transform` | Where its output is recorded or stored, a secret it read is not carried into the record: it is redacted (§6.7) | — |
| every capability | Its output satisfies the output contract (§5.18.9) | R402 |
| every capability | Records and evidence the layer writes carry no secret: it redacts them (§6.7) | — |

A host-specific mechanism, such as a hook declared in a skill's
frontmatter, is one implementation of these checks. A host that loads a
skill's text as instructions without running its hooks applies these checks
by other means, or its layer does not cover the skill's calls and its
statement says so (§10.4). With §5.18.8's rule that a host claiming a
conforming layer runs no covered call without the layer's decision, this
makes each check above required of the host, whatever mechanism declares
it. A condition a skill's hook adds that this table does not list is a
model-judged or host-specific addition: it MAY refuse a call and is never
required.

### 5.19 Host Protocol

An **executor** runs a workflow and does no input or output of its own; a
**host** performs what the run needs from the world. The executor says what
it needs next (an **action**), the host performs it and answers (a
**response**), and time enters only through the times the host gives. The
same catalog, inputs, responses and times give the same actions.
`schemas/host_protocol.schema.json` defines every action and response; an
executor of class EX (§10.5) issues exactly those actions, and takes every
response the schema allows as §5.19.1 says.

#### 5.19.1 Actions and Responses

A run has, at any time, one **pending** action, or it has **ended** with a
terminal action (`Completed` or `Failed`). Every action carries:

- `run_id`: the run's identifier (§5.19.2);
- `id`: an integer. A run's first action has id 1 and each later action,
  the terminal one included, the next integer; a restored run issues its
  pending action again with the same `id` (§5.19.4);
- `frame`: the workflows of the nested runs (§5.12), root first;
- `kind`, and the members of its kind:

| Action | The host | Responses |
|--------|----------|-----------|
| `InvokeCapability` | performs `capability` with `inputs` for `step`, for the step's `domain` (null when it declares none, §5.2), by `deadline` when it is not null; `attempt` counts attempts from 1 (§5.2), and `replaces` names a delegation this one replaces (§5.13) | `Output` (`value`: the capability's output, an object with the fields its contract requires, else the step fails R402; a host that gets the output as text decodes it as §5.18.9 says; and, optionally, `evidence_seen`: the refs of the evidence the host attests the output's producer had for this answer (§5.20, §6.5); absent, it attests nothing), `Error` |
| `CreateCheckpoint` | takes a checkpoint before `step` | `Checkpoint` (`checkpoint_id`), `Error` (the step fails F501) |
| `Rollback` | restores `checkpoint_id` | `RolledBack`, `Error` (the run ends F503) |
| `RequestApproval` | asks `approver`, in `mode`, about `shown`, by `expires_at` when it is not null (§5.14) | `Decision` (`decision_id`, `decision`, `approvers`, `digest`) |
| `RecheckSource` | reads `source` again, to compare by `compare` (§5.14) | `Current` (`value`), `Error` (the step fails F502) |
| `AwaitEvent` | waits for an event that matches `event_type`, `source_kind`, `correlate` and the sender checks (§5.13, §5.15, §5.17), by `deadline`, and watches `liveness` | `Event` (`event`, optional `principal` and `identity`), `LivenessLost` (R406), `Error` |
| `Sleep` | lets time pass until `until` (a retry's backoff, §5.2; a delay, §5.13) | none: the host gives the run the time (§5.19.3) |
| `Completed` | none: the run ended with `outcome` (`completed`, `escalated`, `deferred` or `replan_required`), `cause`, `ended` (§5.6), `outputs`, `action_records` and `deferred` (§5.14) | none |
| `Failed` | none: the run ended with `code` (§9) at `step`, with `message`, `action_records` and `deferred`, and `reason` (§5.19.7) and `checkpoint_id` (§5.19.5) where they apply | none |

The executor computes these members:

- `inputs`: the step's `input_bindings` with every reference resolved
  (§5.3, §5.4).
- `attempt`: 1 for the first attempt of a pass of the step, one more for
  each retry (§5.2); a recovery loop starts a new pass (§5.12).
- `deadline`: when the step declares a `timeout`, the run's clock when the
  attempt's action was issued plus the timeout; for the wait of a waiting
  `delegate`, the deadline of its delegation (one timeout bounds both,
  §5.13); else null.
- `expires_at`: the run's clock when the approval was requested plus the
  approval's `expires` (§5.14); else null.
- `Sleep.until`: for a retry, the run's clock when the attempt failed plus
  the backoff of §5.2; for a delay, the run's clock when the step reached it
  plus `delay` (§5.13).
- `correlate`: the step's `correlate`, and, for a waiting `delegate`, the
  `task_id` its delegation returned (§5.13); `accept_from`, `sender_check`
  and `accept_trust_classes`: the step's bound inputs of those names, or
  null (§5.15, §5.17); `RecheckSource.source`: the `recheck.source`
  reference as written (§5.14); `shown` and `digest`: as §5.14 says.
- Every time is at most the maximum time (§5.19.3).

The terminal action's members:

- `outputs`: the root workflow's stores at the end: for each of its steps
  whose output is current (it completed, and no skip, deferral or recovery
  loop has since cleared it, §5.12, §5.14), that output under the step's
  `store_as`.
- `cause`: for `escalated`, and for `deferred` that kept an escalation, the
  code that caused the escalation, or R404 (§5.11); else null.
- `action_records`: the run's action records (§6.4), in the order first
  written, less any the host has taken from the run's state (§5.19.4).
- `deferred`: the deferred steps (§5.14), in the order deferred.

A step's output is the `value` of the host's `Output`, except for the steps
the executor runs itself, whose outputs it composes:

| Step | Output |
|------|--------|
| a wait on `receive` (§5.13) | `data`: a one-item list, the event with `sender` and `sender_identity` added when the host gave them (§5.17); `source`: the event's `source.kind`, and `timestamp`: its `timestamp` (each null when the event lacks it); `evidence_anchors`: the event's `anchors` (`[]` when the event has no such member) |
| a wait on `synchronize` | `synchronized: true`; `agreed_state`: the event's `canonical` (`{}` when absent); `participants`: the step's `agents`; `evidence_anchors` as above; `sender` and `sender_identity` when given |
| a waiting `delegate` | the delegation's `Output`, with the matching event (as in `data` above) as `result` |
| an `invoke` of a catalog workflow (§5.12) | `result`: the nested run's stores, as `outputs` above; `steps_executed`: the `store_as` names of its steps whose output is current, in step order; `evidence_anchors: []` |
| a quorum (§5.16) | `compliant`; `tally`; `violations`: in verdict order, `{reviewer_id, ignored}` for each verdict not counted, `{reviewer_id, note}` for a counted verdict whose `scope` is neither `full` nor `delta`, then `{quorum}` for each requirement not met, where `ignored`, `note` and `quorum` are text; `evidence_anchors: []`. `tally.voters` lists the counted reviewers sorted |

A response answers the pending action, named by its `id`. A response for
another action, of a kind the pending action does not take, or holding a
value that is not I-JSON (§5.14) is refused, and the run is unchanged. A run
that has ended takes no response. A response member this protocol does not
define is ignored, as in 1.1: a host may send members a later version
defines. Likewise, a host MUST ignore an action member it does not know:
later versions may add members to actions.

An `Error` carries a `code` and a `message`, and may carry a `reason`
(§5.19.7). Neither holds a secret (§6.7): both reach the run's diagnostics,
trace and records. To `InvokeCapability`, an `Error` with code R401 keeps it and any
other code is R402; to `AwaitEvent`, R401 and R406 keep theirs and any other
is R402.

The action records an executor writes (§6.4) have the `action_id`
`<run_id>/<frame>/<step>/<n>`, where `<frame>` is the frame's workflows
joined with `/` and `<n>` is the number of records the run wrote before
this one, taken ones included.

#### 5.19.2 Run Operations

An executor offers these operations on a run; each binding names them in
its own way, and its conformance statement says how (§10.5):

- **start**: with a catalog that validates (§10.5) and, for a catalog
  set, its other catalogs (§5.1.1); for each catalog, the version its
  header declares or none (§11.5: always given, and a host that loaded the
  catalog from a file passes the version of the file's header); the
  workflow, its inputs, the run's attendance (§5.10.2), its `run_id`, the
  time and, optionally, its actor (§5.17), its record mode (§6.4), the
  agent manifests it gives (§5.15.1), its destination policies (§4.4.2),
  the grounding policies it applies to the run and its nested runs (§5.20)
  and the domain profiles it applies (§5.21). The executor refuses to start
  a run whose destination policies hold an invalid pattern (§4.4.2), whose
  grounding policies name a capability the ontology lacks (V101, §5.20), or
  whose profiles have an error (§5.21.2). The run then has its first
  action.
- **next**: the pending action, or the terminal one. It changes nothing.
- **submit**: a response to the pending action, with the time.
- **tick**: the time, with no response (§5.19.3). It says whether it changed
  the run.
- **wake at**: the earliest time at which a tick changes the run, or none
  (§5.19.3). It changes nothing.
- **cancel**: ends the run, with a reason and the time (§5.19.5).
- **save** and **restore**: the run's state as a value the host keeps, and
  a run continued from such a value (§5.19.4).
- **resume**: continues a run that ended `deferred` (§5.14.1).

An executor MAY also offer **take** (the settled records and the trace,
§5.19.4) and **run record** (§5.19.8).

The `run_id` is the host's choice. It MUST differ from the `run_id` of every
other run whose action records, run record (§5.19.8), delivery keys
(§5.19.4) or idempotency keys (§4.4.2) the host keeps: they are keyed by it, and two runs under one
`run_id` would share keys, so a host would give one run a response it kept
for the other. A run continued from a saved state, restored or resumed,
keeps its `run_id`.

#### 5.19.3 Time

Times are integers of milliseconds since 1970-01-01T00:00:00Z. A run's clock
is the latest time the host has given it; an earlier time leaves the clock
where it is, and a time after 253402300799999 (the last millisecond of the
year 9999) counts as that time.

- A `Sleep` ends at a tick whose time is at or after its `until` (when it
  falls is §5.19.1).
- An action with a `deadline` (`InvokeCapability`, `AwaitEvent`) or an
  `expires_at` (`RequestApproval`) times out at a tick whose time is after
  it. An answer submitted at the deadline is in time; one submitted after it
  is late: a late output or event is R401, a late decision has lapsed
  (F502).
- So the **wake-up time** of a run is `until` for a pending `Sleep`, the
  `deadline` or `expires_at` plus one millisecond for an action that has
  one (none when that time would be after 253402300799999: no tick is ever
  after it), and none for any other pending action or an ended run.
- The executor has no clock of its own: it acts only when the host submits,
  ticks, cancels or resumes. A host that waits on a run sets its own timer
  for the wake-up time and ticks when it fires.
- A time-out is not announced: the next action shows what followed (a
  retry, a failure mode, the end). A host still performing the action
  SHOULD stop, since a response to it is now refused.
- Liveness (§5.13) is the host's to watch: the executor does not schedule
  heartbeats or probes. The host answers `LivenessLost` once the source has
  missed `failure_threshold` heartbeats or probes, `interval` apart.

#### 5.19.4 Saving and Continuing a Run

A run's **state** is all an executor needs to continue it. A host that keeps
a run across turns, processes or machines saves the state and restores it
later. Such a host:

1. **One writer.** MUST let only one party at a time submit to, tick,
   cancel or resume a run, and only from the latest state: it serialises the
   operations on one run, and MUST NOT continue two copies of one saved state
   (each would perform the same pending action, and resuming a deferred run
   twice could carry out a queued action twice, §5.14.1).
2. **Save before acting.** MUST save the state after each operation that
   changed it (start, submit, a tick that changed it, cancel, resume) and
   before it performs the action that operation left pending; a host that
   cannot save MUST NOT perform the action.
3. **At least once.** A restored run's pending action is the one pending
   when the state was saved, with the same `run_id` and `id`, though the host
   may already have performed it (it acted, then stopped before it could
   submit or save). The host MUST make what it does for an action idempotent
   under its **delivery key** (`run_id`, `id`): it keeps the response it gave
   for each delivery key it acted on and, given the key again, submits that
   response instead of acting again. Where an effect cannot be made
   idempotent, the host SHOULD record the key with the effect, so a repeat
   can be found. (A delivery key names one action; the idempotency key of
   §4.4.2 names a pass, every attempt of a step, and keeps a retry from
   repeating an effect.)
4. **Interrupted turns.** When the host's own execution stops between
   performing an action and submitting the response (its process ends, a
   client stops it), the run is unchanged: on its next turn the host
   restores the latest state and goes on as item 3 says. To end the run
   instead, it cancels it (§5.19.5).

Every host, whether or not it saves states, keeps each run's record
(§5.19.8).

**Integrity.** An executor MUST detect, when it restores a state, that the
state was corrupted (the reference executor saves a SHA-256 digest with it),
and, when the host gives a key, MUST refuse a state whose MAC under that key
does not verify (the reference executor: HMAC-SHA-256). A digest alone does
not show who wrote a state: whoever can change the state can recompute it.
So a host that keeps states where any party other than the run's writer can
change them MUST have the executor use a key, and MUST keep the key from
those parties. An executor SHOULD also refuse a state it could not have
produced (the reference executor checks the state's consistency). Saving
and restoring changes nothing: a restored run issues the same actions, and
reaches the same end, as the run it was saved from (§10.5).

**Taking records out.** An executor MAY let the host take settled action
records, and its trace, out of a run's state, so the state stays small; the
host then keeps what it takes (records as audit records, §6.4). An executor
that does MUST keep in the state a commitment to everything taken, in
order, so that a state that verifies also vouches for what was taken: the
reference executor keeps, for records and for trace events, a chain head
`h`, starting from the empty string and replaced, for each item taken, by
the lowercase hexadecimal SHA-256 of `h` followed by the item's canonical
JSON (RFC 8785).

#### 5.19.5 Cancelling a Run

A host MAY **cancel** a run that has not ended, or one that ended
`deferred`, with a reason. Cancelling:

- ends the run at once with a `Failed` action of code R408 (`CANCELLED`):
  its `message` is the reason, its `step` the step the run was at (null for
  a run that had ended), and its `checkpoint_id` the latest checkpoint the
  run knows of, if it knows of one;
- runs no retry, failure mode, recovery loop, handler or rollback: they
  answer failures of steps, and a host that stops a run may no longer be
  able to perform them. The executor does not roll back; a host that wants
  the run's effects undone restores `checkpoint_id` itself;
- withdraws the pending action: a response to it is refused. A host
  performing it SHOULD stop;
- sets each of the run's action records that is `approved` or `planned` to
  `cancelled`, with code R408 and the reason: an approved action may or may
  not have been carried out, and a queued one will not be;
- in record mode `actions` (§6.4), writes a `cancelled` record, with code
  R408 and the reason, for each step, in any of the run's nested runs, that
  has started its current pass and has no record of it. A step has
  **started** its pass once the executor has issued, in that pass, a
  `CreateCheckpoint`, `InvokeCapability` or `AwaitEvent` for it, or, for an
  `invoke`, started its nested run, or, for a quorum (§5.16), evaluated it; so a step waiting out a retry's backoff
  and a waiting `delegate` whose delegation was sent have started, and one
  waiting for its approval, its recheck or its delay has not. A pending
  `CreateCheckpoint` of a failure mode, or a pending `Rollback`, also gets
  its own `cancelled` record (capability `checkpoint` or `rollback`), as it
  would have had one had it completed;
- ends the nested runs with it. A cancelled run cannot be resumed.

A run that ended any other way cannot be cancelled. Nothing else ends a run
early: an `Error` that a host gives to stop a run is a failure of the step,
and the step's retries, failure modes and recovery apply.

#### 5.19.6 Protocol Traffic

What a host transmits to perform an action that is not `InvokeCapability`
(to the approvers for `RequestApproval`, to the source for `RecheckSource`
and `AwaitEvent`, liveness probes included, and to whoever started the run
for a terminal action) is **protocol traffic**, not a step. The safety flags
of `send` (§4.4) do not apply to it, and it needs no checkpoint or approval,
provided it carries only values the action holds: for `RequestApproval`, its
approver, mode, shown values, digest and expiry; for a terminal action, its
members. A host MUST NOT add other values of the run (stores, inputs,
outputs) to it. Anything else a workflow means to transmit is a step: a
`send`, or an `inquire` for a question to a person. A tool-calling host that
delivers protocol traffic through a tool treats that tool as a host action
(§5.18.3), not as a call of `send`.

#### 5.19.7 Error Reasons

An `Error` response MAY carry a `reason`, a token that says why without a
reader having to parse the message. The code still decides what the run
does (§5.19.1). This version defines:

| Reason | Meaning |
|--------|---------|
| `unsupported_capability` | The host does not perform the capability |
| `unsupported_domain` | The host performs the capability, but not for the step's `domain` (§5.2.4) |
| `not_recorded` | A record that was required was not written (§6.4) |
| `outcome_unknown` | An earlier attempt under the same idempotency key may have taken effect, and the host cannot tell; it did not act again (§4.4.2) |
| `key_conflict` | The idempotency key was first used with another capability or other inputs, so a `run_id` was reused; the host did not act (§4.4.2) |
| `destination_not_allowed` | The destination is not one the destination policies in force allow (§4.4.2) |
| `unsupported_scope` | The host does not provide the memory scope asked for, or did not use it (§4.5) |
| `unsupported_ttl` | The host cannot parse the `ttl`, or cannot end entries (§4.5) |
| `over_capacity` | The host refused to store for size or capacity; the message names the limit (§4.5) |
| `secret_in_data` | The data or key a `persist` would store holds a secret the host recognises; nothing was stored (§4.5, §6.7) |
| `below_minimum_confidence` | The output's `confidence` is below the minimum an applied domain profile sets (§5.21.3) |
| `invalid_confidence` | A minimum confidence applies and the output's `confidence` is not a number from 0 to 1 (§5.21.3) |

A host MAY also send a vendor reason: `x-`, then a lowercase letter or a
digit, then at most 61 lowercase letters, digits, `_`, `.` or `-`. A
`reason` that is neither (another string, or a value that is not a string)
is ignored: the `Error` is taken as if it carried no `reason`, as 1.1 took
any member it did not define, and the executor MAY note the ignored value
in its trace. A step that fails with a reason keeps it: the run's `Failed`
action carries it as `reason` when the run ends with that failure, and the
step's action record as `reason_code` (§6.4). The executor raises
`not_recorded` itself for an `audit` step (§6.4),
`destination_not_allowed` with F504 for a `send` step (§4.4.2),
`unsupported_scope` with R402 for a `persist` or `recall` step whose output
does not echo its scope (§4.5), and `below_minimum_confidence` and
`invalid_confidence` with F504 for an output an applied profile's minimum
confidence covers (§5.21.3).

#### 5.19.8 The Run's Record

Every run has a **run record**: an action record (§6.4) derived from its
terminal action, so that a run that failed or was cancelled before any step
wrote a record still leaves one. Its members are:

| Member | Value |
|--------|-------|
| `action_id`, `run_id` | the run's `run_id` |
| `frame` | the terminal action's `frame` |
| `step` | for `Failed`, its `step` when not null; absent otherwise |
| `timestamp` | the run's clock (§5.19.3) when it ended, as an RFC 3339 UTC time with milliseconds |
| `actor`, `actor_identity` | the run's actor when it ended (§5.17, §5.14.1): `actor` is its `kind`; without one, `actor` is `agent` and `actor_identity` is absent |
| `intent` | `run ` followed by the root workflow's name |
| `status` | `executed` for `Completed`, except `planned` when its outcome is `deferred` (the run can still be resumed or cancelled); `cancelled` for `Failed` with code R408; `failed` for any other `Failed` |
| `code`, `reason_code`, `checkpoint_id` | the `Failed` action's `code`, `reason` and `checkpoint_id`, when it has them |
| `details` | `kind`; `outcome`, `cause` and `ended` (for `Completed`); `message` (for `Failed`); `deferred`; and `records`, the number of action records the run wrote, taken ones included |

Every host that runs workflows MUST keep, when a run ends, its run record
and the run's action records (those in the terminal action and those it
took, §5.19.4) where it keeps its audit records, before it discards the
run's state. A run that ended `deferred` and is resumed (§5.14.1) or
cancelled (§5.19.5) ends again; the host then replaces its run record, which
keeps its `action_id`. An executor MAY derive the run record for the host.

### 5.20 Grounding

```yaml
spec_version: "1.2"
workflow_extensions:
  requires: [grounding@1]
grounding:
  require: [classify, predict, generate]
  kinds: [file, record, x-lab_result]
  attested: true
```

With `grounding@1` declared, a workflow MAY state a **grounding policy** in
`grounding`:

| Field | Description |
|-------|-------------|
| `require` | Required: the capabilities whose outputs are checked, a non-empty list of distinct ontology ids |
| `kinds` | A non-empty list of distinct anchor kinds (§6.5): only anchors of these kinds count |
| `attested` | Boolean, default false. When true, an anchor counts only when its availability is established: an `acs:` anchor (checked as below) or one whose `ref` the host lists in `evidence_seen` |

In a workflow that targets 1.2 or later (§11.5), `grounding` without the
declaration is V106; in one that targets an earlier version or declares
none, it is an unknown field (W604), as in 1.1. With the declaration, a
`grounding` that is not a mapping, a `require` or `kinds` that is not a
non-empty list of distinct strings, a kind outside §6.5's vocabulary and an
`attested` that is not a boolean are S303; a missing `require` is S304; an
id in `require` that the ontology does not define is V101; unknown fields
are W604. A workflow's policy applies to the workflow's own steps, not to
the steps of a workflow it invokes.

A host MAY also apply grounding policies, of the same three fields, to a
run, by giving a list of them when it starts the run (§5.19.2), and a
safety layer to the calls it covers (below). A policy a host applies to a
run applies to the steps of the run's nested runs (§5.12) as well as its
own. A host refuses a policy whose `require` names a capability the
ontology does not define, as a validator does (V101), rather than apply it
to nothing, and one with a member other than the three and extension
members `x-...`, which a misspelt `kinds` or `attested` would be. A domain
profile's `evidence_policy` states one:
`require_grounding` is its `require` and `required_anchor_types` its
`kinds`. Each policy that requires a step's capability applies on its own:
the output must pass every one.

**The check.** When a host answers a step's `InvokeCapability` with an
`Output` (§5.19.1), and a policy requires the step's capability, the
executor checks the output after the fields its contract requires (a
missing one is R402) and before its after-gates. A `delegate` step that
waits (§5.13) is not checked: its `Output` is the delegation's acceptance,
not its claim, and its result is an output the executor composes; a policy
that requires `delegate` covers the delegations that do not wait. The
`Output` MAY carry `evidence_seen`: a list of the `ref`s of the evidence
the host attests the output's producer had for this answer (§6.5): what it
put in the request a model answered, the anchors inside the step's inputs,
and what the step's tool calls returned. It lists nothing the producer did
not receive for this answer, such as an item of a stored history that the
request did not carry. An absent `evidence_seen` attests nothing; an empty
one attests that the producer had no evidence.

A reference (§5.3) B **covers** a reference C when they have the same root
and each segment of B's path matches the segment of C at the same
position: the same field name or the same index, or, where B's segment is
a slice, an index within it or a slice within it (indices count, for both,
from the start of the array the path names before the slice). C may go on
past B's path. For instance, `search_out.results[0:3]` covers
`search_out.results[1]` and `search_out.results[1].url`, but not
`search_out.results[7]`, `search_out.total` or `search_out`.

The executor reads `evidence_anchors`:

1. A value that is not a list fails the step: F505.
2. An item that is an object whose `ref` is a string starting with `acs:`
   cites a workflow value (§6.5). Its `kind` MUST be `record`, and the rest
   of its `ref` MUST be a reference body (§5.3, without `${`, `}` and a type
   annotation) that one of the references in the step's `input_bindings`
   covers; otherwise the step fails: F505. Its availability is established.
3. Any other item that is an **evidence anchor** (an object whose `ref` is
   a non-empty string and whose `kind` is in §6.5's vocabulary, with a
   `digest`, when present, of §6.5's form): when the `Output` carries
   `evidence_seen` and does not list its `ref`, the step fails: F505; when
   it lists it, its availability is established.
4. Any other item (a bare string, or an object that is not an evidence
   anchor, the deprecated forms of §6.5) does not count, and is not itself
   a failure.
5. An anchor of items 2 and 3 **counts** when its kind is in the policy's
   `kinds` (when the policy has them) and, under `attested`, its
   availability is established.

The output passes when at least one anchor counts: this Standard grounds an
output as a whole, and does not say which anchor supports which field.
Otherwise it MUST be marked inferred, with an `inference_method` of §4.1.1's vocabulary and a
`confidence` from 0 to 1, or the step fails: F505. F505 is not retried
(§5.2); a failure mode can fire on it (§5.12).

Outputs the executor builds itself (an `invoke` step's, a quorum's, the
output of a wait, and the result of a `delegate` step that waits; §5.12,
§5.13, §5.16) are grounded in the run's own records and are not checked.
With
`grounding@1` declared by the workflow a completed `invoke` step belongs
to, the step's `evidence_anchors` are the anchors of the outputs its nested
run stored, in the order of its steps, each `ref` once, and without `acs:`
anchors, which name the nested run's values; without the declaration they
are empty, as in 1.1.

**Hosts outside a workflow.** A safety layer (§5.18), or any host that runs
capabilities as calls without a workflow, applies the grounding policies
its configuration names to the output of each call whose capability one
requires, as above. An `acs:` anchor names an argument of the call
(`acs:<argument>`, or a path within it): each argument the call received
counts as a reference the call binds. A layer that knows what was in the
request the output answers gives that as `evidence_seen`; a layer that does
not know the request gives none (absent, not an empty list). It refuses an
output that fails with F505 (§5.18.8); the call has run, and the refusal is
what its caller is told.

### 5.21 Domain Profiles

A **domain profile** states, for one domain, rules that tighten what this
Standard requires of steps and calls: which need a checkpoint, which need
approval and from whom, what counts as evidence, how confident an output
must be, where a `send` may go and how sources are weighed. A profile is a
YAML or JSON document of the shape `schemas/profiles/profile_schema.yaml`
gives. The profiles under `schemas/profiles/` are examples.

#### 5.21.1 Applying Profiles

A profile has effect only where it is **applied**:

- A host applies profiles to a run by giving them when it starts the run
  (§5.19.2). They apply to every step of the run, the steps of its nested runs
  included (§5.12), and stay with the run when it is saved and restored
  (§5.19.4). They do not apply to the runs of the agents it delegates to
  (§5.15), which those agents' hosts govern.
- A safety layer (§5.18) applies the profiles its configuration names to
  every call it covers.
- A validator MAY be given profiles. It then validates each workflow with the
  effective flags of §5.21.3, so that F501, W606 and W608 see what a run under
  those profiles would; nothing else changes. Without profiles it validates as
  if none were applied.

A workflow does not select a profile. Its `profile` field (§5.1) records the
profile it was written for and applies nothing; a host MAY use it to choose
the profiles it applies. A workflow that needs a checkpoint or an approval
wherever it runs declares the flag itself (§5.2.1). Whether a step may carry
an `approval` field (§5.14) does not depend on profiles: declare
`requires_approval: true` on a step whose approval only a profile would
require, to say how it is asked.

Several profiles MAY be applied together. Each applies on its own: a step or
call meets every one, so the strictest result holds. For flags, checks,
evidence, confidence and destinations a profile only tightens: it never
lowers a flag, never removes a check and never changes a step's `risk` or
`mutation`. Its `trust_weights` are different: they replace weights, higher
or lower, as §8.3 says, bounded by §8.3's rule that evidence with both a
source type and a trust class weighs the lower of the two; with several
profiles, the lowest weight given to a key applies.

#### 5.21.2 Loading a Profile

An implementation checks a profile before it applies it, and refuses a
profile with an error: an executor does not start the run, a safety layer
does not load its configuration, a validator reports the errors. A
diagnostic about a profile has `location.profile` (its `domain`, or `#<i>`,
its zero-based position among the profiles given, when it has no valid
`domain`) and `location.field` (the path to the member, such as
`risk_thresholds.block_autonomous[1]`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `domain` | string | Yes | Lower-case letters and digits, starting with a letter, in words joined by single `-` |
| `version` | string | Yes | The profile's own version, `MAJOR.MINOR.PATCH` |
| `standard` | string | No | The Standard version the profile is written for (§11.6) |
| `ontology` | string | No | The ontology version the profile is written for (§11.6) |
| `trust_weights` | object | No | Keys to numbers from 0 to 1: `trust_class:<class>`, where `<class>` is a trust class of `agent_identity_schema.yaml`, or a source key: a lower-case letter, then lower-case letters, digits, `_`, `.` or `-` |
| `risk_thresholds` | object | No | Exactly these members, each optional: `auto_approve` (`none`, `low`, `medium` or `high`), `require_review` and `require_human` (the same four), `block_autonomous` (a list of capability ids) |
| `checkpoint_policy` | object | No | `*`, or a capability id other than `checkpoint`, to `always`, `high_risk`, `medium_risk` or `never` |
| `evidence_policy` | object | No | Exactly these members, each optional: `required_anchor_types` (a non-empty list of distinct anchor kinds, §6.5), `minimum_confidence` (a number from 0 to 1), `require_grounding` (a list of distinct capability ids) |
| `allowed_destinations` | array | No | A destination policy (§4.4.2) |
| `description` | string | No | Informative; no effect |
| `domain_sources` | array | No | Informative; no effect |
| `workflows` | array | No | Informative; no effect |
| `trust_model_reviewed` | boolean | No | Informative; no effect |
| `trust_model_reviewed_at` | string | No | Informative; no effect |
| `compliance` | object | No | Informative; no effect |

| Code | A profile is reported when |
|------|----------------------------|
| S303 | It is not a mapping, or a member is of the wrong type or outside its grammar: a `trust_class:` key whose class is not a trust class, a kind outside §6.5, an invalid destination pattern, the `checkpoint_policy` key `checkpoint`, a member of `risk_thresholds` or `evidence_policy` that the table does not list, whatever its name (both mappings are closed), or a member, `x-` ones included, that is not I-JSON (RFC 7493), such as an integer beyond 2^53 |
| S304 | Its `domain` or `version` is missing |
| V101 | A capability id in `block_autonomous`, in `require_grounding` or as a `checkpoint_policy` key other than `*` is not one the ontology defines |
| V109 | Its `standard` is not one the implementation supports, or its `ontology`'s major differs from the implementation's ontology's (§11.6) |
| W604 | A top-level member is not one the table lists; it is ignored. A member whose name starts with `x-` is never reported |
| W602 | Its `checkpoint_policy` gives `never` for a capability the ontology requires a checkpoint before (by `requires_checkpoint`, or a `checkpoint` `requires` edge as for `rollback`); it has no effect |
| W603 | Its `require_review` or `require_human` is `critical`, which is deprecated and read as `none` |

#### 5.21.3 Effect on Steps and Calls

For a step, or a call classified by §5.18.3, let C be its capability and R
its effective risk (§5.2.1, before profiles). A threshold covers a set of
risk levels: `auto_approve: L` covers L and the levels below it,
`require_review: L` and `require_human: L` cover L and the levels above it,
and `none` covers no level (`low` < `medium` < `high`). Each applied profile
raises:

| Member | Raises | Code |
|--------|--------|------|
| `risk_thresholds.auto_approve` | `requires_approval` when R is not covered | F502 |
| `risk_thresholds.require_review` | `requires_approval` when R is covered | F502 |
| `risk_thresholds.require_human` | `requires_approval`, and requires **a person**, when R is covered | F502, W606 |
| `risk_thresholds.block_autonomous` | `requires_approval`, and requires a person, when C is listed | F502, W606 |
| `checkpoint_policy` | `requires_checkpoint` when C is not `checkpoint` and the value for C or for `*` is `always`, is `high_risk` and R is `high`, or is `medium_risk` and R is `medium` or `high` | F501 |

An absent member raises nothing. The raised flags are effective flags
(§5.2.1): a step whose `requires_checkpoint` a profile raised needs a
`checkpoint` running before it (F501) and uses a valid checkpoint before it
runs (§4.4.1); one whose `requires_approval` a profile raised is asked for
approval (§5.14), fails without a valid decision (F502), and counts as a
step that acts in §5.14's deferral rules.
A `checkpoint` step is never given `requires_checkpoint` by a profile: it
would need a checkpoint before itself.

**A person.** A step that a profile requires a person for is asked as a step
that uses an always-ask item is asked (§5.17): the request names a `human`
approver, with `always_ask: true` and no `mandate_ref`, whatever its
`approver` declares; a standing mandate does not cover it, and the decision
is recorded with no `mandate_ref`; in an unattended run it is not asked, and
its `when_unattended` applies (W606 where an unattended trigger reaches it
without one, §9.7). The requirement belongs to that step alone. It is not a
mark (§5.17): it does not pass to the step's output or to the steps that
read it, to the nested runs the step starts, or to context injected for
recovery (§5.12), each of which a profile governs by its own capability and
risk. The step's action records carry `person_required: true`
(`ActionRecord`, `world_state_schema.yaml`); they carry `always_ask: true`
only if the step also uses an always-ask item. A safety layer accepts for
such a call only a decision a person made for it. Since a composite's
approval covers its nested calls (§5.18.4), a composite that lists a binding
a profile requires a person for, directly or through another composite, is
itself asked of a person, and a composite's approval no person gave covers
no nested call that needs one.

Each applied profile also puts in force:

| Member | In force as | Code |
|--------|-------------|------|
| `evidence_policy.require_grounding` | A grounding policy (§5.20) applied as a host's, with `required_anchor_types` as its `kinds`: an output of a step whose capability it lists must pass it. `required_anchor_types` alone has no effect | F505 |
| `evidence_policy.minimum_confidence` | A minimum for the `confidence` member of an output a host returns for a step; with several profiles, the highest applies | F504 |
| `allowed_destinations` | A destination policy (§4.4.2) beside the host's own, so a send must be allowed by each; an empty list allows no send | F504 |
| `trust_weights` | Weights that override the trust model's where a host computes trust scores for the run's evidence (§8.3) | — |

**Minimum confidence.** When a minimum applies and an output has a
`confidence` member, that member MUST be a number from 0 to 1: one that is
not (a string, `null`, a boolean, a number outside the range) fails the step
with F504 and the reason `invalid_confidence`; one below the minimum fails it
with F504 and the reason `below_minimum_confidence` (§5.19.7). An output
without a `confidence` member is not checked: a capability whose contract
requires one already fails such an output (R402), and one whose contract
does not require it reports no confidence to compare. The check comes after
the grounding check and before the step's after-gates; outputs the executor
builds itself are not checked (§5.20).

A safety layer that applies a profile applies these to the outputs of the
calls it covers, as §5.20 says for hosts outside a workflow.

#### 5.21.4 Conformance

An implementation that applies profiles (an executor, a safety layer, or a
validator given them) MUST report each profile vector's diagnostics and
compute each one's effective flags and rules (§10.3). An executor or a
safety layer that does not put a rule of §5.21.3 in force (a safety layer
that checks no output, say) refuses a profile that sets it, as it refuses a
profile with an error, rather than apply the profile without it. A validator
applies only the flags (§5.21.1) and refuses no profile for the other rules.

---

## 6. Canonical Schemas

### 6.1 Required Schema Files

| Schema | Purpose |
|--------|---------|
| `world_state_schema.yaml` | World state structure |
| `event_schema.yaml` | Event and observation structure |
| `entity_taxonomy.yaml` | Entity type hierarchy |
| `authority_trust_model.yaml` | Trust scoring configuration |
| `identity_resolution_policy.yaml` | Identity resolution rules |

Supporting schemas that specific sections use, not required of every
implementation: `review_verdict_schema.yaml` (§5.16),
`agent_identity_schema.yaml` 1.1.0 (§5.17), `agent_manifest_schema.yaml`
1.0.0 (§5.15.1), `host_protocol.schema.json` (§5.19, required for class EX,
§10.5), `interop/tool_binding.schema.json` (§5.18.1, required for class SL,
§10.4), `interop/evidence.schema.json` (§6.5, §6.6) and
`profiles/profile_schema.yaml` (§5.21, the shape of a domain profile).

### 6.2 Observation Requirements

Field names in this section are those of the `event` object in
`event_schema.yaml`. They belong to the **canonical-event namespace**, which is
distinct from the capability-I/O namespace of §4.1 — a capability's
`evidence_anchors` output and an event's `anchors` field are different
fields; the items of both are evidence anchors (§6.5).

All canonical events MUST record:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_id` | string | Yes | Unique event ID |
| `timestamp` | string | Yes | ISO-8601 time of observation |
| `source` | object | Yes | Where observed (`kind`, `name`) |
| `event_type` | string | Yes | Normalized event type |
| `raw` | any | Yes | Original data, unmodified except that each secret is replaced (§6.7) |
| `canonical` | object | Yes | Normalized data |
| `anchors` | array | Yes | Links to original evidence |
| `provenance` | object | Yes | Traceability record |

An event MAY also record `redactions`: the JSON pointers (RFC 6901), from
the event, of the members in which a secret was replaced by `[REDACTED]`
(§6.7). Without it, a consumer still finds the marker where the loss is.

Projecting a canonical event into `world_state.observations[]` narrows it to
the `ObservationEvent` type, whose `payload` carries the event's `canonical`
value. `transform_mapping_rawlog_to_observation.yaml` defines that projection.

### 6.3 World State Requirements

Field names in this section are those of `world_state_schema.yaml`. Snapshot
identity and derivation live under `meta`, not at the top level.

World state snapshots MUST record:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `meta.world_id` | string | Yes | Namespace for the modelled world |
| `meta.as_of` | string | Yes | ISO-8601 time the snapshot describes |
| `meta.timezone` | string | Yes | IANA timezone |
| `meta.version_id` | string | Yes | Unique snapshot ID |
| `meta.parent_version_id` | string | No | Previous snapshot (null for initial) |
| `meta.lineage` | array | Yes | Ordered ancestor version IDs |
| `entities` | array | Yes | Current entity states |
| `relationships` | array | Yes | Entity relationships |
| `state_variables` | array | Yes | Observed state variables |
| `observations` | array | Yes | Observations this state derives from |
| `transition_rules` | array | Yes | Rules governing state transitions |
| `actions` | array | Yes | Action records |
| `indexes` | object | Yes | Lookup indexes |
| `retention_policy` | object | No | How long the store that holds them keeps observations, audit logs and snapshots; durations as §5.10.1 |

Retention applies to the store the records are written to (§6.6). A store
whose durability is `memory` or `session` cannot keep a record beyond its
process or session, whatever a retention says; a host that must keep
records longer exports each one, when it writes it, to a `durable` store.
An `audit` step's `retention` is a duration (§5.10.1) asking how long the
record it writes is kept; absent, the store's own policy applies, and a
literal outside the grammar is W614. Its host SHOULD report where the
record went in the output's `store`: the store's `name`, its `durability`
and the `retention` it applies. A host whose store does not outlive the
session MUST NOT report it as `durable`, so a workflow that needs a durable
record can stop on `${a.store.durability} != 'durable'`.

An action record or a provenance record may carry the identity of who
acted (`actor_identity`, `agent_identity`; §5.17), and an action record's
approval the identities of the approvers that counted
(`approval.approver_identities`; §5.17). An action record is also an audit
record (§6.4).

### 6.4 Audit Records

An **audit record** says what happened. It is one of:

- an **action record** (`world_state_schema.yaml#/types/ActionRecord`): an
  action an agent took, was refused, or deferred, whether a step of a run or
  a call on a tool-calling host (§5.18); or
- a **canonical event** (`event_schema.yaml#/event`, §6.2): something
  observed.

An implementation that writes audit records (an executor's action records,
a safety layer's records of calls, §5.18.8, the record an `audit` step
writes, a run record, §5.19.8, a host's log of what it did) writes them in,
or exports them as, one of these shapes: it may keep its own form
internally, provided it can give each record in one of these shapes. An
executor's trace of its own decisions is not an audit record; its form is
the executor's own.

**An executor's records.** An executor writes an action record for each step
that requires approval (§5.14). Started in record mode `actions`, it also
writes one for each pass of each step that runs, whatever its flags (a
retry is the same pass; a recovery loop that runs the step again starts
another): `executed` when the step has its output, `failed` when it fails
after it started, or when the checkpoint it needs cannot be taken (F501),
and `cancelled` when the run is cancelled after the step started (§5.19.5);
and one for each checkpoint a failure mode takes (`pause_and_checkpoint`,
`capability: checkpoint`) and each `Rollback` it asks for (`capability:
rollback`), `executed`, `failed` (F501, F503) or `cancelled`. The default
mode, `approvals`, writes only the first kind. An executor MUST offer both
modes. Each record an executor writes carries `run_id`, `frame`, `step` and
`capability`; as `intent`, the step's `purpose`; as `timestamp`, the run's
clock when the record was first written; `checkpoint_id`, when the action
used, took or restored a checkpoint; `code` (§9) and, where the failure had
one, `reason_code` (§5.19.7), when the action failed or was refused or
cancelled; and, in its `approval`, the `decision_id` of the decision. A
record of a step that an applied domain profile requires a person for
carries `person_required: true` (§5.21.3); `always_ask: true` says only
that the action used an item from an always-ask trust class (§5.17).

**The `audit` capability.** An `audit` step records its `event`. The
implementation performing the step writes an action record of its own:
`capability: audit`, status `executed`, `intent` the event's `intent` or
`event_type` when it is a string, else `audit`, and the event, whatever its
shape, as `details.event` (with the step's `context` and `retention`, when
bound, as `details.context` and `details.retention`). When it performs the
step for a run it SHOULD set `run_id`, `frame` and `step` from the action.
It MUST set `recorded_by` to itself, replacing any value the event offers,
and MUST compute any chain fields (below) itself; no member of the event
becomes a member of the record. So an event that has the shape of an action
record or a canonical event is kept as given, but under `details.event`: it
is what the step reported, not a record the implementation vouches for, and
it cannot claim another writer, an actor, an approval or a place in a
chain. The step's output `record` is the record written, and `recorded`
says whether it was written. A step that binds `require_record: true` fails
with R402, reason `not_recorded`, unless its output's `recorded` is `true`.
Without it the step completes when the record was not written, and a later
gate or failure mode may read `recorded`.

**Required and best-effort capture.** The records this Standard requires are
required: an executor keeps its records in the run's state (§5.19.4), a host
keeps each run's record (§5.19.8), and a safety layer that cannot write the
record of a call refuses the call (§5.18.8). Any other capture a host makes,
such as evidence anchors taken from tool results or a log of tool calls, is
best-effort unless the host states that it is required. A host that
requires a capture and cannot make it reports the failure where the
action's result goes: for a step, R402 with reason `not_recorded`; for a
call that has already run, in what the caller is told of the call. A
best-effort capture that fails MUST still be reported where the host's
operator sees it, such as an error the host shows: it may miss a record,
but never silently.

**Who wrote it.** A record MAY name the implementation that wrote it and the
configuration it applied: `recorded_by`, with `name`, `version` and
`config_sha256`. An implementation sets `recorded_by` only to itself.

**Integrity.** A store that keeps audit records as an append-only log SHOULD
chain them: each record carries `prev_hmac`, the `hmac` of the record before
it (the empty string for the first), and `hmac`, the HMAC-SHA-256 under the
store's key of the record without `hmac`, as 64 lowercase hexadecimal
digits. The store computes both when it appends the record, whatever the
record offered. The store documents how it serialises the record for the
MAC.

### 6.5 Evidence Anchors

An **evidence anchor** names one piece of evidence. It is the item of a
capability output's `evidence_anchors` (§4.1.1), of a canonical event's
`anchors` (§6.2) and of the `anchors` of world-state records (§6.3): one
type, `event_schema.yaml#/types/Anchor`, which `world_state_schema.yaml`
repeats.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ref` | string | Yes | Where the evidence is: a non-empty string |
| `kind` | string | Yes | What kind of evidence it is (below) |
| `timestamp` | string | No | ISO-8601 time at which the producer read or observed it |
| `excerpt` | string | No | A short quotation of it, as the producer read it; never a secret (§6.7) |
| `digest` | string | No | `sha256:` and the 64 lower-case hexadecimal digits of the SHA-256 of its content as the producer read it: the bytes `ref` names or, for a JSON value, its canonical JSON (RFC 8785) in UTF-8 |

Other fields MAY appear; a producer's own SHOULD start with `x-`.

**Kinds.** `file`; `url`; `tool` (the result of a tool call); `log`;
`sensor`; `human_note` (something a person wrote); `api` (a response of a
service's API); `record` (a record the agent system itself wrote or holds:
an action or audit record, a checkpoint, a memory item, a workflow value);
or a vendor kind: `x-` followed by a lower-case letter or digit, then
lower-case letters, digits, `_`, `.` or `-`. A domain profile's
`required_anchor_types` and a grounding policy's `kinds` (§5.20) list kinds
of this vocabulary.

**Refs.** A `ref` is opaque to this Standard: a URI, or `<scheme>:<rest>`
with a scheme its producer documents (for instance `file:src/app.py#L10-L20`
or `tool:Read:toolu_01`). The scheme `acs:` is reserved: `acs:` followed by
a reference body as §5.3 writes it without `${` and `}` (for instance
`acs:search_out.results[0]`), with no index above 2^53 − 1 (I-JSON), names
a workflow value, the one a binding with that body would resolve to in the
run, and its kind MUST be `record`.
Outside a workflow, `acs:<argument>` names an argument of the call (§5.20).

**Available evidence.** An anchor grounds a claim only if the evidence it
names was available to the claim's producer (§3.1): obtained while the step
or call ran (a tool's result, a file it read), received as input (a value
the step's bindings pass, §5.3, including the anchors inside it), or put in
the request a model answered. A host MUST NOT return an anchor it knows its
producer did not have, such as a model's citation of a stored item the host
did not put in the model's request; a host that assembles a model's context
for each request SHOULD check each anchor a model cites against that
request. An `acs:` anchor names a workflow value, which an executor can
check; a host attests the availability of other evidence with
`evidence_seen` (§5.20).

**Anchors of actions.** An output that reports an action its producer
performed (a checkpoint taken, a rollback, a mutation, a message sent, a
command run, an audit or memory record written) has the evidence of that
action because it performed it. It is grounded by an anchor to the action's
record, of kind `record`, with a ref its producer documents (for instance
`checkpoint:<checkpoint_id>`, `audit:<audit_id>`, `mutation:<target>`), or
by an anchor to what the action read or wrote (the file it changed).

**The legacy forms.** Before 1.2 an item of `evidence_anchors` was not
specified: producers wrote bare strings, and objects of their own shape
(without a `kind`, or with a kind outside this vocabulary, such as
`tool_output`). Both are still accepted there: a string reads as an anchor
with that `ref` and no kind, and an object that is not an evidence anchor as
its producer's own citation. Neither counts toward a grounding policy
(§5.20), and neither is refused for its shape: no implementation refuses an
output because of the shape of its `evidence_anchors` items unless a
grounding policy applies, and under one such an item only does not count.
Both are deprecated, and the next major version removes them (§11.2). A
producer SHOULD write evidence anchors. No validator can see an output, so
this deprecation is announced here rather than by W603. The items of an
event's or a record's `anchors` are evidence anchors.

### 6.6 Evidence Records and Stores

An **evidence record** is an evidence anchor kept with the context it was
recorded in. `schemas/interop/evidence.schema.json` defines it
(`EvidenceRecord`); the optional fields are present where they apply.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `record_id` | string | Yes | Unique within its store |
| `anchor` | object | Yes | The evidence anchor kept (§6.5) |
| `recorded_at` | string | Yes | ISO-8601 time at which the store kept it |
| `run_id` | string | No | The run (§5.19), or for a call the safety layer's scope (§5.18) |
| `frame` | array of strings | No | For a step, the workflows of its nested runs, root first |
| `step` | integer | No | For a step, its index in the last workflow of `frame` |
| `capability` | string | No | The capability whose output cited the anchor |
| `tool` | string | No | For a call, the name the host offers the tool under |
| `call_id` | string | No | For a call, the host's identifier of the call |

An **evidence store** keeps evidence records for later reading. This
Standard requires none. An implementation that offers one:

1. appends records, never changes or reorders a record it has kept, and
   never gives a record the `record_id` of another, including one it has
   removed;
2. returns a record by its `record_id`, and the records whose `capability`,
   `anchor.kind` or `run_id` match a given value, in the order they were
   appended;
3. exports its records as JSON Lines, one `EvidenceRecord` per line, in the
   order they were appended;
4. states its **durability**: `memory` (its records are lost when its
   process ends), `session` (deleted with the session, conversation or
   thread they belong to) or `durable` (kept until its retention removes
   them, §6.3); and whether it is **bounded**, that is, removes records
   before their retention ends to stay within a size. A store that removes
   records other than by their retention (because it is bounded, or when it
   is cleared) counts them and reports the count with what it exports
   (`StoreInfo.removed`).

A host whose evidence must outlive the session SHOULD NOT rely on a
`memory` or `session` store: it exports each record, when it is written, to
a `durable` one.

Evidence records are not audit records (§6.4). A run's audit records go to
whatever implements its `audit` steps and to where the host keeps the
executor's records (§5.19.4); a host MAY keep evidence records and audit
records in one store.

**Notification.** When a host stores evidence records, a canonical event
(§6.2) or audit records (§6.4), it MAY notify its clients with an
`EvidenceRecorded` payload (`schemas/interop/evidence.schema.json`): `type`
`acs.evidence_recorded`; what was stored: the evidence records'
`record_ids`, the canonical event's `event_id`, or the audit records'
`action_ids`; the `anchors` of what was stored, each as its `ref`, `kind`
and `digest` (an audit record's own `anchors`, possibly none); and, where
they apply, `capability`, `run_id`, `frame`, `step`, `tool`, `call_id`, and
`recorded_at`. A notification is not a record: it MAY be delivered at most
once, and a client that needs the evidence or the record reads the store.
It carries no `excerpt` and no secret (§6.7).

### 6.7 Secrets in Records

A **secret** is a value that grants access or proves identity (a password,
an API key or token, a session cookie, a private or signing key, a
credential inside a URL or a header), and any value the host or its
operator classifies as secret. How a host recognises secrets is its own
choice; it SHOULD at least recognise the credentials it holds itself.

**Where secrets never go.** An implementation MUST NOT write a secret into:

- an evidence anchor, an evidence record or a notification (§6.5, §6.6);
- a canonical event (§6.2) or a world-state record (§6.3);
- an audit record (§6.4) or a safety layer's record of a call (§5.18.8);
- a diagnostic (§9.8), or the `message` or `reason` of an `Error` a host
  returns (§5.19.1), which reach a run's diagnostics, trace and records;
- an executor's trace;
- the data a `persist` step or call stores.

**Redaction.** An implementation that would write a value holding a secret
into one of these redacts it: it replaces each secret, or the part of a
string that is one, with the string `[REDACTED]`, or leaves out the member
or the anchor that holds it. Redaction is a transform with documented loss
(§3.2): the marker shows where the loss is, and a canonical event MAY list
the members it changed in `redactions` (§6.2), its `raw` then being the
original with its secrets replaced. A record MAY hold, in place of a value
that contains a secret, the SHA-256 digest of the whole value (a tool's
whole input, say), so that a reader who has the value can confirm it; it
MUST NOT hold the digest of a secret alone, which guessing can invert. An
implementation that cannot tell whether such a value is more than the
secret it holds (a file's whole content, a tool's whole response) keeps no
digest of it.

Data a `persist` step or call would store that holds a secret the host
recognises is refused, not redacted, since memory is read back as fact:
a tool-calling host refuses the call with F504 (§5.18.8); a host answering
a step returns an `Error` with reason `secret_in_data` (§5.19.7), and the
step fails with R402.

**Workflows carry no secrets.** A catalog MUST NOT contain a secret. A host
SHOULD NOT pass one through a run's inputs or a step's output, since a
run's values are kept in its state and snapshots and reach records through
bindings: it adds a credential where it is used, to the request a
capability makes. The values an approval request shows (§5.14) are what the
approvers decide on; an approval channel MAY display them with secrets
replaced, saying so, and the digest stays that of the values.

---

## 7. Identity Resolution Policy

### 7.1 Entity Identification

An entity's id (`Entity.id` in `world_state_schema.yaml`, and an
`EntityRef`'s `entity_id`) is written `<class>:<namespace>/<local_id>`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `class` | string | Yes | The entity's `type`: a class name or alias of `entity_taxonomy.yaml` (`service` or `svc`, `person`, `sensor`, …), or a vendor class, `x-` followed by a lower-case letter or digit and then lower-case letters, digits, `_` or `-` |
| `namespace` | string | Yes | One or more segments separated by `/`, outermost first, which with the class make the id unique within the world (`meta.world_id`). The taxonomy's `namespace_components` (organisation, domain, environment, system, subsystem) is the recommended order: an id SHOULD use those that apply, in that order, and MAY add segments of its own (`person:acme/hr/employee/12345`). The grammar does not check what a segment means |
| `local_id` | string | Yes | The entity's identifier within the namespace: one segment |

A segment is one or more characters, none of them `/`, `:`, white space (a
character JSON Schema's `\s` matches, U+00A0, U+2028 and U+FEFF among them)
or a control character (U+0000–U+001F, U+007F–U+009F); percent-encode them
(RFC 3986). An id therefore has exactly one `:`, and at least one `/` after
it. Ids are compared as strings, case-sensitively. `id_convention.pattern` in `entity_taxonomy.yaml` is the
grammar; the entity id vectors (§10.3) fix it.

```
svc:acme/payments/prod/api
host:acme/oslo/cluster-a/node-7
sensor:acme/factory/line-3/temp-02
person:org.company/user/12345
```

Versions 1.0 and 1.1 printed the form `namespace:type:id` here, with the
example `org.company:user:12345`, while `entity_taxonomy.yaml` already gave
the form above; the last example is that id written in it. No
implementation checked either form.

### 7.2 Alias Confidence Scoring

Alias matching MUST use weighted feature scoring:

| Feature | Weight Range | Description |
|---------|--------------|-------------|
| Exact match | 1.0 | Identical identifiers |
| Fuzzy match | 0.0-0.9 | Similar but not identical |
| Cross-reference | 0.5-1.0 | Linked by another source |
| Temporal proximity | 0.0-0.5 | Close in time |

### 7.3 Merge/Split Rules

- Merge: Combine two entity records into one
- Split: Divide one entity record into multiple

Hard constraints that MUST NOT be violated:
- Never merge entities with conflicting unique identifiers
- Never merge across incompatible entity types
- Always record merge/split in lineage

---

## 8. Authority Trust Model

### 8.1 Trust Score Calculation

The **trust score** of a piece of evidence is a number from 0 to 1:

```
score = weight × confidence × decay
```

computed in that order in binary64 arithmetic, where:

| Factor | Value |
|--------|-------|
| Source ranking: `weight` | The evidence's static weight (§8.3) |
| Confidence weight: `confidence` | The confidence the source reports (§4.1.1), from 0 to 1; 1 when it reports none |
| Time decay: `decay` | `max(0.5 ** (age / half_life), min_trust)`, or `0.5 ** (age / half_life)` when the model sets no `min_trust` |

- `half_life` is `decay_model.half_life` of `authority_trust_model.yaml`: a
  duration of whole days, `P<n>D` with `n` at least 1. `age` is the time from
  the evidence's timestamp to the time the score is computed, in the same
  unit. An age below zero (evidence dated after that time) counts as zero.
- Time decay MUST be a true half-life: before the floor, the factor for an
  age of one half-life is exactly `0.5`. (An exponential time constant,
  `exp(-age / half_life)`, gives 0.368 there and does not conform.)
- `decay_model.min_trust` is a floor on the decay factor only: not on the
  static weight and not on the score. Age alone therefore never takes
  evidence's weight to zero; it only removes its advantage over fresher
  evidence. A floor above 0.5 holds the factor at the floor from the age at
  which the curve reaches it.
- A weight, a confidence or a `min_trust` outside 0 to 1, or a half-life of
  another form, makes the model or the evidence invalid, and an
  implementation refuses it. Evidence without a static weight (§8.3) has no
  score: an implementation MUST NOT give it one.

**Field authority** is not a factor of the score: the trust model's
`field_authority.fields` names, for a field, the source types that are
authoritative for it, and §8.2 ranks them first. (`field_authority.examples`
is illustrative and is not read.)

### 8.2 Conflict Resolution

When **candidates** give different values for one field of one entity, a
strategy resolves the conflict. Each candidate has its evidence: a source
type, a trust class or both (§8.3), an age and a confidence. A strategy
either chooses one candidate (`chosen`), keeps all of them (`merged`) or puts
the conflict to a person (`escalated`):

| Strategy | Result |
|----------|--------|
| `highest_score` (default) | The candidate with the highest trust score (§8.1) |
| `prefer_authoritative_sources` | Where some candidates' source types are authorities for the field (`field_authority.fields`), only those compete; of the competing candidates, the one with the highest static weight |
| `prefer_recent` | The candidate with the lowest age |
| `prefer_high_confidence` | The candidate with the highest confidence |
| `merge_with_uncertainty` | `merged`: every candidate with its score, highest score first, candidates of equal score in the order given |
| `escalate_to_human` | `escalated`: no candidate is chosen |

**Ties.** Values within 10⁻¹² of each other are equal. When several
candidates are best by the strategy, the model's
`conflict_resolution_function.tie_breakers` apply to them in order:
`prefer_authoritative_source` keeps those whose source type is an authority
for the field, if any is; `prefer_high_confidence` those with the highest
confidence; `prefer_recent` those with the lowest age; `escalate_to_human`
stops. If more than one candidate remains, the conflict is `escalated`.
Whatever the strategy, a conflict with one candidate chooses it, and one in
which a candidate has no static weight is refused: it is not resolved by
leaving the candidate out.

A capability that resolves conflicts names its strategy (`integrate`'s
`conflict_resolution`); absent, the strategy is `highest_score`. The
conflict resolution vectors (§10.3) fix these results.

### 8.3 Trust Classes and Static Weights

`authority_trust_model.yaml` gives each source type a weight
(`source_ranking.weights`) and each sender trust class of §5.17 a default
weight (`trust_classes.weights`); the classes are exactly those of
`agent_identity.trust_class`. The **static weight** of evidence is:

- with a source type only: the source type's weight;
- from an item whose sender's identity has a trust class, with no source
  type: the class weight;
- with both: the lower of the two, so a trusted channel cannot lift an
  untrusted sender;
- with neither, with a source type that has no weight, or with a trust class
  the model does not have: none.

A domain profile applied to the run (§5.21) overrides weights with
`trust_weights`: the key `trust_class:<class>` replaces the weight of that
class, kept apart from a source key of the same name; any other key replaces
the weight of the source type it names, or gives one to a source type the
model does not name. A replacement may be higher or lower; evidence with both
a source type and a class still takes the lower of the two. With several
profiles, the lowest weight they give a key applies.

### 8.4 Manual Overrides

A **manual override** replaces, by a person's or an agent's decision, what
§8.1–§8.3 computed: a trust score, or which value won a conflict.
`authority_trust_model.yaml` `overrides` governs it:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allow_manual_override` | boolean | No | When false, an implementation refuses every override |
| `requires_anchors` | boolean | No | When true, an override MUST cite at least one evidence anchor for the value it sets, and one that cites none is refused |
| `audit_required` | boolean | No | When true, an override MUST be recorded as an audit record (§6.4) before it takes effect |

The audit record of an override is an action record whose `intent` names
the override, whose `actor_identity` (or `actor`) is who made it, whose
`details` hold what was overridden, the value it had and the value set, and
whose `anchors` are the anchors cited. An override whose record cannot be
written does not take effect.

---

## 9. Diagnostic Model

### 9.1 Categories and Severity

| Category | Code Range | Severity | Description |
|----------|------------|----------|-------------|
| Validation | V1xx | error | Static validation failures |
| Binding | B2xx | error | Binding and expression-reference failures |
| Schema | S3xx | error | Schema validation failures |
| Runtime | R4xx | error | Runtime execution failures |
| Safety | F5xx | error | Safety constraint violations |
| Warning | W6xx | warning | Valid but suspect: the workflow is accepted |

Severity is fixed per code. A workflow is valid when it has no errors. A
validator MAY offer a strict mode that treats warnings as errors; it MUST
NOT change any code's severity otherwise.

A V1xx code is a static validation failure of a workflow, and the same code
keeps its meaning where §5.18 uses it: a safety layer reports V101, V105,
V107 and V109–V111 when it loads tool bindings or checks the tools a host
offers (§5.18.1–§5.18.4), and refuses a call with V102 when a prerequisite
other than a checkpoint has not run in its scope (§5.18.5). A V-code on a
call is that call's refusal; it says nothing about any workflow.

The codes of this section are this standard's. A code an implementation
defines for findings of its own MUST NOT have the form of a standard code (a
letter of the six categories followed by three digits); it SHOULD start with
a prefix that names the implementation (`sa-binding.unclassified`).

### 9.2 Validation Errors

| Code | Name | Description |
|------|------|-------------|
| V101 | UNKNOWN_CAPABILITY | Capability ID not found in ontology: a step's; a tool binding's `capability` or `additional_capabilities` entry (§5.18.1); an id in a grounding policy's `require` (§5.20); an id in a domain profile's `block_autonomous`, `require_grounding` or `checkpoint_policy` keys (§5.21.2); a capability an agent manifest lists, at each `delegate` step whose target maxima draw on it (§5.15.1); any id that a document citing a later ontology minor names, where it is used (§11.6) |
| V102 | MISSING_PREREQUISITE | A `requires` or `precedes` edge is violated (§4.3); a call's prerequisite other than a checkpoint has not run, and the layer refuses the call (§5.18.5); an offered tool requires a capability no offered tool can perform (§5.18.2) |
| V103 | INVALID_STEP | Step is not a mapping, or its `capability` is missing or not a string |
| V104 | DUPLICATE_STORE_AS | Same store_as used by multiple steps |
| V105 | CIRCULAR_DEPENDENCY | Workflow contains circular dependencies, including `invoke` cycles across the catalogs of a set (§5.1.1), or tool bindings' `invokes` form a cycle (§5.18.4) |
| V106 | UNSUPPORTED_EXTENSION | `workflow_extensions.requires` lists an unknown or unsupported extension, or an extension field is used without its declaration; in a workflow that targets 1.2, also `grounding` without `grounding@1` (§5.20) and an approver's `sender_check` or `accept_trust_classes` without `identity@1` (§5.17) |
| V107 | UNRESOLVED_TARGET | A `goto_step`, `on_exhausted`, `reviewers`, `forbidden_inputs` or `delivers_to` name does not resolve, or names the wrong kind of step or input; an `invoke` of a workflow whose `triggers` include no `invoke`; a handler's failure mode that loops or escalates (§5.10–§5.12, §5.16); a manifest `exports` entry that names no workflow of its catalog, or an invoke target that is a qualified id of the invoking catalog or of another catalog of the set where that catalog does not have the workflow or (another catalog) does not export it (§5.1.1); a literal `delegate` `agent` that the workflow's `agents` does not list, or a listed agent that a host composing agents statically does not provide (§5.15.2); a tool binding's `invokes` name that no binding of the set has (§5.18.4). Every other invoke target that resolves to nothing, a bare name included, is W607 |
| V108 | INVALID_EXPRESSION | Expression syntax error or limit exceeded |
| V109 | UNSUPPORTED_SPEC_VERSION | The declared standard version is not supported; or a document's cited `standard` is not supported, or its cited `ontology` has another major than the implementation's (§11.5, §11.6): a domain profile, a tool binding record (§5.18.1), a catalog manifest (§5.1.1), an interoperability mapping. (An agent manifest that does is refused when loaded, §5.15.1.) |
| V110 | DUPLICATE_BINDING | Two tool bindings in one set name the same tool (§5.18.1) |
| V111 | TOOL_NAME_MISMATCH | A tool binding's `tool` is not the name the host offers the tool under (§5.18.2) |

### 9.3 Binding Errors

| Code | Name | Description |
|------|------|-------------|
| B201 | INVALID_BINDING_PATH | Reference is malformed, or its path does not exist in the producer's schema |
| B202 | MISSING_PRODUCER | Root is neither an earlier store_as nor an input |
| B203 | TYPE_MISMATCH | Annotation or inferred type incompatible with the schema or consumer |
| B204 | AMBIGUOUS_TYPE | Type cannot be inferred, annotation required |
| B205 | INVALID_ANNOTATION | Type annotation names no type |
| B206 | EXPRESSION_TYPE_ERROR | Operator applied to kinds it does not accept, or non-boolean result |

### 9.4 Schema Errors

| Code | Name | Description |
|------|------|-------------|
| S301 | SCHEMA_NOT_FOUND | Referenced schema or mapping file not found |
| S302 | INVALID_REF | $ref or JSON pointer cannot be resolved, or its refs expand past the validator's size limit |
| S303 | SCHEMA_VALIDATION_FAILED | A field has the wrong type or value; or a domain profile member of the wrong type or outside its grammar, including a member of `risk_thresholds` or `evidence_policy` this version does not define and the `checkpoint_policy` key `checkpoint` (§5.21.2) |
| S304 | MISSING_REQUIRED_FIELD | Required field not present |

### 9.5 Runtime Errors

| Code | Name | Description |
|------|------|-------------|
| R401 | EXECUTION_TIMEOUT | Step exceeded timeout, or a wait lapsed |
| R402 | EXECUTION_FAILED | Step execution failed; an `Error` may say why (`reason`, §5.19.7); a capability output on a text-only channel is not I-JSON, not an object, or lacks a required field (§5.18.9) |
| R403 | GATE_BLOCKED | A gate stopped the run, or a condition was false with `skip_if_false: false` |
| R404 | RECOVERY_EXHAUSTED | Max recovery loops exceeded |
| R405 | EXPRESSION_ERROR | An expression failed to evaluate (§5.8.2) |
| R406 | LIVENESS_LOST | A wait's source stopped answering (§5.13) |
| R407 | SAFETY_CHECK_FAILED | A safety layer could not complete its checks of a call, or a tool was reached without a layer's decision, so the call was refused (§5.18.8) |
| R408 | CANCELLED | The host cancelled the run (§5.19.5); no retry, failure mode, recovery or handler ran |

### 9.6 Safety Errors

| Code | Name | Description |
|------|------|-------------|
| F501 | CHECKPOINT_REQUIRED | A step or call that requires a checkpoint has no valid one, or one could not be taken (§5.2.2, §5.18.6) |
| F502 | APPROVAL_REQUIRED | A step or call that requires approval has no valid decision (§5.14, §5.18.7) |
| F503 | ROLLBACK_FAILED | Could not restore a checkpoint: the host failed the executor's `Rollback`, or there was no checkpoint to restore (§4.4.1, §5.2.2, §5.18.6) |
| F504 | CONSTRAINT_VIOLATED | Policy constraint violated: conflicting capabilities in one parallel group; a `send` destination that a destination policy in force does not allow (§4.4.2); a composite's call to a binding it does not list (§5.18.4); a safety layer's own policy, such as a rate limit (§5.18.8); a `persist` or `audit` write that holds a secret the layer recognises (§5.18.10, §6.7); an output whose confidence is below an applied profile's minimum, or not a number from 0 to 1 while a minimum applies (§5.21.3) |
| F505 | PROVENANCE_MISSING | Under a grounding policy, a host's output that is neither grounded nor marked inferred, that cites evidence its producer did not have, or whose citation of a workflow value is not of kind `record` (§3.1, §5.20) |
| F506 | GATED_CONTROL_ACTION | A host action taken whenever a tool is called, whatever the result, is tied to a tool that is not control-only and is unbound, has a prerequisite, or requires a checkpoint or approval (§5.18.3) |

### 9.7 Warnings

| Code | Name | Description |
|------|------|-------------|
| W601 | SOFT_REQUIREMENT_UNMET | No `soft_requires` source runs before the step (a safety layer MAY report it for a call, §5.18.5) |
| W602 | SAFETY_FLAG_DOWNGRADE | A step, a tool binding (§5.18.1) or a `delegate` step of a workflow with `agents` (§5.15.2) declares a flag weaker than its baseline (the ontology's, or the delegation's target maxima), or a domain profile's `checkpoint_policy` says `never` for a capability whose ontology requires a checkpoint (§5.21.2); the stricter value applies |
| W603 | DEPRECATED_FORM | Accepted legacy form (self-reading gate without `phase`, goto_step by capability id, a profile threshold `critical` (§5.21.2), a reference to `persist`'s `timestamp` (§4.5)) |
| W604 | UNKNOWN_FIELD | Unrecognised field, ignored; or a binding key outside the capability's inputs (§5.5); or an unknown top-level domain profile member (§5.21.2); with a closest-match hint |
| W605 | MISSING_SPEC_VERSION | No `spec_version` and no version header |
| W606 | UNATTENDED_APPROVAL | An unattended trigger reaches an approval step without `when_unattended` or a standing mandate, or whose mandate cannot cover it: an always-ask item it uses (§5.17), or a person an applied profile requires (§5.21) |
| W607 | UNRESOLVED_WORKFLOW | An invoke target that resolves to no workflow: a bare name its catalog does not have, or a qualified id whose catalog is not in the catalog set (§5.1.1, §5.12); it cannot be checked |
| W608 | WAIT_SPANS_CHECKPOINT | A wait, or an invoke of a workflow that waits, sits between a checkpoint and a later step that requires one (§5.13) |
| W609 | UNTRIGGERED_FAILURE_MODE | Structured recovery with neither `on_error` nor `when`, or a failure mode that fires only on R406 where no wait has `liveness` |
| W610 | NULLABLE_OPERAND | An ordering operand, or the right operand of `in`, may be null |
| W611 | CONSTANT_COMPARISON | Equality between kinds that can never be equal; `in` that can never hold |
| W612 | MANGLED_REFERENCE | YAML read a typed reference as a mapping; quote it |
| W613 | UNREACHABLE_HANDLER | A handler step no escalation targets |
| W614 | INVALID_DURATION | Legacy `timeout`, a literal `audit` `retention` or a literal `persist` `ttl` outside the duration grammar, or a `ttl` of zero (§4.5, §5.10.1, §6.3) |
| W615 | MISSING_INPUT | A required capability input the step does not bind (§5.5) |
| W616 | VERSION_FEATURE_MISMATCH | A workflow that targets an earlier version uses a feature new in a later one (§11.5) |
| W617 | UNBOUND_TOOL | A tool offered to a model has no binding; its calls are treated as the strictest case (§5.18.2) |
| W618 | UNKNOWN_JOIN | A `join` other than `all_complete`, or a `join` on a step with no `parallel_group`; it is ignored (§5.2.3) |
| W619 | GROUP_MATE_READ | A step reads the store of a step in its own `parallel_group`, which need not have run yet (§5.2.3) |
| W620 | NONCANONICAL_NAME | A workflow name that is not an identifier or is `catalog` (§5.1), a step `domain` that is not a domain id (§5.2.4), or a literal model family outside `[a-z][a-z0-9_-]*` (§5.15) |
| W621 | UNBOUNDED_DELEGATION | In a workflow that targets 1.2 or later, a `delegate` step whose target maxima are unknown: in a workflow that declares `agents`, always (the executor will not delegate there); otherwise, when it binds no literal `read_only: true` and its effective `requires_approval` is false (§5.15.2) |
| W622 | UNDECLARED_DELEGATE | In a workflow that targets 1.2 or later and declares no `agents`, a `delegate` step whose `agent` is not a literal (§5.15.2) |
| W623 | CONCURRENT_RUN_CONFLICT | A workflow with a trigger whose `overlap` is `allow_all` exercises both capabilities of a `conflicts_with` pair: through its steps, a gate's or failure mode's `rollback` action, or the workflows it invokes (§4.3). Event triggers do not count: they declare no overlap policy, and whether their runs overlap is the host's (§4.3) |
| W624 | UNCHECKED_ROLLBACK | In a workflow that targets 1.2 or later, a `rollback` step whose `restored` no condition, gate or failure-mode `when` reads (§4.4.1) |
| W625 | DESTINATION_NOT_SHOWN | In a workflow that targets 1.2 or later, a `send` step whose `approval.shows` leaves out a destination given by reference (§4.4.2) |
| W626 | UNKNOWN_MEMORY_SCOPE | A literal `persist` or `recall` `scope` that is neither a defined scope nor an `x-` name (§4.5) |

### 9.8 Diagnostic Format

Diagnostics MUST be returned in this format:

```json
{
  "code": "W604",
  "name": "UNKNOWN_FIELD",
  "severity": "warning",
  "message": "unknown field 'requires_aproval' is ignored",
  "location": {
    "workflow": "my_workflow",
    "step": 3,
    "capability": "observe",
    "field": "requires_aproval",
    "path": "/my_workflow/steps/3/requires_aproval"
  },
  "suggestion": "did you mean 'requires_approval'?"
}
```

`location` says where the finding is. Most findings are about the catalog
document: a workflow, a step, or the catalog's manifest or header. Some are
about another document: a domain profile (§5.21), a tool binding record or a
tool the host offers (§5.18). Its keys have these meanings:

| Key | Meaning |
|-----|---------|
| `catalog` | The `id` of the catalog the finding is in, when that is not the catalog being validated but another of its catalog set (§5.1.1) |
| `workflow` | The workflow's name, its key in the catalog. Present whenever the finding concerns a workflow or anything in it |
| `step` | The step's zero-based index in the workflow's `steps` list, in list order (handlers included), whatever the order of checking. Present whenever the finding concerns a step or anything in it |
| `capability` | The capability concerned: the step's `capability`, when it is a string, or a tool's capability (§5.18) |
| `profile` | A finding about a domain profile: its `domain`, or `#<i>`, its zero-based position among the profiles given (§5.21.2). Such a finding has no `workflow` |
| `tool` | A finding about a tool: the name the host offers it under (§5.18). Such a finding has no `workflow` or `step` |
| `call` | The host's identifier of the tool call a safety layer refused (§5.18.8) |
| `action` | The host action tied to the tool (§5.18.3) |
| `field` | The member the finding is about, as a path relative to the step when `step` is present, else to the workflow when `workflow` is present, else to the document the finding is about (the catalog, or the profile or tool record that `profile` or `tool` names): keys joined by `.`, list indices as `[n]` (`gates[0].when`, `input_bindings.task`, `triggers[0].schedule.cron`, `catalog.exports[1]`, `risk_thresholds.auto_approve`). It is written for people, and a key that contains `.`, `[` or `]` makes it ambiguous. A finding about the version header has `field` `# Standard version` |
| `path` | The member `field` names, as an RFC 6901 JSON Pointer from the root of the catalog document (`/review/steps/1/gates/0/when`): for a member that is missing, where it would be; for a finding about a whole workflow or step, that workflow or step; `""` for the document as a whole. Exact where `field` is ambiguous. Present on every finding about the catalog document, and absent from one about the version header or about another document |
| `column` | For a finding in an expression or reference at `field`: the 1-based position, in Unicode code points, of the character it concerns |
| `ref` | The `${...}` reference the finding concerns, as written |
| `prerequisite` | V102: the capability that must run before the step or tool |
| `expected_type`, `actual_type` | B203: the type required and the type found, in the annotation grammar of §5.3 |
| `input_key` | B203 on an input: its `input_bindings` key |
| `store_as`, `first_step` | V104: the name used twice, and the index of the step that used it first |
| `wait_step` | W608: the index of the wait between the checkpoint and the step |
| `mate` | W619: the index of the group mate whose store the step reads (§5.2.3) |

A validator MUST give these keys these meanings, and MUST set `workflow`,
`step`, `profile`, `tool` and `path` as stated. `location` MAY carry further
keys, under names this table does not use. A consumer that needs one path
string for a finding about the catalog uses `path`; one that needs the
dot-and-bracket form of another format writes `workflow`, then
`.steps[step]` when `step` is present, then `.` and `field` when `field` is
present (`review.steps[1].gates[0].when`).

A safety layer's refusal of a call (§5.18.8) is a diagnostic in this
format. Its `location` holds `tool`, `capability` (absent for an unbound
tool) and optionally `call`, and no `workflow` or `step`. On a channel that
carries only text it is written as the code, a space, the name, a colon, a
space and the message: `F501 CHECKPOINT_REQUIRED: write requires a
checkpoint`.

A single error MAY be wrapped as `{"error": {...}}` and a list as
`{"errors": [...]}`, as in 1.0.

---

## 10. Conformance

### 10.1 Conformance Levels

| Level | Requirements |
|-------|--------------|
| **L1** | Validate structure, capability existence and ontology edges |
| **L2** | Resolve $ref schemas and infer binding types |
| **L3** | Validate binding types against consumer contracts; check expressions |
| **L4** | Emit patch suggestions using coercion registry |
| **SL** | A safety layer on a tool-calling host: applies §5.18 to the calls it covers (§10.4) |
| **EX** | An executor: runs validated workflows by the host protocol, records as §6.4 says, and passes the runtime fixtures (§10.5) |

Levels L1–L4 rank validators; SL (§10.4) and EX (§10.5) are separate
classes: a layer validates no catalog, a validator checks no call and runs
no workflow, and an implementation claims each level or class it meets.

### 10.2 Conformance Requirements

An implementation is conformant at a given level if it:

**L1 (Basic)**
- Validates required fields and field types (§5.1, §5.2)
- Validates all capabilities exist in the ontology
- Enforces `requires`, `precedes` and `conflicts_with` (§4.3) and reports
  unmet `soft_requires`
- Validates all store_as identifiers are unique
- Resolves effective safety flags and reports downgrades (§5.2.1)
- Reports unknown fields and the standard version (§11.3, §11.5)

**L2 (Schema)**
- Resolves all $ref schema references
- Infers binding types from producer schemas, checking each binding's root
  and path (B202, B201)
- Reports ambiguous types requiring annotation

**L3 (Contracts)**
- Validates inferred types against consumer input schemas
- Reports type mismatches with suggested fixes
- Parses and checks condition expressions (§5.8.3)

**L4 (Patches)**
- Emits JSON patch suggestions for fixable errors
- Uses coercion registry for type conversions
- Generates diff patches on request

### 10.3 Conformance Testing

Conformance tests MUST include:
- Positive fixtures (valid workflows that MUST pass)
- Negative fixtures (invalid workflows that MUST fail with specific error codes)
- Patch fixtures (invalid workflows with expected patch suggestions)

A negative fixture's `expected_error_codes` are the exact set of error codes
it MUST produce, so each fixture isolates what it tests. Fixture
expectations MAY list `expected_warning_codes`, likewise exact; absent or
empty, the fixture MUST produce no warnings. Expression fixtures
(`tests/conformance/expressions/eval.json` and `check.json`) are
language-neutral; the reference suite also runs them against cel-go to
check §5.8.2's CEL compatibility. Runtime fixtures
(`tests/conformance/runtime/*.json`) script runs: the actions an executor
must issue, the responses it gets, the ticks, cancellations and resumptions
it is given, and the end it must reach, for the runtime semantics of
§4.4–§4.5, §5.2, §5.6–§5.21 and §6.4. They are normative for class EX
(§10.5), except their `trace_kinds`, which name kinds of the reference
executor's trace and are informative. The trigger vectors
(`tests/conformance/triggers/`) are normative for §5.10.2: an implementation
that computes fire times, a trigger's attendance, which events start runs,
or overlap decisions MUST give each vector's result. The fire-time vectors
depend on the time zone database: each file names the tzdata release it was
computed with, and the vectors are normative with that release, or with any
release that agrees with it on the vectors' dates.

Binding fixtures (`tests/conformance/bindings/*.json`) and call-sequence
fixtures (`tests/conformance/calls/*.json`) are normative for class SL
(§10.4).

The approval digest vectors (`tests/conformance/approval/digests.json`) are
normative for §5.14 and §5.18.7. Each vector has a `kind`. A `step` vector is
one approval request of a workflow step: the step's `approval` field (or
null for none); where the step declares no `shows`, its resolved `inputs`;
where it does, the values its references resolve against (`bindings`, by
root name); for a request asked again after a recheck, the value the recheck
read (`recheck_read`); and the `shown` values. A `tool_call` vector is the
approval of a tool call: the `call` (`action`, `capability`, `args`) and the
`shown` values `[call]`. Every vector gives the RFC 8785 `canonical` text of
`shown` and its `digest`. An implementation that computes or checks approval
digests MUST produce each vector's `canonical` text and `digest` from its
`shown` values. An executor MUST show, for each `step` vector's step, given
that vector's `inputs` or `bindings` and its `recheck_read`, that vector's
`shown` values, and a layer (§5.18) MUST show, for each `tool_call` vector's
call, that vector's `shown` values.

Grounding vectors (`tests/conformance/grounding/check.json`) state the check
of §5.20 for one output at a time: an executor that accepts `grounding@1`,
and a safety layer that applies grounding policies, MUST give the status and
code each vector expects. The runtime fixtures whose names start with
`grounding_` script the check inside runs.

Trust vectors (`tests/conformance/trust/`), profile vectors
(`tests/conformance/profiles/`) and entity id vectors
(`tests/conformance/entities/ids.json`) are normative for §8, §5.21 and §7.1.
An implementation that computes trust scores or resolves conflicts MUST give
each trust vector's result within the file's `tolerance`, and refuse what a
vector expects refused. One of any level or class that applies profiles
loads and applies them as §5.21 says, and MUST report each `load` vector's
diagnostics (code and field) and compute each `effective` vector's flags and
rules.

### 10.4 Safety-Layer Conformance

A safety layer conforms to class SL when, for every call it covers, it:

- loads bindings and reports their diagnostics as §5.18.1–§5.18.4 state,
  and passes every binding fixture whose `needs` it supports;
- applies §5.18.5–§5.18.9 and passes every call-sequence fixture whose
  `needs` it supports;
- applies the capability checks of §5.18.10;
- runs in a mode that fails closed (§5.18.8).

Its **conformance statement** names: the host, and the layer's name and
version; the calls it covers and those it cannot see; its scope, and
whether a delegate's calls share it; the execution boundaries it observes;
its checkpoint maximum age; how it obtains approval (a prompt, recorded
decisions, or both), the host configurations in which it relies on a
prompt, its decision expiry, the most approvers it can obtain for one call,
and whether it can verify an approver's role; how it makes a check and its
use atomic (a lock or reservation, or its host's order); the fixture
features it supports; its host gaps, the cases in which its host can run
a covered call without the layer's decision; and any check of §5.18.10 it
does not apply, which a conforming layer has none of. The statements of the
reference layers follow `tests/conformance/calls/schema/statement.schema.json`.

**Binding fixtures.** Each fixture holds an `ontology` version, `records`,
optionally `needs`, `offered` (each name the host offers a tool under,
mapped to the `tool` of the record it carries, or null), `host_actions`
(each an `action` and a `tool`) and `host_takes_checkpoints` (default
false), and `expect`: the exact lists of error and warning codes, each
with the tool it names, in any order, and the effective flags of each
loaded record. A layer
passes a fixture when it reports exactly those diagnostics and computes
exactly those flags. Fixtures that check offered tools and host actions
(§5.18.2, a SHOULD) have `needs: ["offered_tools"]`; a layer that does not
check them skips those fixtures and says so in its statement.

**Call-sequence fixtures.** Each fixture is one scope with a person
present. Its `bindings` are records under its `ontology`; a tool not listed
is unbound. A bound tool succeeds and returns what its output contract
requires; a call of a tool classified `checkpoint` that runs takes a
checkpoint. Its `sequence` is a list of calls and events:

- A call names `call` (the tool), `args` (default `{}`), optionally
  `approve` or `reject` (who decided on it beforehand: on its shown value
  §5.18.7, or at the prompt), `fails` (its tool reports an error after it
  started), `nested` (calls the tool makes while it runs), and `expect`:
  `"run"` or `{"refuse": <code>}`. A call with neither `approve` nor
  `reject` is undecided.
- An event is `{"boundary": true}` (an execution boundary) or
  `{"expire": "checkpoint"}` / `{"expire": "decision"}` (the layer's
  checkpoint maximum age, or a decision's expiry, passes).

`needs` names features a layer must have to run the fixture:
`unbound_calls` (it sees calls of tools with no binding), `nested_calls`
(it attributes nested calls), `recorded_approval` (decisions recorded apart
from the call, from several approvers), and, for binding fixtures,
`offered_tools` (it checks the tools a host offers, §5.18.2). A layer that
lacks one says so in its statement and skips those fixtures; no expectation
depends on the order in which a layer checks approval and the checkpoint.
A runner gives the layer a fixture's values as its JSON text writes them:
an integer literal beyond 2^53 is not rounded on the way.

Not testable by fixture, and stated instead: that a prompt shows what runs
(§5.18.7), that the layer sees every call it claims to cover, and its host
gaps.

### 10.5 Executor Conformance

An executor conforms to class EX when it:

- starts a run only when the catalog has no error under a validator that
  conforms at L3 or above (its own or another), and refuses to start it
  otherwise;
- implements each extension a workflow it starts declares (§5.9), and
  refuses a workflow that declares one it does not implement;
- offers the run operations of §5.19.2 and issues exactly the actions of
  `schemas/host_protocol.schema.json`;
- takes every response that schema allows as §5.19.1 says: it refuses the
  responses §5.19.1 refuses, and ignores the members the protocol does not
  define and a `reason` outside §5.19.7;
- keeps time, saves and restores, and cancels as §5.19.3–§5.19.5 say, and
  writes action records as §6.4 says, in both record modes;
- passes every runtime fixture whose declared extensions it implements.

**Runtime fixtures.** A fixture
(`tests/conformance/runtime/schema/fixture.schema.json`) holds a `catalog`,
the version of its header or null (`header`), the `workflow` to run, its
`inputs`, its `attendance`, optionally its `actor_identity`, `records` (the
record mode, default `approvals`), further catalogs of its set with their
headers (`catalogs`), agent manifests (`agents`), destination policies
(`destinations`), grounding policies (`grounding`) and domain profiles
(`profiles`), which the run is started with (§5.19.2), the `start` time, a
`script`, the `end` and, optionally, the `run_record`. The
run starts with `run_id` `"run-1"`. Each script entry is one of:

- `{"expect": A, "respond": R, "at": T}`: the pending action matches `A`,
  and holds none of the members the entry's `absent` lists (each a path of
  member names joined by `.`); then `R`, when given, is submitted for it at
  time `T` (default: the latest time used). In `R`, the string `"{{digest}}"` stands for the
  pending action's `digest`, and `"{{digest_upper}}"` for the same in
  uppercase;
- `{"tick": T, "changed": C}`: the time `T` is given with no response; when
  `changed` is given, the tick changed the run exactly when `C` is true;
- `{"wake_at": W}`: the run's wake-up time is `W` (null: none);
- `{"cancel": {"reason": S, "at": T}}`: the run is cancelled;
- `{"resume": {"attendance": …, "at": T, "actor_identity": …}}`: the run is
  resumed (§5.14.1).

After the script, the run's next action matches `end`, and, when the
fixture gives a `run_record`, the run record derived from that end
(§5.19.8, with the run's clock and actor) matches it. An actual value
**matches** an expected one when they are equal; when both are objects and
the actual one has every member the expected one names, each matching; or
when both are arrays of the same length whose elements match in order. Text
the executor composes is not compared: a `message` member (except
`ended.message`, a gate's message, §5.6, which the workflow wrote), the
`reason` member of an action record or of a deferral, and the `ignored`,
`note` and `quorum` members of an item of a quorum's `violations`
(§5.19.1). (`reason` on a `Failed` action is a token, §5.19.7, and is
compared.) An executor passes a fixture when every expectation matches,
both when it runs the script as it is and when its state is saved and
restored before every entry. `description` and `trace_kinds` are not part
of the test. Every other member a fixture pins is one this Standard
defines (§4.4.1, §4.4.2, §4.5, §5.2, §5.6, §5.11–§5.17, §5.19.1, §5.20,
§5.21, §6.4).

**Conformance statement.** An executor that claims class EX names its
version, the Standard version it implements, the extensions it implements,
how its binding names the operations of §5.19.2, and whether it restores
states saved by its earlier versions.

---

## 11. Versioning and Compatibility

### 11.1 Semantic Versioning

This standard follows Semantic Versioning 2.0.0:

| Change Type | Version Bump | Example |
|-------------|--------------|---------|
| Breaking changes | MAJOR | Removing capability, changing required fields |
| New features | MINOR | Adding optional fields, new capabilities |
| Bug fixes | PATCH | Clarifications, typo fixes |

### 11.2 Deprecation Policy

1. Features are deprecated in a MINOR release with warnings (W603)
2. Deprecated features are removed in the next MAJOR release
3. Deprecation notices MUST include migration path
4. Minimum deprecation period: 6 months

### 11.3 Compatibility Guarantees

**Forward Compatibility**
- Validators MUST accept unknown fields, report them as W604, and otherwise
  ignore them; `x-` prefixed fields are never reported
- New optional fields MUST have sensible defaults
- New capabilities MUST NOT break existing workflows
- A workflow that depends on an extension MUST declare it (§5.9), so a
  consumer that does not know the extension refuses the workflow instead of
  silently ignoring the extension's fields

**Backward Compatibility**
- Existing capabilities MUST NOT change semantics
- Removed features MUST be deprecated first
- Clarifications of 1.0 semantics (Appendix C) apply to workflows of both
  versions

### 11.4 Schema Evolution

| Change | Compatibility |
|--------|---------------|
| Add optional field | Compatible |
| Add required field | Breaking |
| Remove field | Breaking |
| Change field type | Breaking |
| Rename field | Breaking |
| Add enum value | Compatible |
| Remove enum value | Breaking |
| Make a required field optional | Compatible |

**A breaking change in 1.1.0.** Ontology 2.1.0 widens `transform.output`
from `object` to `object|array`, so a transform can return a list of
records. By the table this is breaking, and it is the one field type change
to an existing capability contract in this version: a reference to the
output is now a union, so one without an annotation is B204 (§5.4), in a
1.0 workflow too. Annotate it with the type the workflow expects
(`${t.output: object}`).

### 11.5 Version Declaration

A workflow declares the standard version it targets with `spec_version`
(`"1.2"`, optionally with a patch: `"1.2.0"`), or a catalog file declares it
for all its workflows with a header among its leading comment lines (a BOM,
blank lines, `%` directives and a `---` marker may precede it):

```yaml
# Standard version: 1.2.0
workflow_name:
  goal: ...
```

`spec_version` takes precedence over the header. A version is
`digits.digits[.digits]`; `spec_version` MUST be a string (quote it in YAML).
A validator for this version MUST support 1.0, 1.1 and 1.2.

The header, a comment, is gone once a catalog is parsed, so the start
operation (§5.19.2) takes the version it declares, or none, as an explicit
value: a host that loaded the catalog from a file MUST pass it, and a binding
MUST NOT let a host omit it. The executor validates and runs the catalog with
it, as a validator reading the file would, and keeps it in the run's saved
state (§5.19.4).

The version a workflow declares is its **target**. A workflow of any target
is validated and run under this Standard; a rule for targets of 1.2 or later
applies to a workflow only when it declares such a version.

A consumer of an earlier version does not know the features later versions
added, so a workflow that targets an earlier version than a feature's and
uses the feature gets W616:

| New in | Features |
|--------|----------|
| 1.1 | `workflow_extensions.requires` (and so every extension; the advisory `supports_*` flags are 1.0), gate `phase`, gate `action: end`, the `in` operator, failure-mode `when` and `on_error` |
| 1.2 | approver `sender_check` and `accept_trust_classes` (§5.14, §5.17); the `delegate` input `continues` (§5.15.3); an `invoke` target that is a qualified id (§5.1.1) and a catalog manifest (§5.1.1, reported at the manifest when the file's header targets an earlier version); the extension `grounding@1` and the workflow field `grounding` (§5.20); F505 in a failure mode's `on_error` (§5.12); the `audit` input `require_record` (§6.4); the `persist` and `recall` input `scope` (§4.5) |

Declaring the version a feature is new in, or a later one, clears it. A
feature is new in a version when a consumer of the version before would
refuse a workflow that uses it or run it differently: a workflow or step
field, a field value, an extension, or an input the executor reads. An input
only a host reads is not: an older consumer reports it as W604 and passes it
on (§5.5); §11.6 governs it. A feature that an older consumer must refuse
(V109), not ignore, is allowed only in a workflow that targets its version:
the workflow field `agents` (§5.15.2).

| Code | A workflow or catalog is reported when |
|------|----------------------------------------|
| W605 | It declares no version: neither `spec_version` nor a header |
| V109 | The version it declares is not one the validator supports |
| S303 | Its `spec_version` is not a string; or it uses `agents` and targets 1.0 or 1.1 or declares no version |
| W616 | It targets an earlier version than a feature it uses (the table above): once per feature, at its first use |

### 11.6 Ontology Versions

The capability ontology (`schemas/capability_ontology.yaml`) has its own
Semantic Version, `meta.version`:

| Change to the ontology | Version |
|------------------------|---------|
| Remove or rename a capability, a layer or an edge type; move a capability to another layer; change a capability's `risk`, `mutation`, `requires_checkpoint`, `requires_approval` or `mutation_overridable`; add a required input or a required output field; remove an input or an output field, or stop requiring an output field; change a field's type (§11.4); add a constraint to an existing input or to a member it already names, or tighten one it has (a `pattern`, a bound, a narrower `enum`, a type for items it left open); tighten a constraint an existing output field already has; add or remove a `requires`, `precedes` or `conflicts_with` edge | MAJOR |
| Add a capability, an optional input, an optional member of an input or output object, an optional output field or an enum value; constrain the items or members of an existing output field where its contract left them open; remove or relax a constraint, other than its type, on an existing input; add or remove a `soft_requires`, `enables`, `alternative_to` or `specializes` edge | MINOR |
| Change only descriptions, rationales and examples | PATCH |

The constraint rows follow §11.4 and who bears a constraint. One on an input
binds the workflows that bind it, so adding or tightening it is breaking. One
on an output binds producers; where the contract said nothing about an
output's items or members, describing them binds producers only for values
the contract never described, and no implementation refuses an output on it
(an executor checks an output's required fields, §5.19). Tightening what an
output already promised is breaking for producers.

Ontology 2.1.0 widened `transform.output` from `object` to `object|array`, a
type change and so MAJOR by this table; it was published with Standard 1.1.0
as a MINOR version before this rule existed, and §11.4 of Standard 1.1.0
records it as the one breaking change of that release. This rule applies
from ontology 2.2.0.

An ontology MAJOR version is published only with a Standard MAJOR version:
every Standard 1.x uses ontology 2.x. An ontology MINOR version is published
with the Standard version that names it (§4, §11.7): Standard 1.2.0 with
ontology 2.2.0. An ontology PATCH version MAY be published alone. An
implementation of a Standard version uses the ontology version it names, or
a later PATCH of that version.

**Citing.** A document outside a workflow that names capabilities by id — a
domain profile (§5.21), a tool binding record (§5.18.1), an agent or catalog
manifest (§5.15.1, §5.1.1), an interoperability mapping — cites the versions
it was written against as `standard` and `ontology`, each `MAJOR.MINOR` or
`MAJOR.MINOR.PATCH`. Each format says where the two members sit (a domain
profile's are top-level members; the repository's interoperability mappings
keep them under `meta.agent_capability_standard`) and MAY make them optional
(a domain profile's are). A consumer checks those present:

| Code | A consumer reports a cited document when |
|------|------------------------------------------|
| V109 | Its `ontology` has another major than the consumer's ontology's: the consumer refuses it |
| V109 | Its `standard` is not one the consumer supports: the consumer refuses it |
| S303 | Its `standard` or `ontology` is not `MAJOR.MINOR` or `MAJOR.MINOR.PATCH` |
| V101 | It names a capability the consumer's ontology does not define, as one whose ontology MINOR is later may: at each place it uses the id |

A workflow cites only the Standard version it targets (§11.5), which fixes the
ontology's major.

### 11.7 Artifacts of This Version

Standard 1.2.0 is this text and these files. A file's version is the one it
declares (`meta.version` or `schema.version`); a file that declares none is
the one published with this version.

| Artifact | File | Version | Sections |
|----------|------|---------|----------|
| Capability ontology | `schemas/capability_ontology.yaml` | 2.2.0 | §4 |
| Ontology dialect metaschema | `schemas/capability_ontology.schema.json` | — | §4.1.2 |
| Contracts in Draft 2020-12 (generated) | `schemas/generated/capability_contracts.schema.json` | — | §4.1.2 |
| World state (canonical) | `schemas/world_state_schema.yaml` | 1.2.0 | §6.3, §6.4 |
| Events (canonical) | `schemas/event_schema.yaml` | 1.2.0 | §6.2, §6.5 |
| Entity taxonomy (canonical) | `schemas/entity_taxonomy.yaml` | 1.1.0 | §7.1 |
| Authority trust model (canonical) | `schemas/authority_trust_model.yaml` | 1.2.0 | §8 |
| Identity resolution policy (canonical) | `schemas/identity_resolution_policy.yaml` | 1.0.0 | §7.2, §7.3 |
| Review verdict | `schemas/review_verdict_schema.yaml` | 1.1.0 | §5.16 |
| Agent identity | `schemas/agent_identity_schema.yaml` | 1.1.0 | §5.17 |
| Agent manifest | `schemas/agent_manifest_schema.yaml` | 1.0.0 | §5.15.1 |
| Domain profile | `schemas/profiles/profile_schema.yaml` | 1.0.0 | §5.21 |
| Workflow catalog (JSON Schema) | `schemas/workflow_catalog.schema.json` | — | §5 |
| Host protocol | `schemas/host_protocol.schema.json` | — | §5.19 |
| Tool binding record | `schemas/interop/tool_binding.schema.json` | — | §5.18.1 |
| Evidence anchors and records | `schemas/interop/evidence.schema.json` | — | §6.5, §6.6 |
| Conformance vectors and fixtures | `tests/conformance/` and `tests/fixtures/` | — | §10.3 |

---

## 12. Decision Frameworks

This section provides guidance for common decisions when applying the standard.

### 12.1 When to Use Checkpoints

Use this decision tree:

```
Does the step modify external state?
├── No → Checkpoint not required
└── Yes → Is the modification reversible by other means?
    ├── Yes (idempotent, can retry) → Checkpoint recommended but optional
    └── No → Checkpoint REQUIRED
```

**Examples:**

| Operation | Checkpoint Required? | Reason |
|-----------|---------------------|--------|
| Read file contents | No | No mutation |
| Write to database | Yes | State change, may not be reversible |
| Send HTTP GET | No | Read-only |
| Send HTTP POST | Yes | May cause side effects |
| Rename file | Yes | May overwrite existing file |
| Append to log | Optional | Append-only, can ignore duplicate |

On a tool-calling host the same question is answered by the call's
classification (§5.18.3): a call is classified by its effect, and an HTTP
POST whose effect is not known is a `send` call.

### 12.2 When to Require Typed Bindings

Typed annotations are REQUIRED when:

| Scenario | Example | Solution |
|----------|---------|----------|
| Union schemas | `anyOf: [string, object]` | Add `: string` or `: object` |
| Open schemas | `additionalProperties: true` | Add explicit type |
| Array item ambiguity | `items: {}` | Add `: array<object>` |
| Cross-workflow references | Dynamic binding | Always annotate |

Typed annotations are OPTIONAL when:
- Producer schema has explicit, unambiguous type
- Single possible type interpretation exists

### 12.3 Choosing Conflict Resolution Strategy

| Scenario | Recommended Strategy |
|----------|---------------------|
| Hardware sensor vs. derived inference | `prefer_authoritative_sources` |
| Recent data vs. stale data | `prefer_recent` |
| High-confidence vs. low-confidence | `prefer_high_confidence` |
| Both sources equally valid | `merge_with_uncertainty` |
| Critical decision, ambiguous data | `escalate_to_human` |

### 12.4 Selecting Conformance Level

| Your situation | Start with | Target |
|----------------|------------|--------|
| New to the standard | L1 | L2 within 1 month |
| Existing workflows, want validation | L2 | L3 within 1 quarter |
| Production system, high reliability needed | L3 | L4 for auto-fix |
| Compliance/audit requirements | L3 minimum | L4 recommended |

### 12.5 Common Patterns

Safety flags are omitted below: they inherit from the ontology (§5.2.1).

**Pattern: Safe Mutation**
```yaml
- capability: plan
  purpose: Plan the change.
  input_bindings:
    goal: Rotate the service certificate
  store_as: plan_out
- capability: constrain
  purpose: Check the plan against policy.
  input_bindings:
    target: "${plan_out.steps: array<object>}"
    constraints: [change_policy]
  store_as: policy_out
- capability: checkpoint
  purpose: Save a restore point.
  input_bindings:
    scope: service_config
  store_as: checkpoint_out
- capability: mutate
  purpose: Apply the change.
  input_bindings:
    target: service_config
    operation:
      apply: "${plan_out.steps: array<object>}"
    checkpoint_id: ${checkpoint_out.checkpoint_id}
  gates:
    - when: ${policy_out.compliant} == false
      action: stop
  store_as: mutate_out
- capability: verify
  purpose: Check the result.
  input_bindings:
    target: "${mutate_out.new_state: object}"
    conditions: [change_applied]
  store_as: verify_out
- capability: audit
  purpose: Record what happened.
  input_bindings:
    event:
      type: safe_mutation
      plan: "${plan_out.steps: array<object>}"
      verified: ${verify_out.passed}
  store_as: audit_out
```

**Pattern: Multi-Source Integration**
```yaml
- capability: retrieve
  purpose: Fetch source A.
  input_bindings:
    target: https://example.com/a
  store_as: source_a
- capability: retrieve
  purpose: Fetch source B.
  input_bindings:
    target: https://example.com/b
  store_as: source_b
- capability: integrate
  purpose: Merge both sources.
  input_bindings:
    sources: ["${source_a.data: object}", "${source_b.data: object}"]
  store_as: integrated
```

**Pattern: Recovery Loop**

A fragment of Safe Mutation above (declaring `recovery@1`): `verify` rolls
back and re-plans, and `plan_out` reads the evidence the loop injects.
`goto_step` names that pattern's `plan_out` step. Before the first loop
`${_recovery}` is absent, so the plan sees null `context` (§5.11).

```yaml
- capability: plan
  purpose: Plan the change, using why the last attempt failed.
  input_bindings:
    goal: Rotate the service certificate
    context: "${_recovery.failure_evidence: array<object>}"
  store_as: plan_out
# ... constrain, checkpoint and mutate as in Safe Mutation ...
- capability: verify
  purpose: Check the result.
  input_bindings:
    target: "${mutate_out.new_state: object}"
    conditions: [change_applied]
  store_as: verify_out
  failure_modes:
    - condition: Verdict == FAIL
      when: ${verify_out.passed} == false
      action: rollback
      recovery:
        goto_step: plan_out
        inject_context:
          failure_evidence: ${verify_out.violations}
        max_loops: 3
```

---

## 13. References

### 13.1 Normative References

- [JSON Schema](https://json-schema.org/)
- [YAML 1.2](https://yaml.org/spec/1.2.2/)
- [Semantic Versioning](https://semver.org/)
- [RFC 3986: Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986) (§7.1)
- [RFC 5545: Internet Calendaring and Scheduling Core Object Specification (iCalendar)](https://www.rfc-editor.org/rfc/rfc5545) (§5.10.2)
- [RFC 6901: JavaScript Object Notation (JSON) Pointer](https://www.rfc-editor.org/rfc/rfc6901) (§4.1.2, §6.2, §9.8)
- [RFC 7493: The I-JSON Message Format](https://www.rfc-editor.org/rfc/rfc7493)
- [RFC 8785: JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785)
- [ISO 8601: Date and time format](https://www.iso.org/iso-8601-date-and-time-format.html)
- [IANA Time Zone Database](https://www.iana.org/time-zones)

### 13.2 Informative References

- [RFC-0001: Agent Capability Ontology](RFC-0001-agent-capability-ontology-and-workflow-dsl.md)
- [RFC-0003: Orchestration Extensions and Validation Semantics](RFC-0003-orchestration-extensions.md)
- [RFC-0004: Agent Identity](RFC-0004-agent-identity.md)
- [RFC-0005: Tool-Calling Hosts](RFC-0005-tool-calling-hosts.md)
- [RFC-0006: Host Protocol, Approval and Runs](RFC-0006-host-protocol-approval-and-runs.md)
- [RFC-0007: Delegation, Catalogs and Validator Diagnostics](RFC-0007-delegation-catalogs-and-diagnostics.md)
- [RFC-0008: Evidence, Grounding and Secrets](RFC-0008-evidence-grounding-and-secrets.md)
- [RFC-0009: Checkpoint, Rollback, Send and Memory](RFC-0009-checkpoint-rollback-send-memory.md)
- [RFC-0010: Domain Profiles, Trust, Versioning and Schema Dialect](RFC-0010-profiles-trust-versioning-and-dialect.md)
- [Agent Skills specification](https://agentskills.io/specification) (the skill format of the reference plugin)
- [Common Expression Language](https://github.com/google/cel-spec)
- [Whitepaper: Grounded Agency](WHITEPAPER.md)
- [Conformance Guide](CONFORMANCE.md)
- [Security Model](SECURITY.md)

---

## Appendix A: Layer Reference

| Layer | Count | Capabilities |
|-------|-------|-------------|
| PERCEIVE | 4 | retrieve, search, observe, receive |
| UNDERSTAND | 6 | detect, classify, measure, predict, compare, discover |
| REASON | 4 | plan, decompose, critique, explain |
| MODEL | 5 | state, transition, attribute, ground, simulate |
| SYNTHESIZE | 3 | generate, transform, integrate |
| EXECUTE | 3 | execute, mutate, send |
| VERIFY | 5 | verify, checkpoint, rollback, constrain, audit |
| REMEMBER | 2 | persist, recall |
| COORDINATE | 4 | delegate, synchronize, invoke, inquire |

## Appendix B: Reserved Identifiers

The following identifiers are reserved and MUST NOT be used for custom capabilities:

- All identifiers starting with `_` (underscore); `_recovery` is the root of
  injected recovery context (§5.12)
- All identifiers starting with `system-`
- All identifiers starting with `internal-`

The `ref` scheme `acs:` of an evidence anchor is reserved for workflow
values (§6.5). Evidence anchor kinds and `inference_method` values starting
with `x-` are vendor values (§4.1.1, §6.5).

Field names starting with `x-` are reserved for vendor extensions, except
those starting with `x-acs-`, which are reserved for this Standard (such as
`x-acs-type` in a rendering of the schema dialect, §4.1.2).

## Appendix C: Changes from 1.0.0

**Clarifications of 1.0 semantics** (apply to 1.0 and 1.1 workflows; the
1.0 validator and engine disagreements they settle are reproduced in
[validator-engine-disagreements-1.0](../docs/research/analysis/validator-engine-disagreements-1.0.md)):

| Area | 1.0.0 text | 1.1.0 |
|------|------------|-------|
| `precedes` | "MUST complete before the target begins" (read by validators as "must be present") | Ordering only when both are present (§4.3) |
| `conflicts_with` | "MUST NOT appear in the same workflow" | MUST NOT run concurrently; sequence allowed (§4.3) |
| `soft_requires` | "SHOULD be satisfied when available" | Any-of presence per target, W601 (§4.3) |
| Concurrency | Unspecified | A step in the same parallel group does not run before another (§4.3) |
| Safety flags | Listed as optional step fields | Inherit from the ontology; downgrades ineffective, W602 (§5.2.1) |
| Unknown fields | "SHOULD ignore" | Ignored and reported, W604; `x-` exempt (§11.3). Binding keys outside the capability's inputs are W604 too (§5.5) |
| `invoke` inputs | Unchecked | A literal `input` is checked against the target's `inputs`: undeclared name S303, missing required S304; the executor refuses both (R402) (§5.12) |
| Version header | "SHOULD warn if missing" | `spec_version` or header; W605 / V109, and W616 for a 1.1 feature in a workflow that targets 1.0 (§11.5) |
| B205 | "Type annotation does not match schema" | Annotation names no type; a mismatch is B203 (§9.3) |
| `inputs` | Required | Optional, default `{}` (§5.1) |
| `store_as` | Any string | An identifier `[A-Za-z_][A-Za-z0-9_-]*`, else S303; `_recovery` is reserved (§5.2, §5.12) |
| `retry` | "Retry configuration (max, backoff)", unchecked | A mapping or null; `max` an integer from 0 to 1000, `backoff` `none`, `linear`, `exponential` or null, else S303 (§5.2) |
| Gate and failure-mode fields | Enums listed | Gate `when` and `action`, failure-mode `condition` and `action` are required strings (S304, S303); an `action` outside its enum is S303 (§5.6, §5.7) |
| Failure-mode `condition` | "When this failure mode applies" | Prose only, never evaluated; the trigger is `when` (an expression) or `on_error` (codes) (§5.7) |

**Migration of failure modes.** A 1.0 failure mode whose trigger was
written in `condition` never fires under this standard until it is
migrated: keep the prose in `condition` and add the trigger as `when` or
`on_error`. For example, `condition: Verdict == FAIL` gains
`when: ${verify_out.passed} == false`. A structured recovery without
either is W609 (§5.12).

**New in 1.1.0:**
- Condition expression language with CEL compatibility (§5.8), gate `phase`
  and gate `action: end`, a successful early end (§5.6), and failure-mode
  `when` (§5.7). A 1.0 consumer does not know `end`; a workflow using it
  targets 1.1, and declaring 1.0 is W616 (§11.5)
- Diagnostic severities and warning codes W601–W616 (§9.1, §9.7); codes
  V106–V109, B206, R405, R406
- With `identity@1`, a delegation's attested identity
  (`effective.identity`), which binds a waiting delegate's result, and
  quorum `require_distinct_identities` (§5.16, §5.17); a quorum's model
  families count only as attested (§5.16)
- Orchestration extensions and their declaration: triggers, handler steps,
  recovery and escalation, wait, approval, delegation, quorum, sender
  identity (§5.9–§5.17)
- Canonical schemas: `event_schema.yaml` 1.1.0 (`source.kind` gains
  `agent`); `world_state_schema.yaml` 1.1.0 (action status `rejected` and
  `expired`, the `approval` record of §5.14 with decisions `approved`,
  `rejected`, `expired` and `unavailable`, and a `reason`)
- `review_verdict_schema.yaml` 1.1.0 for quorum verdicts, with `scope`
  (§5.16)
- `agent_identity_schema.yaml` 1.0.0 (§5.17); `world_state_schema.yaml`
  1.1.0 also adds `ActionRecord.actor_identity` and
  `ProvenanceRecord.agent_identity`; `authority_trust_model.yaml` 1.1.0 adds
  `trust_classes` (§8.3)
- Capability ontology 2.1.0 (`capability_ontology.yaml`): the
  `mutation_overridable` flag (§4.4); `retrieve` and `search` as soft
  prerequisites of `ground` (a retrieved source or a search result is
  evidence to ground a claim in); the edges reclassified by §4.3 (five
  follow-up edges became `enables`, one redundant edge was removed, and
  `constrain` became the soft prerequisite of `execute`, `mutate` and
  `send`); `delegate` inputs `fresh_context`, `model_family`, `role`,
  `read_only`, and outputs `effective` and `result` (a waiting delegate,
  §5.13); `receive`/`synchronize` inputs `accept_from`, `sender_check`,
  `accept_trust_classes` and `always_ask_trust_classes` (§5.17); received
  items' `sender` and `sender_identity`, and on `synchronize` the same
  beside the agreed state; `constrain` output `tally` (§5.15, §5.16);
  optional inputs `retrieve.filter` and `retrieve.references`,
  `state.observations`, `plan.context`, `critique.context` and
  `explain.constraints`, which catalogs already bound; `transform.output`
  is `object|array` (a list of records, say), so a reference to it needs
  an annotation (B204): a breaking change for a catalog that reads it
  unannotated (§11.4)

## Appendix D: Changes from 1.1.0

Every change is backward compatible: a workflow valid under 1.1.0 is valid
under 1.2.0 and runs the same way unless its host opts in to a new feature;
a change that would invalidate a 1.1 workflow is phased in as a warning.
Clarifications of 1.1 semantics apply to 1.0 and 1.1 workflows too.

### D.1 Tool-calling hosts (RFC-0005)

**Clarification** (applies to workflows of every version):

- Checkpoint use for steps stated (§5.2.2): one checkpoint per gated step,
  used up just before the capability is called; the most recently taken
  valid one first; with none valid, the executor has its host take one
  (F501 if it fails); validity ends at the end of a wait or delay and at a
  resumption; a gate or failure-mode rollback restores the latest
  checkpoint (F503 with none), and a `rollback` step restores the one its
  input names. This is the reference executor's behaviour since 1.1.0

**New in 1.2.0:**

- Tool-calling hosts (§5.18): tool bindings
  (`schemas/interop/tool_binding.schema.json`), unbound tools,
  classification by effect, composite tools, `requires`, checkpoints and
  approval over calls, refusals, records and fail-closed loading, text-only
  results (binding every host that carries an output as a string, workflow
  hosts included) and capability checks; class SL, whose layers apply
  §5.18.5–§5.18.10, with binding and call-sequence fixtures (§10.4)
- The terms tool-calling host, call, tool binding, safety layer, layer
  scope and execution boundary (§2)
- Codes V110, V111, R407, F506, W617; V101, V102, V105, V107, V109, R402,
  F501–F504, W601 and W602 cover bindings and calls too, and §9.1 says a
  V-code keeps its meaning when a safety layer uses it for a call (§9)

### D.2 Approval, deferral and run identity (RFC-0006, Part A)

**Clarifications of 1.1 semantics** (apply to 1.0, 1.1 and 1.2 workflows):

| Area | 1.1.0 text | 1.2.0 |
|------|------------|-------|
| Default approval request | Not stated | A step that requires approval and has no `approval` field is asked as `approval: {approver: {kind: human}}`: in session, shown its resolved inputs, no expiry; omitted members take their defaults; `expires` runs from the request (§5.14) |
| Approval digest input | "the canonical JSON of the shown values" | The array of resolved `shows` values in order (null when unresolved), `[inputs]` without `shows`, plus a `recheck` element on a re-ask; SHA-256 as lowercase hex, compared regardless of case (§5.14); normative vectors with a `kind` per vector (§10.3) |
| I-JSON shown values | "integers within ±2^53" | An integer, a number written without a fraction or an exponent, has magnitude at most 2^53 and is refused otherwise; every other number is a binary64 value, so `1e+21` is valid; whatever reads values from JSON text refuses a member name twice in one object (§5.14) |
| `approval.mode` | Listed values only | `in_session` and `out_of_band` defined; a human approver is still never asked in an unattended run (§5.14) |

**New in 1.2.0:**
- Resumption of a deferred run (§5.14.1): the deferred steps run again, with
  the steps that ran ahead of them that they read and a checkpoint step whose
  invalidated checkpoint a re-entered mutation binds; nested deferred runs
  continue; a queued step is asked afresh (of a person when attended), the
  request names `queued_action_id`, and its `planned` record is updated in
  place, with the time and actor of each decision or supersession. The
  queued actions of a run that did not end `deferred` are never carried out
- With `identity@1`, approver identities on a decision
  (`approver_identities`), approvers counted by principal and checked against
  the requested kind and role, and, in a workflow that targets 1.2, the
  approver fields `sender_check` and `accept_trust_classes` (§5.17)
- A run keeps its actor while it continues: a restore for another actor is
  refused, a handoff cancels the run unless it ended `deferred`, and
  resumption may name a new actor (§5.17)
- `world_state_schema.yaml` 1.2.0: `ActionRecord.approval.approver_identities`,
  and descriptions of `approval.mode` and of `planned` records that a
  resumption updates

### D.3 Host protocol, runs and audit records (RFC-0006, Part B)

**Clarifications of 1.1 semantics** (apply to 1.0, 1.1 and 1.2 workflows):

| Area | 1.1.0 text | 1.2.0 |
|------|------------|-------|
| Parallel groups at run time | "steps of one group run concurrently" | Members are not ordered; an executor may run them in any order or concurrently, and a §5.19 executor runs them in list order; a group is complete when every member has finished; unfinished members are abandoned when a recovery escalates or ends the run, and a loop continues from its target (§5.2.3) |
| `join` | Free string | One defined value, `all_complete`; any other is W618 and ignored (§5.2.3) |
| Tick boundaries | Not stated | A `Sleep` ends at `until`; an action times out after its deadline, and an answer at the deadline is in time (§5.19.3) |
| Liveness probes | "the runtime polls it" | The host polls and reports `LivenessLost` (§5.13, §5.19.3) |
| Protocol traffic | Not stated | Not a `send` step, when it carries only the action's values (§5.19.6) |
| Retry backoff | `none`, `linear`, `exponential` named, schedule not stated | `linear` waits attempt × 1 s, `exponential` 2^(attempt−1) s (exponent at most 32), from the failure (§5.2), as the reference executor did |
| Executor-computed members | Not stated | `deadline`, `expires_at`, `Sleep.until`, `correlate`, `Completed.outputs`, `cause`, and the outputs the executor composes for waits, `invoke` and quorums (§5.19.1), as the reference executor did |
| Unknown response members | Ignored by the reference executor, not stated | Ignored (§5.19.1); a host ignores unknown action members |

**New in 1.2.0:**
- The host protocol (§5.19): actions, responses, run operations, time,
  saving and continuing a run (one writer, save before acting, at-least-once
  delivery keyed by `run_id` and `id`, a unique `run_id`, state integrity
  and a key where others can change stored states), cancellation (R408),
  protocol traffic, error reasons, and the run record every host keeps
  (§5.19.8); `schemas/host_protocol.schema.json`
- Trigger evaluation (§5.10.2): the host's duties, event acceptance and one
  run per `event_id`, fire times in the declared time zone (RFC 5545 for
  clock changes), the `every` anchor, the meaning of `overlap`, missed fire
  times
- Audit records (§6.4): action records and canonical events, written or
  exported; the executor's record mode `actions`; `audit` records its event
  in a record of its own; `require_record`; required and best-effort
  capture, and no silent capture failure
- Manual trust overrides (§8.4)
- Class EX (§10.5): the runtime fixtures are normative for executors; the
  trigger vectors are normative (§10.3)
- Codes R408, W618, W619
- `world_state_schema.yaml` 1.2.0: `ActionRecord` `run_id`, `frame`,
  `step`, `capability`, `tool`, `call_id`, `checkpoint_id`, `code`,
  `reason_code`, `details`, `recorded_by`, `prev_hmac`, `hmac`; status
  `cancelled`; `approval.decision_id`
- Ontology 2.2.0: `audit` input `require_record` and output `record`

### D.4 Delegation, catalogs and diagnostics (RFC-0007)
<!-- owner: S3; entries: S3.md part 2.24 -->

### D.5 Evidence, grounding and secrets (RFC-0008)

**Clarifications of 1.1 semantics** (apply to 1.0, 1.1 and 1.2 workflows):

| Area | 1.1.0 text | 1.2.0 |
|------|------------|-------|
| Grounded and inferred outputs | "Every claim MUST be evidence-backed or explicitly marked as inferred" | An output is grounded by an anchor to evidence its producer had, or marked inferred by `inference_method` and `confidence`; an empty list grounds nothing; an output reporting an action is grounded by a `record` anchor to it (§3.1, §6.5) |
| Available evidence | Not stated | An anchor grounds a claim only if its producer had the evidence; a host MUST NOT return an anchor it knows its producer did not have (§6.5) |
| `confidence` | Undefined; `meta.principles` said every capability returns one | A self-reported probability that the output's claim is correct, with no threshold in the Standard; the principle matches the contracts (§4.1.1) |
| `raw` of a canonical event | "Original unmodified data" | Unmodified except that each secret is replaced; `redactions` may list where (§6.2, §6.7) |
| `retention_policy` | "How long to retain" | Applies to the store the records are written to; a session-scoped store cannot keep them longer (§6.3) |

**New in 1.2.0:**
- Grounding (§3.1, §5.20): the extension `grounding@1` and the policies a
  host applies to a run (covering its nested runs) or to calls make the
  executor or the layer check host outputs: `acs:` citations covered by a
  bound reference, the host's `evidence_seen`, `attested`, legacy items
  that do not count. F505, reserved since 1.0, is raised and can fire a
  failure mode. Opt-in. In a workflow that targets 1.2, `grounding` without
  `grounding@1` is V106; in a 1.0 or 1.1 workflow it stays W604. With
  `grounding@1`, an `invoke` step carries its nested run's anchors
- Common output fields (§4.1.1): `confidence`, `inference_method` and
  `uncertainty` are defined; every output contract declares them (ontology
  2.2.0); `inference_method` has a vocabulary a producer SHOULD use
- Evidence anchors (§6.5): one anchor type for outputs, events and records,
  with `digest`, the kind `record` and vendor kinds; the `acs:` ref scheme;
  `evidence_anchors` items are anchors, a bare string or another object
  being the deprecated legacy forms, accepted until 2.0
- Evidence records and stores (§6.6): what an evidence store keeps and
  states, and the optional `acs.evidence_recorded` notification for
  evidence, canonical events and audit records
  (`schemas/interop/evidence.schema.json`)
- Secrets (§6.7): secrets never enter evidence, records, diagnostics,
  traces or persisted memory; redaction and its marker; a `persist` of a
  secret is refused
- Retention (§6.3): `audit.retention` is a duration (W614 otherwise);
  `audit` reports its `store`
- The `Output` response's `evidence_seen` (§5.19.1); grounding vectors and
  `grounding_` runtime fixtures (§10.3)
- `event_schema.yaml` and `world_state_schema.yaml` 1.2.0 share one
  `Anchor` and one `Uncertainty`; events MAY record `redactions`

### D.6 Checkpoint, rollback, send and memory (RFC-0009)
<!-- owner: S5; entries: S5.md part 2.15 -->

### D.7 Profiles, trust, versioning and schema dialect (RFC-0010)

**Clarifications** (apply to workflows of every version):

- Contract schemas: 1.1 called them "JSON Schema"; they are written in the
  schema dialect, Draft 2020-12 keywords plus `type: any`, `a|b`, `$ref`
  with merged siblings and `nullable`, with a Draft 2020-12 rendering
  (§4.1.2). An ontology whose contract keeps a `$ref` that names nothing,
  is cyclic or nests too deep is refused at load
- Entity ids: 1.1's §7.1 printed `namespace:type:id` while the taxonomy
  gave `<class>:<namespace>/<local_id>`; the taxonomy's form is the one
  (§7.1)
- Trust score: 1.1 listed the factors; the score is
  `weight × confidence × decay`, with confidence 1 when none is reported,
  an age below zero counting as zero, a `min_trust` above 0.5 applying, and
  no score for evidence without a static weight (§8.1, §8.3)
- Conflict resolution: 1.1 named the strategies; they are defined, with
  the default `highest_score` and tie-breaking by the model's
  `tie_breakers` (§8.2)
- Version declaration: 1.0, 1.1 and 1.2 are supported; W616 covers any
  feature newer than a workflow's target; rules for 1.2 targets apply only
  to a workflow that declares one; the catalog header is an explicit value
  of the start operation (§11.5)

**New in 1.2.0:**

- Domain profiles, applied by hosts, safety layers and validators, which
  tighten flags, checks, evidence, confidence and destinations and replace
  trust weights (§5.21); `profiles/profile_schema.yaml` 1.0.0 as a supporting
  schema; `ActionRecord.person_required` (`world_state_schema.yaml` 1.2.0)
- How the ontology is versioned and how documents cite it (§11.6); the
  artifacts of a version (§11.7)
- `entity_taxonomy.yaml` 1.1.0 (`id_convention.pattern`);
  `authority_trust_model.yaml` 1.2.0 (`field_authority.fields`, descriptions)
- The start operation's `header` member (§5.19.2, §11.5)
- Normative trust, profile and entity id vectors (§10.3)
- The prefix `x-acs-` reserved for this Standard (Appendix B)
- The terms domain profile, schema dialect and entity id, and the trust
  score defined by its formula (§2)

---

**End of Standard**
