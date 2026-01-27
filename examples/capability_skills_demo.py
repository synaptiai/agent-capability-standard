#!/usr/bin/env python3
"""
Capability Skills Demo

Demonstrates how Claude can autonomously invoke capability skills
to satisfy safety requirements:

1. Claude invokes the 'checkpoint' skill when needed
2. The skill_tracker hook detects this and updates CheckpointTracker
3. Subsequent mutations are now allowed

This enables a conversational safety pattern:
  User: "Create a checkpoint then edit config.yaml"
  Claude: [invokes checkpoint skill, then Edit tool]

Usage:
    python examples/capability_skills_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.hooks.skill_tracker import create_skill_tracker


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
        )
    )

    # Get the skill tracker hook
    skill_hook = create_skill_tracker(adapter.checkpoint_tracker)
    permission_callback = adapter._make_permission_callback()

    print("\n--- Initial State ---")
    print(f"Valid checkpoint: {adapter.has_valid_checkpoint()}")

    # Try Write without checkpoint
    print("\nAttempting Write without checkpoint:")
    result = await permission_callback(
        "Write",
        {"file_path": "config.yaml", "content": "debug: true"},
        None,
    )
    blocked = isinstance(result, dict) and not result.get("allowed", True)
    print(f"  Result: {'BLOCKED' if blocked else 'allowed'}")

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

    # Invoke the skill tracker hook (as SDK would)
    await skill_hook(skill_input_data, "skill_001", None)

    print(f"\n--- After Skill Invocation ---")
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
        None,
    )
    allowed = isinstance(result, dict) and result.get("allowed", True)
    print(f"  Result: {'ALLOWED' if allowed else 'blocked'}")

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

3. The checkpoint skill executes (e.g., git stash, file copy)

4. PostToolUse hook (skill_tracker) detects the skill invocation

5. CheckpointTracker is updated with a valid checkpoint

6. Claude can now use Write/Edit tools on files in scope

7. After mutations complete, checkpoint can be consumed
   or used for rollback if verification fails
""")

    print("\n" + "=" * 60)
    print("Skill Integration Summary")
    print("=" * 60)
    print("""
Key Points:
- Skills are SKILL.md files in skills/<name>/
- Claude autonomously invokes skills based on context
- skill_tracker hook updates CheckpointTracker when
  the 'checkpoint' skill is invoked
- This enables natural language safety: "checkpoint then edit"
""")


if __name__ == "__main__":
    asyncio.run(main())
