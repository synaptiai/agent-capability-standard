"""
Grounded Client Wrapper

Wraps ``ClaudeSDKClient`` with the Grounded Agency safety layer,
providing an async context manager that automatically injects
checkpoint enforcement, evidence collection, and audit hooks.

Example::

    from grounded_agency import GroundedClient, GroundedAgentAdapter

    adapter = GroundedAgentAdapter()
    adapter.create_checkpoint(["*"], "Before edits")

    async with GroundedClient(adapter) as client:
        await client.query("Refactor the config module")
        async for msg in client.receive_response():
            print(msg)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from .adapter import GroundedAgentAdapter, GroundedAgentConfig

logger = logging.getLogger("grounded_agency.client")


class GroundedClient:
    """Wraps ``ClaudeSDKClient`` with grounded safety.

    Automatically applies :meth:`GroundedAgentAdapter.wrap_options`
    to inject checkpoint enforcement, evidence collection, and audit
    hooks before constructing the underlying SDK client.

    Attributes:
        adapter: The :class:`GroundedAgentAdapter` providing safety.

    Example::

        adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
        adapter.create_checkpoint(["*.py"], "Before changes")

        async with GroundedClient(adapter) as client:
            await client.query("Add type hints to utils.py")
            async for msg in client.receive_response():
                print(msg)

        print("Evidence:", adapter.get_evidence())
    """

    def __init__(
        self,
        adapter: GroundedAgentAdapter | None = None,
        config: GroundedAgentConfig | None = None,
        options: Any | None = None,
    ) -> None:
        """Initialize the grounded client.

        Args:
            adapter: Pre-configured adapter.  If *None*, one is created
                from *config*.
            config: Configuration for the adapter.  Ignored when
                *adapter* is provided.
            options: Optional base ``ClaudeAgentOptions``.  Safety
                layer is applied on top.
        """
        # Lazy import check — done at init so the error is clear
        try:
            from claude_agent_sdk import ClaudeAgentOptions
        except ImportError as exc:
            raise ImportError(
                "claude_agent_sdk is required for GroundedClient. "
                "Install with: pip install claude-agent-sdk"
            ) from exc

        self.adapter = adapter or GroundedAgentAdapter(config or GroundedAgentConfig())
        self._base_options = options or ClaudeAgentOptions()
        self._wrapped_options = self.adapter.wrap_options(self._base_options)
        self._client: Any = None
        self._result_message_cls: type | None = None

    async def __aenter__(self) -> GroundedClient:
        """Enter the async context, creating the SDK client."""
        from claude_agent_sdk import ClaudeSDKClient

        # Cache ResultMessage class once at context entry
        try:
            from claude_agent_sdk import ResultMessage

            self._result_message_cls = ResultMessage
        except ImportError:
            self._result_message_cls = None

        self._client = ClaudeSDKClient(options=self._wrapped_options)
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit the async context, cleaning up the SDK client."""
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)
            self._client = None

    async def query(self, prompt: str) -> None:
        """Send a query to the underlying SDK client.

        Args:
            prompt: The user prompt to send.

        Raises:
            RuntimeError: If used outside an async context manager.
        """
        if self._client is None:
            raise RuntimeError(
                "GroundedClient must be used as an async context manager. "
                "Use: async with GroundedClient(...) as client:"
            )
        await self._client.query(prompt)

    async def receive_response(self) -> AsyncIterator[Any]:
        """Receive and yield response messages.

        Captures ``ResultMessage`` cost data in the adapter's
        cost summary.

        Yields:
            Messages from the SDK client.

        Raises:
            RuntimeError: If used outside an async context manager.
        """
        if self._client is None:
            raise RuntimeError(
                "GroundedClient must be used as an async context manager."
            )

        async for msg in self._client.receive_response():
            # Capture cost when ResultMessage type is available
            if self._result_message_cls is not None and isinstance(
                msg, self._result_message_cls
            ):
                from .query import _update_cost_summary

                _update_cost_summary(self.adapter, msg)
            yield msg
