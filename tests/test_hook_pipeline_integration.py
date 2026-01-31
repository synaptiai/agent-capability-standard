"""Integration tests for the dual-layer safety enforcement pipeline (TD-003).

Tests the composition of shell hooks and Python CheckpointTracker
to verify the full safety lifecycle works end-to-end:

1. Shell↔Python checkpoint bridge
2. Full lifecycle with evidence
3. Cross-process checkpoint persistence
4. Audit log integrity
5. Permission enforcement round-trip

Shell-dependent tests are marked with ``@pytest.mark.skipif`` for CI portability.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.state.evidence_store import EvidenceAnchor, EvidenceStore

ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / "hooks"
PRETOOLUSE_HOOK = HOOKS_DIR / "pretooluse_require_checkpoint.sh"
POSTTOOLUSE_HOOK = HOOKS_DIR / "posttooluse_log_tool.sh"

HAS_BASH = shutil.which("bash") is not None
HAS_JQ = shutil.which("jq") is not None
HAS_OPENSSL = shutil.which("openssl") is not None

skip_no_bash = pytest.mark.skipif(not HAS_BASH, reason="bash not available")
skip_no_jq = pytest.mark.skipif(not HAS_JQ, reason="jq not available")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Set up a temporary project directory with .claude/ subdirectory."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    return tmp_path


@pytest.fixture
def tracker_with_marker(project_dir: Path) -> CheckpointTracker:
    """Create a tracker that writes both state file and shell marker."""
    chk_dir = project_dir / ".checkpoints"
    chk_dir.mkdir()
    return CheckpointTracker(
        checkpoint_dir=chk_dir,
        marker_dir=project_dir / ".claude",
    )


def _minimal_env(overrides: dict[str, str]) -> dict[str, str]:
    """Build a minimal, deterministic environment for shell hook tests.

    Only passes PATH, HOME, and SHELL from the host to avoid
    non-deterministic behaviour from leaked environment variables.
    """
    base = {}
    for key in ("PATH", "HOME", "SHELL", "TMPDIR"):
        if key in os.environ:
            base[key] = os.environ[key]
    base.update(overrides)
    return base


def _run_hook(hook_path: Path, payload: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    """Execute a shell hook script with the given payload and environment."""
    return subprocess.run(
        ["bash", str(hook_path), payload],
        capture_output=True,
        text=True,
        env=_minimal_env(env),
        timeout=10,
    )


# ------------------------------------------------------------------
# 1. Shell ↔ Python checkpoint bridge
# ------------------------------------------------------------------


class TestCheckpointBridge:
    """Verify that Python tracker creates marker files the shell hook accepts."""

    @skip_no_bash
    def test_shell_hook_passes_with_valid_marker(
        self, tracker_with_marker: CheckpointTracker, project_dir: Path
    ) -> None:
        """create_checkpoint() writes marker; shell hook should pass."""
        tracker_with_marker.create_checkpoint(scope=["*"], reason="integration test")

        marker = project_dir / ".claude" / "checkpoint.ok"
        assert marker.exists(), "Python tracker should create marker file"

        result = _run_hook(
            PRETOOLUSE_HOOK,
            '{"tool_name": "Edit"}',
            {"CLAUDE_PROJECT_DIR": str(project_dir)},
        )
        assert result.returncode == 0, f"Hook should pass: {result.stderr}"

    @skip_no_bash
    def test_shell_hook_blocks_without_marker(
        self, project_dir: Path
    ) -> None:
        """Without marker file, shell hook should block mutation."""
        result = _run_hook(
            PRETOOLUSE_HOOK,
            '{"tool_name": "Edit"}',
            {"CLAUDE_PROJECT_DIR": str(project_dir)},
        )
        assert result.returncode != 0, "Hook should block without marker"
        output = (result.stdout + result.stderr).lower()
        assert "checkpoint" in output or "blocked" in output

    @skip_no_bash
    def test_consume_removes_marker_shell_blocks(
        self, tracker_with_marker: CheckpointTracker, project_dir: Path
    ) -> None:
        """After consume, marker is gone and shell hook should block again."""
        tracker_with_marker.create_checkpoint(scope=["*"], reason="test")
        tracker_with_marker.consume_checkpoint()

        marker = project_dir / ".claude" / "checkpoint.ok"
        assert not marker.exists(), "consume should remove marker"

        result = _run_hook(
            PRETOOLUSE_HOOK,
            '{"tool_name": "Edit"}',
            {"CLAUDE_PROJECT_DIR": str(project_dir)},
        )
        assert result.returncode != 0, "Hook should block after consume"
        output = (result.stdout + result.stderr).lower()
        assert "checkpoint" in output or "blocked" in output

    @skip_no_bash
    def test_state_file_and_marker_both_written(
        self, tracker_with_marker: CheckpointTracker, project_dir: Path
    ) -> None:
        """create_checkpoint() should write both persistence state and shell marker."""
        tracker_with_marker.create_checkpoint(scope=["*"], reason="dual write")

        state_file = project_dir / ".checkpoints" / "tracker_state.json"
        marker_file = project_dir / ".claude" / "checkpoint.ok"

        assert state_file.exists(), "State file should exist for persistence"
        assert marker_file.exists(), "Marker file should exist for shell hook"


# ------------------------------------------------------------------
# 2. Full lifecycle with evidence
# ------------------------------------------------------------------


class TestFullLifecycle:
    """Test a complete create → use → consume cycle with evidence."""

    def test_lifecycle_with_evidence_collection(
        self, tracker_with_marker: CheckpointTracker
    ) -> None:
        """Full lifecycle: create → verify valid → collect evidence → consume."""
        store = EvidenceStore()

        # Create checkpoint
        chk_id = tracker_with_marker.create_checkpoint(
            scope=["src/*.py"],
            reason="Before editing source files",
        )
        assert tracker_with_marker.has_valid_checkpoint()
        assert tracker_with_marker.has_checkpoint_for_scope("src/main.py")

        # Simulate evidence collection during tool execution
        anchor = EvidenceAnchor.from_tool_output(
            tool_name="Edit",
            tool_use_id="test_001",
            tool_input={"path": "src/main.py"},
        )
        store.add_anchor(anchor)

        # Consume after successful mutation
        consumed_id = tracker_with_marker.consume_checkpoint()
        assert consumed_id == chk_id
        assert not tracker_with_marker.has_valid_checkpoint()

        # Evidence is retained
        assert len(store) == 1
        assert store.get_recent(1) == ["tool:Edit:test_001"]


# ------------------------------------------------------------------
# 3. Cross-process checkpoint persistence
# ------------------------------------------------------------------


class TestCrossProcessPersistence:
    """Verify state survives across tracker instances (simulates process restart)."""

    def test_checkpoint_survives_restart(self, project_dir: Path) -> None:
        """Checkpoint created by one tracker instance is visible to another."""
        chk_dir = project_dir / ".checkpoints"
        chk_dir.mkdir()
        marker_dir = project_dir / ".claude"

        # Process 1
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir, marker_dir=marker_dir)
        chk_id = tracker1.create_checkpoint(scope=["*"], reason="cross-process")

        # Process 2 (new instance, same dirs)
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir, marker_dir=marker_dir)
        assert tracker2.has_valid_checkpoint()
        assert tracker2.get_active_checkpoint_id() == chk_id

    def test_consumed_state_survives_restart(self, project_dir: Path) -> None:
        """Consumed state is visible to a new tracker instance."""
        chk_dir = project_dir / ".checkpoints"
        chk_dir.mkdir()

        # Process 1
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir)
        chk_id = tracker1.create_checkpoint(scope=["*"], reason="consume test")
        tracker1.consume_checkpoint()

        # Process 2
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir)
        assert not tracker2.has_valid_checkpoint()
        chk = tracker2.get_checkpoint_by_id(chk_id)
        assert chk is not None
        assert chk.consumed is True

    @skip_no_bash
    def test_cross_process_shell_hook_consistency(self, project_dir: Path) -> None:
        """Shell hook agrees with Python state across tracker restarts."""
        chk_dir = project_dir / ".checkpoints"
        chk_dir.mkdir()
        marker_dir = project_dir / ".claude"

        # Process 1: create checkpoint
        tracker1 = CheckpointTracker(checkpoint_dir=chk_dir, marker_dir=marker_dir)
        tracker1.create_checkpoint(scope=["*"], reason="shell test")

        # Shell hook should pass (marker exists from tracker1)
        result = _run_hook(
            PRETOOLUSE_HOOK,
            '{"tool_name": "Bash"}',
            {"CLAUDE_PROJECT_DIR": str(project_dir)},
        )
        assert result.returncode == 0

        # Process 2: new tracker, consume
        tracker2 = CheckpointTracker(checkpoint_dir=chk_dir, marker_dir=marker_dir)
        tracker2.consume_checkpoint()

        # Shell hook should now block
        result = _run_hook(
            PRETOOLUSE_HOOK,
            '{"tool_name": "Bash"}',
            {"CLAUDE_PROJECT_DIR": str(project_dir)},
        )
        assert result.returncode != 0, "Hook should block after cross-process consume"
        output = (result.stdout + result.stderr).lower()
        assert "checkpoint" in output or "blocked" in output


# ------------------------------------------------------------------
# 4. Audit log integrity
# ------------------------------------------------------------------


class TestAuditLogIntegrity:
    """Test that the PostToolUse hook produces valid, chained audit log entries."""

    @skip_no_bash
    @skip_no_jq
    def test_audit_log_entry_written(self, project_dir: Path) -> None:
        """PostToolUse hook writes a JSON entry to audit.log."""
        payload = json.dumps({
            "tool_name": "Skill",
            "tool_input": {"skill": "test-skill", "args": ""},
        })

        result = subprocess.run(
            ["bash", str(POSTTOOLUSE_HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            env=_minimal_env({"CLAUDE_PROJECT_DIR": str(project_dir)}),
            timeout=10,
        )
        assert result.returncode == 0

        log_file = project_dir / ".claude" / "audit.log"
        assert log_file.exists(), "Audit log should be created"

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1

        entry = json.loads(lines[-1])
        assert entry["skill"] == "test-skill"
        assert "ts" in entry
        assert "hmac" in entry

    @skip_no_bash
    @skip_no_jq
    def test_audit_log_hmac_chain(self, project_dir: Path) -> None:
        """Two consecutive entries form an HMAC chain (prev_hmac links)."""
        for i in range(2):
            payload = json.dumps({
                "tool_name": "Skill",
                "tool_input": {"skill": f"skill-{i}", "args": ""},
            })
            subprocess.run(
                ["bash", str(POSTTOOLUSE_HOOK)],
                input=payload,
                capture_output=True,
                text=True,
                env=_minimal_env({"CLAUDE_PROJECT_DIR": str(project_dir)}),
                timeout=10,
            )

        log_file = project_dir / ".claude" / "audit.log"
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        entry0 = json.loads(lines[0])
        entry1 = json.loads(lines[1])

        # First entry's prev_hmac should be empty
        assert entry0["prev_hmac"] == ""
        # Second entry should chain to first
        assert entry1["prev_hmac"] == entry0["hmac"]

    @skip_no_bash
    @skip_no_jq
    def test_non_skill_invocations_not_logged(self, project_dir: Path) -> None:
        """PostToolUse hook should skip non-Skill tool invocations."""
        payload = json.dumps({
            "tool_name": "Read",
            "tool_input": {"path": "/some/file"},
        })

        subprocess.run(
            ["bash", str(POSTTOOLUSE_HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            env=_minimal_env({"CLAUDE_PROJECT_DIR": str(project_dir)}),
            timeout=10,
        )

        log_file = project_dir / ".claude" / "audit.log"
        # Log file should not exist or be empty
        if log_file.exists():
            assert log_file.read_text(encoding="utf-8").strip() == ""


# ------------------------------------------------------------------
# 5. Permission enforcement round-trip
# ------------------------------------------------------------------


class TestPermissionEnforcement:
    """Test strict-mode permission enforcement using checkpoints."""

    @skip_no_bash
    def test_deny_create_allow_consume_deny(
        self, project_dir: Path
    ) -> None:
        """Full cycle: deny → create → allow → consume → deny again."""
        chk_dir = project_dir / ".checkpoints"
        chk_dir.mkdir()
        marker_dir = project_dir / ".claude"

        env = {"CLAUDE_PROJECT_DIR": str(project_dir)}
        mutation_payload = '{"tool_name": "Edit"}'

        # Step 1: No checkpoint — should be blocked
        result = _run_hook(PRETOOLUSE_HOOK, mutation_payload, env)
        assert result.returncode != 0, "Should block without checkpoint"
        output = (result.stdout + result.stderr).lower()
        assert "checkpoint" in output or "blocked" in output

        # Step 2: Create checkpoint
        tracker = CheckpointTracker(checkpoint_dir=chk_dir, marker_dir=marker_dir)
        tracker.create_checkpoint(scope=["*"], reason="permission test")

        # Step 3: With checkpoint — should be allowed
        result = _run_hook(PRETOOLUSE_HOOK, mutation_payload, env)
        assert result.returncode == 0, f"Should allow with checkpoint: {result.stderr}"

        # Step 4: Consume checkpoint
        tracker.consume_checkpoint()

        # Step 5: After consume — should be blocked again
        result = _run_hook(PRETOOLUSE_HOOK, mutation_payload, env)
        assert result.returncode != 0, "Should block after consume"
        output = (result.stdout + result.stderr).lower()
        assert "checkpoint" in output or "blocked" in output

    @skip_no_bash
    def test_non_mutation_always_allowed(self, project_dir: Path) -> None:
        """Non-mutation tools should always pass, even without a checkpoint."""
        env = {"CLAUDE_PROJECT_DIR": str(project_dir)}

        # Read is not a mutation tool — should pass without checkpoint
        result = _run_hook(
            PRETOOLUSE_HOOK,
            '{"tool_name": "Read"}',
            env,
        )
        assert result.returncode == 0, "Read should always be allowed"
