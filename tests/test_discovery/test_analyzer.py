"""Tests for TaskAnalyzer."""

from __future__ import annotations

import pytest

from grounded_agency.discovery.analyzer import TaskAnalyzer, _VERB_HEURISTICS


class TestTaskAnalyzerKeywordFallback:
    """Tests for keyword-based analysis (no LLM)."""

    @pytest.mark.asyncio
    async def test_simple_search_task(self, analyzer: TaskAnalyzer):
        """'Find files' should match search capability."""
        reqs, matches = await analyzer.analyze("Find all Python files")
        assert len(reqs) >= 1
        assert any(m.capability_id == "search" for m in matches)

    @pytest.mark.asyncio
    async def test_mutation_task(self, analyzer: TaskAnalyzer):
        """'Delete files' should match mutate capability."""
        reqs, matches = await analyzer.analyze("Delete old log files")
        assert any(m.capability_id == "mutate" for m in matches)

    @pytest.mark.asyncio
    async def test_multi_action_task(self, analyzer: TaskAnalyzer):
        """Multiple verbs should produce multiple matches."""
        reqs, matches = await analyzer.analyze(
            "Search for errors, detect anomalies, and send a report"
        )
        cap_ids = {m.capability_id for m in matches}
        assert "search" in cap_ids
        assert "detect" in cap_ids
        assert "send" in cap_ids

    @pytest.mark.asyncio
    async def test_no_matches_for_gibberish(self, analyzer: TaskAnalyzer):
        """Non-verb text should produce no matches."""
        reqs, matches = await analyzer.analyze("xyzzy foobar baz")
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_keyword_confidence(self, analyzer: TaskAnalyzer):
        """Keyword matches should have reduced confidence (0.5)."""
        reqs, matches = await analyzer.analyze("Search for something")
        for m in matches:
            assert m.confidence == 0.5

    @pytest.mark.asyncio
    async def test_deduplication(self, analyzer: TaskAnalyzer):
        """Same verb appearing twice should only produce one match."""
        reqs, matches = await analyzer.analyze("Search here and search there")
        search_matches = [m for m in matches if m.capability_id == "search"]
        assert len(search_matches) == 1

    @pytest.mark.asyncio
    async def test_domain_hint_passed_through(self, analyzer: TaskAnalyzer):
        """Domain parameter should propagate to matches."""
        reqs, matches = await analyzer.analyze("Find files", domain="security")
        for m in matches:
            assert m.domain == "security"


class TestTaskAnalyzerWithLLM:
    """Tests for LLM-based analysis."""

    @pytest.mark.asyncio
    async def test_llm_analysis(self, analyzer_with_llm: TaskAnalyzer):
        """LLM analysis should return structured requirements and matches."""
        reqs, matches = await analyzer_with_llm.analyze("Find files and detect patterns")
        assert len(reqs) == 2
        assert len(matches) == 2
        assert matches[0].capability_id == "search"
        assert matches[1].capability_id == "detect"

    @pytest.mark.asyncio
    async def test_llm_confidence_scores(self, analyzer_with_llm: TaskAnalyzer):
        """LLM matches should have confidence from response."""
        reqs, matches = await analyzer_with_llm.analyze("Find files and detect patterns")
        assert matches[0].confidence == 0.9
        assert matches[1].confidence == 0.85

    @pytest.mark.asyncio
    async def test_llm_fallback_on_error(self, registry):
        """If LLM fails, should fall back to keywords."""

        async def failing_llm(prompt, schema):
            raise ConnectionError("LLM unavailable")

        analyzer = TaskAnalyzer(registry, llm_fn=failing_llm)
        reqs, matches = await analyzer.analyze("Search for files")
        # Should get keyword-based results
        assert any(m.capability_id == "search" for m in matches)
        assert all(m.confidence == 0.5 for m in matches)


class TestVerbHeuristicTable:
    """Tests for the verb -> capability heuristic mapping."""

    def test_all_layers_covered(self, registry):
        """Heuristic table should have verbs mapping to capabilities in each layer."""
        mapped_caps = set(_VERB_HEURISTICS.values())
        layers_covered = set()
        for cap in registry.all_capabilities():
            if cap.id in mapped_caps:
                layers_covered.add(cap.layer)
        # Should cover at least the main cognitive layers
        assert "PERCEIVE" in layers_covered
        assert "UNDERSTAND" in layers_covered
        assert "EXECUTE" in layers_covered
        assert "VERIFY" in layers_covered

    def test_heuristic_targets_exist_in_ontology(self, registry):
        """Every capability ID in the heuristic table should exist in the ontology."""
        for cap_id in set(_VERB_HEURISTICS.values()):
            assert registry.get_capability(cap_id) is not None, (
                f"Heuristic maps to unknown capability: {cap_id}"
            )
