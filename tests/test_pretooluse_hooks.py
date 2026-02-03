"""
Tests for PreToolUse checkpoint enforcement hooks.

Verifies that the PreToolUse hook correctly blocks mutation tools
when no checkpoint exists and allows them when one does.
"""

from __future__ import annotations

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from grounded_agency import GroundedAgentAdapter

# =============================================================================
# PreToolUse Hook Tests
# =============================================================================


class TestPreToolUseCheckpointHook:
    """Tests for the PreToolUse checkpoint enforcement hook."""

    @pytest.mark.asyncio
    async def test_blocks_write_without_checkpoint(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Test that Write is blocked when no checkpoint exists."""
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": "test.txt"}},
            "tool_123",
            None,
        )

        assert result.get("permissionDecision") == "deny"
        assert "requires checkpoint" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_blocks_edit_without_checkpoint(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Test that Edit is blocked when no checkpoint exists."""
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "test.txt"}},
            "tool_456",
            None,
        )

        assert result.get("permissionDecision") == "deny"

    @pytest.mark.asyncio
    async def test_allows_write_with_checkpoint(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Test that Write is allowed when checkpoint exists."""
        strict_adapter.create_checkpoint(["*"], "Test checkpoint")
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": "test.txt"}},
            "tool_789",
            None,
        )

        # Should return empty dict (no denial)
        assert result == {} or "permissionDecision" not in result

    @pytest.mark.asyncio
    async def test_allows_read_always(self, strict_adapter: GroundedAgentAdapter):
        """Test that Read is always allowed (no checkpoint needed)."""
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Read", "tool_input": {"path": "test.txt"}},
            "tool_aaa",
            None,
        )

        assert result == {} or "permissionDecision" not in result

    @pytest.mark.asyncio
    async def test_allows_grep_always(self, strict_adapter: GroundedAgentAdapter):
        """Test that Grep is always allowed."""
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Grep", "tool_input": {"pattern": "test"}},
            "tool_bbb",
            None,
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_lenient_mode_warns_but_allows(
        self, lenient_adapter: GroundedAgentAdapter
    ):
        """Test that non-strict mode doesn't deny mutations."""
        hook = lenient_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": "test.txt"}},
            "tool_ccc",
            None,
        )

        # In non-strict mode, should NOT deny
        assert result.get("permissionDecision") != "deny"

    @pytest.mark.asyncio
    async def test_blocks_destructive_bash(self, strict_adapter: GroundedAgentAdapter):
        """Test that destructive Bash commands are blocked."""
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/test"}},
            "tool_ddd",
            None,
        )

        assert result.get("permissionDecision") == "deny"

    @pytest.mark.asyncio
    async def test_allows_readonly_bash(self, strict_adapter: GroundedAgentAdapter):
        """Test that read-only Bash commands are allowed."""
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
            "tool_eee",
            None,
        )

        assert result == {}


# =============================================================================
# PreToolUse Hook in wrap_options Tests
# =============================================================================


class TestPreToolUseInWrapOptions:
    """Tests that PreToolUse hooks are properly injected by wrap_options."""

    def test_wrap_options_includes_pretooluse(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Test that wrap_options adds PreToolUse hooks."""
        base = ClaudeAgentOptions()
        wrapped = strict_adapter.wrap_options(base)

        assert "PreToolUse" in wrapped.hooks
        assert len(wrapped.hooks["PreToolUse"]) >= 1

    def test_wrap_options_preserves_existing_pretooluse(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Test that existing PreToolUse hooks are preserved."""
        existing_hook = {"hooks": [lambda: None]}
        base = ClaudeAgentOptions(hooks={"PreToolUse": [existing_hook]})
        wrapped = strict_adapter.wrap_options(base)

        # Should have existing + new
        assert len(wrapped.hooks["PreToolUse"]) >= 2

    def test_wrap_options_has_both_pre_and_post(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Test that wrap_options includes both PreToolUse and PostToolUse."""
        base = ClaudeAgentOptions()
        wrapped = strict_adapter.wrap_options(base)

        assert "PreToolUse" in wrapped.hooks
        assert "PostToolUse" in wrapped.hooks


# =============================================================================
# PreToolUse Exception Handling Tests (Issue 12)
# =============================================================================


class TestPreToolUseExceptionHandling:
    """Tests for PreToolUse hook exception handling."""

    @pytest.mark.asyncio
    async def test_exception_in_mapper_returns_empty_dict(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Test that an exception in the mapper returns {} (fail-open for hooks).

        The catch-all except in the PreToolUse hook returns {} on error,
        which means 'no opinion' — allowing the tool to proceed. This is
        intentional: PreToolUse is defense-in-depth, and the permission
        callback provides the primary enforcement.
        """
        from unittest.mock import MagicMock

        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        # Replace mapper with one that raises
        strict_adapter.mapper.map_tool = MagicMock(  # type: ignore[assignment]
            side_effect=RuntimeError("mapper exploded")
        )

        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": "test.txt"}},
            "tool_err",
            None,
        )

        # Should return empty dict (no denial), not crash
        assert result == {}
