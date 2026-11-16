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


def call(tool: str, **tool_input: object) -> str:
    """Claude Code's PreToolUse payload: the hook reads only this JSON
    object (STANDARD 1.2.0 §5.18.8)."""
    return json.dumps(
        {
            "tool_name": tool,
            "tool_input": tool_input,
            "permission_mode": "default",
            "tool_use_id": f"t-{tool}",
        }
    )


def run_pretooluse(
    payload: str, project_dir: str, approval: str = "off"
) -> subprocess.CompletedProcess[str]:
    """Run pretooluse hook with given payload and project dir. Approval is
    off unless a test asks for it: with it, an allowed mutation exits 0 and
    prints an "ask" decision instead."""
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = project_dir
    env["ACS_HOOK_APPROVAL"] = approval
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
        result = run_pretooluse(call("Write", file_path="file.py"), project_dir)
        assert result.returncode == 0, f"PreToolUse blocked: {result.stderr}"

        # Step 4: PostToolUse should log a Skill invocation
        skill_payload = {
            "tool_name": "Skill",
            "tool_input": {"skill": "checkpoint", "args": ""},
        }
        result = run_posttooluse(skill_payload, project_dir)
        assert result.returncode == 0

        # Step 5: Verify audit log
        audit_log = marker_dir / "audit.log"
        assert audit_log.exists(), "PostToolUse hook should have created audit.log"
        entries = audit_log.read_text().strip().split("\n")
        assert len(entries) >= 1
        entry = json.loads(entries[-1])
        assert entry["tool"] == "Skill"
        assert entry["details"]["skill"] == "checkpoint"

    def test_no_checkpoint_blocks_mutation(self, tmp_path: Path) -> None:
        """Without checkpoint, PreToolUse should block mutations."""
        project_dir = str(tmp_path)
        # No checkpoint created — no marker file

        result = run_pretooluse(call("Write", file_path="file.py"), project_dir)
        assert result.returncode == 2

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
        result = run_pretooluse(call("Write", file_path="file.py"), project_dir)
        assert result.returncode == 0

        # Consume the checkpoint (simulating post-mutation)
        tracker.consume_checkpoint()

        # Next mutation should be blocked: the hook used the marker itself
        # (one marker per gated call), and the tracker removed it too
        result = run_pretooluse(call("Edit", file_path="other.py"), project_dir)
        assert result.returncode == 2


class TestHookMatcherRouting:
    """Test that hooks only fire for their target tools."""

    def test_pretooluse_ignores_read_operations(self) -> None:
        """A Read call passes: hooks.json does not route it here, and the
        hook gates only the tools it is routed (not by the payload's
        words)."""
        result = run_pretooluse(call("Read", file_path="f"), "/nonexistent")
        assert result.returncode == 0

    def test_pretooluse_catches_write(self, tmp_path: Path) -> None:
        result = run_pretooluse(call("Write", file_path="f"), str(tmp_path))
        assert result.returncode == 2

    def test_pretooluse_catches_edit(self, tmp_path: Path) -> None:
        result = run_pretooluse(call("Edit", file_path="f"), str(tmp_path))
        assert result.returncode == 2

    def test_pretooluse_catches_bash(self, tmp_path: Path) -> None:
        result = run_pretooluse(call("Bash", command="rm -rf /tmp/test"), str(tmp_path))
        assert result.returncode == 2

    def test_pretooluse_catches_multiedit(self, tmp_path: Path) -> None:
        """MultiEdit should trigger checkpoint check and be blocked without marker."""
        result = run_pretooluse(call("MultiEdit", file_path="f"), str(tmp_path))
        assert result.returncode == 2, (
            "MultiEdit should be caught as a mutation and blocked without checkpoint"
        )

    def test_pretooluse_catches_notebookedit(self, tmp_path: Path) -> None:
        """NotebookEdit should trigger checkpoint check and be blocked without marker."""
        result = run_pretooluse(
            call("NotebookEdit", notebook_path="n.ipynb"), str(tmp_path)
        )
        assert result.returncode == 2, (
            "NotebookEdit should be caught as a mutation and blocked without checkpoint"
        )

    def test_posttooluse_logs_every_tool(self, tmp_path: Path) -> None:
        """PostToolUse logs every tool call, not only Skill invocations."""
        for tool_name in ("Read", "Bash", "Skill", "mcp__github__get_me"):
            payload = {"tool_name": tool_name, "tool_input": {"path": "/tmp/x"}}
            result = run_posttooluse(payload, str(tmp_path))
            assert result.returncode == 0

        audit_log = tmp_path / ".claude" / "audit.log"
        entries = [json.loads(line) for line in audit_log.read_text().splitlines()]
        assert [entry["tool"] for entry in entries] == [
            "Read",
            "Bash",
            "Skill",
            "mcp__github__get_me",
        ]
        assert "/tmp/x" not in audit_log.read_text()

    def test_posttooluse_matcher_routes_every_tool(self) -> None:
        """hooks.json sends every tool call, succeeded or failed, to the log hook."""
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        for event in ("PostToolUse", "PostToolUseFailure"):
            logging = [
                group["matcher"]
                for group in hooks[event]
                if any(
                    h["command"].endswith("posttooluse_log_tool.sh")
                    for h in group["hooks"]
                )
            ]
            assert logging == ["*"]


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
        result = run_pretooluse(call("Write", file_path="f"), str(tmp_path))
        assert result.returncode == 0

        # Python consumes checkpoint (removes marker)
        tracker.consume_checkpoint()

        # Shell hook now blocks
        result = run_pretooluse(call("Write", file_path="f"), str(tmp_path))
        assert result.returncode == 2

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
        result = run_pretooluse(call("Write", file_path="f"), str(tmp_path))
        assert result.returncode == 0
