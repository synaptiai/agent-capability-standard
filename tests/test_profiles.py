"""Domain profiles (STANDARD v1.2 §5.21) through the Python package: the
normative vectors through ``_core``, ``AppliedProfiles``, the shipped
profiles, the domain catalogs under their own profiles, the adapter, the
runner, and what the runtime fixtures cannot state (absent members)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import (
    AppliedProfiles,
    GroundedAgentAdapter,
    GroundedAgentConfig,
    ProfileError,
    _core,
    check_offered,
)
from grounded_agency.grounding import GroundingPolicy
from grounded_agency.workflows import WorkflowEngine, WorkflowRunner
from tests.runtime_replay import load, play, start
from tests.test_runner import Clock, FakeHost

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
VECTORS = ROOT / "tests" / "conformance" / "profiles"
LOAD = json.loads((VECTORS / "load.json").read_text("utf-8"))
EFFECTIVE = json.loads((VECTORS / "effective.json").read_text("utf-8"))
SHIPPED = sorted(
    p
    for p in (ROOT / "schemas" / "profiles").glob("*.yaml")
    if p.stem != "profile_schema"
)
RUNTIME = ROOT / "tests" / "conformance" / "runtime"


@pytest.fixture(scope="module")
def validator() -> _core.Validator:
    return _core.Validator(str(ONTOLOGY), str(ROOT))


def found(report: dict[str, Any], severity: str) -> set[tuple[str, str, str]]:
    return {
        (d["code"], d["location"]["profile"], d["location"]["field"])
        for d in report["diagnostics"]
        if d["severity"] == severity
    }


def expected(items: list[dict[str, str]]) -> set[tuple[str, str, str]]:
    return {(d["code"], d["profile"], d["field"]) for d in items}


@pytest.mark.parametrize("vector", LOAD["vectors"], ids=lambda v: v["name"])
def test_load_vector(validator: _core.Validator, vector: dict[str, Any]) -> None:
    report = validator.check_profiles(vector["profiles"])
    assert found(report, "error") == expected(vector["expect"]["errors"])
    assert found(report, "warning") == expected(vector["expect"]["warnings"])
    assert all("workflow" not in d["location"] for d in report["diagnostics"])


@pytest.mark.parametrize("vector", EFFECTIVE["flags"], ids=lambda v: v["name"])
def test_flags_vector(validator: _core.Validator, vector: dict[str, Any]) -> None:
    got = validator.profile_flags(
        vector["profiles"], vector["capability"], vector.get("declared")
    )
    got.pop("warnings")
    assert got == vector["expect"]
    flags = AppliedProfiles(vector["profiles"], validator=validator).flags(
        vector["capability"], vector.get("declared")
    )
    assert {
        "risk": flags.risk,
        "mutation": flags.mutation,
        "requires_checkpoint": flags.requires_checkpoint,
        "requires_approval": flags.requires_approval,
        "person": flags.person,
    } == vector["expect"]


@pytest.mark.parametrize("vector", EFFECTIVE["calls"], ids=lambda v: v["name"])
def test_call_vector(
    ontology_path: str, tmp_path: Path, vector: dict[str, Any]
) -> None:
    """The adapter's layer raises each applied profile's flags for every
    capability a call performs, at the call's effective risk (§5.21.3,
    §5.18.3): a binding's `additional_capabilities` do not escape a
    profile."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=vector["profiles"],
        )
    )
    mapper = adapter.mapper
    mapper.register_binding(
        {
            "tool": "mcp__srv__tool",
            "ontology": mapper.ontology_version,
            **vector["binding"],
        }
    )
    mapping = mapper.map_tool("mcp__srv__tool", {})
    assert {
        "risk": mapping.risk,
        "mutation": mapping.mutation,
        "requires_checkpoint": mapping.requires_checkpoint,
        "requires_approval": mapping.requires_approval,
        "person": mapper.person_required(mapping),
    } == vector["expect"]


@pytest.mark.parametrize("vector", EFFECTIVE["policy"], ids=lambda v: v["name"])
def test_policy_vector(validator: _core.Validator, vector: dict[str, Any]) -> None:
    assert validator.profile_policy(vector["profiles"]) == vector["expect"]
    applied = AppliedProfiles(vector["profiles"], validator=validator)
    assert applied.minimum_confidence == vector["expect"]["minimum_confidence"]
    assert applied.grounding == vector["expect"]["grounding"]
    assert applied.destinations == vector["expect"]["destinations"]
    assert applied.trust_weights == vector["expect"]["trust_weights"]


def test_the_vector_files_are_normative() -> None:
    for doc in (LOAD, EFFECTIVE):
        assert (doc["standard"], doc["status"]) == ("1.2.0", "normative")


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.stem)
def test_every_shipped_profile_applies_cleanly(path: Path) -> None:
    applied = AppliedProfiles([path])
    assert applied.warnings == []
    assert applied.documents[0]["version"] == "2.0.0"


def test_an_invalid_profile_is_refused(validator: _core.Validator) -> None:
    path = ROOT / "tests" / "fixtures" / "profiles" / "invalid.profile.yaml"
    with pytest.raises(ProfileError) as caught:
        AppliedProfiles([path], validator=validator)
    codes = {d["code"] for d in caught.value.diagnostics}
    assert codes == {"S303", "V101"}
    # And the core refuses it when it is given to a run or a validation.
    with pytest.raises(ValueError):
        validator.profile_policy([_core.load_yaml(str(path))])


def test_a_non_finite_weight_cannot_reach_the_core(validator: _core.Validator) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        AppliedProfiles(
            [{"domain": "d", "version": "1.0.0", "trust_weights": {"a": float("nan")}}],
            validator=validator,
        )


def test_every_domain_catalog_validates_strictly_under_its_own_profile(
    validator: _core.Validator,
) -> None:
    """The catalog's `profile` field names its profile; applied, it adds no
    diagnostic (Standard v1.2 §5.21, part 3.7 of the migration)."""
    catalogs = sorted((ROOT / "schemas" / "workflows").glob("*.yaml"))
    assert catalogs
    for path in catalogs:
        catalog = _core.load_yaml(str(path))
        named = {wf.get("profile") for wf in catalog.values() if isinstance(wf, dict)}
        assert len(named) == 1, path
        profile = _core.load_yaml(str(ROOT / named.pop()))
        report = validator.validate_file(path, profiles=[profile])
        assert report["diagnostics"] == [], (path.name, report["diagnostics"])


@pytest.mark.asyncio
async def test_the_adapter_asks_a_person_for_every_call_under_healthcare(
    ontology_path: str, tmp_path: Path
) -> None:
    """Healthcare's thresholds cover every risk level with require_human:
    even a Read needs a person's approval, and its record says why."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[ROOT / "schemas" / "profiles" / "healthcare.yaml"],
        )
    )
    mapping = adapter.mapper.map_tool("Read", {"file_path": "a"})
    assert (mapping.requires_approval, mapping.person_required) == (True, True)
    hook = adapter._make_pretooluse_safety_hook()
    call = {
        "tool_name": "Read",
        "tool_input": {"file_path": "a"},
        "permission_mode": "default",
    }
    result = await hook(call, "r1", None)
    assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
    record = adapter.call_records[-1]
    assert (record["decision"], record["person_required"]) == ("asked", True)


@pytest.mark.asyncio
async def test_the_ask_reason_says_a_person_must_decide(
    ontology_path: str, tmp_path: Path
) -> None:
    """The reason is all a host's can_use_tool callback sees: under a
    profile that requires a person it says so (§5.21.3); otherwise it does
    not."""
    hook_input = {
        "tool_name": "Write",
        "tool_input": {"file_path": "a", "content": "x"},
        "permission_mode": "default",
    }

    async def reason(profiles: list[dict[str, Any]]) -> str:
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                profiles=profiles,
            )
        )
        adapter.create_checkpoint(["a"], "before")
        result = await adapter._make_pretooluse_safety_hook()(hook_input, "w1", None)
        output = result["hookSpecificOutput"]
        assert output["permissionDecision"] == "ask"
        return str(output["permissionDecisionReason"])

    person = await reason(
        [
            {
                "domain": "d",
                "version": "1.0.0",
                "risk_thresholds": {"block_autonomous": ["mutate"]},
            }
        ]
    )
    assert person.startswith("F502 ")
    assert "requires approval by a person" in person
    assert "§5.21.3" in person
    plain = await reason([{"domain": "d", "version": "1.0.0"}])
    assert "by a person" not in plain
    assert "requires approval" in plain


@pytest.mark.asyncio
async def test_an_unbound_tool_records_person_required_under_a_mutate_rule(
    ontology_path: str, tmp_path: Path
) -> None:
    """An unbound tool is treated as mutate (§5.18.2): a profile that
    requires a person for mutate puts person_required on its record and in
    its ask reason, though its mapping keeps its identity."""
    from grounded_agency.capabilities.mapper import UNCLASSIFIED_TOOL

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[
                {
                    "domain": "d",
                    "version": "1.0.0",
                    "risk_thresholds": {"block_autonomous": ["mutate"]},
                }
            ],
        )
    )
    mapping = adapter.mapper.map_tool("SomeUnknownTool", {})
    assert mapping is UNCLASSIFIED_TOOL
    assert adapter.mapper.person_required(mapping) is True
    adapter.create_checkpoint(["a"], "before")
    result = await adapter._make_pretooluse_safety_hook()(
        {
            "tool_name": "SomeUnknownTool",
            "tool_input": {},
            "permission_mode": "default",
        },
        "u1",
        None,
    )
    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "ask"
    assert "by a person" in output["permissionDecisionReason"]
    record = adapter.call_records[-1]
    assert (record["decision"], record["capability"], record["person_required"]) == (
        "asked",
        None,
        True,
    )
    # Exported, it is the ActionRecord member (world_state_schema.yaml), not
    # a detail.
    exported = adapter.export_action_records("scope")[-1]
    assert exported["action_id"] == f"scope/{record['seq']}"
    assert exported["person_required"] is True
    assert "person_required" not in exported.get("details", {})
    # Without a rule that covers mutate, the unbound tool's record has none.
    plain = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp2"),
            profiles=[{"domain": "d", "version": "1.0.0"}],
        )
    )
    assert plain.mapper.person_required(UNCLASSIFIED_TOOL) is False


def _profiled_adapter(
    ontology_path: str, tmp_path: Path, profile: dict[str, Any]
) -> GroundedAgentAdapter:
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[{"domain": "d", "version": "1.0.0", **profile}],
        )
    )


@pytest.mark.asyncio
async def test_a_composite_is_asked_of_a_person_for_a_binding_it_invokes(
    ontology_path: str, tmp_path: Path
) -> None:
    """A composite's approval covers its nested calls (§5.18.4), which this
    layer does not see: a composite that lists a binding a profile requires
    a person for, directly or through another composite, is itself asked of
    a person (§5.21.3), its ask reason says so and its records carry
    person_required, whatever its own capability."""
    adapter = _profiled_adapter(
        ontology_path, tmp_path, {"risk_thresholds": {"block_autonomous": ["mutate"]}}
    )
    mapper = adapter.mapper
    mapper.register_mcp_tool("mcp__srv__write", "mutate")
    mapper.register_mcp_tool("mcp__srv__batch", "plan", invokes=["mcp__srv__write"])
    mapper.register_mcp_tool("mcp__srv__outer", "plan", invokes=["mcp__srv__batch"])
    mapper.register_mcp_tool("mcp__srv__alone", "plan")
    person = {
        name: mapper.person_required(mapper.map_tool(f"mcp__srv__{name}", {}))
        for name in ("write", "batch", "outer", "alone")
    }
    assert person == {"write": True, "batch": True, "outer": True, "alone": False}

    pre = adapter._make_pretooluse_safety_hook()
    for name in ("batch", "outer"):
        adapter.create_checkpoint(["a"], "before")
        result = await pre(
            {
                "tool_name": f"mcp__srv__{name}",
                "tool_input": {},
                "permission_mode": "default",
            },
            f"c-{name}",
            None,
        )
        output = result["hookSpecificOutput"]
        assert output["permissionDecision"] == "ask"
        assert "requires approval by a person" in output["permissionDecisionReason"]
        assert "a binding it invokes" in output["permissionDecisionReason"]
        record = adapter.call_records[-1]
        assert (
            record["decision"],
            record["capability"],
            record["person_required"],
        ) == (
            "asked",
            "plan",
            True,
        )


def test_a_composite_takes_the_raised_flags_of_the_bindings_it_invokes(
    ontology_path: str, tmp_path: Path
) -> None:
    """The flags a profile raises for an invoked binding are effective flags
    (§5.21.3), and a composite's effective flags include those of each
    binding it lists, transitively (§5.18.4): a composite of a low-risk
    read needs the checkpoint and the approval the profile raised for it."""
    adapter = _profiled_adapter(
        ontology_path,
        tmp_path,
        {
            "checkpoint_policy": {"retrieve": "always"},
            "risk_thresholds": {"block_autonomous": ["retrieve"]},
        },
    )
    mapper = adapter.mapper
    mapper.register_mcp_tool("mcp__srv__fetch", "retrieve")
    mapper.register_mcp_tool(
        "mcp__srv__summarize", "explain", invokes=["mcp__srv__fetch"]
    )
    mapper.register_mcp_tool(
        "mcp__srv__report", "explain", invokes=["mcp__srv__summarize"]
    )
    mapper.register_mcp_tool("mcp__srv__alone", "explain")
    for name in ("fetch", "summarize", "report"):
        mapping = mapper.map_tool(f"mcp__srv__{name}", {})
        assert (
            mapping.risk,
            mapping.requires_checkpoint,
            mapping.requires_approval,
            mapper.person_required(mapping),
        ) == ("low", True, True, True), name
    alone = mapper.map_tool("mcp__srv__alone", {})
    assert (alone.requires_checkpoint, alone.requires_approval) == (False, False)


def test_a_composite_reads_the_bindings_it_invokes_as_registered_now(
    ontology_path: str, tmp_path: Path
) -> None:
    """A binding registered again changes what a composite that invokes it
    takes from it: the composite mapped before is not served from a cache."""
    adapter = _profiled_adapter(
        ontology_path, tmp_path, {"risk_thresholds": {"block_autonomous": ["mutate"]}}
    )
    mapper = adapter.mapper
    mapper.register_mcp_tool("mcp__srv__write", "retrieve")
    mapper.register_mcp_tool("mcp__srv__batch", "plan", invokes=["mcp__srv__write"])
    assert mapper.person_required(mapper.map_tool("mcp__srv__batch", {})) is False
    mapper.register_mcp_tool("mcp__srv__write", "mutate")
    assert mapper.person_required(mapper.map_tool("mcp__srv__batch", {})) is True


@pytest.mark.asyncio
async def test_a_failed_call_keeps_its_person_required(
    ontology_path: str, tmp_path: Path
) -> None:
    """Every record of a call a profile requires a person for carries
    person_required (§5.21.3), the failed one written by PostToolUseFailure
    included, and its exported ActionRecord too."""
    adapter = _profiled_adapter(
        ontology_path, tmp_path, {"risk_thresholds": {"block_autonomous": ["mutate"]}}
    )
    adapter.create_checkpoint(["a"], "before")
    call = {
        "tool_name": "Write",
        "tool_input": {"file_path": "a", "content": "x"},
        "permission_mode": "default",
    }
    await adapter._make_pretooluse_safety_hook()(call, "c1", None)
    await adapter._make_failure_recorder()(
        {**call, "tool_use_id": "c1", "error": "the tool failed"}, "c1", None
    )
    asked, failed = list(adapter.call_records)[-2:]
    assert (asked["decision"], asked["person_required"]) == ("asked", True)
    assert (failed["decision"], failed["capability"], failed["person_required"]) == (
        "failed",
        "mutate",
        True,
    )
    exported = adapter.export_action_records("scope")[-1]
    assert (
        exported["status"],
        exported["capability"],
        exported["person_required"],
    ) == (
        "failed",
        "mutate",
        True,
    )


@pytest.mark.parametrize(
    ("policy", "refused"),
    [
        ({"*": "always"}, True),
        ({"mutate": "high_risk", "retrieve": "never"}, True),
        ({"retrieve": "never"}, False),
    ],
)
def test_strict_mode_off_refuses_a_raised_checkpoint(
    ontology_path: str, tmp_path: Path, policy: dict[str, str], refused: bool
) -> None:
    """strict_mode=False only logs a missing checkpoint, so a profile whose
    checkpoint_policy raises requires_checkpoint is refused (§5.21.4), as
    approval='off' refuses profiles; strict_mode=True applies it, and a
    policy of never alone raises nothing."""
    profile = {"domain": "d", "version": "1.0.0", "checkpoint_policy": policy}

    def adapter(strict: bool) -> GroundedAgentAdapter:
        return GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                strict_mode=strict,
                acknowledge_unenforced_checks=not strict,
                profiles=[profile],
            )
        )

    assert adapter(True).profiles
    if refused:
        with pytest.raises(ProfileError, match="strict_mode=False") as caught:
            adapter(False)
        assert "checkpoint_policy" in str(caught.value)
        assert " yet" not in str(caught.value)
    else:
        assert adapter(False).profiles


@pytest.mark.parametrize("rule", ["grounding", "minimum_confidence", "destinations"])
def test_only_the_checkpoint_rule_can_go_unapplied(rule: str) -> None:
    """Every applier applies a profile's grounding, minimum confidence and
    destinations, so refuse_unapplied knows only the checkpoint rule."""
    profiles = AppliedProfiles(
        [{"domain": "d", "version": "1.0.0", "allowed_destinations": ["mailto:*"]}]
    )
    with pytest.raises(KeyError):
        profiles.refuse_unapplied((rule,), "x")


@pytest.mark.parametrize(
    "rule",
    [{"allowed_destinations": []}, {"allowed_destinations": ["mailto:*"]}],
    ids=["none", "mailto"],
)
def test_the_adapter_applies_a_profiles_send_rule(
    ontology_path: str, tmp_path: Path, rule: dict[str, Any]
) -> None:
    """A profile's ``allowed_destinations`` is a destination policy the
    adapter puts in force for send calls (STANDARD v1.2 §5.21.3, §4.4.2);
    tests/test_adapter_effects.py checks the calls it refuses."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[{"domain": "d", "version": "1.0.0", **rule}],
        )
    )
    assert adapter._destinations == [rule["allowed_destinations"]]


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.stem)
def test_the_adapter_applies_every_shipped_profile(
    ontology_path: str, tmp_path: Path, path: Path
) -> None:
    """Every shipped profile sets require_grounding, and the adapter applies
    it as a grounding policy (§5.21.3), with the configuration's own."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[path],
        )
    )
    (expected,) = adapter.profiles.grounding
    assert [p.to_dict() for p in adapter._grounding] == [
        GroundingPolicy.from_profile(expected).to_dict()  # type: ignore[union-attr]
    ]


def test_the_adapter_applies_a_profile_grounding_policy_and_minimum_confidence(
    ontology_path: str, tmp_path: Path
) -> None:
    """A call's output (§5.20 *Hosts outside a workflow*) is checked against
    a profile's grounding policy (required_anchor_types are its kinds),
    then against the profiles' minimum confidence (F504, with its reason),
    as the executor checks a step's output; the record of a call that failed
    carries the reason, and its exported action record ``reason_code``."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[
                {
                    "domain": "d",
                    "version": "1.0.0",
                    "evidence_policy": {
                        "require_grounding": ["retrieve"],
                        "required_anchor_types": ["file"],
                        "minimum_confidence": 0.9,
                    },
                }
            ],
        )
    )
    args = {"file_path": "a.py"}
    anchor = {"ref": "file:a.py", "kind": "file"}

    def output(confidence: Any, *anchors: dict[str, Any]) -> dict[str, Any]:
        return {
            "data": "x",
            "confidence": confidence,
            "evidence_anchors": list(anchors),
        }

    # Grounding first: no anchor (and a low confidence) is F505.
    text = adapter.check_call_output("Read", args, output(0.5), call="c1")
    assert text is not None and text.startswith("F505 PROVENANCE_MISSING:")
    # A log anchor is not of the profile's kinds.
    log = {"ref": "log:app#1", "kind": "log"}
    assert adapter.check_call_output("Read", args, output(1, log)) is not None
    assert adapter.check_call_output("Read", args, output(0.95, anchor)) is None
    text = adapter.check_call_output("Read", args, output(0.5, anchor), call="c2")
    assert text is not None and text.startswith("F504 CONSTRAINT_VIOLATED:")
    assert "below the minimum confidence 0.9" in text
    text = adapter.check_call_output("Read", args, output("high", anchor), call="c3")
    assert text is not None and "not a number from 0 to 1" in text
    failed = [r for r in adapter.call_records if r.get("call") in ("c2", "c3")]
    assert [(r["decision"], r["reason"]) for r in failed] == [
        ("failed", "below_minimum_confidence"),
        ("failed", "invalid_confidence"),
    ]
    exported = adapter.export_action_records("scope")
    assert [r.get("reason_code") for r in exported if r.get("call_id") == "c2"] == [
        "below_minimum_confidence"
    ]
    # A capability the policy does not require is held to the minimum only.
    assert adapter.check_call_output("Grep", {"pattern": "x"}, output(1)) is None
    grep = adapter.check_call_output("Grep", {"pattern": "x"}, output(0.1))
    assert grep is not None and grep.startswith("F504")


def test_anchor_kinds_alone_are_applied_by_the_adapter(
    ontology_path: str, tmp_path: Path
) -> None:
    """``required_anchor_types`` without ``require_grounding`` has no
    effect (§5.21.3), so nothing is refused."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[
                {
                    "domain": "d",
                    "version": "1.0.0",
                    "evidence_policy": {"required_anchor_types": ["file"]},
                }
            ],
        )
    )
    assert adapter.profiles.grounding == []


@pytest.mark.asyncio
async def test_an_output_rule_reports_each_tool_whose_results_it_cannot_check(
    ontology_path: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Claude Code's own tools return results in their own forms, which are
    not capability outputs (§5.18.9): the adapter puts a profile's grounding
    policy and minimum confidence in force on the outputs it receives, and
    reports, once for each tool whose calls they would check, that they
    check nothing for its calls (§5.21.4); the conformance statement names
    those calls."""
    import logging

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[ROOT / "schemas" / "profiles" / "personal_assistant.yaml"],
        )
    )
    pre = adapter._make_pretooluse_safety_hook()
    task = {
        "tool_name": "Task",
        "tool_input": {"description": "d", "prompt": "p"},
        "permission_mode": "default",
    }
    with caplog.at_level(logging.WARNING, logger="grounded_agency.adapter"):
        for i in range(2):
            await pre(task, f"t{i}", None)
    reports = [r.getMessage() for r in caplog.records if "5.21.3" in r.getMessage()]
    assert len(reports) == 1, reports
    assert "Task" in reports[0]
    assert "a grounding policy requires delegate" in reports[0]
    assert "minimum confidence" in reports[0]
    statement = json.loads(
        (
            ROOT / "tests/conformance/calls/statements/grounded_agency_adapter.json"
        ).read_text("utf-8")
    )
    assert any(
        "applied profiles' grounding policies" in calls
        and "minimum confidence" in calls
        for calls in statement["calls_without_output"]
    )


def test_the_profiles_are_in_every_record_digest(
    ontology_path: str, tmp_path: Path
) -> None:
    def digest(profiles: list[dict[str, Any]]) -> str:
        return GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                profiles=profiles,
            )
        ).recorded_by["config_sha256"]

    plain = digest([])
    low = digest([{"domain": "d", "version": "1.0.0"}])
    review = digest(
        [
            {
                "domain": "d",
                "version": "1.0.0",
                "risk_thresholds": {"require_review": "low"},
            }
        ]
    )
    assert len({plain, low, review}) == 3


def test_the_adapter_without_profiles_is_unchanged(
    ontology_path: str, tmp_path: Path
) -> None:
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp")
        )
    )
    mapping = adapter.mapper.map_tool("Read", {"file_path": "a"})
    assert (mapping.requires_approval, mapping.person_required) == (False, False)


def test_check_offered_reads_the_flags_the_profiles_raise(
    ontology_path: str, tmp_path: Path
) -> None:
    """``check_offered`` checks the mappings it is given (section 5.18.2):
    those the adapter's mapper gives (``map_tool``) carry the flags the
    applied profiles raise (section 5.21.3), so a host action tied to a tool
    they make refusable is F506, as the TypeScript binding's lint reports it
    (security round 5, batch 5); a record's mapping alone states none."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            profiles=[ROOT / "schemas" / "profiles" / "healthcare.yaml"],
        )
    )
    name = "mcp__s__finish"
    record = {"tool": name, "ontology": "2.2.0", "capability": "classify"}
    assert adapter.mapper.load_bindings([record]) == []
    effective = {name: adapter.mapper.map_tool(name, {})}
    assert (effective[name].requires_approval, effective[name].person_required) == (
        True,
        True,
    )
    diagnostics = check_offered({name: name}, effective, [("stopTool", name)])
    assert [(d.code_str, d.location["tool"]) for d in diagnostics] == [("F506", name)]
    # The record's own mapping, which no profile raised, passes.
    plain = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp2")
        )
    )
    assert plain.mapper.load_bindings([record]) == []
    own = {name: plain.mapper.map_tool(name, {})}
    assert check_offered({name: name}, own, [("stopTool", name)]) == []


def test_profiles_need_approvals_on(ontology_path: str) -> None:
    with pytest.raises(ValueError, match="approval='ask'"):
        GroundedAgentConfig(
            ontology_path=ontology_path,
            approval="off",
            profiles=[{"domain": "d", "version": "1.0.0"}],
        )


def test_the_adapter_refuses_an_invalid_profile(
    ontology_path: str, tmp_path: Path
) -> None:
    with pytest.raises(ProfileError):
        GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                profiles=[
                    ROOT / "tests" / "fixtures" / "profiles" / "invalid.profile.yaml"
                ],
            )
        )


def test_the_runner_applies_its_profiles(tmp_path: Path) -> None:
    """``WorkflowRunner(profiles=...)`` gives them to every run it starts:
    the fixture profile_review_threshold, driven through a host."""
    fixture = load(RUNTIME / "profile_review_threshold.json")
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(json.dumps(fixture["catalog"]))
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    host = FakeHost(Clock())
    result = WorkflowRunner(engine, profiles=fixture["profiles"]).run("w", None, host)
    assert result.ok, result
    assert [r["status"] for r in result.action_records] == ["executed"]
    assert result.action_records[0]["approval"]["decision"] == "approved"
    # Without the profile, the retrieve asks nobody.
    plain = WorkflowRunner(engine).run("w", None, FakeHost(Clock()))
    assert plain.ok and plain.action_records == []
    with pytest.raises(ProfileError):
        WorkflowRunner(engine, profiles=[{"domain": "d"}])


def test_a_misspelled_member_is_logged_with_the_member_meant(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A misspelled top-level member is W604 and ignored (§5.21.2): it is
    not silent, the log names the member meant."""
    with caplog.at_level("WARNING", logger="grounded_agency.profiles"):
        applied = AppliedProfiles(
            [
                {
                    "domain": "d",
                    "version": "1.0.0",
                    "risk_thresholds": {"require_human": "low"},
                    "checkpoint_polcy": {"*": "always"},
                }
            ]
        )
    assert [w["code"] for w in applied.warnings] == ["W604"]
    (logged,) = [r.getMessage() for r in caplog.records]
    assert "W604" in logged and "checkpoint_polcy" in logged
    assert "did you mean 'checkpoint_policy'?" in logged


CATALOG = {
    "w": {
        "goal": "g",
        "risk": "low",
        "spec_version": "1.1",
        "steps": [
            {
                "capability": "retrieve",
                "purpose": "p",
                "store_as": "r",
                "input_bindings": {"target": "x"},
            }
        ],
    }
}


SEND_CATALOG = {
    "w": {
        "goal": "g",
        "risk": "high",
        "spec_version": "1.1",
        "steps": [
            {
                "capability": "checkpoint",
                "purpose": "p",
                "store_as": "cp",
                "input_bindings": {"scope": "*"},
            },
            {
                "capability": "send",
                "purpose": "p",
                "store_as": "s",
                "input_bindings": {"destination": "https://x.example/", "payload": "p"},
            },
        ],
    }
}


@pytest.mark.parametrize("patterns", [[], ["mailto:*"]], ids=["none", "mailto"])
def test_the_executor_applies_a_profile_destination_policy(
    validator: _core.Validator, patterns: list[str]
) -> None:
    """A profile's ``allowed_destinations`` is a destination policy in force
    (STANDARD v1.2 §5.21.3, §4.4.2): a send it does not allow fails F504
    with ``destination_not_allowed`` before anyone is asked to approve it."""
    profile = {"domain": "d", "version": "1.0.0", "allowed_destinations": patterns}
    run = _core.Run.start(
        validator,
        SEND_CATALOG,
        "w",
        {},
        header=None,
        run_id="r",
        now_ms=0,
        profiles=[profile],
    )
    action = run.next()
    run.submit(
        action["id"],
        {"kind": "Output", "value": {"checkpoint_id": "cp1", "evidence_anchors": []}},
        0,
    )
    end = run.next()
    assert (end["kind"], end["code"], end["reason"]) == (
        "Failed",
        "F504",
        "destination_not_allowed",
    )


def test_the_runner_applies_a_profile_grounding_policy(tmp_path: Path) -> None:
    """A profile's grounding policy (§5.21.3) is checked by the executor the
    runner drives, as a host's policy is (§5.20): an output with no anchor
    of the profile's kinds fails its step with F505; one with a file anchor
    completes."""
    path = tmp_path / "catalog.yaml"
    path.write_text(json.dumps(CATALOG))
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(path)
    profile = {
        "domain": "d",
        "version": "1.0.0",
        "evidence_policy": {
            "require_grounding": ["retrieve"],
            "required_anchor_types": ["file"],
        },
    }

    class Anchored(FakeHost):
        def __init__(self, anchors: list[dict[str, Any]]) -> None:
            super().__init__(Clock())
            self.anchors = anchors

        def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
            answer = super().invoke_capability(action)
            answer["value"]["evidence_anchors"] = self.anchors
            return answer

    for anchors, end in (
        ([], (None, "F505")),
        ([{"ref": "file:a.md", "kind": "file"}], ("completed", None)),
    ):
        runner = WorkflowRunner(engine, profiles=[profile])
        result = runner.run("w", None, Anchored(anchors))
        assert (result.outcome, result.code) == end, result


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.stem)
def test_every_shipped_profile_starts_a_run(
    validator: _core.Validator, path: Path
) -> None:
    """No shipped profile sets a rule the executor does not apply."""
    profile = _core.load_yaml(str(path))
    run = _core.Run.start(
        validator,
        CATALOG,
        "w",
        {},
        header=None,
        run_id="r",
        now_ms=0,
        profiles=[profile],
    )
    assert run.next()["kind"] in ("InvokeCapability", "RequestApproval")


def replay(
    validator: _core.Validator, name: str
) -> tuple[_core.Run, list[dict[str, Any]]]:
    fixture = load(RUNTIME / f"{name}.json")
    asked: list[dict[str, Any]] = []

    def expect(i: int, expected: Any, action: dict[str, Any]) -> None:
        if action["kind"] == "RequestApproval":
            asked.append(action)

    run = play(start(validator, fixture), fixture, expect)
    return run, asked


def test_a_person_required_step_marks_nothing(validator: _core.Validator) -> None:
    """What subset matching cannot say about profile_person_does_not_mark_readers:
    the person's request has no mandate_ref, the later step's has no
    always_ask, the trace has person_required once and no always_ask, and
    the reader's record has neither member."""
    run, asked = replay(validator, "profile_person_does_not_mark_readers")
    assert run.next()["kind"] == "Completed"
    first, second = asked
    assert first["approver"] == {"kind": "human", "always_ask": True}
    assert second["approver"] == {"kind": "standing_mandate", "mandate_ref": "m1"}
    kinds = [t["kind"] for t in run.trace()]
    assert kinds.count("person_required") == 1
    assert "always_ask" not in kinds
    person = next(t for t in run.trace() if t["kind"] == "person_required")
    assert person["detail"] == {"profiles": ["person-mutate"]}
    mutate, reader = run.action_records()
    assert mutate["person_required"] is True and "always_ask" not in mutate
    assert "person_required" not in reader and "always_ask" not in reader


def test_a_person_overrides_a_mandate_without_always_ask_on_the_record(
    validator: _core.Validator,
) -> None:
    run, asked = replay(validator, "profile_person_overrides_mandate")
    assert asked[0]["approver"] == {"kind": "human", "always_ask": True}
    (record,) = run.action_records()
    assert "always_ask" not in record
    assert record["approval"]["mandate_ref"] is None


@pytest.mark.parametrize(
    ("name", "person", "profile"),
    [
        ("profile_person_not_passed_to_nested_run", "invoke step", "person-invoke"),
        ("profile_person_not_passed_to_recovery", "verify step", "person-verify"),
    ],
)
def test_the_person_requirement_reaches_no_nested_run_or_recovery_context(
    validator: _core.Validator, name: str, person: str, profile: str
) -> None:
    """§5.21.3: the requirement is not a mark, so it reaches neither the
    nested run an invoke starts nor the context a failure mode injects. The
    trace has person_required once per ask of the step the profile names and
    no always_ask; every other step's request names its standing mandate,
    and its record carries neither member."""
    run, asked = replay(validator, name)
    assert run.next()["kind"] == "Completed"
    records = run.action_records()
    traced = [t for t in run.trace() if t["kind"] == "person_required"]
    kinds = [t["kind"] for t in run.trace()]
    assert "always_ask" not in kinds
    assert all(t["detail"] == {"profiles": [profile]} for t in traced)
    assert len(traced) == sum(r["intent"] == person for r in records)
    for action, record in zip(asked, records, strict=True):
        assert "always_ask" not in record
        if record["intent"] == person:
            assert action["approver"] == {"kind": "human", "always_ask": True}
            assert record["person_required"] is True
            assert record["approval"]["mandate_ref"] is None
        else:
            assert action["approver"] == {
                "kind": "standing_mandate",
                "mandate_ref": "m1",
            }
            assert "person_required" not in record
            assert record["approval"]["mandate_ref"] == "m1"


def test_a_profile_without_an_exact_json_form_is_refused_everywhere(
    validator: _core.Validator, ontology_path: str, tmp_path: Path
) -> None:
    """A run saves its profiles as given and a record digest covers them, so
    a member beyond I-JSON (an integer above 2^53) is S303 when the profile
    loads: the executor, the validator and the adapter refuse it alike,
    rather than save a profile other than the one given."""
    big = {"domain": "d", "version": "1.0.0", "x-n": 2**60 + 1}
    report = validator.check_profiles([big])
    assert found(report, "error") == {("S303", "d", "x-n")}
    catalog = {
        "w": {
            "goal": "g",
            "risk": "low",
            "spec_version": "1.1",
            "steps": [
                {
                    "capability": "retrieve",
                    "purpose": "p",
                    "store_as": "r",
                    "input_bindings": {"target": "x"},
                }
            ],
        }
    }
    with pytest.raises(ValueError, match="S303"):
        _core.Run.start(
            validator,
            catalog,
            "w",
            {},
            header=None,
            run_id="r",
            now_ms=0,
            profiles=[big],
        )
    with pytest.raises(ProfileError, match="S303"):
        GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                profiles=[big],
            )
        )
    exact = {"domain": "d", "version": "1.0.0", "x-n": 2**53}
    run = _core.Run.start(
        validator, catalog, "w", {}, header=None, run_id="r", now_ms=0, profiles=[exact]
    )
    assert run.snapshot()["state"].count("9007199254740992") == 1


HEADER_CATALOG = """\
# Standard version: {version}
# No workflow declares spec_version: the header gives the target (STANDARD
# v1.2 §11.5).
w:
  goal: Change a setting once a person whose identity is checked approves.
  risk: high
  workflow_extensions:
    requires: [identity@1, approval@1]
  steps:
  - capability: checkpoint
    purpose: Save the state.
    store_as: cp
    input_bindings: {{scope: repo}}
  - capability: constrain
    purpose: Check the policy.
    store_as: policy
    input_bindings: {{target: config, constraints: [policy]}}
  - capability: mutate
    purpose: Change the setting.
    store_as: m
    input_bindings: {{target: config, operation: {{set: 1}}}}
    approval:
      approver: {{kind: human, sender_check: [directory_id]}}
"""


@pytest.mark.parametrize(
    ("version", "end"), [("1.2.0", (None, "F502")), ("1.1.0", ("completed", None))]
)
def test_the_runner_runs_a_catalog_file_under_its_header(
    tmp_path: Path, version: str, end: tuple[str | None, str | None]
) -> None:
    """A catalog file whose only declaration is its header targets that
    version in the executor as in the validator: under 1.2.0 the approver's
    sender_check requires attested identities, and a decision without them
    counts no approver (F502, §5.17); under 1.1.0 sender_check is not read
    and the decision counts."""
    path = tmp_path / "catalog.yaml"
    path.write_text(HEADER_CATALOG.format(version=version))
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(path)
    result = WorkflowRunner(engine).run("w", None, FakeHost(Clock()))
    assert (result.outcome, result.code) == end, result
