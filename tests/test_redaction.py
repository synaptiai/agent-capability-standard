"""The secret redactor (STANDARD v1.2 §6.7), against
``tests/conformance/secrets/redact.json``, which the TypeScript redactor
(``packages/acs-core/src/redact.ts``) reads too."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.state.redaction import (
    DEFAULT_PATTERNS,
    DEFAULT_REDACTOR,
    MARKER,
    Redactor,
    holds_secret,
    redact,
    redact_text,
)

VECTORS = Path(__file__).resolve().parent / "conformance" / "secrets" / "redact.json"
DOC = json.loads(VECTORS.read_text(encoding="utf-8"))


def test_the_vector_file() -> None:
    assert DOC["standard"] == "1.2.0"
    assert DOC["status"] == "informative"
    names = [v["name"] for v in DOC["vectors"]]
    assert len(names) == len(set(names))
    # Non-ASCII text is written as escapes.
    assert VECTORS.read_text(encoding="utf-8").isascii()


@pytest.mark.parametrize("vector", DOC["vectors"], ids=lambda v: v["name"])
def test_vector(vector: dict[str, Any]) -> None:
    redactor = Redactor(vector["secret_values"])
    given = copy.deepcopy(vector["input"])
    output, pointers = redactor.redact(given)
    assert output == vector["expect"]["output"]
    assert pointers == vector["expect"]["pointers"]
    # The value given is not modified.
    assert given == vector["input"]
    assert redactor.holds_secret(vector["input"]) == bool(pointers)
    # Redacting again changes nothing: the marker is not a secret.
    assert redactor.redact(output) == (output, [])
    if isinstance(vector["input"], str):
        assert redactor.redact_text(vector["input"]) == (output, bool(pointers))


def test_defaults() -> None:
    assert MARKER == "[REDACTED]"
    assert all("secret" in p.groupindex for p in DEFAULT_PATTERNS)
    assert redact_text("password=hunter22") == ("password=[REDACTED]", True)
    assert redact({"a": "plain"}) == ({"a": "plain"}, [])
    assert holds_secret(["x", "Bearer abcdefgh12345678"])
    assert not holds_secret([1, None, True])
    assert DEFAULT_REDACTOR.redact_text("nothing here") == ("nothing here", False)


def test_registered_values() -> None:
    r = Redactor()
    r.add_secret("abc")  # shorter than four characters: ignored
    r.add_secret("hunter")
    r.add_secret("hunter22")
    # The longest first, so a value that holds another is replaced whole.
    assert r.redact_text("hunter22 and hunter") == ("[REDACTED] and [REDACTED]", True)
    assert r.redact_text("abc") == ("abc", False)
    with pytest.raises(TypeError):
        r.add_secret(1234)  # type: ignore[arg-type]
    # A redactor's values are its own.
    assert DEFAULT_REDACTOR.redact_text("hunter22") == ("hunter22", False)


def test_patterns_name_their_secret() -> None:
    with pytest.raises(ValueError, match="secret"):
        Redactor(patterns=[re.compile("token")])
    only = Redactor(patterns=[re.compile(r"pin (?P<secret>\d{4})")])
    assert only.redact_text("pin 1234, password=hunter22") == (
        "pin [REDACTED], password=hunter22",
        True,
    )


def test_pointers_escape_and_tuples() -> None:
    value = {"a~b": ("Bearer abcdefgh12345678",), "c": {"client_secret": "s3cr3t!"}}
    output, pointers = redact(value)
    assert output == {"a~b": ["Bearer [REDACTED]"], "c": {"client_secret": MARKER}}
    assert pointers == ["/a~0b/0", "/c/client_secret"]
