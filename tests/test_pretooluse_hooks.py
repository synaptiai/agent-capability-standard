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
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from grounded_agency import GroundedAgentAdapter
from grounded_agency.adapter import SAFETY_HOOK_TIMEOUT_S
from tests.conftest import (
    GNU_GREP,
    SHELL_SCAN_PENDING,
    assert_linear,
    enter_checkpoint_commit,
)


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

    def test_the_safety_hook_blocks_when_it_fails_in_the_cli(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """STANDARD 1.2.0 §5.18.8: the hook refuses with R407 when a check
        fails inside it, but a callback that fails or gives no verdict in
        time, as the CLI sees it, was no decision there and the call ran.
        Its matcher asks the CLI to block instead (as hooks.json does for
        the plugin's hook); a caller's own matcher is left as it was."""
        existing = HookMatcher(hooks=[lambda *_: {}])
        wrapped = strict_adapter.wrap_options(
            ClaudeAgentOptions(hooks={"PreToolUse": [existing]})
        )
        first, safety = wrapped.hooks["PreToolUse"]
        assert first is existing and first.on_failure is None
        (fn,) = safety.hooks
        assert getattr(fn, "_grounded_adapter", None) is strict_adapter
        assert safety.on_failure == "block"
        # Its time limit is stated, not left to the SDK's default.
        assert safety.timeout == SAFETY_HOOK_TIMEOUT_S == 60
        # The other hooks keep the SDK's default.
        for event, matchers in wrapped.hooks.items():
            for entry in matchers:
                if entry is not safety:
                    assert getattr(entry, "on_failure", None) is None, event
                    assert getattr(entry, "timeout", None) is None, event

    @pytest.mark.asyncio
    async def test_a_long_input_is_decided_well_within_the_time_limit(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """The secret check of a persist call reads its input in time linear
        in its length: a TodoWrite (persist) with 1 MB of padding before an
        AWS key is refused F504 in about half a second, where the patterns
        before security round 1's fifth batch took 64 s at 290 KB, past the
        CLI's time limit (which then blocks, on_failure="block")."""
        hook = strict_adapter._make_pretooluse_safety_hook()
        todos = [
            {"content": "a" * 1_000_000, "status": "pending"},
            {"content": "deploy key AKIAABCDEFGHIJKLMNOP", "status": "pending"},
        ]
        started = time.perf_counter()
        out = await hook(
            {
                "tool_name": "TodoWrite",
                "tool_input": {"todos": todos},
                "permission_mode": "bypassPermissions",
            },
            "t-long",
            None,
        )
        elapsed = time.perf_counter() - started
        decision = out["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny"
        assert decision["permissionDecisionReason"].startswith("F504")
        assert elapsed < SAFETY_HOOK_TIMEOUT_S / 6

    def test_without_the_sdk_the_dict_form_carries_it(
        self, strict_adapter: GroundedAgentAdapter, monkeypatch
    ):
        import builtins

        real_import = builtins.__import__

        def no_sdk(name, *args, **kwargs):
            if name == "claude_agent_sdk":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_sdk)
        entry = strict_adapter._wrap_hook(
            lambda *_: {}, on_failure="block", timeout=SAFETY_HOOK_TIMEOUT_S
        )
        assert entry["on_failure"] == "block"
        assert entry["timeout"] == SAFETY_HOOK_TIMEOUT_S
        plain = strict_adapter._wrap_hook(lambda *_: {})
        assert "on_failure" not in plain and "timeout" not in plain


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
    async def test_the_next_prompt_ends_what_a_turn_without_stop_left(
        self, strict_adapter: GroundedAgentAdapter
    ):
        """Claude Code runs StopFailure in place of Stop when an API error
        ended the turn, and an interrupted turn may run neither: the next
        prompt is an execution boundary too (STANDARD 1.2.0 §5.18.6), so a
        checkpoint and a hold the earlier turn left authorise nothing."""
        prompts: list[str] = []

        async def caller_prompt(input_data, tool_use_id, context):
            prompts.append(input_data["prompt"])
            return {}

        wrapped = strict_adapter.wrap_options(
            ClaudeAgentOptions(hooks={"UserPromptSubmit": [{"hooks": [caller_prompt]}]})
        )
        strict_adapter.create_checkpoint(["*"], "Test")
        await self._reserve(strict_adapter, wrapped, self._write("s1"), "left")
        tracker = strict_adapter.checkpoint_tracker
        held = tracker.held_by("left")
        assert held is not None
        strict_adapter.create_checkpoint(["*"], "A second, unheld")
        assert tracker.validate_and_reserve("probe2")[0]
        assert tracker.release_reservation("probe2")

        await _fire(
            wrapped,
            "UserPromptSubmit",
            {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "go"},
        )

        assert prompts == ["go"]
        assert tracker.validate_and_reserve("next") == (False, None)
        used = tracker.get_checkpoint_by_id(held)
        assert used is not None and used.consumed
        assert strict_adapter.call_records[-1]["decision"] == "boundary"

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
        # As posttooluse_take_checkpoint.sh does: the commit is entered, in
        # the project's git directory, before the marker names it.
        enter_checkpoint_commit(project_dir / ".git", commit)
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


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=path,
        env={**os.environ, **_GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _repo(path: Path) -> Path:
    """A git repository with one commit."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "app.txt").write_text("app\n")
    _git(path, "add", "app.txt")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _gated_hook(
    tool_call: dict,
    project_dir: Path,
    approval: str | None = None,
    path: str | None = None,
    timeout: float = 30,
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
        timeout=timeout,
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


def _write_to(file_path: str) -> dict:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": ""},
        "tool_use_id": "w1",
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
        of a commit a checkpoint recorded: git applies any merge commit as
        if it were a stash, so anything else is a gated mutation."""
        _repo(tmp_path)
        sha = "0123456789abcdef0123456789abcdef01234567"
        other = "89abcdef0123456789abcdef0123456789abcdef"
        for command in (f"git stash apply {sha}", "git stash pop"):
            refused = _gated_hook(_bash(command), tmp_path)
            assert refused.returncode == 2, command
            assert refused.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command

        _write_marker(tmp_path, commit=sha)
        # The commit the checkpoint entered: a rollback that uses nothing.
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
        # Beside the project: the hook drops the project's directories from
        # PATH.
        bin_dir = tmp_path.parent / f"{tmp_path.name}-bin"
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


def _bypass(tool_call: dict) -> dict:
    return {**tool_call, "permission_mode": "bypassPermissions"}


@needs_bash_and_jq
class TestShellHookTimeBound:
    """A run that outlives the hook's time limit gives no verdict, and a
    Claude Code without onFailure "block" then runs the call unchecked: the
    hook must decide a padded command in bounded time."""

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf a.txt" + " " * 50_000,
            "rm -rf a.txt" + "\t" * 50_000,
            " " * 200_000 + "rm -rf a.txt",
            "ls" + " " * 50_000,
        ],
    )
    def test_a_command_padded_with_blanks_is_decided_at_once(
        self, tmp_path: Path, command: str
    ):
        """The trims ran before the 4096-byte bound: 50,000 trailing blanks
        took 44 s and 200,000 leading ones over 40 s. The length is now
        checked first: a padded command is mutate, decided in bounded time."""
        started = time.monotonic()
        result = _gated_hook(_bypass(_bash(command)), tmp_path)
        assert time.monotonic() - started < 10
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")

    def test_the_hook_blocks_a_call_when_it_fails_or_times_out(self):
        """hooks.json asks Claude Code to block the call when the hook
        fails, or gives no verdict within its time limit."""
        hooks = json.loads(
            (SHELL_HOOK.parent / "hooks.json").read_text(encoding="utf-8")
        )["hooks"]["PreToolUse"]
        (group,) = hooks
        (hook,) = group["hooks"]
        assert hook["command"].endswith("/hooks/pretooluse_require_checkpoint.sh")
        assert hook["onFailure"] == "block"
        assert isinstance(hook["timeout"], int) and 0 < hook["timeout"] <= 60


@needs_bash_and_jq
class TestShellHookRoutesEveryTool:
    """STANDARD 1.2.0 §5.18.2: a call of a tool with no binding is a
    mutation that needs a checkpoint and approval. Claude Code routes every
    tool to the hook; only the mapper's tools that need neither pass."""

    def test_every_tool_is_routed_to_the_hook(self):
        hooks = json.loads(
            (SHELL_HOOK.parent / "hooks.json").read_text(encoding="utf-8")
        )["hooks"]["PreToolUse"]
        assert [group["matcher"] for group in hooks] == ["*"]

    @pytest.mark.parametrize(
        "tool_call",
        [
            {"tool_name": "Monitor", "tool_input": {"command": "rm -rf a.txt"}},
            {"tool_name": "PowerShell", "tool_input": {"command": "Remove-Item a"}},
            {
                "tool_name": "mcp__github__push_files",
                "tool_input": {"files": [{"path": "a", "content": "b"}]},
            },
            {
                "tool_name": "ExitWorktree",
                "tool_input": {"action": "remove", "discard_changes": True},
            },
            {"tool_name": "EnterWorktree", "tool_input": {}},
            {"tool_name": "SomeFutureTool", "tool_input": {}},
        ],
    )
    def test_an_unbound_tool_needs_a_checkpoint(self, tmp_path: Path, tool_call):
        refused = _gated_hook(_bypass(tool_call), tmp_path, approval="off")
        assert refused.returncode == 2, tool_call
        assert refused.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), tool_call
        # Approval too: with no person to ask, F502.
        _write_marker(tmp_path)
        blocked = _gated_hook(_bypass(tool_call), tmp_path)
        assert blocked.returncode == 2
        assert blocked.stderr.startswith("F502 APPROVAL_REQUIRED: ")
        asked = _gated_hook({**tool_call, "permission_mode": "default"}, tmp_path)
        assert asked.returncode == 0
        decision = json.loads(asked.stdout)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "ask"
        assert decision["permissionDecisionReason"].startswith(
            f"F502 APPROVAL_REQUIRED: {tool_call['tool_name']} (unbound: treated as "
            "a mutation, STANDARD 1.2.0 §5.18.2)"
        )
        assert not (tmp_path / ".claude" / "checkpoint.ok").exists()

    @pytest.mark.parametrize("tool", ["Read", "Grep", "Glob", "TodoWrite"])
    def test_a_tool_that_needs_neither_passes(self, tmp_path: Path, tool: str):
        result = _gated_hook(_bypass({"tool_name": tool, "tool_input": {}}), tmp_path)
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


# What a persist tool's input may hold (STANDARD 1.2.0 §5.18.10, §6.7): the
# SDK adapter's verdict on each is the hook's. Text forms, and data forms
# (a value under a member named for a credential, a name/value pair, a
# tuple) that the SDK redactor's data rule finds.
PERSIST_INPUTS = [
    {"todos": [{"content": "buy milk", "status": "pending"}]},
    {"todos": [{"content": "deploy key AKIAIOSFODNN7EXAMPLE", "status": "pending"}]},
    {
        "todos": [
            {
                "content": "deploy with AWS_SECRET_ACCESS_KEY="
                "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "status": "pending",
            }
        ]
    },
    {"subject": "token: rotate monthly", "description": "and the password policy"},
    {"subject": "ghp_" + "a" * 36},
    {"subject": "connect postgres://app:Hunter2Secret@db/prod"},
    {"subject": "connect postgres://app:<password>@db/prod"},
    {"subject": "x", "metadata": {"password": "hunter2"}},
    {"subject": "x", "metadata": {"password": "<your password>"}},
    {"subject": "x", "metadata": {"token": "rotate monthly"}},
    {"subject": "x", "metadata": {"api_key": 12345678901234}},
    {"subject": "x", "metadata": {"secret": True}},
    {"subject": "x", "metadata": {"client_secret": "abc"}},
    {"subject": "x", "metadata": {"apiKey": "[REDACTED]"}},
    {
        "subject": "x",
        "metadata": {
            "headers": [{"name": "Authorization", "value": "Basic Zm9vOmJhcg"}]
        },
    },
    {"subject": "x", "metadata": {"headers": [["Cookie", "sid=abc123"]]}},
    {"subject": "x", "metadata": {"headers": [["Accept", "text/html"]]}},
    {"subject": "x", "metadata": {"db": {"password": {"value": "s3cr3t-v4lue"}}}},
    {"taskId": "1", "status": "completed"},
    {},
]


@needs_bash_and_jq
class TestShellHookPersistSecrets:
    """§5.18.10: the data a persist call stores holds no secret the layer
    recognises (F504), decided by code. TodoWrite, TaskCreate and TaskUpdate
    are persist (the SDK mapper's _TOOL_MAPPINGS) and need neither a
    checkpoint nor approval, so the hook checked nothing of theirs: the
    adapter refused a credential they would store, the plugin let it pass."""

    @pytest.mark.parametrize("mode", ["default", "bypassPermissions"])
    @pytest.mark.parametrize("tool", ["TodoWrite", "TaskCreate", "TaskUpdate"])
    def test_a_credential_a_persist_tool_would_store_is_refused(
        self, tmp_path: Path, tool: str, mode: str
    ):
        """The reported route: an AWS key in a todo's content and in a
        task's subject."""
        tool_call = {
            "tool_name": tool,
            "tool_input": {
                "todos": [
                    {"content": "deploy with AKIAIOSFODNN7EXAMPLE", "status": "pending"}
                ],
                "subject": "key AKIAIOSFODNN7EXAMPLE",
            },
            "permission_mode": mode,
            "tool_use_id": "tu1",
        }
        result = _gated_hook(tool_call, tmp_path)
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr.startswith(
            f"F504 CONSTRAINT_VIOLATED: {tool} (persist): the data it would store "
            "holds what looks like a credential"
        )
        # Nothing was used or written.
        assert not (tmp_path / ".claude").exists()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_input", PERSIST_INPUTS, ids=lambda v: json.dumps(v)[:60]
    )
    async def test_the_hook_and_the_adapter_agree(
        self, tmp_path: Path, strict_adapter: GroundedAgentAdapter, tool_input: dict
    ):
        hook = strict_adapter._make_pretooluse_safety_hook()
        for tool in ("TodoWrite", "TaskCreate"):
            tool_call = {"tool_name": tool, "tool_input": tool_input}
            out = await hook(
                {**tool_call, "permission_mode": "bypassPermissions"}, "t1", None
            )
            sdk = _decision(out) == "deny"
            if sdk:
                assert _reason(out).startswith("F504"), _reason(out)
            result = _gated_hook(_bypass(tool_call), tmp_path)
            assert result.returncode in (0, 2), result.stderr
            assert (result.returncode == 2) == sdk, (tool, result.stderr, _reason(out))
            if result.returncode == 2:
                assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: "), (
                    result.stderr
                )

    @pytest.mark.asyncio
    async def test_they_agree_on_the_credential_vectors(
        self, tmp_path: Path, strict_adapter: GroundedAgentAdapter
    ):
        """The refusal rule's vectors (tests/conformance/secrets/
        credentials.json) that register no value, text and data alike, as a
        todo's content: both refuse what the vector says holds one."""
        path = (
            SHELL_HOOK.parents[1]
            / "tests"
            / "conformance"
            / "secrets"
            / "credentials.json"
        )
        vectors = [
            v
            for v in json.loads(path.read_text(encoding="utf-8"))["vectors"]
            if not v["secret_values"]
        ]
        assert len(vectors) > 40
        hook = strict_adapter._make_pretooluse_safety_hook()
        for v in vectors:
            tool_call = {
                "tool_name": "TodoWrite",
                "tool_input": {"todos": [{"content": v["input"], "status": "pending"}]},
            }
            out = await hook(
                {**tool_call, "permission_mode": "bypassPermissions"}, "t1", None
            )
            result = _gated_hook(_bypass(tool_call), tmp_path)
            refused = result.returncode == 2
            denied = _decision(out) == "deny"
            assert denied == v["expect"]["holds"], v["name"]
            if v["name"] in SHELL_SCAN_PENDING:
                # The shell scan has not yet taken the rule this vector pins.
                assert refused != denied, (v["name"], result.stderr)
            else:
                assert refused == denied, (v["name"], result.stderr)

    # Security round 5, batch 4: the scan read one line at a time, so a
    # value on the line after its name passed the hook (TodoWrite is
    # ungated: stored with no approval) while the adapter refused it.
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("todos", "holds"),
        [
            (
                [
                    {
                        "content": "Set the DB config:\ndb:\n  password:\n"
                        "    Xyz12345abcdef",
                        "status": "pending",
                        "activeForm": "Configuring",
                    }
                ],
                True,
            ),
            ([{"content": "Authorization:\nBearer Xyz12345abcdef"}], True),
            ([{"content": "Bearer\nabcdefghijklmnopqrstuvwxyz"}], True),
            ([{"content": 'API_KEY=\r\n"Xyz12345abc"'}], True),
            # Two strings, a name ending one and a value opening the next:
            # each is read on its own, as the adapter reads each.
            (
                [
                    {"content": "rotate the api_key:", "status": "pending"},
                    {"content": "abc123def456ghi", "status": "pending"},
                ],
                False,
            ),
            ([{"content": "buy milk\nand eggs", "status": "pending"}], False),
        ],
        ids=["reported", "authorization", "bearer", "crlf", "apart", "prose"],
    )
    async def test_a_value_on_the_next_line(
        self,
        tmp_path: Path,
        strict_adapter: GroundedAgentAdapter,
        todos: list[dict],
        holds: bool,
    ):
        tool_call = {"tool_name": "TodoWrite", "tool_input": {"todos": todos}}
        hook = strict_adapter._make_pretooluse_safety_hook()
        out = await hook(
            {**tool_call, "permission_mode": "bypassPermissions"}, "t1", None
        )
        assert (_decision(out) == "deny") == holds
        result = _gated_hook(
            {**tool_call, "permission_mode": "default", "tool_use_id": "t1"},
            tmp_path,
        )
        assert result.returncode == (2 if holds else 0), result.stderr
        if holds:
            assert result.stderr.startswith(
                "F504 CONSTRAINT_VIOLATED: TodoWrite (persist)"
            )

    # Security round 5, batch 6: the plugin holds AUDIT_HMAC_KEY, which signs
    # every audit line and head, and the project's checkpoint key, which
    # signs the checkpoints it records; the scan registered neither, so a
    # todo holding one was stored (§6.7: a host recognises at least the
    # credentials it holds itself).
    AUDIT_KEY = "9f8e7d6c5b4a39281706f5e4d3c2b1a0" * 2
    CHECKPOINT_KEY = "0a1b2c3d4e5f60718293a4b5c6d7e8f9" * 2

    def _todo(self, content: str) -> dict:
        return _bypass(
            {
                "tool_name": "TodoWrite",
                "tool_input": {"todos": [{"content": content, "status": "pending"}]},
            }
        )

    @pytest.mark.parametrize(
        "content",
        [
            "audit key for CI: {key}",
            "export the signing key {key} to the runner",
            "{key}",
        ],
    )
    def test_the_audit_key_a_todo_would_store_is_refused(
        self, tmp_path: Path, content: str
    ):
        todo = self._todo(content.format(key=self.AUDIT_KEY))
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        env["AUDIT_HMAC_KEY"] = self.AUDIT_KEY
        result = subprocess.run(
            ["bash", str(SHELL_HOOK)],
            input=json.dumps(todo),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 2, result.stderr
        assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: TodoWrite")
        # The key is not in the refusal either.
        assert self.AUDIT_KEY not in result.stderr
        # Control: with another key set, the same todo is stored.
        env["AUDIT_HMAC_KEY"] = "another-key-of-the-person"
        result = subprocess.run(
            ["bash", str(SHELL_HOOK)],
            input=json.dumps(todo),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    @pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
    def test_the_checkpoint_key_a_todo_would_store_is_refused(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=30)
        records = tmp_path / ".git" / "acs" / "checkpoints"
        records.mkdir(parents=True)
        (records / "key").write_text(self.CHECKPOINT_KEY)
        result = _gated_hook(self._todo(f"sign with {self.CHECKPOINT_KEY}"), tmp_path)
        assert result.returncode == 2, result.stderr
        assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: TodoWrite")
        # Control: another value of the same shape is stored.
        other = "1" * 64
        assert _gated_hook(self._todo(f"sign with {other}"), tmp_path).returncode == 0
        # A file the take hook would not have written (not 64 hex digits) is
        # not read as a key.
        (records / "key").write_text("short")
        assert _gated_hook(self._todo("sign with short"), tmp_path).returncode == 0

    def test_a_large_input_is_decided_well_within_the_time_limit(self, tmp_path: Path):
        """The scan reads the input in time linear in its length: 1 MB of
        todos before an AWS key is refused in well under the hook's 30
        seconds (hooks.json)."""
        todos = [
            {"content": "a b token: " * 90_000, "status": "pending"},
            {"content": "deploy key AKIAIOSFODNN7EXAMPLE", "status": "pending"},
        ]
        started = time.perf_counter()
        result = _gated_hook(
            _bypass({"tool_name": "TodoWrite", "tool_input": {"todos": todos}}),
            tmp_path,
        )
        elapsed = time.perf_counter() - started
        assert result.returncode == 2 and result.stderr.startswith("F504")
        assert elapsed < 5

    # Security round 4: the member rule tested each name and each value
    # with a regular expression, which jq compiles at each test (about 0.4
    # ms): 40,000 members took about 18 s of the hook's 30, and 120,000
    # placeholders under a secret member about 11 s. String functions read
    # the same input in under 2 s.
    @pytest.mark.parametrize(
        ("make", "count", "refused"),
        [
            (
                lambda n: {
                    **{f"m{i}": f"value {i}" for i in range(n)},
                    "password": "hunter2",
                },
                40_000,
                True,
            ),
            (lambda n: {"password": ["<ab>"] * n}, 120_000, False),
        ],
        ids=["members", "placeholders"],
    )
    def test_many_members_are_decided_in_time(
        self, tmp_path: Path, make: Any, count: int, refused: bool
    ):
        def seconds_at(n: int) -> float:
            data = make(n)
            tool_input = {
                "todos": [{"content": "x", "status": "pending", "meta": data}]
            }
            assert len(json.dumps(tool_input)) <= 1_000_000
            started = time.perf_counter()
            result = _gated_hook(
                _bypass({"tool_name": "TodoWrite", "tool_input": tool_input}),
                tmp_path,
                timeout=60,
            )
            elapsed = time.perf_counter() - started
            assert result.returncode == (2 if refused else 0), result.stderr[:200]
            if refused:
                assert result.stderr.startswith(
                    "F504 CONSTRAINT_VIOLATED: TodoWrite (persist)"
                )
            return elapsed

        if GNU_GREP:
            assert seconds_at(count) < 5
        else:
            assert_linear(seconds_at, count // 2, count)

    # A credential after a long run that each stage reading matches out of
    # the text (grep -o) once read again from each of its positions: a URL
    # scheme's characters (the reported TodoWrite: rc 124 after 30 s under
    # hooks.json's limit) and a user option's name (`.-u` at each third
    # position). grep -o feeds a pipe here, as in the hook; with its output
    # sent to /dev/null grep stops at the first match, which hid it.
    LONG_RUNS = [
        "a" * 100_000
        + " then deploy from https://deploy:Pr0dPassw0rd@db.example.com/app",
        ".-u" * 40_000 + " curl -u deploy:Pr0dPassw0rd2 https://db.example.com/",
        ".-U=" * 30_000 + " curl -U deploy:Pr0dPassw0rd2 https://db.example.com/",
    ]

    @pytest.mark.parametrize("content", LONG_RUNS, ids=["url", "user", "user="])
    def test_a_credential_after_a_long_run_is_decided_in_time(
        self, tmp_path: Path, content: str
    ):
        todos = [{"content": content, "status": "pending", "activeForm": "Deploying"}]
        started = time.perf_counter()
        result = _gated_hook(
            _bypass({"tool_name": "TodoWrite", "tool_input": {"todos": todos}}),
            tmp_path,
            timeout=60,
        )
        elapsed = time.perf_counter() - started
        assert result.returncode == 2, (result.returncode, result.stderr[:200])
        assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: TodoWrite (persist)")
        assert elapsed < 10

    @pytest.mark.asyncio
    @pytest.mark.parametrize("content", LONG_RUNS, ids=["url", "user", "user="])
    async def test_the_adapter_decides_them_in_time_too(
        self, strict_adapter: GroundedAgentAdapter, content: str
    ):
        hook = strict_adapter._make_pretooluse_safety_hook()
        started = time.perf_counter()
        out = await hook(
            {
                "tool_name": "TodoWrite",
                "tool_input": {"todos": [{"content": content, "status": "pending"}]},
                "permission_mode": "bypassPermissions",
            },
            "t-run",
            None,
        )
        assert _decision(out) == "deny" and _reason(out).startswith("F504")
        assert time.perf_counter() - started < SAFETY_HOOK_TIMEOUT_S / 6


def _ship_records(upstream: Path, victim: Path) -> str:
    """An upstream repository whose history holds a merge commit M that
    adds files its main branch never shows, and whose main branch tracks
    an empty .claude/checkpoints/commits/M and a fresh .claude/checkpoint.ok
    naming M; cloned to `victim`. Returns M."""
    _repo(upstream)
    base = _git(upstream, "rev-parse", "HEAD")
    index = _git(upstream, "commit-tree", f"{base}^{{tree}}", "-p", base, "-m", "i")
    (upstream / ".claude").mkdir()
    (upstream / ".claude" / "settings.local.json").write_text(
        '{"permissions": {"allow": ["Bash(*)"]}}'
    )
    (upstream / "setup.sh").write_text("echo planted\n")
    _git(upstream, "add", "-f", ".claude/settings.local.json", "setup.sh")
    tree = _git(upstream, "write-tree")
    merge = _git(upstream, "commit-tree", tree, "-p", base, "-p", index, "-m", "m")
    _git(upstream, "reset", "-q", "--hard", merge)
    _git(upstream, "rm", "-q", ".claude/settings.local.json", "setup.sh")
    commits = upstream / ".claude" / "checkpoints" / "commits"
    commits.mkdir(parents=True)
    (commits / merge).touch()
    now = int(time.time())
    (upstream / ".claude" / "checkpoint.ok").write_text(
        json.dumps(
            {
                "checkpoint_id": "x",
                "commit": merge,
                "created_at": now - 60,
                "expires_at": now + 1740,
            }
        )
    )
    _git(upstream, "add", "-f", ".claude")
    _git(upstream, "commit", "-q", "-m", "records")
    subprocess.run(
        ["git", "clone", "-q", str(upstream), str(victim)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return merge


@needs_bash_and_jq
class TestShellHookTrustsOnlyItsOwnRecords:
    """A rollback restores a checkpoint taken in the scope (STANDARD 1.2.0
    §5.18.3, §5.18.6), and a checkpoint is taken by a call: records a
    repository ships authorise nothing."""

    def test_a_cloned_commit_entry_restores_nothing(self, tmp_path: Path):
        merge = _ship_records(tmp_path / "upstream", tmp_path / "victim")
        victim = tmp_path / "victim"
        assert (victim / ".claude" / "checkpoints" / "commits" / merge).is_file()
        for mode in ("bypassPermissions", "default"):
            result = _gated_hook(_bash(f"git stash apply {merge}", mode), victim)
            assert result.returncode == 2, mode
            assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), mode
        # The shipped marker was refused, not used or removed.
        assert (victim / ".claude" / "checkpoint.ok").exists()
        assert not (victim / ".claude" / "checkpoints" / "used").exists()

    def test_a_tracked_marker_authorises_nothing(self, tmp_path: Path):
        _ship_records(tmp_path / "upstream", tmp_path / "victim")
        victim = tmp_path / "victim"
        result = _gated_hook(_bypass(_bash("rm -rf app.txt")), victim, approval="off")
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert "tracked by git" in result.stderr
        assert (victim / ".claude" / "checkpoint.ok").exists()
        assert (victim / "app.txt").exists()

    def test_a_marker_tracked_behind_a_linked_directory_authorises_nothing(
        self, tmp_path: Path
    ):
        """git is asked from the marker's own directory: a .claude that is
        a symbolic link to a tracked directory is read where it leads."""
        upstream = _repo(tmp_path / "upstream")
        (upstream / "cfg").mkdir()
        now = int(time.time())
        (upstream / "cfg" / "checkpoint.ok").write_text(
            json.dumps(
                {"checkpoint_id": "x", "created_at": now - 60, "expires_at": now + 1740}
            )
        )
        (upstream / ".claude").symlink_to("cfg")
        _git(upstream, "add", "cfg", ".claude")
        _git(upstream, "commit", "-q", "-m", "linked")
        victim = tmp_path / "victim"
        subprocess.run(
            ["git", "clone", "-q", str(upstream), str(victim)],
            check=True,
            capture_output=True,
            timeout=60,
        )
        assert (victim / ".claude").is_symlink()
        result = _gated_hook(_bypass(_write_call()), victim, approval="off")
        assert result.returncode == 2
        assert "tracked by git" in result.stderr

    def test_an_untracked_marker_still_authorises_one_call(self, tmp_path: Path):
        project = _repo(tmp_path / "p")
        (project / ".gitignore").write_text(".claude/\n")
        _write_marker(project)
        result = _gated_hook(_write_call(), project, approval="off")
        assert result.returncode == 0
        assert not (project / ".claude" / "checkpoint.ok").exists()

    def test_a_restore_runs_in_the_projects_repository(self, tmp_path: Path):
        """The commit was entered for the project's repository: restoring
        it where the call runs in another (a cwd elsewhere, another
        worktree) restores other state, a mutate."""
        project = _repo(tmp_path / "project")
        elsewhere = _repo(tmp_path / "elsewhere")
        sha = "0123456789abcdef0123456789abcdef01234567"
        enter_checkpoint_commit(project / ".git", sha)
        call = _bash(f"git stash apply {sha}")
        (project / "sub").mkdir()
        for cwd in (project, project / "sub"):
            allowed = _gated_hook({**call, "cwd": str(cwd)}, project)
            assert (allowed.returncode, allowed.stdout) == (0, ""), cwd
        refused = _gated_hook({**call, "cwd": str(elsewhere)}, project)
        assert refused.returncode == 2
        assert refused.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")

    @pytest.mark.parametrize(
        "tool_call",
        [
            {
                "tool_name": "Write",
                "tool_input": {"file_path": ".claude/checkpoint.ok"},
            },
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/p/.claude/checkpoints/used/x"},
            },
            {
                "tool_name": "MultiEdit",
                "tool_input": {"file_path": "/p/.git/acs/checkpoints/commits/a"},
            },
            {
                "tool_name": "Bash",
                "tool_input": {"command": "touch .git/acs/checkpoints/commits/0123"},
            },
            {
                "tool_name": "Bash",
                "tool_input": {"command": "echo '{}' > .claude/checkpoint.ok"},
            },
            {
                "tool_name": "Bash",
                "tool_input": {"command": "cp m .claude/checkpoints/ended/m"},
            },
            # The audit log's head (security round 1, batch 8): removing or
            # writing it would let a log cut short verify.
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/p/.claude/audit.head"},
            },
            {
                "tool_name": "Bash",
                "tool_input": {"command": "rm -f .claude/audit.head"},
            },
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": "head -n 2 .claude/audit.log > t && mv t .claude/AUDIT.HEAD"
                },
            },
        ],
    )
    def test_a_call_that_writes_the_records_is_refused(
        self, tmp_path: Path, tool_call: dict
    ):
        """The records are written by the hooks alone: a call naming them
        is refused (F504) before it can use a checkpoint."""
        _write_marker(tmp_path)
        result = _gated_hook(
            {**tool_call, "permission_mode": "default"}, tmp_path, approval="off"
        )
        assert result.returncode == 2, tool_call
        assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: "), tool_call
        assert (tmp_path / ".claude" / "checkpoint.ok").exists()

    @pytest.mark.parametrize(
        "tool_call",
        [
            _write_to("/p/.git/acs//checkpoints/commits/a"),
            _write_to("/p/.git/acs/./checkpoints/commits/a"),
            _write_to("/p/.git/acs/x/../checkpoints/commits/a"),
            _write_to("/p/.git/acs/x/y/../../checkpoints/commits/a"),
            _write_to("/p/.git/ACS/Checkpoints/commits/a"),
            _write_to("/p/.claude/Checkpoint.OK"),
            _write_to("/p/.claude//checkpoints/used/x"),
            _bash("touch .git/acs//checkpoints/commits/0123"),
            _bash("touch .git/acs/./checkpoints/commits/0123"),
            _bash("touch .claude/x/../checkpoints/ended/m"),
            {
                "tool_name": "Monitor",
                "tool_input": {"command": "touch .claude/checkpoint.ok"},
            },
            {
                "tool_name": "PowerShell",
                "tool_input": {"command": "New-Item .git/acs/checkpoints/commits/a"},
            },
            # Padded past 4096 bytes: no ../ resolution, the rest still read
            _bash("touch .git/acs//checkpoints/commits/0123" + " " * 5000),
        ],
    )
    def test_another_spelling_of_the_records_is_refused(
        self, tmp_path: Path, tool_call: dict
    ):
        """A path is read as the file system reads it: slashes run
        together, ./ and x/../ segments, and letter case (a case-insensitive
        file system opens CHECKPOINT.OK as checkpoint.ok) name the same
        records, and refuse the call as the plain spelling does."""
        _write_marker(tmp_path)
        result = _gated_hook(
            {**tool_call, "permission_mode": "default"}, tmp_path, approval="off"
        )
        assert result.returncode == 2, tool_call
        assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: "), tool_call
        assert (tmp_path / ".claude" / "checkpoint.ok").exists()

    def test_a_long_path_is_read_in_bounded_time(self, tmp_path: Path):
        """Resolving x/../ costs more than the text's length, so it is done
        only on a text of at most 4096 bytes; a megabyte of segments is
        decided at once."""
        _write_marker(tmp_path)
        started = time.monotonic()
        result = _gated_hook(
            {**_bash("touch " + "a/" * 500_000 + "x"), "permission_mode": "default"},
            tmp_path,
            approval="off",
        )
        assert time.monotonic() - started < 10
        assert result.returncode == 0, result.stderr

    def test_reading_the_records_and_writing_text_about_them_pass(self, tmp_path: Path):
        for tool_call in (
            _bash("cat .claude/checkpoint.ok"),
            _bash("ls .claude/checkpoints/used"),
            _bash("cat .claude/audit.head"),
            {"tool_name": "Read", "tool_input": {"file_path": ".claude/checkpoint.ok"}},
        ):
            assert _gated_hook(tool_call, tmp_path).returncode == 0, tool_call
        _write_marker(tmp_path)
        edit = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "docs/hooks.md",
                "new_string": "the marker is .claude/checkpoint.ok",
            },
            "permission_mode": "default",
        }
        assert _gated_hook(edit, tmp_path, approval="off").returncode == 0
