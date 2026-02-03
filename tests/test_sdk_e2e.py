"""End-to-end tests for SDK integration (TEST-006).

Tests real wrap_options(), permission callback, and hook registration
using the real Claude Agent SDK types.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from grounded_agency import (
    GroundedAgentAdapter,
    GroundedAgentConfig,
    RateLimitConfig,
)


def _is_allowed(result: Any) -> bool:
    """Check if permission result indicates allowed, handling SDK and fallback types."""
    if isinstance(result, dict):
        return result.get("allowed", False) is True
    # SDK types use behavior='allow', fallback types use allowed=True
    if getattr(result, "behavior", None) == "allow":
        return True
    return getattr(result, "allowed", False) is True


def _get_message(result: Any) -> str:
    """Extract message from permission result."""
    if isinstance(result, dict):
        return result.get("message", "")
    return getattr(result, "message", "")


@pytest.fixture
def adapter(tmp_path: Path) -> GroundedAgentAdapter:
    """Create a GroundedAgentAdapter with test configuration."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            strict_mode=True,
            rate_limit=RateLimitConfig(high_rpm=60, medium_rpm=120, low_rpm=300),
        )
    )


class TestWrapOptions:
    """Test wrap_options with mock SDK options."""

    def test_injects_file_checkpointing(self, adapter: GroundedAgentAdapter) -> None:
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)
        assert wrapped.enable_file_checkpointing is True

    def test_injects_permission_callback(self, adapter: GroundedAgentAdapter) -> None:
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)
        assert wrapped.can_use_tool is not None
        assert callable(wrapped.can_use_tool)

    def test_adds_skill_to_allowed_tools(self, adapter: GroundedAgentAdapter) -> None:
        base = ClaudeAgentOptions(allowed_tools=["Read", "Write"])
        wrapped = adapter.wrap_options(base)
        assert "Skill" in wrapped.allowed_tools

    def test_preserves_existing_allowed_tools(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        base = ClaudeAgentOptions(allowed_tools=["Read", "Write"])
        wrapped = adapter.wrap_options(base)
        assert "Read" in wrapped.allowed_tools
        assert "Write" in wrapped.allowed_tools

    def test_adds_post_hooks(self, adapter: GroundedAgentAdapter) -> None:
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)
        assert "PostToolUse" in wrapped.hooks
        # Should have 3 hooks: evidence collector, skill tracker, mutation consumer
        assert len(wrapped.hooks["PostToolUse"]) == 3

    def test_preserves_existing_hooks(self, adapter: GroundedAgentAdapter) -> None:
        existing_hook = {"hooks": [lambda: None]}
        base = ClaudeAgentOptions(
            hooks={"PostToolUse": [existing_hook], "PreToolUse": []}
        )
        wrapped = adapter.wrap_options(base)
        assert "PreToolUse" in wrapped.hooks
        # Existing + 3 new
        assert len(wrapped.hooks["PostToolUse"]) == 4


class TestPermissionCallback:
    """Test the permission callback end-to-end."""

    async def test_blocks_write_without_checkpoint(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """Write tool should be blocked without a checkpoint."""
        callback = adapter._make_permission_callback()
        result = await callback(
            "Write", {"file_path": "/tmp/test.txt", "content": "hello"}, None
        )
        assert not _is_allowed(result)
        assert "checkpoint" in _get_message(result).lower()

    async def test_allows_write_with_checkpoint(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """Write tool should be allowed with a valid checkpoint."""
        adapter.create_checkpoint(scope=["*"], reason="test")
        callback = adapter._make_permission_callback()
        result = await callback(
            "Write", {"file_path": "/tmp/test.txt", "content": "hello"}, None
        )
        assert _is_allowed(result)

    async def test_allows_read_without_checkpoint(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """Read tool should always be allowed."""
        callback = adapter._make_permission_callback()
        result = await callback("Read", {"file_path": "/tmp/test.txt"}, None)
        assert _is_allowed(result)

    async def test_rate_limiting_blocks_excess(self, tmp_path: Path) -> None:
        """SEC-010: Rate limiting should block excess requests."""
        # Very strict rate limit
        test_adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                strict_mode=True,
                rate_limit=RateLimitConfig(
                    high_rpm=2,
                    medium_rpm=4,
                    low_rpm=8,
                    burst_multiplier=1.0,
                ),
            )
        )
        test_adapter.create_checkpoint(scope=["*"], reason="rate test")
        callback = test_adapter._make_permission_callback()

        # First 2 should succeed
        for _ in range(2):
            result = await callback(
                "Write", {"file_path": "/tmp/t.txt", "content": "x"}, None
            )
            assert _is_allowed(result)
            # Re-create checkpoint after each use
            test_adapter.create_checkpoint(scope=["*"], reason="rate test")

        # 3rd should be rate limited
        result = await callback(
            "Write", {"file_path": "/tmp/t.txt", "content": "x"}, None
        )
        assert not _is_allowed(result)
        assert "rate limit" in _get_message(result).lower()


class TestFullE2EFlow:
    """End-to-end flow tests."""

    def test_checkpoint_create_mutate_consume(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """Full lifecycle: create checkpoint, verify, consume, verify blocked."""
        # No checkpoint — should block
        assert adapter.has_valid_checkpoint() is False

        # Create checkpoint
        checkpoint_id = adapter.create_checkpoint(scope=["*.py"], reason="e2e test")
        assert checkpoint_id is not None
        assert adapter.has_valid_checkpoint() is True

        # Consume
        consumed = adapter.consume_checkpoint()
        assert consumed == checkpoint_id

        # Now blocked again
        assert adapter.has_valid_checkpoint() is False

    def test_evidence_collection(self, adapter: GroundedAgentAdapter) -> None:
        """Evidence store collects anchors."""
        from grounded_agency.state.evidence_store import EvidenceAnchor

        anchor = EvidenceAnchor.from_tool_output("Read", "abc123", {"path": "/tmp"})
        adapter.evidence_store.add_anchor(anchor)

        evidence = adapter.get_evidence(5)
        assert len(evidence) == 1
        assert "tool:Read:abc123" in evidence[0]

    def test_ontology_accessible(self, adapter: GroundedAgentAdapter) -> None:
        """Ontology version and capabilities accessible via adapter."""
        assert adapter.ontology_version != "unknown"
        assert adapter.capability_count >= 36

    def test_rate_limiter_accessible(self, adapter: GroundedAgentAdapter) -> None:
        """Rate limiter is accessible via adapter."""
        remaining = adapter.rate_limiter.get_remaining("high")
        assert remaining > 0


class TestWithRealSDK:
    """Tests that use the real Claude Agent SDK types."""

    def test_real_wrap_options(self, adapter: GroundedAgentAdapter) -> None:
        """Test wrap_options with real SDK types."""
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)
        assert wrapped.enable_file_checkpointing is True
