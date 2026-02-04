"""Tests for DiscoveryPipeline (integration)."""

from __future__ import annotations

import pytest

from grounded_agency.discovery.pipeline import DiscoveryPipeline
from grounded_agency.state.evidence_store import EvidenceStore


class TestDiscoveryPipelineKeyword:
    """Integration tests for the full pipeline (keyword fallback, no LLM)."""

    @pytest.mark.asyncio
    async def test_simple_task(self, pipeline: DiscoveryPipeline):
        """Simple task should produce requirements (may or may not match at keyword threshold)."""
        result = await pipeline.discover("Search for Python files with errors")
        assert result.task_description == "Search for Python files with errors"
        assert len(result.requirements) >= 1
        # Keyword fallback has 0.5 confidence (below 0.6 threshold),
        # so matches may be empty — requirements should still be found
        assert len(result.requirements) + len(result.gaps) >= 1

    @pytest.mark.asyncio
    async def test_mutation_task(self, pipeline: DiscoveryPipeline):
        """Mutation task should have safety steps in workflow."""
        result = await pipeline.discover("Delete old log files and send a report")
        if result.synthesized_workflow:
            cap_ids = [s["capability"] for s in result.synthesized_workflow.steps]
            # If mutate was matched, checkpoint should be present
            if "mutate" in cap_ids:
                assert "checkpoint" in cap_ids

    @pytest.mark.asyncio
    async def test_no_matches(self, pipeline: DiscoveryPipeline):
        """Task with no recognizable verbs should have low confidence."""
        result = await pipeline.discover("xyzzy foobar baz")
        assert result.confidence == 0.0
        assert len(result.matches) == 0

    @pytest.mark.asyncio
    async def test_evidence_anchors_created(self, pipeline: DiscoveryPipeline):
        """Discovery should produce evidence anchors."""
        result = await pipeline.discover("Search for files")
        assert len(result.evidence_anchors) >= 1

    @pytest.mark.asyncio
    async def test_cache_hit(self, pipeline: DiscoveryPipeline):
        """Same task should return cached result on second call."""
        result1 = await pipeline.discover("Search for files")
        result2 = await pipeline.discover("Search for files")
        assert result1 is result2  # Same object (cached)

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, pipeline: DiscoveryPipeline):
        """Cache invalidation should force re-analysis."""
        result1 = await pipeline.discover("Search for files")
        pipeline.invalidate_cache()
        result2 = await pipeline.discover("Search for files")
        assert result1 is not result2  # Different objects

    @pytest.mark.asyncio
    async def test_domain_parameter(self, pipeline: DiscoveryPipeline):
        """Domain parameter should propagate to matches."""
        result = await pipeline.discover("Search for files", domain="security")
        for match in result.matches:
            assert match.domain == "security"

    @pytest.mark.asyncio
    async def test_different_tasks_different_results(self, pipeline: DiscoveryPipeline):
        """Different tasks should produce different results."""
        result1 = await pipeline.discover("Search for files")
        result2 = await pipeline.discover("Delete old logs and send report")
        assert result1.task_description != result2.task_description


class TestDiscoveryPipelineWithLLM:
    """Integration tests with mock LLM."""

    @pytest.mark.asyncio
    async def test_llm_pipeline(self, pipeline_with_llm: DiscoveryPipeline):
        """Full pipeline with LLM should produce richer results."""
        result = await pipeline_with_llm.discover("Find files and detect patterns")
        assert len(result.requirements) == 2
        assert len(result.matches) == 2
        assert result.matches[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_llm_workflow_synthesis(self, pipeline_with_llm: DiscoveryPipeline):
        """Pipeline with LLM should produce a workflow."""
        result = await pipeline_with_llm.discover("Find files and detect patterns")
        assert result.synthesized_workflow is not None
        assert len(result.synthesized_workflow.steps) >= 2

    @pytest.mark.asyncio
    async def test_overall_confidence(self, pipeline_with_llm: DiscoveryPipeline):
        """Overall confidence should reflect match quality."""
        result = await pipeline_with_llm.discover("Find files and detect patterns")
        # Average of 0.9 and 0.85 = 0.875, no gaps
        assert result.confidence > 0.8


class TestDiscoveryPipelineWithEvidenceStore:
    """Tests for evidence store integration."""

    @pytest.mark.asyncio
    async def test_evidence_stored(
        self, registry, engine, evidence_store: EvidenceStore
    ):
        """Discovery should add evidence to the store."""
        pipeline = DiscoveryPipeline(registry, engine, evidence_store=evidence_store)
        await pipeline.discover("Search for files")
        assert len(evidence_store) > 0

    @pytest.mark.asyncio
    async def test_evidence_refs(self, registry, engine, evidence_store: EvidenceStore):
        """Evidence anchors should have tool refs."""
        pipeline = DiscoveryPipeline(registry, engine, evidence_store=evidence_store)
        result = await pipeline.discover("Search for files")
        for anchor_dict in result.evidence_anchors:
            assert "ref" in anchor_dict
