"""Tests for checkpoint persistence across tracker instances (TD-011).

Validates that CheckpointTracker persists state to disk and can
restore it in a new instance, surviving process restarts.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from grounded_agency.state.checkpoint_tracker import Checkpoint, CheckpointTracker


@pytest.fixture
def chk_dir(tmp_path: Path) -> Path:
    """Provide a temporary checkpoint directory."""
    d = tmp_path / "checkpoints"
    d.mkdir()
    return d


@pytest.fixture
def tracker(chk_dir: Path) -> CheckpointTracker:
    """Create a tracker with persistence enabled."""
    return CheckpointTracker(checkpoint_dir=chk_dir)


class TestStatePersistence:
    """Tests for basic state persistence."""

    def test_state_file_created_on_checkpoint(
        self, tracker: CheckpointTracker, chk_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        state_file = chk_dir / "tracker_state.json"
        assert state_file.exists()

    def test_state_file_is_valid_json(
        self, tracker: CheckpointTracker, chk_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        state_file = chk_dir / "tracker_state.json"
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert "active" in data
        assert "history" in data

    def test_state_file_contains_active_checkpoint(
        self, tracker: CheckpointTracker, chk_dir: Path
    ) -> None:
        chk_id = tracker.create_checkpoint(scope=["src/*.py"], reason="refactor")
        state_file = chk_dir / "tracker_state.json"
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["active"] is not None
        assert data["active"]["id"] == chk_id
        assert data["active"]["scope"] == ["src/*.py"]
        assert data["active"]["reason"] == "refactor"

    def test_consume_updates_state_file(
        self, tracker: CheckpointTracker, chk_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        tracker.consume_checkpoint()
        state_file = chk_dir / "tracker_state.json"
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["active"] is None
        assert len(data["history"]) == 1
        assert data["history"][0]["consumed"] is True


class TestCrossInstanceRestore:
    """Tests for restoring state across different tracker instances."""

    def test_restore_active_checkpoint(self, chk_dir: Path) -> None:
        # Instance 1: create checkpoint
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir)
        chk_id = tracker1.create_checkpoint(scope=["*"], reason="persist test")

        # Instance 2: should see the checkpoint
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        assert tracker2.has_valid_checkpoint()
        assert tracker2.get_active_checkpoint_id() == chk_id

    def test_restore_history(self, chk_dir: Path) -> None:
        # Instance 1: create and consume
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir)
        chk_id = tracker1.create_checkpoint(scope=["*"], reason="first")
        tracker1.consume_checkpoint()

        # Instance 2: should see in history
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker2.has_valid_checkpoint()
        restored = tracker2.get_checkpoint_by_id(chk_id)
        assert restored is not None
        assert restored.consumed is True

    def test_restore_scope_matching(self, chk_dir: Path) -> None:
        # Instance 1: create checkpoint with specific scope
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir)
        tracker1.create_checkpoint(scope=["src/*.py", "tests/*.py"], reason="scoped")

        # Instance 2: verify scope matching works
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        assert tracker2.has_checkpoint_for_scope("src/main.py")
        assert tracker2.has_checkpoint_for_scope("tests/test_foo.py")
        assert not tracker2.has_checkpoint_for_scope("docs/README.md")

    def test_restore_metadata(self, chk_dir: Path) -> None:
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir)
        tracker1.create_checkpoint(
            scope=["*"], reason="meta", metadata={"tool": "Edit", "path": "foo.py"}
        )

        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        active = tracker2.get_active_checkpoint()
        assert active is not None
        assert active.metadata == {"tool": "Edit", "path": "foo.py"}


class TestCorruptStateHandling:
    """Tests for graceful handling of corrupt/missing state files."""

    def test_missing_state_file_starts_fresh(self, chk_dir: Path) -> None:
        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker.has_valid_checkpoint()
        assert tracker.checkpoint_count == 0

    def test_corrupt_json_starts_fresh(self, chk_dir: Path) -> None:
        state_file = chk_dir / "tracker_state.json"
        state_file.write_text("{{not valid json", encoding="utf-8")

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker.has_valid_checkpoint()
        assert tracker.checkpoint_count == 0

    def test_empty_state_file_starts_fresh(self, chk_dir: Path) -> None:
        state_file = chk_dir / "tracker_state.json"
        state_file.write_text("", encoding="utf-8")

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker.has_valid_checkpoint()
        assert tracker.checkpoint_count == 0

    def test_missing_fields_starts_fresh(self, chk_dir: Path) -> None:
        state_file = chk_dir / "tracker_state.json"
        state_file.write_text('{"active": {"id": "broken"}}', encoding="utf-8")

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker.has_valid_checkpoint()
        assert tracker.checkpoint_count == 0

    def test_recovery_after_corruption(self, chk_dir: Path) -> None:
        """After loading corrupt state, new checkpoints should persist correctly."""
        state_file = chk_dir / "tracker_state.json"
        state_file.write_text("corrupt", encoding="utf-8")

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        chk_id = tracker.create_checkpoint(scope=["*"], reason="recovery")

        # Verify new state is clean
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        assert tracker2.has_valid_checkpoint()
        assert tracker2.get_active_checkpoint_id() == chk_id


class TestAtomicWrites:
    """Tests for atomic write safety."""

    def test_state_file_not_empty_after_persist(
        self, tracker: CheckpointTracker, chk_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        state_file = chk_dir / "tracker_state.json"
        content = state_file.read_text(encoding="utf-8")
        assert len(content) > 0
        # Validate it's parseable
        json.loads(content)

    def test_no_tmp_files_left_after_persist(
        self, tracker: CheckpointTracker, chk_dir: Path
    ) -> None:
        tracker.create_checkpoint(scope=["*"], reason="test")
        tmp_files = list(chk_dir.glob("*.tmp"))
        assert tmp_files == []

    def test_checkpoint_dir_created_if_missing(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "brand_new_dir"
        tracker = CheckpointTracker(checkpoint_dir=new_dir)
        tracker.create_checkpoint(scope=["*"], reason="test")
        assert (new_dir / "tracker_state.json").exists()


class TestEdgeCases:
    """Tests for edge-case resilience."""

    def test_oversized_state_file_starts_fresh(self, chk_dir: Path) -> None:
        """State file exceeding _MAX_STATE_FILE_BYTES is ignored."""
        state_file = chk_dir / "tracker_state.json"
        # Write a file larger than 10 MB
        state_file.write_text("x" * (10 * 1024 * 1024 + 1), encoding="utf-8")

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker.has_valid_checkpoint()
        assert tracker.checkpoint_count == 0

    def test_persist_failure_does_not_crash(self, tmp_path: Path) -> None:
        """Tracker operates in-memory when persistence fails (read-only dir)."""
        import os
        import platform

        chk_dir = tmp_path / "readonly_dir"
        chk_dir.mkdir()

        # Create the tracker while the dir is writable
        tracker = CheckpointTracker(checkpoint_dir=chk_dir)

        if platform.system() != "Windows":
            # Make directory read-only to force persistence failure
            os.chmod(chk_dir, 0o555)
            try:
                chk_id = tracker.create_checkpoint(scope=["*"], reason="ro test")
                # Should still work in-memory even though persist failed
                assert tracker.has_valid_checkpoint()
                assert tracker.get_active_checkpoint_id() == chk_id
            finally:
                os.chmod(chk_dir, 0o755)


class TestClearExpiredPersistence:
    """Tests for clear_expired persistence behavior."""

    def test_clear_expired_persists_active_removal(self, chk_dir: Path) -> None:
        """Expired active checkpoint is cleared from disk after clear_expired()."""
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir)
        # Create checkpoint that is already expired
        tracker1.create_checkpoint(scope=["*"], reason="will expire", expiry_minutes=0)
        # Force expiry by setting expires_at to the past
        assert tracker1._active_checkpoint is not None
        tracker1._active_checkpoint.expires_at = datetime.now(timezone.utc) - timedelta(
            seconds=10
        )
        tracker1._persist_state()

        # Clear expired
        tracker1.clear_expired()
        assert tracker1._active_checkpoint is None

        # Restore from disk — active should be gone
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker2.has_valid_checkpoint()
        assert tracker2._active_checkpoint is None

    def test_clear_expired_removes_from_history(self, chk_dir: Path) -> None:
        """Expired history entries are removed from disk after clear_expired()."""
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir)
        # Create and consume a checkpoint (moves to history)
        tracker1.create_checkpoint(scope=["*"], reason="will expire", expiry_minutes=0)
        assert tracker1._active_checkpoint is not None
        tracker1._active_checkpoint.expires_at = datetime.now(timezone.utc) - timedelta(
            seconds=10
        )
        tracker1.consume_checkpoint()

        # History should have 1 expired entry
        assert len(tracker1._checkpoint_history) == 1

        tracker1.clear_expired()
        assert len(tracker1._checkpoint_history) == 0

        # Restore — history should be empty on disk too
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        assert tracker2.checkpoint_count == 0


class TestHistoryPruningPersistence:
    """Tests that history pruning is respected during persistence."""

    def test_history_capped_on_persist(self, chk_dir: Path) -> None:
        """Creating more checkpoints than max_history caps persisted history."""
        max_h = 5
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir, max_history=max_h)

        # Create max_h + 3 checkpoints (each new one pushes the previous to history)
        for i in range(max_h + 3):
            tracker1.create_checkpoint(scope=["*"], reason=f"checkpoint {i}")

        # History should be exactly max_h (active is separate)
        assert len(tracker1._checkpoint_history) == max_h

        # Restore from disk — history should still be exactly max_h
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir, max_history=max_h)
        assert len(tracker2._checkpoint_history) == max_h
        # Active + history = max_h + 1
        assert tracker2.checkpoint_count == max_h + 1

    def test_history_cap_on_load_with_large_state(self, chk_dir: Path) -> None:
        """Loading a state file with more entries than max_history caps on read."""
        entries = []
        for i in range(20):
            ts = datetime(2025, 1, 1, 0, i, tzinfo=timezone.utc)
            entries.append(
                {
                    "id": f"chk_old_{i}",
                    "scope": ["*"],
                    "reason": f"old {i}",
                    "created_at": ts.isoformat(),
                    "expires_at": None,
                    "consumed": True,
                    "consumed_at": ts.isoformat(),
                    "metadata": {},
                }
            )

        chk_dir.mkdir(parents=True, exist_ok=True)
        state_path = chk_dir / "tracker_state.json"
        state_path.write_text(
            json.dumps({"active": None, "history": entries}), encoding="utf-8"
        )

        # Load with max_history=5 — should cap at 5
        tracker = CheckpointTracker(checkpoint_dir=chk_dir, max_history=5)
        assert len(tracker._checkpoint_history) == 5


class TestInvalidateAllPersistence:
    """Tests for persistence during invalidate_all."""

    def test_invalidate_all_persists(self, chk_dir: Path) -> None:
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir)
        tracker1.create_checkpoint(scope=["*"], reason="test")
        tracker1.invalidate_all()

        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker2.has_valid_checkpoint()


class TestCheckpointSerialization:
    """Tests for Checkpoint.to_dict() and from_dict()."""

    def test_round_trip(self) -> None:
        chk = Checkpoint(
            id="chk_test_123",
            scope=["src/*.py"],
            reason="testing",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2025, 1, 1, 0, 30, tzinfo=timezone.utc),
            consumed=False,
            metadata={"key": "value"},
        )

        d = chk.to_dict()
        restored = Checkpoint.from_dict(d)

        assert restored.id == chk.id
        assert restored.scope == chk.scope
        assert restored.reason == chk.reason
        assert restored.created_at == chk.created_at
        assert restored.expires_at == chk.expires_at
        assert restored.consumed == chk.consumed
        assert restored.metadata == chk.metadata

    def test_round_trip_consumed(self) -> None:
        chk = Checkpoint(
            id="chk_consumed",
            scope=["*"],
            reason="consumed",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            consumed=True,
            consumed_at=datetime(2025, 1, 1, 0, 5, tzinfo=timezone.utc),
        )

        d = chk.to_dict()
        restored = Checkpoint.from_dict(d)

        assert restored.consumed is True
        assert restored.consumed_at == chk.consumed_at

    def test_round_trip_no_expiry(self) -> None:
        chk = Checkpoint(
            id="chk_no_expiry",
            scope=["*"],
            reason="no expiry",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        d = chk.to_dict()
        restored = Checkpoint.from_dict(d)

        assert restored.expires_at is None


class TestFromDictValidation:
    """Tests for type validation in Checkpoint.from_dict()."""

    def _valid_data(self) -> dict:
        """Return a valid checkpoint dict for mutation-based testing."""
        return {
            "id": "chk_test",
            "scope": ["*"],
            "reason": "test",
            "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
            "metadata": {},
        }

    def test_rejects_non_string_id(self) -> None:
        data = self._valid_data()
        data["id"] = 123
        with pytest.raises(ValueError, match="id must be a string"):
            Checkpoint.from_dict(data)

    def test_rejects_non_list_scope(self) -> None:
        data = self._valid_data()
        data["scope"] = "not-a-list"
        with pytest.raises(ValueError, match="scope must be a list"):
            Checkpoint.from_dict(data)

    def test_rejects_non_string_reason(self) -> None:
        data = self._valid_data()
        data["reason"] = 42
        with pytest.raises(ValueError, match="reason must be a string"):
            Checkpoint.from_dict(data)

    def test_rejects_non_dict_metadata(self) -> None:
        data = self._valid_data()
        data["metadata"] = ["not", "a", "dict"]
        with pytest.raises(ValueError, match="metadata must be a dict"):
            Checkpoint.from_dict(data)

    def test_missing_required_field_raises(self) -> None:
        data = self._valid_data()
        del data["id"]
        with pytest.raises(ValueError, match="id must be a string"):
            Checkpoint.from_dict(data)


class TestArchiveErrorHandling:
    """Tests for per-line error handling in get_archived_checkpoints."""

    def test_corrupt_line_skipped(self, chk_dir: Path) -> None:
        """A single corrupt JSONL line should not abort the entire archive read."""
        archive_dir = chk_dir / "archive"
        archive_dir.mkdir(parents=True)
        archive_file = archive_dir / "pruned_checkpoints.jsonl"

        good_entry = json.dumps({
            "id": "chk_good",
            "scope": ["*"],
            "reason": "good",
            "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
            "metadata": {},
        })
        archive_file.write_text(
            f"{good_entry}\n{{bad json\n{good_entry}\n",
            encoding="utf-8",
        )

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        results = tracker.get_archived_checkpoints()
        # Both good lines should be parsed; the corrupt line is skipped
        assert len(results) == 2
        assert all(r.id == "chk_good" for r in results)

    def test_all_corrupt_lines_returns_empty(self, chk_dir: Path) -> None:
        """If every line is corrupt, return empty list (no crash)."""
        archive_dir = chk_dir / "archive"
        archive_dir.mkdir(parents=True)
        archive_file = archive_dir / "pruned_checkpoints.jsonl"
        archive_file.write_text("not json\nalso not json\n", encoding="utf-8")

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        assert tracker.get_archived_checkpoints() == []

    def test_oversized_archive_file_skipped(self, chk_dir: Path) -> None:
        """Archive files exceeding _MAX_STATE_FILE_BYTES are skipped entirely."""
        archive_dir = chk_dir / "archive"
        archive_dir.mkdir(parents=True)
        archive_file = archive_dir / "pruned_checkpoints.jsonl"

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        # Write a file larger than _MAX_STATE_FILE_BYTES (10 MB)
        archive_file.write_text(
            "x" * (tracker._MAX_STATE_FILE_BYTES + 1), encoding="utf-8"
        )
        assert tracker.get_archived_checkpoints() == []

    def test_empty_archive_returns_empty(self, chk_dir: Path) -> None:
        """Empty archive file returns empty list."""
        archive_dir = chk_dir / "archive"
        archive_dir.mkdir(parents=True)
        (archive_dir / "pruned_checkpoints.jsonl").write_text("", encoding="utf-8")

        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        assert tracker.get_archived_checkpoints() == []


class TestSymlinkStateFileRejection:
    """Tests that _load_persisted_state rejects symlinked state files."""

    def test_rejects_symlink_state_file(self, chk_dir: Path) -> None:
        """A symlinked tracker_state.json should be refused, starting fresh."""
        # Create a real state file elsewhere
        real_dir = chk_dir.parent / "real_checkpoints"
        real_dir.mkdir()
        real_state = real_dir / "tracker_state.json"
        real_state.write_text(
            json.dumps(
                {
                    "active": {
                        "id": "chk_symlink",
                        "scope": ["*"],
                        "reason": "symlinked",
                        "created_at": datetime(
                            2025, 1, 1, tzinfo=timezone.utc
                        ).isoformat(),
                        "metadata": {},
                    },
                    "history": [],
                }
            ),
            encoding="utf-8",
        )

        # Symlink state file into the checkpoint dir
        chk_dir.mkdir(parents=True, exist_ok=True)
        symlink_path = chk_dir / "tracker_state.json"
        symlink_path.symlink_to(real_state)

        # Tracker should refuse the symlink and start fresh
        tracker = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker.has_valid_checkpoint()
        assert tracker.checkpoint_count == 0
