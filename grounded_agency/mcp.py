"""
Capability-Aware MCP Server Factory

Creates MCP servers where tools are bound to Grounded Agency capabilities,
enabling safety enforcement (checkpoint requirements, approval, risk levels,
rate limits) for MCP-provided tools (STANDARD 1.2.0 section 5.18).

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
from .errors import Severity, text_form

logger = logging.getLogger("grounded_agency.mcp")

# Members of a tool binding record (schemas/interop/tool_binding.schema.json)
# that tool metadata may carry; `tool` and `ontology` the factory supplies.
_RECORD_MEMBERS: tuple[str, ...] = (
    "capability",
    "domain",
    "flags",
    "additional_capabilities",
    "classifier",
    "invokes",
    "approval",
    "control",
    "destination",
    "standard",
)
# The legacy flat keys, still accepted.
_LEGACY_FLAGS: tuple[str, ...] = (
    "risk",
    "mutation",
    "requires_checkpoint",
    "requires_approval",
)


def _record(
    full_name: str, server: str, ontology: str, metadata: dict[str, Any]
) -> dict[str, Any] | None:
    """The tool binding record a tool's metadata carries, or None for a
    tool with no capability that is not control-only (unbound).

    Raises:
        ValueError: S303 when ``capability`` and ``capability_id`` disagree,
            or a flag is given both flat and in ``flags`` with different
            values.
    """
    record: dict[str, Any] = {"tool": full_name, "ontology": ontology}
    for member in _RECORD_MEMBERS:
        if member in metadata:
            record[member] = metadata[member]
    for key, value in metadata.items():
        if isinstance(key, str) and key.startswith("x-"):
            record[key] = value
    if "capability_id" in metadata:
        legacy = metadata["capability_id"]
        if "capability" in record and record["capability"] != legacy:
            raise ValueError(
                f"S303 SCHEMA_VALIDATION_FAILED: tool '{full_name}' of server "
                f"'{server}' gives capability {record['capability']!r} and "
                f"capability_id {legacy!r}; give one"
            )
        record["capability"] = legacy
    flat = {k: metadata[k] for k in _LEGACY_FLAGS if k in metadata}
    if flat:
        flags = dict(record.get("flags") or {})
        if not isinstance(record.get("flags", {}), dict):
            return record  # the loader reports the malformed member
        for key, value in flat.items():
            if key in flags and flags[key] != value:
                raise ValueError(
                    f"S303 SCHEMA_VALIDATION_FAILED: tool '{full_name}' of "
                    f"server '{server}' declares {key} both as {value!r} and in "
                    f"flags as {flags[key]!r}"
                )
            flags[key] = value
        # A declared high risk implies a mutation that needs a checkpoint,
        # unless the metadata says otherwise (the earlier factory's rule).
        if flags.get("risk") == "high":
            flags.setdefault("mutation", True)
            flags.setdefault("requires_checkpoint", True)
        record["flags"] = flags
    if "capability" not in record and record.get("control") is not True:
        return None
    return record


def create_grounded_mcp_server(
    *,
    name: str,
    version: str,
    tools: list[Any],
    adapter: GroundedAgentAdapter,
    require_layer: bool = True,
) -> Any:
    """Create an MCP server with capability-aware tool mappings.

    Wraps ``claude_agent_sdk.create_sdk_mcp_server()`` and loads each tool's
    binding into the adapter's :class:`ToolCapabilityMapper`, as one set, so
    that safety enforcement (checkpoints, approval, rate limits) applies to
    MCP tools and ``invokes`` among them resolve.

    A tool's ``metadata`` is a carrier of the tool binding record (STANDARD
    1.2.0 section 5.18.1, ``schemas/interop/tool_binding.schema.json``): it
    holds the record's members except ``tool`` and ``ontology``, which the
    factory supplies (``mcp__<server>__<tool>`` and the adapter's ontology
    version):

    - ``capability`` (or the legacy ``capability_id``): the capability the
      tool performs;
    - ``domain``, ``flags`` (``risk``, ``mutation``, ``requires_checkpoint``,
      ``requires_approval``; the legacy flat keys are still accepted),
      ``additional_capabilities``, ``classifier``, ``invokes``,
      ``approval`` (``min_approvers``, ``role``, ``expires``), ``control``.

    The registered flags are the stricter of the metadata's and the
    ontology's (section 5.2.1); a weaker one has no effect and is reported
    as W602 in ``adapter.mapper.warnings``. A tool with no capability and
    not ``control: true`` is unbound (section 5.18.2): the strictest case,
    reported as W617 in ``adapter.mapper.warnings``.

    With ``require_layer`` (the default) each tool refuses to run, with
    ``R407 SAFETY_CHECK_FAILED``, unless the adapter's safety layer allowed
    this exact call (tool name and arguments), so a session whose options
    were not wrapped with :meth:`GroundedAgentAdapter.wrap_options` cannot
    run it (section 5.18.8). A control-only tool (``control: true``) is
    served as it is: it is never refused (section 5.18.3).
    ``require_layer=False`` restores the earlier behaviour and is outside
    class SL.

    Args:
        name: MCP server name.
        version: MCP server version string.
        tools: List of MCP tool objects (decorated with ``@tool``).
        adapter: The :class:`GroundedAgentAdapter` to register mappings in.
        require_layer: Refuse a call the adapter's layer did not allow.

    Returns:
        The MCP server instance from the SDK.

    Raises:
        ImportError: If ``claude_agent_sdk`` is not installed.
        ValueError: If a binding does not load: a capability the ontology
            does not define (V101 UNKNOWN_CAPABILITY), a member of the wrong
            type (S303), an ``invokes`` name that does not resolve (V107) or
            forms a cycle (V105). The message lists every error; no server is
            created.

    Example::

        from claude_agent_sdk import tool

        @tool("search_docs", "Search documentation.", {"query": str})
        async def search_docs(args):
            return {"content": [{"type": "text", "text": "results..."}]}

        search_docs.metadata = {"capability": "search"}

        server = create_grounded_mcp_server(
            name="doc-tools",
            version="1.0.0",
            tools=[search_docs],
            adapter=adapter,
        )
    """
    try:
        from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server
    except ImportError as exc:
        raise ImportError(
            "claude_agent_sdk is required for create_grounded_mcp_server(). "
            "Install with: pip install claude-agent-sdk"
        ) from exc

    # Read every tool's binding before the server exists: a binding that
    # does not load raises here and nothing is registered.
    ontology = adapter.mapper.ontology_version
    records: list[dict[str, Any]] = []
    unbound: list[str] = []
    for t in tools:
        full_name = f"mcp__{name}__{_get_tool_name(t)}"
        metadata = getattr(t, "metadata", None) or {}
        if not isinstance(metadata, dict):
            raise ValueError(
                f"S303 SCHEMA_VALIDATION_FAILED: tool '{full_name}' has metadata "
                f"that is not a dict"
            )
        record = _record(full_name, name, ontology, metadata)
        if record is None:
            unbound.append(full_name)
        else:
            records.append(record)

    from .capabilities.bindings import load_bindings

    _, diagnostics = load_bindings(
        records,
        {node.id: node for node in adapter.registry.all_capabilities()},
        [
            (e.from_cap, e.to_cap)
            for e in adapter.registry.all_edges()
            if e.edge_type == "requires"
        ],
        ontology,
        known=adapter.mapper._dynamic_mappings,
    )
    errors = [d for d in diagnostics if d.severity is Severity.ERROR]
    if errors:
        raise ValueError("; ".join(text_form(e) for e in errors))

    adapter.mapper.load_bindings(records)
    for full_name in unbound:
        adapter.mapper.register_mcp_tool(full_name)
    for record in records:
        logger.info(
            "Registered MCP tool %s → %s",
            record["tool"],
            adapter.mapper.map_tool(record["tool"], {}),
        )

    served = tools
    if require_layer:
        served = []
        for t in tools:
            full_name = f"mcp__{name}__{_get_tool_name(t)}"
            if adapter.mapper.map_tool(full_name, {}).control:
                # A control-only tool is never refused (section 5.18.3): no
                # check applies, so there is no decision to wait for.
                served.append(t)
            elif isinstance(t, SdkMcpTool):
                served.append(_guarded(t, full_name, adapter, SdkMcpTool))
            else:
                logger.warning(
                    "MCP tool %r is not an SdkMcpTool and cannot be guarded; a "
                    "call that reaches it without the safety layer's decision "
                    "will run",
                    t,
                )
                served.append(t)
    return create_sdk_mcp_server(name=name, version=version, tools=served)


def _guarded(tool: Any, full_name: str, adapter: GroundedAgentAdapter, cls: Any) -> Any:
    """``tool`` with a handler that refuses (R407) a call the adapter's
    layer did not allow."""
    handler = tool.handler

    async def guarded(args: Any) -> dict[str, Any]:
        if not adapter.take_allowed(full_name, args):
            logger.warning("%s ran without a safety layer decision; refused", full_name)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"R407 SAFETY_CHECK_FAILED: {full_name} ran without "
                            f"a safety layer decision; wrap the session's "
                            f"options with GroundedAgentAdapter.wrap_options()"
                        ),
                    }
                ],
                "is_error": True,
            }
        result: dict[str, Any] = await handler(args)
        refusal = _grounding_refusal(adapter, full_name, args, result)
        if refusal is not None:
            return {"content": [{"type": "text", "text": refusal}], "is_error": True}
        return result

    wrapped = cls(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        handler=guarded,
        annotations=tool.annotations,
    )
    metadata = getattr(tool, "metadata", None)
    if metadata is not None:
        try:
            wrapped.metadata = metadata
        except AttributeError:
            pass
    return wrapped


def _grounding_refusal(
    adapter: GroundedAgentAdapter, full_name: str, args: Any, result: Any
) -> str | None:
    """The F505 refusal of a call's output under the adapter's grounding
    policies (STANDARD v1.2 section 5.20), or None. The output is the
    result's ``structuredContent`` when it is an object, else the capability
    output its text carries (section 5.18.9); an error result is no output
    and is passed on."""
    if not adapter.config.grounding or not isinstance(result, dict):
        return None
    if result.get("is_error"):
        return None
    output: Any = result.get("structuredContent")
    if not isinstance(output, dict):
        output = None
        texts = [
            c.get("text")
            for c in result.get("content") or []
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        mapping = adapter.mapper.map_tool(
            full_name, args if isinstance(args, dict) else {}
        )
        capability = getattr(mapping, "capability_id", None)
        if len(texts) == 1 and isinstance(texts[0], str) and capability:
            from .capabilities.output import (
                CapabilityOutputError,
                decode_capability_output,
            )

            try:
                output = decode_capability_output(
                    capability, texts[0], adapter.registry
                )
            except CapabilityOutputError:
                output = None
    return adapter.check_call_output(full_name, args, output)


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
