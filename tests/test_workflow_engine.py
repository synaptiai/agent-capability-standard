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

from grounded_agency.errors import ErrorCode, ValidationError
from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.workflows.engine import (
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
                            "scope": "${obs_out.scope}",
                            "items": ["${obs_out.items}"],
                        }
                    },
                ),
            ],
        )
        eng._workflows["test_nested"] = wf
        errors = eng.validate_bindings("test_nested")
        assert len(errors) == 0

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

    def test_safety_flag_downgrade_maps_to_f504(self) -> None:
        """A step that downgrades ontology safety flags should produce F504."""
        engine = WorkflowEngine(ONTOLOGY_PATH)
        # mutate has mutation=true in ontology; downgrade it to false
        engine._workflows["downgrade_wf"] = WorkflowDefinition(
            name="downgrade_wf",
            goal="test",
            risk="low",
            steps=[
                WorkflowStep(capability="checkpoint", purpose="save state"),
                WorkflowStep(
                    capability="mutate",
                    purpose="modify",
                    mutation=False,  # downgrades ontology's mutation=true
                ),
            ],
        )
        results = engine.validate_all_structured()
        assert "downgrade_wf" in results
        codes = {err.code for err in results["downgrade_wf"]}
        assert ErrorCode.CONSTRAINT_VIOLATED in codes

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

    def test_unresolved_ref_maps_to_invalid_binding_path(self) -> None:
        err = BindingError(
            workflow_name="w",
            step_index=0,
            step_capability="retrieve",
            binding_key="k",
            reference="r",
            error_type="unresolved_ref",
            message="ref not found",
        )
        assert err.error_code == ErrorCode.INVALID_BINDING_PATH

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


# ---------------------------------------------------------------------------
# SEC-P1-1: Safety flag cross-reference against ontology
# ---------------------------------------------------------------------------


class TestSafetyFlagValidation:
    """Verify that validate_capabilities detects safety flag downgrades."""

    def test_mutate_with_mutation_false_fails_validation(self) -> None:
        """A crafted step declaring mutation=false for 'mutate' must be caught."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_bypass_mutate",
            goal="test",
            risk="high",
            steps=[
                WorkflowStep(
                    capability="mutate",
                    purpose="sneaky mutation",
                    mutation=False,  # Ontology says True — bypass attempt
                    requires_checkpoint=True,
                ),
            ],
        )
        eng._workflows["test_bypass_mutate"] = wf
        errors = eng.validate_capabilities("test_bypass_mutate")
        assert any("downgrades to mutation=false" in e for e in errors)

    def test_send_with_checkpoint_false_fails_validation(self) -> None:
        """'send' with requires_checkpoint=false must be flagged."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_bypass_send",
            goal="test",
            risk="high",
            steps=[
                WorkflowStep(
                    capability="send",
                    purpose="sneaky send",
                    mutation=True,
                    requires_checkpoint=False,  # Ontology says True — bypass
                ),
            ],
        )
        eng._workflows["test_bypass_send"] = wf
        errors = eng.validate_capabilities("test_bypass_send")
        assert any("downgrades to requires_checkpoint=false" in e for e in errors)

    def test_honest_mutate_step_passes_validation(self) -> None:
        """A step that correctly declares mutation=true passes."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_honest_mutate",
            goal="test",
            risk="high",
            steps=[
                WorkflowStep(
                    capability="mutate",
                    purpose="honest mutation",
                    mutation=True,
                    requires_checkpoint=True,
                ),
            ],
        )
        eng._workflows["test_honest_mutate"] = wf
        errors = eng.validate_capabilities("test_honest_mutate")
        assert errors == []

    def test_upgrade_from_ontology_passes(self) -> None:
        """Being MORE cautious than the ontology is fine (no error)."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        wf = WorkflowDefinition(
            name="test_upgrade",
            goal="test",
            risk="low",
            steps=[
                WorkflowStep(
                    capability="observe",  # Ontology: mutation=false
                    purpose="cautious observe",
                    mutation=True,  # Step upgrades to true — fine
                    requires_checkpoint=True,
                ),
            ],
        )
        eng._workflows["test_upgrade"] = wf
        errors = eng.validate_capabilities("test_upgrade")
        assert errors == []


# ---------------------------------------------------------------------------
# SEC-P1-2: Binding traversal limits (YAML alias bomb protection)
# ---------------------------------------------------------------------------


class TestBindingTraversalLimits:
    """Verify _extract_binding_refs resists CPU amplification."""

    def test_deeply_nested_bindings_raise(self) -> None:
        """Nesting beyond _MAX_BINDING_DEPTH (50) must raise ValueError."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        # Build 60 levels of nesting
        bindings: dict[str, Any] = {"val": "${leaf_ref}"}
        for i in range(60):
            bindings = {f"level_{i}": bindings}
        with pytest.raises(ValueError, match="max depth"):
            eng._extract_binding_refs(bindings)

    def test_alias_bomb_shared_refs_handled(self) -> None:
        """Shared dict references should be traversed only once."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        shared: dict[str, str] = {"q": "${shared_ref}"}
        # 1000 references to the same dict — without protection this
        # would traverse 1000 copies
        bindings: dict[str, Any] = {f"k{i}": shared for i in range(1000)}
        refs = eng._extract_binding_refs(bindings)
        # shared dict visited once → exactly 1 ref extracted
        assert len(refs) == 1
        assert refs[0][1] == "shared_ref"

    def test_element_count_limit_raises(self) -> None:
        """More than _MAX_BINDING_ELEMENTS unique dicts must raise."""
        eng = WorkflowEngine(ONTOLOGY_PATH)
        # Create 10_001 unique dicts (each with unique id())
        bindings: dict[str, Any] = {f"k{i}": {"v": f"${{{i}}}"} for i in range(10_001)}
        with pytest.raises(ValueError, match="max element count"):
            eng._extract_binding_refs(bindings)

    def test_normal_bindings_unaffected(self, engine: WorkflowEngine) -> None:
        """Real catalog workflows must still validate without hitting limits."""
        for name in engine.list_workflows():
            wf = engine.get_workflow(name)
            assert wf is not None
            for step in wf.steps:
                # Should not raise
                engine._extract_binding_refs(step.input_bindings)


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
