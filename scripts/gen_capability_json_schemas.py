"""Generate a strict JSON Schema rendering of the ontology's capability contracts.

schemas/capability_ontology.yaml writes each capability's `input_schema` and
`output_schema` in the ACS schema dialect (STANDARD v1.2 §4.1.2): Draft
2020-12 keywords, plus `type: any`, a union written `type: a|b`, `$ref` with
the keywords beside it merged over its target, `nullable`, and `x-`
annotations. This script renders the contracts as one Draft 2020-12
document, schemas/generated/capability_contracts.schema.json, whose `$defs`
holds `<capability>.input` and `<capability>.output` for every capability.
The ontology stays the source: the rendering is for tools that read JSON
Schema, and nothing in this repository reads a contract from it.

It renders the contracts the reference core resolved
(`_core.Validator(...).contracts()`), the ones validation and the executor
read, so no `$ref` reaches the renderer; one that did not resolve is an
error. The rules of §4.1.2:

- `type: a|b` becomes `type: ["a", "b"]`, which admits the same values. A
  union with `null` is outside the dialect and an error.
- `type: any` becomes a schema with no `type` and the keyword
  `"x-acs-type": "any"`. A schema with no `type` accepts every JSON value,
  which is what `any` admits. `any` may stand only beside annotations
  (`description`, `title`, `default`, `examples`, `nullable`, `x-` keys), so
  the rendering cannot accept less than the dialect. The keyword records that
  the ontology wrote `any`, so the slot stays apart from one where the
  ontology states no type (the "missing type metadata" of §5.4). Draft 2020-12
  says an implementation SHOULD treat a keyword it does not know as an
  annotation (JSON Schema Core §4.3.1 and §6.5), so the keyword asserts
  nothing; Appendix B reserves `x-acs-` keys for this Standard.
- `nullable: true` adds `"null"` to the rendered `type` (making a list of a
  single name; nothing where there is no `type`) and is dropped; `nullable:
  false` is dropped.
- Every other keyword of the dialect means there what it means in Draft
  2020-12 and is carried over unchanged, in the contract's order; `x-` keys
  are carried as they are; `properties`, `items`, `additionalProperties` and
  the schema lists are rendered recursively. A keyword this script does not
  know is an error, not a pass-through.

The rendering accepts exactly the values the dialect accepts. It is not
type-identical for §5.4: the reference validator reads a rendered
`["t", "null"]` as nullable but ignores the dialect's `nullable: true`
(STANDARD v1.2 §4.1.2), so a reference to such a member can be W610 against
the rendering and not against the ontology. `render_contracts` and
`render_schema` take `nullable_as_null=False` to drop `nullable` without
adding `"null"`; the published document never does, and only the test that
compares the two readings uses it.

An object schema is left open, as the ontology writes it. For an output, the
reference executor fails a step whose output lacks a field its contract
requires (R402, docs/guides/RUNNING_WORKFLOWS.md) and accepts other fields.
For an input, a binding key the contract does not define is a warning and
the host still receives it (W604, STANDARD v1.1.0 §5.5). The rule that a
reference names a declared property (§5.4, "Paths") is a rule on references
in a workflow, not on values.

    python scripts/gen_capability_json_schemas.py          # write the file
    python scripts/gen_capability_json_schemas.py --check  # fail if it differs (CI)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from grounded_agency import _core

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
# The root the ontology's `$ref`s are resolved from (the repository root).
SCHEMA_ROOT = ROOT
OUT = ROOT / "schemas" / "generated" / "capability_contracts.schema.json"
ME = "scripts/gen_capability_json_schemas.py"

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ID = (
    "https://github.com/synaptiai/agent-capability-standard/"
    "schemas/generated/capability_contracts.schema.json"
)

# The Draft 2020-12 primitive type names.
JSON_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)
# The keyword that records `type: any`, and the two values `type` takes in the
# ontology that Draft 2020-12 does not define: `any` and the `a|b` shorthand.
ANY_KEYWORD = "x-acs-type"
ANY = "any"
UNION_SEPARATOR = "|"

# Keywords that assert nothing about a value, beside which `type: any` may
# stand, and the others whose value is carried over as it is.
ANNOTATIONS = frozenset({"default", "description", "examples", "title"})
CARRIED = ANNOTATIONS | {
    "const",
    "enum",
    "format",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "pattern",
    "required",
    "uniqueItems",
}
# Keywords holding a list of schemas, which the reference validator also reads
# (`schema_type` in core/src/types.rs).
SCHEMA_LISTS = frozenset({"allOf", "anyOf", "oneOf"})
NULLABLE = "nullable"
VENDOR_PREFIX = "x-"


class RenderError(ValueError):
    """The ontology holds something this script has no rendering for."""


def render_type(value: Any, where: str) -> dict[str, Any]:
    """The Draft 2020-12 keywords for one `type` value of the dialect."""
    if value == ANY:
        return {ANY_KEYWORD: ANY}
    rendered: str | list[Any]
    if isinstance(value, str) and UNION_SEPARATOR in value:
        # The validator trims the names of a union.
        rendered = [name.strip() for name in value.split(UNION_SEPARATOR)]
        if "null" in rendered:
            raise RenderError(
                f"{where}: {value!r} is a union with null, outside the dialect;"
                " write nullable: true"
            )
    elif isinstance(value, (str, list)) and value:
        rendered = value
    else:
        raise RenderError(f"{where}: {value!r} is not a type name or a list of them")
    names = [rendered] if isinstance(rendered, str) else rendered
    unknown = [n for n in names if not isinstance(n, str) or n not in JSON_TYPES]
    if unknown:
        raise RenderError(
            f"{where}: {value!r} names {unknown}, which Draft 2020-12 does not define"
        )
    if len(set(names)) != len(names):
        raise RenderError(f"{where}: {value!r} names a type twice")
    return {"type": rendered}


def with_null(rendered: dict[str, Any]) -> dict[str, Any]:
    """`nullable: true` rendered: `"null"` added to the schema's `type`."""
    kind = rendered.get("type")
    if kind is None:
        return rendered
    names = [kind] if isinstance(kind, str) else list(kind)
    if "null" not in names:
        names.append("null")
    return {**rendered, "type": names}


def render_schema(
    schema: Any, where: str, *, nullable_as_null: bool = True
) -> dict[str, Any]:
    """One schema of the dialect as a Draft 2020-12 schema."""
    if not isinstance(schema, dict):
        raise RenderError(f"{where}: a schema must be a mapping, not {schema!r}")
    if schema.get("type") == ANY:
        # `any` is rendered as a schema that accepts every value, which it
        # would not be beside a keyword that constrains the value.
        asserting = sorted(
            key
            for key in set(schema) - ANNOTATIONS - {"type", NULLABLE}
            if not key.startswith(VENDOR_PREFIX)
        )
        if asserting:
            raise RenderError(f"{where}: `type: any` beside {asserting}")

    def sub(value: Any, at: str) -> dict[str, Any]:
        return render_schema(value, at, nullable_as_null=nullable_as_null)

    out: dict[str, Any] = {}
    nullable = False
    for key, value in schema.items():
        at = f"{where}/{key}"
        if key == "type":
            out.update(render_type(value, at))
        elif key == "$ref":
            raise RenderError(f"{at}: {value!r} did not resolve")
        elif key == NULLABLE:
            if not isinstance(value, bool):
                raise RenderError(f"{at}: must be true or false, not {value!r}")
            nullable = value
        elif key == "properties":
            if not isinstance(value, dict):
                raise RenderError(f"{at}: must be a mapping")
            out[key] = {name: sub(s, f"{at}/{name}") for name, s in value.items()}
        elif key == "items":
            out[key] = sub(value, at)
        elif key == "additionalProperties":
            out[key] = value if isinstance(value, bool) else sub(value, at)
        elif key in SCHEMA_LISTS:
            if not isinstance(value, list) or not value:
                raise RenderError(f"{at}: must be a list of schemas")
            out[key] = [sub(s, f"{at}/{i}") for i, s in enumerate(value)]
        elif key in CARRIED or key.startswith(VENDOR_PREFIX):
            out[key] = value
        else:
            raise RenderError(
                f"{at}: no rendering is defined for this keyword; add one to {ME}"
            )
    return with_null(out) if nullable and nullable_as_null else out


def render_contracts(
    ontology: dict[str, Any],
    contracts: dict[str, Any],
    *,
    nullable_as_null: bool = True,
) -> dict[str, Any]:
    """`<capability>.input` and `<capability>.output` for every node of the
    ontology, rendered from its resolved contracts (`contracts()` of the
    core)."""
    defs: dict[str, Any] = {}
    for node in ontology["nodes"]:
        resolved = contracts.get(node["id"]) or {}
        for side in ("input", "output"):
            name = f"{node['id']}.{side}"
            if name in defs:
                raise RenderError(f"{name}: defined twice")
            if not isinstance(node.get(f"{side}_schema"), dict):
                raise RenderError(f"{name}: the ontology gives no {side}_schema")
            defs[name] = render_schema(
                resolved.get(side), name, nullable_as_null=nullable_as_null
            )
    return defs


def render_document(ontology: dict[str, Any], contracts: dict[str, Any]) -> str:
    version = str(ontology["meta"]["version"])
    defs = render_contracts(ontology, contracts)
    document = {
        "$schema": DIALECT,
        "$id": ID,
        "$comment": (
            f"Generated from schemas/capability_ontology.yaml (ontology {version}) "
            f"by {ME}. Do not edit: change the ontology and run that script."
        ),
        "title": f"Capability contracts of ontology {version}",
        "description": (
            "The input and output contract of each capability in the Agent "
            "Capability Standard ontology, rendered as JSON Schema Draft "
            "2020-12 by the rules of STANDARD v1.2 §4.1.2. `$defs` holds "
            "`<capability>.input` and `<capability>.output`; the document "
            "itself constrains nothing. The ontology writes its contracts in "
            "the ACS schema dialect: `$ref`s are rendered as their merged "
            "targets, a union `a|b` as a type list, `nullable: true` as "
            '`"null"` in the type list, and `type: any` as a schema with no '
            f'`type` and the keyword `"{ANY_KEYWORD}": "{ANY}"`, which accepts '
            "every value. A schema with neither `type` nor that keyword is one "
            "whose type the ontology does not state. Objects are open: a "
            "contract lists the fields it requires and does not forbid others."
        ),
        "$defs": defs,
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the file on disk differs"
    )
    check = parser.parse_args(argv).check
    try:
        contracts = _core.Validator(str(ONTOLOGY), str(SCHEMA_ROOT)).contracts()
        text = render_document(_core.load_yaml(str(ONTOLOGY)), contracts)
    except RenderError as error:
        print(f"{ONTOLOGY.relative_to(ROOT)}: {error}")
        return 1
    stale = not OUT.exists() or OUT.read_text(encoding="utf-8") != text
    if check:
        if stale:
            print(f"out of date: {OUT.relative_to(ROOT)}")
            print(f"run: python {ME}")
            return 1
        print(f"{OUT.relative_to(ROOT)} up to date")
        return 0
    if stale:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} ({'written' if stale else 'unchanged'})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
