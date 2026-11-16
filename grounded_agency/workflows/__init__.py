"""
Workflow Execution Engine

Provides runtime workflow orchestration for the Grounded Agency capability standard.
Loads declarative workflow YAML and orchestrates step execution with:
- Binding validation between steps
- Checkpoint auto-creation before mutation steps
- Conformance tracing (validation mode)
- Running workflows on the core's executor (``WorkflowRunner`` with a ``Host``)
"""

from __future__ import annotations

from .engine import (
    BindingError,
    StepStatus,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowStep,
    WorkflowStepResult,
)
from .runner import (
    Host,
    HostCannotServe,
    HostResponseError,
    RunArchiveError,
    RunIncomplete,
    RunResult,
    RunStartError,
    Turn,
    WorkflowRunner,
)
from .tracer import ConformanceReport, StepTrace, WorkflowTracer
from .triggers import (
    EventGate,
    OverlapGate,
    matches_event,
    next_fire,
    trigger_attendance,
)

__all__ = [
    "BindingError",
    "ConformanceReport",
    "EventGate",
    "Host",
    "HostCannotServe",
    "HostResponseError",
    "OverlapGate",
    "RunArchiveError",
    "RunIncomplete",
    "RunResult",
    "RunStartError",
    "StepStatus",
    "StepTrace",
    "Turn",
    "WorkflowDefinition",
    "WorkflowEngine",
    "WorkflowRunner",
    "WorkflowStep",
    "WorkflowStepResult",
    "WorkflowTracer",
    "matches_event",
    "next_fire",
    "trigger_attendance",
]
