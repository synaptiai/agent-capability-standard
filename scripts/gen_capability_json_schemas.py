"""Generate a strict JSON Schema rendering of the ontology's capability contracts.

schemas/capability_ontology.yaml writes each capability's `input_schema` and
`output_schema` in a dialect of JSON Schema with two spellings that Draft
2020-12 does not have: `type: any`, and a union written `type: a|b`. This
script renders the contracts as one Draft 2020-12 document,
schemas/generated/capability_contracts.schema.json, whose `$defs` holds
`<capability>.input` and `<capability>.output` for every capability. The
ontology stays the source: the rendering is for tools that read JSON Schema,
and nothing in this repository reads a contract from it.

The rendering follows the reference validator's reading of the dialect. The
core reads a schema's `type` in three places: `schema_type` in
core/src/types.rs (binding types), `type_names` in core/src/schema.rs
(paths) and `schema_kinds` in core/src/expr/check.rs (expressions).

- `type: a|b` becomes `type: ["a", "b"]`, which admits the same values. The
  validator reads both as the same union, unless a member is `null`, where
  `schema_type` reads the two spellings differently; the ontology writes no
  union with `null`.
- `type: any` becomes a schema with no `type` and the keyword
  `"x-acs-type": "any"`. A schema with no `type` accepts every JSON value,
  which is what `any` admits, and the validator reads `any` as it reads a
  schema that states no type and holds no keyword it could infer one from
  (`properties`, `items`, `enum` and the like). `type: any` beside any
  keyword but `description` and `default` is refused here, so the two
  readings cannot part. The keyword records that the ontology wrote
  `any`, so the slot stays apart from one where the ontology states no type
  (the "missing type metadata" of STANDARD v1.1.0 §5.4 rule 3). Draft 2020-12
  says an implementation SHOULD treat a keyword it does not know as an
  annotation (JSON Schema Core §4.3.1 and §6.5), so the keyword asserts
  nothing; a tool that refuses unknown keywords has to be told about it. The
  `x-` prefix marks the keyword as an extension, as the Standard marks
  vendor fields (Appendix B).
- Every other keyword the ontology uses means there what it means in Draft
  2020-12 and is carried over unchanged, in the ontology's order;
  `properties` and `items` are rendered recursively. A keyword this script
  does not know is an error, not a pass-through.

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

# Keywords that assert nothing about a value, and the others whose value is
# carried over as it is.
ANNOTATIONS = frozenset({"default", "description"})
CARRIED = ANNOTATIONS | {"enum", "format", "maximum", "minimum", "required"}
# Keywords holding a list of schemas, which the reference validator also reads
# (`schema_type` in core/src/types.rs). Like `additionalProperties`, which it
# reads there and in core/src/schema.rs, the ontology uses none of them today.
SCHEMA_LISTS = frozenset({"allOf", "anyOf", "oneOf"})


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


def render_schema(schema: Any, where: str) -> dict[str, Any]:
    """One schema of the dialect as a Draft 2020-12 schema."""
    if not isinstance(schema, dict):
        raise RenderError(f"{where}: a schema must be a mapping, not {schema!r}")
    if schema.get("type") == ANY:
        # `any` is rendered as a schema that accepts every value, which it
        # would not be beside a keyword that constrains the value.
        asserting = sorted(set(schema) - ANNOTATIONS - {"type"})
        if asserting:
            raise RenderError(f"{where}: `type: any` beside {asserting}")
    out: dict[str, Any] = {}
    for key, value in schema.items():
        at = f"{where}/{key}"
        if key == "type":
            out.update(render_type(value, at))
        elif key == "properties":
            if not isinstance(value, dict):
                raise RenderError(f"{at}: must be a mapping")
            out[key] = {
                name: render_schema(sub, f"{at}/{name}") for name, sub in value.items()
            }
        elif key == "items":
            out[key] = render_schema(value, at)
        elif key == "additionalProperties":
            out[key] = value if isinstance(value, bool) else render_schema(value, at)
        elif key in SCHEMA_LISTS:
            if not isinstance(value, list) or not value:
                raise RenderError(f"{at}: must be a list of schemas")
            out[key] = [render_schema(sub, f"{at}/{i}") for i, sub in enumerate(value)]
        elif key in CARRIED:
            out[key] = value
        else:
            raise RenderError(
                f"{at}: no rendering is defined for this keyword; add one to {ME}"
            )
    return out


def render_document(ontology: dict[str, Any]) -> str:
    version = str(ontology["meta"]["version"])
    defs: dict[str, Any] = {}
    for node in ontology["nodes"]:
        for side in ("input", "output"):
            name = f"{node['id']}.{side}"
            if name in defs:
                raise RenderError(f"{name}: defined twice")
            defs[name] = render_schema(node.get(f"{side}_schema"), name)
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
            "2020-12. `$defs` holds `<capability>.input` and "
            "`<capability>.output`; the document itself constrains nothing. "
            "The ontology writes `type: any`, and writes a union as `a|b`. A "
            "union is rendered as a type list. `any` is rendered as a schema "
            "with no `type`, which accepts every value, and the keyword "
            f'`"{ANY_KEYWORD}": "{ANY}"`. A schema with neither `type` nor '
            "that keyword is one whose type the ontology does not state. "
            "Objects are open: a contract lists the fields it requires and "
            "does not forbid others."
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
        text = render_document(_core.load_yaml(str(ONTOLOGY)))
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
