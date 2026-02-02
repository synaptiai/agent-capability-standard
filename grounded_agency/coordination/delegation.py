"""
Delegation Protocol

Typed task delegation between agents.  Each delegation validates that
the target agent has the required capabilities (contract enforcement),
creates evidence anchors, and records audit events.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..state.evidence_store import EvidenceAnchor, EvidenceStore
from .audit import CoordinationAuditLog
from .registry import AgentRegistry

logger = logging.getLogger(__name__)

# Sentinel agent ID for the orchestration layer itself.
ORCHESTRATOR_AGENT_ID = "orchestrator"


@dataclass(slots=True)
class DelegationTask:
    """A task to be delegated to another agent.

    Attributes:
        task_id: Unique identifier (128-bit hex).
        description: Human-readable description of the work.
        required_capabilities: Ontology capability IDs needed to perform
                               the task.
        input_data: Typed input payload for the task.
        constraints: Additional constraints (timeout, quality, etc.).
        created_at: ISO 8601 UTC timestamp.
    """

    task_id: str
    description: str
    required_capabilities: frozenset[str]
    input_data: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "required_capabilities": sorted(self.required_capabilities),
            "input_data": dict(self.input_data),
            "constraints": dict(self.constraints),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class DelegationResult:
    """Result of a delegation attempt.

    Attributes:
        task_id: Which task this result is for.
        agent_id: Agent that accepted (or was asked).
        accepted: Whether the delegation was accepted.
        status: Lifecycle status -- ``"accepted"``, ``"rejected"``, or
                ``"completed"``.  Kept consistent with *accepted*.
        evidence_anchors: Evidence produced during delegation.
        rejection_reason: Why delegation was rejected (if not accepted).
        output_data: Task output (populated by ``complete_task``).
    """

    task_id: str
    agent_id: str
    accepted: bool
    evidence_anchors: list[EvidenceAnchor] = field(default_factory=list)
    rejection_reason: str = ""
    output_data: dict[str, Any] = field(default_factory=dict)
    status: str = "accepted"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "accepted": self.accepted,
            "status": self.status,
            "evidence_anchors": [a.to_dict() for a in self.evidence_anchors],
            "rejection_reason": self.rejection_reason,
            "output_data": dict(self.output_data),
        }


class DelegationProtocol:
    """Manages typed task delegation between agents.

    Lock order: 3.

    Thread-safe.  Validates capability contracts, creates evidence
    anchors, and integrates with the audit log.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        evidence_store: EvidenceStore,
        audit_log: CoordinationAuditLog,
        max_tasks: int = 10000,
        max_delegation_depth: int = 10,
    ) -> None:
        self._agent_registry = agent_registry
        self._evidence_store = evidence_store
        self._audit_log = audit_log
        self._max_tasks = max_tasks
        self._max_delegation_depth = max_delegation_depth
        self._tasks: dict[str, DelegationTask] = {}
        self._results: dict[str, DelegationResult] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_delegation_anchor(
        self,
        task_id: str,
        description: str,
        target_agent_id: str,
        accepted: bool,
        rejection_reason: str = "",
    ) -> EvidenceAnchor:
        """Create and store an evidence anchor for a delegation attempt."""
        metadata: dict[str, Any] = {
            "description": description[:100],
            "target_agent": target_agent_id,
            "accepted": accepted,
        }
        if rejection_reason:
            metadata["rejection_reason"] = rejection_reason
        anchor = EvidenceAnchor(
            ref=f"delegation:{task_id}",
            kind="coordination",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )
        self._evidence_store.add_anchor(anchor, capability_id="delegate")
        return anchor

    def _record_delegation_event(
        self,
        task_id: str,
        target_agent_ids: list[str],
        accepted: bool,
        required_capabilities: frozenset[str],
        rejection_reason: str = "",
        evidence_ref: str = "",
    ) -> None:
        """Record an audit event for a delegation attempt."""
        details: dict[str, Any] = {
            "task_id": task_id,
            "accepted": accepted,
            "required_capabilities": sorted(required_capabilities),
        }
        if rejection_reason:
            details["rejection_reason"] = rejection_reason
        self._audit_log.record(
            event_type="delegation",
            source_agent_id=ORCHESTRATOR_AGENT_ID,
            target_agent_ids=target_agent_ids,
            capability_id="delegate",
            details=details,
            evidence_refs=[evidence_ref] if evidence_ref else [],
        )

    def _evict_oldest_if_over_limit(self) -> None:
        """Evict the oldest task entry when the collection exceeds max_tasks.

        Must be called with ``self._lock`` held.
        """
        if len(self._tasks) > self._max_tasks:
            oldest_key = next(iter(self._tasks))
            del self._tasks[oldest_key]
            self._results.pop(oldest_key, None)

    # ------------------------------------------------------------------
    # Delegation
    # ------------------------------------------------------------------

    def delegate(
        self,
        description: str,
        required_capabilities: set[str] | frozenset[str] | list[str],
        target_agent_id: str,
        input_data: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        _depth: int = 0,
    ) -> DelegationResult:
        """Delegate a task to a specific agent.

        Validates the agent has the required capabilities.  Creates an
        evidence anchor and audit event regardless of acceptance.

        Args:
            _depth: Internal recursion depth counter for chained delegations.
                Raises ``ValueError`` when it exceeds ``max_delegation_depth``.
        """
        if _depth > self._max_delegation_depth:
            raise ValueError(
                f"Delegation depth limit exceeded: {_depth} > {self._max_delegation_depth}"
            )
        task_id = os.urandom(16).hex()
        caps = frozenset(required_capabilities)

        task = DelegationTask(
            task_id=task_id,
            description=description,
            required_capabilities=caps,
            input_data=dict(input_data) if input_data else {},
            constraints=dict(constraints) if constraints else {},
        )

        agent = self._agent_registry.get_agent(target_agent_id)
        if agent is None:
            result = DelegationResult(
                task_id=task_id,
                agent_id=target_agent_id,
                accepted=False,
                rejection_reason=f"Agent not registered: {target_agent_id}",
                status="rejected",
            )
        elif not caps <= agent.capabilities:
            missing = caps - agent.capabilities
            result = DelegationResult(
                task_id=task_id,
                agent_id=target_agent_id,
                accepted=False,
                rejection_reason=(f"Agent lacks capabilities: {sorted(missing)}"),
                status="rejected",
            )
        else:
            result = DelegationResult(
                task_id=task_id,
                agent_id=target_agent_id,
                accepted=True,
                status="accepted",
            )

        # Create evidence anchor for this delegation
        anchor = self._create_delegation_anchor(
            task_id=task_id,
            description=description,
            target_agent_id=target_agent_id,
            accepted=result.accepted,
            rejection_reason=result.rejection_reason,
        )
        result.evidence_anchors = [anchor]

        with self._lock:
            # Re-verify agent still exists (TOCTOU protection).
            # Between the initial get_agent() check and this critical section,
            # another thread may have unregistered the target agent.
            if result.accepted:
                reverify = self._agent_registry.get_agent(target_agent_id)
                if reverify is None:
                    result.accepted = False
                    result.rejection_reason = (
                        f"Agent unregistered during delegation: {target_agent_id}"
                    )
                    result.status = "rejected"
            self._tasks[task_id] = task
            self._results[task_id] = result
            self._evict_oldest_if_over_limit()

        # Audit event
        self._record_delegation_event(
            task_id=task_id,
            target_agent_ids=[target_agent_id],
            accepted=result.accepted,
            required_capabilities=caps,
            rejection_reason=result.rejection_reason,
            evidence_ref=anchor.ref,
        )

        logger.debug(
            "Delegation %s -> %s: %s",
            task_id[:8],
            target_agent_id,
            "accepted" if result.accepted else result.rejection_reason,
        )
        return result

    def auto_delegate(
        self,
        description: str,
        required_capabilities: set[str] | frozenset[str] | list[str],
        input_data: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> DelegationResult:
        """Discover the best agent and delegate automatically.

        Selects the agent with the highest trust score that has all
        required capabilities.  Returns a rejected result if no
        suitable agent is found.
        """
        caps = frozenset(required_capabilities)
        candidates = self._agent_registry.discover_by_capabilities(caps)

        if not candidates:
            task_id = os.urandom(16).hex()
            task = DelegationTask(
                task_id=task_id,
                description=description,
                required_capabilities=caps,
                input_data=dict(input_data) if input_data else {},
                constraints=dict(constraints) if constraints else {},
            )
            rejection_reason = "No agent found with required capabilities"
            result = DelegationResult(
                task_id=task_id,
                agent_id="",
                accepted=False,
                rejection_reason=rejection_reason,
                status="rejected",
            )
            # Evidence and audit for the rejection
            anchor = self._create_delegation_anchor(
                task_id=task_id,
                description=description,
                target_agent_id="",
                accepted=False,
                rejection_reason=rejection_reason,
            )
            result.evidence_anchors = [anchor]
            self._record_delegation_event(
                task_id=task_id,
                target_agent_ids=[],
                accepted=False,
                required_capabilities=caps,
                rejection_reason=rejection_reason,
                evidence_ref=anchor.ref,
            )
            with self._lock:
                self._tasks[task_id] = task
                self._results[task_id] = result
                self._evict_oldest_if_over_limit()
            return result

        # Best candidate is first (sorted by trust descending)
        return self.delegate(
            description=description,
            required_capabilities=caps,
            target_agent_id=candidates[0].agent_id,
            input_data=input_data,
            constraints=constraints,
        )

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------

    def complete_task(
        self,
        task_id: str,
        output_data: dict[str, Any] | None = None,
        evidence_anchors: list[EvidenceAnchor] | None = None,
    ) -> DelegationResult | None:
        """Mark a delegated task as complete with output and evidence.

        Returns a snapshot of the result, or None if task_id is unknown.

        Raises:
            ValueError: If the task status is not ``"accepted"`` (e.g. the
                task was already completed or was rejected).
        """
        with self._lock:
            result = self._results.get(task_id)
            if result is None:
                return None
            if result.status != "accepted":
                raise ValueError(
                    f"Cannot complete task {task_id}: "
                    f"status is '{result.status}', expected 'accepted'"
                )
            result.output_data = dict(output_data) if output_data else {}
            result.status = "completed"
            if evidence_anchors:
                result.evidence_anchors = result.evidence_anchors + list(
                    evidence_anchors
                )
            # Snapshot under lock for thread-safe audit recording
            agent_id = result.agent_id
            evidence_refs = [a.ref for a in result.evidence_anchors]

        self._audit_log.record(
            event_type="task_complete",
            source_agent_id=agent_id,
            target_agent_ids=[ORCHESTRATOR_AGENT_ID],
            capability_id="delegate",
            details={"task_id": task_id},
            evidence_refs=evidence_refs,
        )

        return result

    def get_task(self, task_id: str) -> DelegationTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def get_result(self, task_id: str) -> DelegationResult | None:
        with self._lock:
            return self._results.get(task_id)

    def list_tasks(self) -> list[DelegationTask]:
        """Return all tracked delegation tasks."""
        with self._lock:
            return list(self._tasks.values())

    def list_results(self) -> list[DelegationResult]:
        """Return all tracked delegation results."""
        with self._lock:
            return list(self._results.values())
