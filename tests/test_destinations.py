"""The destination policy vectors (STANDARD v1.2 §4.4.2,
``tests/conformance/destinations/match.json``), through the core: the one
implementation Python uses (``_core.check_destination_pattern``,
``_core.destination_allowed``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / "tests/conformance/destinations/match.json").read_text()
VECTORS = json.loads(TEXT)


def test_the_file_is_ascii() -> None:
    # The NFC and NFD cases stay distinct only as escapes.
    assert TEXT.isascii()


@pytest.mark.parametrize("case", VECTORS["patterns"], ids=lambda c: repr(c["pattern"]))
def test_pattern_vectors(case: dict[str, Any]) -> None:
    if case["valid"]:
        _core.check_destination_pattern(case["pattern"])
    else:
        with pytest.raises(ValueError):
            _core.check_destination_pattern(case["pattern"])


@pytest.mark.parametrize(
    "case",
    VECTORS["matches"],
    ids=lambda c: f"{c['policies']}:{c['destination']!r}",
)
def test_match_vectors(case: dict[str, Any]) -> None:
    assert (
        _core.destination_allowed(case["policies"], case["destination"])
        is case["allowed"]
    )
