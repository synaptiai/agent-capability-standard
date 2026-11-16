"""A durable evidence store: one JSON Lines file (STANDARD v1.2 §6.6).

Each line is one ``EvidenceRecord`` (``schemas/interop/evidence.schema.json``),
written in one ``write`` when it is appended, so the file is the store's
export. The store is durable and unbounded: it never removes a record, and
it has no ``clear()``. Record ids continue the sequence across reopenings
(``ev-<n>``, one more than the highest in the file), so none is reused.

One writer per file: two stores appending to one file interleave their
sequences. A last line without its newline is an append that never
completed (the process stopped mid-write); on open the store truncates the
file to the last newline, logs the bytes it dropped and reports them as
``x-torn_tail_bytes`` in :meth:`JsonlEvidenceStore.info`, so the next append
starts on a line of its own. A complete line that does not parse is skipped
and counted as ``x-unreadable_lines``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .evidence_store import (
    EvidenceAnchor,
    EvidenceRecord,
    Listener,
    StoreInfo,
    _context,
    _default_redactor,
    _Listeners,
    _now,
    _query_kind,
)

if TYPE_CHECKING:
    from .redaction import Redactor

__all__ = ["JsonlEvidenceStore"]

logger = logging.getLogger(__name__)

_RECORD_ID = re.compile(r"ev-(0|[1-9][0-9]*)")


class JsonlEvidenceStore:
    """An append-only JSON Lines evidence store: durability ``durable``, not
    bounded. Every anchor is redacted (§6.7) before it is written."""

    DURABILITY = "durable"

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        redactor: Redactor | None = None,
        fsync: bool = False,
    ) -> None:
        """Open (or create, mode 0o600) the store's file. ``ValueError`` when
        ``path`` is a symbolic link; with ``fsync``, every append is synced
        to disk before it returns."""
        self.path = Path(path)
        if self.path.is_symlink():
            raise ValueError(f"{self.path} is a symbolic link; refusing to follow it")
        self.redactor: Redactor = redactor or _default_redactor()
        self._fsync = fsync
        self._lock = threading.Lock()
        self._listeners = _Listeners()
        self._capture_failures = 0
        self._unreadable = 0
        self._torn = 0
        self._offsets: dict[str, int] = {}
        self._next = 0
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        self._fd = os.open(self.path, flags, 0o600)
        try:
            self._load()
        except BaseException:
            os.close(self._fd)
            raise

    def _load(self) -> None:
        """Repair a torn last line, then index the records."""
        with open(self.path, "rb") as f:
            data = f.read()
        end = data.rfind(b"\n") + 1
        if end < len(data):
            self._torn = len(data) - end
            os.ftruncate(self._fd, end)
            logger.warning(
                "%s: dropped %d bytes after the last newline, an append that "
                "never completed",
                self.path,
                self._torn,
            )
            data = data[:end]
        self._size = len(data)
        offset = 0
        for line in data.splitlines(keepends=True):
            here, offset = offset, offset + len(line)
            try:
                record = EvidenceRecord.from_dict(json.loads(line))
            except (ValueError, TypeError) as e:
                self._unreadable += 1
                logger.warning(
                    "%s: skipped an unreadable line at byte %d: %s", self.path, here, e
                )
                continue
            self._offsets[record.record_id] = here
            m = _RECORD_ID.fullmatch(record.record_id)
            if m:
                self._next = max(self._next, int(m.group(1)) + 1)

    def close(self) -> None:
        """Close the file."""
        with self._lock:
            if self._fd >= 0:
                os.close(self._fd)
                self._fd = -1

    def __enter__(self) -> JsonlEvidenceStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def append(
        self,
        anchor: EvidenceAnchor,
        *,
        capability: str | None = None,
        run_id: str | None = None,
        frame: Iterable[str] | None = None,
        step: int | None = None,
        tool: str | None = None,
        call_id: str | None = None,
    ) -> EvidenceRecord:
        """Write ``anchor`` (redacted) as one line; notify once."""
        return self.append_many(
            [anchor],
            capability=capability,
            run_id=run_id,
            frame=frame,
            step=step,
            tool=tool,
            call_id=call_id,
        )[0]

    def append_many(
        self,
        anchors: Iterable[EvidenceAnchor],
        *,
        capability: str | None = None,
        run_id: str | None = None,
        frame: Iterable[str] | None = None,
        step: int | None = None,
        tool: str | None = None,
        call_id: str | None = None,
    ) -> list[EvidenceRecord]:
        """Write several anchors with one context, one line each; one
        notification. The batch is written whole or not at all: every line
        is serialized before any is written (a value that is not JSON raises
        ``TypeError`` and writes nothing), and a write that fails is cut
        back to the end of the last whole record before the error is
        raised, so no torn line is left for the next record to follow."""
        context = _context(capability, run_id, frame, step, tool, call_id)
        kept = [self.redactor.redact_anchor(a).frozen_copy() for a in anchors]
        out: list[EvidenceRecord] = []
        with self._lock:
            if self._fd < 0:
                raise ValueError(f"{self.path}: the store is closed")
            lines: list[bytes] = []
            for i, anchor in enumerate(kept):
                record = EvidenceRecord(
                    record_id=f"ev-{self._next + i}",
                    anchor=anchor,
                    recorded_at=_now(),
                    **context,
                )
                lines.append(
                    (
                        json.dumps(
                            record.to_dict(),
                            sort_keys=True,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                out.append(record)
            self._write_whole(b"".join(lines))
            offset = self._size
            for record, line in zip(out, lines, strict=True):
                self._offsets[record.record_id] = offset
                offset += len(line)
            self._size = offset
            self._next += len(out)
        self._listeners.notify(out)
        return out

    def _write_whole(self, data: bytes) -> None:
        """Append ``data`` (whole lines) and, with ``fsync``, sync it. A
        short write is continued; one that makes no progress, or an
        ``OSError``, truncates the file back to ``self._size`` and raises.
        Called with the lock held."""
        view = memoryview(data)
        try:
            while view:
                written = os.write(self._fd, view)
                if written <= 0:
                    raise OSError(
                        f"{self.path}: short write ({len(data) - len(view)} of "
                        f"{len(data)} bytes)"
                    )
                view = view[written:]
            if self._fsync and data:
                os.fsync(self._fd)
        except OSError:
            try:
                os.ftruncate(self._fd, self._size)
            except OSError as e:
                logger.error("%s: could not cut back a failed write: %s", self.path, e)
            raise

    def add_anchor(
        self, anchor: EvidenceAnchor, capability_id: str | None = None
    ) -> EvidenceRecord:
        """:meth:`append` with ``capability`` (the in-memory store's 1.1
        name)."""
        return self.append(anchor, capability=capability_id)

    def _read(self) -> Iterator[EvidenceRecord]:
        """The indexed records, in file order."""
        with self._lock:
            wanted = set(self._offsets.values())
            size = self._size
        with open(self.path, "rb") as f:
            offset = 0
            for line in f:
                if offset >= size:
                    break
                here, offset = offset, offset + len(line)
                if here in wanted:
                    yield EvidenceRecord.from_dict(json.loads(line))

    def get(self, record_id: str) -> EvidenceRecord | None:
        """The record with ``record_id``, read at its offset, or None."""
        with self._lock:
            offset = self._offsets.get(record_id)
        if offset is None:
            return None
        with open(self.path, "rb") as f:
            f.seek(offset)
            return EvidenceRecord.from_dict(json.loads(f.readline()))

    def records(
        self,
        *,
        capability: str | None = None,
        kind: str | None = None,
        run_id: str | None = None,
    ) -> list[EvidenceRecord]:
        """The records that match every given value, in append order. A
        legacy ``kind`` is answered by ref prefix, with a warning."""
        canonical, prefixes = _query_kind(kind) if kind is not None else (None, None)
        return [
            r
            for r in self._read()
            if (capability is None or r.capability == capability)
            and (run_id is None or r.run_id == run_id)
            and (canonical is None or r.anchor.kind == canonical)
            and (prefixes is None or r.anchor.ref.startswith(prefixes))
        ]

    def export(self) -> Iterator[dict[str, Any]]:
        """Every record's ``EvidenceRecord`` JSON, in append order."""
        return (r.to_dict() for r in self._read())

    def info(self) -> StoreInfo:
        """Durability ``durable``, not bounded; nothing is ever removed."""
        with self._lock:
            return StoreInfo(
                durability=self.DURABILITY,
                bounded=False,
                count=len(self._offsets),
                removed=0,
                capture_failures=self._capture_failures,
                extra={
                    "x-torn_tail_bytes": self._torn,
                    "x-unreadable_lines": self._unreadable,
                },
            )

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener`` with an ``EvidenceRecorded`` payload after each
        append; returns the unsubscribe function."""
        return self._listeners.subscribe(listener)

    def record_capture_failure(self, call_id: str | None, message: str) -> None:
        """Count a capture that failed and log it (§6.4: never silently)."""
        with self._lock:
            self._capture_failures += 1
        logger.warning("evidence capture failed (call %s): %s", call_id, message)

    def __len__(self) -> int:
        with self._lock:
            return len(self._offsets)
