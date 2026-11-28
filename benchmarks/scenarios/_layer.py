"""A driver that puts tool calls through a real GroundedAgentAdapter.

The safety-layer scenarios measure what the shipped layer does, so every
layer metric comes from the adapter's own hooks, not from a model of them.
The driver plays Claude Code's part for one session, as the call-sequence
conformance runner does (STANDARD 1.2.0 section 10.4):

1. the PreToolUse hook decides (``deny`` refuses the call; ``ask`` goes on);
2. for an ``ask``, the wrapped ``can_use_tool`` callback asks the host's
   person, here the ``approve`` callable the scenario passes;
3. a call that runs reaches the PostToolUse hooks with its result, which
   check the output and may replace it with a refusal.

Every tool is a tool of another MCP server (``mcp__ext__<name>``), bound to
a capability by its binding record, so its result reaches the layer as
Claude Code passes it to PostToolUse.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.grounding import GroundingPolicy

SERVER = "mcp__ext__"
ONTOLOGY = "2.2.0"
_CODE = re.compile(r"^([VBSRFW]\d{3}) [A-Z_]+: ")

# The tools the scenarios call, by short name: a checkpoint, a write, a
# send whose destination is its `to` argument, a retrieve, a recall and an
# explain.
BINDINGS: tuple[dict[str, Any], ...] = (
    {"tool": "save", "capability": "checkpoint"},
    {"tool": "write", "capability": "mutate"},
    {"tool": "notify", "capability": "send", "destination": "/to"},
    {"tool": "fetch", "capability": "retrieve"},
    {"tool": "remember", "capability": "recall"},
    {"tool": "explain", "capability": "explain"},
)


def tool(name: str) -> str:
    """The full name of a scenario tool."""
    return SERVER + name


@dataclass(frozen=True)
class Outcome:
    """What the layer did with one call.

    ``ran`` is true when the call reached the tool. ``code`` is the refusal's
    code (``F501``, ``F504``...), None when nothing was refused. ``stage``
    says where: ``pre`` (the PreToolUse hook), ``approval`` (the permission
    callback, after an ask) or ``output`` (the result was refused after the
    call ran). ``asked`` is true when the layer asked a person.
    """

    ran: bool
    code: str | None
    stage: str | None
    asked: bool
    message: str = ""


def _code(text: str) -> str:
    match = _CODE.match(text)
    if match is None:
        raise AssertionError(f"a refusal that does not open with a code: {text!r}")
    return match.group(1)


class Clock:
    """A clock that stands still until the scenario advances it."""

    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class LayerDriver:
    """One adapter and one session of calls through it."""

    def __init__(
        self,
        workdir: Path,
        *,
        allowed_destinations: Sequence[str] | None = None,
        grounding: Sequence[GroundingPolicy] = (),
        secret_values: Sequence[str] = (),
        permission_mode: str = "default",
        approve: Callable[[str, dict[str, Any]], bool] | None = None,
    ) -> None:
        self.clock = Clock()
        self.adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                checkpoint_dir=str(workdir / ".checkpoints"),
                audit_log_path=str(workdir / "audit.log"),
                allowed_destinations=allowed_destinations,
                grounding=tuple(grounding),
                secret_values=tuple(secret_values),
            ),
            clock=self.clock,
        )
        records = [
            {**b, "tool": tool(b["tool"]), "ontology": ONTOLOGY} for b in BINDINGS
        ]
        self.adapter.mapper.load_bindings(records)
        self.permission_mode = permission_mode
        self._approve = approve or (lambda name, args: False)
        self.options = self.adapter.wrap_options(
            ClaudeAgentOptions(can_use_tool=self._person)
        )
        self._n = 0

    async def _person(self, name: str, args: dict[str, Any], context: Any) -> Any:
        if self._approve(name, args):
            return PermissionResultAllow(updated_input=args)
        return PermissionResultDeny(message="the person did not approve")

    async def _fire(
        self, event: str, data: dict[str, Any], call_id: str | None
    ) -> list[Any]:
        results = []
        for entry in self.options.hooks.get(event, []):
            for hook in entry.hooks:
                results.append(await hook(data, call_id, None))
        return results

    async def _call(self, name: str, args: dict[str, Any], returns: Any) -> Outcome:
        self._n += 1
        call_id = f"c{self._n}"
        data = {
            "tool_name": name,
            "tool_input": args,
            "tool_use_id": call_id,
            "session_id": "s1",
            "permission_mode": self.permission_mode,
        }
        (pre,) = await self._fire("PreToolUse", data, call_id)
        out = pre.get("hookSpecificOutput", {})
        decision = out.get("permissionDecision")
        if decision == "deny":
            reason = out["permissionDecisionReason"]
            return Outcome(False, _code(reason), "pre", False, reason)
        asked = decision == "ask"
        if asked:
            result = await self.options.can_use_tool(
                name, args, ToolPermissionContext(tool_use_id=call_id)
            )
            if getattr(result, "behavior", None) != "allow":
                return Outcome(False, _code(result.message), "approval", True)
        response = [{"type": "text", "text": json.dumps(returns)}]
        posted = await self._fire(
            "PostToolUse", {**data, "tool_response": response}, call_id
        )
        replaced = [
            r["hookSpecificOutput"]["updatedMCPToolOutput"]
            for r in posted
            if "updatedMCPToolOutput" in r.get("hookSpecificOutput", {})
        ]
        if replaced:
            ((item,),) = replaced
            return Outcome(True, _code(item["text"]), "output", asked, item["text"])
        return Outcome(True, None, None, asked)

    def call(self, name: str, args: dict[str, Any], returns: Any = None) -> Outcome:
        """Put one call of tool ``name`` (a short name) through the layer;
        ``returns`` is the tool's result when it runs."""
        return asyncio.run(self._call(tool(name), args, returns))

    def boundary(self) -> None:
        """End the turn (the Stop hook): an execution boundary, which ends
        every checkpoint the layer holds (section 5.18.5)."""
        asyncio.run(
            self._fire("Stop", {"hook_event_name": "Stop", "session_id": "s1"}, None)
        )

    def expire(self) -> None:
        """Move the layer's clock past the checkpoint maximum age."""
        self.clock.advance(minutes=self.adapter.config.expiry_minutes, seconds=1)

    def checkpoint(self) -> Outcome:
        """Take a checkpoint through the bound checkpoint tool."""
        return self.call(
            "save",
            {},
            {
                "checkpoint_id": f"cp-{self._n + 1}",
                "timestamp": "2026-11-27T00:00:00.000Z",
                "evidence_anchors": [],
            },
        )
