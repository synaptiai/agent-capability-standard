"""The Standard Agents binding (examples/standard_agents/) stays in step with
the ontology and the reference executor.

The binding is TypeScript and has its own tests (`npm test` there). What is
checked here is the part that belongs to this repository: the files the
binding takes from it are the ones `scripts/gen_standard_agents_binding.py`
generates, and the annotation schema says what the ontology says.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from grounded_agency import _core

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen_standard_agents_binding.py"
SCHEMA = ROOT / "schemas" / "interop" / "standard_agents_annotation.schema.json"
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return loaded


@pytest.fixture(scope="module")
def ontology() -> dict[str, Any]:
    loaded: dict[str, Any] = _core.load_yaml(str(ONTOLOGY))
    return loaded


def annotation(ontology: dict[str, Any], capability: str) -> dict[str, Any]:
    """The annotation the binding writes for a tool of this capability."""
    node = next(n for n in ontology["nodes"] if n["id"] == capability)
    layer = next(
        name
        for name, info in ontology["layers"].items()
        if capability in info["capabilities"]
    )
    return {
        "standard": "1.1.0",
        "ontology": str(ontology["meta"]["version"]),
        "capability": capability,
        "layer": layer,
        "risk": node.get("risk", "low"),
        "mutation": bool(node.get("mutation", False)),
        "requires_checkpoint": bool(node.get("requires_checkpoint", False)),
        "requires_approval": bool(node.get("requires_approval", False)),
    }


def test_generated_files_are_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_annotation_schema_is_a_valid_schema(schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)


def test_annotation_schema_lists_the_ontology(
    schema: dict[str, Any], ontology: dict[str, Any]
) -> None:
    properties = schema["properties"]
    assert properties["capability"]["enum"] == [n["id"] for n in ontology["nodes"]]
    assert properties["layer"]["enum"] == list(ontology["layers"])


def test_every_capability_has_a_valid_annotation(
    schema: dict[str, Any], ontology: dict[str, Any]
) -> None:
    validator = Draft202012Validator(schema)
    for node in ontology["nodes"]:
        errors = list(validator.iter_errors(annotation(ontology, node["id"])))
        assert not errors, (node["id"], [e.message for e in errors])


@pytest.mark.parametrize(
    "change",
    [
        {"capability": "detect-anomaly"},
        {"risk": "critical"},
        {"requires_checkpoint": "yes"},
        {"domain": ""},
        {"unknown_field": 1},
    ],
)
def test_annotation_schema_rejects(
    schema: dict[str, Any], ontology: dict[str, Any], change: dict[str, Any]
) -> None:
    bad = {**annotation(ontology, "mutate"), **change}
    assert list(Draft202012Validator(schema).iter_errors(bad))


def test_annotation_schema_requires_the_safety_flags(
    schema: dict[str, Any], ontology: dict[str, Any]
) -> None:
    for flag in ("risk", "mutation", "requires_checkpoint", "requires_approval"):
        partial = annotation(ontology, "mutate")
        del partial[flag]
        assert list(Draft202012Validator(schema).iter_errors(partial)), flag
