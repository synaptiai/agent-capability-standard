"""
Tests for MCP integration: dynamic tool registration and mapper support.

Since claude_agent_sdk may not be installed, these tests focus on:
- Dynamic tool registration in ToolCapabilityMapper
- Capability metadata for registered tools
- Import error handling in create_grounded_mcp_server
"""

from __future__ import annotations

from pathlib import Path

import pytest

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.capabilities.mapper import ToolCapabilityMapper

# =============================================================================
# Dynamic Tool Registration Tests
# =============================================================================


class TestDynamicToolRegistration:
    """Tests for register_mcp_tool in ToolCapabilityMapper."""

    @pytest.fixture
    def mapper(self) -> ToolCapabilityMapper:
        return ToolCapabilityMapper()

    def test_register_basic_tool(self, mapper: ToolCapabilityMapper):
        """Test registering a basic MCP tool."""
        mapper.register_mcp_tool(
            tool_name="mcp__server__search",
            capability_id="search",
            risk="low",
        )

        mapping = mapper.map_tool("mcp__server__search", {})
        assert mapping.capability_id == "search"
        assert mapping.risk == "low"
        assert mapping.mutation is False
        assert mapping.requires_checkpoint is False

    def test_register_high_risk_tool(self, mapper: ToolCapabilityMapper):
        """Test registering a high-risk MCP tool."""
        mapper.register_mcp_tool(
            tool_name="mcp__deploy__push",
            capability_id="execute",
            risk="high",
        )

        mapping = mapper.map_tool("mcp__deploy__push", {})
        assert mapping.capability_id == "execute"
        assert mapping.risk == "high"
        assert mapping.mutation is True
        assert mapping.requires_checkpoint is True

    def test_register_custom_mutation_flag(self, mapper: ToolCapabilityMapper):
        """Test registering with explicit mutation flag."""
        mapper.register_mcp_tool(
            tool_name="mcp__data__write",
            capability_id="mutate",
            risk="medium",
            mutation=True,
            requires_checkpoint=True,
        )

        mapping = mapper.map_tool("mcp__data__write", {})
        assert mapping.mutation is True
        assert mapping.requires_checkpoint is True

    def test_register_overrides_default(self, mapper: ToolCapabilityMapper):
        """Test that registered tools override default mapping."""
        # Without registration, unknown tool gets default
        default = mapper.map_tool("mcp__server__tool", {})
        assert default.capability_id == "observe"
        assert default.risk == "medium"

        # After registration, gets specific mapping
        mapper.register_mcp_tool(
            tool_name="mcp__server__tool",
            capability_id="retrieve",
            risk="low",
        )
        registered = mapper.map_tool("mcp__server__tool", {})
        assert registered.capability_id == "retrieve"
        assert registered.risk == "low"

    def test_register_does_not_affect_static(self, mapper: ToolCapabilityMapper):
        """Test that registering doesn't affect static tool mappings."""
        mapper.register_mcp_tool(
            tool_name="mcp__test__read",
            capability_id="retrieve",
            risk="low",
        )

        # Static mappings should be unchanged
        write_mapping = mapper.map_tool("Write", {})
        assert write_mapping.capability_id == "mutate"
        assert write_mapping.risk == "high"

    def test_register_multiple_tools(self, mapper: ToolCapabilityMapper):
        """Test registering multiple MCP tools."""
        mapper.register_mcp_tool("mcp__a__search", "search", "low")
        mapper.register_mcp_tool("mcp__a__write", "mutate", "high")
        mapper.register_mcp_tool("mcp__a__invoke", "invoke", "medium")

        assert mapper.map_tool("mcp__a__search", {}).risk == "low"
        assert mapper.map_tool("mcp__a__write", {}).risk == "high"
        assert mapper.map_tool("mcp__a__invoke", {}).risk == "medium"

    def test_register_default_mutation_low_risk(self, mapper: ToolCapabilityMapper):
        """Test that low-risk defaults to mutation=False."""
        mapper.register_mcp_tool("mcp__x__y", "observe", "low")
        mapping = mapper.map_tool("mcp__x__y", {})
        assert mapping.mutation is False
        assert mapping.requires_checkpoint is False

    def test_register_default_mutation_medium_risk(self, mapper: ToolCapabilityMapper):
        """Test that medium-risk defaults to mutation=False."""
        mapper.register_mcp_tool("mcp__x__y", "execute", "medium")
        mapping = mapper.map_tool("mcp__x__y", {})
        assert mapping.mutation is False
        assert mapping.requires_checkpoint is False

    def test_bash_still_works_after_registration(self, mapper: ToolCapabilityMapper):
        """Test that Bash classification isn't affected by registrations."""
        mapper.register_mcp_tool("mcp__test__x", "search", "low")

        # Bash should still be classified by command content
        ls_mapping = mapper.map_tool("Bash", {"command": "ls -la"})
        assert ls_mapping.risk == "low"

        rm_mapping = mapper.map_tool("Bash", {"command": "rm -rf /tmp"})
        assert rm_mapping.risk == "high"


# =============================================================================
# MCP Server Factory Tests
# =============================================================================


class TestMCPServerFactory:
    """Tests for create_grounded_mcp_server."""

    def test_import_error_without_sdk(self):
        """Test that factory raises ImportError without SDK."""
        from grounded_agency.mcp import create_grounded_mcp_server

        ontology_path = str(
            Path(__file__).parent.parent / "schemas/capability_ontology.yaml"
        )
        adapter = GroundedAgentAdapter(GroundedAgentConfig(ontology_path=ontology_path))

        try:
            create_grounded_mcp_server(
                name="test",
                version="1.0",
                tools=[],
                adapter=adapter,
            )
            # If SDK is installed, this succeeds
        except ImportError as e:
            assert "claude_agent_sdk" in str(e)

    def test_get_tool_name_helper(self):
        """Test the _get_tool_name helper function."""
        from grounded_agency.mcp import _get_tool_name

        # Object with name attribute
        class NamedTool:
            name = "my_tool"

        assert _get_tool_name(NamedTool()) == "my_tool"

        # Object with __name__ attribute
        def func_tool():
            pass

        assert _get_tool_name(func_tool) == "func_tool"

        # Object with tool_name attribute (Issue 11)
        class ToolNameTool:
            tool_name = "custom_tool"

        assert _get_tool_name(ToolNameTool()) == "custom_tool"

        # Object without name
        class AnonymousTool:
            pass

        assert _get_tool_name(AnonymousTool()) == "unknown"


# =============================================================================
# Adapter Integration with MCP Registration
# =============================================================================


class TestAdapterMCPIntegration:
    """Tests that MCP tool registration works through the adapter."""

    def test_register_through_adapter_mapper(self, adapter: GroundedAgentAdapter):
        """Test registering MCP tools through adapter.mapper."""
        adapter.mapper.register_mcp_tool(
            tool_name="mcp__db__query",
            capability_id="retrieve",
            risk="low",
        )

        mapping = adapter.mapper.map_tool("mcp__db__query", {})
        assert mapping.capability_id == "retrieve"

    @pytest.mark.asyncio
    async def test_permission_callback_respects_mcp_tools(
        self, adapter: GroundedAgentAdapter
    ):
        """Test that permission callback enforces checkpoints for MCP tools.

        Note: Without the SDK installed, the adapter returns FallbackPermission*
        types which use an ``allowed`` attribute (bool). SDK types use a
        ``behavior`` attribute instead. We check both for robustness.
        """
        # Register a high-risk MCP tool
        adapter.mapper.register_mcp_tool(
            tool_name="mcp__deploy__push",
            capability_id="execute",
            risk="high",
            mutation=True,
            requires_checkpoint=True,
        )

        callback = adapter._make_permission_callback()

        # Without checkpoint, should be blocked
        result = await callback("mcp__deploy__push", {}, None)
        # Fallback types use `allowed`; SDK types use `behavior`
        if hasattr(result, "allowed"):
            assert result.allowed is False
        elif hasattr(result, "behavior"):
            assert result.behavior == "deny"

        # With checkpoint, should be allowed
        adapter.create_checkpoint(["*"], "Test")
        result = await callback("mcp__deploy__push", {}, None)
        if hasattr(result, "allowed"):
            assert result.allowed is True
        elif hasattr(result, "behavior"):
            assert result.behavior == "allow"


# =============================================================================
# to_sdk_agents() Tests (Issue 8)
# =============================================================================


class TestToSdkAgents:
    """Tests for OrchestrationRuntime.to_sdk_agents()."""

    def test_exports_registered_agents(self, ontology_path: str):
        """Test that to_sdk_agents() exports registered agents correctly."""
        from grounded_agency import CapabilityRegistry, OrchestrationRuntime

        registry = CapabilityRegistry(ontology_path)
        runtime = OrchestrationRuntime(registry)
        runtime.register_agent("analyst", {"search", "retrieve"})

        agents = runtime.to_sdk_agents()
        assert "analyst" in agents
        assert "description" in agents["analyst"]
        assert "prompt" in agents["analyst"]
        assert "tools" in agents["analyst"]
        assert "model" in agents["analyst"]

    def test_exports_empty_when_no_agents(self, ontology_path: str):
        """Test that to_sdk_agents() returns empty dict with no agents."""
        from grounded_agency import CapabilityRegistry, OrchestrationRuntime

        registry = CapabilityRegistry(ontology_path)
        runtime = OrchestrationRuntime(registry)

        agents = runtime.to_sdk_agents()
        assert agents == {}

    def test_exports_agent_with_metadata(self, ontology_path: str):
        """Test that to_sdk_agents() uses metadata when available."""
        from grounded_agency import CapabilityRegistry, OrchestrationRuntime

        registry = CapabilityRegistry(ontology_path)
        runtime = OrchestrationRuntime(registry)
        runtime.register_agent(
            "writer",
            {"generate"},
            metadata={
                "description": "A writing assistant",
                "system_prompt": "You are a writer.",
                "allowed_tools": ["Write", "Edit"],
                "model": "opus",
            },
        )

        agents = runtime.to_sdk_agents()
        assert agents["writer"]["description"] == "A writing assistant"
        assert agents["writer"]["prompt"] == "You are a writer."
        assert agents["writer"]["tools"] == ["Write", "Edit"]
        assert agents["writer"]["model"] == "opus"

    def test_exports_agent_fallback_defaults(self, ontology_path: str):
        """Test that to_sdk_agents() falls back to defaults for missing metadata."""
        from grounded_agency import CapabilityRegistry, OrchestrationRuntime

        registry = CapabilityRegistry(ontology_path)
        runtime = OrchestrationRuntime(registry)
        runtime.register_agent("basic", {"observe"})

        agents = runtime.to_sdk_agents()
        agent = agents["basic"]
        # Default description is generated from capabilities
        assert "observe" in agent["description"]
        assert agent["prompt"] == ""
        assert agent["tools"] == []
        assert agent["model"] == "sonnet"


# =============================================================================
# Orchestrator Injection in wrap_options Tests (Issue 9)
# =============================================================================


class TestOrchestratorInjection:
    """Tests for orchestrator agent injection via wrap_options."""

    def test_agents_injected_when_orchestrator_set(
        self, ontology_path: str, tmp_path: Path
    ):
        """Test that agents are injected when orchestrator has agents."""
        sdk = pytest.importorskip("claude_agent_sdk")
        ClaudeAgentOptions = sdk.ClaudeAgentOptions

        from grounded_agency import CapabilityRegistry, OrchestrationRuntime

        registry = CapabilityRegistry(ontology_path)
        runtime = OrchestrationRuntime(registry)
        runtime.register_agent("analyst", {"search"})

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
            ),
            orchestrator=runtime,
        )
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)

        assert wrapped.agents is not None
        assert "analyst" in wrapped.agents

    def test_agents_not_injected_when_base_has_agents(
        self, ontology_path: str, tmp_path: Path
    ):
        """Test that existing agents on base options are NOT overridden."""
        sdk = pytest.importorskip("claude_agent_sdk")
        ClaudeAgentOptions = sdk.ClaudeAgentOptions

        from grounded_agency import CapabilityRegistry, OrchestrationRuntime

        registry = CapabilityRegistry(ontology_path)
        runtime = OrchestrationRuntime(registry)
        runtime.register_agent("analyst", {"search"})

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
            ),
            orchestrator=runtime,
        )
        existing_agents = {"custom_agent": {"description": "My custom agent"}}
        base = ClaudeAgentOptions(agents=existing_agents)
        wrapped = adapter.wrap_options(base)

        # Should keep existing agents, not inject orchestrator's
        assert wrapped.agents == existing_agents

    def test_no_crash_when_orchestrator_has_no_to_sdk_agents(
        self, ontology_path: str, tmp_path: Path
    ):
        """Test no crash when orchestrator lacks to_sdk_agents method."""
        sdk = pytest.importorskip("claude_agent_sdk")
        ClaudeAgentOptions = sdk.ClaudeAgentOptions

        class FakeOrchestrator:
            pass

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
            ),
            orchestrator=FakeOrchestrator(),
        )
        base = ClaudeAgentOptions()
        # Should not raise
        wrapped = adapter.wrap_options(base)
        assert wrapped.agents is None
