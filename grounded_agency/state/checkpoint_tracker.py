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
- A tracker is one scope (section 5.18.5). The checkpoints it reads back
  from its state file were taken in another scope (an earlier process, or
  another tracker on the same ``checkpoint_dir``): it finds and restores
  them, but they authorise none of its calls and count as no checkpoint
  taken in its scope. Trackers that share a directory merge their records
  into the state file under a lock, so none loses another's.

Validity is what a checkpoint authorises; retention is what it can restore
(STANDARD 1.2.0 section 4.4.1). With a :class:`FileSnapshotStore`
(``snapshots``), a checkpoint also holds a copy of the files in its scope:
:meth:`CheckpointTracker.restore_checkpoint` puts them back, whether or not
the checkpoint is still valid or was used, as long as its content is kept.
The tracker's own state, archive and marker are never captured, so no
rollback brings a used checkpoint back.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..utils.git import SAFE_GIT_OPTIONS, git_dir_is_made, safe_git_environment
from ..utils.layer_dir import LayerDir, LinkedPathError, open_layer_dir
from .redaction import DEFAULT_REDACTOR, Redactor

try:  # POSIX: trackers that share a directory serialise their writes
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows
    _fcntl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .snapshots import FileSnapshotStore, Restore

_STATE_FILE = "tracker_state.json"
_STATE_LOCK = "tracker_state.lock"
_ARCHIVE_DIR = "archive"
_ARCHIVE_FILE = "pruned_checkpoints.jsonl"

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
            ValueError: If ``data`` is not a dict (a line or entry that
                parsed to a list, a number, a string or null reads as one
                that does not parse), or required fields have wrong types.
            KeyError: If required fields are missing.
        """
        # Validate types to catch crafted/corrupt state files early.
        if not isinstance(data, dict):
            raise ValueError("a checkpoint is a JSON object")
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


def _file_identity(st: os.stat_result) -> tuple[int, ...]:
    """A file as fstat gives it: device, inode, size, modification and
    change times. A file replaced since has another."""
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _tracked_by_git(path: Path) -> bool:
    """Whether git tracks ``path``, an existing file: one a repository ships,
    not one this layer wrote. git is asked from the file's own directory, so
    a linked directory or a submodule is read where it leads, but only where
    the git directory it finds there is one git made for a work tree
    (:func:`~..utils.git.git_dir_is_made`): a repository can ship the
    directory, or one above it, as a git directory of its own, whose index
    would answer for the file and whose configuration names programs git
    runs (the layer's git runs none). No git, or no repository, reads as
    untracked (nothing a clone can ship); any other git directory, any
    answer but yes or no, and a git that does not answer in time read as
    tracked, so the file is not trusted."""
    if not path.is_file():
        return False
    git = shutil.which("git")
    if git is None:
        return False
    where = str(path.parent)
    try:
        found = subprocess.run(
            [git, *SAFE_GIT_OPTIONS, "-C", where, "rev-parse", "--absolute-git-dir"],
            capture_output=True,
            timeout=10,
            check=False,
            env=safe_git_environment(),
        )
        if found.returncode != 0:
            return False
        if not git_dir_is_made(found.stdout.decode("utf-8", "surrogateescape").strip()):
            return True
        result = subprocess.run(
            [
                git,
                *SAFE_GIT_OPTIONS,
                "-C",
                where,
                "ls-files",
                "--error-unmatch",
                "--",
                path.name,
            ],
            capture_output=True,
            timeout=10,
            check=False,
            env=safe_git_environment(),
        )
    except subprocess.TimeoutExpired:
        return True
    except OSError, subprocess.SubprocessError:
        return False
    return result.returncode != 1


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
    expires_at, consumed, consumed_at, metadata, invalidated_at.

    The checkpoints are the layer's records of the calls that took them
    (STANDARD 1.2.0 sections 5.18.8, 6.7), and a call's ``reason`` and
    ``scope`` may be text a model wrote: every string the tracker records
    (a checkpoint's ``reason``, its ``scope`` items, its ``metadata`` and
    the words that end or use it) is redacted with its ``redactor`` when
    recorded, so no secret it recognises reaches the records in memory,
    the state file or the archive. A snapshot store captures the files the
    scope names as given.

    One tracker is one scope (STANDARD 1.2.0 section 5.18.5). What it reads
    back from the state file was recorded in another scope: by an earlier
    process, or by another tracker on the same directory (another adapter,
    which may still be running). Those checkpoints are found and restored
    (:meth:`find_checkpoint`, :meth:`restore_checkpoint`), but they
    authorise no call of this tracker, count as no checkpoint taken in its
    scope (:meth:`has_taken_since`, :meth:`has_commit`), and are never held,
    used or ended by it (it prunes them from its history as its own); a
    hold the file names is its holder's. Each write merges
    this tracker's records with those other trackers wrote since it loaded
    (under an exclusive lock on ``tracker_state.lock`` where the platform
    has ``fcntl``), so a tracker never drops or rewinds another's.
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
        snapshots: FileSnapshotStore | None = None,
        redactor: Redactor = DEFAULT_REDACTOR,
    ) -> None:
        """
        Initialize the tracker.

        Args:
            checkpoint_dir: Directory to store checkpoint metadata. It,
                        its ``archive/`` and their files are opened without
                        following a symbolic link (nor one at a directory on
                        the way to a relative path): with one there, the
                        tracker writes nothing and keeps its records in
                        memory.
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
            snapshots: Where checkpoints keep their content (STANDARD 1.2.0
                       section 4.4.1). With it, :meth:`create_checkpoint`
                       copies the files in the checkpoint's scope and
                       :meth:`restore_checkpoint` puts them back; the
                       tracker's ``checkpoint_dir`` and ``marker_dir`` are
                       protected in it, never captured or restored.
            redactor: What the records are redacted with (STANDARD 1.2.0
                       section 6.7; default: the default patterns). The
                       adapter passes its own, which knows the host's
                       registered secrets.

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
        # When the newest checkpoint of this scope was taken: survives
        # history pruning.
        self._last_taken_at: datetime | None = None
        # Ids of the checkpoints read back from the state file: another
        # scope's, never valid here, so never held, used or ended here
        # (section 5.18.5).
        self._earlier: set[str] = set()
        # Ids of every checkpoint this tracker knows (read back or taken):
        # a record in the state file with another id was written by another
        # tracker since the load, and each write keeps it.
        self._known: set[str] = set()
        # The state file this tracker wrote last, as fstat gives it (device,
        # inode, size, modification and change times): a file that is still
        # that one is merged without asking git whether it tracks it.
        self._written_state: tuple[int, ...] | None = None
        self._snapshots = snapshots
        self._redactor = redactor
        if snapshots is not None:
            # The tracker's own records are never within a rollback's reach
            # (section 4.4.1): a used checkpoint stays used.
            snapshots.protect(self._checkpoint_dir)
            if self._marker_dir is not None:
                snapshots.protect(self._marker_dir)
        self._load_persisted_state()

    @property
    def snapshots(self) -> FileSnapshotStore | None:
        """The store that keeps checkpoints' content, if any."""
        return self._snapshots

    @property
    def redactor(self) -> Redactor:
        """What the tracker redacts its records with (section 6.7)."""
        return self._redactor

    @redactor.setter
    def redactor(self, redactor: Redactor) -> None:
        self._redactor = redactor

    def _redacted_text(self, text: str) -> str:
        """``text`` as a record keeps it: each secret replaced."""
        return self._redactor.redact_text(text)[0]

    def _now(self) -> datetime:
        return self._clock()

    @property
    def max_age_minutes(self) -> float:
        """The maximum age of a checkpoint, in minutes (section 5.18.6)."""
        return self._max_age_minutes

    def _valid(self, checkpoint: Checkpoint, now: datetime) -> bool:
        """Whether ``checkpoint`` can authorise a call at ``now``: taken by
        this tracker (one read back from the state file is another scope's,
        section 5.18.5), valid by its own record, taken no later than
        ``now`` and no longer ago than the maximum age. A checkpoint dated
        after ``now`` (a clock that stepped back) authorises nothing: the
        maximum age could not bound it."""
        return (
            checkpoint.id not in self._earlier
            and checkpoint.is_valid(now)
            and checkpoint.created_at <= now
            and now <= checkpoint.created_at + timedelta(minutes=self._max_age_minutes)
        )

    # ------------------------------------------------------------------
    # Persistence (TD-011)
    # ------------------------------------------------------------------

    def _state_file_path(self) -> Path:
        """Path to the persisted tracker state file."""
        return self._checkpoint_dir / _STATE_FILE

    def _state_lock_path(self) -> Path:
        """Path to the lock trackers that share the directory write under."""
        return self._checkpoint_dir / _STATE_LOCK

    def _open_dir(self, create: bool) -> LayerDir | None:
        """``checkpoint_dir``, opened without following a symbolic link at
        it or, for a relative ``checkpoint_dir``, at any directory on the
        way to it (:func:`~..utils.layer_dir.open_layer_dir`): a repository
        can ship a link there, which would take the tracker's records out
        of the project. None when it does not exist and ``create`` is
        false.

        Raises:
            LinkedPathError: It is, or goes through, a link.
        """
        return open_layer_dir(self._checkpoint_dir, create=create)

    @contextmanager
    def _state_file_lock(self, where: LayerDir) -> Iterator[None]:
        """An exclusive lock on :meth:`_state_lock_path`, where the platform
        has ``fcntl``: trackers that share the directory, in this process or
        another, read and write the state file one at a time. Without
        ``fcntl`` the merge still runs, unlocked."""
        if _fcntl is None:  # pragma: no cover - Windows
            yield
            return
        fd = where.open(_STATE_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _fcntl.flock(fd, _fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _open_state_file(self, where: LayerDir) -> Any:
        """The state file in ``where``, opened for reading without
        following a symbolic link (``O_NOFOLLOW`` and ``fstat`` on the
        descriptor, so no check races the read). None when there is none,
        or it is a link or not a regular file."""
        try:
            fd = where.open_regular(_STATE_FILE, os.O_RDONLY)
        except FileNotFoundError:
            return None
        except LinkedPathError:
            logger.warning(
                "Refusing to follow symlink for state file: %s", self._state_file_path()
            )
            return None
        try:
            return os.fdopen(fd, encoding="utf-8")
        except Exception:
            os.close(fd)
            raise

    def _read_state_file(
        self, where: LayerDir, *, untracked: bool = False
    ) -> dict[str, Any] | None:
        """The state file's object, or None when there is none, it is a
        link, or it is larger than the limit. With ``untracked``, also None
        when git tracks it (:func:`_tracked_by_git`), unless it is still the
        file this tracker wrote last: a repository can ship one, and the
        load refuses it, so the merge of each write must not read it either.

        Raises:
            OSError, ValueError: The file cannot be read, or holds no JSON
                object. JSON nested deeper than the parser's stack allows
                (`[[[...`, which raises RecursionError, no ValueError) is a
                ValueError here, so every caller handles it as a file that
                does not parse.
        """
        f = self._open_state_file(where)
        if f is None:
            return None
        with f:
            st = os.fstat(f.fileno())
            if st.st_size > self._MAX_STATE_FILE_BYTES:
                logger.warning(
                    "State file too large (%d bytes, limit %d) — starting fresh",
                    st.st_size,
                    self._MAX_STATE_FILE_BYTES,
                )
                return None
            if (
                untracked
                and _file_identity(st) != self._written_state
                and _tracked_by_git(self._state_file_path())
            ):
                logger.warning(
                    "Not merging %s: git tracks it, so a repository shipped it; "
                    "it is replaced",
                    self._state_file_path(),
                )
                return None
            raw = f.read()
        try:
            state = json.loads(raw)
        except RecursionError:
            raise ValueError("the state file nests too deeply to parse") from None
        if not isinstance(state, dict):
            raise ValueError("the state file holds no JSON object")
        return state

    @staticmethod
    def _checkpoints_in(state: dict[str, Any]) -> list[Checkpoint]:
        """The checkpoints a state file's object records (its active one,
        then its history), skipping any entry that does not read as one."""
        history = state.get("history")
        entries = [state.get("active"), *(history if isinstance(history, list) else [])]
        found: list[Checkpoint] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                found.append(Checkpoint.from_dict(entry))
            except KeyError, ValueError, TypeError, AttributeError:
                continue
        return found

    def _merged_state(self, where: LayerDir) -> dict[str, Any]:
        """What :meth:`_persist_state` writes: this tracker's checkpoints
        and holds as it holds them; each checkpoint it read back as the
        file has it now (its own tracker may have used it since); and every
        checkpoint and hold another tracker on the directory wrote since
        this one loaded, unchanged. A checkpoint this tracker removed
        (pruned or cleared) stays removed. Caller holds the file lock."""
        try:
            current = self._read_state_file(where, untracked=True) or {}
        except (OSError, ValueError) as e:
            logger.warning("Replacing a state file that cannot be read: %s", e)
            current = {}
        on_file = {c.id: c for c in self._checkpoints_in(current)}
        history = [
            on_file.get(c.id, c) if c.id in self._earlier else c
            for c in self._checkpoint_history
        ]
        history += [c for c in on_file.values() if c.id not in self._known]
        history.sort(key=lambda c: c.created_at.timestamp())
        history = history[-self._max_history :]
        written = {c.id for c in history}
        if self._active_checkpoint is not None:
            written.add(self._active_checkpoint.id)
        own = self._known - self._earlier
        holds = [
            {"checkpoint_id": r.checkpoint_id, "holder": r.holder}
            for r in self._reservations.values()
        ]
        file_holds = current.get("reservations")
        for hold in file_holds if isinstance(file_holds, list) else []:
            if not isinstance(hold, dict):
                continue
            checkpoint_id = hold.get("checkpoint_id")
            if (
                isinstance(checkpoint_id, str)
                and checkpoint_id in written
                and checkpoint_id not in own
                and checkpoint_id not in self._reservations
            ):
                holds.append(
                    {"checkpoint_id": checkpoint_id, "holder": str(hold.get("holder"))}
                )
        last = self._last_taken_at
        try:
            file_last = datetime.fromisoformat(str(current.get("last_taken_at")))
            if last is None or file_last.timestamp() > last.timestamp():
                last = file_last
        except ValueError:
            pass
        return {
            "active": (
                self._active_checkpoint.to_dict() if self._active_checkpoint else None
            ),
            "history": [c.to_dict() for c in history],
            "reservations": holds,
            "last_taken_at": last.isoformat() if last else None,
        }

    def _persist_state(self) -> None:
        """Atomically write tracker state to disk, merged with what other
        trackers on the directory wrote (:meth:`_merged_state`), under the
        directory's lock.

        Uses write-to-tmp + rename for crash safety. Every file is opened in
        ``checkpoint_dir`` without following a link (:meth:`_open_dir`): a
        directory that is, or goes through, one is not written to, and the
        tracker keeps its records in memory. Never raises: a write that
        fails is logged, and the change stands in memory.
        """
        try:
            where = self._open_dir(create=True)
            if where is None:  # pragma: no cover - create=True makes it
                raise FileNotFoundError(str(self._checkpoint_dir))
            with where, self._state_file_lock(where):
                state = self._merged_state(where)
                tmp_name, fd = where.create_temp("tmp", ".tmp")
                try:
                    try:
                        f = os.fdopen(fd, "w", encoding="utf-8")
                    except Exception:
                        os.close(fd)
                        raise
                    with f:
                        json.dump(state, f)
                    where.replace(tmp_name, _STATE_FILE)
                except Exception:
                    # Clean up temp file on failure; re-raise original error.
                    try:
                        where.unlink(tmp_name)
                    except OSError:
                        pass
                    raise
                # What was written, as the next merge will find it (the
                # rename may change its change time): still under the lock.
                fd = where.open_regular(_STATE_FILE, os.O_RDONLY)
                try:
                    self._written_state = _file_identity(os.fstat(fd))
                finally:
                    os.close(fd)
            # A removed checkpoint is gone from the file now: only the ids
            # this tracker still holds need to stay known.
            self._known = {c.id for c in self._all()}
        except Exception as e:
            # Whatever the reason (RecursionError included), the change
            # stands in memory, which is what this tracker's calls are
            # decided on: a caller in the middle of a transition (a hold
            # resolved at a boundary, then every checkpoint ended) must not
            # be cut short by a write that failed.
            logger.warning("Failed to persist checkpoint state: %s", e)

    def _load_persisted_state(self) -> None:
        """Load tracker state from disk if available.

        What is loaded was recorded in another scope (STANDARD 1.2.0 section
        5.18.5): by an earlier process, or by another tracker on the same
        directory. It goes to the history, to be found and restored; none of
        it authorises a call of this tracker or counts as a checkpoint taken
        in its scope, and this tracker never holds, uses or ends it. A hold
        the file names is its holder's, and stays in the file.

        A state file git tracks is not loaded: a repository can ship one (a
        clone or a checkout writes it), and its checkpoints were taken by no
        call of this layer (STANDARD 1.2.0 sections 5.18.5, 5.18.6). The
        tracker starts fresh, and logs why. So does a file that is a
        symbolic link, larger than the limit, or does not parse, and one in
        a ``checkpoint_dir`` that is, or goes through, a link
        (:meth:`_open_dir`).
        """
        state_path = self._state_file_path()
        try:
            where = self._open_dir(create=False)
        except LinkedPathError as e:
            logger.warning(
                "Not loading checkpoint state: %s. A repository may have shipped "
                "the link; checkpoints are kept in memory only",
                e,
            )
            return
        except OSError as e:
            logger.warning("Failed to load persisted checkpoint state: %s", e)
            return
        if where is None:
            return
        if _tracked_by_git(state_path):
            where.close()
            logger.warning(
                "Not loading %s: git tracks it, so a repository shipped it and "
                "no checkpoint in it was taken here; remove it from the "
                "repository",
                state_path,
            )
            return
        try:
            with where:
                state = self._read_state_file(where)
            if state is None:
                return
            loaded_at = self._now()
            loaded: list[Checkpoint] = []
            if state.get("active"):
                loaded.append(Checkpoint.from_dict(state["active"]))
            # Cap loaded history to _max_history to prevent unbounded growth
            # from a crafted or accumulated state file.
            loaded += [
                Checkpoint.from_dict(entry)
                for entry in state.get("history", [])[: self._max_history]
            ]
            # A checkpoint dated after the load (a crafted file, or a clock
            # that stepped back) names no restore point the maximum age
            # could bound: it is dropped (section 5.18.6).
            future = [c.id for c in loaded if c.created_at > loaded_at]
            if future:
                logger.warning(
                    "Dropping %d checkpoint(s) dated after the load time: %s",
                    len(future),
                    ", ".join(future),
                )
                loaded = [c for c in loaded if c.created_at <= loaded_at]
            loaded.sort(key=lambda c: c.created_at.timestamp())
            self._checkpoint_history = loaded
            self._earlier = {c.id for c in loaded}
            self._known = set(self._earlier)
            if any(c.is_valid(loaded_at) for c in loaded):
                logger.info(
                    "Read back %d checkpoint(s) from %s: taken in another "
                    "scope, they authorise no call of this tracker",
                    len(loaded),
                    state_path,
                )
        except (
            json.JSONDecodeError,
            KeyError,
            ValueError,
            TypeError,
            AttributeError,
            OSError,
            RecursionError,
        ) as e:
            logger.warning("Failed to load persisted checkpoint state: %s", e)
            # Start fresh — don't propagate corrupt state
            self._active_checkpoint = None
            self._checkpoint_history = []
            self._earlier = set()
            self._known = set()

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
                checkpoint.metadata["consumed_by"] = self._redacted_text(by)
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

        The checkpoint records ``reason``, ``scope`` and ``metadata``
        with every secret the tracker's ``redactor`` recognises replaced
        (section 6.7); a snapshot store captures what ``scope`` names as
        given.

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
        metadata = dict(metadata or {})
        if self._snapshots is not None:
            # The content, before the checkpoint is recorded (I/O outside
            # the lock): a capture that fails records no checkpoint.
            capture = self._snapshots.capture(checkpoint_id, scope)
            summary = capture.output()
            summary["captured"] = len(capture.captured)
            summary.pop("checkpoint_id", None)
            summary.pop("timestamp", None)
            metadata["capture"] = summary
        # The record holds no secret the redactor recognises (section 6.7):
        # a bound tool's reason and scope are the model's words.
        redacted_metadata, _ = self._redactor.redact(metadata)
        now = self._now()
        checkpoint = Checkpoint(
            id=checkpoint_id,
            scope=[self._redacted_text(str(s)) for s in scope],
            reason=self._redacted_text(str(reason)),
            created_at=now,
            expires_at=now + timedelta(minutes=min(minutes, self._max_age_minutes)),
            metadata=redacted_metadata,
        )

        with self._lock:
            # Move previous active checkpoint to history
            if self._active_checkpoint:
                self._checkpoint_history.append(self._active_checkpoint)
                self._prune_history_if_needed()

            # A hold of the previous checkpoint stays with its holder.
            self._active_checkpoint = checkpoint
            self._known.add(checkpoint.id)
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

    def find_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """A checkpoint by id: active, in history, or archived (pruned from
        the history), valid or not; None when the tracker never took it."""
        with self._lock:
            found = self._find(checkpoint_id)
        if found is not None:
            return found
        for archived in self.get_archived_checkpoints():
            if archived.id == checkpoint_id:
                return archived
        return None

    def restore_checkpoint(
        self, checkpoint_id: str, scope: Sequence[str] | None = None
    ) -> Restore:
        """Put back what checkpoint ``checkpoint_id`` captured, within
        ``scope`` (all of it when None), STANDARD 1.2.0 section 4.4.1. It
        neither uses nor invalidates any checkpoint (section 5.2.2: a
        rollback uses none), and works on a used or expired checkpoint while
        its content is kept.

        Raises:
            KeyError: The tracker never took the checkpoint.
            NotImplementedError: The tracker keeps no content (no
                ``snapshots``).
        """
        if self.find_checkpoint(checkpoint_id) is None:
            raise KeyError(checkpoint_id)
        if self._snapshots is None:
            raise NotImplementedError("this tracker keeps no checkpoint content")
        return self._snapshots.restore(checkpoint_id, scope)

    def checkpoint_output(self, checkpoint_id: str) -> dict[str, Any]:
        """The ``checkpoint`` capability's output for a checkpoint this
        tracker took: its id, time and, with a snapshot store, what it
        captured (section 4.4.1).

        Raises:
            KeyError: The tracker never took the checkpoint.
        """
        checkpoint = self.find_checkpoint(checkpoint_id)
        if checkpoint is None:
            raise KeyError(checkpoint_id)
        out: dict[str, Any] = {
            "checkpoint_id": checkpoint.id,
            "timestamp": checkpoint.created_at.astimezone(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        }
        capture = checkpoint.metadata.get("capture")
        if isinstance(capture, dict):
            out.update({k: v for k, v in capture.items() if k != "captured"})
            manifest = (
                self._snapshots.manifest(checkpoint.id)
                if self._snapshots is not None
                else None
            )
            if manifest is not None:
                out["captured"] = sorted(manifest["files"])
        out["evidence_anchors"] = [
            {"ref": f"checkpoint:{checkpoint.id}", "kind": "record"}
        ]
        return out

    def has_commit(self, commit: str, since: datetime | None = None) -> bool:
        """Whether a checkpoint this tracker took at or after ``since`` (any
        time when omitted) and not after now, valid or not, recorded
        ``commit`` as its restore point (``metadata["commit"]``, as ``git
        stash create`` printed it): what lets ``git stash pop|apply
        <commit>`` count as a rollback (section 5.18.3). A checkpoint read
        back from the state file was taken in another scope and is not
        counted; one pruned from the history is not found."""
        with self._lock:
            now = self._now()
            return any(
                c.id not in self._earlier
                and c.metadata.get("commit") == commit
                and (since is None or c.created_at >= since)
                and c.created_at <= now
                for c in self._all()
            )

    def has_taken_since(self, when: datetime) -> bool:
        """Whether this tracker took a checkpoint at or after ``when``, and
        not after now: what a ``checkpoint`` prerequisite reads (section
        5.18.5). History pruning does not hide one; one read back from the
        state file was taken in another scope and does not count."""
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

    def _archive_path(self) -> Path:
        """Path to the archive of pruned checkpoints."""
        return self._checkpoint_dir / _ARCHIVE_DIR / _ARCHIVE_FILE

    def _archive_refusal(self) -> str | None:
        """Why the archive is not read or written, or None: git tracks it,
        so a repository shipped it, and its records were written by no
        tracker (as for the state file, :meth:`_load_persisted_state`)."""
        if _tracked_by_git(self._archive_path()):
            return (
                f"git tracks {self._archive_path()}, so a repository shipped it; "
                f"remove it from the repository"
            )
        return None

    def _archive_checkpoints(self, checkpoints: list[Checkpoint]) -> None:
        """SEC-011: Write pruned checkpoints to archive JSONL file.

        Archives are append-only JSONL files in .checkpoints/archive/.
        Each line is a JSON-serialized checkpoint dict.

        The archive is opened in ``checkpoint_dir/archive`` without
        following a symbolic link at either directory or at the file, and
        only a regular file is appended to (``O_NOFOLLOW`` and ``fstat`` on
        the descriptor): a repository can ship a link there, which would
        take the records (a ``reason`` and ``scope`` a model may have
        written among them) out of the project. An archive git tracks is
        not written to either. When the archive cannot be written, the
        prune is logged with the ids it drops. Either way, the pruned
        checkpoints' content is discarded (section 4.4.1).
        """
        if not checkpoints:
            return
        archive_file = self._archive_path()
        try:
            where = self._open_dir(create=True)
            if where is None:  # pragma: no cover - create=True makes it
                raise FileNotFoundError(str(self._checkpoint_dir))
            with where:
                archive = where.subdir(_ARCHIVE_DIR, create=True)
            if archive is None:  # pragma: no cover - create=True makes it
                raise FileNotFoundError(str(archive_file.parent))
            with archive:
                refusal = self._archive_refusal()
                if refusal is not None:
                    raise OSError(refusal)
                fd = archive.open_regular(
                    _ARCHIVE_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
                )
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                for cp in checkpoints:
                    f.write(json.dumps(cp.to_dict()) + "\n")
            logger.info(
                "Archived %d pruned checkpoints to %s",
                len(checkpoints),
                archive_file,
            )
        except OSError as e:
            logger.warning(
                "Pruned %d checkpoint(s) from the history without archiving "
                "them (%s): %s",
                len(checkpoints),
                e,
                ", ".join(cp.id for cp in checkpoints),
            )
        # Content retention ends with the history entry (section 4.4.1):
        # a later rollback to it reports `discarded`.
        if self._snapshots is not None:
            for cp in checkpoints:
                try:
                    self._snapshots.discard(cp.id)
                except (OSError, ValueError) as e:
                    logger.warning("Failed to discard checkpoint content: %s", e)

    def get_archived_checkpoints(self) -> list[Checkpoint]:
        """SEC-011: Retrieve archived (pruned) checkpoints from JSONL.

        Per-line error handling: corrupt lines are skipped with a warning
        rather than aborting the entire archive read. A line that parses to
        anything but a checkpoint's object (a list, a number, a string,
        null) is one, as is a line nested deeper than the parser allows
        (RecursionError, raised or not according to the stack size; the
        parser can return the nested lists instead). File-level errors
        (permissions, missing file) are caught at the outer level. The
        archive is read as it is written (:meth:`_archive_checkpoints`):
        never through a symbolic link, a regular file only, and not when
        git tracks it.

        Returns:
            List of archived Checkpoint objects, oldest first.
        """
        try:
            where = self._open_dir(create=False)
            if where is None:
                return []
            with where:
                archive = where.subdir(_ARCHIVE_DIR)
            if archive is None:
                return []
            with archive:
                try:
                    fd = archive.open_regular(_ARCHIVE_FILE, os.O_RDONLY)
                except FileNotFoundError:
                    return []
            with os.fdopen(fd, encoding="utf-8") as f:
                # P2-4: Reject oversized archive files before reading
                size = os.fstat(f.fileno()).st_size
                if size > self._MAX_STATE_FILE_BYTES:
                    logger.warning(
                        "Archive file too large (%d bytes, limit %d) — skipping",
                        size,
                        self._MAX_STATE_FILE_BYTES,
                    )
                    return []
                refusal = self._archive_refusal()
                if refusal is not None:
                    logger.warning("Not reading the checkpoint archive: %s", refusal)
                    return []
                results: list[Checkpoint] = []
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        results.append(Checkpoint.from_dict(json.loads(line)))
                    except (
                        json.JSONDecodeError,
                        KeyError,
                        ValueError,
                        TypeError,
                        RecursionError,
                    ) as e:
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
                    checkpoint.metadata["invalidated_by"] = self._redacted_text(reason)
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
