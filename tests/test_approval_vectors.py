"""The approval digest vectors (tests/conformance/approval/digests.json,
STANDARD v1.1.0 §5.14) hold against the reference executor and against a
computation that uses neither the executor nor the generator: an RFC 8785
serializer written here, and ``hashlib``.

Each vector is replayed from its own fields alone (``approval``, ``inputs``,
``shown``), so the file is enough to reproduce a digest on an executor.

Also checked here: what the executor asks for a step that needs approval and
has no ``approval`` field. The runtime fixture ``checkpoint_per_mutation``
pins it, but fixture matching is by subset, so the exact request is compared
here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
VECTORS = ROOT / "tests" / "conformance" / "approval" / "digests.json"
BINDING_COPY = (
    ROOT
    / "examples"
    / "standard_agents"
    / "test"
    / "fixtures"
    / "approval-digests.json"
)
RUNTIME = ROOT / "tests" / "conformance" / "runtime"

DOC: dict[str, Any] = json.loads(VECTORS.read_text(encoding="utf-8"))
CASES: list[dict[str, Any]] = DOC["vectors"]
IDS = [v["name"] for v in CASES]
# The vectors of workflow steps, which the reference executor replays; a
# `tool_call` vector has no step to run.
STEP_CASES = [v for v in CASES if v["kind"] == "step"]
STEP_IDS = [v["name"] for v in STEP_CASES]


# ---------------------------------------------------------------------------
# RFC 8785 (JCS), written for this test
# ---------------------------------------------------------------------------


def es_number(x: float) -> str:
    """ECMAScript's Number.prototype.toString for a finite binary64 value
    (RFC 8785 §3.2.2.3), from the shortest digits that round-trip."""
    assert math.isfinite(x)
    if x == 0:
        return "0"
    if x < 0:
        return "-" + es_number(-x)
    _, digit_tuple, exponent = Decimal(repr(x)).as_tuple()
    assert isinstance(exponent, int)
    digits = "".join(map(str, digit_tuple)).rstrip("0")
    # x == 0.<digits> * 10**point
    point = len(digit_tuple) + exponent
    if 0 < point <= 21:
        whole = digits[:point].ljust(point, "0")
        return whole + ("." + digits[point:] if len(digits) > point else "")
    if -6 < point <= 0:
        return "0." + "0" * -point + digits
    mantissa = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
    return f"{mantissa}e{point - 1:+d}"


def jcs(value: Any) -> str:
    """The RFC 8785 serialization of JSON data."""
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, int | float):
        return es_number(float(value))
    if isinstance(value, str):
        # With ensure_ascii off, json.dumps escapes what RFC 8785 §3.2.2.2
        # escapes and nothing else, with lowercase hexadecimal digits.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(jcs(item) for item in value) + "]"
    assert isinstance(value, dict), type(value)
    # UTF-16BE bytes compare as the UTF-16 code units do (RFC 8785 §3.2.3).
    names = sorted(value, key=lambda name: name.encode("utf-16-be"))
    return "{" + ",".join(f"{jcs(n)}:{jcs(value[n])}" for n in names) + "}"


@pytest.mark.parametrize(
    ("number", "text"),
    [
        # RFC 8785 Appendix B, and the limits of ECMAScript's notations.
        (0.0, "0"),
        (-0.0, "0"),
        (5e-324, "5e-324"),
        (-5e-324, "-5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (9007199254740992.0, "9007199254740992"),
        (295147905179352830000.0, "295147905179352830000"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (9.999999999999997e22, "9.999999999999997e+22"),
        (1e23, "1e+23"),
        (0.000001, "0.000001"),
        (1e-7, "1e-7"),
        (1.5e-7, "1.5e-7"),
        (333333333.3333333, "333333333.3333333"),
        (1424953923781206.2, "1424953923781206.2"),
        (-1.5, "-1.5"),
        (100.0, "100"),
        (123.456, "123.456"),
    ],
)
def test_the_serializer_here_writes_numbers_as_ecmascript(
    number: float, text: str
) -> None:
    assert es_number(number) == text


def test_the_serializer_here_follows_rfc_8785() -> None:
    # RFC 8785 §3.2.2 (the sample object) and §3.2.3 (member order).
    sample = {
        "numbers": [
            333333333.33333329,
            1e30,
            4.50,
            2e-3,
            0.000000000000000000000000001,
        ],
        "string": '\u20ac$\u000f\nA\'B"\\\\"/',
        "literals": [None, True, False],
    }
    assert jcs(sample) == (
        '{"literals":[null,true,false],'
        '"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        '"string":"\u20ac$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    )
    order = {
        "\u20ac": "Euro Sign",
        "\r": "Carriage Return",
        "\ufb33": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "\U0001f600": "Emoji: Grinning Face",
        "\u0080": "Control",
        "\u00f6": "Latin Small Letter O With Diaeresis",
    }
    assert list(json.loads(jcs(order)).values()) == [
        "Carriage Return",
        "One",
        "Control",
        "Latin Small Letter O With Diaeresis",
        "Euro Sign",
        "Emoji: Grinning Face",
        "Hebrew Letter Dalet With Dagesh",
    ]


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def test_the_file_is_printable_ascii() -> None:
    """No tool that normalises or transcodes text can change a vector."""
    text = VECTORS.read_text(encoding="utf-8")
    assert re.fullmatch(r"[\x20-\x7e\n]*", text)


def test_the_binding_tests_against_the_same_vectors() -> None:
    assert BINDING_COPY.read_bytes() == VECTORS.read_bytes()


def test_the_vectors_are_informative_and_named() -> None:
    assert DOC["standard"] == "1.1.0"
    assert DOC["section"] == "5.14"
    assert DOC["status"] == "informative"
    assert len(set(IDS)) == len(IDS)
    for vector in CASES:
        assert set(vector) <= set(DOC["fields"]), vector["name"]
        assert {"name", "kind", "about", "shown", "canonical", "digest"} <= set(vector)
        assert vector["kind"] in ("step", "tool_call"), vector["name"]
        if vector["kind"] == "step":
            assert "approval" in vector and "call" not in vector, vector["name"]
        else:
            assert vector["shown"] == [vector["call"]], vector["name"]
            assert not {"approval", "inputs"} & set(vector), vector["name"]


def test_the_vectors_cover_what_the_digest_depends_on() -> None:
    shown = {v["name"]: v["shown"] for v in CASES}
    canonical = {v["name"]: v["canonical"] for v in CASES}
    # Member order: the canonical order differs from the order in the file.
    assert list(shown["member_order"][0]) != sorted(shown["member_order"][0])
    # ... and UTF-16 order differs from code point order.
    names = list(json.loads(canonical["member_order_non_ascii"])[0])
    assert names != sorted(names)
    # Nesting, numbers that are not written as given, text outside ASCII.
    assert "nested" in shown["nesting"][0]
    numbers = shown["numbers"][0]["numbers"]
    assert any(n == 0 and math.copysign(1.0, n) < 0 for n in numbers)
    assert "1e-7" in canonical["numbers"]
    assert any(ord(ch) > 0xFFFF for ch in canonical["string_escapes"])
    # An empty list, as a shown value and as the whole of `shows`.
    assert shown["empty_list_value"] == [[]]
    assert shown["empty_shows"] == []
    # No `shows`: the step's resolved inputs, wrapped in an array.
    for name in ("no_shows", "no_approval_field"):
        vector = next(v for v in CASES if v["name"] == name)
        assert vector["shown"] == [vector["inputs"]]
    assert (
        next(v for v in CASES if v["name"] == "no_approval_field")["approval"] is None
    )
    assert "recheck" in shown["asked_again_after_recheck"][-1]


# ---------------------------------------------------------------------------
# Each vector, without the executor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vector", CASES, ids=IDS)
def test_canonical_text_and_digest_computed_here(vector: dict[str, Any]) -> None:
    canonical = jcs(vector["shown"])
    assert canonical == vector["canonical"]
    assert re.fullmatch(r"[0-9a-f]{64}", vector["digest"])
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == vector["digest"]


# ---------------------------------------------------------------------------
# Each vector, on the reference executor
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def validator() -> _core.Validator:
    return _core.Validator(ONTOLOGY, ROOT)


def same_json(a: Any, b: Any) -> bool:
    """Equal as JSON data: 1 and 1.0 are one number, true is not 1."""
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a is b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_json(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(
            same_json(x, y) for x, y in zip(a, b, strict=True)
        )
    return type(a) is type(b) and bool(a == b)


def requests_expected(vector: dict[str, Any]) -> int:
    """A step with a recheck is asked twice: the vector is the second
    request, made after the recheck read a changed source."""
    return 2 if "recheck" in (vector["approval"] or {}) else 1


def replay(
    validator: _core.Validator, vector: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run a workflow built from the vector's fields. Returns its approval
    requests and how the run ended.

    The values its references resolve to are read back from ``shown``: a
    ``shows`` entry at index ``i`` resolved to ``shown[i]``. The request the
    vector describes is answered with the vector's digest, so the run
    completes only if the executor accepts that digest."""
    approval = vector["approval"]
    shows = (approval or {}).get("shows")
    resolved = dict(zip(shows or [], vector["shown"], strict=False))
    change: dict[str, Any] = {
        "capability": "mutate",
        "purpose": "Apply the change.",
        "store_as": "applied",
        # Literal bindings resolve to themselves.
        "input_bindings": vector.get(
            "inputs", {"target": "config", "operation": {"set": 1}}
        ),
    }
    workflow: dict[str, Any] = {
        "goal": "Replay one approval digest vector.",
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
    run = _core.Run.start(
        validator,
        {"replay": workflow},
        "replay",
        {"setting": resolved.get("${setting}", "any")},
        attendance="attended",
        run_id="replay",
        now_ms=0,
    )
    outputs: dict[str, dict[str, Any]] = {
        "retrieve": {"data": resolved.get("${current.data}"), "confidence": 1.0},
        "checkpoint": {"checkpoint_id": "cp-1"},
        "mutate": {"success": True},
    }
    requests: list[dict[str, Any]] = []
    for _ in range(20):
        action = run.next()
        kind = action["kind"]
        response: dict[str, Any]
        if kind in ("Completed", "Failed"):
            return requests, action
        if kind == "InvokeCapability":
            value = {**outputs[action["capability"]], "evidence_anchors": []}
            response = {"kind": "Output", "value": value}
        elif kind == "RequestApproval":
            requests.append(action)
            last = len(requests) == requests_expected(vector)
            response = {
                "kind": "Decision",
                "decision_id": f"d{len(requests)}",
                "decision": "approved",
                "approvers": ["alice"],
                "digest": vector["digest"] if last else action["digest"],
            }
        else:
            assert kind == "RecheckSource", action
            # The source as the vector says it was read: changed.
            current = vector["shown"][-1]["recheck"]["current"]
            response = {"kind": "Current", "value": current}
        run.submit(action["id"], response, 0)
    raise AssertionError(f"{vector['name']}: the run did not end")


@pytest.mark.parametrize("vector", STEP_CASES, ids=STEP_IDS)
def test_the_executor_asks_with_the_vector(
    validator: _core.Validator, vector: dict[str, Any]
) -> None:
    requests, end = replay(validator, vector)
    assert len(requests) == requests_expected(vector)
    request = requests[-1]
    assert same_json(request["shown"], vector["shown"]), request["shown"]
    assert request["digest"] == vector["digest"]
    # The decision carried the vector's digest, and the executor took it.
    assert (end["kind"], end.get("outcome")) == ("Completed", "completed"), end
    if len(requests) == 2:
        # The first request showed the declared values alone.
        assert same_json(requests[0]["shown"], vector["shown"][:-1])
        assert requests[0]["digest"] != request["digest"]


def test_the_executor_refuses_the_digest_of_other_values(
    validator: _core.Validator,
) -> None:
    """The replay answers with the vector's digest, so a vector whose digest
    is not the digest of its shown values does not complete (F502)."""
    vector, other = STEP_CASES[0], STEP_CASES[1]
    assert vector["digest"] != other["digest"]
    requests, end = replay(validator, {**vector, "digest": other["digest"]})
    assert requests[-1]["digest"] == vector["digest"]
    assert (end["kind"], end.get("code")) == ("Failed", "F502"), end


# ---------------------------------------------------------------------------
# A step that needs approval and has no `approval` field
# ---------------------------------------------------------------------------


def test_a_step_with_no_approval_field_asks_a_human_in_session(
    validator: _core.Validator,
) -> None:
    """The reference executor's default request (core/src/exec/machine.rs):
    approver ``{kind: human}`` and nothing else, mode ``in_session``, the
    step's resolved inputs wrapped in an array, no expiry."""
    fixture = json.loads((RUNTIME / "checkpoint_per_mutation.json").read_text())
    steps = fixture["catalog"][fixture["workflow"]]["steps"]
    run = _core.Run.start(
        validator,
        fixture["catalog"],
        fixture["workflow"],
        fixture["inputs"],
        attendance=fixture["attendance"],
        run_id="run-1",
        now_ms=fixture["start"],
    )
    requests: dict[int, dict[str, Any]] = {}
    invoked: dict[int, dict[str, Any]] = {}
    for entry in fixture["script"]:
        action = run.next()
        if action["kind"] == "RequestApproval":
            requests[action["step"]] = action
            # The fixture pins the four values, as far as a subset match can.
            assert {"approver", "mode", "shown", "expires_at"} <= set(entry["expect"])
        elif action["kind"] == "InvokeCapability":
            invoked[action["step"]] = action["inputs"]
        response = entry["respond"]
        if response.get("digest") == "{{digest}}":
            response = {**response, "digest": action["digest"]}
        run.submit(action["id"], response, fixture["start"])
    assert run.next()["kind"] == "Completed"
    assert sorted(requests) == [2, 3]
    for step, request in requests.items():
        assert "approval" not in steps[step]
        assert request["approver"] == {"kind": "human"}
        assert request["mode"] == "in_session"
        assert request["expires_at"] is None
        assert same_json(request["shown"], [invoked[step]])
        assert (
            request["digest"]
            == hashlib.sha256(jcs(request["shown"]).encode("utf-8")).hexdigest()
        )
