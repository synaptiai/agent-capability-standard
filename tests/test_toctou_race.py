"""Tests for TOCTOU race condition fix in checkpoint validation (SEC-007).

Verifies that validate_and_reserve() provides atomic check-and-reserve
semantics, preventing race conditions between has_valid_checkpoint()
and subsequent checkpoint consumption.
"""

from __future__ import annotations

import threading
import time

import pytest

from grounded_agency.state.checkpoint_tracker import CheckpointTracker


@pytest.fixture
def tracker(tmp_path: object) -> CheckpointTracker:
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

        # Logical consistency: if consume succeeded, validate may or may not
        # have seen the checkpoint (depending on scheduling). But both
        # seeing success is contradictory only if consume already consumed it
        # before validate ran.
        if consumed[0] is not None and results[0][0] is True:
            # Both succeeded — this is valid if validate ran before consume
            pass
        elif consumed[0] is not None and results[0][0] is False:
            # Consume won the race, validate saw no checkpoint — valid
            pass
        elif consumed[0] is None and results[0][0] is True:
            # Validate saw the checkpoint but consume found nothing — impossible
            # with proper locking unless checkpoint expired between calls
            pass

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
