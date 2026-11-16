"""The call-sequence fixtures (tests/conformance/calls/, STANDARD 1.2.0
section 10.4) through a real GroundedAgentAdapter.

The runner plays Claude Code's part for a tool in allowed_tools: the
PreToolUse hook; for an "ask", the wrapped can_use_tool callback with a host
callback that allows only an approved call (one with `approve` and no
`reject`); then, for a call that runs, PostToolUse, or PostToolUseFailure
when it `fails`. A bound tool with a capability is served as
create_grounded_mcp_server serves it: it runs only on the layer's decision,
and returns what its output contract requires, or what the call `returns`,
as the JSON text of its one content item (section 5.18.9), which the layer
checks (section 5.18.10). A boundary is the Stop hook; an expired checkpoint
moves the adapter's clock past its maximum age. Fixtures whose `needs` the
adapter's conformance statement lacks are skipped with the reason.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from claude_agent_sdk import (
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    SdkMcpTool,
    ToolPermissionContext,
)

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.errors import Severity
from grounded_agency.mcp import _guarded
from tests.conftest import FakeClock

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "conformance" / "calls"
STATEMENT = FIXTURES / "statements" / "grounded_agency_adapter.json"
CASES = sorted(FIXTURES.glob("*.json"))
CODE = re.compile(r"^([VBSRFW]\d{3}) [A-Z_]+: ")


def _statement() -> dict[str, Any]:
    return json.loads(STATEMENT.read_text(encoding="utf-8"))


def test_the_statement_validates() -> None:
    schema = json.loads((FIXTURES / "schema" / "statement.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(_statement())
    for other in (FIXTURES / "statements").glob("*.json"):
        jsonschema.Draft202012Validator(schema).validate(json.loads(other.read_text()))


def test_the_statement_matches_the_adapter() -> None:
    from grounded_agency import __version__
    from grounded_agency.adapter import PROMPTING_PERMISSION_MODES

    statement = _statement()
    assert statement["layer"]["version"] == __version__
    assert (
        statement["checkpoint_max_age"] == f"PT{GroundedAgentConfig().expiry_minutes}M"
    )
    configurations = " ".join(statement["approval"]["prompt_configurations"])
    for mode in PROMPTING_PERMISSION_MODES:
        assert mode in configurations
    # A prompt decides alone: one approver, no role, no expiry of its own
    # (a binding needing more is refused with F502, tests/test_permission_callback.py).
    assert statement["approval"]["max_approvers"] == 1
    assert statement["approval"]["roles"] is False
    assert statement["approval"]["expires"] is None
    # Every check of section 5.18.10 is applied (class SL): the output
    # contract by default, and turning it off is outside the class.
    assert "not_applied" not in statement
    assert GroundedAgentConfig().check_outputs is True
    assert any(
        "check_outputs=False" in gap and "outside class SL" in gap
        for gap in statement["host_gaps"]
    )


def test_there_are_fixtures() -> None:
    assert len(CASES) == 26


def _output(capability: str, adapter: GroundedAgentAdapter, n: int) -> dict[str, Any]:
    """The output a capability's contract requires, with plain values."""
    node = adapter.registry.get_capability(capability)
    assert node is not None
    output: dict[str, Any] = {}
    for field in node.output_schema.get("required") or []:
        output[field] = {"evidence_anchors": [], "confidence": 1}.get(
            field, f"cp-{n}" if field == "checkpoint_id" else True
        )
    return output


class _Runner:
    def __init__(
        self,
        adapter: GroundedAgentAdapter,
        clock: FakeClock,
        bindings: list[dict[str, Any]],
    ) -> None:
        self.adapter = adapter
        self.clock = clock
        self.approved: dict[str, bool] = {}
        self.options = adapter.wrap_options(ClaudeAgentOptions(can_use_tool=self._host))
        self.n = 0
        # What the current call of a served tool returns.
        self.returns: Any = None
        self.served = {
            b["tool"]: _guarded(
                SdkMcpTool(
                    name=b["tool"],
                    description=b["tool"],
                    input_schema={},
                    handler=self._tool(b["capability"]),
                ),
                b["tool"],
                adapter,
                SdkMcpTool,
            )
            for b in bindings
            if b.get("capability") and not b.get("control")
        }

    def _tool(self, capability: str) -> Any:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            value = (
                _output(capability, self.adapter, self.n)
                if self.returns is None
                else self.returns
            )
            return {"content": [{"type": "text", "text": json.dumps(value)}]}

        return handler

    async def _host(self, tool: str, args: dict[str, Any], context: Any) -> Any:
        if self.approved.get(context.tool_use_id):
            return PermissionResultAllow(updated_input=args)
        return PermissionResultDeny(message="the person did not approve")

    async def _fire(
        self, event: str, data: dict[str, Any], tool_use_id: str | None
    ) -> list[Any]:
        results = []
        for entry in self.options.hooks.get(event, []):
            for hook in entry.hooks:
                results.append(await hook(data, tool_use_id, None))
        return results

    async def call(self, step: dict[str, Any]) -> str:
        self.n += 1
        call_id = f"c{self.n}"
        self.approved[call_id] = "approve" in step and "reject" not in step
        data = {
            "tool_name": step["call"],
            "tool_input": step.get("args", {}),
            "tool_use_id": call_id,
            "session_id": "s1",
            "permission_mode": "default",
        }
        (pre,) = await self._fire("PreToolUse", data, call_id)
        decision = pre.get("hookSpecificOutput", {}).get("permissionDecision")
        if decision == "deny":
            return _code(pre["hookSpecificOutput"]["permissionDecisionReason"])
        if decision == "ask":
            context = ToolPermissionContext(tool_use_id=call_id)
            result = await self.options.can_use_tool(
                step["call"], data["tool_input"], context
            )
            if getattr(result, "behavior", None) != "allow":
                return _code(result.message)
        if step.get("fails"):
            await self._fire(
                "PostToolUseFailure", {**data, "error": "the tool failed"}, call_id
            )
            return "run"
        response: dict[str, Any] = {}
        if step["call"] in self.served:
            self.returns = step.get("returns")
            tool = self.served[step["call"]]
            response = await tool.handler(data["tool_input"])
        await self._fire("PostToolUse", {**data, "tool_response": response}, call_id)
        if response.get("is_error"):
            # The call ran; the layer refused its output (section 5.18.10).
            return "output " + _code(response["content"][0]["text"])
        return "run"

    async def boundary(self) -> None:
        await self._fire("Stop", {"hook_event_name": "Stop", "session_id": "s1"}, None)


def _code(text: str) -> str:
    match = CODE.match(text)
    assert match, f"a refusal that does not open with a code: {text!r}"
    return match.group(1)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
async def test_call_fixture(path: Path, ontology_path: str, tmp_path: Path) -> None:
    fixture: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    statement = _statement()
    missing = set(fixture.get("needs", [])) - set(statement["features"])
    if missing:
        pytest.skip(
            f"the adapter's conformance statement lacks {sorted(missing)}: "
            f"{statement['does_not_cover'] if 'nested_calls' in missing else 'approval is by prompt'}"
        )

    clock = FakeClock()
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp")
        ),
        clock=clock,
    )
    diagnostics = adapter.mapper.load_bindings(fixture["bindings"])
    assert [d for d in diagnostics if d.severity is Severity.ERROR] == []
    runner = _Runner(adapter, clock, fixture["bindings"])

    for index, step in enumerate(fixture["sequence"]):
        if "boundary" in step:
            await runner.boundary()
            continue
        if "expire" in step:
            assert step["expire"] == "checkpoint"  # decisions: recorded_approval
            clock.advance(minutes=adapter.config.expiry_minutes, seconds=1)
            continue
        outcome = await runner.call(step)
        expect = step["expect"]
        expected = (
            expect
            if expect == "run"
            else expect["refuse"]
            if "refuse" in expect
            else "output " + expect["refuse_output"]
        )
        assert outcome == expected, (
            f"step {index} ({step['call']}): {outcome} != {expected}"
        )
