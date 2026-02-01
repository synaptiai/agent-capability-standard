"""
Grounded Agency — Shared Type Definitions

Protocol types for Claude Agent SDK interop, avoiding hard dependency.
Uses structural subtyping so any object with matching shape satisfies
the contract without inheritance.

This is a leaf module — zero imports from other grounded_agency modules.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HookContext(Protocol):
    """Structural match for the SDK's hook context object.

    The SDK passes a context object to hook callbacks containing
    conversation state and tool metadata. This Protocol matches
    any object with the expected attributes, or ``None`` when
    the SDK omits context.

    Extend this Protocol as the SDK adds new context fields
    (e.g., ``conversation_id``, ``session_metadata``).
    """

    @property
    def tool_name(self) -> str: ...

    @property
    def tool_use_id(self) -> str: ...


# Canonical type alias for hook callbacks
HookCallback = Callable[
    [dict[str, Any], str | None, HookContext | None],
    Coroutine[Any, Any, dict[str, Any]],
]


@dataclass(frozen=True, slots=True)
class FallbackPermissionAllow:
    """Returned when SDK ``PermissionResultAllow`` is unavailable.

    Mirrors the SDK type so callers can use the same interface
    regardless of whether ``claude_agent_sdk`` is installed.
    """

    allowed: bool = True
    updated_input: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class FallbackPermissionDeny:
    """Returned when SDK ``PermissionResultDeny`` is unavailable.

    Mirrors the SDK type so callers can use the same interface
    regardless of whether ``claude_agent_sdk`` is installed.
    """

    allowed: bool = False
    message: str = ""
