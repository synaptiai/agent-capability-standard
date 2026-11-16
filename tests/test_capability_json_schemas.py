"""The strict JSON Schema rendering of the capability contracts.

schemas/generated/capability_contracts.schema.json is generated from the
ontology's resolved contracts by scripts/gen_capability_json_schemas.py
(STANDARD v1.2 §4.1.2). Checked here: the file is the generator's output, it
is valid Draft 2020-12, it says what the contracts say, example outputs
validate against it, and the reference validator reads it as it reads the
ontology's own spelling (with `nullable` left out of the comparison, the one
divergence §4.1.2 states).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from grounded_agency import _core

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen_capability_json_schemas.py"
DOCUMENT = ROOT / "schemas" / "generated" / "capability_contracts.schema.json"
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
FIXTURES = ROOT / "tests" / "fixtures"

spec = importlib.util.spec_from_file_location("gen_capability_json_schemas", SCRIPT)
assert spec and spec.loader
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

# Every keyword the rendering may hold: the Draft 2020-12 keywords of the
# dialect (STANDARD v1.2 §4.1.2), and the one that records `type: any`.
KEYWORDS = {
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "default",
    "description",
    "enum",
    "examples",
    "format",
    "items",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "oneOf",
    "pattern",
    "properties",
    "required",
    "title",
    "type",
    "uniqueItems",
    "x-acs-type",
}


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    return loaded


@pytest.fixture(scope="module")
def ontology() -> dict[str, Any]:
    loaded: dict[str, Any] = _core.load_yaml(str(ONTOLOGY))
    return loaded


@pytest.fixture(scope="module")
def contracts() -> dict[str, Any]:
    """The contracts the reference core resolved, which the generator renders."""
    resolved: dict[str, Any] = _core.Validator(str(ONTOLOGY), str(ROOT)).contracts()
    return resolved


def nodes(schema: dict[str, Any], path: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """A rendered schema and every schema below it, each with its path."""
    yield path, schema
    for name, sub in schema.get("properties", {}).items():
        yield from nodes(sub, f"{path}/properties/{name}")
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            yield from nodes(schema[key], f"{path}/{key}")
    for key in ("allOf", "anyOf", "oneOf"):
        for i, sub in enumerate(schema.get(key, [])):
            yield from nodes(sub, f"{path}/{key}/{i}")


def all_nodes(document: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for name, schema in document["$defs"].items():
        yield from nodes(schema, name)


def as_written(schema: dict[str, Any]) -> dict[str, Any]:
    """The dialect's spelling of a schema rendered without `nullable`: the
    `any` and `a|b` rules undone."""
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "x-acs-type":
            out["type"] = value
        elif key == "type" and isinstance(value, list):
            out["type"] = "|".join(value)
        elif key == "properties":
            out[key] = {name: as_written(sub) for name, sub in value.items()}
        elif key in ("items", "additionalProperties") and isinstance(value, dict):
            out[key] = as_written(value)
        elif key in ("allOf", "anyOf", "oneOf"):
            out[key] = [as_written(sub) for sub in value]
        else:
            out[key] = value
    return out


def without_nullable(schema: Any) -> Any:
    """A contract with every `nullable` member dropped."""
    if isinstance(schema, dict):
        return {k: without_nullable(v) for k, v in schema.items() if k != "nullable"}
    if isinstance(schema, list):
        return [without_nullable(v) for v in schema]
    return schema


def nullable_nodes(schema: Any, path: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every schema under a contract that says `nullable: true`."""
    if isinstance(schema, dict):
        if schema.get("nullable") is True:
            yield path, schema
        for key, value in schema.items():
            yield from nullable_nodes(value, f"{path}/{key}")
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            yield from nullable_nodes(value, f"{path}/{i}")


def at(document: dict[str, Any], path: str) -> dict[str, Any]:
    """The rendered schema at a contract path (`<name>/<key>/...`)."""
    name, *keys = path.split("/")
    node: Any = document["$defs"][name]
    for key in keys:
        node = node[int(key)] if isinstance(node, list) else node[key]
    assert isinstance(node, dict)
    return node


def contract(document: dict[str, Any], name: str) -> Draft202012Validator:
    """A validator for one contract, addressed as a consumer addresses it."""
    return Draft202012Validator({**document, "$ref": f"#/$defs/{name}"})


# --- The file --------------------------------------------------------------


def test_generated_file_is_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_document_is_valid_draft_2020_12(document: dict[str, Any]) -> None:
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert document["$id"].endswith(
        "/schemas/generated/capability_contracts.schema.json"
    )
    # The metaschema applies to every schema under `$defs` as well.
    Draft202012Validator.check_schema(document)


@pytest.mark.parametrize("spelling", ["any", "string|object"])
def test_the_metaschema_rejects_the_ontology_spellings(spelling: str) -> None:
    with pytest.raises(SchemaError):
        Draft202012Validator.check_schema({"$defs": {"x": {"type": spelling}}})


def test_comment_names_the_source_and_its_version(
    document: dict[str, Any], ontology: dict[str, Any]
) -> None:
    comment = document["$comment"]
    assert "schemas/capability_ontology.yaml" in comment
    assert f"(ontology {ontology['meta']['version']})" in comment
    assert "scripts/gen_capability_json_schemas.py" in comment


# --- What it says ----------------------------------------------------------


def test_every_capability_has_both_contracts(
    document: dict[str, Any], ontology: dict[str, Any]
) -> None:
    expected = [
        f"{node['id']}.{side}"
        for node in ontology["nodes"]
        for side in ("input", "output")
    ]
    assert list(document["$defs"]) == expected


def test_only_known_keywords(document: dict[str, Any]) -> None:
    unknown = {
        f"{path}: {key}"
        for path, node in all_nodes(document)
        for key in node
        if key not in KEYWORDS
    }
    assert not unknown


def test_any_is_marked_and_untyped(document: dict[str, Any]) -> None:
    marked = [node for _, node in all_nodes(document) if "x-acs-type" in node]
    assert marked
    for node in marked:
        assert node["x-acs-type"] == "any"
        assert set(node) <= {"x-acs-type", "description", "default"}


def test_required_fields_are_declared_properties(document: dict[str, Any]) -> None:
    undeclared = {
        f"{path}: {name}"
        for path, node in all_nodes(document)
        if "properties" in node
        for name in node.get("required", [])
        if name not in node["properties"]
    }
    assert not undeclared


def test_document_renders_the_resolved_contracts(
    document: dict[str, Any], ontology: dict[str, Any], contracts: dict[str, Any]
) -> None:
    assert document["$defs"] == gen.render_contracts(ontology, contracts)


def test_rendering_differs_from_the_contracts_only_in_type(
    ontology: dict[str, Any], contracts: dict[str, Any]
) -> None:
    rendered = gen.render_contracts(ontology, contracts, nullable_as_null=False)
    for node in ontology["nodes"]:
        for side in ("input", "output"):
            name = f"{node['id']}.{side}"
            # Compared as text, so the order of the keywords counts too.
            assert json.dumps(as_written(rendered[name])) == json.dumps(
                without_nullable(contracts[node["id"]][side])
            ), name
    # Both rules were exercised: the ontology uses both spellings.
    types = [n.get("type") for name in rendered for _, n in nodes(rendered[name], name)]
    assert any(isinstance(t, list) for t in types)
    assert any(
        "x-acs-type" in n for name in rendered for _, n in nodes(rendered[name], name)
    )


def test_no_dialect_spelling_is_left(document: dict[str, Any]) -> None:
    text = json.dumps(document)
    assert '"$ref"' not in text
    assert '"nullable"' not in text
    for path, node in all_nodes(document):
        kind = node.get("type")
        names = kind if isinstance(kind, list) else [kind] if kind else []
        assert all(n in gen.JSON_TYPES for n in names), path


def test_nullable_members_admit_null(
    document: dict[str, Any], contracts: dict[str, Any]
) -> None:
    found = [
        (path, schema)
        for cap, sides in contracts.items()
        for side, contract in sides.items()
        for path, schema in nullable_nodes(contract, f"{cap}.{side}")
    ]
    # The canonical Anchor and Uncertainty the contracts reach have some.
    assert found
    for path, schema in found:
        rendered = at(document, path)
        if "type" in schema:
            assert "null" in rendered["type"], path


# --- Values ----------------------------------------------------------------

EXAMPLE_OUTPUTS: dict[str, dict[str, Any]] = {
    "retrieve": {
        "data": {"timeout_s": 30},
        "evidence_anchors": ["file:config/app.yaml:12"],
        "confidence": 0.9,
    },
    "mutate": {
        "success": True,
        "previous_state": {"timeout_s": 30},
        "new_state": {"timeout_s": 60},
        "evidence_anchors": ["file:config/app.yaml:12"],
    },
    "checkpoint": {
        "checkpoint_id": "cp-1",
        "timestamp": "2026-11-14T10:00:00Z",
        "size": 2048,
        "evidence_anchors": ["checkpoint:cp-1"],
    },
}


@pytest.mark.parametrize("capability", sorted(EXAMPLE_OUTPUTS))
def test_example_output_validates(document: dict[str, Any], capability: str) -> None:
    contract(document, f"{capability}.output").validate(EXAMPLE_OUTPUTS[capability])


@pytest.mark.parametrize("capability", sorted(EXAMPLE_OUTPUTS))
def test_output_without_evidence_anchors_fails(
    document: dict[str, Any], capability: str
) -> None:
    output = dict(EXAMPLE_OUTPUTS[capability])
    del output["evidence_anchors"]
    errors = list(contract(document, f"{capability}.output").iter_errors(output))
    assert [e.validator for e in errors] == ["required"]
    assert "evidence_anchors" in errors[0].message


@pytest.mark.parametrize("value", [None, True, 3, 1.5, "text", [1], {"a": 1}])
def test_any_accepts_every_value(document: dict[str, Any], value: Any) -> None:
    output = {**EXAMPLE_OUTPUTS["mutate"], "previous_state": value}
    assert contract(document, "mutate.output").is_valid(output)


def test_union_accepts_its_members_only(document: dict[str, Any]) -> None:
    # `transform.output.output` is `object|array` in the ontology.
    validator = contract(document, "transform.output")
    base = {"evidence_anchors": [], "confidence": 1}
    assert validator.is_valid({**base, "output": {"rows": 2}})
    assert validator.is_valid({**base, "output": [{"id": 1}]})
    errors = list(validator.iter_errors({**base, "output": "rows"}))
    assert [e.validator for e in errors] == ["type"]


def test_bounds_and_open_objects(document: dict[str, Any]) -> None:
    validator = contract(document, "retrieve.output")
    output = EXAMPLE_OUTPUTS["retrieve"]
    errors = list(validator.iter_errors({**output, "confidence": 1.5}))
    assert [e.validator for e in errors] == ["maximum"]
    # A contract requires fields; it does not forbid others.
    assert validator.is_valid({**output, "retrieved_by": "cache"})


@pytest.mark.parametrize(
    "items",
    [
        [{"ref": "file:a.txt", "kind": "file"}],
        [{"ref": "file:a.txt", "kind": "file", "digest": "sha256:" + "0" * 64}],
        # The deprecated legacy forms (STANDARD v1.2 §6.5) are accepted.
        ["file:a.txt"],
        [{"ref": "file:a.txt"}],
        [{"ref": "tool:Read:1", "kind": "tool_output"}],
    ],
)
def test_anchor_items_and_the_legacy_forms(
    document: dict[str, Any], items: list[Any]
) -> None:
    output = {**EXAMPLE_OUTPUTS["retrieve"], "evidence_anchors": items}
    assert contract(document, "retrieve.output").is_valid(output)


@pytest.mark.parametrize("item", [1, True, None, ["file:a"]])
def test_an_item_that_names_no_evidence_is_outside_the_contract(
    document: dict[str, Any], item: Any
) -> None:
    output = {**EXAMPLE_OUTPUTS["retrieve"], "evidence_anchors": [item]}
    assert not contract(document, "retrieve.output").is_valid(output)


def test_common_output_fields(document: dict[str, Any]) -> None:
    """Any string inference_method is valid against the contract (the
    vocabulary is enforced only under a grounding policy); an uncertainty
    must have its type (STANDARD v1.2 §4.1.1)."""
    validator = contract(document, "mutate.output")
    output = EXAMPLE_OUTPUTS["mutate"]
    assert validator.is_valid({**output, "inference_method": "llm-reasoning"})
    assert validator.is_valid(
        {
            **output,
            "confidence": 0.4,
            "uncertainty": {"type": "epistemic", "confidence": 0.4},
        }
    )
    assert not validator.is_valid({**output, "uncertainty": {"confidence": 0.4}})
    assert not validator.is_valid({**output, "confidence": 1.5})


# --- The reference validator's reading -------------------------------------


@pytest.fixture(scope="module")
def strict_ontology(
    tmp_path_factory: pytest.TempPathFactory,
    ontology: dict[str, Any],
    contracts: dict[str, Any],
) -> Path:
    """The ontology with each contract replaced by its strict rendering,
    without the `"null"` that `nullable` adds: §5.4 reads one and not the
    other (STANDARD v1.2 §4.1.2), so the comparison below would part on it."""
    rendered = gen.render_contracts(ontology, contracts, nullable_as_null=False)
    strict = copy.deepcopy(ontology)
    for node in strict["nodes"]:
        for side in ("input", "output"):
            node[f"{side}_schema"] = rendered[f"{node['id']}.{side}"]
    path = tmp_path_factory.mktemp("strict") / "capability_ontology.yaml"
    # JSON is YAML, and the core's loader reads it.
    path.write_text(json.dumps(strict, ensure_ascii=False), encoding="utf-8")
    return path


def transform(
    store_as: str, reference: str, condition: str | None = None
) -> dict[str, Any]:
    """A step whose input is of type `any`, so only the reference is checked."""
    step: dict[str, Any] = {
        "capability": "transform",
        "purpose": "Read one reference.",
        "store_as": store_as,
        "input_bindings": {"input": reference, "target_format": "json"},
    }
    if condition is not None:
        step["condition"] = condition
    return step


# References into `retrieve.output.data` (`any`) and `transform.output.output`
# (`object|array`), and the diagnostic the reference validator gives each.
PROBES: list[tuple[str, str | None]] = [
    ("${t.output}", "B204"),  # a union needs an annotation
    ("${t.output: object}", None),
    ("${t.output[0].title: string}", None),  # the array member
    ("${r.data}", "B204"),  # `any` needs one too
    ("${r.data: object}", None),
    ("${r.data.rows[0].title: string}", None),  # `any` is open below
    ("${r.confidence.value: string}", "B201"),  # a number is not
]
# The same two slots in a condition, where the validator reads the kinds a
# schema admits (`schema_kinds` in core/src/expr/check.rs).
CONDITION_PROBES: list[tuple[str, str | None]] = [
    ("${r.data} > 1", "B204"),  # ordering needs a known type
    ("${r.data: number} > 1", None),
    ("${t.output} > 1", "B206"),  # neither member of the union can be ordered
    ("${t.output} == 1", "W611"),  # and neither is a number
]


def probe_catalog() -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "capability": "retrieve",
            "purpose": "Produce a value of type any.",
            "store_as": "r",
            "input_bindings": {"target": "config"},
        },
        transform("t", "${r.data: object}"),
    ]
    steps += [transform(f"p{i}", reference) for i, (reference, _) in enumerate(PROBES)]
    steps += [
        transform(f"c{i}", "constant", condition)
        for i, (condition, _) in enumerate(CONDITION_PROBES)
    ]
    return {"probe": {"goal": "Read typed slots.", "risk": "low", "steps": steps}}


@pytest.fixture(scope="module")
def validators(strict_ontology: Path) -> tuple[Any, Any]:
    """The reference validator on the ontology, and on its strict rendering."""
    return (
        _core.Validator(str(ONTOLOGY), str(ROOT)),
        _core.Validator(str(strict_ontology), str(ROOT)),
    )


def test_reference_validator_reads_any_and_unions_alike(
    validators: tuple[Any, Any],
) -> None:
    dialect, strict = validators
    report = dialect.validate(probe_catalog(), "1.1.0")
    assert strict.validate(probe_catalog(), "1.1.0") == report
    found = {d["location"]["step"]: d["code"] for d in report["diagnostics"]}
    # The probes follow the two steps that produce the values.
    expected = [code for _, code in PROBES + CONDITION_PROBES]
    assert found == {i + 2: code for i, code in enumerate(expected) if code}


def test_reference_validator_reports_alike_on_every_fixture(
    validators: tuple[Any, Any],
) -> None:
    dialect, strict = validators
    catalogs = [
        ROOT / "schemas" / "workflow_catalog.yaml",
        *sorted((ROOT / "schemas" / "workflows").glob("*.yaml")),
        *sorted((ROOT / "examples").glob("*.workflow_catalog.yaml")),
        *sorted(FIXTURES.glob("*.workflow_catalog.yaml")),
    ]
    codes: set[str] = set()
    for catalog in catalogs:
        # Diagnostics and suggestions, messages included.
        report = dialect.validate_file(str(catalog))
        assert strict.validate_file(str(catalog)) == report, catalog.name
        codes.update(d["code"] for d in report["diagnostics"])
    # The fixtures include the binding checks that read the contracts.
    assert {"B201", "B203", "B204"} <= codes


# --- The generator ---------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "rendered"),
    [
        ("string", {"type": "string"}),
        ("string|object", {"type": ["string", "object"]}),
        ("object | array", {"type": ["object", "array"]}),
        (["string", "null"], {"type": ["string", "null"]}),
        ("any", {"x-acs-type": "any"}),
    ],
)
def test_render_type(written: Any, rendered: dict[str, Any]) -> None:
    assert gen.render_type(written, "t") == rendered


@pytest.mark.parametrize(
    "written", ["banana", "string|banana", "string|any", "string|string", "", [], 3]
)
def test_render_type_refuses_what_it_cannot_render(written: Any) -> None:
    with pytest.raises(gen.RenderError):
        gen.render_type(written, "t")


def test_render_schema_recurses() -> None:
    written = {
        "type": "object",
        "required": ["rows"],
        "properties": {
            "rows": {
                "type": "array",
                "items": {"type": "string|object", "description": "A row"},
            },
            "extra": {"type": "object", "additionalProperties": {"type": "any"}},
            "open": {"type": "object", "additionalProperties": True},
            "either": {"oneOf": [{"type": "any"}, {"type": "object|array"}]},
        },
    }
    assert gen.render_schema(written, "s") == {
        "type": "object",
        "required": ["rows"],
        "properties": {
            "rows": {
                "type": "array",
                "items": {"type": ["string", "object"], "description": "A row"},
            },
            "extra": {
                "type": "object",
                "additionalProperties": {"x-acs-type": "any"},
            },
            "open": {"type": "object", "additionalProperties": True},
            "either": {"oneOf": [{"x-acs-type": "any"}, {"type": ["object", "array"]}]},
        },
    }


@pytest.mark.parametrize(
    ("written", "rendered"),
    [
        ({"type": "string", "nullable": True}, {"type": ["string", "null"]}),
        ({"type": ["string", "null"], "nullable": True}, {"type": ["string", "null"]}),
        (
            {"type": "object|array", "nullable": True},
            {"type": ["object", "array", "null"]},
        ),
        ({"type": "string", "nullable": False}, {"type": "string"}),
        ({"nullable": True, "description": "d"}, {"description": "d"}),
        ({"type": "any", "nullable": True}, {"x-acs-type": "any"}),
        (
            {"type": "any", "title": "t", "x-note": 1},
            {"x-acs-type": "any", "title": "t", "x-note": 1},
        ),
        (
            {"type": "string", "pattern": "^a$", "minLength": 1, "const": "a"},
            {"type": "string", "pattern": "^a$", "minLength": 1, "const": "a"},
        ),
    ],
)
def test_render_schema_dialect_keywords(written: Any, rendered: Any) -> None:
    assert gen.render_schema(written, "s") == rendered


def test_nullable_as_null_off_drops_nullable() -> None:
    written = {
        "type": "object",
        "properties": {"n": {"type": "number", "nullable": True}},
    }
    assert gen.render_schema(written, "s", nullable_as_null=False) == {
        "type": "object",
        "properties": {"n": {"type": "number"}},
    }


@pytest.mark.parametrize(
    "written",
    [
        {"type": "string", "nullable": "yes"},  # nullable is a boolean
        {"type": "string|null"},  # a union with null is outside the dialect
        {"$ref": "schemas/nowhere.yaml#/X"},  # a $ref the core did not resolve
        {"type": "any", "enum": [1, 2]},  # `any` that would not accept every value
        {"type": "any", "minimum": 0},
        {"type": "string", "unknownKeyword": 1},  # a keyword with no rendering
        {"type": "object", "properties": {"a": "string"}},
        {"type": "object", "properties": ["a"]},
        {"oneOf": []},
        "string",
    ],
)
def test_render_schema_refuses_what_it_cannot_render(written: Any) -> None:
    with pytest.raises(gen.RenderError):
        gen.render_schema(written, "s")


def test_a_capability_without_a_contract_is_an_error() -> None:
    ontology = {
        "meta": {"version": "0.0.0"},
        "nodes": [{"id": "retrieve", "input_schema": {"type": "object"}}],
    }
    contracts = {"retrieve": {"input": {"type": "object"}}}
    with pytest.raises(gen.RenderError, match="retrieve.output"):
        gen.render_document(ontology, contracts)


def test_check_fails_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]
) -> None:
    out = tmp_path / "generated" / "capability_contracts.schema.json"
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    monkeypatch.setattr(gen, "OUT", out)
    assert gen.main(["--check"]) == 1  # no file
    assert gen.main([]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == document
    assert gen.main(["--check"]) == 0
    written = out.read_text(encoding="utf-8")
    drifted = written.replace('"x-acs-type": "any"', '"type": "object"', 1)
    assert drifted != written
    out.write_text(drifted, encoding="utf-8")
    assert gen.main(["--check"]) == 1
    # Writing again restores the file.
    assert gen.main([]) == 0
    assert gen.main(["--check"]) == 0
