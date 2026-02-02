"""
Synchronization Primitives

Barrier-based state agreement between agents.  Participants contribute
state proposals which are merged using a configurable strategy.
"""

from __future__ import annotations

import enum
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..state.evidence_store import EvidenceAnchor, EvidenceStore
from .audit import CoordinationAuditLog

logger = logging.getLogger(__name__)


class SyncStrategy(str, enum.Enum):
    """Supported merge strategies for barrier resolution."""

    LAST_WRITER_WINS = "last_writer_wins"
    MERGE_KEYS = "merge_keys"
    REQUIRE_UNANIMOUS = "require_unanimous"


_VALID_STRATEGIES = frozenset(SyncStrategy)


@dataclass(slots=True)
class SyncBarrier:
    """A synchronization barrier waiting for participant agreement.

    Attributes:
        barrier_id: Unique identifier (128-bit hex).
        participants: Agent IDs that must contribute.
        required_state: Keys/structure that proposals must contain.
        timeout_seconds: Maximum wait (informational; not enforced in-process).
        created_at: ISO 8601 UTC timestamp.
        proposals: Mapping from agent_id to their state proposal.
    """

    barrier_id: str
    participants: frozenset[str]
    required_state: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 60.0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    proposals: dict[str, dict[str, Any]] = field(default_factory=dict)
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        return {
            "barrier_id": self.barrier_id,
            "participants": sorted(self.participants),
            "required_state": dict(self.required_state),
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "proposals": {k: dict(v) for k, v in self.proposals.items()},
            "resolved": self.resolved,
        }


@dataclass(slots=True)
class SyncResult:
    """Outcome of barrier resolution.

    Attributes:
        barrier_id: Which barrier was resolved.
        synchronized: Whether agreement was reached.
        agreed_state: Merged state (empty if not synchronized).
        participants: Agent IDs that contributed.
        evidence_anchors: Evidence produced during sync.
        conflict_details: Description of conflicts (if any).
    """

    barrier_id: str
    synchronized: bool
    agreed_state: dict[str, Any] = field(default_factory=dict)
    participants: tuple[str, ...] = field(default_factory=tuple)
    evidence_anchors: list[EvidenceAnchor] = field(default_factory=list)
    conflict_details: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        return {
            "barrier_id": self.barrier_id,
            "synchronized": self.synchronized,
            "agreed_state": dict(self.agreed_state),
            "participants": list(self.participants),
            "evidence_anchors": [a.to_dict() for a in self.evidence_anchors],
            "conflict_details": self.conflict_details,
        }


class SyncPrimitive:
    """Barrier-based state agreement for multi-agent coordination.

    Lock order: 4.

    Thread-safe.  Participants call ``contribute()`` to submit a state
    proposal, then ``resolve()`` to merge all proposals using a given
    strategy.
    """

    def __init__(
        self,
        evidence_store: EvidenceStore,
        audit_log: CoordinationAuditLog,
    ) -> None:
        self._evidence_store = evidence_store
        self._audit_log = audit_log
        self._barriers: dict[str, SyncBarrier] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_coordination_evidence(
        self,
        ref_prefix: str,
        ref_id: str,
        event_type: str,
        source_agent_id: str,
        target_agent_ids: list[str],
        capability_id: str,
        metadata: dict[str, Any],
        audit_details: dict[str, Any] | None = None,
    ) -> EvidenceAnchor:
        """Create an evidence anchor and record an audit event.

        Args:
            ref_prefix: Prefix for the evidence ref (e.g. ``"sync"``).
            ref_id: Unique ID appended to the prefix.
            event_type: Audit event type string.
            source_agent_id: Agent that initiated the action.
            target_agent_ids: Agents affected by the action.
            capability_id: Ontology capability ID.
            metadata: Metadata stored on the evidence anchor.
            audit_details: Details for the audit event.  Defaults to
                *metadata* when not provided.
        """
        anchor = EvidenceAnchor(
            ref=f"{ref_prefix}:{ref_id}",
            kind="coordination",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )
        self._evidence_store.add_anchor(anchor, capability_id=capability_id)
        self._audit_log.record(
            event_type=event_type,
            source_agent_id=source_agent_id,
            target_agent_ids=target_agent_ids,
            capability_id=capability_id,
            details=audit_details if audit_details is not None else metadata,
            evidence_refs=[anchor.ref],
        )
        return anchor

    # ------------------------------------------------------------------
    # Barrier lifecycle
    # ------------------------------------------------------------------

    def create_barrier(
        self,
        participants: list[str] | set[str] | frozenset[str],
        required_state: dict[str, Any] | None = None,
        timeout_seconds: float = 60.0,
    ) -> SyncBarrier:
        """Create a new synchronization barrier."""
        barrier_id = os.urandom(16).hex()
        barrier = SyncBarrier(
            barrier_id=barrier_id,
            participants=frozenset(participants),
            required_state=dict(required_state) if required_state else {},
            timeout_seconds=timeout_seconds,
        )
        with self._lock:
            self._barriers[barrier_id] = barrier
        logger.debug(
            "Created barrier %s with %d participants",
            barrier_id[:8],
            len(barrier.participants),
        )
        return barrier

    def contribute(
        self,
        barrier_id: str,
        agent_id: str,
        state_proposal: dict[str, Any],
    ) -> bool:
        """Submit a state proposal to a barrier.

        Returns True if the contribution was accepted, False if the
        barrier doesn't exist or the agent isn't a participant.
        """
        with self._lock:
            barrier = self._barriers.get(barrier_id)
            if barrier is None:
                return False
            if barrier.resolved:
                raise ValueError(f"Cannot contribute to resolved barrier: {barrier_id}")
            if agent_id not in barrier.participants:
                return False
            barrier.proposals[agent_id] = dict(state_proposal)
        logger.debug(
            "Agent %s contributed to barrier %s",
            agent_id,
            barrier_id[:8],
        )
        return True

    def resolve(
        self,
        barrier_id: str,
        strategy: str = SyncStrategy.LAST_WRITER_WINS,
    ) -> SyncResult:
        """Merge proposals and resolve the barrier.

        Strategies:
        - ``last_writer_wins``: Last proposal overwrites earlier ones.
        - ``merge_keys``: Shallow dict merge; overlapping keys are
          resolved last-writer-wins and logged in ``conflict_details``.
        - ``require_unanimous``: All proposals must be identical.

        Returns a ``SyncResult`` indicating success/failure.
        """
        if strategy not in _VALID_STRATEGIES:
            raise ValueError(
                f"Unknown sync strategy: {strategy!r}. "
                f"Valid: {sorted(_VALID_STRATEGIES)}"
            )

        with self._lock:
            barrier = self._barriers.get(barrier_id)
            if barrier is None:
                return SyncResult(
                    barrier_id=barrier_id,
                    synchronized=False,
                    conflict_details="Barrier not found",
                )
            if barrier.resolved:
                raise ValueError(f"Barrier already resolved: {barrier_id}")
            barrier.resolved = True

            proposals = dict(barrier.proposals)
            participants = tuple(sorted(proposals.keys()))
            all_participants = frozenset(barrier.participants)

        # Check all participants have contributed
        missing = all_participants - set(proposals.keys())
        if missing:
            return SyncResult(
                barrier_id=barrier_id,
                synchronized=False,
                participants=participants,
                conflict_details=(f"Missing contributions from: {sorted(missing)}"),
            )

        # Merge according to strategy
        agreed_state: dict[str, Any] = {}
        conflicts: list[str] = []

        if strategy == SyncStrategy.LAST_WRITER_WINS:
            for agent_id in participants:
                agreed_state.update(proposals[agent_id])

        elif strategy == SyncStrategy.MERGE_KEYS:
            for agent_id in participants:
                for key, value in proposals[agent_id].items():
                    if key in agreed_state and agreed_state[key] != value:
                        conflicts.append(
                            f"Key conflict on '{key}': "
                            f"existing={agreed_state[key]!r}, "
                            f"from {agent_id}={value!r}"
                        )
                    agreed_state[key] = value

        elif strategy == SyncStrategy.REQUIRE_UNANIMOUS:
            values = list(proposals.values())
            if all(v == values[0] for v in values[1:]):
                agreed_state = dict(values[0])
            else:
                return SyncResult(
                    barrier_id=barrier_id,
                    synchronized=False,
                    participants=participants,
                    conflict_details="Proposals are not unanimous",
                )

        # Create evidence and audit
        anchor = self._record_coordination_evidence(
            ref_prefix="sync",
            ref_id=barrier_id,
            event_type="synchronization",
            source_agent_id=participants[0] if participants else "",
            target_agent_ids=list(participants),
            capability_id="synchronize",
            metadata={
                "strategy": strategy,
                "participant_count": len(participants),
                "synchronized": True,
            },
            audit_details={
                "barrier_id": barrier_id,
                "strategy": strategy,
                "synchronized": True,
            },
        )

        result = SyncResult(
            barrier_id=barrier_id,
            synchronized=True,
            agreed_state=agreed_state,
            participants=participants,
            evidence_anchors=[anchor],
            conflict_details="; ".join(conflicts) if conflicts else "",
        )

        # Clean up resolved barrier
        with self._lock:
            self._barriers.pop(barrier_id, None)

        return result

    def get_barrier(self, barrier_id: str) -> SyncBarrier | None:
        with self._lock:
            return self._barriers.get(barrier_id)

    def list_barriers(self) -> list[SyncBarrier]:
        """Return all active (non-resolved) barriers."""
        with self._lock:
            return list(self._barriers.values())
