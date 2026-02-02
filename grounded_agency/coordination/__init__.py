"""
Coordination Subpackage

Multi-agent coordination runtime: registration, delegation,
synchronization, shared evidence, audit, and orchestration.
"""

from __future__ import annotations

from .audit import CoordinationAuditLog, CoordinationEvent
from .delegation import (
    ORCHESTRATOR_AGENT_ID,
    DelegationProtocol,
    DelegationResult,
    DelegationTask,
)
from .exceptions import (
    AgentNotRegisteredError,
    BarrierResolvedError,
    CapabilityMismatchError,
    CoordinationError,
    TaskLifecycleError,
)
from .evidence_bridge import CrossAgentEvidenceBridge, SharedEvidence
from .orchestrator import OrchestrationConfig, OrchestrationResult, OrchestrationRuntime
from .registry import AgentDescriptor, AgentRegistry
from .synchronization import SyncBarrier, SyncPrimitive, SyncResult, SyncStrategy

__all__ = [
    # Audit
    "CoordinationAuditLog",
    "CoordinationEvent",
    # Delegation
    "ORCHESTRATOR_AGENT_ID",
    "DelegationProtocol",
    "DelegationTask",
    "DelegationResult",
    # Exceptions
    "CoordinationError",
    "AgentNotRegisteredError",
    "CapabilityMismatchError",
    "BarrierResolvedError",
    "TaskLifecycleError",
    # Evidence bridge
    "CrossAgentEvidenceBridge",
    "SharedEvidence",
    # Orchestrator
    "OrchestrationRuntime",
    "OrchestrationConfig",
    "OrchestrationResult",
    # Registry
    "AgentRegistry",
    "AgentDescriptor",
    # Synchronization
    "SyncPrimitive",
    "SyncBarrier",
    "SyncResult",
    "SyncStrategy",
]
