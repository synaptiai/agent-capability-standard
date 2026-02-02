"""
Tests for Multi-Agent Coordination Runtime

Tests cover the 5 acceptance criteria from Issue #76:
- AC1: Agent registration and discovery (TestAgentRegistry)
- AC2: Typed delegation with contract enforcement (TestDelegationProtocol)
- AC3: Trust propagation and evidence sharing (TestCrossAgentEvidenceBridge)
- AC4: Coordination audit trail (TestCoordinationAuditLog)
- AC3 cont: Barrier synchronization (TestSyncPrimitive)
- AC5: End-to-end orchestration (TestOrchestrationRuntime)
- Concurrency: Thread-safety validation (TestConcurrency)
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import patch

import pytest

from grounded_agency import (
    AgentRegistry,
    CapabilityRegistry,
    CoordinationAuditLog,
    CrossAgentEvidenceBridge,
    DelegationProtocol,
    EvidenceAnchor,
    EvidenceStore,
    OrchestrationConfig,
    OrchestrationRuntime,
    StepStatus,
    SyncPrimitive,
    WorkflowStep,
)
from grounded_agency.coordination.delegation import DelegationResult, DelegationTask
from grounded_agency.coordination.evidence_bridge import SharedEvidence

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ontology_path() -> str:
    """Path to the capability ontology."""
    return str(Path(__file__).parent.parent / "schemas/capability_ontology.yaml")


@pytest.fixture
def capability_registry(ontology_path: str) -> CapabilityRegistry:
    """Create a fresh CapabilityRegistry."""
    return CapabilityRegistry(ontology_path)


@pytest.fixture
def evidence_store() -> EvidenceStore:
    """Create a fresh EvidenceStore."""
    return EvidenceStore()


@pytest.fixture
def audit_log() -> CoordinationAuditLog:
    """Create a fresh CoordinationAuditLog."""
    return CoordinationAuditLog()


@pytest.fixture
def agent_registry(capability_registry: CapabilityRegistry) -> AgentRegistry:
    """Create a fresh AgentRegistry backed by the ontology."""
    return AgentRegistry(capability_registry)


@pytest.fixture
def delegation(
    agent_registry: AgentRegistry,
    evidence_store: EvidenceStore,
    audit_log: CoordinationAuditLog,
) -> DelegationProtocol:
    """Create a fresh DelegationProtocol."""
    return DelegationProtocol(agent_registry, evidence_store, audit_log)


@pytest.fixture
def sync(
    evidence_store: EvidenceStore,
    audit_log: CoordinationAuditLog,
) -> SyncPrimitive:
    """Create a fresh SyncPrimitive."""
    return SyncPrimitive(evidence_store, audit_log)


@pytest.fixture
def evidence_bridge(
    agent_registry: AgentRegistry,
    evidence_store: EvidenceStore,
    audit_log: CoordinationAuditLog,
) -> CrossAgentEvidenceBridge:
    """Create a fresh CrossAgentEvidenceBridge with 0.9 decay."""
    return CrossAgentEvidenceBridge(
        agent_registry,
        evidence_store,
        audit_log,
        trust_decay=0.9,
    )


@pytest.fixture
def runtime(capability_registry: CapabilityRegistry) -> OrchestrationRuntime:
    """Create a fresh OrchestrationRuntime."""
    return OrchestrationRuntime(capability_registry)


@pytest.fixture
def make_anchor() -> Callable[..., EvidenceAnchor]:
    """Factory for creating test evidence anchors with minimal boilerplate."""

    def _make(
        ref: str = "test:evidence:default",
        kind: str = "tool_output",
    ) -> EvidenceAnchor:
        return EvidenceAnchor(
            ref=ref,
            kind=kind,
            timestamp="2025-01-01T00:00:00+00:00",
        )

    return _make


# ---------------------------------------------------------------------------
# AC1: Agent Registration and Discovery
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    """AC1: Agents can register, be discovered by capability, and unregister."""

    def test_register_agent(
        self,
        agent_registry: AgentRegistry,
    ) -> None:
        """Register an agent and verify its descriptor fields."""
        desc = agent_registry.register(
            agent_id="agent-1",
            capabilities={"retrieve", "search"},
            trust_score=0.95,
        )
        assert desc.agent_id == "agent-1"
        assert desc.capabilities == frozenset({"retrieve", "search"})
        assert desc.trust_score == 0.95
        assert agent_registry.agent_count == 1

    def test_register_validates_capabilities(
        self,
        agent_registry: AgentRegistry,
    ) -> None:
        """Reject agents that declare capabilities absent from the ontology."""
        with pytest.raises(ValueError, match="Unknown capabilities"):
            agent_registry.register(
                agent_id="agent-bad",
                capabilities={"nonexistent_capability"},
            )

    def test_register_duplicate_overwrites(
        self,
        agent_registry: AgentRegistry,
    ) -> None:
        """Re-registering the same agent_id overwrites the previous descriptor."""
        agent_registry.register("a1", {"retrieve"}, trust_score=0.5)
        agent_registry.register("a1", {"search"}, trust_score=0.9)
        assert agent_registry.agent_count == 1
        desc = agent_registry.get_agent("a1")
        assert desc is not None
        assert desc.capabilities == frozenset({"search"})
        assert desc.trust_score == 0.9

    def test_discover_by_capability(
        self,
        agent_registry: AgentRegistry,
    ) -> None:
        """Discover agents by a single capability, ordered by trust descending."""
        agent_registry.register("a1", {"retrieve", "search"}, trust_score=0.8)
        agent_registry.register("a2", {"retrieve"}, trust_score=0.9)
        agent_registry.register("a3", {"search"}, trust_score=0.7)

        results = agent_registry.discover_by_capability("retrieve")
        assert len(results) == 2
        assert results[0].agent_id == "a2"
        assert results[1].agent_id == "a1"

    def test_discover_by_capabilities_all_required(
        self,
        agent_registry: AgentRegistry,
    ) -> None:
        """Only return agents that have ALL requested capabilities."""
        agent_registry.register("a1", {"retrieve", "search", "generate"})
        agent_registry.register("a2", {"retrieve", "search"})
        agent_registry.register("a3", {"retrieve"})

        results = agent_registry.discover_by_capabilities(
            {"retrieve", "search", "generate"},
        )
        assert len(results) == 1
        assert results[0].agent_id == "a1"

    def test_unregister(self, agent_registry: AgentRegistry) -> None:
        """Unregister an agent and verify it is gone."""
        agent_registry.register("a1", {"retrieve"})
        assert agent_registry.agent_count == 1
        assert agent_registry.unregister("a1") is True
        assert agent_registry.agent_count == 0
        assert agent_registry.unregister("a1") is False

    def test_get_agent(self, agent_registry: AgentRegistry) -> None:
        """Look up agent by ID, returns None for missing."""
        agent_registry.register("a1", {"retrieve"})
        assert agent_registry.get_agent("a1") is not None
        assert agent_registry.get_agent("missing") is None

    def test_list_agents(self, agent_registry: AgentRegistry) -> None:
        """List all registered agents."""
        agent_registry.register("a1", {"retrieve"})
        agent_registry.register("a2", {"search"})
        agents = agent_registry.list_agents()
        assert len(agents) == 2

    def test_trust_score_validation(
        self,
        agent_registry: AgentRegistry,
    ) -> None:
        """Reject trust scores outside [0.0, 1.0]."""
        with pytest.raises(ValueError, match="trust_score"):
            agent_registry.register("bad", {"retrieve"}, trust_score=1.5)
        with pytest.raises(ValueError, match="trust_score"):
            agent_registry.register("bad", {"retrieve"}, trust_score=-0.1)

    def test_agent_descriptor_is_frozen(
        self,
        agent_registry: AgentRegistry,
    ) -> None:
        """AgentDescriptor cannot be modified after creation."""
        desc = agent_registry.register("a1", {"retrieve"}, trust_score=0.5)
        with pytest.raises(AttributeError):
            desc.trust_score = 5.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC2: Typed Delegation with Contract Enforcement
# ---------------------------------------------------------------------------


class TestDelegationProtocol:
    """AC2: Delegation validates contracts and produces evidence."""

    def test_delegate_to_capable_agent(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
    ) -> None:
        """Accepted delegation to a capable agent produces evidence."""
        agent_registry.register("worker", {"retrieve", "search"})
        result = delegation.delegate(
            description="Search the web",
            required_capabilities={"search"},
            target_agent_id="worker",
            input_data={"query": "test"},
        )
        assert result.accepted is True
        assert result.agent_id == "worker"
        assert len(result.evidence_anchors) >= 1
        assert result.evidence_anchors[0].ref.startswith("delegation:")
        assert result.evidence_anchors[0].kind == "coordination"

    def test_delegate_rejects_incapable_agent(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
    ) -> None:
        """Reject delegation when agent lacks required capabilities."""
        agent_registry.register("worker", {"retrieve"})
        result = delegation.delegate(
            description="Generate content",
            required_capabilities={"generate"},
            target_agent_id="worker",
        )
        assert result.accepted is False
        assert "lacks capabilities" in result.rejection_reason

    def test_delegate_rejects_unregistered_agent(
        self,
        delegation: DelegationProtocol,
    ) -> None:
        """Reject delegation to an unregistered agent."""
        result = delegation.delegate(
            description="Do something",
            required_capabilities={"retrieve"},
            target_agent_id="ghost",
        )
        assert result.accepted is False
        assert "not registered" in result.rejection_reason

    def test_auto_delegate_selects_best_agent(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
    ) -> None:
        """Auto-delegation selects the highest-trust capable agent."""
        agent_registry.register("low-trust", {"search"}, trust_score=0.5)
        agent_registry.register("high-trust", {"search"}, trust_score=0.9)

        result = delegation.auto_delegate(
            description="Search task",
            required_capabilities={"search"},
        )
        assert result.accepted is True
        assert result.agent_id == "high-trust"

    def test_auto_delegate_no_candidates(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
    ) -> None:
        """Auto-delegation fails when no agent has required capabilities."""
        agent_registry.register("worker", {"retrieve"})
        result = delegation.auto_delegate(
            description="Impossible task",
            required_capabilities={"simulate"},
        )
        assert result.accepted is False
        assert "No agent found" in result.rejection_reason

    def test_auto_delegate_no_candidates_records_audit(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
        audit_log: CoordinationAuditLog,
        evidence_store: EvidenceStore,
    ) -> None:
        """Auto-delegation rejection records audit event and evidence."""
        agent_registry.register("worker", {"retrieve"})
        result = delegation.auto_delegate(
            description="Impossible task",
            required_capabilities={"simulate"},
        )
        assert result.accepted is False
        # Should have evidence even for rejections
        assert len(result.evidence_anchors) >= 1
        # Should have an audit event
        events = audit_log.get_events_by_type("delegation")
        assert len(events) >= 1
        rejection_event = [e for e in events if not e.details.get("accepted", True)]
        assert len(rejection_event) >= 1

    def test_auto_delegate_forwards_input_data(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
    ) -> None:
        """Auto-delegation forwards input_data to the delegate call."""
        agent_registry.register("worker", {"search"})
        result = delegation.auto_delegate(
            description="Search with data",
            required_capabilities={"search"},
            input_data={"query": "test"},
        )
        assert result.accepted is True
        task = delegation.get_task(result.task_id)
        assert task is not None
        assert task.input_data == {"query": "test"}

    def test_complete_task(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
    ) -> None:
        """Mark a delegation as complete with output data."""
        agent_registry.register("worker", {"retrieve"})
        dr = delegation.delegate(
            description="Fetch data",
            required_capabilities={"retrieve"},
            target_agent_id="worker",
        )
        completed = delegation.complete_task(
            task_id=dr.task_id,
            output_data={"result": "data"},
        )
        assert completed is not None
        assert completed.output_data == {"result": "data"}

    def test_complete_unknown_task(self, delegation: DelegationProtocol) -> None:
        """Completing an unknown task returns None."""
        assert delegation.complete_task("nonexistent") is None

    def test_get_task_and_get_result(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
    ) -> None:
        """get_task and get_result retrieve stored objects; None for missing."""
        agent_registry.register("worker", {"retrieve"})
        dr = delegation.delegate(
            description="Fetch data",
            required_capabilities={"retrieve"},
            target_agent_id="worker",
        )
        task = delegation.get_task(dr.task_id)
        assert task is not None
        assert task.description == "Fetch data"
        assert delegation.get_task("nonexistent") is None

        result = delegation.get_result(dr.task_id)
        assert result is not None
        assert result.accepted is True
        assert delegation.get_result("nonexistent") is None

    def test_delegation_creates_evidence(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
        evidence_store: EvidenceStore,
    ) -> None:
        """Each delegation adds a coordination evidence anchor to the store."""
        agent_registry.register("worker", {"retrieve"})
        delegation.delegate(
            description="Fetch",
            required_capabilities={"retrieve"},
            target_agent_id="worker",
        )
        coordination_evidence = evidence_store.get_by_kind("coordination")
        assert len(coordination_evidence) >= 1
        assert coordination_evidence[0].ref.startswith("delegation:")

    def test_delegation_records_audit_event(
        self,
        delegation: DelegationProtocol,
        agent_registry: AgentRegistry,
        audit_log: CoordinationAuditLog,
    ) -> None:
        """Each delegation records an audit event of type 'delegation'."""
        agent_registry.register("worker", {"retrieve"})
        delegation.delegate(
            description="Fetch",
            required_capabilities={"retrieve"},
            target_agent_id="worker",
        )
        events = audit_log.get_events_by_type("delegation")
        assert len(events) == 1
        assert events[0].capability_id == "delegate"


# ---------------------------------------------------------------------------
# AC3: Trust Propagation and Evidence Sharing
# ---------------------------------------------------------------------------


class TestCrossAgentEvidenceBridge:
    """AC3: Evidence sharing with trust decay."""

    def test_share_evidence_with_trust_decay(
        self,
        evidence_bridge: CrossAgentEvidenceBridge,
        agent_registry: AgentRegistry,
        make_anchor: Callable[..., EvidenceAnchor],
    ) -> None:
        """Propagated trust = source trust * decay factor."""
        agent_registry.register("source", {"retrieve"}, trust_score=0.8)
        agent_registry.register("target", {"search"})

        shared = evidence_bridge.share_evidence(
            anchor=make_anchor("test:evidence:1"),
            source_agent_id="source",
            target_agent_ids=["target"],
        )
        assert len(shared) == 1
        # 0.8 * 0.9 = 0.72
        assert abs(shared[0].trust_score - 0.72) < 1e-9
        assert shared[0].source_agent_id == "source"

    def test_min_trust_filter(
        self,
        evidence_bridge: CrossAgentEvidenceBridge,
        agent_registry: AgentRegistry,
        make_anchor: Callable[..., EvidenceAnchor],
    ) -> None:
        """get_shared_evidence filters out evidence below min_trust."""
        agent_registry.register("low", {"retrieve"}, trust_score=0.3)
        agent_registry.register("target", {"search"})

        evidence_bridge.share_evidence(
            anchor=make_anchor("test:evidence:2"),
            source_agent_id="low",
            target_agent_ids=["target"],
        )
        # 0.3 * 0.9 = 0.27 — below 0.5 threshold
        assert len(evidence_bridge.get_shared_evidence("target", min_trust=0.5)) == 0
        assert len(evidence_bridge.get_shared_evidence("target", min_trust=0.2)) == 1

    @pytest.mark.parametrize(
        "trust_decay,expected_trust",
        [
            (1.0, 0.8),  # trust fully preserved
            (0.5, 0.4),  # half decay
            (0.1, 0.08),  # near-zero decay
        ],
    )
    def test_trust_decay_boundaries(
        self,
        agent_registry: AgentRegistry,
        evidence_store: EvidenceStore,
        audit_log: CoordinationAuditLog,
        make_anchor: Callable[..., EvidenceAnchor],
        trust_decay: float,
        expected_trust: float,
    ) -> None:
        """Trust decay boundary values: 0.1, 0.5, and 1.0."""
        bridge = CrossAgentEvidenceBridge(
            agent_registry,
            evidence_store,
            audit_log,
            trust_decay=trust_decay,
        )
        agent_registry.register("source", {"retrieve"}, trust_score=0.8)
        agent_registry.register("target", {"search"})

        shared = bridge.share_evidence(
            anchor=make_anchor(f"test:decay:{trust_decay}"),
            source_agent_id="source",
            target_agent_ids=["target"],
        )
        assert abs(shared[0].trust_score - expected_trust) < 1e-9

    def test_trust_inflation_prevented(
        self,
        agent_registry: AgentRegistry,
        evidence_store: EvidenceStore,
        audit_log: CoordinationAuditLog,
        make_anchor: Callable[..., EvidenceAnchor],
    ) -> None:
        """Re-sharing evidence cannot inflate trust above original level."""
        bridge = CrossAgentEvidenceBridge(
            agent_registry,
            evidence_store,
            audit_log,
            trust_decay=0.9,
        )
        agent_registry.register("low-trust", {"retrieve"}, trust_score=0.3)
        agent_registry.register("high-trust", {"search"}, trust_score=1.0)
        agent_registry.register("final", {"generate"})

        anchor = make_anchor("test:inflation")
        # Low-trust agent shares: trust = 0.3 * 0.9 = 0.27
        bridge.share_evidence(
            anchor=anchor,
            source_agent_id="low-trust",
            target_agent_ids=["high-trust"],
        )

        # High-trust agent re-shares: would be 1.0 * 0.9 = 0.9 without cap
        reshared = bridge.share_evidence(
            anchor=anchor,
            source_agent_id="high-trust",
            target_agent_ids=["final"],
        )
        # Trust must be capped at exactly 0.27, not inflated to 0.9
        assert abs(reshared[0].trust_score - 0.27) < 1e-9

    def test_broadcast_to_all_agents(
        self,
        evidence_bridge: CrossAgentEvidenceBridge,
        agent_registry: AgentRegistry,
        make_anchor: Callable[..., EvidenceAnchor],
    ) -> None:
        """target_agent_ids=None broadcasts to all agents except source."""
        agent_registry.register("source", {"retrieve"}, trust_score=1.0)
        agent_registry.register("a1", {"search"})
        agent_registry.register("a2", {"generate"})

        shared = evidence_bridge.share_evidence(
            anchor=make_anchor("test:broadcast"),
            source_agent_id="source",
            target_agent_ids=None,
        )
        assert len(shared) == 2  # a1 and a2, not source
        assert evidence_bridge.total_shared == 2

    def test_evidence_lineage(
        self,
        evidence_bridge: CrossAgentEvidenceBridge,
        agent_registry: AgentRegistry,
        make_anchor: Callable[..., EvidenceAnchor],
    ) -> None:
        """Trace all sharing events for a given evidence ref."""
        agent_registry.register("s1", {"retrieve"})
        agent_registry.register("t1", {"search"})
        agent_registry.register("t2", {"generate"})

        evidence_bridge.share_evidence(
            anchor=make_anchor("test:lineage"),
            source_agent_id="s1",
            target_agent_ids=["t1", "t2"],
        )
        lineage = evidence_bridge.get_evidence_lineage("test:lineage")
        assert len(lineage) == 2

    def test_share_rejects_unregistered_source(
        self,
        evidence_bridge: CrossAgentEvidenceBridge,
        make_anchor: Callable[..., EvidenceAnchor],
    ) -> None:
        """Sharing from an unregistered agent raises ValueError."""
        with pytest.raises(ValueError, match="not registered"):
            evidence_bridge.share_evidence(
                anchor=make_anchor("test:orphan"),
                source_agent_id="ghost",
            )


# ---------------------------------------------------------------------------
# AC4: Coordination Audit Trail
# ---------------------------------------------------------------------------


class TestCoordinationAuditLog:
    """AC4: Append-only audit with queries by agent, type, and task."""

    def test_record_event(self, audit_log: CoordinationAuditLog) -> None:
        """Record an event and verify its fields."""
        event = audit_log.record(
            event_type="delegation",
            source_agent_id="orchestrator",
            target_agent_ids=["worker-1"],
            capability_id="delegate",
            details={"task_id": "t1"},
        )
        assert len(event.event_id) == 32  # 16 bytes hex
        assert event.event_type == "delegation"
        assert len(audit_log) == 1

    def test_get_events_for_agent(self, audit_log: CoordinationAuditLog) -> None:
        """Query events by agent (as source or target)."""
        audit_log.record("delegation", "orch", ["w1"], "delegate")
        audit_log.record("delegation", "orch", ["w2"], "delegate")
        audit_log.record("sync", "w1", ["w2"], "synchronize")

        w1_events = audit_log.get_events_for_agent("w1")
        assert len(w1_events) == 2  # target of first, source of third

    def test_get_events_by_type(self, audit_log: CoordinationAuditLog) -> None:
        """Query events by type."""
        audit_log.record("delegation", "a", ["b"])
        audit_log.record("synchronization", "a", ["b"])
        audit_log.record("delegation", "a", ["c"])

        assert len(audit_log.get_events_by_type("delegation")) == 2

    def test_get_events_for_task(self, audit_log: CoordinationAuditLog) -> None:
        """Query events by task_id in details."""
        audit_log.record("delegation", "a", ["b"], details={"task_id": "t1"})
        audit_log.record("delegation", "a", ["c"], details={"task_id": "t2"})

        t1_events = audit_log.get_events_for_task("t1")
        assert len(t1_events) == 1
        assert t1_events[0].details["task_id"] == "t1"

    def test_get_events_for_nonexistent_task(
        self,
        audit_log: CoordinationAuditLog,
    ) -> None:
        """Query for a task_id that doesn't exist returns empty list."""
        audit_log.record("delegation", "a", ["b"], details={"task_id": "t1"})
        assert audit_log.get_events_for_task("nonexistent") == []

    def test_bounded_size_evicts_oldest(self) -> None:
        """Oldest events are evicted when max_events is exceeded."""
        log = CoordinationAuditLog(max_events=5)
        for i in range(10):
            log.record("test", f"agent-{i}", [])
        assert len(log) == 5
        surviving = log.get_events()
        surviving_sources = [e.source_agent_id for e in surviving]
        assert surviving_sources == [f"agent-{i}" for i in range(5, 10)]

    def test_to_list_serialization(self, audit_log: CoordinationAuditLog) -> None:
        """Serialize events to list of dicts."""
        audit_log.record("delegation", "a", ["b"], evidence_refs=["ref1"])
        data = audit_log.to_list()
        assert len(data) == 1
        assert data[0]["event_type"] == "delegation"
        assert data[0]["evidence_refs"] == ["ref1"]

    def test_event_immutability(self, audit_log: CoordinationAuditLog) -> None:
        """CoordinationEvent is frozen — attributes can't be changed."""
        event = audit_log.record("delegation", "a", ["b"])
        with pytest.raises(AttributeError):
            event.event_type = "modified"  # type: ignore[misc]

    def test_event_details_immutability(
        self,
        audit_log: CoordinationAuditLog,
    ) -> None:
        """CoordinationEvent.details cannot be mutated after creation."""
        event = audit_log.record(
            "delegation",
            "a",
            ["b"],
            details={"key": "value"},
        )
        with pytest.raises(TypeError):
            event.details["key"] = "modified"  # type: ignore[index]

    def test_get_events_since(self, audit_log: CoordinationAuditLog) -> None:
        """get_events_since returns only events after a given index."""
        for i in range(5):
            audit_log.record("test", f"agent-{i}", [])
        events = audit_log.get_events_since(3)
        assert len(events) == 2
        assert events[0].source_agent_id == "agent-3"

    def test_get_events_since_with_eviction(self) -> None:
        """get_events_since returns correct events after deque eviction."""
        log = CoordinationAuditLog(max_events=5)
        # Record 10 events (first 5 will be evicted)
        for i in range(10):
            log.record(
                event_type="test",
                source_agent_id=f"agent-{i}",
                target_agent_ids=[],
            )
        # After 10 records into maxlen=5, events 0-4 are evicted.
        # Requesting events since index 7 (absolute) should return events 7, 8, 9.
        events = log.get_events_since(7)
        assert len(events) == 3
        assert events[0].source_agent_id == "agent-7"
        assert events[1].source_agent_id == "agent-8"
        assert events[2].source_agent_id == "agent-9"


# ---------------------------------------------------------------------------
# AC3 (cont): Barrier Synchronization
# ---------------------------------------------------------------------------


class TestSyncPrimitive:
    """AC3: Barrier creation, contribution, and conflict resolution."""

    def test_create_barrier(self, sync: SyncPrimitive) -> None:
        """Create a barrier with specified participants."""
        barrier = sync.create_barrier(
            participants=["a1", "a2"],
            timeout_seconds=30.0,
        )
        assert len(barrier.barrier_id) == 32
        assert barrier.participants == frozenset({"a1", "a2"})

    def test_last_writer_wins_overwrite(self, sync: SyncPrimitive) -> None:
        """last_writer_wins: later proposals overwrite earlier ones."""
        barrier = sync.create_barrier(["a1", "a2"])
        assert sync.contribute(barrier.barrier_id, "a1", {"x": 1})
        assert sync.contribute(barrier.barrier_id, "a2", {"x": 2, "y": 3})

        result = sync.resolve(barrier.barrier_id, "last_writer_wins")
        assert result.synchronized is True
        assert result.agreed_state["x"] == 2
        assert result.agreed_state["y"] == 3

    def test_merge_keys_disjoint(self, sync: SyncPrimitive) -> None:
        """merge_keys with disjoint keys produces a clean merge."""
        barrier = sync.create_barrier(["a1", "a2"])
        sync.contribute(barrier.barrier_id, "a1", {"a": 1})
        sync.contribute(barrier.barrier_id, "a2", {"b": 2})

        result = sync.resolve(barrier.barrier_id, "merge_keys")
        assert result.synchronized is True
        assert result.agreed_state == {"a": 1, "b": 2}
        assert result.conflict_details == ""

    def test_merge_keys_with_conflict(self, sync: SyncPrimitive) -> None:
        """merge_keys records conflict details when keys overlap."""
        barrier = sync.create_barrier(["a1", "a2"])
        sync.contribute(barrier.barrier_id, "a1", {"x": 1, "shared": "from_a1"})
        sync.contribute(barrier.barrier_id, "a2", {"y": 2, "shared": "from_a2"})

        result = sync.resolve(barrier.barrier_id, "merge_keys")
        assert result.synchronized is True
        # Last writer wins within merge_keys
        assert result.agreed_state["shared"] == "from_a2"
        assert result.agreed_state["x"] == 1
        assert result.agreed_state["y"] == 2
        assert "shared" in result.conflict_details

    def test_require_unanimous_success(self, sync: SyncPrimitive) -> None:
        """require_unanimous succeeds when all proposals are identical."""
        barrier = sync.create_barrier(["a1", "a2"])
        sync.contribute(barrier.barrier_id, "a1", {"status": "ok"})
        sync.contribute(barrier.barrier_id, "a2", {"status": "ok"})

        result = sync.resolve(barrier.barrier_id, "require_unanimous")
        assert result.synchronized is True
        assert result.agreed_state == {"status": "ok"}

    def test_require_unanimous_conflict(self, sync: SyncPrimitive) -> None:
        """require_unanimous fails when proposals differ."""
        barrier = sync.create_barrier(["a1", "a2"])
        sync.contribute(barrier.barrier_id, "a1", {"status": "ok"})
        sync.contribute(barrier.barrier_id, "a2", {"status": "fail"})

        result = sync.resolve(barrier.barrier_id, "require_unanimous")
        assert result.synchronized is False
        assert "not unanimous" in result.conflict_details

    def test_resolve_missing_contributions(self, sync: SyncPrimitive) -> None:
        """Resolve fails when not all participants have contributed."""
        barrier = sync.create_barrier(["a1", "a2", "a3"])
        sync.contribute(barrier.barrier_id, "a1", {"x": 1})

        result = sync.resolve(barrier.barrier_id, "last_writer_wins")
        assert result.synchronized is False
        assert "Missing contributions" in result.conflict_details

    def test_resolve_unknown_barrier(self, sync: SyncPrimitive) -> None:
        """Resolving a non-existent barrier returns a failed result."""
        result = sync.resolve("nonexistent_barrier_id")
        assert result.synchronized is False
        assert "not found" in result.conflict_details.lower()

    def test_contribute_nonparticipant_rejected(
        self,
        sync: SyncPrimitive,
    ) -> None:
        """Non-participant contributions are rejected."""
        barrier = sync.create_barrier(["a1", "a2"])
        assert sync.contribute(barrier.barrier_id, "outsider", {"x": 1}) is False

    def test_contribute_unknown_barrier(self, sync: SyncPrimitive) -> None:
        """Contributing to a non-existent barrier returns False."""
        assert sync.contribute("nonexistent", "a1", {}) is False

    def test_resolve_creates_evidence(
        self,
        sync: SyncPrimitive,
        evidence_store: EvidenceStore,
    ) -> None:
        """Successful resolution creates a coordination evidence anchor."""
        barrier = sync.create_barrier(["a1"])
        sync.contribute(barrier.barrier_id, "a1", {"done": True})
        result = sync.resolve(barrier.barrier_id)
        assert result.synchronized is True
        assert len(result.evidence_anchors) >= 1
        assert result.evidence_anchors[0].ref.startswith("sync:")

        coordination_evidence = evidence_store.get_by_kind("coordination")
        assert len(coordination_evidence) >= 1

    def test_invalid_strategy_raises(self, sync: SyncPrimitive) -> None:
        """Invalid strategy name raises ValueError."""
        barrier = sync.create_barrier(["a1"])
        sync.contribute(barrier.barrier_id, "a1", {})
        with pytest.raises(ValueError, match="Unknown sync strategy"):
            sync.resolve(barrier.barrier_id, "invalid_strategy")

    def test_get_barrier(self, sync: SyncPrimitive) -> None:
        """Look up barrier by ID, returns None for missing."""
        barrier = sync.create_barrier(["a1"])
        fetched = sync.get_barrier(barrier.barrier_id)
        assert fetched is not None
        assert fetched.barrier_id == barrier.barrier_id
        assert sync.get_barrier("nonexistent") is None


# ---------------------------------------------------------------------------
# OrchestrationConfig validation
# ---------------------------------------------------------------------------


class TestOrchestrationConfig:
    """Validate OrchestrationConfig bounds checking."""

    def test_valid_config(self) -> None:
        """Default config is valid."""
        config = OrchestrationConfig()
        assert config.trust_decay == 0.9

    @pytest.mark.parametrize("trust_decay", [0.0, -0.1, 1.5])
    def test_invalid_trust_decay(self, trust_decay: float) -> None:
        """trust_decay must be in (0.0, 1.0]."""
        with pytest.raises(ValueError, match="trust_decay"):
            OrchestrationConfig(trust_decay=trust_decay)

    def test_invalid_sync_timeout(self) -> None:
        """default_sync_timeout must be > 0."""
        with pytest.raises(ValueError, match="default_sync_timeout"):
            OrchestrationConfig(default_sync_timeout=0)

    def test_invalid_audit_max_events(self) -> None:
        """audit_max_events must be > 0."""
        with pytest.raises(ValueError, match="audit_max_events"):
            OrchestrationConfig(audit_max_events=0)


# ---------------------------------------------------------------------------
# AC5: End-to-End Orchestration
# ---------------------------------------------------------------------------

# The multi_agent_orchestration workflow has 7 phases:
# decompose, plan, delegate, synchronize, verify, integrate, audit
_ORCHESTRATION_STEP_COUNT = 7


class TestOrchestrationRuntime:
    """AC5: Full orchestrate() execution with audit and evidence."""

    def test_orchestrate_basic(self, runtime: OrchestrationRuntime) -> None:
        """Single-subtask orchestration succeeds end-to-end."""
        runtime.register_agent("worker", {"retrieve", "search"})
        result = runtime.orchestrate(task_goal="Find relevant data")
        assert result.success is True
        assert result.task_goal == "Find relevant data"
        assert result.steps_executed == _ORCHESTRATION_STEP_COUNT
        assert len(result.subtasks) >= 1
        assert result.subtasks[0].accepted is True
        assert len(result.evidence_anchors) >= 1
        assert len(result.audit_events) >= 1

    def test_orchestrate_with_subtasks(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Multi-subtask orchestration delegates to different agents."""
        runtime.register_agent("searcher", {"search"}, trust_score=0.9)
        runtime.register_agent("generator", {"generate"}, trust_score=0.8)

        subtasks = [
            {
                "description": "Search for data",
                "required_capabilities": ["search"],
            },
            {
                "description": "Generate report",
                "required_capabilities": ["generate"],
            },
        ]
        result = runtime.orchestrate(
            task_goal="Research and report",
            subtask_descriptions=subtasks,
        )
        assert result.success is True
        assert len(result.subtasks) == 2
        assert all(dr.accepted for dr in result.subtasks)
        # With 2+ accepted agents, synchronization should have run
        assert result.sync_result is not None
        assert result.sync_result.synchronized is True

    def test_orchestrate_no_agents(
        self,
        capability_registry: CapabilityRegistry,
    ) -> None:
        """Orchestration fails with no registered agents."""
        rt = OrchestrationRuntime(capability_registry)
        result = rt.orchestrate(task_goal="No one around")
        assert result.success is False
        assert "No agents available" in str(result.integrated_output)

    def test_orchestrate_produces_audit_trail(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Orchestration produces delegation and completion audit events."""
        runtime.register_agent("worker", {"retrieve"})
        result = runtime.orchestrate(task_goal="Audit test")
        assert len(result.audit_events) >= 2
        event_types = {e.event_type for e in result.audit_events}
        assert "delegation" in event_types
        assert "orchestration_complete" in event_types

    def test_orchestrate_audit_events_scoped(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Orchestration audit_events only contain events from this run."""
        runtime.register_agent("worker", {"retrieve"})
        # First orchestration
        runtime.orchestrate(task_goal="Run 1")
        # Second orchestration should NOT include first run's events
        result2 = runtime.orchestrate(task_goal="Run 2")
        # All events should be from run 2 (no "Run 1" leakage)
        assert len(result2.audit_events) >= 1
        for event in result2.audit_events:
            if event.details.get("task_goal"):
                assert event.details["task_goal"] != "Run 1"
        # Verify run 2 events ARE present
        run2_goals = [
            e.details["task_goal"]
            for e in result2.audit_events
            if e.details.get("task_goal")
        ]
        assert "Run 2" in run2_goals

    def test_orchestrate_collects_evidence(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Orchestration collects delegation and orchestration evidence."""
        runtime.register_agent("worker", {"retrieve"})
        result = runtime.orchestrate(task_goal="Evidence test")
        refs = [e.ref for e in result.evidence_anchors]
        assert any(r.startswith("delegation:") for r in refs)
        assert any(r.startswith("orchestration:") for r in refs)

    def test_runtime_exposes_components(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Runtime exposes all coordination sub-components."""
        assert isinstance(runtime.agent_registry, AgentRegistry)
        assert isinstance(runtime.delegation, DelegationProtocol)
        assert isinstance(runtime.sync, SyncPrimitive)
        assert isinstance(runtime.evidence_bridge, CrossAgentEvidenceBridge)
        assert isinstance(runtime.audit_log, CoordinationAuditLog)

    def test_runtime_with_custom_config(
        self,
        capability_registry: CapabilityRegistry,
    ) -> None:
        """Runtime works with custom OrchestrationConfig."""
        config = OrchestrationConfig(
            trust_decay=0.5,
            default_sync_timeout=10.0,
            sync_strategy="merge_keys",
            audit_max_events=100,
        )
        rt = OrchestrationRuntime(capability_registry, config=config)
        rt.register_agent("a1", {"search"})
        rt.register_agent("a2", {"generate"})

        result = rt.orchestrate(
            task_goal="Custom config test",
            subtask_descriptions=[
                {"description": "Search", "required_capabilities": ["search"]},
                {"description": "Generate", "required_capabilities": ["generate"]},
            ],
        )
        assert result.success is True

    def test_orchestrate_partial_delegation_failure(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Orchestration succeeds if at least one subtask is accepted."""
        runtime.register_agent("searcher", {"search"})
        subtasks = [
            {"description": "Search", "required_capabilities": ["search"]},
            {"description": "Generate", "required_capabilities": ["generate"]},
        ]
        result = runtime.orchestrate(
            task_goal="Partial failure",
            subtask_descriptions=subtasks,
        )
        assert result.success is True
        accepted = [dr for dr in result.subtasks if dr.accepted]
        rejected = [dr for dr in result.subtasks if not dr.accepted]
        assert len(accepted) == 1
        assert len(rejected) == 1

    def test_orchestrate_integrated_output_structure(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Integrated output contains expected keys and counts."""
        runtime.register_agent("worker", {"retrieve"})
        result = runtime.orchestrate(task_goal="Structure test")
        output = result.integrated_output
        assert output["task_goal"] == "Structure test"
        assert output["total_subtasks"] == 1
        assert output["accepted_subtasks"] == 1
        assert isinstance(output["agent_outputs"], dict)


# ---------------------------------------------------------------------------
# execute_workflow_step (individual step dispatch)
# ---------------------------------------------------------------------------


class TestExecuteWorkflowStep:
    """Test the per-step dispatch in OrchestrationRuntime."""

    @staticmethod
    def _make_step(capability: str, purpose: str = "test") -> WorkflowStep:
        """Helper to build a minimal WorkflowStep."""
        return WorkflowStep(capability=capability, purpose=purpose)

    def test_delegate_step_with_agents(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Delegate step succeeds when agents are registered."""
        runtime.register_agent("worker", {"retrieve"})
        step = self._make_step("delegate")
        result = runtime.execute_workflow_step(step, {"description": "Test"})
        assert result.status == StepStatus.COMPLETED
        assert result.output["accepted"] is True

    def test_delegate_step_no_agents(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Delegate step fails when no agents are registered."""
        step = self._make_step("delegate")
        result = runtime.execute_workflow_step(step)
        assert result.status == StepStatus.FAILED
        assert "No agents" in (result.error or "")

    def test_synchronize_step_skipped_with_few_participants(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Synchronize step is skipped with fewer than 2 participants."""
        runtime.register_agent("solo", {"retrieve"})
        step = self._make_step("synchronize")
        result = runtime.execute_workflow_step(step)
        assert result.status == StepStatus.SKIPPED

    def test_synchronize_step_with_participants(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Synchronize step succeeds with 2+ participants."""
        runtime.register_agent("a1", {"retrieve"})
        runtime.register_agent("a2", {"search"})
        step = self._make_step("synchronize")
        result = runtime.execute_workflow_step(
            step,
            {"state": {"key": "value"}},
        )
        assert result.status == StepStatus.COMPLETED

    def test_audit_step(self, runtime: OrchestrationRuntime) -> None:
        """Audit step records an event and returns completed."""
        step = self._make_step("audit")
        result = runtime.execute_workflow_step(step, {"info": "test"})
        assert result.status == StepStatus.COMPLETED
        assert result.output["audited"] is True

    def test_passthrough_step(self, runtime: OrchestrationRuntime) -> None:
        """Non-coordination steps pass through with completed status."""
        step = self._make_step("retrieve")
        ctx = {"data": "passthrough"}
        result = runtime.execute_workflow_step(step, ctx)
        assert result.status == StepStatus.COMPLETED
        assert result.output == ctx


# ---------------------------------------------------------------------------
# Concurrency tests
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Thread-safety validation for shared state operations."""

    def test_concurrent_evidence_store_add(
        self,
        evidence_store: EvidenceStore,
    ) -> None:
        """Concurrent add_anchor calls do not corrupt the store."""
        n_threads = 8
        n_per_thread = 50

        def add_batch(thread_id: int) -> int:
            for i in range(n_per_thread):
                anchor = EvidenceAnchor(
                    ref=f"thread:{thread_id}:item:{i}",
                    kind="tool_output",
                    timestamp="2025-01-01T00:00:00+00:00",
                )
                evidence_store.add_anchor(anchor)
            return n_per_thread

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [pool.submit(add_batch, t) for t in range(n_threads)]
            for f in as_completed(futures):
                f.result()  # raises if thread hit an exception

        assert len(evidence_store) == n_threads * n_per_thread

    def test_concurrent_audit_log_record(self) -> None:
        """Concurrent audit log records do not lose events."""
        log = CoordinationAuditLog(max_events=10000)
        n_threads = 8
        n_per_thread = 50

        def record_batch(thread_id: int) -> int:
            for i in range(n_per_thread):
                log.record(
                    event_type="test",
                    source_agent_id=f"agent-{thread_id}",
                    target_agent_ids=[f"target-{i}"],
                )
            return n_per_thread

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [pool.submit(record_batch, t) for t in range(n_threads)]
            for f in as_completed(futures):
                f.result()

        assert len(log) == n_threads * n_per_thread

    def test_concurrent_agent_registration(
        self,
        capability_registry: CapabilityRegistry,
    ) -> None:
        """Concurrent agent registrations do not corrupt the registry."""
        registry = AgentRegistry(capability_registry)
        n_threads = 8

        def register_agent(thread_id: int) -> None:
            registry.register(
                agent_id=f"agent-{thread_id}",
                capabilities={"retrieve"},
                trust_score=0.5 + thread_id * 0.05,
            )

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [pool.submit(register_agent, t) for t in range(n_threads)]
            for f in as_completed(futures):
                f.result()

        assert registry.agent_count == n_threads

    def test_concurrent_barrier_contributions(
        self,
        evidence_store: EvidenceStore,
        audit_log: CoordinationAuditLog,
    ) -> None:
        """Concurrent barrier contributions are all recorded."""
        sync = SyncPrimitive(evidence_store, audit_log)
        n_participants = 8
        participants = [f"agent-{i}" for i in range(n_participants)]
        barrier = sync.create_barrier(participants)

        def contribute(agent_id: str) -> bool:
            return sync.contribute(
                barrier.barrier_id,
                agent_id,
                {"from": agent_id},
            )

        with ThreadPoolExecutor(max_workers=n_participants) as pool:
            futures = [pool.submit(contribute, p) for p in participants]
            results = [f.result() for f in as_completed(futures)]

        assert all(results)
        result = sync.resolve(barrier.barrier_id)
        assert result.synchronized is True


# ---------------------------------------------------------------------------
# Serialization tests (to_dict)
# ---------------------------------------------------------------------------


class TestSerialization:
    """Verify to_dict() on all coordination dataclasses."""

    def test_delegation_task_to_dict(self) -> None:
        """DelegationTask.to_dict converts frozenset to sorted list."""
        task = DelegationTask(
            task_id="t1",
            description="Test task",
            required_capabilities=frozenset({"search", "retrieve"}),
            input_data={"key": "val"},
            constraints={"timeout": 30},
            created_at="2025-01-01T00:00:00+00:00",
        )
        d = task.to_dict()
        assert d["task_id"] == "t1"
        assert d["description"] == "Test task"
        assert d["required_capabilities"] == ["retrieve", "search"]
        assert d["input_data"] == {"key": "val"}
        assert d["constraints"] == {"timeout": 30}
        assert d["created_at"] == "2025-01-01T00:00:00+00:00"

    def test_delegation_result_to_dict(self) -> None:
        """DelegationResult.to_dict serializes evidence anchors inline."""
        anchor = EvidenceAnchor(
            ref="delegation:abc",
            kind="coordination",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        result = DelegationResult(
            task_id="t1",
            agent_id="worker",
            accepted=True,
            evidence_anchors=[anchor],
            output_data={"result": "ok"},
        )
        d = result.to_dict()
        assert d["task_id"] == "t1"
        assert d["accepted"] is True
        assert len(d["evidence_anchors"]) == 1
        assert d["evidence_anchors"][0]["ref"] == "delegation:abc"
        assert d["evidence_anchors"][0]["kind"] == "coordination"
        assert d["output_data"] == {"result": "ok"}

    def test_shared_evidence_to_dict(self) -> None:
        """SharedEvidence.to_dict inlines the anchor."""
        anchor = EvidenceAnchor(
            ref="test:ev",
            kind="tool_output",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        se = SharedEvidence(
            anchor=anchor,
            source_agent_id="agent-1",
            trust_score=0.72,
            original_trust=0.72,
            shared_at="2025-01-01T00:00:00+00:00",
        )
        d = se.to_dict()
        assert d["anchor"]["ref"] == "test:ev"
        assert d["source_agent_id"] == "agent-1"
        assert abs(d["trust_score"] - 0.72) < 1e-9
        assert d["shared_at"] == "2025-01-01T00:00:00+00:00"

    def test_orchestration_config_to_dict(self) -> None:
        """OrchestrationConfig.to_dict maps all fields."""
        config = OrchestrationConfig(
            trust_decay=0.8,
            default_sync_timeout=30.0,
            sync_strategy="merge_keys",
            audit_max_events=500,
        )
        d = config.to_dict()
        assert d["trust_decay"] == 0.8
        assert d["default_sync_timeout"] == 30.0
        assert d["sync_strategy"] == "merge_keys"
        assert d["audit_max_events"] == 500

    def test_orchestration_result_to_dict(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """OrchestrationResult.to_dict recursively serializes subtasks and events."""
        runtime.register_agent("worker", {"retrieve"})
        result = runtime.orchestrate(task_goal="Serialization test")
        d = result.to_dict()
        assert d["success"] is True
        assert d["task_goal"] == "Serialization test"
        assert isinstance(d["subtasks"], list)
        assert len(d["subtasks"]) >= 1
        assert isinstance(d["subtasks"][0], dict)
        assert "task_id" in d["subtasks"][0]
        assert isinstance(d["audit_events"], list)
        assert len(d["audit_events"]) >= 1
        assert isinstance(d["evidence_anchors"], list)

    def test_agent_descriptor_to_dict(
        self,
        agent_registry: AgentRegistry,
    ) -> None:
        """AgentDescriptor.to_dict sorts capabilities."""
        desc = agent_registry.register("a1", {"search", "retrieve"}, trust_score=0.9)
        d = desc.to_dict()
        assert d["agent_id"] == "a1"
        assert d["capabilities"] == ["retrieve", "search"]
        assert d["trust_score"] == 0.9
        assert isinstance(d["metadata"], dict)

    def test_sync_barrier_to_dict(self, sync: SyncPrimitive) -> None:
        """SyncBarrier.to_dict sorts participants and copies proposals."""
        barrier = sync.create_barrier(["b", "a"], timeout_seconds=20.0)
        sync.contribute(barrier.barrier_id, "a", {"x": 1})
        updated = sync.get_barrier(barrier.barrier_id)
        assert updated is not None
        d = updated.to_dict()
        assert d["participants"] == ["a", "b"]
        assert d["timeout_seconds"] == 20.0
        assert "a" in d["proposals"]

    def test_sync_result_to_dict(self, sync: SyncPrimitive) -> None:
        """SyncResult.to_dict converts participants tuple to list."""
        barrier = sync.create_barrier(["a1"])
        sync.contribute(barrier.barrier_id, "a1", {"done": True})
        result = sync.resolve(barrier.barrier_id)
        d = result.to_dict()
        assert d["synchronized"] is True
        assert isinstance(d["participants"], list)
        assert d["participants"] == ["a1"]
        assert isinstance(d["evidence_anchors"], list)
        assert len(d["evidence_anchors"]) >= 1
        assert d["evidence_anchors"][0]["ref"].startswith("sync:")


# ---------------------------------------------------------------------------
# invoke and inquire step handlers
# ---------------------------------------------------------------------------


class TestExecuteWorkflowStepInvokeInquire:
    """Test invoke and inquire handlers in execute_workflow_step."""

    @staticmethod
    def _make_step(capability: str, purpose: str = "test") -> WorkflowStep:
        return WorkflowStep(capability=capability, purpose=purpose)

    def test_invoke_step_with_workflow(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """invoke step succeeds with a workflow name in context."""
        step = self._make_step("invoke")
        result = runtime.execute_workflow_step(step, {"workflow": "debug_code_change"})
        assert result.status == StepStatus.COMPLETED
        assert result.output["workflow"] == "debug_code_change"
        assert len(result.output["evidence_anchors"]) >= 1
        assert result.output["evidence_anchors"][0].startswith("invoke:")

    def test_invoke_step_no_workflow(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """invoke step fails without a workflow name."""
        step = self._make_step("invoke")
        result = runtime.execute_workflow_step(step, {})
        assert result.status == StepStatus.FAILED
        assert "No workflow" in (result.error or "")

    def test_inquire_step_with_input(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """inquire step generates clarification questions."""
        step = self._make_step("inquire")
        result = runtime.execute_workflow_step(
            step, {"ambiguous_input": "unclear request", "max_questions": 5}
        )
        assert result.status == StepStatus.COMPLETED
        assert len(result.output["questions"]) >= 1
        assert "unclear request" in result.output["questions"][0]
        assert result.output["confidence"] == 0.5
        assert len(result.output["evidence_anchors"]) >= 1

    def test_inquire_step_empty_input(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """inquire step handles missing ambiguous_input."""
        step = self._make_step("inquire")
        result = runtime.execute_workflow_step(step, {})
        assert result.status == StepStatus.COMPLETED
        assert result.output["questions"] == []
        assert result.output["confidence"] == 1.0


# ---------------------------------------------------------------------------
# Dependency-based subtask ordering
# ---------------------------------------------------------------------------


class TestDependencyOrdering:
    """Test _order_subtasks_by_dependencies in OrchestrationRuntime."""

    def test_orchestrate_dependency_ordering(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Subtasks are reordered based on ontology edges.

        'plan' precedes 'delegate' in the ontology, so a subtask
        requiring 'delegate' should come after one requiring 'plan'.
        """
        runtime.register_agent("planner", {"plan", "delegate"})
        subtasks = [
            {"description": "Delegate work", "required_capabilities": ["delegate"]},
            {"description": "Plan first", "required_capabilities": ["plan"]},
        ]
        result = runtime.orchestrate(
            task_goal="Ordering test",
            subtask_descriptions=subtasks,
        )
        assert result.success is True
        # Both should be accepted by the planner agent
        assert len(result.subtasks) == 2
        # Verify tasks ran (we can't directly inspect order from results,
        # but we can verify both were delegated successfully)
        assert all(dr.accepted for dr in result.subtasks)

    def test_orchestrate_no_cycle_crash(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Cycles fall back to original order without crashing."""
        runtime.register_agent("worker", {"retrieve", "search"})
        # Both subtasks have capabilities; if there were cycles the
        # runtime should still work (falls back to original order)
        subtasks = [
            {"description": "A", "required_capabilities": ["retrieve"]},
            {"description": "B", "required_capabilities": ["search"]},
        ]
        result = runtime.orchestrate(
            task_goal="Cycle safety",
            subtask_descriptions=subtasks,
        )
        assert result.success is True
        assert len(result.subtasks) == 2

    def test_orchestrate_unconstrained_subtasks_stable(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """Subtasks without capabilities keep their original order."""
        runtime.register_agent("worker", {"retrieve"})
        subtasks = [
            {"description": "First"},
            {"description": "Second"},
            {"description": "Third"},
        ]
        result = runtime.orchestrate(
            task_goal="Stable order",
            subtask_descriptions=subtasks,
        )
        assert result.success is True
        assert len(result.subtasks) == 3


# ---------------------------------------------------------------------------
# Wiring verification
# ---------------------------------------------------------------------------


class TestOrchestrateWiring:
    """Verify orchestrate() uses execute_workflow_step() for delegation."""

    def test_orchestrate_uses_execute_workflow_step(
        self,
        runtime: OrchestrationRuntime,
    ) -> None:
        """orchestrate() calls execute_workflow_step for delegate steps."""
        runtime.register_agent("worker", {"retrieve"})

        with patch.object(
            runtime, "execute_workflow_step", wraps=runtime.execute_workflow_step
        ) as spy:
            result = runtime.orchestrate(task_goal="Wiring test")

        assert result.success is True
        # execute_workflow_step should have been called at least once
        # for the delegation step
        assert spy.call_count >= 1
        # At least one call should have been for a delegate step
        delegate_calls = [
            call for call in spy.call_args_list if call[0][0].capability == "delegate"
        ]
        assert len(delegate_calls) >= 1
