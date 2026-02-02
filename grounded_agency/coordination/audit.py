"""
Coordination Audit Log

Append-only audit trail for multi-agent coordination events.
Records delegation, synchronization, evidence sharing, and task completion
events with full provenance for post-hoc analysis.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Default maximum events retained in memory
DEFAULT_MAX_EVENTS = 10000


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
    """

    event_id: str
    event_type: str
    source_agent_id: str
    target_agent_ids: tuple[str, ...]
    capability_id: str
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_agent_id": self.source_agent_id,
            "target_agent_ids": list(self.target_agent_ids),
            "capability_id": self.capability_id,
            "timestamp": self.timestamp,
            "details": dict(self.details),
            "evidence_refs": list(self.evidence_refs),
        }


class CoordinationAuditLog:
    """Append-only, bounded audit log for coordination events.

    Thread-safe via ``threading.Lock()``.  Uses ``collections.deque``
    with a max length so memory stays bounded — oldest events are
    silently dropped when the limit is reached.
    """

    def __init__(self, max_events: int = DEFAULT_MAX_EVENTS) -> None:
        self._max_events = max_events
        self._events: deque[CoordinationEvent] = deque(maxlen=max_events)
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
        details: dict[str, Any] | None = None,
        evidence_refs: list[str] | tuple[str, ...] | None = None,
    ) -> CoordinationEvent:
        """Create and append a new audit event.

        Returns the recorded ``CoordinationEvent`` so callers can
        reference its ``event_id`` if needed.
        """
        event = CoordinationEvent(
            event_id=os.urandom(16).hex(),
            event_type=event_type,
            source_agent_id=source_agent_id,
            target_agent_ids=tuple(target_agent_ids),
            capability_id=capability_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=dict(details) if details else {},
            evidence_refs=tuple(evidence_refs) if evidence_refs else (),
        )
        with self._lock:
            self._events.append(event)
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
                if e.source_agent_id == agent_id
                or agent_id in e.target_agent_ids
            ]

    def get_events_by_type(self, event_type: str) -> list[CoordinationEvent]:
        """Return events matching the given type."""
        with self._lock:
            return [e for e in self._events if e.event_type == event_type]

    def get_events_for_task(self, task_id: str) -> list[CoordinationEvent]:
        """Return events whose details contain the given task_id."""
        with self._lock:
            return [
                e
                for e in self._events
                if e.details.get("task_id") == task_id
            ]

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize all events to a list of dicts."""
        with self._lock:
            return [e.to_dict() for e in self._events]

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
