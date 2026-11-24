"""A decision counts against the binding as it is when the decision arrives
(security round 5, batch 3, #2; STANDARD 1.2.0 section 5.18.7).

The PreToolUse hook refuses a binding whose approval policy this layer
cannot meet (``min_approvers`` above 1, a ``role``) and starts the clock of
``approval.expires``. The permission callback used the mapping it read
before the host's prompt, and never applied the first two: a binding the
host registered again with a stricter policy after the ask, or while the
person decided, ran on one decision with no role, and an expiry added
while the person decided was never applied. The callback now refuses a call
whose binding changed since the hook checked it, or while the host decided,
where it requires approval (F502: the decision was asked under another
binding), checks such a call again under the new binding where it does not,
and applies the policy in force when the decision arrives.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions, PermissionResultAllow

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

F501 = "F501 CHECKPOINT_REQUIRED: "
F502 = "F502 APPROVAL_REQUIRED: "
TOOL = "mcp__ops__deploy"


def _adapter(
    ontology_path: str, tmp_path: Path, clock: Any = None
) -> GroundedAgentAdapter:
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp")
        ),
        clock=clock,
    )


def _decision(result: dict[str, Any]) -> str | None:
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


def _reason(result: dict[str, Any]) -> str:
    return result.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


class _Host:
    """A host whose person allows every call; ``during`` runs while the
    person decides (the host's own code, or another task of it)."""

    def __init__(self, during: Any = None) -> None:
        self.during = during
        self.asked = 0

    async def __call__(self, tool: str, args: dict[str, Any], context: Any) -> Any:
        self.asked += 1
        if self.during is not None:
            self.during()
        return PermissionResultAllow(updated_input=args)


async def _ask(
    adapter: GroundedAgentAdapter, host: _Host, call: str, args: dict[str, Any]
) -> tuple[dict[str, Any], Any]:
    """The PreToolUse hook's answer, then the permission callback's."""
    wrapped = adapter.wrap_options(ClaudeAgentOptions(can_use_tool=host))
    pre = wrapped.hooks["PreToolUse"][-1].hooks[0]
    asked = await pre(
        {
            "tool_name": TOOL,
            "tool_input": args,
            "session_id": "s",
            "permission_mode": "default",
        },
        call,
        None,
    )
    assert _decision(asked) == "ask", asked
    assert wrapped.can_use_tool is not None
    result = await wrapped.can_use_tool(TOOL, args, SimpleNamespace(tool_use_id=call))
    return asked, result


STRICTER = [
    {"min_approvers": 3},
    {"role": "admin"},
    {"min_approvers": 2, "role": "admin"},
]


class TestAfterTheAsk:
    """The verifier's p1b: the host registers the tool again with a
    stricter policy after the hook asked, before the callback."""

    @pytest.mark.parametrize("approval", STRICTER)
    @pytest.mark.parametrize("capability", ["execute", "mutate"])
    @pytest.mark.asyncio
    async def test_the_pending_call_is_refused(
        self,
        ontology_path: str,
        tmp_path: Path,
        capability: str,
        approval: dict[str, Any],
    ) -> None:
        adapter = _adapter(ontology_path, tmp_path)
        adapter.mapper.register_mcp_tool(TOOL, capability)
        adapter.create_checkpoint(["*"], "before")
        host = _Host()
        wrapped = adapter.wrap_options(ClaudeAgentOptions(can_use_tool=host))
        pre = wrapped.hooks["PreToolUse"][-1].hooks[0]
        call = {"tool_name": TOOL, "tool_input": {}, "session_id": "s"}
        assert _decision(await pre(call, "t1", None)) == "ask"
        adapter.mapper.register_mcp_tool(TOOL, capability, approval=approval)
        result = await wrapped.can_use_tool(TOOL, {}, SimpleNamespace(tool_use_id="t1"))
        assert result.behavior == "deny"
        assert result.message.startswith(F502)
        assert host.asked == 0  # no one is asked to decide what cannot run
        assert adapter.call_records[-1]["decision"] == "refused"
        if capability == "mutate":
            # The call never ran: its checkpoint stays valid.
            assert adapter.has_valid_checkpoint()
        # A new call under the new binding is refused at the hook (control).
        fresh = await pre(call, "t2", None)
        assert _decision(fresh) == "deny" and _reason(fresh).startswith(F502)


class TestWhileThePersonDecides:
    """The verifier's p1 and p1c: the binding changes inside the host's
    prompt."""

    @pytest.mark.parametrize("approval", STRICTER)
    @pytest.mark.parametrize("capability", ["execute", "mutate"])
    @pytest.mark.asyncio
    async def test_a_stricter_policy_refuses_the_decision(
        self,
        ontology_path: str,
        tmp_path: Path,
        capability: str,
        approval: dict[str, Any],
    ) -> None:
        adapter = _adapter(ontology_path, tmp_path)
        adapter.mapper.register_mcp_tool(TOOL, capability)
        adapter.create_checkpoint(["*"], "before")
        host = _Host(
            lambda: adapter.mapper.register_mcp_tool(
                TOOL, capability, approval=approval
            )
        )
        _, result = await _ask(adapter, host, "t1", {})
        assert host.asked == 1
        assert result.behavior == "deny"
        assert result.message.startswith(F502)
        assert "changed" in result.message
        if capability == "mutate":
            assert adapter.has_valid_checkpoint()

    @pytest.mark.asyncio
    async def test_an_expiry_added_while_deciding_is_applied(
        self, ontology_path: str, tmp_path: Path, fake_clock: Any
    ) -> None:
        adapter = _adapter(ontology_path, tmp_path, fake_clock)
        adapter.mapper.register_mcp_tool(TOOL, "execute")

        def later() -> None:
            adapter.mapper.register_mcp_tool(
                TOOL, "execute", approval={"expires": "PT30S"}
            )
            fake_clock.advance(minutes=10)

        _, result = await _ask(adapter, _Host(later), "t1", {})
        assert result.behavior == "deny"
        assert result.message.startswith(F502)

    @pytest.mark.asyncio
    async def test_a_checkpoint_needed_now_is_not_held(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """A tool registered again as `mutate` while the person decided:
        the call asked as `execute` holds no checkpoint, and the decision
        was asked under the other binding."""
        adapter = _adapter(ontology_path, tmp_path)
        adapter.mapper.register_mcp_tool(TOOL, "execute")
        adapter.create_checkpoint(["*"], "before")
        host = _Host(lambda: adapter.mapper.register_mcp_tool(TOOL, "mutate"))
        _, result = await _ask(adapter, host, "t1", {})
        assert result.behavior == "deny"
        assert result.message.startswith((F501, F502))
        assert adapter.has_valid_checkpoint()

    @pytest.mark.asyncio
    async def test_a_composite_reloaded_while_deciding_is_refused(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """The verifier's v3: `outer` invokes `inner`, which is registered
        again with two approvers while the person decides on `outer`."""
        adapter = _adapter(ontology_path, tmp_path)
        inner = "mcp__ops__inner"
        adapter.mapper.register_mcp_tool(inner, "execute")
        adapter.mapper.register_mcp_tool(TOOL, "execute", invokes=[inner])
        host = _Host(
            lambda: adapter.mapper.register_mcp_tool(
                inner, "execute", approval={"min_approvers": 2}
            )
        )
        _, result = await _ask(adapter, host, "t1", {})
        assert result.behavior == "deny"
        assert result.message.startswith(F502)
        assert adapter.mapper.map_tool(TOOL, {}).approval is not None


class TestControls:
    @pytest.mark.parametrize("capability", ["execute", "mutate"])
    @pytest.mark.asyncio
    async def test_an_unchanged_binding_runs_on_its_decision(
        self, ontology_path: str, tmp_path: Path, capability: str
    ) -> None:
        adapter = _adapter(ontology_path, tmp_path)
        adapter.mapper.register_mcp_tool(
            TOOL, capability, approval={"expires": "PT30S"}
        )
        adapter.create_checkpoint(["*"], "before")
        _, result = await _ask(adapter, _Host(), "t1", {})
        assert result.behavior == "allow"
        assert adapter.call_records[-1]["decision"] == "allowed"

    @pytest.mark.asyncio
    async def test_the_same_binding_registered_again_runs(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """Registering the same binding again changes nothing."""
        adapter = _adapter(ontology_path, tmp_path)
        adapter.mapper.register_mcp_tool(TOOL, "execute")
        host = _Host(lambda: adapter.mapper.register_mcp_tool(TOOL, "execute"))
        _, result = await _ask(adapter, host, "t1", {})
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_a_call_that_needs_no_approval_is_checked_again(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """A binding that changes to another that needs no approval: the
        call is checked under it and runs (its decision is the host's)."""
        adapter = _adapter(ontology_path, tmp_path)
        adapter.mapper.register_mcp_tool(TOOL, "execute")
        host = _Host(lambda: adapter.mapper.register_mcp_tool(TOOL, "retrieve"))
        _, result = await _ask(adapter, host, "t1", {})
        assert result.behavior == "allow"
