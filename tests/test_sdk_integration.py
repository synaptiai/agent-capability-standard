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

import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions

sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import (
    CapabilityRegistry,
    CheckpointTracker,
    EvidenceAnchor,
    EvidenceStore,
    GroundedAgentAdapter,
    GroundedAgentConfig,
    ToolCapabilityMapper,
)


# Fixtures
@pytest.fixture
def ontology_path() -> str:
    """Path to the capability ontology."""
    return str(Path(__file__).parent.parent / "schemas/capability_ontology.yaml")


@pytest.fixture
def registry(ontology_path: str) -> CapabilityRegistry:
    """Create a fresh CapabilityRegistry."""
    return CapabilityRegistry(ontology_path)


@pytest.fixture
def mapper() -> ToolCapabilityMapper:
    """Create a fresh ToolCapabilityMapper."""
    return ToolCapabilityMapper()


@pytest.fixture
def checkpoint_tracker(tmp_path: Path) -> CheckpointTracker:
    """Create a fresh CheckpointTracker with isolated directory."""
    return CheckpointTracker(checkpoint_dir=tmp_path / ".checkpoints")


@pytest.fixture
def evidence_store() -> EvidenceStore:
    """Create a fresh EvidenceStore."""
    return EvidenceStore()


@pytest.fixture
def adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Create a fresh GroundedAgentAdapter with isolated checkpoint directory.

    ``approval="off"``: these tests are about the checkpoint rule, so a call
    that satisfies it is allowed outright. The approval rule is tested in
    tests/test_tool_call_approval.py.
    """
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            strict_mode=True,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            approval="off",
        )
    )


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

    # -------------------------------------------------------------------------
    # Edge Type Methods Tests
    # -------------------------------------------------------------------------

    def test_get_preceding_capabilities(self, registry: CapabilityRegistry):
        """Test getting capabilities that must temporally precede."""
        preceding = registry.get_preceding_capabilities("mutate")
        assert "checkpoint" in preceding
        assert "plan" in preceding

    def test_get_preceding_capabilities_no_predecessors(
        self, registry: CapabilityRegistry
    ):
        """Test capability with no incoming precedes edges returns empty list."""
        preceding = registry.get_preceding_capabilities("observe")
        assert preceding == []

    def test_get_conflicting_capabilities(self, registry: CapabilityRegistry):
        """Test getting mutually exclusive capabilities."""
        conflicts = registry.get_conflicting_capabilities("rollback")
        assert "persist" in conflicts
        assert "mutate" in conflicts

    def test_get_conflicting_capabilities_symmetric(self, registry: CapabilityRegistry):
        """Test that conflicts_with is symmetric (A conflicts B implies B conflicts A)."""
        rollback_conflicts = registry.get_conflicting_capabilities("rollback")
        persist_conflicts = registry.get_conflicting_capabilities("persist")
        assert "persist" in rollback_conflicts
        assert "rollback" in persist_conflicts

    def test_get_conflicting_capabilities_no_conflicts(
        self, registry: CapabilityRegistry
    ):
        """Test capability with no conflicts returns empty list."""
        conflicts = registry.get_conflicting_capabilities("observe")
        assert conflicts == []

    def test_get_alternatives(self, registry: CapabilityRegistry):
        """Test getting substitutable capabilities."""
        alternatives = registry.get_alternatives("search")
        assert "retrieve" in alternatives

    def test_get_alternatives_symmetric(self, registry: CapabilityRegistry):
        """Test that alternative_to is symmetric (A alt B implies B alt A)."""
        search_alts = registry.get_alternatives("search")
        retrieve_alts = registry.get_alternatives("retrieve")
        assert "retrieve" in search_alts
        assert "search" in retrieve_alts

    def test_get_alternatives_no_alternatives(self, registry: CapabilityRegistry):
        """Test capability with no alternatives returns empty list."""
        alternatives = registry.get_alternatives("observe")
        assert alternatives == []

    def test_get_specialized_by(self, registry: CapabilityRegistry):
        """Test getting capabilities that specialize this one."""
        specialized = registry.get_specialized_by("detect")
        assert "classify" in specialized

    def test_get_specialized_by_no_specializations(self, registry: CapabilityRegistry):
        """Test capability with no specializations returns empty list."""
        specialized = registry.get_specialized_by("classify")
        assert specialized == []

    def test_get_generalizes_to(self, registry: CapabilityRegistry):
        """Test getting the parent capability in specialization hierarchy."""
        parent = registry.get_generalizes_to("classify")
        assert parent == "detect"

    def test_get_generalizes_to_top_level(self, registry: CapabilityRegistry):
        """Test top-level capability (no parent) returns None."""
        parent = registry.get_generalizes_to("observe")
        assert parent is None

    def test_edge_methods_nonexistent_capability(self, registry: CapabilityRegistry):
        """Test all edge methods return empty/None for nonexistent capability."""
        assert registry.get_preceding_capabilities("nonexistent") == []
        assert registry.get_conflicting_capabilities("nonexistent") == []
        assert registry.get_alternatives("nonexistent") == []
        assert registry.get_specialized_by("nonexistent") == []
        assert registry.get_generalizes_to("nonexistent") is None


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

    @pytest.mark.usefixtures("bash_under_sandbox")
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

    @pytest.mark.usefixtures("bash_under_sandbox")
    def test_map_bash_curl_post(self, mapper: ToolCapabilityMapper):
        """Test mapping curl POST command."""
        mapping = mapper.map_tool(
            "Bash", {"command": "curl -X POST https://api.example.com"}
        )
        assert mapping.capability_id == "send"
        assert mapping.risk == "high"
        assert mapping.requires_checkpoint is True

    def test_map_unknown_tool(self, mapper: ToolCapabilityMapper):
        """A tool the mapper does not know gets the strictest flags, not a
        read's."""
        mapping = mapper.map_tool("UnknownTool", {})
        assert mapping.capability_id == "mutate"
        assert mapping.risk == "high"
        assert mapping.mutation is True
        assert mapping.requires_checkpoint is True
        assert mapping.requires_approval is True

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

    def test_has_valid_checkpoint_false_initially(
        self, checkpoint_tracker: CheckpointTracker
    ):
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
        evidence_store.add_anchor(EvidenceAnchor.from_tool_output("Read", "1", {}))
        evidence_store.add_anchor(EvidenceAnchor.from_file("test.py"))
        evidence_store.add_anchor(EvidenceAnchor.from_mutation("config.yaml", "write"))

        # A legacy kind returns what it returned in 1.1, by ref prefix.
        with pytest.warns(DeprecationWarning):
            tool_outputs = evidence_store.get_by_kind("tool_output")
        assert len(tool_outputs) == 1
        assert len(evidence_store.get_by_kind("tool")) == 1

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
        # A command's result is a tool's result (STANDARD v1.2 §6.5).
        assert anchor.kind == "tool"
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

    @pytest.mark.parametrize("acknowledged", [False, None, 1, "yes"])
    def test_strict_mode_off_needs_the_acknowledgement(
        self, ontology_path: str, tmp_path: Path, acknowledged: object
    ) -> None:
        """strict_mode=False is refused unless the caller passes
        acknowledge_unenforced_checks=True itself: a truthy stand-in is not
        an acknowledgement."""
        with pytest.raises(ValueError, match="acknowledge_unenforced_checks=True"):
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                strict_mode=False,
                acknowledge_unenforced_checks=acknowledged,  # type: ignore[arg-type]
            )

    def test_strict_mode_on_needs_no_acknowledgement(self, ontology_path: str) -> None:
        assert GroundedAgentConfig(ontology_path=ontology_path).strict_mode is True
        assert GroundedAgentConfig(
            ontology_path=ontology_path, strict_mode=True
        ).strict_mode

    def test_a_copy_that_turns_strict_mode_off_is_refused(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        config = GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp")
        )
        with pytest.raises(ValueError, match="outside class SL"):
            replace(config, strict_mode=False)
        assert not replace(
            config, strict_mode=False, acknowledge_unenforced_checks=True
        ).strict_mode

    def test_a_configuration_changed_after_it_was_made_is_refused(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """The adapter checks the acknowledgement again when it is built."""
        config = GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp")
        )
        config.strict_mode = False
        with pytest.raises(ValueError, match="acknowledge_unenforced_checks=True"):
            GroundedAgentAdapter(config)

    @pytest.mark.asyncio
    async def test_acknowledged_strict_mode_off_warns_and_lets_the_call_run(
        self,
        ontology_path: str,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """With the acknowledgement the adapter starts, says so in the log,
        and logs a missing checkpoint instead of refusing the call."""
        with caplog.at_level("WARNING", logger="grounded_agency.adapter"):
            lenient = GroundedAgentAdapter(
                GroundedAgentConfig(
                    ontology_path=ontology_path,
                    checkpoint_dir=str(tmp_path / ".cp"),
                    strict_mode=False,
                    acknowledge_unenforced_checks=True,
                    approval="off",
                )
            )
        assert "strict_mode=False (acknowledged)" in caplog.text
        hook = lenient._make_pretooluse_safety_hook()
        result = await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)
        assert result == {}

    @pytest.mark.parametrize(
        ("heading", "bypass"),
        [
            ("### F501 CHECKPOINT_REQUIRED", "strict_mode=False"),
            ("### F502 APPROVAL_REQUIRED", 'approval="off"'),
        ],
    )
    def test_the_guide_offers_no_bypass_as_a_fix(
        self, heading: str, bypass: str
    ) -> None:
        """The SDK guide's troubleshooting for a refusal gives no code that
        turns the rule off: such a mode is outside class SL."""
        guide = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "integrations"
            / "claude_agent_sdk.md"
        ).read_text(encoding="utf-8")
        assert heading in guide
        section = guide.split(heading, 1)[1].split("\n### ", 1)[0]
        code = "".join(section.split("```")[1::2])
        assert code.strip()
        assert bypass not in code

    def test_wrap_options(self, adapter: GroundedAgentAdapter):
        """Test wrapping SDK options."""
        base = ClaudeAgentOptions(allowed_tools=["Read", "Write"])
        wrapped = adapter.wrap_options(base)

        # Check injected settings
        assert wrapped.enable_file_checkpointing is True
        assert wrapped.can_use_tool is not None
        assert "Skill" not in wrapped.allowed_tools
        assert "PostToolUse" in wrapped.hooks

    def test_wrap_options_preserves_existing(self, adapter: GroundedAgentAdapter):
        """Test that wrap_options preserves existing tools."""
        base = ClaudeAgentOptions(allowed_tools=["Read", "Write", "Bash"])
        wrapped = adapter.wrap_options(base)

        assert "Read" in wrapped.allowed_tools
        assert "Write" in wrapped.allowed_tools
        assert "Bash" in wrapped.allowed_tools
        assert "Skill" not in wrapped.allowed_tools

    @pytest.mark.parametrize(
        "sources",
        [
            None,
            [],
            ["user"],
            ["local"],
            ["user", "local"],
            ["user", "project", "local"],
        ],
    )
    def test_wrap_options_keeps_the_hosts_setting_sources(
        self, adapter: GroundedAgentAdapter, sources: list[str] | None
    ) -> None:
        """Which settings files the CLI loads is the host's choice: ``[]``
        (the SDK's isolation mode, for a cwd that may be untrusted, whose
        project settings can run hooks) stays ``[]``, and ``None`` (every
        source) stays ``None``; nothing adds ``"project"``."""
        given = None if sources is None else list(sources)
        wrapped = adapter.wrap_options(ClaudeAgentOptions(setting_sources=given))
        assert wrapped.setting_sources == sources
        try:
            from claude_agent_sdk._internal.transport.subprocess_cli import (
                SubprocessCLITransport,
            )

            build = SubprocessCLITransport(
                prompt="x", options=replace(wrapped, cli_path="/bin/false")
            )._build_command
        except ImportError, AttributeError, TypeError:
            return  # an SDK whose transport this test cannot read
        flags = [a for a in build() if a.startswith("--setting-sources")]
        expected = [] if sources is None else [f"--setting-sources={','.join(sources)}"]
        assert flags == expected

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


def _denied(result: Any) -> bool:
    """Deny from the SDK (behavior) or the fallback type (allowed)."""
    return (
        getattr(result, "behavior", None) == "deny"
        or getattr(result, "allowed", None) is False
    )


class TestCheckpointReservation:
    """One checkpoint covers one gated call (STANDARD 1.2.0 §5.18.6): a call
    holds it under its tool_use_id, another call is denied while it is
    held, and the call uses it up when it is allowed to start, or, having
    run without passing the callback, when it reports back, whatever its
    outcome. Only a refusal the layer learns of releases it (SEC-007)."""

    @staticmethod
    def _ctx(tool_use_id: str) -> Any:
        return SimpleNamespace(tool_use_id=tool_use_id)

    @staticmethod
    def _post(tool_name: str, is_error: bool = False) -> dict[str, Any]:
        return {
            "tool_name": tool_name,
            "tool_input": {"file_path": "a.txt"},
            "tool_response": {"is_error": is_error},
        }

    @pytest.mark.asyncio
    async def test_second_concurrent_mutation_is_denied(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        checkpoint_id = adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()

        first = await pre(
            {"tool_name": "Write", "tool_input": {"file_path": "a.txt"}}, "t1", None
        )
        second = await pre(
            {"tool_name": "Write", "tool_input": {"file_path": "b.txt"}}, "t2", None
        )
        # The same call reaches the callback: its hold is the same
        # (idempotent), and it is used up at the allow.
        same_call = await callback("Write", {"file_path": "a.txt"}, self._ctx("t1"))

        assert first == {}
        assert second["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert (
            f"checkpoint {checkpoint_id} is held by another call"
            in second["hookSpecificOutput"]["permissionDecisionReason"]
        )
        assert not _denied(same_call)
        assert not adapter.has_valid_checkpoint()

    @pytest.mark.asyncio
    async def test_pretooluse_reserves_for_pre_approved_tools(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """Pre-approved tools never reach can_use_tool; PreToolUse always
        runs, so it takes the reservation."""
        adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()

        ok = await pre({"tool_name": "Write", "tool_input": {}}, "t1", None)
        blocked = await pre({"tool_name": "Edit", "tool_input": {}}, "t2", None)
        same_call = await callback("Write", {}, self._ctx("t1"))

        assert ok == {}
        assert blocked["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert not _denied(same_call)

    @pytest.mark.asyncio
    async def test_failed_mutation_uses_the_checkpoint(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """Claude Code reports failures and interrupts through
        PostToolUseFailure, not PostToolUse. A call that started uses its
        checkpoint whatever its outcome (STANDARD 1.2.0 §5.18.6): it may
        have changed something before it failed."""
        adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()
        failed = adapter._make_failure_recorder()

        # A pre-approved tool: PreToolUse holds the checkpoint, the call runs
        # without reaching the callback, and fails.
        assert await pre({"tool_name": "Write", "tool_input": {}}, "t1", None) == {}
        await failed(
            {"tool_name": "Write", "tool_use_id": "t1", "error": "boom"}, "t1", None
        )
        assert not adapter.has_valid_checkpoint()
        assert _denied(await callback("Write", {}, self._ctx("t2")))

    @pytest.mark.asyncio
    async def test_error_response_uses_the_checkpoint(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """A call that ran and reported an error uses its checkpoint all the
        same (STANDARD 1.2.0 §5.18.6)."""
        adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()
        consumer = adapter._make_mutation_consumer()

        assert await pre({"tool_name": "Write", "tool_input": {}}, "t1", None) == {}
        await consumer(self._post("Write", is_error=True), "t1", None)
        assert not adapter.has_valid_checkpoint()
        denied = await pre({"tool_name": "Write", "tool_input": {}}, "t2", None)
        assert denied["hookSpecificOutput"]["permissionDecisionReason"].startswith(
            "F501 CHECKPOINT_REQUIRED:"
        )
        assert _denied(await callback("Write", {}, self._ctx("t2")))

    @pytest.mark.asyncio
    async def test_successful_mutation_consumes_the_checkpoint(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()
        consumer = adapter._make_mutation_consumer()

        assert await pre({"tool_name": "Write", "tool_input": {}}, "t1", None) == {}
        assert not _denied(await callback("Write", {}, self._ctx("t1")))
        # Used up at the callback's allow, before the call runs.
        assert not adapter.has_valid_checkpoint()
        await consumer(self._post("Write"), "t1", None)
        assert not adapter.has_valid_checkpoint()
        denied = await pre({"tool_name": "Write", "tool_input": {}}, "t2", None)
        reason = denied["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason.startswith("F501 CHECKPOINT_REQUIRED:")
        assert "reserved" not in reason

    @pytest.mark.asyncio
    async def test_other_calls_cannot_end_a_reservation(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """Neither a call without a reservation (here TodoWrite, a mutation
        that needs no checkpoint) nor another call's failure touches the
        holder's checkpoint."""
        checkpoint_id = adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        consumer = adapter._make_mutation_consumer()
        failed = adapter._make_failure_recorder()

        assert await pre({"tool_name": "Write", "tool_input": {}}, "t1", None) == {}
        await consumer(self._post("TodoWrite"), "t9", None)
        await consumer(self._post("Edit"), "t2", None)
        await failed({"tool_name": "Edit", "tool_use_id": "t2"}, "t2", None)

        assert adapter.has_valid_checkpoint()
        assert adapter.checkpoint_tracker.held_by("t1") == checkpoint_id
        blocked = await pre({"tool_name": "Edit", "tool_input": {}}, "t3", None)
        assert blocked["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_non_strict_unreserved_call_cannot_release(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        lenient = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                strict_mode=False,
                acknowledge_unenforced_checks=True,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                approval="off",
            )
        )
        lenient.create_checkpoint(["*"], "Test")
        callback = lenient._make_permission_callback()
        consumer = lenient._make_mutation_consumer()

        assert not _denied(await callback("Write", {}, self._ctx("t1")))
        # Allowed with a warning, but holds no reservation.
        assert not _denied(await callback("Edit", {}, self._ctx("t2")))
        await consumer(self._post("Edit", is_error=True), "t2", None)
        reserved, _ = lenient.checkpoint_tracker.validate_and_reserve("t3")
        assert reserved is False

    @pytest.mark.asyncio
    async def test_strict_mode_turned_off_on_a_built_adapter_is_not_in_force(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """strict_mode=False set on a built adapter without the
        acknowledgement leaves the checks enforced: the PreToolUse hook and
        the permission callback refuse a Write with no checkpoint (F501),
        and the records' configuration digest names the strict mode in
        force."""
        digest = adapter.recorded_by["config_sha256"]
        adapter.config.strict_mode = False
        assert adapter._strict() is True
        assert adapter.recorded_by["config_sha256"] == digest
        wrapped = adapter.wrap_options(ClaudeAgentOptions())
        pre = wrapped.hooks["PreToolUse"][-1].hooks[0]
        denied = await pre({"tool_name": "Write", "tool_input": {}}, "t1", None)
        assert denied["hookSpecificOutput"]["permissionDecisionReason"].startswith(
            "F501 CHECKPOINT_REQUIRED:"
        )
        # A call the hook did not see, with no id to hold a checkpoint by.
        refused = await wrapped.can_use_tool("Write", {}, None)
        assert _denied(refused)
        assert refused.message.startswith("F501 CHECKPOINT_REQUIRED:")

        # Acknowledged, the same change is in force.
        adapter.config.acknowledge_unenforced_checks = True
        assert adapter._strict() is False
        assert adapter.recorded_by["config_sha256"] != digest
        lenient = adapter._make_pretooluse_safety_hook()
        assert await lenient({"tool_name": "Write", "tool_input": {}}, "t2", None) == {}
        callback = adapter._make_permission_callback()
        assert not _denied(await callback("Write", {}, None))

    @pytest.mark.asyncio
    async def test_context_without_tool_use_id_is_r407(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """A gated call whose context has no tool_use_id cannot hold a
        checkpoint, so the layer cannot complete its check: R407 (STANDARD
        1.2.0 §5.18.8). The package's minimum SDK, 0.1.52, always sends
        one."""
        adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()

        assert await pre({"tool_name": "Write", "tool_input": {}}, "t1", None) == {}
        for context in (SimpleNamespace(), None):
            denied = await callback("Write", {}, context)
            assert _denied(denied)
            assert denied.message.startswith("R407 SAFETY_CHECK_FAILED:")
        # t1 still holds the checkpoint; nothing anonymous took it over.
        assert not adapter.checkpoint_tracker.validate_and_reserve("t2")[0]
        assert adapter.checkpoint_tracker.validate_and_reserve("t1")[0]

    @pytest.mark.asyncio
    async def test_context_without_tool_use_id_still_needs_a_checkpoint(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        """With no valid checkpoint the refusal is F501, as for a call with
        an id: the missing checkpoint is what to fix first."""
        callback = adapter._make_permission_callback()
        pre = adapter._make_pretooluse_safety_hook()
        for context in (SimpleNamespace(), None):
            denied = await callback("Write", {}, context)
            assert _denied(denied)
            assert denied.message.startswith("F501 CHECKPOINT_REQUIRED:")
        result = await pre({"tool_name": "Write", "tool_input": {}}, None, None)
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason.startswith("F501 CHECKPOINT_REQUIRED:")

    @pytest.mark.asyncio
    async def test_denied_call_releases_its_reservation(
        self, adapter: GroundedAgentAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A call can_use_tool denies never runs, so no PostToolUse hook
        ends the reservation its PreToolUse took; the deny releases it."""
        adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()

        assert await pre({"tool_name": "Write", "tool_input": {}}, "t1", None) == {}

        def fail(*args: object) -> None:
            raise RuntimeError("mapper failure")

        monkeypatch.setattr(adapter.mapper, "map_tool", fail)
        denied = await callback("Write", {}, self._ctx("t1"))
        assert _denied(denied)
        assert "internal error" in denied.message
        monkeypatch.undo()

        assert adapter.has_valid_checkpoint()
        assert await pre({"tool_name": "Write", "tool_input": {}}, "t2", None) == {}
        assert not _denied(await callback("Write", {}, self._ctx("t2")))

    @pytest.mark.asyncio
    async def test_deny_leaves_another_holders_reservation(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        adapter.create_checkpoint(["*"], "Test")
        pre = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()

        assert await pre({"tool_name": "Write", "tool_input": {}}, "t1", None) == {}
        for other in ("t2", "t3"):
            refused = await pre({"tool_name": "Write", "tool_input": {}}, other, None)
            assert refused["hookSpecificOutput"]["permissionDecision"] == "deny"
            assert _denied(await callback("Write", {}, self._ctx(other)))
        assert adapter.checkpoint_tracker.held_by("t1")
        assert not _denied(await callback("Write", {}, self._ctx("t1")))

    def test_wrap_options_registers_the_failure_hook(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        options = adapter.wrap_options(ClaudeAgentOptions())
        assert options.hooks["PostToolUseFailure"]

    def test_reservation_timeout_is_configurable(
        self, ontology_path: str, tmp_path: Path, fake_clock: Any
    ) -> None:
        with pytest.raises(ValueError, match="more than 0"):
            GroundedAgentConfig(
                ontology_path=ontology_path, checkpoint_reservation_seconds=0
            )
        quick = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                checkpoint_reservation_seconds=1,
            ),
            clock=fake_clock,
        )
        quick.create_checkpoint(["*"], "Test")
        tracker = quick.checkpoint_tracker
        assert tracker.validate_and_reserve("t1")[0]
        fake_clock.advance(seconds=2)
        # t1's hold lapsed, so the checkpoint counts as used (§5.18.6).
        assert tracker.validate_and_reserve("t2") == (False, None)


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

    @pytest.mark.usefixtures("bash_under_sandbox")
    @pytest.mark.asyncio
    async def test_checkpoint_recorder_hook(
        self,
        checkpoint_tracker: CheckpointTracker,
        tmp_path: Path,
    ):
        """The call that saves the state takes the checkpoint, not the call
        that loads the skill (STANDARD 1.2.0 §5.18.6)."""
        from grounded_agency.hooks.skill_tracker import create_checkpoint_recorder

        hook = create_checkpoint_recorder(checkpoint_tracker)

        skill = {
            "tool_name": "Skill",
            "tool_input": {
                "skill": "checkpoint",
                "scope": ["*.yaml"],
                "reason": "Before config changes",
            },
            "tool_response": {},
        }
        await hook(skill, "skill_123", None)
        assert not checkpoint_tracker.has_valid_checkpoint()

        def stash(
            command: str, response: dict[str, Any], **call: Any
        ) -> dict[str, Any]:
            return {
                "tool_name": "Bash",
                "tool_input": {"command": command, **call},
                "tool_response": response,
                "cwd": str(tmp_path),
            }

        # A failed git stash create and a git stash store take none.
        await hook(stash("git stash create", {"is_error": True}), "b0", None)
        await hook(stash("git stash store -m m " + "a" * 40, {}), "b1", None)
        assert not checkpoint_tracker.has_valid_checkpoint()

        sha = "0123456789abcdef0123456789abcdef01234567"
        await hook(
            stash('git stash create "checkpoint:x"', {"stdout": sha + "\n"}), "b2", None
        )
        active = checkpoint_tracker.get_active_checkpoint()
        assert active is not None
        assert active.metadata["commit"] == sha
        assert active.metadata["untracked_not_captured"] is True

        # A clean tree: nothing printed, HEAD is the restore point.
        _clean_repo(tmp_path)
        await hook(stash("git stash create", {"stdout": ""}), "b3", None)
        active = checkpoint_tracker.get_active_checkpoint()
        assert active is not None and active.metadata["commit"] == "HEAD"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("change", "call", "stdout"),
        [
            ("worktree", {}, ""),
            ("index", {}, ""),
            (None, {"run_in_background": True}, ""),
            (None, {"run_in_background": True}, "0123456789abcdef" * 2 + "01234567"),
            (None, {}, "warning: not a commit"),
            (None, {}, "0123456789abcdef" * 2 + "01234567\nmore"),
        ],
    )
    async def test_checkpoint_recorder_takes_no_unverified_checkpoint(
        self,
        checkpoint_tracker: CheckpointTracker,
        tmp_path: Path,
        change: str | None,
        call: dict[str, Any],
        stdout: str,
    ):
        """Empty output means nothing was saved: HEAD restores the state only
        when the tracked files and the index are HEAD's. A background call's
        output is not yet the command's, and output that is not one commit
        id names nothing to restore. None of these takes a checkpoint."""
        from grounded_agency.hooks.skill_tracker import create_checkpoint_recorder

        _clean_repo(tmp_path)
        if change is not None:
            (tmp_path / "a.txt").write_text("uncommitted\n")
        if change == "index":
            _git(tmp_path, "add", "a.txt")
        hook = create_checkpoint_recorder(checkpoint_tracker)
        await hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git stash create", **call},
                "tool_response": {"stdout": stdout},
                "cwd": str(tmp_path),
            },
            "b1",
            None,
        )
        assert not checkpoint_tracker.has_valid_checkpoint()

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


def _git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), *args],
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        },
        check=True,
        capture_output=True,
    )


def _clean_repo(path: Path) -> None:
    """A repository with one commit whose tree is HEAD's."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    _git(path, "init", "-q")
    (path / "a.txt").write_text("a\n")
    _git(path, "add", "a.txt")
    _git(path, "commit", "-q", "-m", "init")


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the full workflow."""

    @pytest.mark.asyncio
    async def test_full_checkpoint_mutation_flow(self, adapter: GroundedAgentAdapter):
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


# ---------------------------------------------------------------------------
# Edge semantics: requires edges reflect spec Section 4.4
# ---------------------------------------------------------------------------


class TestEdgeSemantics:
    """Verify ontology edge semantics match spec requirements.

    These tests guard against regressions like the PR #101 issue where
    wrong 'requires' edges made 'verify' unusable standalone.
    """

    def test_verify_has_no_requirements(self, registry: CapabilityRegistry) -> None:
        """verify must be usable standalone (no requires edges targeting it)."""
        assert registry.get_required_capabilities("verify") == []

    def test_rollback_requires_checkpoint(self, registry: CapabilityRegistry) -> None:
        """rollback must require checkpoint (spec Section 4.4)."""
        required = registry.get_required_capabilities("rollback")
        assert "checkpoint" in required

    def test_send_requires_checkpoint(self, registry: CapabilityRegistry) -> None:
        """send must require checkpoint (spec Section 4.4)."""
        required = registry.get_required_capabilities("send")
        assert "checkpoint" in required

    def test_mutate_requires_checkpoint(self, registry: CapabilityRegistry) -> None:
        """mutate must require checkpoint (spec Section 4.4)."""
        required = registry.get_required_capabilities("mutate")
        assert "checkpoint" in required

    def test_only_three_requires_edges_exist(
        self, registry: CapabilityRegistry
    ) -> None:
        """Exactly 3 requires edges: checkpoint→mutate, checkpoint→send,
        checkpoint→rollback. No other capability should have requires deps."""
        all_caps = registry.all_capabilities()
        caps_with_reqs = {}
        for cap in all_caps:
            reqs = registry.get_required_capabilities(cap.id)
            if reqs:
                caps_with_reqs[cap.id] = reqs
        assert set(caps_with_reqs.keys()) == {"mutate", "send", "rollback"}
        for cap_id, reqs in caps_with_reqs.items():
            assert reqs == ["checkpoint"], (
                f"{cap_id} requires {reqs}, expected ['checkpoint']"
            )
