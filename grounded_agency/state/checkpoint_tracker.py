"""
Checkpoint Tracker

Manages checkpoint lifecycle for mutation safety in the Grounded Agency pattern.
Tracks checkpoint creation, validity, consumption, and expiry, under the rules
of STANDARD 1.2.0 section 5.18.6 (and section 5.2.2 for steps):

- A checkpoint authorises one call whose effective ``requires_checkpoint`` is
  true. The one used is the most recently taken of the valid checkpoints no
  other call holds, active or in history.
- It is used up when the call is allowed to start, whatever the call's
  outcome. A call holds it (a reservation) while a host prompt is open; the
  hold is re-checked and used in one atomic step (:meth:`consume_if_valid`).
- A hold the layer cannot resolve (it lapses, the process restarts, the host
  never reports a refusal) counts as used.
- Validity ends at an execution boundary (:meth:`end_validity`) and at the
  maximum age, at most 30 minutes.
"""

from __future__ import annotations

import errno as _errno_mod
import fnmatch
import json
import logging
import os
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Platform-portable ELOOP errno values (Linux=40, macOS/BSD=62).
_ELOOP_ERRNOS: set[int] = {getattr(_errno_mod, "ELOOP", 40), 62}

logger = logging.getLogger(__name__)


# STANDARD 1.2.0 section 5.18.6: a layer's maximum age is at most 30 minutes.
MAX_AGE_MINUTES: int = 30


@dataclass(frozen=True, slots=True)
class _Reservation:
    """A checkpoint held for one in-flight call (SEC-007): one holder per
    checkpoint, one checkpoint per holder."""

    checkpoint_id: str
    holder: str  # the tool call's tool_use_id, or an anonymous token
    reserved_at: datetime  # the tracker's clock
    # (session_id, agent_id) of the call that took it, when known
    scope: tuple[str | None, str | None] | None = None


@dataclass(slots=True)
class Checkpoint:
    """
    Represents a single checkpoint in the safety lifecycle.

    A checkpoint must be created before mutations and is used up when the
    call it authorises is allowed to start (STANDARD 1.2.0 section 5.18.6).
    ``invalidated_at`` is set when an execution boundary ended its validity.
    """

    id: str
    scope: list[str]
    reason: str
    created_at: datetime
    expires_at: datetime | None = None
    consumed: bool = False
    consumed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    invalidated_at: datetime | None = None

    def is_valid(self, now: datetime | None = None) -> bool:
        """Whether the checkpoint can authorise a call at ``now`` (default:
        the current time): not consumed, not invalidated, not expired."""
        if self.consumed or self.invalidated_at is not None:
            return False
        if now is None:
            now = datetime.now(UTC)
        if self.expires_at and now > self.expires_at:
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
            "invalidated_at": (
                self.invalidated_at.isoformat() if self.invalidated_at else None
            ),
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
        if not all(isinstance(s, str) for s in data["scope"]):
            raise ValueError("checkpoint scope elements must be strings")
        if not isinstance(data.get("reason"), str):
            raise ValueError("checkpoint reason must be a string")
        if "created_at" not in data:
            raise ValueError("checkpoint created_at is required")
        if not isinstance(data.get("consumed", False), bool):
            raise ValueError("checkpoint consumed must be a boolean")
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
            invalidated_at=(
                datetime.fromisoformat(data["invalidated_at"])
                if data.get("invalidated_at")
                else None
            ),
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
    3. Holds (reservations) of a checkpoint by an in-flight call, and the
       atomic re-check and use of a hold when the call is allowed
    4. Checkpoint consumption: one checkpoint per gated call
    5. Execution boundaries, after which earlier checkpoints authorise
       nothing (:meth:`end_validity`)
    6. Checkpoint history for audit trails

    The rules are STANDARD 1.2.0 section 5.18.6's. Every time the tracker
    reads goes through one clock (``clock``), so a test can advance it.

    Example:
        tracker = CheckpointTracker(checkpoint_dir=".checkpoints")

        # Before mutation
        checkpoint_id = tracker.create_checkpoint(
            scope=["src/*.py"],
            reason="Before refactoring"
        )

        # A call holds it, then uses it when it is allowed to start
        ok, held = tracker.validate_and_reserve("call-1")
        used = tracker.consume_if_valid("call-1")

    State file format (``checkpoint_dir/tracker_state.json``)::

        {
            "active": { <Checkpoint dict> } | null,
            "history": [ { <Checkpoint dict> }, ... ],
            "reservations": [ {"checkpoint_id": ..., "holder": ...}, ... ],
            "last_taken_at": <ISO time> | null
        }

    Each Checkpoint dict contains: id, scope, reason, created_at,
    expires_at, consumed, consumed_at, metadata, invalidated_at. A hold
    found in the state file belongs to a process that is gone, so it is
    unresolved: its checkpoint counts as used.
    """

    MAX_AGE_MINUTES: int = MAX_AGE_MINUTES
    DEFAULT_EXPIRY_MINUTES: int = MAX_AGE_MINUTES
    DEFAULT_MAX_HISTORY: int = 100
    # A hold ends with its checkpoint's expiry unless reservation_seconds
    # sets a shorter time.
    DEFAULT_RESERVATION_SECONDS: float | None = None
    _MAX_STATE_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        checkpoint_dir: str | Path = ".checkpoints",
        max_history: int | None = None,
        marker_dir: str | Path | None = None,
        reservation_seconds: float | None = None,
        clock: Callable[[], datetime] | None = None,
        max_age_minutes: float | None = None,
    ) -> None:
        """
        Initialize the tracker.

        Args:
            checkpoint_dir: Directory to store checkpoint metadata
            max_history: Maximum checkpoints to keep in history (default: 100).
                        Oldest checkpoints are pruned when limit is exceeded.
            marker_dir: Directory for the shell hook marker file (.claude/).
                       If provided, create_checkpoint() writes .claude/checkpoint.ok
                       and using the active checkpoint up removes it, bridging the
                       Python tracker with the shell PreToolUse hook (SEC-001).
            reservation_seconds: How long a hold lasts if the call never
                       reports back, at most the checkpoint's own expiry.
                       ``None`` (default): only the checkpoint's expiry ends
                       it. A hold that lapses counts as used.
            clock: Returns the current time (timezone-aware); defaults to
                       ``datetime.now(UTC)``.
            max_age_minutes: The layer's maximum age (section 5.18.6): no
                       checkpoint authorises a call later than this after it
                       was taken, whatever its own ``expires_at`` (one taken
                       directly through this tracker, or read back from its
                       state file, included). More than 0 and at most 30
                       (default: 30); it is also the default expiry of
                       :meth:`create_checkpoint`.

        Raises:
            ValueError: If ``reservation_seconds`` is not more than 0, or
                ``max_age_minutes`` is not more than 0 or is more than 30.
        """
        if reservation_seconds is not None and not reservation_seconds > 0:
            raise ValueError(
                f"reservation_seconds must be more than 0, got {reservation_seconds!r}"
            )
        max_age = self.MAX_AGE_MINUTES if max_age_minutes is None else max_age_minutes
        if (
            isinstance(max_age, bool)
            or not isinstance(max_age, (int, float))
            or not 0 < max_age <= self.MAX_AGE_MINUTES
        ):
            raise ValueError(
                f"max_age_minutes must be more than 0 and at most "
                f"{self.MAX_AGE_MINUTES}, got {max_age_minutes!r}: STANDARD "
                f"1.2.0 §5.18.6 caps a checkpoint's maximum age at 30 minutes"
            )
        self._max_age_minutes: float = max_age
        self._checkpoint_dir = Path(checkpoint_dir)
        self._max_history = (
            max_history if max_history is not None else self.DEFAULT_MAX_HISTORY
        )
        self._marker_dir = Path(marker_dir) if marker_dir is not None else None
        self._reservation_seconds = reservation_seconds
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._active_checkpoint: Checkpoint | None = None
        # Holds by checkpoint id.
        self._reservations: dict[str, _Reservation] = {}
        self._checkpoint_history: list[Checkpoint] = []
        # When the newest checkpoint was taken: survives history pruning.
        self._last_taken_at: datetime | None = None
        self._load_persisted_state()

    def _now(self) -> datetime:
        return self._clock()

    @property
    def max_age_minutes(self) -> float:
        """The maximum age of a checkpoint, in minutes (section 5.18.6)."""
        return self._max_age_minutes

    def _valid(self, checkpoint: Checkpoint, now: datetime) -> bool:
        """Whether ``checkpoint`` can authorise a call at ``now``: valid by
        its own record, taken no later than ``now`` and no longer ago than
        the maximum age. A checkpoint dated after ``now`` (a crafted state
        file, or a clock that stepped back) authorises nothing: the maximum
        age could not bound it."""
        return (
            checkpoint.is_valid(now)
            and checkpoint.created_at <= now
            and now <= checkpoint.created_at + timedelta(minutes=self._max_age_minutes)
        )

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
                    c.to_dict() for c in self._checkpoint_history[-self._max_history :]
                ],
                "reservations": [
                    {"checkpoint_id": r.checkpoint_id, "holder": r.holder}
                    for r in self._reservations.values()
                ],
                "last_taken_at": (
                    self._last_taken_at.isoformat() if self._last_taken_at else None
                ),
            }
            state_path = self._state_file_path()
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._checkpoint_dir), suffix=".tmp"
            )
            try:
                try:
                    f = os.fdopen(fd, "w", encoding="utf-8")
                except Exception:
                    os.close(fd)
                    raise
                with f:
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

        Uses O_NOFOLLOW + fstat() on the opened fd to avoid TOCTOU between
        symlink check/existence check and read.  Falls back to is_symlink()
        on platforms without O_NOFOLLOW.
        Handles missing and corrupt files gracefully.

        A hold in the file belongs to a call this process never saw finish:
        it is unresolved, so its checkpoint counts as used (STANDARD 1.2.0
        section 5.18.6).
        """
        state_path = self._state_file_path()
        o_nofollow = getattr(os, "O_NOFOLLOW", 0)
        if o_nofollow:
            try:
                fd = os.open(str(state_path), os.O_RDONLY | o_nofollow)
            except FileNotFoundError:
                return
            except OSError as e:
                if e.errno in _ELOOP_ERRNOS:  # ELOOP — symlink rejected
                    logger.warning(
                        "Refusing to follow symlink for state file: %s", state_path
                    )
                    return
                raise
            try:
                f = os.fdopen(fd, encoding="utf-8")
            except Exception:
                os.close(fd)
                raise
        else:
            if state_path.is_symlink():
                logger.warning(
                    "Refusing to follow symlink for state file: %s", state_path
                )
                return
            try:
                f = open(state_path, encoding="utf-8")
            except FileNotFoundError:
                return
        try:
            with f:
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
            loaded_at = self._now()
            if state.get("active"):
                self._active_checkpoint = Checkpoint.from_dict(state["active"])
            # Cap loaded history to _max_history to prevent unbounded growth
            # from a crafted or accumulated state file.
            self._checkpoint_history = [
                Checkpoint.from_dict(entry)
                for entry in state.get("history", [])[: self._max_history]
            ]
            # A checkpoint dated after the load was not taken by this layer
            # as the clock now reads (a crafted file, or a clock that stepped
            # back): it authorises nothing, counts as no checkpoint taken and
            # names no restore point, so it is dropped (section 5.18.6).
            future = [c.id for c in self._all() if c.created_at > loaded_at]
            if future:
                logger.warning(
                    "Dropping %d checkpoint(s) dated after the load time: %s",
                    len(future),
                    ", ".join(future),
                )
                if (
                    self._active_checkpoint is not None
                    and self._active_checkpoint.created_at > loaded_at
                ):
                    self._active_checkpoint = None
                self._checkpoint_history = [
                    c for c in self._checkpoint_history if c.created_at <= loaded_at
                ]
            last = state.get("last_taken_at")
            if isinstance(last, str) and datetime.fromisoformat(last) <= loaded_at:
                self._last_taken_at = datetime.fromisoformat(last)
            else:
                created = [c.created_at for c in self._all()]
                self._last_taken_at = max(created) if created else None
            holds = state.get("reservations") or []
            resolved = False
            if isinstance(holds, list):
                for hold in holds:
                    if not isinstance(hold, dict):
                        continue
                    checkpoint = self._find(str(hold.get("checkpoint_id")))
                    if checkpoint is not None and not checkpoint.consumed:
                        logger.warning(
                            "Checkpoint %s was held by %s when the tracker last "
                            "stopped; the hold is unresolved, so it counts as used",
                            checkpoint.id,
                            hold.get("holder"),
                        )
                        self._mark_used(checkpoint, "unresolved hold")
                        resolved = True
            if resolved:
                self._persist_state()
        except (
            json.JSONDecodeError,
            KeyError,
            ValueError,
            TypeError,
            AttributeError,
            OSError,
        ) as e:
            logger.warning("Failed to load persisted checkpoint state: %s", e)
            # Start fresh — don't propagate corrupt state
            self._active_checkpoint = None
            self._checkpoint_history = []
            self._last_taken_at = None

    # ------------------------------------------------------------------
    # Internal helpers (caller holds the lock unless stated)
    # ------------------------------------------------------------------

    def _all(self) -> list[Checkpoint]:
        """History then the active checkpoint: oldest to newest."""
        checkpoints = list(self._checkpoint_history)
        if self._active_checkpoint is not None:
            checkpoints.append(self._active_checkpoint)
        return checkpoints

    def _find(self, checkpoint_id: str) -> Checkpoint | None:
        if self._active_checkpoint and self._active_checkpoint.id == checkpoint_id:
            return self._active_checkpoint
        for checkpoint in self._checkpoint_history:
            if checkpoint.id == checkpoint_id:
                return checkpoint
        return None

    def _mark_used(self, checkpoint: Checkpoint, by: str | None = None) -> None:
        """Mark a checkpoint consumed; the active one moves to history and
        its shell marker is removed. Does not persist."""
        if not checkpoint.consumed:
            checkpoint.consumed = True
            checkpoint.consumed_at = self._now()
            if by is not None:
                checkpoint.metadata["consumed_by"] = by
        if self._active_checkpoint is checkpoint:
            self._active_checkpoint = None
            self._checkpoint_history.append(checkpoint)
            self._prune_history_if_needed()
            self._remove_marker()

    def _hold_of(self, holder: str) -> _Reservation | None:
        for r in self._reservations.values():
            if r.holder == holder:
                return r
        return None

    def _lapsed(self, r: _Reservation, now: datetime) -> bool:
        checkpoint = self._find(r.checkpoint_id)
        if checkpoint is None:
            return True
        if checkpoint.expires_at is not None and now > checkpoint.expires_at:
            return True
        if now > checkpoint.created_at + timedelta(minutes=self._max_age_minutes):
            return True
        return (
            self._reservation_seconds is not None
            and (now - r.reserved_at).total_seconds() > self._reservation_seconds
        )

    def _sweep_lapsed(self) -> None:
        """Every hold that lapsed counts as used: the layer never learned
        what became of its call (section 5.18.6)."""
        now = self._now()
        changed = False
        for checkpoint_id, r in list(self._reservations.items()):
            if not self._lapsed(r, now):
                continue
            del self._reservations[checkpoint_id]
            checkpoint = self._find(checkpoint_id)
            if checkpoint is not None:
                logger.warning(
                    "The hold of checkpoint %s by %s lapsed; the checkpoint "
                    "counts as used",
                    checkpoint_id,
                    r.holder,
                )
                self._mark_used(checkpoint, f"lapsed hold of {r.holder}")
            changed = True
        if changed:
            self._persist_state()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_checkpoint(
        self,
        scope: list[str],
        reason: str,
        expiry_minutes: int | float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a new checkpoint.

        Args:
            scope: List of file patterns or "*" for all
            reason: Human-readable reason for checkpoint
            expiry_minutes: Minutes until checkpoint expires: more than 0
                and at most 30 (default: the tracker's maximum age). The
                expiry stored is never later than the maximum age allows.
            metadata: Additional metadata to attach

        Returns:
            Checkpoint ID

        Raises:
            ValueError: If ``expiry_minutes`` is not more than 0, or is more
                than 30: STANDARD 1.2.0 section 5.18.6 caps a checkpoint's
                maximum age at 30 minutes.
        """
        minutes = self._max_age_minutes if expiry_minutes is None else expiry_minutes
        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, (int, float))
            or not 0 < minutes <= self.MAX_AGE_MINUTES
        ):
            raise ValueError(
                f"expiry_minutes must be more than 0 and at most "
                f"{self.MAX_AGE_MINUTES}, got {expiry_minutes!r}: STANDARD "
                f"1.2.0 §5.18.6 caps a checkpoint's maximum age at 30 minutes"
            )
        checkpoint_id = self._generate_checkpoint_id()
        now = self._now()
        checkpoint = Checkpoint(
            id=checkpoint_id,
            scope=scope,
            reason=reason,
            created_at=now,
            expires_at=now + timedelta(minutes=min(minutes, self._max_age_minutes)),
            metadata=metadata or {},
        )

        with self._lock:
            # Move previous active checkpoint to history
            if self._active_checkpoint:
                self._checkpoint_history.append(self._active_checkpoint)
                self._prune_history_if_needed()

            # A hold of the previous checkpoint stays with its holder.
            self._active_checkpoint = checkpoint
            self._last_taken_at = now
            self._write_marker(checkpoint)
            self._persist_state()
        return checkpoint_id

    def _generate_checkpoint_id(self) -> str:
        """Generate a unique checkpoint ID with 128 bits of entropy.

        Uses 16 cryptographically random bytes (128 bits) encoded as
        32 hex characters.  ``os.urandom`` is already cryptographically
        secure, so hashing adds no additional entropy.
        """
        timestamp = self._now().strftime("%Y%m%d_%H%M%S")
        random_suffix = os.urandom(16).hex()
        return f"chk_{timestamp}_{random_suffix}"

    def has_commit(self, commit: str, since: datetime | None = None) -> bool:
        """Whether a checkpoint taken at or after ``since`` (any time when
        omitted) and not after now, valid or not, recorded ``commit`` as its
        restore point
        (``metadata["commit"]``, as ``git stash create`` printed it): what
        lets ``git stash pop|apply <commit>`` count as a rollback (section
        5.18.3). A checkpoint pruned from the history is not found."""
        with self._lock:
            now = self._now()
            return any(
                c.metadata.get("commit") == commit
                and (since is None or c.created_at >= since)
                and c.created_at <= now
                for c in self._all()
            )

    def has_taken_since(self, when: datetime) -> bool:
        """Whether a checkpoint was taken at or after ``when``, and not
        after now: what a ``checkpoint`` prerequisite reads (section
        5.18.5). History pruning does not hide one."""
        with self._lock:
            return (
                self._last_taken_at is not None
                and when <= self._last_taken_at <= self._now()
            )

    def _prune_history_if_needed(self) -> None:
        """Prune oldest checkpoints if history exceeds max_history.

        SEC-011: Archives pruned checkpoints to JSONL before deletion
        to preserve forensic data for audit trails.
        """
        if len(self._checkpoint_history) > self._max_history:
            to_prune = self._checkpoint_history[: -self._max_history]
            self._archive_checkpoints(to_prune)
            self._checkpoint_history = self._checkpoint_history[-self._max_history :]

    def _archive_checkpoints(self, checkpoints: list[Checkpoint]) -> None:
        """SEC-011: Write pruned checkpoints to archive JSONL file.

        Archives are append-only JSONL files in .checkpoints/archive/.
        Each line is a JSON-serialized checkpoint dict.
        """
        if not checkpoints:
            return
        try:
            archive_dir = self._checkpoint_dir / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_file = archive_dir / "pruned_checkpoints.jsonl"
            with open(archive_file, "a", encoding="utf-8") as f:
                for cp in checkpoints:
                    f.write(json.dumps(cp.to_dict()) + "\n")
            logger.info(
                "Archived %d pruned checkpoints to %s",
                len(checkpoints),
                archive_file,
            )
        except OSError as e:
            logger.warning("Failed to archive pruned checkpoints: %s", e)

    def get_archived_checkpoints(self) -> list[Checkpoint]:
        """SEC-011: Retrieve archived (pruned) checkpoints from JSONL.

        Per-line error handling: corrupt lines are skipped with a warning
        rather than aborting the entire archive read. File-level errors
        (permissions, missing file) are caught at the outer level.

        Returns:
            List of archived Checkpoint objects, oldest first.
        """
        archive_file = self._checkpoint_dir / "archive" / "pruned_checkpoints.jsonl"
        if not archive_file.exists():
            return []
        try:
            # P2-4: Reject oversized archive files before reading
            if archive_file.stat().st_size > self._MAX_STATE_FILE_BYTES:
                logger.warning(
                    "Archive file too large (%d bytes, limit %d) — skipping",
                    archive_file.stat().st_size,
                    self._MAX_STATE_FILE_BYTES,
                )
                return []
            results: list[Checkpoint] = []
            with open(archive_file, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        results.append(Checkpoint.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                        logger.warning(
                            "Skipping corrupt archive line %d: %s", line_num, e
                        )
            return results
        except OSError as e:
            logger.warning("Failed to read checkpoint archive: %s", e)
            return []

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
            fd, tmp_path = tempfile.mkstemp(dir=str(self._marker_dir), suffix=".tmp")
            try:
                try:
                    f = os.fdopen(fd, "w", encoding="utf-8")
                except Exception:
                    os.close(fd)
                    raise
                with f:
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

    # ------------------------------------------------------------------
    # Validity, holds and use (section 5.18.6)
    # ------------------------------------------------------------------

    def has_valid_checkpoint(self) -> bool:
        """Whether any checkpoint, active or in history, can still authorise
        a call (unconsumed, not invalidated, unexpired, within the maximum
        age), whether or not a call holds it."""
        with self._lock:
            now = self._now()
            return any(self._valid(c, now) for c in self._all())

    def valid_checkpoint_id(self) -> str | None:
        """The checkpoint :meth:`validate_and_reserve` would hold now, without
        holding it: the newest valid one, active or in history, that no call
        holds. ``None`` when there is none."""
        with self._lock:
            self._sweep_lapsed()
            now = self._now()
            free = [
                c
                for c in self._all()
                if self._valid(c, now) and c.id not in self._reservations
            ]
            if not free:
                return None
            # validate_and_reserve's order: by time taken, later first among
            # equals.
            return sorted(free, key=lambda c: c.created_at)[-1].id

    def validate_and_reserve(
        self,
        holder: str | None = None,
        scope: tuple[str | None, str | None] | None = None,
    ) -> tuple[bool, str | None]:
        """Atomically find a valid checkpoint and hold it for one call.

        SEC-007: Prevents the TOCTOU race between a validity check and the
        call that relies on it. A checkpoint covers one call, so it has at
        most one holder: concurrent calls cannot both proceed on it. The
        checkpoint held is the most recently created one, active or in
        history, that is valid and that no other call holds (the reference
        executor's rule, STANDARD 1.2.0 sections 5.2.2 and 5.18.6). Holding
        again with the same ``holder`` (from both the PreToolUse hook and
        the permission callback of one call) returns the same hold.

        The holder ends the hold with :meth:`consume_if_valid` when the call
        is allowed, :meth:`consume_checkpoint` once it ran, or
        :meth:`release_reservation` when the layer learns the call was
        refused. A hold that lapses (its checkpoint expires, or
        ``reservation_seconds`` passes) counts as used.

        Args:
            holder: Who holds it, normally the tool call's ``tool_use_id``.
                Omitted, an anonymous holder is used that only
                :meth:`release_reservation` / :meth:`consume_checkpoint`
                without a holder can end.
            scope: ``(session_id, agent_id)`` of the call, for
                :meth:`resolve_holds_in_scope`.

        Returns:
            ``(True, checkpoint_id)``: held for ``holder``.
            ``(False, checkpoint_id)``: every valid checkpoint is held by
            another call (the newest of them is named).
            ``(False, None)``: no valid checkpoint (or the holder's hold is
            on one that is no longer valid).
        """
        with self._lock:
            self._sweep_lapsed()
            now = self._now()
            if holder is not None:
                existing = self._hold_of(holder)
                if existing is not None:
                    checkpoint = self._find(existing.checkpoint_id)
                    if checkpoint is not None and self._valid(checkpoint, now):
                        return True, checkpoint.id
                    return False, None
            valid = [c for c in self._all() if self._valid(c, now)]
            if not valid:
                return False, None
            valid.sort(key=lambda c: c.created_at)
            free = [c for c in valid if c.id not in self._reservations]
            if not free:
                return False, valid[-1].id
            chosen = free[-1]
            self._reservations[chosen.id] = _Reservation(
                checkpoint_id=chosen.id,
                holder=holder if holder is not None else f"anon_{os.urandom(8).hex()}",
                reserved_at=now,
                scope=scope,
            )
            self._persist_state()
            return True, chosen.id

    def held_by(self, holder: str) -> str | None:
        """The id of the checkpoint ``holder`` holds, or None."""
        with self._lock:
            r = self._hold_of(holder)
            return r.checkpoint_id if r is not None else None

    def release_reservation(self, holder: str | None = None) -> bool:
        """End a hold and leave its checkpoint valid: only where the layer
        learns that the call was refused, so it never ran. With ``holder``,
        only that holder's hold is released; without, every hold.

        Returns:
            True if a hold was released
        """
        with self._lock:
            if holder is None:
                if not self._reservations:
                    return False
                self._reservations.clear()
            else:
                r = self._hold_of(holder)
                if r is None:
                    return False
                del self._reservations[r.checkpoint_id]
            self._persist_state()
            return True

    def resolve_holds_in_scope(self, scope: tuple[str | None, str | None]) -> list[str]:
        """Resolve the holds of calls in ``scope`` (``(session_id,
        agent_id)``), for when that session's turn, or that agent, has
        ended: a call still holding a checkpoint then never reported back,
        so the layer cannot know it did not run, and its checkpoint counts
        as used (section 5.18.6).

        Returns:
            The holders whose holds were resolved
        """
        with self._lock:
            holders: list[str] = []
            for checkpoint_id, r in list(self._reservations.items()):
                if r.scope != scope:
                    continue
                del self._reservations[checkpoint_id]
                checkpoint = self._find(checkpoint_id)
                if checkpoint is not None:
                    self._mark_used(checkpoint, "unresolved hold at turn end")
                holders.append(r.holder)
            if holders:
                self._persist_state()
            return holders

    def consume_if_valid(self, holder: str) -> str | None:
        """Use the checkpoint ``holder`` holds, if it is still valid: the
        atomic re-check and use of section 5.18.6, for when the call is
        allowed to start.

        Returns:
            The checkpoint's id. ``None`` when the holder holds none, or its
            checkpoint is no longer valid (it expired, or an execution
            boundary passed): the hold then ends and its checkpoint counts as
            used all the same.
        """
        with self._lock:
            self._sweep_lapsed()
            r = self._hold_of(holder)
            if r is None:
                return None
            del self._reservations[r.checkpoint_id]
            checkpoint = self._find(r.checkpoint_id)
            if checkpoint is None:
                self._persist_state()
                return None
            valid = self._valid(checkpoint, self._now())
            self._mark_used(checkpoint, None if valid else f"ended hold of {holder}")
            self._persist_state()
            return checkpoint.id if valid else None

    def consume_checkpoint(self, holder: str | None = None) -> str | None:
        """
        Mark a checkpoint used. Thread-safe via self._lock (SEC-007).

        With ``holder``: the call that holds a checkpoint ran, so its
        checkpoint is used whatever its validity now; nothing happens for a
        call that holds none. Without ``holder`` (the host's own API): the
        active checkpoint is used, and any hold on it ends.

        Returns:
            ID of the consumed checkpoint, or None if nothing was consumed
        """
        with self._lock:
            self._sweep_lapsed()
            if holder is None:
                checkpoint = self._active_checkpoint
                if checkpoint is None:
                    return None
                self._reservations.pop(checkpoint.id, None)
            else:
                r = self._hold_of(holder)
                if r is None:
                    return None
                del self._reservations[r.checkpoint_id]
                found = self._find(r.checkpoint_id)
                if found is None:
                    self._persist_state()
                    return None
                checkpoint = found
            self._mark_used(checkpoint)
            self._persist_state()
            return checkpoint.id

    def end_validity(self, reason: str) -> list[str]:
        """An execution boundary (section 5.18.6): every checkpoint that is
        still valid stops authorising anything, for good. The active one
        moves to history and the shell marker is removed. Holds stay with
        their holders: a call that already ran uses its checkpoint when it
        reports back, and one still waiting fails :meth:`consume_if_valid`.

        Returns:
            The ids of the checkpoints whose validity ended
        """
        with self._lock:
            now = self._now()
            ended: list[str] = []
            for checkpoint in self._all():
                if self._valid(checkpoint, now):
                    checkpoint.invalidated_at = now
                    checkpoint.metadata["invalidated_by"] = reason
                    ended.append(checkpoint.id)
            if self._active_checkpoint is not None:
                self._checkpoint_history.append(self._active_checkpoint)
                self._active_checkpoint = None
                self._prune_history_if_needed()
                self._remove_marker()
            self._persist_state()
            return ended

    def has_checkpoint_for_scope(self, target: str) -> bool:
        """
        Check if there's a valid checkpoint covering the target.

        Args:
            target: File path or resource to check

        Returns:
            True if a valid checkpoint covers this target
        """
        with self._lock:
            if self._active_checkpoint is None:
                return False
            if not self._valid(self._active_checkpoint, self._now()):
                return False
            return self._active_checkpoint.matches_scope(target)

    def get_active_checkpoint(self) -> Checkpoint | None:
        """Get the currently active checkpoint, if any."""
        with self._lock:
            if self._active_checkpoint and self._valid(
                self._active_checkpoint, self._now()
            ):
                return self._active_checkpoint
            return None

    def get_active_checkpoint_id(self) -> str | None:
        """Get the ID of the active checkpoint, or None."""
        checkpoint = self.get_active_checkpoint()
        return checkpoint.id if checkpoint else None

    def get_checkpoint_by_id(self, checkpoint_id: str) -> Checkpoint | None:
        """
        Look up a checkpoint by ID.

        Searches active checkpoint and history.

        Args:
            checkpoint_id: The checkpoint ID to find

        Returns:
            Checkpoint or None if not found
        """
        with self._lock:
            return self._find(checkpoint_id)

    def get_history(self, limit: int = 10) -> list[Checkpoint]:
        """
        Get recent checkpoint history.

        Args:
            limit: Maximum number of checkpoints to return

        Returns:
            List of checkpoints, most recent first
        """
        with self._lock:
            history = self._all()
            return sorted(history, key=lambda c: c.created_at, reverse=True)[:limit]

    def clear_expired(self) -> int:
        """
        Remove expired checkpoints from history.

        If the active checkpoint has expired, it is moved to history and
        then filtered out along with any other expired history entries.
        The returned count includes the active checkpoint if it was expired.
        A checkpoint a call holds is kept until the hold ends.

        Returns:
            Number of expired checkpoints removed (active + history)
        """
        with self._lock:
            self._sweep_lapsed()
            now = self._now()
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
                if c.expires_at is None
                or c.expires_at > now
                or c.id in self._reservations
            ]
            # Includes the expired active (appended above) that was then filtered out.
            total_cleared = original_count - len(self._checkpoint_history)

            # Persist whenever state changed (active cleared or history pruned)
            if active_cleared or total_cleared > 0:
                self._persist_state()
            return total_cleared

    def invalidate_all(self) -> None:
        """Use up the active checkpoint and drop every hold.

        Kept for API compatibility; nothing in this package calls it. For
        an execution boundary use :meth:`end_validity`, which ends the
        validity of every checkpoint, history included, and leaves holds
        with their holders.
        """
        with self._lock:
            self._reservations.clear()
            if self._active_checkpoint:
                self._mark_used(self._active_checkpoint)
            self._persist_state()

    @property
    def checkpoint_count(self) -> int:
        """Get total number of checkpoints (active + history)."""
        with self._lock:
            return len(self._all())
