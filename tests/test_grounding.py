"""Grounding (STANDARD v1.2 §3.1, §5.20): the vectors through the core's
check and the Python API, policies and their validation, and the runner
applying host policies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import (
    GroundedAgentAdapter,
    GroundedAgentConfig,
    GroundingPolicy,
    _core,
    check_grounding_output,
)
from grounded_agency.grounding import as_policies
from grounded_agency.workflows import Host, WorkflowEngine, WorkflowRunner

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = str(ROOT / "schemas" / "capability_ontology.yaml")
VECTORS = json.loads(
    (ROOT / "tests" / "conformance" / "grounding" / "check.json").read_text()
)["vectors"]


def test_the_vectors_are_normative() -> None:
    doc = json.loads(
        (ROOT / "tests" / "conformance" / "grounding" / "check.json").read_text()
    )
    assert doc["status"] == "normative" and doc["standard"] == "1.2.0"
    assert len({v["name"] for v in VECTORS}) == len(VECTORS) >= 45


def _check(v: dict[str, Any]) -> dict[str, Any]:
    policy = {k: x for k, x in v["policy"].items() if x is not None}
    return _core.check_grounding(
        v["output"], policy, v["bound_refs"], v["evidence_seen"]
    )


@pytest.mark.parametrize("v", VECTORS, ids=[v["name"] for v in VECTORS])
def test_core_check_gives_each_vector(v: dict[str, Any]) -> None:
    got = _check(v)
    expect = v["expect"]
    assert (got["status"], got["code"]) == (expect["status"], expect["code"]), got
    if expect["status"] != "refused":
        assert (got["counted"], got["legacy"]) == (expect["counted"], expect["legacy"])
    else:
        assert got["message"]


@pytest.mark.parametrize("v", VECTORS, ids=[v["name"] for v in VECTORS])
def test_check_output_gives_each_vector(v: dict[str, Any]) -> None:
    policy = GroundingPolicy(
        require={"retrieve"},
        kinds=v["policy"]["kinds"],
        attested=v["policy"]["attested"],
    )
    got = check_grounding_output(
        v["output"],
        policy,
        bound_refs=v["bound_refs"],
        evidence_seen=v["evidence_seen"],
    )
    expect = v["expect"]
    assert (got.status, got.code) == (expect["status"], expect["code"])
    assert got.ok is (expect["code"] is None)
    if expect["status"] != "refused":
        assert (got.counted, got.legacy) == (expect["counted"], expect["legacy"])


def test_absent_and_empty_evidence_seen_differ() -> None:
    policy = GroundingPolicy(require={"retrieve"})
    out = {"evidence_anchors": [{"ref": "file:a", "kind": "file"}]}
    assert check_grounding_output(out, policy, evidence_seen=None).status == "grounded"
    refused = check_grounding_output(out, policy, evidence_seen=())
    assert refused.code == "F505" and "evidence_seen" in refused.message


def test_check_refuses_a_bound_reference_that_is_not_one() -> None:
    with pytest.raises(ValueError, match="bound_refs"):
        check_grounding_output(
            {"evidence_anchors": []},
            GroundingPolicy(require={"retrieve"}),
            bound_refs=["r: string"],
        )


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"require": {"clasify"}}, "V101.*'classify'"),
        ({"require": set()}, "must not be empty"),
        ({"require": "retrieve"}, "list of strings"),
        ({"require": {"retrieve"}, "kinds": set()}, "must not be empty"),
        (
            {"require": {"retrieve"}, "kinds": {"tool_output"}},
            "not an evidence anchor kind",
        ),
        ({"require": {"retrieve"}, "attested": "yes"}, "boolean"),
    ],
)
def test_policy_is_validated(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        GroundingPolicy(**kwargs)


def test_policy_round_trip_and_normalisation() -> None:
    p = GroundingPolicy(require=["search", "retrieve"], kinds=["x-db", "file"])
    assert p.to_dict() == {
        "require": ["retrieve", "search"],
        "kinds": ["file", "x-db"],
        "attested": False,
    }
    assert GroundingPolicy.from_dict(p.to_dict()) == p
    assert p.requires("search") and not p.requires("send")
    assert as_policies(None) == ()
    assert as_policies(p) == (p,)
    assert as_policies([p, p]) == (p, p)
    with pytest.raises(TypeError):
        as_policies([{"require": ["search"]}])  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"require": ["retrieve"], "kind": ["file"]}, "kind"),
        ({"require": ["retrieve"], "atested": True}, "atested"),
    ],
)
def test_a_policy_refuses_a_member_it_does_not_define(
    data: dict[str, Any], key: str
) -> None:
    """A misspelt member would turn a check off: it is refused, in Python
    and by the core (the runner's and ``_core.Run.start``'s path), as
    ``groundingPolicies`` refuses it in TypeScript. Extension members
    ``x-...`` are allowed."""
    with pytest.raises(ValueError, match=f"S303.*'{key}' is not a member"):
        GroundingPolicy.from_dict(data)
    with pytest.raises(ValueError, match=f"'{key}' is not a member"):
        _core.check_grounding({"evidence_anchors": []}, data)
    ok = {"require": ["retrieve"], "x-note": "from the audit"}
    assert GroundingPolicy.from_dict(ok) == GroundingPolicy(require={"retrieve"})


def test_core_start_refuses_a_policy_member_it_does_not_define() -> None:
    validator = _core.Validator(ONTOLOGY, str(ROOT))
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
                    "input_bindings": {"target": "t"},
                }
            ],
        }
    }
    with pytest.raises(ValueError, match=r"grounding\[0\]: 'atested' is not a member"):
        _core.Run.start(
            validator,
            catalog,
            "w",
            header=None,
            run_id="r",
            now_ms=0,
            grounding=[{"require": ["retrieve"], "atested": True}],
        )


def test_policy_from_a_profile() -> None:
    profile = {
        "evidence_policy": {
            "require_grounding": ["classify", "predict"],
            "required_anchor_types": ["record", "x-lab_result"],
        }
    }
    p = GroundingPolicy.from_profile(profile)
    assert p is not None
    assert p.require == {"classify", "predict"}
    assert p.kinds == {"record", "x-lab_result"}
    assert GroundingPolicy.from_profile({"evidence_policy": {}}) is None
    assert GroundingPolicy.from_profile({}) is None
    # A policy entry of the {require, kinds} form (S6's profile_policy()).
    entry = GroundingPolicy.from_profile({"require": ["search"], "kinds": ["file"]})
    assert entry == GroundingPolicy(require={"search"}, kinds={"file"})
    # Kinds that are not §6.5 kinds are refused, so a shipped profile is read
    # only once its required_anchor_types are migrated (S6).
    with pytest.raises(ValueError, match="not an evidence anchor kind"):
        GroundingPolicy.from_profile(
            {
                "evidence_policy": {
                    "require_grounding": ["classify"],
                    "required_anchor_types": ["clinical_data_point"],
                }
            }
        )
    with pytest.raises(ValueError, match="V101"):
        GroundingPolicy.from_profile(
            {"evidence_policy": {"require_grounding": ["clasify"]}}
        )


def test_core_start_refuses_an_unknown_id() -> None:
    validator = _core.Validator(ONTOLOGY, str(ROOT))
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
                    "input_bindings": {"target": "t"},
                }
            ],
        }
    }
    with pytest.raises(ValueError, match="V101.*'classify'"):
        _core.Run.start(
            validator,
            catalog,
            "w",
            header=None,
            run_id="r",
            now_ms=0,
            grounding=[{"require": ["clasify"]}],
        )


def test_adapter_config_takes_one_policy_or_several(tmp_path: Path) -> None:
    one = GroundingPolicy(require={"search"})
    config = GroundedAgentConfig(
        ontology_path=ONTOLOGY, checkpoint_dir=str(tmp_path), grounding=one
    )
    assert config.grounding == (one,)
    with pytest.raises(ValueError, match="V101"):
        GroundedAgentConfig(
            ontology_path=ONTOLOGY,
            checkpoint_dir=str(tmp_path),
            grounding=(GroundingPolicy(require={"clasify"}),),
        )


def test_adapter_refuses_an_ungrounded_call_output(tmp_path: Path) -> None:
    """A safety layer applies its policies to a call's output (§5.20 *Hosts
    outside a workflow*): argument names are bound, no evidence_seen."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ONTOLOGY,
            checkpoint_dir=str(tmp_path),
            grounding=GroundingPolicy(require={"retrieve"}),
        )
    )
    args = {"file_path": "a.py"}
    ungrounded = {"data": "x", "evidence_anchors": [], "confidence": 1}
    text = adapter.check_call_output("Read", args, ungrounded, call="c1")
    assert text is not None and text.startswith("F505 PROVENANCE_MISSING:")
    assert adapter.diagnostics[-1].location == {
        "tool": "Read",
        "capability": "retrieve",
        "call": "c1",
    }
    cites_arg = {
        "data": "x",
        "evidence_anchors": [{"ref": "acs:file_path", "kind": "record"}],
        "confidence": 1,
    }
    assert adapter.check_call_output("Read", args, cites_arg) is None
    unbound = {
        "data": "x",
        "evidence_anchors": [{"ref": "acs:other", "kind": "record"}],
        "confidence": 1,
    }
    assert adapter.check_call_output("Read", args, unbound) is not None
    # No capability output at all fails too; a capability no policy
    # requires is not checked.
    assert adapter.check_call_output("Read", args, "plain text") is not None
    assert adapter.check_call_output("Grep", {"pattern": "x"}, "plain text") is None


def test_adapter_warns_once_when_a_policy_cannot_check_a_tool(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Claude Code's own tools return no capability output, so a policy that
    requires their capability checks nothing for their calls: the adapter
    says so, once per tool, instead of turning the check off silently."""
    import asyncio
    import logging

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ONTOLOGY,
            checkpoint_dir=str(tmp_path),
            approval="off",
            grounding=GroundingPolicy(require={"retrieve"}),
        )
    )
    hook = adapter._make_pretooluse_safety_hook()
    call = {"tool_name": "Read", "tool_input": {"file_path": "a.py"}}
    with caplog.at_level(logging.WARNING, logger="grounded_agency.adapter"):
        for i in range(2):
            asyncio.run(hook(call, f"r{i}", None))
        asyncio.run(
            hook({"tool_name": "Grep", "tool_input": {"pattern": "x"}}, "g1", None)
        )
    warned = [r.getMessage() for r in caplog.records if "5.20" in r.getMessage()]
    assert len(warned) == 1, warned
    assert "retrieve" in warned[0] and "Read" in warned[0]
    # A tool create_grounded_mcp_server serves is checked: no warning.
    adapter._register_grounded_tool("mcp__srv__fetch")
    adapter.mapper.register_mcp_tool("mcp__srv__fetch", capability_id="retrieve")
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="grounded_agency.adapter"):
        asyncio.run(
            hook({"tool_name": "mcp__srv__fetch", "tool_input": {}}, "f1", None)
        )
    assert not [r for r in caplog.records if "5.20" in r.getMessage()]


# ---------------------------------------------------------------------------
# The runner with host policies
# ---------------------------------------------------------------------------

CATALOG = """\
# Standard version: 1.1.0
fetch:
  goal: Fetch and classify.
  risk: low
  steps:
  - capability: retrieve
    purpose: Read.
    store_as: r
    input_bindings:
      target: t
  - capability: classify
    purpose: Classify.
    store_as: c
    input_bindings:
      item: "${r.data: object}"
"""


class GroundingHost(Host):
    """Answers retrieve and classify with given anchors."""

    def __init__(
        self,
        anchors: dict[str, list[Any]],
        seen: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__()
        self.anchors = anchors
        self.seen = seen or {}
        self.now = 1_000

    def now_ms(self) -> int:
        return self.now

    def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
        cap = action["capability"]
        value: dict[str, Any] = {
            "evidence_anchors": self.anchors.get(cap, []),
            "confidence": 0.9,
        }
        value["data" if cap == "retrieve" else "labels"] = {"x": 1}
        response: dict[str, Any] = {"kind": "Output", "value": value}
        if cap in self.seen:
            response["evidence_seen"] = self.seen[cap]
        return response


@pytest.fixture()
def runner(tmp_path: Path) -> WorkflowRunner:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(CATALOG)
    engine = WorkflowEngine(ONTOLOGY, schema_root=str(ROOT))
    engine.load_catalog(catalog)
    return WorkflowRunner(engine)


FILE = {"ref": "file:a.txt", "kind": "file"}


def test_runner_applies_a_policy(runner: WorkflowRunner) -> None:
    host = GroundingHost({"retrieve": [FILE]})
    ok = runner.run("fetch", {}, host, grounding=GroundingPolicy(require={"retrieve"}))
    assert ok.ok, ok
    failed = runner.run(
        "fetch", {}, host, grounding=GroundingPolicy(require={"classify"})
    )
    assert failed.code == "F505"


def test_runner_applies_each_policy(runner: WorkflowRunner) -> None:
    host = GroundingHost({"retrieve": [FILE], "classify": [FILE]})
    passes = runner.run(
        "fetch",
        {},
        host,
        grounding=[
            GroundingPolicy(require={"retrieve"}),
            GroundingPolicy(require={"classify"}, kinds={"file"}),
        ],
    )
    assert passes.ok, passes
    # Each policy applies on its own: the second refuses classify's file
    # anchor although the first would count it.
    refused = runner.run(
        "fetch",
        {},
        host,
        grounding=[
            GroundingPolicy(require={"classify"}),
            GroundingPolicy(require={"classify"}, kinds={"log"}),
        ],
    )
    assert refused.code == "F505"


def test_evidence_seen_reaches_the_core(runner: WorkflowRunner) -> None:
    policy = GroundingPolicy(require={"retrieve"}, attested=True)
    seen = runner.run(
        "fetch",
        {},
        GroundingHost({"retrieve": [FILE]}, seen={"retrieve": ["file:a.txt"]}),
        grounding=policy,
    )
    assert seen.ok, seen
    unseen = runner.run(
        "fetch",
        {},
        GroundingHost({"retrieve": [FILE]}, seen={"retrieve": ["file:b.txt"]}),
        grounding=policy,
    )
    assert unseen.code == "F505"
