"""The SDK adapter's destination policy (STANDARD v1.2 §4.4.2, §5.18.10)
and its shared checkpoint scope across subagents (§5.15.4, §5.18.5)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from claude_agent_sdk import PermissionResultAllow

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.state.snapshots import FileSnapshotStore

POLICY = ["https://hooks.example.com/*"]


def make(ontology_path: str, tmp_path: Path, **kw: Any) -> GroundedAgentAdapter:
    kw.setdefault("approval", "off")
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            **kw,
        )
    )


def bind_send(adapter: GroundedAgentAdapter, destination: str | None = "/to") -> None:
    record: dict[str, Any] = {
        "tool": "mcp__mail__deliver",
        "standard": "1.2.0",
        "ontology": adapter.registry.version,
        "capability": "send",
    }
    if destination is not None:
        record["destination"] = destination
    adapter.mapper.register_binding(record)


def reason(result: dict[str, Any]) -> str | None:
    out = result.get("hookSpecificOutput") or {}
    if out.get("permissionDecision") != "deny":
        return None
    return str(out.get("permissionDecisionReason"))


async def pre(adapter: GroundedAgentAdapter, args: dict[str, Any], call: str) -> Any:
    hook = adapter._make_pretooluse_safety_hook()
    return await hook(
        {"tool_name": "mcp__mail__deliver", "tool_input": args}, call, None
    )


@pytest.mark.asyncio
async def test_a_destination_the_policy_does_not_allow_is_f504(
    ontology_path: str, tmp_path: Path
) -> None:
    adapter = make(ontology_path, tmp_path, allowed_destinations=POLICY)
    bind_send(adapter)
    adapter.create_checkpoint(["*"], "t")
    denied = reason(await pre(adapter, {"to": "https://evil.net/x"}, "c1"))
    assert denied is not None and denied.startswith("F504 CONSTRAINT_VIOLATED:")
    assert "evil.net" not in denied
    # Refused before the checkpoint: it is still valid.
    assert adapter.has_valid_checkpoint()
    assert (
        reason(await pre(adapter, {"to": "https://hooks.example.com/r"}, "c2")) is None
    )


@pytest.mark.asyncio
async def test_a_send_whose_destination_the_layer_cannot_tell_is_f504(
    ontology_path: str, tmp_path: Path
) -> None:
    adapter = make(ontology_path, tmp_path, allowed_destinations=POLICY)
    bind_send(adapter, destination=None)
    adapter.create_checkpoint(["*"], "t")
    denied = reason(await pre(adapter, {"to": "https://hooks.example.com/r"}, "c1"))
    assert denied is not None and "cannot tell where" in denied
    bound = make(ontology_path, tmp_path / "2", allowed_destinations=POLICY)
    bind_send(bound)
    bound.create_checkpoint(["*"], "t")
    denied = reason(await pre(bound, {"to": 7}, "c2"))
    assert denied is not None and "is not a string" in denied


@pytest.mark.asyncio
async def test_an_unbound_tool_is_f504_under_a_policy(
    ontology_path: str, tmp_path: Path
) -> None:
    """An unbound tool is treated as the strictest case (§5.18.2): the
    layer cannot tell whether or where it sends, so while a destination
    policy is in force it is refused (§4.4.2, §5.18.10), before the
    checkpoint is used."""
    adapter = make(ontology_path, tmp_path, allowed_destinations=POLICY)
    adapter.create_checkpoint(["*"], "t")
    hook = adapter._make_pretooluse_safety_hook()
    args = {"url": "https://evil.net/x", "body": "data"}
    denied = reason(
        await hook({"tool_name": "mcp__web__post", "tool_input": args}, "c1", None)
    )
    assert denied is not None and denied.startswith("F504 CONSTRAINT_VIOLATED:")
    assert "no binding" in denied and "evil.net" not in denied
    assert adapter.has_valid_checkpoint()
    # Without a policy, it is the strictest case and nothing more: it holds
    # the checkpoint and goes on.
    open_ = make(ontology_path, tmp_path / "2")
    open_.create_checkpoint(["*"], "t")
    hook = open_._make_pretooluse_safety_hook()
    assert (
        reason(
            await hook({"tool_name": "mcp__web__post", "tool_input": args}, "c2", None)
        )
        is None
    )


@pytest.mark.asyncio
async def test_an_applied_profiles_destination_policy_alone_is_in_force(
    ontology_path: str, tmp_path: Path
) -> None:
    profile = {"domain": "d", "version": "1.0.0", "allowed_destinations": ["mailto:*"]}
    adapter = make(ontology_path, tmp_path, approval="ask", profiles=[profile])
    bind_send(adapter)
    adapter.create_checkpoint(["*"], "t")
    denied = reason(await pre(adapter, {"to": "https://x.example/"}, "c1"))
    assert denied is not None and denied.startswith("F504 CONSTRAINT_VIOLATED:")
    # An empty list allows no send.
    none = make(
        ontology_path,
        tmp_path / "2",
        approval="ask",
        profiles=[{**profile, "allowed_destinations": []}],
    )
    bind_send(none)
    none.create_checkpoint(["*"], "t")
    assert reason(await pre(none, {"to": "mailto:ops@example.com"}, "c2")) is not None


def bind_composite(adapter: GroundedAgentAdapter, *invokes: str) -> None:
    adapter.mapper.register_binding(
        {
            "tool": "mcp__mail__digest_and_deliver",
            "standard": "1.2.0",
            "ontology": adapter.registry.version,
            "capability": "generate",
            "invokes": list(invokes),
        }
    )


async def pre_tool(
    adapter: GroundedAgentAdapter, tool: str, args: dict[str, Any], call: str
) -> Any:
    hook = adapter._make_pretooluse_safety_hook()
    return await hook({"tool_name": tool, "tool_input": args}, call, None)


@pytest.mark.asyncio
async def test_a_composite_that_invokes_a_send_is_f504_under_a_policy(
    ontology_path: str, tmp_path: Path
) -> None:
    """§5.18.4: every check but checkpoint and approval applies to nested
    calls. This layer does not see them, so a composite whose bindings
    send, directly or through another composite, is refused while a
    destination policy is in force (§4.4.2)."""
    adapter = make(ontology_path, tmp_path, allowed_destinations=POLICY)
    bind_send(adapter)
    bind_composite(adapter, "mcp__mail__deliver")
    adapter.mapper.register_binding(
        {
            "tool": "mcp__mail__weekly",
            "standard": "1.2.0",
            "ontology": adapter.registry.version,
            "capability": "generate",
            "invokes": ["mcp__mail__digest_and_deliver"],
        }
    )
    adapter.create_checkpoint(["*"], "t")
    for tool in ("mcp__mail__digest_and_deliver", "mcp__mail__weekly"):
        denied = reason(await pre_tool(adapter, tool, {"topic": "x"}, f"c-{tool}"))
        assert denied is not None and denied.startswith("F504 CONSTRAINT_VIOLATED:")
        assert "mcp__mail__deliver" in denied and "nested" in denied
    # No policy, no check.
    free = make(ontology_path, tmp_path / "2")
    bind_send(free)
    bind_composite(free, "mcp__mail__deliver")
    free.create_checkpoint(["*"], "t")
    assert (
        reason(await pre_tool(free, "mcp__mail__digest_and_deliver", {}, "c3")) is None
    )


@pytest.mark.asyncio
async def test_no_policy_no_check(ontology_path: str, tmp_path: Path) -> None:
    adapter = make(ontology_path, tmp_path)
    bind_send(adapter, destination=None)
    adapter.create_checkpoint(["*"], "t")
    assert reason(await pre(adapter, {"to": "https://evil.net/x"}, "c1")) is None


def test_an_invalid_pattern_refuses_the_configuration(
    ontology_path: str, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="allowed_destinations"):
        make(
            ontology_path,
            tmp_path,
            allowed_destinations=["https://hooks.example.com:*"],
        )


@pytest.mark.asyncio
async def test_changed_arguments_are_checked_against_the_policy(
    ontology_path: str, tmp_path: Path
) -> None:
    """§5.18.7: arguments the host changed are checked again against every
    row of §5.18.10, the destination row included."""
    adapter = make(ontology_path, tmp_path, approval="ask", allowed_destinations=POLICY)
    bind_send(adapter)
    adapter.create_checkpoint(["*"], "t")

    async def host(tool: str, args: dict[str, Any], context: Any) -> Any:
        return PermissionResultAllow(updated_input={"to": "https://evil.net/x"})

    callback = adapter._make_permission_callback(host)
    result = await callback(
        "mcp__mail__deliver",
        {"to": "https://hooks.example.com/r"},
        SimpleNamespace(tool_use_id="c1"),
    )
    assert getattr(result, "behavior", None) != "allow"
    assert result.message.startswith("F504 CONSTRAINT_VIOLATED:")


@pytest.mark.asyncio
async def test_subagent_mutation_uses_shared_checkpoint(
    ontology_path: str, tmp_path: Path
) -> None:
    """§5.15.4, tool-calling hosts: this adapter orders a subagent's calls
    in the delegator's scope (one scope per adapter instance), so one
    checkpoint authorises one change, whichever agent makes it."""
    adapter = make(ontology_path, tmp_path)
    hook = adapter._make_pretooluse_safety_hook()
    consumer = adapter._make_mutation_consumer()

    def write(call: str, agent: str | None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "tool_name": "Write",
            "tool_input": {"file_path": f"{call}.txt"},
            "session_id": "s1",
        }
        if agent is not None:
            data["agent_id"] = agent
        return data

    adapter.create_checkpoint(["*"], "before the delegation")
    # The parent delegates (the mapper classifies Task as delegate) ...
    assert adapter.mapper.map_tool("Task", {}).capability_id == "delegate"
    # ... and the subagent's Write uses the shared checkpoint.
    assert await hook(write("sub", "agent-1"), "w1", None) == {}
    await consumer(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "sub.txt"},
            "tool_response": {},
        },
        "w1",
        None,
    )
    assert not adapter.has_valid_checkpoint()
    denied = reason(await hook(write("parent", None), "w2", None))
    assert denied is not None and denied.startswith("F501 CHECKPOINT_REQUIRED:")
    adapter.create_checkpoint(["*"], "again")
    assert await hook(write("parent", None), "w3", None) == {}


def test_snapshots_protect_the_audit_log(ontology_path: str, tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    snapshots = FileSnapshotStore(root, tmp_path / "store")
    adapter = make(
        ontology_path,
        tmp_path,
        snapshots=snapshots,
        audit_log_path=str(root / "logs" / "audit.log"),
    )
    assert "logs/audit.log" in snapshots.protected
    assert adapter.checkpoint_tracker.snapshots is snapshots


def test_snapshots_protect_the_evidence_store(
    ontology_path: str, tmp_path: Path
) -> None:
    """Evidence is the record of what happened, never within a rollback's
    reach (§4.4.1): a restore leaves an evidence file under the root as it
    is, and later records still reach it."""
    from grounded_agency.state.evidence_store import EvidenceAnchor
    from grounded_agency.state.jsonl_evidence_store import JsonlEvidenceStore

    root = tmp_path / "work"
    root.mkdir()
    (root / "app.txt").write_text("v1")
    evidence = JsonlEvidenceStore(root / "evidence.jsonl")
    evidence.add_anchor(EvidenceAnchor.from_tool_output("Read", "t1", {"path": "a"}))
    snapshots = FileSnapshotStore(root, root / ".snapshots")
    adapter = make(
        ontology_path, tmp_path, snapshots=snapshots, evidence_store=evidence
    )
    assert "evidence.jsonl" in snapshots.protected
    tracker = adapter.checkpoint_tracker
    checkpoint = tracker.create_checkpoint(["*"], "before the edit")
    assert "evidence.jsonl" in tracker.checkpoint_output(checkpoint)["excluded"]
    (root / "app.txt").write_text("v2")
    evidence.add_anchor(EvidenceAnchor.from_tool_output("Edit", "t2", {"path": "a"}))
    restored = tracker.restore_checkpoint(checkpoint)
    assert restored.restored
    assert (root / "app.txt").read_text() == "v1"
    assert {c["item"] for c in restored.changes_reverted} == {"app.txt"}
    evidence.add_anchor(EvidenceAnchor.from_tool_output("Read", "t3", {"path": "a"}))
    lines = (root / "evidence.jsonl").read_text().splitlines()
    assert len(lines) == len(evidence) == 3
