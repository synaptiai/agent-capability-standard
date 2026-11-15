"""
Capability output over a text-only channel (STANDARD 1.2.0 section 5.18.9).

Where a host carries a capability output as a string (a tool's result, a
sub-prompt's or a model's reply, the string a host turns into the output of
an executor's capability call), it travels as the I-JSON text (RFC 7493) of
the output object, with nothing before or after it. A consumer parses the
text and checks that it is an object with every field the capability's
output contract requires; a producer checks the I-JSON limits before it
sends. Either failure is R402 EXECUTION_FAILED.

:func:`encode_capability_output` is the producer's side and
:func:`decode_capability_output` the consumer's. The TypeScript package's
``encodeCapabilityOutput`` and ``decodeCapabilityOutput``
(``packages/acs-core/src/output.ts``) apply the same rules.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

from ..errors import ErrorCode, ValidationError, text_form

if TYPE_CHECKING:
    from .registry import CapabilityRegistry

__all__ = [
    "CapabilityOutputError",
    "check_i_json",
    "decode_capability_output",
    "encode_capability_output",
]

# I-JSON limits, as the reference executor applies them (core/src/exec):
# integers of magnitude at most 2^53, values nested at most 100 levels.
_INT_LIMIT = 2**53
_MAX_DEPTH = 100


class CapabilityOutputError(ValueError):
    """A capability output that breaks section 5.18.9 (R402).

    ``error`` is the diagnostic; ``str()`` is its text form.
    """

    def __init__(self, error: ValidationError) -> None:
        super().__init__(text_form(error))
        self.error = error


def _fail(capability: str, message: str, field: str | None = None) -> None:
    """Raise R402. ``message`` follows "the '<capability>' output"."""
    location: dict[str, Any] = {"capability": capability}
    if field is not None:
        location["field"] = field
    joiner = "" if message.startswith("'s ") else " "
    raise CapabilityOutputError(
        ValidationError(
            ErrorCode.EXECUTION_FAILED,
            f"the '{capability}' output{joiner}{message}",
            location,
        )
    )


def check_i_json(value: Any, capability: str = "", path: str = "$") -> None:
    """Check that ``value`` is I-JSON (RFC 7493) within the executor's
    limits: integers of magnitude at most 2^53, finite numbers, strings
    without lone surrogates, string object keys, nesting at most 100 levels.

    Raises:
        CapabilityOutputError: R402, naming the first value that fails.
    """
    stack: list[tuple[Any, str, int]] = [(value, path, 0)]
    while stack:
        v, at, depth = stack.pop()
        if depth > _MAX_DEPTH:
            _fail(capability, f"nests deeper than {_MAX_DEPTH} levels at {at}")
        if v is None or isinstance(v, bool):
            continue
        if isinstance(v, int):
            if abs(v) > _INT_LIMIT:
                _fail(
                    capability,
                    f"holds the integer {v} at {at}, outside ±2^53, which has "
                    f"no exact I-JSON form",
                )
        elif isinstance(v, float):
            if not math.isfinite(v):
                _fail(capability, f"holds {v} at {at}, which is not a JSON number")
        elif isinstance(v, str):
            _check_text(capability, v, at)
        elif isinstance(v, list):
            stack.extend((x, f"{at}[{i}]", depth + 1) for i, x in enumerate(v))
        elif isinstance(v, dict):
            for key, x in v.items():
                if not isinstance(key, str):
                    _fail(capability, f"has a non-string key {key!r} at {at}")
                _check_text(capability, key, at)
                stack.append((x, f"{at}.{key}", depth + 1))
        else:
            _fail(capability, f"holds a {type(v).__name__} at {at}, not JSON")


def _check_text(capability: str, text: str, at: str) -> None:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        _fail(capability, f"holds a string with a lone surrogate at {at}")


def _required(capability: str, registry: CapabilityRegistry | None) -> list[str]:
    if registry is None:
        from .mapper import _get_default_registry

        registry = _get_default_registry()
    node = registry.get_capability(capability)
    if node is None:
        raise CapabilityOutputError(
            ValidationError(
                ErrorCode.UNKNOWN_CAPABILITY,
                f"capability {capability!r} is not in the ontology",
                {"capability": capability},
            )
        )
    required = node.output_schema.get("required") or []
    return [f for f in required if isinstance(f, str)]


def _check_contract(
    capability: str, output: Any, registry: CapabilityRegistry | None
) -> dict[str, Any]:
    if not isinstance(output, dict):
        _fail(capability, "is not a JSON object")
    required = _required(capability, registry)
    missing = [f for f in required if f not in output]
    if missing:
        _fail(capability, f"is missing {', '.join(missing)}", missing[0])
    if "evidence_anchors" in output and not isinstance(
        output["evidence_anchors"], list
    ):
        _fail(capability, "'s evidence_anchors is not an array", "evidence_anchors")
    if "confidence" in required:
        confidence = output.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            _fail(
                capability,
                "'s confidence is not a number from 0 to 1",
                "confidence",
            )
    check_i_json(output, capability)
    checked: dict[str, Any] = output
    return checked


def encode_capability_output(
    capability: str,
    output: Any,
    registry: CapabilityRegistry | None = None,
) -> str:
    """The text a capability output travels as on a string channel: the
    I-JSON text of the object, nothing around it.

    Args:
        capability: The capability whose output contract applies.
        output: The output object.
        registry: The ontology; the packaged one when omitted.

    Raises:
        CapabilityOutputError: R402 if ``output`` is not an object, lacks a
            required field, or is not I-JSON.
    """
    _check_contract(capability, output, registry)
    return json.dumps(
        output, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate member {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not a JSON number")


def decode_capability_output(
    capability: str,
    text: str,
    registry: CapabilityRegistry | None = None,
) -> dict[str, Any]:
    """Read a capability output carried as a string (section 5.18.9).

    The text must be the I-JSON text of one object and nothing else: no
    prose, fence or second value around it, no duplicate member, no NaN or
    Infinity, every field the capability's output contract requires.

    Raises:
        CapabilityOutputError: R402 otherwise. A host that answers an
            executor's capability call answers it with an error then.
    """
    if not isinstance(text, str):
        _fail(capability, f"arrived as a {type(text).__name__}, not as text")
    try:
        value = json.loads(
            text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant
        )
    except (ValueError, RecursionError) as e:
        _fail(capability, f"is not the JSON text of one object and nothing else: {e}")
    return _check_contract(capability, value, registry)
