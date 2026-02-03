"""
Orchestration Runtime

Wires together all coordination components (AgentRegistry,
DelegationProtocol, SyncPrimitive, CrossAgentEvidenceBridge,
CoordinationAuditLog) and executes the ``multi_agent_orchestration``
workflow from the workflow catalog.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..capabilities.registry import CapabilityRegistry
from ..state.evidence_store import EvidenceAnchor, EvidenceStore
from ..workflows.engine import StepStatus, WorkflowStep, WorkflowStepResult
from ._evidence_helpers import record_coordination_evidence
from .audit import CoordinationAuditLog, CoordinationEvent
from .delegation import ORCHESTRATOR_AGENT_ID, DelegationProtocol, DelegationResult
from .evidence_bridge import CrossAgentEvidenceBridge
from .registry import AgentRegistry
from .synchronization import SyncPrimitive, SyncResult

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OrchestrationConfig:
    """Configuration for the orchestration runtime.

    Attributes:
        trust_decay: Multiplicative factor for trust propagation (0, 1].
        default_sync_timeout: Default barrier timeout in seconds (> 0).
        sync_strategy: Default merge strategy for synchronization.
        audit_max_events: Maximum audit events retained in memory (> 0).
    """

    trust_decay: float = 0.9
    default_sync_timeout: float = 60.0
    sync_strategy: str = "last_writer_wins"
    audit_max_events: int = 10000

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        return {
            "trust_decay": self.trust_decay,
            "default_sync_timeout": self.default_sync_timeout,
            "sync_strategy": self.sync_strategy,
            "audit_max_events": self.audit_max_events,
        }

    def __post_init__(self) -> None:
        if not (0.0 < self.trust_decay <= 1.0):
            raise ValueError(
                f"trust_decay must be in (0.0, 1.0], got {self.trust_decay}"
            )
        if self.default_sync_timeout <= 0:
            raise ValueError(
                f"default_sync_timeout must be > 0, got {self.default_sync_timeout}"
            )
        if self.audit_max_events <= 0:
            raise ValueError(
                f"audit_max_events must be > 0, got {self.audit_max_events}"
            )


@dataclass(slots=True)
class OrchestrationResult:
    """Result of an end-to-end orchestration run.

    Attributes:
        success: Whether the orchestration completed successfully.
        task_goal: The original task goal.
        subtasks: Delegation results for each subtask.
        sync_result: Synchronization outcome (if applicable).
        integrated_output: Merged output from all agents.
        audit_events: Audit trail for this orchestration.
        evidence_anchors: All evidence collected during orchestration.
        steps_executed: Number of workflow steps that ran.
    """

    success: bool
    task_goal: str
    subtasks: list[DelegationResult] = field(default_factory=list)
    sync_result: SyncResult | None = None
    integrated_output: dict[str, Any] = field(default_factory=dict)
    audit_events: list[CoordinationEvent] = field(default_factory=list)
    evidence_anchors: list[EvidenceAnchor] = field(default_factory=list)
    steps_executed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        return {
            "success": self.success,
            "task_goal": self.task_goal,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "sync_result": self.sync_result.to_dict() if self.sync_result else None,
            "integrated_output": dict(self.integrated_output),
            "audit_events": [e.to_dict() for e in self.audit_events],
            "evidence_anchors": [a.to_dict() for a in self.evidence_anchors],
            "steps_executed": self.steps_executed,
        }


class OrchestrationRuntime:
    """Main entry point for multi-agent coordination.

    Lock ordering (acquire in this order to prevent deadlocks):
        1. AgentRegistry._lock
        2. EvidenceStore._lock
        3. DelegationProtocol._lock
        4. SyncPrimitive._lock
        5. CrossAgentEvidenceBridge._lock
        6. CoordinationAuditLog._lock

    Creates and wires all sub-components.  The ``orchestrate()`` method
    executes the ``multi_agent_orchestration`` workflow end-to-end,
    mapping each step to the appropriate coordination primitive.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        evidence_store: EvidenceStore | None = None,
        config: OrchestrationConfig | None = None,
    ) -> None:
        self._config = config or OrchestrationConfig()
        self._capability_registry = capability_registry
        self._evidence_store = evidence_store or EvidenceStore()

        # Create coordination components
        self._audit_log = CoordinationAuditLog(
            max_events=self._config.audit_max_events,
        )
        self._agent_registry = AgentRegistry(capability_registry)
        self._delegation = DelegationProtocol(
            agent_registry=self._agent_registry,
            evidence_store=self._evidence_store,
            audit_log=self._audit_log,
        )
        self._sync = SyncPrimitive(
            evidence_store=self._evidence_store,
            audit_log=self._audit_log,
        )
        self._evidence_bridge = CrossAgentEvidenceBridge(
            agent_registry=self._agent_registry,
            evidence_store=self._evidence_store,
            audit_log=self._audit_log,
            trust_decay=self._config.trust_decay,
        )

    # ------------------------------------------------------------------
    # SDK bridge
    # ------------------------------------------------------------------

    def to_sdk_agents(self) -> dict[str, Any]:
        """Export registered agents as SDK ``AgentDefinition`` dicts.

        Converts the :class:`AgentDescriptor` instances in the registry
        into the format expected by the Claude Agent SDK's ``agents``
        option.  Each agent gets:

        - ``description``: From descriptor metadata or capabilities list.
        - ``prompt``: From descriptor metadata ``system_prompt`` key.
        - ``tools``: From descriptor metadata ``allowed_tools`` key.
        - ``model``: From descriptor metadata ``model`` key.

        Returns:
            Dict mapping agent IDs to ``AgentDefinition``-compatible dicts.

        Example::

            runtime = OrchestrationRuntime(cap_registry)
            runtime.register_agent("analyst", {"search", "retrieve"})
            sdk_agents = runtime.to_sdk_agents()
            # {'analyst': {'description': 'Agent with: retrieve, search', ...}}
        """
        result: dict[str, Any] = {}
        for descriptor in self._agent_registry.list_agents():
            meta = dict(descriptor.metadata) if descriptor.metadata else {}
            agent_def: dict[str, Any] = {
                "description": meta.get(
                    "description",
                    f"Agent with: {', '.join(sorted(descriptor.capabilities))}",
                ),
                "prompt": meta.get("system_prompt", ""),
                "tools": list(meta.get("allowed_tools", [])),
                "model": meta.get("model", "sonnet"),
            }
            result[descriptor.agent_id] = agent_def

        return result

    # ------------------------------------------------------------------
    # Properties (expose sub-components for direct access)
    # ------------------------------------------------------------------

    @property
    def agent_registry(self) -> AgentRegistry:
        return self._agent_registry

    @property
    def delegation(self) -> DelegationProtocol:
        return self._delegation

    @property
    def sync(self) -> SyncPrimitive:
        return self._sync

    @property
    def evidence_bridge(self) -> CrossAgentEvidenceBridge:
        return self._evidence_bridge

    @property
    def audit_log(self) -> CoordinationAuditLog:
        return self._audit_log

    # ------------------------------------------------------------------
    # Agent management (convenience wrappers)
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        capabilities: set[str] | frozenset[str] | list[str],
        trust_score: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register an agent with the coordination runtime."""
        self._agent_registry.register(
            agent_id=agent_id,
            capabilities=capabilities,
            trust_score=trust_score,
            metadata=metadata,
        )

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
        evidence_refs_override: list[str] | None = None,
    ) -> EvidenceAnchor:
        """Create an evidence anchor and record an audit event.

        Delegates to the shared ``record_coordination_evidence`` helper.
        """
        return record_coordination_evidence(
            self._evidence_store,
            self._audit_log,
            ref_prefix=ref_prefix,
            ref_id=ref_id,
            event_type=event_type,
            source_agent_id=source_agent_id,
            target_agent_ids=target_agent_ids,
            capability_id=capability_id,
            metadata=metadata,
            audit_details=audit_details,
            evidence_refs_override=evidence_refs_override,
        )

    def _order_subtasks_by_dependencies(
        self,
        subtasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Order subtasks using Kahn's topological sort on ontology edges.

        Builds a DAG from ``precedes`` and ``requires`` relationships
        between subtask capabilities.  Falls back to the original order
        if a cycle is detected or all subtasks lack capabilities.

        Stable tie-breaking: subtasks with equal priority retain their
        original order.
        """
        n = len(subtasks)
        if n <= 1:
            return subtasks

        # Map each subtask index to its capabilities
        subtask_caps: list[frozenset[str]] = []
        for st in subtasks:
            raw = st.get("required_capabilities", [])
            subtask_caps.append(frozenset(raw))

        # Build adjacency: edge i → j means subtask i must precede j
        in_degree = [0] * n
        adj: list[list[int]] = [[] for _ in range(n)]

        for j in range(n):
            predecessors: set[str] = set()
            for cap in subtask_caps[j]:
                predecessors.update(
                    self._capability_registry.get_preceding_capabilities(cap)
                )
                predecessors.update(
                    self._capability_registry.get_required_capabilities(cap)
                )
            if not predecessors:
                continue
            for i in range(n):
                if i == j:
                    continue
                if subtask_caps[i] & predecessors:
                    adj[i].append(j)
                    in_degree[j] += 1

        # Kahn's algorithm with stable tie-breaking (original order)
        queue: deque[int] = deque()
        for i in range(n):
            if in_degree[i] == 0:
                queue.append(i)

        ordered: list[int] = []
        while queue:
            idx = queue.popleft()
            ordered.append(idx)
            for neighbor in sorted(adj[idx]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != n:
            logger.warning(
                "Cycle detected in subtask dependencies; using original order"
            )
            return subtasks

        return [subtasks[i] for i in ordered]

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def orchestrate(
        self,
        task_goal: str,
        subtask_descriptions: list[dict[str, Any]] | None = None,
    ) -> OrchestrationResult:
        """Execute the multi_agent_orchestration workflow end-to-end.

        Follows the 7-step workflow:
        1. decompose — break task into subtasks
        2. plan — order subtasks by dependencies
        3. delegate — assign subtasks to agents
        4. synchronize — coordinate shared state
        5. verify — validate results
        6. integrate — merge outputs
        7. audit — record decisions

        If no *subtask_descriptions* are provided, a default single
        subtask is created from the goal.

        Returns an ``OrchestrationResult`` with full audit trail.
        """
        result = OrchestrationResult(success=False, task_goal=task_goal)
        all_evidence: list[EvidenceAnchor] = []
        audit_start_idx = len(self._audit_log)

        # Check that at least one agent is registered
        if not self._agent_registry.list_agents():
            result.integrated_output = {"error": "No agents available"}
            return result

        # Step 1: Decompose — use provided subtasks or create default
        if subtask_descriptions is None:
            subtask_descriptions = [
                {
                    "description": task_goal,
                    "required_capabilities": [],
                }
            ]
        result.steps_executed += 1

        # Step 2: Plan — order subtasks by dependencies
        subtask_descriptions = self._order_subtasks_by_dependencies(
            subtask_descriptions
        )
        result.steps_executed += 1

        # Step 3: Delegate — assign each subtask via execute_workflow_step
        delegation_results: list[DelegationResult] = []
        for subtask in subtask_descriptions:
            caps = subtask.get("required_capabilities", [])
            desc = subtask.get("description", task_goal)
            input_data = subtask.get("input_data", {})

            step = WorkflowStep(
                capability="delegate",
                purpose=desc,
            )
            step_result = self.execute_workflow_step(
                step,
                {
                    "description": desc,
                    "required_capabilities": caps,
                    "input_data": input_data,
                },
            )

            # Retrieve the full DelegationResult if the step produced a task_id
            task_id = (step_result.output or {}).get("task_id", "")
            dr = self._delegation.get_result(task_id) if task_id else None
            if dr is None:
                # Fallback: construct a minimal rejected result
                dr = DelegationResult(
                    task_id=task_id or os.urandom(16).hex(),
                    agent_id="",
                    accepted=False,
                    rejection_reason=step_result.error or "Delegation failed",
                )

            delegation_results.append(dr)
            all_evidence.extend(dr.evidence_anchors)

        result.subtasks = delegation_results
        result.steps_executed += 1

        # Step 4: Synchronize — create barrier for all delegated agents
        delegated_agents = [dr.agent_id for dr in delegation_results if dr.accepted]
        if len(delegated_agents) > 1:
            barrier = self._sync.create_barrier(
                participants=delegated_agents,
                timeout_seconds=self._config.default_sync_timeout,
            )
            # Each agent contributes their delegation result as state
            for dr in delegation_results:
                if dr.accepted:
                    self._sync.contribute(
                        barrier_id=barrier.barrier_id,
                        agent_id=dr.agent_id,
                        state_proposal={
                            "task_id": dr.task_id,
                            "accepted": dr.accepted,
                        },
                    )
            sync_result = self._sync.resolve(
                barrier_id=barrier.barrier_id,
                strategy=self._config.sync_strategy,
            )
            result.sync_result = sync_result
            all_evidence.extend(sync_result.evidence_anchors)
        result.steps_executed += 1

        # Step 5: Verify — check all accepted delegations
        accepted_count = sum(1 for dr in delegation_results if dr.accepted)
        total_count = len(delegation_results)
        verification_passed = accepted_count > 0
        result.steps_executed += 1

        # Step 6: Integrate — merge outputs from all delegation results
        integrated: dict[str, Any] = {
            "task_goal": task_goal,
            "total_subtasks": total_count,
            "accepted_subtasks": accepted_count,
            "agent_outputs": {},
        }
        for dr in delegation_results:
            if dr.accepted:
                integrated["agent_outputs"][dr.agent_id] = {
                    "task_id": dr.task_id,
                    "output_data": dr.output_data,
                }
        result.integrated_output = integrated
        result.steps_executed += 1

        # Step 7: Audit — record the orchestration
        orchestration_id = os.urandom(16).hex()
        audit_evidence = self._record_coordination_evidence(
            ref_prefix="orchestration",
            ref_id=orchestration_id,
            event_type="orchestration_complete",
            source_agent_id=ORCHESTRATOR_AGENT_ID,
            target_agent_ids=delegated_agents,
            capability_id="audit",
            metadata={
                "task_goal": task_goal[:100],
                "subtask_count": total_count,
                "accepted_count": accepted_count,
            },
            audit_details={
                "task_goal": task_goal,
                "subtask_count": total_count,
                "accepted_count": accepted_count,
                "verification_passed": verification_passed,
            },
            evidence_refs_override=[e.ref for e in all_evidence]
            + [f"orchestration:{orchestration_id}"],
        )
        all_evidence.append(audit_evidence)
        result.steps_executed += 1

        result.evidence_anchors = all_evidence
        result.audit_events = self._audit_log.get_events_since(audit_start_idx)
        result.success = verification_passed

        logger.info(
            "Orchestration %s: %d/%d subtasks accepted, %d audit events",
            "succeeded" if result.success else "failed",
            accepted_count,
            total_count,
            len(result.audit_events),
        )
        return result

    def execute_workflow_step(
        self,
        step: WorkflowStep,
        context: dict[str, Any] | None = None,
    ) -> WorkflowStepResult:
        """Execute a single workflow step using coordination primitives.

        Maps coordination capabilities (delegate, synchronize, audit)
        to their respective components.  Non-coordination steps return
        a completed result with the context as output.
        """
        ctx = dict(context) if context else {}

        if step.capability == "delegate":
            desc = ctx.get("description", step.purpose)
            caps = ctx.get("required_capabilities", [])
            # Use explicit input_data from context if present, else full ctx
            step_input = (
                ctx["input_data"] if isinstance(ctx.get("input_data"), dict) else ctx
            )
            if caps:
                dr = self._delegation.auto_delegate(
                    description=desc,
                    required_capabilities=caps,
                    input_data=step_input,
                )
            else:
                agents = self._agent_registry.list_agents()
                if agents:
                    dr = self._delegation.delegate(
                        description=desc,
                        required_capabilities=set(),
                        target_agent_id=agents[0].agent_id,
                        input_data=step_input,
                    )
                else:
                    return WorkflowStepResult(
                        step=step,
                        status=StepStatus.FAILED,
                        error="No agents registered for delegation",
                    )
            return WorkflowStepResult(
                step=step,
                status=StepStatus.COMPLETED if dr.accepted else StepStatus.FAILED,
                output={"task_id": dr.task_id, "accepted": dr.accepted},
                error=dr.rejection_reason if not dr.accepted else None,
            )

        if step.capability == "synchronize":
            participants = ctx.get("participants", [])
            if not participants:
                participants = [a.agent_id for a in self._agent_registry.list_agents()]
            if len(participants) < 2:
                return WorkflowStepResult(
                    step=step,
                    status=StepStatus.SKIPPED,
                    output={"reason": "Fewer than 2 participants"},
                )
            barrier = self._sync.create_barrier(participants=participants)
            for agent_id in participants:
                self._sync.contribute(
                    barrier.barrier_id,
                    agent_id,
                    ctx.get("state", {}),
                )
            sr = self._sync.resolve(
                barrier.barrier_id,
                strategy=self._config.sync_strategy,
            )
            return WorkflowStepResult(
                step=step,
                status=(StepStatus.COMPLETED if sr.synchronized else StepStatus.FAILED),
                output=sr.agreed_state,
                error=sr.conflict_details if not sr.synchronized else None,
            )

        if step.capability == "audit":
            self._audit_log.record(
                event_type="workflow_step_audit",
                source_agent_id=ORCHESTRATOR_AGENT_ID,
                target_agent_ids=[],
                capability_id="audit",
                details=ctx,
            )
            return WorkflowStepResult(
                step=step,
                status=StepStatus.COMPLETED,
                output={"audited": True},
            )

        if step.capability == "invoke":
            workflow = ctx.get("workflow", "")
            if not workflow:
                return WorkflowStepResult(
                    step=step,
                    status=StepStatus.FAILED,
                    error="No workflow name provided for invoke step",
                )
            invoke_id = os.urandom(16).hex()
            anchor = self._record_coordination_evidence(
                ref_prefix="invoke",
                ref_id=invoke_id,
                event_type="workflow_step_audit",
                source_agent_id=ORCHESTRATOR_AGENT_ID,
                target_agent_ids=[],
                capability_id="invoke",
                metadata={"workflow": workflow},
            )
            return WorkflowStepResult(
                step=step,
                status=StepStatus.COMPLETED,
                output={
                    "workflow": workflow,
                    "result": {},
                    "steps_executed": [],
                    "evidence_anchors": [anchor.ref],
                },
            )

        if step.capability == "inquire":
            ambiguous_input = ctx.get("ambiguous_input", "")
            max_questions = ctx.get("max_questions", 3)
            questions = []
            if ambiguous_input:
                questions.append(f"Could you clarify: {ambiguous_input!r}?")
            inquire_id = os.urandom(16).hex()
            anchor = self._record_coordination_evidence(
                ref_prefix="inquire",
                ref_id=inquire_id,
                event_type="workflow_step_audit",
                source_agent_id=ORCHESTRATOR_AGENT_ID,
                target_agent_ids=[],
                capability_id="inquire",
                metadata={
                    "ambiguous_input": str(ambiguous_input)[:200],
                    "max_questions": max_questions,
                },
                audit_details={"ambiguous_input": str(ambiguous_input)[:200]},
            )
            return WorkflowStepResult(
                step=step,
                status=StepStatus.COMPLETED,
                output={
                    "questions": questions,
                    "ambiguity_analysis": ambiguous_input,
                    "evidence_anchors": [anchor.ref],
                    "confidence": 0.5 if ambiguous_input else 1.0,
                },
            )

        # Non-coordination step — pass through
        return WorkflowStepResult(
            step=step,
            status=StepStatus.COMPLETED,
            output=ctx,
        )
