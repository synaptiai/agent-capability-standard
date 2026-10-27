"""Tests for the Workflow Execution Engine (TD-006, Issue #65).

Covers:
- Workflow loading from YAML catalog
- Step parsing with bindings, gates, failure_modes
- Validation mode tracing and conformance reporting
- Binding type mismatch detection
- CheckpointTracker integration for mutation steps
- Edge constraint validation
- Error handling for invalid definitions
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from grounded_agency.errors import ErrorCode, Severity, ValidationError
from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.workflows.engine import (
    SAFETY_KEYS,
    BindingError,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowStep,
)
from grounded_agency.workflows.tracer import WorkflowTracer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ONTOLOGY_PATH = Path(__file__).parent.parent / "schemas" / "capability_ontology.yaml"
CATALOG_PATH = Path(__file__).parent.parent / "schemas" / "workflow_catalog.yaml"


@pytest.fixture
def engine() -> WorkflowEngine:
    """Create a WorkflowEngine loaded with the real catalog."""
    eng = WorkflowEngine(ONTOLOGY_PATH)
    eng.load_catalog(CATALOG_PATH)
    return eng


@pytest.fixture
def engine_with_tracker(tmp_path: Path) -> WorkflowEngine:
    """Create a WorkflowEngine with a CheckpointTracker."""
    tracker = CheckpointTracker(checkpoint_dir=str(tmp_path / ".checkpoints"))
    eng = WorkflowEngine(ONTOLOGY_PATH, checkpoint_tracker=tracker)
    eng.load_catalog(CATALOG_PATH)
    return eng


def _add_parsed(
    eng: WorkflowEngine, name: str, steps: list[dict[str, Any]]
) -> WorkflowDefinition:
    """Add a workflow parsed from catalog data, as load_catalog would."""
    wf = WorkflowDefinition.from_dict(
        name,
        {"goal": "g", "risk": "high", "spec_version": "1.1", "steps": steps},
        eng.registry,
    )
    eng.add_workflow(wf)
    return wf


# ---------------------------------------------------------------------------
# AC1: Workflow engine MVP loads workflow definitions
# ---------------------------------------------------------------------------


class TestWorkflowLoading:
    """AC1: Workflow engine loads definitions from workflow_catalog.yaml."""

    def test_loads_all_12_workflows(self, engine: WorkflowEngine) -> None:
        workflows = engine.list_workflows()
        assert len(workflows) == 12

    def test_known_workflow_names(self, engine: WorkflowEngine) -> None:
        expected = {
            "monitor_and_replan",
            "clarify_intent",
            "debug_code_change",
            "world_model_build",
            "capability_gap_analysis",
            "digital_twin_sync_loop",
            "digital_twin_bootstrap",
            "rag_pipeline",
            "security_assessment",
            "multi_agent_orchestration",
            "data_quality_pipeline",
            "model_deployment",
        }
        actual = set(engine.list_workflows())
        assert actual == expected

    def test_workflow_has_steps(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        assert len(wf.steps) > 0

    def test_workflow_goal_parsed(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        assert "diagnose" in wf.goal.lower() or "fix" in wf.goal.lower()

    def test_workflow_risk_parsed(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        assert wf.risk == "medium"

    def test_workflow_success_criteria(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        assert len(wf.success) > 0

    def test_nonexistent_workflow_returns_none(self, engine: WorkflowEngine) -> None:
        assert engine.get_workflow("does_not_exist") is None

    def test_load_catalog_returns_count(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        count = eng.load_catalog(CATALOG_PATH)
        assert count == 12

    def test_workflow_inputs_parsed(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("monitor_and_replan")
        assert wf is not None
        assert "plan" in wf.inputs


class TestStepParsing:
    """Verify step fields are parsed correctly."""

    def test_step_capability(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        assert wf.steps[0].capability == "observe"

    def test_step_store_as(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        assert wf.steps[0].store_as == "observe_out"

    def test_step_mutation_flag(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        # checkpoint step has mutation: true
        checkpoint_step = next(s for s in wf.steps if s.capability == "checkpoint")
        assert checkpoint_step.mutation is True

    def test_step_requires_checkpoint(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        execute_step = next(s for s in wf.steps if s.capability == "execute")
        assert execute_step.requires_checkpoint is True

    def test_step_timeout(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        execute_step = next(s for s in wf.steps if s.capability == "execute")
        assert execute_step.timeout == "5m"

    def test_step_retry_policy(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        verify_step = next(s for s in wf.steps if s.capability == "verify")
        assert verify_step.retry is not None
        assert verify_step.retry.max == 3
        assert verify_step.retry.backoff == "exponential"

    def test_step_failure_modes(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        observe_step = wf.steps[0]
        assert len(observe_step.failure_modes) > 0
        fm = observe_step.failure_modes[0]
        assert fm.action == "request_more_context"

    def test_step_gates_parsed(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("monitor_and_replan")
        assert wf is not None
        # detect step has gates
        detect_step = next(s for s in wf.steps if s.capability == "detect")
        assert len(detect_step.gates) > 0
        gate = detect_step.gates[0]
        assert gate.action in ("skip", "stop")

    def test_step_domain(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        attribute_step = next(s for s in wf.steps if s.capability == "attribute")
        assert attribute_step.domain == "dependencies"

    def test_step_input_bindings(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("monitor_and_replan")
        assert wf is not None
        compare_step = next(s for s in wf.steps if s.capability == "compare")
        assert len(compare_step.input_bindings) > 0

    def test_mutation_steps_property(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        mutation_steps = wf.mutation_steps
        assert len(mutation_steps) >= 2  # checkpoint, execute, rollback

    def test_checkpoint_required_steps_property(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        cp_steps = wf.checkpoint_required_steps
        assert any(s.capability == "execute" for s in cp_steps)

    def test_store_as_names_property(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        names = wf.store_as_names
        assert "observe_out" in names
        assert "execute_out" in names


# ---------------------------------------------------------------------------
# AC1: Capability validation
# ---------------------------------------------------------------------------


class TestCapabilityValidation:
    """Verify that step capabilities are validated against ontology."""

    def test_all_real_workflows_have_valid_capabilities(
        self, engine: WorkflowEngine
    ) -> None:
        for name in engine.list_workflows():
            errors = engine.validate_capabilities(name)
            # Filter out flag-downgrade warnings — real catalog workflows
            # may legitimately downgrade flags (e.g., audit used as
            # non-mutating append-only). Only structural errors (capability
            # not found in ontology) should fail the build.
            structural_errors = [e for e in errors if "not found in ontology" in e]
            assert structural_errors == [], (
                f"Workflow {name} has unknown capabilities: {structural_errors}"
            )

    def test_invalid_capability_detected(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        # Manually add a workflow with bad capability
        wf = WorkflowDefinition(
            name="test_bad",
            goal="test",
            risk="low",
            steps=[
                WorkflowStep(capability="nonexistent_cap", purpose="test"),
            ],
        )
        eng._workflows["test_bad"] = wf
        errors = eng.validate_capabilities("test_bad")
        assert len(errors) == 1
        assert "nonexistent_cap" in errors[0]


# ---------------------------------------------------------------------------
# AC2: Validation mode tracing
# ---------------------------------------------------------------------------


class TestValidationModeTracing:
    """AC2: Traces agent actions and reports workflow pattern conformance."""

    def test_perfect_trace_scores_1(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("rag_pipeline")
        assert wf is not None

        tracer = WorkflowTracer(engine, "rag_pipeline")
        for step in wf.steps:
            tracer.record_action(
                step.capability,
                domain=step.domain,
            )

        report = tracer.get_report()
        assert report.conformance_score == 1.0
        assert len(report.pending_steps) == 0

    def test_partial_trace(self, engine: WorkflowEngine) -> None:
        tracer = WorkflowTracer(engine, "debug_code_change")
        # Only record first two steps
        tracer.record_action("observe")
        tracer.record_action("search")

        report = tracer.get_report()
        assert report.conformance_score < 1.0
        assert len(report.pending_steps) > 0
        assert len(report.matched_steps) == 2

    def test_out_of_order_detected(self, engine: WorkflowEngine) -> None:
        tracer = WorkflowTracer(engine, "debug_code_change")
        # Skip observe, start with search (step 1 before step 0)
        tracer.record_action("search")
        tracer.record_action("observe")

        report = tracer.get_report()
        assert len(report.out_of_order_steps) > 0

    def test_extra_actions_tracked(self, engine: WorkflowEngine) -> None:
        tracer = WorkflowTracer(engine, "rag_pipeline")
        tracer.record_action("observe")  # Not in rag_pipeline
        tracer.record_action("retrieve")  # First real step

        report = tracer.get_report()
        assert len(report.extra_actions) >= 1

    def test_skipped_step_counted(self, engine: WorkflowEngine) -> None:
        tracer = WorkflowTracer(engine, "debug_code_change")
        tracer.record_action("observe")
        tracer.mark_step_skipped(1, reason="gate_condition")  # Skip search
        # attribute step has domain: "dependencies", must match it
        tracer.record_action("attribute", domain="dependencies")

        report = tracer.get_report()
        assert 1 in report.skipped_steps
        assert len(report.matched_steps) >= 2

    def test_invalid_workflow_raises(self, engine: WorkflowEngine) -> None:
        with pytest.raises(ValueError, match="Workflow not found"):
            WorkflowTracer(engine, "nonexistent")

    def test_report_violations_for_checkpoint_missing(
        self, engine: WorkflowEngine
    ) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None

        tracer = WorkflowTracer(engine, "debug_code_change")
        # Record observe through plan, skip checkpoint, do execute
        for step in wf.steps:
            if step.capability == "checkpoint":
                continue  # Skip checkpoint
            tracer.record_action(step.capability, domain=step.domain)

        report = tracer.get_report()
        # Should have violation about execute without checkpoint
        checkpoint_violations = [
            v for v in report.violations if "checkpoint" in v.lower()
        ]
        assert len(checkpoint_violations) > 0

    def test_conformance_report_properties(self, engine: WorkflowEngine) -> None:
        tracer = WorkflowTracer(engine, "debug_code_change")
        report = tracer.get_report()
        assert report.workflow_name == "debug_code_change"
        assert report.total_steps > 0
        assert isinstance(report.conformance_score, float)


# ---------------------------------------------------------------------------
# AC3: Binding type mismatch detection
# ---------------------------------------------------------------------------


class TestBindingValidation:
    """AC3: Binding mismatches between steps detected and reported."""

    def test_real_workflows_bindings_valid(self, engine: WorkflowEngine) -> None:
        """All real workflows should have resolvable bindings."""
        for name in engine.list_workflows():
            errors = engine.validate_bindings(name)
            # Workflows with input bindings referencing workflow-level inputs
            # should resolve correctly; no workflow should be "not found"
            assert all(e.error_type != "workflow_not_found" for e in errors), (
                f"Workflow {name}: {errors}"
            )

    def test_unresolved_ref_detected(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_bad_binding",
            goal="test",
            risk="low",
            steps=[
                WorkflowStep(
                    capability="observe",
                    purpose="test",
                    store_as="obs_out",
                ),
                WorkflowStep(
                    capability="search",
                    purpose="test",
                    input_bindings={"query": "${nonexistent_ref}"},
                ),
            ],
        )
        eng._workflows["test_bad_binding"] = wf
        errors = eng.validate_bindings("test_bad_binding")
        assert len(errors) == 1
        assert errors[0].error_type == "unresolved_ref"
        assert "nonexistent_ref" in errors[0].message

    def test_valid_ref_resolves(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_good_binding",
            goal="test",
            risk="low",
            steps=[
                WorkflowStep(
                    capability="observe",
                    purpose="test",
                    store_as="obs_out",
                ),
                WorkflowStep(
                    capability="search",
                    purpose="test",
                    input_bindings={"query": "${obs_out}"},
                ),
            ],
        )
        eng._workflows["test_good_binding"] = wf
        errors = eng.validate_bindings("test_good_binding")
        assert len(errors) == 0

    def test_workflow_input_ref_resolves(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_input_binding",
            goal="test",
            risk="low",
            inputs={"user_query": {"type": "string"}},
            steps=[
                WorkflowStep(
                    capability="search",
                    purpose="test",
                    input_bindings={"query": "${user_query}"},
                ),
            ],
        )
        eng._workflows["test_input_binding"] = wf
        errors = eng.validate_bindings("test_input_binding")
        assert len(errors) == 0

    def test_nested_binding_ref(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_nested",
            goal="test",
            risk="low",
            steps=[
                WorkflowStep(
                    capability="observe",
                    purpose="test",
                    store_as="obs_out",
                ),
                WorkflowStep(
                    capability="search",
                    purpose="test",
                    input_bindings={
                        "filters": {
                            "scope": "${obs_out.observation}",
                            "items": ["${obs_out.confidence}"],
                        }
                    },
                ),
            ],
        )
        eng._workflows["test_nested"] = wf
        errors = eng.validate_bindings("test_nested")
        assert len(errors) == 0

    def test_path_outside_producer_schema_detected(self) -> None:
        """A path the producer's output schema lacks is B201."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.add_workflow(
            WorkflowDefinition(
                name="test_bad_path",
                goal="test",
                risk="low",
                steps=[
                    WorkflowStep(capability="observe", purpose="t", store_as="obs"),
                    WorkflowStep(
                        capability="search",
                        purpose="t",
                        store_as="found",
                        input_bindings={"query": "${obs.no_such_field}"},
                    ),
                ],
            )
        )
        errors = eng.validate_bindings("test_bad_path")
        assert [
            (e.error_code, e.error_type, e.binding_key, e.reference) for e in errors
        ] == [
            (
                ErrorCode.INVALID_BINDING_PATH,
                "invalid_path",
                "query",
                "obs.no_such_field",
            )
        ]

    def test_nonexistent_workflow_binding_check(self, engine: WorkflowEngine) -> None:
        errors = engine.validate_bindings("nonexistent")
        assert len(errors) == 1
        assert errors[0].error_type == "workflow_not_found"

    def test_binding_error_fields(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_error_fields",
            goal="test",
            risk="low",
            steps=[
                WorkflowStep(
                    capability="search",
                    purpose="test",
                    input_bindings={"query": "${missing_ref}"},
                ),
            ],
        )
        eng._workflows["test_error_fields"] = wf
        errors = eng.validate_bindings("test_error_fields")
        assert len(errors) == 1
        err = errors[0]
        assert err.workflow_name == "test_error_fields"
        assert err.step_index == 0
        assert err.step_capability == "search"
        assert err.binding_key == "query"
        assert err.reference == "missing_ref"


# ---------------------------------------------------------------------------
# AC4: CheckpointTracker integration
# ---------------------------------------------------------------------------


class TestCheckpointIntegration:
    """AC4: Auto-creates checkpoints before mutation steps."""

    def test_auto_checkpoint_for_mutation_step(
        self, engine_with_tracker: WorkflowEngine
    ) -> None:
        tracker = engine_with_tracker.checkpoint_tracker
        assert tracker is not None

        wf = engine_with_tracker.get_workflow("debug_code_change")
        assert wf is not None

        execute_step = next(s for s in wf.steps if s.capability == "execute")
        cp_id = engine_with_tracker.ensure_checkpoint_before_step(
            execute_step, "debug_code_change"
        )
        assert cp_id is not None
        assert tracker.has_valid_checkpoint()

    def test_no_checkpoint_for_readonly_step(
        self, engine_with_tracker: WorkflowEngine
    ) -> None:
        wf = engine_with_tracker.get_workflow("debug_code_change")
        assert wf is not None

        observe_step = wf.steps[0]
        assert observe_step.capability == "observe"
        cp_id = engine_with_tracker.ensure_checkpoint_before_step(
            observe_step, "debug_code_change"
        )
        assert cp_id is None

    def test_existing_checkpoint_reused(
        self, engine_with_tracker: WorkflowEngine
    ) -> None:
        tracker = engine_with_tracker.checkpoint_tracker
        assert tracker is not None

        # Pre-create a checkpoint
        existing_id = tracker.create_checkpoint(scope=["*"], reason="Pre-existing")

        wf = engine_with_tracker.get_workflow("debug_code_change")
        assert wf is not None
        execute_step = next(s for s in wf.steps if s.capability == "execute")

        cp_id = engine_with_tracker.ensure_checkpoint_before_step(
            execute_step, "debug_code_change"
        )
        # Should reuse existing checkpoint
        assert cp_id == existing_id

    def test_no_tracker_returns_none(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        execute_step = next(s for s in wf.steps if s.capability == "execute")
        cp_id = engine.ensure_checkpoint_before_step(execute_step, "debug_code_change")
        assert cp_id is None

    def test_checkpoint_reason_includes_context(
        self, engine_with_tracker: WorkflowEngine
    ) -> None:
        tracker = engine_with_tracker.checkpoint_tracker
        assert tracker is not None

        wf = engine_with_tracker.get_workflow("debug_code_change")
        assert wf is not None
        execute_step = next(s for s in wf.steps if s.capability == "execute")

        engine_with_tracker.ensure_checkpoint_before_step(
            execute_step, "debug_code_change"
        )

        cp = tracker.get_active_checkpoint()
        assert cp is not None
        assert "execute" in cp.reason
        assert "debug_code_change" in cp.reason


# ---------------------------------------------------------------------------
# Edge constraint validation
# ---------------------------------------------------------------------------


class TestEdgeConstraintValidation:
    """Validate ontology edge constraints within workflows."""

    def test_validate_edge_constraints_runs(self, engine: WorkflowEngine) -> None:
        # Should run without exception on real workflows
        for name in engine.list_workflows():
            errors = engine.validate_edge_constraints(name)
            assert isinstance(errors, list)

    def test_all_workflows_pass_requires_constraints(
        self, engine: WorkflowEngine
    ) -> None:
        """All 12 production workflows must satisfy 'requires' edges.

        'precedes' and 'conflicts_with' violations are separate from the
        hard prerequisite contract — this test focuses on 'requires' only.
        """
        for name in engine.list_workflows():
            errors = engine.validate_edge_constraints(name)
            requires_errors = [e for e in errors if ": requires '" in e]
            assert requires_errors == [], (
                f"Workflow {name} has unsatisfied requires edges: {requires_errors}"
            )

    def test_nonexistent_workflow_edge_check(self, engine: WorkflowEngine) -> None:
        errors = engine.validate_edge_constraints("nonexistent")
        assert len(errors) == 1
        assert "not found" in errors[0]


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------


class TestValidateAll:
    """Test the batch validation method."""

    def test_validate_all_returns_dict(self, engine: WorkflowEngine) -> None:
        results = engine.validate_all()
        assert isinstance(results, dict)

    def test_validate_all_keys_are_workflow_names(self, engine: WorkflowEngine) -> None:
        results = engine.validate_all()
        known = set(engine.list_workflows())
        for key in results:
            assert key in known


# ---------------------------------------------------------------------------
# validate_all_structured
# ---------------------------------------------------------------------------


class TestValidateAllStructured:
    """Test the structured validation method that returns ValidationError objects."""

    def test_returns_dict_of_validation_errors(self, engine: WorkflowEngine) -> None:
        results = engine.validate_all_structured()
        assert isinstance(results, dict)
        for wf_name, errors in results.items():
            assert isinstance(wf_name, str)
            assert isinstance(errors, list)
            for err in errors:
                assert isinstance(err, ValidationError)
                assert isinstance(err.code, ErrorCode)

    def test_unknown_capability_maps_to_v101(self) -> None:
        """An unknown capability in a workflow should produce V101."""
        engine = WorkflowEngine(ONTOLOGY_PATH)
        engine._workflows["bad_wf"] = WorkflowDefinition(
            name="bad_wf",
            goal="test",
            risk="low",
            steps=[WorkflowStep(capability="nonexistent_cap", purpose="test")],
        )
        results = engine.validate_all_structured()
        assert "bad_wf" in results
        codes = {err.code for err in results["bad_wf"]}
        assert ErrorCode.UNKNOWN_CAPABILITY in codes

    def test_safety_flag_downgrade_is_a_w602_warning(self) -> None:
        """A step that downgrades ontology safety flags is W602: a warning,
        since the ontology value applies regardless (STANDARD v1.1 §5.2)."""
        engine = WorkflowEngine(ONTOLOGY_PATH)
        _add_parsed(
            engine,
            "downgrade_wf",
            [
                {"capability": "plan", "purpose": "p", "store_as": "p"},
                {"capability": "checkpoint", "purpose": "save", "store_as": "cp"},
                # mutate has mutation=true in the ontology; downgrade it
                {
                    "capability": "mutate",
                    "purpose": "m",
                    "store_as": "m",
                    "mutation": False,
                },
            ],
        )
        assert "downgrade_wf" not in engine.validate_all_structured()
        report = engine.validate_report("downgrade_wf")
        downgrades = [d for d in report if d.code is ErrorCode.SAFETY_FLAG_DOWNGRADE]
        assert [d.location["field"] for d in downgrades] == ["mutation"]
        assert downgrades[0].severity is Severity.WARNING

    def test_structured_covers_same_workflows_as_plain(
        self, engine: WorkflowEngine
    ) -> None:
        """validate_all_structured() should flag the same workflows as validate_all()."""
        plain = engine.validate_all()
        structured = engine.validate_all_structured()
        assert set(structured.keys()) == set(plain.keys())


# ---------------------------------------------------------------------------
# BindingError.error_code
# ---------------------------------------------------------------------------


class TestBindingErrorCode:
    """Test the BindingError.error_code property mapping."""

    def test_unresolved_ref_maps_to_missing_producer(self) -> None:
        """An unknown store is a missing producer (B202), not a bad path."""
        err = BindingError(
            workflow_name="w",
            step_index=0,
            step_capability="retrieve",
            binding_key="k",
            reference="r",
            error_type="unresolved_ref",
            message="ref not found",
        )
        assert err.error_code == ErrorCode.MISSING_PRODUCER

    def test_explicit_code_wins(self) -> None:
        err = BindingError(
            workflow_name="w",
            step_index=0,
            step_capability="retrieve",
            binding_key="k",
            reference="r",
            error_type="unresolved_ref",
            message="ambiguous",
            code=ErrorCode.AMBIGUOUS_TYPE,
        )
        assert err.error_code == ErrorCode.AMBIGUOUS_TYPE

    def test_type_mismatch_maps_to_type_mismatch(self) -> None:
        err = BindingError(
            workflow_name="w",
            step_index=0,
            step_capability="retrieve",
            binding_key="k",
            reference="r",
            error_type="type_mismatch",
            message="type mismatch",
        )
        assert err.error_code == ErrorCode.TYPE_MISMATCH

    def test_missing_store_as_maps_to_missing_producer(self) -> None:
        err = BindingError(
            workflow_name="w",
            step_index=0,
            step_capability="retrieve",
            binding_key="k",
            reference="r",
            error_type="missing_store_as",
            message="missing store",
        )
        assert err.error_code == ErrorCode.MISSING_PRODUCER

    def test_unknown_error_type_falls_back_to_invalid_binding_path(self) -> None:
        err = BindingError(
            workflow_name="w",
            step_index=0,
            step_capability="retrieve",
            binding_key="k",
            reference="r",
            error_type="some_future_type",
            message="unknown",
        )
        assert err.error_code == ErrorCode.INVALID_BINDING_PATH


# ---------------------------------------------------------------------------
# WorkflowStep.from_dict
# ---------------------------------------------------------------------------


class TestStepFromDict:
    """Test WorkflowStep.from_dict edge cases."""

    def test_minimal_step(self) -> None:
        step = WorkflowStep.from_dict({"capability": "observe"})
        assert step.capability == "observe"
        assert step.risk == "low"
        assert step.mutation is False
        assert step.gates == []
        assert step.failure_modes == []

    def test_full_step(self) -> None:
        data: dict[str, Any] = {
            "capability": "execute",
            "purpose": "Apply fix",
            "risk": "high",
            "mutation": True,
            "requires_checkpoint": True,
            "requires_approval": False,
            "timeout": "5m",
            "retry": {"max": 3, "backoff": "exponential"},
            "store_as": "exec_out",
            "domain": "code",
            "input_bindings": {"plan": "${plan_out}"},
            "gates": [{"when": "condition", "action": "skip", "message": "msg"}],
            "failure_modes": [
                {"condition": "error", "action": "rollback", "recovery": "revert"}
            ],
        }
        step = WorkflowStep.from_dict(data)
        assert step.capability == "execute"
        assert step.risk == "high"
        assert step.mutation is True
        assert step.requires_checkpoint is True
        assert step.timeout == "5m"
        assert step.retry is not None
        assert step.retry.max == 3
        assert step.retry.backoff == "exponential"
        assert step.domain == "code"
        assert len(step.gates) == 1
        assert step.gates[0].action == "skip"
        assert len(step.failure_modes) == 1
        assert step.failure_modes[0].action == "rollback"


# ---------------------------------------------------------------------------
# WorkflowDefinition.from_dict
# ---------------------------------------------------------------------------


class TestWorkflowDefinitionFromDict:
    """Test WorkflowDefinition.from_dict."""

    def test_minimal_definition(self) -> None:
        wf = WorkflowDefinition.from_dict(
            "test_wf",
            {
                "goal": "Test goal",
                "risk": "low",
                "steps": [{"capability": "observe"}],
            },
        )
        assert wf.name == "test_wf"
        assert wf.goal == "Test goal"
        assert len(wf.steps) == 1

    def test_empty_steps_list(self) -> None:
        wf = WorkflowDefinition.from_dict(
            "empty",
            {"goal": "Empty", "risk": "low", "steps": []},
        )
        assert len(wf.steps) == 0


class TestCatalogData:
    """Definitions keep their source for validation; definitions built in
    code are validated as to_dict() renders them."""

    def test_to_dict_validates_like_the_source(self, engine: WorkflowEngine) -> None:
        """Re-rendering every catalog workflow from its typed fields gives
        the validator nothing new to say."""
        rebuilt = WorkflowEngine(ONTOLOGY_PATH)
        for name in engine.list_workflows():
            wf = engine.get_workflow(name)
            assert wf is not None
            data = wf.to_dict()
            rebuilt.add_workflow(WorkflowDefinition.from_dict(name, data))
            assert data["spec_version"] == "1.1.0"
        assert rebuilt.validate_report() == []

    def test_step_round_trip_keeps_every_field(self) -> None:
        data = {
            "capability": "verify",
            "purpose": "p",
            "store_as": "v",
            "risk": "medium",
            "mutation": False,
            "requires_checkpoint": False,
            "requires_approval": False,
            "timeout": "5m",
            "retry": {"max": 3, "backoff": "exponential"},
            "input_bindings": {"target": "${x}", "conditions": ["c"]},
            "condition": "${x.ok} == true",
            "skip_if_false": False,
            "parallel_group": "g",
            "join": "all_complete",
            "gates": [
                {"when": "${v.passed} == false", "phase": "after", "action": "stop"}
            ],
            "failure_modes": [
                {
                    "condition": "Verdict == FAIL",
                    "action": "rollback",
                    "when": "${v.passed} == false",
                    "recovery": {"goto_step": "plan", "max_loops": 2},
                }
            ],
            "x-vendor": {"k": 1},
        }
        assert WorkflowStep.from_dict(data).to_dict() == data

    def test_workflow_extra_fields_survive(self) -> None:
        data = {
            "goal": "g",
            "risk": "low",
            "steps": [],
            "domain": "healthcare",
            "x-owner": "team",
        }
        wf = WorkflowDefinition.from_dict("w", data)
        assert wf.extra == {"domain": "healthcare", "x-owner": "team"}
        assert wf.to_dict() == data

    def test_header_version_is_carried_into_validation(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog.yaml"
        catalog.write_text(
            "# Standard version: 1.1.0\n"
            "w:\n  goal: g\n  risk: low\n  steps:\n"
            "  - capability: observe\n    purpose: p\n    store_as: o\n"
        )
        eng = WorkflowEngine(ONTOLOGY_PATH)
        assert eng.load_catalog(catalog) == 1
        wf = eng.get_workflow("w")
        assert wf is not None
        assert wf.spec_version == "1.1.0"
        assert wf.validation_data()["spec_version"] == "1.1.0"
        assert eng.validate_report() == []

    def test_unsupported_header_version_is_v109(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog.yaml"
        catalog.write_text(
            "# Standard version: 9.0.0\n"
            "w:\n  goal: g\n  risk: low\n  steps:\n"
            "  - capability: observe\n    purpose: p\n    store_as: o\n"
        )
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.load_catalog(catalog)
        assert [d.code for d in eng.validate_report()] == [
            ErrorCode.UNSUPPORTED_SPEC_VERSION
        ]

    def test_load_skips_vendor_and_rejects_non_mapping(self, tmp_path: Path) -> None:
        good = tmp_path / "good.yaml"
        good.write_text(
            "x-notes: {a: 1}\n"
            "w:\n  goal: g\n  risk: low\n  spec_version: '1.1'\n  steps: []\n"
        )
        eng = WorkflowEngine(ONTOLOGY_PATH)
        assert eng.load_catalog(good) == 1
        assert eng.list_workflows() == ["w"]

        bad = tmp_path / "bad.yaml"
        bad.write_text("- just\n- a list\n")
        with pytest.raises(ValueError, match="must be a mapping"):
            eng.load_catalog(bad)

    def test_malformed_entries_are_left_to_the_validator(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog.yaml"
        catalog.write_text(
            "w:\n  goal: g\n  risk: low\n  spec_version: '1.1'\n  steps:\n"
            "  - capability: observe\n    purpose: p\n    store_as: o\n"
            "    gates: [not-a-mapping]\n"
            "  - just a string\n"
        )
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.load_catalog(catalog)
        wf = eng.get_workflow("w")
        assert wf is not None
        assert len(wf.steps) == 1 and wf.steps[0].gates == []
        codes = {d.code for d in eng.validate_report("w")}
        assert codes == {ErrorCode.SCHEMA_VALIDATION_FAILED, ErrorCode.INVALID_STEP}

    def test_validate_report_unknown_workflow_raises(
        self, engine: WorkflowEngine
    ) -> None:
        with pytest.raises(KeyError, match="nonexistent"):
            engine.validate_report("nonexistent")


class TestValidationSeesEdits:
    """Validation reflects the typed fields once they differ from what was
    parsed; it never reports a stale source."""

    def test_replace_drops_the_source(self, engine: WorkflowEngine) -> None:
        import dataclasses

        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        copy = dataclasses.replace(
            wf,
            name="dcc2",
            steps=[*wf.steps[:1], WorkflowStep(capability="nonexistent", purpose="x")],
        )
        assert copy.source is None
        engine.add_workflow(copy)
        assert any("nonexistent" in e for e in engine.validate_capabilities("dcc2"))

    def test_in_place_edits_are_seen(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None
        wf.steps.append(WorkflowStep(capability="bogus", purpose="x", store_as="b"))
        assert any("bogus" in e for e in engine.validate_capabilities(wf.name))

    def test_edited_bindings_are_seen(self, engine: WorkflowEngine) -> None:
        wf = engine.get_workflow("clarify_intent")
        assert wf is not None
        step = next(s for s in wf.steps if s.input_bindings)
        key = next(iter(step.input_bindings))
        step.input_bindings[key] = "${no_such_store}"
        errors = engine.validate_bindings(wf.name)
        assert [e.reference for e in errors] == ["no_such_store"]

    def test_unedited_definition_validates_its_source(
        self, engine: WorkflowEngine
    ) -> None:
        """The catalog's header version is carried over as spec_version."""
        wf = engine.get_workflow("debug_code_change")
        assert wf is not None and wf.source is not None
        assert "spec_version" not in wf.source
        assert wf.validation_data() == {**wf.source, "spec_version": "1.1.0"}


class TestMalformedCatalogs:
    """Malformed shapes load without crashing and get the same diagnostics
    from the engine as from tools/validate_workflows.py."""

    HEADER = "# Standard version: 1.1.0\n"

    @pytest.mark.parametrize(
        "body, code",
        [
            ("  - capability: [observe]\n    purpose: p\n", "V103"),
            ("  - capability: {a: 1}\n    purpose: p\n", "V103"),
            (
                "  - capability: observe\n    purpose: p\n    store_as: o\n"
                "    gates: 5\n",
                "S303",
            ),
            (
                "  - capability: observe\n    purpose: p\n    store_as: o\n"
                "    failure_modes: 5\n",
                "S303",
            ),
            (
                "  - capability: observe\n    purpose: p\n    store_as: o\n"
                "    gates:\n    - when: null\n      action: stop\n",
                "S303",
            ),
        ],
        ids=["capability-list", "capability-map", "gates-int", "fm-int", "when-null"],
    )
    def test_malformed_step_shapes(self, tmp_path: Path, body: str, code: str) -> None:
        catalog = tmp_path / "c.yaml"
        catalog.write_text(f"{self.HEADER}w:\n  goal: g\n  risk: low\n  steps:\n{body}")
        eng = WorkflowEngine(ONTOLOGY_PATH)
        assert eng.load_catalog(catalog) == 1
        assert code in {d.code.value for d in eng.validate_report()}

    def test_steps_not_a_list(self, tmp_path: Path) -> None:
        catalog = tmp_path / "c.yaml"
        catalog.write_text(f"{self.HEADER}w:\n  goal: g\n  risk: low\n  steps: 5\n")
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.load_catalog(catalog)
        wf = eng.get_workflow("w")
        assert wf is not None and wf.steps == []
        assert [d.code for d in eng.validate_report()] == [
            ErrorCode.SCHEMA_VALIDATION_FAILED
        ]

    def test_unloadable_entries_are_still_validated(self, tmp_path: Path) -> None:
        catalog = tmp_path / "c.yaml"
        catalog.write_text(
            f"{self.HEADER}not_a_map: [1, 2]\nno_steps:\n  goal: g\n  risk: low\n"
        )
        eng = WorkflowEngine(ONTOLOGY_PATH)
        assert eng.load_catalog(catalog) == 0
        assert eng.list_workflows() == []
        results = eng.validate_all_structured()
        assert {n: [e.code.value for e in errs] for n, errs in results.items()} == {
            "not_a_map": ["S303"],
            "no_steps": ["S304"],
        }
        assert eng.validate_report("no_steps")[0].code is (
            ErrorCode.MISSING_REQUIRED_FIELD
        )

    @pytest.mark.parametrize(
        "fixture",
        sorted(
            p.name
            for p in (Path(__file__).parent / "fixtures").glob(
                "*.workflow_catalog.yaml"
            )
        ),
    )
    def test_engine_matches_the_file_validator(self, fixture: str) -> None:
        from collections import Counter

        from grounded_agency import _core

        path = Path(__file__).parent / "fixtures" / fixture
        root = ONTOLOGY_PATH.parent.parent
        expected = Counter(
            d["code"]
            for d in _core.validate_catalog(path, ONTOLOGY_PATH, root)["diagnostics"]
        )
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.load_catalog(path)
        assert Counter(d.code.value for d in eng.validate_report()) == expected

    def test_catalogs_with_different_headers(self, tmp_path: Path) -> None:
        old = tmp_path / "old.yaml"
        old.write_text(
            "# Standard version: 1.0.0\n"
            "a:\n  goal: g\n  risk: low\n  steps:\n"
            "  - capability: observe\n    purpose: p\n    store_as: o\n"
        )
        future = tmp_path / "future.yaml"
        future.write_text(
            "# Standard version: 3.0.0\n"
            "b:\n  goal: g\n  risk: low\n  steps:\n"
            "  - capability: observe\n    purpose: p\n    store_as: o\n"
        )
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.load_catalog(old)
        eng.load_catalog(future)
        report = eng.validate_report()
        assert [(d.code.value, d.location["workflow"]) for d in report] == [
            ("V109", "b")
        ]


class TestEngineMisc:
    def test_binding_error_types_for_b203(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.load_catalog(
            Path(__file__).parent
            / "fixtures"
            / "fail_type_mismatch_binding.workflow_catalog.yaml"
        )
        mismatches = [
            e
            for name in eng.list_workflows()
            for e in eng.validate_bindings(name)
            if e.error_code is ErrorCode.TYPE_MISMATCH
        ]
        assert mismatches
        for e in mismatches:
            assert e.expected_type and e.actual_type
            assert e.expected_type != e.actual_type

    def test_vendor_names_are_rejected(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        with pytest.raises(ValueError, match="vendor data"):
            eng.add_workflow(
                WorkflowDefinition(name="x-bad", goal="g", risk="low", steps=[])
            )

    def test_registry_refuses_a_harmful_override(self) -> None:
        from grounded_agency.capabilities.registry import CapabilityNode

        with pytest.raises(ValueError, match="mutation_overridable"):
            CapabilityNode.from_dict(
                {
                    "id": "mutate",
                    "layer": "EXECUTE",
                    "risk": "high",
                    "mutation": True,
                    "mutation_overridable": True,
                }
            )

    def test_null_gate_fields_stay_empty(self) -> None:
        step = WorkflowStep.from_dict(
            {
                "capability": "observe",
                "purpose": "p",
                "gates": [{"when": None, "action": "stop", "phase": 3}],
            }
        )
        assert step.gates[0].when == ""
        assert step.gates[0].phase is None


class TestTracerUsesEffectiveFlags:
    def test_inherited_checkpoint_requirement_is_traced(self) -> None:
        """A step built in code that leaves requires_checkpoint False is still
        held to the ontology's requirement."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.add_workflow(
            WorkflowDefinition(
                name="w",
                goal="g",
                risk="high",
                steps=[
                    WorkflowStep(capability="plan", purpose="p", store_as="p"),
                    WorkflowStep(capability="mutate", purpose="m", store_as="m"),
                ],
            )
        )
        tracer = WorkflowTracer(eng, "w")
        tracer.record_action("plan")
        tracer.record_action("mutate")
        violations = tracer.get_report().violations
        assert violations == [
            "Step 1 (mutate) requires checkpoint but no checkpoint step preceded it"
        ]


# ---------------------------------------------------------------------------
# SEC-P1-1: Safety flag cross-reference against ontology
# ---------------------------------------------------------------------------


class TestSafetyFlagValidation:
    """Safety flags inherit from the ontology; a downgrade is W602 and has no
    effect (STANDARD v1.1 §5.2)."""

    @staticmethod
    def _downgrades(eng: WorkflowEngine, name: str) -> list[str]:
        return [
            d.location["field"]
            for d in eng.validate_report(name)
            if d.code is ErrorCode.SAFETY_FLAG_DOWNGRADE
        ]

    def test_mutate_with_mutation_false_warns(self) -> None:
        """A crafted step declaring mutation=false for 'mutate' is caught."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = _add_parsed(
            eng,
            "test_bypass_mutate",
            [{"capability": "mutate", "purpose": "sneaky", "mutation": False}],
        )
        assert self._downgrades(eng, "test_bypass_mutate") == ["mutation"]
        # The ontology value applies.
        assert wf.steps[0].mutation is True
        assert eng.effective_flags(wf.steps[0])["mutation"] is True

    def test_send_with_checkpoint_false_warns(self) -> None:
        """'send' with requires_checkpoint=false is flagged."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        _add_parsed(
            eng,
            "test_bypass_send",
            [{"capability": "send", "purpose": "s", "requires_checkpoint": False}],
        )
        assert self._downgrades(eng, "test_bypass_send") == ["requires_checkpoint"]

    def test_code_built_defaults_are_not_downgrades(self) -> None:
        """A step built in code that leaves the safety fields at their
        defaults declares nothing: no W602, and the ontology applies."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.add_workflow(
            WorkflowDefinition(
                name="w",
                goal="g",
                risk="high",
                spec_version="1.1",
                steps=[
                    WorkflowStep(capability="plan", purpose="p", store_as="p"),
                    WorkflowStep(capability="constrain", purpose="c", store_as="c"),
                    WorkflowStep(capability="checkpoint", purpose="k", store_as="k"),
                    WorkflowStep(capability="mutate", purpose="m", store_as="m"),
                ],
            )
        )
        assert eng.validate_report("w") == []
        wf = eng.get_workflow("w")
        assert wf is not None
        assert [s.capability for s in wf.mutation_steps] == ["checkpoint", "mutate"]
        assert [s.capability for s in wf.checkpoint_required_steps] == ["mutate"]

    def test_code_built_audit_default_is_not_an_override(self) -> None:
        """mutation_overridable honours a declared mutation: false, not the
        attribute's default."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        default = WorkflowStep(capability="audit", purpose="a")
        declared = WorkflowStep(
            capability="audit", purpose="a", declared={"mutation": False}
        )
        assert eng.effective_flags(default)["mutation"] is True
        assert eng.effective_flags(declared)["mutation"] is False

    def test_honest_mutate_step_has_no_downgrade(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.add_workflow(
            WorkflowDefinition(
                name="test_honest_mutate",
                goal="test",
                risk="high",
                steps=[
                    WorkflowStep(
                        capability="mutate",
                        purpose="honest mutation",
                        store_as="m",
                        risk="high",
                        mutation=True,
                        requires_checkpoint=True,
                        requires_approval=True,
                    ),
                ],
            )
        )
        assert self._downgrades(eng, "test_honest_mutate") == []

    def test_upgrade_from_ontology_passes(self) -> None:
        """Being MORE cautious than the ontology is fine."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.add_workflow(
            WorkflowDefinition(
                name="test_upgrade",
                goal="test",
                risk="low",
                spec_version="1.1",
                steps=[
                    WorkflowStep(
                        capability="observe",  # Ontology: mutation=false
                        purpose="cautious observe",
                        store_as="o",
                        mutation=True,  # Step upgrades to true — fine
                        requires_checkpoint=True,
                    ),
                ],
            )
        )
        assert eng.validate_report("test_upgrade") == []

    def test_omitted_flags_inherit_from_ontology(self) -> None:
        """Parsed with a registry, a step that omits its safety fields is
        treated as the ontology declares; ``declared`` records the omission."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        step = WorkflowStep.from_dict(
            {"capability": "mutate", "purpose": "p", "store_as": "m"}, eng.registry
        )
        assert (step.risk, step.mutation) == ("high", True)
        assert (step.requires_checkpoint, step.requires_approval) == (True, True)
        assert step.declared == {}

    def test_declared_downgrade_is_ignored_when_parsed(self) -> None:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        data = {
            "capability": "mutate",
            "purpose": "p",
            "store_as": "m",
            "risk": "low",
            "requires_approval": False,
        }
        step = WorkflowStep.from_dict(data, eng.registry)
        assert (step.risk, step.requires_approval) == ("high", True)
        assert step.declared == {"risk": "low", "requires_approval": False}

    def test_overridable_mutation_may_be_declared_false(self) -> None:
        """audit is mutation_overridable: declaring mutation=false stands."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        declared = WorkflowStep.from_dict(
            {"capability": "audit", "purpose": "p", "mutation": False}, eng.registry
        )
        inherited = WorkflowStep.from_dict(
            {"capability": "audit", "purpose": "p"}, eng.registry
        )
        assert declared.mutation is False
        assert inherited.mutation is True
        assert eng.effective_flags(declared)["mutation"] is False

    def test_without_registry_the_declaration_applies(self) -> None:
        step = WorkflowStep.from_dict({"capability": "mutate", "purpose": "p"})
        assert (step.risk, step.mutation, step.requires_checkpoint) == (
            "low",
            False,
            False,
        )

    def test_loaded_catalog_steps_carry_effective_flags(
        self, engine: WorkflowEngine
    ) -> None:
        for name in engine.list_workflows():
            for step in engine.get_workflow(name).steps:  # type: ignore[union-attr]
                assert {k: getattr(step, k) for k in SAFETY_KEYS} == (
                    engine.effective_flags(step)
                ), (name, step.capability)


# ---------------------------------------------------------------------------
# SEC-P1-2: Validation input limits (alias bomb protection)
# ---------------------------------------------------------------------------


class TestValidationInputLimits:
    """Data handed to the core is bounded like YAML is: nesting depth, total
    size (which shared and cyclic containers would otherwise blow up), and
    plain JSON-like types only."""

    @staticmethod
    def _engine_with_bindings(bindings: Any) -> WorkflowEngine:
        eng = WorkflowEngine(ONTOLOGY_PATH)
        eng.add_workflow(
            WorkflowDefinition(
                name="w",
                goal="g",
                risk="low",
                steps=[
                    WorkflowStep(
                        capability="observe",
                        purpose="p",
                        store_as="o",
                        input_bindings=bindings,
                    )
                ],
            )
        )
        return eng

    def test_deeply_nested_bindings_raise(self) -> None:
        bindings: dict[str, Any] = {"val": "x"}
        for i in range(200):
            bindings = {f"level_{i}": bindings}
        eng = self._engine_with_bindings(bindings)
        with pytest.raises(ValueError, match="nesting deeper than 128"):
            eng.validate_report()

    def test_shared_refs_count_each_use(self) -> None:
        """1000 references to one dict are 1000 values, well within budget."""
        shared: dict[str, str] = {"q": "plain"}
        eng = self._engine_with_bindings({f"k{i}": shared for i in range(1000)})
        assert all(
            d.code is not ErrorCode.SCHEMA_VALIDATION_FAILED
            for d in eng.validate_report()
        )

    def test_alias_bomb_raises(self) -> None:
        """Doubling shared containers 30 times would be 2^30 values."""
        layer: Any = ["x"]
        for _ in range(30):
            layer = [layer, layer]
        eng = self._engine_with_bindings({"bomb": layer})
        with pytest.raises(ValueError, match="more than 1000000 values"):
            eng.validate_report()

    def test_cycle_raises(self) -> None:
        cyclic: list[Any] = []
        cyclic.append(cyclic)
        eng = self._engine_with_bindings({"loop": cyclic})
        with pytest.raises(ValueError, match="nesting deeper"):
            eng.validate_report()

    @pytest.mark.parametrize(
        "value, error",
        [
            ({1: "int key"}, TypeError),
            (object(), TypeError),
            (float("nan"), ValueError),
            (2**64, ValueError),
        ],
        ids=["non-string-key", "object", "nan", "big-int"],
    )
    def test_non_json_values_rejected(self, value: Any, error: type) -> None:
        eng = self._engine_with_bindings({"v": value})
        with pytest.raises(error):
            eng.validate_report()

    def test_real_catalog_validates(self, engine: WorkflowEngine) -> None:
        assert engine.validate_all() == {}


# ---------------------------------------------------------------------------
# SEC-P1-1: Runtime checkpoint enforcement despite YAML downgrade
# ---------------------------------------------------------------------------


class TestCheckpointEnforcementWithDowngrade:
    """Verify checkpoint is created even when YAML downgrades flags."""

    def test_checkpoint_enforced_despite_yaml_downgrade(
        self, engine_with_tracker: WorkflowEngine
    ) -> None:
        """A 'mutate' step with mutation=false should still get a checkpoint
        because the ontology declares mutation=true."""
        tracker = engine_with_tracker.checkpoint_tracker
        assert tracker is not None

        # Craft a step that lies about its mutation flag
        crafted_step = WorkflowStep(
            capability="mutate",
            purpose="sneaky mutate",
            mutation=False,  # Lie — ontology says True
            requires_checkpoint=False,  # Lie — ontology says True
        )

        cp_id = engine_with_tracker.ensure_checkpoint_before_step(
            crafted_step, "test_bypass"
        )
        # Checkpoint MUST be created despite the YAML downgrade
        assert cp_id is not None
        assert tracker.has_valid_checkpoint()
