"""
Cross-Agent Evidence Bridge

Enables agents to share evidence anchors with trust decay propagation.
When evidence is shared, the propagated trust equals
``source_agent.trust_score * trust_decay``, preventing unbounded trust
through long delegation chains.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..state.evidence_store import EvidenceAnchor, EvidenceStore
from .audit import CoordinationAuditLog
from .registry import AgentRegistry

logger = logging.getLogger(__name__)

# Default multiplicative decay applied each time evidence is shared
DEFAULT_TRUST_DECAY = 0.9


@dataclass(slots=True)
class SharedEvidence:
    """Evidence shared between agents with propagated trust.

    Attributes:
        anchor: The original evidence anchor.
        source_agent_id: Agent that shared the evidence.
        trust_score: Propagated trust (source trust * decay).
        original_trust: Trust score from the first time this evidence
            was shared.  Caps re-sharing to prevent trust inflation.
        shared_at: ISO 8601 UTC timestamp of sharing.
    """

    anchor: EvidenceAnchor
    source_agent_id: str
    trust_score: float
    original_trust: float = 0.0
    shared_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CrossAgentEvidenceBridge:
    """Facilitates evidence sharing between agents with trust propagation.

    Thread-safe.  Integrates with ``AgentRegistry`` for trust scores
    and ``CoordinationAuditLog`` for audit trails.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        evidence_store: EvidenceStore,
        audit_log: CoordinationAuditLog,
        trust_decay: float = DEFAULT_TRUST_DECAY,
    ) -> None:
        self._agent_registry = agent_registry
        self._evidence_store = evidence_store
        self._audit_log = audit_log
        self._trust_decay = trust_decay
        # Keyed by target_agent_id -> list of SharedEvidence
        self._shared: dict[str, list[SharedEvidence]] = defaultdict(list)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Sharing
    # ------------------------------------------------------------------

    def share_evidence(
        self,
        anchor: EvidenceAnchor,
        source_agent_id: str,
        target_agent_ids: list[str] | None = None,
    ) -> list[SharedEvidence]:
        """Share an evidence anchor from *source_agent_id* to targets.

        If *target_agent_ids* is ``None``, broadcast to all registered
        agents except the source.

        Returns the list of ``SharedEvidence`` objects created.
        """
        source = self._agent_registry.get_agent(source_agent_id)
        if source is None:
            raise ValueError(f"Source agent not registered: {source_agent_id}")

        # Resolve targets — broadcast if None
        if target_agent_ids is None:
            target_agent_ids = [
                a.agent_id
                for a in self._agent_registry.list_agents()
                if a.agent_id != source_agent_id
            ]

        propagated_trust = source.trust_score * self._trust_decay
        shared_at = datetime.now(timezone.utc).isoformat()
        results: list[SharedEvidence] = []

        with self._lock:
            # Cap trust at the original sharing trust to prevent inflation
            # when high-trust agents re-share low-trust evidence.
            prior = self._find_prior_sharing_unlocked(anchor.ref)
            if prior is not None:
                propagated_trust = min(propagated_trust, prior.original_trust)
                original_trust = prior.original_trust
            else:
                original_trust = propagated_trust

            for target_id in target_agent_ids:
                se = SharedEvidence(
                    anchor=anchor,
                    source_agent_id=source_agent_id,
                    trust_score=propagated_trust,
                    original_trust=original_trust,
                    shared_at=shared_at,
                )
                self._shared[target_id].append(se)
                results.append(se)

        # Audit the sharing event
        self._audit_log.record(
            event_type="evidence_share",
            source_agent_id=source_agent_id,
            target_agent_ids=target_agent_ids,
            details={
                "evidence_ref": anchor.ref,
                "propagated_trust": propagated_trust,
            },
            evidence_refs=[anchor.ref],
        )

        logger.debug(
            "Shared evidence %s from %s to %d agent(s) (trust=%.3f)",
            anchor.ref,
            source_agent_id,
            len(target_agent_ids),
            propagated_trust,
        )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_prior_sharing_unlocked(
        self, evidence_ref: str,
    ) -> SharedEvidence | None:
        """Find the first prior sharing event for this evidence ref.

        Must be called with ``self._lock`` held.
        """
        for entries in self._shared.values():
            for se in entries:
                if se.anchor.ref == evidence_ref:
                    return se
        return None

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_shared_evidence(
        self,
        target_agent_id: str,
        min_trust: float = 0.0,
    ) -> list[SharedEvidence]:
        """Get evidence shared *to* a specific agent.

        Only returns evidence with ``trust_score >= min_trust``.
        """
        with self._lock:
            return [
                se
                for se in self._shared.get(target_agent_id, [])
                if se.trust_score >= min_trust
            ]

    def get_evidence_lineage(self, evidence_ref: str) -> list[SharedEvidence]:
        """Trace all sharing events for a given evidence ref across agents."""
        with self._lock:
            return [
                se
                for entries in self._shared.values()
                for se in entries
                if se.anchor.ref == evidence_ref
            ]

    @property
    def total_shared(self) -> int:
        """Total number of shared evidence entries across all targets."""
        with self._lock:
            return sum(len(v) for v in self._shared.values())
