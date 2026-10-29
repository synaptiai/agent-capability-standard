"""
Tests for PreToolUse checkpoint enforcement hooks.

Verifies that the PreToolUse hook correctly blocks mutation tools
when no checkpoint exists and allows them when one does: the SDK adapter's
hook, and the plugin's shell hook as Claude Code runs it (JSON on stdin,
exit 2 with the reason on stderr to block).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from grounded_agency import GroundedAgentAdapter


def _decision(result: dict) -> str | None:
    """The PreToolUse permission decision, as the SDK reads it."""
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


def _reason(result: dict) -> str:
    return result.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


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

        assert _decision(result) == "deny"
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert "requires checkpoint" in _reason(result)

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

        assert _decision(result) == "deny"

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
        assert result == {}

    @pytest.mark.asyncio
    async def test_allows_read_always(self, strict_adapter: GroundedAgentAdapter):
        """Test that Read is always allowed (no checkpoint needed)."""
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Read", "tool_input": {"path": "test.txt"}},
            "tool_aaa",
            None,
        )

        assert result == {}

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
        assert _decision(result) != "deny"

    @pytest.mark.asyncio
    async def test_blocks_destructive_bash(self, strict_adapter: GroundedAgentAdapter):
        """Test that destructive Bash commands are blocked."""
        hook = strict_adapter._make_pretooluse_checkpoint_hook()

        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/test"}},
            "tool_ddd",
            None,
        )

        assert _decision(result) == "deny"

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


# =============================================================================
# Plugin shell hook (hooks/pretooluse_require_checkpoint.sh)
# =============================================================================

SHELL_HOOK = (
    Path(__file__).resolve().parents[1] / "hooks" / "pretooluse_require_checkpoint.sh"
)

needs_bash_and_jq = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the shell hook needs bash, and jq to read the tool call",
)


def _run_shell_hook(
    tool_call: dict, project_dir: Path
) -> subprocess.CompletedProcess[str]:
    """Run the hook the way Claude Code does: the tool call as JSON on stdin."""
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        ["bash", str(SHELL_HOOK)],
        input=json.dumps(tool_call),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _write_marker(project_dir: Path, expires_in: int = 1800) -> None:
    marker_dir = project_dir / ".claude"
    marker_dir.mkdir(exist_ok=True)
    now = int(time.time())
    (marker_dir / "checkpoint.ok").write_text(
        json.dumps(
            {
                "checkpoint_id": "chk_stdin_test",
                "created_at": now,
                "expires_at": now + expires_in,
            }
        )
    )


@needs_bash_and_jq
class TestShellPreToolUseHookStdin:
    """The shell hook reads Claude Code's JSON from stdin and blocks with exit 2."""

    @pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
    def test_blocks_file_tools_without_marker(self, tmp_path: Path, tool: str):
        result = _run_shell_hook(
            {"tool_name": tool, "tool_input": {"file_path": "a.py"}}, tmp_path
        )
        assert result.returncode == 2
        assert "missing checkpoint marker" in result.stderr.lower()
        assert result.stdout == ""

    def test_blocks_mutating_bash_without_marker(self, tmp_path: Path):
        result = _run_shell_hook(
            {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}},
            tmp_path,
        )
        assert result.returncode == 2
        assert "blocked" in result.stderr.lower()

    def test_blocks_every_bash_call_without_marker(self, tmp_path: Path):
        """A command is not trusted to be read-only: the hook fails closed."""
        result = _run_shell_hook(
            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, tmp_path
        )
        assert result.returncode == 2

    def test_allows_write_with_valid_marker(self, tmp_path: Path):
        _write_marker(tmp_path)
        result = _run_shell_hook(
            {"tool_name": "Write", "tool_input": {"file_path": "a.py"}}, tmp_path
        )
        assert result.returncode == 0

    def test_blocks_and_removes_expired_marker(self, tmp_path: Path):
        _write_marker(tmp_path, expires_in=-60)
        result = _run_shell_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}, tmp_path
        )
        assert result.returncode == 2
        assert "expired" in result.stderr.lower()
        assert not (tmp_path / ".claude" / "checkpoint.ok").exists()

    def test_allows_non_mutation_tool(self, tmp_path: Path):
        result = _run_shell_hook(
            {"tool_name": "Read", "tool_input": {"file_path": "a.py"}}, tmp_path
        )
        assert result.returncode == 0

    def test_argument_payload_still_accepted(self, tmp_path: Path):
        """A payload passed as $1 is read instead of stdin."""
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(SHELL_HOOK), json.dumps({"tool_name": "Write"})],
            input="",
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 2
