"""
Coordination Audit Log

Append-only audit trail for multi-agent coordination events.
Records delegation, synchronization, evidence sharing, and task completion
events with full provenance for post-hoc analysis.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import types
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..state.redaction import DEFAULT_REDACTOR, Redactor

logger = logging.getLogger(__name__)

# Default maximum events retained in memory
DEFAULT_MAX_EVENTS = 10000

# Who writes the action records this log exports (STANDARD v1.2 §6.4).
RECORDED_BY = {"name": "grounded_agency.coordination"}


@dataclass(frozen=True, slots=True)
class CoordinationEvent:
    """A single coordination event in the audit trail.

    Frozen to ensure immutability once recorded — audit entries
    must never be modified after creation.

    Attributes:
        event_id: Unique identifier (128-bit hex from os.urandom).
        event_type: Category of event (delegation, synchronization,
                    evidence_share, task_complete).
        source_agent_id: Agent that initiated the event.
        target_agent_ids: Agents affected by the event.
        capability_id: Ontology capability involved (if any).
        timestamp: ISO 8601 UTC timestamp.
        details: Free-form event-specific data.
        evidence_refs: Evidence anchor refs associated with this event.
        intent: What the event records, as its audit record's ``intent``
                (an ``audit`` step's event type, say); empty for the
                event type.
    """

    event_id: str
    event_type: str
    source_agent_id: str
    target_agent_ids: tuple[str, ...]
    capability_id: str
    timestamp: str
    details: types.MappingProxyType[str, Any] = field(
        default_factory=lambda: types.MappingProxyType({})
    )
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    intent: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        out: dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_agent_id": self.source_agent_id,
            "target_agent_ids": list(self.target_agent_ids),
            "capability_id": self.capability_id,
            "timestamp": self.timestamp,
            "details": dict(self.details),
            "evidence_refs": list(self.evidence_refs),
        }
        if self.intent:
            out["intent"] = self.intent
        return out

    def to_action_record(
        self, recorded_by: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """The event as an audit record (STANDARD v1.2 §6.4): an action
        record of this log's own. The event's ``details`` stay under
        ``details``, with the log's own members (``source_agent_id``,
        ``target_agent_ids``, ``evidence_refs``) written last, so a detail
        cannot replace them; nothing in ``details`` becomes a member of the
        record. Its ``intent`` is the event's, else the event type, so the
        record is the same whenever it is given; ``recorded_by`` defaults to
        this log."""
        record: dict[str, Any] = {
            "action_id": self.event_id,
            "timestamp": self.timestamp,
            "actor": "agent",
            "intent": self.intent or self.event_type,
            "status": "executed",
        }
        if self.capability_id:
            record["capability"] = self.capability_id
        record["details"] = {
            **dict(self.details),
            "source_agent_id": self.source_agent_id,
            "target_agent_ids": list(self.target_agent_ids),
            "evidence_refs": list(self.evidence_refs),
        }
        record["recorded_by"] = dict(recorded_by or RECORDED_BY)
        return record


class CoordinationAuditLog:
    """Append-only, bounded audit log for coordination events.

    Lock order: 6 (lowest priority -- acquired last).

    Thread-safe via ``threading.Lock()``.  Uses ``collections.deque``
    with a max length so memory stays bounded — oldest events are
    silently dropped when the limit is reached.

    Every event's ``details`` pass through ``redactor`` before the event is
    kept: a secret never enters an audit record (STANDARD v1.2 §6.7).
    """

    STORE_INFO: types.MappingProxyType[str, str] = types.MappingProxyType(
        {"name": "grounded_agency.coordination.audit_log", "durability": "memory"}
    )
    """The ``store`` an ``audit`` step reports (§6.3): the log is held in
    memory, bounded by ``max_events``, and keeps no retention of its own."""

    def __init__(
        self,
        max_events: int = DEFAULT_MAX_EVENTS,
        *,
        redactor: Redactor | None = None,
    ) -> None:
        self.redactor: Redactor = redactor or DEFAULT_REDACTOR
        self._max_events = max_events
        self._events: deque[CoordinationEvent] = deque(maxlen=max_events)
        self._total_recorded: int = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        event_type: str,
        source_agent_id: str,
        target_agent_ids: list[str] | tuple[str, ...],
        capability_id: str = "",
        details: dict[str, Any] | types.MappingProxyType[str, Any] | None = None,
        evidence_refs: list[str] | tuple[str, ...] | None = None,
        intent: str = "",
    ) -> CoordinationEvent:
        """Create and append a new audit event. ``intent`` is its audit
        record's ``intent``, when not the event type. ``details`` are
        redacted (§6.7) before the event is kept.

        Returns the recorded ``CoordinationEvent`` so callers can
        reference its ``event_id`` if needed.
        """
        kept_details: Any = (
            json.loads(json.dumps(details, default=str)) if details else {}
        )
        kept_details, _ = self.redactor.redact(kept_details)
        event = CoordinationEvent(
            event_id=os.urandom(16).hex(),
            event_type=event_type,
            source_agent_id=source_agent_id,
            target_agent_ids=tuple(target_agent_ids),
            capability_id=capability_id,
            timestamp=datetime.now(UTC).isoformat(),
            details=types.MappingProxyType(kept_details),
            evidence_refs=tuple(evidence_refs) if evidence_refs else (),
            intent=intent,
        )
        with self._lock:
            self._events.append(event)
            self._total_recorded += 1
        logger.debug(
            "Audit: %s from %s -> %s [%s]",
            event_type,
            source_agent_id,
            target_agent_ids,
            event.event_id[:8],
        )
        return event

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_events(self) -> list[CoordinationEvent]:
        """Return all events in insertion order."""
        with self._lock:
            return list(self._events)

    def get_events_for_agent(self, agent_id: str) -> list[CoordinationEvent]:
        """Return events where *agent_id* is source or target."""
        with self._lock:
            return [
                e
                for e in self._events
                if e.source_agent_id == agent_id or agent_id in e.target_agent_ids
            ]

    def get_events_by_type(self, event_type: str) -> list[CoordinationEvent]:
        """Return events matching the given type."""
        with self._lock:
            return [e for e in self._events if e.event_type == event_type]

    def get_events_for_task(self, task_id: str) -> list[CoordinationEvent]:
        """Return events whose details contain the given task_id."""
        with self._lock:
            return [e for e in self._events if e.details.get("task_id") == task_id]

    def get_events_since(self, start_index: int) -> list[CoordinationEvent]:
        """Return events added at or after *start_index* (0-based).

        The *start_index* is an absolute insertion index (total events
        ever recorded), so it remains correct even after older events
        have been evicted from the bounded deque.
        """
        with self._lock:
            evicted = self._total_recorded - len(self._events)
            offset = max(start_index - evicted, 0)
            return list(self._events)[offset:]

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize all events to a list of dicts."""
        with self._lock:
            return [e.to_dict() for e in self._events]

    def export_action_records(self) -> list[dict[str, Any]]:
        """Every event as an audit record, an action record of this log's
        own (STANDARD v1.2 §6.4): the log keeps its own form internally and
        gives its records in the canonical shape."""
        with self._lock:
            return [e.to_action_record() for e in self._events]

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
