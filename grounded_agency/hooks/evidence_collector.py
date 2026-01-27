"""
Evidence Collector Hook

PostToolUse hook that captures evidence anchors from tool executions.
This enables provenance tracking for grounded decisions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..capabilities.mapper import ToolCapabilityMapper
from ..state.evidence_store import EvidenceAnchor, EvidenceStore

if TYPE_CHECKING:
    from .. import HookCallback

logger = logging.getLogger("grounded_agency.hooks.evidence_collector")


def create_evidence_collector(
    store: EvidenceStore,
    mapper: ToolCapabilityMapper | None = None,
) -> HookCallback:
    """
    Create a PostToolUse hook that collects evidence anchors.

    The hook captures:
    - Tool name and ID
    - Tool input parameters
    - Capability ID (via mapper)
    - Timestamp

    This evidence can later be used to verify that decisions
    are grounded in actual observations.

    Args:
        store: EvidenceStore to add anchors to
        mapper: Optional mapper to associate anchors with capabilities

    Returns:
        Async hook callback function

    Example:
        store = EvidenceStore()
        hook = create_evidence_collector(store)
        # Hook is invoked by SDK after each tool use
    """
    mapper_instance = mapper or ToolCapabilityMapper()

    async def collect_evidence(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: Any,
    ) -> dict[str, Any]:
        """
        PostToolUse hook that captures evidence from tool execution.

        Args:
            input_data: Contains tool_name, tool_input, tool_response
            tool_use_id: Unique identifier for this tool use
            context: SDK hook context (HookContext)

        Returns:
            Empty dict (passive observation, doesn't modify execution)
        """
        try:
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input", {})
            tool_response = input_data.get("tool_response")

            # Create evidence anchor
            anchor = EvidenceAnchor.from_tool_output(
                tool_name=tool_name,
                tool_use_id=tool_use_id or "unknown",
                tool_input=tool_input,
                tool_response=tool_response,
            )

            # Determine associated capability
            capability_id = None
            if mapper_instance:
                try:
                    mapping = mapper_instance.map_tool(tool_name, tool_input)
                    capability_id = mapping.capability_id
                except Exception:
                    pass

            # Add to store
            store.add_anchor(anchor, capability_id=capability_id)

            # For file operations, also add a file evidence anchor
            if tool_name in ("Read", "Write", "Edit", "MultiEdit"):
                file_path = tool_input.get("file_path") or tool_input.get("path")
                if file_path:
                    operation = "read" if tool_name == "Read" else "write"
                    file_anchor = EvidenceAnchor.from_file(
                        file_path=file_path,
                        operation=operation,
                    )
                    store.add_anchor(file_anchor, capability_id=capability_id)

            # For Bash commands, add command evidence
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                exit_code = 0
                if isinstance(tool_response, dict):
                    exit_code = tool_response.get("exit_code", 0)
                elif tool_response is not None and hasattr(tool_response, "exit_code"):
                    exit_code = getattr(tool_response, "exit_code", 0)

                cmd_anchor = EvidenceAnchor.from_command(
                    command=command,
                    exit_code=exit_code,
                    tool_use_id=tool_use_id,
                )
                store.add_anchor(cmd_anchor, capability_id=capability_id)

        except Exception as e:
            # Fail silently - evidence collection is observational
            logger.warning("Evidence collection failed: %s", e)

        # Return empty dict - we don't modify execution
        return {}

    return collect_evidence
