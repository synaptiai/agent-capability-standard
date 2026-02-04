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
from .client import GroundedClient
from .coordination import (
    ORCHESTRATOR_AGENT_ID,
    AgentDescriptor,
    AgentNotRegisteredError,
    AgentRegistry,
    BarrierResolvedError,
    CapabilityMismatchError,
    CoordinationAuditLog,
    CoordinationError,
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
    SyncStrategy,
    TaskLifecycleError,
)
from .discovery import (
    CapabilityGap,
    CapabilityMatch,
    DiscoveryPipeline,
    DiscoveryResult,
    GapDetector,
    LLMFunction,
    ProposedCapability,
    SynthesizedWorkflow,
    TaskRequirement,
    WorkflowSynthesizer,
)
from .errors import ErrorCode, ValidationError, format_error, format_errors_response
from .mcp import create_grounded_mcp_server
from .query import CostSummary, grounded_query
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

# Configure package-level logger
logger = logging.getLogger("grounded_agency")
logger.addHandler(logging.NullHandler())  # Let users configure handlers

__version__ = "0.1.0"

__all__ = [
    # Main adapter
    "GroundedAgentAdapter",
    "GroundedAgentConfig",
    # Query and client wrappers
    "grounded_query",
    "GroundedClient",
    "CostSummary",
    # MCP integration
    "create_grounded_mcp_server",
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
    "SyncStrategy",
    "ORCHESTRATOR_AGENT_ID",
    # Coordination exceptions
    "CoordinationError",
    "AgentNotRegisteredError",
    "CapabilityMismatchError",
    "BarrierResolvedError",
    "TaskLifecycleError",
    # Discovery
    "DiscoveryPipeline",
    "GapDetector",
    "WorkflowSynthesizer",
    "CapabilityGap",
    "CapabilityMatch",
    "DiscoveryResult",
    "LLMFunction",
    "ProposedCapability",
    "SynthesizedWorkflow",
    "TaskRequirement",
    # Error model
    "ErrorCode",
    "ValidationError",
    "format_error",
    "format_errors_response",
    # Logging
    "logger",
]
