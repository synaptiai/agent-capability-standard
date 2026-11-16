"""Evidence anchors, records and the common output fields in the schemas
(STANDARD v1.2 §4.1.1, §6.5, §6.6): the two canonical ``Anchor`` and
``Uncertainty`` types agree, the interop schema restates them, every output
contract declares the common fields, the ontology's principle matches the
contracts, and every capability skill glosses ``confidence`` as §4.1.1
defines it."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = yaml.safe_load((ROOT / "schemas" / "capability_ontology.yaml").read_text())
EVENT = yaml.safe_load((ROOT / "schemas" / "event_schema.yaml").read_text())
WORLD = yaml.safe_load((ROOT / "schemas" / "world_state_schema.yaml").read_text())
INTEROP = json.loads(
    (ROOT / "schemas" / "interop" / "evidence.schema.json").read_text()
)
NODES = {n["id"]: n for n in ONTOLOGY["nodes"]}

# The 23 outputs whose contract requires a confidence; the other 13 declare
# it optional (Standard v1.2 §4.1.1).
REQUIRE_CONFIDENCE = {
    "retrieve", "search", "observe", "detect", "classify", "measure", "predict",
    "compare", "discover", "plan", "decompose", "critique", "explain", "state",
    "transition", "attribute", "ground", "simulate", "generate", "transform",
    "integrate", "verify", "inquire",
}  # fmt: skip
ANCHOR_REF = "schemas/event_schema.yaml#/types/Anchor"
UNCERTAINTY_REF = "schemas/event_schema.yaml#/types/Uncertainty"
METHODS = [
    "model_knowledge", "deduction", "induction", "abduction", "analogy",
    "statistical", "simulation", "assumption",
]  # fmt: skip


def without_descriptions(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: without_descriptions(v) for k, v in value.items() if k != "description"
        }
    if isinstance(value, list):
        return [without_descriptions(v) for v in value]
    return value


@pytest.mark.parametrize("name", ["Anchor", "Uncertainty"])
def test_the_canonical_types_are_equal(name: str) -> None:
    assert without_descriptions(EVENT["types"][name]) == without_descriptions(
        WORLD["types"][name]
    )


def test_the_interop_anchor_restates_the_canonical_one() -> None:
    yaml_anchor = EVENT["types"]["Anchor"]
    interop = INTEROP["$defs"]["EvidenceAnchor"]
    assert interop["required"] == yaml_anchor["required"] == ["ref", "kind"]
    assert set(interop["properties"]) == set(yaml_anchor["properties"])
    assert (
        INTEROP["$defs"]["Kind"]["pattern"]
        == yaml_anchor["properties"]["kind"]["pattern"]
    )
    assert (
        INTEROP["$defs"]["Digest"]["pattern"]
        == yaml_anchor["properties"]["digest"]["pattern"]
    )


@pytest.mark.parametrize("capability", sorted(NODES))
def test_every_output_declares_the_common_fields(capability: str) -> None:
    out = NODES[capability]["output_schema"]
    props = out["properties"]
    items = props["evidence_anchors"]["items"]["anyOf"]
    assert items[0] == {"$ref": ANCHOR_REF}
    assert [i.get("type") for i in items[1:]] == ["string", "object"]
    method = props["inference_method"]
    assert method["type"] == "string" and "pattern" not in method
    for m in METHODS:
        assert m in method["description"]
    assert props["confidence"]["type"] == "number"
    if capability == "measure":
        assert set(props["uncertainty"]["properties"]) >= {"lower", "upper", "interval"}
    else:
        assert props["uncertainty"]["$ref"] == UNCERTAINTY_REF
    assert ("confidence" in out.get("required", [])) is (
        capability in REQUIRE_CONFIDENCE
    )


def test_the_principle_matches_the_contracts() -> None:
    principles = ONTOLOGY["meta"]["principles"]
    assert (
        "Every capability output carries evidence anchors, or is marked inferred "
        "with an inference method and a confidence" in principles
    )
    assert (
        "A capability whose output contract requires a confidence returns one in "
        "every output" in principles
    )
    assert len(REQUIRE_CONFIDENCE) == 23 and len(NODES) == 36


def test_the_common_fields_table_matches_the_contracts() -> None:
    """§4.1.1's table says where each common field is required: it agrees
    with the contracts (``uncertainty`` is required by ``measure`` only,
    ``inference_method`` by none)."""
    text = (ROOT / "spec" / "STANDARD-v1.2.0.md").read_text(encoding="utf-8")
    section = text[text.index("#### 4.1.1 ") : text.index("### 4.2 ")]
    rows = {
        cells[0].strip("`"): cells[2]
        for line in section.splitlines()
        if line.startswith("| `")
        for cells in [[c.strip() for c in line.strip("|").split("|")]]
    }
    required = {
        name: sorted(
            c for c, n in NODES.items() if name in n["output_schema"]["required"]
        )
        for name in (
            "evidence_anchors",
            "confidence",
            "inference_method",
            "uncertainty",
        )
    }
    assert len(required["evidence_anchors"]) == 36
    assert rows["evidence_anchors"] == "Required"
    assert sorted(required["confidence"]) == sorted(REQUIRE_CONFIDENCE)
    assert rows["confidence"].startswith("Required where")
    assert required["inference_method"] == [] and rows["inference_method"] == "Optional"
    assert required["uncertainty"] == ["measure"]
    assert rows["uncertainty"] == "Required for `measure`, optional elsewhere"


def test_every_on_error_list_in_the_standard_matches_the_schema() -> None:
    """Each place the Standard lists the codes ``on_error`` fires on (§5.7's
    table, §5.12) names exactly the catalog schema's fireable codes."""
    schema = json.loads((ROOT / "schemas" / "workflow_catalog.schema.json").read_text())
    codes = schema["$defs"]["fireable_code"]["enum"]
    text = (ROOT / "spec" / "STANDARD-v1.2.0.md").read_text(encoding="utf-8")
    table_row = re.search(r"^\| `on_error` \|.*$", text, re.MULTILINE)
    assert table_row is not None
    section = text[text.index("### 5.12 ") : text.index("### 5.13 ")]
    listed = re.search(r"code or a list: ((?:[RF]\d{3}, )*[RF]\d{3});", section)
    assert listed is not None
    for where, found in (
        ("§5.7", re.findall(r"[RF]\d{3}", table_row.group(0))),
        ("§5.12", re.findall(r"[RF]\d{3}", listed.group(1))),
    ):
        assert found == codes, (where, found, codes)


def test_audit_reports_its_store_and_retention_is_a_duration() -> None:
    audit = NODES["audit"]
    assert set(audit["output_schema"]["properties"]["store"]["properties"]) == {
        "name",
        "durability",
        "retention",
    }
    assert "§5.10.1" in audit["input_schema"]["properties"]["retention"]["description"]


# ---------------------------------------------------------------------------
# The notification
# ---------------------------------------------------------------------------


def validate(name: str, value: Any) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": INTEROP["$defs"],
        "$ref": f"#/$defs/{name}",
    }
    jsonschema.Draft202012Validator(schema).validate(value)


BASE = {"type": "acs.evidence_recorded", "recorded_at": "2026-11-16T00:00:00Z"}
FILE = {"ref": "file:a", "kind": "file"}


@pytest.mark.parametrize(
    "payload",
    [
        {**BASE, "record_ids": ["ev-0"], "anchors": [FILE]},
        {**BASE, "event_id": "evt-1", "anchors": [FILE]},
        # An audit record with no anchors of its own.
        {**BASE, "action_ids": ["run-1/w/0/1"], "anchors": []},
    ],
)
def test_notifications_that_validate(payload: dict[str, Any]) -> None:
    validate("EvidenceRecorded", payload)


@pytest.mark.parametrize(
    "payload",
    [
        {**BASE, "record_ids": ["ev-0"], "action_ids": ["a"], "anchors": [FILE]},
        {**BASE, "anchors": [FILE]},
        {**BASE, "record_ids": ["ev-0"], "anchors": [{**FILE, "excerpt": "x"}]},
    ],
)
def test_notifications_that_do_not(payload: dict[str, Any]) -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate("EvidenceRecorded", payload)


def test_a_record_validates() -> None:
    record = {
        "record_id": "ev-0",
        "anchor": {**FILE, "digest": "sha256:" + "0" * 64},
        "recorded_at": "2026-11-16T00:00:00Z",
        "run_id": "run-1",
        "frame": ["w"],
        "step": 0,
        "capability": "retrieve",
    }
    validate("EvidenceRecord", record)
    bad = copy.deepcopy(record)
    bad["anchor"]["kind"] = "tool_output"
    with pytest.raises(jsonschema.ValidationError):
        validate("EvidenceRecord", bad)


# ---------------------------------------------------------------------------
# The skills' confidence glosses (§4.1.1)
# ---------------------------------------------------------------------------

# Glosses of something other than a probability, which the skills used
# before Standard 1.2.
NOT_A_PROBABILITY = [
    "parse success",
    "successful delivery",
    "completeness of audit",
    "completeness of the audit",
    "write verification",
    "match quality",
    "conflict count",
    "delegation clarity",
    "policy coverage",
    "integrity verification",
    "verification match",
    "methodology",
    "analysis completeness",
    "mapping completeness",
    "evidence completeness",
    "observation completeness",
    "artifact quality",
    "artifact fitness",
]


@pytest.mark.parametrize("capability", sorted(NODES))
def test_confidence_glosses_state_a_probability(capability: str) -> None:
    text = (ROOT / "skills" / capability / "SKILL.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| `confidence` |")]
    for row in rows:
        assert "probability" in row.lower() and "§4.1.1" in row, (capability, row)
    for line in text.splitlines():
        if "confidence" not in line.lower():
            continue
        for phrase in NOT_A_PROBABILITY:
            assert phrase not in line.lower(), (capability, line)
    # The skills of the three that document none are execute, mutate and
    # invoke.
    assert bool(rows) is (capability not in {"execute", "mutate", "invoke"})


def test_skill_examples_cite_anchors() -> None:
    """No capability skill's example lists a bare string as an anchor any
    more (the deprecated form, §6.5)."""
    for capability in NODES:
        text = (ROOT / "skills" / capability / "SKILL.md").read_text(encoding="utf-8")
        assert "evidence_anchors: array[string]" not in text, capability
        for block in re.findall(r"evidence_anchors:\n((?:\s+- .*\n)+)", text):
            for item in block.strip().splitlines():
                assert item.strip().startswith("- {ref: "), (capability, item)


def test_the_oasf_proposal_quotes_the_principle() -> None:
    text = (ROOT / "docs" / "proposals" / "OASF_SAFETY_EXTENSIONS.md").read_text()
    assert "every capability returns evidence anchors and confidence" not in text
    assert "marked inferred" in text
