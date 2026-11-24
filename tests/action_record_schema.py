"""`ActionRecord` of `schemas/world_state_schema.yaml` as JSON Schema 2020-12,
for the tests that check audit records (STANDARD v1.2 §6.4) against it.

The canonical schema is written in the repository's YAML dialect: `nullable:
true` admits null, and `$ref: '#/types/X'` names a type of the same file.
This turns both into JSON Schema (`type: [t, "null"]`, `#/$defs/X`).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORLD_STATE = ROOT / "schemas" / "world_state_schema.yaml"


def _convert(node: Any) -> Any:
    if isinstance(node, list):
        return [_convert(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {k: _convert(v) for k, v in node.items() if k != "nullable"}
    ref = out.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/types/"):
        out["$ref"] = "#/$defs/" + ref.removeprefix("#/types/")
    if node.get("nullable") is True:
        if "type" in out:
            t = out["type"]
            out["type"] = [*(t if isinstance(t, list) else [t]), "null"]
        else:
            out = {"anyOf": [out, {"type": "null"}]}
    return out


@cache
def action_record_validator() -> jsonschema.protocols.Validator:
    """A validator of one action record."""
    doc = yaml.safe_load(WORLD_STATE.read_text(encoding="utf-8"))
    defs = {name: _convert(t) for name, t in doc["types"].items()}
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": defs,
        "$ref": "#/$defs/ActionRecord",
    }
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def problems(record: dict[str, Any]) -> list[str]:
    """Why `record` is not an action record (empty when it is)."""
    return [
        f"{'/'.join(map(str, e.path))}: {e.message}"
        for e in action_record_validator().iter_errors(record)
    ]
