"""
Workflow Execution Engine

Loads workflow definitions from a workflow catalog and exposes them as typed
objects, with validation by the Rust core (the same validator
``tools/validate_workflows.py`` runs) and checkpoint integration.

Example:
    engine = WorkflowEngine("schemas/capability_ontology.yaml")
    engine.load_catalog("schemas/workflow_catalog.yaml")

    workflow = engine.get_workflow("debug_code_change")
    errors = engine.validate_bindings("debug_code_change")
    report = engine.validate_report("debug_code_change")  # errors and warnings
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .. import _core
from ..capabilities.registry import CapabilityNode, CapabilityRegistry
from ..errors import ErrorCode, Severity, ValidationError
from ..state.checkpoint_tracker import CheckpointTracker

logger = logging.getLogger(__name__)

# The step fields that carry safety semantics. Omitted, each inherits the
# ontology's value; declared less safe than the ontology, it is ignored (W602).
SAFETY_KEYS: tuple[str, ...] = (
    "risk",
    "mutation",
    "requires_checkpoint",
    "requires_approval",
)

_RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def _stricter_risk(a: str, b: str) -> str:
    """The higher of two risk levels; an unknown level counts as lowest."""
    return a if _RISK_ORDER.get(a, -1) >= _RISK_ORDER.get(b, -1) else b


class StepStatus(str, Enum):
    """Status of a workflow step during execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True)
class Gate:
    """Conditional gate on a workflow step (STANDARD v1.1 §5.8)."""

    when: str
    action: str  # "stop", "rollback", "skip", "warn"
    message: str = ""
    phase: str | None = None  # "before" (the default) or "after"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"when": self.when, "action": self.action}
        if self.message:
            d["message"] = self.message
        if self.phase is not None:
            d["phase"] = self.phase
        return d


@dataclass(slots=True)
class FailureMode:
    """Declared failure mode for a step."""

    condition: str
    action: str  # "request_more_context", "stop", "rollback", "pause_and_checkpoint"
    recovery: str | dict[str, Any] = ""
    when: str | None = None  # expression that fires the failure mode

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"condition": self.condition, "action": self.action}
        if self.recovery:
            d["recovery"] = self.recovery
        if self.when is not None:
            d["when"] = self.when
        return d


@dataclass(slots=True)
class RetryPolicy:
    """Retry configuration for a step."""

    max: int = 1
    backoff: str = "none"  # "none", "linear", "exponential"


# Optional step fields modelled one-to-one as attributes.
_PLAIN_STEP_FIELDS: tuple[str, ...] = (
    "timeout",
    "domain",
    "condition",
    "skip_if_false",
    "parallel_group",
    "join",
    "workflow_id",
    "mapping_ref",
    "output_conforms_to",
)
_STEP_FIELDS = frozenset(
    {
        "capability",
        "purpose",
        "store_as",
        "input_bindings",
        "gates",
        "failure_modes",
        "retry",
        *SAFETY_KEYS,
        *_PLAIN_STEP_FIELDS,
    }
)


@dataclass(slots=True)
class WorkflowStep:
    """A single step in a workflow definition.

    ``risk``, ``mutation``, ``requires_checkpoint`` and ``requires_approval``
    are the *effective* values: what the step is treated as. When the step is
    parsed with a registry, each is the stricter of the declaration and the
    ontology (STANDARD v1.1 §5.2); ``declared`` keeps what the source said.
    """

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
    condition: str | None = None
    skip_if_false: bool | None = None
    parallel_group: str | None = None
    join: str | None = None
    workflow_id: str | None = None
    mapping_ref: str | None = None
    output_conforms_to: str | None = None
    # The safety fields exactly as the source declared them (absent if omitted).
    declared: dict[str, Any] = field(default_factory=dict)
    # Fields the model does not cover, kept verbatim (``x-`` extensions, ...).
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        registry: CapabilityRegistry | None = None,
    ) -> WorkflowStep:
        """Parse a step from catalog data.

        With a ``registry``, the safety fields are resolved against the
        ontology. Malformed gates and failure modes are skipped here; the
        validator reports them.
        """
        gates = [
            Gate(
                when=str(g.get("when", "")),
                action=str(g.get("action", "")),
                message=str(g.get("message", "")),
                phase=g.get("phase"),
            )
            for g in (data.get("gates") or [])
            if isinstance(g, dict)
        ]
        failure_modes = [
            FailureMode(
                condition=str(fm.get("condition", "")),
                action=str(fm.get("action", "")),
                recovery=fm.get("recovery") or "",
                when=fm.get("when"),
            )
            for fm in (data.get("failure_modes") or [])
            if isinstance(fm, dict)
        ]
        retry = None
        retry_data = data.get("retry")
        if isinstance(retry_data, dict):
            retry = RetryPolicy(
                max=retry_data.get("max", 1),
                backoff=retry_data.get("backoff", "none"),
            )

        declared = {k: data[k] for k in SAFETY_KEYS if k in data}
        plain: dict[str, Any] = {k: data.get(k) for k in _PLAIN_STEP_FIELDS}
        cap = registry.get_capability(data["capability"]) if registry else None
        bindings = data.get("input_bindings")
        return cls(
            capability=data["capability"],
            purpose=data.get("purpose", ""),
            retry=retry,
            store_as=data.get("store_as", ""),
            input_bindings=bindings if isinstance(bindings, dict) else {},
            gates=gates,
            failure_modes=failure_modes,
            declared=declared,
            extra={k: v for k, v in data.items() if k not in _STEP_FIELDS},
            **plain,
            **resolve_safety_flags(declared, cap),
        )

    def to_dict(self) -> dict[str, Any]:
        """The step as catalog data. Safety fields are written as their
        effective values, which are never weaker than the ontology's for a
        step parsed with a registry."""
        d: dict[str, Any] = {"capability": self.capability, "purpose": self.purpose}
        if self.store_as:
            d["store_as"] = self.store_as
        for k in SAFETY_KEYS:
            d[k] = getattr(self, k)
        if self.input_bindings:
            d["input_bindings"] = self.input_bindings
        if self.gates:
            d["gates"] = [g.to_dict() for g in self.gates]
        if self.failure_modes:
            d["failure_modes"] = [fm.to_dict() for fm in self.failure_modes]
        if self.retry is not None:
            d["retry"] = {"max": self.retry.max, "backoff": self.retry.backoff}
        for k in _PLAIN_STEP_FIELDS:
            value = getattr(self, k)
            if value is not None:
                d[k] = value
        d.update(self.extra)
        return d


def resolve_safety_flags(
    declared: dict[str, Any], cap: CapabilityNode | None
) -> dict[str, Any]:
    """The safety fields a step is treated as (STANDARD v1.1 §5.2).

    Each is the stricter of the declaration and the ontology: an omitted
    field inherits, a weaker one is ignored. The one exception is
    ``mutation: false`` on a capability the ontology marks
    ``mutation_overridable``. Without a capability (unknown, or no registry)
    the declaration applies, defaulting to the least strict value.
    """
    risk = declared.get("risk")
    flags: dict[str, Any] = {
        "risk": risk if isinstance(risk, str) else "low",
        "mutation": declared.get("mutation") is True,
        "requires_checkpoint": declared.get("requires_checkpoint") is True,
        "requires_approval": declared.get("requires_approval") is True,
    }
    if cap is None:
        return flags
    flags["risk"] = _stricter_risk(flags["risk"], cap.risk)
    overridden = cap.mutation_overridable and declared.get("mutation") is False
    flags["mutation"] = flags["mutation"] or (cap.mutation and not overridden)
    flags["requires_checkpoint"] = (
        flags["requires_checkpoint"] or cap.requires_checkpoint
    )
    flags["requires_approval"] = flags["requires_approval"] or cap.requires_approval
    return flags


_WORKFLOW_FIELDS = frozenset(
    {
        "goal",
        "risk",
        "steps",
        "success",
        "description",
        "inputs",
        "risk_propagation",
        "data_flow",
        "spec_version",
    }
)


@dataclass(slots=True)
class WorkflowDefinition:
    """A complete workflow.

    A definition parsed from catalog data keeps that data as ``source``, and
    validation reads the source, so it sees exactly what was written. A
    definition built in code has no source and is validated as
    :meth:`to_dict` renders it.
    """

    name: str
    goal: str
    risk: str
    steps: list[WorkflowStep]
    success: list[str] = field(default_factory=list)
    description: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    risk_propagation: dict[str, str] = field(default_factory=dict)
    data_flow: dict[str, str] = field(default_factory=dict)
    # The standard version targeted: the workflow's own ``spec_version`` or,
    # failing that, its catalog's ``# Standard version:`` header.
    spec_version: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(
        cls,
        name: str,
        data: dict[str, Any],
        registry: CapabilityRegistry | None = None,
        header_version: str | None = None,
    ) -> WorkflowDefinition:
        """Parse a workflow from catalog data. Steps that are not mappings
        with a ``capability`` are skipped here; the validator reports them."""
        steps = [
            WorkflowStep.from_dict(s, registry)
            for s in (data.get("steps") or [])
            if isinstance(s, dict) and "capability" in s
        ]
        spec_version = data.get("spec_version")
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
            spec_version=(
                spec_version if isinstance(spec_version, str) else header_version
            ),
            extra={k: v for k, v in data.items() if k not in _WORKFLOW_FIELDS},
            source=data,
        )

    def to_dict(self) -> dict[str, Any]:
        """The workflow as catalog data, built from the typed fields."""
        d: dict[str, Any] = {
            "goal": self.goal,
            "risk": self.risk,
            "steps": [s.to_dict() for s in self.steps],
        }
        if self.spec_version is not None:
            d["spec_version"] = self.spec_version
        if self.success:
            d["success"] = self.success
        if self.description:
            d["description"] = self.description
        for key in ("inputs", "risk_propagation", "data_flow"):
            value = getattr(self, key)
            if value:
                d[key] = value
        d.update(self.extra)
        return d

    def validation_data(self) -> dict[str, Any]:
        """What the validator checks: the source when there is one (with a
        header version carried over as ``spec_version``), else
        :meth:`to_dict`."""
        if self.source is None:
            return self.to_dict()
        if "spec_version" in self.source or self.spec_version is None:
            return self.source
        return {**self.source, "spec_version": self.spec_version}

    @property
    def mutation_steps(self) -> list[WorkflowStep]:
        """Steps that perform mutations."""
        return [s for s in self.steps if s.mutation]

    @property
    def checkpoint_required_steps(self) -> list[WorkflowStep]:
        """Steps that require a checkpoint."""
        return [s for s in self.steps if s.requires_checkpoint]

    @property
    def store_as_names(self) -> set[str]:
        """All store_as variable names defined by steps."""
        return {s.store_as for s in self.steps if s.store_as}


@dataclass(slots=True)
class WorkflowStepResult:
    """Result of executing a single workflow step."""

    step: WorkflowStep
    status: StepStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    checkpoint_id: str | None = None


_ERROR_TYPE_TO_CODE: dict[str, ErrorCode] = {
    "invalid_path": ErrorCode.INVALID_BINDING_PATH,
    "unresolved_ref": ErrorCode.MISSING_PRODUCER,
    "missing_store_as": ErrorCode.MISSING_PRODUCER,
    "type_mismatch": ErrorCode.TYPE_MISMATCH,
    "ambiguous_type": ErrorCode.AMBIGUOUS_TYPE,
    "invalid_annotation": ErrorCode.INVALID_ANNOTATION,
    "expression_type": ErrorCode.EXPRESSION_TYPE_ERROR,
}
_CODE_TO_ERROR_TYPE: dict[ErrorCode, str] = {
    ErrorCode.INVALID_BINDING_PATH: "invalid_path",
    ErrorCode.MISSING_PRODUCER: "unresolved_ref",
    ErrorCode.TYPE_MISMATCH: "type_mismatch",
    ErrorCode.AMBIGUOUS_TYPE: "ambiguous_type",
    ErrorCode.INVALID_ANNOTATION: "invalid_annotation",
    ErrorCode.EXPRESSION_TYPE_ERROR: "expression_type",
}


@dataclass(slots=True)
class BindingError:
    """A binding error (B2xx): a reference that does not resolve, or whose
    type does not fit where it is used."""

    workflow_name: str
    step_index: int
    step_capability: str
    binding_key: str
    reference: str
    error_type: str  # see _ERROR_TYPE_TO_CODE
    message: str
    expected_type: str | None = None
    actual_type: str | None = None
    code: ErrorCode | None = None

    @property
    def error_code(self) -> ErrorCode:
        """The standard code (Section 9): ``code`` when known, else derived
        from ``error_type``."""
        if self.code is not None:
            return self.code
        return _ERROR_TYPE_TO_CODE.get(self.error_type, ErrorCode.INVALID_BINDING_PATH)

    @classmethod
    def from_diagnostic(cls, d: ValidationError) -> BindingError:
        loc = d.location
        field_name = str(loc.get("field", ""))
        raw_ref = str(loc.get("ref", ""))
        return cls(
            workflow_name=str(loc.get("workflow", "")),
            step_index=int(loc.get("step", -1)),
            step_capability=str(loc.get("capability", "")),
            binding_key=field_name.removeprefix("input_bindings."),
            reference=raw_ref.split(":", 1)[0].strip(),
            error_type=_CODE_TO_ERROR_TYPE.get(d.code, d.code.name.lower()),
            message=d.message,
            code=d.code,
        )


_EDGE_CODES = frozenset({ErrorCode.MISSING_PREREQUISITE, ErrorCode.CONSTRAINT_VIOLATED})


def _describe(d: ValidationError) -> str:
    """One line for a diagnostic: the step it concerns, then the message."""
    loc = d.location
    if "step" in loc:
        return f"Step {loc['step']} ({loc.get('capability', '?')}): {d.message}"
    return d.message


class WorkflowEngine:
    """
    Workflow engine: loads workflow definitions and validates them.

    - Workflow loading and retrieval, with safety flags resolved against the
      ontology
    - Validation by the Rust core (STANDARD v1.1 §5, §9): capabilities,
      ontology edges, bindings, expressions, safety flags, warnings
    - Checkpoint auto-creation before mutation steps

    Example:
        engine = WorkflowEngine("schemas/capability_ontology.yaml")
        engine.load_catalog("schemas/workflow_catalog.yaml")

        workflow = engine.get_workflow("debug_code_change")
        assert workflow is not None

        assert engine.validate_bindings("debug_code_change") == []
    """

    def __init__(
        self,
        ontology_path: str | Path,
        checkpoint_tracker: CheckpointTracker | None = None,
        schema_root: str | Path | None = None,
    ) -> None:
        """
        Initialize the workflow engine.

        Args:
            ontology_path: Path to capability_ontology.yaml
            checkpoint_tracker: Optional tracker for auto-checkpoint integration.
                              If None, checkpoint integration is disabled.
            schema_root: Directory that schema, mapping and input references
                         are relative to. Defaults to the directory above the
                         ontology's (the repository root for
                         ``schemas/capability_ontology.yaml``).
        """
        self._ontology_path = Path(ontology_path)
        self._schema_root = (
            Path(schema_root)
            if schema_root is not None
            else self._ontology_path.resolve().parent.parent
        )
        self._registry = CapabilityRegistry(ontology_path)
        self._checkpoint_tracker = checkpoint_tracker
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._validator: _core.Validator | None = None

    @property
    def registry(self) -> CapabilityRegistry:
        """Access the capability registry."""
        return self._registry

    @property
    def checkpoint_tracker(self) -> CheckpointTracker | None:
        """Access the checkpoint tracker, if configured."""
        return self._checkpoint_tracker

    def _core_validator(self) -> _core.Validator:
        """The core validator, created on first use (it loads the ontology)."""
        if self._validator is None:
            self._validator = _core.Validator(self._ontology_path, self._schema_root)
        return self._validator

    def load_catalog(self, catalog_path: str | Path) -> int:
        """
        Load workflow definitions from a YAML catalog file.

        The file is read with the core's YAML loader, the one validation
        uses. Entries that are not workflows (non-mappings, ``x-`` vendor
        data, mappings without ``steps``) are skipped.

        Args:
            catalog_path: Path to workflow_catalog.yaml

        Returns:
            Number of workflows loaded

        Raises:
            FileNotFoundError: If the catalog file doesn't exist
            ValueError: If the catalog is a symlink, too large, not valid
                YAML, or not a mapping
        """
        data, header = _core.load_catalog(catalog_path)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError(
                f"{catalog_path}: a workflow catalog must be a mapping of "
                f"workflow names, found {type(data).__name__}"
            )

        count = 0
        for name, wf_data in data.items():
            if name.startswith("x-"):
                continue
            if not isinstance(wf_data, dict):
                logger.warning("Skipping non-dict workflow entry: %s", name)
                continue
            if "steps" not in wf_data:
                logger.warning("Skipping workflow without steps: %s", name)
                continue
            self._workflows[name] = WorkflowDefinition.from_dict(
                name, wf_data, self._registry, header
            )
            count += 1

        logger.info("Loaded %d workflows from %s", count, catalog_path)
        return count

    def add_workflow(self, workflow: WorkflowDefinition) -> None:
        """Add (or replace) a workflow under its name."""
        self._workflows[workflow.name] = workflow

    def get_workflow(self, name: str) -> WorkflowDefinition | None:
        """Get a workflow by name."""
        return self._workflows.get(name)

    def list_workflows(self) -> list[str]:
        """List all loaded workflow names."""
        return list(self._workflows.keys())

    def effective_flags(self, step: WorkflowStep) -> dict[str, Any]:
        """The safety fields ``step`` is treated as: its own values made at
        least as strict as the ontology's. For a step parsed with this
        engine's registry this equals the step's attributes."""
        own = {k: getattr(step, k) for k in SAFETY_KEYS}
        return resolve_safety_flags(own, self._registry.get_capability(step.capability))

    # -- Validation ---------------------------------------------------------

    def validate_report(
        self, workflow_name: str | None = None
    ) -> list[ValidationError]:
        """Every diagnostic, errors and warnings, in the validator's order.

        All loaded workflows are validated together, so references between
        them resolve. With ``workflow_name``, only that workflow's
        diagnostics are returned.

        Raises:
            KeyError: If ``workflow_name`` is not loaded
        """
        if workflow_name is not None and workflow_name not in self._workflows:
            raise KeyError(f"Workflow not found: {workflow_name}")
        catalog = {name: wf.validation_data() for name, wf in self._workflows.items()}
        report = self._core_validator().validate(catalog)
        diagnostics = [ValidationError.from_core(d) for d in report["diagnostics"]]
        if workflow_name is None:
            return diagnostics
        return [d for d in diagnostics if d.location.get("workflow") == workflow_name]

    def _errors(self, workflow_name: str) -> list[ValidationError]:
        return [
            d
            for d in self.validate_report(workflow_name)
            if d.severity is Severity.ERROR
        ]

    def validate_capabilities(self, workflow_name: str) -> list[str]:
        """
        Errors for capabilities a workflow names that the ontology lacks
        (V101). Safety-flag downgrades are warnings (W602; the ontology value
        applies) and appear in :meth:`validate_report`.

        Returns:
            List of error messages (empty if all valid)
        """
        if workflow_name not in self._workflows:
            return [f"Workflow not found: {workflow_name}"]
        return [
            _describe(d)
            for d in self._errors(workflow_name)
            if d.code is ErrorCode.UNKNOWN_CAPABILITY
        ]

    def validate_bindings(self, workflow_name: str) -> list[BindingError]:
        """
        Binding errors (B2xx) in a workflow: references in input bindings,
        conditions and gates that name no earlier step or input, paths not in
        the producer's schema, and types that do not fit.

        Returns:
            List of BindingError objects (empty if all valid)
        """
        if workflow_name not in self._workflows:
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
        return [
            BindingError.from_diagnostic(d)
            for d in self._errors(workflow_name)
            if d.code.value.startswith("B")
        ]

    def validate_edge_constraints(self, workflow_name: str) -> list[str]:
        """
        Errors against the ontology's edges: ``requires`` and ``precedes``
        (V102) and ``conflicts_with`` within a parallel group (F504).
        Unmet ``soft_requires`` are warnings (W601) in :meth:`validate_report`.

        Returns:
            List of error messages (empty if all valid)
        """
        if workflow_name not in self._workflows:
            return [f"Workflow not found: {workflow_name}"]
        return [
            _describe(d) for d in self._errors(workflow_name) if d.code in _EDGE_CODES
        ]

    def validate_all(self) -> dict[str, list[str]]:
        """
        Errors for every loaded workflow.

        Returns:
            Dict mapping each workflow with errors to its error messages
        """
        return {
            name: [_describe(e) for e in errors]
            for name, errors in self.validate_all_structured().items()
        }

    def validate_all_structured(self) -> dict[str, list[ValidationError]]:
        """Errors for every loaded workflow, as structured ValidationError
        objects (the counterpart of :meth:`validate_all`).

        Returns:
            Dict mapping each workflow with errors to its errors
        """
        results: dict[str, list[ValidationError]] = {}
        for d in self.validate_report():
            if d.severity is Severity.ERROR:
                name = str(d.location.get("workflow", ""))
                results.setdefault(name, []).append(d)
        return results

    # -- Checkpoints --------------------------------------------------------

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

        # The ontology prevails over the step's own flags: a crafted
        # definition cannot downgrade mutation/requires_checkpoint to bypass
        # checkpoint creation.
        flags = self.effective_flags(step)
        if not (flags["mutation"] or flags["requires_checkpoint"]):
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
