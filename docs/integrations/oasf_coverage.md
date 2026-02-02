# OASF Coverage Report

**Mapping Version:** 1.1.0
**OASF Target Version:** 0.8.0
**Grounded Agency Version:** 2.0.0 (36 atomic capabilities)

## Overview

The OASF-to-Grounded-Agency mapping covers **30 of 36** capabilities through standard OASF skill codes. The remaining capabilities are handled through GA extensions and partial mappings:

| Status | Count | Description |
|--------|-------|-------------|
| Fully mapped | 23 | Complete OASF skill code coverage |
| Partially mapped | 7 | Some OASF codes exist but with incomplete semantics |
| Unmapped (GA extensions) | 6 | No OASF equivalent; wrapped with synthetic `GA-` codes |

## GA Extension Codes

These 6 capabilities have no corresponding OASF skill category. They are assigned synthetic `GA-` prefixed codes so they participate in the standard translation and reverse-lookup pipeline.

| GA Code | Capability | Layer | Risk | Description |
|---------|-----------|-------|------|-------------|
| `GA-001` | `attribute` | MODEL | low | Causal reasoning and attribution analysis |
| `GA-002` | `integrate` | SYNTHESIZE | low | Data merging from multiple sources |
| `GA-003` | `recall` | REMEMBER | low | Stored data retrieval from agent memory |
| `GA-004` | `receive` | PERCEIVE | low | Pushed data and event acceptance |
| `GA-005` | `send` | EXECUTE | **high** | External data transmission (requires checkpoint) |
| `GA-006` | `transition` | MODEL | low | State machine transition and dynamics modeling |

> **Safety note:** `GA-005` (`send`) is the only GA extension with `risk: high`. It requires checkpoint enforcement before invocation, consistent with the standard `send` capability's safety contract.

## Partial Mappings

These 7 capabilities have some OASF skill codes but the mapping does not fully capture their semantics:

| Capability | Layer | OASF Codes | Coverage Gap |
|-----------|-------|------------|--------------|
| `checkpoint` | VERIFY | 12, 1201, 1202, 1204 | Only DevOps/MLOps; missing from general safety workflows |
| `simulate` | MODEL | 15, 1501, 1504 | Only Advanced Reasoning; missing domain-specific simulation |
| `inquire` | COORDINATE | 10, 1004 | Only Agent Orchestration; missing human-in-the-loop clarification |
| `synchronize` | COORDINATE | 10, 1004 | Only Agent Orchestration; missing distributed state sync |
| `state` | MODEL | 1, 15, 106, 1501, 1504 | NLP and Reasoning only; missing general world-model representation |
| `ground` | MODEL | 1, 6, 103 | NLP and RAG only; missing domain-agnostic evidence anchoring |
| `rollback` | VERIFY | 12, 1202 | Only Deployment Orchestration; missing general recovery |

## For OASF Consumers

### Translating GA extension codes

```python
from grounded_agency.adapters import OASFAdapter

adapter = OASFAdapter("schemas/interop/oasf_mapping.yaml")

# Translate a GA extension code — works like any OASF code
result = adapter.translate("GA-001")
print(result.mapping.capabilities)   # ("attribute",)
print(result.mapping.mapping_type)   # "ga_extension"
print(result.mapping.domain_hint)    # "causal"
```

### Identifying GA extensions

```python
# List all GA extensions
for ext in adapter.list_ga_extensions():
    print(f"{ext.skill_code}: {ext.skill_name} -> {ext.capabilities}")

# Check if a mapping is a GA extension
mapping = adapter.get_mapping("GA-005")
if mapping and mapping.mapping_type == "ga_extension":
    print("This is a GA-native capability, not an OASF standard code")
```

### Coverage introspection

```python
# Get unmapped capability IDs
unmapped = adapter.unmapped_capabilities()
# ["attribute", "integrate", "recall", "receive", "send", "transition"]

# Get partial mappings with their OASF codes
partial = adapter.partial_capabilities()
# {"checkpoint": ["12", "1201", "1202", "1204"], ...}

# Full coverage report
report = adapter.coverage_report()
print(f"Fully mapped: {report['fully_mapped']}/36")
print(f"Unmapped: {report['unmapped_count']}")
print(f"Partial: {report['partial_count']}")
```

## OASF Version Tracking

This mapping targets **OASF v0.8.0**. As the OASF standard evolves, some GA extensions may be superseded by native OASF skill categories. The [OASF Safety Extensions Proposal](../proposals/OASF_SAFETY_EXTENSIONS.md) advocates for first-class adoption of `checkpoint`, `rollback`, and `ground` as OASF skill categories.

When new OASF versions add coverage for currently unmapped capabilities:
1. Add the new OASF code to `categories` in `oasf_mapping.yaml`
2. Update the capability's `reverse_mapping` entry to include the OASF code
3. Move the capability from `coverage_gaps.unmapped` to `coverage_gaps.partial` (or remove entirely)
4. Consider deprecating the corresponding `GA-` extension code

## Safety Notes

- **`send` (GA-005)** requires checkpoint enforcement before invocation. This is the only high-risk GA extension. OASF consumers must ensure checkpoint safety when mapping to this capability.
- **`checkpoint` and `rollback`** are partially mapped but critical to the Grounded Agency safety model. The partial OASF coverage (DevOps/MLOps only) does not capture their general-purpose safety semantics.
- **`ground`** (evidence anchoring) is partially covered by OASF NLP/RAG categories but its domain-agnostic evidence anchoring semantics are unique to Grounded Agency.
