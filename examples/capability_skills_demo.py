#!/usr/bin/env python3
"""
Capability Skills Demo

Demonstrates how Claude can autonomously invoke capability skills
to satisfy safety requirements:

1. Claude invokes the 'checkpoint' skill when needed; loading the skill's
   instructions saves nothing, so it takes no checkpoint
2. The skill has Claude save the state with one Bash call,
   `git stash create "checkpoint:<id>"`; the checkpoint recorder sees that
   call succeed and updates CheckpointTracker (STANDARD 1.2.0 section
   5.18.6)
3. The next gated call is allowed, and uses that checkpoint up

This enables a conversational safety pattern:
  User: "Create a checkpoint then edit config.yaml"
  Claude: [invokes checkpoint skill, runs git stash create, then Edit]

Usage:
    python examples/capability_skills_demo.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.hooks.skill_tracker import create_checkpoint_recorder


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
    """Demonstrate autonomous skill invocation flow."""
    print("=" * 60)
    print("Capability Skills Demo")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            strict_mode=True,
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
            # A fresh directory, so no checkpoint of an earlier run counts.
            checkpoint_dir=tempfile.mkdtemp(prefix="acs-demo-"),
        )
    )

    # The checkpoint recorder: a PostToolUse hook for every tool
    recorder = create_checkpoint_recorder(adapter.checkpoint_tracker, adapter.mapper)
    # mutate requires approval as well as a checkpoint; approve stands in
    # for the host's can_use_tool callback.
    permission_callback = adapter._make_permission_callback(approve)

    print("\n--- Initial State ---")
    print(f"Valid checkpoint: {adapter.has_valid_checkpoint()}")

    # Try Write without checkpoint
    print("\nAttempting Write without checkpoint:")
    result = await permission_callback(
        "Write",
        {"file_path": "config.yaml", "content": "debug: true"},
        SimpleNamespace(tool_use_id="write_001"),
    )
    print(f"  Result: {'allowed' if is_allowed(result) else 'BLOCKED'}")

    print("\n--- Simulating Skill Invocation ---")
    print("Claude invokes: Skill(skill='checkpoint', scope=['*.yaml'])")

    # Simulate what happens when Claude invokes the checkpoint skill
    # This is what the PostToolUse hook would receive
    skill_input_data = {
        "tool_name": "Skill",
        "tool_input": {
            "skill": "checkpoint",
            "scope": ["*.yaml"],
            "reason": "Before modifying config files",
        },
        "tool_response": {
            "checkpoint_created": True,
            "checkpoint": {
                "id": "chk_20240115_143022_abc123",
                "scope": ["*.yaml"],
            },
        },
    }

    # The recorder sees the Skill call: it takes no checkpoint.
    await recorder(skill_input_data, "skill_001", None)
    print("\n--- After Skill Invocation ---")
    print(f"Valid checkpoint: {adapter.has_valid_checkpoint()}")

    # The skill's instructions have Claude save the state; that call, once
    # it succeeded, is what takes the checkpoint.
    print("\nClaude runs: Bash(git stash create \"checkpoint:config\")")
    await recorder(
        {
            "tool_name": "Bash",
            "tool_input": {"command": 'git stash create "checkpoint:config"'},
            "tool_response": {"stdout": "0123456789abcdef0123456789abcdef01234567\n"},
        },
        "bash_001",
        None,
    )
    print(f"Valid checkpoint: {adapter.has_valid_checkpoint()}")

    checkpoint = adapter.checkpoint_tracker.get_active_checkpoint()
    if checkpoint:
        print(f"Checkpoint ID: {checkpoint.id}")
        print(f"Scope: {checkpoint.scope}")
        print(f"Reason: {checkpoint.reason}")

    # Now try Write again - should be allowed
    print("\nAttempting Write with checkpoint:")
    result = await permission_callback(
        "Write",
        {"file_path": "config.yaml", "content": "debug: true"},
        SimpleNamespace(tool_use_id="write_002"),
    )
    print(f"  Result: {'ALLOWED' if is_allowed(result) else 'blocked'}")
    print(f"Valid checkpoint after the Write: {adapter.has_valid_checkpoint()}")

    print("\n--- Available Capability Skills ---")
    skills_path = Path(__file__).parent.parent / "skills"
    if skills_path.exists():
        skills = sorted([d.name for d in skills_path.iterdir() if d.is_dir()])
        print(f"Skills in {skills_path}:")
        for skill in skills[:15]:  # Show first 15
            print(f"  - {skill}")
        if len(skills) > 15:
            print(f"  ... and {len(skills) - 15} more")
    else:
        print("Skills directory not found")

    print("\n--- Skill Invocation Workflow ---")
    print("""
How it works:

1. User asks Claude: "Create a checkpoint before editing config"

2. Claude invokes the Skill tool:
   {
     "skill": "checkpoint",
     "scope": ["config/*.yaml"],
     "reason": "Before config changes"
   }

3. The skill's instructions have Claude save the state with one Bash
   call: git stash create "checkpoint:<id>" (the Skill call itself
   takes no checkpoint)

4. The PostToolUse checkpoint recorder sees that call succeed

5. CheckpointTracker is updated with a valid checkpoint

6. Claude can now make one gated call (Write, Edit, ...): the call
   uses the checkpoint up when it is allowed

7. A further gated call needs a new checkpoint; a checkpoint, used
   or not, can still be restored if verification fails
""")

    print("\n" + "=" * 60)
    print("Skill Integration Summary")
    print("=" * 60)
    print("""
Key Points:
- Skills are SKILL.md files in skills/<name>/
- Claude autonomously invokes skills based on context
- the checkpoint recorder updates CheckpointTracker when a call
  that saves the state (git stash create, a checkpoint tool) succeeds
- This enables natural language safety: "checkpoint then edit"
""")


if __name__ == "__main__":
    asyncio.run(main())
