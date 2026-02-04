"""
LLM prompt templates for the capability discovery pipeline.

Each prompt function returns a tuple of (system_prompt, user_prompt, output_schema)
so callers can pass them to any LLM function.
"""

from __future__ import annotations

import json
from typing import Any

from ..capabilities.registry import CapabilityNode, CapabilityRegistry

# ── Output schemas ──────────────────────────────────────────────

ANALYSIS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["requirements", "matches"],
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["action", "target"],
                "properties": {
                    "action": {"type": "string"},
                    "target": {"type": "string"},
                    "constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "domain_hint": {"type": ["string", "null"]},
                },
            },
        },
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["requirement_index", "capability_id", "confidence", "reasoning"],
                "properties": {
                    "requirement_index": {"type": "integer"},
                    "capability_id": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reasoning": {"type": "string"},
                    "domain": {"type": ["string", "null"]},
                },
            },
        },
    },
}

GAP_PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "layer", "description", "risk", "mutation"],
    "properties": {
        "id": {"type": "string"},
        "layer": {
            "type": "string",
            "enum": [
                "PERCEIVE", "UNDERSTAND", "REASON", "MODEL",
                "SYNTHESIZE", "EXECUTE", "VERIFY", "REMEMBER", "COORDINATE",
            ],
        },
        "description": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "mutation": {"type": "boolean"},
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "suggested_edges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["from", "to", "type"],
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "type": {"type": "string"},
                },
            },
        },
        "reasoning": {"type": "string"},
    },
}

BINDING_GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["steps"],
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["capability", "store_as"],
                "properties": {
                    "capability": {"type": "string"},
                    "store_as": {"type": "string"},
                    "purpose": {"type": "string"},
                    "input_bindings": {"type": "object"},
                    "gates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "when": {"type": "string"},
                                "action": {"type": "string"},
                                "message": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}


# ── Formatting helpers ──────────────────────────────────────────

def _format_capability_list(registry: CapabilityRegistry) -> str:
    """Format all capabilities as compact reference text for LLM context."""
    lines: list[str] = []
    for cap in registry.all_capabilities():
        flags = []
        if cap.mutation:
            flags.append("mutation")
        if cap.requires_checkpoint:
            flags.append("requires_checkpoint")
        if cap.requires_approval:
            flags.append("requires_approval")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        lines.append(
            f"- {cap.id} (layer={cap.layer}, risk={cap.risk}{flag_str}): "
            f"{cap.description}"
        )
    return "\n".join(lines)


def _format_capability_schemas(
    capabilities: list[CapabilityNode],
) -> str:
    """Format capability input/output schemas for binding generation."""
    parts: list[str] = []
    for cap in capabilities:
        io = f"  inputs: {json.dumps(cap.input_schema, indent=2)}" if cap.input_schema else ""
        oo = f"  outputs: {json.dumps(cap.output_schema, indent=2)}" if cap.output_schema else ""
        parts.append(f"- {cap.id}:\n{io}\n{oo}")
    return "\n".join(parts)


def _format_layer_descriptions(registry: CapabilityRegistry) -> str:
    """Format layer names with descriptions for gap proposal context."""
    layers = registry.ontology.get("layers", {})
    lines: list[str] = []
    for name, meta in layers.items():
        desc = meta.get("description", "")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


# ── Prompt builders ─────────────────────────────────────────────

def build_analysis_prompt(
    task_description: str,
    registry: CapabilityRegistry,
    domain: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """
    Build the combined analysis + classification prompt.

    Returns (system_prompt, user_prompt, output_schema).
    """
    cap_list = _format_capability_list(registry)
    domain_note = f"\nDomain context: {domain}" if domain else ""

    system_prompt = f"""\
You are a capability analyst for the Grounded Agency ontology.
Given a task description, decompose it into atomic capability requirements
and map each to the closest ontology capability.

The ontology has {registry.capability_count} capabilities across 9 layers:

{cap_list}

For each requirement you identify:
1. Extract the action verb and target object.
2. Map to the best ontology capability ID with a confidence score (0.0-1.0).
3. If no good match exists (confidence below 0.6), still include it with low confidence.
4. Include the domain parameter if the action applies to a specific domain.

Be thorough: identify ALL atomic actions, including implicit safety steps
(e.g., checkpoint before mutation, audit after changes).

Respond with the exact JSON structure specified."""

    user_prompt = f"Task: {task_description}{domain_note}"

    return system_prompt, user_prompt, ANALYSIS_OUTPUT_SCHEMA


def build_gap_proposal_prompt(
    action: str,
    target: str,
    constraints: list[str],
    nearest_capabilities: list[CapabilityNode],
    registry: CapabilityRegistry,
) -> tuple[str, str, dict[str, Any]]:
    """
    Build a prompt to propose a new capability for an ontology gap.

    Returns (system_prompt, user_prompt, output_schema).
    """
    layer_desc = _format_layer_descriptions(registry)
    nearest_text = "\n".join(
        f"- {c.id} (layer={c.layer}): {c.description}" for c in nearest_capabilities
    )

    system_prompt = f"""\
You are an ontology designer for the Grounded Agency framework.
A task requires a capability not in the current ontology.
Propose a new atomic capability following these conventions:

- ID: kebab-case verb (e.g., "negotiate", "summarize")
- Layer: one of the 9 cognitive layers:
{layer_desc}

- Risk: low (read-only), medium (side effects), high (persistent mutations)
- Input/output schemas: JSON Schema format with required fields
- Suggest edges to related existing capabilities

Respond with the exact JSON structure specified."""

    constraint_text = f"\nConstraints: {', '.join(constraints)}" if constraints else ""
    user_prompt = (
        f"Action: {action}\nTarget: {target}{constraint_text}\n\n"
        f"Nearest existing capabilities:\n{nearest_text}"
    )

    return system_prompt, user_prompt, GAP_PROPOSAL_SCHEMA


def build_binding_prompt(
    ordered_steps: list[dict[str, Any]],
    task_description: str,
    capability_schemas: list[CapabilityNode],
) -> tuple[str, str, dict[str, Any]]:
    """
    Build a prompt to generate data flow bindings between workflow steps.

    Returns (system_prompt, user_prompt, output_schema).
    """
    schema_text = _format_capability_schemas(capability_schemas)
    steps_text = json.dumps(ordered_steps, indent=2)

    system_prompt = f"""\
You are a workflow composer for the Grounded Agency ontology.
Given an ordered list of capability steps and a task description,
generate data flow bindings between steps using ${{ref}} syntax.

Capability schemas:
{schema_text}

For each step, specify:
- input_bindings: ${{ref}} expressions pointing to previous step outputs
- store_as: variable name for this step's output (snake_case)
- purpose: one-sentence description of what this step does
- gates (optional): conditions to skip/stop

Binding syntax: ${{step_store_as.field}} references a previous step's output field.

Respond with the exact JSON structure specified."""

    user_prompt = f"Task: {task_description}\n\nOrdered steps:\n{steps_text}"

    return system_prompt, user_prompt, BINDING_GENERATION_SCHEMA
