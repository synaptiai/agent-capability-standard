"""Entity ids (STANDARD v1.2 §7.1): ``grounded_agency.entities`` against the
normative vectors, the taxonomy's examples and pattern, and the §7.1 code
block of the newest Standard. Merge and split checks (§7.3 as RFC-0012
proposes it for 1.3.0) against the proposed vectors."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core
from grounded_agency.entities import (
    ENTITY_ID,
    check_merge,
    check_split,
    class_index,
    parse_entity_id,
    taxonomy_classes,
)

ROOT = Path(__file__).resolve().parent.parent
IDS = json.loads((ROOT / "tests/conformance/entities/ids.json").read_text("utf-8"))
TAXONOMY: dict[str, Any] = _core.load_yaml(str(ROOT / "schemas/entity_taxonomy.yaml"))
CLASSES = taxonomy_classes(TAXONOMY)
MERGE = json.loads((ROOT / "tests/conformance/entities/merge.json").read_text("utf-8"))


def newest_standard() -> Path:
    def version(p: Path) -> tuple[int, ...]:
        return tuple(int(x) for x in p.stem.removeprefix("STANDARD-v").split("."))

    return max((ROOT / "spec").glob("STANDARD-v*.md"), key=version)


def test_the_vector_file_lists_the_taxonomy_classes() -> None:
    assert IDS["status"] == "normative"
    assert IDS["standard"] == "1.2.0"
    assert set(IDS["classes"]) == CLASSES


@pytest.mark.parametrize("vector", IDS["vectors"], ids=lambda v: v["name"])
def test_id_vector(vector: dict[str, Any]) -> None:
    expect = vector["expect"]
    if expect.get("error"):
        with pytest.raises(ValueError):
            parse_entity_id(vector["id"], IDS["classes"])
        return
    got = parse_entity_id(vector["id"], IDS["classes"])
    assert got.cls == expect["class"]
    assert list(got.namespace) == expect["namespace"]
    assert got.local_id == expect["local_id"]


def test_the_taxonomy_pattern_is_the_grammar() -> None:
    # No flag: the pattern names every character it refuses, so it means
    # the same here as in ECMA-262 (JSON Schema's dialect) and under
    # re.ASCII, which the parity below would hide.
    pattern = re.compile(TAXONOMY["id_convention"]["pattern"])
    assert pattern.pattern == "^" + ENTITY_ID.pattern.replace("(?:", "(") + "$"
    for vector in IDS["vectors"]:
        grammatical = pattern.fullmatch(vector["id"]) is not None
        if vector["expect"].get("error") and vector["name"] == "class_not_in_taxonomy":
            # The class list is checked by code, not by the pattern.
            assert grammatical
            continue
        assert grammatical != bool(vector["expect"].get("error")), vector["name"]


def test_every_taxonomy_example_parses() -> None:
    for example in TAXONOMY["id_convention"]["examples"]:
        parse_entity_id(example, CLASSES)
    assert "person:org.company/user/12345" in TAXONOMY["id_convention"]["examples"]


def test_the_standard_examples_are_ids_the_taxonomy_lists() -> None:
    text = newest_standard().read_text("utf-8")
    section = text[text.index("### 7.1 Entity Identification") :]
    section = section[: section.index("### 7.2")]
    blocks = re.findall(r"```\n(.*?)```", section, re.S)
    examples = [line for line in blocks[-1].splitlines() if line.strip()]
    assert len(examples) >= 4
    for example in examples:
        parse_entity_id(example, CLASSES)
        assert example in TAXONOMY["id_convention"]["examples"], example


# A literal entity id the repository's own examples write, quoted on the
# line of its key: `entity_id: "..."` (YAML) or `"entity_id": "..."` (JSON).
# An unquoted value is a schema's type (`entity_id: string`), not an id.
LITERAL_ENTITY_ID = re.compile(r"""["']?entity_id["']?:[ \t]*(["'])(.*?)\1""")


def test_every_literal_entity_id_in_the_examples_parses() -> None:
    """The skills, templates, docs, examples and schemas teach the §7.1 form:
    each literal ``entity_id`` they write is an id of a taxonomy class."""
    found: list[tuple[str, str]] = []
    for top in ("skills", "templates", "docs", "examples", "schemas"):
        for path in sorted((ROOT / top).rglob("*")):
            if path.suffix not in {".md", ".yaml", ".yml", ".json"}:
                continue
            if "node_modules" in path.parts:
                continue
            for _, value in LITERAL_ENTITY_ID.findall(path.read_text("utf-8")):
                found.append((str(path.relative_to(ROOT)), value))
    assert found, "the skills write entity ids in their examples"
    for where, value in found:
        try:
            parse_entity_id(value, CLASSES)
        except ValueError as e:
            raise AssertionError(f"{where}: {value!r}: {e}") from e


def test_the_merge_vectors_are_proposed_and_list_the_taxonomy_classes() -> None:
    # Proposed by RFC-0012 (a Draft) for 1.3.0: not normative for 1.2.0.
    assert MERGE["status"] == "proposed"
    assert MERGE["rfc"] == "RFC-0012"
    assert (ROOT / "spec/RFC-0012-identity-merge-and-split.md").is_file()
    assert MERGE["classes"] == class_index(TAXONOMY)
    assert set(MERGE["classes"]) == CLASSES


def test_the_merge_vectors_cover_every_reason() -> None:
    merge = {v["expect"].get("reason") for v in MERGE["merge"]}
    split = {v["expect"].get("reason") for v in MERGE["split"]}
    assert merge - {None} == {
        "too_few_entities",
        "invalid_entity",
        "invalid_entity_id",
        "unknown_class",
        "class_mismatch",
        "duplicate_id",
        "incompatible_types",
        "conflicting_identifier",
    }
    assert split - {None} == {
        "too_few_entities",
        "invalid_entity",
        "invalid_entity_id",
        "unknown_class",
        "class_mismatch",
        "duplicate_id",
        "reused_id",
        "incompatible_types",
    }
    assert None in merge and None in split
    for group in ("merge", "split"):
        names = [v["name"] for v in MERGE[group]]
        assert len(names) == len(set(names)), group


def _expect(got: Any, expect: dict[str, Any]) -> None:
    assert got.ok is expect["ok"], got.message
    if expect["ok"]:
        assert got.reason is None
        assert got.lineage == expect["lineage"]
    else:
        assert got.reason == expect["reason"], got.message
        assert got.lineage is None


@pytest.mark.parametrize("vector", MERGE["merge"], ids=lambda v: v["name"])
def test_merge_vector(vector: dict[str, Any]) -> None:
    got = check_merge(
        vector["entities"],
        vector["into"],
        classes=MERGE["classes"],
        unique_attributes=vector["unique_attributes"],
    )
    _expect(got, vector["expect"])


@pytest.mark.parametrize("vector", MERGE["split"], ids=lambda v: v["name"])
def test_split_vector(vector: dict[str, Any]) -> None:
    got = check_split(vector["entity"], vector["into"], classes=MERGE["classes"])
    _expect(got, vector["expect"])


def test_a_name_in_two_classes_is_refused() -> None:
    taxonomy = {
        "classes": {
            "digital": {"service": {"aliases": ["s"]}, "sensor": {"aliases": ["s"]}}
        }
    }
    with pytest.raises(ValueError):
        class_index(taxonomy)
