"""
Evidence Collector Hook

PostToolUse hook that captures evidence anchors from tool executions.
This enables provenance tracking for grounded decisions.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from .. import _core
from ..capabilities.mapper import UNCLASSIFIED_TOOL, ToolCapabilityMapper
from ..state.evidence_store import EvidenceAnchor, EvidenceStoreProtocol
from ..state.redaction import DEFAULT_REDACTOR, Redactor

if TYPE_CHECKING:
    from .._types import HookCallback, HookContext

logger = logging.getLogger("grounded_agency.hooks.evidence_collector")


def response_digest(response: Any, redactor: Redactor = DEFAULT_REDACTOR) -> str | None:
    """The §6.5 ``digest`` of a tool's response, or None: of its UTF-8 text
    when it is a string or a dict whose ``content`` is a string, else of its
    canonical JSON (RFC 8785). None when the response is absent, is not JSON
    data, or holds a secret ``redactor`` recognises: the digest of a whole
    response that may be a secret alone (a one-line password file) could be
    inverted by guessing (STANDARD v1.2 §6.7)."""
    if response is None or redactor.holds_secret(response):
        return None
    if isinstance(response, str):
        data = response.encode("utf-8")
    elif isinstance(response, dict) and isinstance(response.get("content"), str):
        data = response["content"].encode("utf-8")
    else:
        try:
            data = _core.canonical_json(response).encode("utf-8")
        except ValueError, TypeError:
            return None
    return "sha256:" + hashlib.sha256(data).hexdigest()


def create_evidence_collector(
    store: EvidenceStoreProtocol,
    mapper: ToolCapabilityMapper | None = None,
    *,
    include_tool_input: bool = False,
    required: bool = False,
) -> HookCallback:
    """
    Create a PostToolUse hook that collects evidence anchors.

    The hook captures, in one ``append_many`` per call (one notification),
    with the capability, the tool's name and the call's id:
    - a ``tool`` anchor for the call, with the response's ``digest``
      (:func:`response_digest`) unless the response holds a recognised
      secret, in which case its metadata says ``digest_omitted: secret``
    - Capability ID (via mapper); none for a tool the mapper does not know
    - Timestamp
    - a ``file`` anchor for a file tool's path
    - a ``tool`` anchor (``command:<id>``) for a Bash call
    - Tool input parameters, and a Bash command's text, only with
      ``include_tool_input``: inputs can hold credentials, and the store
      redacts them (STANDARD v1.2 §6.7)

    This evidence can later be used to verify that decisions
    are grounded in actual observations.

    Args:
        store: Evidence store to append the anchors to (§6.6)
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
        store = EvidenceStore()  # or JsonlEvidenceStore(path), a durable one
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

            redactor = getattr(store, "redactor", None) or DEFAULT_REDACTOR
            digest = response_digest(tool_response, redactor)
            anchor = EvidenceAnchor.from_tool_output(
                tool_name=tool_name,
                tool_use_id=tool_use_id or "unknown",
                tool_input=tool_input,
                tool_response=tool_response,
                include_tool_input=include_tool_input,
                digest=digest,
            )
            if digest is None and tool_response is not None:
                if redactor.holds_secret(tool_response):
                    anchor.metadata["digest_omitted"] = "secret"
            anchors = [anchor]

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

            # For file operations, also a file evidence anchor
            if tool_name in ("Read", "Write", "Edit", "MultiEdit"):
                file_path = tool_input.get("file_path") or tool_input.get("path")
                if file_path:
                    operation = "read" if tool_name == "Read" else "write"
                    anchors.append(
                        EvidenceAnchor.from_file(
                            file_path=file_path,
                            operation=operation,
                        )
                    )

            # For Bash commands, command evidence
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                exit_code = 0
                if isinstance(tool_response, dict):
                    exit_code = tool_response.get("exit_code", 0)
                elif tool_response is not None and hasattr(tool_response, "exit_code"):
                    exit_code = getattr(tool_response, "exit_code", 0)

                anchors.append(
                    EvidenceAnchor.from_command(
                        command=command if include_tool_input else None,
                        exit_code=exit_code,
                        tool_use_id=tool_use_id,
                    )
                )

            append_many = getattr(store, "append_many", None)
            if callable(append_many):
                append_many(
                    anchors,
                    capability=capability_id,
                    tool=tool_name or None,
                    call_id=tool_use_id,
                )
            else:
                # A store of the 1.1 interface (add_anchor only).
                for a in anchors:
                    store.add_anchor(a, capability_id=capability_id)  # type: ignore[attr-defined]

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
