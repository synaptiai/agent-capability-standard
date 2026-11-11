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


def _pre_decision(result: dict[str, Any]) -> str | None:
    """The PreToolUse permission decision, as the SDK reads it."""
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


def _pre_reason(result: dict[str, Any]) -> str:
    return result.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


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
    async def test_wrapping_twice_charges_the_rate_limit_once(
        self, tmp_path: Path
    ) -> None:
        # GroundedClient wraps the options it is given; options the adapter
        # already wrapped must not gain a second safety hook.
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                rate_limit=RateLimitConfig(medium_rpm=2, burst_multiplier=1.0),
            )
        )
        once = adapter.wrap_options(ClaudeAgentOptions())
        twice = adapter.wrap_options(once)
        assert twice is once
        assert len(twice.hooks["PreToolUse"]) == 1

        call = {"tool_name": "Skill", "tool_input": {"skill": "checkpoint"}}
        for n in range(2):
            for entry in twice.hooks["PreToolUse"]:
                for hook in entry.hooks:
                    assert _pre_decision(await hook(call, f"s{n}", None)) is None

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

    def test_does_not_add_skill_to_allowed_tools(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        # An allowed_tools entry is approved before can_use_tool runs, so
        # adding Skill would exempt skill calls from the rate limit.
        base = ClaudeAgentOptions(allowed_tools=["Read", "Write"])
        wrapped = adapter.wrap_options(base)
        assert wrapped.allowed_tools == ["Read", "Write"]

    async def test_listed_tools_are_rate_limited(self, tmp_path: Path) -> None:
        # The SDK approves a tool in allowed_tools without calling
        # can_use_tool, but PreToolUse still runs for it, and that is
        # where the rate limit lives. Skill is medium-risk; one token, so
        # the second call is denied.
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                rate_limit=RateLimitConfig(medium_rpm=1, burst_multiplier=1.0),
            )
        )
        wrapped = adapter.wrap_options(ClaudeAgentOptions(allowed_tools=["Skill"]))
        pre = wrapped.hooks["PreToolUse"][-1].hooks[0]
        call = {"tool_name": "Skill", "tool_input": {"skill": "checkpoint"}}
        assert _pre_decision(await pre(call, "s1", None)) is None
        second = await pre(call, "s2", None)
        assert _pre_decision(second) == "deny"
        assert "Rate limited" in _pre_reason(second)

    async def test_callback_does_not_charge_the_rate_limit(
        self, tmp_path: Path
    ) -> None:
        # A call not in allowed_tools passes PreToolUse and then
        # can_use_tool. Only the hook may take a token, or each such call
        # would count twice.
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                rate_limit=RateLimitConfig(medium_rpm=1, burst_multiplier=1.0),
            )
        )
        charged: list[str] = []
        allow = adapter.rate_limiter.allow

        def counting_allow(risk: str) -> bool:
            charged.append(risk)
            return allow(risk)

        adapter.rate_limiter.allow = counting_allow  # type: ignore[method-assign]
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()
        call = {"tool_name": "Skill", "tool_input": {"skill": "checkpoint"}}
        assert _pre_decision(await pre(call, "s1", None)) is None
        assert _is_allowed(await callback("Skill", call["tool_input"], None))
        assert charged == ["medium"]

    async def test_rate_limited_call_reserves_no_checkpoint(
        self, tmp_path: Path
    ) -> None:
        # A denied call never runs, so no PostToolUse hook would release a
        # reservation it took. The rate check comes first.
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                strict_mode=True,
                rate_limit=RateLimitConfig(high_rpm=1, burst_multiplier=1.0),
            )
        )
        adapter.create_checkpoint(scope=["*"], reason="test")
        pre = adapter._make_pretooluse_safety_hook()
        assert adapter.rate_limiter.allow("high")  # use the only token
        denied = await pre({"tool_name": "Write", "tool_input": {}}, "w1", None)
        assert _pre_decision(denied) == "deny"
        assert "Rate limited" in _pre_reason(denied)
        assert adapter.checkpoint_tracker.validate_and_reserve("w2")[0]

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
        pre = test_adapter._make_pretooluse_safety_hook()
        call = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/t.txt", "content": "x"},
        }

        # First 2 should succeed
        for n in range(2):
            test_adapter.create_checkpoint(scope=["*"], reason="rate test")
            assert _pre_decision(await pre(call, f"w{n}", None)) is None

        # 3rd should be rate limited
        test_adapter.create_checkpoint(scope=["*"], reason="rate test")
        result = await pre(call, "w2", None)
        assert _pre_decision(result) == "deny"
        assert "rate limit" in _pre_reason(result).lower()


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
