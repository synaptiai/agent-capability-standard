"""Tool binding records (STANDARD 1.2.0 sections 5.18.1 to 5.18.4).

The binding fixtures in tests/conformance/bindings/ pin the loader's
diagnostics and effective flags; these tests cover the shape checks, the
metadata carrier, the mapper's registration and the static mappings.
"""

from __future__ import annotations

from typing import Any

import pytest

from grounded_agency import GroundedAgentAdapter
from grounded_agency.capabilities.bindings import (
    ToolBinding,
    check_offered,
    load_bindings,
    parse_record,
)
from grounded_agency.capabilities.mapper import (
    UNCLASSIFIED_TOOL,
    ToolCapabilityMapper,
    ToolMapping,
)
from grounded_agency.capabilities.registry import CapabilityRegistry
from grounded_agency.mcp import _record


@pytest.fixture
def registry(ontology_path: str) -> CapabilityRegistry:
    return CapabilityRegistry(ontology_path)


@pytest.fixture
def mapper(registry: CapabilityRegistry) -> ToolCapabilityMapper:
    return ToolCapabilityMapper(registry)


def _codes(diagnostics: list[Any]) -> list[str]:
    return sorted(d.code_str for d in diagnostics)


def _load(
    registry: CapabilityRegistry, records: list[Any]
) -> tuple[dict[str, ToolMapping], list[Any]]:
    return load_bindings(
        records,
        {n.id: n for n in registry.all_capabilities()},
        [
            (e.from_cap, e.to_cap)
            for e in registry.all_edges()
            if e.edge_type == "requires"
        ],
        registry.version,
    )


def _rec(**members: Any) -> dict[str, Any]:
    return {"tool": "t", "ontology": "2.2.0", **members}


class TestParseRecord:
    def test_a_full_record_reads(self) -> None:
        binding, errors = parse_record(
            _rec(
                standard="1.2",
                capability="send",
                domain="email",
                flags={"risk": "high"},
                additional_capabilities=["mutate"],
                classifier="shell",
                invokes=["other"],
                approval={"min_approvers": 2, "role": "ops", "expires": "PT10M"},
                destination="/to",
                **{"x-vendor": {"anything": 1}},
            )
        )
        assert errors == []
        assert isinstance(binding, ToolBinding)
        assert binding.capabilities == ("send", "mutate")
        assert binding.approval is not None
        assert binding.approval.expires_seconds == 600
        assert binding.destination == "/to"

    @pytest.mark.parametrize(
        ("record", "code", "field"),
        [
            ({"ontology": "2.2.0", "capability": "mutate"}, "S304", "tool"),
            ({"tool": "t", "capability": "mutate"}, "S304", "ontology"),
            (_rec(), "S304", "capability"),
            (_rec(capability="mutate", surprise=1), "S303", "surprise"),
            (_rec(capability="mutate", control=True), "S303", "capability"),
            (_rec(control=False, capability="mutate"), "S303", "control"),
            (_rec(capability=7), "S303", "capability"),
            (_rec(capability="mutate", ontology="2.x"), "S303", "ontology"),
            (_rec(capability="mutate", standard="one"), "S303", "standard"),
            (
                _rec(capability="mutate", flags={"risk": "extreme"}),
                "S303",
                "flags/risk",
            ),
            (
                _rec(capability="mutate", flags={"mutation": "no"}),
                "S303",
                "flags/mutation",
            ),
            (_rec(capability="mutate", flags={"other": True}), "S303", "flags/other"),
            (
                _rec(capability="plan", additional_capabilities=[]),
                "S303",
                "additional_capabilities",
            ),
            (
                _rec(capability="plan", additional_capabilities=["mutate", "mutate"]),
                "S303",
                "additional_capabilities",
            ),
            (_rec(capability="invoke", invokes=["a", "a"]), "S303", "invokes"),
            (
                _rec(capability="mutate", approval={"min_approvers": 0}),
                "S303",
                "approval/min_approvers",
            ),
            (
                _rec(capability="mutate", approval={"min_approvers": True}),
                "S303",
                "approval/min_approvers",
            ),
            (
                _rec(capability="mutate", approval={"expires": "1w"}),
                "S303",
                "approval/expires",
            ),
            (
                _rec(capability="mutate", approval={"expires": "P"}),
                "S303",
                "approval/expires",
            ),
            (
                _rec(capability="mutate", approval={"expires": "PT"}),
                "S303",
                "approval/expires",
            ),
            (
                _rec(capability="mutate", approval={"expires": "0s"}),
                "S303",
                "approval/expires",
            ),
            (_rec(capability="send", destination="to"), "S303", "destination"),
            (_rec(capability="send", destination="/a~2"), "S303", "destination"),
        ],
    )
    def test_malformed_records_are_not_loaded(
        self, record: dict[str, Any], code: str, field: str
    ) -> None:
        binding, errors = parse_record(record)
        assert binding is None
        assert (code, field) in [(e.code_str, e.location["field"]) for e in errors]

    def test_not_an_object(self) -> None:
        binding, errors = parse_record(["tool"])
        assert binding is None
        assert _codes(errors) == ["S303"]
        assert errors[0].location == {"tool": "", "field": ""}

    def test_control_record_has_no_capability(self) -> None:
        binding, errors = parse_record(
            {"tool": "done", "ontology": "2.2.0", "control": True}
        )
        assert errors == []
        assert binding is not None and binding.control and binding.capabilities == ()


class TestLoadBindings:
    def test_effective_flags_and_prerequisites(
        self, registry: CapabilityRegistry
    ) -> None:
        loaded, diagnostics = _load(
            registry,
            [_rec(tool="apply", capability="plan", additional_capabilities=["mutate"])],
        )
        assert diagnostics == []
        apply = loaded["apply"]
        assert apply.capabilities == ("plan", "mutate")
        assert (
            apply.risk,
            apply.mutation,
            apply.requires_checkpoint,
            apply.requires_approval,
        ) == (
            "high",
            True,
            True,
            True,
        )
        assert apply.prerequisites == frozenset({"checkpoint"})

    def test_a_composite_takes_its_invokes_flags_not_their_prerequisites(
        self, registry: CapabilityRegistry
    ) -> None:
        loaded, diagnostics = _load(
            registry,
            [
                _rec(tool="fix", capability="invoke", invokes=["undo"]),
                _rec(tool="undo", capability="rollback"),
            ],
        )
        assert diagnostics == []
        assert loaded["fix"].risk == "medium"
        assert loaded["fix"].mutation is True
        assert loaded["fix"].prerequisites == frozenset()
        assert loaded["undo"].prerequisites == frozenset({"checkpoint"})

    def test_a_record_citing_an_unsupported_standard_is_v109(
        self, registry: CapabilityRegistry
    ) -> None:
        loaded, diagnostics = _load(
            registry, [_rec(capability="mutate", standard="1.9")]
        )
        assert loaded == {}
        assert _codes(diagnostics) == ["V109"]
        assert diagnostics[0].location == {"tool": "t", "field": "standard"}

    def test_a_malformed_duplicate_counts(self, registry: CapabilityRegistry) -> None:
        """A record that cannot be read could declare something stricter, so
        a second record for its tool does not load either."""
        loaded, diagnostics = _load(
            registry,
            [_rec(capability="observe"), {"tool": "t", "capability": "mutate"}],
        )
        assert loaded == {}
        assert _codes(diagnostics) == ["S304", "V110"]

    def test_invokes_resolve_among_known_mappings(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        mapper.register_mcp_tool("mcp__s__write", capability_id="mutate")
        batch = mapper.register_binding(
            {
                "tool": "mcp__s__batch",
                "ontology": mapper.ontology_version,
                "capability": "invoke",
                "invokes": ["mcp__s__write"],
            }
        )
        assert batch.requires_checkpoint and batch.requires_approval
        assert batch.invokes == ("mcp__s__write",)

    def test_a_record_that_does_not_load_leaves_its_tool_unbound(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        mapper.register_mcp_tool("mcp__s__write", capability_id="observe")
        diagnostics = mapper.load_bindings(
            [{"tool": "mcp__s__write", "ontology": "2.2.0", "capability": "nope"}]
        )
        assert _codes(diagnostics) == ["V101"]
        assert mapper.map_tool("mcp__s__write", {}) is UNCLASSIFIED_TOOL
        assert [d.code_str for d in mapper.diagnostics] == ["V101"]


class TestCheckOffered:
    def test_an_offered_tool_under_another_binding_is_not_bound(
        self, registry: CapabilityRegistry
    ) -> None:
        loaded, _ = _load(registry, [_rec(tool="save", capability="checkpoint")])
        diagnostics = check_offered({"save2": "save", "save": "save"}, loaded)
        assert [(d.code_str, d.location["tool"]) for d in diagnostics] == [
            ("V111", "save2")
        ]

    def test_an_offered_tool_missing_from_the_mappings_is_w617(
        self, registry: CapabilityRegistry
    ) -> None:
        diagnostics = check_offered({"write": "write"}, {})
        assert [(d.code_str, d.location["tool"]) for d in diagnostics] == [
            ("W617", "write")
        ]

    def test_v102_names_the_prerequisite(self, registry: CapabilityRegistry) -> None:
        loaded, _ = _load(registry, [_rec(tool="undo", capability="rollback")])
        (diagnostic,) = check_offered({"undo": "undo"}, loaded)
        assert diagnostic.code_str == "V102"
        assert diagnostic.location == {
            "tool": "undo",
            "capability": "rollback",
            "prerequisite": "checkpoint",
        }

    def test_f506_names_the_action(self, registry: CapabilityRegistry) -> None:
        loaded, _ = _load(registry, [_rec(tool="ask", capability="execute")])
        (diagnostic,) = check_offered({"ask": "ask"}, loaded, [("stop", "ask")])
        assert diagnostic.code_str == "F506"
        assert diagnostic.location == {"tool": "ask", "action": "stop"}


class TestMapperRegistration:
    def test_no_capability_is_unbound_and_w617(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        mapping = mapper.register_mcp_tool("mcp__x__y")
        assert mapping is UNCLASSIFIED_TOOL
        assert mapper.map_tool("mcp__x__y", {}) is UNCLASSIFIED_TOOL
        assert [(w.code_str, w.location["tool"]) for w in mapper.warnings] == [
            ("W617", "mcp__x__y")
        ]

    def test_control_registration(self, mapper: ToolCapabilityMapper) -> None:
        mapping = mapper.register_mcp_tool("mcp__x__done", control=True)
        assert mapping.control
        assert mapping.capabilities == ()
        assert not (mapping.requires_checkpoint or mapping.requires_approval)

    @pytest.mark.parametrize(
        ("kwargs", "code"),
        [
            ({"capability_id": "mutate", "risk": "extreme"}, "S303"),
            ({"capability_id": "invoke", "invokes": ["mcp__x__missing"]}, "V107"),
            ({"capability_id": "nope"}, "V101"),
        ],
    )
    def test_errors_raise_and_register_nothing(
        self, mapper: ToolCapabilityMapper, kwargs: dict[str, Any], code: str
    ) -> None:
        with pytest.raises(ValueError, match=f"^{code} "):
            mapper.register_mcp_tool("mcp__x__y", **kwargs)
        assert mapper.map_tool("mcp__x__y", {}) is UNCLASSIFIED_TOOL

    def test_mapping_capabilities_default_to_the_capability(self) -> None:
        mapping = ToolMapping("observe", "low", False, False, False)
        assert mapping.capabilities == ("observe",)

    @pytest.mark.parametrize("skill", ["checkpoint", "rollback", "anything"])
    def test_skill_is_invoke_whatever_the_skill(
        self, mapper: ToolCapabilityMapper, skill: str
    ) -> None:
        mapping = mapper.map_tool("Skill", {"skill": skill})
        assert mapping.capability_id == "invoke"
        assert mapping.capabilities == ("invoke",)
        assert not mapping.requires_checkpoint

    def test_static_mutate_carries_its_prerequisite(
        self, mapper: ToolCapabilityMapper
    ) -> None:
        assert mapper.map_tool("Write", {}).prerequisites == frozenset({"checkpoint"})
        assert mapper.map_tool("Read", {}).prerequisites == frozenset()


class TestMetadataCarrier:
    """Tool metadata is a carrier of the tool binding record."""

    def test_record_form(self) -> None:
        record = _record(
            "mcp__s__t",
            "s",
            "2.2.0",
            {"capability": "send", "flags": {"risk": "high"}, "x-owner": "ops"},
        )
        assert record == {
            "tool": "mcp__s__t",
            "ontology": "2.2.0",
            "capability": "send",
            "flags": {"risk": "high"},
            "x-owner": "ops",
        }

    def test_legacy_keys(self) -> None:
        record = _record(
            "mcp__s__t", "s", "2.2.0", {"capability_id": "execute", "risk": "high"}
        )
        assert record == {
            "tool": "mcp__s__t",
            "ontology": "2.2.0",
            "capability": "execute",
            "flags": {"risk": "high", "mutation": True, "requires_checkpoint": True},
        }

    def test_conflicting_capability_is_s303(self) -> None:
        with pytest.raises(ValueError, match="^S303 "):
            _record(
                "mcp__s__t",
                "s",
                "2.2.0",
                {"capability": "send", "capability_id": "mutate"},
            )

    def test_no_capability_is_unbound(self) -> None:
        assert _record("mcp__s__t", "s", "2.2.0", {}) is None
        assert _record("mcp__s__t", "s", "2.2.0", {"control": True}) == {
            "tool": "mcp__s__t",
            "ontology": "2.2.0",
            "control": True,
        }


class TestRecordedBy:
    def test_the_digest_follows_the_bindings(
        self, adapter: GroundedAgentAdapter
    ) -> None:
        before = adapter.recorded_by
        assert before["name"] == "grounded_agency.adapter"
        assert len(before["config_sha256"]) == 64
        adapter.mapper.register_mcp_tool("mcp__s__t", capability_id="observe")
        assert adapter.recorded_by["config_sha256"] != before["config_sha256"]
