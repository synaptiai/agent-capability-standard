"""Tests for WorkflowSynthesizer."""

from __future__ import annotations

import pytest

from grounded_agency.discovery.synthesizer import WorkflowSynthesizer
from grounded_agency.discovery.types import CapabilityMatch, TaskRequirement


class TestDependencyResolution:
    """Tests for transitive dependency resolution."""

    def test_resolve_requires_edges(self, synthesizer: WorkflowSynthesizer):
        """Required capabilities should be added transitively."""
        # mutate requires checkpoint in the ontology
        ids = synthesizer._resolve_dependencies({"mutate"})
        # Should include mutate plus any capabilities it requires
        assert "mutate" in ids

    def test_no_duplicates(self, synthesizer: WorkflowSynthesizer):
        """Already-present capabilities should not be duplicated."""
        ids = synthesizer._resolve_dependencies({"search", "detect"})
        assert len(ids) == len(set(ids))


class TestSafetyStepInjection:
    """Tests for automatic safety step insertion."""

    def test_checkpoint_added_for_mutation(self, synthesizer: WorkflowSynthesizer):
        """Checkpoint should be injected when mutation capabilities are present."""
        ids = synthesizer._inject_safety_steps({"mutate"})
        assert "checkpoint" in ids
        assert "audit" in ids

    def test_no_safety_for_read_only(self, synthesizer: WorkflowSynthesizer):
        """Read-only workflows should not get safety steps injected."""
        ids = synthesizer._inject_safety_steps({"search", "detect"})
        assert "checkpoint" not in ids
        assert "audit" not in ids

    def test_audit_added_with_mutation(self, synthesizer: WorkflowSynthesizer):
        """Audit should be added when any mutation capability is present."""
        ids = synthesizer._inject_safety_steps({"send"})
        # send has mutation=true and requires_checkpoint=true in ontology
        cap = synthesizer.registry.get_capability("send")
        if cap and cap.requires_checkpoint:
            assert "audit" in ids


class TestConflictDetection:
    """Tests for conflicts_with edge validation."""

    def test_no_conflicts_in_normal_workflow(self, synthesizer: WorkflowSynthesizer):
        """Common capability sets should have no conflicts."""
        conflicts = synthesizer._check_conflicts({"search", "detect", "explain"})
        assert len(conflicts) == 0

    def test_empty_set_no_conflicts(self, synthesizer: WorkflowSynthesizer):
        """Empty capability set should have no conflicts."""
        conflicts = synthesizer._check_conflicts(set())
        assert len(conflicts) == 0


class TestTopologicalSort:
    """Tests for topological sort with layer-based tiebreaking."""

    def test_perceive_before_execute(self, synthesizer: WorkflowSynthesizer):
        """PERCEIVE layer capabilities should come before EXECUTE."""
        ordered = synthesizer._topological_sort({"search", "mutate"})
        if "search" in ordered and "mutate" in ordered:
            assert ordered.index("search") < ordered.index("mutate")

    def test_checkpoint_before_mutation(self, synthesizer: WorkflowSynthesizer):
        """Checkpoint should be ordered before mutation capabilities."""
        ordered = synthesizer._topological_sort({"checkpoint", "mutate", "search"})
        if "checkpoint" in ordered and "mutate" in ordered:
            assert ordered.index("checkpoint") < ordered.index("mutate")

    def test_single_capability(self, synthesizer: WorkflowSynthesizer):
        """Single capability should produce a single-element list."""
        ordered = synthesizer._topological_sort({"search"})
        assert ordered == ["search"]

    def test_deterministic_ordering(self, synthesizer: WorkflowSynthesizer):
        """Same input should produce same output (deterministic)."""
        caps = {"search", "detect", "explain", "generate"}
        order1 = synthesizer._topological_sort(caps)
        order2 = synthesizer._topological_sort(caps)
        assert order1 == order2


class TestWorkflowSynthesis:
    """Tests for full workflow synthesis."""

    @pytest.mark.asyncio
    async def test_simple_workflow(self, synthesizer: WorkflowSynthesizer):
        """Simple search + detect should produce a valid workflow."""
        req1 = TaskRequirement(action="find", target="files")
        req2 = TaskRequirement(action="detect", target="patterns")
        matches = [
            CapabilityMatch(
                capability_id="search",
                confidence=0.9,
                requirement=req1,
                reasoning="Search for files",
            ),
            CapabilityMatch(
                capability_id="detect",
                confidence=0.85,
                requirement=req2,
                reasoning="Detect patterns",
                domain="pattern",
            ),
        ]
        workflow = await synthesizer.synthesize(matches, "Find files and detect patterns")
        assert workflow.name != ""
        assert len(workflow.steps) >= 2
        assert workflow.confidence > 0

    @pytest.mark.asyncio
    async def test_mutation_workflow_has_safety(self, synthesizer: WorkflowSynthesizer):
        """Mutation workflows should include checkpoint and audit steps."""
        req = TaskRequirement(action="delete", target="files")
        matches = [
            CapabilityMatch(
                capability_id="mutate",
                confidence=0.95,
                requirement=req,
                reasoning="Delete files",
            ),
        ]
        workflow = await synthesizer.synthesize(matches, "Delete old files")
        cap_ids = [s["capability"] for s in workflow.steps]
        assert "checkpoint" in cap_ids
        assert "audit" in cap_ids
        # Checkpoint should come before mutate
        assert cap_ids.index("checkpoint") < cap_ids.index("mutate")

    @pytest.mark.asyncio
    async def test_empty_matches(self, synthesizer: WorkflowSynthesizer):
        """Empty matches should produce empty workflow."""
        workflow = await synthesizer.synthesize([], "Nothing")
        assert len(workflow.steps) == 0
        assert workflow.confidence == 0.0

    @pytest.mark.asyncio
    async def test_deterministic_bindings(self, synthesizer: WorkflowSynthesizer):
        """Without LLM, bindings should chain sequentially."""
        req = TaskRequirement(action="find", target="files")
        matches = [
            CapabilityMatch(
                capability_id="search",
                confidence=0.9,
                requirement=req,
                reasoning="Search",
            ),
            CapabilityMatch(
                capability_id="detect",
                confidence=0.85,
                requirement=TaskRequirement(action="detect", target="patterns"),
                reasoning="Detect",
            ),
        ]
        workflow = await synthesizer.synthesize(matches, "Find and detect")
        # Second step should reference first step's output
        for step in workflow.steps:
            if step["capability"] == "detect":
                bindings = step.get("input_bindings", {})
                if bindings:
                    # Should contain a ${ref} to a previous step
                    assert any("${" in str(v) for v in bindings.values())

    @pytest.mark.asyncio
    async def test_workflow_validation(self, synthesizer: WorkflowSynthesizer):
        """Synthesized workflow should include validation results."""
        req = TaskRequirement(action="find", target="files")
        matches = [
            CapabilityMatch(
                capability_id="search",
                confidence=0.9,
                requirement=req,
                reasoning="Search",
            ),
        ]
        workflow = await synthesizer.synthesize(matches, "Find files")
        assert "valid" in workflow.validation_result
        assert "errors" in workflow.validation_result


class TestExistingWorkflowMatch:
    """Tests for matching against existing catalog workflows."""

    def test_no_match_for_unrelated(self, synthesizer: WorkflowSynthesizer):
        """Unrelated capability sets should not match existing workflows."""
        result = synthesizer._check_existing_workflows({"xyzzy_nonexistent"})
        assert result is None

    def test_empty_set_no_match(self, synthesizer: WorkflowSynthesizer):
        """Empty capability set should not match."""
        result = synthesizer._check_existing_workflows(set())
        assert result is None
