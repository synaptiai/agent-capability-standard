"""
Grounded Query Wrapper

Drop-in replacement for ``claude_agent_sdk.query()`` that auto-injects
the Grounded Agency safety layer and enriches result messages with
capability metadata and cost tracking.

Example::

    from grounded_agency import grounded_query, GroundedAgentConfig

    async for message in grounded_query("Refactor auth module"):
        print(message)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .adapter import GroundedAgentAdapter, GroundedAgentConfig

if TYPE_CHECKING:
    from claude_agent_sdk import Message

logger = logging.getLogger("grounded_agency.query")


@dataclass(slots=True)
class CostSummary:
    """Tracks cumulative cost across query invocations.

    Attributes:
        total_usd: Total cost in USD.
        by_model: Per-model cost breakdown.
        turn_count: Number of turns (result messages) observed.
    """

    total_usd: float = 0.0
    by_model: dict[str, float] = field(default_factory=dict)
    turn_count: int = 0


async def grounded_query(
    prompt: str,
    *,
    options: Any | None = None,
    config: GroundedAgentConfig | None = None,
    adapter: GroundedAgentAdapter | None = None,
) -> AsyncIterator[Message]:
    """Drop-in replacement for ``query()`` with grounded safety.

    Creates or reuses a :class:`GroundedAgentAdapter`, wraps the
    provided (or default) options with the safety layer, and yields
    messages from the SDK's ``query()`` generator.

    When a ``ResultMessage`` is received the adapter's last-result
    state is updated so callers can access cost and evidence summary
    after iteration completes.

    Args:
        prompt: The user prompt to send to the agent.
        options: Optional ``ClaudeAgentOptions`` instance.  If *None*,
            a default instance is created.
        config: Optional ``GroundedAgentConfig``.  Ignored when
            *adapter* is provided.
        adapter: Optional pre-configured adapter.  When omitted a new
            one is constructed from *config*.

    Yields:
        Messages from the SDK (``AssistantMessage``, ``ResultMessage``,
        ``SystemMessage``, etc.).

    Raises:
        ImportError: If ``claude_agent_sdk`` is not installed.

    Example::

        adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
        adapter.create_checkpoint(["*.py"], "Before changes")

        async for msg in grounded_query("Edit utils.py", adapter=adapter):
            print(type(msg).__name__, msg)

        print("Cost:", adapter.cost_summary.total_usd)
    """
    # Lazy import — fails fast with a clear message
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
        from claude_agent_sdk import query as sdk_query
    except ImportError as exc:
        raise ImportError(
            "claude_agent_sdk is required for grounded_query(). "
            "Install with: pip install claude-agent-sdk"
        ) from exc

    if adapter is None:
        adapter = GroundedAgentAdapter(config or GroundedAgentConfig())

    base = options or ClaudeAgentOptions()
    wrapped = adapter.wrap_options(base)

    stream = sdk_query(prompt=prompt, options=wrapped)
    try:
        async for message in stream:
            # Capture cost and metadata from ResultMessage
            if isinstance(message, ResultMessage):
                _update_cost_summary(adapter, message)
            yield message
    finally:
        # ``async for`` does not close its iterator when the loop body breaks
        # or raises -- PEP 533 was deferred -- and this generator re-yields
        # from the SDK's. Without this, a caller that breaks out of
        # ``grounded_query`` leaves the inner generator open, so its
        # ``finally: await query.close()`` -- the call that terminates the CLI
        # subprocess -- is deferred to garbage collection rather than running
        # at the break. The SDK guards its own re-yield the same way; see
        # ``claude_agent_sdk/_internal/client.py``.
        #
        # Closed via getattr rather than ``contextlib.aclosing`` because the
        # SDK types ``query()`` as an AsyncIterator, which does not promise
        # ``aclose``. Every shipped version returns an async generator, so this
        # branch is taken in practice; the guard keeps a future iterator-only
        # return from raising AttributeError during cleanup.
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()


def _update_cost_summary(adapter: GroundedAgentAdapter, result: Any) -> None:
    """Extract cost information from a ResultMessage into the adapter."""
    cost = getattr(result, "total_cost_usd", None)
    model = getattr(result, "model", None)

    summary = adapter.cost_summary
    summary.turn_count += 1

    if cost is not None:
        # SDK reports cumulative cost — compute per-turn delta for model breakdown
        delta = cost - summary.total_usd
        summary.total_usd = cost
        if model and delta > 0:
            summary.by_model[model] = summary.by_model.get(model, 0.0) + delta

    logger.debug(
        "ResultMessage captured: cost=%.4f model=%s turns=%d",
        summary.total_usd,
        model,
        summary.turn_count,
    )
