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


@dataclass(slots=True)
class DelegationResult:
    """Result of a delegation attempt.

    Attributes:
        task_id: Which task this result is for.
        agent_id: Agent that accepted (or was asked).
        accepted: Whether the delegation was accepted.
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


class DelegationProtocol:
    """Manages typed task delegation between agents.

    Thread-safe.  Validates capability contracts, creates evidence
    anchors, and integrates with the audit log.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        evidence_store: EvidenceStore,
        audit_log: CoordinationAuditLog,
    ) -> None:
        self._agent_registry = agent_registry
        self._evidence_store = evidence_store
        self._audit_log = audit_log
        self._tasks: dict[str, DelegationTask] = {}
        self._results: dict[str, DelegationResult] = {}
        self._lock = threading.Lock()

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
    ) -> DelegationResult:
        """Delegate a task to a specific agent.

        Validates the agent has the required capabilities.  Creates an
        evidence anchor and audit event regardless of acceptance.
        """
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
            )
        elif not caps <= agent.capabilities:
            missing = caps - agent.capabilities
            result = DelegationResult(
                task_id=task_id,
                agent_id=target_agent_id,
                accepted=False,
                rejection_reason=(
                    f"Agent lacks capabilities: {sorted(missing)}"
                ),
            )
        else:
            result = DelegationResult(
                task_id=task_id,
                agent_id=target_agent_id,
                accepted=True,
            )

        # Create evidence anchor for this delegation
        anchor = EvidenceAnchor(
            ref=f"delegation:{task_id}",
            kind="coordination",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "description": description[:100],
                "target_agent": target_agent_id,
                "accepted": result.accepted,
            },
        )
        self._evidence_store.add_anchor(anchor, capability_id="delegate")
        result.evidence_anchors = [anchor]

        with self._lock:
            self._tasks[task_id] = task
            self._results[task_id] = result

        # Audit event
        self._audit_log.record(
            event_type="delegation",
            source_agent_id=ORCHESTRATOR_AGENT_ID,
            target_agent_ids=[target_agent_id],
            capability_id="delegate",
            details={
                "task_id": task_id,
                "accepted": result.accepted,
                "required_capabilities": sorted(caps),
            },
            evidence_refs=[anchor.ref],
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
            )
            # Evidence and audit for the rejection
            anchor = EvidenceAnchor(
                ref=f"delegation:{task_id}",
                kind="coordination",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "description": description[:100],
                    "accepted": False,
                    "rejection_reason": rejection_reason,
                },
            )
            self._evidence_store.add_anchor(anchor, capability_id="delegate")
            result.evidence_anchors = [anchor]
            self._audit_log.record(
                event_type="delegation",
                source_agent_id=ORCHESTRATOR_AGENT_ID,
                target_agent_ids=[],
                capability_id="delegate",
                details={
                    "task_id": task_id,
                    "accepted": False,
                    "required_capabilities": sorted(caps),
                    "rejection_reason": rejection_reason,
                },
                evidence_refs=[anchor.ref],
            )
            with self._lock:
                self._tasks[task_id] = task
                self._results[task_id] = result
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
        """
        with self._lock:
            result = self._results.get(task_id)
            if result is None:
                return None
            result.output_data = dict(output_data) if output_data else {}
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
