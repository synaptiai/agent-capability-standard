"""Performance and load tests for EvidenceStore (TEST-003).

Benchmarks at 10K anchors, tests priority eviction at capacity,
tests secondary index consistency after eviction.
"""

from __future__ import annotations

import time

import pytest

from grounded_agency.state.evidence_store import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    EvidenceAnchor,
    EvidenceStore,
    _validate_metadata_key,
)

# ─── SEC-008: Metadata key denylist tests ───


class TestMetadataKeyDenylist:
    """Tests for SEC-008 metadata key validation hardening."""

    @pytest.mark.parametrize(
        "key",
        [
            "__proto__",
            "constructor",
            "__class__",
            "__init__",
            "__bases__",
            "__mro__",
            "__subclasses__",
            "__reduce__",
            "__reduce_ex__",
            "__getattr__",
            "__setattr__",
            "__delattr__",
            "__globals__",
            "__builtins__",
            "__import__",
        ],
    )
    def test_rejects_dangerous_key(self, key: str) -> None:
        assert _validate_metadata_key(key) is False

    def test_rejects_dunder_prefix(self) -> None:
        assert _validate_metadata_key("__anything__") is False

    def test_rejects_long_key(self) -> None:
        assert _validate_metadata_key("a" * 65) is False

    def test_allows_normal_key(self) -> None:
        assert _validate_metadata_key("tool_name") is True

    def test_allows_single_underscore_prefix(self) -> None:
        assert _validate_metadata_key("_private") is True

    def test_allows_max_length_key(self) -> None:
        assert _validate_metadata_key("a" * 64) is True

    def test_anchor_strips_denied_keys(self) -> None:
        """EvidenceAnchor sanitization should drop denied keys."""
        anchor = EvidenceAnchor(
            ref="test:1",
            kind="tool_output",
            timestamp="2024-01-01T00:00:00Z",
            metadata={
                "safe_key": "ok",
                "__proto__": "evil",
                "__class__": "also_evil",
                "another_safe": 42,
            },
        )
        assert "safe_key" in anchor.metadata
        assert "another_safe" in anchor.metadata
        assert "__proto__" not in anchor.metadata
        assert "__class__" not in anchor.metadata


# ─── SEC-004: Priority eviction tests ───


class TestPriorityEviction:
    """Tests for SEC-004 priority-aware eviction."""

    def test_mutations_get_high_priority(self) -> None:
        anchor = EvidenceAnchor.from_mutation("file.py", "write", "chk_1")
        assert anchor.priority == PRIORITY_HIGH

    def test_tool_output_gets_normal_priority(self) -> None:
        anchor = EvidenceAnchor.from_tool_output("Read", "id1", {"path": "/tmp"})
        assert anchor.priority == PRIORITY_NORMAL

    def test_mark_critical(self) -> None:
        anchor = EvidenceAnchor.from_tool_output("Read", "id1", {"path": "/tmp"})
        anchor.mark_critical()
        assert anchor.priority == PRIORITY_CRITICAL

    def test_low_priority_evicted_first(self) -> None:
        """When at capacity, lowest-priority anchor is evicted."""
        store = EvidenceStore(max_anchors=3)

        # Add three anchors: LOW, HIGH, NORMAL
        low = EvidenceAnchor(
            ref="low:1", kind="tool_output", timestamp="t1", priority=PRIORITY_LOW
        )
        high = EvidenceAnchor(
            ref="high:1", kind="mutation", timestamp="t2", priority=PRIORITY_HIGH
        )
        normal = EvidenceAnchor(
            ref="normal:1", kind="file", timestamp="t3", priority=PRIORITY_NORMAL
        )

        store.add_anchor(low)
        store.add_anchor(high)
        store.add_anchor(normal)

        assert len(store) == 3

        # Add a 4th — should evict the LOW priority anchor
        new = EvidenceAnchor(
            ref="new:1", kind="tool_output", timestamp="t4", priority=PRIORITY_NORMAL
        )
        store.add_anchor(new)

        assert len(store) == 3
        refs = [a.ref for a in store]
        assert "low:1" not in refs
        assert "high:1" in refs
        assert "normal:1" in refs
        assert "new:1" in refs

    def test_fifo_within_same_priority(self) -> None:
        """Among same priority, oldest is evicted first."""
        store = EvidenceStore(max_anchors=3)

        a1 = EvidenceAnchor(ref="a:1", kind="tool_output", timestamp="t1")
        a2 = EvidenceAnchor(ref="a:2", kind="tool_output", timestamp="t2")
        a3 = EvidenceAnchor(ref="a:3", kind="tool_output", timestamp="t3")

        store.add_anchor(a1)
        store.add_anchor(a2)
        store.add_anchor(a3)

        # Add a 4th — should evict a:1 (oldest, same priority)
        a4 = EvidenceAnchor(ref="a:4", kind="tool_output", timestamp="t4")
        store.add_anchor(a4)

        refs = [a.ref for a in store]
        assert "a:1" not in refs
        assert "a:4" in refs

    def test_critical_survives_eviction(self) -> None:
        """Critical anchors survive eviction even when they're oldest."""
        store = EvidenceStore(max_anchors=3)

        critical = EvidenceAnchor(
            ref="critical:1",
            kind="mutation",
            timestamp="t1",
            priority=PRIORITY_CRITICAL,
        )
        normal1 = EvidenceAnchor(ref="n:1", kind="tool_output", timestamp="t2")
        normal2 = EvidenceAnchor(ref="n:2", kind="tool_output", timestamp="t3")

        store.add_anchor(critical)
        store.add_anchor(normal1)
        store.add_anchor(normal2)

        # Add a 4th — should evict n:1 (lowest priority among normal+)
        new = EvidenceAnchor(ref="new:1", kind="tool_output", timestamp="t4")
        store.add_anchor(new)

        refs = [a.ref for a in store]
        assert "critical:1" in refs  # Critical survived
        assert "n:1" not in refs  # Oldest normal evicted

    def test_index_consistency_after_eviction(self) -> None:
        """Secondary indexes remain consistent after priority eviction."""
        store = EvidenceStore(max_anchors=5)

        for i in range(5):
            kind = "mutation" if i % 2 == 0 else "tool_output"
            anchor = EvidenceAnchor(
                ref=f"ref:{i}",
                kind=kind,
                timestamp=f"t{i}",
                priority=PRIORITY_LOW if kind == "tool_output" else PRIORITY_HIGH,
            )
            store.add_anchor(anchor, capability_id="retrieve" if i < 3 else None)

        # Force eviction
        new = EvidenceAnchor(ref="new:1", kind="tool_output", timestamp="t99")
        store.add_anchor(new)

        # Verify index consistency (dict-valued indexes after #63)
        for kind, anchors_dict in store._by_kind.items():
            for a in anchors_dict.values():
                assert a in store._anchors, f"Stale {a.ref} in _by_kind[{kind}]"

        for cap, anchors_dict in store._by_capability.items():
            for a in anchors_dict.values():
                assert a in store._anchors, f"Stale {a.ref} in _by_capability[{cap}]"


# ─── P1-2: Stale index prevention after capacity overflow ───


class TestNoStaleIndexes:
    """Verify that overflowing capacity doesn't leave stale secondary indexes."""

    def test_no_stale_indexes_after_capacity_overflow(self) -> None:
        """Adding N items beyond max_anchors must not leave stale index entries.

        Without the maxlen removal fix, deque auto-eviction bypasses
        _remove_from_indexes, leaving ghost references in _by_kind.
        """
        cap = 50
        store = EvidenceStore(max_anchors=cap)

        # Overflow by 2x capacity
        for i in range(cap * 2):
            kind = "mutation" if i % 5 == 0 else "tool_output"
            anchor = EvidenceAnchor(
                ref=f"ref:{i}",
                kind=kind,
                timestamp=f"t{i}",
                priority=PRIORITY_HIGH if kind == "mutation" else PRIORITY_NORMAL,
            )
            store.add_anchor(anchor, capability_id="retrieve" if i % 3 == 0 else None)

        assert len(store) == cap

        # Every anchor in _by_kind must still exist in _anchors (dict-valued after #63)
        for kind, anchors_dict in store._by_kind.items():
            for a in anchors_dict.values():
                assert a in store._anchors, f"Stale anchor {a.ref} in _by_kind[{kind}]"

        # Every anchor in _by_capability must still exist in _anchors (dict-valued after #63)
        for cap_id, anchors_dict in store._by_capability.items():
            for a in anchors_dict.values():
                assert a in store._anchors, (
                    f"Stale anchor {a.ref} in _by_capability[{cap_id}]"
                )


# ─── TEST-003: Performance benchmarks ───


class TestPerformance:
    """Performance benchmarks at scale."""

    def test_add_10k_anchors(self) -> None:
        """Benchmark: add 10K anchors should complete within reasonable time."""
        store = EvidenceStore(max_anchors=10000)

        start = time.monotonic()
        for i in range(10000):
            anchor = EvidenceAnchor.from_tool_output(
                "Read", f"id_{i}", {"path": f"/tmp/file_{i}"}
            )
            store.add_anchor(anchor)
        elapsed = time.monotonic() - start

        assert len(store) == 10000
        # Should complete in under 2 seconds with O(1) eviction (#63)
        assert elapsed < 2.0, f"Adding 10K anchors took {elapsed:.2f}s"

    def test_eviction_at_capacity(self) -> None:
        """Benchmark: adding beyond capacity triggers eviction without crash."""
        store = EvidenceStore(max_anchors=1000)

        # Fill to capacity
        for i in range(1000):
            anchor = EvidenceAnchor.from_tool_output(
                "Read", f"id_{i}", {"path": f"/tmp/file_{i}"}
            )
            store.add_anchor(anchor)

        # Add 500 more — triggers 500 evictions
        start = time.monotonic()
        for i in range(500):
            anchor = EvidenceAnchor.from_tool_output(
                "Write", f"evict_{i}", {"path": f"/tmp/evict_{i}"}
            )
            store.add_anchor(anchor)
        elapsed = time.monotonic() - start

        assert len(store) == 1000
        assert elapsed < 0.5, f"500 evictions took {elapsed:.2f}s"

    def test_mixed_priority_eviction_at_scale(self) -> None:
        """Priority eviction with mixed priorities at scale."""
        store = EvidenceStore(max_anchors=500)

        # Fill with mixed priorities
        for i in range(500):
            if i % 10 == 0:
                anchor = EvidenceAnchor.from_mutation(
                    f"file_{i}.py", "write", f"chk_{i}"
                )
            else:
                anchor = EvidenceAnchor.from_tool_output(
                    "Read", f"id_{i}", {"path": f"/tmp/{i}"}
                )
            store.add_anchor(anchor)

        # Add 200 more — evictions should prefer low-priority
        mutations_before = len(store.get_mutations())
        for i in range(200):
            anchor = EvidenceAnchor.from_tool_output(
                "Grep", f"new_{i}", {"pattern": "test"}
            )
            store.add_anchor(anchor)

        mutations_after = len(store.get_mutations())
        assert len(store) == 500
        # Mutations (HIGH priority) should survive better than tool_output (NORMAL)
        assert mutations_after >= mutations_before * 0.8, (
            f"Too many mutations evicted: {mutations_before} -> {mutations_after}"
        )

    def test_get_recent_performance(self) -> None:
        """Benchmark: get_recent on 10K store should be fast."""
        store = EvidenceStore(max_anchors=10000)
        for i in range(10000):
            anchor = EvidenceAnchor.from_tool_output(
                "Read", f"id_{i}", {"path": f"/tmp/{i}"}
            )
            store.add_anchor(anchor)

        start = time.monotonic()
        for _ in range(1000):
            store.get_recent(10)
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, f"1000 get_recent calls took {elapsed:.2f}s"

    def test_search_by_ref_prefix_performance(self) -> None:
        """Benchmark: search_by_ref_prefix should be reasonable at 10K."""
        store = EvidenceStore(max_anchors=10000)
        for i in range(10000):
            tool = "Read" if i % 2 == 0 else "Write"
            anchor = EvidenceAnchor.from_tool_output(
                tool, f"id_{i}", {"path": f"/tmp/{i}"}
            )
            store.add_anchor(anchor)

        start = time.monotonic()
        results = store.search_by_ref_prefix("tool:Read")
        elapsed = time.monotonic() - start

        assert len(results) == 5000
        assert elapsed < 1.0, f"search_by_ref_prefix took {elapsed:.2f}s"

    def test_10k_insert_evict_under_100ms(self) -> None:
        """Benchmark: 10K insert+evict cycle under 100ms with O(1) eviction."""
        store = EvidenceStore(max_anchors=5000)

        # Fill to capacity
        for i in range(5000):
            anchor = EvidenceAnchor.from_tool_output(
                "Read", f"fill_{i}", {"path": f"/tmp/{i}"}
            )
            store.add_anchor(anchor)

        # 10K more inserts (each triggers eviction)
        start = time.monotonic()
        for i in range(10000):
            anchor = EvidenceAnchor.from_tool_output(
                "Write", f"evict_{i}", {"path": f"/tmp/e_{i}"}
            )
            store.add_anchor(anchor)
        elapsed = time.monotonic() - start

        assert len(store) == 5000
        assert elapsed < 1.0, f"10K insert+evict took {elapsed:.3f}s, expected < 1.0s"
