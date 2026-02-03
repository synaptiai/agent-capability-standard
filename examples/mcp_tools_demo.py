#!/usr/bin/env python3
"""
MCP Capability-Aware Tools Demo

Demonstrates registering MCP tools with capability metadata
so that safety enforcement (checkpoints, rate limits) applies.

Usage:
    python examples/mcp_tools_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig


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

    adapter.mapper.register_mcp_tool(
        tool_name="mcp__db__insert",
        capability_id="mutate",
        risk="high",
    )

    # Show mappings
    tools = [
        "mcp__search__query",
        "mcp__deploy__push",
        "mcp__db__insert",
    ]

    print(f"{'Tool':<25} {'Capability':<12} {'Risk':<8} {'Checkpoint'}")
    print("-" * 60)

    for tool_name in tools:
        mapping = adapter.mapper.map_tool(tool_name, {})
        checkpoint = "Yes" if mapping.requires_checkpoint else "No"
        print(f"{tool_name:<25} {mapping.capability_id:<12} {mapping.risk:<8} {checkpoint}")


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

        callback = adapter._make_permission_callback()

        # Without checkpoint
        result = await callback("mcp__deploy__push", {}, None)
        # SDK types use 'behavior' attr; fallback types use 'allowed'
        behavior = getattr(result, "behavior", None)
        if behavior is not None:
            is_blocked = behavior != "allow"
        else:
            is_allowed = getattr(result, "allowed", None)
            if is_allowed is None and isinstance(result, dict):
                is_allowed = result.get("allowed")
            is_blocked = not is_allowed
        print(f"Without checkpoint: {'BLOCKED' if is_blocked else 'allowed'}")

        # With checkpoint
        adapter.create_checkpoint(["*"], "Before deploy")
        result = await callback("mcp__deploy__push", {}, None)
        behavior = getattr(result, "behavior", None)
        if behavior is not None:
            is_allowed = behavior == "allow"
        else:
            is_allowed = getattr(result, "allowed", None)
            if is_allowed is None and isinstance(result, dict):
                is_allowed = result.get("allowed")
        print(f"With checkpoint: {'ALLOWED' if is_allowed else 'blocked'}")


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
    print("  @tool")
    print("  def search_docs(query: str) -> str:")
    print('      """Search documentation."""')
    print('      return "results..."')
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
    print("  # search_docs is now registered with capability metadata")
    print("  # Safety enforcement applies automatically")


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
