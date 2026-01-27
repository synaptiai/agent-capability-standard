"""
Tests for Claude Agent SDK Integration

Tests the grounded_agency package components:
- CapabilityRegistry
- ToolCapabilityMapper
- CheckpointTracker
- EvidenceStore
- GroundedAgentAdapter
- Hooks
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import (
    GroundedAgentAdapter,
    GroundedAgentConfig,
    CapabilityRegistry,
    ToolCapabilityMapper,
    ToolMapping,
    CheckpointTracker,
    Checkpoint,
    EvidenceStore,
    EvidenceAnchor,
)


# Fixtures
@pytest.fixture
def ontology_path() -> str:
    """Path to the capability ontology."""
    return str(Path(__file__).parent.parent / "schemas/capability_ontology.json")


@pytest.fixture
def registry(ontology_path: str) -> CapabilityRegistry:
    """Create a fresh CapabilityRegistry."""
    return CapabilityRegistry(ontology_path)


@pytest.fixture
def mapper() -> ToolCapabilityMapper:
    """Create a fresh ToolCapabilityMapper."""
    return ToolCapabilityMapper()


@pytest.fixture
def checkpoint_tracker() -> CheckpointTracker:
    """Create a fresh CheckpointTracker."""
    return CheckpointTracker()


@pytest.fixture
def evidence_store() -> EvidenceStore:
    """Create a fresh EvidenceStore."""
    return EvidenceStore()


@pytest.fixture
def adapter(ontology_path: str) -> GroundedAgentAdapter:
    """Create a fresh GroundedAgentAdapter."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            strict_mode=True,
        )
    )


# Mock SDK types for testing
@dataclass
class MockClaudeAgentOptions:
    """Mock ClaudeAgentOptions for testing."""
    allowed_tools: list = field(default_factory=list)
    permission_mode: str = "default"
    hooks: dict = field(default_factory=dict)
    setting_sources: list = field(default_factory=lambda: ["project"])
    enable_file_checkpointing: bool = False
    can_use_tool: object = None


# =============================================================================
# CapabilityRegistry Tests
# =============================================================================

class TestCapabilityRegistry:
    """Tests for CapabilityRegistry."""

    def test_load_ontology(self, registry: CapabilityRegistry):
        """Test that ontology loads successfully."""
        assert registry.ontology is not None
        assert "nodes" in registry.ontology
        assert "edges" in registry.ontology
        assert "layers" in registry.ontology

    def test_get_capability(self, registry: CapabilityRegistry):
        """Test getting a capability by ID."""
        mutate = registry.get_capability("mutate")
        assert mutate is not None
        assert mutate.id == "mutate"
        assert mutate.layer == "EXECUTE"
        assert mutate.risk == "high"
        assert mutate.mutation is True
        assert mutate.requires_checkpoint is True

    def test_get_nonexistent_capability(self, registry: CapabilityRegistry):
        """Test that nonexistent capability returns None."""
        result = registry.get_capability("nonexistent")
        assert result is None

    def test_get_high_risk_capabilities(self, registry: CapabilityRegistry):
        """Test getting high-risk capabilities."""
        high_risk = registry.get_high_risk_capabilities()
        assert len(high_risk) > 0
        assert all(cap.risk == "high" for cap in high_risk)
        # mutate and send should be high risk
        ids = [cap.id for cap in high_risk]
        assert "mutate" in ids
        assert "send" in ids

    def test_get_checkpoint_required_capabilities(self, registry: CapabilityRegistry):
        """Test getting capabilities that require checkpoints."""
        checkpoint_required = registry.get_checkpoint_required_capabilities()
        assert len(checkpoint_required) > 0
        assert all(cap.requires_checkpoint for cap in checkpoint_required)

    def test_get_edges(self, registry: CapabilityRegistry):
        """Test getting edges for a capability."""
        edges = registry.get_edges("checkpoint")
        assert len(edges) > 0
        # checkpoint requires mutate and send
        to_caps = [e.to_cap for e in edges]
        assert "mutate" in to_caps or "send" in to_caps

    def test_get_required_capabilities(self, registry: CapabilityRegistry):
        """Test getting hard requirements."""
        required = registry.get_required_capabilities("mutate")
        # checkpoint is required for mutate
        assert "checkpoint" in required

    def test_get_layer(self, registry: CapabilityRegistry):
        """Test getting layer metadata."""
        execute = registry.get_layer("EXECUTE")
        assert "description" in execute
        assert "capabilities" in execute
        assert "mutate" in execute["capabilities"]

    def test_version(self, registry: CapabilityRegistry):
        """Test getting ontology version."""
        assert registry.version != "unknown"
        assert registry.version.startswith("2.")  # Version 2.x

    def test_capability_count(self, registry: CapabilityRegistry):
        """Test capability count."""
        assert registry.capability_count == 36  # 36 atomic capabilities


# =============================================================================
# ToolCapabilityMapper Tests
# =============================================================================

class TestToolCapabilityMapper:
    """Tests for ToolCapabilityMapper."""

    def test_map_read_tool(self, mapper: ToolCapabilityMapper):
        """Test mapping Read tool."""
        mapping = mapper.map_tool("Read", {"path": "/tmp/file.txt"})
        assert mapping.capability_id == "retrieve"
        assert mapping.risk == "low"
        assert mapping.mutation is False
        assert mapping.requires_checkpoint is False

    def test_map_write_tool(self, mapper: ToolCapabilityMapper):
        """Test mapping Write tool."""
        mapping = mapper.map_tool("Write", {"file_path": "/tmp/out.txt"})
        assert mapping.capability_id == "mutate"
        assert mapping.risk == "high"
        assert mapping.mutation is True
        assert mapping.requires_checkpoint is True

    def test_map_edit_tool(self, mapper: ToolCapabilityMapper):
        """Test mapping Edit tool."""
        mapping = mapper.map_tool("Edit", {"file_path": "/tmp/file.txt"})
        assert mapping.capability_id == "mutate"
        assert mapping.requires_checkpoint is True

    def test_map_grep_tool(self, mapper: ToolCapabilityMapper):
        """Test mapping Grep tool."""
        mapping = mapper.map_tool("Grep", {"pattern": "error"})
        assert mapping.capability_id == "search"
        assert mapping.risk == "low"
        assert mapping.requires_checkpoint is False

    def test_map_bash_read_only(self, mapper: ToolCapabilityMapper):
        """Test mapping read-only Bash commands."""
        mapping = mapper.map_tool("Bash", {"command": "ls -la"})
        assert mapping.capability_id == "observe"
        assert mapping.risk == "low"
        assert mapping.requires_checkpoint is False

    def test_map_bash_destructive(self, mapper: ToolCapabilityMapper):
        """Test mapping destructive Bash commands."""
        mapping = mapper.map_tool("Bash", {"command": "rm -rf /tmp/test"})
        assert mapping.capability_id == "mutate"
        assert mapping.risk == "high"
        assert mapping.requires_checkpoint is True

    def test_map_bash_git_push(self, mapper: ToolCapabilityMapper):
        """Test mapping git push command."""
        mapping = mapper.map_tool("Bash", {"command": "git push origin main"})
        assert mapping.capability_id == "mutate"
        assert mapping.requires_checkpoint is True

    def test_map_bash_curl_post(self, mapper: ToolCapabilityMapper):
        """Test mapping curl POST command."""
        mapping = mapper.map_tool("Bash", {"command": "curl -X POST https://api.example.com"})
        assert mapping.capability_id == "send"
        assert mapping.risk == "high"
        assert mapping.requires_checkpoint is True

    def test_map_unknown_tool(self, mapper: ToolCapabilityMapper):
        """Test mapping unknown tool."""
        mapping = mapper.map_tool("UnknownTool", {})
        assert mapping.capability_id == "observe"
        assert mapping.risk == "medium"

    def test_is_high_risk(self, mapper: ToolCapabilityMapper):
        """Test is_high_risk helper."""
        assert mapper.is_high_risk("Write", {}) is True
        assert mapper.is_high_risk("Read", {}) is False

    def test_requires_checkpoint(self, mapper: ToolCapabilityMapper):
        """Test requires_checkpoint helper."""
        assert mapper.requires_checkpoint("Write", {}) is True
        assert mapper.requires_checkpoint("Read", {}) is False


# =============================================================================
# CheckpointTracker Tests
# =============================================================================

class TestCheckpointTracker:
    """Tests for CheckpointTracker."""

    def test_create_checkpoint(self, checkpoint_tracker: CheckpointTracker):
        """Test creating a checkpoint."""
        checkpoint_id = checkpoint_tracker.create_checkpoint(
            scope=["*.py"],
            reason="Test checkpoint",
        )
        assert checkpoint_id.startswith("chk_")
        assert checkpoint_tracker.has_valid_checkpoint()

    def test_has_valid_checkpoint_false_initially(self, checkpoint_tracker: CheckpointTracker):
        """Test that no checkpoint exists initially."""
        assert checkpoint_tracker.has_valid_checkpoint() is False

    def test_consume_checkpoint(self, checkpoint_tracker: CheckpointTracker):
        """Test consuming a checkpoint."""
        checkpoint_tracker.create_checkpoint(["*"], "Test")
        assert checkpoint_tracker.has_valid_checkpoint()

        consumed_id = checkpoint_tracker.consume_checkpoint()
        assert consumed_id is not None
        assert checkpoint_tracker.has_valid_checkpoint() is False

    def test_checkpoint_scope_matching(self, checkpoint_tracker: CheckpointTracker):
        """Test checkpoint scope matching."""
        checkpoint_tracker.create_checkpoint(
            scope=["src/*.py"],
            reason="Test",
        )

        assert checkpoint_tracker.has_checkpoint_for_scope("src/main.py")
        assert checkpoint_tracker.has_checkpoint_for_scope("src/utils.py")
        assert not checkpoint_tracker.has_checkpoint_for_scope("tests/test.py")

    def test_wildcard_scope(self, checkpoint_tracker: CheckpointTracker):
        """Test wildcard scope matching."""
        checkpoint_tracker.create_checkpoint(["*"], "All files")
        assert checkpoint_tracker.has_checkpoint_for_scope("any/file.txt")
        assert checkpoint_tracker.has_checkpoint_for_scope("deeply/nested/path.py")

    def test_get_active_checkpoint(self, checkpoint_tracker: CheckpointTracker):
        """Test getting active checkpoint."""
        assert checkpoint_tracker.get_active_checkpoint() is None

        checkpoint_tracker.create_checkpoint(["*"], "Test")
        checkpoint = checkpoint_tracker.get_active_checkpoint()
        assert checkpoint is not None
        assert checkpoint.scope == ["*"]
        assert checkpoint.reason == "Test"

    def test_checkpoint_history(self, checkpoint_tracker: CheckpointTracker):
        """Test checkpoint history."""
        # Create and consume multiple checkpoints
        checkpoint_tracker.create_checkpoint(["1.py"], "First")
        checkpoint_tracker.consume_checkpoint()

        checkpoint_tracker.create_checkpoint(["2.py"], "Second")
        checkpoint_tracker.consume_checkpoint()

        history = checkpoint_tracker.get_history(10)
        assert len(history) == 2


# =============================================================================
# EvidenceStore Tests
# =============================================================================

class TestEvidenceStore:
    """Tests for EvidenceStore."""

    def test_add_anchor(self, evidence_store: EvidenceStore):
        """Test adding an evidence anchor."""
        anchor = EvidenceAnchor.from_tool_output(
            tool_name="Read",
            tool_use_id="abc123",
            tool_input={"path": "/tmp/test.txt"},
        )
        evidence_store.add_anchor(anchor)
        assert len(evidence_store) == 1

    def test_get_recent(self, evidence_store: EvidenceStore):
        """Test getting recent evidence."""
        for i in range(5):
            anchor = EvidenceAnchor.from_tool_output(
                tool_name="Read",
                tool_use_id=f"id_{i}",
                tool_input={},
            )
            evidence_store.add_anchor(anchor)

        recent = evidence_store.get_recent(3)
        assert len(recent) == 3
        assert all(ref.startswith("tool:Read:") for ref in recent)

    def test_get_by_kind(self, evidence_store: EvidenceStore):
        """Test getting evidence by kind."""
        evidence_store.add_anchor(
            EvidenceAnchor.from_tool_output("Read", "1", {})
        )
        evidence_store.add_anchor(
            EvidenceAnchor.from_file("test.py")
        )
        evidence_store.add_anchor(
            EvidenceAnchor.from_mutation("config.yaml", "write")
        )

        tool_outputs = evidence_store.get_by_kind("tool_output")
        assert len(tool_outputs) == 1

        files = evidence_store.get_by_kind("file")
        assert len(files) == 1

        mutations = evidence_store.get_mutations()
        assert len(mutations) == 1

    def test_get_for_capability(self, evidence_store: EvidenceStore):
        """Test getting evidence for a capability."""
        anchor = EvidenceAnchor.from_tool_output("Read", "1", {})
        evidence_store.add_anchor(anchor, capability_id="retrieve")

        retrieve_evidence = evidence_store.get_for_capability("retrieve")
        assert len(retrieve_evidence) == 1

    def test_evidence_anchor_from_command(self):
        """Test creating evidence from command."""
        anchor = EvidenceAnchor.from_command(
            command="ls -la",
            exit_code=0,
            tool_use_id="cmd_123",
        )
        assert anchor.ref.startswith("command:")
        assert anchor.kind == "command"
        assert anchor.metadata["exit_code"] == 0


# =============================================================================
# GroundedAgentAdapter Tests
# =============================================================================

class TestGroundedAgentAdapter:
    """Tests for GroundedAgentAdapter."""

    def test_adapter_initialization(self, adapter: GroundedAgentAdapter):
        """Test adapter initializes correctly."""
        assert adapter.registry is not None
        assert adapter.mapper is not None
        assert adapter.checkpoint_tracker is not None
        assert adapter.evidence_store is not None

    def test_wrap_options(self, adapter: GroundedAgentAdapter):
        """Test wrapping SDK options."""
        base = MockClaudeAgentOptions(allowed_tools=["Read", "Write"])
        wrapped = adapter.wrap_options(base)

        # Check injected settings
        assert wrapped.enable_file_checkpointing is True
        assert wrapped.can_use_tool is not None
        assert "Skill" in wrapped.allowed_tools
        assert "PostToolUse" in wrapped.hooks

    def test_wrap_options_preserves_existing(self, adapter: GroundedAgentAdapter):
        """Test that wrap_options preserves existing tools."""
        base = MockClaudeAgentOptions(allowed_tools=["Read", "Write", "Bash"])
        wrapped = adapter.wrap_options(base)

        assert "Read" in wrapped.allowed_tools
        assert "Write" in wrapped.allowed_tools
        assert "Bash" in wrapped.allowed_tools
        assert "Skill" in wrapped.allowed_tools

    def test_create_checkpoint_convenience(self, adapter: GroundedAgentAdapter):
        """Test adapter's create_checkpoint convenience method."""
        checkpoint_id = adapter.create_checkpoint(
            scope="*.py",
            reason="Test",
        )
        assert checkpoint_id.startswith("chk_")
        assert adapter.has_valid_checkpoint()

    def test_get_evidence(self, adapter: GroundedAgentAdapter):
        """Test adapter's get_evidence method."""
        # Add some evidence
        anchor = EvidenceAnchor.from_tool_output("Read", "1", {})
        adapter.evidence_store.add_anchor(anchor)

        evidence = adapter.get_evidence()
        assert len(evidence) == 1

    @pytest.mark.asyncio
    async def test_permission_callback_blocks_without_checkpoint(
        self, adapter: GroundedAgentAdapter
    ):
        """Test that permission callback blocks mutations without checkpoint."""
        callback = adapter._make_permission_callback()

        result = await callback(
            "Write",
            {"file_path": "test.txt"},
            None,
        )

        # Should be blocked (returns dict with allowed=False or deny type)
        if isinstance(result, dict):
            assert result.get("allowed") is False

    @pytest.mark.asyncio
    async def test_permission_callback_allows_with_checkpoint(
        self, adapter: GroundedAgentAdapter
    ):
        """Test that permission callback allows mutations with checkpoint."""
        adapter.create_checkpoint(["*"], "Test")
        callback = adapter._make_permission_callback()

        result = await callback(
            "Write",
            {"file_path": "test.txt"},
            None,
        )

        # Should be allowed
        if isinstance(result, dict):
            assert result.get("allowed") is True

    @pytest.mark.asyncio
    async def test_permission_callback_allows_read_always(
        self, adapter: GroundedAgentAdapter
    ):
        """Test that read operations are always allowed."""
        callback = adapter._make_permission_callback()

        # No checkpoint, but Read should still work
        result = await callback(
            "Read",
            {"path": "test.txt"},
            None,
        )

        if isinstance(result, dict):
            assert result.get("allowed") is True


# =============================================================================
# Hook Tests
# =============================================================================

class TestHooks:
    """Tests for hook callbacks."""

    @pytest.mark.asyncio
    async def test_evidence_collector_hook(
        self,
        evidence_store: EvidenceStore,
    ):
        """Test evidence collector hook."""
        from grounded_agency.hooks.evidence_collector import create_evidence_collector

        hook = create_evidence_collector(evidence_store)

        input_data = {
            "tool_name": "Read",
            "tool_input": {"path": "test.py"},
            "tool_response": {"content": "..."},
        }

        result = await hook(input_data, "tool_123", None)

        # Hook should return empty dict (passive)
        assert result == {}

        # Evidence should be collected
        assert len(evidence_store) > 0

    @pytest.mark.asyncio
    async def test_skill_tracker_hook(
        self,
        checkpoint_tracker: CheckpointTracker,
    ):
        """Test skill tracker hook."""
        from grounded_agency.hooks.skill_tracker import create_skill_tracker

        hook = create_skill_tracker(checkpoint_tracker)

        # Simulate checkpoint skill invocation
        input_data = {
            "tool_name": "Skill",
            "tool_input": {
                "skill": "checkpoint",
                "scope": ["*.yaml"],
                "reason": "Before config changes",
            },
            "tool_response": {},
        }

        assert not checkpoint_tracker.has_valid_checkpoint()

        await hook(input_data, "skill_123", None)

        # Checkpoint should now exist
        assert checkpoint_tracker.has_valid_checkpoint()

    @pytest.mark.asyncio
    async def test_skill_tracker_ignores_non_skill(
        self,
        checkpoint_tracker: CheckpointTracker,
    ):
        """Test skill tracker ignores non-Skill tools."""
        from grounded_agency.hooks.skill_tracker import create_skill_tracker

        hook = create_skill_tracker(checkpoint_tracker)

        input_data = {
            "tool_name": "Read",
            "tool_input": {"path": "test.py"},
        }

        await hook(input_data, "read_123", None)

        # No checkpoint should be created
        assert not checkpoint_tracker.has_valid_checkpoint()


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full workflow."""

    @pytest.mark.asyncio
    async def test_full_checkpoint_mutation_flow(
        self, adapter: GroundedAgentAdapter
    ):
        """Test complete checkpoint -> mutation -> consume flow."""
        callback = adapter._make_permission_callback()

        # 1. Try mutation without checkpoint (blocked)
        result1 = await callback("Write", {"file_path": "test.txt"}, None)
        if isinstance(result1, dict):
            assert result1.get("allowed") is False

        # 2. Create checkpoint
        checkpoint_id = adapter.create_checkpoint(["*.txt"], "Before edit")
        assert adapter.has_valid_checkpoint()

        # 3. Mutation now allowed
        result2 = await callback("Write", {"file_path": "test.txt"}, None)
        if isinstance(result2, dict):
            assert result2.get("allowed") is True

        # 4. Consume checkpoint
        consumed = adapter.consume_checkpoint()
        assert consumed == checkpoint_id
        assert not adapter.has_valid_checkpoint()

        # 5. Next mutation blocked again
        result3 = await callback("Write", {"file_path": "test.txt"}, None)
        if isinstance(result3, dict):
            assert result3.get("allowed") is False

    @pytest.mark.asyncio
    async def test_evidence_collection_during_workflow(
        self, adapter: GroundedAgentAdapter
    ):
        """Test that evidence is collected during workflow."""
        from grounded_agency.hooks.evidence_collector import create_evidence_collector

        hook = create_evidence_collector(adapter.evidence_store, adapter.mapper)

        # Simulate tool uses
        tools = [
            ("Read", {"path": "config.yaml"}),
            ("Grep", {"pattern": "debug"}),
        ]

        for tool_name, tool_input in tools:
            await hook(
                {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_response": {},
                },
                f"{tool_name.lower()}_123",
                None,
            )

        # Check evidence was collected
        evidence = adapter.get_evidence(10)
        assert len(evidence) >= 2

    def test_ontology_version_accessible(self, adapter: GroundedAgentAdapter):
        """Test that ontology version is accessible."""
        version = adapter.ontology_version
        assert version is not None
        assert version.startswith("2.")

    def test_capability_count_correct(self, adapter: GroundedAgentAdapter):
        """Test that capability count is correct."""
        assert adapter.capability_count == 36
