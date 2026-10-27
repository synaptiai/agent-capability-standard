"""Tests for TOCTOU race condition fix in checkpoint validation (SEC-007).

Verifies that validate_and_reserve() provides atomic check-and-reserve
semantics, preventing race conditions between has_valid_checkpoint()
and subsequent checkpoint consumption.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from grounded_agency.state.checkpoint_tracker import CheckpointTracker


@pytest.fixture
def tracker(tmp_path: Path) -> CheckpointTracker:
    """Create a fresh CheckpointTracker for testing."""
    return CheckpointTracker(checkpoint_dir=str(tmp_path))


class TestValidateAndReserve:
    """Tests for atomic validate_and_reserve method."""

    def test_returns_false_when_no_checkpoint(self, tracker: CheckpointTracker) -> None:
        is_valid, checkpoint_id = tracker.validate_and_reserve()
        assert is_valid is False
        assert checkpoint_id is None

    def test_returns_true_with_valid_checkpoint(
        self, tracker: CheckpointTracker
    ) -> None:
        created_id = tracker.create_checkpoint(scope=["*"], reason="test")
        is_valid, checkpoint_id = tracker.validate_and_reserve()
        assert is_valid is True
        assert checkpoint_id == created_id

    def test_returns_false_after_consumption(self, tracker: CheckpointTracker) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        tracker.consume_checkpoint()
        is_valid, checkpoint_id = tracker.validate_and_reserve()
        assert is_valid is False
        assert checkpoint_id is None

    def test_returns_false_for_expired_checkpoint(
        self, tracker: CheckpointTracker
    ) -> None:
        # Create checkpoint that expires immediately
        tracker.create_checkpoint(scope=["*"], reason="test", expiry_minutes=0)
        # Wait a tiny bit to ensure expiry
        time.sleep(0.01)
        is_valid, checkpoint_id = tracker.validate_and_reserve()
        assert is_valid is False
        assert checkpoint_id is None


class TestThreadSafety:
    """Tests for thread-safety of checkpoint operations."""

    def test_concurrent_validate_and_consume(self, tracker: CheckpointTracker) -> None:
        """Verify that concurrent validate + consume doesn't corrupt state."""
        tracker.create_checkpoint(scope=["*"], reason="test")

        results: list[tuple[bool, str | None]] = []
        consumed: list[str | None] = []
        barrier = threading.Barrier(2)

        def validate_worker() -> None:
            barrier.wait()
            result = tracker.validate_and_reserve()
            results.append(result)

        def consume_worker() -> None:
            barrier.wait()
            consumed.append(tracker.consume_checkpoint())

        threads = [
            threading.Thread(target=validate_worker),
            threading.Thread(target=consume_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Both operations ran
        assert len(results) == 1
        assert len(consumed) == 1

        # Logical consistency: at most one of consume/validate can "win"
        # the checkpoint exclusively. Both seeing success is valid only if
        # validate ran before consume (it reserved but didn't consume).
        consume_ok = consumed[0] is not None
        validate_ok = results[0][0] is True

        if consume_ok and validate_ok:
            # Both succeeded — valid only if validate ran before consume
            assert results[0][1] is not None  # validate returned a checkpoint ID
        elif consume_ok and not validate_ok:
            # Consume won the race, validate saw no checkpoint — valid
            assert results[0][1] is None
        elif not consume_ok and validate_ok:
            # Validate saw the checkpoint but consume found nothing — this
            # should not happen with proper locking (unless checkpoint expired).
            # If it does occur, the checkpoint must still exist.
            assert tracker.has_valid_checkpoint() or not tracker._active_checkpoint
        else:
            # Neither succeeded — checkpoint may have expired or was
            # already consumed; either way state must be consistent
            assert (
                tracker._active_checkpoint is None
                or not tracker._active_checkpoint.is_valid()
            )

    def test_multiple_concurrent_consumes(self, tracker: CheckpointTracker) -> None:
        """Only one concurrent consume should succeed."""
        tracker.create_checkpoint(scope=["*"], reason="test")

        consumed_ids: list[str | None] = []
        barrier = threading.Barrier(5)

        def consume_worker() -> None:
            barrier.wait()  # Synchronize all threads
            consumed_ids.append(tracker.consume_checkpoint())

        threads = [threading.Thread(target=consume_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one thread should have consumed the checkpoint
        non_none = [cid for cid in consumed_ids if cid is not None]
        assert len(non_none) == 1

    def test_concurrent_create_and_consume(self, tracker: CheckpointTracker) -> None:
        """Concurrent create + consume must not corrupt internal state.

        Uses a barrier to maximize the chance of true concurrency
        between the create and consume operations.
        """
        barrier = threading.Barrier(2)
        errors: list[str] = []
        created_ids: list[str] = []
        consumed_ids: list[str | None] = []

        def create_worker() -> None:
            try:
                barrier.wait()
                cid = tracker.create_checkpoint(scope=["*"], reason="concurrent")
                created_ids.append(cid)
            except Exception as e:
                errors.append(str(e))

        def consume_worker() -> None:
            try:
                barrier.wait()
                consumed_ids.append(tracker.consume_checkpoint())
            except Exception as e:
                errors.append(str(e))

        # Seed a checkpoint so consume has something to work with
        tracker.create_checkpoint(scope=["*"], reason="seed")

        threads = [
            threading.Thread(target=create_worker),
            threading.Thread(target=consume_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        # Internal state must be consistent: history entries are all valid Checkpoint objects
        for cp in tracker._checkpoint_history:
            assert cp.id is not None
            assert isinstance(cp.scope, list)

    def test_rapid_create_consume_cycles(self, tracker: CheckpointTracker) -> None:
        """Rapid create/consume cycles shouldn't corrupt state."""
        errors: list[str] = []

        def cycle_worker(n: int) -> None:
            for _ in range(n):
                try:
                    tracker.create_checkpoint(scope=["*"], reason="cycle")
                    tracker.consume_checkpoint()
                except Exception as e:
                    errors.append(str(e))

        threads = [threading.Thread(target=cycle_worker, args=(20,)) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # State should be consistent — no active checkpoint after all consumes
        # (unless a create happened after the last consume, which is fine)
        # History entries must all be valid Checkpoint objects
        for cp in tracker._checkpoint_history:
            assert cp.id is not None
            assert isinstance(cp.scope, list)


class TestReservation:
    """A checkpoint covers one mutation: validate_and_reserve() hands it to
    one holder at a time until that holder consumes or releases it."""

    def test_second_holder_sees_reserved(self, tracker: CheckpointTracker) -> None:
        created = tracker.create_checkpoint(scope=["*"], reason="test")
        assert tracker.validate_and_reserve("a") == (True, created)
        assert tracker.validate_and_reserve("a") == (True, created)  # idempotent
        assert tracker.validate_and_reserve("b") == (False, created)
        assert tracker.validate_and_reserve() == (False, created)
        # Still a valid checkpoint, only taken.
        assert tracker.has_valid_checkpoint()

    def test_only_the_holder_releases(self, tracker: CheckpointTracker) -> None:
        created = tracker.create_checkpoint(scope=["*"], reason="test")
        tracker.validate_and_reserve("a")
        assert tracker.release_reservation("b") is False
        assert tracker.validate_and_reserve("b") == (False, created)
        assert tracker.release_reservation("a") is True
        assert tracker.release_reservation("a") is False
        assert tracker.validate_and_reserve("b") == (True, created)

    def test_release_without_holder_releases_any(
        self, tracker: CheckpointTracker
    ) -> None:
        created = tracker.create_checkpoint(scope=["*"], reason="test")
        assert tracker.validate_and_reserve() == (True, created)
        assert tracker.release_reservation() is True
        assert tracker.validate_and_reserve("b") == (True, created)

    def test_only_the_holder_consumes(self, tracker: CheckpointTracker) -> None:
        created = tracker.create_checkpoint(scope=["*"], reason="test")
        tracker.validate_and_reserve("a")
        assert tracker.consume_checkpoint("b") is None
        assert tracker.has_valid_checkpoint()
        assert tracker.consume_checkpoint("a") == created
        assert not tracker.has_valid_checkpoint()

    def test_holder_consumes_its_own_checkpoint_after_a_new_one(
        self, tracker: CheckpointTracker
    ) -> None:
        """A checkpoint created mid-flight is not consumed by the earlier
        holder's success; the reserved (superseded) one is."""
        first = tracker.create_checkpoint(scope=["*"], reason="first")
        tracker.validate_and_reserve("a")
        second = tracker.create_checkpoint(scope=["*"], reason="second")
        assert tracker.consume_checkpoint("a") == first
        assert tracker.get_active_checkpoint_id() == second
        consumed = tracker.get_checkpoint_by_id(first)
        assert consumed is not None and consumed.consumed
        assert tracker.validate_and_reserve("b") == (True, second)

    def test_unheld_consume_keeps_legacy_behaviour(
        self, tracker: CheckpointTracker
    ) -> None:
        created = tracker.create_checkpoint(scope=["*"], reason="test")
        tracker.validate_and_reserve("a")
        assert tracker.consume_checkpoint() == created
        assert tracker.release_reservation("a") is False

    def test_new_checkpoint_is_unreserved(self, tracker: CheckpointTracker) -> None:
        tracker.create_checkpoint(scope=["*"], reason="first")
        tracker.validate_and_reserve("a")
        second = tracker.create_checkpoint(scope=["*"], reason="second")
        assert tracker.validate_and_reserve("b") == (True, second)

    def test_invalidate_all_ends_the_reservation(
        self, tracker: CheckpointTracker
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        tracker.validate_and_reserve("a")
        tracker.invalidate_all()
        assert tracker.release_reservation() is False

    def test_abandoned_reservation_lapses(self, tmp_path: Path) -> None:
        tracker = CheckpointTracker(checkpoint_dir=str(tmp_path), reservation_seconds=0)
        created = tracker.create_checkpoint(scope=["*"], reason="test")
        tracker.validate_and_reserve("a")
        assert tracker.validate_and_reserve("b") == (True, created)

    def test_reservation_is_not_persisted(self, tmp_path: Path) -> None:
        tracker = CheckpointTracker(checkpoint_dir=str(tmp_path))
        created = tracker.create_checkpoint(scope=["*"], reason="test")
        tracker.validate_and_reserve("a")
        reloaded = CheckpointTracker(checkpoint_dir=str(tmp_path))
        assert reloaded.validate_and_reserve("b") == (True, created)

    def test_concurrent_reservations_have_one_winner(
        self, tracker: CheckpointTracker
    ) -> None:
        created = tracker.create_checkpoint(scope=["*"], reason="test")
        workers = 16
        barrier = threading.Barrier(workers)
        results: list[tuple[bool, str | None]] = []
        results_lock = threading.Lock()

        def reserve(holder: str) -> None:
            barrier.wait()
            result = tracker.validate_and_reserve(holder)
            with results_lock:
                results.append(result)

        threads = [
            threading.Thread(target=reserve, args=(f"t{i}",)) for i in range(workers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(results) == [(False, created)] * (workers - 1) + [(True, created)]
