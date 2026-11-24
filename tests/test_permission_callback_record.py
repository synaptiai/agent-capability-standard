"""The permission callback decides on what the PreToolUse hook checked
(STANDARD 1.2.0 sections 5.18.7, 5.18.8, 5.18.10).

The hook keeps, per call id, the digest of the input it checked, the
directory the call runs in and the time of its ask, until the call reports
back or the callback refuses it:

- an execution boundary of any session the adapter serves (a Stop or a
  UserPromptSubmit) does not clear it, so a call waiting between the hook
  and the callback is still classified in its own directory, and a
  binding's ``approval.expires`` still counts from the hook's ask;
- an input the callback is asked about that differs from the one the hook
  checked (another PreToolUse hook's ``updatedInput``) is changed
  arguments: checked again against section 5.18.10 (F504), and refused
  when it needs a checkpoint the call does not hold (F501) or approval
  (F502: the decision asked for was on other arguments);
- a call the hook has no record of is refused (R407).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions, PermissionResultAllow

import grounded_agency.adapter as adapter_module
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from tests.conftest import FakeClock, missing_objects, pre_tool_use

POLICY = ["https://hooks.example.com/*"]
GIT_READ = "git log -p -1 HEAD~1"


def _ctx(call: str | None) -> Any:
    return SimpleNamespace(tool_use_id=call)


def _decision(result: dict[str, Any]) -> str | None:
    return (result.get("hookSpecificOutput") or {}).get("permissionDecision")


def _allowed(result: Any) -> bool:
    return getattr(result, "behavior", None) == "allow"


async def _approve(tool: str, args: dict[str, Any], context: Any) -> Any:
    return PermissionResultAllow(updated_input=args)


def _adapter(tmp_path: Path, clock: Any = None, **config: Any) -> GroundedAgentAdapter:
    return GroundedAgentAdapter(
        GroundedAgentConfig(checkpoint_dir=str(tmp_path / ".cp"), **config),
        clock=clock,
    )


async def _boundary(options: Any, event: str, session: str) -> None:
    for entry in options.hooks[event]:
        for hook in entry.hooks:
            await hook({"hook_event_name": event, "session_id": session}, None, None)


class TestABoundaryKeepsWhatTheHookChecked:
    """Another session's boundary between session A's PreToolUse hook and
    the permission callback (one adapter, one scope)."""

    @pytest.mark.parametrize("event", ["Stop", "UserPromptSubmit"])
    @pytest.mark.asyncio
    async def test_a_partial_clone_read_is_still_gated(
        self,
        partial_clone: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        event: str,
    ) -> None:
        """Before, the callback classified the call in the host process's
        directory, where the read fetches nothing: observe, allowed with
        no one to approve it. Now it is mutate there too, and the boundary
        ended the checkpoint it held (checked before approval)."""
        elsewhere = tmp_path / "host"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        adapter = _adapter(tmp_path)
        options = adapter.wrap_options(ClaudeAgentOptions(cwd=str(partial_clone)))
        adapter.create_checkpoint(["*"], "t")
        (pre,) = options.hooks["PreToolUse"][-1].hooks
        call = {
            "tool_name": "Bash",
            "tool_input": {"command": GIT_READ},
            "cwd": str(partial_clone),
            "session_id": "A",
            "permission_mode": "default",
        }
        assert _decision(await pre(call, "c1", None)) == "ask"
        await _boundary(options, event, "B")
        missing = missing_objects(partial_clone)

        result = await options.can_use_tool("Bash", call["tool_input"], _ctx("c1"))

        assert not _allowed(result)
        assert result.message.startswith("F501 CHECKPOINT_REQUIRED:")
        refused = adapter.call_records[-1]
        assert refused["decision"] == "refused"
        assert refused["capability"] == "mutate"
        assert missing_objects(partial_clone) == missing

    @pytest.mark.asyncio
    async def test_an_allow_after_the_boundary_is_f501(
        self, partial_clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With a host that approves, the call is still gated, so the
        boundary that ended its checkpoint refuses it at the allow."""
        monkeypatch.chdir(tmp_path)
        adapter = _adapter(tmp_path)
        options = adapter.wrap_options(
            ClaudeAgentOptions(cwd=str(partial_clone), can_use_tool=_approve)
        )
        adapter.create_checkpoint(["*"], "t")
        (pre,) = options.hooks["PreToolUse"][-1].hooks
        call = {
            "tool_name": "Bash",
            "tool_input": {"command": GIT_READ},
            "cwd": str(partial_clone),
            "session_id": "A",
        }
        assert _decision(await pre(call, "c1", None)) == "ask"
        await _boundary(options, "Stop", "B")

        result = await options.can_use_tool("Bash", call["tool_input"], _ctx("c1"))

        assert result.message.startswith("F501 CHECKPOINT_REQUIRED:")

    @pytest.mark.asyncio
    async def test_the_expiry_counts_from_the_hooks_ask(
        self, tmp_path: Path, fake_clock: FakeClock
    ) -> None:
        """The hook asks at 0 s; the callback starts at 25 s; the person
        answers at 40 s, after a PT30S expiry."""

        async def late(tool: str, args: dict[str, Any], context: Any) -> Any:
            fake_clock.advance(seconds=15)
            return PermissionResultAllow(updated_input=args)

        adapter = _adapter(tmp_path, clock=fake_clock)
        adapter.mapper.register_mcp_tool(
            "mcp__ops__run", "execute", approval={"expires": "PT30S"}
        )
        options = adapter.wrap_options(ClaudeAgentOptions(can_use_tool=late))
        (pre,) = options.hooks["PreToolUse"][-1].hooks
        call = {"tool_name": "mcp__ops__run", "tool_input": {}, "session_id": "A"}
        assert _decision(await pre(call, "c1", None)) == "ask"
        fake_clock.advance(seconds=25)
        await _boundary(options, "Stop", "B")

        result = await options.can_use_tool("mcp__ops__run", {}, _ctx("c1"))

        assert result.message.startswith("F502 APPROVAL_REQUIRED:")
        assert "approval.expires" in result.message


def _send_adapter(tmp_path: Path) -> GroundedAgentAdapter:
    adapter = _adapter(tmp_path, allowed_destinations=POLICY)
    adapter.mapper.register_binding(
        {
            "tool": "mcp__mail__post",
            "standard": "1.2.0",
            "ontology": adapter.registry.version,
            "capability": "send",
            "destination": "/url",
        }
    )
    adapter.create_checkpoint(["*"], "t")
    return adapter


GOOD = {"url": "https://hooks.example.com/r", "body": "x"}
EVIL = {"url": "https://evil.example/r", "body": "x"}
PLAIN = {"subject": "notes", "description": "plain"}
SECRET = {
    "subject": "notes",
    "description": "password: Summer2026Rocks! AKIAIOSFODNN7EXAMPLE",
}


class TestAnInputTheHookDidNotCheck:
    """Another PreToolUse hook answered with ``updatedInput``: the callback
    is asked about input B, the hook checked input A."""

    @pytest.mark.parametrize("host", [_approve, None], ids=["host", "no-host"])
    @pytest.mark.asyncio
    async def test_a_destination_the_policy_refuses_is_f504(
        self, tmp_path: Path, host: Any
    ) -> None:
        adapter = _send_adapter(tmp_path)
        asked = await pre_tool_use(adapter, "mcp__mail__post", GOOD, "c1")
        assert _decision(asked) == "ask"

        result = await adapter._make_permission_callback(host)(
            "mcp__mail__post", EVIL, _ctx("c1")
        )

        assert not _allowed(result)
        assert result.message.startswith("F504 CONSTRAINT_VIOLATED:")
        assert not adapter.take_allowed("mcp__mail__post", EVIL)

    @pytest.mark.parametrize("host", [_approve, None], ids=["host", "no-host"])
    @pytest.mark.asyncio
    async def test_a_secret_in_persist_data_is_f504(
        self, tmp_path: Path, host: Any
    ) -> None:
        adapter = _adapter(tmp_path)
        assert adapter.mapper.map_tool("TaskCreate", PLAIN).capability_id == "persist"
        assert _decision(await pre_tool_use(adapter, "TaskCreate", PLAIN, "c1")) is None

        result = await adapter._make_permission_callback(host)(
            "TaskCreate", SECRET, _ctx("c1")
        )

        assert not _allowed(result)
        assert result.message.startswith("F504 CONSTRAINT_VIOLATED:")
        assert "AKIAIOSFODNN7EXAMPLE" not in result.message

    @pytest.mark.asyncio
    async def test_a_call_that_needs_approval_is_f502(self, tmp_path: Path) -> None:
        """An allowed destination, but not the arguments the layer asked
        a decision on."""
        adapter = _send_adapter(tmp_path)
        assert _decision(
            await pre_tool_use(adapter, "mcp__mail__post", GOOD, "c1")
        ) == ("ask")
        other = {"url": "https://hooks.example.com/other", "body": "y"}

        result = await adapter._make_permission_callback(_approve)(
            "mcp__mail__post", other, _ctx("c1")
        )

        assert result.message.startswith("F502 APPROVAL_REQUIRED:")
        assert "not the one this layer's PreToolUse hook checked" in result.message
        # Refused: the hold is released, the checkpoint stays valid.
        assert adapter.has_valid_checkpoint()

    @pytest.mark.asyncio
    async def test_a_call_that_needs_a_checkpoint_it_does_not_hold_is_f501(
        self, tmp_path: Path
    ) -> None:
        adapter = _adapter(tmp_path, approval="off")
        adapter.create_checkpoint(["*"], "t")
        assert (
            _decision(await pre_tool_use(adapter, "Bash", {"command": "ls"}, "c1"))
            is None
        )

        result = await adapter._make_permission_callback()(
            "Bash", {"command": "rm -rf x"}, _ctx("c1")
        )

        assert result.message.startswith("F501 CHECKPOINT_REQUIRED:")
        assert adapter.has_valid_checkpoint()

    @pytest.mark.asyncio
    async def test_the_same_input_is_decided_as_before(self, tmp_path: Path) -> None:
        adapter = _send_adapter(tmp_path)
        assert _decision(
            await pre_tool_use(adapter, "mcp__mail__post", GOOD, "c1")
        ) == ("ask")
        result = await adapter._make_permission_callback(_approve)(
            "mcp__mail__post", dict(GOOD), _ctx("c1")
        )
        assert _allowed(result)
        assert adapter.take_allowed("mcp__mail__post", GOOD)


class TestACallTheHookHasNoRecordOf:
    @pytest.mark.asyncio
    async def test_is_r407(self, tmp_path: Path) -> None:
        adapter = _adapter(tmp_path)
        adapter.create_checkpoint(["*"], "t")
        result = await adapter._make_permission_callback(_approve)(
            "Write", {"file_path": "a"}, _ctx("never-hooked")
        )
        assert result.message.startswith("R407 SAFETY_CHECK_FAILED:")
        assert adapter.has_valid_checkpoint()

    @pytest.mark.asyncio
    async def test_a_control_only_call_still_runs(self, tmp_path: Path) -> None:
        adapter = _adapter(tmp_path)
        adapter.mapper.register_binding(
            {
                "tool": "mcp__ui__done",
                "standard": "1.2.0",
                "ontology": adapter.registry.version,
                "control": True,
            }
        )
        result = await adapter._make_permission_callback()(
            "mcp__ui__done", {}, _ctx("never-hooked")
        )
        assert _allowed(result)

    @pytest.mark.asyncio
    async def test_the_record_goes_when_the_call_ends(self, tmp_path: Path) -> None:
        """Refused at the callback, or reported back: the record is
        dropped, so the table holds only calls in flight."""
        adapter = _adapter(tmp_path)
        adapter.create_checkpoint(["*"], "t")
        options = adapter.wrap_options(ClaudeAgentOptions(can_use_tool=_approve))
        (pre,) = options.hooks["PreToolUse"][-1].hooks
        call = {"tool_name": "Write", "tool_input": {"file_path": "a"}}
        assert _decision(await pre(call, "w1", None)) == "ask"
        assert _allowed(
            await options.can_use_tool("Write", {"file_path": "a"}, _ctx("w1"))
        )
        assert "w1" in adapter._hook_checks
        for entry in options.hooks["PostToolUse"]:
            for hook in entry.hooks:
                await hook(
                    {**call, "tool_use_id": "w1", "tool_response": {}}, "w1", None
                )
        assert "w1" not in adapter._hook_checks

        refused = await adapter._make_permission_callback()(
            "Bash", {"command": "rm x"}, _ctx("w2")
        )
        assert not _allowed(refused)
        assert not adapter._hook_checks

    @pytest.mark.asyncio
    async def test_the_oldest_record_goes_past_the_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(adapter_module, "_HOOK_CHECK_LIMIT", 2)
        adapter = _adapter(tmp_path)
        for call in ("r1", "r2", "r3"):
            await pre_tool_use(adapter, "Read", {"file_path": call}, call)
        assert list(adapter._hook_checks) == ["r2", "r3"]
        callback = adapter._make_permission_callback(_approve)
        gone = await callback("Read", {"file_path": "r1"}, _ctx("r1"))
        assert gone.message.startswith("R407 SAFETY_CHECK_FAILED:")
        assert _allowed(await callback("Read", {"file_path": "r3"}, _ctx("r3")))
