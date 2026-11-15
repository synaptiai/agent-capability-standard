"""The Standard Agents interop file stays in step with what it cites.

`schemas/interop/standard_agents_mapping.yaml` is the machine-readable part of
the Standard Agents binding: which ontology capability a Standard Agents
construct is, the anchor reference forms, the timestamp rule and the identity
field map. Its wording is a record of reviewed mapping rows and is not checked
here. What is checked is what a binding loads and what would rot unnoticed:
the pinned versions equal those of the row-level mapping, every capability id
is in the ontology, every cited row exists, and the values it gives for schema
fields fit the schemas that define those fields.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "schemas" / "interop" / "standard_agents_mapping.yaml"
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
WORLD_STATE = ROOT / "schemas" / "world_state_schema.yaml"

# What each ruling type must say (the file's header defines the four).
RULINGS = {"is", "carrier", "by_effect", "audit_label"}
# A row of the row-level mapping, as the file and its prose name one.
ROW = re.compile(r"\b[a-z]+(?:-[a-z]+)+#[a-z]+-\d{2}\b")


def load(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        loaded: dict[str, Any] = yaml.safe_load(f)
    return loaded


@pytest.fixture(scope="module")
def mapping() -> dict[str, Any]:
    return load(MAPPING)


@pytest.fixture(scope="module")
def rows_dir(mapping: dict[str, Any]) -> Path:
    rows: str = mapping["meta"]["rows"]
    return ROOT / rows


@pytest.fixture(scope="module")
def index(rows_dir: Path) -> dict[str, Any]:
    return load(rows_dir / "index.yaml")


@pytest.fixture(scope="module")
def known_rows(index: dict[str, Any], rows_dir: Path) -> set[str]:
    return {
        f"{entry['concern']}#{row['id']}"
        for entry in index["concerns"]
        for row in load(rows_dir / entry["file"])["rows"]
    }


@pytest.fixture(scope="module")
def capability_ids() -> set[str]:
    return {node["id"] for node in load(ONTOLOGY)["nodes"]}


def walk(value: Any, key: str = "") -> Iterator[tuple[str, Any]]:
    """Every (key, value) pair of the document, at any depth."""
    yield key, value
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, str(k))
    elif isinstance(value, list):
        for v in value:
            yield from walk(v, key)


def test_pinned_versions_equal_the_row_level_mapping(
    mapping: dict[str, Any], index: dict[str, Any]
) -> None:
    meta = mapping["meta"]
    theirs = meta["standard_agent_specification"]
    pinned = index["meta"]["standard_agent_specification"]
    assert theirs["version"] == pinned["version"]
    assert theirs["repository"] == pinned["repository"]
    assert theirs["commit"] == pinned["commit"]
    package = theirs["types_package"]
    assert f"{package['name']} {package['version']}" == pinned["types_package"]

    ours = index["meta"]["agent_capability_standard"]
    assert meta["agent_capability_standard"] == {
        "standard": ours["standard"],
        "ontology": ours["ontology"],
    }


def test_versions_are_strings(mapping: dict[str, Any]) -> None:
    """A bare 1.0 would load as a number; every version here is quoted."""
    meta = mapping["meta"]
    versions = [
        meta["version"],
        meta["standard_agent_specification"]["version"],
        meta["standard_agent_specification"]["types_package"]["version"],
        *meta["agent_capability_standard"].values(),
    ]
    for version in versions:
        assert isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert re.fullmatch(r"[0-9a-f]{40}", meta["standard_agent_specification"]["commit"])


def test_annotation_key_and_documents_exist(mapping: dict[str, Any]) -> None:
    meta = mapping["meta"]
    schema = json.loads((ROOT / meta["annotation"]["schema"]).read_text("utf-8"))
    # The annotation schema says which key of a tool's `annotations` it describes.
    assert f"`{meta['annotation']['key']}` key" in schema["description"]
    assert (ROOT / meta["document"]).is_file()
    assert (ROOT / meta["rows"] / "index.yaml").is_file()
    assert (ROOT / mapping["identity"]["schema"]).is_file()


def test_every_capability_id_is_in_the_ontology(
    mapping: dict[str, Any], capability_ids: set[str]
) -> None:
    named = [
        (key, capability)
        for key, value in walk(mapping)
        if key in {"capabilities", "not_classified_as"} and isinstance(value, list)
        for capability in value
    ]
    assert named
    unknown = [f"{key}: {c}" for key, c in named if c not in capability_ids]
    assert unknown == []


def test_rulings_have_the_documented_fields(mapping: dict[str, Any]) -> None:
    rulings = mapping["capability_rulings"]
    assert rulings
    for name, ruling in rulings.items():
        assert set(ruling) <= {
            "construct",
            "ruling",
            "capabilities",
            "not_classified_as",
            "notes",
            "rows",
        }, name
        assert ruling["construct"].strip() and ruling["notes"].strip(), name
        assert ruling["ruling"] in RULINGS, name
        assert ruling["rows"], name
        assert isinstance(ruling["capabilities"], list), name
        assert len(ruling["capabilities"]) == len(set(ruling["capabilities"])), name
        if ruling["ruling"] != "by_effect":
            # Only a construct classified by what it does may name no capability.
            assert ruling["capabilities"], name
        assert not set(ruling.get("not_classified_as", [])) & set(
            ruling["capabilities"]
        ), name


def test_the_delegation_operations_are_ruled_on(mapping: dict[str, Any]) -> None:
    """The rulings a binding cannot derive: the tools a runtime injects.

    Only `subagent_create` is classified by its reserved name. The rows leave
    that question open for `subagent_message` (tools-contracts#cls-07), so it
    and `notifyParent` are carriers: the step that uses them is classified.
    """
    rulings = mapping["capability_rulings"]
    assert rulings["subagent_create"]["capabilities"] == ["delegate"]
    assert rulings["subagent_create"]["ruling"] == "is"
    assert rulings["subagent_message"]["capabilities"] == ["delegate"]
    assert rulings["subagent_message"]["ruling"] == "carrier"
    assert rulings["notify_parent"]["capabilities"] == ["send"]
    assert rulings["notify_parent"]["ruling"] == "carrier"


def test_every_cited_row_exists(mapping: dict[str, Any], known_rows: set[str]) -> None:
    cited = [
        row
        for key, value in walk(mapping)
        if key == "rows" and isinstance(value, list)
        for row in value
    ]
    # Each ruling, each anchor form, the timestamp rule and each identity entry.
    assert len(cited) >= 20
    assert sorted({row for row in cited if row not in known_rows}) == []


def test_every_entry_cites_a_row(mapping: dict[str, Any]) -> None:
    entries: dict[str, dict[str, Any]] = {
        **{f"ruling {k}": v for k, v in mapping["capability_rulings"].items()},
        **{f"anchor {k}": v for k, v in mapping["anchor_refs"].items()},
        "timestamps": mapping["timestamps"],
        **{f"party {k}": v for k, v in mapping["identity"]["parties"].items()},
        **{
            f"without_identity {i}": v
            for i, v in enumerate(mapping["identity"]["without_identity"])
        },
    }
    for where, entry in entries.items():
        assert entry.get("rows"), where


def test_rows_named_in_prose_exist(known_rows: set[str]) -> None:
    """A row named in a note or a comment, not only in a `rows` list."""
    named = set(ROW.findall(MAPPING.read_text(encoding="utf-8")))
    assert named
    assert sorted(named - known_rows) == []


def test_anchor_forms_fit_the_anchor_type(mapping: dict[str, Any]) -> None:
    anchor = load(WORLD_STATE)["types"]["Anchor"]
    kinds = set(anchor["properties"]["kind"]["enum"])
    assert {"tool_call", "file", "message"} <= set(mapping["anchor_refs"])
    schemes = []
    for name, form in mapping["anchor_refs"].items():
        assert form["kind"] in kinds, name
        scheme, _, rest = form["ref"].partition(":")
        assert re.fullmatch(r"[a-z_]+", scheme) and rest, name
        schemes.append(scheme)
        # Every placeholder of the form is described, and nothing else is.
        assert set(re.findall(r"<([^<>]+)>", form["ref"])) == set(form["parts"]), name
    assert len(schemes) == len(set(schemes))


def test_timestamp_fields_name_a_known_unit(mapping: dict[str, Any]) -> None:
    timestamps = mapping["timestamps"]
    assert timestamps["units_per_second"] == {
        "seconds": 1,
        "milliseconds": 1000,
        "microseconds": 1_000_000,
    }
    assert timestamps["fields"]
    for entry in timestamps["fields"]:
        assert entry["unit"] in timestamps["units_per_second"], entry["field"]
    assert "ISO-8601" in timestamps["acs_form"]


def test_identity_map_fits_the_identity_schema(mapping: dict[str, Any]) -> None:
    identity = mapping["identity"]
    schema = load(ROOT / identity["schema"])["agent_identity"]
    properties = schema["properties"]
    prefixes = []
    for name, party in identity["parties"].items():
        fields = party["fields"]
        assert set(fields) <= set(properties), name
        assert set(schema["required"]) <= set(fields), name
        for field, source in fields.items():
            where = f"{name}.{field}"
            assert set(source) <= {"literal", "from", "prefix", "asserted_by"}, where
            # A field has a fixed value or a named source, never both.
            assert ("literal" in source) != ("from" in source), where
            if "literal" not in source:
                continue
            definition = properties[field]
            if "enum" in definition:
                assert source["literal"] in definition["enum"], where
            if "pattern" in definition:
                assert re.fullmatch(definition["pattern"], source["literal"]), where
        prefix = fields["principal"]["prefix"]
        assert re.fullmatch(r"[a-z][a-z-]*:", prefix), name
        prefixes.append(prefix)
        # A vendor value: the schema's named mechanisms are not observable here.
        assert fields["authenticated_by"]["literal"].startswith("x-"), name
    assert len(prefixes) == len(set(prefixes))


def test_identity_conventions_of_the_binding(mapping: dict[str, Any]) -> None:
    parties = mapping["identity"]["parties"]
    caller = parties["endpoint_caller"]["fields"]
    assert caller["principal"]["prefix"] == "sa-user:"
    assert caller["authenticated_by"]["literal"] == "x-acs.sa-caller"
    # Standard Agents does not say what kind of party a caller is.
    assert caller["kind"] == {
        "from": "Deployment configuration",
        "asserted_by": "deployment",
    }
    child = parties["child_thread"]["fields"]
    assert child["principal"]["prefix"] == "sa-subagent:"
    assert child["authenticated_by"]["literal"] == "x-acs.sa-child-thread"
    assert child["kind"] == {"literal": "agent"}
    assert child["trust_class"] == {"literal": "own_subagent_report"}
