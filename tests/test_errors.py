"""The Python error model mirrors the Rust core's diagnostic codes."""

from __future__ import annotations

from grounded_agency import _core
from grounded_agency.errors import (
    ErrorCode,
    Severity,
    ValidationError,
    format_error,
    format_errors_response,
)


def test_codes_match_the_core() -> None:
    python = [(c.value, c.name, c.severity.value) for c in ErrorCode]
    assert python == list(_core.CODES)


def test_warnings_are_w6xx() -> None:
    for code in ErrorCode:
        assert (code.severity is Severity.WARNING) == code.value.startswith("W6")


def test_from_core_diagnostic() -> None:
    err = ValidationError.from_core(
        {
            "code": "W604",
            "name": "UNKNOWN_FIELD",
            "severity": "warning",
            "message": "unknown field 'stpes' is ignored",
            "location": {"workflow": "w", "field": "stpes"},
            "suggestion": "did you mean 'steps'?",
        }
    )
    assert err.code is ErrorCode.UNKNOWN_FIELD
    assert err.severity is Severity.WARNING
    assert err.suggestion == "did you mean 'steps'?"


def test_format_includes_severity() -> None:
    err = ValidationError(ErrorCode.UNKNOWN_CAPABILITY, "no such capability")
    assert format_error(err) == {
        "error": {
            "code": "V101",
            "name": "UNKNOWN_CAPABILITY",
            "severity": "error",
            "message": "no such capability",
            "location": {},
        }
    }
    assert format_errors_response([err])["errors"][0]["severity"] == "error"
