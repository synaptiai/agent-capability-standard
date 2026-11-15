"""Unit tests for shell hook scripts (TEST-002).

Tests each exit code path, missing directories, missing jq,
empty payloads, and special characters in skill arguments.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRETOOLUSE_HOOK = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
POSTTOOLUSE_HOOK = ROOT / "hooks" / "posttooluse_log_tool.sh"

# The audit log verifier lives in tools/
sys.path.insert(0, str(ROOT / "tools"))
from verify_audit_log import verify_log  # noqa: E402


def input_digest(tool_input: Any) -> str:
    """SHA-256 of a tool input as compact JSON with sorted keys (jq -cS)."""
    canonical = json.dumps(
        tool_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_entries(project_dir: Path) -> list[dict[str, Any]]:
    """The entries of a project's audit log, one per line."""
    log_file = project_dir / ".claude" / "audit.log"
    return [json.loads(line) for line in log_file.read_text().splitlines()]


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

    # These PreToolUse tests pass the payload as $1 (the hook also reads
    # Claude Code's JSON from stdin when no argument is given); PostToolUse
    # reads from stdin
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

    def test_exit_0_for_non_mutation(self) -> None:
        """Non-mutation commands should pass (exit 0)."""
        result = run_hook(PRETOOLUSE_HOOK, "Read some file")
        assert result.returncode == 0

    def test_exit_2_missing_marker(self, tmp_path: Path) -> None:
        """Mutation without marker should be blocked (exit 2)."""
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Write to file", env)
        assert result.returncode == 2
        assert "missing checkpoint marker" in result.stderr.lower()

    def test_block_reason_opens_with_the_code(self, tmp_path: Path) -> None:
        """The reason names the rule that refused the call: F501."""
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Write to file", env)
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert result.stdout == ""

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

    def test_exit_2_symlink_marker(self, tmp_path: Path) -> None:
        """Symlinked marker should be rejected (exit 2)."""
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
        assert result.returncode == 2
        assert "symlink" in result.stderr.lower()

    def test_exit_2_empty_marker(self, tmp_path: Path) -> None:
        """Empty marker file should fail."""
        marker_dir = tmp_path / ".claude"
        marker_dir.mkdir()
        (marker_dir / "checkpoint.ok").write_text("")

        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Edit something", env)
        assert result.returncode == 2

    def test_exit_2_expired_marker(self, tmp_path: Path) -> None:
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
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert "expired" in result.stderr.lower()

    @pytest.mark.parametrize(
        "content", ["ok", '"just a string"', "[1, 2]", "5", "null"]
    )
    def test_exit_2_marker_not_a_json_object(
        self, tmp_path: Path, content: str
    ) -> None:
        """A marker that is not a JSON object blocks: jq's own exit code
        would be a non-blocking error, and the call would run."""
        if shutil.which("jq") is None:
            pytest.skip("jq not installed; the fallback checks the marker's age only")
        marker = tmp_path / ".claude" / "checkpoint.ok"
        marker.parent.mkdir()
        marker.write_text(content)

        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, "Write something", env)
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert "not a json object" in result.stderr.lower()
        assert not marker.exists()

    def test_a_failing_command_blocks(self, tmp_path: Path) -> None:
        """Any unexpected failure inside the hook blocks the call (exit 2),
        rather than exiting with the failing command's status."""
        if shutil.which("jq") is None:
            pytest.skip("jq not installed")
        import time

        marker = tmp_path / ".claude" / "checkpoint.ok"
        marker.parent.mkdir()
        marker.write_text(
            json.dumps({"checkpoint_id": "chk", "expires_at": int(time.time()) + 600})
        )
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake_date = bin_dir / "date"
        fake_date.write_text("#!/bin/sh\nexit 1\n")
        fake_date.chmod(0o755)

        env = {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        }
        result = run_hook(PRETOOLUSE_HOOK, "Write something", env)
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert "hook failed" in result.stderr

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

    def test_logs_non_skill_tool_call(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """Every tool call is logged, not only Skill calls."""
        payload = {"tool_name": "Read", "tool_input": {"path": "/tmp/x"}}
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Read"
        assert "skill" not in entry, "the skill name is for Skill calls only"

    def test_logs_bash_call(self, log_env: dict[str, str], tmp_path: Path) -> None:
        """A Bash call is logged with its tool name and the time."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la", "description": "List files"},
        }
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Bash"
        assert entry["event"] == "PostToolUse"
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", entry["ts"])
        assert set(entry) == {
            "ts",
            "event",
            "tool",
            "input_sha256",
            "prev_hmac",
            "hmac",
        }

    def test_log_line_holds_a_digest_and_not_the_command(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """The tool input is never written: a SHA-256 digest stands in for it."""
        secret = "sk-live-0123456789abcdef"
        tool_input = {
            "command": f"curl -H 'Authorization: Bearer {secret}' https://example.com",
            "description": "Call the API",
        }
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": tool_input,
            "tool_response": {"stdout": f"token={secret}", "stderr": ""},
        }
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

        content = (tmp_path / ".claude" / "audit.log").read_text()
        assert secret not in content
        assert "curl" not in content
        assert "example.com" not in content
        assert "Call the API" not in content

        (entry,) = read_entries(tmp_path)
        assert entry["input_sha256"] == input_digest(tool_input)
        assert re.fullmatch(r"[0-9a-f]{64}", entry["input_sha256"])

    def test_digest_does_not_depend_on_key_order(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """The same input gives the same digest however its keys are ordered."""
        for tool_input in (
            {"file_path": "a.py", "limit": 10},
            {"limit": 10, "file_path": "a.py"},
        ):
            payload = {"tool_name": "Read", "tool_input": tool_input}
            assert run_hook(POSTTOOLUSE_HOOK, payload, log_env).returncode == 0

        first, second = read_entries(tmp_path)
        assert first["input_sha256"] == second["input_sha256"]

    def test_logs_skill_invocation(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """A Skill call is logged with the skill's name and not its arguments."""
        tool_input = {"skill": "checkpoint", "args": "--scope *.py"}
        payload = {"tool_name": "Skill", "tool_input": tool_input}
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

        log_file = tmp_path / ".claude" / "audit.log"
        assert log_file.exists(), "PostToolUse hook should have created audit.log"
        assert "--scope" not in log_file.read_text()

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Skill"
        assert entry["skill"] == "checkpoint"
        assert entry["input_sha256"] == input_digest(tool_input)
        assert "args" not in entry

    def test_special_characters_in_args(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """Special characters in skill args should be handled safely."""
        tool_input = {
            "skill": "test-skill",
            "args": 'file with "quotes" and $pecial chars',
        }
        payload = {"tool_name": "Skill", "tool_input": tool_input}
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

        content = (tmp_path / ".claude" / "audit.log").read_text()
        assert "quotes" not in content
        (entry,) = read_entries(tmp_path)
        assert entry["skill"] == "test-skill"
        assert entry["input_sha256"] == input_digest(tool_input)

    @pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl needed")
    def test_non_ascii_skill_name_verifies(self, tmp_path: Path) -> None:
        """The verifier recomputes the HMAC the hook wrote for a non-ASCII name."""
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "AUDIT_HMAC_KEY": "unit-test-key"}
        # characters jq and json.dumps could print differently: non-ASCII text,
        # a quote, a backslash, a control character and DEL
        names = ["prüfen", 'q"uo\\te', "tab\there", "del\x7fete"]
        for name in names:
            payload = {"tool_name": "Skill", "tool_input": {"skill": name}}
            assert run_hook(POSTTOOLUSE_HOOK, payload, env).returncode == 0

        assert [entry["skill"] for entry in read_entries(tmp_path)] == names
        log_file = tmp_path / ".claude" / "audit.log"
        assert verify_log(log_file, "unit-test-key") == (4, 4, [])

    def test_logs_failed_call(self, log_env: dict[str, str], tmp_path: Path) -> None:
        """A call that failed is logged too, marked by its event."""
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "error": "Exit code 1\nError: Cannot find module 'express'",
        }
        result = run_hook(POSTTOOLUSE_HOOK, payload, log_env)
        assert result.returncode == 0

        content = (tmp_path / ".claude" / "audit.log").read_text()
        assert "express" not in content, "the error text is not written"
        (entry,) = read_entries(tmp_path)
        assert entry["event"] == "PostToolUseFailure"
        assert entry["tool"] == "Bash"

    def test_one_line_per_call(self, log_env: dict[str, str], tmp_path: Path) -> None:
        """Three calls leave three chained lines, in order."""
        calls = [
            {"tool_name": "Read", "tool_input": {"file_path": "a.py"}},
            {"tool_name": "Skill", "tool_input": {"skill": "verify"}},
            {"tool_name": "mcp__memory__search", "tool_input": {"query": "x"}},
        ]
        for payload in calls:
            assert run_hook(POSTTOOLUSE_HOOK, payload, log_env).returncode == 0

        entries = read_entries(tmp_path)
        assert [entry["tool"] for entry in entries] == [
            "Read",
            "Skill",
            "mcp__memory__search",
        ]
        assert entries[0]["prev_hmac"] == ""
        assert entries[1]["prev_hmac"] == entries[0]["hmac"]
        assert entries[2]["prev_hmac"] == entries[1]["hmac"]

    def test_empty_stdin(self, log_env: dict[str, str], tmp_path: Path) -> None:
        """Empty stdin should not crash, and is not a tool call."""
        result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin="")
        assert result.returncode == 0
        assert not (tmp_path / ".claude" / "audit.log").exists()

    def test_invalid_json_stdin(self, log_env: dict[str, str], tmp_path: Path) -> None:
        """Invalid JSON on stdin should not crash, and is not a tool call."""
        result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin="not json")
        assert result.returncode == 0
        assert not (tmp_path / ".claude" / "audit.log").exists()

    def test_input_without_a_tool_name_is_not_logged(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """JSON that names no tool, or a JSON value and more, is not a tool call."""
        for stdin in (
            '{"tool_input": {"command": "ls"}}',
            '{"tool_name": 7}',
            "[1]",
            '{"tool_name": "Bash", "tool_input": {"command": "ls"}} trailing text',
        ):
            result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin=stdin)
            assert result.returncode == 0
        assert not (tmp_path / ".claude" / "audit.log").exists()

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

    @pytest.mark.skipif(shutil.which("flock") is None, reason="flock not installed")
    def test_symlinked_lock_file_truncates_nothing(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """The lock file is opened for append: a symlink there empties no file."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        target = tmp_path / "unrelated.txt"
        target.write_text("keep\n")
        (claude_dir / "audit.log.lock").symlink_to(target)

        payload = {"tool_name": "Read", "tool_input": {"file_path": "a.py"}}
        assert run_hook(POSTTOOLUSE_HOOK, payload, log_env).returncode == 0
        assert target.read_text() == "keep\n"
        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Read"

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


# ─── Audit log under concurrent tool calls ───

# What the audit hook runs, apart from flock
_AUDIT_HOOK_TOOLS = [
    "bash",
    "cat",
    "jq",
    "date",
    "tail",
    "awk",
    "openssl",
    "sha256sum",
    "mkdir",
    "rmdir",
    "sleep",
    "seq",
]


def _run_concurrently(payloads: list[dict[str, Any]], env: dict[str, str]) -> None:
    def run(payload: dict[str, Any]) -> int:
        return subprocess.run(
            [env["HOOK_BASH"], str(POSTTOOLUSE_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        ).returncode

    with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
        assert list(pool.map(run, payloads)) == [0] * len(payloads)


@pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in _AUDIT_HOOK_TOOLS),
    reason="the audit hook's tools are not all installed",
)
class TestAuditLogConcurrency:
    """Tool calls made in parallel run the hook concurrently; the chain holds."""

    PAYLOADS = [
        {"tool_name": "Read", "tool_input": {"file_path": f"file_{i}.py"}}
        for i in range(6)
    ]
    KEY = "test-key-for-concurrency"

    def _env(self, tmp_path: Path, path: str) -> dict[str, str]:
        return {
            "PATH": path,
            "HOME": str(tmp_path),
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "AUDIT_HMAC_KEY": self.KEY,
            "HOOK_BASH": shutil.which("bash") or "bash",
        }

    def _assert_chain(self, tmp_path: Path) -> None:
        total, valid, errors = verify_log(tmp_path / ".claude" / "audit.log", self.KEY)
        assert errors == []
        assert (total, valid) == (len(self.PAYLOADS), len(self.PAYLOADS))
        digests = {entry["input_sha256"] for entry in read_entries(tmp_path)}
        assert digests == {input_digest(p["tool_input"]) for p in self.PAYLOADS}

    @pytest.mark.skipif(shutil.which("flock") is None, reason="flock not installed")
    def test_chain_holds_with_flock(self, tmp_path: Path) -> None:
        _run_concurrently(self.PAYLOADS, self._env(tmp_path, os.environ["PATH"]))
        self._assert_chain(tmp_path)

    def test_chain_holds_without_flock(self, tmp_path: Path) -> None:
        """Where flock is not installed (macOS), a lock directory serializes."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for tool in _AUDIT_HOOK_TOOLS:
            tool_path = shutil.which(tool)
            assert tool_path is not None
            (bin_dir / tool).symlink_to(tool_path)

        _run_concurrently(self.PAYLOADS, self._env(tmp_path, str(bin_dir)))
        self._assert_chain(tmp_path)
        assert not (tmp_path / ".claude" / "audit.log.lock.d").exists(), (
            "the lock directory is released"
        )


# ─── Audit log when the digest cannot be computed ───


@pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in _AUDIT_HOOK_TOOLS),
    reason="the audit hook's tools are not all installed",
)
class TestAuditDigestUnavailable:
    """A digest that cannot be computed does not drop the entry or keep the input."""

    KEY = "test-key-for-digest"
    SECRET = "sk-live-0123456789abcdef"

    def _bin_dir(self, tmp_path: Path, leave_out: set[str]) -> Path:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for tool in _AUDIT_HOOK_TOOLS:
            if tool not in leave_out:
                tool_path = shutil.which(tool)
                assert tool_path is not None
                (bin_dir / tool).symlink_to(tool_path)
        return bin_dir

    def _log(self, tmp_path: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": f"echo {self.SECRET}"},
        }
        env = {
            "PATH": str(bin_dir),
            "HOME": str(tmp_path),
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "AUDIT_HMAC_KEY": self.KEY,
        }
        return subprocess.run(
            [shutil.which("bash") or "bash", str(POSTTOOLUSE_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    @pytest.mark.parametrize(
        "fake_sha256sum",
        [
            "cat > /dev/null; exit 1",  # the tool fails
            "cat > /dev/null; echo not-a-digest",  # it prints no digest
        ],
    )
    def test_failing_sha256_tool(self, tmp_path: Path, fake_sha256sum: str) -> None:
        bin_dir = self._bin_dir(tmp_path, {"sha256sum"})
        fake = bin_dir / "sha256sum"
        fake.write_text(f"#!{shutil.which('bash')}\n{fake_sha256sum}\n")
        fake.chmod(0o755)

        assert self._log(tmp_path, bin_dir).returncode == 0

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Bash"
        assert entry["input_sha256"] == "unavailable"
        assert self.SECRET not in (tmp_path / ".claude" / "audit.log").read_text()
        assert verify_log(tmp_path / ".claude" / "audit.log", self.KEY) == (1, 1, [])

    def test_input_that_cannot_be_serialized(self, tmp_path: Path) -> None:
        """A jq that fails to print the input gives no digest, not a digest of null."""
        bin_dir = self._bin_dir(tmp_path, {"jq"})
        fake = bin_dir / "jq"
        fake.write_text(
            f"#!{shutil.which('bash')}\n"
            'for arg in "$@"; do\n'
            '  if [ "$arg" = "-cS" ]; then cat > /dev/null; exit 5; fi\n'
            "done\n"
            f'exec {shutil.which("jq")} "$@"\n'
        )
        fake.chmod(0o755)

        assert self._log(tmp_path, bin_dir).returncode == 0

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Bash"
        assert entry["input_sha256"] == "unavailable"
        assert verify_log(tmp_path / ".claude" / "audit.log", self.KEY) == (1, 1, [])

    def test_no_sha256_tool(self, tmp_path: Path) -> None:
        """Without sha256sum, shasum or openssl the entry is still written."""
        bin_dir = self._bin_dir(tmp_path, {"sha256sum", "openssl"})
        assert shutil.which("shasum", path=str(bin_dir)) is None

        assert self._log(tmp_path, bin_dir).returncode == 0

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Bash"
        assert entry["input_sha256"] == "unavailable"
        assert self.SECRET not in (tmp_path / ".claude" / "audit.log").read_text()


# ─── Hook Pattern Parity Tests ───


# Shell hook regex extracted for testing (must stay in sync with
# mutation_re in hooks/pretooluse_require_checkpoint.sh).
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
        assert _regex_matches(_SHELL_HOOK_REGEX, tool_name), (
            f"Shell hook regex does not catch SDK mutation tool '{tool_name}'"
        )

    # ── Bash sub-command parity ──

    @pytest.mark.parametrize("cmd", BASH_MUTATION_COMMANDS)
    def test_shell_regex_catches_bash_mutation_command(self, cmd: str) -> None:
        """Shell hook regex must match destructive Bash sub-commands from mapper."""
        payload = f"Bash {cmd} something"
        assert _regex_matches(_SHELL_HOOK_REGEX, payload), (
            f"Shell hook regex does not catch Bash mutation command '{cmd}'"
        )

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

    def test_hooks_json_matcher_includes_bash(self) -> None:
        """hooks.json PreToolUse matcher must include Bash for sub-command gating."""
        hooks_json_path = ROOT / "hooks" / "hooks.json"
        hooks_data = json.loads(hooks_json_path.read_text())

        matcher = hooks_data["hooks"]["PreToolUse"][0]["matcher"]
        matcher_tools = set(matcher.split("|"))

        assert "Bash" in matcher_tools, (
            f"hooks.json matcher must include 'Bash' to gate destructive sub-commands; "
            f"current matcher: {matcher}"
        )

    @pytest.mark.parametrize("event", ["PostToolUse", "PostToolUseFailure"])
    def test_hooks_json_audit_hook_matches_every_tool(self, event: str) -> None:
        """The audit hook runs after every tool call, succeeded or failed."""
        hooks_data = json.loads((ROOT / "hooks" / "hooks.json").read_text())

        (group,) = hooks_data["hooks"][event]
        assert group["matcher"] == "*", "`*` matches every tool"
        (hook,) = group["hooks"]
        assert hook["type"] == "command"
        assert hook["command"].endswith("/hooks/posttooluse_log_tool.sh")
