"""
Shared data structures for the capability discovery pipeline.

All types are plain dataclasses with no external dependencies,
following the codebase convention of @dataclass(slots=True).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

# Type alias for the pluggable LLM function.
# Accepts (prompt: str, schema: dict | None) and returns parsed dict.
# This decouples the discovery module from any specific LLM client.
LLMFunction = Callable[[str, dict[str, Any] | None], Coroutine[Any, Any, dict[str, Any]]]


@dataclass(slots=True)
class TaskRequirement:
    """A single capability requirement extracted from a task description."""

    action: str  # verb/action detected (e.g., "find", "modify", "send")
    target: str  # what the action operates on
    constraints: list[str] = field(default_factory=list)  # qualifiers
    domain_hint: str | None = None  # domain parameter if detectable

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskRequirement:
        """Create from LLM response dict."""
        return cls(
            action=data.get("action", ""),
            target=data.get("target", ""),
            constraints=data.get("constraints", []),
            domain_hint=data.get("domain_hint"),
        )


@dataclass(slots=True)
class CapabilityMatch:
    """A capability matched to a requirement with confidence."""

    capability_id: str  # ontology capability ID
    confidence: float  # 0.0-1.0
    requirement: TaskRequirement
    reasoning: str  # why this capability was matched
    domain: str | None = None  # domain parameter value

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], requirement: TaskRequirement
    ) -> CapabilityMatch:
        """Create from LLM response dict."""
        return cls(
            capability_id=data.get("capability_id", ""),
            confidence=float(data.get("confidence", 0.0)),
            requirement=requirement,
            reasoning=data.get("reasoning", ""),
            domain=data.get("domain"),
        )


@dataclass(slots=True)
class ProposedCapability:
    """Auto-generated capability proposal for an ontology gap."""

    id: str
    layer: str
    description: str
    risk: str
    mutation: bool
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    suggested_edges: list[dict[str, str]] = field(default_factory=list)
    reasoning: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposedCapability:
        """Create from LLM response dict."""
        return cls(
            id=data.get("id", ""),
            layer=data.get("layer", ""),
            description=data.get("description", ""),
            risk=data.get("risk", "low"),
            mutation=data.get("mutation", False),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            suggested_edges=data.get("suggested_edges", []),
            reasoning=data.get("reasoning", ""),
        )


@dataclass(slots=True)
class CapabilityGap:
    """A requirement that doesn't map to existing capabilities."""

    requirement: TaskRequirement
    proposed_capability: ProposedCapability | None = None
    nearest_existing: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SynthesizedWorkflow:
    """A workflow composed from identified capabilities."""

    name: str
    description: str
    steps: list[dict[str, Any]]  # workflow_catalog.yaml compatible step dicts
    bindings: dict[str, str] = field(default_factory=dict)
    validation_result: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass(slots=True)
class DiscoveryResult:
    """Complete output of the discovery pipeline."""

    task_description: str
    requirements: list[TaskRequirement]
    matches: list[CapabilityMatch]
    gaps: list[CapabilityGap] = field(default_factory=list)
    synthesized_workflow: SynthesizedWorkflow | None = None
    existing_workflow_match: str | None = None
    evidence_anchors: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
