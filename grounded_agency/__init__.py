"""
Grounded Agency - Claude Agent SDK Integration

Provides safety-first agent execution with:
- Evidence-grounded decisions
- Checkpoint-before-mutation safety
- Typed capability contracts
- Audit trails

Usage:
    from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

    adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
    options = adapter.wrap_options(base_options)
"""

from __future__ import annotations

import logging

from ._types import (
    FallbackPermissionAllow,
    FallbackPermissionDeny,
    HookCallback,
    HookContext,
)
from .adapter import GroundedAgentAdapter, GroundedAgentConfig
from .capabilities.mapper import ToolCapabilityMapper, ToolMapping
from .capabilities.registry import CapabilityRegistry
from .state.checkpoint_tracker import Checkpoint, CheckpointTracker
from .state.evidence_store import EvidenceAnchor, EvidenceStore
from .state.rate_limiter import RateLimitConfig, RateLimiter
from .workflows.engine import (
    BindingError,
    StepStatus,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowStep,
    WorkflowStepResult,
)
from .workflows.tracer import ConformanceReport, StepTrace, WorkflowTracer
from .coordination import (
    AgentDescriptor,
    AgentRegistry,
    CoordinationAuditLog,
    CoordinationEvent,
    CrossAgentEvidenceBridge,
    DelegationProtocol,
    DelegationResult,
    DelegationTask,
    OrchestrationConfig,
    OrchestrationResult,
    OrchestrationRuntime,
    SharedEvidence,
    SyncBarrier,
    SyncPrimitive,
    SyncResult,
)

# Configure package-level logger
logger = logging.getLogger("grounded_agency")
logger.addHandler(logging.NullHandler())  # Let users configure handlers

__version__ = "0.1.0"

__all__ = [
    # Main adapter
    "GroundedAgentAdapter",
    "GroundedAgentConfig",
    # Capabilities
    "CapabilityRegistry",
    "ToolCapabilityMapper",
    "ToolMapping",
    # State management
    "CheckpointTracker",
    "Checkpoint",
    "EvidenceStore",
    "EvidenceAnchor",
    "RateLimiter",
    "RateLimitConfig",
    # Types
    "HookCallback",
    "HookContext",
    "FallbackPermissionAllow",
    "FallbackPermissionDeny",
    # Workflow engine
    "StepStatus",
    "WorkflowEngine",
    "WorkflowDefinition",
    "WorkflowStep",
    "WorkflowStepResult",
    "BindingError",
    "WorkflowTracer",
    "ConformanceReport",
    "StepTrace",
    # Coordination
    "OrchestrationRuntime",
    "OrchestrationConfig",
    "OrchestrationResult",
    "AgentRegistry",
    "AgentDescriptor",
    "DelegationProtocol",
    "DelegationTask",
    "DelegationResult",
    "SyncPrimitive",
    "SyncBarrier",
    "SyncResult",
    "CrossAgentEvidenceBridge",
    "SharedEvidence",
    "CoordinationAuditLog",
    "CoordinationEvent",
    # Logging
    "logger",
]
