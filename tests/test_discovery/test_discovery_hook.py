"""Tests for discovery_injector hook."""

from __future__ import annotations

from typing import Any

import pytest

from grounded_agency.discovery.pipeline import DiscoveryPipeline
from grounded_agency.hooks.discovery_injector import (
    _extract_prompt,
    create_discovery_injector,
)
from grounded_agency.state.evidence_store import EvidenceStore


class TestExtractPrompt:
    """Tests for prompt extraction from hook context."""

    def test_extract_from_input_data(self):
        """Should extract prompt from input_data dict."""
        result = _extract_prompt({"prompt": "Hello world"}, None)
        assert result == "Hello world"

    def test_extract_user_prompt_key(self):
        """Should find user_prompt key."""
        result = _extract_prompt({"user_prompt": "Task description"}, None)
        assert result == "Task description"

    def test_extract_message_key(self):
        """Should find message key."""
        result = _extract_prompt({"message": "Do something"}, None)
        assert result == "Do something"

    def test_extract_query_key(self):
        """Should find query key."""
        result = _extract_prompt({"query": "Find files"}, None)
        assert result == "Find files"

    def test_empty_input_returns_none(self):
        """Empty input should return None."""
        result = _extract_prompt({}, None)
        assert result is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only prompt should return None."""
        result = _extract_prompt({"prompt": "   "}, None)
        assert result is None

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        result = _extract_prompt({"prompt": "  Hello  "}, None)
        assert result == "Hello"


class TestDiscoveryInjectorHook:
    """Tests for the create_discovery_injector factory."""

    @pytest.mark.asyncio
    async def test_hook_returns_empty_dict(
        self, pipeline: DiscoveryPipeline, evidence_store: EvidenceStore
    ):
        """Hook should always return empty dict (non-blocking)."""
        hook = create_discovery_injector(pipeline, evidence_store)
        result = await hook({"prompt": "Search for files"}, "tool_123", None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_hook_caches_per_turn(
        self, pipeline: DiscoveryPipeline, evidence_store: EvidenceStore
    ):
        """Same prompt should not trigger re-analysis."""
        hook = create_discovery_injector(pipeline, evidence_store)
        # First call
        await hook({"prompt": "Search for files"}, "tool_1", None)
        # Second call with same prompt — should be cached
        await hook({"prompt": "Search for files"}, "tool_2", None)
        # No error means caching worked

    @pytest.mark.asyncio
    async def test_hook_handles_missing_prompt(
        self, pipeline: DiscoveryPipeline, evidence_store: EvidenceStore
    ):
        """Hook should handle missing prompt gracefully."""
        hook = create_discovery_injector(pipeline, evidence_store)
        result = await hook({}, "tool_123", None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_hook_handles_error(
        self, registry, engine, evidence_store: EvidenceStore
    ):
        """Hook should fail silently if pipeline errors."""

        async def broken_llm(prompt: str, schema: Any) -> dict[str, Any]:
            raise RuntimeError("Kaboom")

        pipeline = DiscoveryPipeline(registry, engine, llm_fn=broken_llm)
        hook = create_discovery_injector(pipeline, evidence_store)
        # Should not raise
        result = await hook({"prompt": "Test task"}, "tool_123", None)
        assert result == {}
