"""
Grounded Agency -- Standard Error Model

Implements the error codes and formatting defined in Section 9 of
spec/STANDARD-v1.0.0.md.  Twenty-three error codes across five categories
(Validation, Binding, Schema, Runtime, Safety) with a structured JSON
response format.

This is a leaf module -- zero imports from other grounded_agency modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Error codes (Section 9.2 -- 9.6)
# ---------------------------------------------------------------------------

class ErrorCode(Enum):
    """All standard error codes grouped by category.

    Each member's *value* is the short code string (e.g. ``"V101"``);
    the member *name* is the canonical error name (e.g. ``UNKNOWN_CAPABILITY``).
    """

    # -- 9.2 Validation errors (V1xx) --------------------------------------
    UNKNOWN_CAPABILITY = "V101"
    MISSING_PREREQUISITE = "V102"
    INVALID_STEP = "V103"
    DUPLICATE_STORE_AS = "V104"
    CIRCULAR_DEPENDENCY = "V105"

    # -- 9.3 Binding errors (B2xx) ------------------------------------------
    INVALID_BINDING_PATH = "B201"
    MISSING_PRODUCER = "B202"
    TYPE_MISMATCH = "B203"
    AMBIGUOUS_TYPE = "B204"
    INVALID_ANNOTATION = "B205"

    # -- 9.4 Schema errors (S3xx) -------------------------------------------
    SCHEMA_NOT_FOUND = "S301"
    INVALID_REF = "S302"
    SCHEMA_VALIDATION_FAILED = "S303"
    MISSING_REQUIRED_FIELD = "S304"

    # -- 9.5 Runtime errors (R4xx) ------------------------------------------
    EXECUTION_TIMEOUT = "R401"
    EXECUTION_FAILED = "R402"
    GATE_BLOCKED = "R403"
    RECOVERY_EXHAUSTED = "R404"

    # -- 9.6 Safety errors (F5xx) -------------------------------------------
    CHECKPOINT_REQUIRED = "F501"
    APPROVAL_REQUIRED = "F502"
    ROLLBACK_FAILED = "F503"
    CONSTRAINT_VIOLATED = "F504"
    PROVENANCE_MISSING = "F505"


# ---------------------------------------------------------------------------
# Error dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StandardError:
    """A single structured error conforming to Section 9.7.

    Parameters
    ----------
    code:
        The :class:`ErrorCode` for this error.
    message:
        Human-readable description of what went wrong.
    location:
        Where the error occurred.  Typical keys are ``workflow`` (str),
        ``step`` (int), and ``field`` (str), but any JSON-serialisable
        dict is accepted.
    suggestion:
        Optional hint on how to fix the problem.
    """

    code: ErrorCode
    message: str
    location: dict[str, Any] = field(default_factory=dict)
    suggestion: str | None = None

    # Convenience accessors ---------------------------------------------------

    @property
    def code_str(self) -> str:
        """Short code string, e.g. ``"V101"``."""
        return self.code.value

    @property
    def name(self) -> str:
        """Canonical error name, e.g. ``"UNKNOWN_CAPABILITY"``."""
        return self.code.name


# ---------------------------------------------------------------------------
# Formatting helpers (Section 9.7)
# ---------------------------------------------------------------------------

def format_error(error: StandardError) -> dict[str, Any]:
    """Return the standard JSON-serialisable envelope for a single error.

    The output matches the format mandated by Section 9.7::

        {
          "error": {
            "code": "V101",
            "name": "UNKNOWN_CAPABILITY",
            "message": "...",
            "location": {...},
            "suggestion": "..."
          }
        }

    When *suggestion* is ``None`` the key is omitted from the inner dict.
    """
    inner: dict[str, Any] = {
        "code": error.code_str,
        "name": error.name,
        "message": error.message,
        "location": error.location,
    }
    if error.suggestion is not None:
        inner["suggestion"] = error.suggestion
    return {"error": inner}


def format_errors_response(errors: list[StandardError]) -> dict[str, Any]:
    """Return a JSON-serialisable response containing multiple errors.

    Returns::

        {
          "errors": [
            {"code": "V101", "name": "...", "message": "...", ...},
            ...
          ]
        }

    Each element uses the same inner structure as :func:`format_error`
    (without the outer ``"error"`` wrapper).
    """
    items: list[dict[str, Any]] = []
    for err in errors:
        item: dict[str, Any] = {
            "code": err.code_str,
            "name": err.name,
            "message": err.message,
            "location": err.location,
        }
        if err.suggestion is not None:
            item["suggestion"] = err.suggestion
        items.append(item)
    return {"errors": items}
