"""
Workflow Execution Engine

Loads workflow definitions from workflow_catalog.yaml and provides runtime
orchestration of capability invocations with binding validation, gate
evaluation, and checkpoint integration.

Example:
    engine = WorkflowEngine("schemas/capability_ontology.yaml")
    engine.load_catalog("schemas/workflow_catalog.yaml")

    workflow = engine.get_workflow("debug_code_change")
    errors = engine.validate_bindings("debug_code_change")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..capabilities.registry import CapabilityRegistry
from ..state.checkpoint_tracker import CheckpointTracker
from ..utils.safe_yaml import ONTOLOGY_MAX_BYTES, safe_yaml_load

logger = logging.getLogger(__name__)

# Pattern for ${variable_ref} and ${variable_ref.field: type} bindings
_BINDING_REF_PATTERN = re.compile(
    r"\$\{([a-zA-Z_][a-zA-Z0-9_.]*?)(?::\s*([a-zA-Z_<>]+(?:\[[a-zA-Z_<>]+\])?))?\}"
)


class StepStatus(str, Enum):
    """Status of a workflow step during execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True)
class Gate:
    """Conditional gate on a workflow step."""

    when: str
    action: str  # "skip", "stop"
    message: str = ""


@dataclass(slots=True)
class FailureMode:
    """Declared failure mode for a step."""

    condition: str
    action: str  # "request_more_context", "stop", "rollback", "pause_and_checkpoint"
    recovery: str = ""


@dataclass(slots=True)
class RetryPolicy:
    """Retry configuration for a step."""

    max: int = 1
    backoff: str = "none"  # "none", "linear", "exponential"


@dataclass(slots=True)
class WorkflowStep:
    """Represents a single step in a workflow definition."""

    capability: str
    purpose: str
    risk: str = "low"
    mutation: bool = False
    requires_checkpoint: bool = False
    requires_approval: bool = False
    timeout: str | None = None
    retry: RetryPolicy | None = None
    store_as: str = ""
    domain: str | None = None
    input_bindings: dict[str, Any] = field(default_factory=dict)
    gates: list[Gate] = field(default_factory=list)
    failure_modes: list[FailureMode] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        """Parse a workflow step from YAML data."""
        gates = [
            Gate(
                when=g.get("when", ""),
                action=g.get("action", "skip"),
                message=g.get("message", ""),
            )
            for g in (data.get("gates") or [])
        ]

        failure_modes = [
            FailureMode(
                condition=fm.get("condition", ""),
                action=fm.get("action", "stop"),
                recovery=fm.get("recovery", ""),
            )
            for fm in (data.get("failure_modes") or [])
        ]

        retry = None
        retry_data = data.get("retry")
        if retry_data and isinstance(retry_data, dict):
            retry = RetryPolicy(
                max=retry_data.get("max", 1),
                backoff=retry_data.get("backoff", "none"),
            )

        return cls(
            capability=data["capability"],
            purpose=data.get("purpose", ""),
            risk=data.get("risk", "low"),
            mutation=data.get("mutation", False),
            requires_checkpoint=data.get("requires_checkpoint", False),
            requires_approval=data.get("requires_approval", False),
            timeout=data.get("timeout"),
            retry=retry,
            store_as=data.get("store_as", ""),
            domain=data.get("domain"),
            input_bindings=data.get("input_bindings") or {},
            gates=gates,
            failure_modes=failure_modes,
        )


@dataclass(slots=True)
class WorkflowDefinition:
    """Represents a complete workflow loaded from YAML."""

    name: str
    goal: str
    risk: str
    steps: list[WorkflowStep]
    success: list[str] = field(default_factory=list)
    description: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    risk_propagation: dict[str, str] = field(default_factory=dict)
    data_flow: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> WorkflowDefinition:
        """Parse a workflow definition from YAML data."""
        steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]

        return cls(
            name=name,
            goal=data.get("goal", ""),
            risk=data.get("risk", "low"),
            steps=steps,
            success=data.get("success") or [],
            description=data.get("description", ""),
            inputs=data.get("inputs") or {},
            risk_propagation=data.get("risk_propagation") or {},
            data_flow=data.get("data_flow") or {},
        )

    @property
    def mutation_steps(self) -> list[WorkflowStep]:
        """Get steps that perform mutations."""
        return [s for s in self.steps if s.mutation]

    @property
    def checkpoint_required_steps(self) -> list[WorkflowStep]:
        """Get steps that require a checkpoint."""
        return [s for s in self.steps if s.requires_checkpoint]

    @property
    def store_as_names(self) -> set[str]:
        """Get all store_as variable names defined by steps."""
        return {s.store_as for s in self.steps if s.store_as}


@dataclass(slots=True)
class WorkflowStepResult:
    """Result of executing a single workflow step."""

    step: WorkflowStep
    status: StepStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    checkpoint_id: str | None = None


@dataclass(slots=True)
class BindingError:
    """Describes a binding type mismatch or unresolvable reference."""

    workflow_name: str
    step_index: int
    step_capability: str
    binding_key: str
    reference: str
    error_type: str  # "unresolved_ref", "type_mismatch", "missing_store_as"
    message: str
    expected_type: str | None = None
    actual_type: str | None = None


class WorkflowEngine:
    """
    Runtime workflow engine that loads and validates workflow definitions.

    Loads workflow YAML from the catalog and provides:
    - Workflow loading and retrieval
    - Binding validation between steps
    - Ontology constraint checking (requires, precedes, conflicts_with edges)
    - Checkpoint auto-creation before mutation steps

    Example:
        engine = WorkflowEngine("schemas/capability_ontology.yaml")
        engine.load_catalog("schemas/workflow_catalog.yaml")

        workflow = engine.get_workflow("debug_code_change")
        assert workflow is not None
        assert len(workflow.steps) == 11

        errors = engine.validate_bindings("debug_code_change")
        assert len(errors) == 0
    """

    def __init__(
        self,
        ontology_path: str | Path,
        checkpoint_tracker: CheckpointTracker | None = None,
    ) -> None:
        """
        Initialize the workflow engine.

        Args:
            ontology_path: Path to capability_ontology.yaml
            checkpoint_tracker: Optional tracker for auto-checkpoint integration.
                              If None, checkpoint integration is disabled.
        """
        self._registry = CapabilityRegistry(ontology_path)
        self._checkpoint_tracker = checkpoint_tracker
        self._workflows: dict[str, WorkflowDefinition] = {}

    @property
    def registry(self) -> CapabilityRegistry:
        """Access the capability registry."""
        return self._registry

    @property
    def checkpoint_tracker(self) -> CheckpointTracker | None:
        """Access the checkpoint tracker, if configured."""
        return self._checkpoint_tracker

    def load_catalog(self, catalog_path: str | Path) -> int:
        """
        Load workflow definitions from a YAML catalog file.

        Args:
            catalog_path: Path to workflow_catalog.yaml

        Returns:
            Number of workflows loaded

        Raises:
            FileNotFoundError: If catalog file doesn't exist
            ValueError: If catalog is a symlink
        """
        data: dict[str, Any] = safe_yaml_load(
            catalog_path, max_size=ONTOLOGY_MAX_BYTES
        )

        count = 0
        for name, wf_data in data.items():
            if not isinstance(wf_data, dict):
                logger.warning("Skipping non-dict workflow entry: %s", name)
                continue
            if "steps" not in wf_data:
                logger.warning("Skipping workflow without steps: %s", name)
                continue
            self._workflows[name] = WorkflowDefinition.from_dict(name, wf_data)
            count += 1

        logger.info("Loaded %d workflows from %s", count, catalog_path)
        return count

    def get_workflow(self, name: str) -> WorkflowDefinition | None:
        """Get a workflow by name."""
        return self._workflows.get(name)

    def list_workflows(self) -> list[str]:
        """List all loaded workflow names."""
        return list(self._workflows.keys())

    def validate_capabilities(self, workflow_name: str) -> list[str]:
        """
        Validate that all capabilities referenced in a workflow exist in the ontology.

        Args:
            workflow_name: Name of the workflow to validate

        Returns:
            List of error messages (empty if all valid)
        """
        workflow = self._workflows.get(workflow_name)
        if workflow is None:
            return [f"Workflow not found: {workflow_name}"]

        errors: list[str] = []
        for i, step in enumerate(workflow.steps):
            cap = self._registry.get_capability(step.capability)
            if cap is None:
                errors.append(
                    f"Step {i} ({step.capability}): "
                    f"capability not found in ontology"
                )
        return errors

    def validate_bindings(self, workflow_name: str) -> list[BindingError]:
        """
        Validate input bindings between workflow steps.

        Checks that:
        - All ${ref} references point to existing store_as names or workflow inputs
        - Type annotations in bindings match output schemas where available

        Args:
            workflow_name: Name of the workflow to validate

        Returns:
            List of BindingError objects (empty if all valid)
        """
        workflow = self._workflows.get(workflow_name)
        if workflow is None:
            return [
                BindingError(
                    workflow_name=workflow_name,
                    step_index=-1,
                    step_capability="",
                    binding_key="",
                    reference="",
                    error_type="workflow_not_found",
                    message=f"Workflow not found: {workflow_name}",
                )
            ]

        errors: list[BindingError] = []

        # Collect all available store_as names from preceding steps
        # and workflow input names
        available_refs: dict[str, int] = {}  # ref_name -> defining step index
        for input_name in workflow.inputs:
            available_refs[input_name] = -1  # -1 means workflow input

        for i, step in enumerate(workflow.steps):
            # Check bindings in this step
            step_errors = self._validate_step_bindings(
                workflow_name, i, step, available_refs
            )
            errors.extend(step_errors)

            # Register this step's store_as for subsequent steps
            if step.store_as:
                available_refs[step.store_as] = i

        return errors

    def _validate_step_bindings(
        self,
        workflow_name: str,
        step_index: int,
        step: WorkflowStep,
        available_refs: dict[str, int],
    ) -> list[BindingError]:
        """Validate bindings for a single step."""
        errors: list[BindingError] = []
        refs = self._extract_binding_refs(step.input_bindings)

        for binding_key, ref_name, declared_type in refs:
            # Split ref_name to get base variable (before any dot-path)
            base_ref = ref_name.split(".")[0]

            if base_ref not in available_refs:
                errors.append(
                    BindingError(
                        workflow_name=workflow_name,
                        step_index=step_index,
                        step_capability=step.capability,
                        binding_key=binding_key,
                        reference=ref_name,
                        error_type="unresolved_ref",
                        message=(
                            f"Reference '${{{ref_name}}}' not found. "
                            f"Available: {sorted(available_refs.keys())}"
                        ),
                    )
                )
                continue

            # Type mismatch detection (when declared types are available)
            if declared_type:
                source_step_index = available_refs[base_ref]
                type_error = self._check_type_compatibility(
                    workflow_name,
                    step_index,
                    step,
                    binding_key,
                    ref_name,
                    declared_type,
                    source_step_index,
                )
                if type_error:
                    errors.append(type_error)

        return errors

    def _extract_binding_refs(
        self,
        bindings: Any,
        parent_key: str = "",
    ) -> list[tuple[str, str, str | None]]:
        """
        Extract ${ref} references from binding values.

        Returns:
            List of (binding_key, ref_name, declared_type) tuples
        """
        refs: list[tuple[str, str, str | None]] = []

        if isinstance(bindings, str):
            for match in _BINDING_REF_PATTERN.finditer(bindings):
                ref_name = match.group(1)
                declared_type = match.group(2)  # May be None
                refs.append((parent_key, ref_name, declared_type))

        elif isinstance(bindings, dict):
            for key, value in bindings.items():
                full_key = f"{parent_key}.{key}" if parent_key else key
                refs.extend(self._extract_binding_refs(value, full_key))

        elif isinstance(bindings, list):
            for idx, item in enumerate(bindings):
                full_key = f"{parent_key}[{idx}]"
                refs.extend(self._extract_binding_refs(item, full_key))

        return refs

    def _check_type_compatibility(
        self,
        workflow_name: str,
        step_index: int,
        step: WorkflowStep,
        binding_key: str,
        ref_name: str,
        declared_type: str,
        source_step_index: int,
    ) -> BindingError | None:
        """Check type compatibility between binding declaration and source output."""
        workflow = self._workflows[workflow_name]

        # Get source capability's output schema
        if source_step_index < 0:
            # Workflow input — check against workflow input schema
            return None  # Input types validated separately

        source_step = workflow.steps[source_step_index]
        source_cap = self._registry.get_capability(source_step.capability)
        if source_cap is None:
            return None  # Capability validation handles this

        # Extract the output type from the ontology output_schema
        output_schema = source_cap.output_schema
        if not output_schema:
            return None  # No schema to check against

        # Try to resolve the field path after the store_as base
        parts = ref_name.split(".")
        if len(parts) > 1:
            field_path = parts[1:]
            resolved_type = self._resolve_schema_type(output_schema, field_path)
        else:
            resolved_type = output_schema.get("type")

        if resolved_type and not self._types_compatible(resolved_type, declared_type):
            return BindingError(
                workflow_name=workflow_name,
                step_index=step_index,
                step_capability=step.capability,
                binding_key=binding_key,
                reference=ref_name,
                error_type="type_mismatch",
                message=(
                    f"Type mismatch: '${{{ref_name}}}' declared as "
                    f"'{declared_type}' but source outputs '{resolved_type}'"
                ),
                expected_type=declared_type,
                actual_type=resolved_type,
            )
        return None

    def _resolve_schema_type(
        self,
        schema: dict[str, Any],
        field_path: list[str],
    ) -> str | None:
        """Resolve a field path through a JSON Schema-like output schema."""
        current = schema
        for part in field_path:
            props = current.get("properties", {})
            if part in props:
                current = props[part]
            else:
                return None
        return current.get("type")

    def _types_compatible(self, schema_type: str, declared_type: str) -> bool:
        """Check if a schema type is compatible with a declared binding type."""
        # Normalize common type aliases
        type_map: dict[str, set[str]] = {
            "string": {"string", "str"},
            "array": {"array", "list"},
            "object": {"object", "dict", "map"},
            "number": {"number", "float", "int", "integer"},
            "integer": {"integer", "int", "number"},
            "boolean": {"boolean", "bool"},
        }

        # Handle parameterized types like array<object>
        base_declared = declared_type.split("<")[0].split("[")[0].lower()
        base_schema = schema_type.lower()

        schema_set = type_map.get(base_schema, {base_schema})
        return base_declared in schema_set

    def validate_edge_constraints(self, workflow_name: str) -> list[str]:
        """
        Validate ontology edge constraints within a workflow.

        Checks:
        - 'requires' edges: hard dependencies are satisfied by prior steps
        - 'precedes' edges: temporal ordering is respected
        - 'conflicts_with' edges: conflicting capabilities don't coexist

        Args:
            workflow_name: Name of the workflow to validate

        Returns:
            List of error messages (empty if all valid)
        """
        workflow = self._workflows.get(workflow_name)
        if workflow is None:
            return [f"Workflow not found: {workflow_name}"]

        errors: list[str] = []
        seen_capabilities: set[str] = set()

        for i, step in enumerate(workflow.steps):
            cap_id = step.capability

            # Check 'requires' edges
            required = self._registry.get_required_capabilities(cap_id)
            for req in required:
                if req not in seen_capabilities:
                    errors.append(
                        f"Step {i} ({cap_id}): requires '{req}' "
                        f"but it hasn't been executed in prior steps"
                    )

            # Check 'precedes' edges
            preceding = self._registry.get_preceding_capabilities(cap_id)
            for pred in preceding:
                if pred not in seen_capabilities:
                    errors.append(
                        f"Step {i} ({cap_id}): must be preceded by '{pred}' "
                        f"but it hasn't been executed in prior steps"
                    )

            # Check 'conflicts_with' edges
            conflicts = self._registry.get_conflicting_capabilities(cap_id)
            for conflict in conflicts:
                if conflict in seen_capabilities:
                    errors.append(
                        f"Step {i} ({cap_id}): conflicts with '{conflict}' "
                        f"which was already executed"
                    )

            seen_capabilities.add(cap_id)

        return errors

    def ensure_checkpoint_before_step(
        self,
        step: WorkflowStep,
        workflow_name: str,
    ) -> str | None:
        """
        Auto-create a checkpoint before a mutation step if needed.

        Args:
            step: The workflow step about to execute
            workflow_name: Name of the containing workflow

        Returns:
            Checkpoint ID if created, None if not needed or tracker unavailable
        """
        if self._checkpoint_tracker is None:
            return None

        if not (step.mutation or step.requires_checkpoint):
            return None

        # Check if a valid checkpoint already exists
        if self._checkpoint_tracker.has_valid_checkpoint():
            return self._checkpoint_tracker.get_active_checkpoint_id()

        # Auto-create checkpoint
        checkpoint_id = self._checkpoint_tracker.create_checkpoint(
            scope=["*"],
            reason=(
                f"Auto-checkpoint before '{step.capability}' step "
                f"in workflow '{workflow_name}'"
            ),
        )
        logger.info(
            "Auto-created checkpoint %s before %s in %s",
            checkpoint_id,
            step.capability,
            workflow_name,
        )
        return checkpoint_id

    def validate_all(self) -> dict[str, list[str]]:
        """
        Run all validations on all loaded workflows.

        Returns:
            Dict mapping workflow name to list of error messages
        """
        results: dict[str, list[str]] = {}
        for name in self._workflows:
            errors: list[str] = []
            errors.extend(self.validate_capabilities(name))
            errors.extend(
                e.message for e in self.validate_bindings(name)
            )
            errors.extend(self.validate_edge_constraints(name))
            if errors:
                results[name] = errors
        return results
