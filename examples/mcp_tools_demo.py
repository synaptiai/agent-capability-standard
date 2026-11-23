#!/usr/bin/env python3
"""
MCP Capability-Aware Tools Demo

Demonstrates registering MCP tools with capability metadata
so that safety enforcement (checkpoints, approval, rate limits) applies.
A tool's flags are the stricter of its declaration and the ontology's.

Usage:
    python examples/mcp_tools_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig


async def approve(tool_name: str, tool_input: dict, context: object) -> object:
    """Stand-in for the host's ``can_use_tool`` callback: approves every call.

    A real host shows the person the tool and its input and returns their
    decision. Without such a callback, a call whose capability requires
    approval is denied with F502 (APPROVAL_REQUIRED).
    """
    try:
        from claude_agent_sdk import PermissionResultAllow
    except ImportError:
        from grounded_agency import FallbackPermissionAllow

        return FallbackPermissionAllow(updated_input=tool_input)
    return PermissionResultAllow(updated_input=tool_input)


def is_allowed(result: object) -> bool:
    """An SDK permission result (``behavior``) or the fallback (``allowed``)."""
    return (
        getattr(result, "behavior", None) == "allow"
        or getattr(result, "allowed", None) is True
    )


async def demo_dynamic_tool_registration():
    """Show dynamic MCP tool registration."""
    print("\n" + "=" * 60)
    print("Demo 1: Dynamic Tool Registration")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
        )
    )

    # Register tools as if they came from an MCP server
    adapter.mapper.register_mcp_tool(
        tool_name="mcp__search__query",
        capability_id="search",
        risk="low",
    )

    adapter.mapper.register_mcp_tool(
        tool_name="mcp__deploy__push",
        capability_id="execute",
        risk="high",
        mutation=True,
        requires_checkpoint=True,
    )

    # A declaration weaker than the ontology has no effect: mutate is
    # high-risk and needs a checkpoint whatever the tool says (W602).
    adapter.mapper.register_mcp_tool(
        tool_name="mcp__db__insert",
        capability_id="mutate",
        risk="low",
        requires_checkpoint=False,
    )

    # Show mappings. The last tool is not registered: it gets the
    # strictest flags.
    tools = [
        "mcp__search__query",
        "mcp__deploy__push",
        "mcp__db__insert",
        "mcp__other__tool",
    ]

    print(
        f"{'Tool':<25} {'Capability':<12} {'Risk':<8} {'Checkpoint':<11} {'Approval'}"
    )
    print("-" * 68)

    for tool_name in tools:
        mapping = adapter.mapper.map_tool(tool_name, {})
        checkpoint = "Yes" if mapping.requires_checkpoint else "No"
        approval = "Yes" if mapping.requires_approval else "No"
        print(
            f"{tool_name:<25} {mapping.capability_id:<12} {mapping.risk:<8} "
            f"{checkpoint:<11} {approval}"
        )

    print("\nDeclarations that had no effect:")
    for warning in adapter.mapper.warnings:
        print(
            f"  {warning.code_str} {warning.name} "
            f"({warning.location['tool']}): {warning.message}"
        )

    # A capability the ontology does not define is refused.
    try:
        adapter.mapper.register_mcp_tool("mcp__db__drop", capability_id="destroy")
    except ValueError as exc:
        print(f"\nRefused: {exc}")


async def demo_permission_enforcement():
    """Show that MCP tools respect checkpoint enforcement."""
    import tempfile

    print("\n" + "=" * 60)
    print("Demo 2: Permission Enforcement for MCP Tools")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                strict_mode=True,
                ontology_path=str(
                    Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
                ),
                checkpoint_dir=str(Path(tmpdir) / ".checkpoints"),
            )
        )

        # Register a high-risk MCP tool
        adapter.mapper.register_mcp_tool(
            tool_name="mcp__deploy__push",
            capability_id="execute",
            risk="high",
            mutation=True,
            requires_checkpoint=True,
        )

        # execute requires approval, so the host's callback (here:
        # approve) decides the call once the checkpoint rule is satisfied.
        callback = adapter._make_permission_callback(approve)
        pre_tool_use = adapter._make_pretooluse_safety_hook()

        async def decide(tool_use_id: str) -> object:
            # Claude Code names each call (tool_use_id), runs the PreToolUse
            # hook on it, then, unless the hook refused it, asks the
            # callback, which decides only on a call the hook checked. The
            # call holds the checkpoint it uses under that id.
            call = {"tool_name": "mcp__deploy__push", "tool_input": {}}
            out = (await pre_tool_use(call, tool_use_id, None)).get(
                "hookSpecificOutput", {}
            )
            if out.get("permissionDecision") == "deny":
                return SimpleNamespace(
                    behavior="deny", message=out["permissionDecisionReason"]
                )
            return await callback(
                "mcp__deploy__push", {}, SimpleNamespace(tool_use_id=tool_use_id)
            )

        # Without checkpoint
        result = await decide("deploy-1")
        print(f"Without checkpoint: {'allowed' if is_allowed(result) else 'BLOCKED'}")
        print(f"  {getattr(result, 'message', '')}")

        # With checkpoint
        adapter.create_checkpoint(["*"], "Before deploy")
        result = await decide("deploy-2")
        print(f"With checkpoint: {'ALLOWED' if is_allowed(result) else 'blocked'}")


async def demo_mcp_server_factory():
    """Show how create_grounded_mcp_server would work."""
    print("\n" + "=" * 60)
    print("Demo 3: MCP Server Factory Pattern")
    print("=" * 60)

    print("With claude_agent_sdk installed:")
    print()
    print("  from claude_agent_sdk import tool")
    print("  from grounded_agency import create_grounded_mcp_server")
    print()
    print('  @tool("search_docs", "Search documentation.", {"query": str})')
    print("  async def search_docs(args):")
    print("      # The search output, as JSON text (STANDARD 1.2.0 section 5.18.9);")
    print("      # a result without it fails the call with R402 (section 5.18.10).")
    print('      output = {"results": [], "evidence_anchors": [], "confidence": 0.9}')
    print('      return {"content": [{"type": "text", "text": json.dumps(output)}]}')
    print()
    print("  search_docs.metadata = {")
    print('      "capability_id": "search",')
    print('      "risk": "low",')
    print("  }")
    print()
    print("  server = create_grounded_mcp_server(")
    print('      name="doc-tools",')
    print('      version="1.0.0",')
    print("      tools=[search_docs],")
    print("      adapter=adapter,")
    print("  )")
    print()
    print("  # mcp__doc-tools__search_docs is now registered as 'search'.")
    print("  # Metadata naming a capability the ontology does not define")
    print("  # raises ValueError (V101) and no server is created.")


async def main():
    print("=" * 60)
    print("MCP Capability-Aware Tools Demo")
    print("=" * 60)

    await demo_dynamic_tool_registration()
    await demo_permission_enforcement()
    await demo_mcp_server_factory()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
