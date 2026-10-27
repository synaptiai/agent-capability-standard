# Design contract — issue #114 (Standard v1.1.0, Rust core)

This is the implementation contract for every stage in `tasks/todo.md`.
RFC-0003 and `spec/STANDARD-v1.1.0.md` restate it normatively. If code and
this document disagree, fix one of them in the same commit — never leave
them divergent.

## 1. Architecture

```
core/                       Rust crate `acs-core` (lib: rlib + cdylib; no binary —
                            the CLI is tools/validate_workflows.py over the module)
  src/yaml.rs               saphyr loader -> serde_json::Value, with guards
  src/ontology.rs           capability nodes, edges
  src/schema.rs             $ref resolution, schema navigation
  src/refs.rs               reference syntax ${root.path: type}
  src/types.rs              type AST, annotation grammar, compatibility
  src/diag.rs               Diagnostic, codes, severities
  src/expr/                 expression grammar (lexer, parser, eval, check)
  src/validate/             structure + bindings (mod, bindings), expressions
                            and gates (exprs), edges/flags/fields/versions
                            (semantics)
  src/python.rs             PyO3 bindings (feature `python`)
  -- planned --
  src/duration.rs, src/cron.rs, src/validate/extensions.rs   (S5)
  src/exec/                 sans-IO executor                 (S6)
grounded_agency/_core       compiled module (maturin)
grounded_agency/workflows/  Python facade over the core (engine; executor in S6)
tools/validate_workflows.py thin CLI over the core
```

* Build: maturin mixed project. `pyproject.toml` build-backend `maturin`,
  `[tool.maturin] manifest-path = "core/Cargo.toml"`, `module-name =
  "grounded_agency._core"`, `features = ["python"]`, `python-source = "."`.
  No pure-Python fallback.
* Dependencies (Rust), today: serde, serde_json (`float_roundtrip`,
  `preserve_order`), saphyr + saphyr-parser, pyo3 (optional), libc (unix:
  `O_NOFOLLOW`), indexmap; planned: chrono, chrono-tz (S5), sha2, hmac, hex
  (S6). indexmap (ordered maps of
  typed values — capabilities in file order, scopes in declaration order —
  which `serde_json::Map` cannot hold; already in the tree via
  `preserve_order`). Nothing else without a recorded reason.
* Values crossing the boundary are JSON-compatible; Python passes native
  objects, the core converts with the YAML loader's depth cap (128 nested
  containers) and a node budget per workflow (1,000,000).
* Python API: `_core.load_yaml`, `load_yaml_str`, `load_catalog` (data +
  header version), `validate_catalog`, `Validator(ontology, schema_root)`
  with `validate_file` / `validate(catalog, header=None)`, and `CODES`.

## 2. YAML loading (core)

* YAML 1.2 via saphyr. Guards ported from `safe_yaml`: size limit (1 MiB
  default, 10 MiB for the ontology/catalog), refuse symlinks (O_NOFOLLOW where
  available), plus a per-document budget of 1,000,000 weight units (one per
  node plus one per string byte) for everything anchors and aliases copy —
  only anchors some alias references are copied — and a nesting-depth cap of
  128 that also covers collections spliced in by aliases.
* Mapping keys must be strings (non-string keys → load error); keys must be
  unique; numbers must be finite and fit in 64 bits; explicit core-schema
  tags decide the type whatever the quoting; other tags are rejected.
* Parity: a test asserts that every YAML file in the repo loads to the same
  JSON in the core and in PyYAML. Where YAML 1.1 and 1.2 disagree the file is
  fixed (quoted), never special-cased.

## 3. Diagnostics

`Diagnostic { code, name, severity: error|warning, message, location{...},
suggestion? }`. Severity is fixed per code: V/B/S/F/R are errors, W are
warnings. `--strict` promotes warnings to errors. Existing codes keep their
meaning. New codes:

| Code | Name | Meaning |
|------|------|---------|
| V106 | UNSUPPORTED_EXTENSION | `workflow_extensions.requires` lists an unknown/unsupported extension, or a widening field is used without listing its extension |
| V107 | UNRESOLVED_TARGET | goto_step / on_exhausted / reviewers / delivers_to / invoke target does not resolve, or resolves to the wrong kind of step |
| V108 | INVALID_EXPRESSION | expression syntax error or limit exceeded (a non-string expression is S303) |
| V109 | UNSUPPORTED_SPEC_VERSION | `spec_version` or header names a version the validator does not support |
| B206 | EXPRESSION_TYPE_ERROR | ordering on non-orderable kinds, non-boolean logic operand or result |
| R405 | EXPRESSION_ERROR | runtime expression evaluation error |
| W601 | SOFT_REQUIREMENT_UNMET | `soft_requires` predecessor absent |
| W602 | SAFETY_FLAG_DOWNGRADE | step declares a flag less safe than the ontology (ineffective: ontology prevails) |
| W603 | DEPRECATED_FORM | accepted legacy form (goto_step by capability id, self-referencing gate without `phase`) |
| W604 | UNKNOWN_FIELD | unknown key (with closest-match hint); `x-` keys exempt |
| W605 | MISSING_SPEC_VERSION | no `spec_version` and no `# Standard version:` header |
| W606 | UNATTENDED_APPROVAL | an unattended trigger reaches an approval step with no `approval.when_unattended` |
| W607 | UNRESOLVED_WORKFLOW | invoke target not in the loaded catalog |
| W608 | WAIT_SPANS_CHECKPOINT | a `wait` sits between a checkpoint and a later step that requires one (mutate, send, raised flag), with no new checkpoint |
| W609 | UNTRIGGERED_FAILURE_MODE | structured recovery with neither `on_error` nor `when` |
| W610 | NULLABLE_OPERAND | ordering operand may be null (optional field or skippable producer) |
| W611 | CONSTANT_COMPARISON | equality between kinds that can never be equal |
| W612 | MANGLED_REFERENCE | YAML parsed `- ${a: t}` as a mapping; quote it |
| W613 | UNREACHABLE_HANDLER | `handler: true` step that no escalation targets |
| W614 | INVALID_DURATION | legacy `timeout` value outside the duration grammar |

## 4. Catalog and workflow model

* Top level: mapping of workflow name → workflow. Keys starting `x-` are
  ignored. Any other non-mapping value → S303 (no crash).
* Workflow keys: `goal`, `risk`, `steps` (required; missing → S304);
  `inputs` (optional, default `{}`), `success`, `description`,
  `spec_version`, `triggers`, `workflow_extensions`; recognised de-facto keys
  `domain`, `profile`, `risk_propagation`, `data_flow`. Anything else → W604.
* Spec version: per-workflow `spec_version` ("1.0", "1.1", optional patch) or
  file header `# Standard version: X.Y.Z`. Neither → W605. Unsupported → V109.
  The header is found among the file's leading comment lines; a BOM, blank
  lines, `%` directives and a `---` marker may precede it. Versions are
  `digits.digits[.digits]`, nothing else.
* `workflow_extensions`: `supports_*` booleans (advisory) and `requires:
  ["name@major"]`. Known: `triggers@1`, `recovery@1`, `wait@1`, `approval@1`,
  `delegation@1`, `quorum@1` (`extensions::EXTENSIONS`; all checked).
  Unknown name or major → V106; an extension is listed there only together
  with its checks, since a validator must not accept a declaration it does
  not check. A non-mapping `workflow_extensions`, a
  non-list `requires`, a non-string entry or a duplicate → S303, and then
  extension fields are not reported again as undeclared.
* Must-understand: each extension's fields may only be used when the
  extension is declared, else V106 at the field:

  | Extension | Fields |
  |-----------|--------|
  | `triggers@1` | workflow `triggers` |
  | `recovery@1` | step `handler`; recovery `on_exhausted`; failure-mode `action: escalate` |
  | `wait@1` | step `wait` |
  | `approval@1` | step `approval` |
  | `delegation@1` | bindings of `delegate.fresh_context`, `delegate.model_family`, `delegate.role`, `receive.accept_from`, `synchronize.accept_from` |
  | `quorum@1` | step `quorum` |

  `failure_modes[].on_error` and `.when` are base 1.1 (not an extension): a
  consumer that ignores them only loses an optional trigger.
* Step keys: `capability`, `purpose`, `store_as` (required: missing
  capability → V103, missing purpose/store_as → S304); optional §5.2 keys
  plus `workflow_id`, `domain`, `handler`, `wait`, `approval`, `quorum`, and
  de-facto keys found in the repo inventory. Anything else → W604.
* Safety flags (`mutation`, `requires_checkpoint`, `requires_approval`,
  `risk`): omitted → inherit the ontology. Effective value = ontology OR step
  (risk = max). A step value less safe than the ontology → W602, except
  `mutation: false` on a node with `mutation_overridable: true` (audit), which
  is allowed only on low-risk nodes without checkpoint/approval requirements
  (enforced by `validate_ontology.py`).

## 5. Edges

A step *runs before* another when it comes earlier in the list and is not
in the same `parallel_group` (steps of one group run concurrently).

| Edge | Rule | Code |
|------|------|------|
| requires | a `from` step runs before each `to` step | V102 per `to` step |
| precedes | if both are present, a `from` step runs before every `to` step | V102 once per edge, at the first offending `to` |
| soft_requires | one of the target's incoming sources runs before it (any-of) | W601 per step |
| conflicts_with | not in the same `parallel_group` | F504 once per (group, pair) |

All edge checks are linear in the number of steps.

New ontology edges: `soft_requires` constrain→{execute, mutate, send}. (No
plan→ soft edges: with any-of per target they would let a plan stand in for
the policy check; `precedes` plan→{execute, mutate} already orders a plan.)
A pre-flight check before a mutation is `constrain`, not `verify`:
`{execute, mutate, send} precedes verify` makes an early verify V102. Handler steps are outside the sequence for
precedes/conflicts; their `requires` are checked against steps up to the
earliest step that targets them.

## 6. References and bindings

* Reference: `${root(.ident | [n] | [a:b])*( : type)?}`; whitespace around
  `:` allowed. Identifiers: `[A-Za-z_][A-Za-z0-9_-]*` (a `store_as` that is
  not one → S303). Root = prior `store_as`, else workflow input, else
  `_recovery`.
* Scopes: input_bindings, condition, `phase: before` gates, wait.correlate,
  approval.shows/recheck.source, quorum refs → prior steps + inputs.
  `phase: after` gates, failure_modes[].when, recovery.inject_context → also
  the step's own store. Handler steps → stores produced at or before the
  earliest step that targets them.
* Paths: a field must name a property; an undeclared key is allowed only
  where `additionalProperties` permits it (or the object declares no
  properties). No implicit projection: a field on an array is B201 and null
  at runtime — select an element with `[n]`. Index segments have no leading
  zeros.
* Checks: unknown root B202; bad path B201; annotation token invalid B205;
  annotation vs schema B203; ambiguous untyped (input_bindings, condition,
  gates) B204; consumer input type mismatch B203 + coercion suggestion.
  Extension-block refs: B202/B201 only.
* Type AST: unknown, any, null, string, number, integer, boolean, object,
  array<T>, map<K,V>, nullable<T>, union. `integer` ⊂ `number`.
* `$ref` resolved relative to the schema root (repo root). `mapping_ref`
  missing → S301; `output_conforms_to` file missing → S301, pointer
  unresolved → S302; `inputs.*.ref` unresolved → S302.

## 7. Expressions (grammar B — ACS, CEL-compatible)

Sites: `condition`, `gates[].when`, `failure_modes[].when`. Must be YAML
strings (else S303).

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

* Limits: 4096 UTF-8 bytes, nesting depth 32. Integer literals |n| ≤ 2^53;
  numbers finite binary64. Duplicate map keys rejected.
* Values are JSON. `==`/`!=`: total, deep, structural; numbers by binary64
  value; different kinds unequal. Ordering: number/number, string/string
  (code point) or boolean/boolean (false < true, as CEL) else error. `!`, `&&`, `||` need booleans. `&&`/`||` follow
  CEL absorption: a determining operand (false for `&&`, true for `||`) wins
  over an error on the other side. Result must be boolean.
* Absent path or skipped producer → `null`. A producer is skippable when it
  has a `condition` that skips (`skip_if_false` absent or true) or a
  before-gate with `action: skip`; its own after-gates still see its output.
* Null narrowing: after `${x} != null` in an `&&` chain (or `${x} == null` in
  an `||` chain) later operands treat that reference as present, and with it
  every reference it is a prefix of up to that point: `${x}` present makes
  `${x.f}` non-null when `f` is required (optional segments below stay
  nullable). Below an untyped node nothing is required, so every further
  segment may be null unless that exact prefix was narrowed.
* After an unknown root (B202) or bad path (B201) no further diagnostic is
  reported for that operand.
* Runtime errors (R405): a gate whose `when` errors FIRES; a `condition`
  that errors is false; a failure-mode `when` that errors does not fire. All
  are recorded in the trace.
* Static checks: V108 syntax (B205 when only an annotation is malformed —
  the parser validates annotations), B202/B201 refs, B206 type errors, B204
  ordering/logic on unknown/any without annotation, B203 annotation vs
  schema (the same `types::compatible` rule as binding annotations), W610,
  W611.
* Fixtures: `tests/conformance/expressions/{eval,check}.json` (language
  neutral). `tools/cel_differential` (cel-go, unchecked evaluation, refs
  hoisted to dyn variables) asserts in CI that every ACS-valid case is valid
  CEL and that results agree wherever CEL returns a value.
* Every valid expression must be valid CEL (references hoisted to opaque
  variables) with the same result wherever CEL returns a value.

## 8. Gates and conditions

* `gates[]`: `when`, `action` (stop|rollback|skip|warn; else S303),
  `message`, `phase` (before|after, default before).
* A gate referencing its own step's store with no `phase` → treated as
  `after` + W603. Explicit `phase: before` with a self-reference → B202.
  `phase: after` with `action: skip` → S303.
* Order: condition → before-gates (declaration order) → step → after-gates.
* `condition` false: skipped if `skip_if_false` is true or absent; if
  `skip_if_false: false` the run fails with R403.
* Gate actions at runtime: stop → R403; skip → step skipped; rollback →
  Rollback to the latest checkpoint then R403; warn → trace warning.

## 9. Failure modes and recovery (E5)

* `failure_modes[]`: `condition` (prose), `action` (stop | rollback |
  request_more_context | pause_and_checkpoint | escalate; else S303),
  optional `on_error` (one code or a non-empty list of R401 | R402 | R403 |
  F501 | F502 | F504 — the codes a step can fail with; R405 never fails a
  step; else S303), optional `when` (expression), `recovery` (string |
  object).
* Fires when the step raised a matching `on_error`, or `when` is true after
  the step. First match in order. Neither present → documentation only; with
  an object recovery → W609.
* `recovery` is a string or an object, else S303. Recovery object:
  `goto_step`, `inject_context` (map of ref-strings, else S303),
  `max_loops` (int 1–1000, default 1, a float with no fraction accepted
  as JSON Schema does; else S303 — a loop needs no host call, so it is
  bounded), `on_exhausted: {goto_step}` (S304 without
  goto_step; S303 if not a mapping). `max_loops` / `on_exhausted` without a
  `goto_step` → S304. `on_error` is checked before the recovery@1 gate on
  `action: escalate`, since it is base 1.1.
* goto_step resolution: store_as; else a capability id held by exactly one
  non-handler step (W603); else V107. Loop targets must be non-handler steps
  at or before the current step (V107).
* Escalation targets (`on_exhausted.goto_step`, and `recovery.goto_step` when
  `action: escalate`, which then requires it: S304) must be steps with
  `handler: true`, else V107. An escalation takes no `max_loops`,
  `on_exhausted` or `inject_context` (S303 each).
* `handler: true`: boolean (S303); capability must be `invoke` (else
  S303). Only a valid flag (invoke, recovery@1 declared) makes a handler;
  otherwise the step stays in the normal flow, so nothing cascades.
  Skipped in normal flow; unreferenced → W613. Running it ends the run with
  outcome `escalated` (R404 or the triggering code is still recorded), so a
  handler's own failure modes cannot loop or escalate (V107) — which also
  means only normal steps target handlers.
* Checking order (validate/recovery.rs): a pre-pass resolves targets; each
  targeted handler is checked right after its earliest targeting step, in
  that scope, with the targeting step's store and its earlier
  parallel-group mates' stores maybe-absent. The scope is switched in place
  and restored (`HandlerView`), never copied. Handlers are not placed in
  the edge sequence and their store is never added to the shared scope;
  their `requires` edges and effective `requires_checkpoint` (F501) are
  checked against what runs before the earliest targeter. V104 is judged
  in list order.
* Injected context is readable as `${_recovery.<key>}` from the loop target
  onward: the scope root `_recovery` is an object of the injected keys
  (type any), maybe-absent. Injections are sorted by target and brought
  into scope by a cursor as the main loop reaches each target, so the cost
  is linear in the keys. `_recovery` as a store_as or input → S303.
* invoke targets: `workflow_id`, else literal `input_bindings.workflow`
  (diagnostics name whichever field it was). Not in the catalog → W607;
  cycles (incl. self) → V105 at each invoke step whose caller and target
  share a strongly connected component (iterative Tarjan, linear); target
  with triggers but none of kind invoke → V107 (validate/invoke.rs,
  catalog-level).

## 10. Durations

`^\d+(ms|s|m|h|d)$` or ISO-8601 dayTime `P[nD][T[nH][nM][n[.n]S]]` (at least
one component; no Y, calendar M or W). New fields: invalid → S303. Legacy
step `timeout`: invalid → W614.

## 11. Triggers (E6)

`triggers: [{kind, schedule?, event?, attendance?}]`

* kind: schedule | event | manual | invoke.
* schedule (required iff kind=schedule): exactly one of `cron` (5 fields:
  minute 0-59, hour 0-23, dom 1-31, month 1-12|JAN-DEC, dow 0-7|SUN-SAT;
  `* , - /`; Vixie OR when both dom and dow restricted; no `CRON_TZ=`/`TZ=`)
  or `every` (duration); `timezone` IANA (chrono-tz, default "UTC");
  `overlap`: skip | buffer_one | allow_all (default skip).
* event (required iff kind=event): `event_type` (string), `source_kind`
  (event_schema source.kind enum, which gains `agent`), `delivers_to` (an
  input whose `ref` ends `event_schema.yaml#/event`; else V107).
* attendance: attended | unattended. Default: manual → attended, invoke →
  inherited, schedule/event → unattended.
* An invoke step whose target declares triggers without kind invoke → V107.
* A trigger whose attendance is unattended (explicit, or the
  schedule/event default; `invoke` inherits and is not counted statically)
  + a step whose effective `requires_approval` is true without
  `approval.when_unattended` → W606 (validate/approval.rs; also without
  approval@1 declared, since the step will still fail with F502).

## 12. Wait (E1)

`wait: {event_type, source_kind?, correlate?: {k: ref}, liveness?: {mode:
push|probe, interval, failure_threshold (default 3)}}`

* Only on `receive`, or `synchronize` whose literal `agents` list has ≥ 2
  entries (else S303).
* `event_type` required (S304); `source_kind` checked against the event
  schema's `source.kind` enum (S301 if it cannot be loaded); `correlate`
  is a mapping whose references are checked for existence; unknown fields
  W604.
* Step `timeout` required (S304) and must parse (S303 — the W614 leniency
  for legacy timeouts is skipped for a declared wait); liveness `mode` and
  `interval` required (S304), `interval` > 0, `failure_threshold` ≥ 1;
  `interval × failure_threshold < timeout` (S303, overflow-safe).
* `correlate` values, `approval.shows` items and `approval.recheck.source`
  must be `${...}` references (S303), then are existence-checked. A wait
  that is not a mapping still gets its timeout checked, and does not count
  as a wait for W608.
* W608 (validate/wait.rs `spans_checkpoint`): for each placed step with
  effective `requires_checkpoint`, the latest checkpoint and the latest
  wait that run before it (§3 "runs before") are found in O(1) — each kind
  keeps its latest occurrence and the latest one not concurrent with it.
  W608 fires when that wait comes after that checkpoint in the list, or
  when a wait was recorded in the checkpoint's parallel group (it may
  outlast the checkpoint, whichever is listed first), or when the step
  waits itself. Handlers are judged at their earliest targeter's position,
  counting the targeter's own wait.
* Runtime: AwaitEvent; the matching Event is delivered in the step's
  output (`data`); a lapse
  raises R401 (cause timeout|liveness). After a resume, pre-wait checkpoints
  no longer authorise mutations.

## 13. Approval (E3)

`approval: {approver: {kind: human|standing_mandate, role?, min_approvers
(default 1), mandate_ref?}, mode: in_session|out_of_band (default
in_session), shows?: [ref], binds_to: digest, recheck?: {source, compare:
version|digest (default digest), on_change: reask|replan|stop (default
reask)}, expires?, when_unattended: defer_to_queue|skip|fail (default fail)}`

* Allowed only where effective `requires_approval` is true (else S303).
  `approver` and `approver.kind` required (S304); `mandate_ref` required iff
  standing_mandate (S304 / S303); `min_approvers` ≥ 1; `shows` a list of
  references and `recheck.source` a reference (existence-checked);
  `expires` a duration > 0; enums S303; unknown fields W604
  (validate/approval.rs).
* Runtime: RequestApproval carries the shown values and their SHA-256 digest
  (canonical JSON). A decision is valid only if the digest matches, distinct
  approver ids ≥ min_approvers, not expired, and unused (single use).
  Unattended runs follow `when_unattended`: fail → F502, skip → step skipped,
  defer_to_queue → run ends `deferred` with a planned ActionRecord.
* ActionRecord status gains `rejected`, `expired`; optional `approval`
  sub-object.

## 14. Delegation (E2)

* Ontology: delegate inputs `fresh_context`, `model_family`, `role`; output
  `effective {fresh_context, model_family, role}`. receive and synchronize
  input `accept_from: array<string>`; receive data items gain `sender`.
* Static (validate/delegation.rs): binding any of these inputs without
  `delegation@1` → V106 per input; otherwise they are typed by the
  ontology like any input.
* Runtime: receive items count only if the host-authenticated `principal` is
  in `accept_from`; others are dropped and counted. `sender` = principal.

## 15. Quorum (E4)

`quorum: {verdicts: ref, reviewers: [store_as], vocabulary: [str],
pass_values: [str], blocking_values?: [str], min_pass: int, pinned_to: ref,
forbidden_inputs?: [store_as], require_fresh_context?: bool,
require_model_families?: [str]}`

* Only on `constrain` with literal `action_on_violation: block` (S303).
  Required keys (S304): verdicts, reviewers, vocabulary, pass_values,
  min_pass, pinned_to; `verdicts`/`pinned_to` must be `${...}` references
  (S303) and are existence-checked. reviewers must be delegate steps listed
  earlier and not in the quorum step's parallel group (V107), to distinct
  literal agents (F504: a verdict counts once per agent). vocabulary ≥ 2
  unique; pass_values ⊆ vocabulary, non-empty; blocking_values ⊆
  vocabulary, disjoint from pass_values; 1 ≤ min_pass ≤ |reviewers| (S303).
  Unknown `forbidden_inputs` names → V107.
* Independence (F504): no reviewer's bindings depend, directly or
  transitively, on a forbidden store or input; require_fresh_context → each
  reviewer binds literal `fresh_context: true`; require_model_families →
  literal model families cover the set (any non-literal → checked at
  runtime). Dependencies (validate/quorum.rs `Independence`): a reverse
  "who reads what" graph is built once per workflow from every step's
  bindings (duplicate names included), with each recovery
  `inject_context` value read through the root `_recovery`; each distinct
  forbidden set is propagated breadth-first over it once (cached across
  quorum steps), recording per store the next hop and the forbidden store
  reached. Linear per distinct forbidden set, safe on cycles, and each
  reviewer's diagnostic is O(1). Reviewers listed twice are judged once.
* Runtime (executor evaluates; no host call for this step): a verdict counts
  if its reviewer_id equals a reviewer delegate's `agent`, its `pinned`
  equals the resolved pinned_to, its value is in the vocabulary, it is the
  first from that reviewer, and (if required) the delegate's attestation
  satisfies fresh_context. Any counted blocking value vetoes. Compliant iff no
  veto, passes ≥ min_pass, model-family coverage holds. Output: compliant,
  violations, tally {passes, blocks, abstains, voters}. Non-compliant → F504.
* `schemas/review_verdict_schema.yaml#/review_verdict`: reviewer_id, value,
  pinned (required), evidence_anchors, notes.

## 16. Executor (sans-IO)

The reference executor (`core/src/exec/`) is a deterministic state machine
with no I/O: the host asks it what to do next, does it, and reports back.
The same inputs and responses always give the same actions, trace and
snapshot. Exposed to Python as `_core.Run`; `grounded_agency/workflows/
runner.py` drives it with a host object.

### 16.1 Interface

* `Run::start(ctx, catalog, workflow, inputs, StartOptions{attendance,
  run_id, now_ms}) → Result<Run, StartError>`. The catalog is validated
  first; any error (not warning) refuses the start with the diagnostics.
  Required inputs must be given; unknown inputs are refused.
* Values a run takes in (inputs, outputs, events, recheck values) must be
  I-JSON (RFC 7493): integers within ±2^53 and at most 100 levels deep;
  anything else is refused (`StartError::Inputs`, `SubmitError::Malformed`),
  so snapshots and digests represent every value exactly. Times are capped
  at 2^53 ms for the same reason.
* `run.next() → Action`: the pending action. Idempotent: it returns the
  same action (same `id`) until a response to it is submitted.
* `run.submit(id, Response, now_ms) → Result<(), SubmitError>`: the response
  must answer the pending action (`id`) with a matching kind; otherwise it
  is refused and the run is unchanged.
* `run.tick(now_ms)`: tells the run the time. A pending action whose
  deadline has passed times out (R401); a `Sleep` whose `until` has passed
  ends.
* `run.snapshot(key) → Snapshot { state (canonical JSON), sha256, hmac? }`;
  `Run::restore(ctx, catalog, snapshot, key)` verifies the digest, the HMAC
  when a key is given (a signed snapshot without its key is refused), that
  the catalog and the ontology contracts its steps use are the ones the
  snapshot was taken against, and that the state is one the executor could
  have produced (frames, step indices, pending or terminal action, record
  indices), before resuming.
* Time is only what the host passes in (`now_ms`, Unix epoch ms).

### 16.2 Actions and responses

| Action | Host does | Response |
|--------|-----------|----------|
| `InvokeCapability{step, capability, inputs, domain, deadline, attempt}` | run the capability | `Output{value}` or `Error{code: R401/R402, message}` |
| `CreateCheckpoint{step}` | take a checkpoint before a step that needs one (or for `pause_and_checkpoint`) | `Checkpoint{checkpoint_id}`, or `Error` (the step fails with F501) |
| `Rollback{checkpoint_id, step}` | restore it | `RolledBack`, or `Error` (the run fails with F503) |
| `RequestApproval{step, approver, mode, shown, digest, expires_at}` | ask | `Decision{decision_id, decision: approved/rejected, approvers, digest}`; no decision by `expires_at` → F502 |
| `RecheckSource{step, source, compare}` | re-read the source now | `Current{value}`, or `Error` (F502) |
| `AwaitEvent{step, event_type, source_kind, correlate, accept_from, liveness, deadline}` | wait | `Event{event, principal}`, `LivenessLost` (R401) or `Error` (R402) |
| `Sleep{until}` | call `tick` at or after `until` | — |
| `Completed{outcome, cause, outputs, action_records}` | finished: `completed`, `escalated` (with the `cause` code), `deferred`, `replan_required` | — |
| `Failed{code, step, message, action_records}` | finished with an error | — |

Every action carries `frame` (the stack of workflow names: nested `invoke`
runs surface their actions through the parent) and `id`.

### 16.3 Step algorithm

For each step of the normal flow in list order (handlers are skipped;
parallel groups run in declaration order):

1. `condition`: false or an evaluation error (R405, traced) → skip, unless
   `skip_if_false: false`, which raises R403.
2. Before-gates in order; an evaluation error fires the gate. `stop` →
   R403; `skip` → skip; `rollback` → `Rollback` to the latest checkpoint,
   then R403; `warn` → trace.
3. Inputs: each binding is resolved (a whole-string reference keeps the
   value's type; references inside a longer string are interpolated, a
   string as-is and other values as compact JSON). Absent or skipped →
   `null`.
4. Approval: if the effective `requires_approval` is true. Unattended runs
   follow `when_unattended` (`fail` → F502 with a `rejected` record, `skip`
   → skip the step, also recorded `rejected` with the reason,
   `defer_to_queue` → `Completed{deferred}` with a `planned` action
   record). Otherwise `RequestApproval` with `shown` = the resolved `shows`
   (default: `[inputs]`) and `digest` = SHA-256 (hex) of the canonical JSON
   (RFC 8785) of `shown`. A decision counts only if `decision` is
   `approved`, its `digest` matches, it has at least `min_approvers`
   distinct approvers (default 1), `now ≤ expires_at` (when `expires`), and
   its `decision_id` was not used before in the run (digests compare
   case-insensitively). Rejected or otherwise invalid → F502 with a
   `rejected` record and its `reason`; expired → F502 with an `expired`
   record. Then `recheck`, if any: `RecheckSource`; the current value is
   compared with the value at approval time (`digest`: canonical digest;
   `version`: the values' `version` fields); on change `reask` asks again,
   showing `{recheck: {previous, current}}` after the shown values (so the
   digest changes too), `replan` → `Completed{replan_required}`, `stop` →
   F502.
5. Checkpoint: if the effective `requires_checkpoint` is true, the latest
   *valid* checkpoint is consumed (one checkpoint authorises one step).
   This comes after approval, so a skipped, deferred or refused step uses
   none. A checkpoint is valid once taken and stops being valid when
   consumed or when a wait completes after it. None valid →
   `CreateCheckpoint` (an `Error` response fails the step with F501).
6. Execute:
   * a step with `wait` → `AwaitEvent` (deadline = now + `timeout`). An
     event counts if its `event_type` matches, its `source.kind` matches
     `source_kind` (when given), every `correlate` key equals
     (`event.canonical[key]`, else `event[key]`), and its `principal` is in
     `accept_from` (when bound); otherwise it is dropped and the wait goes
     on (drops are counted per reason, traced once per reason, and reported
     with `event_received`). `LivenessLost` or the deadline → R401. The
     output is built from the event: receive → `{data: [event], source:
     event.source.kind, timestamp: event.timestamp, evidence_anchors:
     event.anchors}` (the item gains `sender`: the principal); synchronize
     → `{synchronized: true, agreed_state:
     event.canonical, participants: agents, evidence_anchors:
     event.anchors}`. A completed wait invalidates earlier checkpoints.
   * `invoke` → the target (`workflow_id`, else the bound `workflow`) runs
     as a nested run (at most 4 runs deep, else R402) with the bound
     `input`, checked against its declared inputs (else R402). Its
     `Completed{completed}` outputs become the step's output `{result,
     steps_executed (in step order), evidence_anchors}`; a child that fails
     (including a failed rollback inside it) or escalates is
     the step's error (R402, retried as usual); a child that ends
     `deferred` or `replan_required` ends the whole run that way.
   * `constrain` with `quorum` → evaluated by the executor (no host call),
     §16.4.
   * anything else → `InvokeCapability`, deadline = now + `timeout`. The
     output must be an object with the capability's required output
     fields, else R402. A late response (`now > deadline`) is R401.
   * a `checkpoint` step's output records a valid checkpoint
     (`checkpoint_id`, else one derived from the run id and step).
7. Errors R401/R402 are retried up to `retry.max` more times; between
   attempts `Sleep` for the backoff (`none` 0; `linear` 1 s × n;
   `exponential` 1 s × 2^(n−1); unknown → none).
8. The output is stored under `store_as`, with the inputs the step ran
   with (a quorum judges its reviewers by these); then after-gates (as 2,
   without `skip`). A gate is an after-gate when it says `phase: after`, or
   says no phase and reads the step's own output (§5.6).
9. Failure modes, in order, the first that fires: `on_error` matches the
   step's error code, or `when` is true (an evaluation error does not
   fire). If the step erred and none fires, the run fails with that code.
   The action runs first: `rollback` → `Rollback`; `pause_and_checkpoint` →
   `CreateCheckpoint`; `stop`, `request_more_context`, `escalate` → nothing.
   Then the recovery:
   * a loop (`goto_step`, not escalate): if this failure mode has looped
     fewer than `max_loops` (default 1, at most 1000) times, evaluate `inject_context`
     into `_recovery`, clear the outputs of the target and every later
     step, and continue at the target; exhausted → `on_exhausted` handler,
     else `Failed{R404}`;
   * `escalate` → the handler;
   * none (or prose) → `Failed{code}`: the step's error, else R402.
   A handler runs (as an `invoke`) and the run ends `Completed{escalated}`
   with the cause recorded; a handler that fails ends `Failed`.
10. After the last step: `Completed{completed, outputs}` where outputs are
    all stored step outputs.

### 16.4 Quorums at runtime

`verdicts` resolves to a list. Only reviewer delegate steps that ran count.
A verdict counts if it is an object whose `reviewer_id` equals the `agent`
input one of them ran with, whose `pinned` equals the resolved `pinned_to`, whose
`value` is in the vocabulary, that is the first from that reviewer, and —
with `require_fresh_context` — whose delegate output's
`effective.fresh_context` is true. With `require_model_families`, the
families of counted reviewers (`effective.model_family`, else the bound
`model_family`) must cover the set. Compliant iff no counted verdict is a
blocking value, passes ≥ `min_pass` and coverage holds. Output:
`{compliant, violations, tally: {passes, blocks, abstains, voters},
evidence_anchors}`; not compliant → F504.

### 16.5 Trace, records, snapshots

* Trace events: `{seq, at, kind, frame, step, detail}`. Kinds:
  `run_started`, `run_finished`, `run_failed`, `step_started`,
  `step_skipped`, `step_completed`, `step_failed`, `expression_error`
  (site and message; R405), `gate_fired`, `rolled_back`,
  `checkpoint_created`, `checkpoint_consumed`, `checkpoints_invalidated`,
  `approval_unattended`, `approval_requested`, `approval_decided`,
  `approval_expired`, `recheck`, `event_dropped`, `event_received`,
  `retry`, `quorum`, `failure_mode_fired`, `loop`, `recovery_exhausted`,
  `escalated`, `invoke_started`, `invoke_returned`.
* Action records (world_state 1.1.0 `ActionRecord`) for every step that
  required approval: `planned` (deferred), `approved` → `executed` (or
  `failed` if the step then failed), `rejected` (refused, invalid, or
  unattended `fail`/`skip`), `expired` (also an approval that a recheck
  found stale), with the `approval` sub-record and a `reason` when the
  action did not go ahead.
* The snapshot is the whole run state as canonical JSON (RFC 8785) with
  its SHA-256; with a key, an HMAC-SHA-256 too. Restore refuses a snapshot
  whose digest or HMAC does not match, that was taken against another
  catalog or other ontology contracts, or whose state is not well formed
  (§16.1). Numbers are printed as ECMAScript does (`ryu-js`).

### 16.6 Runtime conformance fixtures

`tests/conformance/runtime/*.json`: catalog (inline), workflow, inputs,
attendance, a script of `{expect: <action kind and fields>, respond:
<response>}` entries (or `tick`), and the expected end (`Completed`
outcome or `Failed` code) and trace kinds. Run by `cargo test` and by
pytest through the Python driver.
