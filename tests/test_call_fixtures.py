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

Each fixture is played twice. Route ``served``: as above. Route ``host``:
every tool is a tool of another MCP server (``mcp__ext__<tool>``), bound by
its record and not served by the adapter, so its result reaches the layer
only as Claude Code passes it to PostToolUse (the content items), where the
layer checks it and replaces a refused result (``updatedMCPToolOutput``).
"""

from __future__ import annotations

import inspect
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

from grounded_agency import (
    GroundedAgentAdapter,
    GroundedAgentConfig,
    ToolCapabilityMapper,
)
from grounded_agency.errors import Severity
from grounded_agency.mcp import _guarded, create_grounded_mcp_server
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


def test_the_statement_schema_checks_an_os_boundary() -> None:
    schema = json.loads((FIXTURES / "schema" / "statement.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    boundary = {
        "mechanism": "a sandbox",
        "routes_outside": "none honoured",
        "writes": "the project only",
        "credentials": "denied",
        "network": "an allowlist",
        "verification": "every source merged",
        "outside": ["the layer's hooks"],
    }
    statement = _statement()
    statement["shell_tools"] = {"Bash": boundary}
    validator.validate(statement)
    # The layer's own decision code always runs outside the boundary.
    statement["shell_tools"] = {"Bash": {**boundary, "outside": []}}
    assert not validator.is_valid(statement)
    # The boundary object is closed: a member it does not define is refused.
    statement["shell_tools"] = {"Bash": {**boundary, "x_other": "x"}}
    assert not validator.is_valid(statement)
    # The member is required.
    del statement["shell_tools"]
    assert not validator.is_valid(statement)


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
    # contract by default, and turning it off is outside the class. The rule
    # for shell-like tools (section 5.18.3) binds a claim of class SL only
    # once RFC-0011, a Draft, is Accepted, so the Bash classifier's gap is
    # not listed here yet (RFC-0011 decision 8).
    assert "not_applied" not in statement
    assert GroundedAgentConfig().check_outputs is True
    # Each setting that turns a check off is named outside the class: with
    # require_layer=False a served tool runs without the layer's decision.
    assert (
        inspect.signature(create_grounded_mcp_server)
        .parameters["require_layer"]
        .default
        is True
    )
    (outside,) = [g for g in statement["host_gaps"] if "outside class SL" in g]
    for setting in (
        "strict_mode=False",
        "approval='off'",
        "check_outputs=False",
        "create_grounded_mcp_server(require_layer=False)",
    ):
        assert setting in outside
    # The calls whose results carry no capability output are named apart
    # from the host gaps (section 10.4): they get a decision, but no output
    # check applies to them. Only Claude Code's own tools: an MCP tool bound
    # to a capability is checked, served or not (route "host" below).
    (without,) = statement["calls_without_output"]
    assert "Claude Code's own tools" in without
    assert "other MCP servers" not in without
    assert "PostToolUse hook checks the result of any other" in without
    assert not any("Claude Code's own tools" in gap for gap in statement["host_gaps"])
    # Section 5.18.3 (RFC-0011, Draft): the adapter declares no
    # operating-system boundary for Claude Code's shell-like tools.
    assert statement["shell_tools"] == dict.fromkeys(
        ("Bash", "Monitor", "PowerShell", "Skill", "Agent", "Task"), "none"
    )
    mapper = ToolCapabilityMapper()
    unbound = mapper.map_tool("an_unknown_tool", {})
    # Monitor and PowerShell get an unbound tool's worst case for any input.
    for name in ("Monitor", "PowerShell"):
        for command in ("ls", "git stash create"):
            assert mapper.map_tool(name, {"command": command}) == unbound
    # Skill, Agent and Task get one gated mapping whatever their arguments.
    for name, first, second in (
        ("Skill", {"skill": "a"}, {"skill": "b", "args": "ls"}),
        ("Agent", {"prompt": "a"}, {"prompt": "b", "subagent_type": "c"}),
        ("Task", {"prompt": "a"}, {"prompt": "b", "subagent_type": "c"}),
    ):
        mapping = mapper.map_tool(name, first)
        assert mapping == mapper.map_tool(name, second)
        assert mapping.requires_checkpoint and mapping.requires_approval
    # The Bash classifier still relaxes calls with no boundary declared,
    # which RFC-0011's rule, once Accepted, does not allow (issue #184).
    # When it stops, this fails and the statement and docs change with it.
    assert mapper.map_tool("Bash", {"command": "ls"}).capability_id == "observe"
    assert (
        mapper.map_tool("Bash", {"command": "git stash create"}).capability_id
        == "checkpoint"
    )


def test_there_are_fixtures() -> None:
    assert len(CASES) == 33


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


# A step that states no `returns`: its tool returns what the contract
# requires. A step's `returns` may be null, which is an output to refuse.
_NO_RETURNS: Any = object()


ROUTES = ("served", "host")
_SERVER = "mcp__ext__"


def _on_another_server(fixture: dict[str, Any]) -> dict[str, Any]:
    """The fixture with every tool a tool of another MCP server: each
    binding's `tool` and `invokes`, and each call, prefixed."""

    def step(item: dict[str, Any]) -> dict[str, Any]:
        if "call" not in item:
            return item
        moved = {**item, "call": _SERVER + item["call"]}
        if "nested" in item:
            moved["nested"] = [step(n) for n in item["nested"]]
        return moved

    bindings = []
    for record in fixture["bindings"]:
        moved = {**record, "tool": _SERVER + record["tool"]}
        if "invokes" in record:
            moved["invokes"] = [_SERVER + n for n in record["invokes"]]
        bindings.append(moved)
    return {
        **fixture,
        "bindings": bindings,
        "sequence": [step(s) for s in fixture["sequence"]],
    }


class _Runner:
    def __init__(
        self,
        adapter: GroundedAgentAdapter,
        clock: FakeClock,
        bindings: list[dict[str, Any]],
        route: str = "served",
    ) -> None:
        self.adapter = adapter
        self.clock = clock
        self.route = route
        self.approved: dict[str, bool] = {}
        self.options = adapter.wrap_options(ClaudeAgentOptions(can_use_tool=self._host))
        self.n = 0
        # What the current call of a bound tool returns, when its step
        # states `returns` (null included); else the contract's output.
        self.returns: Any = _NO_RETURNS
        self.tools = {
            b["tool"]: self._tool(b["capability"])
            for b in bindings
            if b.get("capability") and not b.get("control")
        }
        self.served = (
            {
                name: _guarded(
                    SdkMcpTool(
                        name=name, description=name, input_schema={}, handler=handler
                    ),
                    name,
                    adapter,
                    SdkMcpTool,
                )
                for name, handler in self.tools.items()
            }
            if route == "served"
            else {}
        )

    def _tool(self, capability: str) -> Any:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            value = (
                _output(capability, self.adapter, self.n)
                if self.returns is _NO_RETURNS
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
        response: Any = {}
        self.returns = step["returns"] if "returns" in step else _NO_RETURNS
        if step["call"] in self.served:
            tool = self.served[step["call"]]
            response = await tool.handler(data["tool_input"])
        elif step["call"] in self.tools:
            # Another server's tool: Claude Code passes its content items.
            response = (await self.tools[step["call"]](data["tool_input"]))["content"]
        posted = await self._fire(
            "PostToolUse", {**data, "tool_response": response}, call_id
        )
        replaced = [
            r["hookSpecificOutput"]["updatedMCPToolOutput"]
            for r in posted
            if "updatedMCPToolOutput" in r.get("hookSpecificOutput", {})
        ]
        if isinstance(response, dict) and response.get("is_error"):
            # The call ran; the layer refused its output (section 5.18.10).
            assert replaced == []
            return "output " + _code(response["content"][0]["text"])
        if replaced:
            # The same, at PostToolUse: the session reads the refusal.
            ((item,),) = replaced
            return "output " + _code(item["text"])
        return "run"

    async def boundary(self) -> None:
        await self._fire("Stop", {"hook_event_name": "Stop", "session_id": "s1"}, None)


def _code(text: str) -> str:
    match = CODE.match(text)
    assert match, f"a refusal that does not open with a code: {text!r}"
    return match.group(1)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
async def test_call_fixture(
    path: Path, route: str, ontology_path: str, tmp_path: Path
) -> None:
    fixture: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if route == "host":
        fixture = _on_another_server(fixture)
    statement = _statement()
    missing = set(fixture.get("needs", [])) - set(statement["features"])
    if missing:
        pytest.skip(
            f"the adapter's conformance statement lacks {sorted(missing)}: "
            f"{statement['does_not_cover'] if 'nested_calls' in missing else 'approval is by prompt'}"
        )
    present = set(fixture.get("without", [])) & set(statement["features"])
    if present:
        pytest.skip(f"the fixture is for a layer without {sorted(present)}")

    clock = FakeClock()
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            allowed_destinations=fixture.get("destination_policy"),
        ),
        clock=clock,
    )
    diagnostics = adapter.mapper.load_bindings(fixture["bindings"])
    assert [d for d in diagnostics if d.severity is Severity.ERROR] == []
    runner = _Runner(adapter, clock, fixture["bindings"], route)

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
