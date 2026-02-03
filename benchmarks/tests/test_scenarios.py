"""
Unit tests for benchmark scenarios.

Tests that:
- Scenarios produce expected metric ranges
- Edge cases are handled properly
- Results are reproducible with same seed
- Edge-type-aware validation works correctly
"""

import pytest

from benchmarks.scenarios import (
    SCENARIOS,
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
        assert 0.30 <= result["accuracy"] <= 0.70

    def test_ga_accuracy_higher_than_baseline(self):
        """GA should significantly outperform baseline."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=100)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()

        assert ga["accuracy"] > baseline["accuracy"]

    def test_ga_always_has_evidence(self):
        """GA results should always include evidence anchors."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=10)
        scenario.setup()
        result = scenario.run_ga()

        assert result["has_evidence"] is True
        assert result["evidence_completeness"] == 1.0

    def test_source_type_diversity(self):
        """Sources should use diverse types (not both primary_api)."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=50)
        scenario.setup()

        source1_types = {case["source1"]["type"] for case in scenario.test_cases}
        source2_types = {case["source2"]["type"] for case in scenario.test_cases}

        # Source 1 should be high-trust types
        assert source1_types <= {"hardware_sensor", "system_of_record", "primary_api"}
        # Source 2 should be low-trust types
        assert source2_types <= {
            "observability_pipeline",
            "derived_inference",
            "human_note",
        }
        # Both pools should have multiple types represented
        assert len(source1_types) > 1
        assert len(source2_types) > 1

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

    def test_coercions_loaded_from_registry(self):
        """Coercions should be loaded from YAML, not hardcoded."""
        from benchmarks.scenarios.workflow_type_error import COERCIONS

        # The canonical registry has these 5 coercions
        assert ("string", "number") in COERCIONS
        assert ("number", "string") in COERCIONS
        assert ("object", "string") in COERCIONS
        assert ("array<object>", "array<string>") in COERCIONS
        assert ("array<any>", "array<object>") in COERCIONS
        # The old buggy key should NOT exist
        assert ("any", "object") not in COERCIONS


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

    def test_uses_real_registry(self):
        """Scenario should use CapabilityRegistry, not hardcoded deps."""
        scenario = CapabilityGapScenario(seed=42)
        assert hasattr(scenario, "registry")
        # Registry should be loaded and have capabilities
        assert scenario.registry.capability_count >= 36

    def test_registry_requires_edges(self, registry):
        """Registry should have the 4 canonical requires edges."""
        # mutate requires checkpoint
        mutate_deps = registry.get_required_capabilities("mutate")
        assert "checkpoint" in mutate_deps

        # send requires checkpoint
        send_deps = registry.get_required_capabilities("send")
        assert "checkpoint" in send_deps

    def test_send_requires_checkpoint(self):
        """send must require checkpoint (was missing in old CAPABILITY_DEPS)."""
        scenario = CapabilityGapScenario(seed=42)
        scenario.setup()

        # Case 2: workflow with send — should detect missing checkpoint AND send
        case_2 = scenario.test_cases[1]  # missing_send
        result = scenario._validate_capabilities(case_2["workflow"])
        missing = set(result["missing_capabilities"])

        assert "send" in missing
        assert "checkpoint" in missing  # Hard requires edge

    def test_mutate_requires_checkpoint(self):
        """mutate must require checkpoint."""
        scenario = CapabilityGapScenario(seed=42)
        scenario.setup()

        # Case 3: workflow with mutate — should detect missing checkpoint AND mutate
        case_3 = scenario.test_cases[2]  # missing_mutation_chain
        result = scenario._validate_capabilities(case_3["workflow"])
        missing = set(result["missing_capabilities"])

        assert "mutate" in missing
        assert "checkpoint" in missing


class TestEdgeTypeAwareness:
    """Tests for multi-edge-type awareness in capability gap detection.

    Beyond just `requires` checking, these tests verify that the
    registry correctly distinguishes between edge types.
    """

    def test_requires_vs_soft_requires(self, registry):
        """Only `requires` edges should be treated as hard dependencies."""
        # `detect` has soft_requires edges to `observe` in the ontology,
        # but these should NOT be returned by get_required_capabilities
        detect_hard_deps = registry.get_required_capabilities("detect")
        # detect has no hard requires — all its edges are soft_requires or enables
        # (the old CAPABILITY_DEPS wrongly had detect -> observe as hard dep)
        assert "observe" not in detect_hard_deps

    def test_conflicts_with_detection(self, registry):
        """Registry should detect conflicting capabilities from ontology."""
        # mutate <-> rollback is a conflicts_with edge in the ontology
        mutate_conflicts = registry.get_conflicting_capabilities("mutate")
        assert "rollback" in mutate_conflicts

        rollback_conflicts = registry.get_conflicting_capabilities("rollback")
        assert "mutate" in rollback_conflicts
        assert "persist" in rollback_conflicts

    def test_alternative_to_awareness(self, registry):
        """Registry should report alternative capabilities from ontology."""
        # search <-> retrieve is an alternative_to edge
        search_alts = registry.get_alternatives("search")
        assert "retrieve" in search_alts

        retrieve_alts = registry.get_alternatives("retrieve")
        assert "search" in retrieve_alts

        # measure <-> predict is an alternative_to edge
        measure_alts = registry.get_alternatives("measure")
        assert "predict" in measure_alts

    def test_precedes_edges(self, registry):
        """Registry should report temporal ordering via precedes edges."""
        # plan -> execute is a precedes edge
        plan_precedes = registry.get_preceding_capabilities("execute")
        assert "plan" in plan_precedes

        # observe -> detect is a precedes edge
        detect_precedes = registry.get_preceding_capabilities("detect")
        assert "observe" in detect_precedes

        # checkpoint -> mutate is a precedes edge
        mutate_precedes = registry.get_preceding_capabilities("mutate")
        assert "checkpoint" in mutate_precedes


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
        assert result.metadata is not None
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
        assert result.metadata is not None
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


class TestAverageMetrics:
    """Tests for the _average_metrics helper in base class."""

    def test_average_numeric_values(self):
        """Should average numeric values across runs."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=10)
        results = [
            {"accuracy": 0.5, "count": 10},
            {"accuracy": 0.6, "count": 10},
            {"accuracy": 0.7, "count": 10},
        ]
        averaged = scenario._average_metrics(results)

        assert averaged["accuracy"] == 0.6  # (0.5 + 0.6 + 0.7) / 3
        assert averaged["count"] == 10

    def test_non_numeric_takes_last_value(self):
        """Non-numeric values should take the last value."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=10)
        results = [
            {"status": "running", "count": 1},
            {"status": "done", "count": 2},
        ]
        averaged = scenario._average_metrics(results)

        assert averaged["status"] == "done"
        assert averaged["count"] == 1.5

    def test_empty_results_returns_empty_dict(self):
        """Empty results list should return empty dict."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=10)
        averaged = scenario._average_metrics([])

        assert averaged == {}


class TestCompareMethod:
    """Tests for the compare() method of each scenario."""

    def test_conflicting_sources_compare(self):
        """ConflictingSourcesScenario.compare should calculate improvement."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=50)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()
        comparison = scenario.compare(baseline, ga)

        assert "accuracy_improvement_absolute" in comparison
        assert "accuracy_improvement_percent" in comparison
        assert "evidence_completeness" in comparison
        assert comparison["accuracy_improvement_absolute"] > 0

    def test_mutation_recovery_compare(self):
        """MutationRecoveryScenario.compare should calculate improvements."""
        scenario = MutationRecoveryScenario(seed=42)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()
        comparison = scenario.compare(baseline, ga)

        assert "recovery_rate_improvement" in comparison
        assert "data_integrity_improvement" in comparison
        assert "lines_saved" in comparison
        assert comparison["recovery_rate_improvement"] == 1.0

    def test_decision_audit_compare(self):
        """DecisionAuditScenario.compare should calculate improvements."""
        scenario = DecisionAuditScenario(seed=42, num_decisions=20)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()
        comparison = scenario.compare(baseline, ga)

        assert "faithfulness_improvement" in comparison
        assert "evidence_coverage_improvement" in comparison
        assert "confabulation_reduction" in comparison

    def test_workflow_type_error_compare(self):
        """WorkflowTypeErrorScenario.compare should calculate improvements."""
        scenario = WorkflowTypeErrorScenario(seed=42)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()
        comparison = scenario.compare(baseline, ga)

        assert "design_time_detection_improvement" in comparison
        assert "runtime_errors_prevented" in comparison
        assert "suggestion_accuracy" in comparison

    def test_capability_gap_compare(self):
        """CapabilityGapScenario.compare should calculate improvements."""
        scenario = CapabilityGapScenario(seed=42)
        scenario.setup()

        baseline = scenario.run_baseline()
        ga = scenario.run_ga()
        comparison = scenario.compare(baseline, ga)

        assert "detection_improvement" in comparison
        assert "compute_savings" in comparison
        assert "identification_accuracy" in comparison


class TestVerboseMode:
    """Tests for verbose output mode."""

    def test_verbose_does_not_crash(self):
        """Running with verbose=True should not crash."""
        scenario = ConflictingSourcesScenario(seed=42, num_cases=5, verbose=True)
        result = scenario.run(iterations=1)

        assert isinstance(result, BenchmarkResult)

    def test_log_only_outputs_when_verbose(self, capsys):
        """log() should only output when verbose=True."""
        scenario_quiet = ConflictingSourcesScenario(seed=42, num_cases=5, verbose=False)
        scenario_quiet.log("test message")
        captured = capsys.readouterr()
        assert "test message" not in captured.out

        scenario_verbose = ConflictingSourcesScenario(
            seed=42, num_cases=5, verbose=True
        )
        scenario_verbose.log("test message")
        captured = capsys.readouterr()
        assert "test message" in captured.out


class TestMutationRecoveryCleanup:
    """Tests for temp file cleanup in MutationRecoveryScenario."""

    def test_temp_dir_created_on_setup(self):
        """Temp directory should be created during setup."""
        scenario = MutationRecoveryScenario(seed=42)
        assert scenario.temp_dir is None

        scenario.setup()
        assert scenario.temp_dir is not None
        assert scenario.temp_dir.exists()

    def test_cleanup_removes_temp_dir(self):
        """_cleanup should remove temp directory."""
        scenario = MutationRecoveryScenario(seed=42)
        scenario.setup()
        temp_dir = scenario.temp_dir
        assert temp_dir is not None

        scenario._cleanup()
        assert not temp_dir.exists()

    def test_cleanup_handles_already_deleted(self):
        """_cleanup should handle already deleted temp dir gracefully."""
        scenario = MutationRecoveryScenario(seed=42)
        scenario.setup()
        temp_dir = scenario.temp_dir
        assert temp_dir is not None

        # Manually delete
        import shutil

        shutil.rmtree(temp_dir)

        # Should not raise
        scenario._cleanup()


class TestBenchmarkResultDefaults:
    """Tests for BenchmarkResult dataclass defaults."""

    def test_metadata_defaults_to_none(self):
        """metadata should default to None if not provided."""
        result = BenchmarkResult(
            scenario_name="test",
            baseline_metrics={},
            ga_metrics={},
            improvement={},
            execution_time_ms=0.0,
        )
        assert result.metadata is None

    def test_all_fields_populated(self):
        """All fields should be accessible when populated."""
        result = BenchmarkResult(
            scenario_name="test",
            baseline_metrics={"a": 1},
            ga_metrics={"b": 2},
            improvement={"c": 3.0},
            execution_time_ms=42.0,
            metadata={"key": "value"},
        )
        assert result.scenario_name == "test"
        assert result.baseline_metrics == {"a": 1}
        assert result.ga_metrics == {"b": 2}
        assert result.improvement == {"c": 3.0}
        assert result.execution_time_ms == 42.0
        assert result.metadata == {"key": "value"}


class TestSetupRequired:
    """Tests verifying setup() must be called before run methods."""

    def test_mutation_recovery_requires_setup_for_baseline(self):
        """run_baseline should fail if setup() not called."""
        scenario = MutationRecoveryScenario(seed=42)
        with pytest.raises(RuntimeError, match="setup\\(\\) must be called"):
            scenario.run_baseline()

    def test_mutation_recovery_requires_setup_for_ga(self):
        """run_ga should fail if setup() not called."""
        scenario = MutationRecoveryScenario(seed=42)
        with pytest.raises(RuntimeError, match="setup\\(\\) must be called"):
            scenario.run_ga()
