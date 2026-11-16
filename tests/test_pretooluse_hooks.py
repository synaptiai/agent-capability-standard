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
        hook = strict_adapter._make_pretooluse_safety_hook()

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
        hook = strict_adapter._make_pretooluse_safety_hook()

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
        hook = strict_adapter._make_pretooluse_safety_hook()

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
        hook = strict_adapter._make_pretooluse_safety_hook()

        result = await hook(
            {"tool_name": "Read", "tool_input": {"path": "test.txt"}},
            "tool_aaa",
            None,
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_allows_grep_always(self, strict_adapter: GroundedAgentAdapter):
        """Test that Grep is always allowed."""
        hook = strict_adapter._make_pretooluse_safety_hook()

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
        hook = lenient_adapter._make_pretooluse_safety_hook()

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
        hook = strict_adapter._make_pretooluse_safety_hook()

        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/test"}},
            "tool_ddd",
            None,
        )

        assert _decision(result) == "deny"

    @pytest.mark.asyncio
    async def test_allows_readonly_bash(self, strict_adapter: GroundedAgentAdapter):
        """Test that read-only Bash commands are allowed."""
        hook = strict_adapter._make_pretooluse_safety_hook()

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


def _hooks(entry) -> list:
    return entry["hooks"] if isinstance(entry, dict) else entry.hooks


async def _fire(wrapped, event: str, input_data: dict) -> None:
    for entry in wrapped.hooks[event]:
        for hook in _hooks(entry):
            await hook(input_data, None, None)


class TestTurnEndReleasesLeftoverReservation:
    """A call another hook denies after the adapter's PreToolUse hook
    reserved for it never runs, so nothing else ends its reservation. When
    the session's turn (or the subagent) ends, it is released -- and only
    reservations taken in that session by that agent."""

    @staticmethod
    def _write(session: str, agent: str | None = None) -> dict:
        data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "a.txt"},
            "session_id": session,
        }
        if agent is not None:
            data["agent_id"] = agent
        return data

    async def _reserve(self, adapter, wrapped, call: dict, holder: str) -> None:
        (pre,) = _hooks(wrapped.hooks["PreToolUse"][-1])
        assert await pre(call, holder, None) == {}
        assert not adapter.checkpoint_tracker.validate_and_reserve("probe")[0]

    @pytest.mark.asyncio
    async def test_stop_uses_its_sessions_hold_and_ends_validity(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """STANDARD 1.2.0 §5.18.6: a hold the layer cannot resolve counts as
        used, and the end of a turn is an execution boundary."""
        stop_calls: list[str] = []

        async def caller_stop(input_data, tool_use_id, context):
            stop_calls.append(input_data["session_id"])
            return {}

        wrapped = strict_adapter.wrap_options(
            ClaudeAgentOptions(hooks={"Stop": [{"hooks": [caller_stop]}]})
        )
        strict_adapter.create_checkpoint(["*"], "Test")
        await self._reserve(strict_adapter, wrapped, self._write("s1"), "denied")

        tracker = strict_adapter.checkpoint_tracker
        held = tracker.held_by("denied")
        assert held is not None

        await _fire(wrapped, "Stop", {"hook_event_name": "Stop", "session_id": "s1"})

        assert stop_calls == ["s1"]
        assert tracker.validate_and_reserve("next") == (False, None)
        used = tracker.get_checkpoint_by_id(held)
        assert used is not None and used.consumed
        assert used.metadata["consumed_by"] == "unresolved hold at turn end"

    @pytest.mark.asyncio
    async def test_stop_of_another_session_keeps_the_reservation(
        self, strict_adapter: GroundedAgentAdapter
    ):
        wrapped = strict_adapter.wrap_options(ClaudeAgentOptions())
        strict_adapter.create_checkpoint(["*"], "Test")
        await self._reserve(strict_adapter, wrapped, self._write("s2"), "in_flight")
        tracker = strict_adapter.checkpoint_tracker
        held = tracker.held_by("in_flight")

        await _fire(wrapped, "Stop", {"hook_event_name": "Stop", "session_id": "s1"})

        # One adapter is one scope: s1's Stop ends the validity of every
        # checkpoint, but s2's call keeps its hold, and is refused (F501)
        # when it is allowed.
        assert not tracker.validate_and_reserve("next")[0]
        assert tracker.held_by("in_flight") == held
        assert tracker.consume_if_valid("in_flight") is None

    @pytest.mark.asyncio
    async def test_main_stop_keeps_a_subagents_reservation(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """A background subagent can still be mid-call when the main turn
        ends; its own SubagentStop resolves what it left: the hold counts as
        used (STANDARD 1.2.0 §5.18.6)."""
        wrapped = strict_adapter.wrap_options(ClaudeAgentOptions())
        strict_adapter.create_checkpoint(["*"], "Test")
        await self._reserve(
            strict_adapter, wrapped, self._write("s1", agent="sub1"), "sub_call"
        )
        tracker = strict_adapter.checkpoint_tracker
        held = tracker.held_by("sub_call")

        await _fire(wrapped, "Stop", {"hook_event_name": "Stop", "session_id": "s1"})
        assert not tracker.validate_and_reserve("next")[0]
        assert tracker.held_by("sub_call") == held

        await _fire(
            wrapped,
            "SubagentStop",
            {"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "sub1"},
        )
        assert tracker.held_by("sub_call") is None
        used = tracker.get_checkpoint_by_id(held)
        assert used is not None and used.consumed

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_reserves_under_the_input_tool_use_id(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """With no tool_use_id argument the hook uses the one in the input,
        so the reservation is named and scoped rather than anonymous."""
        wrapped = strict_adapter.wrap_options(ClaudeAgentOptions())
        strict_adapter.create_checkpoint(["*"], "Test")
        (pre,) = _hooks(wrapped.hooks["PreToolUse"][-1])
        call = {**self._write("s1"), "tool_use_id": "w1"}
        assert await pre(call, None, None) == {}
        tracker = strict_adapter.checkpoint_tracker
        held = tracker.held_by("w1")
        assert tracker.validate_and_reserve("w1") == (True, held)  # same holder
        assert tracker.resolve_holds_in_scope(("s1", None)) == ["w1"]
        used = tracker.get_checkpoint_by_id(held)
        assert used is not None and used.consumed

    @pytest.mark.asyncio
    async def test_post_hook_consumes_when_the_run_input_is_not_gated(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Another hook rewrote a destructive command to a read-only one: a
        call that ran uses the hold it took, whatever input it ran with
        (STANDARD 1.2.0 §5.18.6)."""
        wrapped = strict_adapter.wrap_options(ClaudeAgentOptions())
        strict_adapter.create_checkpoint(["*"], "Test")
        (pre,) = _hooks(wrapped.hooks["PreToolUse"][-1])
        bash = {"tool_name": "Bash", "session_id": "s1"}
        destructive = {**bash, "tool_input": {"command": "rm -rf build"}}
        assert await pre(destructive, "b1", None) == {}

        ran = {**bash, "tool_input": {"command": "ls"}, "tool_response": {}}
        for entry in wrapped.hooks["PostToolUse"]:
            for hook in _hooks(entry):
                await hook(ran, "b1", None)

        assert strict_adapter.checkpoint_tracker.validate_and_reserve("next") == (
            False,
            None,
        )

    @pytest.mark.asyncio
    async def test_stop_leaves_a_later_holders_reservation(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """A recorded call that already finished does not release a
        reservation another call took afterwards."""
        wrapped = strict_adapter.wrap_options(ClaudeAgentOptions())
        strict_adapter.create_checkpoint(["*"], "Test")
        tracker = strict_adapter.checkpoint_tracker
        await self._reserve(strict_adapter, wrapped, self._write("s1"), "done")
        assert tracker.release_reservation("done")
        assert tracker.validate_and_reserve("other_session_call")[0]

        await _fire(wrapped, "Stop", {"hook_event_name": "Stop", "session_id": "s1"})

        assert not tracker.validate_and_reserve("next")[0]


# =============================================================================
# PreToolUse Exception Handling Tests (Issue 12)
# =============================================================================


class TestMalformedBashInput:
    """A Bash call whose input cannot be read is a checkpoint-gated
    mutation, not a mapper error the hook would let through."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_input", [None, "rm -rf /", ["rm"], 7])
    async def test_non_dict_bash_input_needs_a_checkpoint(
        self, strict_adapter: GroundedAgentAdapter, tool_input: object
    ):
        hook = strict_adapter._make_pretooluse_safety_hook()
        result = await hook({"tool_name": "Bash", "tool_input": tool_input}, "b1", None)
        assert _decision(result) == "deny"


class TestPreToolUseExceptionHandling:
    """Tests for PreToolUse hook exception handling."""

    @pytest.mark.asyncio
    async def test_unclassified_tool_needs_a_checkpoint_in_strict_mode(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """For a tool in allowed_tools this hook is the only check that
        runs, so a tool the mapper cannot classify must not pass unchecked:
        it is treated as a high-risk mutation."""
        from unittest.mock import MagicMock

        hook = strict_adapter._make_pretooluse_safety_hook()
        strict_adapter.mapper.map_tool = MagicMock(  # type: ignore[assignment]
            side_effect=RuntimeError("mapper exploded at /secret/path")
        )
        call = {"tool_name": "Read", "tool_input": {}}

        denied = await hook(call, "r1", None)
        assert _decision(denied) == "deny"
        assert "/secret/path" not in _reason(denied)

        strict_adapter.create_checkpoint(["*"], "Test")
        assert await hook(call, "r2", None) == {}

    @pytest.mark.asyncio
    async def test_unclassified_tool_charges_the_high_risk_limit(
        self, strict_adapter: GroundedAgentAdapter
    ):
        from unittest.mock import MagicMock

        charged: list[str] = []
        strict_adapter.rate_limiter.allow = lambda risk: charged.append(risk) or True  # type: ignore[method-assign]
        strict_adapter.mapper.map_tool = MagicMock(  # type: ignore[assignment]
            side_effect=RuntimeError("mapper exploded")
        )
        strict_adapter.create_checkpoint(["*"], "Test")
        hook = strict_adapter._make_pretooluse_safety_hook()

        await hook({"tool_name": "Read", "tool_input": {}}, "r1", None)

        assert charged == ["high"]

    @pytest.mark.asyncio
    async def test_exception_in_reservation_denies_in_strict_mode(
        self, strict_adapter: GroundedAgentAdapter
    ):
        from unittest.mock import MagicMock

        strict_adapter.create_checkpoint(["*"], "Test")
        hook = strict_adapter._make_pretooluse_safety_hook()
        strict_adapter.checkpoint_tracker.validate_and_reserve = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("tracker broken at /secret/path")
        )

        result = await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)

        assert _decision(result) == "deny"
        assert "/secret/path" not in _reason(result)

    @pytest.mark.asyncio
    async def test_exception_in_reservation_allows_in_non_strict_mode(
        self, lenient_adapter: GroundedAgentAdapter, caplog: pytest.LogCaptureFixture
    ):
        """Non-strict mode logs instead of denying, as it does for a
        missing checkpoint."""
        from unittest.mock import MagicMock

        lenient_adapter.create_checkpoint(["*"], "Test")
        hook = lenient_adapter._make_pretooluse_safety_hook()
        lenient_adapter.checkpoint_tracker.validate_and_reserve = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("tracker broken")
        )

        with caplog.at_level("ERROR", logger="grounded_agency.adapter"):
            result = await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)

        assert result == {}
        assert "PreToolUse safety check failed" in caplog.text
        assert "tracker broken" in caplog.text  # with the traceback

    @pytest.mark.asyncio
    async def test_exception_in_rate_limiter_denies(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """The rate limit fails closed, as it did in the permission callback."""
        from unittest.mock import MagicMock

        hook = strict_adapter._make_pretooluse_safety_hook()
        strict_adapter.rate_limiter.allow = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("limiter exploded")
        )

        result = await hook({"tool_name": "Read", "tool_input": {}}, "r1", None)

        assert _decision(result) == "deny"
        assert _reason(result).startswith(
            "R407 SAFETY_CHECK_FAILED: the rate limit check"
        )


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


def _write_marker(
    project_dir: Path, expires_in: int = 1800, commit: str | None = None
) -> None:
    marker_dir = project_dir / ".claude"
    marker_dir.mkdir(exist_ok=True)
    now = int(time.time())
    marker: dict[str, object] = {
        "checkpoint_id": "chk_stdin_test",
        "created_at": now,
        "expires_at": now + expires_in,
    }
    if commit is not None:
        marker["commit"] = commit
        # As posttooluse_take_checkpoint.sh does: the commit is entered
        # before the marker names it.
        commits = marker_dir / "checkpoints" / "commits"
        commits.mkdir(parents=True, exist_ok=True)
        (commits / commit).touch()
    (marker_dir / "checkpoint.ok").write_text(json.dumps(marker))


@needs_bash_and_jq
class TestShellPreToolUseHookStdin:
    """The shell hook reads Claude Code's JSON from stdin and blocks with exit 2."""

    @pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
    def test_blocks_file_tools_without_marker(self, tmp_path: Path, tool: str):
        result = _run_shell_hook(
            {"tool_name": tool, "tool_input": {"file_path": "a.py"}}, tmp_path
        )
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert "missing checkpoint marker" in result.stderr.lower()
        assert result.stdout == ""

    def test_blocks_mutating_bash_without_marker(self, tmp_path: Path):
        result = _run_shell_hook(
            {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}},
            tmp_path,
        )
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")

    def test_read_only_bash_needs_no_marker(self, tmp_path: Path):
        """A command on the read-only list, a subset of the SDK mapper's,
        is an observe call: allowed without a marker (STANDARD 1.2.0
        §5.18.3)."""
        result = _run_shell_hook(
            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, tmp_path
        )
        assert result.returncode == 0
        assert result.stdout == ""

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
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
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


def _gated_hook(
    tool_call: dict,
    project_dir: Path,
    approval: str | None = None,
    path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env.pop("ACS_HOOK_APPROVAL", None)
    if approval is not None:
        env["ACS_HOOK_APPROVAL"] = approval
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        ["bash", str(SHELL_HOOK)],
        input=json.dumps(tool_call),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _bash(command: str, mode: str = "default", call: str = "b1") -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "permission_mode": mode,
        "tool_use_id": call,
    }


def _write_call(mode: str = "default", call: str = "w1") -> dict:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": "a.py"},
        "permission_mode": mode,
        "tool_use_id": call,
    }


@needs_bash_and_jq
class TestShellHookSection518:
    """The plugin's PreToolUse hook under STANDARD 1.2.0 §5.18: one marker
    per gated call, approval asked in the modes that reach a person, the
    single-command git stash classes, rollback history."""

    def test_the_marker_is_used_up_by_one_write(self, tmp_path: Path):
        _write_marker(tmp_path)
        first = _gated_hook(_write_call(call="w1"), tmp_path, approval="off")
        second = _gated_hook(_write_call(call="w2"), tmp_path, approval="off")
        assert first.returncode == 0
        assert second.returncode == 2
        assert second.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        used = list((tmp_path / ".claude" / "checkpoints" / "used").iterdir())
        assert [p.name.rsplit(".", 1)[0] for p in used] == ["chk_stdin_test.w1"]

    def test_read_only_bash_leaves_the_marker(self, tmp_path: Path):
        _write_marker(tmp_path)
        assert _gated_hook(_bash("git status"), tmp_path).returncode == 0
        assert (tmp_path / ".claude" / "checkpoint.ok").exists()

    def test_git_stash_create_needs_no_marker(self, tmp_path: Path):
        result = _gated_hook(_bash('git stash create "checkpoint:x"'), tmp_path)
        assert result.returncode == 0
        assert result.stdout == ""

    @pytest.mark.parametrize(
        "command",
        [
            "git stash store -m m 0123456789abcdef0123456789abcdef01234567",
            "git stash pop && rm -rf x",
            "rg --pre cat x",
            "tree -R -H . -o out",
            "file -C x",
            "file -bC x",
            "git stash show --output=f",
            "git stash list --output=f",
            "git log --output=f",
            "git -C d stash list",
        ],
    )
    def test_these_need_the_marker(self, tmp_path: Path, command: str):
        result = _gated_hook(_bash(command), tmp_path)
        assert result.returncode == 2, command
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command

    @pytest.mark.parametrize(
        "command", ["git status " + "a" * 100_000, "git status " + "a " * 2100]
    )
    def test_a_line_over_4096_bytes_needs_the_marker(
        self, tmp_path: Path, command: str
    ):
        """The word splitter reads one character at a time, each read
        costing time that grows with the line: a ~100 KB line under a UTF-8
        locale held the hook past Claude Code's 60-second limit, after which
        the call runs unchecked. A line over 4096 bytes is not read: it is
        mutate, decided at once."""
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "LC_ALL": "C.UTF-8"}
        started = time.monotonic()
        result = subprocess.run(
            ["bash", str(SHELL_HOOK)],
            input=json.dumps(_bash(command)),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert time.monotonic() - started < 10
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")

    def test_a_line_of_4096_bytes_is_still_read(self, tmp_path: Path):
        command = "git status " + "a " * 2040
        assert len(command) <= 4096
        result = _gated_hook(_bash(command), tmp_path)
        assert result.returncode == 0

    def test_rollback_restores_only_a_recorded_checkpoint(self, tmp_path: Path):
        """`git stash pop|apply <commit>` is a rollback only for the full id
        of a commit a marker recorded: git applies any merge commit as if it
        were a stash, so anything else is a gated mutation."""
        sha = "0123456789abcdef0123456789abcdef01234567"
        other = "89abcdef0123456789abcdef0123456789abcdef"
        for command in (f"git stash apply {sha}", "git stash pop"):
            refused = _gated_hook(_bash(command), tmp_path)
            assert refused.returncode == 2, command
            assert refused.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command

        _write_marker(tmp_path, commit=sha)
        # The marker's own commit: a rollback that uses nothing.
        kept = _gated_hook(_bash(f"git stash apply {sha}"), tmp_path)
        assert (kept.returncode, kept.stdout) == (0, "")
        assert (tmp_path / ".claude" / "checkpoint.ok").exists()
        assert _gated_hook(_write_call(), tmp_path, approval="off").returncode == 0
        # The marker was used; a used checkpoint can still be restored.
        assert not (tmp_path / ".claude" / "checkpoint.ok").exists()
        allowed = _gated_hook(_bash(f"git stash pop {sha}"), tmp_path)
        assert (allowed.returncode, allowed.stdout) == (0, "")
        for command in (
            f"git stash apply {other}",
            f"git stash apply {sha[:12]}",
            f"git stash apply --index {sha}",
            "git stash apply",
            "git stash apply stash@{0}",
        ):
            gated = _gated_hook(_bash(command), tmp_path)
            assert gated.returncode == 2, command
            assert gated.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command

    @pytest.mark.parametrize("mode", ["default", "acceptEdits", "plan"])
    def test_a_gated_call_asks_in_a_prompting_mode(self, tmp_path: Path, mode: str):
        _write_marker(tmp_path)
        result = _gated_hook(_write_call(mode), tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "ask"
        assert decision["permissionDecisionReason"].startswith(
            "F502 APPROVAL_REQUIRED: Write (capability 'mutate') requires approval"
        )

    @pytest.mark.parametrize("mode", ["bypassPermissions", "auto", "dontAsk"])
    def test_another_mode_is_f502_and_keeps_the_marker(self, tmp_path: Path, mode: str):
        _write_marker(tmp_path)
        result = _gated_hook(_write_call(mode), tmp_path)
        assert result.returncode == 2
        assert result.stderr.startswith(
            f"F502 APPROVAL_REQUIRED: permission mode '{mode}' does not put this call to a person"
        )
        assert (tmp_path / ".claude" / "checkpoint.ok").exists()

    def test_approval_off_prints_nothing(self, tmp_path: Path):
        _write_marker(tmp_path)
        result = _gated_hook(_write_call("bypassPermissions"), tmp_path, approval="off")
        assert result.returncode == 0
        assert result.stdout == ""

    def test_no_jq_is_r407(self, tmp_path: Path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for tool in ("bash", "cat", "date", "printf"):
            found = shutil.which(tool)
            if found:
                (bin_dir / tool).symlink_to(found)
        result = _gated_hook(_write_call(), tmp_path, path=str(bin_dir))
        assert result.returncode == 2
        assert result.stderr.startswith(
            "R407 SAFETY_CHECK_FAILED: cannot read the tool call"
        )

    def test_two_concurrent_writes_on_one_marker(self, tmp_path: Path):
        """The marker is taken by one rename: exactly one call passes."""
        import concurrent.futures

        for _ in range(5):
            _write_marker(tmp_path)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(
                    pool.map(
                        lambda n: _gated_hook(
                            _write_call(call=f"c{n}"), tmp_path, approval="off"
                        ),
                        range(4),
                    )
                )
            assert sorted(r.returncode for r in results) == [0, 2, 2, 2]
