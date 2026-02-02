"""
Agent Registry

Registration and discovery of agents in a multi-agent coordination
runtime.  Each agent declares a set of ontology capabilities it can
fulfil; the registry validates these against ``CapabilityRegistry``
at registration time and supports discovery by capability.
"""

from __future__ import annotations

import logging
import threading
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..capabilities.registry import CapabilityRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    """Describes a registered agent and its declared capabilities.

    Attributes:
        agent_id: Unique identifier for the agent.
        capabilities: Ontology capability IDs this agent can perform.
        trust_score: Trust level in [0.0, 1.0].
        metadata: Arbitrary extra info (model name, version, etc.).
        registered_at: ISO 8601 UTC timestamp of registration.
    """

    agent_id: str
    capabilities: frozenset[str]
    trust_score: float = 1.0
    metadata: types.MappingProxyType | dict[str, Any] = field(
        default_factory=lambda: types.MappingProxyType({})
    )
    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if not 0.0 <= self.trust_score <= 1.0:
            raise ValueError(
                f"trust_score must be in [0.0, 1.0], got {self.trust_score}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON export."""
        return {
            "agent_id": self.agent_id,
            "capabilities": sorted(self.capabilities),
            "trust_score": self.trust_score,
            "metadata": dict(self.metadata),
            "registered_at": self.registered_at,
        }


class AgentRegistry:
    """Registry for multi-agent coordination.

    Lock order: 1 (highest priority -- acquired first).

    Thread-safe.  Validates declared capabilities against the
    ``CapabilityRegistry`` so only ontology-defined capabilities
    can be claimed.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        max_agents: int = 1000,
    ) -> None:
        self._cap_registry = capability_registry
        self._max_agents = max_agents
        self._agents: dict[str, AgentDescriptor] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        agent_id: str,
        capabilities: set[str] | frozenset[str] | list[str],
        trust_score: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> AgentDescriptor:
        """Register an agent, validating its capabilities against the ontology.

        Raises ``ValueError`` if any declared capability is unknown.
        """
        caps = frozenset(capabilities)

        # Validate every declared capability exists in ontology
        unknown = [c for c in caps if self._cap_registry.get_capability(c) is None]
        if unknown:
            raise ValueError(f"Unknown capabilities not in ontology: {sorted(unknown)}")

        descriptor = AgentDescriptor(
            agent_id=agent_id,
            capabilities=caps,
            trust_score=trust_score,
            metadata=types.MappingProxyType(dict(metadata) if metadata else {}),
        )
        with self._lock:
            if (
                len(self._agents) >= self._max_agents
                and descriptor.agent_id not in self._agents
            ):
                raise ValueError(
                    f"Agent registry is full ({self._max_agents} agents)"
                )
            self._agents[descriptor.agent_id] = descriptor
        logger.debug("Registered agent %s with capabilities %s", agent_id, caps)
        return descriptor

    def unregister(self, agent_id: str) -> bool:
        """Remove an agent.  Returns True if the agent existed."""
        with self._lock:
            return self._agents.pop(agent_id, None) is not None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> AgentDescriptor | None:
        """Look up an agent by ID."""
        with self._lock:
            return self._agents.get(agent_id)

    def discover_by_capability(self, capability_id: str) -> list[AgentDescriptor]:
        """Find agents that declare a single capability, ordered by trust."""
        with self._lock:
            matches = [
                a for a in self._agents.values() if capability_id in a.capabilities
            ]
        matches.sort(key=lambda a: a.trust_score, reverse=True)
        return matches

    def discover_by_capabilities(
        self,
        capability_ids: set[str] | frozenset[str] | list[str],
    ) -> list[AgentDescriptor]:
        """Find agents that declare *all* of the given capabilities."""
        required = frozenset(capability_ids)
        with self._lock:
            matches = [a for a in self._agents.values() if required <= a.capabilities]
        matches.sort(key=lambda a: a.trust_score, reverse=True)
        return matches

    def list_agents(self) -> list[AgentDescriptor]:
        """Return all registered agents."""
        with self._lock:
            return list(self._agents.values())

    @property
    def agent_count(self) -> int:
        with self._lock:
            return len(self._agents)
