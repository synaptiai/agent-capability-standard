#!/usr/bin/env python3
"""
Grounded Query Demo

Demonstrates using grounded_query() as a drop-in replacement for
the SDK's query() function, with automatic safety enforcement and
cost tracking.

Prerequisites:
    pip install claude-agent-sdk

Usage:
    python examples/grounded_query_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import (
    CostSummary,
    GroundedAgentAdapter,
    GroundedAgentConfig,
    GroundedClient,
)


async def demo_cost_summary():
    """Demonstrate CostSummary tracking."""
    print("\n" + "=" * 60)
    print("Demo 1: CostSummary")
    print("=" * 60)

    summary = CostSummary()
    print(f"Initial: ${summary.total_usd:.4f}, turns={summary.turn_count}")

    # Simulate cost updates from multiple result messages
    summary.total_usd = 0.015
    summary.by_model["sonnet"] = 0.015
    summary.turn_count = 1

    print(f"After turn 1: ${summary.total_usd:.4f} ({summary.by_model})")

    summary.total_usd = 0.032
    summary.by_model["sonnet"] = 0.032
    summary.turn_count = 2

    print(f"After turn 2: ${summary.total_usd:.4f} ({summary.by_model})")


async def demo_adapter_cost_tracking():
    """Demonstrate cost tracking through the adapter."""
    print("\n" + "=" * 60)
    print("Demo 2: Adapter Cost Tracking")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
            max_budget_usd=5.00,
            model="sonnet",
        )
    )

    print(f"Budget cap: ${adapter.config.max_budget_usd}")
    print(f"Default model: {adapter.config.model}")
    print(f"Cost so far: ${adapter.cost_summary.total_usd:.4f}")

    # Simulate _update_cost_summary
    from dataclasses import dataclass

    from grounded_agency.query import _update_cost_summary

    @dataclass
    class MockResult:
        total_cost_usd: float = 0.0
        model: str = "sonnet"

    _update_cost_summary(adapter, MockResult(total_cost_usd=0.042))
    _update_cost_summary(adapter, MockResult(total_cost_usd=0.087))

    print(f"After 2 turns: ${adapter.cost_summary.total_usd:.4f}")
    print(f"Turns: {adapter.cost_summary.turn_count}")
    print(f"Per-model: {adapter.cost_summary.by_model}")


async def demo_grounded_query_with_sdk():
    """Try using grounded_query with the actual SDK (if available)."""
    print("\n" + "=" * 60)
    print("Demo 3: grounded_query() with SDK")
    print("=" * 60)

    try:
        from grounded_agency import grounded_query

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=str(
                    Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
                ),
                max_budget_usd=1.00,
            )
        )

        # Create checkpoint for any mutations
        adapter.create_checkpoint(["*"], "Demo checkpoint")

        print("grounded_query() is available")
        print("To use it with the SDK:")
        print()
        print("  async for msg in grounded_query('Hello', adapter=adapter):")
        print("      print(msg)")
        print()
        print(f"  # Cost: ${adapter.cost_summary.total_usd:.4f}")

    except ImportError:
        print("Claude Agent SDK not installed.")
        print("Install with: pip install claude-agent-sdk")


async def demo_grounded_client():
    """Demonstrate GroundedClient usage pattern."""
    print("\n" + "=" * 60)
    print("Demo 4: GroundedClient Pattern")
    print("=" * 60)

    print("GroundedClient wraps ClaudeSDKClient:")
    print()
    print("  adapter = GroundedAgentAdapter(config)")
    print("  adapter.create_checkpoint(['*'], 'Before edits')")
    print()
    print("  async with GroundedClient(adapter) as client:")
    print("      await client.query('Edit the config')")
    print("      async for msg in client.receive_response():")
    print("          print(msg)")
    print()
    print("  print(f'Cost: ${adapter.cost_summary.total_usd}')")


async def main():
    """Run all demos."""
    print("=" * 60)
    print("Grounded Query & Client Demo")
    print("=" * 60)

    await demo_cost_summary()
    await demo_adapter_cost_tracking()
    await demo_grounded_query_with_sdk()
    await demo_grounded_client()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
