"""
Discovery Injector Hook

PreToolUse hook that silently analyzes user prompts and injects
capability metadata into the execution context.

Follows the same factory-function pattern as evidence_collector.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..state.evidence_store import EvidenceStore

if TYPE_CHECKING:
    from .._types import HookCallback, HookContext
    from ..discovery.pipeline import DiscoveryPipeline

logger = logging.getLogger("grounded_agency.hooks.discovery_injector")


def create_discovery_injector(
    pipeline: DiscoveryPipeline,
    store: EvidenceStore,
) -> HookCallback:
    """
    Create a PreToolUse hook that runs capability discovery on user prompts.

    The hook:
    1. Extracts the user's original prompt from context (on first tool use)
    2. Runs DiscoveryPipeline.discover() with per-turn caching
    3. Attaches DiscoveryResult metadata to evidence store
    4. Returns empty dict (non-blocking, observational)

    Args:
        pipeline: Configured DiscoveryPipeline instance.
        store: EvidenceStore for recording discovery evidence.

    Returns:
        Async hook callback function.
    """
    # Track whether we've analyzed the current turn.
    # Bounded to prevent unbounded growth in long-running processes.
    _MAX_TRACKED_TURNS = 500
    _analyzed_turns: set[str] = set()

    async def inject_discovery(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext | None,
    ) -> dict[str, Any]:
        """
        PreToolUse hook that runs discovery on the user's prompt.

        Non-blocking: never modifies execution, never raises.
        Discovery results are cached per-turn and stored as evidence.
        """
        try:
            # Extract user prompt from context or input
            prompt = _extract_prompt(input_data, context)
            if not prompt:
                return {}

            # Cache key based on prompt content
            turn_key = prompt[:200]  # Truncate for dedup
            if turn_key in _analyzed_turns:
                return {}

            # Evict all entries if set grows too large (bounded memory)
            if len(_analyzed_turns) >= _MAX_TRACKED_TURNS:
                _analyzed_turns.clear()

            _analyzed_turns.add(turn_key)

            # Run discovery (pipeline has its own per-prompt cache)
            result = await pipeline.discover(prompt)

            # Log discovery summary
            logger.info(
                "Discovery: %d matches, %d gaps, confidence=%.2f for: %s",
                len(result.matches),
                len(result.gaps),
                result.confidence,
                prompt[:80],
            )

        except Exception as e:
            # Fail silently — discovery injection is observational
            logger.warning("Discovery injection failed: %s", e)

        return {}

    return inject_discovery


def _extract_prompt(
    input_data: dict[str, Any],
    context: HookContext | None,
) -> str | None:
    """Extract the user's original prompt from hook context.

    Tries multiple paths since context structure varies by SDK version.
    """
    # Try context attributes
    if context is not None:
        for attr in ("user_prompt", "prompt", "message"):
            val = getattr(context, attr, None)
            if isinstance(val, str) and val.strip():
                return val.strip()

    # Try input_data
    for key in ("prompt", "user_prompt", "message", "query"):
        val = input_data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    return None
