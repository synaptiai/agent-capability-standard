"""A capability output over a text-only channel (STANDARD 1.2.0 section
5.18.9): the I-JSON text of the output object, nothing around it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import (
    CapabilityOutputError,
    decode_capability_output,
    encode_capability_output,
)

VECTORS = json.loads(
    (
        Path(__file__).resolve().parent / "conformance" / "output" / "vectors.json"
    ).read_text(encoding="utf-8")
)

GOOD: dict[str, Any] = {
    "observation": {"files": 3},
    "evidence_anchors": [{"ref": "tool:Bash:t1", "kind": "tool_output"}],
    "confidence": 0.9,
}


def test_round_trip() -> None:
    text = encode_capability_output("observe", GOOD)
    assert json.loads(text) == GOOD
    assert decode_capability_output("observe", text) == GOOD
    # Insignificant whitespace around the value is still the value.
    assert decode_capability_output("observe", " \n" + text + "\n") == GOOD


def test_encode_keeps_non_ascii_text() -> None:
    output = {**GOOD, "observation": "café"}
    assert "café" in encode_capability_output("observe", output)


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"observation": 1, "evidence_anchors": []}),  # no confidence
        json.dumps([GOOD]),  # not an object
        "Here it is: " + json.dumps(GOOD),  # text before
        json.dumps(GOOD) + "\nDone.",  # text after
        "```json\n" + json.dumps(GOOD) + "\n```",  # a fence
        '{"observation": 1, "observation": 2, "evidence_anchors": [], "confidence": 1}',
        '{"observation": NaN, "evidence_anchors": [], "confidence": 1}',
        '{"observation": 1e999, "evidence_anchors": [], "confidence": 1}',
        '{"observation": 9007199254740993, "evidence_anchors": [], "confidence": 1}',
        '{"observation": "\\ud800", "evidence_anchors": [], "confidence": 1}',
        '{"observation": 1, "evidence_anchors": {}, "confidence": 1}',
        '{"observation": 1, "evidence_anchors": [], "confidence": 2}',
        '{"observation": '
        + "[" * 101
        + "]" * 101
        + ', "evidence_anchors": [], "confidence": 1}',
    ],
)
def test_decode_refuses_with_r402(text: str) -> None:
    with pytest.raises(CapabilityOutputError) as raised:
        decode_capability_output("observe", text)
    assert raised.value.error.code_str == "R402"
    assert str(raised.value).startswith("R402 EXECUTION_FAILED: ")
    assert raised.value.error.location["capability"] == "observe"


@pytest.mark.parametrize(
    "output",
    [
        [GOOD],
        {"observation": 1, "evidence_anchors": []},
        {**GOOD, "observation": 2**53 + 1},
        {**GOOD, "observation": float("nan")},
        {**GOOD, "observation": "\ud800"},
    ],
)
def test_encode_refuses_with_r402(output: Any) -> None:
    with pytest.raises(CapabilityOutputError) as raised:
        encode_capability_output("observe", output)
    assert raised.value.error.code_str == "R402"


def test_the_integer_limit_is_2_to_the_53() -> None:
    """Integers within ±2^53 are I-JSON, as the reference executor reads
    them (§5.14)."""
    output = {**GOOD, "observation": -(2**53)}
    assert decode_capability_output(
        "observe", encode_capability_output("observe", output)
    )


def test_100_levels_deep_is_accepted() -> None:
    nested: Any = []
    for _ in range(98):
        nested = [nested]
    output = {**GOOD, "observation": nested}
    assert decode_capability_output(
        "observe", encode_capability_output("observe", output)
    )


def _outcome(run: Any) -> Any:
    try:
        run()
    except CapabilityOutputError as e:
        return {"refuse": e.error.code_str}
    return "ok"


@pytest.mark.parametrize(
    "vector", VECTORS["decode"], ids=[v["name"] for v in VECTORS["decode"]]
)
def test_shared_decode_vectors(vector: dict[str, Any]) -> None:
    """tests/conformance/output/vectors.json, which the TypeScript package
    reads too, so the two codecs agree."""
    assert (
        _outcome(lambda: decode_capability_output("observe", vector["text"]))
        == vector["expect"]
    )


@pytest.mark.parametrize(
    "vector", VECTORS["encode"], ids=[v["name"] for v in VECTORS["encode"]]
)
def test_shared_encode_vectors(vector: dict[str, Any]) -> None:
    value = json.loads(vector["value_text"])

    def encode_then_decode() -> None:
        text = encode_capability_output("observe", value)
        # What a producer sends, a consumer accepts.
        decode_capability_output("observe", text)

    assert _outcome(encode_then_decode) == vector["expect"]


def test_python_writes_a_large_double_in_exponent_form() -> None:
    """The case the shared vectors leave out: Python writes the double 1.8e16
    as 1.8e+16, a double in any reader; JavaScript writes it as an integer
    literal and so refuses it (packages/acs-core/test/output.test.ts)."""
    text = encode_capability_output("observe", {**GOOD, "observation": 1.8e16})
    assert '"observation":1.8e+16' in text
    assert decode_capability_output("observe", text)["observation"] == 1.8e16


@pytest.mark.parametrize("layout", ["array", "object"])
def test_the_check_takes_memory_in_proportion_to_the_output(layout: str) -> None:
    """The I-JSON walks (the output check, and a binding's or a call's
    arguments, ``i_json_problem``) keep each value's place as a link to its
    parent's and write a place out only for the value they refuse. Before,
    each child's whole path was built when its parent was read: a long
    member name above a wide array cost the name's length times the width
    (a result of 80 KB took about 800 MB at PostToolUse, so a hostile MCP
    server could exhaust the host's memory)."""
    import tracemalloc

    from grounded_agency.capabilities.bindings import i_json_problem

    name = "x" * 20_000
    wide: Any = [0] * 5_000 if layout == "array" else {f"k{i}": 0 for i in range(5_000)}
    output = {**GOOD, "observation": {name: wide}}
    text = encode_capability_output("observe", output)
    tracemalloc.start()
    try:
        assert decode_capability_output("observe", text)
        assert i_json_problem(output) is None
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # The paths alone were 20,000 x 5,000 bytes: 100 MB.
    assert peak < 20 * len(text) + 2_000_000, peak


def test_a_refusal_still_names_the_place() -> None:
    """The place a refusal names is written as before: member names after
    dots, indexes in brackets."""
    from grounded_agency.capabilities.bindings import i_json_problem

    output = {**GOOD, "observation": {"a": [0, {"b": 2**60}]}}
    with pytest.raises(CapabilityOutputError) as refused:
        decode_capability_output("observe", json.dumps(output))
    assert "at $.observation.a[1].b," in refused.value.error.message
    assert "at $.a[0].b," in str(i_json_problem({"a": [{"b": 1.8e16}]}))
