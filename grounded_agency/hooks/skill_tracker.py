"""
Skill Tracker Hook

PostToolUse hook that tracks Skill invocations and updates checkpoint state.
When the checkpoint skill is invoked, this hook updates the CheckpointTracker.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..state.checkpoint_tracker import CheckpointTracker

if TYPE_CHECKING:
    from .._types import HookCallback, HookContext

logger = logging.getLogger("grounded_agency.hooks.skill_tracker")


def create_skill_tracker(checkpoint_tracker: CheckpointTracker) -> HookCallback:
    """
    Create a PostToolUse hook that tracks checkpoint skill invocations.

    When Claude autonomously invokes the `checkpoint` skill, this hook
    updates the CheckpointTracker so subsequent mutations are allowed.

    This enables the workflow:
    1. User asks Claude to "create a checkpoint before editing"
    2. Claude invokes Skill tool with skill="checkpoint"
    3. This hook detects the skill invocation
    4. CheckpointTracker is updated with a new valid checkpoint
    5. Subsequent mutations are now allowed

    Args:
        checkpoint_tracker: CheckpointTracker to update

    Returns:
        Async hook callback function

    Example:
        tracker = CheckpointTracker()
        hook = create_skill_tracker(tracker)
        # When checkpoint skill is invoked, tracker is updated
    """

    async def track_skill(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext | None,
    ) -> dict[str, Any]:
        """
        PostToolUse hook to track checkpoint skill invocations.

        Args:
            input_data: Contains tool_name, tool_input, tool_response
            tool_use_id: Unique identifier for this tool use
            context: SDK hook context

        Returns:
            Empty dict (passive observation)
        """
        try:
            tool_name = input_data.get("tool_name", "")

            # Only track Skill tool invocations
            if tool_name != "Skill":
                return {}

            tool_input = input_data.get("tool_input", {})
            skill_name = tool_input.get("skill", "")

            # When checkpoint skill is invoked, create a checkpoint
            if skill_name == "checkpoint":
                tool_response = input_data.get("tool_response", {})

                # Extract scope from skill input or response
                scope = tool_input.get("scope")
                if scope is None:
                    scope = (
                        tool_response.get("scope")
                        if isinstance(tool_response, dict)
                        else None
                    )
                if scope is None:
                    scope = ["*"]  # Default to all files

                # Ensure scope is a list
                if isinstance(scope, str):
                    scope = [scope]

                # Extract reason
                reason = tool_input.get("reason")
                if reason is None:
                    reason = (
                        tool_response.get("reason")
                        if isinstance(tool_response, dict)
                        else None
                    )
                if reason is None:
                    reason = "Checkpoint created via skill invocation"

                # Create the checkpoint
                checkpoint_id = checkpoint_tracker.create_checkpoint(
                    scope=scope,
                    reason=reason,
                )
                logger.info("Checkpoint created via skill: %s", checkpoint_id)

            # Track other safety-related skills
            elif skill_name == "rollback":
                # On rollback skill, invalidate all checkpoints
                checkpoint_tracker.invalidate_all()
                logger.info("All checkpoints invalidated due to rollback skill")

        except Exception as e:
            logger.error("Skill tracking failed: %s", e)

        return {}

    return track_skill
