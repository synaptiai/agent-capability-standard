"""The SDK's evidence anchor (STANDARD v1.2 §6.5): canonical kinds, the
legacy names as deprecated aliases whose queries return what they returned
in 1.1, the factories, and the anchors that ground action outputs (§3.1)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.state.evidence_store import (
    ANCHOR_KINDS,
    COORDINATION_REF_PREFIXES,
    PRIORITY_HIGH,
    EvidenceAnchor,
    EvidenceStore,
)

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = str(ROOT / "schemas" / "capability_ontology.yaml")
SHA = "sha256:" + "0" * 64


@pytest.mark.parametrize("kind", [*ANCHOR_KINDS, "x-lab_result"])
def test_canonical_kinds_are_kept_without_a_warning(kind: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert EvidenceAnchor(ref="r", kind=kind, timestamp=None).kind == kind


@pytest.mark.parametrize(
    "legacy, canonical",
    [
        ("tool_output", "tool"),
        ("command", "tool"),
        ("mutation", "record"),
        ("coordination", "record"),
    ],
)
def test_legacy_kinds_map_with_a_warning(legacy: str, canonical: str) -> None:
    with pytest.warns(DeprecationWarning, match=legacy):
        a = EvidenceAnchor(ref="r", kind=legacy, timestamp="t")
    assert a.kind == canonical
    if legacy == "mutation":
        assert a.priority == PRIORITY_HIGH


def test_a_free_kind_becomes_a_vendor_kind() -> None:
    with pytest.warns(DeprecationWarning):
        a = EvidenceAnchor(ref="r", kind="Custom Kind", timestamp="t")
    assert a.kind == "x-custom_kind"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ref": "", "kind": "file"},
        {"ref": "r", "kind": ""},
        {"ref": "r", "kind": "file", "digest": "sha256:ABC"},
        {"ref": "r", "kind": "file", "digest": "0" * 64},
    ],
)
def test_malformed_anchors_are_refused(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        EvidenceAnchor(timestamp="t", **kwargs)


def test_dict_round_trip() -> None:
    a = EvidenceAnchor(
        ref="file:a.txt", kind="file", timestamp="t", excerpt="line 1", digest=SHA
    )
    d = a.to_dict()
    assert d == {
        "ref": "file:a.txt",
        "kind": "file",
        "timestamp": "t",
        "excerpt": "line 1",
        "digest": SHA,
    }
    assert EvidenceAnchor.from_dict(d) == a
    for bad in [
        "file:a",
        {"ref": "a"},
        {"ref": "a", "kind": "tool_output"},
        {"ref": "", "kind": "file"},
    ]:
        with pytest.raises(ValueError):
            EvidenceAnchor.from_dict(bad)


def test_factories() -> None:
    assert EvidenceAnchor.from_tool_output("Read", "1", {}).kind == "tool"
    cmd = EvidenceAnchor.from_command("ls", 0, "c1")
    assert (cmd.ref, cmd.kind) == ("command:c1", "tool")
    m = EvidenceAnchor.from_mutation("cfg.yaml", "write")
    assert (m.ref, m.kind, m.priority) == ("mutation:cfg.yaml", "record", PRIORITY_HIGH)
    cp = EvidenceAnchor.from_checkpoint("cp-1")
    assert cp.to_dict()["ref"] == "checkpoint:cp-1" and cp.kind == "record"
    f = EvidenceAnchor.from_file("a.py", file_hash=SHA)
    assert f.digest == SHA and "hash" not in f.metadata
    g = EvidenceAnchor.from_file("a.py", file_hash="md5:abc")
    assert g.digest is None and g.metadata["hash"] == "md5:abc"


def test_legacy_queries_return_what_they_returned() -> None:
    """A legacy kind is answered by ref prefix: ``command`` returns command
    anchors only, though ``tool`` now covers them too."""
    store = EvidenceStore()
    store.add_anchor(EvidenceAnchor.from_tool_output("Bash", "b1", {}))
    store.add_anchor(EvidenceAnchor.from_command(None, 0, "b1"))
    store.add_anchor(EvidenceAnchor.from_mutation("cfg", "write"))
    for prefix in COORDINATION_REF_PREFIXES:
        store.add_anchor(EvidenceAnchor(ref=f"{prefix}x", kind="record", timestamp="t"))
    with pytest.warns(DeprecationWarning):
        (command,) = store.get_by_kind("command")
    assert command.ref == "command:b1"
    with pytest.warns(DeprecationWarning):
        (tool,) = store.get_by_kind("tool_output")
    assert tool.ref == "tool:Bash:b1"
    with pytest.warns(DeprecationWarning):
        assert len(store.get_by_kind("coordination")) == len(COORDINATION_REF_PREFIXES)
    with pytest.warns(DeprecationWarning):
        assert [a.ref for a in store.get_by_kind("mutation")] == ["mutation:cfg"]
    assert {a.ref for a in store.get_by_kind("tool")} == {"tool:Bash:b1", "command:b1"}
    assert [a.ref for a in store.get_mutations()] == ["mutation:cfg"]
    assert [a.ref for a in store.get_tool_outputs()] == ["tool:Bash:b1"]
    with pytest.warns(DeprecationWarning):
        assert store.records(kind="command")[0].anchor.ref == "command:b1"


def test_outputs_get_objects() -> None:
    store = EvidenceStore()
    store.add_anchor(EvidenceAnchor.from_file("a.py"), capability_id="retrieve")
    (obj,) = store.evidence_anchors_for("retrieve")
    assert obj["ref"] == "file:a.py" and obj["kind"] == "file"
    with pytest.warns(DeprecationWarning):
        assert store.get_for_capability_output("retrieve") == ["file:a.py"]


def test_coordination_refuses_an_unknown_prefix() -> None:
    from grounded_agency.coordination._evidence_helpers import (
        record_coordination_evidence,
    )
    from grounded_agency.coordination.audit import CoordinationAuditLog

    with pytest.raises(ValueError, match="COORDINATION_REF_PREFIXES|one of"):
        record_coordination_evidence(
            EvidenceStore(),
            CoordinationAuditLog(),
            ref_prefix="gossip",
            ref_id="1",
            event_type="x",
            source_agent_id="a",
            target_agent_ids=[],
            capability_id="synchronize",
            metadata={},
        )


def test_create_checkpoint_records_its_anchor(tmp_path: Path) -> None:
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(ontology_path=ONTOLOGY, checkpoint_dir=str(tmp_path))
    )
    checkpoint_id = adapter.create_checkpoint(["*.py"], "before")
    (obj,) = adapter.evidence_store.evidence_anchors_for("checkpoint")  # type: ignore[attr-defined]
    assert obj["ref"] == f"checkpoint:{checkpoint_id}" and obj["kind"] == "record"
