#!/usr/bin/env python3
"""
Structured Output & Budget Enforcement Demo

Demonstrates configuring GroundedAgentConfig with:
- output_format for structured JSON responses
- max_budget_usd for cost caps
- model and max_turns defaults

Usage:
    python examples/structured_output_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig


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


async def demo_structured_output():
    """Show structured output configuration."""
    print("\n" + "=" * 60)
    print("Demo 1: Structured Output")
    print("=" * 60)

    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Change summary"},
            "files_changed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files modified",
            },
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
        },
        "required": ["summary", "files_changed", "risk_level"],
    }

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
            output_format=schema,
        )
    )

    base = MockClaudeAgentOptions(allowed_tools=["Read", "Write"])
    wrapped = adapter.wrap_options(base)

    print(f"output_format injected: {wrapped.output_format is not None}")
    print(f"Schema type: {wrapped.output_format.get('type')}")
    print(f"Required fields: {wrapped.output_format.get('required')}")


async def demo_budget_enforcement():
    """Show budget and model configuration."""
    print("\n" + "=" * 60)
    print("Demo 2: Budget & Model Defaults")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
            max_budget_usd=2.50,
            model="sonnet",
            max_turns=15,
        )
    )

    base = MockClaudeAgentOptions(allowed_tools=["Read"])
    wrapped = adapter.wrap_options(base)

    print(f"max_budget_usd: ${wrapped.max_budget_usd}")
    print(f"model: {wrapped.model}")
    print(f"max_turns: {wrapped.max_turns}")

    # Show that existing values aren't overridden
    print("\n--- Override Protection ---")
    base_with_budget = MockClaudeAgentOptions(
        allowed_tools=["Read"],
        max_budget_usd=10.0,
        model="opus",
    )
    wrapped2 = adapter.wrap_options(base_with_budget)
    print(f"Config says $2.50 but base says $10.00 → ${wrapped2.max_budget_usd}")
    print(f"Config says sonnet but base says opus → {wrapped2.model}")


async def demo_no_injection_when_none():
    """Show that None config values don't inject."""
    print("\n" + "=" * 60)
    print("Demo 3: No Injection for None Values")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
            # All new fields default to None
        )
    )

    base = MockClaudeAgentOptions()
    wrapped = adapter.wrap_options(base)

    print(f"output_format: {wrapped.output_format}")
    print(f"max_budget_usd: {wrapped.max_budget_usd}")
    print(f"model: {wrapped.model}")
    print(f"max_turns: {wrapped.max_turns}")
    print("All None — no injection when not configured.")


async def main():
    print("=" * 60)
    print("Structured Output & Budget Enforcement Demo")
    print("=" * 60)

    await demo_structured_output()
    await demo_budget_enforcement()
    await demo_no_injection_when_none()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
