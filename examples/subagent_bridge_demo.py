#!/usr/bin/env python3
"""
Subagent Bridge Demo

Demonstrates bridging the OrchestrationRuntime's agent registry
to SDK-compatible AgentDefinition format via to_sdk_agents().

Usage:
    python examples/subagent_bridge_demo.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import (
    GroundedAgentAdapter,
    GroundedAgentConfig,
    OrchestrationConfig,
    OrchestrationRuntime,
)


# Mock for demonstration without SDK
@dataclass
class MockClaudeAgentOptions:
    allowed_tools: list = field(default_factory=list)
    permission_mode: str = "default"
    hooks: dict = field(default_factory=dict)
    setting_sources: list = field(default_factory=lambda: ["project"])
    enable_file_checkpointing: bool = False
    can_use_tool: object = None
    output_format: dict | None = None
    max_budget_usd: float | None = None
    model: str | None = None
    max_turns: int | None = None
    agents: dict | None = None


async def demo_agent_registration():
    """Show registering agents and exporting to SDK format."""
    print("\n" + "=" * 60)
    print("Demo 1: Agent Registration & SDK Export")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
        )
    )

    runtime = OrchestrationRuntime(
        capability_registry=adapter.registry,
        evidence_store=adapter.evidence_store,
    )

    # Register agents with metadata
    runtime.register_agent(
        "analyst",
        capabilities={"search", "retrieve", "classify"},
        metadata={
            "description": "Research and analysis agent",
            "system_prompt": "You are a research analyst.",
            "model": "sonnet",
            "allowed_tools": ["Read", "Grep", "WebSearch"],
        },
    )

    runtime.register_agent(
        "writer",
        capabilities={"generate", "mutate"},
        metadata={
            "description": "Content generation and editing agent",
            "system_prompt": "You are a technical writer.",
            "model": "sonnet",
            "allowed_tools": ["Read", "Write", "Edit"],
        },
    )

    runtime.register_agent(
        "reviewer",
        capabilities={"verify", "critique"},
        metadata={
            "description": "Code review agent",
            "model": "opus",
            "allowed_tools": ["Read", "Grep"],
        },
    )

    # Export to SDK format
    sdk_agents = runtime.to_sdk_agents()

    print(f"Registered {len(sdk_agents)} agents")
    print()
    print(json.dumps(sdk_agents, indent=2))


async def demo_wrap_options_with_agents():
    """Show that wrap_options injects agents from orchestrator."""
    print("\n" + "=" * 60)
    print("Demo 2: wrap_options with Orchestrator Agents")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
        )
    )

    runtime = OrchestrationRuntime(
        capability_registry=adapter.registry,
        evidence_store=adapter.evidence_store,
    )

    runtime.register_agent(
        "helper",
        capabilities={"search", "retrieve"},
        metadata={
            "description": "Helper agent",
            "model": "haiku",
            "allowed_tools": ["Read", "Grep"],
        },
    )

    # Attach orchestrator to adapter
    adapter.orchestrator = runtime

    # wrap_options should inject agents
    base = MockClaudeAgentOptions(allowed_tools=["Read", "Write"])
    wrapped = adapter.wrap_options(base)

    print(f"Agents injected: {wrapped.agents is not None}")
    if wrapped.agents:
        for agent_id, agent_def in wrapped.agents.items():
            print(f"  {agent_id}: {agent_def['description']} ({agent_def['model']})")


async def demo_no_override_existing_agents():
    """Show that existing agents aren't overridden."""
    print("\n" + "=" * 60)
    print("Demo 3: Existing Agents Not Overridden")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
        )
    )

    runtime = OrchestrationRuntime(
        capability_registry=adapter.registry,
        evidence_store=adapter.evidence_store,
    )
    runtime.register_agent("x", capabilities={"search"})
    adapter.orchestrator = runtime

    # Base already has agents
    existing = {"my_agent": {"description": "Pre-existing"}}
    base = MockClaudeAgentOptions(agents=existing)
    wrapped = adapter.wrap_options(base)

    print(f"Kept existing agents: {wrapped.agents == existing}")
    print(f"Agents: {wrapped.agents}")


async def main():
    print("=" * 60)
    print("Subagent Bridge Demo")
    print("=" * 60)

    await demo_agent_registration()
    await demo_wrap_options_with_agents()
    await demo_no_override_existing_agents()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
