# Workflow Coverage Analysis

**Document Status**: Informative
**Last Updated**: 2026-01-26
**Version**: 2.0.0

---

## Purpose

This document tracks which capabilities are exercised by reference workflows, identifies coverage gaps, and guides workflow development priorities.

---

## 1. Coverage Summary

| Metric | Value |
|--------|-------|
| Total Capabilities | 35 |
| Used in Workflows | 29 (83%) |
| Unused | 6 (17%) |
| Reference Workflows | 5 |
| Total Workflow Steps | 51 |

**Note**: The 36-capability model consolidates domain-specific variants into parameterized atomic capabilities (e.g., `detect` with `domain: anomaly` instead of `detect-anomaly`).

---

## 2. Capability Usage Matrix

### Legend

| Symbol | Meaning |
|--------|---------|
| ● | Used in this workflow |
| ○ | Not used |

### PERCEIVE Layer (4 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| retrieve | ○ | ● | ○ | ○ | ○ | 1 |
| search | ● | ○ | ○ | ● | ○ | 2 |
| observe | ● | ● | ● | ○ | ○ | 3 |
| receive | ○ | ○ | ○ | ● | ○ | 1 |

**Coverage**: 4/4 (100%)

### UNDERSTAND Layer (6 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| detect | ○ | ● | ○ | ● | ○ | 2 |
| classify | ○ | ● | ○ | ● | ○ | 2 |
| measure | ○ | ● | ○ | ● | ○ | 2 |
| predict | ○ | ○ | ○ | ● | ○ | 1 |
| compare | ○ | ○ | ● | ● | ○ | 2 |
| discover | ○ | ○ | ● | ○ | ○ | 1 |

**Coverage**: 6/6 (100%)

### REASON Layer (4 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| plan | ● | ○ | ○ | ● | ○ | 2 |
| decompose | ○ | ○ | ○ | ○ | ○ | 0 |
| critique | ● | ○ | ○ | ○ | ○ | 1 |
| explain | ○ | ● | ○ | ● | ○ | 2 |

**Coverage**: 3/4 (75%)

### MODEL Layer (5 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| state | ○ | ● | ○ | ● | ○ | 2 |
| transition | ○ | ● | ○ | ● | ○ | 2 |
| attribute | ● | ● | ● | ○ | ○ | 3 |
| ground | ○ | ● | ○ | ○ | ○ | 1 |
| simulate | ○ | ● | ○ | ○ | ○ | 1 |

**Coverage**: 5/5 (100%)

### SYNTHESIZE Layer (3 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| generate | ○ | ○ | ● | ○ | ○ | 1 |
| transform | ○ | ○ | ○ | ● | ○ | 1 |
| integrate | ○ | ● | ○ | ● | ○ | 2 |

**Coverage**: 3/3 (100%)

### EXECUTE Layer (3 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| execute | ● | ○ | ○ | ● | ○ | 2 |
| mutate | ○ | ○ | ○ | ● | ○ | 1 |
| send | ○ | ○ | ○ | ○ | ○ | 0 |

**Coverage**: 2/3 (67%)

### VERIFY Layer (5 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| verify | ● | ○ | ○ | ● | ○ | 2 |
| checkpoint | ● | ○ | ○ | ● | ○ | 2 |
| rollback | ● | ○ | ○ | ● | ○ | 2 |
| constrain | ● | ○ | ○ | ● | ○ | 2 |
| audit | ● | ● | ● | ● | ○ | 4 |

**Coverage**: 5/5 (100%)

### REMEMBER Layer (2 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| persist | ○ | ○ | ○ | ○ | ○ | 0 |
| recall | ○ | ○ | ○ | ○ | ○ | 0 |

**Coverage**: 0/2 (0%)

### COORDINATE Layer (3 capabilities)

| Capability | debug_code | world_model | gap_analysis | twin_sync | twin_bootstrap | Count |
|------------|------------|-------------|--------------|-----------|----------------|-------|
| delegate | ○ | ○ | ○ | ○ | ○ | 0 |
| synchronize | ○ | ○ | ○ | ○ | ○ | 0 |
| invoke | ○ | ○ | ○ | ○ | ● | 1 |

**Coverage**: 1/3 (33%)

---

## 3. Coverage by Layer

| Layer | Total | Used | Coverage |
|-------|-------|------|----------|
| PERCEIVE | 4 | 4 | 100% |
| UNDERSTAND | 6 | 6 | 100% |
| REASON | 4 | 3 | 75% |
| MODEL | 5 | 5 | 100% |
| SYNTHESIZE | 3 | 3 | 100% |
| EXECUTE | 3 | 2 | 67% |
| VERIFY | 5 | 5 | 100% |
| REMEMBER | 2 | 0 | 0% |
| COORDINATE | 4 | 1 | 25% |
| **TOTAL** | **36** | **29** | **81%** |

---

## 4. Unused Capabilities (6)

| Capability | Layer | Suggested Workflow |
|------------|-------|-------------------|
| `decompose` | REASON | Complex planning, task breakdown |
| `send` | EXECUTE | Notification, alert, message workflows |
| `persist` | REMEMBER | Learning agent, memory-augmented workflows |
| `recall` | REMEMBER | Context retrieval, knowledge lookup |
| `delegate` | COORDINATE | Multi-agent collaboration |
| `synchronize` | COORDINATE | Parallel execution coordination |

---

## 5. Priority Gaps

### Critical (0% coverage)

| Layer | Capabilities | Suggested Workflows |
|-------|--------------|---------------------|
| REMEMBER | persist, recall | Personal assistant, Learning agent, Memory-augmented reasoning |

### High Priority (< 50% coverage)

| Layer | Coverage | Capabilities Needed | Suggested Workflows |
|-------|----------|---------------------|---------------------|
| COORDINATE | 25% | delegate, synchronize, inquire | Multi-agent collaboration, Parallel processing |

### Medium Priority (50-80% coverage)

| Layer | Coverage | Capabilities Needed | Suggested Workflows |
|-------|----------|---------------------|---------------------|
| EXECUTE | 67% | send | Notification, alert dispatch |
| REASON | 75% | decompose | Complex task breakdown |

---

## 6. Proposed Workflows for 100% Coverage

### GitHub Issue #12: Domain-Specific Workflow Templates

| Proposed Workflow | Capabilities Exercised | Coverage Impact |
|-------------------|----------------------|-----------------|
| Personal Assistant | persist, recall, send | +3 capabilities |
| Multi-Agent Task Delegation | delegate, synchronize, decompose | +3 capabilities |

Implementing these 2 workflows would achieve **100% coverage** (35/35).

---

## 7. Comparison: Old vs New Model

| Metric | Old (99 caps) | New (35 caps) |
|--------|---------------|---------------|
| Total Capabilities | 99 | 35 |
| Used in Workflows | 34 (34%) | 29 (83%) |
| Unused | 65 (66%) | 6 (17%) |
| Layers with 0% coverage | 2 | 1 |
| Layers with 100% coverage | 1 | 6 |

The 36-capability model achieves **higher coverage with fewer primitives** because domain parameterization eliminates redundant variants.

---

## 8. Conclusion

Current coverage is **29/36 (81%)**. This indicates:

1. **Strong foundation**: 6 of 9 layers have 100% coverage
2. **Focused gaps**: Only 7 capabilities remain unused
3. **Clear path to 100%**: Two targeted workflows can close the gap

The [Extension Governance](EXTENSION_GOVERNANCE.md) process includes usage requirements, which ensures any proposed new capability must demonstrate coverage gaps that existing capabilities cannot address.

---

## References

- [GitHub Issue #12: Domain-specific workflow templates](https://github.com/synaptiai/agent-capability-standard/issues/12)
- [EXTENSION_GOVERNANCE.md](EXTENSION_GOVERNANCE.md) — Capability tier definitions
- `schemas/workflow_catalog.yaml` — Reference workflow definitions
- `schemas/capability_ontology.json` — 36-capability ontology
