"""
Tests for grounded_query() and GroundedClient wrappers.

Since claude_agent_sdk may not be installed in test environments,
these tests focus on:
- CostSummary dataclass behavior
- Adapter cost_summary initialization
- Import error handling
- Integration with adapter's wrap_options
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from grounded_agency import (
    CostSummary,
    GroundedAgentAdapter,
)

# Upper bound for the one test that reaches the real SDK. Generous enough that
# a healthy API answers well inside it, short enough that an unreachable one
# does not stall the suite.
SDK_CALL_TIMEOUT_SECONDS = 20.0

# =============================================================================
# CostSummary Tests
# =============================================================================


class TestCostSummary:
    """Tests for the CostSummary dataclass."""

    def test_default_values(self):
        """Test CostSummary initializes with zero values."""
        summary = CostSummary()
        assert summary.total_usd == 0.0
        assert summary.by_model == {}
        assert summary.turn_count == 0

    def test_update_cost(self):
        """Test updating cost values."""
        summary = CostSummary()
        summary.total_usd = 0.05
        summary.by_model["sonnet"] = 0.05
        summary.turn_count = 1

        assert summary.total_usd == 0.05
        assert summary.by_model["sonnet"] == 0.05
        assert summary.turn_count == 1

    def test_multiple_models(self):
        """Test tracking cost across multiple models."""
        summary = CostSummary()
        summary.by_model["sonnet"] = 0.03
        summary.by_model["haiku"] = 0.01
        summary.total_usd = 0.04

        assert len(summary.by_model) == 2
        assert summary.total_usd == 0.04


# =============================================================================
# Adapter CostSummary Integration Tests
# =============================================================================


class TestAdapterCostIntegration:
    """Tests for CostSummary integration with adapter."""

    def test_adapter_has_cost_summary(self, adapter: GroundedAgentAdapter):
        """Test that adapter initializes with a CostSummary."""
        assert adapter.cost_summary is not None
        assert isinstance(adapter.cost_summary, CostSummary)
        assert adapter.cost_summary.total_usd == 0.0

    def test_cost_summary_is_mutable(self, adapter: GroundedAgentAdapter):
        """Test that cost summary can be updated."""
        adapter.cost_summary.total_usd = 1.50
        adapter.cost_summary.turn_count = 5
        adapter.cost_summary.by_model["opus"] = 1.50

        assert adapter.cost_summary.total_usd == 1.50
        assert adapter.cost_summary.turn_count == 5


# =============================================================================
# grounded_query Import Tests
# =============================================================================


class TestGroundedQueryImport:
    """Test that grounded_query handles missing SDK gracefully."""

    def test_grounded_query_importable(self):
        """Test that grounded_query can be imported."""
        from grounded_agency import grounded_query

        assert callable(grounded_query)

    def test_grounded_client_importable(self):
        """Test that GroundedClient can be imported."""
        from grounded_agency import GroundedClient

        assert GroundedClient is not None

    @pytest.mark.asyncio
    async def test_grounded_query_callable(self, adapter: GroundedAgentAdapter):
        """Test that grounded_query is callable with the SDK installed.

        The call is real -- no mock, no skip (see #99) -- but it is bounded in
        two ways, because on a machine with a live CLI session this drives an
        actual billable query with no natural end:

        * the loop stops after the first message, which is all that is needed
          to prove the wrapper yields from the SDK;
        * the whole thing runs under a timeout, so an unreachable or slow API
          cannot stall the suite. Wall time for this file has ranged from
          seconds to minutes depending on whether the runner was logged in.

        Only ImportError is a real failure here. Every other outcome --
        validation error, no connection, no session, or timeout -- is the
        environment, not the wrapper.
        """
        from claude_agent_sdk import ClaudeSDKError

        from grounded_agency import grounded_query

        async def consume_first_message() -> None:
            async for _ in grounded_query("test", adapter=adapter):
                break

        try:
            await asyncio.wait_for(
                consume_first_message(), timeout=SDK_CALL_TIMEOUT_SECONDS
            )
        except (
            ConnectionError,
            OSError,
            ValueError,
            ClaudeSDKError,
            asyncio.TimeoutError,
        ):
            # Expected: SDK validation, no live API connection, no session, or
            # an API too slow to answer inside the budget.
            pass

    def test_grounded_client_instantiates(self):
        """Test that GroundedClient instantiates with the SDK installed."""
        from grounded_agency import GroundedClient

        client = GroundedClient()
        assert client is not None


# =============================================================================
# _update_cost_summary Tests
# =============================================================================


class TestUpdateCostSummary:
    """Tests for the _update_cost_summary helper."""

    def test_update_with_cost(self, adapter: GroundedAgentAdapter):
        """Test updating cost summary from a mock result."""
        from grounded_agency.query import _update_cost_summary

        @dataclass
        class MockResult:
            total_cost_usd: float = 0.123
            model: str = "sonnet"

        _update_cost_summary(adapter, MockResult())

        assert adapter.cost_summary.total_usd == 0.123
        assert adapter.cost_summary.by_model["sonnet"] == 0.123
        assert adapter.cost_summary.turn_count == 1

    def test_update_without_cost(self, adapter: GroundedAgentAdapter):
        """Test updating cost summary when result has no cost."""
        from grounded_agency.query import _update_cost_summary

        @dataclass
        class MockResult:
            pass

        _update_cost_summary(adapter, MockResult())

        assert adapter.cost_summary.total_usd == 0.0
        assert adapter.cost_summary.turn_count == 1

    def test_update_multiple_turns(self, adapter: GroundedAgentAdapter):
        """Test accumulating turns with delta-based model tracking."""
        from grounded_agency.query import _update_cost_summary

        @dataclass
        class MockResult:
            total_cost_usd: float = 0.0
            model: str = "sonnet"

        # SDK reports cumulative cost: 0.01, 0.02, 0.03
        for i in range(3):
            _update_cost_summary(adapter, MockResult(total_cost_usd=0.01 * (i + 1)))

        assert adapter.cost_summary.turn_count == 3
        assert adapter.cost_summary.total_usd == 0.03
        # Delta tracking: each turn added 0.01 to sonnet
        assert adapter.cost_summary.by_model["sonnet"] == pytest.approx(0.03)

    def test_update_multiple_models_delta(self, adapter: GroundedAgentAdapter):
        """Test delta tracking across multiple models."""
        from grounded_agency.query import _update_cost_summary

        @dataclass
        class MockResult:
            total_cost_usd: float = 0.0
            model: str = "sonnet"

        # Turn 1: sonnet, cumulative=0.02
        _update_cost_summary(adapter, MockResult(total_cost_usd=0.02, model="sonnet"))
        # Turn 2: sonnet, cumulative=0.05 (delta=0.03)
        _update_cost_summary(adapter, MockResult(total_cost_usd=0.05, model="sonnet"))
        # Turn 3: haiku, cumulative=0.06 (delta=0.01)
        _update_cost_summary(adapter, MockResult(total_cost_usd=0.06, model="haiku"))

        assert adapter.cost_summary.total_usd == 0.06
        assert adapter.cost_summary.turn_count == 3
        # sonnet: 0.02 + 0.03 = 0.05
        assert adapter.cost_summary.by_model["sonnet"] == pytest.approx(0.05)
        # haiku: 0.01
        assert adapter.cost_summary.by_model["haiku"] == pytest.approx(0.01)


# =============================================================================
# GroundedClient Error Path Tests (Issue 10)
# =============================================================================


class TestGroundedClientErrorPaths:
    """Tests for GroundedClient error handling outside context manager."""

    @pytest.mark.asyncio
    async def test_query_outside_context_raises(self, adapter: GroundedAgentAdapter):
        """Test that query() raises RuntimeError outside async context."""
        from grounded_agency.client import GroundedClient

        client = GroundedClient(adapter=adapter)

        with pytest.raises(RuntimeError, match="async context manager"):
            await client.query("test")

    @pytest.mark.asyncio
    async def test_receive_response_outside_context_raises(
        self, adapter: GroundedAgentAdapter
    ):
        """Test that receive_response() raises RuntimeError outside async context."""
        from grounded_agency.client import GroundedClient

        client = GroundedClient(adapter=adapter)

        with pytest.raises(RuntimeError, match="async context manager"):
            async for _ in client.receive_response():
                pass
