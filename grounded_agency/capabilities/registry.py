"""
Capability Ontology Registry

Loads and provides typed access to the capability ontology YAML schema.
Enables querying capabilities, edges, and layers at runtime.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..utils.safe_yaml import ONTOLOGY_MAX_BYTES, safe_yaml_load


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
        """Create CapabilityNode from ontology YAML node."""
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
    edge_type: str  # See spec/EDGE_TYPES.md for all 7 edge types


class CapabilityRegistry:
    """
    Registry for the Grounded Agency capability ontology.

    Loads capability_ontology.yaml and provides methods to query:
    - Individual capabilities by ID
    - Edges (relationships) between capabilities
    - Capabilities by layer
    - High-risk capabilities requiring checkpoints

    Example:
        registry = CapabilityRegistry("schemas/capability_ontology.yaml")
        mutate = registry.get_capability("mutate")
        assert mutate.requires_checkpoint is True
    """

    def __init__(self, ontology_path: str | Path) -> None:
        """
        Initialize the registry.

        Args:
            ontology_path: Path to capability_ontology.yaml
        """
        self._ontology_path = Path(ontology_path)
        self._ontology: dict[str, Any] | None = None
        self._nodes_by_id: dict[str, CapabilityNode] | None = None
        self._edges: list[CapabilityEdge] | None = None
        # Edge indexes for O(1) lookups
        self._outgoing_edges: dict[str, list[CapabilityEdge]] | None = None
        self._incoming_edges: dict[str, list[CapabilityEdge]] | None = None

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
        """Load the ontology YAML from disk.

        SEC-012: Rejects symlinks to prevent path substitution attacks.
        The ontology file must be a regular file, not a symlink.
        """
        if not self._ontology_path.exists():
            raise FileNotFoundError(
                f"Capability ontology not found: {self._ontology_path}"
            )

        # SEC-012: Reject symlinks to prevent ontology substitution
        if self._ontology_path.is_symlink():
            raise ValueError(
                f"SEC-012: Ontology path is a symlink (rejected): {self._ontology_path}"
            )

        ontology: dict[str, Any] = safe_yaml_load(
            self._ontology_path, max_size=ONTOLOGY_MAX_BYTES
        )

        self._ontology = ontology

        # Index nodes by ID for fast lookup
        self._nodes_by_id = {}
        for node_data in ontology.get("nodes", []):
            node = CapabilityNode.from_dict(node_data)
            self._nodes_by_id[node.id] = node

        # Parse edges and build indexes for O(1) lookups
        self._edges = []
        self._outgoing_edges = defaultdict(list)
        self._incoming_edges = defaultdict(list)
        for edge_data in ontology.get("edges", []):
            edge = CapabilityEdge(
                from_cap=edge_data["from"],
                to_cap=edge_data["to"],
                edge_type=edge_data["type"],
            )
            self._edges.append(edge)
            self._outgoing_edges[edge.from_cap].append(edge)
            self._incoming_edges[edge.to_cap].append(edge)

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
        self._ensure_loaded()
        assert self._outgoing_edges is not None
        assert self._incoming_edges is not None
        # Combine outgoing and incoming (may have duplicates if self-referential)
        return list(self._outgoing_edges.get(cap_id, [])) + [
            e
            for e in self._incoming_edges.get(cap_id, [])
            if e.from_cap != cap_id  # Avoid duplicates from self-edges
        ]

    def get_outgoing_edges(self, cap_id: str) -> list[CapabilityEdge]:
        """Get edges originating from a capability."""
        self._ensure_loaded()
        assert self._outgoing_edges is not None
        return list(self._outgoing_edges.get(cap_id, []))

    def get_incoming_edges(self, cap_id: str) -> list[CapabilityEdge]:
        """Get edges pointing to a capability."""
        self._ensure_loaded()
        assert self._incoming_edges is not None
        return list(self._incoming_edges.get(cap_id, []))

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

    def get_preceding_capabilities(self, cap_id: str) -> list[str]:
        """
        Get capabilities that must temporally precede cap_id.

        Returns capabilities connected via 'precedes' edges.

        Args:
            cap_id: Capability identifier

        Returns:
            List of capability IDs that must complete before cap_id
        """
        incoming = self.get_incoming_edges(cap_id)
        return [edge.from_cap for edge in incoming if edge.edge_type == "precedes"]

    def _get_symmetric_edge_targets(self, cap_id: str, edge_type: str) -> list[str]:
        """Get targets of symmetric edges (works regardless of edge direction)."""
        return [
            edge.to_cap if edge.from_cap == cap_id else edge.from_cap
            for edge in self.get_edges(cap_id)
            if edge.edge_type == edge_type
        ]

    def get_conflicting_capabilities(self, cap_id: str) -> list[str]:
        """
        Get capabilities that conflict with cap_id.

        Returns capabilities that cannot coexist in the same workflow.

        Args:
            cap_id: Capability identifier

        Returns:
            List of capability IDs that conflict with cap_id
        """
        return self._get_symmetric_edge_targets(cap_id, "conflicts_with")

    def get_alternatives(self, cap_id: str) -> list[str]:
        """
        Get capabilities that can substitute for cap_id.

        Returns capabilities connected via 'alternative_to' edges.

        Args:
            cap_id: Capability identifier

        Returns:
            List of capability IDs that can substitute for cap_id
        """
        return self._get_symmetric_edge_targets(cap_id, "alternative_to")

    def get_specialized_by(self, cap_id: str) -> list[str]:
        """
        Get capabilities that specialize cap_id.

        Returns more specific variants of this capability.

        Args:
            cap_id: Capability identifier

        Returns:
            List of capability IDs that specialize cap_id
        """
        incoming = self.get_incoming_edges(cap_id)
        return [edge.from_cap for edge in incoming if edge.edge_type == "specializes"]

    def get_generalizes_to(self, cap_id: str) -> str | None:
        """
        Get the capability that cap_id specializes.

        Returns the more general capability, if any.

        Args:
            cap_id: Capability identifier

        Returns:
            Capability ID that cap_id specializes, or None
        """
        outgoing = self.get_outgoing_edges(cap_id)
        for edge in outgoing:
            if edge.edge_type == "specializes":
                return edge.to_cap
        return None

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
            node for node in self._loaded_nodes.values() if node.layer == layer_name
        ]

    def get_high_risk_capabilities(self) -> list[CapabilityNode]:
        """Get all capabilities with risk='high'."""
        return [node for node in self._loaded_nodes.values() if node.risk == "high"]

    def get_checkpoint_required_capabilities(self) -> list[CapabilityNode]:
        """Get all capabilities that require a checkpoint before execution."""
        return [
            node for node in self._loaded_nodes.values() if node.requires_checkpoint
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
