# Standard: Agent Capability Ontology + Workflow DSL

**Version:** 1.1.0
**Status:** Draft — accepted by RFC-0003; sections marked *(pending
reference implementation)* are normative but not yet enforced by the
reference validator
**Date:** 2026-10-27
**Supersedes:** [STANDARD-v1.0.0](STANDARD-v1.0.0.md) (still supported; see §11.5)

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
   approval, delegation, quorum) that a workflow opts into

Changes from 1.0.0 are listed in [Appendix C](#appendix-c-changes-from-100).

### 1.1 Normative References

- JSON Schema Draft 2020-12
- YAML 1.2
- Semantic Versioning 2.0.0
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
| **Trust Score** | Authority-weighted, confidence-weighted, recency-decayed score |
| **Binding** | A reference from one step to another step's output |
| **Gate** | A conditional check that can halt or redirect workflow execution |
| **Checkpoint** | A saved state that enables rollback |
| **Grounding** | Anchoring claims to evidence references |
| **Diagnostic** | An error or warning reported by a validator or executor (§9) |
| **Effective flag** | The safety flag a step is treated as: the stricter of its declaration and the ontology (§5.2.1) |
| **Runs before** | Step A runs before step B when A comes earlier in the step list and is not in B's parallel group (§4.3) |

---

## 3. Design Principles

These principles are non-negotiable. An implementation that violates them is non-conformant.

### 3.1 Grounded Claims
Every claim MUST be evidence-backed or explicitly marked as inferred. Ungrounded claims MUST include an `inference_method` and `confidence` score.

### 3.2 Auditable Transforms
Every transformation MUST be either:
- Deterministic (same input produces same output)
- Documented with explicit loss (what information is discarded)

### 3.3 Safety by Construction
- Mutation REQUIRES checkpoints
- Actions REQUIRE plans
- Rollback MUST be possible for any mutation
- A workflow cannot weaken a capability's safety flags (§5.2.1)

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

### 4.1 Capability Definition

A capability MUST define:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (lowercase, hyphens allowed) |
| `layer` | enum | Yes | Classification layer |
| `description` | string | Yes | Human-readable purpose |
| `input_schema` | object | Yes | JSON Schema for inputs |
| `output_schema` | object | Yes | JSON Schema for outputs |
| `risk` | enum | No | `low` (default), `medium`, `high` |
| `mutation` | boolean | No | Whether the capability changes persistent state (default false) |
| `requires_checkpoint` | boolean | No | A checkpoint must precede each use (default false) |
| `requires_approval` | boolean | No | Each use needs approval (default false) |
| `mutation_overridable` | boolean | No | A step may declare `mutation: false` (§4.4) |

Relationships between capabilities are edges (§4.3), listed in the
ontology's `edges` array as `{from, to, type, rationale?}`.

### 4.2 Layers

Capabilities are classified into 9 cognitive layers:

| Layer | Purpose | Mutation | Count |
|-------|---------|----------|-------|
| **PERCEIVE** | Acquire information from the world | No | 4 |
| **UNDERSTAND** | Make sense of information | No | 6 |
| **REASON** | Plan and analyze | No | 4 |
| **MODEL** | Represent the world | No | 5 |
| **SYNTHESIZE** | Create content | No | 3 |
| **EXECUTE** | Change the world | Yes | 3 |
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
is not in the same `parallel_group`**: steps of one group run concurrently,
so neither completes before the other starts.

**Enforcement semantics:**

| Edge | Rule | Diagnostic |
|------|------|------------|
| `requires` | For every `to` step, some `from` step runs before it | V102 per `to` step |
| `precedes` | If the workflow contains both, every `to` step has a `from` step running before it. It never requires `from` to be present. | V102, once per edge, at the first offending `to` |
| `soft_requires` | Every `to` step has at least one of its incoming `soft_requires` sources running before it (any-of per target) | W601 per step |
| `conflicts_with` | The two capabilities never share a `parallel_group`; in sequence they are allowed (a rollback after a mutation is the normal recovery pattern) | F504, once per (group, pair) |
| `enables`, `alternative_to`, `specializes` | None | — |

Validators MUST implement these checks in time linear in the number of steps.

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
| `success` | array | Success criteria |
| `description` | string | Long description |
| `spec_version` | string | Standard version targeted (§11.5) |
| `workflow_extensions` | object | Extension declarations (§5.9) |
| `triggers` | array | How runs start (§5.10) |
| `domain`, `profile`, `risk_propagation`, `data_flow` | — | Recognised descriptive fields |

A missing required field is S304. An unrecognised field is W604 and is
otherwise ignored; fields whose name starts with `x-` are vendor extensions
and are never reported (§11.3).

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
| `retry` | object | `{max, backoff}` |
| `parallel_group` | string | Group ID; steps of one group run concurrently |
| `join` | string | How to wait for parallel completion |
| `mapping_ref` | string | Transform mapping file (missing file: S301) |
| `output_conforms_to` | string | `file#/pointer` the output must match (S301/S302) |
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

Validators, executors and safety layers MUST act on effective flags. A
declaration stricter than the ontology (e.g. `requires_approval: true` on
`observe`) is allowed and takes effect: a step whose effective
`requires_checkpoint` is true needs a `checkpoint` step running before it
(§4.3), else F501 — reported as V102 instead where the ontology's
`requires` edge from `checkpoint` already demands it.

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
no type is B205.

### 5.4 Typed Binding Rules

1. Untyped bindings infer type from the producer's output schema.
2. An annotation MUST be compatible with the schema node's type, else B203.
3. Annotations are REQUIRED where inference is ambiguous (B204):
   - Union schemas (`oneOf`, `anyOf`, type lists)
   - Missing type metadata
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

### 5.6 Gate Semantics

```yaml
gates:
  - when: ${checkpoint_out.checkpoint_id} == null
    action: stop
    message: "No checkpoint created. Do not mutate."
  - when: ${verify_out.passed} == false
    phase: after
    action: rollback
    message: "Verification failed. Rolling back."
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `when` | string | Yes | Expression (§5.8) |
| `action` | enum | Yes | `stop`, `rollback`, `skip`, `warn` (else S303) |
| `message` | string | No | Explanation for the action |
| `phase` | enum | No | `before` (default) or `after` the step |

- Order: `condition` → before-gates in declaration order → the step →
  after-gates.
- A before-gate cannot read the step's own output (B202). A gate that
  reads it without declaring `phase` is treated as `after` and reported as
  W603 (`DEPRECATED_FORM`).
- An after-gate cannot `skip` (S303): the step has already run.
- Actions at runtime: `stop` → R403; `skip` → the step is skipped;
  `rollback` → roll back to the latest checkpoint, then R403; `warn` → a
  trace warning.

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
| `on_error` | code or list | No | Fires on a code the step failed with: R401, R402, R403, F501, F502, F504 (§5.12) |
| `recovery` | string or object | No | Prose, or a recovery loop (§5.12) |

A failure mode fires when the step raised a matching `on_error` code or its
`when` is true; the first match in declaration order applies. A failure
mode with neither is documentation only. `recovery.inject_context` values
are references checked like bindings and may read the step's own output.

### 5.8 Condition Expressions

`condition`, `gates[].when` and `failure_modes[].when` hold expressions.
They MUST be YAML strings (else S303).

#### 5.8.1 Grammar

```ebnf
expr      = or_expr ;
or_expr   = and_expr { "||" and_expr } ;
and_expr  = cmp_expr { "&&" cmp_expr } ;
cmp_expr  = unary [ cmp_op unary ] ;            (* non-associative *)
cmp_op    = "==" | "!=" | "<=" | ">=" | "<" | ">" ;
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
V108; a malformed annotation alone is B205.

#### 5.8.2 Evaluation

- Values are JSON values. `==` and `!=` are total, deep and structural;
  numbers compare by binary64 value; values of different kinds are unequal.
- Ordering (`<`, `<=`, `>`, `>=`) is defined for number/number,
  string/string (by code point) and boolean/boolean (`false < true`); any
  other pair is an evaluation error.
- `!`, `&&`, `||` require booleans. `&&` and `||` absorb errors as CEL does:
  a determining operand (`false` for `&&`, `true` for `||`) decides the
  result even if the other operand is an error.
- The result MUST be a boolean.
- An absent path, an out-of-range index, or the output of a skipped step is
  `null`.

An evaluation error is R405 (`EXPRESSION_ERROR`) and is recorded in the
trace. Its effect is fail-safe by site: a **gate** whose `when` errors
fires; a **condition** that errors is false; a **failure-mode** `when` that
errors does not fire.

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
| Unknown root / bad path | B202 / B201 |
| Annotation incompatible with the schema | B203 |
| Ordering or logic on a value of unknown type with no annotation | B204 |
| Operator applied to kinds it does not accept; non-boolean result | B206 |
| An ordering operand may be null (optional field, skippable producer) | W610 |
| Equality between kinds that can never be equal | W611 |

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
| `wait@1` | step `wait` (§5.13) |
| `approval@1` | step `approval` (§5.14) |
| `delegation@1` | bindings of `delegate.fresh_context`, `.model_family`, `.role` and `receive`/`synchronize` `accept_from` (§5.15) |
| `quorum@1` | step `quorum` (§5.16) |

`failure_modes[].when` and `.on_error` are part of base 1.1, not an
extension: a consumer that ignores them only loses an optional trigger.

A validator MUST NOT accept a declaration of an extension it does not
check: listing one is V106, as for an unknown extension. *(The reference
validator implements all six.)*

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
| `attendance` | `attended` or `unattended`. Default: `manual` → attended, `invoke` → the invoker's, `schedule`/`event` → unattended |

**Cron:** minute 0–59, hour 0–23, day-of-month 1–31, month 1–12 or JAN–DEC,
day-of-week 0–7 or SUN–SAT (0 and 7 are Sunday); `*`, lists, ranges and
`/` steps. When both day fields are restricted, a day matches either (Vixie
semantics). `CRON_TZ=`/`TZ=` prefixes are not allowed; use `timezone`.

A `triggers` that is not a list, a trigger without a valid `kind`, a
`schedule` or `event` that is missing for its kind or present for another
kind, a malformed cron, duration or time zone, and an unknown `overlap` or
`attendance` are S303 or S304 (missing). Unknown trigger fields are W604.

An `invoke` step whose target declares triggers but none of kind `invoke`
is V107. A step whose effective `requires_approval` is true, in a workflow
with an unattended trigger, and with no `approval.when_unattended` is W606:
an unattended run fails there (F502).

#### 5.10.1 Durations

A duration is `<digits>(ms|s|m|h|d)` or an ISO-8601 day-time duration
`P[nD][T[nH][nM][n[.n]S]]` with at least one component, a `T` followed by at
least one time component, and a fraction (up to 9 digits) on seconds only.
Years, calendar months and weeks are not allowed: their length varies. An
invalid duration in an extension field is S303; an invalid legacy step
`timeout` is W614 (1.0 allowed any string, so it stays accepted but cannot
be enforced).

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
code or a list: R401, R402, R403, F501, F502, F504; anything else is S303 —
an expression error, R405, is fail-safe at its site and never fails a step)
or its
`when` is true after the step. A structured recovery whose failure mode has
neither can never fire and is W609.

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
  `input_bindings.workflow`). A target that is not in the catalog is W607
  (it cannot be checked); invoke cycles among catalog workflows, including a
  workflow invoking itself, are V105.

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
| `liveness` | `mode` (`push`: the source sends heartbeats; `probe`: the runtime polls it) and `interval` (a duration longer than zero), both required (S304); `failure_threshold` (integer ≥ 1, default 3) |

`wait` is allowed only on `receive`, or on `synchronize` whose literal
`agents` list has at least two entries (else S303). The step MUST declare a
`timeout` (S304) that parses as a duration (S303; the W614 leniency for
legacy timeouts does not apply to a wait, which must end). Liveness MUST
be able to fail before the timeout: `interval × failure_threshold` less than
the timeout, else S303. The matching event is delivered in the step's
output (`data`, under the capability's output contract); a lapse raises
R401.

A step that requires a checkpoint (`mutate`, `send`, or a raised
`requires_checkpoint`) whose latest checkpoint runs before a `wait` is
W608: a wait can last hours and the run may resume elsewhere, so a
checkpoint taken before it no longer authorises the step. Take a new
checkpoint after the wait. "Runs before" is as in §4.3: a wait in the
checkpoint's parallel group counts (the checkpoint may finish first), one
in the step's own group does not. A step that waits itself acts after its
wait, so any earlier checkpoint is stale for it; a handler (§5.11) is
judged at its earliest targeting step, including that step's own wait.

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
| `approver` | Required (S304). `kind` (required): `human` or `standing_mandate`; `role`; `min_approvers` (integer ≥ 1, default 1); `mandate_ref`, required for and only for a standing mandate (S304 / S303) |
| `mode` | `in_session` (default) or `out_of_band` |
| `shows` | References whose values the approvers see (each a `${...}` reference, else S303) |
| `binds_to` | `digest` (default): the decision binds to the shown values |
| `recheck` | `source` (required, a `${...}` reference re-read before acting, else S303), `compare`: `version` or `digest` (default), `on_change`: `reask` (default), `replan` or `stop` |
| `expires` | How long a decision stays valid: a duration longer than zero |
| `when_unattended` | `fail` (default), `skip` or `defer_to_queue` |

`approval` is allowed only where the effective `requires_approval` is true
(S303); other values above are S303 when malformed, and unknown fields W604.
A decision is valid only if the SHA-256 digest of the canonical JSON of the
shown values matches, at least `min_approvers` distinct approvers agree, it
has not expired, and it has not been used before. Unattended runs follow
`when_unattended`: `fail` → F502, `skip` → the step is skipped,
`defer_to_queue` → the run ends `deferred` with a `planned` action record.
The decision is recorded on the action record (`world_state_schema.yaml`
1.1.0: `approval` with the digest, decision and approvers; status
`rejected` or `expired` when it was refused or lapsed).

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
delegator's context), `model_family` and `role`, and reports the values the
host actually used as `effective`. `receive` and `synchronize` accept
`accept_from` (a list of principals): received items from other principals
are dropped and counted, and each kept item's `sender` is the
host-authenticated principal. Binding any of these inputs needs
`delegation@1` (V106); they are typed by the ontology like any other input.

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
    forbidden_inputs: [author_notes]
    require_fresh_context: true
    require_model_families: [claude, gpt]
```

`quorum` is allowed only on `constrain` with literal
`action_on_violation: block` (S303), so a failed quorum stops the run:

| Field | Description |
|-------|-------------|
| `verdicts` | Required: reference to the reviews (`review_verdict_schema.yaml#/review_verdict` items) |
| `reviewers` | Required: `store_as` names of `delegate` steps that run before this one (else V107), delegating to distinct agents when the agents are literal (else F504) |
| `vocabulary` | Required: at least two distinct verdict values |
| `pass_values` | Required: a non-empty subset of the vocabulary |
| `blocking_values` | A subset of the vocabulary, disjoint from `pass_values`, that vetoes |
| `min_pass` | Required: 1 ≤ `min_pass` ≤ number of reviewers |
| `pinned_to` | Required: reference every counted verdict must be pinned to (e.g. the commit reviewed) |
| `forbidden_inputs` | Stores or inputs no reviewer may depend on, directly or transitively through bindings — including context a recovery loop injects (`${_recovery.*}`) — (names that are neither inputs nor stores of steps running before the quorum step: V107; a dependency: F504) |
| `require_fresh_context` | Every reviewer binds `fresh_context: true` (F504 otherwise) |
| `require_model_families` | Families the reviewers must cover; F504 when every reviewer binds a literal family and they do not cover the set (otherwise checked at runtime) |

A missing required field is S304; a malformed value is S303; `verdicts` and
`pinned_to` must be references; unknown fields are W604.

A verdict counts once per reviewer: only if its `reviewer_id` is a
reviewer delegate's agent, its `pinned` equals the resolved `pinned_to`,
its value is in the vocabulary, it is the first from that reviewer, and
(when required) the delegate's `effective` settings show a fresh context.
The step is compliant iff no counted verdict is blocking, passes ≥
`min_pass`, and model-family coverage holds; otherwise F504. The output
gains `tally` (`passes`, `blocks`, `abstains`, `voters`).

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

### 6.2 Observation Requirements

Field names in this section are those of the `event` object in
`event_schema.yaml`. They belong to the **canonical-event namespace**, which is
distinct from the capability-I/O namespace of §4.1 — a capability's
`evidence_anchors` output and an event's `anchors` field are different things.

All canonical events MUST record:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_id` | string | Yes | Unique event ID |
| `timestamp` | string | Yes | ISO-8601 time of observation |
| `source` | object | Yes | Where observed (`kind`, `name`) |
| `event_type` | string | Yes | Normalized event type |
| `raw` | any | Yes | Original unmodified data |
| `canonical` | object | Yes | Normalized data |
| `anchors` | array | Yes | Links to original evidence |
| `provenance` | object | Yes | Traceability record |

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
| `retention_policy` | object | No | How long to retain |

---

## 7. Identity Resolution Policy

### 7.1 Entity Identification

Entities MUST have hierarchical namespaces:
```
namespace:type:id
example: org.company:user:12345
```

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

Trust scores MUST support:

| Factor | Description |
|--------|-------------|
| Source ranking | Static authority weight per source |
| Time decay | Score decreases over time (configurable half-life) |
| Field authority | Sources may be authoritative for specific fields |
| Confidence weight | Self-reported confidence from source |

Time decay MUST be a true half-life: the decay factor for an observation of age
equal to the configured `half_life` MUST be `0.5`. Implementations SHOULD use
`0.5 ** (age / half_life)`.

`decay_model.min_trust`, when present, is a floor on the **decay factor** — not
on the composed score of §8.2 and not on the static source weight. Age alone
therefore never reduces an observation's weight to zero; it only removes that
observation's recency advantage over fresher ones.

### 8.2 Conflict Resolution

When sources disagree, resolution strategies include:

| Strategy | Description |
|----------|-------------|
| `prefer_authoritative_sources` | Highest authority wins |
| `prefer_recent` | Most recent wins |
| `prefer_high_confidence` | Highest confidence wins |
| `merge_with_uncertainty` | Keep both with uncertainty |
| `escalate_to_human` | Require human decision |

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

### 9.2 Validation Errors

| Code | Name | Description |
|------|------|-------------|
| V101 | UNKNOWN_CAPABILITY | Capability ID not found in ontology |
| V102 | MISSING_PREREQUISITE | A `requires` or `precedes` edge is violated (§4.3) |
| V103 | INVALID_STEP | Step is not a mapping, or its `capability` is missing or not a string |
| V104 | DUPLICATE_STORE_AS | Same store_as used by multiple steps |
| V105 | CIRCULAR_DEPENDENCY | Workflow contains circular dependencies |
| V106 | UNSUPPORTED_EXTENSION | `workflow_extensions.requires` lists an unknown or unsupported extension, or an extension field is used without its declaration |
| V107 | UNRESOLVED_TARGET | A `goto_step`, `on_exhausted`, `reviewers`, `delivers_to` or invoke target does not resolve, or resolves to the wrong kind of step |
| V108 | INVALID_EXPRESSION | Expression syntax error or limit exceeded |
| V109 | UNSUPPORTED_SPEC_VERSION | The declared standard version is not supported |

### 9.3 Binding Errors

| Code | Name | Description |
|------|------|-------------|
| B201 | INVALID_BINDING_PATH | Referenced path does not exist in the producer's schema |
| B202 | MISSING_PRODUCER | Root is neither an earlier store_as nor an input |
| B203 | TYPE_MISMATCH | Annotation or inferred type incompatible with the schema or consumer |
| B204 | AMBIGUOUS_TYPE | Type cannot be inferred, annotation required |
| B205 | INVALID_ANNOTATION | Type annotation names no type |
| B206 | EXPRESSION_TYPE_ERROR | Operator applied to kinds it does not accept, or non-boolean result |

### 9.4 Schema Errors

| Code | Name | Description |
|------|------|-------------|
| S301 | SCHEMA_NOT_FOUND | Referenced schema or mapping file not found |
| S302 | INVALID_REF | $ref or JSON pointer cannot be resolved |
| S303 | SCHEMA_VALIDATION_FAILED | A field has the wrong type or value |
| S304 | MISSING_REQUIRED_FIELD | Required field not present |

### 9.5 Runtime Errors

| Code | Name | Description |
|------|------|-------------|
| R401 | EXECUTION_TIMEOUT | Step exceeded timeout, or a wait lapsed |
| R402 | EXECUTION_FAILED | Step execution failed |
| R403 | GATE_BLOCKED | A gate stopped the run, or a condition was false with `skip_if_false: false` |
| R404 | RECOVERY_EXHAUSTED | Max recovery loops exceeded |
| R405 | EXPRESSION_ERROR | An expression failed to evaluate (§5.8.2) |

### 9.6 Safety Errors

| Code | Name | Description |
|------|------|-------------|
| F501 | CHECKPOINT_REQUIRED | Mutation without checkpoint |
| F502 | APPROVAL_REQUIRED | Action requires approval |
| F503 | ROLLBACK_FAILED | Could not restore checkpoint |
| F504 | CONSTRAINT_VIOLATED | Policy constraint violated (incl. conflicting capabilities in one parallel group) |
| F505 | PROVENANCE_MISSING | Claim without provenance |

### 9.7 Warnings

| Code | Name | Description |
|------|------|-------------|
| W601 | SOFT_REQUIREMENT_UNMET | No `soft_requires` source runs before the step |
| W602 | SAFETY_FLAG_DOWNGRADE | Step declares a flag weaker than the ontology; the ontology value applies |
| W603 | DEPRECATED_FORM | Accepted legacy form (self-reading gate without `phase`, goto_step by capability id) |
| W604 | UNKNOWN_FIELD | Unrecognised field, ignored; with a closest-match hint |
| W605 | MISSING_SPEC_VERSION | No `spec_version` and no version header |
| W606 | UNATTENDED_APPROVAL | An unattended trigger reaches an approval step without `when_unattended` |
| W607 | UNRESOLVED_WORKFLOW | invoke target not in the loaded catalog |
| W608 | WAIT_SPANS_CHECKPOINT | A wait sits between a checkpoint and a later step that requires one (§5.13) |
| W609 | UNTRIGGERED_FAILURE_MODE | Structured recovery with neither `on_error` nor `when` |
| W610 | NULLABLE_OPERAND | An ordering operand may be null |
| W611 | CONSTANT_COMPARISON | Equality between kinds that can never be equal |
| W612 | MANGLED_REFERENCE | YAML read a typed reference as a mapping; quote it |
| W613 | UNREACHABLE_HANDLER | A handler step no escalation targets |
| W614 | INVALID_DURATION | Legacy `timeout` outside the duration grammar |

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
    "field": "requires_aproval"
  },
  "suggestion": "did you mean 'requires_approval'?"
}
```

`location` MAY carry further keys (`ref`, `prerequisite`, `expected_type`,
`actual_type`, `column`, …). A single error MAY be wrapped as
`{"error": {...}}` and a list as `{"errors": [...]}`, as in 1.0.

---

## 10. Conformance

### 10.1 Conformance Levels

| Level | Requirements |
|-------|--------------|
| **L1** | Validate structure, capability existence and ontology edges |
| **L2** | Resolve $ref schemas and infer binding types |
| **L3** | Validate binding types against consumer contracts; check expressions |
| **L4** | Emit patch suggestions using coercion registry |

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
- Infers binding types from producer schemas
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

Fixture expectations MAY list `expected_warning_codes`; an empty list means
the fixture MUST produce no warnings. Expression fixtures
(`tests/conformance/expressions/eval.json` and `check.json`) are
language-neutral; the reference suite also runs them against cel-go to
check §5.8.2's CEL compatibility. Runtime fixtures
(`tests/conformance/runtime/*.json`) script runs of the reference executor
— the actions it must request, the responses it gets, and the end and trace
it must reach — for the runtime semantics of §5.6, §5.7, §5.8.2 and
§5.11–§5.16; they are informative for implementations that execute
workflows.

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

### 11.5 Version Declaration

A workflow declares the standard version it targets with `spec_version`
(`"1.1"`, optionally with a patch: `"1.1.0"`), or a catalog file declares it
for all its workflows with a header among its leading comment lines (a BOM,
blank lines, `%` directives and a `---` marker may precede it):

```yaml
# Standard version: 1.1.0
workflow_name:
  goal: ...
```

`spec_version` takes precedence over the header. A version is
`digits.digits[.digits]`; `spec_version` MUST be a string (quote it in
YAML). Neither present → W605. A version the validator does not support →
V109. A validator for this version MUST support 1.0 and 1.1.

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
  store_as: plan_out
- capability: constrain
  purpose: Check the plan against policy.
  input_bindings:
    target: ${plan_out}
    constraints: [change_policy]
  store_as: policy_out
- capability: checkpoint
  purpose: Save a restore point.
  store_as: checkpoint_out
- capability: mutate
  purpose: Apply the change.
  input_bindings:
    target: ${plan_out}
  gates:
    - when: ${policy_out.compliant} == false
      action: stop
  store_as: mutate_out
- capability: verify
  purpose: Check the result.
  input_bindings:
    target: ${mutate_out}
    conditions: [change_applied]
  store_as: verify_out
- capability: audit
  purpose: Record what happened.
  input_bindings:
    event: ${verify_out}
  store_as: audit_out
```

**Pattern: Multi-Source Integration**
```yaml
- capability: retrieve
  purpose: Fetch source A.
  store_as: source_a
- capability: retrieve
  purpose: Fetch source B.
  store_as: source_b
- capability: integrate
  purpose: Merge both sources.
  input_bindings:
    sources: ["${source_a}", "${source_b}"]
  store_as: integrated
```

**Pattern: Recovery Loop**
```yaml
- capability: verify
  purpose: Check the result.
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

### 13.2 Informative References

- [RFC-0001: Agent Capability Ontology](RFC-0001-agent-capability-ontology-and-workflow-dsl.md)
- [RFC-0003: Orchestration Extensions and Validation Semantics](RFC-0003-orchestration-extensions.md)
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

Field names starting with `x-` are reserved for vendor extensions.

## Appendix C: Changes from 1.0.0

**Clarifications of 1.0 semantics** (apply to 1.0 and 1.1 workflows):

| Area | 1.0.0 text | 1.1.0 |
|------|------------|-------|
| `precedes` | "MUST complete before the target begins" (read by validators as "must be present") | Ordering only when both are present (§4.3) |
| `conflicts_with` | "MUST NOT appear in the same workflow" | MUST NOT run concurrently; sequence allowed (§4.3) |
| `soft_requires` | "SHOULD be satisfied when available" | Any-of presence per target, W601 (§4.3) |
| Concurrency | Unspecified | A step in the same parallel group does not run before another (§4.3) |
| Safety flags | Listed as optional step fields | Inherit from the ontology; downgrades ineffective, W602 (§5.2.1) |
| Unknown fields | "SHOULD ignore" | Ignored and reported, W604; `x-` exempt (§11.3) |
| Version header | "SHOULD warn if missing" | `spec_version` or header; W605 / V109 (§11.5) |
| B205 | "Type annotation does not match schema" | Annotation names no type; a mismatch is B203 (§9.3) |
| `inputs` | Required | Optional, default `{}` (§5.1) |

**New in 1.1.0:**
- Condition expression language with CEL compatibility (§5.8), gate `phase`
  (§5.6) and failure-mode `when` (§5.7)
- Diagnostic severities and warning codes W601–W614 (§9.1, §9.7); codes
  V106–V109, B206, R405
- `mutation_overridable` (§4.4)
- Orchestration extensions and their declaration: triggers, handler steps,
  recovery and escalation, wait, approval, delegation, quorum (§5.9–§5.16)
- Canonical schemas: `event_schema.yaml` 1.1.0 (`source.kind` gains
  `agent`); `world_state_schema.yaml` 1.1.0 (action status `rejected` and
  `expired`, and the `approval` record of §5.14)
- `review_verdict_schema.yaml` 1.0.0 for quorum verdicts (§5.16)
- Ontology: `delegate` inputs `fresh_context`, `model_family`, `role` and
  output `effective`; `receive`/`synchronize` input `accept_from`; received
  items' `sender`; `constrain` output `tally` (§5.15, §5.16)

---

**End of Standard**
