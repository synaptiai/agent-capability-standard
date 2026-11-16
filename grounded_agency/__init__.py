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
from .capabilities.bindings import ToolBinding, check_offered, load_bindings
from .capabilities.mapper import UNCLASSIFIED_TOOL, ToolCapabilityMapper, ToolMapping
from .capabilities.output import (
    CapabilityOutputError,
    decode_capability_output,
    encode_capability_output,
)
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
from .entities import EntityId, parse_entity_id
from .errors import (
    ErrorCode,
    Severity,
    ValidationError,
    format_error,
    format_errors_response,
)
from .grounding import GroundingPolicy, GroundingResult
from .grounding import check_output as check_grounding_output
from .mcp import create_grounded_mcp_server
from .profiles import AppliedProfiles, ProfileError, load_profile
from .query import CostSummary, grounded_query
from .state.checkpoint_tracker import Checkpoint, CheckpointTracker
from .state.evidence_store import (
    EvidenceAnchor,
    EvidenceRecord,
    EvidenceStore,
    EvidenceStoreProtocol,
    StoreInfo,
)
from .state.jsonl_evidence_store import JsonlEvidenceStore
from .state.rate_limiter import RateLimitConfig, RateLimiter
from .state.redaction import Redactor
from .trust import Candidate, Resolution, merge_trust_weights
from .trust import resolve as resolve_conflict
from .versions import CitedVersionError
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
    "UNCLASSIFIED_TOOL",
    # Tool bindings and text-only outputs (STANDARD 1.2.0 section 5.18)
    "ToolBinding",
    "load_bindings",
    "check_offered",
    "encode_capability_output",
    "decode_capability_output",
    "CapabilityOutputError",
    # State management
    "CheckpointTracker",
    "Checkpoint",
    "EvidenceStore",
    "EvidenceAnchor",
    # Evidence records, stores and redaction (STANDARD v1.2 §6.5-§6.7)
    "EvidenceRecord",
    "EvidenceStoreProtocol",
    "JsonlEvidenceStore",
    "StoreInfo",
    "Redactor",
    # Grounding (STANDARD v1.2 §3.1, §5.20)
    "GroundingPolicy",
    "GroundingResult",
    "check_grounding_output",
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
    "Severity",
    "ValidationError",
    "format_error",
    "format_errors_response",
    # Domain profiles, trust, entity ids and cited versions (Standard 1.2)
    "AppliedProfiles",
    "ProfileError",
    "load_profile",
    "EntityId",
    "parse_entity_id",
    "Candidate",
    "Resolution",
    "resolve_conflict",
    "merge_trust_weights",
    "CitedVersionError",
    # Logging
    "logger",
]
