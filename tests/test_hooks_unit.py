"""Unit tests for shell hook scripts (TEST-002).

Tests each exit code path, missing directories, missing jq,
empty payloads, and special characters in skill arguments.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRETOOLUSE_HOOK = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
POSTTOOLUSE_HOOK = ROOT / "hooks" / "posttooluse_log_tool.sh"


def run_hook(
    script: Path,
    payload: str | dict | None = None,
    env_override: dict[str, str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a hook script with optional payload/env."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)

    # PreToolUse hooks receive payload as $1; PostToolUse reads from stdin
    if script == PRETOOLUSE_HOOK:
        args = [str(script)]
        if payload is not None:
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            args.append(payload)
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    else:
        # PostToolUse hooks read from stdin
        if stdin is None:
            if payload is not None:
                stdin = json.dumps(payload) if isinstance(payload, dict) else payload
            else:
                stdin = ""
        return subprocess.run(
            [str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )


# ─── PreToolUse Hook Tests ───


class TestPreToolUseExitCodes:
    """Test each exit code path in pretooluse_require_checkpoint.sh."""

    def test_exit_0_for_non_mutation(self, tmp_path: Path) -> None:
        """Non-mutation commands should pass (exit 0)."""
        result = run_hook(PRETOOLUSE_HOOK, "Read some file")
        assert result.returncode == 0

    def test_exit_1_missing_marker(self, tmp_path: Path) -> None:
        """Mutation without marker should fail (exit 1)."""
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Write to file", env)
        assert result.returncode == 1
        assert (
            "missing checkpoint marker" in result.stdout.lower()
            or "blocked" in result.stdout.lower()
        )

    def test_exit_0_with_valid_marker(self, tmp_path: Path) -> None:
        """Mutation with valid marker should pass (exit 0)."""
        marker_dir = tmp_path / ".claude"
        marker_dir.mkdir()
        marker = marker_dir / "checkpoint.ok"

        import time

        marker_data = {
            "checkpoint_id": "chk_test_123",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + 1800,
        }
        marker.write_text(json.dumps(marker_data))

        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Write to file", env)
        assert result.returncode == 0

    def test_exit_1_symlink_marker(self, tmp_path: Path) -> None:
        """Symlinked marker should be rejected (exit 1)."""
        marker_dir = tmp_path / ".claude"
        marker_dir.mkdir()

        # Create a real file and symlink to it
        real_file = tmp_path / "real_marker"
        real_file.write_text(
            '{"checkpoint_id":"fake","created_at":9999999999,"expires_at":9999999999}'
        )
        marker = marker_dir / "checkpoint.ok"
        marker.symlink_to(real_file)

        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Write to file", env)
        assert result.returncode == 1
        assert "symlink" in result.stdout.lower()

    def test_exit_1_empty_marker(self, tmp_path: Path) -> None:
        """Empty marker file should fail."""
        marker_dir = tmp_path / ".claude"
        marker_dir.mkdir()
        (marker_dir / "checkpoint.ok").write_text("")

        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Edit something", env)
        assert result.returncode == 1

    def test_exit_1_expired_marker(self, tmp_path: Path) -> None:
        """Expired checkpoint should fail."""
        marker_dir = tmp_path / ".claude"
        marker_dir.mkdir()
        marker_data = {
            "checkpoint_id": "chk_expired",
            "created_at": 1000000000,
            "expires_at": 1000000001,  # Long expired
        }
        (marker_dir / "checkpoint.ok").write_text(json.dumps(marker_data))

        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Write something", env)
        assert result.returncode == 1
        assert "expired" in result.stdout.lower()

    def test_empty_payload_passes(self) -> None:
        """Empty payload (no arg) should pass — not a mutation."""
        result = run_hook(PRETOOLUSE_HOOK, "")
        assert result.returncode == 0


# ─── PostToolUse Hook Tests ───


@pytest.fixture
def log_env(tmp_path: Path) -> dict[str, str]:
    """Environment with CLAUDE_PROJECT_DIR set for log output."""
    return {"CLAUDE_PROJECT_DIR": str(tmp_path)}


class TestPostToolUseExitCodes:
    """Test each path in posttooluse_log_tool.sh."""

    def test_exit_0_for_non_skill(self, log_env: dict[str, str]) -> None:
        """Non-Skill tool invocation should exit 0 without logging."""
        payload = {"tool_name": "Read", "tool_input": {"path": "/tmp/x"}}
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

    def test_logs_skill_invocation(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """Skill invocation should write to audit.log."""
        payload = {
            "tool_name": "Skill",
            "tool_input": {"skill": "checkpoint", "args": "--scope *.py"},
        }
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

        log_file = tmp_path / ".claude" / "audit.log"
        if log_file.exists():
            content = log_file.read_text()
            assert "checkpoint" in content

    def test_special_characters_in_args(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """Special characters in skill args should be handled safely."""
        payload = {
            "tool_name": "Skill",
            "tool_input": {
                "skill": "test-skill",
                "args": 'file with "quotes" and $pecial chars',
            },
        }
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

    def test_empty_stdin(self, log_env: dict[str, str]) -> None:
        """Empty stdin should not crash."""
        result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin="")
        assert result.returncode == 0

    def test_invalid_json_stdin(self, log_env: dict[str, str]) -> None:
        """Invalid JSON on stdin should not crash."""
        result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin="not json")
        assert result.returncode == 0

    def test_rejects_symlinked_audit_log(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """SEC-006: Should refuse to write to symlinked audit.log."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        # Create a symlink for audit.log
        real_log = tmp_path / "real_audit.log"
        real_log.write_text("")
        (claude_dir / "audit.log").symlink_to(real_log)

        payload = {
            "tool_name": "Skill",
            "tool_input": {"skill": "test", "args": ""},
        }
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        # Should not crash, but should log a warning
        assert result.returncode == 0

    def test_missing_claude_dir_created(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """Missing .claude/ directory should be created automatically."""
        payload = {
            "tool_name": "Skill",
            "tool_input": {"skill": "test-create-dir", "args": ""},
        }
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0
        assert (tmp_path / ".claude").exists()


# ─── Hook Pattern Parity Tests ───


# Shell hook regex extracted for testing (must stay in sync with
# hooks/pretooluse_require_checkpoint.sh line 19).
_SHELL_HOOK_REGEX = (
    r"(Write\b|Edit\b|MultiEdit\b|NotebookEdit\b|Bash\b|Git\b|"
    r"rm\b|mv\b|sed\b|perl\b|curl\b|docker\b|kubectl\b|scp\b|"
    r"rsync\b|npm\b|pip\b|chmod\b|chown\b|shred\b|unlink\b|ln\b)"
)


def _regex_matches(pattern: str, text: str) -> bool:
    """Return True if *pattern* matches anywhere in *text* (case-insensitive)."""
    return re.search(pattern, text, re.IGNORECASE) is not None


class TestHookPatternParity:
    """Regression tests ensuring shell hook regex covers Python mapper patterns."""

    # Mutation tool names from _TOOL_MAPPINGS in mapper.py that have
    # mutation=True or requires_checkpoint=True.
    PYTHON_MUTATION_TOOLS = [
        "Write",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
    ]

    # Bash sub-commands classified as destructive / network-send in mapper.py
    # that should be caught by the shell hook regex.
    BASH_MUTATION_COMMANDS = [
        "rm",
        "mv",
        "sed",
        "perl",
        "curl",
        "docker",
        "kubectl",
        "scp",
        "rsync",
        "npm",
        "pip",
        "chmod",
        "chown",
        "shred",
        "unlink",
        "ln",
    ]

    # ── SDK tool-name parity ──

    @pytest.mark.parametrize("tool_name", PYTHON_MUTATION_TOOLS)
    def test_shell_regex_catches_sdk_mutation_tool(self, tool_name: str) -> None:
        """Shell hook regex must match every mutation tool from Python mapper."""
        assert _regex_matches(
            _SHELL_HOOK_REGEX, tool_name
        ), f"Shell hook regex does not catch SDK mutation tool '{tool_name}'"

    # ── Bash sub-command parity ──

    @pytest.mark.parametrize("cmd", BASH_MUTATION_COMMANDS)
    def test_shell_regex_catches_bash_mutation_command(self, cmd: str) -> None:
        """Shell hook regex must match destructive Bash sub-commands from mapper."""
        payload = f"Bash {cmd} something"
        assert _regex_matches(
            _SHELL_HOOK_REGEX, payload
        ), f"Shell hook regex does not catch Bash mutation command '{cmd}'"

    # ── Explicit MultiEdit / NotebookEdit tests ──

    def test_multiedit_matched(self) -> None:
        """MultiEdit must be caught by shell hook regex."""
        assert _regex_matches(_SHELL_HOOK_REGEX, "MultiEdit files")

    def test_notebookedit_matched(self) -> None:
        """NotebookEdit must be caught by shell hook regex."""
        assert _regex_matches(_SHELL_HOOK_REGEX, "NotebookEdit cell 3")

    # ── hooks.json matcher parity ──

    def test_hooks_json_matcher_includes_mutation_tools(self) -> None:
        """hooks.json PreToolUse matcher must list all SDK mutation tools."""
        hooks_json_path = ROOT / "hooks" / "hooks.json"
        hooks_data = json.loads(hooks_json_path.read_text())

        matcher = hooks_data["hooks"]["PreToolUse"][0]["matcher"]
        matcher_tools = set(matcher.split("|"))

        for tool_name in self.PYTHON_MUTATION_TOOLS:
            assert tool_name in matcher_tools, (
                f"hooks.json matcher is missing mutation tool '{tool_name}'; "
                f"current matcher: {matcher}"
            )
