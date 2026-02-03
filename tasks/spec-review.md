# Specification vs. Implementation Review

Date: 2026-02-03

## Summary

This review compares the formal standard (`spec/STANDARD-v1.0.0.md`) against the actual implementation (ontology YAML, validators, SDK, skills, workflows). While the core architecture is sound, there are **significant discrepancies** — including an internally inconsistent appendix in the standard itself, missing error model implementation, and several claims in the standard that the ontology does not enforce.

---

## Part 1: STANDARD-v1.0.0.md vs Implementation

### CRITICAL: Appendix A contradicts Section 4.2 (internal inconsistency)

The standard is **self-contradictory**. Section 4.2 and Appendix A define completely different layer architectures:

| Aspect | Section 4.2 (lines 98-112) | Appendix A (lines 679-690) |
|--------|---------------------------|---------------------------|
| Layer count | **9** layers | **8** layers |
| Total capabilities | **36** | **99** (4+45+20+12+7+6+2+3) |
| Layer names | PERCEIVE, UNDERSTAND, REASON, MODEL, SYNTHESIZE, EXECUTE, VERIFY, REMEMBER, COORDINATE | PERCEPTION, MODELING, REASONING, ACTION, SAFETY, META, MEMORY, COORDINATION |
| PERCEIVE/PERCEPTION examples | (not listed) | `inspect`, `search`, `retrieve`, `receive` |
| COORDINATE/COORDINATION count | 4 | 3 |

Appendix A is a leftover from the archived v1 99-capability model. Specific stale references:
- `inspect` — does not exist (current: `observe`)
- `detect-*`, `identify-*`, `estimate-*` — old domain-specific variants (current: `detect`, `classify`, `measure` with domain params)
- `act-plan` — does not exist (current: `execute` or `mutate`)
- `mitigate`, `improve`, `prioritize` — do not exist in the 36-capability model
- `invoke-workflow` — does not exist (current: `invoke`)
- `model-schema` — does not exist (current: `state`)
- META layer — does not exist in the current model
- COORDINATION shows count 3, but implementation has 4 (missing `inquire`)

**The implementation matches Section 4.2. Appendix A is entirely wrong.**

### Section 4.4: `verify` → `constrain` relationship is wrong

The standard (line 146) states:
> | `verify` | `constrain` | Should have constraints to verify against |

**Actual ontology**: `verify` and `constrain` are `alternative_to` each other (lines 1864-1871), meaning they are *substitutable*, not dependent. There is no `requires` or `soft_requires` edge from `verify` to `constrain`.

### Section 6.1: Schema filename mismatch

| Standard says (line 276) | Actual file |
|--------------------------|-------------|
| `identity_policy.yaml` | `identity_resolution_policy.yaml` |

### Section 9: Error model is specified but not implemented

The standard defines a complete error model (25 error codes across 5 categories: V1xx, B2xx, S3xx, R4xx, F5xx) and a structured JSON response format. **None of this is implemented**:

| Component | Standard requires | Actual |
|-----------|------------------|--------|
| Validation tools | Emit V101, V102, etc. codes | Plain string error messages |
| Workflow engine | BindingError with B2xx codes | Internal types (`unresolved_ref`, `type_mismatch`) |
| SDK exceptions | F5xx safety error codes | Python exceptions without codes |
| Error response format | `{error: {code, name, message, location, suggestion}}` | No structured format |
| Tutorial references | V101, V102, B201, B204 shown in examples | Examples reference codes that tools don't emit |

The error codes appear only in documentation (`docs/TUTORIAL.md`, `spec/SECURITY.md`), never in executable code.

### Section 9.7: Error example references stale capability

The standard's error response example (line 444):
```json
"suggestion": "Did you mean 'detect-anomaly'?"
```

`detect-anomaly` is from the old 99-capability model. The current model uses `detect` with `domain: anomaly`.

### Section 10.3: Patch fixtures missing

The standard requires three categories of conformance tests:
1. Positive fixtures — **13 exist** ✓
2. Negative fixtures — **8 exist** ✓
3. Patch fixtures (invalid workflows with expected patch suggestions) — **0 exist** ✗

The `fail_consumer_contract_mismatch` fixture is the closest candidate but it actually tests L1 structural errors (unknown capabilities like `inspect`), not L3 contract mismatches. It never reaches the type-checking code.

### Section 11.5: Version headers missing

The standard says workflow files SHOULD include `# Standard version: 1.0.0`. Neither the workflow catalog nor any fixture files include this header.

### Section 12.5: Common patterns reference non-existent capabilities

The "Safe Mutation" pattern (line 622) uses `act-plan` — this capability does not exist in the 36-model ontology.

The "Multi-Source Integration" pattern (line 643) uses `identity-resolution` — this is not an atomic capability in the ontology.

---

## Part 2: CLAUDE.md vs Implementation

### 1. Hooks matcher understated

| | CLAUDE.md (line 120) | hooks.json |
|--|---|---|
| PreToolUse matcher | `Write\|Edit` | `Write\|Edit\|MultiEdit\|NotebookEdit\|Bash` |

### 2. Medium-risk list incomplete

| | CLAUDE.md | Ontology |
|--|---|---|
| Medium-risk | `execute`, `delegate`, `invoke` | `execute`, `rollback`, `delegate`, `synchronize`, `invoke` |

### 3. `requires_approval` incorrectly attributed

CLAUDE.md claims medium-risk capabilities (`execute`, `delegate`, `invoke`) all have `requires_approval: true`. **Only `execute` does** (plus the high-risk `mutate` and `send`). `delegate`, `synchronize`, and `invoke` do NOT have this flag.

### 4. Mutation capabilities partially documented

CLAUDE.md mentions `mutate` and `send` as mutation capabilities. The ontology has **6**: also `checkpoint`, `rollback`, `audit`, `persist`.

### 5. COORDINATE layer description

CLAUDE.md: "Multi-agent interaction". Ontology: "Multi-agent **and user** interaction".

### 6. Workflow catalog overrides audit mutation flag

All workflows set `audit` to `mutation: false` despite ontology `mutation: true`. Documented as intentional in comments but not in CLAUDE.md or the ontology.

### 7. Domain profiles missing SEC-009 trust review

All 7 profiles have `trust_model_reviewed: null`.

---

## Part 3: What's Consistent

- **36 atomic capabilities** across **9 cognitive layers** — counts match everywhere
- **12 workflow patterns** in catalog — consistent
- **41 skill files** (36 atomic + 5 composed) — all present
- **7 edge types** — spec/EDGE_TYPES.md matches ontology
- **95 edges** — ontology graph validates (no orphans, no cycles, symmetric pairs verified)
- **All 6 validators pass** (workflows, profiles, skill refs, ontology graph, YAML sync, transform refs)
- **SDK components** — all 5 documented classes exist and match docs
- **Conformance levels L1-L4** — validator code implements all levels
- **22 conformance fixtures** — all pass expected behavior
- **6 transform coercions** — registry matches implementation

---

## Severity Assessment

| # | Discrepancy | Severity | Category |
|---|-------------|----------|----------|
| A1 | Appendix A shows 99-cap/8-layer model | **Critical** | Standard internal inconsistency |
| A2 | `verify` requires `constrain` claim | **High** | Standard vs ontology |
| A3 | Error model not implemented | **High** | Standard vs implementation |
| A4 | `identity_policy.yaml` filename | Medium | Standard vs implementation |
| A5 | `act-plan`, `identity-resolution` in patterns | Medium | Standard references stale caps |
| A6 | `detect-anomaly` in error example | Low | Standard references stale cap |
| A7 | Patch fixtures missing | Medium | Conformance gap |
| A8 | Version headers missing | Low | SHOULD-level recommendation |
| B1 | Hooks matcher understated | Low | CLAUDE.md vs implementation |
| B2 | Medium-risk list incomplete | Medium | CLAUDE.md vs ontology |
| B3 | `requires_approval` for delegate/invoke | **High** | CLAUDE.md claims unenforced constraint |
| B4 | Mutation list incomplete | Medium | CLAUDE.md vs ontology |
| B5 | COORDINATE description | Low | CLAUDE.md vs ontology |
| B6 | audit mutation override | Low | Ontology vs workflow catalog |
| B7 | SEC-009 trust review | Medium | Profiles incomplete |
