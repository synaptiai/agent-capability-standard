"""
Capability Ontology Registry

Loads and provides typed access to the capability ontology JSON schema.
Enables querying capabilities, edges, and layers at runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CapabilityNode:
    """Represents a single capability from the ontology."""

    id: str
    layer: str
    description: str
    risk: str
    mutation: bool
    requires_checkpoint: bool = False
    requires_approval: bool = False
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityNode:
        """Create CapabilityNode from ontology JSON node."""
        return cls(
            id=data["id"],
            layer=data["layer"],
            description=data.get("description", ""),
            risk=data.get("risk", "low"),
            mutation=data.get("mutation", False),
            requires_checkpoint=data.get("requires_checkpoint", False),
            requires_approval=data.get("requires_approval", False),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
        )


@dataclass(slots=True)
class CapabilityEdge:
    """Represents a relationship between capabilities."""

    from_cap: str
    to_cap: str
    edge_type: str  # "requires", "soft_requires", "enables"


class CapabilityRegistry:
    """
    Registry for the Grounded Agency capability ontology.

    Loads capability_ontology.json and provides methods to query:
    - Individual capabilities by ID
    - Edges (relationships) between capabilities
    - Capabilities by layer
    - High-risk capabilities requiring checkpoints

    Example:
        registry = CapabilityRegistry("schemas/capability_ontology.json")
        mutate = registry.get_capability("mutate")
        assert mutate.requires_checkpoint is True
    """

    def __init__(self, ontology_path: str | Path) -> None:
        """
        Initialize the registry.

        Args:
            ontology_path: Path to capability_ontology.json
        """
        self._ontology_path = Path(ontology_path)
        self._ontology: dict[str, Any] | None = None
        self._nodes_by_id: dict[str, CapabilityNode] | None = None
        self._edges: list[CapabilityEdge] | None = None

    def _ensure_loaded(self) -> None:
        """Ensure ontology is loaded. Call before accessing data."""
        if self._ontology is None:
            self._load_ontology()

    @property
    def _loaded_ontology(self) -> dict[str, Any]:
        """Get ontology with guaranteed loading. Internal use."""
        self._ensure_loaded()
        assert self._ontology is not None
        return self._ontology

    @property
    def _loaded_nodes(self) -> dict[str, CapabilityNode]:
        """Get nodes dict with guaranteed loading. Internal use."""
        self._ensure_loaded()
        assert self._nodes_by_id is not None
        return self._nodes_by_id

    @property
    def _loaded_edges(self) -> list[CapabilityEdge]:
        """Get edges list with guaranteed loading. Internal use."""
        self._ensure_loaded()
        assert self._edges is not None
        return self._edges

    @property
    def ontology(self) -> dict[str, Any]:
        """Lazy-load and return the raw ontology data."""
        return self._loaded_ontology

    def _load_ontology(self) -> None:
        """Load the ontology JSON from disk."""
        if not self._ontology_path.exists():
            raise FileNotFoundError(
                f"Capability ontology not found: {self._ontology_path}"
            )

        with open(self._ontology_path, encoding="utf-8") as f:
            ontology: dict[str, Any] = json.load(f)

        self._ontology = ontology

        # Index nodes by ID for fast lookup
        self._nodes_by_id = {}
        for node_data in ontology.get("nodes", []):
            node = CapabilityNode.from_dict(node_data)
            self._nodes_by_id[node.id] = node

        # Parse edges
        self._edges = [
            CapabilityEdge(
                from_cap=edge["from"],
                to_cap=edge["to"],
                edge_type=edge["type"],
            )
            for edge in ontology.get("edges", [])
        ]

    def get_capability(self, cap_id: str) -> CapabilityNode | None:
        """
        Get a capability by its ID.

        Args:
            cap_id: Capability identifier (e.g., "mutate", "checkpoint")

        Returns:
            CapabilityNode or None if not found
        """
        return self._loaded_nodes.get(cap_id)

    def get_edges(self, cap_id: str) -> list[CapabilityEdge]:
        """
        Get all edges involving a capability.

        Args:
            cap_id: Capability identifier

        Returns:
            List of edges where cap_id is source or target
        """
        return [
            edge
            for edge in self._loaded_edges
            if edge.from_cap == cap_id or edge.to_cap == cap_id
        ]

    def get_outgoing_edges(self, cap_id: str) -> list[CapabilityEdge]:
        """Get edges originating from a capability."""
        return [edge for edge in self._loaded_edges if edge.from_cap == cap_id]

    def get_incoming_edges(self, cap_id: str) -> list[CapabilityEdge]:
        """Get edges pointing to a capability."""
        return [edge for edge in self._loaded_edges if edge.to_cap == cap_id]

    def get_required_capabilities(self, cap_id: str) -> list[str]:
        """
        Get capabilities that must be satisfied before using cap_id.

        Only returns 'requires' edges, not 'soft_requires'.

        Args:
            cap_id: Capability identifier

        Returns:
            List of capability IDs that are hard requirements
        """
        incoming = self.get_incoming_edges(cap_id)
        return [edge.from_cap for edge in incoming if edge.edge_type == "requires"]

    def get_layer(self, layer_name: str) -> dict[str, Any]:
        """
        Get layer metadata.

        Args:
            layer_name: Layer identifier (e.g., "VERIFY", "EXECUTE")

        Returns:
            Layer metadata dict or empty dict if not found
        """
        layers: dict[str, Any] = self.ontology.get("layers", {})
        result: dict[str, Any] = layers.get(layer_name, {})
        return result

    def get_capabilities_in_layer(self, layer_name: str) -> list[CapabilityNode]:
        """
        Get all capabilities belonging to a layer.

        Args:
            layer_name: Layer identifier

        Returns:
            List of CapabilityNode objects in that layer
        """
        return [
            node
            for node in self._loaded_nodes.values()
            if node.layer == layer_name
        ]

    def get_high_risk_capabilities(self) -> list[CapabilityNode]:
        """Get all capabilities with risk='high'."""
        return [
            node for node in self._loaded_nodes.values() if node.risk == "high"
        ]

    def get_checkpoint_required_capabilities(self) -> list[CapabilityNode]:
        """Get all capabilities that require a checkpoint before execution."""
        return [
            node
            for node in self._loaded_nodes.values()
            if node.requires_checkpoint
        ]

    def all_capabilities(self) -> list[CapabilityNode]:
        """Get all capabilities in the ontology."""
        return list(self._loaded_nodes.values())

    @property
    def version(self) -> str:
        """Get ontology version."""
        meta: dict[str, Any] = self._loaded_ontology.get("meta", {})
        version: str = meta.get("version", "unknown")
        return version

    @property
    def capability_count(self) -> int:
        """Get total number of capabilities."""
        return len(self._loaded_nodes)
