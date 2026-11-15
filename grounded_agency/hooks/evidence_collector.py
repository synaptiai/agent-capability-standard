"""
Evidence Collector Hook

PostToolUse hook that captures evidence anchors from tool executions.
This enables provenance tracking for grounded decisions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..capabilities.mapper import UNCLASSIFIED_TOOL, ToolCapabilityMapper
from ..state.evidence_store import EvidenceAnchor, EvidenceStore

if TYPE_CHECKING:
    from .._types import HookCallback, HookContext

logger = logging.getLogger("grounded_agency.hooks.evidence_collector")


def create_evidence_collector(
    store: EvidenceStore,
    mapper: ToolCapabilityMapper | None = None,
    *,
    include_tool_input: bool = False,
    required: bool = False,
) -> HookCallback:
    """
    Create a PostToolUse hook that collects evidence anchors.

    The hook captures:
    - Tool name and ID
    - Capability ID (via mapper); none for a tool the mapper does not know
    - Timestamp
    - The file path of a file tool's call
    - Tool input parameters, and a Bash command's text, only with
      ``include_tool_input``: inputs can hold credentials

    This evidence can later be used to verify that decisions
    are grounded in actual observations.

    Args:
        store: EvidenceStore to add anchors to
        mapper: Optional mapper to associate anchors with capabilities
        include_tool_input: Keep each call's input in its anchor's
            metadata, and a Bash command's text in its command anchor
        required: The capture is required (STANDARD v1.2 §6.4): a call
            whose evidence could not be recorded is reported to the model
            in the hook's result (R402, reason ``not_recorded``), logged at
            error level, and handed to the store's
            ``record_capture_failure`` when it has one. By default the
            capture is best-effort: a failure is logged as a warning, never
            silently dropped.

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
        context: HookContext | None,
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
                include_tool_input=include_tool_input,
            )

            # Determine associated capability. A tool with no classification
            # is evidence of no particular capability.
            capability_id = None
            if mapper_instance:
                try:
                    mapping = mapper_instance.map_tool(tool_name, tool_input)
                    if mapping is not UNCLASSIFIED_TOOL:
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
                    command=command if include_tool_input else None,
                    exit_code=exit_code,
                    tool_use_id=tool_use_id,
                )
                store.add_anchor(cmd_anchor, capability_id=capability_id)

        except Exception as e:
            # A best-effort capture that fails is reported where the
            # operator sees it; a required one also where the call's result
            # goes (§6.4). The call itself has already run.
            if not required:
                logger.warning("Evidence collection failed: %s", e)
                return {}
            logger.error("Evidence collection failed (required): %s", e)
            report = getattr(store, "record_capture_failure", None)
            if callable(report):
                try:
                    report(tool_use_id, str(e))
                except Exception as nested:
                    logger.error("Could not report the capture failure: %s", nested)
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        "R402 EXECUTION_FAILED: the call ran, but its evidence was "
                        f"not recorded (not_recorded): {e}"
                    ),
                }
            }

        # Return empty dict - we don't modify execution
        return {}

    return collect_evidence
