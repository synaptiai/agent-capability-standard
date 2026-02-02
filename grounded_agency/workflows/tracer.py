"""
Workflow Tracer (Validation Mode)

Records agent actions and validates them against declared workflow patterns.
Operates in audit-only mode — observes and reports conformance without
blocking or enforcing step transitions.

Example:
    engine = WorkflowEngine("schemas/capability_ontology.yaml")
    engine.load_catalog("schemas/workflow_catalog.yaml")

    tracer = WorkflowTracer(engine, "debug_code_change")
    tracer.record_action("observe", {"signals": ["error.log"]})
    tracer.record_action("search", {"query": "NullPointerException"})

    report = tracer.get_report()
    print(report.conformance_score)  # 0.0 - 1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .engine import StepStatus, WorkflowDefinition, WorkflowEngine, WorkflowStep

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StepTrace:
    """Records a single traced action and its mapping to a workflow step."""

    capability: str
    domain: str | None
    timestamp: datetime
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    matched_step_index: int | None = None
    status: StepStatus = StepStatus.PENDING
    notes: str = ""


@dataclass(slots=True)
class ConformanceReport:
    """Summary of how well traced actions conform to a workflow pattern."""

    workflow_name: str
    total_steps: int
    matched_steps: list[int]
    skipped_steps: list[int]
    pending_steps: list[int]
    out_of_order_steps: list[int]
    extra_actions: list[int]
    violations: list[str]
    conformance_score: float

    @property
    def is_conformant(self) -> bool:
        """Check if the trace fully conforms to the workflow pattern."""
        return len(self.violations) == 0 and len(self.pending_steps) == 0


class WorkflowTracer:
    """
    Traces agent actions and validates conformance to a workflow pattern.

    The tracer records capability invocations as they occur and maps them
    to steps in a declared workflow. After execution, it produces a
    conformance report indicating:

    - Which workflow steps were matched by agent actions
    - Which steps were skipped (potentially via gates)
    - Which steps are still pending
    - Whether actions occurred out of order
    - Any extra actions not part of the workflow

    This is audit-only — no enforcement or blocking.

    Example:
        tracer = WorkflowTracer(engine, "rag_pipeline")
        tracer.record_action("retrieve", {"query": "API docs"})
        tracer.record_action("generate", {"context": "..."})
        report = tracer.get_report()
    """

    def __init__(
        self,
        engine: WorkflowEngine,
        workflow_name: str,
    ) -> None:
        """
        Initialize the tracer for a specific workflow.

        Args:
            engine: WorkflowEngine with loaded catalog
            workflow_name: Name of the workflow to trace against

        Raises:
            ValueError: If workflow not found in engine
        """
        workflow = engine.get_workflow(workflow_name)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_name}")

        self._engine = engine
        self._workflow = workflow
        self._traces: list[StepTrace] = []
        self._next_expected_step: int = 0
        self._matched_step_indices: set[int] = set()

    @property
    def workflow(self) -> WorkflowDefinition:
        """The workflow definition being traced against."""
        return self._workflow

    @property
    def traces(self) -> list[StepTrace]:
        """All recorded traces."""
        return list(self._traces)

    def record_action(
        self,
        capability: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        domain: str | None = None,
    ) -> StepTrace:
        """
        Record an agent action and attempt to match it to a workflow step.

        Args:
            capability: The capability ID that was invoked
            input_data: Input data provided to the capability
            output_data: Output data produced by the capability
            domain: Optional domain parameter for the capability

        Returns:
            StepTrace with match information
        """
        trace = StepTrace(
            capability=capability,
            domain=domain,
            timestamp=datetime.now(timezone.utc),
            input_data=input_data or {},
            output_data=output_data or {},
        )

        # Try to match against expected workflow steps
        matched_index = self._find_matching_step(capability, domain)

        if matched_index is not None:
            trace.matched_step_index = matched_index
            trace.status = StepStatus.COMPLETED

            if matched_index < self._next_expected_step:
                trace.notes = "out_of_order"
            elif matched_index > self._next_expected_step:
                trace.notes = "steps_skipped"

            self._matched_step_indices.add(matched_index)
            # Advance expected pointer past this match
            self._next_expected_step = matched_index + 1
        else:
            trace.status = StepStatus.COMPLETED
            trace.notes = "extra_action"

        self._traces.append(trace)

        logger.debug(
            "Traced %s → step %s (%s)",
            capability,
            matched_index,
            trace.notes or "matched",
        )

        return trace

    def _find_matching_step(
        self,
        capability: str,
        domain: str | None,
    ) -> int | None:
        """
        Find the best matching workflow step for a capability invocation.

        Searches forward from the current position, then checks any
        unmatched prior steps for out-of-order matches.
        """
        steps = self._workflow.steps

        # First: look forward from current position
        for i in range(self._next_expected_step, len(steps)):
            if i in self._matched_step_indices:
                continue
            if self._step_matches(steps[i], capability, domain):
                return i

        # Second: look backward for out-of-order matches
        for i in range(self._next_expected_step):
            if i in self._matched_step_indices:
                continue
            if self._step_matches(steps[i], capability, domain):
                return i

        return None

    def _step_matches(
        self,
        step: WorkflowStep,
        capability: str,
        domain: str | None,
    ) -> bool:
        """Check if a workflow step matches a capability invocation."""
        if step.capability != capability:
            return False
        # If step has domain constraint, the action must satisfy it
        if step.domain is not None and step.domain != domain:
            return False
        return True

    def mark_step_skipped(self, step_index: int, reason: str = "") -> None:
        """
        Explicitly mark a workflow step as skipped (e.g., via a gate).

        Args:
            step_index: Index of the step in the workflow
            reason: Why the step was skipped

        Raises:
            ValueError: If step_index is out of range
        """
        if not (0 <= step_index < len(self._workflow.steps)):
            raise ValueError(
                f"Step index {step_index} out of range "
                f"(workflow has {len(self._workflow.steps)} steps)"
            )
        self._matched_step_indices.add(step_index)
        trace = StepTrace(
            capability=self._workflow.steps[step_index].capability,
            domain=self._workflow.steps[step_index].domain,
            timestamp=datetime.now(timezone.utc),
            input_data={},
            output_data={},
            matched_step_index=step_index,
            status=StepStatus.SKIPPED,
            notes=reason or "gate_condition",
        )
        self._traces.append(trace)

    def get_report(self) -> ConformanceReport:
        """
        Generate a conformance report for the current trace state.

        Returns:
            ConformanceReport with match details and conformance score
        """
        total = len(self._workflow.steps)
        matched: list[int] = []
        skipped: list[int] = []
        pending: list[int] = []
        out_of_order: list[int] = []
        extra: list[int] = []
        violations: list[str] = []

        # Classify each workflow step
        for i in range(total):
            if i in self._matched_step_indices:
                # Find the trace for this step
                step_trace = next(
                    (t for t in self._traces if t.matched_step_index == i),
                    None,
                )
                if step_trace and step_trace.status == StepStatus.SKIPPED:
                    skipped.append(i)
                elif step_trace and step_trace.notes == "out_of_order":
                    out_of_order.append(i)
                    matched.append(i)
                else:
                    matched.append(i)
            else:
                pending.append(i)

        # Classify extra actions
        for trace_idx, trace in enumerate(self._traces):
            if trace.notes == "extra_action":
                extra.append(trace_idx)

        # Generate violations
        if out_of_order:
            for idx in out_of_order:
                step = self._workflow.steps[idx]
                violations.append(
                    f"Step {idx} ({step.capability}) executed out of order"
                )

        # Check for mutation steps executed without checkpoint coverage
        for i in matched:
            step = self._workflow.steps[i]
            if step.requires_checkpoint:
                # Check if a checkpoint step preceded this
                checkpoint_found = False
                for j in matched:
                    if j < i and self._workflow.steps[j].capability == "checkpoint":
                        checkpoint_found = True
                        break
                if not checkpoint_found:
                    violations.append(
                        f"Step {i} ({step.capability}) requires checkpoint "
                        f"but no checkpoint step preceded it"
                    )

        # Calculate conformance score
        if total == 0:
            score = 1.0
        else:
            # Score: matched + skipped count as "covered"
            covered = len(matched) + len(skipped)
            # Penalize out-of-order (half credit) and extra actions
            order_penalty = len(out_of_order) * 0.5
            extra_penalty = len(extra) * 0.1
            raw_score = (covered / total) - (order_penalty / total) - (
                extra_penalty / total
            )
            score = max(0.0, min(1.0, raw_score))

        return ConformanceReport(
            workflow_name=self._workflow.name,
            total_steps=total,
            matched_steps=matched,
            skipped_steps=skipped,
            pending_steps=pending,
            out_of_order_steps=out_of_order,
            extra_actions=extra,
            violations=violations,
            conformance_score=round(score, 3),
        )
