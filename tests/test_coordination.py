"""
Tests for Multi-Agent Coordination Runtime

Tests cover the 5 acceptance criteria from Issue #76:
- AC1: Agent registration and discovery (TestAgentRegistry)
- AC2: Typed delegation with contract enforcement (TestDelegationProtocol)
- AC3: Trust propagation and evidence sharing (TestCrossAgentEvidenceBridge)
- AC4: Coordination audit trail (TestCoordinationAuditLog)
- AC3 cont: Barrier synchronization (TestSyncPrimitive)
- AC5: End-to-end orchestration (TestOrchestrationRuntime)
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

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
        agent_registry, evidence_store, audit_log, trust_decay=0.9,
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
        self, agent_registry: AgentRegistry,
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
        self, agent_registry: AgentRegistry,
    ) -> None:
        """Reject agents that declare capabilities absent from the ontology."""
        with pytest.raises(ValueError, match="Unknown capabilities"):
            agent_registry.register(
                agent_id="agent-bad",
                capabilities={"nonexistent_capability"},
            )

    def test_register_duplicate_overwrites(
        self, agent_registry: AgentRegistry,
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
        self, agent_registry: AgentRegistry,
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
        self, agent_registry: AgentRegistry,
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
        self, agent_registry: AgentRegistry,
    ) -> None:
        """Reject trust scores outside [0.0, 1.0]."""
        with pytest.raises(ValueError, match="trust_score"):
            agent_registry.register("bad", {"retrieve"}, trust_score=1.5)
        with pytest.raises(ValueError, match="trust_score"):
            agent_registry.register("bad", {"retrieve"}, trust_score=-0.1)


# ---------------------------------------------------------------------------
# AC2: Typed Delegation with Contract Enforcement
# ---------------------------------------------------------------------------

class TestDelegationProtocol:
    """AC2: Delegation validates contracts and produces evidence."""

    def test_delegate_to_capable_agent(
        self, delegation: DelegationProtocol, agent_registry: AgentRegistry,
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
        self, delegation: DelegationProtocol, agent_registry: AgentRegistry,
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
        self, delegation: DelegationProtocol,
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
        # Use a real ontology capability that no agent has
        result = delegation.auto_delegate(
            description="Impossible task",
            required_capabilities={"simulate"},
        )
        assert result.accepted is False
        assert "No agent found" in result.rejection_reason

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

    @pytest.mark.parametrize("trust_decay,expected_trust", [
        (0.0, 0.0),    # all trust destroyed
        (1.0, 0.8),    # trust fully preserved
        (0.5, 0.4),    # half decay
    ])
    def test_trust_decay_boundaries(
        self,
        agent_registry: AgentRegistry,
        evidence_store: EvidenceStore,
        audit_log: CoordinationAuditLog,
        make_anchor: Callable[..., EvidenceAnchor],
        trust_decay: float,
        expected_trust: float,
    ) -> None:
        """Trust decay boundary values: 0.0, 0.5, and 1.0."""
        bridge = CrossAgentEvidenceBridge(
            agent_registry, evidence_store, audit_log, trust_decay=trust_decay,
        )
        agent_registry.register("source", {"retrieve"}, trust_score=0.8)
        agent_registry.register("target", {"search"})

        shared = bridge.share_evidence(
            anchor=make_anchor(f"test:decay:{trust_decay}"),
            source_agent_id="source",
            target_agent_ids=["target"],
        )
        assert abs(shared[0].trust_score - expected_trust) < 1e-9

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

    def test_access_tracking(
        self,
        evidence_bridge: CrossAgentEvidenceBridge,
        agent_registry: AgentRegistry,
        make_anchor: Callable[..., EvidenceAnchor],
    ) -> None:
        """Accessing shared evidence records the accessor's agent_id."""
        agent_registry.register("source", {"retrieve"})
        agent_registry.register("target", {"search"})

        evidence_bridge.share_evidence(
            anchor=make_anchor("test:access"),
            source_agent_id="source",
            target_agent_ids=["target"],
        )
        items = evidence_bridge.get_shared_evidence("target")
        assert len(items) == 1
        assert "target" in items[0].accessed_by


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
        self, audit_log: CoordinationAuditLog,
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
        self, sync: SyncPrimitive,
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
        self, runtime: OrchestrationRuntime,
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
        self, capability_registry: CapabilityRegistry,
    ) -> None:
        """Orchestration fails with no registered agents."""
        rt = OrchestrationRuntime(capability_registry)
        result = rt.orchestrate(task_goal="No one around")
        assert result.success is False
        assert "No agents available" in str(result.integrated_output)

    def test_orchestrate_produces_audit_trail(
        self, runtime: OrchestrationRuntime,
    ) -> None:
        """Orchestration produces delegation and completion audit events."""
        runtime.register_agent("worker", {"retrieve"})
        result = runtime.orchestrate(task_goal="Audit test")
        assert len(result.audit_events) >= 2
        event_types = {e.event_type for e in result.audit_events}
        assert "delegation" in event_types
        assert "orchestration_complete" in event_types

    def test_orchestrate_collects_evidence(
        self, runtime: OrchestrationRuntime,
    ) -> None:
        """Orchestration collects delegation and orchestration evidence."""
        runtime.register_agent("worker", {"retrieve"})
        result = runtime.orchestrate(task_goal="Evidence test")
        refs = [e.ref for e in result.evidence_anchors]
        assert any(r.startswith("delegation:") for r in refs)
        assert any(r.startswith("orchestration:") for r in refs)

    def test_runtime_exposes_components(
        self, runtime: OrchestrationRuntime,
    ) -> None:
        """Runtime exposes all coordination sub-components."""
        assert isinstance(runtime.agent_registry, AgentRegistry)
        assert isinstance(runtime.delegation, DelegationProtocol)
        assert isinstance(runtime.sync, SyncPrimitive)
        assert isinstance(runtime.evidence_bridge, CrossAgentEvidenceBridge)
        assert isinstance(runtime.audit_log, CoordinationAuditLog)

    def test_runtime_with_custom_config(
        self, capability_registry: CapabilityRegistry,
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
        self, runtime: OrchestrationRuntime,
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
        self, runtime: OrchestrationRuntime,
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
        self, runtime: OrchestrationRuntime,
    ) -> None:
        """Delegate step succeeds when agents are registered."""
        runtime.register_agent("worker", {"retrieve"})
        step = self._make_step("delegate")
        result = runtime.execute_workflow_step(step, {"description": "Test"})
        assert result.status == StepStatus.COMPLETED
        assert result.output["accepted"] is True

    def test_delegate_step_no_agents(
        self, runtime: OrchestrationRuntime,
    ) -> None:
        """Delegate step fails when no agents are registered."""
        step = self._make_step("delegate")
        result = runtime.execute_workflow_step(step)
        assert result.status == StepStatus.FAILED
        assert "No agents" in (result.error or "")

    def test_synchronize_step_skipped_with_few_participants(
        self, runtime: OrchestrationRuntime,
    ) -> None:
        """Synchronize step is skipped with fewer than 2 participants."""
        runtime.register_agent("solo", {"retrieve"})
        step = self._make_step("synchronize")
        result = runtime.execute_workflow_step(step)
        assert result.status == StepStatus.SKIPPED

    def test_synchronize_step_with_participants(
        self, runtime: OrchestrationRuntime,
    ) -> None:
        """Synchronize step succeeds with 2+ participants."""
        runtime.register_agent("a1", {"retrieve"})
        runtime.register_agent("a2", {"search"})
        step = self._make_step("synchronize")
        result = runtime.execute_workflow_step(
            step, {"state": {"key": "value"}},
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
