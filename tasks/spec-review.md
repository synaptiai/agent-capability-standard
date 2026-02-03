# Specification vs. Implementation Review

Date: 2026-02-03

## Summary

The implementation is largely consistent with the specification. All 6 validation tools pass, counts are synchronized across all documentation files, and all referenced files exist. However, there are **7 discrepancies** between what `CLAUDE.md` documents and what the implementation actually does.

---

## Discrepancies Found

### 1. Hooks matcher is broader than documented

| | Documented (CLAUDE.md:120) | Actual (hooks/hooks.json:5) |
|--|---|---|
| PreToolUse matcher | `Write\|Edit` | `Write\|Edit\|MultiEdit\|NotebookEdit\|Bash` |

CLAUDE.md says the PreToolUse hook triggers on `Write|Edit`, but `hooks.json` also covers `MultiEdit`, `NotebookEdit`, and `Bash`. The documentation understates the actual enforcement scope.

### 2. Medium-risk capability list is incomplete

| | Documented (CLAUDE.md:233) | Actual (ontology) |
|--|---|---|
| Medium-risk capabilities | `execute`, `delegate`, `invoke` | `execute`, `rollback`, `delegate`, `synchronize`, `invoke` |

`rollback` (VERIFY layer) and `synchronize` (COORDINATE layer) are `risk: medium` in the ontology but are not listed in the Safety Model section of CLAUDE.md.

### 3. `requires_approval` incorrectly attributed to delegate and invoke

CLAUDE.md:233-234 states:
> Medium-risk capabilities (`execute`, `delegate`, `invoke`) have:
> - `requires_approval: true`

**Actual ontology**: Only `execute` (line 1002), `mutate` (line 1045), and `send` (line 1083) have `requires_approval: true`. The capabilities `delegate`, `synchronize`, and `invoke` are medium-risk but do **not** have `requires_approval: true` set in the ontology.

### 4. Mutation capabilities are only partially documented

CLAUDE.md's Safety Model section only mentions `mutate` and `send` as having `mutation: true`. The ontology defines **6** mutation capabilities:

| Capability | Risk | `mutation: true` | Documented in Safety Model? |
|------------|------|-------------------|-----------------------------|
| `mutate` | high | yes | yes |
| `send` | high | yes | yes |
| `checkpoint` | low | yes | **no** |
| `rollback` | medium | yes | **no** |
| `audit` | low | yes | **no** |
| `persist` | low | yes | **no** |

### 5. COORDINATE layer description drops "and user"

| | CLAUDE.md:95 | Ontology (line 90) |
|--|---|---|
| COORDINATE description | "Multi-agent interaction" | "Multi-agent and user interaction" |

This matters because `inquire` specifically handles user interaction (not just multi-agent).

### 6. Workflow catalog overrides audit's mutation flag

The ontology defines `audit` with `mutation: true`, but every workflow in `workflow_catalog.yaml` overrides it to `mutation: false`. A comment at line 1241 explains:
> audit has mutation: true in the ontology (writes audit log), but workflows mark it mutation: false because the mutation is append-only and non-destructive

This is intentionally documented in the catalog, but not mentioned in CLAUDE.md or the ontology itself. The semantic disagreement between the ontology and the workflow catalog could be confusing.

### 7. All domain profiles fail SEC-009 trust model review

All 7 domain profiles (`audio`, `data_analysis`, `healthcare`, `manufacturing`, `multimodal`, `personal_assistant`, `vision`) have `trust_model_reviewed` unset (None). The profile schema defines this as a SEC-009 security control:
> Trust weights may not reflect intentional calibration. Set trust_model_reviewed: true after reviewing trust_weights.

Profile validation passes but with 7 warnings.

---

## Verified as Consistent

These areas have **no discrepancies**:

- **Capability count**: 36 atomic capabilities — consistent across all 11+ documentation files
- **Layer count**: 9 cognitive layers — consistent everywhere
- **Layer composition**: Per-layer capability counts match (PERCEIVE:4, UNDERSTAND:6, REASON:4, MODEL:5, SYNTHESIZE:3, EXECUTE:3, VERIFY:5, REMEMBER:2, COORDINATE:4)
- **Workflow count**: 12 composed workflows — consistent across CLAUDE.md, README.md, skills/README.md, and workflow_catalog.yaml
- **Skill files**: 41 SKILL.md files exist (36 atomic + 5 composed) matching skills/README.md
- **All referenced files exist**: ontology, profiles, templates, archive, interop mapping, edge types spec, modality guide, OASF proposal, SDK components
- **SDK components**: All 5 documented classes (GroundedAgentAdapter, CapabilityRegistry, ToolCapabilityMapper, CheckpointTracker, EvidenceStore) exist in `grounded_agency/`
- **Edge types**: 7 types documented in spec/EDGE_TYPES.md match the 7 types in the ontology (95 total edges)
- **Validation tools**: All 6 validators pass (workflows, profiles, skill refs, ontology graph, YAML sync, transform refs)

---

## Severity Assessment

| # | Discrepancy | Severity | Reason |
|---|-------------|----------|--------|
| 1 | Hooks matcher | Low | Implementation is stricter than documented (not weaker) |
| 2 | Medium-risk list | Medium | Users may not realize rollback/synchronize are medium-risk |
| 3 | requires_approval claim | **High** | Documentation claims a constraint that the ontology does not enforce |
| 4 | Mutation list incomplete | Medium | 4 mutation capabilities not mentioned in safety model |
| 5 | COORDINATE description | Low | Minor wording difference |
| 6 | audit mutation override | Low | Intentionally documented in workflow catalog |
| 7 | SEC-009 trust review | Medium | All profiles missing formal trust calibration |
