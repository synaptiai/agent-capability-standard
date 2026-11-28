"""Approval relies on a permission prompt only where it reaches a person
(STANDARD 1.2.0 section 5.18.7): the adapter answers "ask" in Claude Code's
permission modes default, acceptEdits and plan, and refuses with F502 in
every other mode, a mode it does not know included."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.adapter import PROMPTING_PERMISSION_MODES


@pytest.fixture
def asking(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp")
        )
    )
    adapter.create_checkpoint(["*"], "test")
    return adapter


def _write(mode: str | None) -> dict[str, Any]:
    call: dict[str, Any] = {"tool_name": "Write", "tool_input": {"file_path": "a"}}
    if mode is not None:
        call["permission_mode"] = mode
    return call


def _decision(result: dict[str, Any]) -> str:
    return result["hookSpecificOutput"]["permissionDecision"]


def _reason(result: dict[str, Any]) -> str:
    return result["hookSpecificOutput"]["permissionDecisionReason"]


def test_the_prompting_modes() -> None:
    assert PROMPTING_PERMISSION_MODES == {"default", "acceptEdits", "plan"}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["default", "acceptEdits", "plan"])
async def test_a_prompting_mode_asks(asking: GroundedAgentAdapter, mode: str) -> None:
    hook = asking._make_pretooluse_safety_hook()
    result = await hook(_write(mode), "w1", None)
    assert _decision(result) == "ask"
    assert _reason(result).startswith("F502 APPROVAL_REQUIRED:")
    record = asking.call_records[-1]
    assert (record["decision"], record["permission_mode"]) == ("asked", mode)
    assert len(record["digest"]) == 64


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["bypassPermissions", "auto", "dontAsk", "somethingNew"]
)
async def test_another_mode_is_f502_and_keeps_the_checkpoint(
    asking: GroundedAgentAdapter, mode: str
) -> None:
    hook = asking._make_pretooluse_safety_hook()
    result = await hook(_write(mode), "w1", None)
    assert _decision(result) == "deny"
    assert _reason(result).startswith(
        f"F502 APPROVAL_REQUIRED: permission mode '{mode}' does not put this call to a person"
    )
    # The hold was released: the checkpoint is still valid for another call.
    assert asking.checkpoint_tracker.held_by("w1") is None
    assert asking.has_valid_checkpoint()
    assert asking.call_records[-1]["permission_mode"] == mode


@pytest.mark.asyncio
async def test_no_mode_in_the_input_falls_back_to_the_options(
    asking: GroundedAgentAdapter,
) -> None:
    assert (
        _decision(await asking._make_pretooluse_safety_hook()(_write(None), "w1", None))
        == "ask"
    )
    hook = asking._make_pretooluse_safety_hook(options_mode="bypassPermissions")
    assert _decision(await hook(_write(None), "w2", None)) == "deny"


@pytest.mark.usefixtures("bash_under_sandbox")
@pytest.mark.asyncio
async def test_a_call_needing_no_approval_is_not_affected(
    asking: GroundedAgentAdapter,
) -> None:
    hook = asking._make_pretooluse_safety_hook()
    call = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "permission_mode": "bypassPermissions",
    }
    assert await hook(call, "b1", None) == {}
