"""A capability output over a text-only channel (STANDARD 1.2.0 section
5.18.9): the I-JSON text of the output object, nothing around it."""

from __future__ import annotations

import json
from typing import Any

import pytest

from grounded_agency import (
    CapabilityOutputError,
    decode_capability_output,
    encode_capability_output,
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
