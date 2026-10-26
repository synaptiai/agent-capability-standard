# Design contract — issue #114 (Standard v1.1.0, Rust core)

This is the implementation contract for every stage in `tasks/todo.md`.
RFC-0003 and `spec/STANDARD-v1.1.0.md` restate it normatively. If code and
this document disagree, fix one of them in the same commit — never leave
them divergent.

## 1. Architecture

```
core/                       Rust crate `acs-core` (lib: rlib + cdylib, bin: `acs`)
  src/yaml.rs               saphyr loader -> serde_json::Value, with guards
  src/ontology.rs           capability nodes, edges, layers
  src/schema.rs             $ref resolution, schema navigation
  src/types.rs              type AST, annotation grammar, compatibility
  src/diag.rs               Diagnostic, codes, severities, report
  src/model.rs              typed workflow model + unknown-field detection
  src/expr/                 expression grammar (lexer, parser, eval, check)
  src/duration.rs           duration grammar
  src/cron.rs               5-field cron
  src/validate/             structure, bindings, edges, flags, extensions
  src/exec/                 sans-IO executor
  src/python.rs             PyO3 bindings (feature `python`)
  src/bin/acs.rs            CLI
grounded_agency/_core       compiled module (maturin)
grounded_agency/workflows/  Python facade over the core (engine, executor)
tools/validate_workflows.py thin CLI over the core
```

* Build: maturin mixed project. `pyproject.toml` build-backend `maturin`,
  `[tool.maturin] manifest-path = "core/Cargo.toml"`, `module-name =
  "grounded_agency._core"`, `features = ["python"]`, `python-source = "."`.
  No pure-Python fallback.
* Dependencies (Rust): serde, serde_json (`float_roundtrip`,
  `preserve_order`), saphyr + saphyr-parser, chrono, chrono-tz, sha2, hmac,
  hex, pyo3 (optional), libc (unix: `O_NOFOLLOW`), indexmap (ordered maps of
  typed values — capabilities in file order, scopes in declaration order —
  which `serde_json::Map` cannot hold; already in the tree via
  `preserve_order`). Nothing else without a recorded reason.
* Values crossing the boundary are JSON-compatible; Python passes native
  objects, the core converts with a depth cap of 128.

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
| V108 | INVALID_EXPRESSION | expression syntax error, limit exceeded, or non-string expression |
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
| W608 | WAIT_SPANS_CHECKPOINT | a `wait` sits between a checkpoint and a later mutate/send with no new checkpoint |
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
* `workflow_extensions`: `supports_*` booleans (advisory) and `requires:
  ["name@major"]`. Known: `triggers@1`, `recovery@1`, `wait@1`, `approval@1`,
  `delegation@1`, `quorum@1`. Unknown name or major → V106.
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

| Edge | Rule | Code |
|------|------|------|
| requires | `from` present at an earlier step | V102 |
| precedes | if both present, the first `to` must not come before the first `from` | V102 |
| soft_requires | `from` present at an earlier step | W601 |
| conflicts_with | not in the same `parallel_group` (pairs de-duplicated) | F504 |

New ontology edges: `soft_requires` constrain→{execute, mutate, send},
plan→{execute, mutate}. Handler steps are outside the sequence for
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
strings (else V108).

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
string    = '"' { char | escape } '"' ;   (* \" \\ \b \f \n \r \t \uXXXX *)
```

* Limits: 4096 UTF-8 bytes, nesting depth 32. Integer literals |n| ≤ 2^53;
  numbers finite binary64. Duplicate map keys rejected.
* Values are JSON. `==`/`!=`: total, deep, structural; numbers by binary64
  value; different kinds unequal. Ordering: number/number or string/string
  (code point) else error. `!`, `&&`, `||` need booleans. `&&`/`||` follow
  CEL absorption: a determining operand (false for `&&`, true for `||`) wins
  over an error on the other side. Result must be boolean.
* Absent path or skipped producer → `null`.
* Runtime errors (R405): a gate whose `when` errors FIRES; a `condition`
  that errors is false; a failure-mode `when` that errors does not fire. All
  are recorded in the trace.
* Static checks: V108 syntax, B202/B201 refs, B206 type errors, B204
  ordering/logic on unknown/any without annotation, B203 annotation vs
  schema, W610, W611.
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
  optional `on_error` (R401 | R402 | R403 | R405 | F502), optional `when`
  (expression), `recovery` (string | object).
* Fires when the step raised a matching `on_error`, or `when` is true after
  the step. First match in order. Neither present → documentation only; with
  an object recovery → W609.
* Recovery object: `goto_step`, `inject_context` (map of ref-strings),
  `max_loops` (int ≥ 1, default 1), `on_exhausted: {goto_step}`.
* goto_step resolution: store_as; else a capability id held by exactly one
  step (W603); else V107. Loop targets must be at or before the current step.
* Escalation targets (`on_exhausted.goto_step`, and `recovery.goto_step` when
  `action: escalate`) must be steps with `handler: true`, else V107.
* `handler: true`: capability must be `invoke` (else S303); skipped in normal
  flow; unreferenced → W613. Running it ends the run with outcome
  `escalated` (R404 or the triggering code is still recorded).
* Injected context is readable as `${_recovery.<key>}` from the loop target
  onward.
* invoke cycles among catalog workflows → V105.

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
* Effective attendance unattended + approval step without
  `approval.when_unattended` → W606.

## 12. Wait (E1)

`wait: {event_type, source_kind?, correlate?: {k: ref}, liveness?: {mode:
push|probe, interval, failure_threshold (default 3)}}`

* Only on `receive`, or `synchronize` whose literal `agents` list has ≥ 2
  entries (else S303).
* Step `timeout` required (S304) and must parse; `interval ×
  failure_threshold < timeout` (S303).
* W608 as in §3.
* Runtime: AwaitEvent; the matching Event becomes the receive output; a lapse
  raises R401 (cause timeout|liveness). After a resume, pre-wait checkpoints
  no longer authorise mutations.

## 13. Approval (E3)

`approval: {approver: {kind: human|standing_mandate, role?, min_approvers
(default 1), mandate_ref?}, mode: in_session|out_of_band (default
in_session), shows?: [ref], binds_to: digest, recheck?: {source, compare:
version|digest (default digest), on_change: reask|replan|stop (default
reask)}, expires?, when_unattended: defer_to_queue|skip|fail (default fail)}`

* Allowed only where effective `requires_approval` is true (else S303).
  `mandate_ref` required iff standing_mandate. standing_mandate requires
  `approval@1` in `workflow_extensions.requires` (V106).
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
* Runtime: receive items count only if the host-authenticated `principal` is
  in `accept_from`; others are dropped and counted. `sender` = principal.

## 15. Quorum (E4)

`quorum: {verdicts: ref, reviewers: [store_as], vocabulary: [str],
pass_values: [str], blocking_values?: [str], min_pass: int, pinned_to: ref,
forbidden_inputs?: [store_as], require_fresh_context?: bool,
require_model_families?: [str]}`

* Only on `constrain` with literal `action_on_violation: block` (S303).
  reviewers must be earlier delegate steps (V107). vocabulary ≥ 2 unique;
  pass_values ⊆ vocabulary, non-empty; blocking_values ⊆ vocabulary,
  disjoint from pass_values; 1 ≤ min_pass ≤ |reviewers| (S303).
* Independence (F504): no reviewer's bindings depend, directly or
  transitively, on a forbidden store; require_fresh_context → each reviewer
  binds literal `fresh_context: true`; require_model_families → literal
  model families cover the set (non-literal → checked at runtime).
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

* `Executor::start(workflow, inputs, StartOptions{attendance, run_id, now})
  → Run`. `run.next() → Action`, `run.submit(Response, now)`,
  `run.tick(now)`, `run.snapshot()` (canonical JSON + SHA-256, optional
  HMAC key), `Run::restore`.
* Actions: InvokeCapability, CreateCheckpoint, Rollback, RequestApproval,
  RecheckSource, AwaitEvent, Completed{outcome: completed | escalated |
  deferred | replan_required}, Failed{code}.
* Steps run sequentially (parallel groups in declaration order; a step may
  not bind to a store of its own group). invoke steps run the target as a
  nested run (depth ≤ 3; cycle → R402).
* Checkpoints: each checkpoint authorises one effective-requires_checkpoint
  step; if none is valid the executor emits CreateCheckpoint. Retries:
  `retry.max` attempts, backoff none | linear (1s × n) | exponential
  (1s × 2^(n-1)). Deadlines from `timeout`; late results → R401.
* Trace: every decision (gate, condition, expression error, approval,
  retry, escalation) is an event in the snapshot.
