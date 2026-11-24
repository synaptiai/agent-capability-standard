"""Skill, Agent and Task calls take the worst case (STANDARD 1.2.0 section
5.18.3).

Claude Code runs the shell commands a skill's file embeds (``!`cmd``` and
```` ```! ```` blocks, with the call's arguments substituted into them) as
the skill loads, under the skill's ``allowed-tools``, and starts the hooks
and MCP servers a subagent's definition names as the subagent runs. None of
these reaches a PreToolUse or PostToolUse hook: the plugin's hook and the
SDK adapter see only the Skill or Agent call. A project's skill or agent
can take any name, a built-in agent's included (a project's definition
replaces it). So the call itself is gated: the plugin's hook gives it
``mutate`` (a checkpoint, and approval), and the SDK mapper its own
capability and Bash's worst case (``mutate`` and ``send``, which a
destination policy refuses)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.capabilities.mapper import ToolCapabilityMapper

HOOK = (
    Path(__file__).resolve().parents[1] / "hooks" / "pretooluse_require_checkpoint.sh"
)

needs_bash_and_jq = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the shell hook needs bash, and jq to read the tool call",
)

CALLS: list[tuple[str, dict[str, Any]]] = [
    ("Skill", {"skill": "helper"}),
    ("Skill", {"skill": "agent-capability-standard:checkpoint"}),
    ("Agent", {"prompt": "look", "subagent_type": "Explore"}),
    ("Agent", {"prompt": "look"}),
    ("Task", {"description": "d", "prompt": "p"}),
]


def _hook(
    call: dict[str, Any], project: Path, **env: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(call),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), **env},
        timeout=60,
    )


def _marker(project: Path) -> Path:
    claude = project / ".claude"
    claude.mkdir(exist_ok=True)
    now = int(time.time())
    marker = claude / "checkpoint.ok"
    marker.write_text(
        json.dumps({"checkpoint_id": "c1", "created_at": now, "expires_at": now + 600})
    )
    return marker


@needs_bash_and_jq
class TestPluginHook:
    @pytest.mark.parametrize(("tool", "args"), CALLS)
    def test_a_call_needs_a_checkpoint(
        self, tmp_path: Path, tool: str, args: dict[str, Any]
    ) -> None:
        for mode in ("default", "bypassPermissions"):
            result = _hook(
                {"tool_name": tool, "tool_input": args, "permission_mode": mode},
                tmp_path,
            )
            assert result.returncode == 2, (mode, result.stdout)
            assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), mode

    @pytest.mark.parametrize(("tool", "args"), CALLS)
    def test_with_a_checkpoint_it_is_put_to_a_person(
        self, tmp_path: Path, tool: str, args: dict[str, Any]
    ) -> None:
        marker = _marker(tmp_path)
        result = _hook(
            {"tool_name": tool, "tool_input": args, "permission_mode": "default"},
            tmp_path,
        )
        assert result.returncode == 0, result.stderr
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "ask"
        reason = decision["permissionDecisionReason"]
        assert reason.startswith(f"F502 APPROVAL_REQUIRED: {tool} (capability 'mutate'")
        assert "no hook seeing them" in reason
        assert not marker.exists()  # the call took it

    @pytest.mark.parametrize(("tool", "args"), CALLS)
    def test_a_mode_that_asks_no_one_blocks_it(
        self, tmp_path: Path, tool: str, args: dict[str, Any]
    ) -> None:
        marker = _marker(tmp_path)
        result = _hook(
            {
                "tool_name": tool,
                "tool_input": args,
                "permission_mode": "bypassPermissions",
            },
            tmp_path,
        )
        assert result.returncode == 2
        assert result.stderr.startswith("F502 APPROVAL_REQUIRED: ")
        assert marker.exists()

    def test_a_skills_arguments_naming_the_records_are_refused(
        self, tmp_path: Path
    ) -> None:
        """Claude Code substitutes the arguments into the commands a skill's
        file embeds: they are read as a command's text is."""
        _marker(tmp_path)
        for args in (
            "touch .git/acs/checkpoints/key",
            "x .claude/CHECKPOINT.OK",
            "a .git/acs/x/../checkpoints/commits/0123",
        ):
            result = _hook(
                {
                    "tool_name": "Skill",
                    "tool_input": {"skill": "helper", "args": args},
                    "permission_mode": "default",
                },
                tmp_path,
            )
            assert result.returncode == 2, args
            assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: "), args


class TestSdkMapper:
    @pytest.mark.parametrize(
        ("tool", "own"),
        [("Skill", "invoke"), ("Agent", "delegate"), ("Task", "delegate")],
    )
    @pytest.mark.parametrize("skill", ["checkpoint", "rollback", "anything"])
    def test_its_own_capability_and_the_worst_case(
        self, tool: str, own: str, skill: str
    ) -> None:
        mapping = ToolCapabilityMapper().map_tool(tool, {"skill": skill, "prompt": "p"})
        assert mapping.capabilities == (own, "mutate", "send")
        assert mapping.capability_id == own
        assert mapping.requires_checkpoint and mapping.requires_approval
        assert mapping.mutation and mapping.risk == "high"
        assert "checkpoint" in mapping.prerequisites

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tool", "args"), CALLS)
    async def test_the_adapter_asks_with_a_checkpoint(
        self, ontology_path: str, tmp_path: Path, tool: str, args: dict[str, Any]
    ) -> None:
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                approval="ask",
            )
        )
        hook = adapter._make_pretooluse_safety_hook()
        call = {"tool_name": tool, "tool_input": args, "permission_mode": "default"}
        refused = await hook(call, "u1", None)
        assert refused["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert refused["hookSpecificOutput"]["permissionDecisionReason"].startswith(
            "F501 CHECKPOINT_REQUIRED:"
        )
        adapter.create_checkpoint(["*"], "t")
        asked = await hook(call, "u2", None)
        assert asked["hookSpecificOutput"]["permissionDecision"] == "ask"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tool", "args"), CALLS)
    async def test_a_destination_policy_refuses_it(
        self, ontology_path: str, tmp_path: Path, tool: str, args: dict[str, Any]
    ) -> None:
        """The commands it runs unseen may send anywhere: under a destination
        policy the layer cannot tell where, so it refuses (section 4.4.2)."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                approval="ask",
                allowed_destinations=["https://hooks.example.com/*"],
            )
        )
        adapter.create_checkpoint(["*"], "t")
        hook = adapter._make_pretooluse_safety_hook()
        result = await hook(
            {"tool_name": tool, "tool_input": args, "permission_mode": "default"},
            "u1",
            None,
        )
        out = result["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        assert out["permissionDecisionReason"].startswith("F504 CONSTRAINT_VIOLATED:")
