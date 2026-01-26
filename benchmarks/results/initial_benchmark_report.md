# Grounded Agency Benchmark Report

**Generated**: 2026-01-27T00:31:00.044493

## Summary

| Scenario | Baseline | GA | Improvement |
|----------|----------|-----|-------------|
| conflicting_sources | 54.0% | 91.0% | +37.0% |
| mutation_recovery | 0.0% | 100.0% | +100.0% |
| decision_audit | 38.0% | 100.0% | +62.0% |
| workflow_type_error | 100.0% | 100.0% | +100.0% |
| capability_gap | 100.0% | 100.0% | +0.0% |

## Detailed Results

### conflicting_sources

**Description**: Tests trust-weighted conflict resolution vs last-write-wins

#### Baseline Metrics

- accuracy: 54.0%
- correct_count: 54.00
- total_count: 100.00
- has_evidence: 0.0%

#### Grounded Agency Metrics

- accuracy: 91.0%
- correct_count: 91.00
- total_count: 100.00
- has_evidence: 1.00
- evidence_completeness: 1.00

#### Improvement

- accuracy_improvement_absolute: 37.0%
- accuracy_improvement_percent: 68.52
- evidence_completeness: 1.00

### mutation_recovery

**Description**: Tests checkpoint/rollback recovery vs no checkpointing

#### Baseline Metrics

- recovery_rate: 0.0%
- data_integrity_rate: 0.0%
- lines_preserved: 55.00
- lines_lost: 45.00
- recovery_time_ms: 0.0%
- has_checkpoint: 0.0%

#### Grounded Agency Metrics

- recovery_rate: 1.00
- data_integrity_rate: 1.00
- lines_preserved: 100.00
- lines_lost: 0.0%
- recovery_time_ms: 6.8%
- has_checkpoint: 1.00
- checkpoint_hash: 6f996b43944915156bf480d45a52d09fad5bcd464f360202ee6962f27155f303

#### Improvement

- recovery_rate_improvement: 1.00
- data_integrity_improvement: 1.00
- lines_saved: 45.00
- recovery_time_ms: 6.8%

### decision_audit

**Description**: Tests evidence-based explanations vs confabulated ones

#### Baseline Metrics

- faithfulness: 38.0%
- evidence_coverage: 0.0%
- confabulation_rate: 48.0%

#### Grounded Agency Metrics

- faithfulness: 1.00
- evidence_coverage: 1.00
- confabulation_rate: 0.0%

#### Improvement

- faithfulness_improvement: 62.0%
- evidence_coverage_improvement: 1.00
- confabulation_reduction: 48.0%

### workflow_type_error

**Description**: Tests design-time type validation vs runtime errors

#### Baseline Metrics

- detection_rate: 1.00
- design_time_detection_rate: 0.0%
- runtime_detection_rate: 1.00
- suggestion_accuracy: 0.0%

#### Grounded Agency Metrics

- detection_rate: 1.00
- design_time_detection_rate: 1.00
- runtime_detection_rate: 0.0%
- suggestion_accuracy: 1.00

#### Improvement

- design_time_detection_improvement: 1.00
- runtime_errors_prevented: 1.00
- suggestion_accuracy: 1.00

### capability_gap

**Description**: Tests pre-execution dependency checking vs runtime failures

#### Baseline Metrics

- detection_rate: 1.00
- design_time_detection_rate: 0.0%
- compute_wasted: 1400.00
- compute_saved: 0.0%
- false_negatives: 0.0%

#### Grounded Agency Metrics

- detection_rate: 1.00
- design_time_detection_rate: 1.00
- compute_wasted: 0.0%
- compute_saved: 2200.00
- identification_accuracy: 1.00

#### Improvement

- detection_improvement: 0.0%
- design_time_detection_improvement: 1.00
- compute_savings: 3600.00
- identification_accuracy: 1.00

---

## Interpretation

- **Scenario 1 (Conflicting Sources)**: Higher accuracy indicates better conflict resolution
- **Scenario 2 (Mutation Recovery)**: 100% recovery rate indicates checkpoint/rollback working
- **Scenario 3 (Decision Audit)**: Higher faithfulness indicates reliable explanations
- **Scenario 4 (Workflow Type Error)**: Design-time detection prevents runtime failures
- **Scenario 5 (Capability Gap)**: Pre-execution blocking saves wasted compute

## Methodology

Each scenario compares a baseline (naive) approach against a Grounded Agency approach.
Baseline approaches represent common patterns without GA's structural guarantees.
GA approaches use the capability ontology with evidence grounding, typed contracts,
and reversibility guarantees.

For full methodology, see the [benchmark README](./README.md).