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
from collections.abc import Callable, Coroutine
from typing import Any

from .adapter import GroundedAgentAdapter, GroundedAgentConfig
from .capabilities.mapper import ToolCapabilityMapper, ToolMapping
from .capabilities.registry import CapabilityRegistry
from .state.checkpoint_tracker import Checkpoint, CheckpointTracker
from .state.evidence_store import EvidenceAnchor, EvidenceStore
from .state.rate_limiter import RateLimitConfig, RateLimiter

# Configure package-level logger
logger = logging.getLogger("grounded_agency")
logger.addHandler(logging.NullHandler())  # Let users configure handlers

# Canonical type alias for hook callbacks (avoid duplication)
HookCallback = Callable[
    [dict[str, Any], str | None, Any],
    Coroutine[Any, Any, dict[str, Any]],
]

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
    # Logging
    "logger",
]
