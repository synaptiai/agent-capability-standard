"""
Tests for MCP integration: dynamic tool registration and mapper support.

Since claude_agent_sdk may not be installed, these tests focus on:
- Dynamic tool registration in ToolCapabilityMapper
- Capability metadata for registered tools
- Import error handling in create_grounded_mcp_server
"""

from __future__ import annotations

import json
from collections.abc import Callable
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
            # An object without the contract's required fields.
            (
                {"content": [{"type": "text", "text": '{"results": []}'}]},
                "is missing evidence_anchors",
            ),
            # JSON that is not an object.
            ({"content": [{"type": "text", "text": '["a"]'}]}, "is not a JSON object"),
            # The output as structured content only: the SDK's server
            # delivers the content, not structuredContent, so the session
            # would read nothing (section 5.18.9).
            (
                {"content": [], "structuredContent": FOUND},
                "its structuredContent is not delivered to the session",
            ),
            ({"structuredContent": FOUND}, "carries 0 content item(s)"),
            # Prose beside a valid structured output: the session reads the
            # prose, so the prose is checked.
            (
                {
                    "content": [{"type": "text", "text": "3 results"}],
                    "structuredContent": FOUND,
                },
                "is not the JSON text of one object",
            ),
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
                    "content": [
                        {
                            "type": "text",
                            "text": '{"results": [9007199254740993], '
                            '"evidence_anchors": [], "confidence": 1}',
                        }
                    ]
                },
                "outside ±2^53",
            ),
            # A confidence outside 0 to 1.
            (
                {
                    "content": [
                        {
                            "type": "text",
                            "text": '{"results": [], "evidence_anchors": [], '
                            '"confidence": 2}',
                        }
                    ]
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
        as the session reads it (the I-JSON text of the object as its one
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
            {"content": [{"type": "text", "text": json.dumps(FOUND)}]},
            # The text as MCP tools return it beside their structured
            # content: the text is checked, the structure is not delivered.
            {
                "content": [{"type": "text", "text": json.dumps(FOUND)}],
                "structuredContent": FOUND,
            },
            # A forwarded result (mcp.types.CallToolResult.model_dump()) has
            # structuredContent None: no structure at all.
            {
                "content": [{"type": "text", "text": json.dumps(FOUND)}],
                "structuredContent": None,
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
        """``check_outputs=False`` (outside class SL) passes a result on
        without the output-contract check (R402), and the layer's
        configuration says so."""
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

    @pytest.mark.parametrize(
        ("result", "fails"),
        [
            # A grounded structured output beside a text that holds none:
            # the session reads the text, so the policy refuses it.
            (
                {
                    "content": [{"type": "text", "text": "x"}],
                    "structuredContent": {
                        "results": [],
                        "evidence_anchors": [{"ref": "file:a", "kind": "file"}],
                        "confidence": 1,
                    },
                },
                True,
            ),
            # structuredContent None: the text is read.
            (
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "results": [],
                                    "evidence_anchors": [
                                        {"ref": "file:a", "kind": "file"}
                                    ],
                                    "confidence": 1,
                                }
                            ),
                        }
                    ],
                    "structuredContent": None,
                },
                False,
            ),
            # Prose holds no output: the grounding policy refuses it.
            ({"content": [{"type": "text", "text": "found"}]}, True),
            # A result that is not a mapping was passed on.
            ("found", False),
        ],
    )
    def test_check_outputs_off_reads_the_delivered_text(
        self,
        ontology_path: str,
        tmp_path: Path,
        result: object,
        fails: bool,
    ) -> None:
        """With ``check_outputs=False`` the grounding policies read the
        output the one text item carries, the text the session reads; a
        ``structuredContent`` member is not delivered and is not read."""
        from grounded_agency import GroundingPolicy

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                check_outputs=False,
                grounding=GroundingPolicy(require={"search"}),
            )
        )
        adapter.mapper.register_mcp_tool("mcp__srv__find", capability_id="search")
        refusal = adapter.check_call_result("mcp__srv__find", {}, result, "c1")
        if fails:
            assert refusal is not None and refusal.startswith("F505 ")
        else:
            assert refusal is None
            assert list(adapter.diagnostics) == []

    @staticmethod
    def _run_tool(
        adapter: GroundedAgentAdapter,
        monkeypatch: pytest.MonkeyPatch,
        result: dict[str, object],
    ) -> object:
        """The SDK's own ``run_tool`` for a server whose ``find`` (search)
        returns ``result``: what the session receives for a call."""
        import claude_agent_sdk
        from claude_agent_sdk import tool

        from grounded_agency.mcp import create_grounded_mcp_server

        @tool("find", "Searches.", {"q": str})
        async def find(args: dict[str, object]) -> dict[str, object]:
            return result

        find.metadata = {"capability": "search"}  # type: ignore[attr-defined]
        build = claude_agent_sdk.build_tool_server
        captured: dict[str, object] = {}

        def capture(name: str, version: str, tools: object, run_tool: object) -> object:
            captured["run_tool"] = run_tool
            return build(name, version, tools, run_tool)  # type: ignore[arg-type]

        monkeypatch.setattr(claude_agent_sdk, "build_tool_server", capture)
        create_grounded_mcp_server(
            name="srv", version="1.0.0", tools=[find], adapter=adapter
        )
        return captured["run_tool"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("prose", "is_error", "check_outputs", "code"),
        [
            (True, None, True, "R402"),
            (False, None, True, None),
            # An is_error the SDK reads as false: the session receives the
            # result as no error, so it is checked like any other.
            (True, "false", True, "R402"),
            (True, "no", True, "R402"),
            (True, 0, True, "R402"),
            # check_outputs=False: grounding reads the delivered text, not
            # the grounded structure beside it.
            (True, None, False, "F505"),
            (False, None, False, None),
            (True, "false", False, "F505"),
        ],
    )
    async def test_the_session_receives_the_output_that_was_checked(
        self,
        ontology_path: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        prose: bool,
        is_error: object,
        check_outputs: bool,
        code: str | None,
    ) -> None:
        """Through the SDK's server: it delivers a result's content and
        ``is_error``, not its ``structuredContent``, so the adapter checks the
        text. A grounded structured output beside prose is refused, not
        passed on as grounded prose (R402, or F505 with ``check_outputs``
        off); the output's own text passes, and is what the session
        receives. A result is passed on unchecked only when its ``is_error``
        is ``True``."""
        from grounded_agency import GroundingPolicy

        grounded = {
            "results": [],
            "evidence_anchors": [{"ref": "file:README.md", "kind": "file"}],
            "confidence": 1,
        }
        text = "The capital of Mars is Olympus" if prose else json.dumps(grounded)
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                grounding=GroundingPolicy(require={"search"}),
                check_outputs=check_outputs,
            )
        )
        result: dict[str, object] = {
            "content": [{"type": "text", "text": text}],
            "structuredContent": grounded,
        }
        if is_error is not None:
            result["is_error"] = is_error
        run_tool = self._run_tool(adapter, monkeypatch, result)
        assert await self._pre(adapter, "mcp__srv__find", {"q": "x"}) == {}
        delivered = (await run_tool("find", {"q": "x"})).model_dump(  # type: ignore[operator]
            by_alias=True, exclude_none=True
        )
        # The host's form: no structured content reaches the session.
        assert "structuredContent" not in delivered
        if code is not None:
            assert delivered["isError"] is True
            assert delivered["content"][0]["text"].startswith(f"{code} ")
            assert [d.code_str for d in adapter.diagnostics] == [code]
        else:
            assert delivered["isError"] is False
            assert delivered["content"] == [{"type": "text", "text": text}]
            assert list(adapter.diagnostics) == []

    @pytest.mark.asyncio
    async def test_an_error_result_is_passed_on_only_when_is_error_is_true(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``is_error: True`` is an error the session receives as one: it
        carries no output and is passed on, unchecked."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
            )
        )
        failed = {"content": [{"type": "text", "text": "disk full"}], "is_error": True}
        run_tool = self._run_tool(adapter, monkeypatch, failed)
        assert await self._pre(adapter, "mcp__srv__find", {"q": "x"}) == {}
        delivered = (await run_tool("find", {"q": "x"})).model_dump(  # type: ignore[operator]
            by_alias=True, exclude_none=True
        )
        assert delivered["isError"] is True
        assert delivered["content"] == [{"type": "text", "text": "disk full"}]
        assert list(adapter.diagnostics) == []

    @pytest.mark.asyncio
    async def test_a_tool_of_any_class_with_a_handler_is_guarded(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tool that is not an ``SdkMcpTool`` but has the members the SDK's
        server runs is served guarded: R407 without the layer's decision,
        R402 for a result that carries no output (sections 5.18.8,
        5.18.10)."""
        import claude_agent_sdk

        from grounded_agency.mcp import create_grounded_mcp_server

        async def handler(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "The capital is Olympus"}]}

        duck = SimpleNamespace(
            name="find",
            description="Searches.",
            input_schema={"q": str},
            handler=handler,
            metadata={"capability": "search"},
        )
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
            )
        )
        build = claude_agent_sdk.build_tool_server
        captured: dict[str, object] = {}

        def capture(name: str, version: str, tools: object, run_tool: object) -> object:
            captured["run_tool"] = run_tool
            return build(name, version, tools, run_tool)  # type: ignore[arg-type]

        monkeypatch.setattr(claude_agent_sdk, "build_tool_server", capture)
        create_grounded_mcp_server(
            name="srv", version="1.0.0", tools=[duck], adapter=adapter
        )
        run_tool = captured["run_tool"]
        # No decision: R407.
        undecided = (await run_tool("find", {"q": "x"})).model_dump(  # type: ignore[operator]
            by_alias=True, exclude_none=True
        )
        assert undecided["isError"] is True
        assert undecided["content"][0]["text"].startswith("R407 ")
        # A decision, and prose for an output: R402.
        assert await self._pre(adapter, "mcp__srv__find", {"q": "x"}) == {}
        ran = (await run_tool("find", {"q": "x"})).model_dump(  # type: ignore[operator]
            by_alias=True, exclude_none=True
        )
        assert ran["isError"] is True
        assert ran["content"][0]["text"].startswith("R402 ")
        assert [d.code_str for d in adapter.diagnostics] == ["R402"]

    def test_a_tool_that_cannot_be_guarded_is_refused(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """With ``require_layer``, a tool with no callable handler cannot be
        guarded: ``ValueError`` with R407, and nothing is registered."""
        from grounded_agency.mcp import create_grounded_mcp_server

        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
            )
        )
        broken = SimpleNamespace(
            name="find",
            description="Searches.",
            input_schema={},
            handler=None,
            metadata={"capability": "search"},
        )
        with pytest.raises(ValueError, match=r"^R407 SAFETY_CHECK_FAILED: "):
            create_grounded_mcp_server(
                name="srv", version="1.0.0", tools=[broken], adapter=adapter
            )
        assert adapter.mapper.records == []


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


# =============================================================================
# Bound tools of other MCP servers: their output checked at PostToolUse
# =============================================================================


class TestOtherServersOutputs:
    """A tool of an MCP server the adapter does not serve, bound to a
    capability, returns an MCP result that reaches the layer at PostToolUse
    (``tool_response``, the content items Claude Code passes), and the hook
    can replace what the session reads (``updatedMCPToolOutput``). Its
    output is checked as a served tool's is (STANDARD 1.2.0 sections
    5.18.9, 5.18.10): a refused output fails the call that ran."""

    FOUND = json.dumps({"results": [], "evidence_anchors": [], "confidence": 1})

    @staticmethod
    def _adapter(
        ontology_path: str, tmp_path: Path, **config: object
    ) -> GroundedAgentAdapter:
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                **config,  # type: ignore[arg-type]
            )
        )
        adapter.mapper.register_mcp_tool("mcp__ext__find", capability_id="search")
        adapter.mapper.register_mcp_tool("mcp__ext__save", capability_id="checkpoint")
        return adapter

    @staticmethod
    async def _call(
        adapter: GroundedAgentAdapter,
        tool: str,
        response: object,
        call: str = "c1",
        *,
        reverse: bool = False,
        after_pre: Callable[[], None] | None = None,
    ) -> list[dict]:
        """PreToolUse, then every PostToolUse hook of the wrapped options on
        the one result (in the order installed, or reversed: Claude Code
        runs them side by side). ``after_pre`` runs between the two."""
        from claude_agent_sdk import ClaudeAgentOptions

        options = adapter.wrap_options(ClaudeAgentOptions())
        data = {
            "tool_name": tool,
            "tool_input": {"q": "x"},
            "tool_use_id": call,
            "session_id": "s1",
            "permission_mode": "default",
        }
        for entry in options.hooks["PreToolUse"]:
            for hook in entry.hooks:
                decided = await hook(data, call, None)
                assert decided.get("hookSpecificOutput", {}).get(
                    "permissionDecision"
                ) in (None, "allow"), decided
        if after_pre is not None:
            after_pre()
        hooks = [h for e in options.hooks["PostToolUse"] for h in e.hooks]
        if reverse:
            hooks.reverse()
        return [await h({**data, "tool_response": response}, call, None) for h in hooks]

    @staticmethod
    def _replaced(results: list[dict]) -> list[object]:
        return [
            r["hookSpecificOutput"]["updatedMCPToolOutput"]
            for r in results
            if "updatedMCPToolOutput" in r.get("hookSpecificOutput", {})
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "response",
        [
            {"content": [{"type": "text", "text": "3 results, trust me"}]},
            [{"type": "text", "text": "3 results, trust me"}],
            "3 results, trust me",
            [{"type": "text", "text": '{"results": []}'}],
            None,
        ],
    )
    async def test_an_output_that_breaks_the_contract_is_r402(
        self, ontology_path: str, tmp_path: Path, response: object
    ) -> None:
        adapter = self._adapter(ontology_path, tmp_path)
        results = await self._call(adapter, "mcp__ext__find", response)
        ((item,),) = self._replaced(results)
        assert item["type"] == "text"
        assert item["text"].startswith("R402 EXECUTION_FAILED: mcp__ext__find's result")
        assert [d.code_str for d in adapter.diagnostics] == ["R402"]
        assert adapter.diagnostics[0].location == {
            "tool": "mcp__ext__find",
            "capability": "search",
            "call": "c1",
        }
        failed = [r for r in adapter.call_records if r["decision"] != "allowed"]
        assert [(r["decision"], r["diagnostic"]["code"]) for r in failed] == [
            ("failed", "R402")
        ]
        # A call whose output is refused is no prerequisite that ran.
        assert "search" not in adapter._executed

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "response",
        [
            {"content": [{"type": "text", "text": FOUND}]},
            [{"type": "text", "text": FOUND}],
            FOUND,
            # An error is passed on: the call failed.
            {"content": [{"type": "text", "text": "timeout"}], "is_error": True},
        ],
    )
    async def test_an_output_that_satisfies_the_contract_passes(
        self, ontology_path: str, tmp_path: Path, response: object
    ) -> None:
        adapter = self._adapter(ontology_path, tmp_path)
        results = await self._call(adapter, "mcp__ext__find", response)
        assert self._replaced(results) == []
        assert list(adapter.diagnostics) == []

    @pytest.mark.asyncio
    async def test_grounding_applies_to_another_servers_output(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """The grounding policies apply too (F505), with ``check_outputs``
        off as well (only R402 is skipped)."""
        from grounded_agency import GroundingPolicy

        for check_outputs in (True, False):
            adapter = self._adapter(
                ontology_path,
                tmp_path,
                check_outputs=check_outputs,
                grounding=GroundingPolicy(require={"search"}),
            )
            results = await self._call(
                adapter, "mcp__ext__find", [{"type": "text", "text": self.FOUND}]
            )
            ((item,),) = self._replaced(results)
            assert item["text"].startswith("F505 ")
        # With check_outputs off, prose is not R402: it holds no output,
        # which the grounding policy refuses.
        prose = await self._call(adapter, "mcp__ext__find", "trust me", "c2")
        ((item,),) = self._replaced(prose)
        assert item["text"].startswith("F505 ")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reverse", [False, True])
    async def test_a_refused_checkpoint_output_takes_no_checkpoint(
        self, ontology_path: str, tmp_path: Path, reverse: bool
    ) -> None:
        """The checkpoint recorder and the output check run side by side on
        one result and agree: a refused output takes no checkpoint (section
        5.18.6), whatever order the hooks run in; one that passes takes
        one."""
        adapter = self._adapter(ontology_path, tmp_path)
        results = await self._call(
            adapter, "mcp__ext__save", "saved", "c1", reverse=reverse
        )
        ((item,),) = self._replaced(results)
        assert item["text"].startswith("R402 ")
        assert not adapter.checkpoint_tracker.has_valid_checkpoint()
        # The fields the checkpoint output contract requires, plain values.
        node = adapter.registry.get_capability("checkpoint")
        assert node is not None
        value = {
            field: {"checkpoint_id": "cp-1", "evidence_anchors": []}.get(field, True)
            for field in node.output_schema.get("required") or []
        }
        results = await self._call(
            adapter,
            "mcp__ext__save",
            [{"type": "text", "text": json.dumps(value)}],
            "c2",
            reverse=reverse,
        )
        assert self._replaced(results) == []
        assert adapter.checkpoint_tracker.has_valid_checkpoint()

    @pytest.mark.asyncio
    async def test_tools_whose_results_carry_no_output_are_not_checked(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """Claude Code's own tools return results in their own forms; an
        unbound MCP tool and a control-only one have no output contract."""
        adapter = self._adapter(ontology_path, tmp_path)
        adapter.mapper.register_mcp_tool("mcp__ext__legacy")
        adapter.mapper.register_mcp_tool("mcp__ext__done", control=True)
        for tool in ("Read", "Grep", "mcp__ext__legacy", "mcp__ext__done"):
            mapping = adapter.mapper.map_tool(tool, {})
            assert not adapter._checks_host_result(tool, mapping)
            assert adapter._host_result_fault(tool, {}, "prose") is None
        assert adapter._checks_host_result(
            "mcp__ext__find", adapter.mapper.map_tool("mcp__ext__find", {})
        )

    @pytest.mark.asyncio
    async def test_a_check_that_cannot_complete_fails_closed(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A check that raises is R407, and the result the session reads is
        replaced all the same (section 5.18.8)."""
        adapter = self._adapter(ontology_path, tmp_path)

        def broken(*args: object) -> None:
            raise RuntimeError("the registry is gone")

        monkeypatch.setattr(adapter, "_result_fault", broken)
        results = await self._call(
            adapter, "mcp__ext__find", [{"type": "text", "text": self.FOUND}]
        )
        ((item,),) = self._replaced(results)
        assert item["text"].startswith("R407 SAFETY_CHECK_FAILED: ")
        assert [d.code_str for d in adapter.diagnostics] == ["R407"]

    @pytest.mark.asyncio
    async def test_the_result_is_checked_when_its_hold_cannot_be_used(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Using the call's checkpoint fails (the state cannot be saved):
        the call has run, so its result is still checked and replaced
        (section 5.18.8), not passed on."""
        adapter = self._adapter(ontology_path, tmp_path, approval="off")
        adapter.mapper.register_mcp_tool("mcp__ext__write", capability_id="mutate")
        adapter.create_checkpoint(["*"], "before")

        def full(*args: object) -> None:
            raise OSError(28, "No space left on device")

        results = await self._call(
            adapter,
            "mcp__ext__write",
            "done, trust me",
            after_pre=lambda: monkeypatch.setattr(
                adapter.checkpoint_tracker, "_persist_state", full
            ),
        )
        ((item,),) = self._replaced(results)
        assert item["text"].startswith("R402 EXECUTION_FAILED: mcp__ext__write's")
        assert [d.code_str for d in adapter.diagnostics] == ["R402"]

    @pytest.mark.asyncio
    async def test_a_recorder_that_fails_replaces_the_result(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The post-call recorder itself raises: a result it checks is
        replaced with R407, never passed on unchecked (section 5.18.8)."""
        adapter = self._adapter(ontology_path, tmp_path)

        def broken(*args: object, **kw: object) -> None:
            raise RuntimeError("the record store is gone")

        monkeypatch.setattr(adapter, "_take_outcome_recorded", broken)
        results = await self._call(
            adapter, "mcp__ext__find", [{"type": "text", "text": self.FOUND}]
        )
        ((item,),) = self._replaced(results)
        assert item["text"].startswith("R407 SAFETY_CHECK_FAILED: mcp__ext__find's")
        # Claude Code's own tools return no MCP result to replace.
        assert not adapter._may_check_host_result("Read", {})

    @pytest.mark.asyncio
    async def test_a_tool_served_without_require_layer_is_checked_at_post_tool_use(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``require_layer=False`` serves the tool unwrapped (outside class
        SL): its result is then checked at PostToolUse, as another
        server's is."""
        import claude_agent_sdk
        from claude_agent_sdk import tool

        from grounded_agency.mcp import create_grounded_mcp_server

        @tool("find", "Searches.", {"q": str})
        async def find(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "trust me"}]}

        find.metadata = {"capability": "search"}  # type: ignore[attr-defined]
        monkeypatch.setattr(
            claude_agent_sdk,
            "create_sdk_mcp_server",
            lambda *, name, version, tools: {"name": name},
        )
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
            )
        )
        create_grounded_mcp_server(
            name="srv",
            version="1.0.0",
            tools=[find],
            adapter=adapter,
            require_layer=False,
        )
        results = await self._call(
            adapter, "mcp__srv__find", [{"type": "text", "text": "trust me"}]
        )
        ((item,),) = self._replaced(results)
        assert item["text"].startswith("R402 ")

    def test_no_warning_for_a_checked_tool(
        self, ontology_path: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A grounding policy over another server's bound tool is applied,
        so no "not applied" warning is logged; one over Claude Code's own
        tools is warned about."""
        from grounded_agency import GroundingPolicy

        adapter = self._adapter(
            ontology_path, tmp_path, grounding=GroundingPolicy(require={"search"})
        )
        with caplog.at_level("WARNING", logger="grounded_agency.adapter"):
            adapter._warn_unchecked_output(
                adapter.mapper.map_tool("mcp__ext__find", {}), "mcp__ext__find"
            )
            assert "mcp__ext__find" not in caplog.text
            adapter._warn_unchecked_output(adapter.mapper.map_tool("Grep", {}), "Grep")
            assert "Grep" in caplog.text
