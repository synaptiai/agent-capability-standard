"""
Evidence Store

Collects and provides access to evidence anchors from tool executions.
Evidence anchors form the provenance chain for grounded decisions.

An anchor is STANDARD v1.2 §6.5's evidence anchor: ``ref``, ``kind`` (one of
:data:`ANCHOR_KINDS` or a vendor kind ``x-...``), and optional
``timestamp``, ``excerpt`` and ``digest``. A store keeps evidence records
(§6.6): an anchor with the context it was recorded in. Every store of this
package implements :class:`EvidenceStoreProtocol`: it appends, never changes
or reorders a kept record, never reuses a ``record_id``, answers queries in
append order, exports JSON Lines, states its durability and whether it is
bounded, counts what it removes, and notifies subscribers
(``acs.evidence_recorded``). It redacts every anchor before keeping it
(§6.7) and keeps a frozen copy, never the caller's object.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import threading
import warnings
from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import FrozenInstanceError, dataclass, field
from datetime import UTC, datetime
from itertools import islice
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .redaction import Redactor

logger = logging.getLogger(__name__)

# Metadata validation constants
_MAX_METADATA_SIZE_BYTES = 1024  # 1KB max per anchor
_MAX_METADATA_DEPTH = 2  # No deeply nested structures
_MAX_KEY_LENGTH = 64  # SEC-008: Maximum metadata key length
_VALID_KEY_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

# SEC-008: Explicit denylist for dangerous metadata keys.
# These keys can cause prototype pollution or class manipulation
# in downstream JSON consumers (JavaScript, Python pickling, etc.).
_DENIED_KEYS: frozenset[str] = frozenset(
    {
        "__proto__",
        "constructor",
        "__class__",
        "__init__",
        "__bases__",
        "__mro__",
        "__subclasses__",
        "__reduce__",
        "__reduce_ex__",
        "__getattr__",
        "__setattr__",
        "__delattr__",
        "__globals__",
        "__builtins__",
        "__import__",
    }
)


def _validate_metadata_key(key: str) -> bool:
    """Check if metadata key is safe.

    SEC-008: Validates against regex pattern, explicit denylist,
    max length, and rejects keys starting with double underscore.
    """
    if len(key) > _MAX_KEY_LENGTH:
        return False
    # Reject all dunder keys (broader than explicit denylist)
    if key.startswith("__"):
        return False
    if key in _DENIED_KEYS:
        return False
    return bool(_VALID_KEY_PATTERN.fullmatch(key))


def _validate_metadata_depth(value: Any, current_depth: int = 0) -> bool:
    """Check if metadata value doesn't exceed max depth."""
    if current_depth > _MAX_METADATA_DEPTH:
        return False
    if isinstance(value, dict):
        return all(
            _validate_metadata_depth(v, current_depth + 1) for v in value.values()
        )
    if isinstance(value, list):
        return all(_validate_metadata_depth(v, current_depth + 1) for v in value)
    return True


def _flatten(value: Any) -> str:
    """A metadata value nested too deep, as JSON text: redacted with the
    default patterns first, while its structure can still be read (a
    header's name/value pair, a secret member), since its text reads only as
    a string (STANDARD v1.2 §6.7). Whole: a cut could keep part of a secret
    that a redactor then no longer recognises, a registered one included;
    the size limit replaces a value too large whole. A value with no JSON
    text (a reference cycle) becomes a marker, not its repr."""
    from .redaction import DEFAULT_REDACTOR

    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
        redacted, _ = DEFAULT_REDACTOR.redact(json.loads(text))
        return json.dumps(redacted, ensure_ascii=False)
    except TypeError, ValueError, RecursionError:
        return "[unserializable]"


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize metadata to prevent injection attacks.

    - Validates key names (alphanumeric + underscore)
    - Limits nesting depth: a deeper value becomes its JSON text,
      redacted first (``_flatten``)
    - Enforces the size limit by replacing the largest values whole
    """
    if not metadata:
        return {}

    sanitized: dict[str, Any] = {}

    for key, value in metadata.items():
        # Skip invalid keys
        if not _validate_metadata_key(str(key)):
            continue

        # Values that are too deeply nested become their (redacted) text
        if not _validate_metadata_depth(value):
            value = _flatten(value)

        sanitized[str(key)] = value

    # Check size and truncate if needed
    try:
        serialized = json.dumps(sanitized, default=str)
        if len(serialized.encode("utf-8")) > _MAX_METADATA_SIZE_BYTES:
            # Truncate by removing largest values until under limit
            while (
                len(json.dumps(sanitized, default=str).encode("utf-8"))
                > _MAX_METADATA_SIZE_BYTES
            ):
                if not sanitized:
                    break
                # Remove the key with largest value
                largest_key = max(
                    sanitized.keys(), key=lambda k: len(str(sanitized[k]))
                )
                sanitized[largest_key] = "[truncated]"
    except (TypeError, ValueError) as e:
        # If serialization fails, return minimal safe metadata
        logger.debug("Metadata serialization failed: %s", e)
        return {"_error": "metadata_serialization_failed"}

    return sanitized


# Priority levels for evidence retention during eviction (SEC-004).
# Higher values = more important = evicted last.
PRIORITY_LOW = 0
PRIORITY_NORMAL = 1
PRIORITY_HIGH = 2
PRIORITY_CRITICAL = 3

ANCHOR_KINDS: tuple[str, ...] = (
    "file",
    "url",
    "tool",
    "log",
    "sensor",
    "human_note",
    "api",
    "record",
)
"""The evidence-anchor kinds of STANDARD v1.2 §6.5; any other kind is a
vendor kind, ``x-`` then a lowercase letter or digit, then lowercase
letters, digits, ``_``, ``.`` or ``-``."""

_VENDOR = re.compile(r"x-[a-z0-9][a-z0-9_.-]*", re.ASCII)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)

LEGACY_KINDS: dict[str, str] = {
    "tool_output": "tool",
    "command": "tool",
    "mutation": "record",
    "coordination": "record",
}
"""The SDK's kinds before Standard 1.2, and the §6.5 kind each now is.
Accepted with a ``DeprecationWarning``."""

COORDINATION_REF_PREFIXES: tuple[str, ...] = (
    "delegation:",
    "sync:",
    "orchestration:",
    "invoke:",
    "inquire:",
)
"""The ref prefixes of coordination evidence (kind ``record``). A new
prefix is added here, in one place: ``record_coordination_evidence``
refuses any other."""

LEGACY_REF_PREFIXES: dict[str, tuple[str, ...]] = {
    "tool_output": ("tool:",),
    "command": ("command:",),
    "mutation": ("mutation:",),
    "coordination": COORDINATION_REF_PREFIXES,
}
"""How a query by a legacy kind is answered: by ref prefix, so it returns
what it returned before Standard 1.2 (``tool`` now covers both ``tool:``
and ``command:`` anchors)."""

# Default priorities by legacy kind (SEC-004): a former mutation anchor
# keeps its high priority.
_LEGACY_PRIORITY: dict[str, int] = {"mutation": PRIORITY_HIGH}

EVIDENCE_EVENT = "acs.evidence_recorded"
"""The ``type`` of the notification a store sends (§6.6)."""


def is_anchor_kind(kind: object) -> bool:
    """Whether ``kind`` is a §6.5 kind: one of :data:`ANCHOR_KINDS` or a
    vendor kind."""
    return isinstance(kind, str) and (
        kind in ANCHOR_KINDS or _VENDOR.fullmatch(kind) is not None
    )


def is_digest(digest: object) -> bool:
    """Whether ``digest`` has §6.5's form: ``sha256:`` and 64 lowercase
    hexadecimal digits."""
    return isinstance(digest, str) and _DIGEST.fullmatch(digest) is not None


def _vendor_kind(kind: str) -> str:
    """A free kind as a vendor kind: lowercased, characters outside
    ``[a-z0-9_.-]`` replaced by ``_``."""
    body = re.sub(r"[^a-z0-9_.-]", "_", kind.lower())
    if not re.match(r"[a-z0-9]", body):
        body = "k" + body
    return f"x-{body}"


def _read_only(value: Any) -> Any:
    """A deep, read-only copy: mappings become ``MappingProxyType``, lists
    and tuples tuples."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: _read_only(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_read_only(v) for v in value)
    return copy.deepcopy(value)


def plain(value: Any) -> Any:
    """JSON data from a read-only copy: mappings become dicts, tuples
    lists."""
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


@dataclass(slots=True)
class EvidenceAnchor:
    """
    A single piece of evidence: a §6.5 evidence anchor.

    Evidence anchors track the provenance of information,
    enabling verification that decisions are grounded in
    actual observations rather than hallucination.

    Attributes:
        ref: Where the evidence is (e.g., "tool:Read:abc123",
            "file:src/main.py"); a non-empty string
        kind: A §6.5 kind (:data:`ANCHOR_KINDS` or ``x-...``). A legacy
            kind (``tool_output``, ``command``, ``mutation``,
            ``coordination``) is mapped with a ``DeprecationWarning``, and
            any other string becomes the vendor kind ``x-<kind>``
        timestamp: When the evidence was captured (ISO-8601), or None
        metadata: Additional context (tool name, file path, etc.). A tool
            call's input is kept only when the caller asks for it; see
            :meth:`from_tool_output`.
        priority: Retention priority (SEC-004). Higher = evicted later.
        excerpt: A short quotation of the evidence; never a secret (§6.7)
        digest: ``sha256:`` and 64 lowercase hex digits of the content as
            read

    A store keeps a frozen copy (:meth:`frozen_copy`): assigning to it, or
    calling :meth:`mark_critical` on it, raises ``FrozenInstanceError``,
    and its metadata is read-only. The caller's own anchor stays mutable.
    """

    ref: str
    kind: str
    timestamp: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int = PRIORITY_NORMAL
    excerpt: str | None = field(default=None, kw_only=True)
    digest: str | None = field(default=None, kw_only=True)
    _frozen: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate the anchor, map a legacy or free kind, and sanitize the
        metadata."""
        if not isinstance(self.ref, str) or not self.ref:
            raise ValueError("an evidence anchor's ref is a non-empty string (§6.5)")
        if self.digest is not None and not is_digest(self.digest):
            raise ValueError(
                f"digest {self.digest!r} is not 'sha256:' and 64 lowercase "
                "hexadecimal digits (§6.5)"
            )
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("an evidence anchor's kind is a non-empty string (§6.5)")
        if not is_anchor_kind(self.kind):
            legacy = self.kind
            canonical = LEGACY_KINDS.get(legacy) or _vendor_kind(legacy)
            warnings.warn(
                f"evidence anchor kind {legacy!r} is deprecated; use {canonical!r} "
                "(STANDARD v1.2 §6.5)",
                DeprecationWarning,
                stacklevel=3,
            )
            if self.priority == PRIORITY_NORMAL:
                self.priority = _LEGACY_PRIORITY.get(legacy, PRIORITY_NORMAL)
            self.kind = canonical
        self.metadata = _sanitize_metadata(plain(self.metadata))

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            frozen = object.__getattribute__(self, "_frozen")
        except AttributeError:
            frozen = False
        if frozen:
            raise FrozenInstanceError(f"cannot assign to field {name!r}")
        object.__setattr__(self, name, value)

    @classmethod
    def from_tool_output(
        cls,
        tool_name: str,
        tool_use_id: str,
        tool_input: dict[str, Any],
        tool_response: Any = None,
        *,
        include_tool_input: bool = False,
        digest: str | None = None,
    ) -> EvidenceAnchor:
        """
        Create an evidence anchor (kind ``tool``) from a tool output.

        The anchor's metadata holds the tool name and whether there was a
        response. The input is left out unless ``include_tool_input`` is
        true: a tool input can hold credentials (a token in a command or a
        header), and an anchor is stored and exported; a store redacts it
        when it is kept (§6.7).

        Args:
            tool_name: Name of the tool (e.g., "Read", "Bash")
            tool_use_id: Unique ID for this tool use
            tool_input: Input parameters to the tool
            tool_response: Optional response data; only its presence is
                recorded
            include_tool_input: Keep ``tool_input`` in the metadata
            digest: The response's digest (§6.5), when the caller computed
                one

        Returns:
            EvidenceAnchor for this tool execution
        """
        metadata: dict[str, Any] = {
            "tool_name": tool_name,
            "has_response": tool_response is not None,
        }
        if include_tool_input:
            metadata["tool_input"] = tool_input
        return cls(
            ref=f"tool:{tool_name}:{tool_use_id}",
            kind="tool",
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata,
            digest=digest,
        )

    @classmethod
    def from_file(
        cls,
        file_path: str,
        file_hash: str | None = None,
        operation: str = "read",
    ) -> EvidenceAnchor:
        """
        Create an evidence anchor (kind ``file``) for a file reference.

        Args:
            file_path: Path to the file
            file_hash: Optional content hash: one of §6.5's form
                (``sha256:...``) becomes the anchor's ``digest``, any other
                is kept in the metadata
            operation: What was done ("read", "write", "edit")

        Returns:
            EvidenceAnchor for this file reference
        """
        digest = file_hash if is_digest(file_hash) else None
        metadata: dict[str, Any] = {"path": file_path, "operation": operation}
        if digest is None:
            metadata["hash"] = file_hash
        return cls(
            ref=f"file:{file_path}",
            kind="file",
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata,
            digest=digest,
        )

    @classmethod
    def from_command(
        cls,
        command: str | None,
        exit_code: int,
        tool_use_id: str | None = None,
    ) -> EvidenceAnchor:
        """
        Create an evidence anchor (kind ``tool``, ref ``command:<id>``) for
        a command execution.

        Args:
            command: The command that was run, kept in the metadata. Pass
                None to record that a command ran without keeping its
                text, which can hold credentials.
            exit_code: Exit code from the command
            tool_use_id: Optional tool use ID

        Returns:
            EvidenceAnchor for this command execution
        """
        ref_id = tool_use_id or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        metadata: dict[str, Any] = {"exit_code": exit_code}
        if command is not None:
            metadata["command"] = command
        return cls(
            ref=f"command:{ref_id}",
            kind="tool",
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata,
        )

    @classmethod
    def from_mutation(
        cls,
        target: str,
        operation: str,
        checkpoint_id: str | None = None,
    ) -> EvidenceAnchor:
        """
        Create an evidence anchor (kind ``record``, ref ``mutation:<target>``)
        for a state mutation: the record of the action, which grounds a
        ``mutate`` output (§3.1).

        Args:
            target: What was mutated (file path, resource ID)
            operation: Type of mutation (write, edit, delete)
            checkpoint_id: Associated checkpoint ID

        Returns:
            EvidenceAnchor for this mutation (priority=HIGH)
        """
        return cls(
            ref=f"mutation:{target}",
            kind="record",
            timestamp=datetime.now(UTC).isoformat(),
            metadata={
                "target": target,
                "operation": operation,
                "checkpoint_id": checkpoint_id,
            },
            priority=PRIORITY_HIGH,
        )

    @classmethod
    def from_checkpoint(cls, checkpoint_id: str) -> EvidenceAnchor:
        """An evidence anchor (kind ``record``, ref ``checkpoint:<id>``) for
        a checkpoint taken: the record that grounds a ``checkpoint`` output
        (§3.1)."""
        return cls(
            ref=f"checkpoint:{checkpoint_id}",
            kind="record",
            timestamp=datetime.now(UTC).isoformat(),
            metadata={"checkpoint_id": checkpoint_id},
            priority=PRIORITY_HIGH,
        )

    @classmethod
    def from_dict(cls, data: Any) -> EvidenceAnchor:
        """An anchor from its §6.5 JSON form. ``ValueError`` for anything
        that is not an evidence anchor: not a mapping, an empty ``ref``, a
        kind outside §6.5's vocabulary (a legacy kind included), a
        ``digest`` that is present and malformed (``null`` included), a
        ``timestamp`` or ``excerpt`` that is not a string."""
        if not isinstance(data, Mapping):
            raise ValueError("an evidence anchor is an object (§6.5)")
        ref, kind = data.get("ref"), data.get("kind")
        if not isinstance(ref, str) or not ref:
            raise ValueError("an evidence anchor's ref is a non-empty string (§6.5)")
        if not is_anchor_kind(kind):
            raise ValueError(f"{kind!r} is not an evidence anchor kind (§6.5)")
        for member in ("timestamp", "excerpt"):
            if data.get(member) is not None and not isinstance(data[member], str):
                raise ValueError(f"an evidence anchor's {member} is a string (§6.5)")
        # A digest that is present has §6.5's form; ``null`` is not one (the
        # core and the TypeScript package read it so too).
        if "digest" in data and not is_digest(data["digest"]):
            raise ValueError(
                f"an evidence anchor's digest is 'sha256:' and 64 lowercase hex "
                f"digits, not {data['digest']!r} (§6.5)"
            )
        metadata = data.get("metadata")
        return cls(
            ref=ref,
            kind=str(kind),
            timestamp=data.get("timestamp"),
            metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
            excerpt=data.get("excerpt"),
            digest=data.get("digest"),
        )

    def to_dict(self) -> dict[str, Any]:
        """The anchor's §6.5 JSON form (without its metadata)."""
        out: dict[str, Any] = {
            "ref": self.ref,
            "kind": self.kind,
            "timestamp": self.timestamp,
        }
        if self.excerpt is not None:
            out["excerpt"] = self.excerpt
        if self.digest is not None:
            out["digest"] = self.digest
        return out

    def frozen_copy(self) -> EvidenceAnchor:
        """A frozen copy: its fields cannot be assigned, and its metadata is
        a read-only deep copy."""
        c = object.__new__(EvidenceAnchor)
        for name in ("ref", "kind", "timestamp", "priority", "excerpt", "digest"):
            object.__setattr__(c, name, getattr(self, name))
        object.__setattr__(c, "metadata", _read_only(self.metadata))
        object.__setattr__(c, "_frozen", True)
        return c

    @property
    def frozen(self) -> bool:
        """Whether this is a store's frozen copy."""
        return self._frozen

    def mark_critical(self) -> None:
        """Mark this anchor as critical for forensic retention.

        SEC-004: Critical anchors are evicted last during capacity pressure.
        Use for evidence that must be preserved for audit/compliance. Call
        it before the anchor is added: a kept anchor is frozen.
        """
        self.priority = PRIORITY_CRITICAL

    def __str__(self) -> str:
        return self.ref


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """An evidence record (STANDARD v1.2 §6.6): a kept anchor with the
    context it was recorded in."""

    record_id: str
    anchor: EvidenceAnchor
    recorded_at: str
    run_id: str | None = None
    frame: tuple[str, ...] | None = None
    step: int | None = None
    capability: str | None = None
    tool: str | None = None
    call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """The ``EvidenceRecord`` JSON of ``schemas/interop/evidence.schema.json``
        (members that do not apply left out; the anchor's metadata as
        ``metadata``)."""
        out: dict[str, Any] = {
            "record_id": self.record_id,
            "anchor": self.anchor.to_dict(),
            "recorded_at": self.recorded_at,
        }
        for name in ("run_id", "frame", "step", "capability", "tool", "call_id"):
            value = getattr(self, name)
            if value is not None:
                out[name] = list(value) if name == "frame" else value
        if self.anchor.metadata:
            out["metadata"] = plain(self.anchor.metadata)
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidenceRecord:
        """A record from its JSON form; ``ValueError`` when it is not one."""
        if not isinstance(data, Mapping):
            raise ValueError("an evidence record is an object (§6.6)")
        record_id, recorded_at = data.get("record_id"), data.get("recorded_at")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("an evidence record's record_id is a non-empty string")
        if not isinstance(recorded_at, str):
            raise ValueError("an evidence record's recorded_at is a string")
        anchor_data = data.get("anchor")
        if isinstance(anchor_data, Mapping) and isinstance(
            data.get("metadata"), Mapping
        ):
            anchor_data = {**anchor_data, "metadata": data["metadata"]}
        anchor = EvidenceAnchor.from_dict(anchor_data).frozen_copy()
        frame = data.get("frame")
        return cls(
            record_id=record_id,
            anchor=anchor,
            recorded_at=recorded_at,
            run_id=data.get("run_id"),
            frame=tuple(frame) if isinstance(frame, list) else None,
            step=data.get("step"),
            capability=data.get("capability"),
            tool=data.get("tool"),
            call_id=data.get("call_id"),
        )


@dataclass(frozen=True, slots=True)
class StoreInfo:
    """What a store states about itself (STANDARD v1.2 §6.6)."""

    durability: str
    bounded: bool
    count: int
    removed: int
    capture_failures: int = 0
    retention: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """The ``StoreInfo`` JSON, with ``x-capture_failures`` and any
        implementation members (``x-...``)."""
        out: dict[str, Any] = {
            "durability": self.durability,
            "bounded": self.bounded,
            "count": self.count,
            "removed": self.removed,
        }
        if self.retention is not None:
            out["retention"] = self.retention
        out["x-capture_failures"] = self.capture_failures
        out.update(self.extra)
        return out


Listener = Callable[[dict[str, Any]], None]
"""A subscriber: called with an ``EvidenceRecorded`` payload (§6.6)."""


@runtime_checkable
class EvidenceStoreProtocol(Protocol):
    """An evidence store (STANDARD v1.2 §6.6)."""

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
        """Keep one anchor (redacted, frozen) as a record; notify once."""
        ...

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
        """Keep several anchors with one context; notify once."""
        ...

    def get(self, record_id: str) -> EvidenceRecord | None:
        """The record with this id, or None."""
        ...

    def records(
        self,
        *,
        capability: str | None = None,
        kind: str | None = None,
        run_id: str | None = None,
    ) -> list[EvidenceRecord]:
        """The records that match every given value, in append order."""
        ...

    def export(self) -> Iterator[dict[str, Any]]:
        """Every record's ``EvidenceRecord`` JSON, in append order (one
        line each of a JSON Lines export)."""
        ...

    def info(self) -> StoreInfo:
        """The store's durability, bound and counts."""
        ...

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener`` after each append; returns the unsubscribe
        function."""
        ...

    def record_capture_failure(self, call_id: str | None, message: str) -> None:
        """Count a capture that failed (§6.4: never silently)."""
        ...


def notification(records: list[EvidenceRecord]) -> dict[str, Any]:
    """The ``EvidenceRecorded`` payload (§6.6) for records appended with one
    context: their ids, their anchors' ``ref``, ``kind`` and ``digest`` (no
    excerpt), the correlation and the time."""
    first = records[0]
    payload: dict[str, Any] = {
        "type": EVIDENCE_EVENT,
        "record_ids": [r.record_id for r in records],
        "anchors": [
            {
                k: v
                for k, v in (
                    ("ref", r.anchor.ref),
                    ("kind", r.anchor.kind),
                    ("digest", r.anchor.digest),
                )
                if v is not None
            }
            for r in records
        ],
        "recorded_at": first.recorded_at,
    }
    for name in ("capability", "run_id", "frame", "step", "tool", "call_id"):
        value = getattr(first, name)
        if value is not None:
            payload[name] = list(value) if name == "frame" else value
    return payload


class _Listeners:
    """Subscribers, called outside the store's lock; one that raises is
    logged and does not reach the appender or the other subscribers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def notify(self, records: list[EvidenceRecord]) -> None:
        if not records:
            return
        with self._lock:
            listeners = list(self._listeners)
        if not listeners:
            return
        payload = notification(records)
        for listener in listeners:
            try:
                listener(copy.deepcopy(payload))
            except Exception:  # noqa: BLE001 - a subscriber never breaks an append
                logger.warning("an evidence subscriber raised", exc_info=True)


def _context(
    capability: str | None,
    run_id: str | None,
    frame: Iterable[str] | None,
    step: int | None,
    tool: str | None,
    call_id: str | None,
) -> dict[str, Any]:
    return {
        "capability": capability,
        "run_id": run_id,
        "frame": tuple(frame) if frame is not None else None,
        "step": step,
        "tool": tool,
        "call_id": call_id,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _default_redactor() -> Redactor:
    from .redaction import DEFAULT_REDACTOR

    return DEFAULT_REDACTOR


def _query_kind(kind: str) -> tuple[str | None, tuple[str, ...] | None]:
    """A kind query: a §6.5 kind reads the kind index; a legacy kind is
    answered by its ref prefixes, and any other (free) kind by the vendor
    kind an anchor made with it now has (``x-<kind>``), each with a
    ``DeprecationWarning``: a query by the kind an anchor was made with
    returns it, as in 1.1."""
    if kind in LEGACY_REF_PREFIXES:
        warnings.warn(
            f"evidence anchor kind {kind!r} is deprecated; the query is answered "
            f"by ref prefix {LEGACY_REF_PREFIXES[kind]} (STANDARD v1.2 §6.5)",
            DeprecationWarning,
            stacklevel=3,
        )
        return None, LEGACY_REF_PREFIXES[kind]
    if isinstance(kind, str) and kind and not is_anchor_kind(kind):
        vendor = _vendor_kind(kind)
        warnings.warn(
            f"evidence anchor kind {kind!r} is deprecated; the query is answered "
            f"by the vendor kind {vendor!r} (STANDARD v1.2 §6.5)",
            DeprecationWarning,
            stacklevel=3,
        )
        return vendor, None
    return kind, None


class EvidenceStore:
    """
    In-memory evidence store (§6.6): durability ``memory``, bounded.

    Collects evidence anchors from tool executions and provides
    methods to query them for provenance and verification.

    SEC-004: Uses priority-aware eviction when max_anchors is exceeded.
    Lower-priority anchors are evicted first; within the same priority,
    oldest anchors are evicted first (FIFO within priority tier). Each
    eviction, and each record :meth:`clear` drops, counts in
    ``info().removed``; record ids (``ev-<n>``) are never reused.

    Every anchor is redacted (``redactor``, §6.7) and kept as a frozen copy:
    what a getter returns cannot be changed, and changing the caller's
    anchor after it was added changes nothing the store holds.

    Example:
        store = EvidenceStore(max_anchors=1000)

        # Add evidence from tool use (the input is not kept unless asked for)
        anchor = EvidenceAnchor.from_tool_output("Read", "abc123", {"path": "/tmp/x"})
        store.append(anchor, capability="retrieve")

        # Query recent evidence
        recent = store.get_recent(5)

        # Get evidence for a capability's output (§6.5 objects)
        anchors = store.evidence_anchors_for("retrieve")
    """

    DEFAULT_MAX_ANCHORS: int = 10000
    DURABILITY = "memory"

    def __init__(
        self,
        max_anchors: int | None = None,
        *,
        redactor: Redactor | None = None,
    ) -> None:
        """
        Initialize the evidence store.

        Args:
            max_anchors: Maximum number of anchors to store (default: 10000).
                        When exceeded, lowest-priority oldest anchors are evicted.
            redactor: Applied to every anchor before it is kept (§6.7);
                the default patterns when None.
        """
        self._max_anchors = (
            max_anchors if max_anchors is not None else self.DEFAULT_MAX_ANCHORS
        )
        self.redactor: Redactor = redactor or _default_redactor()
        self._lock = threading.Lock()
        # Primary ordered store — deque for O(1) append/popleft
        self._anchors: deque[EvidenceAnchor] = deque()

        # Sequence counter: only grows, so a record id is never reused.
        self._seq_counter: int = 0
        self._removed: int = 0
        self._capture_failures: int = 0

        # Bidirectional mappings: anchor identity <-> seq_id
        self._anchor_to_seq: dict[int, int] = {}  # id(anchor) -> seq_id
        self._seq_to_anchor: dict[int, EvidenceAnchor] = {}  # seq_id -> anchor
        self._records: dict[int, EvidenceRecord] = {}  # seq_id -> record

        # Priority buckets: priority level -> deque of seq_ids (insertion order)
        self._priority_buckets: dict[int, deque[int]] = defaultdict(deque)
        self._seq_to_priority: dict[int, int] = {}  # seq_id -> priority (reverse)

        # Secondary indexes keyed by seq_id for O(1) removal
        self._by_kind: dict[str, dict[int, EvidenceAnchor]] = defaultdict(dict)
        self._by_capability: dict[str, dict[int, EvidenceAnchor]] = defaultdict(dict)
        self._listeners = _Listeners()

    # ── §6.6 interface ──

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
        """Keep ``anchor`` (redacted, frozen) as a record; notify once."""
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
        """Keep several anchors with one context; one notification."""
        context = _context(capability, run_id, frame, step, tool, call_id)
        kept = [self.redactor.redact_anchor(a).frozen_copy() for a in anchors]
        out: list[EvidenceRecord] = []
        with self._lock:
            for anchor in kept:
                out.append(self._keep(anchor, context))
        self._listeners.notify(out)
        return out

    def _keep(self, anchor: EvidenceAnchor, context: dict[str, Any]) -> EvidenceRecord:
        """Index one kept anchor. Must be called with ``self._lock`` held."""
        if len(self._anchors) >= self._max_anchors:
            self._evict_lowest_priority()
        seq_id = self._seq_counter
        self._seq_counter += 1
        record = EvidenceRecord(
            record_id=f"ev-{seq_id}", anchor=anchor, recorded_at=_now(), **context
        )
        self._anchors.append(anchor)
        self._anchor_to_seq[id(anchor)] = seq_id
        self._seq_to_anchor[seq_id] = anchor
        self._records[seq_id] = record
        self._priority_buckets[anchor.priority].append(seq_id)
        self._seq_to_priority[seq_id] = anchor.priority
        self._by_kind[anchor.kind][seq_id] = anchor
        if context["capability"]:
            self._by_capability[context["capability"]][seq_id] = anchor
        return record

    def get(self, record_id: str) -> EvidenceRecord | None:
        """The record with ``record_id``, or None (also once removed)."""
        if not record_id.startswith("ev-") or not record_id[3:].isdigit():
            return None
        with self._lock:
            return self._records.get(int(record_id[3:]))

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
        with self._lock:
            return [
                r
                for r in self._records.values()
                if (capability is None or r.capability == capability)
                and (run_id is None or r.run_id == run_id)
                and (canonical is None or r.anchor.kind == canonical)
                and (prefixes is None or r.anchor.ref.startswith(prefixes))
            ]

    def export(self) -> Iterator[dict[str, Any]]:
        """Every record's ``EvidenceRecord`` JSON, in append order."""
        with self._lock:
            records = list(self._records.values())
        return (r.to_dict() for r in records)

    def info(self) -> StoreInfo:
        """Durability ``memory``, bounded, with the counts."""
        with self._lock:
            return StoreInfo(
                durability=self.DURABILITY,
                bounded=True,
                count=len(self._records),
                removed=self._removed,
                capture_failures=self._capture_failures,
            )

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener`` with an ``EvidenceRecorded`` payload after each
        append, outside the store's lock; returns the unsubscribe function."""
        return self._listeners.subscribe(listener)

    def record_capture_failure(self, call_id: str | None, message: str) -> None:
        """Count a capture that failed and log it (§6.4: never silently)."""
        with self._lock:
            self._capture_failures += 1
        logger.warning("evidence capture failed (call %s): %s", call_id, message)

    # ── 1.1 interface ──

    def add_anchor(
        self,
        anchor: EvidenceAnchor,
        capability_id: str | None = None,
    ) -> EvidenceRecord:
        """
        Add an evidence anchor to the store: :meth:`append` with
        ``capability``.

        SEC-004: If max_anchors is exceeded, evicts the lowest-priority
        oldest anchor rather than blindly dropping the oldest.

        Args:
            anchor: The evidence anchor to add
            capability_id: Optional capability ID to associate with

        Returns:
            The record kept
        """
        return self.append(anchor, capability=capability_id)

    def _evict_lowest_priority(self) -> None:
        """SEC-004: Evict the lowest-priority, oldest anchor from the store.

        Must be called with ``self._lock`` held.

        O(1) amortized: finds the lowest non-empty priority bucket, pops
        the leftmost (oldest) seq_id, then removes from all indexes via
        dict deletes.
        """
        if not self._anchors:
            return

        # Find lowest non-empty priority bucket (iterate from LOW upward)
        victim_seq: int | None = None
        for priority in (
            PRIORITY_LOW,
            PRIORITY_NORMAL,
            PRIORITY_HIGH,
            PRIORITY_CRITICAL,
        ):
            bucket = self._priority_buckets.get(priority)
            if bucket:
                victim_seq = bucket.popleft()
                break

        if victim_seq is None:
            return  # pragma: no cover — defensive

        victim = self._seq_to_anchor[victim_seq]

        # Remove from seq bookkeeping
        self._remove_from_indexes(victim_seq, victim)
        self._removed += 1

        # Remove from primary deque
        # Common case: victim is leftmost (oldest in its priority, and that
        # priority is the lowest), so popleft is O(1).
        if self._anchors[0] is victim:
            self._anchors.popleft()
        else:
            # Rare case: victim is not at head (higher-priority items precede it).
            # Linear scan is unavoidable for deque mid-removal but rare in practice.
            for i, a in enumerate(self._anchors):
                if a is victim:
                    del self._anchors[i]
                    break

    def _remove_from_indexes(self, seq_id: int, anchor: EvidenceAnchor) -> None:
        """Remove an anchor from all secondary indexes by seq_id (O(1) per index)."""
        # Remove from seq <-> anchor mappings
        self._anchor_to_seq.pop(id(anchor), None)
        self._seq_to_anchor.pop(seq_id, None)
        self._seq_to_priority.pop(seq_id, None)
        self._records.pop(seq_id, None)

        # Remove from kind index
        kind_dict = self._by_kind.get(anchor.kind)
        if kind_dict is not None:
            kind_dict.pop(seq_id, None)

        # Remove from capability indexes
        for cap_dict in self._by_capability.values():
            if seq_id in cap_dict:
                del cap_dict[seq_id]
                break  # Anchor can only be in one capability dict

    def get_recent(self, n: int = 10) -> list[str]:
        """
        Get references for the N most recent evidence anchors.

        Args:
            n: Number of anchors to return

        Returns:
            List of evidence reference strings
        """
        with self._lock:
            start_idx = max(0, len(self._anchors) - n)
            return [anchor.ref for anchor in islice(self._anchors, start_idx, None)]

    def get_recent_anchors(self, n: int = 10) -> list[EvidenceAnchor]:
        """
        Get the N most recent evidence anchors (frozen copies).

        Args:
            n: Number of anchors to return

        Returns:
            List of EvidenceAnchor objects
        """
        with self._lock:
            start_idx = max(0, len(self._anchors) - n)
            return list(islice(self._anchors, start_idx, None))

    def get_by_kind(self, kind: str) -> list[EvidenceAnchor]:
        """
        Get all evidence anchors of a kind. A §6.5 kind reads the kind
        index; a legacy kind (``tool_output``, ``command``, ``mutation``,
        ``coordination``) returns, with a ``DeprecationWarning``, what it
        returned before Standard 1.2: the anchors whose ref starts with its
        prefixes.

        Args:
            kind: Evidence kind

        Returns:
            List of matching anchors, in append order
        """
        canonical, prefixes = _query_kind(kind)
        with self._lock:
            if prefixes is not None:
                return [a for a in self._anchors if a.ref.startswith(prefixes)]
            return list(self._by_kind.get(canonical or kind, {}).values())

    def get_for_capability(self, capability_id: str) -> list[EvidenceAnchor]:
        """
        Get evidence anchors associated with a capability.

        Args:
            capability_id: Capability ID from the ontology

        Returns:
            List of associated anchors
        """
        with self._lock:
            return list(self._by_capability.get(capability_id, {}).values())

    def evidence_anchors_for(self, capability_id: str) -> list[dict[str, Any]]:
        """The §6.5 objects of the anchors associated with a capability: an
        output's ``evidence_anchors``."""
        return [a.to_dict() for a in self.get_for_capability(capability_id)]

    def get_for_capability_output(self, capability_id: str) -> list[str]:
        """
        Get evidence references for a capability's outputs.

        Deprecated: bare strings are the legacy form of an output's
        ``evidence_anchors`` (§6.5); use :meth:`evidence_anchors_for`.

        Args:
            capability_id: Capability ID from the ontology

        Returns:
            List of evidence reference strings
        """
        warnings.warn(
            "get_for_capability_output returns bare refs, the deprecated form of "
            "evidence_anchors (STANDARD v1.2 §6.5); use evidence_anchors_for",
            DeprecationWarning,
            stacklevel=2,
        )
        return [anchor.ref for anchor in self.get_for_capability(capability_id)]

    def get_mutations(self) -> list[EvidenceAnchor]:
        """Get all mutation evidence anchors (refs ``mutation:``)."""
        return self.search_by_ref_prefix("mutation:")

    def get_tool_outputs(self) -> list[EvidenceAnchor]:
        """Get all tool output evidence anchors (refs ``tool:``)."""
        return self.search_by_ref_prefix("tool:")

    def search_by_ref_prefix(self, prefix: str) -> list[EvidenceAnchor]:
        """
        Search for evidence anchors by reference prefix.

        Args:
            prefix: Reference prefix to match (e.g., "tool:Read", "file:")

        Returns:
            List of matching anchors
        """
        with self._lock:
            return [a for a in self._anchors if a.ref.startswith(prefix)]

    def search_by_metadata(
        self,
        key: str,
        value: Any,
    ) -> list[EvidenceAnchor]:
        """
        Search for evidence anchors by metadata key-value.

        Args:
            key: Metadata key to match
            value: Value to match

        Returns:
            List of matching anchors
        """
        with self._lock:
            return [a for a in self._anchors if a.metadata.get(key) == value]

    def clear(self) -> None:
        """Clear all evidence from the store. The cleared records count as
        removed, and record ids are not reused."""
        with self._lock:
            self._removed += len(self._records)
            self._anchors.clear()
            self._anchor_to_seq.clear()
            self._seq_to_anchor.clear()
            self._records.clear()
            self._priority_buckets.clear()
            self._seq_to_priority.clear()
            self._by_kind.clear()
            self._by_capability.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._anchors)

    def __iter__(self) -> Iterator[EvidenceAnchor]:
        with self._lock:
            return iter(list(self._anchors))

    def to_list(self) -> list[dict[str, Any]]:
        """
        Export all evidence as a list of dicts.

        Returns:
            List of anchor dictionaries
        """
        with self._lock:
            return [
                {**a.to_dict(), "metadata": plain(a.metadata)} for a in self._anchors
            ]
