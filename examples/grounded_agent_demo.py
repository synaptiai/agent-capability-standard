#!/usr/bin/env python3
"""
Grounded Agency Agent Demo

Demonstrates all safety features of the Grounded Agency SDK integration:
1. Checkpoint-before-mutation safety
2. Evidence anchor collection
3. Blocking mutations without checkpoints
4. Audit logging

Prerequisites:
    pip install claude-agent-sdk

Usage:
    python examples/grounded_agent_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add parent to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig


async def demo_checkpoint_enforcement():
    """Show that mutations are blocked without checkpoint (in strict mode)."""
    print("\n" + "=" * 60)
    print("Demo 1: Checkpoint Enforcement")
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

    print(f"Ontology version: {adapter.ontology_version}")
    print(f"Total capabilities: {adapter.capability_count}")

    # Check high-risk capabilities
    high_risk = adapter.registry.get_high_risk_capabilities()
    print(f"\nHigh-risk capabilities (require checkpoint):")
    for cap in high_risk:
        print(f"  - {cap.id}: {cap.description}")

    # Demonstrate that mutations would be blocked
    print("\n--- Without Checkpoint ---")
    print(f"Has valid checkpoint: {adapter.has_valid_checkpoint()}")

    # Simulate permission check for Write tool
    permission_callback = adapter._make_permission_callback()
    result = await permission_callback(
        "Write",
        {"file_path": "test.txt", "content": "hello"},
        None,
    )

    print(f"Permission result for Write: {result}")
    if isinstance(result, dict) and not result.get("allowed", True):
        print(f"  Blocked: {result.get('message', 'No message')}")


async def demo_safe_mutation():
    """Show successful mutation with checkpoint."""
    print("\n" + "=" * 60)
    print("Demo 2: Safe Mutation with Checkpoint")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            strict_mode=True,
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
        )
    )

    # Create checkpoint FIRST
    checkpoint_id = adapter.create_checkpoint(
        scope=["*.txt", "*.md"],
        reason="Before creating test files",
    )
    print(f"Checkpoint created: {checkpoint_id}")
    print(f"Has valid checkpoint: {adapter.has_valid_checkpoint()}")

    # Now mutation should be allowed
    print("\n--- With Checkpoint ---")
    permission_callback = adapter._make_permission_callback()
    result = await permission_callback(
        "Write",
        {"file_path": "test.txt", "content": "hello"},
        None,
    )

    print(f"Permission result for Write: {result}")
    if isinstance(result, dict) and result.get("allowed", False):
        print("  Mutation ALLOWED with checkpoint")


async def demo_evidence_collection():
    """Show evidence anchor collection."""
    print("\n" + "=" * 60)
    print("Demo 3: Evidence Collection")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
        )
    )

    # Simulate evidence from tool uses
    from grounded_agency.state.evidence_store import EvidenceAnchor

    # Add evidence as if tools were used
    adapter.evidence_store.add_anchor(
        EvidenceAnchor.from_tool_output(
            tool_name="Read",
            tool_use_id="read_001",
            tool_input={"path": "src/main.py"},
        ),
        capability_id="retrieve",
    )

    adapter.evidence_store.add_anchor(
        EvidenceAnchor.from_tool_output(
            tool_name="Grep",
            tool_use_id="grep_002",
            tool_input={"pattern": "def main", "path": "src/"},
        ),
        capability_id="search",
    )

    adapter.evidence_store.add_anchor(
        EvidenceAnchor.from_file(
            file_path="src/main.py",
            file_hash="sha256:abc123...",
            operation="read",
        ),
        capability_id="retrieve",
    )

    # Query evidence
    print("Recent evidence anchors:")
    for ref in adapter.get_evidence(5):
        print(f"  - {ref}")

    print("\nEvidence by capability:")
    for cap_id in ["retrieve", "search"]:
        anchors = adapter.evidence_store.get_for_capability(cap_id)
        print(f"  {cap_id}: {len(anchors)} anchors")

    print("\nFile evidence:")
    for anchor in adapter.evidence_store.get_by_kind("file"):
        print(f"  - {anchor.ref}")


async def demo_tool_mapping():
    """Show tool-to-capability mapping."""
    print("\n" + "=" * 60)
    print("Demo 4: Tool-to-Capability Mapping")
    print("=" * 60)

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(
                Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
            ),
        )
    )

    # Test various tools
    test_cases = [
        ("Read", {"path": "/tmp/file.txt"}),
        ("Write", {"file_path": "/tmp/out.txt", "content": "data"}),
        ("Edit", {"file_path": "/tmp/file.txt", "old_string": "a", "new_string": "b"}),
        ("Grep", {"pattern": "error", "path": "logs/"}),
        ("Bash", {"command": "ls -la"}),
        ("Bash", {"command": "rm -rf /tmp/test"}),
        ("Bash", {"command": "curl -X POST https://api.example.com"}),
        ("Skill", {"skill": "checkpoint"}),
    ]

    print(f"{'Tool':<12} {'Input':<35} {'Capability':<12} {'Risk':<8} {'Checkpoint'}")
    print("-" * 85)

    for tool_name, tool_input in test_cases:
        mapping = adapter.mapper.map_tool(tool_name, tool_input)
        input_str = str(tool_input)[:33] + ".." if len(str(tool_input)) > 35 else str(tool_input)
        checkpoint_marker = "Yes" if mapping.requires_checkpoint else "-"
        print(
            f"{tool_name:<12} {input_str:<35} {mapping.capability_id:<12} "
            f"{mapping.risk:<8} {checkpoint_marker}"
        )


async def demo_with_sdk():
    """Demo using actual Claude Agent SDK (if available)."""
    print("\n" + "=" * 60)
    print("Demo 5: SDK Integration (if available)")
    print("=" * 60)

    try:
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

        print("Claude Agent SDK is available!")

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                strict_mode=True,
                ontology_path=str(
                    Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
                ),
            )
        )

        # Create checkpoint
        checkpoint_id = adapter.create_checkpoint(
            scope=["*"],
            reason="SDK demo checkpoint",
        )
        print(f"Checkpoint: {checkpoint_id}")

        # Wrap options
        base_options = ClaudeAgentOptions(
            allowed_tools=["Read", "Write", "Bash"],
            permission_mode="acceptEdits",
        )
        options = adapter.wrap_options(base_options)

        print("Options wrapped with grounded agency layer")
        print(f"  - enable_file_checkpointing: {options.enable_file_checkpointing}")
        print(f"  - can_use_tool callback: {options.can_use_tool is not None}")
        print(f"  - hooks configured: {options.hooks is not None}")

    except ImportError:
        print("Claude Agent SDK not installed.")
        print("To test with SDK: pip install claude-agent-sdk")
        print("\nShowing how options would be wrapped:")

        # Mock demonstration
        from dataclasses import dataclass, field

        @dataclass
        class MockClaudeAgentOptions:
            allowed_tools: list = field(default_factory=list)
            permission_mode: str = "default"
            hooks: dict = field(default_factory=dict)
            setting_sources: list = field(default_factory=lambda: ["project"])
            enable_file_checkpointing: bool = False
            can_use_tool: object = None

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=str(
                    Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
                ),
            )
        )

        base = MockClaudeAgentOptions(allowed_tools=["Read", "Write"])
        wrapped = adapter.wrap_options(base)

        print(f"\nBase options:")
        print(f"  allowed_tools: {base.allowed_tools}")
        print(f"  enable_file_checkpointing: {base.enable_file_checkpointing}")

        print(f"\nWrapped options:")
        print(f"  allowed_tools: {wrapped.allowed_tools}")
        print(f"  enable_file_checkpointing: {wrapped.enable_file_checkpointing}")
        print(f"  can_use_tool set: {wrapped.can_use_tool is not None}")
        print(f"  hooks configured: {len(wrapped.hooks.get('PostToolUse', []))} PostToolUse hooks")


async def main():
    """Run all demos."""
    print("=" * 60)
    print("Grounded Agency SDK Integration Demo")
    print("=" * 60)

    await demo_checkpoint_enforcement()
    await demo_safe_mutation()
    await demo_evidence_collection()
    await demo_tool_mapping()
    await demo_with_sdk()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
