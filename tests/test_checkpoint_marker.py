"""Tests for CheckpointTracker marker file bridge (SEC-001).

Validates that the Python CheckpointTracker correctly writes and removes
the .claude/checkpoint.ok marker file used by the shell PreToolUse hook.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from grounded_agency.state.checkpoint_tracker import CheckpointTracker


@pytest.fixture
def marker_dir(tmp_path: Path) -> Path:
    """Create a temporary .claude directory for marker files."""
    d = tmp_path / ".claude"
    d.mkdir()
    return d


@pytest.fixture
def tracker(marker_dir: Path) -> CheckpointTracker:
    """Create a CheckpointTracker with marker support."""
    return CheckpointTracker(marker_dir=marker_dir)


@pytest.fixture
def tracker_no_marker() -> CheckpointTracker:
    """Create a CheckpointTracker without marker support."""
    return CheckpointTracker()


class TestMarkerFileCreation:
    """Tests for marker file creation on checkpoint creation."""

    def test_create_checkpoint_writes_marker(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        marker = marker_dir / "checkpoint.ok"
        assert marker.exists()

    def test_marker_contains_valid_json(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        marker = marker_dir / "checkpoint.ok"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert "checkpoint_id" in data
        assert "created_at" in data
        assert "expires_at" in data

    def test_marker_checkpoint_id_matches(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        chk_id = tracker.create_checkpoint(scope=["*"], reason="test")
        marker = marker_dir / "checkpoint.ok"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["checkpoint_id"] == chk_id

    def test_marker_timestamps_are_integers(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        marker = marker_dir / "checkpoint.ok"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert isinstance(data["created_at"], int)
        assert isinstance(data["expires_at"], int)

    def test_marker_expires_at_is_in_future(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        marker = marker_dir / "checkpoint.ok"
        data = json.loads(marker.read_text(encoding="utf-8"))
        now = int(datetime.now(timezone.utc).timestamp())
        assert data["expires_at"] > now

    def test_no_marker_when_marker_dir_not_set(
        self, tracker_no_marker: CheckpointTracker, tmp_path: Path
    ) -> None:
        tracker_no_marker.create_checkpoint(scope=["*"], reason="test")
        # No marker file should exist anywhere in tmp_path
        assert not list(tmp_path.rglob("checkpoint.ok"))


class TestMarkerFileRemoval:
    """Tests for marker file removal on checkpoint consumption/invalidation."""

    def test_consume_removes_marker(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        marker = marker_dir / "checkpoint.ok"
        assert marker.exists()

        tracker.consume_checkpoint()
        assert not marker.exists()

    def test_invalidate_all_removes_marker(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        marker = marker_dir / "checkpoint.ok"
        assert marker.exists()

        tracker.invalidate_all()
        assert not marker.exists()

    def test_clear_expired_removes_marker_for_expired_active(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        # Create checkpoint with already-expired time
        tracker.create_checkpoint(scope=["*"], reason="test", expiry_minutes=0)
        # Force expiry by manipulating the checkpoint
        active = tracker._active_checkpoint
        assert active is not None
        active.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        marker = marker_dir / "checkpoint.ok"
        assert marker.exists()

        tracker.clear_expired()
        assert not marker.exists()

    def test_consume_without_marker_dir_does_not_raise(
        self, tracker_no_marker: CheckpointTracker
    ) -> None:
        tracker_no_marker.create_checkpoint(scope=["*"], reason="test")
        # Should not raise even without marker_dir
        consumed = tracker_no_marker.consume_checkpoint()
        assert consumed is not None


class TestMarkerFileOverwrite:
    """Tests for marker file replacement when creating new checkpoints."""

    def test_new_checkpoint_overwrites_marker(
        self, tracker: CheckpointTracker, marker_dir: Path
    ) -> None:
        id1 = tracker.create_checkpoint(scope=["*"], reason="first")
        id2 = tracker.create_checkpoint(scope=["*"], reason="second")
        marker = marker_dir / "checkpoint.ok"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["checkpoint_id"] == id2
        assert data["checkpoint_id"] != id1

    def test_marker_dir_created_if_missing(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "new_claude_dir"
        tracker = CheckpointTracker(marker_dir=new_dir)
        tracker.create_checkpoint(scope=["*"], reason="test")
        assert (new_dir / "checkpoint.ok").exists()
