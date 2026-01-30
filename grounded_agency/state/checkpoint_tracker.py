"""
Checkpoint Tracker

Manages checkpoint lifecycle for mutation safety in the Grounded Agency pattern.
Tracks checkpoint creation, validity, consumption, and expiry.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Checkpoint:
    """
    Represents a single checkpoint in the safety lifecycle.

    A checkpoint must be created before mutations and is consumed
    after the mutation completes successfully.
    """

    id: str
    scope: list[str]
    reason: str
    created_at: datetime
    expires_at: datetime | None = None
    consumed: bool = False
    consumed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if checkpoint is still valid (not consumed, not expired)."""
        if self.consumed:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True

    def matches_scope(self, target: str) -> bool:
        """Check if target is covered by this checkpoint's scope."""
        for scope_pattern in self.scope:
            if scope_pattern == "*":
                return True
            if scope_pattern == target:
                return True
            # Use fnmatch for proper glob pattern matching
            if fnmatch.fnmatch(target, scope_pattern):
                return True
        return False


class CheckpointTracker:
    """
    Tracks checkpoint lifecycle for the Grounded Agency safety pattern.

    Before any mutation (Write, Edit, destructive Bash), a checkpoint
    must exist. This tracker manages:

    1. Checkpoint creation with scope and reason
    2. Checkpoint validity checking
    3. Checkpoint consumption after successful mutation
    4. Checkpoint history for audit trails

    Example:
        tracker = CheckpointTracker()

        # Before mutation
        checkpoint_id = tracker.create_checkpoint(
            scope=["src/*.py"],
            reason="Before refactoring"
        )

        # Check before allowing mutation
        if tracker.has_valid_checkpoint():
            # Allow mutation
            pass

        # After successful mutation
        tracker.consume_checkpoint()
    """

    DEFAULT_EXPIRY_MINUTES: int = 30
    DEFAULT_MAX_HISTORY: int = 100

    def __init__(
        self,
        checkpoint_dir: str | Path = ".checkpoints",
        max_history: int | None = None,
        marker_dir: str | Path | None = None,
    ) -> None:
        """
        Initialize the tracker.

        Args:
            checkpoint_dir: Directory to store checkpoint metadata
            max_history: Maximum checkpoints to keep in history (default: 100).
                        Oldest checkpoints are pruned when limit is exceeded.
            marker_dir: Directory for the shell hook marker file (.claude/).
                       If provided, create_checkpoint() writes .claude/checkpoint.ok
                       and consume_checkpoint() removes it, bridging the Python
                       tracker with the shell PreToolUse hook (SEC-001).
        """
        self._checkpoint_dir = Path(checkpoint_dir)
        self._max_history = max_history if max_history is not None else self.DEFAULT_MAX_HISTORY
        self._marker_dir = Path(marker_dir) if marker_dir is not None else None
        self._active_checkpoint: Checkpoint | None = None
        self._checkpoint_history: list[Checkpoint] = []

    def create_checkpoint(
        self,
        scope: list[str],
        reason: str,
        expiry_minutes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a new checkpoint.

        Args:
            scope: List of file patterns or "*" for all
            reason: Human-readable reason for checkpoint
            expiry_minutes: Minutes until checkpoint expires (default: 30)
            metadata: Additional metadata to attach

        Returns:
            Checkpoint ID
        """
        checkpoint_id = self._generate_checkpoint_id()

        expires_at = None
        if expiry_minutes is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
        elif self.DEFAULT_EXPIRY_MINUTES:
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=self.DEFAULT_EXPIRY_MINUTES
            )

        checkpoint = Checkpoint(
            id=checkpoint_id,
            scope=scope,
            reason=reason,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            metadata=metadata or {},
        )

        # Move previous active checkpoint to history
        if self._active_checkpoint:
            self._checkpoint_history.append(self._active_checkpoint)
            self._prune_history_if_needed()

        self._active_checkpoint = checkpoint
        self._write_marker(checkpoint)
        return checkpoint_id

    def _generate_checkpoint_id(self) -> str:
        """Generate a unique checkpoint ID with 128 bits of entropy.

        Uses 32 hex characters (128 bits) from SHA-256 of 16 random bytes
        for cryptographic security against ID prediction/collision.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # Use 16 bytes of randomness → 128 bits of entropy in output
        random_suffix = hashlib.sha256(os.urandom(16)).hexdigest()[:32]
        return f"chk_{timestamp}_{random_suffix}"

    def _prune_history_if_needed(self) -> int:
        """Prune oldest checkpoints if history exceeds max_history.

        Returns:
            Number of checkpoints pruned
        """
        if len(self._checkpoint_history) <= self._max_history:
            return 0

        # Sort by created_at and keep only the most recent
        self._checkpoint_history.sort(key=lambda c: c.created_at, reverse=True)
        to_prune = len(self._checkpoint_history) - self._max_history
        self._checkpoint_history = self._checkpoint_history[:self._max_history]
        return to_prune

    def _write_marker(self, checkpoint: Checkpoint) -> None:
        """Write the shell hook marker file with checkpoint metadata.

        Bridges the Python tracker with the shell PreToolUse hook by
        writing a JSON marker file that the hook validates for freshness.
        """
        if self._marker_dir is None:
            return
        try:
            marker_path = self._marker_dir / "checkpoint.ok"
            self._marker_dir.mkdir(parents=True, exist_ok=True)
            created_ts = int(checkpoint.created_at.timestamp())
            expires_ts = int(checkpoint.expires_at.timestamp()) if checkpoint.expires_at else created_ts + self.DEFAULT_EXPIRY_MINUTES * 60
            marker_data = {
                "checkpoint_id": checkpoint.id,
                "created_at": created_ts,
                "expires_at": expires_ts,
            }
            marker_path.write_text(json.dumps(marker_data), encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to write checkpoint marker: %s", e)

    def _remove_marker(self) -> None:
        """Remove the shell hook marker file when checkpoint is consumed/invalidated."""
        if self._marker_dir is None:
            return
        try:
            marker_path = self._marker_dir / "checkpoint.ok"
            marker_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Failed to remove checkpoint marker: %s", e)

    def has_valid_checkpoint(self) -> bool:
        """Check if there's a valid (unexpired, unconsumed) checkpoint."""
        if self._active_checkpoint is None:
            return False
        return self._active_checkpoint.is_valid()

    def has_checkpoint_for_scope(self, target: str) -> bool:
        """
        Check if there's a valid checkpoint covering the target.

        Args:
            target: File path or resource to check

        Returns:
            True if a valid checkpoint covers this target
        """
        if not self.has_valid_checkpoint():
            return False
        assert self._active_checkpoint is not None  # Guaranteed by has_valid_checkpoint
        return self._active_checkpoint.matches_scope(target)

    def get_active_checkpoint(self) -> Checkpoint | None:
        """Get the currently active checkpoint, if any."""
        if self._active_checkpoint and self._active_checkpoint.is_valid():
            return self._active_checkpoint
        return None

    def get_active_checkpoint_id(self) -> str | None:
        """Get the ID of the active checkpoint, or None."""
        checkpoint = self.get_active_checkpoint()
        return checkpoint.id if checkpoint else None

    def consume_checkpoint(self) -> str | None:
        """
        Mark the active checkpoint as consumed.

        Called after a successful mutation to indicate the checkpoint
        has been "used up" and a new one is needed for further mutations.

        Returns:
            ID of consumed checkpoint, or None if no active checkpoint
        """
        if self._active_checkpoint is None:
            return None

        self._active_checkpoint.consumed = True
        self._active_checkpoint.consumed_at = datetime.now(timezone.utc)

        checkpoint_id = self._active_checkpoint.id

        # Move to history
        self._checkpoint_history.append(self._active_checkpoint)
        self._active_checkpoint = None
        self._remove_marker()

        return checkpoint_id

    def get_checkpoint_by_id(self, checkpoint_id: str) -> Checkpoint | None:
        """
        Look up a checkpoint by ID.

        Searches active checkpoint and history.

        Args:
            checkpoint_id: The checkpoint ID to find

        Returns:
            Checkpoint or None if not found
        """
        if self._active_checkpoint and self._active_checkpoint.id == checkpoint_id:
            return self._active_checkpoint

        for checkpoint in self._checkpoint_history:
            if checkpoint.id == checkpoint_id:
                return checkpoint

        return None

    def get_history(self, limit: int = 10) -> list[Checkpoint]:
        """
        Get recent checkpoint history.

        Args:
            limit: Maximum number of checkpoints to return

        Returns:
            List of checkpoints, most recent first
        """
        history = list(self._checkpoint_history)
        if self._active_checkpoint:
            history.append(self._active_checkpoint)
        return sorted(history, key=lambda c: c.created_at, reverse=True)[:limit]

    def clear_expired(self) -> int:
        """
        Remove expired checkpoints from history.

        Returns:
            Number of checkpoints cleared
        """
        now = datetime.now(timezone.utc)
        original_count = len(self._checkpoint_history)

        self._checkpoint_history = [
            c for c in self._checkpoint_history
            if c.expires_at is None or c.expires_at > now
        ]

        # Clear active if expired
        if self._active_checkpoint and not self._active_checkpoint.is_valid():
            self._checkpoint_history.append(self._active_checkpoint)
            self._active_checkpoint = None
            self._remove_marker()

        return original_count - len(self._checkpoint_history)

    def invalidate_all(self) -> None:
        """Invalidate all checkpoints (used for rollback scenarios)."""
        if self._active_checkpoint:
            self._active_checkpoint.consumed = True
            self._checkpoint_history.append(self._active_checkpoint)
            self._active_checkpoint = None
            self._remove_marker()

    @property
    def checkpoint_count(self) -> int:
        """Get total number of checkpoints (active + history)."""
        count = len(self._checkpoint_history)
        if self._active_checkpoint:
            count += 1
        return count
