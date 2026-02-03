# Grounded Agency Benchmark Suite

> Reproducible scenarios for validating that Grounded Agency provides measurable benefits over naive agent implementations.

## Overview

This benchmark suite empirically validates the three core claims of Grounded Agency:

1. **Grounding improves accuracy** when sources conflict
2. **Checkpointing enables recovery** when mutations fail
3. **Typed contracts catch errors** before runtime

Each scenario compares a **baseline implementation** (naive/common approach) against a **Grounded Agency implementation** using real SDK components (`CapabilityRegistry`, `CheckpointTracker`, `EvidenceStore`).

## Quick Start

```bash
# Run all benchmarks
python benchmarks/runner.py

# Run a specific scenario
python benchmarks/runner.py --scenario conflicting_sources

# Generate comparison report
python benchmarks/runner.py --report

# Run benchmark tests
pytest benchmarks/tests/ -v
```

## SDK Integration

The GA paths use real SDK components instead of inline simulation:

| Scenario | SDK Component | Purpose |
|----------|--------------|---------|
| Capability Gap | `CapabilityRegistry` | Loads real `requires` edges from ontology |
| Mutation Recovery | `CheckpointTracker` | Full create/validate/consume lifecycle |
| Conflicting Sources | `EvidenceStore` | Evidence anchor collection and tracking |
| Workflow Type Error | `safe_yaml_load` | Loads coercions from canonical registry |

This prevents drift — ontology changes automatically propagate to benchmarks.

## Scenarios

| # | Scenario | Tests | Baseline Approach | GA Approach |
|---|----------|-------|-------------------|-------------|
| 1 | [Conflicting Sources](#scenario-1-conflicting-sources) | Grounding | Last-write-wins | Trust-weighted resolution |
| 2 | [Mutation Failure Recovery](#scenario-2-mutation-failure-recovery) | Reversibility | Manual recovery | Checkpoint + rollback |
| 3 | [Decision Audit](#scenario-3-decision-audit) | Explainability | No/hallucinated explanation | Evidence anchor traversal |
| 4 | [Workflow Type Error](#scenario-4-workflow-type-error) | Typed contracts | Runtime crash | Design-time detection |
| 5 | [Capability Gap Detection](#scenario-5-capability-gap-detection) | Dependency graph | Runtime failure | Pre-execution blocking |

## Metrics

Each scenario measures:

| Metric | Description |
|--------|-------------|
| **Accuracy** | Correctness compared to ground truth |
| **Recovery Rate** | Successful state restoration after failure |
| **Detection Rate** | Errors caught before runtime |
| **Faithfulness** | Explanation matches actual reasoning |
| **Time to Detection** | When errors are caught (design vs. runtime) |

## Implementation Structure

```
benchmarks/
├── README.md                      # This file
├── runner.py                      # Test harness and report generation
├── scenarios/
│   ├── __init__.py                # Scenario registry
│   ├── base.py                    # BenchmarkScenario ABC
│   ├── conflicting_sources.py     # Scenario 1 (uses EvidenceStore)
│   ├── mutation_recovery.py       # Scenario 2 (uses CheckpointTracker)
│   ├── decision_audit.py          # Scenario 3
│   ├── workflow_type_error.py     # Scenario 4 (loads coercion registry)
│   └── capability_gap.py          # Scenario 5 (uses CapabilityRegistry)
├── fixtures/
│   ├── mock_apis.json             # API response fixtures
│   └── workflows/                 # Test workflow definitions
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Shared fixtures (registry, paths)
│   └── test_scenarios.py          # Unit and integration tests
└── results/
    └── .gitkeep                   # Results directory (artifacts)
```

## Running Benchmarks

### Prerequisites

```bash
# Ensure in project root
cd agent-capability-standard

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### Full Suite

```bash
python benchmarks/runner.py
```

### Individual Scenarios

```bash
# Run specific scenario with verbose output
python benchmarks/runner.py --scenario conflicting_sources --verbose

# Run with custom iteration count
python benchmarks/runner.py --scenario mutation_recovery --iterations 50
```

### Generate Report

```bash
# Generate markdown report
python benchmarks/runner.py --report --output results/benchmark_report.md

# Generate JSON metrics
python benchmarks/runner.py --report --format json --output results/metrics.json
```

## Extending the Suite

### Adding a New Scenario

1. Create scenario module in `scenarios/`:

```python
# scenarios/new_scenario.py
from .base import BenchmarkScenario

class NewScenario(BenchmarkScenario):
    name = "new_scenario"
    description = "Tests new aspect of GA"

    def setup(self):
        """Prepare test fixtures"""
        pass

    def run_baseline(self):
        """Execute baseline approach"""
        return {"metric": value}

    def run_ga(self):
        """Execute Grounded Agency approach"""
        return {"metric": value}

    def compare(self, baseline_result, ga_result):
        """Compare and return metrics"""
        return {"improvement": ga_result["metric"] - baseline_result["metric"]}
```

2. Register in `scenarios/__init__.py`
3. Add corresponding baseline to `baselines/`
4. Document in this README

## Interpretation Guidelines

### Scenario 1 (Conflicting Sources)

- **~50% baseline accuracy** indicates random selection
- **85%+ GA accuracy** demonstrates trust model effectiveness
- Sources use diverse types (high-trust vs low-trust) to exercise weighting

### Scenario 2 (Mutation Recovery)

- **0% baseline recovery** is expected (no checkpoint = no recovery)
- **100% GA recovery** demonstrates checkpoint/rollback pattern via `CheckpointTracker`

### Scenario 3 (Decision Audit)

- **Faithfulness < 50%** indicates confabulation
- **Faithfulness = 100%** indicates reliable audit trails from evidence anchors

### Scenario 4 (Workflow Type Error)

- **Detection at design-time** = GA working correctly
- **Coercion suggestions** loaded from canonical `transform_coercion_registry.yaml`

### Scenario 5 (Capability Gap)

- **Prevented failures** = workflows blocked before execution
- Dependency graph loaded from `CapabilityRegistry` (real `requires` edges)
- Self-correcting: ontology changes automatically propagate

## Known Limitations

1. **Synthetic scenarios**: Real-world complexity may differ
2. **Trust weight calibration**: Default weights from authority_trust_model.yaml, not production-tuned
3. **LLM-as-judge variance**: Faithfulness scores may vary across models
4. **Determinism**: Some scenarios involve randomness (controlled via seed)

## Related Documentation

- [Failure Taxonomy](../docs/research/failure_taxonomy.md) - Informs scenario selection
- [Capability Ontology](../schemas/capability_ontology.yaml) - Defines GA primitives
- [Trust Model](../schemas/authority_trust_model.yaml) - Conflict resolution weights
- [Workflow DSL](../docs/WORKFLOW_PATTERNS.md) - Composition patterns

---

**Status**: SDK-integrated | **Last Updated**: 2026-02-03
