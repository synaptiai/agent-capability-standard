"""Typed exceptions for the coordination runtime."""

from __future__ import annotations


class CoordinationError(Exception):
    """Base exception for coordination runtime errors."""


class AgentNotRegisteredError(CoordinationError):
    """Raised when an operation references an unregistered agent."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent not registered: {agent_id}")


class CapabilityMismatchError(CoordinationError):
    """Raised when an agent lacks required capabilities."""

    def __init__(self, agent_id: str, missing: set[str]) -> None:
        self.agent_id = agent_id
        self.missing = missing
        super().__init__(f"Agent {agent_id} lacks capabilities: {sorted(missing)}")


class BarrierResolvedError(CoordinationError):
    """Raised when operating on an already-resolved barrier."""

    def __init__(self, barrier_id: str) -> None:
        self.barrier_id = barrier_id
        super().__init__(f"Barrier already resolved: {barrier_id}")


class TaskLifecycleError(CoordinationError):
    """Raised on invalid task state transitions."""

    def __init__(
        self, task_id: str, current_status: str, attempted_action: str
    ) -> None:
        self.task_id = task_id
        self.current_status = current_status
        self.attempted_action = attempted_action
        super().__init__(
            f"Cannot {attempted_action} task {task_id}: status is '{current_status}'"
        )
