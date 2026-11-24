"""
At most one effect per idempotency key (STANDARD v1.2 §4.4.2).

Every ``InvokeCapability`` carries ``idempotency_key``: ``<run_id>:<n>``, the
same for every attempt of one pass of a step. A host MUST NOT transmit twice
for one key: given a key it already acted under, it answers with that
output; when it cannot tell whether an earlier attempt took effect, it does
not act and answers ``outcome_unknown``; and a key that arrives with another
capability or other inputs than it was first used with means a ``run_id``
was reused, so it does not act and answers ``key_conflict``.

:class:`IdempotencyLog` keeps that record. Keys are unique only while
``run_id``s are (§5.19.2). Without a ``path`` the log is in memory and its
keys do not survive a restart: a host that saves runs (§5.19.4), and so
re-delivers a pending attempt after a restart, gives it a path.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .. import _core
from ..state.redaction import DEFAULT_REDACTOR, Redactor
from ._responses import redact_anchors

_MAX_LOG_BYTES = 256 * 1024 * 1024


def inputs_sha256(inputs: Any) -> str:
    """The SHA-256 of the canonical JSON (RFC 8785) of an action's inputs:
    two attempts of one pass have the same."""
    return hashlib.sha256(_core.canonical_json(inputs).encode()).hexdigest()


_STATES = ("started", "done", "cleared")


def _read_entry(line: bytes) -> dict[str, Any]:
    """The entry a line of the log records: an object with a string
    ``key`` and a ``state`` the log writes; unless the key was cleared, a
    string ``capability`` and ``inputs_sha256`` and a numeric ``at``; once
    done, a ``value``. ValueError for any other line, as for one that does
    not parse: a list, a number, a string, null, an object short of what a
    lookup reads, and a line nested deeper than the parser allows
    (RecursionError, raised or not according to the stack size; the
    parser can return the nested lists instead)."""
    try:
        entry = json.loads(line)
    except RecursionError:
        raise ValueError("a line nests too deeply to parse") from None
    if not isinstance(entry, dict):
        raise ValueError(f"a line holds a {type(entry).__name__}, not an entry")
    state = entry.get("state")
    at = entry.get("at")
    if (
        not isinstance(entry.get("key"), str)
        or state not in _STATES
        or (
            state != "cleared"
            and (
                not isinstance(entry.get("capability"), str)
                or not isinstance(entry.get("inputs_sha256"), str)
                or not isinstance(at, int | float)
                or isinstance(at, bool)
            )
        )
        or (state == "done" and "value" not in entry)
    ):
        raise ValueError("a line holds an object that is no entry of this log")
    return entry


def _replay(entry: Mapping[str, Any]) -> dict[str, Any]:
    """The ``Output`` a done entry answers with: its value and, when the
    effect's response carried one, its ``evidence_seen``."""
    response: dict[str, Any] = {"kind": "Output", "value": entry["value"]}
    if "evidence_seen" in entry:
        response["evidence_seen"] = entry["evidence_seen"]
    return response


class IdempotencyLog:
    """At most one effect per idempotency key (STANDARD v1.2 §4.4.2).

    Keys are unique only while run_ids are (§5.19.2). Without a path the log
    is in memory and its keys do not survive a restart: a host that saves
    runs (§5.19.4) must give it a path. Each entry keeps the key, the
    capability, the SHA-256 of the canonical inputs, whether the effect is
    ``started`` or ``done``, when, the destination and, once done, the
    output it answered with and its ``evidence_seen``.

    The log is the host's record of what it did (§6.4), so it holds no
    secret its ``redactor`` recognises (§6.7): the destination is redacted,
    and the output is kept as a runner submits it, its evidence anchors
    redacted (their digest gone) and ``evidence_seen`` rewritten to match,
    with every other secret in the output and in ``evidence_seen`` replaced
    too. A replay answers with that output. A
    :class:`~grounded_agency.workflows.runner.WorkflowRunner` gives the log
    of each host it drives what its own ``redactor`` recognises.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        clock: Callable[[], int] | None = None,
        redactor: Redactor = DEFAULT_REDACTOR,
    ) -> None:
        self._path = Path(path) if path is not None else None
        self._clock: Callable[[], int] = clock or (lambda: time.time_ns() // 1_000_000)
        self._redactor = redactor
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        if self._path is not None:
            self._load()

    @property
    def redactor(self) -> Redactor:
        """What the log redacts with (§6.7)."""
        return self._redactor

    @redactor.setter
    def redactor(self, redactor: Redactor) -> None:
        self._redactor = redactor

    @property
    def path(self) -> Path | None:
        """The JSON Lines file the log is kept in, or None (in memory)."""
        return self._path

    @property
    def durable(self) -> bool:
        """Whether the keys survive a restart (the log has a path)."""
        return self._path is not None

    def perform(
        self,
        action: Mapping[str, Any],
        effect: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Answer ``action`` (an ``InvokeCapability``) with ``effect()`` at
        most once per key. ``effect`` returns the response (``Output`` or
        ``Error``); it returns an ``Error`` only when nothing took effect,
        and raises when it cannot tell (the entry then stays ``started``, so
        a later attempt is answered ``outcome_unknown``). An attempt whose
        key was done is answered with the ``Output`` it got, its
        ``evidence_seen`` included (§5.20), as the log keeps it: redacted
        (§6.7). An action with no key is passed
        straight to ``effect``. A delegation that names the one it
        ``replaces`` has a key of its own (§4.4.2), so it is kept like any
        other: a re-delivery of it is answered, not performed again."""
        key = action.get("idempotency_key")
        if not isinstance(key, str):
            return effect()
        capability = str(action.get("capability", ""))
        digest = inputs_sha256(action.get("inputs"))
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                if (
                    entry["capability"] != capability
                    or entry["inputs_sha256"] != digest
                ):
                    return {
                        "kind": "Error",
                        "code": "R402",
                        "reason": "key_conflict",
                        "message": f"idempotency key '{key}' was first used for another "
                        f"{entry['capability']} request, so a run_id was reused; nothing "
                        "was done (STANDARD §4.4.2, §5.19.2)",
                    }
                if entry["state"] == "done":
                    return _replay(entry)
                return {
                    "kind": "Error",
                    "code": "R402",
                    "reason": "outcome_unknown",
                    "message": f"an earlier attempt under idempotency key '{key}' may have "
                    "taken effect, and this host cannot tell; it did not act again "
                    "(STANDARD §4.4.2)",
                }
            started: dict[str, Any] = {
                "key": key,
                "capability": capability,
                "inputs_sha256": digest,
                "state": "started",
                "at": self._clock(),
            }
            destination = (action.get("inputs") or {}).get("destination")
            if isinstance(destination, str):
                started["destination"] = self._redactor.redact_text(destination)[0]
            self._record(started)
        # The effect runs outside the lock; an exception leaves `started`.
        response = effect()
        with self._lock:
            if response.get("kind") == "Output":
                self._record({**started, "state": "done", **self._kept(response)})
            else:
                self._record({"key": key, "state": "cleared"})
        return response

    def _kept(self, response: Mapping[str, Any]) -> dict[str, Any]:
        """What a done entry keeps of an ``Output``: its ``value`` and its
        ``evidence_seen`` as a runner would submit them (the anchors
        redacted, ``evidence_seen`` rewritten to match, §5.20), and every
        other secret in either replaced (§6.4, §6.7). The host's attestation
        is part of the answer: a replay without it would fail an attested
        policy (F505)."""
        submitted = redact_anchors(self._redactor, dict(response))
        value = submitted.get("value")
        anchors = value.get("evidence_anchors") if isinstance(value, dict) else None
        if isinstance(value, dict) and isinstance(anchors, list):
            rest = {k: v for k, v in value.items() if k != "evidence_anchors"}
            value = {**self._redactor.redact(rest)[0], "evidence_anchors": anchors}
        else:
            value = self._redactor.redact(value)[0]
        kept: dict[str, Any] = {"value": value}
        if "evidence_seen" in submitted:
            kept["evidence_seen"] = self._redactor.redact(submitted["evidence_seen"])[0]
        return kept

    def performed_since(
        self, since_ms: int, *, run_id: str, capability: str | None = "send"
    ) -> list[dict[str, Any]]:
        """The effects that took effect or may have, at or after
        ``since_ms``, under the keys of run ``run_id`` (``<run_id>:<n>``,
        ``<n>`` digits, so a run whose id starts with ``<run_id>:`` is
        another run; nested runs share the run's id), of ``capability``
        (any, when None), oldest first: what a rollback lists as
        ``not_covered`` (§4.4.1). Each entry's ``state`` is ``done``, or
        ``started`` for one whose outcome is unknown (its effect raised, or
        is still running): it may have gone out."""
        with self._lock:
            entries = list(self._entries.values())
        return sorted(
            (
                dict(e)
                for e in entries
                if e["state"] in ("done", "started")
                and e["key"].rpartition(":")[0] == run_id
                and e["at"] >= since_ms
                and (capability is None or e["capability"] == capability)
            ),
            key=lambda e: e["at"],
        )

    # ------------------------------------------------------------------

    def _record(self, entry: dict[str, Any]) -> None:
        if entry["state"] == "cleared":
            self._entries.pop(entry["key"], None)
        else:
            self._entries[entry["key"]] = entry
        if self._path is None:
            return
        line = (json.dumps(entry, sort_keys=True) + "\n").encode()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            self._path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)

    def _load(self) -> None:
        assert self._path is not None
        try:
            fd = os.open(self._path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return
        with os.fdopen(fd, "rb") as f:
            text = f.read(_MAX_LOG_BYTES + 1)
        if len(text) > _MAX_LOG_BYTES:
            raise ValueError(f"idempotency log {self._path} is too large")
        # The last entry per key wins. A torn last line (a crash while it
        # was appended) is skipped and cut off, so that the next entry is
        # appended on a line of its own; one anywhere else is an error. A
        # line that is no entry (_read_entry) is read as one that does not
        # parse.
        chunks = text.split(b"\n")
        offset = 0
        torn_at: int | None = None
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                try:
                    entry = _read_entry(chunk)
                except ValueError as e:
                    if any(c.strip() for c in chunks[i + 1 :]):
                        raise ValueError(
                            f"idempotency log {self._path}: line {i + 1}: {e}"
                        ) from None
                    torn_at = offset
                    break
                if entry.get("state") == "cleared":
                    self._entries.pop(entry["key"], None)
                else:
                    self._entries[entry["key"]] = entry
            offset += len(chunk) + 1
        if torn_at is not None:
            self._repair(torn_at, b"")
        elif text and not text.endswith(b"\n"):
            # A whole entry whose newline was not written: end its line.
            self._repair(len(text), b"\n")

    def _repair(self, length: int, tail: bytes) -> None:
        """Cut the log to ``length`` bytes and append ``tail``."""
        assert self._path is not None
        fd = os.open(self._path, os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.ftruncate(fd, length)
            if tail:
                os.lseek(fd, length, os.SEEK_SET)
                os.write(fd, tail)
            os.fsync(fd)
        finally:
            os.close(fd)
