"""Generate the files the TypeScript package and the Standard Agents binding
take from this repository, and the approval digest vectors.

The TypeScript package in packages/acs-core/ (which the reference binding in
examples/standard_agents/ depends on) must agree with the ontology and with
the reference executor, so one of its files is generated:

- packages/acs-core/src/ontology.gen.ts: each capability's layer, safety
  flags and required output fields, and the ontology's `requires` edges,
  from schemas/capability_ontology.yaml; the trust classes of
  schemas/agent_identity_schema.yaml; the current Standard version (the
  newest spec/STANDARD-v*.md) and the versions the core supports

The approval digest vectors are tests/conformance/approval/digests.json:
approval requests of the reference executor (STANDARD v1.2.0 §5.14), each
with the shown values, their RFC 8785 canonical JSON and the SHA-256 digest
of it. They are conformance data for any implementation; the package's
tests read the file in place.

The binding's former copies (examples/standard_agents/src/acs/ontology.gen.ts
and test/fixtures/approval-digests.json) must not exist: --check fails if
one does.

It also writes schemas/interop/standard_agents_annotation.schema.json, the
schema of the annotation the binding puts on a tool, whose capability and
layer lists are the ontology's.

    python scripts/gen_standard_agents_binding.py          # write the files
    python scripts/gen_standard_agents_binding.py --check  # fail if they differ (CI)
"""

import argparse
import hashlib
import json
import math
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple

from grounded_agency import _core

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
AGENT_IDENTITY = ROOT / "schemas" / "agent_identity_schema.yaml"
PACKAGE = ROOT / "packages" / "acs-core"
ONTOLOGY_TS = PACKAGE / "src" / "ontology.gen.ts"
BINDING = ROOT / "examples" / "standard_agents"
# Files this script once wrote into the binding; the package holds them now.
REMOVED = (
    BINDING / "src" / "acs" / "ontology.gen.ts",
    BINDING / "test" / "fixtures" / "approval-digests.json",
)
ANNOTATION_SCHEMA = (
    ROOT / "schemas" / "interop" / "standard_agents_annotation.schema.json"
)
DIGEST_VECTORS_OUT = ROOT / "tests" / "conformance" / "approval" / "digests.json"
ME = "scripts/gen_standard_agents_binding.py"

HEADER = f"""\
// Generated from schemas/capability_ontology.yaml,
// schemas/agent_identity_schema.yaml and spec/STANDARD-v*.md by
// {ME}. DO NOT EDIT: regenerate with
//   python {ME}
"""


def current_standard() -> str:
    """The version of the newest spec/STANDARD-v*.md."""
    versions = [
        tuple(int(part) for part in m.group(1).split("."))
        for path in (ROOT / "spec").glob("STANDARD-v*.md")
        if (m := re.fullmatch(r"STANDARD-v(\d+\.\d+\.\d+)\.md", path.name))
    ]
    if not versions:
        raise SystemExit("no spec/STANDARD-v*.md file")
    return ".".join(map(str, max(versions)))


def ts(value: Any) -> str:
    """A JSON literal, which is also a TypeScript literal."""
    return json.dumps(value, ensure_ascii=False)


def render_ontology(ontology: dict[str, Any], identity: dict[str, Any]) -> str:
    layer_of = {
        capability: layer
        for layer, info in ontology["layers"].items()
        for capability in info["capabilities"]
    }
    trust_classes = identity["agent_identity"]["properties"]["trust_class"]["enum"]
    lines = [HEADER]
    lines.append(
        "/** The Agent Capability Standard version this package implements. */"
    )
    lines.append(f"export const STANDARD_VERSION = {ts(current_standard())};")
    lines.append("")
    lines.append(
        "/** The Standard versions a workflow may target (§11.5), as the core supports them. */"
    )
    lines.append(
        f"export const SPEC_VERSIONS = {ts(list(_core.SPEC_VERSIONS))} as const;"
    )
    lines.append("")
    lines.append(
        f"export const ONTOLOGY_VERSION = {ts(str(ontology['meta']['version']))};"
    )
    lines.append("")
    lines.append("export const CAPABILITIES = {")
    for node in ontology["nodes"]:
        entry = {
            "layer": layer_of[node["id"]],
            "risk": node.get("risk", "low"),
            "mutation": bool(node.get("mutation", False)),
            "requires_checkpoint": bool(node.get("requires_checkpoint", False)),
            "requires_approval": bool(node.get("requires_approval", False)),
            "mutation_overridable": bool(node.get("mutation_overridable", False)),
            "output_required": list(
                (node.get("output_schema") or {}).get("required", [])
            ),
        }
        lines.append(f"  {ts(node['id'])}: {ts(entry)},")
    lines.append("} as const;")
    lines.append("")
    # The only edge type the binding enforces at run time. `precedes` and
    # `conflicts_with` constrain the steps of one workflow, which the
    # workflow validator checks; a thread has no such static list of steps.
    lines.append(
        "/** `requires` edges as [from, to]: `from` must have run before `to`. */"
    )
    lines.append("export const REQUIRES = [")
    lines.extend(
        f"  {ts([e['from'], e['to']])},"
        for e in ontology["edges"]
        if e["type"] == "requires"
    )
    lines.append("] as const;")
    lines.append("")
    lines.append(
        "/** The trust classes of an `agent_identity` (§5.17), in the schema's order. */"
    )
    lines.append(f"export const TRUST_CLASSES = {ts(trust_classes)} as const;")
    lines.append("")
    return "\n".join(lines)


def render_annotation_schema(ontology: dict[str, Any]) -> str:
    version = {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"}
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://github.com/synaptiai/agent-capability-standard/"
            "schemas/interop/standard_agents_annotation.schema.json"
        ),
        "title": "Agent Capability Standard annotation for a Standard Agents tool",
        "description": (
            "The value of the `acs` key in a Standard Agent Specification "
            "tool's `annotations`: the ontology capability the tool performs "
            "and its effective safety flags. Generated by "
            f"{ME} from the ontology."
        ),
        "type": "object",
        "required": [
            "standard",
            "ontology",
            "capability",
            "layer",
            "risk",
            "mutation",
            "requires_checkpoint",
            "requires_approval",
        ],
        "additionalProperties": False,
        "properties": {
            "standard": {
                **version,
                "description": (
                    "Version of the Agent Capability Standard the "
                    "classification follows."
                ),
            },
            "ontology": {
                **version,
                "description": (
                    "Version of the capability ontology the capability id "
                    "and flags come from (`meta.version`)."
                ),
            },
            "capability": {
                "enum": [node["id"] for node in ontology["nodes"]],
                "description": "The one ontology capability the tool performs.",
            },
            "layer": {
                "enum": list(ontology["layers"]),
                "description": "The capability's layer.",
            },
            "domain": {
                "type": "string",
                "minLength": 1,
                "description": "The capability's domain parameter, e.g. `config`.",
            },
            "risk": {
                "enum": ["low", "medium", "high"],
                "description": (
                    "Effective risk: the higher of the tool's declaration "
                    "and the ontology's value (Standard §5.2.1)."
                ),
            },
            "mutation": {
                "type": "boolean",
                "description": "Whether the tool changes persistent state.",
            },
            "requires_checkpoint": {
                "type": "boolean",
                "description": "Whether a checkpoint must precede each call.",
            },
            "requires_approval": {
                "type": "boolean",
                "description": "Whether each call needs approval.",
            },
        },
    }
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Approval digest vectors (STANDARD v1.2.0 §5.14)
# ---------------------------------------------------------------------------

HUMAN = {"kind": "human"}
# The step shows the value an earlier step returned, so the executor digests
# whatever the host hands back.
SHOW_CURRENT: dict[str, Any] = {"approver": HUMAN, "shows": ["${current.data}"]}


class DigestVector(NamedTuple):
    """One vector to generate, as a run of `digest_catalog`."""

    name: str
    about: str
    # What `retrieve` returns as its `data`.
    value: Any = None
    # The `mutate` step's `approval` field; None: the step has none.
    approval: dict[str, Any] | None = SHOW_CURRENT
    # What a recheck reads, when the step has one.
    reread: Any = None


# The values are written with escapes for every character outside ASCII, so
# that no editor can change a code point. They exercise RFC 8785: member
# order by UTF-16 code units, number forms, string escapes, characters
# outside the Basic Multilingual Plane. The vectors after them cover which
# values the executor shows.
DIGEST_VECTORS = [
    DigestVector(
        "object",
        "An object with a nested object. Members are written in the order of"
        " their names, whatever order the value had.",
        {
            "action": "write_config",
            "capability": "mutate",
            "args": {"key": "a", "value": "b"},
        },
    ),
    DigestVector(
        "member_order",
        "Member names sort by UTF-16 code unit: the empty name first, an"
        " uppercase letter before a lowercase one, a name before a longer"
        " name that begins with it. Array elements keep their order.",
        {"b": 2, "a": 1, "A": 0, "aa": [3, 2, 1], "": None},
    ),
    DigestVector(
        "numbers",
        "Numbers are written as ECMAScript writes the binary64 value, so"
        " -0.0, 1.0, 1e+21 and 1e-07 in the JSON text of `shown` become 0, 1,"
        " 1e+21 and 1e-7. 9007199254740992 is 2^53, the largest magnitude"
        " section 5.14 allows for an integer, a number written without a"
        " fraction or an exponent. 1e+21 is written with an exponent, so it"
        " is a binary64 value and that bound does not apply to it.",
        {
            "numbers": [
                0,
                -0.0,
                1,
                -1,
                1.5,
                1e21,
                1e-7,
                123456789012,
                0.1,
                100,
                1.0,
                4.5e-10,
                2**53,
            ]
        },
    ),
    DigestVector(
        "string_escapes",
        "A string with a line feed, a tab, quotation marks, a backslash,"
        " U+0001, U+007F, U+00E9, U+20AC and U+1F600. The canonical text"
        " escapes the first five (U+0001 as `\\u0001`, in lowercase) and"
        " holds the other four as themselves.",
        {
            "text": 'line\nbreak\ttab "quote" back\\slash'
            " \u0001 \u007f \u00e9 \u20ac \U0001f600"
        },
    ),
    DigestVector(
        "member_order_non_ascii",
        "The member names of the sorting example in RFC 8785 section 3.2.3."
        " U+1F600 is the surrogate pair D83D DE00 in UTF-16, so it sorts before"
        " U+FB33, although its code point is higher.",
        {
            "\u20ac": "Euro",
            "\r": "CR",
            "\ufb33": "Dalet",
            "1": "One",
            "\U0001f600": "Emoji",
            "\u0080": "Control",
            "\u00f6": "o umlaut",
        },
    ),
    DigestVector(
        "nesting",
        "Objects and arrays nested, with true, false, null, an empty array"
        " and an empty object.",
        {"nested": {"z": {"y": {"x": [True, False, None, {"k": []}, {}]}}}},
    ),
    DigestVector("string_value", "The shown value is a string.", "a bare string"),
    DigestVector(
        "array_value",
        "The shown value is an array: it is one element of `shown`, not"
        " spliced into it.",
        [1, "two", {"three": 3}],
    ),
    DigestVector("number_value", "The shown value is a number.", 42),
    DigestVector("null_value", "The shown value is null.", None),
    DigestVector("empty_list_value", "The shown value is an empty array.", []),
    DigestVector(
        "two_values_in_order",
        "Two references: `shown` keeps the order of `shows`.",
        "a",
        approval={"approver": HUMAN, "shows": ["${setting}", "${current.data}"]},
    ),
    DigestVector(
        "unresolved_reference",
        "A `shows` reference that resolves to nothing (here a member the"
        " retrieved value does not have) is null in `shown`: one element per"
        " reference, in order.",
        {"present": 1},
        approval={
            "approver": HUMAN,
            "shows": ["${current.data.absent}", "${current.data}"],
        },
    ),
    DigestVector(
        "empty_shows",
        "`shows` is an empty list: `shown` is the empty array.",
        approval={"approver": HUMAN, "shows": []},
    ),
    DigestVector(
        "no_shows",
        "The `approval` field has no `shows`: the reference executor shows"
        " the step's resolved inputs, wrapped in an array.",
        approval={"approver": HUMAN},
    ),
    DigestVector(
        "no_approval_field",
        "The step has no `approval` field and needs approval by the"
        " ontology: the reference executor shows the step's resolved inputs,"
        " wrapped in an array, as for `no_shows`.",
        approval=None,
    ),
    DigestVector(
        "asked_again_after_recheck",
        "The recheck read a changed source, so the reference executor asks"
        " again (`on_change: reask`, the default). `shown` gains one object"
        " whose `recheck` member holds the value approved before (`previous`)"
        " and the value read now (`current`).",
        {"version": 1},
        approval={**SHOW_CURRENT, "recheck": {"source": "${current.data}"}},
        reread={"version": 2},
    ),
]

DIGEST_FIELDS = {
    "name": "The vector's name, unique in this file.",
    "kind": (
        "`step`: an approval request of a workflow step, with `approval`;"
        " without `shows`, `inputs`; with `shows`, `bindings`; asked again"
        " after a recheck, `recheck_read`. `tool_call`: the approval of a"
        " tool call (STANDARD v1.2.0 §5.18.7), with `call`."
    ),
    "about": "What the vector covers.",
    "approval": (
        "For a `step` vector: the `approval` field of the step that asks, as"
        " the workflow declares it; null when the step has none."
    ),
    "inputs": (
        "For a `step` vector: the step's resolved inputs. Present where the"
        " step declares no `shows`, so that `shown` is built from them."
    ),
    "bindings": (
        "For a `step` vector whose step declares `shows`: the values its"
        " references resolve against, by root name: the workflow input"
        " `setting` and the store `current` of the step before it, so that"
        " `${current.data}` resolves to `bindings.current.data`. A reference"
        " to something they do not hold resolves to null."
    ),
    "recheck_read": (
        "For a `step` vector asked again after a recheck: the value the"
        " recheck read, which differs from the value approved before (the"
        " recheck `source` resolved against `bindings`). The vector is the"
        " request asked again; the first request showed the `shows` values"
        " alone."
    ),
    "call": (
        "For a `tool_call` vector: the call, `{action, capability, args}`;"
        " `shown` is `[call]`."
    ),
    "shown": "The JSON array of shown values that the approval request carries.",
    "canonical": (
        "The RFC 8785 (JCS) serialization of `shown`. It is held here as a"
        " JSON string: the canonical text is the value a JSON parser returns"
        " for it."
    ),
    "digest": (
        "The SHA-256 of the UTF-8 encoding of the canonical text, in"
        " lowercase hexadecimal: the digest the request carries and a"
        " decision repeats."
    ),
}


def digest_catalog(approval: dict[str, Any] | None) -> dict[str, Any]:
    """One workflow whose `mutate` step needs approval (the ontology's
    `requires_approval`), with the step's `approval` field as given, or
    without one."""
    change: dict[str, Any] = {
        "capability": "mutate",
        "purpose": "Apply the change.",
        "store_as": "applied",
        "input_bindings": {"target": "${setting}", "operation": {"set": True}},
    }
    workflow: dict[str, Any] = {
        "goal": "Change a setting once a person has approved what will change.",
        "risk": "high",
        "spec_version": "1.1",
        "inputs": {"setting": {"type": "string", "required": True}},
        "steps": [
            {
                "capability": "retrieve",
                "purpose": "Read the value to show.",
                "store_as": "current",
                "input_bindings": {"target": "${setting}"},
            },
            {
                "capability": "checkpoint",
                "purpose": "Save a restore point.",
                "store_as": "cp",
                "input_bindings": {"scope": "config"},
            },
            change,
        ],
    }
    if approval is not None:
        change["approval"] = approval
        workflow["workflow_extensions"] = {"requires": ["approval@1"]}
    return {"change": workflow}


def canonical_json(value: Any) -> str:
    """The RFC 8785 (JCS) serialization of JSON data: no whitespace, object
    members in the order of their names' UTF-16 code units, numbers as
    ECMAScript writes the binary64 value."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int | float):
        return _ecmascript_number(float(value))
    if isinstance(value, str):
        return _json_string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        names = sorted(value, key=lambda name: name.encode("utf-16-be"))
        members = (f"{_json_string(n)}:{canonical_json(value[n])}" for n in names)
        return "{" + ",".join(members) + "}"
    raise TypeError(f"not JSON data: {type(value).__name__}")


_SHORT_ESCAPES = {
    '"': r"\"",
    "\\": r"\\",
    "\b": r"\b",
    "\f": r"\f",
    "\n": r"\n",
    "\r": r"\r",
    "\t": r"\t",
}


def _json_string(text: str) -> str:
    """A string as ECMAScript's JSON.stringify writes it (RFC 8785 §3.2.2.2)."""
    out = ['"']
    for ch in text:
        if ch in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[ch])
        elif ch < " ":
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _ecmascript_number(x: float) -> str:
    """A finite number as ECMAScript's Number.prototype.toString writes it
    (RFC 8785 §3.2.2.3). `repr` gives the same shortest digits that
    round-trip; only where the decimal point and the exponent go differs."""
    if not math.isfinite(x):
        raise ValueError(f"not a JSON number: {x!r}")
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    parts = Decimal(repr(abs(x))).normalize().as_tuple()
    digits = "".join(str(d) for d in parts.digits)
    k = len(digits)
    # The value is 0.<digits> * 10**n.
    n = k + int(parts.exponent)
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return f"{sign}{digits[:n]}.{digits[n:]}"
    if -6 < n <= 0:
        return f"{sign}0.{'0' * -n}{digits}"
    fraction = f".{digits[1:]}" if k > 1 else ""
    return f"{sign}{digits[0]}{fraction}e{'+' if n > 0 else '-'}{abs(n - 1)}"


# The workflow input of every digest run, and what its `retrieve` step
# returns besides the vector's value.
SETTING = "x"


def retrieved(vector: DigestVector) -> dict[str, Any]:
    """What the `retrieve` step returns, and so what the store `current`
    holds."""
    return {"data": vector.value, "confidence": 1.0, "evidence_anchors": []}


def approval_requests(
    validator: _core.Validator, vector: DigestVector
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the vector's workflow on the reference executor, approving every
    request. Returns each approval request and the `mutate` step's resolved
    inputs."""
    run = _core.Run.start(
        validator,
        digest_catalog(vector.approval),
        "change",
        {"setting": SETTING},
        # The catalog is a value built here, with no header (§11.5).
        header=None,
        attendance="attended",
        run_id="r",
        now_ms=0,
    )
    outputs: dict[str, dict[str, Any]] = {
        "retrieve": retrieved(vector),
        "checkpoint": {"checkpoint_id": "cp-1", "evidence_anchors": []},
        "mutate": {"success": True, "evidence_anchors": []},
    }
    requests: list[dict[str, Any]] = []
    inputs: dict[str, Any] = {}
    # A run here has at most seven actions; the bound stops one that does
    # not end.
    for _ in range(20):
        action = run.next()
        kind = action["kind"]
        response: dict[str, Any]
        if kind == "Completed":
            return requests, inputs
        if kind == "InvokeCapability":
            if action["capability"] == "mutate":
                inputs = action["inputs"]
            response = {"kind": "Output", "value": outputs[action["capability"]]}
        elif kind == "RequestApproval":
            requests.append(action)
            response = {
                "kind": "Decision",
                "decision_id": f"d{len(requests)}",
                "decision": "approved",
                "approvers": ["alice"],
                "digest": action["digest"],
            }
        elif kind == "RecheckSource":
            response = {"kind": "Current", "value": vector.reread}
        else:
            break
        run.submit(action["id"], response, 0)
    raise SystemExit(f"{vector.name}: the digest workflow did not complete")


def render_digests() -> str:
    validator = _core.Validator(ONTOLOGY, ROOT)
    vectors = []
    for vector in DIGEST_VECTORS:
        name = vector.name
        requests, inputs = approval_requests(validator, vector)
        # A step with a recheck is asked twice: the vector is the second
        # request.
        if len(requests) != (1 if vector.reread is None else 2):
            raise SystemExit(f"{name}: {len(requests)} approval requests")
        shown, digest = requests[-1]["shown"], requests[-1]["digest"]
        # `canonical` is written here, not by the executor. Its SHA-256
        # equals the executor's digest, so it is the text the executor
        # digested.
        canonical = canonical_json(shown)
        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != digest:
            raise SystemExit(f"{name}: {canonical} does not have digest {digest}")
        entry = {
            "name": name,
            "kind": "step",
            "about": vector.about,
            "approval": vector.approval,
        }
        if "shows" not in (vector.approval or {}):
            if shown != [inputs]:
                raise SystemExit(f"{name}: shown is not the step's inputs")
            entry["inputs"] = inputs
        else:
            entry["bindings"] = {"setting": SETTING, "current": retrieved(vector)}
        if vector.reread is not None:
            entry["recheck_read"] = vector.reread
        entry.update(shown=shown, canonical=canonical, digest=digest)
        vectors.append(entry)
    if len({v["name"] for v in vectors}) != len(vectors):
        raise SystemExit("two digest vectors have the same name")
    doc = {
        "generated_by": ME,
        "standard": "1.2.0",
        "section": "5.14, 5.18.7",
        "status": "normative",
        "description": (
            "Approval digests (STANDARD v1.2.0 sections 5.14 and 5.18.7,"
            " normative under section 10.3), computed by the reference"
            " executor (core/src/exec/machine.rs, core/src/exec/canonical.rs)."
            " Each `step` vector is one approval request of a workflow step;"
            " each `tool_call` vector is the approval of a tool call. The"
            " shown values are a JSON array; the digest is the SHA-256 of the"
            " UTF-8 encoding of their canonical JSON (RFC 8785), as 64"
            " lowercase hexadecimal digits, compared regardless of case. An"
            " implementation that computes or checks approval digests"
            " produces each vector's `canonical` text and `digest` from its"
            " `shown` values; an executor shows each `step` vector's `shown`"
            " values, given its `inputs` or `bindings` and any"
            " `recheck_read`, and a safety layer each `tool_call` vector's."
            " This"
            " file is printable ASCII: any other character is written as a"
            " JSON \\u escape, so no tool that normalises or transcodes text"
            " can change a vector."
        ),
        "fields": DIGEST_FIELDS,
        "vectors": vectors,
    }
    text = json.dumps(doc, indent=2, ensure_ascii=True) + "\n"
    # json.dumps writes U+007F as itself. It can only be inside a string,
    # where the escape means the same.
    return text.replace("\x7f", "\\u007f")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the files on disk differ"
    )
    check = parser.parse_args(argv).check
    ontology = _core.load_yaml(str(ONTOLOGY))
    identity = _core.load_yaml(str(AGENT_IDENTITY))
    rendered = {
        ONTOLOGY_TS: render_ontology(ontology, identity),
        DIGEST_VECTORS_OUT: render_digests(),
        ANNOTATION_SCHEMA: render_annotation_schema(ontology),
    }
    stale = [
        p
        for p, text in rendered.items()
        if not p.exists() or p.read_text(encoding="utf-8") != text
    ]
    leftover = [p for p in REMOVED if p.exists()]
    if check:
        for p in stale:
            print(f"out of date: {p.relative_to(ROOT)}")
        for p in leftover:
            print(f"no longer generated, delete it: {p.relative_to(ROOT)}")
        if stale or leftover:
            print(f"run: python {ME}")
            return 1
        print(f"{len(rendered)} generated files up to date")
        return 0
    for p in stale:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rendered[p], encoding="utf-8")
    for p in leftover:
        p.unlink()
    print(f"{len(rendered)} files ({len(stale)} written, {len(leftover)} removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
