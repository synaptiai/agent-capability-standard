"""
Capability-Aware MCP Server Factory

Creates MCP servers where tools are automatically mapped to Grounded
Agency capabilities, enabling safety enforcement (checkpoint requirements,
approval, risk levels, rate limits) for MCP-provided tools.

Example::

    from grounded_agency import GroundedAgentAdapter
    from grounded_agency.mcp import create_grounded_mcp_server

    adapter = GroundedAgentAdapter()
    server = create_grounded_mcp_server(
        name="my-tools",
        version="1.0.0",
        tools=[search_tool, write_tool],
        adapter=adapter,
    )
"""

from __future__ import annotations

import logging
from typing import Any

from .adapter import GroundedAgentAdapter

logger = logging.getLogger("grounded_agency.mcp")


def create_grounded_mcp_server(
    *,
    name: str,
    version: str,
    tools: list[Any],
    adapter: GroundedAgentAdapter,
) -> Any:
    """Create an MCP server with capability-aware tool mappings.

    Wraps ``claude_agent_sdk.create_sdk_mcp_server()`` and auto-registers
    each tool in the adapter's :class:`ToolCapabilityMapper` so that
    safety enforcement (checkpoints, approval, rate limits) applies to MCP
    tools.

    Each tool may optionally carry ``metadata`` with:

    - ``capability_id`` (str): The ontology capability this tool exercises
      (defaults to ``"execute"``).
    - ``risk`` (str): Risk level — ``"low"``, ``"medium"``, or ``"high"``
      (defaults to the capability's).
    - ``mutation`` (bool): Whether the tool mutates state
      (defaults to the capability's, or ``True`` for a declared high risk).
    - ``requires_checkpoint`` (bool): Whether a checkpoint is needed
      (defaults to the capability's, or ``True`` for a declared high risk).
    - ``requires_approval`` (bool): Whether a call needs approval
      (defaults to the capability's).
    - ``domain`` (str): The capability's domain parameter.

    The registered flags are the stricter of the metadata's and the
    ontology's (STANDARD v1.1 section 5.2.1); a weaker one has no effect
    and is reported as W602 in ``adapter.mapper.warnings``. A tool with no
    metadata is an ``execute`` tool, which requires approval.

    Args:
        name: MCP server name.
        version: MCP server version string.
        tools: List of MCP tool objects (decorated with ``@tool``).
        adapter: The :class:`GroundedAgentAdapter` to register mappings in.

    Returns:
        The MCP server instance from the SDK.

    Raises:
        ImportError: If ``claude_agent_sdk`` is not installed.
        ValueError: If a tool's metadata names a capability the ontology
            does not define (V101 UNKNOWN_CAPABILITY), or holds a risk or
            flag of the wrong type. No server is created.

    Example::

        from claude_agent_sdk import tool

        @tool
        def search_docs(query: str) -> str:
            '''Search documentation.'''
            return "results..."

        search_docs.metadata = {
            "capability_id": "search",
            "risk": "low",
        }

        server = create_grounded_mcp_server(
            name="doc-tools",
            version="1.0.0",
            tools=[search_docs],
            adapter=adapter,
        )
    """
    try:
        from claude_agent_sdk import create_sdk_mcp_server
    except ImportError as exc:
        raise ImportError(
            "claude_agent_sdk is required for create_grounded_mcp_server(). "
            "Install with: pip install claude-agent-sdk"
        ) from exc

    # Register each tool's capability mapping in the adapter, before the
    # server exists: a declaration the mapper refuses raises here.
    for t in tools:
        tool_name_for_mapping = f"mcp__{name}__{_get_tool_name(t)}"
        metadata = getattr(t, "metadata", None) or {}

        mapping = adapter.mapper.register_mcp_tool(
            tool_name=tool_name_for_mapping,
            capability_id=metadata.get("capability_id", "execute"),
            risk=metadata.get("risk"),
            mutation=metadata.get("mutation"),
            requires_checkpoint=metadata.get("requires_checkpoint"),
            requires_approval=metadata.get("requires_approval"),
            domain=metadata.get("domain"),
        )

        logger.info("Registered MCP tool %s → %s", tool_name_for_mapping, mapping)

    return create_sdk_mcp_server(name=name, version=version, tools=tools)


def _get_tool_name(tool: Any) -> str:
    """Extract the tool name from an MCP tool object."""
    # Try common attribute names
    for attr in ("name", "__name__", "tool_name"):
        name = getattr(tool, attr, None)
        if name:
            return str(name)
    logger.warning(
        "Could not determine tool name for %r; falling back to 'unknown'", tool
    )
    return "unknown"
