"""
Grounded Agency -- Standard Error Model

Implements the diagnostic codes and formatting defined in Section 9 of the
Standard (v1.1.0): error codes in five categories (Validation, Binding,
Schema, Runtime, Safety) and warning codes (W6xx), with a structured JSON
response format. The list mirrors the Rust core's (``_core.CODES``); a test
keeps the two identical.

This is a leaf module -- zero imports from other grounded_agency modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Diagnostic codes (Section 9)
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Severity of a diagnostic, fixed per code. Errors make a workflow
    invalid; warnings do not unless a caller asks for strict validation."""

    ERROR = "error"
    WARNING = "warning"


class ErrorCode(Enum):
    """All standard diagnostic codes grouped by category.

    Each member's *value* is the short code string (e.g. ``"V101"``);
    the member *name* is the canonical name (e.g. ``UNKNOWN_CAPABILITY``).
    """

    # -- 9.2 Validation errors (V1xx) --------------------------------------
    UNKNOWN_CAPABILITY = "V101"
    MISSING_PREREQUISITE = "V102"
    INVALID_STEP = "V103"
    DUPLICATE_STORE_AS = "V104"
    CIRCULAR_DEPENDENCY = "V105"
    UNSUPPORTED_EXTENSION = "V106"
    UNRESOLVED_TARGET = "V107"
    INVALID_EXPRESSION = "V108"
    UNSUPPORTED_SPEC_VERSION = "V109"

    # -- 9.3 Binding errors (B2xx) ------------------------------------------
    INVALID_BINDING_PATH = "B201"
    MISSING_PRODUCER = "B202"
    TYPE_MISMATCH = "B203"
    AMBIGUOUS_TYPE = "B204"
    INVALID_ANNOTATION = "B205"
    EXPRESSION_TYPE_ERROR = "B206"

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
    EXPRESSION_ERROR = "R405"
    LIVENESS_LOST = "R406"

    # -- 9.6 Safety errors (F5xx) -------------------------------------------
    CHECKPOINT_REQUIRED = "F501"
    APPROVAL_REQUIRED = "F502"
    ROLLBACK_FAILED = "F503"
    CONSTRAINT_VIOLATED = "F504"
    PROVENANCE_MISSING = "F505"

    # -- Warnings (W6xx) ----------------------------------------------------
    SOFT_REQUIREMENT_UNMET = "W601"
    SAFETY_FLAG_DOWNGRADE = "W602"
    DEPRECATED_FORM = "W603"
    UNKNOWN_FIELD = "W604"
    MISSING_SPEC_VERSION = "W605"
    UNATTENDED_APPROVAL = "W606"
    UNRESOLVED_WORKFLOW = "W607"
    WAIT_SPANS_CHECKPOINT = "W608"
    UNTRIGGERED_FAILURE_MODE = "W609"
    NULLABLE_OPERAND = "W610"
    CONSTANT_COMPARISON = "W611"
    MANGLED_REFERENCE = "W612"
    UNREACHABLE_HANDLER = "W613"
    INVALID_DURATION = "W614"
    MISSING_INPUT = "W615"
    VERSION_FEATURE_MISMATCH = "W616"

    @property
    def severity(self) -> Severity:
        """W6xx codes are warnings; every other code is an error."""
        return Severity.WARNING if self.value.startswith("W") else Severity.ERROR


# ---------------------------------------------------------------------------
# Error dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationError:
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

    @property
    def severity(self) -> Severity:
        """The code's fixed severity."""
        return self.code.severity

    @classmethod
    def from_core(cls, diagnostic: dict[str, Any]) -> ValidationError:
        """Build from one diagnostic of a ``_core`` validation report."""
        return cls(
            code=ErrorCode(diagnostic["code"]),
            message=diagnostic["message"],
            location=dict(diagnostic.get("location") or {}),
            suggestion=diagnostic.get("suggestion"),
        )


# ---------------------------------------------------------------------------
# Formatting helpers (Section 9.7)
# ---------------------------------------------------------------------------


def _error_to_dict(error: ValidationError) -> dict[str, Any]:
    """Convert a ValidationError to a JSON-serialisable dict.

    Omits ``suggestion`` when it is ``None``.
    """
    d: dict[str, Any] = {
        "code": error.code_str,
        "name": error.name,
        "severity": error.severity.value,
        "message": error.message,
        "location": error.location,
    }
    if error.suggestion is not None:
        d["suggestion"] = error.suggestion
    return d


def format_error(error: ValidationError) -> dict[str, Any]:
    """Return the standard JSON-serialisable envelope for a single error.

    The output matches the format mandated by Section 9.7::

        {
          "error": {
            "code": "V101",
            "name": "UNKNOWN_CAPABILITY",
            "severity": "error",
            "message": "...",
            "location": {...},
            "suggestion": "..."
          }
        }

    When *suggestion* is ``None`` the key is omitted from the inner dict.
    """
    return {"error": _error_to_dict(error)}


def format_errors_response(errors: list[ValidationError]) -> dict[str, Any]:
    """Return a JSON-serialisable response containing multiple errors.

    Returns::

        {
          "errors": [
            {"code": "V101", "name": "...", "severity": "...", ...},
            ...
          ]
        }

    Each element uses the same inner structure as :func:`format_error`
    (without the outer ``"error"`` wrapper).
    """
    return {"errors": [_error_to_dict(err) for err in errors]}
