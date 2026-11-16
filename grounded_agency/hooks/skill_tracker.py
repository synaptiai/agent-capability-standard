"""
Checkpoint Recorder Hook

PostToolUse hook that records a checkpoint when a call that saves the state
completed successfully (STANDARD 1.2.0 section 5.18.6): a call the mapper
classifies ``checkpoint``, such as ``git stash create`` or a tool bound to
``checkpoint``. A ``Skill`` call is ``invoke`` whatever the skill: loading
the checkpoint skill's instructions saves nothing, and the state-saving
command it leads to is the call that takes the checkpoint.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..capabilities.mapper import ToolCapabilityMapper
from ..state.checkpoint_tracker import CheckpointTracker

if TYPE_CHECKING:
    from .._types import HookCallback, HookContext

logger = logging.getLogger("grounded_agency.hooks.skill_tracker")

# A commit id as `git stash create` prints it (SHA-1 or SHA-256).
_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _tree_is_head(cwd: Any) -> bool:
    """Whether the tracked files and the index of the repository at ``cwd``
    (the call's working directory; this process's when it is not given) are
    ``HEAD``'s: only then does ``HEAD`` restore the state a `git stash create`
    that printed nothing saw. Any failure answers no."""
    git = shutil.which("git")
    if git is None:
        return False
    where = cwd if isinstance(cwd, str) and cwd else os.getcwd()
    for args in (
        ["diff", "--quiet", "HEAD", "--"],
        ["diff", "--cached", "--quiet", "HEAD", "--"],
    ):
        try:
            done = subprocess.run(
                [git, "-C", where, *args],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            return False
        if done.returncode != 0:
            return False
    return True


def _is_error(tool_response: Any) -> bool:
    if isinstance(tool_response, dict):
        return bool(tool_response.get("is_error")) or bool(
            tool_response.get("interrupted")
        )
    return bool(getattr(tool_response, "is_error", False))


def _stdout(tool_response: Any) -> str:
    if isinstance(tool_response, dict):
        out = tool_response.get("stdout")
        if out is None:
            out = tool_response.get("output")
        return out.strip() if isinstance(out, str) else ""
    if isinstance(tool_response, str):
        return tool_response.strip()
    return ""


def create_checkpoint_recorder(
    checkpoint_tracker: CheckpointTracker,
    mapper: ToolCapabilityMapper | None = None,
    expiry_minutes: int | float | None = None,
    *,
    refuses_output: Callable[[str, Any, Any], bool] | None = None,
) -> HookCallback:
    """
    Create a PostToolUse hook that records the checkpoint a successful
    state-saving call took.

    Register it for every tool (no matcher). For a call whose mapping's
    capabilities include ``checkpoint``, whose response is not an error and
    whose output ``refuses_output`` does not refuse, a checkpoint is created in the tracker with ``metadata["source"]`` the
    tool. For ``git stash create``, ``metadata["commit"]`` is the commit it
    printed, or ``"HEAD"`` when it printed nothing and the tracked files and
    index of the repository it ran in (the call's ``cwd``) are ``HEAD``'s
    (a clean tree, whose restore point is ``HEAD``), and
    ``metadata["untracked_not_captured"]`` is true; its scope is ``["*"]``.
    It takes none for a call run in the background (its output is not yet
    the command's), for empty output over a changed tree (``HEAD`` would not
    restore it), or for output that is neither. A bound ``checkpoint``
    tool's scope is its input's ``scope``, else its response's, else
    ``["*"]``.

    Args:
        checkpoint_tracker: CheckpointTracker to update
        mapper: Classifies the calls; a mapper over the packaged ontology
            when omitted
        expiry_minutes: The checkpoints' maximum age (at most 30); the
            tracker's default when omitted
        refuses_output: Whether the safety layer refuses the call's output
            (``tool_name``, ``tool_input``, ``tool_response``): a call whose
            output is refused has failed and takes no checkpoint (section
            5.18.6). The adapter passes its PostToolUse output check, which
            runs beside this hook on the same result.

    Returns:
        Async hook callback function
    """
    classify = mapper if mapper is not None else ToolCapabilityMapper()

    async def record_checkpoint(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext | None,
    ) -> dict[str, Any]:
        """PostToolUse hook: take the checkpoint a state-saving call saved."""
        try:
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input", {})
            if not isinstance(tool_input, dict):
                tool_input = {}
            mapping = classify.map_tool(tool_name, tool_input)
            if "checkpoint" not in mapping.capabilities:
                return {}
            tool_response = input_data.get("tool_response")
            if _is_error(tool_response):
                return {}
            if refuses_output is not None and refuses_output(
                tool_name, tool_input, tool_response
            ):
                return {}

            metadata: dict[str, Any] = {"source": tool_name}
            if tool_name == "Bash":
                if tool_input.get("run_in_background") is True:
                    return {}
                printed = _stdout(tool_response)
                if _COMMIT.fullmatch(printed):
                    commit = printed
                elif not printed and await asyncio.to_thread(
                    _tree_is_head, input_data.get("cwd")
                ):
                    commit = "HEAD"
                else:
                    return {}
                metadata["source"] = "git stash create"
                metadata["commit"] = commit
                metadata["untracked_not_captured"] = True
                scope: Any = ["*"]
            else:
                scope = tool_input.get("scope")
                if scope is None and isinstance(tool_response, dict):
                    scope = tool_response.get("scope")
                if scope is None:
                    scope = ["*"]
                if isinstance(scope, str):
                    scope = [scope]
                if not isinstance(scope, list) or not all(
                    isinstance(s, str) for s in scope
                ):
                    scope = ["*"]
            if tool_use_id:
                metadata["tool_use_id"] = tool_use_id

            reason = tool_input.get("reason")
            if not isinstance(reason, str) or not reason:
                reason = f"Checkpoint taken by {metadata['source']}"
            checkpoint_id = checkpoint_tracker.create_checkpoint(
                scope=scope,
                reason=reason,
                expiry_minutes=expiry_minutes,
                metadata=metadata,
            )
            logger.info("Checkpoint %s taken by %s", checkpoint_id, metadata["source"])
        except Exception as e:
            logger.error("Checkpoint recording failed: %s", e)

        return {}

    return record_checkpoint


def create_skill_tracker(
    checkpoint_tracker: CheckpointTracker,
    mapper: ToolCapabilityMapper | None = None,
) -> HookCallback:
    """The former name of :func:`create_checkpoint_recorder`, kept so
    existing code keeps working. A ``Skill`` call no longer takes a
    checkpoint: the state-saving call does."""
    return create_checkpoint_recorder(checkpoint_tracker, mapper)
