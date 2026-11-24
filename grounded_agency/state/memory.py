"""
A memory store for ``persist`` and ``recall`` (STANDARD v1.2 §4.5).

Entries live in a **scope**, which says who can read them and how long they
last: ``run`` (the run the host started, one ``run_id``, and every run
nested in it), ``session``, ``user``, ``project`` and ``global``. One key in
two scopes names two entries; keys compare by code point. ``stored: true``
means a later ``recall`` of the key in the scope returns the data (an I-JSON
round trip) until the entry ends: by its ``ttl``, when its scope ends, or
under the host's retention. Data or a key that holds a secret is refused
(``secret_in_data``, §6.7), and nothing is stored.

:class:`MemoryStore` passes the vectors in ``tests/conformance/memory/
store.json`` for every scope it provides. Without a ``path`` it keeps
entries in memory, and none survives a restart; with one, every change is
written atomically to that file (0600), and entries in every scope survive a
restart (:meth:`MemoryStore.statement` says which).
"""

from __future__ import annotations

import copy
import json
import math
import os
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .. import _core
from .redaction import DEFAULT_REDACTOR, Redactor

SCOPES: tuple[str, ...] = ("run", "session", "user", "project", "global")

_MAX_INT = 2**53
_MAX_FILE_BYTES = 256 * 1024 * 1024
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# The last instant a date-time states, 9999-12-31T23:59:59.999Z, in
# milliseconds since the Unix epoch: no entry ends later (§4.5).
MAX_EXPIRES_MS = 253_402_300_799_999


class MemoryError(Exception):  # noqa: A001 - exported as MemoryStoreError
    """A refused ``persist`` or ``recall`` (§4.5): ``reason`` is the §5.19.7
    token a host answers with (``unsupported_scope``, ``unsupported_ttl``,
    ``over_capacity``, ``secret_in_data``). The message never repeats a
    secret."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True, slots=True)
class MemoryContext:
    """Who is asking: the instance of each scope the call belongs to. ``run``
    is the action's ``run_id`` (every frame of a run shares it), so the
    ``run`` scope is the run the host started and every run nested in it."""

    run: str | None = None
    session: str | None = None
    user: str | None = None
    project: str | None = None


def _iso(ms: int) -> str:
    # Exact: integer milliseconds, no float rounding at the range's ends.
    return (
        (_EPOCH + timedelta(milliseconds=ms))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _ijson_problem(value: Any, at: str = "") -> str | None:
    """Why ``value`` is not I-JSON (RFC 7493), if it is not."""
    if value is None or isinstance(value, (bool, str)):
        return None
    if isinstance(value, int):
        return (
            None if abs(value) <= _MAX_INT else f"{at or '/'}: an integer beyond 2^53"
        )
    if isinstance(value, float):
        return None if math.isfinite(value) else f"{at or '/'}: not a finite number"
    if isinstance(value, list):
        for i, v in enumerate(value):
            if p := _ijson_problem(v, f"{at}/{i}"):
                return p
        return None
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                return f"{at or '/'}: a member name that is not a string"
            if p := _ijson_problem(v, f"{at}/{k}"):
                return p
        return None
    return f"{at or '/'}: a {type(value).__name__}, which JSON has no form for"


class MemoryStore:
    """A memory host's store (§4.5): ``persist`` and ``recall`` on inputs as
    the capabilities take them, in the scope instances a
    :class:`MemoryContext` names.

    ``scopes``: the scopes this store provides (any of :data:`SCOPES`, and
    ``x-`` names); ``default_scope``: the one used when a call names none.
    ``max_value_bytes``: the largest value, as the UTF-8 length of its
    canonical JSON; ``max_entries``: the most entries kept. ``clock``:
    milliseconds since the Unix epoch. ``redactor``: what recognises a
    secret (S4's default patterns and registered values).
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        scopes: Sequence[str] = SCOPES,
        default_scope: str = "session",
        max_value_bytes: int = 1_000_000,
        max_entries: int = 100_000,
        clock: Callable[[], int] | None = None,
        redactor: Redactor = DEFAULT_REDACTOR,
    ) -> None:
        if default_scope not in scopes:
            raise ValueError(f"default scope {default_scope!r} is not one of {scopes}")
        self._path = Path(path) if path is not None else None
        self._scopes = tuple(scopes)
        self._default = default_scope
        self._max_value_bytes = max_value_bytes
        self._max_entries = max_entries
        self._clock: Callable[[], int] = clock or (lambda: time.time_ns() // 1_000_000)
        self._redactor = redactor
        self._lock = threading.Lock()
        # (scope, instance, key) -> {data, stored_at, expires_at}
        self._entries: dict[tuple[str, str, str], dict[str, Any]] = {}
        if self._path is not None:
            self._load()

    @property
    def path(self) -> Path | None:
        """The file entries are kept in, or None (in memory)."""
        return self._path

    @property
    def redactor(self) -> Redactor:
        """What recognises a secret, which a ``persist`` may not store."""
        return self._redactor

    @redactor.setter
    def redactor(self, redactor: Redactor) -> None:
        self._redactor = redactor

    @property
    def default_scope(self) -> str:
        return self._default

    def statement(self) -> dict[str, Any]:
        """What this host states for each scope it provides (§4.5): whether
        entries survive a restart, its retention and its limits."""
        durable = self._path is not None
        return {
            "default_scope": self._default,
            "scopes": {
                s: {
                    "survives_restart": durable,
                    "retention": "until the entry expires or its scope ends"
                    if s in ("run", "session")
                    else "until the entry expires",
                }
                for s in self._scopes
            },
            "limits": {
                "max_value_bytes": self._max_value_bytes,
                "max_entries": self._max_entries,
            },
        }

    # ------------------------------------------------------------------

    def _scope(self, inputs: Mapping[str, Any], ctx: MemoryContext) -> tuple[str, str]:
        scope = inputs.get("scope")
        if scope is None:
            scope = self._default
        if not isinstance(scope, str) or scope not in self._scopes:
            raise MemoryError(
                "unsupported_scope",
                f"this host does not provide the memory scope {scope!r}; it "
                f"provides {', '.join(self._scopes)} (STANDARD §4.5)",
            )
        instance = {
            "run": ctx.run,
            "session": ctx.session,
            "user": ctx.user,
            "project": ctx.project,
            "global": "",
        }.get(scope, "")
        if instance is None:
            raise MemoryError(
                "unsupported_scope",
                f"the call names no {scope} for the memory scope {scope!r} (STANDARD §4.5)",
            )
        return scope, instance

    def persist(self, inputs: Mapping[str, Any], ctx: MemoryContext) -> dict[str, Any]:
        """Store a copy of ``inputs["data"]`` under ``inputs["key"]``
        (generated when absent) in the scope; the ``persist`` capability's
        output. Raises :class:`MemoryError` and stores nothing on a
        refusal, a ``ttl`` that would end the entry after
        9999-12-31T23:59:59.999Z included (``unsupported_ttl``)."""
        data = inputs.get("data")
        key = inputs.get("key")
        if key is not None and not isinstance(key, str):
            raise MemoryError("x-invalid-key", "key must be a string")
        # Secrets first (§4.5, §6.7): the message names where, not what. The
        # refusal rule decides; redaction only names where, and a credential
        # it does not replace (a private key's header with no body after it)
        # is refused all the same.
        held = self._redactor.holds_credential(data)
        pointers = [p or "/" for p in self._redactor.redact(data)[1]] if held else []
        key_hit = key is not None and self._redactor.holds_credential(key)
        if held or key_hit:
            where = ", ".join(pointers + (["the key"] if key_hit else []))
            raise MemoryError(
                "secret_in_data",
                f"the data holds what looks like a secret at {where or 'the data'}; "
                "store a reference to where the secret is kept, not the secret "
                "(STANDARD §4.5, §6.7)",
            )
        scope, instance = self._scope(inputs, ctx)
        ttl = inputs.get("ttl")
        ttl_ms: int | None = None
        if ttl is not None:
            try:
                ttl_ms = _core.duration_ms(ttl) if isinstance(ttl, str) else None
            except ValueError:
                ttl_ms = None
            if not ttl_ms:
                raise MemoryError(
                    "unsupported_ttl",
                    f"ttl {ttl!r} is not a duration longer than zero (STANDARD §4.5, §5.10.1)",
                )
        if problem := _ijson_problem(data):
            raise MemoryError("x-not-i-json", f"the data is not I-JSON: {problem}")
        size = len(_core.canonical_json(data).encode())
        if size > self._max_value_bytes:
            raise MemoryError(
                "over_capacity",
                f"the value is {size} bytes; this host stores at most "
                f"{self._max_value_bytes} bytes per value (STANDARD §4.5)",
            )
        now = self._clock()
        expires_at = now + ttl_ms if ttl_ms is not None else None
        if expires_at is not None and expires_at > MAX_EXPIRES_MS:
            raise MemoryError(
                "unsupported_ttl",
                f"ttl {ttl!r} would end the entry after 9999-12-31T23:59:59.999Z, "
                "the last instant a date-time states (STANDARD §4.5)",
            )
        with self._lock:
            self._drop_expired(now)
            entry_key = (scope, instance, key if key is not None else uuid.uuid4().hex)
            if (
                entry_key not in self._entries
                and len(self._entries) >= self._max_entries
            ):
                raise MemoryError(
                    "over_capacity",
                    f"this host keeps at most {self._max_entries} entries (STANDARD §4.5)",
                )
            # A copy: what the caller does with its value later does not
            # change what a recall returns (§4.5).
            entry: dict[str, Any] = {"data": copy.deepcopy(data), "stored_at": now}
            if expires_at is not None:
                entry["expires_at"] = expires_at
            self._entries[entry_key] = entry
            self._save()
        out: dict[str, Any] = {
            "stored": True,
            "key": entry_key[2],
            "scope": scope,
            "stored_at": _iso(now),
            "timestamp": _iso(now),
            "evidence_anchors": [
                {"ref": f"memory:{scope}:{entry_key[2]}", "kind": "record"}
            ],
        }
        if expires_at is not None:
            out["expires_at"] = _iso(expires_at)
        return out

    def recall(self, inputs: Mapping[str, Any], ctx: MemoryContext) -> dict[str, Any]:
        """Read ``inputs["key"]`` in the scope; the ``recall`` capability's
        output: ``found`` true with the entry's data, or false with the
        ``default`` (or null)."""
        key = inputs.get("key")
        if not isinstance(key, str):
            raise MemoryError("x-invalid-key", "key must be a string")
        scope, instance = self._scope(inputs, ctx)
        now = self._clock()
        with self._lock:
            if self._drop_expired(now):
                self._save()
            entry = self._entries.get((scope, instance, key))
        if entry is None:
            return {
                "data": inputs.get("default"),
                "found": False,
                "scope": scope,
                "evidence_anchors": [],
            }
        out: dict[str, Any] = {
            # A copy: a change to it does not change the entry.
            "data": copy.deepcopy(entry["data"]),
            "found": True,
            "scope": scope,
            "stored_at": _iso(entry["stored_at"]),
            "evidence_anchors": [{"ref": f"memory:{scope}:{key}", "kind": "record"}],
        }
        if "expires_at" in entry:
            out["expires_at"] = _iso(entry["expires_at"])
        return out

    def end_scope(self, scope: str, instance: str) -> int:
        """End one instance of a scope (the run ended, the session closed):
        its entries end. Returns how many did."""
        with self._lock:
            gone = [k for k in self._entries if k[0] == scope and k[1] == instance]
            for k in gone:
                del self._entries[k]
            if gone:
                self._save()
        return len(gone)

    def _drop_expired(self, now: int) -> bool:
        gone = [
            k
            for k, e in self._entries.items()
            if "expires_at" in e and e["expires_at"] <= now
        ]
        for k in gone:
            del self._entries[k]
        return bool(gone)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        if self._path is None:
            return
        rows = [
            {"scope": s, "instance": i, "key": k, **e}
            for (s, i, k), e in self._entries.items()
        ]
        text = json.dumps({"version": 1, "entries": rows}, sort_keys=True).encode()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.{os.getpid()}.tmp")
        fd = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)

    def _load(self) -> None:
        assert self._path is not None
        try:
            fd = os.open(self._path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return
        with os.fdopen(fd, "rb") as f:
            text = f.read(_MAX_FILE_BYTES + 1)
        if len(text) > _MAX_FILE_BYTES:
            raise ValueError(f"memory file {self._path} is too large")
        value = json.loads(text)
        for row in value.get("entries", []):
            entry = {"data": row["data"], "stored_at": int(row["stored_at"])}
            if row.get("expires_at") is not None:
                entry["expires_at"] = int(row["expires_at"])
            self._entries[(row["scope"], row["instance"], row["key"])] = entry
