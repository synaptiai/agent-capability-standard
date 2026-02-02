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


class SyncStrategy(enum.StrEnum):
    """Supported merge strategies for barrier resolution."""

    LAST_WRITER_WINS = "last_writer_wins"
    MERGE_KEYS = "merge_keys"
    REQUIRE_UNANIMOUS = "require_unanimous"


# Backwards-compatible aliases
STRATEGY_LAST_WRITER_WINS = SyncStrategy.LAST_WRITER_WINS
STRATEGY_MERGE_KEYS = SyncStrategy.MERGE_KEYS
STRATEGY_REQUIRE_UNANIMOUS = SyncStrategy.REQUIRE_UNANIMOUS

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


class SyncPrimitive:
    """Barrier-based state agreement for multi-agent coordination.

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
        strategy: str = STRATEGY_LAST_WRITER_WINS,
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
                conflict_details=(
                    f"Missing contributions from: {sorted(missing)}"
                ),
            )

        # Merge according to strategy
        agreed_state: dict[str, Any] = {}
        conflicts: list[str] = []

        if strategy == STRATEGY_LAST_WRITER_WINS:
            for agent_id in participants:
                agreed_state.update(proposals[agent_id])

        elif strategy == STRATEGY_MERGE_KEYS:
            for agent_id in participants:
                for key, value in proposals[agent_id].items():
                    if key in agreed_state and agreed_state[key] != value:
                        conflicts.append(
                            f"Key conflict on '{key}': "
                            f"existing={agreed_state[key]!r}, "
                            f"from {agent_id}={value!r}"
                        )
                    agreed_state[key] = value

        elif strategy == STRATEGY_REQUIRE_UNANIMOUS:
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

        # Create evidence
        anchor = EvidenceAnchor(
            ref=f"sync:{barrier_id}",
            kind="coordination",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "strategy": strategy,
                "participant_count": len(participants),
                "synchronized": True,
            },
        )
        self._evidence_store.add_anchor(anchor, capability_id="synchronize")

        # Audit
        self._audit_log.record(
            event_type="synchronization",
            source_agent_id=participants[0] if participants else "",
            target_agent_ids=list(participants),
            capability_id="synchronize",
            details={
                "barrier_id": barrier_id,
                "strategy": strategy,
                "synchronized": True,
            },
            evidence_refs=[anchor.ref],
        )

        result = SyncResult(
            barrier_id=barrier_id,
            synchronized=True,
            agreed_state=agreed_state,
            participants=participants,
            evidence_anchors=[anchor],
            conflict_details="; ".join(conflicts) if conflicts else "",
        )
        return result

    def get_barrier(self, barrier_id: str) -> SyncBarrier | None:
        with self._lock:
            return self._barriers.get(barrier_id)
