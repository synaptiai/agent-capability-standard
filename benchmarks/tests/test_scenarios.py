"""
Unit tests for benchmark scenarios.

Tests that:
- Scenarios produce expected metric ranges
- Edge cases are handled properly
- Results are reproducible with same seed
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmarks.scenarios import (
    SCENARIOS,
    BenchmarkScenario,
    CapabilityGapScenario,
    ConflictingSourcesScenario,
    DecisionAuditScenario,
    MutationRecoveryScenario,
    WorkflowTypeErrorScenario,
)
from benchmarks.scenarios.base import BenchmarkResult


class TestBenchmarkScenarioBase:
    """Tests for the base BenchmarkScenario class."""

    def test_all_scenarios_registered(self):
        """All scenario classes should be in SCENARIOS dict."""
        assert len(SCENARIOS) == 5
        assert "conflicting_sources" in SCENARIOS
        assert "mutation_recovery" in SCENARIOS
        assert "decision_audit" in SCENARIOS
        assert "workflow_type_error" in SCENARIOS
        assert "capability_gap" in SCENARIOS

    def test_scenario_has_required_attributes(self):
        """Each scenario should have name and description."""
        for name, scenario_class in SCENARIOS.items():
            assert hasattr(scenario_class, "name")
            assert hasattr(scenario_class, "description")
            assert scenario_class.name == name


class TestConflictingSourcesScenario:
    """Tests for Scenario 1: Conflicting Sources."""

    def test_baseline_accuracy_around_50_percent(self):
        """Baseline (random selection) should be ~50% accurate."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=100)
        scenario.setup()
        result = scenario.run_baseline()

        # Random selection should be approximately 50% (allow variance)
        assert 0.40 <= result["accuracy"] <= 0.65

    def test_ga_accuracy_higher_than_baseline(self):
        """GA should significantly outperform baseline."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=100)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()

        assert ga["accuracy"] > baseline["accuracy"]
        assert ga["accuracy"] >= 0.85  # Should be 85%+ with trust weighting

    def test_ga_always_has_evidence(self):
        """GA results should always include evidence anchors."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=10)
        scenario.setup()
        result = scenario.run_ga()

        assert result["has_evidence"] is True
        assert result["evidence_completeness"] == 1.0

    def test_reproducibility_with_same_seed(self):
        """Same seed should produce identical results."""
        scenario1 = ConflictingSourcesScenario(seed=42, num_cases=50)
        scenario1.setup()
        result1 = scenario1.run_ga()

        scenario2 = ConflictingSourcesScenario(seed=42, num_cases=50)
        scenario2.setup()
        result2 = scenario2.run_ga()

        assert result1["accuracy"] == result2["accuracy"]
        assert result1["correct_count"] == result2["correct_count"]

    def test_different_seeds_produce_different_results(self):
        """Different seeds should produce different test cases."""
        scenario1 = ConflictingSourcesScenario(seed=42, num_cases=50)
        scenario1.setup()

        scenario2 = ConflictingSourcesScenario(seed=123, num_cases=50)
        scenario2.setup()

        # Test cases should differ
        assert scenario1.test_cases[0] != scenario2.test_cases[0]


class TestMutationRecoveryScenario:
    """Tests for Scenario 2: Mutation Recovery."""

    def test_baseline_has_zero_recovery(self):
        """Baseline without checkpoint should have 0% recovery."""
        scenario = MutationRecoveryScenario(seed=42)
        scenario.setup()
        result = scenario.run_baseline()

        assert result["recovery_rate"] == 0.0
        assert result["has_checkpoint"] is False

    def test_ga_has_full_recovery(self):
        """GA with checkpoint should have 100% recovery."""
        scenario = MutationRecoveryScenario(seed=42)
        scenario.setup()
        result = scenario.run_ga()

        assert result["recovery_rate"] == 1.0
        assert result["data_integrity_rate"] == 1.0
        assert result["has_checkpoint"] is True

    def test_baseline_loses_data(self):
        """Baseline should lose data on failure."""
        scenario = MutationRecoveryScenario(seed=42, file_lines=100, failure_line=55)
        scenario.setup()
        result = scenario.run_baseline()

        assert result["lines_lost"] > 0
        assert result["lines_preserved"] < 100

    def test_ga_preserves_all_data(self):
        """GA should preserve all data via rollback."""
        scenario = MutationRecoveryScenario(seed=42, file_lines=100)
        scenario.setup()
        result = scenario.run_ga()

        assert result["lines_lost"] == 0
        assert result["lines_preserved"] == 100


class TestDecisionAuditScenario:
    """Tests for Scenario 3: Decision Audit."""

    def test_baseline_has_confabulation(self):
        """Baseline should sometimes confabulate."""
        scenario = DecisionAuditScenario(seed=42, num_decisions=50)
        scenario.setup()
        result = scenario.run_baseline()

        assert result["confabulation_rate"] > 0
        assert result["evidence_coverage"] == 0.0

    def test_ga_never_confabulates(self):
        """GA should never confabulate (uses evidence)."""
        scenario = DecisionAuditScenario(seed=42, num_decisions=50)
        scenario.setup()
        result = scenario.run_ga()

        assert result["confabulation_rate"] == 0.0
        assert result["evidence_coverage"] == 1.0

    def test_ga_faithfulness_is_perfect(self):
        """GA should have 100% faithfulness (explanation matches reasoning)."""
        scenario = DecisionAuditScenario(seed=42, num_decisions=50)
        scenario.setup()
        result = scenario.run_ga()

        assert result["faithfulness"] == 1.0


class TestWorkflowTypeErrorScenario:
    """Tests for Scenario 4: Workflow Type Error."""

    def test_baseline_detects_at_runtime_only(self):
        """Baseline should only detect errors at runtime."""
        scenario = WorkflowTypeErrorScenario(seed=42)
        scenario.setup()
        result = scenario.run_baseline()

        assert result["design_time_detection_rate"] == 0.0
        assert result["runtime_detection_rate"] > 0

    def test_ga_detects_at_design_time(self):
        """GA should detect all errors at design time."""
        scenario = WorkflowTypeErrorScenario(seed=42)
        scenario.setup()
        result = scenario.run_ga()

        assert result["design_time_detection_rate"] == 1.0
        assert result["runtime_detection_rate"] == 0.0

    def test_ga_suggests_coercions(self):
        """GA should suggest coercions where available."""
        scenario = WorkflowTypeErrorScenario(seed=42)
        scenario.setup()
        result = scenario.run_ga()

        assert result["suggestion_accuracy"] == 1.0


class TestCapabilityGapScenario:
    """Tests for Scenario 5: Capability Gap."""

    def test_baseline_wastes_compute(self):
        """Baseline should waste compute on failed workflows."""
        scenario = CapabilityGapScenario(seed=42)
        scenario.setup()
        result = scenario.run_baseline()

        assert result["compute_wasted"] > 0
        assert result["design_time_detection_rate"] == 0.0

    def test_ga_saves_compute(self):
        """GA should save compute by blocking early."""
        scenario = CapabilityGapScenario(seed=42)
        scenario.setup()
        result = scenario.run_ga()

        assert result["compute_saved"] > 0
        assert result["compute_wasted"] == 0
        assert result["design_time_detection_rate"] == 1.0

    def test_ga_identifies_correct_gaps(self):
        """GA should correctly identify missing capabilities."""
        scenario = CapabilityGapScenario(seed=42)
        scenario.setup()
        result = scenario.run_ga()

        assert result["identification_accuracy"] == 1.0


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_result_has_all_fields(self):
        """BenchmarkResult should have all expected fields."""
        result = BenchmarkResult(
            scenario_name="test",
            baseline_metrics={"accuracy": 0.5},
            ga_metrics={"accuracy": 0.9},
            improvement={"accuracy_improvement": 0.4},
            execution_time_ms=100.0,
            metadata={"seed": 42},
        )

        assert result.scenario_name == "test"
        assert result.baseline_metrics["accuracy"] == 0.5
        assert result.ga_metrics["accuracy"] == 0.9
        assert result.improvement["accuracy_improvement"] == 0.4
        assert result.execution_time_ms == 100.0
        assert result.metadata["seed"] == 42


class TestFullBenchmarkRun:
    """Integration tests for full benchmark runs."""

    def test_full_run_returns_benchmark_result(self):
        """Full scenario run should return BenchmarkResult."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=10)
        result = scenario.run(iterations=1)

        assert isinstance(result, BenchmarkResult)
        assert result.scenario_name == "conflicting_sources"
        assert "accuracy" in result.baseline_metrics
        assert "accuracy" in result.ga_metrics
        assert result.execution_time_ms > 0

    def test_multiple_iterations_averages_results(self):
        """Multiple iterations should average numeric results."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=10)
        result = scenario.run(iterations=3)

        # Should still have valid metrics
        assert 0 <= result.baseline_metrics["accuracy"] <= 1
        assert 0 <= result.ga_metrics["accuracy"] <= 1
        assert result.metadata["iterations"] == 3


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_single_test_case(self):
        """Scenarios should handle single test case."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=1)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()

        assert baseline["total_count"] == 1
        assert ga["total_count"] == 1

    def test_single_decision(self):
        """Decision audit should handle single decision."""
        scenario = DecisionAuditScenario(seed=42, num_decisions=1)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()

        # Should not crash and should have valid rates
        assert 0 <= baseline["faithfulness"] <= 1
        assert ga["faithfulness"] == 1.0
