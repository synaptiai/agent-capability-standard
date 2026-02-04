"""Tests for GapDetector."""

from __future__ import annotations

import pytest

from grounded_agency.discovery.gap_detector import GapDetector
from grounded_agency.discovery.types import CapabilityGap, TaskRequirement


class TestGapDetector:
    """Tests for gap detection and capability proposals."""

    @pytest.mark.asyncio
    async def test_passthrough_without_llm(self, gap_detector: GapDetector):
        """Without LLM, gaps pass through unchanged."""
        gap = CapabilityGap(
            requirement=TaskRequirement(action="negotiate", target="terms"),
            nearest_existing=["inquire", "send"],
        )
        result = await gap_detector.detect_gaps([gap])
        assert len(result) == 1
        assert result[0].proposed_capability is None  # No LLM, no proposal
        assert result[0].nearest_existing == ["inquire", "send"]

    @pytest.mark.asyncio
    async def test_proposal_with_llm(self, gap_detector_with_llm: GapDetector):
        """With LLM, gaps should get ProposedCapability."""
        gap = CapabilityGap(
            requirement=TaskRequirement(action="negotiate", target="terms"),
            nearest_existing=["inquire"],
        )
        result = await gap_detector_with_llm.detect_gaps([gap])
        assert len(result) == 1
        proposal = result[0].proposed_capability
        assert proposal is not None
        assert proposal.id == "negotiate"
        assert proposal.layer == "COORDINATE"
        assert proposal.risk == "medium"

    @pytest.mark.asyncio
    async def test_proposal_has_schema(self, gap_detector_with_llm: GapDetector):
        """Proposed capabilities should have input/output schemas."""
        gap = CapabilityGap(
            requirement=TaskRequirement(action="negotiate", target="terms"),
        )
        result = await gap_detector_with_llm.detect_gaps([gap])
        proposal = result[0].proposed_capability
        assert proposal is not None
        assert "properties" in proposal.input_schema
        assert "properties" in proposal.output_schema

    @pytest.mark.asyncio
    async def test_proposal_has_edges(self, gap_detector_with_llm: GapDetector):
        """Proposed capabilities should suggest edges."""
        gap = CapabilityGap(
            requirement=TaskRequirement(action="negotiate", target="terms"),
        )
        result = await gap_detector_with_llm.detect_gaps([gap])
        proposal = result[0].proposed_capability
        assert proposal is not None
        assert len(proposal.suggested_edges) >= 1
        assert proposal.suggested_edges[0]["type"] == "requires"

    @pytest.mark.asyncio
    async def test_empty_gaps_passthrough(self, gap_detector: GapDetector):
        """Empty gap list should return empty list."""
        result = await gap_detector.detect_gaps([])
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_failure_preserves_gap(self, registry):
        """If LLM fails during proposal, gap should still be returned."""

        async def failing_llm(prompt, schema):
            raise RuntimeError("LLM down")

        detector = GapDetector(registry, llm_fn=failing_llm)
        gap = CapabilityGap(
            requirement=TaskRequirement(action="negotiate", target="terms"),
            nearest_existing=["inquire"],
        )
        result = await detector.detect_gaps([gap])
        assert len(result) == 1
        assert result[0].proposed_capability is None  # Failure preserved original
