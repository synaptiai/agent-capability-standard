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
(§10.5); they check §3.1's grounding where a grounding policy applies
(§5.20, F505) and apply domain profiles (§5.21), as the Python adapter does;
the Python SDK adapter and the Standard Agents binding implement §5.18 and
claim class SL (§10.4); `grounded_agency` implements §7.1's entity ids and
§8's arithmetic; §7.2 and §7.3 are not implemented
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
- A `checkpoint` MUST run before every `mutate`, `send` and `rollback` (the
  ontology's `requires` edges, V102) and before any step whose effective
  `requires_checkpoint` is true (F501), so a mutation that needs one has a
  restore point (§4.3, §4.4, §5.2.1)
- A plan is not required. Where a workflow has `plan`, it MUST run before
  `execute` and `mutate`; where it has `constrain`, before `execute`,
  `mutate`, `send` and `generate` (`precedes`: ordering only, V102). A
  `constrain` before `execute`, `mutate` and `send` is recommended (W601)
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

#### 4.1.1 Common Output Fields

<!-- owner: S4; text: S4.md part 2.5 -->

#### 4.1.2 Schema Dialect

<!-- owner: S6; text: S6.md part 2.6 -->

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
| `domain`, `profile`, `risk_propagation`, `data_flow` | — | Recognised descriptive fields |

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
| `retry` | object | `{max, backoff}`: up to `max` further attempts after R401, R402 or R406 (not after an R402 the executor raises itself before asking the host, such as an `invoke` input the target refuses: another attempt would be refused the same way); `max` an integer from 0 to 1000 and `backoff` one of `none` (also when absent or null), `linear`, `exponential` (else S303) |
| `parallel_group` | string | Group ID; steps of one group run concurrently |
| `join` | string | How to wait for parallel completion |
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

Validators, executors and safety layers MUST act on effective flags. A
declaration stricter than the ontology (e.g. `requires_approval: true` on
`observe`) is allowed and takes effect: a step whose effective
`requires_checkpoint` is true needs a `checkpoint` step running before it
(§4.3), else F501 — reported as V102 instead where the ontology's
`requires` edge from `checkpoint` already demands it.

#### 5.2.2 Checkpoint Use

<!-- owner: S1; text: S1.md part 2.6 -->

#### 5.2.3 Parallel Groups

<!-- owner: S2b; text: S2b.md part 2.6 -->

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
  run at the same time and would be left half done.
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
| `on_error` | code or list | No | Fires on a code the step failed with: R401, R402, R403, R406, F501, F502, F504 (§5.12) |
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
| `attendance` | `attended` or `unattended`. Default: `manual` → attended, `invoke` → the invoker's, `schedule`/`event` → unattended |

**Cron:** minute 0–59, hour 0–23, day-of-month 1–31, month 1–12 or JAN–DEC,
day-of-week 0–7 or SUN–SAT (0 and 7 are Sunday); `*`, lists, ranges and
`/` steps. When both day fields are restricted, a day matches either (Vixie
semantics). `CRON_TZ=`/`TZ=` prefixes are not allowed; use `timezone`.

A `triggers` that is not a list, a trigger without a valid `kind`, a
`schedule` or `event` that is missing for its kind or present for another
kind, a malformed cron or one that can never fire (`0 0 31 2 *`), a
malformed duration or time zone, and an unknown `overlap` or
`attendance` are S303 or S304 (missing). Unknown trigger fields are W604.

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

<!-- owner: S2b; text: S2b.md part 2.9 -->

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
code or a list: R401, R402, R403, R406, F501, F502, F504; anything else is S303 —
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
| `liveness` | `mode` (`push`: the source sends heartbeats; `probe`: the runtime polls it) and `interval` (a duration longer than zero), both required (S304); `failure_threshold` (integer ≥ 1, default 3) |

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
since the wait had already lapsed. To re-check a silent source, loop back
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
checkpoint after the wait. "Runs before" is as in §4.3: a wait in the
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
out takes the default the table gives. Two steps are asked of a person even
when their approver is a standing mandate: a step marked always-ask (§5.17)
and a queued step that an attended resumption re-enters (§5.14.1).

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
exponent, has a magnitude of at most 2^53. An executor refuses a value that
breaks either rule: a step whose resolved inputs hold one fails with R402,
and a response that carries one is malformed and changes nothing (§5.19.1). A
host that reads values from JSON text keeps each integer an integer: where
its parser would read an integer too long for it as a binary64 value, it
refuses the value instead. Every other number is a finite binary64 value,
written as RFC 8785 writes it, so `1e+21` (the `numbers` vector of §10.3) is
valid although its value exceeds 2^53. (RFC 7493 §2.2 recommends integers of
magnitude at most 2^53 − 1; 2^53 is also exactly representable in binary64,
and 1.1 executors accept it.)

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
actions. A recovery loop whose target is a deferred step, or one before it,
runs the step again, and an invoke step that runs its workflow again (a
retry) starts it afresh; either way the records of the earlier deferrals
become `rejected` ("superseded"), so a queue never holds the same action
twice.

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
   does (§5.12). The step's condition and gates are not evaluated again, and
   its inputs are not resolved again: they were when the invocation started.
   The queued actions of a nested run that failed are not carried out: the
   resumption supersedes them (`rejected`, "superseded").
4. **A deferred handler.** In a run whose handler was deferred (it ended
   `deferred` with an escalation's cause, §5.11), the steps of the normal
   flow that item 2 lists run first, in step order, and then the handler,
   with that cause; the run then ends as an escalation does.
5. **The approval.** A re-entered step that requires approval is asked
   afresh: its shown values and digest are computed now, a decision must
   match them, `expires` runs from the new request, and `recheck` re-reads
   its source after the decision. Every request for a re-entered queued step
   names its queued action (`queued_action_id`: the `action_id` of the
   record its deferral left), in either attendance, until the step goes on
   (item 6), after a recheck or in a retry too. In an attended resumption
   each such request is put to a person, a `human` approver keeping `role`,
   `min_approvers`, `sender_check` and `accept_trust_classes` and dropping
   `mandate_ref`. In an unattended resumption the step is asked as in any
   unattended run, and its `when_unattended` applies again.
6. **The record.** A re-entered step continues its queued action until it
   goes on to another step, is deferred again, or its run leaves it; a
   recovery loop that runs it again keeps it (item 7). Meanwhile each
   decision and outcome of the step, with the time and the actor, updates
   in place the record its deferral left, keeping its `action_id`; no other
   record is written for it, and the trace keeps every decision. A step
   deferred again leaves the record `planned`. A queued action whose step
   goes on, or is left, before reaching its approval (its condition is
   false, a gate skips or stops it, or it fails first) is superseded
   (`rejected`, "superseded").
7. **Ending early.** A recovery loop during the resumption runs again the
   steps from its target to the step that looped, as in normal flow (a
   handler among them does not run); the resumption then goes on with the
   rest of its list, a deferred handler last. Of the queued steps the loop
   runs again, one that has not gone on continues its queued action (item
   6), one that had runs as a new action, and one deferred again in the
   resumption has its queued action superseded (§5.14). The steps after the
   one that looped keep their queued actions and outputs, so nothing that
   ran ahead runs twice. A gate `end` ends the run before the queued steps
   after it and the deferred handler, whose queued actions are superseded.
   Another escalation takes precedence over the deferred handler's: its
   queued actions are superseded, the queued steps not yet re-entered stay
   deferred, and the new handler is judged against them (§5.14). When the
   resumed run fails, or needs a replan, the queued steps it did not reach
   stay deferred: listed among the run's deferrals, with their records
   `planned`, abandoned as above.

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
then on, including the queued records the resumed run updates, carry the new
actor; earlier records keep theirs.

### 5.18 Tool-Calling Hosts

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.1 Tool Bindings

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.2 Unbound Tools

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.3 Classification

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.4 Composite Tools

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.5 Scope, Order and Concurrency

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.6 Checkpoints for Calls

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.7 Approval for Calls

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.8 Refusals, Records and Failure

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.9 Text-Only Results

<!-- owner: S1; text: S1.md part 2.8 -->

#### 5.18.10 Capability Checks

<!-- owner: S1; text: S1.md part 2.8 -->

### 5.19 Host Protocol

<!-- owner: S2b; text: S2b.md part 2.11, with S4.md part 2.10's and S5.md part 2.8's edits, the start item and the reasons merged (RECONCILIATION C3, C5) -->

#### 5.19.1 Actions and Responses

<!-- owner: S2b; text: S2b.md part 2.11 -->

#### 5.19.2 Run Operations

<!-- owner: S2b; text: S2b.md part 2.11 -->

#### 5.19.3 Time

<!-- owner: S2b; text: S2b.md part 2.11 -->

#### 5.19.4 Saving and Continuing a Run

<!-- owner: S2b; text: S2b.md part 2.11 -->

#### 5.19.5 Cancelling a Run

<!-- owner: S2b; text: S2b.md part 2.11 -->

#### 5.19.6 Protocol Traffic

<!-- owner: S2b; text: S2b.md part 2.11 -->

#### 5.19.7 Error Reasons

<!-- owner: S2b; text: S2b.md part 2.11 -->

#### 5.19.8 The Run's Record

<!-- owner: S2b; text: S2b.md part 2.11 -->

### 5.20 Grounding

<!-- owner: S4; text: S4.md part 2.9 -->

### 5.21 Domain Profiles

<!-- owner: S6; text: S6.md part 2.11 -->

#### 5.21.1 Applying Profiles

<!-- owner: S6; text: S6.md part 2.11 -->

#### 5.21.2 Loading a Profile

<!-- owner: S6; text: S6.md part 2.11 -->

#### 5.21.3 Effect on Steps and Calls

<!-- owner: S6; text: S6.md part 2.11 -->

#### 5.21.4 Conformance

<!-- owner: S6; text: S6.md part 2.11 -->

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

An action record or a provenance record may carry the identity of who
acted (`actor_identity`, `agent_identity`; §5.17), and an action record's
approval the identities of the approvers that counted
(`approval.approver_identities`; §5.17).

### 6.4 Audit Records

<!-- owner: S2b; text: S2b.md part 2.14, with S5.md part 2.9's and S6.md part 2.10b's sentences -->

### 6.5 Evidence Anchors

<!-- owner: S4; text: S4.md part 2.14 -->

### 6.6 Evidence Records and Stores

<!-- owner: S4; text: S4.md part 2.15 -->

### 6.7 Secrets in Records

<!-- owner: S4; text: S4.md part 2.16 -->

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

### 8.3 Trust Classes

`authority_trust_model.yaml` gives each sender trust class of §5.17 a
default weight (`trust_classes.weights`); the classes are exactly those of
`agent_identity.trust_class`. When evidence comes from an item whose
sender's identity has a trust class, its static weight in §8.2 is the
class weight; when the evidence also has a source type of §8.1, the lower
of the two applies, so a trusted channel cannot lift an untrusted sender.
A domain profile overrides a class weight with a `trust_weights` key
`trust_class:<class>` (e.g. `trust_class:peer_agent`), kept apart from
source keys of the same name.

### 8.4 Manual Overrides

<!-- owner: S2b; text: S2b.md part 2.15 -->

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
(`tests/conformance/runtime/*.json`) script runs of the reference executor
— the actions it must request, the responses it gets, and the end and trace
it must reach — for the runtime semantics of §5.6–§5.17; they are
informative for implementations that execute workflows.

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

### 10.4 Safety-Layer Conformance

<!-- owner: S1; text: S1.md part 2.10 -->

### 10.5 Executor Conformance

<!-- owner: S2b; text: S2b.md part 2.17 -->

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

<!-- owner: S6; replaced by S6.md part 2.18 (W616 as reconciled, RECONCILIATION C12) -->

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

A workflow that targets 1.0 is validated and run under this standard, but
a 1.0 consumer does not know the features 1.1 added. Using one of them
there is W616, once per feature at its first use:
`workflow_extensions.requires` (and so every extension; the advisory
`supports_*` flags are 1.0), gate `phase`, gate `action: end`, the `in`
operator, and failure-mode `when` and `on_error`. Declaring `"1.1"` clears
it.

### 11.6 Ontology Versions

<!-- owner: S6; text: S6.md part 2.19 -->

### 11.7 Artifacts of This Version

<!-- owner: S6 (text before the table: S6.md part 2.20); table: foundation (FOUNDATION.md E2) -->

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
<!-- owner: S1; entries: S1.md part 2.13 -->

### D.2 Approval, deferral and run identity (RFC-0006, Part A)

**Clarifications of 1.1 semantics** (apply to 1.0, 1.1 and 1.2 workflows):

| Area | 1.1.0 text | 1.2.0 |
|------|------------|-------|
| Default approval request | Not stated | A step that requires approval and has no `approval` field is asked as `approval: {approver: {kind: human}}`: in session, shown its resolved inputs, no expiry; omitted members take their defaults; `expires` runs from the request (§5.14) |
| Approval digest input | "the canonical JSON of the shown values" | The array of resolved `shows` values in order (null when unresolved), `[inputs]` without `shows`, plus a `recheck` element on a re-ask; SHA-256 as lowercase hex, compared regardless of case (§5.14); normative vectors with a `kind` per vector (§10.3) |
| Numbers in shown values | "integers within ±2^53" | An integer, a number written without a fraction or an exponent, has magnitude at most 2^53 and is refused otherwise; every other number is a binary64 value, so `1e+21` is valid (§5.14) |
| `approval.mode` | Listed values only | `in_session` and `out_of_band` defined; a human approver is still never asked in an unattended run (§5.14) |

**New in 1.2.0:**
- Resumption of a deferred run (§5.14.1): the deferred steps run again, with
  the steps that ran ahead of them that they read and a checkpoint step whose
  invalidated checkpoint a re-entered mutation binds; nested deferred runs
  continue; a queued step is asked afresh (of a person when attended), the
  request names `queued_action_id`, and its `planned` record is updated in
  place. The queued actions of a run that did not end `deferred` are never
  carried out
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
<!-- owner: S2b; entries: S2b.md part 2.18 -->

### D.4 Delegation, catalogs and diagnostics (RFC-0007)
<!-- owner: S3; entries: S3.md part 2.24 -->

### D.5 Evidence, grounding and secrets (RFC-0008)
<!-- owner: S4; entries: S4.md part 2.22 -->

### D.6 Checkpoint, rollback, send and memory (RFC-0009)
<!-- owner: S5; entries: S5.md part 2.15 -->

### D.7 Profiles, trust, versioning and schema dialect (RFC-0010)
<!-- owner: S6; entries: S6.md part 2.23 -->

---

**End of Standard**
