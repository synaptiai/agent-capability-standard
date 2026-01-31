"""
Checkpoint Tracker

Manages checkpoint lifecycle for mutation safety in the Grounded Agency pattern.
Tracks checkpoint creation, validity, consumption, and expiry.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import tempfile
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize checkpoint to a JSON-compatible dict."""
        return {
            "id": self.id,
            "scope": self.scope,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "consumed": self.consumed,
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        """Deserialize checkpoint from a dict.

        Raises:
            ValueError: If required fields have wrong types.
            KeyError: If required fields are missing.
        """
        # Validate types to catch crafted/corrupt state files early.
        if not isinstance(data.get("id"), str):
            raise ValueError("checkpoint id must be a string")
        if not isinstance(data.get("scope"), list):
            raise ValueError("checkpoint scope must be a list")
        if not isinstance(data.get("reason"), str):
            raise ValueError("checkpoint reason must be a string")
        meta = data.get("metadata", {})
        if not isinstance(meta, dict):
            raise ValueError("checkpoint metadata must be a dict")

        return cls(
            id=data["id"],
            scope=data["scope"],
            reason=data["reason"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=(
                datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None
            ),
            consumed=data.get("consumed", False),
            consumed_at=(
                datetime.fromisoformat(data["consumed_at"])
                if data.get("consumed_at")
                else None
            ),
            metadata=meta,
        )

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
        tracker = CheckpointTracker(checkpoint_dir=".checkpoints")

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

    State file format (``checkpoint_dir/tracker_state.json``)::

        {
            "active": { <Checkpoint dict> } | null,
            "history": [ { <Checkpoint dict> }, ... ]
        }

    Each Checkpoint dict contains: id, scope, reason, created_at,
    expires_at, consumed, consumed_at, metadata.
    """

    DEFAULT_EXPIRY_MINUTES: int = 30
    DEFAULT_MAX_HISTORY: int = 100
    _MAX_STATE_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MB

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
        self._max_history = (
            max_history if max_history is not None else self.DEFAULT_MAX_HISTORY
        )
        self._marker_dir = Path(marker_dir) if marker_dir is not None else None
        self._active_checkpoint: Checkpoint | None = None
        self._checkpoint_history: list[Checkpoint] = []
        self._load_persisted_state()

    # ------------------------------------------------------------------
    # Persistence (TD-011)
    # ------------------------------------------------------------------

    def _state_file_path(self) -> Path:
        """Path to the persisted tracker state file."""
        return self._checkpoint_dir / "tracker_state.json"

    def _persist_state(self) -> None:
        """Atomically write tracker state to disk.

        Uses write-to-tmp + rename for crash safety.
        """
        try:
            self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
            state = {
                "active": (
                    self._active_checkpoint.to_dict()
                    if self._active_checkpoint
                    else None
                ),
                # Cap history before serializing to prevent unbounded file growth.
                "history": [
                    c.to_dict()
                    for c in self._checkpoint_history[-self._max_history:]
                ],
            }
            state_path = self._state_file_path()
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._checkpoint_dir), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(state, f)
                os.replace(tmp_path, str(state_path))
            except Exception:
                # Clean up temp file on failure; re-raise original error.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except (OSError, TypeError, ValueError, OverflowError) as e:
            logger.warning("Failed to persist checkpoint state: %s", e)

    def _load_persisted_state(self) -> None:
        """Load tracker state from disk if available.

        Uses open() + fstat() to avoid TOCTOU between existence check and read.
        Handles missing and corrupt files gracefully.
        """
        state_path = self._state_file_path()
        if state_path.is_symlink():
            logger.warning("Refusing to follow symlink for state file: %s", state_path)
            return
        try:
            with open(state_path, encoding="utf-8") as f:
                file_size = os.fstat(f.fileno()).st_size
                if file_size > self._MAX_STATE_FILE_BYTES:
                    logger.warning(
                        "State file too large (%d bytes, limit %d) — starting fresh",
                        file_size,
                        self._MAX_STATE_FILE_BYTES,
                    )
                    return
                raw = f.read()
            state = json.loads(raw)
            if state.get("active"):
                self._active_checkpoint = Checkpoint.from_dict(state["active"])
            # Cap loaded history to _max_history to prevent unbounded growth
            # from a crafted or accumulated state file.
            self._checkpoint_history = [
                Checkpoint.from_dict(entry)
                for entry in state.get("history", [])[:self._max_history]
            ]
        except (json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError, OSError) as e:
            logger.warning("Failed to load persisted checkpoint state: %s", e)
            # Start fresh — don't propagate corrupt state
            self._active_checkpoint = None
            self._checkpoint_history = []

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
        self._persist_state()
        return checkpoint_id

    def _generate_checkpoint_id(self) -> str:
        """Generate a unique checkpoint ID with 128 bits of entropy.

        Uses 16 cryptographically random bytes (128 bits) encoded as
        32 hex characters.  ``os.urandom`` is already cryptographically
        secure, so hashing adds no additional entropy.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        random_suffix = os.urandom(16).hex()
        return f"chk_{timestamp}_{random_suffix}"

    def _prune_history_if_needed(self) -> None:
        """Prune oldest checkpoints if history exceeds max_history."""
        if len(self._checkpoint_history) > self._max_history:
            self._checkpoint_history = self._checkpoint_history[-self._max_history:]

    def _write_marker(self, checkpoint: Checkpoint) -> None:
        """Atomically write the shell hook marker file with checkpoint metadata.

        Uses write-to-tmp + rename so the shell PreToolUse hook never reads
        a partially written marker file.
        """
        if self._marker_dir is None:
            return
        try:
            marker_path = self._marker_dir / "checkpoint.ok"
            self._marker_dir.mkdir(parents=True, exist_ok=True)
            created_ts = int(checkpoint.created_at.timestamp())
            expires_ts = (
                int(checkpoint.expires_at.timestamp())
                if checkpoint.expires_at
                else created_ts + self.DEFAULT_EXPIRY_MINUTES * 60
            )
            marker_data = {
                "checkpoint_id": checkpoint.id,
                "created_at": created_ts,
                "expires_at": expires_ts,
            }
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._marker_dir), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(marker_data, f)
                os.replace(tmp_path, str(marker_path))
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
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

        # Capture reference and clear active first to avoid intermediate
        # invalid state where active still points to consumed checkpoint.
        consumed = self._active_checkpoint
        self._active_checkpoint = None

        consumed.consumed = True
        consumed.consumed_at = datetime.now(timezone.utc)
        checkpoint_id = consumed.id

        # Move to history
        self._checkpoint_history.append(consumed)
        self._remove_marker()
        self._persist_state()

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

        If the active checkpoint has expired, it is moved to history and
        then filtered out along with any other expired history entries.
        The returned count includes the active checkpoint if it was expired.

        Returns:
            Number of expired checkpoints removed (active + history)
        """
        now = datetime.now(timezone.utc)
        active_cleared = False

        # Move expired active checkpoint to history FIRST so it gets
        # filtered along with all other expired history entries.
        # Use explicit expiry check — not is_valid(), which also returns
        # False for consumed checkpoints (different semantic).
        if (
            self._active_checkpoint
            and self._active_checkpoint.expires_at
            and now > self._active_checkpoint.expires_at
        ):
            self._checkpoint_history.append(self._active_checkpoint)
            self._active_checkpoint = None
            self._remove_marker()
            active_cleared = True

        original_count = len(self._checkpoint_history)
        self._checkpoint_history = [
            c
            for c in self._checkpoint_history
            if c.expires_at is None or c.expires_at > now
        ]
        # Includes the expired active (appended above) that was then filtered out.
        total_cleared = original_count - len(self._checkpoint_history)

        # Persist whenever state changed (active cleared or history pruned)
        if active_cleared or total_cleared > 0:
            self._persist_state()
        return total_cleared

    def invalidate_all(self) -> None:
        """Invalidate all checkpoints (used for rollback scenarios)."""
        if self._active_checkpoint:
            self._active_checkpoint.consumed = True
            self._active_checkpoint.consumed_at = datetime.now(timezone.utc)
            self._checkpoint_history.append(self._active_checkpoint)
            self._active_checkpoint = None
            self._remove_marker()
            self._persist_state()

    @property
    def checkpoint_count(self) -> int:
        """Get total number of checkpoints (active + history)."""
        count = len(self._checkpoint_history)
        if self._active_checkpoint:
            count += 1
        return count
