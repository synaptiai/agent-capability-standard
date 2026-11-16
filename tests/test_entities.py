"""Entity ids (STANDARD v1.2 §7.1): ``grounded_agency.entities`` against the
normative vectors, the taxonomy's examples and pattern, and the §7.1 code
block of the newest Standard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core
from grounded_agency.entities import ENTITY_ID, parse_entity_id, taxonomy_classes

ROOT = Path(__file__).resolve().parent.parent
IDS = json.loads((ROOT / "tests/conformance/entities/ids.json").read_text("utf-8"))
TAXONOMY: dict[str, Any] = _core.load_yaml(str(ROOT / "schemas/entity_taxonomy.yaml"))
CLASSES = taxonomy_classes(TAXONOMY)


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
