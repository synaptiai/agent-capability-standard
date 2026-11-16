"""Agent manifests (STANDARD v1.2 §5.15.1, §5.15.2): the schema, the maxima
vectors, the SDK's descriptor and delegation protocol, and the engine's
manifests, libraries and raised flags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.capabilities.registry import CapabilityRegistry
from grounded_agency.coordination.delegation import DelegationProtocol
from grounded_agency.coordination.manifest import (
    check_agent_manifest,
    check_task,
    join_maxima,
    load_agent_manifest,
    manifest_maxima,
)
from grounded_agency.coordination.registry import AgentDescriptor, AgentRegistry
from grounded_agency.workflows.engine import UnboundedDelegation, WorkflowEngine

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
FIXTURES = ROOT / "tests" / "fixtures"
VECTORS = json.loads(
    (ROOT / "tests" / "conformance" / "agents" / "maxima.json").read_text()
)


@pytest.fixture(scope="module")
def registry() -> CapabilityRegistry:
    return CapabilityRegistry(ONTOLOGY)


def _manifest(agent: str, caps: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "agent": agent,
        "standard": "1.2",
        "ontology": "2.2",
        "capabilities": caps,
        **extra,
    }


def test_fixture_manifests_conform_to_the_schema() -> None:
    import jsonschema
    import yaml

    doc = yaml.safe_load((ROOT / "schemas" / "agent_manifest_schema.yaml").read_text())
    schema = {**doc, "$ref": "#/agent_manifest"}
    for path in sorted((FIXTURES / "agents").glob("*.agent.yaml")):
        jsonschema.validate(yaml.safe_load(path.read_text()), schema)
    for missing in ("standard", "ontology"):
        bad = _manifest("a", [])
        del bad[missing]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_maxima_vectors(registry: CapabilityRegistry, case: dict[str, Any]) -> None:
    got = manifest_maxima(
        {"capabilities": case["capabilities"]}, registry, case["read_only"]
    )
    assert got == case["maxima"]


@pytest.mark.parametrize("case", VECTORS["joins"], ids=lambda c: c["name"])
def test_join_vectors(registry: CapabilityRegistry, case: dict[str, Any]) -> None:
    each = [
        manifest_maxima({"capabilities": caps}, registry, case["read_only"])
        for caps in case["manifests"]
    ]
    assert join_maxima(*each) == case["maxima"]


def test_check_refuses_what_the_core_refuses(registry: CapabilityRegistry) -> None:
    check_agent_manifest(_manifest("a", ["retrieve", "divine"]), registry)
    for bad, why in [
        ({"standard": "1.2"}, "non-empty"),
        ({"agent": "a", "ontology": "2.2", "capabilities": []}, "standard"),
        (_manifest("a", [], ontology="3.0"), "V109"),
        (_manifest("a", [], standard="1.9"), "V109"),
        (_manifest("a", ["x", "x"]), "twice"),
        (_manifest("a", [], flags={}), "unknown member"),
        (_manifest("a", [], task=[]), "'task'"),
        (_manifest("a", [], task={"t": 1}), "task input 't': must be a mapping"),
    ]:
        with pytest.raises(ValueError, match=why):
            check_agent_manifest(bad, registry)


BAD_TASK_INPUTS = [
    ({"type": 42}, "'type'"),
    ({"type": []}, "'type'"),
    ({"type": "string", "required": "yes"}, "'required' must be a boolean"),
    ({"description": 1}, "'description'"),
    ({"properties": []}, "'properties'"),
    ({"ref": True}, "'ref'"),
]


@pytest.mark.parametrize(("spec", "why"), BAD_TASK_INPUTS)
def test_task_inputs_are_typed(
    registry: CapabilityRegistry, spec: dict[str, Any], why: str
) -> None:
    """A task input breaking ``agent_task_input`` refuses the manifest, in
    the SDK and in the core alike (§5.15.1): ``required: "yes"`` must not
    make a required input optional."""
    from grounded_agency import _core

    bad = _manifest("db-writer", ["retrieve"], task={"table": spec})
    with pytest.raises(ValueError, match=f"task input 'table': {why}"):
        check_agent_manifest(bad, registry)
    with pytest.raises(ValueError, match=f"task input 'table': {why}"):
        AgentRegistry(registry).register_manifest(bad)
    catalog = {
        "w": {
            "goal": "g",
            "risk": "low",
            "spec_version": "1.2",
            "agents": ["db-writer"],
            "steps": [
                {
                    "capability": "delegate",
                    "purpose": "p",
                    "store_as": "d",
                    "input_bindings": {"agent": "db-writer", "task": {}},
                }
            ],
        }
    }
    validator = _core.Validator(ONTOLOGY, ROOT)
    with pytest.raises(ValueError, match=f"task input 'table': {why}"):
        validator.validate(catalog, agents=[bad])
    # Well typed, the required input is enforced (S304).
    good = _manifest(
        "db-writer", ["retrieve"], task={"table": {"type": "string", "required": True}}
    )
    check_agent_manifest(good, registry)
    codes = {
        d["code"] for d in validator.validate(catalog, agents=[good])["diagnostics"]
    }
    assert "S304" in codes


def test_descriptor_round_trips_a_manifest(registry: CapabilityRegistry) -> None:
    m = load_agent_manifest(FIXTURES / "agents" / "db_writer.agent.yaml")
    d = AgentDescriptor.from_manifest(m, registry)
    assert d.agent_id == "db-writer"
    assert d.manifest(registry) == {
        "agent": "db-writer",
        "standard": "1.2",
        "ontology": "2.2",
        "capabilities": ["checkpoint", "mutate", "retrieve"],
        "task": {
            "table": {"type": "string", "required": True},
            "rows": {"type": "array"},
        },
    }
    assert d.maxima(registry)["requires_approval"] is True
    assert d.maxima(registry, read_only=True)["requires_approval"] is False
    with pytest.raises(ValueError, match="Unknown capabilities"):
        AgentDescriptor.from_manifest(_manifest("o", ["divine"]), registry)


def test_delegation_refuses_a_task_that_does_not_fit(
    registry: CapabilityRegistry,
) -> None:
    agents = AgentRegistry(registry)
    agents.register_manifest(
        load_agent_manifest(FIXTURES / "agents" / "db_writer.agent.yaml")
    )
    from grounded_agency.coordination.audit import CoordinationAuditLog
    from grounded_agency.state.evidence_store import EvidenceStore

    protocol = DelegationProtocol(agents, EvidenceStore(), CoordinationAuditLog())
    ok = protocol.delegate("update", ["retrieve"], "db-writer", {"table": "t"})
    assert ok.accepted
    for task, why in [
        ({"rows": []}, "missing ['table']"),
        ({"table": "t", "colour": 1}, "undeclared ['colour']"),
    ]:
        refused = protocol.delegate("update", ["retrieve"], "db-writer", task)
        assert not refused.accepted and why in (refused.rejection_reason or "")
    assert check_task({}, {"anything": 1}) == ([], [])


def _engine_with(catalog: str) -> WorkflowEngine:
    engine = WorkflowEngine(ONTOLOGY)
    engine.load_catalog(FIXTURES / f"{catalog}.workflow_catalog.yaml")
    return engine


def test_engine_reads_manifests_libraries_and_raises_flags() -> None:
    engine = _engine_with("fail_agents_flags_raised")
    codes = {d.code.value for d in engine.validate_report()}
    assert codes == {"W621"}
    workflow = engine.get_workflow("write")
    assert workflow is not None and workflow.agents == ["db-writer"]
    step = workflow.steps[0]
    with pytest.raises(UnboundedDelegation):
        engine.effective_flags(step, workflow)
    assert engine.load_agents(FIXTURES / "agents") == 3
    codes = {d.code.value for d in engine.validate_report()}
    assert codes == {"F501"}
    assert engine.effective_flags(step, workflow)["requires_checkpoint"] is True
    # Without the workflow, the ontology's flags (the 1.1 view).
    assert engine.effective_flags(step)["requires_checkpoint"] is False
    with pytest.raises(ValueError, match="two agent manifests"):
        engine.add_agent_manifest(
            load_agent_manifest(FIXTURES / "agents" / "oracle.agent.yaml")
        )


def test_engine_libraries_and_the_manifest() -> None:
    engine = _engine_with("pass_qualified_invoke")
    assert {d.code.value for d in engine.validate_report()} == {"W607"}
    assert engine.load_library(FIXTURES / "catalogs" / "lib.workflow_catalog.yaml") == (
        "acs.fixtures.lib"
    )
    assert engine.validate_report() == []
    with pytest.raises(ValueError, match="already loaded"):
        engine.load_library(FIXTURES / "catalogs" / "lib.workflow_catalog.yaml")
    with pytest.raises(ValueError, match="manifest 'id'"):
        engine.load_library(FIXTURES / "pass_minimal_single_step.workflow_catalog.yaml")
    manifest = _engine_with("pass_catalog_manifest")
    assert manifest.list_workflows() == ["w"]
    assert manifest.catalog_data()["catalog"]["id"] == "acs.fixtures.solo"
    assert manifest.validate_report() == []
    assert "spec_version" not in manifest.catalog_data()["catalog"]


def test_library_diagnostics_are_not_a_same_named_primary_workflows(
    tmp_path: Path,
) -> None:
    """A library's diagnostics carry its ``catalog`` id (§9.8): the engine
    never reports them as those of the primary workflow of the same name."""
    (tmp_path / "main.yaml").write_text(
        "# Standard version: 1.2.0\n"
        "catalog: {id: acme.main, version: 1.0.0}\n"
        "inner:\n"
        "  goal: g\n"
        "  risk: low\n"
        "  steps:\n"
        "  - {capability: retrieve, purpose: p, store_as: r,"
        " input_bindings: {target: t}}\n"
    )
    (tmp_path / "lib.yaml").write_text(
        "# Standard version: 1.2.0\n"
        "catalog: {id: acme.lib, version: 1.0.0, exports: [inner]}\n"
        "inner:\n"
        "  goal: g\n"
        "  risk: low\n"
        "  steps:\n"
        "  - {capability: divine, purpose: p, store_as: r}\n"
    )
    engine = WorkflowEngine(ONTOLOGY)
    engine.load_catalog(tmp_path / "main.yaml")
    assert engine.validate_capabilities("inner") == []
    engine.load_library(tmp_path / "lib.yaml")
    report = engine.validate_report()
    assert [(d.code.value, d.location.get("catalog")) for d in report] == [
        ("V101", "acme.lib")
    ]
    assert engine.validate_report("inner") == []
    assert engine.validate_capabilities("inner") == []
    assert engine.validate_bindings("inner") == []
    assert engine.validate_edge_constraints("inner") == []
    assert list(engine.validate_all()) == ["acme.lib/inner"]
    assert [
        d.code.value for d in engine.validate_all_structured()["acme.lib/inner"]
    ] == ["V101"]


def test_runner_runs_with_the_engines_libraries_and_manifests() -> None:
    from grounded_agency.workflows.runner import WorkflowRunner

    engine = _engine_with("pass_qualified_invoke")
    engine.load_library(FIXTURES / "catalogs" / "lib.workflow_catalog.yaml")
    runner = WorkflowRunner(engine)
    run = runner.start("check", now_ms=0)
    action = run.next()
    assert action["kind"] == "InvokeCapability"
    assert action["frame"] == [
        "check",
        "acs.fixtures.lib/shared_check",
        "acs.fixtures.lib/inner",
    ]
    # A snapshot restores against the same set.
    assert runner.restore(run.snapshot(b"k"), b"k").next() == action

    managed = _engine_with("fail_agents_flags_raised")
    managed.load_agents(FIXTURES / "agents")
    with pytest.raises(Exception, match="F501"):
        WorkflowRunner(managed).start("write", now_ms=0)


def test_runner_applies_profiles_and_manifests_together() -> None:
    """A run's delegate step takes its target's maxima (§5.15.2) and the
    applied profiles (§5.21.3) alike: the maxima raise its approval, and a
    profile that blocks autonomous delegation asks that approval of a
    person."""
    from grounded_agency.workflows.runner import WorkflowRunner

    engine = _engine_with("pass_agents_approval_block")
    engine.load_agents(FIXTURES / "agents")
    person = {
        "domain": "person-delegate",
        "version": "1.0.0",
        "risk_thresholds": {"block_autonomous": ["delegate"]},
    }
    for profiles, expect_person in (((), False), ((person,), True)):
        run = WorkflowRunner(engine, profiles=profiles).start("write", now_ms=0)
        checkpoint = run.next()
        assert checkpoint["capability"] == "checkpoint"
        run.submit(
            checkpoint["id"],
            {
                "kind": "Output",
                "value": {"checkpoint_id": "c1", "evidence_anchors": []},
            },
            0,
        )
        approval = run.next()
        assert approval["kind"] == "RequestApproval"
        assert approval["step"] == 1
        assert approval["approver"].get("always_ask", False) is expect_person
