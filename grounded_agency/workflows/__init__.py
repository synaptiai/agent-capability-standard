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
from .runner import Host, RunIncomplete, RunResult, RunStartError, WorkflowRunner
from .tracer import ConformanceReport, StepTrace, WorkflowTracer

__all__ = [
    "BindingError",
    "ConformanceReport",
    "Host",
    "RunIncomplete",
    "RunResult",
    "RunStartError",
    "StepStatus",
    "StepTrace",
    "WorkflowDefinition",
    "WorkflowEngine",
    "WorkflowRunner",
    "WorkflowStep",
    "WorkflowStepResult",
    "WorkflowTracer",
]
