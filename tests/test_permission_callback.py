"""The permission callback re-checks a call when it is allowed (STANDARD
1.2.0 sections 5.18.6 and 5.18.7): the checkpoint it held must still be
valid, arguments the host changed are classified again, and a binding whose
approval a prompt cannot meet is refused."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from claude_agent_sdk import PermissionResultAllow

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig, _core
from tests.conftest import FakeClock


@pytest.fixture
def adapter(
    ontology_path: str, tmp_path: Path, fake_clock: FakeClock
) -> GroundedAgentAdapter:
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp")
        ),
        clock=fake_clock,
    )


def _ctx(tool_use_id: str | None) -> Any:
    return SimpleNamespace(tool_use_id=tool_use_id)


def _allowed(result: Any) -> bool:
    return getattr(result, "behavior", None) == "allow"


def _host(updated: dict[str, Any] | None = None) -> Any:
    async def host(tool: str, args: dict[str, Any], context: Any) -> Any:
        return PermissionResultAllow(
            updated_input=updated if updated is not None else args
        )

    return host


@pytest.mark.asyncio
async def test_a_prompt_answered_after_the_maximum_age_is_f501(
    adapter: GroundedAgentAdapter, fake_clock: FakeClock
) -> None:
    checkpoint_id = adapter.create_checkpoint(["*"], "t")
    pre = adapter._make_pretooluse_safety_hook()
    callback = adapter._make_permission_callback(_host())
    call = {"tool_name": "Write", "tool_input": {"file_path": "a"}}
    assert (await pre(call, "w1", None))["hookSpecificOutput"][
        "permissionDecision"
    ] == "ask"

    fake_clock.advance(minutes=31)
    result = await callback("Write", {"file_path": "a"}, _ctx("w1"))

    assert not _allowed(result)
    assert result.message.startswith("F501 CHECKPOINT_REQUIRED:")
    used = adapter.checkpoint_tracker.get_checkpoint_by_id(checkpoint_id)
    assert used is not None and used.consumed


@pytest.mark.asyncio
async def test_a_stop_of_another_session_while_the_call_waits_is_f501(
    adapter: GroundedAgentAdapter,
) -> None:
    """One adapter is one scope: any served session's Stop is a boundary."""
    options = adapter.wrap_options(_options())
    adapter.create_checkpoint(["*"], "t")
    (pre,) = options.hooks["PreToolUse"][-1].hooks
    call = {"tool_name": "Write", "tool_input": {"file_path": "a"}, "session_id": "A"}
    assert (await pre(call, "w1", None))["hookSpecificOutput"][
        "permissionDecision"
    ] == "ask"
    for entry in options.hooks["Stop"]:
        for hook in entry.hooks:
            await hook({"hook_event_name": "Stop", "session_id": "B"}, None, None)

    result = await adapter._make_permission_callback(_host())(
        "Write", {"file_path": "a"}, _ctx("w1")
    )
    assert result.message.startswith("F501 CHECKPOINT_REQUIRED:")


@pytest.mark.asyncio
async def test_changed_arguments_that_need_a_checkpoint_are_f501(
    adapter: GroundedAgentAdapter,
) -> None:
    adapter.create_checkpoint(["*"], "t")
    callback = adapter._make_permission_callback(_host({"command": "rm -rf x"}))
    result = await callback("Bash", {"command": "ls"}, _ctx("b1"))
    assert result.message.startswith("F501 CHECKPOINT_REQUIRED:")
    assert adapter.has_valid_checkpoint()


@pytest.mark.asyncio
async def test_changed_arguments_that_hold_a_credential_are_f504(
    adapter: GroundedAgentAdapter,
) -> None:
    """Arguments the host changed are checked again against every row of
    §5.18.10, the persist and audit secret rows included (§6.7): the call
    would run with them."""
    secret = {"todos": [{"content": "deploy with AKIAABCDEFGHIJKLMNOP"}]}
    callback = adapter._make_permission_callback(_host(secret))
    result = await callback("TodoWrite", {"todos": [{"content": "deploy"}]}, _ctx("t1"))
    assert not _allowed(result)
    assert result.message.startswith("F504 CONSTRAINT_VIOLATED:")
    assert "AKIAABCDEFGHIJKLMNOP" not in result.message
    # The call is no longer allowed: a grounded tool would refuse it.
    assert not adapter.take_allowed("TodoWrite", secret)


@pytest.mark.asyncio
async def test_changed_arguments_of_an_approved_call_are_f502(
    adapter: GroundedAgentAdapter,
) -> None:
    adapter.create_checkpoint(["*"], "t")
    callback = adapter._make_permission_callback(_host({"file_path": "other"}))
    result = await callback("Write", {"file_path": "a"}, _ctx("w1"))
    assert result.message.startswith("F502 APPROVAL_REQUIRED:")
    assert "the decision was on other arguments" in result.message
    # Refused: the hold was released, the checkpoint stays valid.
    assert adapter.has_valid_checkpoint()


@pytest.mark.asyncio
async def test_unchanged_updated_input_is_allowed_and_recorded(
    adapter: GroundedAgentAdapter,
) -> None:
    adapter.create_checkpoint(["*"], "t")
    callback = adapter._make_permission_callback(_host())
    result = await callback("Write", {"file_path": "a"}, _ctx("w1"))
    assert _allowed(result)
    record = adapter.call_records[-1]
    assert record["digest"] == _core.approval_digest(
        [{"action": "Write", "capability": "mutate", "args": {"file_path": "a"}}]
    )
    assert record["approvers"] == ["in_session"]
    assert record["checkpoint_id"]
    assert record["recorded_by"]["name"] == "grounded_agency.adapter"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approval", "expected"),
    [
        ({"role": "ops"}, "needs an approver with role 'ops'"),
        ({"min_approvers": 2}, "needs 2 approvers"),
    ],
)
async def test_an_approval_a_prompt_cannot_meet_is_f502(
    adapter: GroundedAgentAdapter, approval: dict[str, Any], expected: str
) -> None:
    adapter.mapper.register_mcp_tool(
        "mcp__s__put", capability_id="mutate", approval=approval
    )
    adapter.create_checkpoint(["*"], "t")
    hook = adapter._make_pretooluse_safety_hook()
    result = await hook({"tool_name": "mcp__s__put", "tool_input": {}}, "p1", None)
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert reason.startswith("F502 APPROVAL_REQUIRED:")
    assert expected in reason
    assert adapter.has_valid_checkpoint()


@pytest.mark.asyncio
async def test_a_gated_call_without_a_tool_use_id_is_r407(
    adapter: GroundedAgentAdapter,
) -> None:
    adapter.create_checkpoint(["*"], "t")
    result = await adapter._make_permission_callback(_host())("Write", {}, _ctx(None))
    assert result.message.startswith("R407 SAFETY_CHECK_FAILED:")


def _options() -> Any:
    from claude_agent_sdk import ClaudeAgentOptions

    return ClaudeAgentOptions()
