"""
Tests for the tool-call safety layer's ontology rules.

Covers what the Python SDK integration does with a tool call outside a
workflow:

- ``ToolCapabilityMapper`` resolves a declared capability against the
  ontology, combines declared flags with the ontology's (STANDARD v1.1
  section 5.2.1; a weaker one is W602), and gives a tool it does not know
  the strictest flags.
- The adapter's PreToolUse hook answers ``"ask"`` for a call whose mapping
  requires approval (F502) once the checkpoint rule (F501) is satisfied,
  and its permission callback hands the decision to the host's callback.
- Evidence anchors keep a tool's input only when asked to.
"""

from __future__ import annotations

import json
import logging
import typing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from claude_agent_sdk import (
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
)

import grounded_agency.adapter as adapter_module
from grounded_agency import (
    CapabilityRegistry,
    ErrorCode,
    EvidenceAnchor,
    EvidenceStore,
    GroundedAgentAdapter,
    GroundedAgentConfig,
    RateLimitConfig,
    ToolCapabilityMapper,
    ToolMapping,
)
from grounded_agency.capabilities import mapper as mapper_module
from grounded_agency.capabilities.mapper import UNCLASSIFIED_TOOL
from grounded_agency.hooks.evidence_collector import create_evidence_collector

F501 = "F501 CHECKPOINT_REQUIRED: "
F502 = "F502 APPROVAL_REQUIRED: "
SECRET = "sk-test-0123456789abcdef"


def _decision(result: dict[str, Any]) -> str | None:
    """The PreToolUse permission decision, as the SDK reads it."""
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


def _reason(result: dict[str, Any]) -> str:
    return result.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


def _allowed(result: Any) -> bool:
    return getattr(result, "behavior", None) == "allow"


def _denied(result: Any) -> bool:
    return getattr(result, "behavior", None) == "deny"


def _ctx(tool_use_id: str, **more: Any) -> Any:
    return SimpleNamespace(tool_use_id=tool_use_id, **more)


def _config(ontology_path: str, tmp_path: Path, **more: Any) -> GroundedAgentConfig:
    return GroundedAgentConfig(
        ontology_path=ontology_path,
        checkpoint_dir=str(tmp_path / ".checkpoints"),
        **more,
    )


@pytest.fixture
def registry(ontology_path: str) -> CapabilityRegistry:
    return CapabilityRegistry(ontology_path)


@pytest.fixture
def mapper(registry: CapabilityRegistry) -> ToolCapabilityMapper:
    return ToolCapabilityMapper(registry)


class _Host:
    """A host ``can_use_tool`` callback that records what it was asked."""

    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[tuple[str, dict[str, Any], Any]] = []

    async def __call__(
        self, tool_name: str, tool_input: dict[str, Any], context: Any
    ) -> Any:
        self.calls.append((tool_name, tool_input, context))
        if self.allow:
            return PermissionResultAllow(updated_input=tool_input)
        return PermissionResultDeny(message="the reviewer said no")


# =============================================================================
# Mapper: capability ids and effective flags
# =============================================================================


class TestRegistrationFollowsTheOntology:
    """register_mcp_tool resolves the capability and never weakens it."""

    def test_mutate_declared_low_risk_still_needs_a_checkpoint(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        mapping = mapper.register_mcp_tool(
            "mcp__db__insert", capability_id="mutate", risk="low"
        )

        assert mapping == mapper.map_tool("mcp__db__insert", {})
        assert mapping.risk == "high"
        assert mapping.mutation is True
        assert mapping.requires_checkpoint is True
        assert mapping.requires_approval is True

    def test_weaker_declaration_is_reported_as_w602(
        self, mapper: ToolCapabilityMapper, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger=mapper_module.logger.name):
            mapping = mapper.register_mcp_tool(
                "mcp__db__insert",
                capability_id="mutate",
                risk="low",
                mutation=False,
                requires_checkpoint=False,
                requires_approval=False,
            )

        assert (mapping.risk, mapping.mutation) == ("high", True)
        assert mapping.requires_checkpoint and mapping.requires_approval
        reports = mapper.warnings
        assert {r.code for r in reports} == {ErrorCode.SAFETY_FLAG_DOWNGRADE}
        assert [r.location["field"] for r in reports] == [
            "risk",
            "mutation",
            "requires_checkpoint",
            "requires_approval",
        ]
        for report in reports:
            assert report.severity.value == "warning"
            assert report.location["tool"] == "mcp__db__insert"
            assert report.location["capability"] == "mutate"
            assert "the ontology value applies" in report.message
        assert caplog.text.count("W602 SAFETY_FLAG_DOWNGRADE") == 4

    def test_declaration_equal_to_the_ontology_is_not_reported(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        mapper.register_mcp_tool(
            "mcp__docs__search",
            capability_id="search",
            risk="low",
            mutation=False,
            requires_checkpoint=False,
            requires_approval=False,
        )
        assert mapper.warnings == []

    def test_stricter_declaration_takes_effect(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        mapping = mapper.register_mcp_tool(
            "mcp__pager__read",
            capability_id="observe",
            risk="medium",
            requires_approval=True,
            domain="incident",
        )

        assert mapping == ToolMapping(
            capability_id="observe",
            risk="medium",
            mutation=False,
            requires_checkpoint=False,
            requires_approval=True,
            domain="incident",
        )
        assert mapper.warnings == []

    def test_undeclared_flags_are_the_ontologys(
        self, mapper: ToolCapabilityMapper, registry: CapabilityRegistry
    ) -> None:
        for node in registry.all_capabilities():
            mapping = mapper.register_mcp_tool(f"mcp__t__{node.id}", node.id)
            assert (
                mapping.risk,
                mapping.mutation,
                mapping.requires_checkpoint,
                mapping.requires_approval,
            ) == (
                node.risk,
                node.mutation,
                node.requires_checkpoint,
                node.requires_approval,
            ), node.id
        assert mapper.warnings == []

    def test_mutation_false_is_honoured_only_where_overridable(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        audit = mapper.register_mcp_tool(
            "mcp__log__append", capability_id="audit", mutation=False
        )
        persist = mapper.register_mcp_tool(
            "mcp__kv__put", capability_id="persist", mutation=False
        )

        assert audit.mutation is False
        assert persist.mutation is True
        assert [w.location["tool"] for w in mapper.warnings] == ["mcp__kv__put"]

    def test_unknown_capability_id_is_refused(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        with pytest.raises(ValueError, match="V101 UNKNOWN_CAPABILITY") as raised:
            mapper.register_mcp_tool("mcp__x__y", capability_id="no_such_capability")

        assert "no_such_capability" in str(raised.value)
        # Nothing was registered: the tool is still unclassified.
        assert mapper.map_tool("mcp__x__y", {}) is UNCLASSIFIED_TOOL

    @pytest.mark.parametrize(
        "declaration",
        [
            {"risk": "critical"},
            {"risk": ["high"]},
            {"mutation": "no"},
            {"requires_checkpoint": 0},
            {"requires_approval": "false"},
            {"domain": 7},
            {"capability_id": ["mutate"]},
        ],
    )
    def test_malformed_declaration_is_refused(
        self, mapper: ToolCapabilityMapper, declaration: dict[str, Any]
    ) -> None:
        """A flag that is neither true nor false cannot be combined with
        the ontology's; guessing would let ``"false"`` or ``0`` through."""
        with pytest.raises(ValueError):
            mapper.register_mcp_tool(
                "mcp__x__y", **{"capability_id": "mutate"} | declaration
            )
        assert mapper.map_tool("mcp__x__y", {}) is UNCLASSIFIED_TOOL

    def test_registering_again_replaces_the_reports(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        mapper.register_mcp_tool("mcp__db__insert", "mutate", risk="low")
        assert len(mapper.warnings) == 1
        mapper.register_mcp_tool("mcp__db__insert", "mutate")
        assert mapper.warnings == []

    def test_mapping_is_immutable(self, mapper: ToolCapabilityMapper) -> None:
        mapping = mapper.map_tool("Write", {})
        with pytest.raises(AttributeError):
            mapping.requires_checkpoint = False  # type: ignore[misc]


class TestMapperOntologySources:
    """The flags come from whichever ontology the mapper was given."""

    def test_without_an_ontology_the_packaged_one_is_used(self) -> None:
        mapper = ToolCapabilityMapper()
        assert mapper.map_tool("Write", {}).requires_approval is True
        with pytest.raises(ValueError, match="V101"):
            mapper.register_mcp_tool("mcp__x__y", capability_id="nope")

    def test_raw_ontology_dict(self, registry: CapabilityRegistry) -> None:
        mapper = ToolCapabilityMapper(registry.ontology)
        assert mapper.map_tool("Edit", {}).requires_checkpoint is True
        with pytest.raises(ValueError, match="V101"):
            mapper.register_mcp_tool("mcp__x__y", capability_id="nope")

    def test_static_mappings_take_their_flags_from_the_ontology(
        self, mapper: ToolCapabilityMapper, registry: CapabilityRegistry
    ) -> None:
        for tool, capability_id in mapper_module._TOOL_MAPPINGS.items():
            node = registry.get_capability(capability_id)
            assert node is not None, tool
            assert mapper.map_tool(tool, {}) == ToolMapping(
                capability_id=capability_id,
                risk=node.risk,
                mutation=node.mutation,
                requires_checkpoint=node.requires_checkpoint,
                requires_approval=node.requires_approval,
            ), tool

    def test_a_stricter_ontology_makes_a_static_tool_stricter(
        self, registry: CapabilityRegistry
    ) -> None:
        ontology = json.loads(json.dumps(registry.ontology))
        for node in ontology["nodes"]:
            if node["id"] == "retrieve":
                node["requires_approval"] = True
                node["risk"] = "medium"
        mapper = ToolCapabilityMapper(ontology)

        read = mapper.map_tool("Read", {})
        assert read.requires_approval is True
        assert read.risk == "medium"

    def test_renamed_builtin_tools_keep_their_capability(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        assert mapper.map_tool("Agent", {}) == mapper.map_tool("Task", {})
        assert mapper.map_tool("AskUserQuestion", {}) == mapper.map_tool("AskUser", {})


class TestUnclassifiedTool:
    """A tool the mapper does not know is the strictest case, defined once."""

    def test_unknown_tool_is_the_strictest_case(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        mapping = mapper.map_tool("mcp__unknown__tool", {"anything": 1})

        assert mapping is UNCLASSIFIED_TOOL
        assert mapping == ToolMapping(
            capability_id="mutate",
            risk="high",
            mutation=True,
            requires_checkpoint=True,
            requires_approval=True,
        )
        assert mapper.requires_checkpoint("mcp__unknown__tool", {}) is True
        assert mapper.requires_approval("mcp__unknown__tool", {}) is True
        assert mapper.is_mutation("mcp__unknown__tool", {}) is True
        assert mapper.is_high_risk("mcp__unknown__tool", {}) is True

    @pytest.mark.parametrize(
        ("tool", "capability"),
        [
            ("ToolSearch", "search"),
            ("BashOutput", "observe"),
            ("TaskOutput", "observe"),
            ("ListMcpResourcesTool", "observe"),
            ("ReadMcpResourceTool", "retrieve"),
            ("ExitPlanMode", "inquire"),
            ("TaskList", "recall"),
            ("TaskGet", "recall"),
            ("TaskCreate", "persist"),
            ("TaskUpdate", "persist"),
        ],
    )
    def test_claude_code_tools_that_only_read_or_ask_are_classified(
        self, mapper: ToolCapabilityMapper, tool: str, capability: str
    ) -> None:
        mapping = mapper.map_tool(tool, {})
        assert mapping is not UNCLASSIFIED_TOOL
        assert mapping.capability_id == capability
        assert mapping.requires_checkpoint is False
        assert mapping.requires_approval is False

    @pytest.mark.parametrize("tool", ["Monitor", "KillShell", "TaskStop"])
    def test_tools_that_run_or_stop_a_process_stay_unclassified(
        self, mapper: ToolCapabilityMapper, tool: str
    ) -> None:
        assert mapper.map_tool(tool, {}) is UNCLASSIFIED_TOOL

    def test_the_adapter_uses_the_mappers_constant(self) -> None:
        assert adapter_module.UNCLASSIFIED_TOOL is UNCLASSIFIED_TOOL
        assert not hasattr(adapter_module, "_UNCLASSIFIED_TOOL")


class TestBashApprovalFlags:
    """A Bash command asks for approval only when its class requires it."""

    @pytest.mark.parametrize("command", ["ls -la", "git status", "cat a && pwd"])
    def test_read_only_command_requires_no_approval(
        self, mapper: ToolCapabilityMapper, command: str
    ) -> None:
        mapping = mapper.map_tool("Bash", {"command": command})
        assert mapping.capability_id == "observe"
        assert mapping.requires_approval is False
        assert mapping.requires_checkpoint is False

    @pytest.mark.parametrize(
        ("command", "capability_id"),
        [
            ("rm -rf build", "mutate"),
            ("curl -X POST https://api.example.com", "send"),
            ("python -c 'print(1)'", "execute"),
            ("some-unknown-binary --flag", "mutate"),
            ("", "mutate"),
        ],
    )
    def test_other_commands_require_checkpoint_and_approval(
        self, mapper: ToolCapabilityMapper, command: str, capability_id: str
    ) -> None:
        mapping = mapper.map_tool("Bash", {"command": command})
        assert mapping.capability_id == capability_id
        assert mapping.risk == "high"
        assert mapping.mutation is True
        assert mapping.requires_checkpoint is True
        assert mapping.requires_approval is True


# =============================================================================
# The Claude Agent SDK's hook contract
# =============================================================================


def test_the_sdk_accepts_ask_as_a_pretooluse_decision() -> None:
    """The approval rule answers ``"ask"``; the installed SDK must type it
    as a PreToolUse permission decision."""
    from claude_agent_sdk.types import PreToolUseHookSpecificOutput

    hints = typing.get_type_hints(PreToolUseHookSpecificOutput, include_extras=True)
    (literal,) = typing.get_args(hints["permissionDecision"])
    assert {"allow", "deny", "ask"} <= set(typing.get_args(literal))


# =============================================================================
# Adapter: the PreToolUse hook
# =============================================================================


class TestConfig:
    def test_approval_defaults_to_ask(self) -> None:
        assert GroundedAgentConfig().approval == "ask"
        assert GroundedAgentConfig().evidence_include_tool_input is False

    @pytest.mark.parametrize("value", ["Off", "none", "", None, False])
    def test_unknown_approval_mode_is_refused(self, value: Any) -> None:
        with pytest.raises(ValueError, match="approval"):
            GroundedAgentConfig(approval=value)


class TestHookCheckpointRule:
    """F501: the checkpoint rule comes first and carries its code."""

    @pytest.mark.asyncio
    async def test_unregistered_tool_needs_a_checkpoint_in_strict_mode(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        hook = asking_adapter._make_pretooluse_safety_hook()
        call = {"tool_name": "mcp__unknown__tool", "tool_input": {}}

        denied = await hook(call, "u1", None)

        assert _decision(denied) == "deny"
        assert _reason(denied).startswith(F501)
        assert "mcp__unknown__tool has no capability mapping" in _reason(denied)

        asking_adapter.create_checkpoint(["*"], "Test")
        assert _decision(await hook(call, "u2", None)) == "ask"

    @pytest.mark.asyncio
    async def test_unregistered_tool_needs_a_checkpoint_without_approval(
        self, strict_adapter: GroundedAgentAdapter
    ) -> None:
        hook = strict_adapter._make_pretooluse_safety_hook()
        call = {"tool_name": "mcp__unknown__tool", "tool_input": {}}

        assert _decision(await hook(call, "u1", None)) == "deny"
        strict_adapter.create_checkpoint(["*"], "Test")
        assert await hook(call, "u2", None) == {}

    @pytest.mark.asyncio
    async def test_weakly_declared_mutate_needs_a_checkpoint(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        asking_adapter.mapper.register_mcp_tool(
            "mcp__db__insert",
            capability_id="mutate",
            risk="low",
            requires_checkpoint=False,
        )
        hook = asking_adapter._make_pretooluse_safety_hook()

        denied = await hook(
            {"tool_name": "mcp__db__insert", "tool_input": {}}, "m1", None
        )

        assert _decision(denied) == "deny"
        assert _reason(denied).startswith(
            F501 + "mcp__db__insert (capability 'mutate') requires checkpoint"
        )

    @pytest.mark.asyncio
    async def test_missing_checkpoint_is_denied_not_asked(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        hook = asking_adapter._make_pretooluse_safety_hook()

        result = await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)

        assert _decision(result) == "deny"
        assert _reason(result).startswith(F501)

    @pytest.mark.asyncio
    async def test_reserved_checkpoint_is_f501(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        checkpoint_id = asking_adapter.create_checkpoint(["*"], "Test")
        hook = asking_adapter._make_pretooluse_safety_hook()

        first = await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)
        second = await hook({"tool_name": "Edit", "tool_input": {}}, "w2", None)

        assert _decision(first) == "ask"
        assert _decision(second) == "deny"
        assert _reason(second).startswith(F501)
        assert f"checkpoint {checkpoint_id} is reserved" in _reason(second)

    @pytest.mark.asyncio
    async def test_rate_limited_call_is_denied_not_asked(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        adapter = GroundedAgentAdapter(
            _config(
                ontology_path,
                tmp_path,
                rate_limit=RateLimitConfig(high_rpm=1, burst_multiplier=1.0),
            )
        )
        adapter.create_checkpoint(["*"], "Test")
        hook = adapter._make_pretooluse_safety_hook()
        assert adapter.rate_limiter.allow("high")  # use the only token

        result = await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)

        assert _decision(result) == "deny"
        assert "Rate limited" in _reason(result)


class TestHookApprovalRule:
    """F502: a call that requires approval is put to the host."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "tool_input", "subject"),
        [
            ("Write", {"file_path": "a.txt"}, "Write (capability 'mutate')"),
            ("Edit", {"file_path": "a.txt"}, "Edit (capability 'mutate')"),
            ("Bash", {"command": "rm -rf build"}, "Bash (capability 'mutate')"),
            (
                "Bash",
                {"command": "curl -X POST https://x.example"},
                "Bash (capability 'send')",
            ),
            (
                "Bash",
                {"command": "python -c 'print(1)'"},
                "Bash (capability 'execute')",
            ),
        ],
    )
    async def test_mutating_call_asks(
        self,
        asking_adapter: GroundedAgentAdapter,
        tool_name: str,
        tool_input: dict[str, Any],
        subject: str,
    ) -> None:
        asking_adapter.create_checkpoint(["*"], "Test")
        hook = asking_adapter._make_pretooluse_safety_hook()

        result = await hook(
            {"tool_name": tool_name, "tool_input": tool_input}, "c1", None
        )

        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert _decision(result) == "ask"
        assert _reason(result).startswith(F502 + subject + " requires approval")
        # The call holds the checkpoint while the host decides.
        assert not asking_adapter.checkpoint_tracker.validate_and_reserve("other")[0]
        assert asking_adapter.checkpoint_tracker.validate_and_reserve("c1")[0]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "tool_input"),
        [
            ("Read", {"file_path": "a.txt"}),
            ("Grep", {"pattern": "x"}),
            ("Glob", {"pattern": "*.py"}),
            ("Bash", {"command": "ls -la"}),
            ("Bash", {"command": "git status && git log"}),
            ("Skill", {"skill": "checkpoint"}),
            ("TodoWrite", {"todos": []}),
            ("Agent", {"prompt": "look"}),
        ],
    )
    async def test_call_that_requires_no_approval_does_not_ask(
        self,
        asking_adapter: GroundedAgentAdapter,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> None:
        hook = asking_adapter._make_pretooluse_safety_hook()

        result = await hook(
            {"tool_name": tool_name, "tool_input": tool_input}, "c1", None
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_execute_tool_asks_without_needing_a_checkpoint(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        """``execute`` requires approval and no checkpoint in the ontology."""
        asking_adapter.mapper.register_mcp_tool("mcp__ci__run", capability_id="execute")
        hook = asking_adapter._make_pretooluse_safety_hook()

        result = await hook({"tool_name": "mcp__ci__run", "tool_input": {}}, "e1", None)

        assert _decision(result) == "ask"
        assert _reason(result).startswith(F502 + "mcp__ci__run (capability 'execute')")

    @pytest.mark.asyncio
    async def test_declared_approval_on_a_read_asks(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        asking_adapter.mapper.register_mcp_tool(
            "mcp__hr__lookup", capability_id="retrieve", requires_approval=True
        )
        hook = asking_adapter._make_pretooluse_safety_hook()

        result = await hook(
            {"tool_name": "mcp__hr__lookup", "tool_input": {}}, "r1", None
        )

        assert _decision(result) == "ask"

    @pytest.mark.asyncio
    async def test_non_strict_mode_still_asks(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """strict_mode governs the checkpoint rule only."""
        lenient = GroundedAgentAdapter(
            _config(ontology_path, tmp_path, strict_mode=False)
        )
        hook = lenient._make_pretooluse_safety_hook()

        result = await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)

        assert _decision(result) == "ask"
        assert _reason(result).startswith(F502)

    @pytest.mark.asyncio
    async def test_unclassifiable_call_asks_once_it_has_a_checkpoint(
        self, asking_adapter: GroundedAgentAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(*args: object) -> None:
            raise RuntimeError("mapper exploded at /secret/path")

        monkeypatch.setattr(asking_adapter.mapper, "map_tool", fail)
        hook = asking_adapter._make_pretooluse_safety_hook()
        call = {"tool_name": "Read", "tool_input": {}}

        denied = await hook(call, "r1", None)
        assert _decision(denied) == "deny"
        assert _reason(denied).startswith(F501)

        asking_adapter.create_checkpoint(["*"], "Test")
        asked = await hook(call, "r2", None)
        assert _decision(asked) == "ask"
        assert "/secret/path" not in _reason(asked) + _reason(denied)

    @pytest.mark.asyncio
    async def test_error_let_through_in_non_strict_mode_still_asks(
        self, ontology_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lenient = GroundedAgentAdapter(
            _config(ontology_path, tmp_path, strict_mode=False)
        )
        lenient.create_checkpoint(["*"], "Test")

        def fail(*args: object, **kwargs: object) -> None:
            raise RuntimeError("tracker broken")

        monkeypatch.setattr(lenient.checkpoint_tracker, "validate_and_reserve", fail)
        hook = lenient._make_pretooluse_safety_hook()

        result = await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)

        assert _decision(result) == "ask"


class TestApprovalOff:
    """``approval="off"`` restores the behaviour before the approval rule."""

    @pytest.mark.asyncio
    async def test_mutating_call_passes_the_hook_with_a_checkpoint(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        adapter = GroundedAgentAdapter(_config(ontology_path, tmp_path, approval="off"))
        hook = adapter._make_pretooluse_safety_hook()
        call = {"tool_name": "Write", "tool_input": {}}

        denied = await hook(call, "w1", None)
        assert _decision(denied) == "deny"
        assert _reason(denied).startswith(F501)

        adapter.create_checkpoint(["*"], "Test")
        assert await hook(call, "w2", None) == {}

    @pytest.mark.asyncio
    async def test_callback_allows_with_a_checkpoint_and_no_host(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        adapter = GroundedAgentAdapter(_config(ontology_path, tmp_path, approval="off"))
        callback = adapter._make_permission_callback()

        assert _denied(await callback("Write", {}, _ctx("w1")))
        adapter.create_checkpoint(["*"], "Test")
        assert _allowed(await callback("Write", {}, _ctx("w2")))

    @pytest.mark.asyncio
    async def test_execute_tool_is_not_asked_about(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        adapter = GroundedAgentAdapter(_config(ontology_path, tmp_path, approval="off"))
        adapter.mapper.register_mcp_tool("mcp__ci__run", capability_id="execute")
        hook = adapter._make_pretooluse_safety_hook()
        callback = adapter._make_permission_callback()

        assert (
            await hook({"tool_name": "mcp__ci__run", "tool_input": {}}, "e1", None)
            == {}
        )
        assert _allowed(await callback("mcp__ci__run", {}, _ctx("e1")))


# =============================================================================
# Adapter: the permission callback
# =============================================================================


class TestPermissionCallbackApproval:
    """The host's callback decides; with none, approval cannot be given."""

    @pytest.mark.asyncio
    async def test_no_host_callback_denies_with_f502(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        asking_adapter.create_checkpoint(["*"], "Test")
        hook = asking_adapter._make_pretooluse_safety_hook()
        callback = asking_adapter._make_permission_callback()

        assert (
            _decision(await hook({"tool_name": "Write", "tool_input": {}}, "w1", None))
            == "ask"
        )
        result = await callback("Write", {}, _ctx("w1"))

        assert _denied(result)
        assert result.message.startswith(
            F502 + "Write (capability 'mutate') requires approval"
        )
        # The call will not run: its reservation is given back.
        assert asking_adapter.has_valid_checkpoint()
        assert asking_adapter.checkpoint_tracker.validate_and_reserve("w2")[0]

    @pytest.mark.asyncio
    async def test_no_host_callback_allows_what_needs_no_approval(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        callback = asking_adapter._make_permission_callback()

        assert _allowed(await callback("Read", {"file_path": "a"}, _ctx("r1")))
        assert _allowed(await callback("Bash", {"command": "ls"}, _ctx("b1")))

    @pytest.mark.asyncio
    async def test_host_approval_lets_the_call_run(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        host = _Host(allow=True)
        asking_adapter.create_checkpoint(["*"], "Test")
        callback = asking_adapter._make_permission_callback(host)
        context = _ctx("w1", decision_reason=F502 + "...")

        result = await callback("Write", {"file_path": "a.txt"}, context)

        assert _allowed(result)
        assert host.calls == [("Write", {"file_path": "a.txt"}, context)]
        # Still reserved for this call, to be consumed after it runs.
        assert not asking_adapter.checkpoint_tracker.validate_and_reserve("w2")[0]

    @pytest.mark.asyncio
    async def test_host_rejection_is_returned_and_releases_the_reservation(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        host = _Host(allow=False)
        asking_adapter.create_checkpoint(["*"], "Test")
        callback = asking_adapter._make_permission_callback(host)

        result = await callback("Write", {}, _ctx("w1"))

        assert _denied(result)
        assert result.message == "the reviewer said no"
        assert asking_adapter.checkpoint_tracker.validate_and_reserve("w2")[0]

    @pytest.mark.asyncio
    async def test_host_is_not_asked_about_a_call_without_a_checkpoint(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        host = _Host(allow=True)
        callback = asking_adapter._make_permission_callback(host)

        result = await callback("Write", {}, _ctx("w1"))

        assert _denied(result)
        assert result.message.startswith(F501)
        assert host.calls == []

    @pytest.mark.asyncio
    async def test_host_decides_calls_that_need_no_approval_too(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        """Claude Code asks the callback about a call its own rules do not
        settle; the adapter does not answer in the host's place."""
        host = _Host(allow=False)
        callback = asking_adapter._make_permission_callback(host)

        result = await callback("Read", {"file_path": "/etc/passwd"}, _ctx("r1"))

        assert _denied(result)
        assert [call[0] for call in host.calls] == ["Read"]

    @pytest.mark.asyncio
    async def test_host_callback_that_raises_denies(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        async def broken(*args: object) -> Any:
            raise RuntimeError("approval service down")

        asking_adapter.create_checkpoint(["*"], "Test")
        callback = asking_adapter._make_permission_callback(broken)

        result = await callback("Write", {}, _ctx("w1"))

        assert _denied(result)
        assert "internal error" in result.message
        assert asking_adapter.checkpoint_tracker.validate_and_reserve("w2")[0]

    @pytest.mark.asyncio
    async def test_host_result_that_is_not_an_allow_releases_the_reservation(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        async def odd(*args: object) -> Any:
            return {"behavior": "allow"}  # not a permission result object

        asking_adapter.create_checkpoint(["*"], "Test")
        callback = asking_adapter._make_permission_callback(odd)

        result = await callback("Write", {}, _ctx("w1"))

        assert result == {"behavior": "allow"}  # the SDK refuses this type
        assert asking_adapter.checkpoint_tracker.validate_and_reserve("w2")[0]

    @pytest.mark.asyncio
    async def test_synchronous_host_callback(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        def host(tool_name: str, tool_input: dict[str, Any], context: Any) -> Any:
            return PermissionResultAllow(updated_input=tool_input)

        asking_adapter.create_checkpoint(["*"], "Test")
        callback = asking_adapter._make_permission_callback(host)

        assert _allowed(await callback("Write", {}, _ctx("w1")))

    @pytest.mark.asyncio
    async def test_approval_off_still_calls_the_host(
        self, strict_adapter: GroundedAgentAdapter
    ) -> None:
        host = _Host(allow=False)
        strict_adapter.create_checkpoint(["*"], "Test")
        callback = strict_adapter._make_permission_callback(host)

        assert _denied(await callback("Write", {}, _ctx("w1")))
        assert len(host.calls) == 1


# =============================================================================
# wrap_options wiring
# =============================================================================


def _pre(wrapped: Any) -> Any:
    return wrapped.hooks["PreToolUse"][-1].hooks[0]


class TestWrapOptionsApproval:
    @pytest.mark.asyncio
    async def test_host_can_use_tool_is_chained_not_replaced(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        host = _Host(allow=True)
        wrapped = asking_adapter.wrap_options(ClaudeAgentOptions(can_use_tool=host))
        asking_adapter.create_checkpoint(["*"], "Test")

        assert wrapped.can_use_tool is not host
        result = await wrapped.can_use_tool("Write", {"file_path": "a"}, _ctx("w1"))

        assert _allowed(result)
        assert len(host.calls) == 1

    @pytest.mark.asyncio
    async def test_wrapping_twice_asks_the_host_once(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        host = _Host(allow=True)
        once = asking_adapter.wrap_options(ClaudeAgentOptions(can_use_tool=host))
        twice = asking_adapter.wrap_options(once)
        asking_adapter.create_checkpoint(["*"], "Test")

        assert _allowed(await twice.can_use_tool("Write", {}, _ctx("w1")))
        assert len(host.calls) == 1

    @pytest.mark.asyncio
    async def test_without_a_host_callback_approval_is_refused(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        wrapped = asking_adapter.wrap_options(
            ClaudeAgentOptions(allowed_tools=["Write"])
        )
        asking_adapter.create_checkpoint(["*"], "Test")
        call = {"tool_name": "Write", "tool_input": {"file_path": "a"}}

        asked = await _pre(wrapped)(call, "w1", None)
        result = await wrapped.can_use_tool("Write", call["tool_input"], _ctx("w1"))

        assert _decision(asked) == "ask"
        assert _denied(result)
        assert result.message.startswith(F502)

    def test_permission_prompt_tool_is_left_to_decide(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        """The SDK refuses can_use_tool beside a permission prompt tool, so
        the adapter installs none and the hook's "ask" goes to that tool."""
        from claude_agent_sdk.types import _configure_can_use_tool

        base = ClaudeAgentOptions(permission_prompt_tool_name="mcp__approvals__prompt")
        wrapped = asking_adapter.wrap_options(base)

        assert wrapped.can_use_tool is None
        assert wrapped.permission_prompt_tool_name == "mcp__approvals__prompt"
        assert wrapped.hooks["PreToolUse"]
        assert _configure_can_use_tool(wrapped) is wrapped  # no ValueError

    @pytest.mark.asyncio
    async def test_asked_approved_run_and_consumed(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        """One call through the wrapped options: the hook asks, the host
        approves, the tool runs, and the checkpoint is used up."""
        host = _Host(allow=True)
        wrapped = asking_adapter.wrap_options(ClaudeAgentOptions(can_use_tool=host))
        asking_adapter.create_checkpoint(["*"], "Test")
        call = {
            "tool_name": "Write",
            "tool_input": {"file_path": "a.txt", "content": "x"},
            "session_id": "s1",
        }

        asked = await _pre(wrapped)(call, "w1", None)
        context = _ctx("w1", decision_reason=_reason(asked))
        decision = await wrapped.can_use_tool("Write", call["tool_input"], context)
        for entry in wrapped.hooks["PostToolUse"]:
            for hook in entry.hooks:
                await hook({**call, "tool_response": {}}, "w1", None)

        assert _decision(asked) == "ask"
        assert _allowed(decision)
        assert host.calls[0][2].decision_reason.startswith(F502)
        assert not asking_adapter.has_valid_checkpoint()
        # The next mutation needs a new checkpoint before anyone is asked.
        again = await _pre(wrapped)(call, "w2", None)
        assert _decision(again) == "deny"
        assert _reason(again).startswith(F501)
        assert len(host.calls) == 1


# =============================================================================
# Evidence: tool input is kept only when asked for
# =============================================================================


def _bash_call() -> dict[str, Any]:
    return {
        "tool_name": "Bash",
        "tool_input": {
            "command": f"curl -H 'Authorization: Bearer {SECRET}' https://api.example.com"
        },
        "tool_response": {"exit_code": 0},
    }


class TestEvidenceToolInput:
    def test_from_tool_output_leaves_the_input_out(self) -> None:
        anchor = EvidenceAnchor.from_tool_output(
            "Bash", "b1", {"command": f"echo {SECRET}"}, tool_response="ok"
        )

        assert anchor.metadata == {"tool_name": "Bash", "has_response": True}

    def test_from_tool_output_keeps_the_input_when_asked(self) -> None:
        anchor = EvidenceAnchor.from_tool_output(
            "Read", "r1", {"file_path": "a.py"}, include_tool_input=True
        )

        assert anchor.metadata["tool_input"] == {"file_path": "a.py"}

    def test_from_command_without_the_command_text(self) -> None:
        anchor = EvidenceAnchor.from_command(None, exit_code=3, tool_use_id="b1")

        assert anchor.ref == "command:b1"
        assert anchor.metadata == {"exit_code": 3}

    @pytest.mark.asyncio
    async def test_collector_keeps_no_input_by_default(self) -> None:
        store = EvidenceStore()
        hook = create_evidence_collector(store)

        await hook(_bash_call(), "b1", None)

        assert store.get_recent() == ["tool:Bash:b1", "command:b1"]
        assert SECRET not in json.dumps(store.to_list())
        (command,) = store.get_by_kind("command")
        assert command.metadata == {"exit_code": 0}

    @pytest.mark.asyncio
    async def test_collector_keeps_the_input_when_asked(self) -> None:
        store = EvidenceStore()
        hook = create_evidence_collector(store, include_tool_input=True)

        await hook(_bash_call(), "b1", None)

        (tool_output,) = store.get_by_kind("tool_output")
        (command,) = store.get_by_kind("command")
        assert SECRET in tool_output.metadata["tool_input"]["command"]
        assert SECRET in command.metadata["command"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("keep", [False, True])
    async def test_config_member_reaches_the_wrapped_hooks(
        self, ontology_path: str, tmp_path: Path, keep: bool
    ) -> None:
        adapter = GroundedAgentAdapter(
            _config(ontology_path, tmp_path, evidence_include_tool_input=keep)
        )
        wrapped = adapter.wrap_options(ClaudeAgentOptions())

        for entry in wrapped.hooks["PostToolUse"]:
            for hook in entry.hooks:
                await hook(_bash_call(), "b1", None)

        assert (SECRET in json.dumps(adapter.evidence_store.to_list())) is keep

    @pytest.mark.asyncio
    async def test_unclassified_tool_is_evidence_of_no_capability(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        store = EvidenceStore()
        hook = create_evidence_collector(store, mapper)

        await hook({"tool_name": "mcp__unknown__tool", "tool_input": {}}, "u1", None)
        await hook({"tool_name": "Write", "tool_input": {}}, "w1", None)

        assert [a.ref for a in store.get_for_capability("mutate")] == ["tool:Write:w1"]
        assert len(store) == 2


# =============================================================================
# MCP server factory
# =============================================================================


class TestMcpFactoryDeclarations:
    @staticmethod
    def _tool(name: str, metadata: dict[str, Any] | None) -> Any:
        from claude_agent_sdk import tool

        @tool(name, "A test tool", {"text": str})
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": args["text"]}]}

        if metadata is not None:
            handler.metadata = metadata  # type: ignore[attr-defined]
        return handler

    def test_metadata_is_combined_with_the_ontology(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        from grounded_agency.mcp import create_grounded_mcp_server

        create_grounded_mcp_server(
            name="db",
            version="1.0.0",
            tools=[
                self._tool("insert", {"capability_id": "mutate", "risk": "low"}),
                self._tool("find", {"capability_id": "search", "domain": "orders"}),
                self._tool("run", None),
            ],
            adapter=asking_adapter,
        )
        mapper = asking_adapter.mapper

        insert = mapper.map_tool("mcp__db__insert", {})
        assert (insert.risk, insert.requires_checkpoint, insert.requires_approval) == (
            "high",
            True,
            True,
        )
        find = mapper.map_tool("mcp__db__find", {})
        assert (find.capability_id, find.risk, find.domain) == (
            "search",
            "low",
            "orders",
        )
        # No metadata: an execute tool, which requires approval.
        run = mapper.map_tool("mcp__db__run", {})
        assert (run.capability_id, run.risk, run.requires_approval) == (
            "execute",
            "medium",
            True,
        )
        assert [w.location["tool"] for w in mapper.warnings] == ["mcp__db__insert"]

    def test_stricter_metadata_flags_reach_the_mapping(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        """A read that its server declares as needing a checkpoint and
        approval keeps both flags: the factory passes every declared flag."""
        from grounded_agency.mcp import create_grounded_mcp_server

        create_grounded_mcp_server(
            name="hr",
            version="1.0.0",
            tools=[
                self._tool(
                    "lookup",
                    {
                        "capability_id": "retrieve",
                        "requires_checkpoint": True,
                        "requires_approval": True,
                    },
                )
            ],
            adapter=asking_adapter,
        )

        lookup = asking_adapter.mapper.map_tool("mcp__hr__lookup", {})
        assert (
            lookup.capability_id,
            lookup.risk,
            lookup.requires_checkpoint,
            lookup.requires_approval,
        ) == ("retrieve", "low", True, True)
        assert asking_adapter.mapper.warnings == []

    def test_unknown_capability_in_metadata_is_refused(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        from grounded_agency.mcp import create_grounded_mcp_server

        with pytest.raises(ValueError, match="V101 UNKNOWN_CAPABILITY"):
            create_grounded_mcp_server(
                name="db",
                version="1.0.0",
                tools=[self._tool("drop", {"capability_id": "destroy"})],
                adapter=asking_adapter,
            )
        assert asking_adapter.mapper.map_tool("mcp__db__drop", {}) is UNCLASSIFIED_TOOL
