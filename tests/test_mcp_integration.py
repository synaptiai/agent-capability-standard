"""
Tests for MCP integration: dynamic tool registration and mapper support.

Since claude_agent_sdk may not be installed, these tests focus on:
- Dynamic tool registration in ToolCapabilityMapper
- Capability metadata for registered tools
- Import error handling in create_grounded_mcp_server
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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
        # Without registration, an unknown tool gets the strictest flags
        default = mapper.map_tool("mcp__server__tool", {})
        assert default.capability_id == "mutate"
        assert default.risk == "high"
        assert default.requires_checkpoint is True
        assert default.requires_approval is True

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

        # Without checkpoint, should be blocked. A gated call needs its
        # tool_use_id, under which the layer holds its checkpoint (STANDARD
        # 1.2.0 §5.18.6); without one it is refused with R407.
        result = await callback(
            "mcp__deploy__push", {}, SimpleNamespace(tool_use_id="t1")
        )
        # Fallback types use `allowed`; SDK types use `behavior`
        if hasattr(result, "allowed"):
            assert result.allowed is False
        elif hasattr(result, "behavior"):
            assert result.behavior == "deny"

        # With checkpoint, should be allowed
        adapter.create_checkpoint(["*"], "Test")
        result = await callback(
            "mcp__deploy__push", {}, SimpleNamespace(tool_use_id="t2")
        )
        if hasattr(result, "allowed"):
            assert result.allowed is True
        elif hasattr(result, "behavior"):
            assert result.behavior == "allow"


# =============================================================================
# create_grounded_mcp_server(require_layer=True): the guard (STANDARD 1.2.0
# sections 5.18.3 and 5.18.8)
# =============================================================================


class TestGroundedServerGuard:
    """Each served tool runs only on the adapter's decision for this exact
    call (R407 otherwise), except a control-only tool, which is never
    refused."""

    # A search output with every field its contract requires.
    FOUND: dict[str, object] = {
        "results": [],
        "evidence_anchors": [],
        "confidence": 1,
    }

    @staticmethod
    def _served(
        adapter: GroundedAgentAdapter,
        monkeypatch: pytest.MonkeyPatch,
        output: dict[str, object] | None = None,
        result: object = None,
    ) -> dict[str, object]:
        """The served tools: ``done`` (control-only) and ``find``
        (search), which returns ``result`` as it is when given, else
        ``output`` as its structured content when given, else
        :attr:`FOUND` as the JSON text of its one content item."""
        import claude_agent_sdk
        from claude_agent_sdk import tool

        from grounded_agency.mcp import create_grounded_mcp_server

        @tool("done", "Ends the turn.", {})
        async def done(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        @tool("find", "Searches.", {"q": str})
        async def find(args: dict[str, object]) -> object:
            if result is not None:
                return result
            if output is not None:
                return {
                    "content": [{"type": "text", "text": json.dumps(output)}],
                    "structuredContent": output,
                }
            return {
                "content": [
                    {"type": "text", "text": json.dumps(TestGroundedServerGuard.FOUND)}
                ]
            }

        done.metadata = {"control": True}  # type: ignore[attr-defined]
        find.metadata = {"capability": "search"}  # type: ignore[attr-defined]

        captured: dict[str, object] = {}

        def capture(*, name: str, version: str, tools: list[object]) -> object:
            captured.update({t.name: t for t in tools})  # type: ignore[attr-defined]
            return {"name": name}

        monkeypatch.setattr(claude_agent_sdk, "create_sdk_mcp_server", capture)
        create_grounded_mcp_server(
            name="srv", version="1.0.0", tools=[done, find], adapter=adapter
        )
        return captured

    @staticmethod
    async def _pre(adapter: GroundedAgentAdapter, tool: str, args: dict) -> dict:
        hook = adapter._make_pretooluse_safety_hook()
        payload = {"tool_name": tool, "tool_input": args, "tool_use_id": "c1"}
        result: dict = await hook(payload, "c1", None)
        return result

    @pytest.mark.asyncio
    async def test_control_only_tool_runs_after_pretooluse(
        self, asking_adapter: GroundedAgentAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        served = self._served(asking_adapter, monkeypatch)
        assert await self._pre(asking_adapter, "mcp__srv__done", {}) == {}
        result = await served["done"].handler({})  # type: ignore[attr-defined]
        assert result == {"content": [{"type": "text", "text": "ok"}]}

    @pytest.mark.asyncio
    async def test_control_only_tool_runs_without_pretooluse(
        self, asking_adapter: GroundedAgentAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        served = self._served(asking_adapter, monkeypatch)
        for _ in range(2):
            result = await served["done"].handler({})  # type: ignore[attr-defined]
            assert result == {"content": [{"type": "text", "text": "ok"}]}

    @pytest.mark.asyncio
    async def test_bound_tool_runs_once_per_decision(
        self, asking_adapter: GroundedAgentAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        served = self._served(asking_adapter, monkeypatch)
        handler = served["find"].handler  # type: ignore[attr-defined]
        refused = await handler({"q": "x"})
        assert refused["is_error"] is True
        assert refused["content"][0]["text"].startswith("R407 SAFETY_CHECK_FAILED: ")

        assert await self._pre(asking_adapter, "mcp__srv__find", {"q": "x"}) == {}
        assert await handler({"q": "x"}) == {
            "content": [{"type": "text", "text": json.dumps(self.FOUND)}]
        }
        # The decision was for one call: a second needs its own.
        again = await handler({"q": "x"})
        assert again["is_error"] is True

    @pytest.mark.asyncio
    async def test_an_f505_output_is_the_failure_of_the_call_that_ran(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An output a grounding policy refuses (section 5.20) is recorded
        as the outcome of the call that ran: ``failed`` with F505 and the
        call's id, after its ``allowed`` record; not a refusal of a call that
        did not run, and not recorded twice by the post-call hook."""
        from grounded_agency import GroundingPolicy
        from grounded_agency.adapter import call_action_record

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                grounding=GroundingPolicy(require={"search"}),
            )
        )
        served = self._served(adapter, monkeypatch)
        assert await self._pre(adapter, "mcp__srv__find", {"q": "x"}) == {}
        result = await served["find"].handler({"q": "x"})  # type: ignore[attr-defined]
        assert result["is_error"] is True
        assert result["content"][0]["text"].startswith("F505 PROVENANCE_MISSING: ")
        post = adapter._make_mutation_consumer()
        await post(
            {
                "tool_name": "mcp__srv__find",
                "tool_input": {"q": "x"},
                "tool_response": result,
            },
            "c1",
            None,
        )
        records = [r for r in adapter.call_records if r.get("call") == "c1"]
        assert [r["decision"] for r in records] == ["allowed", "failed"]
        assert records[1]["diagnostic"]["code"] == "F505"
        exported = call_action_record(records[1], "s")
        assert exported is not None
        assert exported["status"] == "failed"
        assert exported["code"] == "F505"
        assert exported["call_id"] == "c1"
        assert not [r for r in adapter.call_records if r["decision"] == "refused"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("evidence_policy", "code", "reason"),
        [
            ({"require_grounding": ["search"]}, "F505", None),
            ({"minimum_confidence": 0.9}, "F504", "below_minimum_confidence"),
        ],
    )
    async def test_an_applied_profile_alone_checks_a_served_tool_output(
        self,
        ontology_path: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        evidence_policy: dict[str, object],
        code: str,
        reason: str | None,
    ) -> None:
        """A profile's grounding policy and minimum confidence (section
        5.21.3) apply to the output of a tool the adapter serves with no
        ``config.grounding``: F505 for an ungrounded output, F504 for one
        below the minimum, each the failure of the call that ran."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                profiles=[
                    {
                        "domain": "d",
                        "version": "1.0.0",
                        "evidence_policy": evidence_policy,
                    }
                ],
            )
        )
        low = {"results": [], "confidence": 0.1, "evidence_anchors": []}
        served = self._served(adapter, monkeypatch, output=low)
        assert await self._pre(adapter, "mcp__srv__find", {"q": "x"}) == {}
        result = await served["find"].handler({"q": "x"})  # type: ignore[attr-defined]
        assert result["is_error"] is True
        assert result["content"][0]["text"].startswith(f"{code} ")
        records = [r for r in adapter.call_records if r.get("call") == "c1"]
        assert [r["decision"] for r in records] == ["allowed", "failed"]
        assert records[1]["diagnostic"]["code"] == code
        assert records[1].get("reason") == reason

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("result", "problem"),
        [
            # Prose, not the capability output (section 5.18.9).
            (
                {"content": [{"type": "text", "text": "found"}]},
                "is not the JSON text of one object",
            ),
            # Text around the JSON.
            (
                {"content": [{"type": "text", "text": 'Here: {"results": []}'}]},
                "is not the JSON text of one object",
            ),
            # Structured content without the contract's required fields.
            ({"structuredContent": {"results": []}}, "is missing evidence_anchors"),
            # Structured content that is not an object.
            ({"structuredContent": ["a"]}, "is not a JSON object"),
            # Two content items: not one output object.
            (
                {
                    "content": [
                        {"type": "text", "text": "{}"},
                        {"type": "text", "text": "{}"},
                    ]
                },
                "carries 2 content item(s)",
            ),
            # An integer no I-JSON reader holds exactly.
            (
                {
                    "structuredContent": {
                        "results": [9007199254740993],
                        "evidence_anchors": [],
                        "confidence": 1,
                    }
                },
                "outside ±2^53",
            ),
            # A confidence outside 0 to 1.
            (
                {
                    "structuredContent": {
                        "results": [],
                        "evidence_anchors": [],
                        "confidence": 2,
                    }
                },
                "confidence is not a number from 0 to 1",
            ),
        ],
    )
    async def test_a_result_that_breaks_the_output_contract_is_r402(
        self,
        asking_adapter: GroundedAgentAdapter,
        monkeypatch: pytest.MonkeyPatch,
        result: dict[str, object],
        problem: str,
    ) -> None:
        """The output-contract row of section 5.18.10: the result of a call
        of a served tool with a capability carries that capability's output
        (its structured content, or the I-JSON text of the object as its one
        text item, section 5.18.9) with every field the contract requires;
        otherwise the call that ran fails with R402, recorded against it once
        (the post-call hook does not record it again)."""
        served = self._served(asking_adapter, monkeypatch, result=result)
        assert await self._pre(asking_adapter, "mcp__srv__find", {"q": "x"}) == {}
        got = await served["find"].handler({"q": "x"})  # type: ignore[attr-defined]
        assert got["is_error"] is True
        text = got["content"][0]["text"]
        assert text.startswith("R402 EXECUTION_FAILED: mcp__srv__find's result: ")
        assert problem in text
        post = asking_adapter._make_mutation_consumer()
        await post(
            {
                "tool_name": "mcp__srv__find",
                "tool_input": {"q": "x"},
                "tool_response": got,
            },
            "c1",
            None,
        )
        records = [r for r in asking_adapter.call_records if r.get("call") == "c1"]
        assert [r["decision"] for r in records] == ["allowed", "failed"]
        assert records[1]["diagnostic"]["code"] == "R402"
        assert records[1]["diagnostic"]["location"] == {
            "tool": "mcp__srv__find",
            "capability": "search",
            "call": "c1",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "result",
        [
            {"structuredContent": FOUND},
            {"content": [{"type": "text", "text": json.dumps(FOUND)}]},
            # Structured content is the output whatever the text says.
            {
                "content": [{"type": "text", "text": "3 results"}],
                "structuredContent": FOUND,
            },
        ],
    )
    async def test_a_result_that_carries_the_output_passes(
        self,
        asking_adapter: GroundedAgentAdapter,
        monkeypatch: pytest.MonkeyPatch,
        result: dict[str, object],
    ) -> None:
        served = self._served(asking_adapter, monkeypatch, result=result)
        assert await self._pre(asking_adapter, "mcp__srv__find", {"q": "x"}) == {}
        assert await served["find"].handler({"q": "x"}) == result  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_an_error_result_is_passed_on(
        self, asking_adapter: GroundedAgentAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tool that reports an error returns no output: its result is
        passed on, and the post-call hook records the failure."""
        failed = {"content": [{"type": "text", "text": "no index"}], "is_error": True}
        served = self._served(asking_adapter, monkeypatch, result=failed)
        assert await self._pre(asking_adapter, "mcp__srv__find", {"q": "x"}) == {}
        assert await served["find"].handler({"q": "x"}) == failed  # type: ignore[attr-defined]
        assert list(asking_adapter.diagnostics) == []

    def test_an_unbound_tool_has_no_output_contract(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        """An unbound tool (section 5.18.2) performs no capability the layer
        knows, so its result has no contract to satisfy: it is passed on."""
        asking_adapter.mapper.register_mcp_tool("mcp__srv__other")
        prose = {"content": [{"type": "text", "text": "done"}]}
        assert asking_adapter.check_call_result("mcp__srv__other", {}, prose) is None
        assert list(asking_adapter.diagnostics) == []

    @pytest.mark.asyncio
    async def test_the_contract_is_checked_before_grounding(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R402 comes before F505, as the executor checks them."""
        from grounded_agency import GroundingPolicy

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                grounding=GroundingPolicy(require={"search"}),
            )
        )
        served = self._served(
            adapter,
            monkeypatch,
            result={"content": [{"type": "text", "text": "found"}]},
        )
        assert await self._pre(adapter, "mcp__srv__find", {"q": "x"}) == {}
        got = await served["find"].handler({"q": "x"})  # type: ignore[attr-defined]
        assert got["content"][0]["text"].startswith("R402 ")
        assert [d.code_str for d in adapter.diagnostics] == ["R402"]

    @pytest.mark.asyncio
    async def test_check_outputs_off_passes_results_on(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``check_outputs=False`` (outside class SL) passes a result on as
        it is, as before 1.2.0, and the layer's configuration says so."""
        on = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".on"),
            )
        )
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                check_outputs=False,
            )
        )
        prose = {"content": [{"type": "text", "text": "found"}]}
        served = self._served(adapter, monkeypatch, result=prose)
        assert await self._pre(adapter, "mcp__srv__find", {"q": "x"}) == {}
        assert await served["find"].handler({"q": "x"}) == prose  # type: ignore[attr-defined]
        assert list(adapter.diagnostics) == []
        assert adapter.recorded_by["config_sha256"] != on.recorded_by["config_sha256"]


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
        from claude_agent_sdk import ClaudeAgentOptions

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
        from claude_agent_sdk import ClaudeAgentOptions

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
        from claude_agent_sdk import ClaudeAgentOptions

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
