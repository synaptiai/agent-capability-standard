#!/usr/bin/env python3
"""
Checkpoint Enforcement Demo

Demonstrates the checkpoint-before-mutation safety pattern:
1. Mutations are BLOCKED without a valid checkpoint (F501)
2. Mutations are ALLOWED after creating a checkpoint, once the host's
   permission callback approves them
3. After mutation, checkpoint is consumed (new one needed)
4. Read-only operations need neither a checkpoint nor approval
5. With no permission callback, approval cannot be given (F502)

This is the core safety mechanism of Grounded Agency.

Usage:
    python examples/checkpoint_enforcement_demo.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from itertools import count
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

_calls = count(1)


def call() -> SimpleNamespace:
    """The context Claude Code passes to ``can_use_tool``: it names the call
    (``tool_use_id``), which holds the checkpoint it uses. Each call has its
    own id; a call without one cannot hold a checkpoint (R407)."""
    return SimpleNamespace(tool_use_id=f"demo-{next(_calls)}")


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
            # A fresh directory: no checkpoint of an earlier run is left.
            checkpoint_dir=tempfile.mkdtemp(prefix="acs-demo-"),
        )
    )

    # What wrap_options() installs as can_use_tool when the options it wraps
    # carry the host's callback (here: approve).
    permission_callback = adapter._make_permission_callback(approve)

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
        result = await permission_callback(tool_name, tool_input, call())

        if is_allowed(result):
            print(f"  {tool_name}: allowed")
        else:
            print(f"  {tool_name}: BLOCKED")
            print(f"    {getattr(result, 'message', '')}")

    # Phase 2: Create checkpoint - mutations allowed
    print("\n--- Phase 2: With Checkpoint ---")
    checkpoint_id = adapter.create_checkpoint(
        scope=["*.txt", "*.md"],
        reason="Demo: Before file modifications",
    )
    print(f"Created checkpoint: {checkpoint_id}")
    print(f"Valid checkpoint exists: {adapter.has_valid_checkpoint()}")

    print("\nAttempting a mutation with checkpoint:")
    tool_name, tool_input = mutations[0]
    result = await permission_callback(tool_name, tool_input, call())
    if is_allowed(result):
        print(f"  {tool_name}: ALLOWED (checkpoint: {checkpoint_id[:20]}...)")
    else:
        print(f"  {tool_name}: blocked")
        print(f"    {getattr(result, 'message', '')}")

    # Phase 3: The allowed call used the checkpoint - back to blocked
    print("\n--- Phase 3: After the Checkpoint Is Used ---")
    print("The allowed call used the checkpoint: each gated call needs its own.")
    print(f"Valid checkpoint exists: {adapter.has_valid_checkpoint()}")

    print("\nAttempting mutations after checkpoint consumed:")
    for tool_name, tool_input in mutations[:2]:
        result = await permission_callback(tool_name, tool_input, call())

        if is_allowed(result):
            print(f"  {tool_name}: allowed")
        else:
            print(f"  {tool_name}: BLOCKED (need new checkpoint)")

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
        result = await permission_callback(tool_name, tool_input, call())
        allowed = is_allowed(result)

        mapping = adapter.mapper.map_tool(tool_name, tool_input)
        print(f"  {tool_name} ({mapping.capability_id}): {'ALLOWED' if allowed else 'blocked'}")

    # Phase 5: Approval
    print("\n--- Phase 5: Approval ---")
    print("mutate, send and execute require approval in the ontology.")
    adapter.create_checkpoint(scope=["*.txt"], reason="Demo: approval")
    pre_tool_use = adapter._make_pretooluse_safety_hook()
    write = {"tool_name": "Write", "tool_input": mutations[0][1]}

    # One call: PreToolUse holds the checkpoint under its tool_use_id, and
    # can_use_tool then decides the same call.
    write_call = call()
    asked = await pre_tool_use(write, write_call.tool_use_id, None)
    output = asked.get("hookSpecificOutput", {})
    print(f"\nPreToolUse hook answers: {output.get('permissionDecision')}")
    print(f"  {output.get('permissionDecisionReason')}")

    print("\nWith no can_use_tool callback, no one can approve:")
    no_approver = adapter._make_permission_callback()
    result = await no_approver("Write", mutations[0][1], write_call)
    print(f"  Write: {'allowed' if is_allowed(result) else 'BLOCKED'}")
    print(f"    {getattr(result, 'message', '')}")

    print("\n" + "=" * 60)
    print("Checkpoint Enforcement Summary")
    print("=" * 60)
    print("""
Key Points:
1. High-risk mutations (Write, Edit, rm, etc.) REQUIRE checkpoints (F501)
2. Checkpoints are consumed after use - one per checkpoint-gated tool call
   (each call reserves the checkpoint under its tool_use_id)
3. Read-only operations (Read, Grep, ls) ALWAYS allowed
4. In strict_mode=False, mutations warn but proceed
5. A call whose capability requires approval is put to the host's
   can_use_tool callback; with none it is denied (F502), unless the
   adapter is configured with approval="off"
""")


if __name__ == "__main__":
    asyncio.run(main())
