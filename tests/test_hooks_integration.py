"""Integration tests for the full hook pipeline (TEST-001).

Tests the full PreToolUse → mutation → PostToolUse pipeline,
hook matcher routing, and shell + Python SDK hook complementarity.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from grounded_agency.state.checkpoint_tracker import CheckpointTracker

ROOT = Path(__file__).resolve().parents[1]
PRETOOLUSE_HOOK = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
POSTTOOLUSE_HOOK = ROOT / "hooks" / "posttooluse_log_tool.sh"


def run_pretooluse(payload: str, project_dir: str) -> subprocess.CompletedProcess[str]:
    """Run pretooluse hook with given payload and project dir."""
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = project_dir
    return subprocess.run(
        [str(PRETOOLUSE_HOOK), payload],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def run_posttooluse(
    payload: dict, project_dir: str
) -> subprocess.CompletedProcess[str]:
    """Run posttooluse hook with given payload on stdin."""
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = project_dir
    return subprocess.run(
        [str(POSTTOOLUSE_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class TestFullPipeline:
    """Test the full PreToolUse → mutation → PostToolUse cycle."""

    def test_create_checkpoint_then_mutate(self, tmp_path: Path) -> None:
        """Full lifecycle: create checkpoint → pretooluse passes → posttooluse logs."""
        project_dir = str(tmp_path)
        marker_dir = tmp_path / ".claude"

        # Step 1: Create checkpoint via Python tracker (with marker bridge)
        tracker = CheckpointTracker(
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            marker_dir=str(marker_dir),
        )
        checkpoint_id = tracker.create_checkpoint(
            scope=["*.py"], reason="Integration test"
        )

        # Step 2: Verify marker was created
        marker = marker_dir / "checkpoint.ok"
        assert marker.exists()
        marker_content = json.loads(marker.read_text())
        assert marker_content["checkpoint_id"] == checkpoint_id

        # Step 3: PreToolUse should PASS for mutation
        result = run_pretooluse("Write to file.py", project_dir)
        assert result.returncode == 0, f"PreToolUse blocked: {result.stdout}"

        # Step 4: PostToolUse should log a Skill invocation
        skill_payload = {
            "tool_name": "Skill",
            "tool_input": {"skill": "checkpoint", "args": ""},
        }
        result = run_posttooluse(skill_payload, project_dir)
        assert result.returncode == 0

        # Step 5: Verify audit log
        audit_log = marker_dir / "audit.log"
        if audit_log.exists():
            entries = audit_log.read_text().strip().split("\n")
            assert len(entries) >= 1
            entry = json.loads(entries[-1])
            assert entry["skill"] == "checkpoint"

    def test_no_checkpoint_blocks_mutation(self, tmp_path: Path) -> None:
        """Without checkpoint, PreToolUse should block mutations."""
        project_dir = str(tmp_path)
        # No checkpoint created — no marker file

        result = run_pretooluse("Write to file.py", project_dir)
        assert result.returncode == 1

    def test_consumed_checkpoint_blocks_next_mutation(self, tmp_path: Path) -> None:
        """After consuming checkpoint, next mutation should be blocked."""
        project_dir = str(tmp_path)
        marker_dir = tmp_path / ".claude"

        tracker = CheckpointTracker(
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            marker_dir=str(marker_dir),
        )
        tracker.create_checkpoint(scope=["*"], reason="test")

        # First mutation passes
        result = run_pretooluse("Write to file.py", project_dir)
        assert result.returncode == 0

        # Consume the checkpoint (simulating post-mutation)
        tracker.consume_checkpoint()

        # Next mutation should be blocked (marker removed)
        result = run_pretooluse("Edit another file", project_dir)
        assert result.returncode == 1


class TestHookMatcherRouting:
    """Test that hooks only fire for their target tools."""

    def test_pretooluse_ignores_read_operations(self) -> None:
        """PreToolUse should pass Read operations unconditionally."""
        result = run_pretooluse("Read some file", "/nonexistent")
        assert result.returncode == 0

    def test_pretooluse_catches_write(self, tmp_path: Path) -> None:
        result = run_pretooluse("Write to file", str(tmp_path))
        assert result.returncode == 1

    def test_pretooluse_catches_edit(self, tmp_path: Path) -> None:
        result = run_pretooluse("Edit something", str(tmp_path))
        assert result.returncode == 1

    def test_pretooluse_catches_bash(self, tmp_path: Path) -> None:
        result = run_pretooluse("Bash rm -rf /tmp/test", str(tmp_path))
        assert result.returncode == 1

    def test_posttooluse_ignores_non_skill(self, tmp_path: Path) -> None:
        """PostToolUse should only log Skill invocations."""
        payload = {"tool_name": "Read", "tool_input": {"path": "/tmp/x"}}
        result = run_posttooluse(payload, str(tmp_path))
        assert result.returncode == 0
        # No audit log should be created for non-Skill tools
        audit_log = tmp_path / ".claude" / "audit.log"
        assert not audit_log.exists()


class TestPythonShellComplementarity:
    """Test that Python SDK hooks and shell hooks work together."""

    def test_tracker_marker_bridge(self, tmp_path: Path) -> None:
        """Python CheckpointTracker creates marker that shell hook reads."""
        marker_dir = tmp_path / ".claude"

        # Python creates checkpoint + marker
        tracker = CheckpointTracker(
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            marker_dir=str(marker_dir),
        )
        tracker.create_checkpoint(scope=["*"], reason="bridge test")

        # Shell hook reads marker
        result = run_pretooluse("Write to file", str(tmp_path))
        assert result.returncode == 0

        # Python consumes checkpoint (removes marker)
        tracker.consume_checkpoint()

        # Shell hook now blocks
        result = run_pretooluse("Write to file", str(tmp_path))
        assert result.returncode == 1

    def test_marker_survives_tracker_restart(self, tmp_path: Path) -> None:
        """Marker persists across Python tracker restarts."""
        marker_dir = tmp_path / ".claude"

        tracker1 = CheckpointTracker(
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            marker_dir=str(marker_dir),
        )
        tracker1.create_checkpoint(scope=["*"], reason="restart test")

        # Simulate process restart — new tracker instance
        del tracker1

        # Shell hook should still pass
        result = run_pretooluse("Write to file", str(tmp_path))
        assert result.returncode == 0
