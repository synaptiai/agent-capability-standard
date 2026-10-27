# Validator and engine disagreements in Standard 1.0.0

At commit `9e2f65b` (Standard 1.0.0) the workflow validator
(`tools/validate_workflows.py`) and the reference engine
(`grounded_agency/workflows/engine.py`) were two separate implementations of
rules the 1.0 text left open, and judged the same catalogs differently. This
document records minimal reproductions of every disagreement found, what
v1.0.0 says about each, and how each case behaves now that both tools call
one Rust core. It backs question 3 of
[#114](https://github.com/synaptiai/agent-capability-standard/issues/114) and
the clarifications listed in
[STANDARD-v1.1.0 Appendix C](../../../spec/STANDARD-v1.1.0.md#appendix-c-changes-from-100);
[RFC-0003](../../../spec/RFC-0003-orchestration-extensions.md) gives the
resolution.

The reproduction catalogs have no `# Standard version:` header, so the
current validator also prints W605 for each; it has no effect on the
verdicts.

## Method

The validator is run as `python tools/validate_workflows.py --catalog <file>` at
`9e2f65b`. The engine is run from a `9e2f65b` checkout with this script (`python
engine_check.py <checkout> <catalog>`), which calls
`WorkflowEngine.validate_all_structured()` (capabilities, bindings and edge
constraints):

```python
"""Run the 9e2f65b WorkflowEngine over a catalog and print every validate_* result."""
import json, sys
from pathlib import Path
root = Path(sys.argv[1]); cat = sys.argv[2]
sys.path.insert(0, str(root))
from grounded_agency.workflows.engine import WorkflowEngine
eng = WorkflowEngine(root / "schemas" / "capability_ontology.yaml")
n = eng.load_catalog(cat)
print(f"loaded {n} workflow(s)")
res = eng.validate_all_structured()
if not res:
    print("ENGINE PASS (validate_all_structured: no errors)")
rc = 0
for wf, errs in res.items():
    rc = 1
    for e in errs:
        print(f"ENGINE FAIL [{wf}] {e.code.value} {e.code.name}: {e.message}")
sys.exit(rc)
```

### Summary

| # | Case | Validator @9e2f65b | Engine @9e2f65b | Right per v1.0.0 | After the fix |
|---|------|--------------------|-----------------|------------------|----------------|
| D1 | `: object` on an `any` field | pass | B203 | validator (§5.4.3) | pass |
| D1b | no annotation on an `any` field | B204 | pass | validator (§5.4.3) | B204 |
| D1c | `: any` / `: str` annotations | pass | B203 ×2 | split (§5.3 has no grammar) | B205 on `str` only |
| D2 | `precedes`, predecessor absent | pass | V102 | validator (§4.3; not explicit) | pass |
| D2b | `precedes`, several sources | pass | V102 ×2 | validator | pass |
| D2c | `precedes`, order reversed | pass | V102 | engine (§4.3) | V102 |
| D3 | audit `mutation: false` | pass | F504 (+V102) | undecided by v1.0.0 | pass (`mutation_overridable`) |
| D3b | safety flags omitted | pass | F504 | validator (§5.2 "MAY") | pass |
| D4 | `requires_checkpoint: false` | pass | F504 | neither clearly (§4.4 met) | pass + W602 |
| D5 | `conflicts_with` in sequence | pass | F504 ×2 | engine (§4.3, EDGE_TYPES §5) | pass (v1.1 concurrency rule) |
| D6 | step binds its own store_as | pass | B201 | engine verdict (§5.5.1), but should be B202 (§9.3) | B202 |
| D7 | non-existent field path | B201 | pass | validator (§5.5.2) | B201 |
| D8 | unannotated `integer` field | B204 | pass | engine (§5.4.3) | pass |
| D9 | `: integer` on an object | pass | B203 | engine (§5.4.2) | B203 |
| D10 | `array<string>` vs `array<object>` | B203 | pass | validator (§5.4.2) | B203 |
| D11 | `map<K,V>` annotation, unknown store | B202 | pass | validator (§5.5.1) | B202 |
| D12 | `${a.b:object}` (no space) | B201 | pass | unspecified (§5.3) | pass |
| D13 | refs in condition/gates | B202 ×2 | pass | validator (§10.2 L3) | B202 ×2 |
| D14 | duplicate store_as | V104 | pass | validator (§9.2, §10.2 L1) | V104 |
| D15 | consumer input type | B203 | pass | validator (§5.5.3) | B203 |
| D16 | annotation on a workflow input | B203 | pass | validator (§5.4.2) | B203 |
| D16b | path into an untyped input | B204 | pass | validator (§5.4.3) | B204 |
| D17 | step without `capability` | V103 | crash (KeyError) | validator (§9.2) | V103 |
| D18 | non-mapping top-level entry | crash (AttributeError) | pass (skipped) | unspecified; crash is wrong | S303 |
| D19 | `steps: null` | pass | crash (TypeError) | neither (§5.1) | S303 |
| D20 | missing mapping_ref / output_conforms_to | S301 ×2 | pass | validator (§9.4) | S301 ×2 |
| D21 | unknown capability, referenced later | V101 + B202 | V101 | both defensible | V101 + B202 |
| D22 | catalog > 1 MiB | load error | pass | unspecified | pass |


### The shipped catalog

Run on its own `schemas/workflow_catalog.yaml`, the validator at 9e2f65b prints
`VALIDATION PASS` (exit 0). The engine reports **56 errors** across all 12 workflows:
36 V102 (all `precedes`: D2/D2b/D2c), 15 F504 (11 audit `mutation: false` (D3), 2
`send` downgrades in `clarify_intent` (`mutation` (D3) and `requires_checkpoint` (D4)),
and 1 `rollback`/`mutate` conflict reported twice (D5)), and 5 B203, all of them `any`
annotations (D1). Run on that same 9e2f65b catalog, the fixed validator fails only
`model_deployment`: `V102 'verify' must come after 'execute' (precedes), but 'execute'
first appears at step 3`. That is the D2c case, which the 9e2f65b validator accepted.
It also prints W602/W612/W601/W603/W609/W610/W611 warnings. (The catalog on the
branch has since been fixed and passes with no warnings.)

### The three cases from #114

### D1. Typed annotation on a field the ontology types as `any`

**Disagreement:** the validator passes and the engine fails with B203.

**Cause:** the ontology writes `type: any` on fields such as `retrieve.data`,
`generate.content`, `execute.result` and `mutate.previous_state`. The validator's
`schema_type` maps the unknown keyword to `unknown`, and `is_type_compatible`
accepts any annotation against `unknown`. The engine compares the strings: in
`_types_compatible("any", "object")`, `"object"` is not in `{"any"}`, so it reports a mismatch.

**Which is right (v1.0.0):** the validator. §5.4 rule 3 says an annotation
is REQUIRED when type metadata is missing. `any` is not a JSON Schema type, so the
annotation is exactly the fix §5.4 prescribes. Rule 2 ("MUST match the schema node type")
cannot fail against a node that sets no constraint. Because the engine rejects the
annotation and the validator (D1b) rejects its absence, no binding to an `any`
field satisfies both tools.

**On the shipped catalog:** all 5 of the engine's B203 errors on the 9e2f65b
`workflow_catalog.yaml` are this case: `retrieve_out.data` and `generate_out.content` (twice) in
`rag_pipeline`, `generate_out.content` in `security_assessment`, and `execute_out.result` in `model_deployment`.

Catalog `r01_any_annotated.yaml`:

```yaml
wf:
  goal: Annotate a field the ontology types as "any"
  risk: low
  inputs: {}
  steps:
  - capability: retrieve
    purpose: Fetch data
    store_as: r
  - capability: explain
    purpose: Explain it
    store_as: e
    input_bindings:
      conclusion: "${r.data: object}"
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r01_any_annotated.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r01_any_annotated.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] B203 TYPE_MISMATCH: Type mismatch: '${r.data}' declared as 'object' but source outputs 'any'
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r01_any_annotated.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

### D2. `precedes` when the predecessor is absent

**Disagreement:** the validator passes and the engine fails with V102.

**Cause:** the validator has no `precedes` check (`requires_map` holds only
`type: requires`). The engine's `validate_edge_constraints` reads every incoming
`precedes` edge as a hard prerequisite.

**Which is right (v1.0.0):** the validator's verdict. §4.3 and EDGE_TYPES.md §4 define
`precedes` as temporal ordering: "MUST complete before the target capability begins …
Validator MUST reject workflows that violate temporal ordering". A workflow without
`observe` has no ordering to violate. §4.3 lists `requires` as a separate edge for
"Hard prerequisite", so reading `precedes` as a prerequisite merges two edge types.
The text never states the absent case outright. STANDARD v1.1.0 §4.3 now says it:
ordering only when both are present.

**On the shipped catalog:** most of the engine's 36 V102 errors on the 9e2f65b
`workflow_catalog.yaml` are this case.

Catalog `r03_precedes_absent.yaml`:

```yaml
wf:
  goal: detect with no observe anywhere in the workflow
  risk: low
  inputs: {}
  steps:
  - capability: detect
    purpose: Detect a pattern
    store_as: d
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r03_precedes_absent.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r03_precedes_absent.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] V102 MISSING_PREREQUISITE: Step 0 (detect): must be preceded by 'observe' but it hasn't been executed in prior steps
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r03_precedes_absent.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

### D2c. `precedes` violated with both capabilities present

**Disagreement:** the validator passes and the engine fails with V102.

**Cause:** the validator has no `precedes` check at all, so it accepts a reversed order too.

**Which is right (v1.0.0):** the engine (§4.3: "Validator MUST reject workflows that violate
temporal ordering"; EDGE_TYPES.md §4).

**On the shipped catalog:** this case is in `workflow_catalog.yaml` at 9e2f65b.
`model_deployment` has `verify` at step 0 and `execute` at step 3. The validator passes it,
and the current branch reports V102 on it (see the shipped-catalog section below).

Catalog `r04_precedes_reversed.yaml`:

```yaml
wf:
  goal: detect before observe (observe precedes detect)
  risk: low
  inputs: {}
  steps:
  - capability: detect
    purpose: Detect a pattern
    store_as: d
  - capability: observe
    purpose: Observe afterwards
    store_as: o
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r04_precedes_reversed.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r04_precedes_reversed.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] V102 MISSING_PREREQUISITE: Step 0 (detect): must be preceded by 'observe' but it hasn't been executed in prior steps
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r04_precedes_reversed.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 0 (detect): V102 'detect' must come after 'observe' (precedes), but 'observe' first appears at step 1
(exit status 1)
```

### D3. `audit` step with `mutation: false`

**Disagreement:** the validator passes. The engine reports F504 (downgrade) and also
V102 (`verify precedes audit`, which is D2).

**Cause:** the ontology gives `audit` `mutation: true`. The engine's
`validate_capabilities` rejects any step whose value is lower than the ontology's.
The validator ignores the step's safety flags entirely.

**Which is right (v1.0.0):** the spec does not decide this. §5.2 lists `mutation`
as an optional step field and says nothing on whether a step may lower the ontology
value. §3.3 ("Mutation REQUIRES checkpoints") and §4.2 (VERIFY layer
mutation "Varies") pull in opposite directions. The engine's reading is the safer one,
but it fails every shipped workflow: 11 audit steps in `workflow_catalog.yaml` declare
`mutation: false`. On the current branch this passes because the ontology now marks audit
`mutation_overridable: true` (v1.1.0 §4.1, §4.4, §5.2.1).

Catalog `r05_audit_mutation_false.yaml`:

```yaml
wf:
  goal: audit step declares mutation false
  risk: low
  inputs: {}
  steps:
  - capability: audit
    purpose: Record an event
    mutation: false
    store_as: a
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r05_audit_mutation_false.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r05_audit_mutation_false.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] F504 CONSTRAINT_VIOLATED: Step 0 (audit): ontology declares mutation=true but step downgrades to mutation=false
ENGINE FAIL [wf] V102 MISSING_PREREQUISITE: Step 0 (audit): must be preceded by 'verify' but it hasn't been executed in prior steps
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r05_audit_mutation_false.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

<details>
<summary>The other 24 cases</summary>

### D1b. The same `any` field without an annotation

**Disagreement:** the reverse of D1. The validator fails with B204 and the engine passes,
because the engine never checks for ambiguity.

**Which is right (v1.0.0):** the validator (§5.4 rule 3, "Missing type metadata"; §10.2 L2,
"Reports ambiguous types requiring annotation").

Catalog `r02_any_unannotated.yaml`:

```yaml
wf:
  goal: Bind a field the ontology types as "any" without an annotation
  risk: low
  inputs: {}
  steps:
  - capability: retrieve
    purpose: Fetch data
    store_as: r
  - capability: explain
    purpose: Explain it
    store_as: e
    input_bindings:
      conclusion: ${r.data}
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r02_any_unannotated.yaml
VALIDATION FAIL:
 - Ambiguous type for ${r.data}: inferred unknown is ambiguous/unknown. Add a typed annotation.
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r02_any_unannotated.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r02_any_unannotated.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 1 (explain): B204 ambiguous type for ${r.data}: inferred unknown is ambiguous or unknown; add a typed annotation
(exit status 1)
```

### D1c. Annotation `any` (and the alias `str`) on a typed field

**Disagreement:** the validator passes and the engine reports B203 twice.

**Cause:** the validator's `parse_type` maps every name outside
`string|number|boolean|object|array<>|map<>|nullable<>` to `unknown`, which is
compatible with everything. The engine accepts the aliases (`str`, `list`, `dict`, `int`)
but rejects `any` as a declared type even though `any` is the widest type. Here it
also rejects `str` against an `object` field.

**Which is right (v1.0.0):** §5.3 shows only examples and defines no annotation
grammar. On `str` vs `object` the engine is right under §5.4 rule 2. On `any` the
validator is closer, since an annotation of `any` cannot contradict a schema.
The current branch accepts `: any` and rejects the unknown name `str` with B205
INVALID_ANNOTATION (§9.3).

Catalog `r13b_annotation_any_and_aliases.yaml`:

```yaml
wf:
  goal: annotations any / dict on typed fields
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: "${o.timestamp: any}"
  - capability: critique
    purpose: Critique
    store_as: cr
    input_bindings:
      target: "${o.observation: str}"
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r13b_annotation_any_and_aliases.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r13b_annotation_any_and_aliases.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] B203 TYPE_MISMATCH: Type mismatch: '${o.timestamp}' declared as 'any' but source outputs 'string'
ENGINE FAIL [wf] B203 TYPE_MISMATCH: Type mismatch: '${o.observation}' declared as 'str' but source outputs 'object'
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r13b_annotation_any_and_aliases.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 2 (critique): B205 unknown type annotation 'str' in ${o.observation: str}
(exit status 1)
```

### D2b. `precedes` with several sources (the engine needs all of them)

**Disagreement:** the validator passes and the engine fails twice.

**Cause:** `verify` has three incoming `precedes` edges (from `mutate`, `execute` and `send`).
The engine requires all three, so a correct `checkpoint → constrain → plan → mutate → verify`
workflow fails. A `verify` step can pass the engine only if the workflow mutates,
executes **and** sends.

**Which is right (v1.0.0):** the validator, as for D2.

Catalog `r03b_precedes_any_of_sources.yaml`:

```yaml
wf:
  goal: verify after mutate; execute and send never appear
  risk: high
  inputs: {}
  steps:
  - capability: checkpoint
    purpose: Save state
    mutation: true
    store_as: c
  - capability: constrain
    purpose: Policy check
    store_as: k
  - capability: plan
    purpose: Plan the change
    store_as: p
  - capability: mutate
    purpose: Apply the change
    mutation: true
    requires_checkpoint: true
    requires_approval: true
    store_as: m
  - capability: verify
    purpose: Check the change
    store_as: v
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r03b_precedes_any_of_sources.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r03b_precedes_any_of_sources.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] V102 MISSING_PREREQUISITE: Step 4 (verify): must be preceded by 'execute' but it hasn't been executed in prior steps
ENGINE FAIL [wf] V102 MISSING_PREREQUISITE: Step 4 (verify): must be preceded by 'send' but it hasn't been executed in prior steps
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r03b_precedes_any_of_sources.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

### D3b. Omitted safety flags count as a downgrade in the engine

**Disagreement:** the validator passes and the engine fails with F504.

**Cause:** `WorkflowStep.from_dict` defaults `mutation` and `requires_checkpoint` to `False`,
so a step that omits them looks like a step that lowers them. Any `checkpoint`, `persist`,
`rollback`, `mutate` or `send` step without explicit flags fails the engine.

**Which is right (v1.0.0):** the validator. §5.2 lists these flags under "Each step MAY
define", so omitting one cannot be a violation. The current branch makes inheritance from the
ontology explicit (v1.1.0 §5.2.1) and passes this catalog.

Catalog `r06_flags_omitted.yaml`:

```yaml
wf:
  goal: checkpoint step that omits its safety flags
  risk: low
  inputs: {}
  steps:
  - capability: checkpoint
    purpose: Save state
    store_as: c
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r06_flags_omitted.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r06_flags_omitted.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] F504 CONSTRAINT_VIOLATED: Step 0 (checkpoint): ontology declares mutation=true but step downgrades to mutation=false
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r06_flags_omitted.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

### D4. `requires_checkpoint: false` on `mutate` (with a checkpoint present)

**Disagreement:** the validator passes and the engine fails with F504.

**Cause:** this is the requires_checkpoint half of the engine's downgrade check. The
engine has no requires_approval half, so the `requires_approval: false` on the same
step goes unreported by both tools (see "Candidates that agree").

**Which is right (v1.0.0):** neither clearly. The substantive rule, a checkpoint before
`mutate` (§3.3, §4.4), is met: the checkpoint is at step 0, and both tools enforce it through the
`requires` edge (see r26 under "Candidates that agree"). v1.0.0 does not make the flag
value itself an error. The current branch reports W602 for both flags, applies the ontology
value, and passes.

Catalog `r07_requires_checkpoint_false.yaml`:

```yaml
wf:
  goal: mutate step lowers requires_checkpoint (and requires_approval)
  risk: high
  inputs: {}
  steps:
  - capability: checkpoint
    purpose: Save state
    mutation: true
    store_as: c
  - capability: constrain
    purpose: Policy check
    store_as: k
  - capability: plan
    purpose: Plan the change
    store_as: p
  - capability: mutate
    purpose: Apply the change
    mutation: true
    requires_checkpoint: false
    requires_approval: false
    store_as: m
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r07_requires_checkpoint_false.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r07_requires_checkpoint_false.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] F504 CONSTRAINT_VIOLATED: Step 3 (mutate): ontology declares requires_checkpoint=true but step downgrades to requires_checkpoint=false
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r07_requires_checkpoint_false.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
 - [wf] step 3 (mutate): W602 ontology declares requires_checkpoint=true but step downgrades to requires_checkpoint=false; the ontology value applies (F501 if no checkpoint precedes it)
 - [wf] step 3 (mutate): W602 ontology declares requires_approval=true but step downgrades to requires_approval=false; the ontology value applies (F502 if it is not approved)
VALIDATION PASS
(exit status 0)
```

### D5. `conflicts_with` pair run in sequence

**Disagreement:** the validator passes. The engine fails with F504, and reports it twice.

**Cause:** the validator does not implement `conflicts_with`. The engine rejects any
workflow that contains both capabilities. The ontology declares the edge in both
directions and the engine does not de-duplicate it, so each conflict is reported twice.

**Which is right (v1.0.0):** the engine's verdict. §4.3 and EDGE_TYPES.md §5 say "Both
capabilities MUST NOT appear in the same workflow. Validator MUST reject workflows
containing both." The double report is an engine bug.

**On the shipped catalog:** the engine fails `digital_twin_sync_loop` (mutate +
rollback). The current branch changed the rule: v1.1.0 §4.3 limits it to sharing a
`parallel_group` (F504), so this sequential catalog passes.

Catalog `r09_conflicts_sequential.yaml`:

```yaml
wf:
  goal: persist then rollback, in sequence (persist conflicts_with rollback)
  risk: medium
  inputs: {}
  steps:
  - capability: checkpoint
    purpose: Save state
    mutation: true
    store_as: c
  - capability: persist
    purpose: Store a result
    mutation: true
    store_as: s
  - capability: rollback
    purpose: Undo
    mutation: true
    store_as: rb
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r09_conflicts_sequential.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r09_conflicts_sequential.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] F504 CONSTRAINT_VIOLATED: Step 2 (rollback): conflicts with 'persist' which was already executed
ENGINE FAIL [wf] F504 CONSTRAINT_VIOLATED: Step 2 (rollback): conflicts with 'persist' which was already executed
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r09_conflicts_sequential.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

### D6. A step binds its own `store_as`

**Disagreement:** the validator passes and the engine fails.

**Cause:** the validator registers `store_as` in `schemas_by_store` before it scans the
same step's bindings. The engine registers it afterwards.

**Which is right (v1.0.0):** the engine's verdict. §5.5 item 1 says the referenced
`store_as` must exist "in a prior step". The engine's code is wrong, though: it
reports B201 INVALID_BINDING_PATH, while §9.3 assigns a missing producer to B202
MISSING_PRODUCER. The fault is in `_ERROR_TYPE_TO_CODE`, which maps `unresolved_ref`
to B201. The current branch reports B202.

Catalog `r10_self_reference.yaml`:

```yaml
wf:
  goal: a step binds its own store_as
  risk: low
  inputs: {}
  steps:
  - capability: explain
    purpose: Explain itself
    store_as: e
    input_bindings:
      conclusion: "${e.explanation: string}"
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r10_self_reference.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r10_self_reference.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] B201 INVALID_BINDING_PATH: Reference '${e.explanation}' not found. Available: []
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r10_self_reference.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 0 (explain): B202 unknown reference store 'e' in ${e.explanation: string}
(exit status 1)
```

### D7. Reference to a field the producer does not output

**Disagreement:** the validator fails with B201 and the engine passes.

**Cause:** `_resolve_schema_type` returns `None` for a missing path, and the engine reads
`None` as "nothing to check".

**Which is right (v1.0.0):** the validator (§5.5 item 2; §9.3 B201).

Catalog `r11_bad_path.yaml`:

```yaml
wf:
  goal: reference a field the producer does not output
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: ${o.no_such_field}
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r11_bad_path.yaml
VALIDATION FAIL:
 - Bad reference ${o.no_such_field}: path no_such_field not in schema for o
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r11_bad_path.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r11_bad_path.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 1 (explain): B201 bad reference ${o.no_such_field}: path no_such_field not in schema for o
(exit status 1)
```

### D8. Unannotated binding to an `integer` field

**Disagreement:** the validator fails with B204 and the engine passes.

**Cause:** the validator's `schema_type` knows only `string|number|boolean|object|array`.
`type: integer` falls through to `unknown`, which it then reports as ambiguous. The
same happens to `search.total_count`, `checkpoint.size` and every other integer field.

**Which is right (v1.0.0):** the engine. `integer` is an explicit JSON Schema type and
none of the ambiguity cases in §5.4 rule 3 or §12.2 cover it. The current branch passes
(v1.1.0 §5.4 makes `integer` a subtype of `number`).

Catalog `r12_integer_untyped.yaml`:

```yaml
wf:
  goal: bind an integer field without annotation
  risk: low
  inputs: {}
  steps:
  - capability: search
    purpose: Search
    store_as: s
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: ${s.total_count}
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r12_integer_untyped.yaml
VALIDATION FAIL:
 - Ambiguous type for ${s.total_count}: inferred unknown is ambiguous/unknown. Add a typed annotation.
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r12_integer_untyped.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r12_integer_untyped.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

### D9. Annotation the validator's type grammar does not know (`integer` on an object)

**Disagreement:** the validator passes and the engine fails with B203.

**Cause:** `parse_type("integer")` returns `unknown`, which is compatible with anything,
so any annotation outside the validator's small grammar is never checked.

**Which is right (v1.0.0):** the engine (§5.4 rule 2; §3.5 "Type mismatches MUST be detected
at validation time"). The current branch reports B203.

Catalog `r13_annotation_outside_grammar.yaml`:

```yaml
wf:
  goal: annotate an object field as integer
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: "${o.observation: integer}"
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r13_annotation_outside_grammar.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r13_annotation_outside_grammar.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] B203 TYPE_MISMATCH: Type mismatch: '${o.observation}' declared as 'integer' but source outputs 'object'
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r13_annotation_outside_grammar.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 1 (explain): B203 type mismatch ${o.observation: integer}: annotated integer but schema has object
(exit status 1)
```

### D10. Array item type in an annotation

**Disagreement:** the validator fails with B203 and the engine passes.

**Cause:** the engine compares only the base name (`array<string>`.split("<")[0] is `array`),
so it never checks item types. `receive.data` is `array<object>`.

**Which is right (v1.0.0):** the validator (§5.4 rule 2).

Catalog `r14_array_item_annotation.yaml`:

```yaml
wf:
  goal: annotate array<object> as array<string>
  risk: low
  inputs: {}
  steps:
  - capability: receive
    purpose: Receive messages
    store_as: rc
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: "${rc.data: array<string>}"
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r14_array_item_annotation.yaml
VALIDATION FAIL:
 - Type mismatch ${rc.data: array<string>}: expected array<string> but schema has array<object>
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r14_array_item_annotation.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r14_array_item_annotation.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 1 (explain): B203 type mismatch ${rc.data: array<string>}: annotated array<string> but schema has array<object>
(exit status 1)
```

### D11. A `map<K,V>` annotation hides the whole reference from the engine

**Disagreement:** the validator fails with B202 and the engine passes.

**Cause:** the engine's `_BINDING_REF_PATTERN` allows only `[a-zA-Z_<>]` in the
annotation, with no comma. `${nosuch.field: map<string,object>}` therefore does not match
at all, and the engine skips the reference, including the check that its store exists.

**Which is right (v1.0.0):** the validator (§5.5 item 1).

Catalog `r15_map_annotation_hides_ref.yaml`:

```yaml
wf:
  goal: a map<...> annotation on a store that does not exist
  risk: low
  inputs: {}
  steps:
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: "${nosuch.field: map<string,object>}"
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r15_map_annotation_hides_ref.yaml
VALIDATION FAIL:
 - Unknown reference store 'nosuch' in ${nosuch.field: map<string,object>}
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r15_map_annotation_hides_ref.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r15_map_annotation_hides_ref.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 0 (explain): B202 unknown reference store 'nosuch' in ${nosuch.field: map<string,object>}
(exit status 1)
```

### D12. Annotation with no space after the colon

**Disagreement:** the validator fails with B201 (it reads `observation:object` as a path)
and the engine passes (it reads `object` as the annotation).

**Cause:** `parse_ref_expr` splits only on `": "`. The engine's regex accepts `:\s*`.

**Which is right (v1.0.0):** not specified. §5.3 shows only the spaced form and
gives no whitespace rule. The engine's reading is the more plausible one, and the
current branch agrees with it: it passes this catalog.

Catalog `r16_no_space_annotation.yaml`:

```yaml
wf:
  goal: annotation written without a space after the colon
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: ${o.observation:object}
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r16_no_space_annotation.yaml
VALIDATION FAIL:
 - Bad reference ${o.observation:object}: path observation:object not in schema for o
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r16_no_space_annotation.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r16_no_space_annotation.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

### D13. References in `condition` and `gates[].when`

**Disagreement:** the validator fails with B202 twice and the engine passes.

**Cause:** the engine scans only `input_bindings`.

**Which is right (v1.0.0):** the validator. §10.2 L3 says "Validates gate and condition
expressions", and §5.5 item 1 requires an existing producer.

Catalog `r17_gate_condition_ref.yaml`:

```yaml
wf:
  goal: unknown store referenced from a gate and a condition
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
    condition: ${nosuch.flag} == true
    gates:
    - when: ${missing.value} == null
      action: stop
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r17_gate_condition_ref.yaml
VALIDATION FAIL:
 - Unknown reference store 'nosuch' in ${nosuch.flag}
 - Unknown reference store 'missing' in ${missing.value}
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r17_gate_condition_ref.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r17_gate_condition_ref.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 0 (observe): B202 condition: 'nosuch' is neither an earlier step's store_as nor a workflow input
 - [wf] step 0 (observe): B202 gates[0].when: 'missing' is neither an earlier step's store_as nor a workflow input
(exit status 1)
```

### D14. Duplicate `store_as`

**Disagreement:** the validator fails with V104 and the engine passes.

**Cause:** the engine silently overwrites the earlier entry in `available_refs`.

**Which is right (v1.0.0):** the validator (§9.2 V104; §10.2 L1, "Validates all store_as
identifiers are unique").

Catalog `r18_duplicate_store_as.yaml`:

```yaml
wf:
  goal: two steps share a store_as
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
  - capability: search
    purpose: Search
    store_as: o
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r18_duplicate_store_as.yaml
VALIDATION FAIL:
 - [wf] step 1 'search': duplicate store_as 'o' (first used at step 0)
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r18_duplicate_store_as.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r18_duplicate_store_as.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 1 (search): V104 duplicate store_as 'o' (first used at step 0)
(exit status 1)
```

### D15. Consumer input contract (object into a string input)

**Disagreement:** the validator fails with B203 and the engine passes.

**Cause:** the engine has no consumer-side check.

**Which is right (v1.0.0):** the validator (§5.5 item 3; §10.2 L3).

Catalog `r19_consumer_mismatch.yaml`:

```yaml
wf:
  goal: object bound to a string input
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
  - capability: retrieve
    purpose: Retrieve by target
    store_as: r
    input_bindings:
      target: ${o.observation}
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r19_consumer_mismatch.yaml
VALIDATION FAIL:
 - Consumer input type mismatch in workflow 'wf' step 1 (retrieve): input 'target' expects string but got object from ${o.observation}
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r19_consumer_mismatch.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r19_consumer_mismatch.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 1 (retrieve): B203 consumer input type mismatch: input 'target' expects string but got object from ${o.observation}
(exit status 1)
```

### D16. Annotation on a workflow input that contradicts the input's schema

**Disagreement:** the validator fails with B203 and the engine passes.

**Cause:** `_check_type_compatibility` returns `None` for workflow inputs, with the
comment "Input types validated separately". Nothing validates them separately.

**Which is right (v1.0.0):** the validator (§5.4 rule 2).

Catalog `r20_input_annotation.yaml`:

```yaml
wf:
  goal: annotation on a workflow input contradicts its schema
  risk: low
  inputs:
    name: {type: string}
  steps:
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: "${name: number}"
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r20_input_annotation.yaml
VALIDATION FAIL:
 - Type mismatch ${name: number} (external): expected number but schema has string
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r20_input_annotation.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r20_input_annotation.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 0 (explain): B203 type mismatch ${name: number}: annotated number but schema has string
(exit status 1)
```

### D16b. Path into a workflow input whose schema has no `properties`

**Disagreement:** the validator fails with B204 and the engine passes.

**Which is right (v1.0.0):** the validator (§5.4 rule 3, missing type metadata).

Catalog `r27_input_untyped_path.yaml`:

```yaml
wf:
  goal: path into a workflow input whose schema has no properties
  risk: low
  inputs:
    payload: {type: object}
  steps:
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: ${payload.field}
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r27_input_untyped_path.yaml
VALIDATION FAIL:
 - Ambiguous external type for ${payload.field}: inferred unknown is ambiguous/unknown. Add typed annotation or refine inputs schema.
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r27_input_untyped_path.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r27_input_untyped_path.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 0 (explain): B204 ambiguous type for ${payload.field}: inferred unknown is ambiguous or unknown; add a typed annotation or refine the inputs schema
(exit status 1)
```

### D17. Step without a `capability` key

**Disagreement:** the validator reports V103. The engine crashes with `KeyError`
inside `load_catalog`, so no validation runs.

**Which is right (v1.0.0):** the validator (§5.2; §9.2 V103).

Catalog `r21_missing_capability_key.yaml`:

```yaml
wf:
  goal: step with no capability key
  risk: low
  inputs: {}
  steps:
  - purpose: Orphan step
    store_as: x
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r21_missing_capability_key.yaml
VALIDATION FAIL:
 - [wf] step 0: invalid step (missing 'capability' key)
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r21_missing_capability_key.yaml
Traceback (most recent call last):
  ... (frames elided) ...
             ~~~~~~~~~~~~~~~~~~~~~~^^^
  File "<checkout>/…", line 127, in from_dict
    capability=data["capability"],
               ~~~~^^^^^^^^^^^^^^
KeyError: 'capability'
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r21_missing_capability_key.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 0: V103 step 0 is invalid (missing 'capability' key)
(exit status 1)
```

### D18. Non-mapping top-level entry in the catalog

**Disagreement:** the validator crashes with `AttributeError` and the engine
skips the entry with a log warning and passes.

**Which is right (v1.0.0):** v1.0.0 does not define the catalog's top level. A crash is
wrong whichever reading applies. The current branch reports S303.

Catalog `r22_non_mapping_entry.yaml`:

```yaml
version: "1.0"
wf:
  goal: catalog with a non-workflow scalar entry
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r22_non_mapping_entry.yaml
Traceback (most recent call last):
  ... (frames elided) ...
    ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<checkout>/…", line 474, in check_workflow
    steps = wf.get('steps',[]) or []
            ^^^^^^
AttributeError: 'str' object has no attribute 'get'
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r22_non_mapping_entry.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r22_non_mapping_entry.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [version]: S303 workflow 'version' must be a mapping, found string
(exit status 1)
```

### D19. `steps: null`

**Disagreement:** the validator passes (`or []`) and the engine crashes with `TypeError`
in `load_catalog`.

**Which is right (v1.0.0):** neither. §5.1 makes `steps` a required array, so the catalog
should be rejected with a diagnostic, not passed and not crash. The current branch reports S303.

Catalog `r23_steps_null.yaml`:

```yaml
wf:
  goal: workflow whose steps key is null
  risk: low
  inputs: {}
  steps:
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r23_steps_null.yaml
VALIDATION PASS
(exit status 0)
```

9e2f65b, engine:

```console
$ python engine_check.py . r23_steps_null.yaml
Traceback (most recent call last):
  ... (frames elided) ...
                            ~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^
  File "<checkout>/…", line 160, in from_dict
    steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]
                                                ~~~~~~~~^^^^^^^^^^^^^
TypeError: 'NoneType' object is not iterable
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r23_steps_null.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf]: S303 'steps' must be a list, found null
(exit status 1)
```

### D20. `mapping_ref` / `output_conforms_to` naming missing files

**Disagreement:** the validator fails with S301 twice and the engine passes. The engine
does not read these fields: `WorkflowStep` drops them.

**Which is right (v1.0.0):** the validator (§9.4 S301).

Catalog `r24_mapping_ref_missing.yaml`:

```yaml
wf:
  goal: transform with a mapping_ref that does not exist
  risk: low
  inputs: {}
  steps:
  - capability: retrieve
    purpose: Fetch
    store_as: r
  - capability: transform
    purpose: Convert
    mapping_ref: schemas/transforms/does_not_exist.yaml
    output_conforms_to: schemas/does_not_exist.json
    store_as: t
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r24_mapping_ref_missing.yaml
VALIDATION FAIL:
 - [wf] step 1 'transform' mapping_ref missing file: schemas/transforms/does_not_exist.yaml
 - [wf] step 1 'transform' output_conforms_to missing file: schemas/does_not_exist.json
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r24_mapping_ref_missing.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r24_mapping_ref_missing.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 1 (transform): S301 mapping_ref missing file: schemas/transforms/does_not_exist.yaml
 - [wf] step 1 (transform): S301 output_conforms_to missing file: schemas/does_not_exist.json
(exit status 1)
```

### D21. Unknown capability: same verdict, different diagnostics

**Disagreement:** both tools fail with V101, but their diagnostics differ.

**Cause:** the validator `continue`s before it registers the unknown step's `store_as`,
so a later reference to it adds B202. The engine registers the `store_as` anyway and
reports only V101.

**Which is right (v1.0.0):** both are defensible. The current branch follows the
validator: V101 + B202.

Catalog `r25_unknown_capability.yaml`:

```yaml
wf:
  goal: unknown capability, later referenced
  risk: low
  inputs: {}
  steps:
  - capability: frobnicate
    purpose: Not in the ontology
    store_as: f
  - capability: explain
    purpose: Explain
    store_as: e
    input_bindings:
      conclusion: "${f.result: object}"
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r25_unknown_capability.yaml
VALIDATION FAIL:
 - [wf] step 0: unknown capability 'frobnicate'
 - Unknown reference store 'f' in ${f.result: object}
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r25_unknown_capability.yaml
loaded 1 workflow(s)
ENGINE FAIL [wf] V101 UNKNOWN_CAPABILITY: Step 0 (frobnicate): capability not found in ontology
(exit status 1)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r25_unknown_capability.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION FAIL:
 - [wf] step 0 (frobnicate): V101 capability 'frobnicate' not found in ontology
 - [wf] step 1 (explain): B202 unknown reference store 'f' in ${f.result: object}
(exit status 1)
```

### D22. Catalog larger than 1 MiB

**Disagreement:** the validator refuses to load the file and the engine loads it and
passes. The catalog is a valid one-step workflow padded with a 1.1 MB YAML comment
(the YAML block below is truncated).

**Cause:** the two loaders behave identically (`tools/yaml_util.py` mirrors
`grounded_agency/utils/safe_yaml.py`), but they are called with different limits. The
validator uses the default `DEFAULT_MAX_BYTES` (1 MiB) for the catalog. The engine's
`load_catalog` passes `ONTOLOGY_MAX_BYTES` (10 MiB).

**Which is right (v1.0.0):** not specified. The current branch loads the file and passes.

Catalog `r28_large_catalog.yaml`:

```yaml
wf:
  goal: valid one-step workflow padded past 1 MiB with a YAML comment
  risk: low
  inputs: {}
  steps:
  - capability: observe
    purpose: Observe
    store_as: o
# xxxxxxxx… (1,100,000 'x' characters)
```

9e2f65b, validator:

```console
$ python tools/validate_workflows.py --catalog r28_large_catalog.yaml
ERROR: Cannot load workflow catalog: YAML file exceeds size limit: <file> is 1,100,172 bytes (limit: 1,048,576 bytes)
(exit status 1)
```

9e2f65b, engine:

```console
$ python engine_check.py . r28_large_catalog.yaml
loaded 1 workflow(s)
ENGINE PASS (validate_all_structured: no errors)
(exit status 0)
```

After the fix (branch `claude/gifted-albattani-qwnlo3`):

```console
$ python tools/validate_workflows.py --catalog r28_large_catalog.yaml
WARNINGS:
 - [wf]: W605 no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets
VALIDATION PASS
(exit status 0)
```

</details>

### Candidates that agree at 9e2f65b

Both tools give the same verdict on these catalogs, so they are not disagreements.
Several are blind spots the two tools share.

* **`requires_approval: false` on `mutate` (`r08_requires_approval_false.yaml`).**
  Both tools pass: neither checks `requires_approval`. The engine checks only
  `mutation` and `requires_checkpoint`. The current branch passes with
  `W602 … requires_approval=true but step downgrades to requires_approval=false`.
* **`requires` edge unmet: `rollback` without a `checkpoint` (`r26_requires_missing.yaml`).**
  Both tools fail with V102. Validator: `[wf] step 0 'rollback' missing required prereq 'checkpoint'
  before it`. Engine: `V102 MISSING_PREREQUISITE: Step 0 (rollback): requires 'checkpoint' but it
  hasn't been executed in prior steps`. The current branch also reports V102.
* **Unquoted typed reference in a YAML list item (`r29_unquoted_typed_ref_in_list.yaml`,
  `- ${nosuch.items: array<object>}`).** PyYAML reads the item as the mapping
  `{'${nosuch.items': 'array<object>}'}`. Both tools scan only mapping values, so both miss
  the reference and pass. The shipped catalog has two such items (`monitor_and_replan`
  step 5). The current branch reports
  `W612 YAML read '${nosuch.items: array<object>}' as a mapping …` plus
  `B202 unknown reference store 'nosuch'`.
* **YAML parsing.** Both tools use PyYAML `safe_load` behind byte-for-byte equivalent
  size-guard wrappers (`tools/yaml_util.py` and `grounded_agency/utils/safe_yaml.py`).
  An unquoted `key: ${a.b: type}` gives the same `ScannerError` (exit 1) in both. The
  only loading difference is the size limit (D22).
* **Unknown capability, verdict only.** Both tools fail with V101. The diagnostics differ;
  see D21.
