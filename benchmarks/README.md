# Grounded Agency Benchmark Suite

> Reproducible scenarios for validating that Grounded Agency provides measurable benefits over naive agent implementations.

## Overview

This benchmark suite empirically validates the three core claims of Grounded Agency:

1. **Grounding improves accuracy** when sources conflict
2. **Checkpointing enables recovery** when mutations fail
3. **Typed contracts catch errors** before runtime

Each scenario compares a **baseline implementation** (naive/common approach) against a **Grounded Agency implementation** using the capability ontology.

## Quick Start

```bash
# Run all benchmarks
python benchmarks/runner.py

# Run a specific scenario
python benchmarks/runner.py --scenario conflicting_sources

# Generate comparison report
python benchmarks/runner.py --report
```

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

## Scenario Details

### Scenario 1: Conflicting Sources

**Problem**: Two data sources return different values for the same entity.

**Setup**:
- API A returns `{"user_id": "123", "status": "active"}`
- API B returns `{"user_id": "123", "status": "suspended"}`
- Ground truth: User was active until 2h ago, now suspended

**Baseline** (Last-Write-Wins):
```
1. Call API A → get "active"
2. Call API B → get "suspended"
3. Return last response: "suspended" (correct by luck)
4. OR return first response: "active" (incorrect)
```

**Grounded Agency**:
```
1. retrieve(API A) → status="active", timestamp=T-3h
2. retrieve(API B) → status="suspended", timestamp=T-1h
3. integrate(sources, conflict_resolution=trust_weighted)
   - API A: trust=0.88, recency=exp(-(3h)/τ) = 0.82
   - API B: trust=0.88, recency=exp(-(1h)/τ) = 0.97
   - Score A: 0.88 × 0.82 = 0.72
   - Score B: 0.88 × 0.97 = 0.85
4. Return "suspended" with evidence anchors
```

**Metrics**:
- Accuracy on 100 seeded conflicts
- Consistency across repeated runs
- Evidence trail completeness

---

### Scenario 2: Mutation Failure Recovery

**Problem**: File edit fails mid-operation, leaving corrupted state.

**Setup**:
- Original file: 100 lines of valid configuration
- Task: Update lines 50-60 with new values
- Injected failure: Process crash at line 55

**Baseline** (No Checkpointing):
```
1. Open file for write
2. Write lines 1-54 (success)
3. CRASH at line 55
4. Result: File truncated at line 54
5. Recovery: Manual reconstruction from memory/logs
```

**Grounded Agency**:
```
1. checkpoint(file_state) → recovery point created
2. mutate(file, lines=50-60)
3. CRASH at line 55
4. Detect: verify(mutation) → FAIL
5. rollback(checkpoint) → restore to line 100
6. Result: Original file intact
```

**Metrics**:
- State recovery rate (complete/partial/failed)
- Data integrity (bytes match original)
- Recovery time

---

### Scenario 3: Decision Audit

**Problem**: User asks "Why did you choose option X?"

**Setup**:
- Agent selected deployment strategy B over A and C
- User requests explanation

**Baseline** (No Audit Trail):
```
1. Agent recalls it chose B
2. Agent generates explanation: "B was optimal"
3. No verification that explanation matches reasoning
4. Risk: Confabulated justification
```

**Grounded Agency**:
```
1. audit_log records: compare([A, B, C], criteria=[cost, latency, reliability])
2. Evidence anchors: [cost_report:L12, latency_test:L45, reliability_data:L78]
3. explain(decision=B) → traverses anchors
4. Output: "B chosen because: cost=$50 (A=$80, C=$90) per anchor cost_report:L12"
```

**Metrics**:
- Faithfulness score (explanation matches actual reasoning)
- Evidence anchor coverage
- Human evaluator agreement (or LLM-as-judge)

---

### Scenario 4: Workflow Type Error

**Problem**: Step N produces type T1 but Step N+1 expects T2.

**Setup**:
- Step 1: `retrieve` → outputs `{documents: array<string>}`
- Step 2: `transform` → expects `{source: object}`
- Mismatch: array vs object

**Baseline** (Runtime Check Only):
```
1. Execute step 1 → produces ["doc1", "doc2"]
2. Execute step 2 → receives ["doc1", "doc2"]
3. RUNTIME ERROR: Cannot read property 'field' of array
4. User sees: "Unexpected error in transform step"
```

**Grounded Agency**:
```
1. Validate workflow definition (design-time)
2. Type inference: step1.output = array<string>
3. Type check: step2.input requires object
4. DESIGN-TIME ERROR: Type mismatch at step2.input
5. Suggestion: Insert transform(array_to_object) between steps
```

**Metrics**:
- Error detection rate (design-time vs runtime)
- Time to detection (pre-execution vs during execution)
- Coercion suggestion accuracy

---

### Scenario 5: Capability Gap Detection

**Problem**: Workflow requires capability the agent lacks.

**Setup**:
- Workflow: `retrieve → transform → execute → send`
- Agent capabilities: `retrieve, transform, execute` (missing `send`)
- Baseline agent attempts the workflow

**Baseline** (Attempt at Runtime):
```
1. Execute retrieve → success
2. Execute transform → success
3. Execute execute → success
4. Execute send → RUNTIME ERROR: "send" not available
5. All previous work wasted
```

**Grounded Agency**:
```
1. Parse workflow definition
2. Check capability dependencies against agent manifest
3. Gap detected: "send" required but not available
4. BLOCKED: Workflow cannot execute
5. Suggestion: Add "send" capability or use alternative workflow
```

**Metrics**:
- Prevented runtime failures
- Resource savings (compute not wasted on doomed workflows)
- Gap identification accuracy

---

## Implementation Structure

```
benchmarks/
├── README.md                      # This file
├── runner.py                      # Test harness
├── scenarios/
│   ├── __init__.py
│   ├── conflicting_sources.py     # Scenario 1
│   ├── mutation_recovery.py       # Scenario 2
│   ├── decision_audit.py          # Scenario 3
│   ├── workflow_type_error.py     # Scenario 4
│   └── capability_gap.py          # Scenario 5
├── fixtures/
│   ├── mock_apis.json             # API response fixtures
│   ├── test_files/                # Files for mutation tests
│   ├── audit_logs/                # Sample audit trails
│   └── workflows/                 # Test workflow definitions
├── baselines/
│   ├── last_write_wins.py         # Baseline conflict resolution
│   ├── no_checkpoint.py           # Baseline mutation handling
│   └── runtime_only.py            # Baseline type checking
└── results/
    └── .gitkeep                   # Results directory
```

## Running Benchmarks

### Prerequisites

```bash
# Ensure in project root
cd agent-capability-standard

# Activate virtual environment
source .venv/bin/activate

# Install dependencies (if not already)
pip install pyyaml
```

### Full Suite

```bash
# Run all scenarios with default iterations
python benchmarks/runner.py

# Output:
# Scenario 1: Conflicting Sources
#   Baseline accuracy: 52% (random chance)
#   GA accuracy: 94%
#   Improvement: +42%
#
# Scenario 2: Mutation Recovery
#   Baseline recovery: 0%
#   GA recovery: 100%
#   Improvement: +100%
# ...
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
        return {
            "baseline": baseline_result,
            "ga": ga_result,
            "improvement": ga_result["metric"] - baseline_result["metric"]
        }
```

2. Register in `scenarios/__init__.py`
3. Add fixtures to `fixtures/`
4. Document in this README

## Interpretation Guidelines

### Scenario 1 (Conflicting Sources)

- **50% baseline accuracy** indicates random selection
- **90%+ GA accuracy** demonstrates trust model effectiveness
- **Evidence anchors** should trace to actual source timestamps

### Scenario 2 (Mutation Recovery)

- **0% baseline recovery** is expected (no checkpoint = no recovery)
- **100% GA recovery** demonstrates checkpoint/rollback pattern
- **Partial recovery** indicates checkpoint granularity issues

### Scenario 3 (Decision Audit)

- **Faithfulness < 50%** indicates confabulation
- **Faithfulness > 80%** indicates reliable audit trails
- **Human evaluator disagreement** may indicate ambiguous criteria

### Scenario 4 (Workflow Type Error)

- **Detection at design-time** = GA working correctly
- **Detection at runtime** = baseline behavior
- **Coercion suggestions** should match registry

### Scenario 5 (Capability Gap)

- **Prevented failures** = workflows blocked before execution
- **Resource savings** = compute not wasted on incomplete workflows
- **Gap identification** should be 100% accurate

## Known Limitations

1. **Synthetic scenarios**: Real-world complexity may differ
2. **Trust weight calibration**: Default weights, not production-tuned
3. **LLM-as-judge variance**: Faithfulness scores may vary across models
4. **Determinism**: Some scenarios involve randomness (controlled via seed)

## Related Documentation

- [Failure Taxonomy](../docs/research/failure_taxonomy.md) - Informs scenario selection
- [Capability Ontology](../schemas/capability_ontology.json) - Defines GA primitives
- [Trust Model](../schemas/authority_trust_model.yaml) - Conflict resolution weights
- [Workflow DSL](../docs/WORKFLOW_PATTERNS.md) - Composition patterns

---

**Status**: Initial implementation | **Last Updated**: 2026-01-27
