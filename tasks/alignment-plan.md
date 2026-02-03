# Alignment Plan: STANDARD-v1.0.0.md ↔ Implementation

Date: 2026-02-03

## Approach

Each discrepancy requires a direction decision: fix the spec, fix the implementation, or both. The principle is **the ontology YAML is the source of truth** for capability definitions, and the standard is the source of truth for process requirements (error model, conformance, workflow DSL semantics).

---

## Phase 1: Fix stale references in the standard

These are unambiguous — the standard references v1 artifacts that no longer exist. The implementation is correct; the spec text must be updated.

### 1.1 Rewrite Appendix A (Critical — A1)

**File:** `spec/STANDARD-v1.0.0.md` lines 679-690

**Problem:** Appendix A shows 8 layers / 99 capabilities from the archived v1 model. Section 4.2 of the same document correctly shows 9 layers / 36 capabilities.

**Action:** Replace Appendix A table with the current model:

```
| Layer       | Count | Capabilities |
|-------------|-------|--------------|
| PERCEIVE    | 4     | retrieve, search, observe, receive |
| UNDERSTAND  | 6     | detect, classify, measure, predict, compare, discover |
| REASON      | 4     | plan, decompose, critique, explain |
| MODEL       | 5     | state, transition, attribute, ground, simulate |
| SYNTHESIZE  | 3     | generate, transform, integrate |
| EXECUTE     | 3     | execute, mutate, send |
| VERIFY      | 5     | verify, checkpoint, rollback, constrain, audit |
| REMEMBER    | 2     | persist, recall |
| COORDINATE  | 4     | delegate, synchronize, invoke, inquire |
```

### 1.2 Fix common patterns (Medium — A5)

**File:** `spec/STANDARD-v1.0.0.md` lines 615-644

**Problem:** Section 12.5 uses capabilities that don't exist in the 36-model.

**Actions:**
- "Safe Mutation" pattern line 621: `act-plan` → `mutate` (with `store_as: mutate_out`)
- "Multi-Source Integration" pattern line 641: remove the `identity-resolution` step entirely (identity resolution is a policy, not an atomic capability)

### 1.3 Fix schema filename reference (Medium — A4)

**File:** `spec/STANDARD-v1.0.0.md` line 276

**Action:** `identity_policy.yaml` → `identity_resolution_policy.yaml`

### 1.4 Fix stale error example (Low — A6)

**File:** `spec/STANDARD-v1.0.0.md` line 444

**Action:** `"Did you mean 'detect-anomaly'?"` → `"Did you mean 'detect' with domain: 'anomaly'?"`

---

## Phase 2: Resolve design decisions

These discrepancies require choosing which direction is correct.

### 2.1 Section 4.4: verify ↔ constrain relationship (High — A2)

**File:** `spec/STANDARD-v1.0.0.md` line 146

**Problem:** Standard says `verify` requires `constrain`. Ontology has them as `alternative_to` (substitutable, not dependent).

**Decision needed:**
- **Option A (recommended):** Fix the spec. The ontology's `alternative_to` semantics are correct — `verify` checks post-hoc, `constrain` checks pre-execution. They substitute, not depend. Change section 4.4 to remove the `verify → constrain` row, or change "Requires" column to say `(none — see alternative_to with constrain)`.
- **Option B:** Add a `soft_requires` edge from `verify` to `constrain` in the ontology. This would mean "verification should have constraints to check against", which has some logic but conflicts with workflows that use `verify` without `constrain`.

**Action (assuming Option A):** Remove the `verify | constrain` row from the Section 4.4 table. Optionally add a note: "verify and constrain are `alternative_to` each other — verify checks post-hoc, constrain checks pre-execution."

### 2.2 CLAUDE.md: Should delegate/invoke have requires_approval? (High — B3)

**Problem:** CLAUDE.md says `delegate`, `invoke` have `requires_approval: true`. The ontology does not set this flag on them.

**Decision needed:**
- **Option A (recommended):** Fix CLAUDE.md. The ontology is intentional — delegation and invocation are orchestration actions, not mutations. They don't need approval themselves; the individual capabilities they compose may need approval.
- **Option B:** Add `requires_approval: true` to `delegate`, `invoke`, `synchronize` in the ontology. This would be a safety-conservative change but could make workflows overly restrictive.

**Action (assuming Option A):** Fix CLAUDE.md Safety Model to only list `execute`, `mutate`, `send` as having `requires_approval: true`.

### 2.3 Audit mutation flag (Low — B6)

**Problem:** Ontology says `audit` has `mutation: true`. Every workflow overrides it to `mutation: false` with comments explaining "append-only, non-destructive."

**Decision needed:**
- **Option A:** Keep `mutation: true` in ontology (conservative — writing to disk IS a mutation). Keep workflow overrides (practical — append-only writes don't need checkpoints). Add a note to the ontology explaining this distinction.
- **Option B:** Change ontology to `mutation: false` and add a new `side_effects: append_only` property. More precise but changes the schema.

**Action (assuming Option A):** Add a comment to `audit` in the ontology:
```yaml
# mutation: true because audit writes to disk, but workflows may override
# to false because append-only writes are non-destructive
```

---

## Phase 3: Fix CLAUDE.md documentation

After Phase 2 decisions, update CLAUDE.md to match reality.

### 3.1 Update hooks documentation (Low — B1)

**File:** `CLAUDE.md` line 120

**Action:** `PreToolUse (Write|Edit)` → `PreToolUse (Write|Edit|MultiEdit|NotebookEdit|Bash)`

### 3.2 Update Safety Model section (Medium — B2, B3, B4)

**File:** `CLAUDE.md` lines 225-237

**Actions:**
- High-risk list: keep `mutate`, `send`. Add note that `checkpoint`, `rollback`, `audit`, `persist` also have `mutation: true` but are not high-risk.
- Medium-risk list: `execute`, `delegate`, `invoke` → `execute`, `rollback`, `delegate`, `synchronize`, `invoke`
- `requires_approval`: only `execute`, `mutate`, `send` (remove from delegate/invoke)

### 3.3 Fix COORDINATE description (Low — B5)

**File:** `CLAUDE.md` line 95

**Action:** "Multi-agent interaction" → "Multi-agent and user interaction"

---

## Phase 4: Implement the error model

This is the largest work item. The standard specifies 23 error codes and a structured JSON format that no tool emits.

### 4.1 Create error code registry

**New file:** `grounded_agency/errors.py`

Define an enum or constants mapping for all 23 error codes:
- V101-V105 (Validation)
- B201-B205 (Binding)
- S301-S304 (Schema)
- R401-R404 (Runtime)
- F501-F505 (Safety)

Include the structured error response class:
```python
@dataclass
class StandardError:
    code: str       # "V101"
    name: str       # "UNKNOWN_CAPABILITY"
    message: str    # Human-readable
    location: dict  # {workflow, step, field}
    suggestion: str | None
```

### 4.2 Integrate into validate_workflows.py

**File:** `tools/validate_workflows.py`

Refactor the 13 `errors.append(f"...")` calls to emit `StandardError` objects. Map current string errors to codes:

| Current error pattern | Standard code |
|-----------------------|---------------|
| `unknown capability` | V101 |
| `missing prerequisite` | V102 |
| `bad reference path` | B201 |
| `unknown reference store` | B202 |
| `type mismatch` | B203 |
| `ambiguous type` | B204 |
| `type annotation mismatch` | B205 |
| `mapping_ref missing` | S301 |
| `output_conforms_to missing` | S301 |
| `consumer input type mismatch` | B203 |

Output the structured JSON format to `validator_suggestions.json`.

### 4.3 Integrate into workflow engine

**File:** `grounded_agency/workflows/engine.py`

Map `BindingError.error_type` values to standard codes:
- `unresolved_ref` → B201
- `type_mismatch` → B203
- `missing_store_as` → B202

Add `code` field to `BindingError` dataclass.

### 4.4 Integrate into SDK exceptions

**File:** `grounded_agency/coordination/exceptions.py`

Add `error_code` field to exception classes and map:
- `CapabilityMismatchError` → V101
- `AgentNotRegisteredError` → R402

---

## Phase 5: Close conformance gaps

### 5.1 Fix misnamed test fixture (Medium — A7 related)

**File:** `tests/fixtures/fail_consumer_contract_mismatch.workflow_catalog.yaml`

**Problem:** This fixture uses old v1 capabilities (`inspect`, `map-relationships`, `act-plan`, `identity-resolution`, `world-state`, etc.). It fails at L1 (unknown capability), never reaching L3 contract checking. It's misnamed.

**Actions:**
- Rename to `fail_unknown_capabilities_v1.workflow_catalog.yaml`
- Update `EXPECTATIONS.json`: change level from `L3` to `L1`, category from `types` to `structural`
- Create a new genuine L3 fixture that uses valid capabilities but has actual type mismatches between producer output and consumer input

### 5.2 Create patch fixtures (Medium — A7)

**New files:** `tests/fixtures/patch_*.workflow_catalog.yaml`

Create 2-3 fixtures that have L3/L4 errors with expected patch output:
- `patch_type_coercion_string_to_number.workflow_catalog.yaml` — string output bound to number input, fixable by coercion
- `patch_missing_transform_step.workflow_catalog.yaml` — type mismatch fixable by inserting transform step

Update `EXPECTATIONS.json` with `expected_patch` metadata for each.

### 5.3 Add version headers (Low — A8)

**Files:** `schemas/workflow_catalog.yaml`, `tests/fixtures/*.workflow_catalog.yaml`

Add `# Standard version: 1.0.0` as first line. This is a SHOULD-level recommendation.

### 5.4 Address SEC-009 trust model review (Medium — B7)

**Files:** `schemas/profiles/*.yaml` (7 files)

**Decision needed:** Either:
- Review each profile's trust_weights and set `trust_model_reviewed: true` with `trust_model_reviewed_at` timestamp
- Or acknowledge these are example profiles and add documentation stating they are not production-reviewed

---

## Execution Order and Dependencies

```
Phase 1 (spec text fixes)          ─── no dependencies, can start immediately
    │
Phase 2 (design decisions)        ─── independent of Phase 1
    │
Phase 3 (CLAUDE.md fixes)         ─── depends on Phase 2 decisions
    │
Phase 4 (error model)             ─── depends on Phase 1.4 (stale code reference)
    │                                   can start in parallel with Phases 1-3
    │
Phase 5 (conformance)             ─── depends on Phase 4 (error codes needed for fixtures)
```

Phases 1, 2, and the start of 4 can proceed in parallel.

---

## Files Changed Summary

| Phase | Files modified | Files created |
|-------|---------------|---------------|
| 1 | `spec/STANDARD-v1.0.0.md` | — |
| 2 | `spec/STANDARD-v1.0.0.md`, `schemas/capability_ontology.yaml` (comment only) | — |
| 3 | `CLAUDE.md` | — |
| 4 | `tools/validate_workflows.py`, `grounded_agency/workflows/engine.py`, `grounded_agency/coordination/exceptions.py` | `grounded_agency/errors.py` |
| 5 | `tests/fixtures/EXPECTATIONS.json`, `schemas/workflow_catalog.yaml`, `schemas/profiles/*.yaml` | 3-4 new test fixtures |
