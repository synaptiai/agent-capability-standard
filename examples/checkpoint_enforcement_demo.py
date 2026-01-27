#!/usr/bin/env python3
"""
Checkpoint Enforcement Demo

Demonstrates the checkpoint-before-mutation safety pattern:
1. Mutations are BLOCKED without a valid checkpoint
2. Mutations are ALLOWED after creating a checkpoint
3. After mutation, checkpoint is consumed (new one needed)

This is the core safety mechanism of Grounded Agency.

Usage:
    python examples/checkpoint_enforcement_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig


async def main():
    """Run checkpoint enforcement demonstration."""
    print("=" * 60)
    print("Checkpoint Enforcement Demo")
    print("=" * 60)

    # Create adapter in strict mode
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            strict_mode=True,
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
        )
    )

    permission_callback = adapter._make_permission_callback()

    # Phase 1: No checkpoint - mutations blocked
    print("\n--- Phase 1: No Checkpoint ---")
    print(f"Valid checkpoint exists: {adapter.has_valid_checkpoint()}")

    mutations = [
        ("Write", {"file_path": "test.txt", "content": "hello"}),
        ("Edit", {"file_path": "test.txt", "old_string": "a", "new_string": "b"}),
        ("Bash", {"command": "rm /tmp/test.txt"}),
    ]

    print("\nAttempting mutations without checkpoint:")
    for tool_name, tool_input in mutations:
        result = await permission_callback(tool_name, tool_input, None)

        if isinstance(result, dict):
            allowed = result.get("allowed", True)
            if not allowed:
                print(f"  {tool_name}: BLOCKED")
            else:
                print(f"  {tool_name}: allowed")
        else:
            # SDK types
            type_name = type(result).__name__
            if "Deny" in type_name:
                print(f"  {tool_name}: BLOCKED")
            else:
                print(f"  {tool_name}: allowed")

    # Phase 2: Create checkpoint - mutations allowed
    print("\n--- Phase 2: With Checkpoint ---")
    checkpoint_id = adapter.create_checkpoint(
        scope=["*.txt", "*.md"],
        reason="Demo: Before file modifications",
    )
    print(f"Created checkpoint: {checkpoint_id}")
    print(f"Valid checkpoint exists: {adapter.has_valid_checkpoint()}")

    print("\nAttempting same mutations with checkpoint:")
    for tool_name, tool_input in mutations[:2]:  # Just Write and Edit
        result = await permission_callback(tool_name, tool_input, None)

        if isinstance(result, dict):
            allowed = result.get("allowed", True)
            if allowed:
                print(f"  {tool_name}: ALLOWED (checkpoint: {checkpoint_id[:20]}...)")
            else:
                print(f"  {tool_name}: blocked")
        else:
            type_name = type(result).__name__
            if "Allow" in type_name:
                print(f"  {tool_name}: ALLOWED (checkpoint: {checkpoint_id[:20]}...)")
            else:
                print(f"  {tool_name}: blocked")

    # Phase 3: Consume checkpoint - back to blocked
    print("\n--- Phase 3: After Consuming Checkpoint ---")
    consumed_id = adapter.consume_checkpoint()
    print(f"Consumed checkpoint: {consumed_id}")
    print(f"Valid checkpoint exists: {adapter.has_valid_checkpoint()}")

    print("\nAttempting mutations after checkpoint consumed:")
    for tool_name, tool_input in mutations[:2]:
        result = await permission_callback(tool_name, tool_input, None)

        if isinstance(result, dict):
            allowed = result.get("allowed", True)
            if not allowed:
                print(f"  {tool_name}: BLOCKED (need new checkpoint)")
            else:
                print(f"  {tool_name}: allowed")
        else:
            type_name = type(result).__name__
            if "Deny" in type_name:
                print(f"  {tool_name}: BLOCKED (need new checkpoint)")
            else:
                print(f"  {tool_name}: allowed")

    # Phase 4: Read-only operations always allowed
    print("\n--- Phase 4: Read-Only Operations ---")
    print("Read-only tools don't require checkpoints:")

    read_only = [
        ("Read", {"path": "README.md"}),
        ("Grep", {"pattern": "def", "path": "src/"}),
        ("Bash", {"command": "ls -la"}),
        ("Bash", {"command": "git status"}),
    ]

    for tool_name, tool_input in read_only:
        result = await permission_callback(tool_name, tool_input, None)

        if isinstance(result, dict):
            allowed = result.get("allowed", True)
        else:
            type_name = type(result).__name__
            allowed = "Allow" in type_name

        mapping = adapter.mapper.map_tool(tool_name, tool_input)
        print(f"  {tool_name} ({mapping.capability_id}): {'ALLOWED' if allowed else 'blocked'}")

    print("\n" + "=" * 60)
    print("Checkpoint Enforcement Summary")
    print("=" * 60)
    print("""
Key Points:
1. High-risk mutations (Write, Edit, rm, etc.) REQUIRE checkpoints
2. Checkpoints are consumed after use - one per mutation batch
3. Read-only operations (Read, Grep, ls) ALWAYS allowed
4. In strict_mode=False, mutations warn but proceed
""")


if __name__ == "__main__":
    asyncio.run(main())
