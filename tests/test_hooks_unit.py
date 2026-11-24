"""Unit tests for shell hook scripts (TEST-002).

Tests each exit code path, missing directories, missing jq,
empty payloads, and special characters in skill arguments.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
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


def outside_project(tmp_path: Path, name: str) -> Path:
    """A directory beside the project directory `tmp_path`, not in it: the
    hooks drop from PATH every directory in the project (a repository's
    program never runs in place of the system's), so a test's own programs
    live here."""
    return tmp_path.parent / f"{tmp_path.name}-{name}"


def input_digest(tool_input: Any) -> str:
    """SHA-256 of a tool input as compact JSON with sorted keys (jq -cS)."""
    canonical = json.dumps(
        tool_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_entries(project_dir: Path) -> list[dict[str, Any]]:
    """The entries of a project's audit log, one per line."""
    log_file = project_dir / ".claude" / "audit.log"
    if not log_file.exists():
        return []
    return [json.loads(line) for line in log_file.read_text().splitlines()]


def call(tool: str, **tool_input: Any) -> dict[str, Any]:
    """Claude Code's PreToolUse payload for a tool call (the hook reads only
    this JSON object, STANDARD 1.2.0 §5.18.8)."""
    return {
        "tool_name": tool,
        "tool_input": tool_input,
        "permission_mode": "default",
        "tool_use_id": "t1",
    }


WRITE = call("Write", file_path="file.py")
EDIT = call("Edit", file_path="file.py")


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
        """A tool hooks.json does not route here passes (exit 0)."""
        result = run_hook(PRETOOLUSE_HOOK, call("Read", file_path="x"))
        assert result.returncode == 0

    def test_exit_2_missing_marker(self, tmp_path: Path) -> None:
        """Mutation without marker should be blocked (exit 2)."""
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, WRITE, env)
        assert result.returncode == 2
        assert "missing checkpoint marker" in result.stderr.lower()

    def test_block_reason_opens_with_the_code(self, tmp_path: Path) -> None:
        """The reason names the rule that refused the call: F501."""
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, WRITE, env)
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
        result = run_hook(PRETOOLUSE_HOOK, WRITE, env)
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
        result = run_hook(PRETOOLUSE_HOOK, WRITE, env)
        assert result.returncode == 2
        assert "symlink" in result.stderr.lower()

    def test_exit_2_empty_marker(self, tmp_path: Path) -> None:
        """Empty marker file should fail."""
        marker_dir = tmp_path / ".claude"
        marker_dir.mkdir()
        (marker_dir / "checkpoint.ok").write_text("")

        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, EDIT, env)
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
        result = run_hook(PRETOOLUSE_HOOK, WRITE, env)
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert "expired" in result.stderr.lower()

    @pytest.mark.parametrize(
        ("times", "why"),
        [
            # An expiry no shell integer holds once failed open.
            ({"created_at": "NOW", "expires_at": 99999999999999999999}, "invalid"),
            ({"created_at": "NOW", "expires_at": "1e10"}, "invalid"),
            ({"created_at": -1, "expires_at": "LATER"}, "invalid"),
            ({"expires_at": "LATER"}, "missing"),
            # Valid for longer than the Standard's 30-minute cap.
            ({"created_at": "NOW", "expires_at": "NOW+1801"}, "not possible"),
            # Taken in the future.
            ({"created_at": "NOW+600", "expires_at": "NOW+900"}, "not possible"),
        ],
    )
    def test_exit_2_marker_with_impossible_times(
        self, tmp_path: Path, times: dict[str, object], why: str
    ) -> None:
        """A marker whose times cannot be read or cannot be true blocks with
        F501 and is removed: it never fails open."""
        if shutil.which("jq") is None:
            pytest.skip("jq not installed")
        import time

        now = int(time.time())

        def resolve(value: object) -> object:
            # "NOW", "NOW+<seconds>" and "LATER" (ten minutes on) are times
            # relative to now; anything else is written as it is.
            if value == "NOW":
                return now
            if value == "LATER":
                return now + 600
            if isinstance(value, str) and value.startswith("NOW+"):
                return now + int(value[4:])
            return value

        resolved = {key: resolve(value) for key, value in times.items()}
        marker = tmp_path / ".claude" / "checkpoint.ok"
        marker.parent.mkdir()
        marker.write_text(json.dumps({"checkpoint_id": "chk", **resolved}))

        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, WRITE, env)
        assert result.returncode == 2, result.stderr
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert why in result.stderr
        assert not marker.exists()

    def test_a_marker_valid_for_exactly_30_minutes_passes(self, tmp_path: Path) -> None:
        import time

        now = int(time.time())
        marker = tmp_path / ".claude" / "checkpoint.ok"
        marker.parent.mkdir()
        marker.write_text(
            json.dumps(
                {"checkpoint_id": "c", "created_at": now, "expires_at": now + 1800}
            )
        )
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "ACS_HOOK_APPROVAL": "off"}
        assert run_hook(PRETOOLUSE_HOOK, WRITE, env).returncode == 0

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
        result = run_hook(PRETOOLUSE_HOOK, WRITE, env)
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
            json.dumps(
                {
                    "checkpoint_id": "chk",
                    "created_at": int(time.time()),
                    "expires_at": int(time.time()) + 600,
                }
            )
        )
        bin_dir = outside_project(tmp_path, "bin")
        bin_dir.mkdir()
        fake_date = bin_dir / "date"
        fake_date.write_text("#!/bin/sh\nexit 1\n")
        fake_date.chmod(0o755)

        env = {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        }
        result = run_hook(PRETOOLUSE_HOOK, WRITE, env)
        assert result.returncode == 2
        assert result.stderr.startswith("R407 SAFETY_CHECK_FAILED: ")
        assert "hook failed" in result.stderr

    @pytest.mark.parametrize(
        "payload", ["", "Write to file.py", "[1]", '{"tool_name": 5}']
    )
    def test_a_payload_that_is_not_a_tool_call_is_r407(self, payload: str) -> None:
        """Only Claude Code's JSON object is read: a plain-text payload, which
        was once classified by its words, is blocked (STANDARD 1.2.0
        §5.18.8)."""
        result = run_hook(PRETOOLUSE_HOOK, payload)
        assert result.returncode == 2
        assert result.stderr.startswith(
            "R407 SAFETY_CHECK_FAILED: cannot read the tool call"
        )


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
        assert entry["details"]["event"] == "PostToolUse"
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", entry["timestamp"])
        assert set(entry) == {
            "action_id",
            "timestamp",
            "actor",
            "intent",
            "status",
            "tool",
            "details",
            "recorded_by",
            "prev_hmac",
            "hmac",
        }
        assert set(entry["details"]) == {"event", "input_sha256"}

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
        assert entry["details"]["input_sha256"] == input_digest(tool_input)
        assert re.fullmatch(r"[0-9a-f]{64}", entry["details"]["input_sha256"])

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
        assert first["details"]["input_sha256"] == second["details"]["input_sha256"]

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
        assert entry["details"]["skill"] == "checkpoint"
        assert entry["details"]["input_sha256"] == input_digest(tool_input)
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
        assert entry["details"]["skill"] == "test-skill"
        assert entry["details"]["input_sha256"] == input_digest(tool_input)

    @pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl needed")
    def test_non_ascii_text_verifies(self, tmp_path: Path) -> None:
        """The verifier recomputes the HMAC the hook wrote for non-ASCII text
        (a call id holds it as given; a skill name outside the plain name
        grammar is written [REDACTED], security round 5)."""
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "AUDIT_HMAC_KEY": "unit-test-key"}
        # characters jq and json.dumps could print differently: non-ASCII text,
        # a quote, a backslash, a control character and DEL
        names = ["prüfen", 'q"uo\\te', "tab\there", "del\x7fete"]
        for name in names:
            payload = {
                "tool_name": "Skill",
                "tool_use_id": name,
                "tool_input": {"skill": name},
            }
            assert run_hook(POSTTOOLUSE_HOOK, payload, env).returncode == 0

        entries = read_entries(tmp_path)
        assert [entry["call_id"] for entry in entries] == names
        assert [entry["details"]["skill"] for entry in entries] == ["[REDACTED]"] * 4
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
        assert entry["details"]["event"] == "PostToolUseFailure"
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

    @pytest.mark.parametrize(
        "stdin",
        [
            "not json",
            '{"tool_name": "Bash", "tool_input": {"command": "ls"}} trailing text',
        ],
    )
    def test_input_jq_cannot_parse_is_reported(
        self, log_env: dict[str, str], tmp_path: Path, stdin: str
    ) -> None:
        """Input jq cannot parse may be a tool call it could not read: the
        hook says so and exits 1 (STANDARD v1.2 §6.4: a capture that fails
        is reported, never silent)."""
        result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin=stdin)
        assert result.returncode == 1
        assert "could not be parsed" in result.stderr
        assert "this tool call was not logged" in result.stderr
        assert not (tmp_path / ".claude" / "audit.log").exists()

    def test_input_without_a_tool_name_is_not_logged(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """JSON that names no tool, and no input at all, is not a tool call."""
        for stdin in (
            '{"tool_input": {"command": "ls"}}',
            '{"tool_name": 7}',
            "[1]",
            "",
        ):
            result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin=stdin)
            assert (result.returncode, result.stderr) == (0, "")
        assert not (tmp_path / ".claude" / "audit.log").exists()

    @pytest.mark.parametrize("where", ["tool_input", "tool_response"])
    @pytest.mark.parametrize("depth", [253, 300, 10_000])
    def test_a_call_nested_past_jqs_limit_is_reported(
        self, log_env: dict[str, str], tmp_path: Path, where: str, depth: int
    ) -> None:
        """jq refuses input nested past its depth limit; Claude Code passes a
        call's arguments and result as they are, so a tool call nested that
        deep was dropped with exit 0 and nothing on stderr."""
        nested = "[" * depth + "]" * depth
        stdin = (
            '{"hook_event_name": "PostToolUse", "tool_name": "mcp__x__y", '
            '"tool_use_id": "toolu_deep", "tool_input": {"batch": []}, '
            f'"{where}": {{"value": {nested}}}}}'
        )
        result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin=stdin)
        assert result.returncode == 1
        assert "could not be parsed" in result.stderr
        assert "depth" in result.stderr

    def test_a_call_with_a_lone_surrogate_is_reported(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """A string cut in the middle of an emoji is written with a lone high
        surrogate escape (JSON.stringify does so), which jq refuses."""
        stdin = '{"tool_name": "mcp__x__y", "tool_input": {"text": "ab\\ud83d"}}'
        result = run_hook(POSTTOOLUSE_HOOK, env_override=log_env, stdin=stdin)
        assert result.returncode == 1
        assert "could not be parsed" in result.stderr

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
        # Refused, and reported: a non-blocking hook error (STANDARD v1.2 §6.4)
        assert result.returncode == 1
        assert "audit.log is a symlink" in result.stderr
        assert "not logged" in result.stderr
        assert real_log.read_text() == ""

    def test_a_lock_file_left_by_an_earlier_version_is_not_touched(
        self, log_env: dict[str, str], tmp_path: Path
    ) -> None:
        """The hook locks the log itself and never opens audit.log.lock, so a
        symlink planted there changes no file."""
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

# What the audit hook runs, apart from flock and perl (which take the lock)
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
    "sleep",
    # The head (.claude/audit.head) is replaced whole, by renaming
    "mv",
]


def _run_concurrently(
    payloads: list[dict[str, Any]], envs: dict[str, str] | list[dict[str, str]]
) -> None:
    env_list = envs if isinstance(envs, list) else [envs] * len(payloads)

    def run(job: tuple[dict[str, Any], dict[str, str]]) -> int:
        payload, env = job
        return subprocess.run(
            [env["HOOK_BASH"], str(POSTTOOLUSE_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=90,
        ).returncode

    with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
        codes = list(pool.map(run, zip(payloads, env_list, strict=True)))
    assert codes == [0] * len(payloads)


@pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in [*_AUDIT_HOOK_TOOLS, "perl"]),
    reason="the audit hook's tools are not all installed",
)
class TestAuditLogConcurrency:
    """Tool calls made in parallel run the hook concurrently; the chain holds.

    The hook takes flock(2) on the log file with flock(1) where installed
    and with perl elsewhere (macOS), so the kernel releases a lock whose
    holder exits, and a run waits at most AUDIT_LOCK_WAIT seconds."""

    PAYLOADS = [
        {"tool_name": "Read", "tool_input": {"file_path": f"file_{i}.py"}}
        for i in range(6)
    ]
    KEY = "test-key-for-concurrency"

    def _env(self, tmp_path: Path, path: str, **more: str) -> dict[str, str]:
        return {
            "PATH": path,
            "HOME": str(tmp_path),
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "AUDIT_HMAC_KEY": self.KEY,
            "HOOK_BASH": shutil.which("bash") or "bash",
            **more,
        }

    def _bin(self, tmp_path: Path, name: str, tools: list[str]) -> Path:
        """A directory of links to `tools`, to run the hook with only them."""
        bin_dir = outside_project(tmp_path, name)
        bin_dir.mkdir()
        for tool in tools:
            tool_path = shutil.which(tool)
            assert tool_path is not None
            (bin_dir / tool).symlink_to(tool_path)
        return bin_dir

    def _slow_openssl(self, bin_dir: Path, seconds: float) -> None:
        """Make the locked part of an append take `seconds` longer."""
        (bin_dir / "openssl").unlink()
        slow = bin_dir / "openssl"
        slow.write_text(
            f"#!{shutil.which('bash')}\n"
            f"{shutil.which('sleep')} {seconds}\n"
            f'exec {shutil.which("openssl")} "$@"\n'
        )
        slow.chmod(0o755)

    def _assert_chain(self, tmp_path: Path, payloads: list[dict[str, Any]]) -> None:
        total, valid, errors = verify_log(tmp_path / ".claude" / "audit.log", self.KEY)
        assert errors == []
        assert (total, valid) == (len(payloads), len(payloads))
        digests = {entry["details"]["input_sha256"] for entry in read_entries(tmp_path)}
        assert digests == {input_digest(p["tool_input"]) for p in payloads}

    @pytest.mark.skipif(shutil.which("flock") is None, reason="flock not installed")
    def test_chain_holds_with_flock(self, tmp_path: Path) -> None:
        bin_dir = self._bin(tmp_path, "bin", [*_AUDIT_HOOK_TOOLS, "flock"])
        _run_concurrently(self.PAYLOADS, self._env(tmp_path, str(bin_dir)))
        self._assert_chain(tmp_path, self.PAYLOADS)

    def test_chain_holds_with_perl(self, tmp_path: Path) -> None:
        """Where flock(1) is not installed (macOS), perl takes the lock."""
        bin_dir = self._bin(tmp_path, "bin", [*_AUDIT_HOOK_TOOLS, "perl"])
        _run_concurrently(self.PAYLOADS, self._env(tmp_path, str(bin_dir)))
        self._assert_chain(tmp_path, self.PAYLOADS)

    @pytest.mark.skipif(shutil.which("flock") is None, reason="flock not installed")
    def test_sessions_with_and_without_flock_share_the_lock(
        self, tmp_path: Path
    ) -> None:
        """flock(1) and perl both take flock(2) on the same file, so runs
        with and without flock(1) exclude each other."""
        with_flock = self._bin(tmp_path, "bin-flock", [*_AUDIT_HOOK_TOOLS, "flock"])
        with_perl = self._bin(tmp_path, "bin-perl", [*_AUDIT_HOOK_TOOLS, "perl"])
        for bin_dir in (with_flock, with_perl):
            self._slow_openssl(bin_dir, 0.3)
        envs = [
            self._env(tmp_path, str(with_flock if i % 2 else with_perl))
            for i in range(len(self.PAYLOADS))
        ]
        _run_concurrently(self.PAYLOADS, envs)
        self._assert_chain(tmp_path, self.PAYLOADS)

    def test_chain_holds_when_the_holder_is_slow(self, tmp_path: Path) -> None:
        """A run waits for a slow holder (as on a loaded CI runner) instead
        of appending beside it: four appends of two seconds each."""
        bin_dir = self._bin(tmp_path, "bin", [*_AUDIT_HOOK_TOOLS, "perl"])
        self._slow_openssl(bin_dir, 2)
        payloads = self.PAYLOADS[:4]
        _run_concurrently(payloads, self._env(tmp_path, str(bin_dir)))
        self._assert_chain(tmp_path, payloads)

    def test_the_kernel_releases_a_killed_holders_lock(self, tmp_path: Path) -> None:
        """A run killed while it holds the lock leaves nothing to clean up:
        the next run gets the lock at once."""
        slow_bin = self._bin(tmp_path, "bin-slow", [*_AUDIT_HOOK_TOOLS, "perl"])
        self._slow_openssl(slow_bin, 60)
        holder = subprocess.Popen(
            [shutil.which("bash") or "bash", str(POSTTOOLUSE_HOOK)],
            stdin=subprocess.PIPE,
            env=self._env(tmp_path, str(slow_bin)),
            start_new_session=True,
        )
        assert holder.stdin is not None
        holder.stdin.write(json.dumps(self.PAYLOADS[0]).encode())
        holder.stdin.close()
        time.sleep(1.5)  # it now holds the lock, inside the slow openssl
        os.killpg(holder.pid, signal.SIGKILL)
        holder.wait(timeout=10)

        bin_dir = self._bin(tmp_path, "bin", [*_AUDIT_HOOK_TOOLS, "perl"])
        start = time.monotonic()
        _run_concurrently(self.PAYLOADS[1:2], self._env(tmp_path, str(bin_dir)))
        assert time.monotonic() - start < 10
        self._assert_chain(tmp_path, self.PAYLOADS[1:2])

    @pytest.mark.parametrize("locker", ["flock", "perl"])
    def test_a_held_lock_delays_but_cannot_silence_the_log(
        self, tmp_path: Path, locker: str
    ) -> None:
        """A lock someone holds only delays a run, for at most
        AUDIT_LOCK_WAIT seconds: the entry is then written."""
        if shutil.which(locker) is None:
            pytest.skip(f"{locker} not installed")
        bin_dir = self._bin(tmp_path, "bin", [*_AUDIT_HOOK_TOOLS, locker])
        log_file = tmp_path / ".claude" / "audit.log"
        log_file.parent.mkdir()
        log_file.touch()
        with open(log_file, "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            start = time.monotonic()
            _run_concurrently(
                self.PAYLOADS[:1],
                self._env(tmp_path, str(bin_dir), AUDIT_LOCK_WAIT="3"),
            )
            waited = time.monotonic() - start
        assert 1.9 <= waited < 10
        self._assert_chain(tmp_path, self.PAYLOADS[:1])

    def test_a_flock_without_a_wait_option_serialises(self, tmp_path: Path) -> None:
        """BusyBox and toybox flock(1) take -x and -n but not -w; the hook
        uses only those."""
        if shutil.which("flock") is None:
            pytest.skip("flock not installed")
        bin_dir = self._bin(tmp_path, "bin", _AUDIT_HOOK_TOOLS)
        limited = bin_dir / "flock"
        limited.write_text(
            f"#!{shutil.which('bash')}\n"
            'for a in "$@"; do case "$a" in -x|-n|[0-9]*) ;; *) exit 1 ;; esac; done\n'
            f'exec {shutil.which("flock")} "$@"\n'
        )
        limited.chmod(0o755)
        self._slow_openssl(bin_dir, 0.3)
        _run_concurrently(self.PAYLOADS, self._env(tmp_path, str(bin_dir)))
        self._assert_chain(tmp_path, self.PAYLOADS)

    def test_a_lock_that_cannot_be_taken_does_not_delay(self, tmp_path: Path) -> None:
        """Where flock(2) fails for a reason other than another holder (a
        filesystem without it), the run appends at once instead of waiting."""
        bin_dir = self._bin(tmp_path, "bin", _AUDIT_HOOK_TOOLS)
        broken = bin_dir / "flock"
        broken.write_text(f"#!{shutil.which('bash')}\nexit 64\n")
        broken.chmod(0o755)
        start = time.monotonic()
        _run_concurrently(self.PAYLOADS[:1], self._env(tmp_path, str(bin_dir)))
        assert time.monotonic() - start < 3
        self._assert_chain(tmp_path, self.PAYLOADS[:1])

    @pytest.mark.parametrize("value", ["99999999999999999999", "-1", "x", "1e3"])
    def test_an_unusable_lock_wait_keeps_the_lock(
        self, tmp_path: Path, value: str
    ) -> None:
        bin_dir = self._bin(tmp_path, "bin", [*_AUDIT_HOOK_TOOLS, "perl"])
        self._slow_openssl(bin_dir, 0.3)
        _run_concurrently(
            self.PAYLOADS, self._env(tmp_path, str(bin_dir), AUDIT_LOCK_WAIT=value)
        )
        self._assert_chain(tmp_path, self.PAYLOADS)

    def test_a_low_open_file_limit_still_logs(self, tmp_path: Path) -> None:
        """The lock uses descriptor 9, below any open-file limit."""
        bin_dir = self._bin(tmp_path, "bin", [*_AUDIT_HOOK_TOOLS, "perl"])
        env = self._env(tmp_path, str(bin_dir))
        result = subprocess.run(
            [
                env["HOOK_BASH"],
                "-c",
                f'ulimit -n 32 && exec "$0" "{POSTTOOLUSE_HOOK}"',
                env["HOOK_BASH"],
            ],
            input=json.dumps(self.PAYLOADS[0]),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        self._assert_chain(tmp_path, self.PAYLOADS[:1])

    def test_stdin_that_is_a_socket_is_read(self, tmp_path: Path) -> None:
        """Claude Code gives a hook a socket as stdin on Linux; a socket
        cannot be opened by path (/dev/stdin), so it must be read as fd 0."""
        import socket

        bin_dir = self._bin(tmp_path, "bin", [*_AUDIT_HOOK_TOOLS, "perl"])
        env = self._env(tmp_path, str(bin_dir))
        ours, theirs = socket.socketpair()
        with ours, theirs:
            ours.sendall(json.dumps(self.PAYLOADS[0]).encode())
            ours.shutdown(socket.SHUT_WR)
            result = subprocess.run(
                [env["HOOK_BASH"], str(POSTTOOLUSE_HOOK)],
                stdin=theirs,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
        assert result.returncode == 0, result.stderr
        self._assert_chain(tmp_path, self.PAYLOADS[:1])

    def test_without_flock_or_perl_the_entry_is_still_written(
        self, tmp_path: Path
    ) -> None:
        bin_dir = self._bin(tmp_path, "bin", _AUDIT_HOOK_TOOLS)
        _run_concurrently(self.PAYLOADS[:1], self._env(tmp_path, str(bin_dir)))
        self._assert_chain(tmp_path, self.PAYLOADS[:1])


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
        bin_dir = outside_project(tmp_path, "bin")
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

        result = self._log(tmp_path, bin_dir)
        assert result.returncode == 1
        assert "input digest could not be computed" in result.stderr

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Bash"
        assert entry["details"]["input_sha256"] == "unavailable"
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

        result = self._log(tmp_path, bin_dir)
        assert result.returncode == 1
        assert "input digest could not be computed" in result.stderr

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Bash"
        assert entry["details"]["input_sha256"] == "unavailable"
        assert verify_log(tmp_path / ".claude" / "audit.log", self.KEY) == (1, 1, [])

    def test_unavailable_digest_is_logged_and_exits_1(self, tmp_path: Path) -> None:
        """Without sha256sum or shasum, and an openssl that signs but fails a
        plain digest, the entry is written with an unavailable digest, and
        the hook says so (STANDARD v1.2 §6.4: never silently)."""
        bin_dir = self._bin_dir(tmp_path, {"sha256sum", "openssl"})
        assert shutil.which("shasum", path=str(bin_dir)) is None
        stub = bin_dir / "openssl"
        stub.write_text(
            f"#!{shutil.which('bash')}\n"
            'case " $* " in *" -hmac "*) ;; *) cat > /dev/null; exit 1 ;; esac\n'
            f'exec {shutil.which("openssl")} "$@"\n'
        )
        stub.chmod(0o755)

        result = self._log(tmp_path, bin_dir)
        assert result.returncode == 1
        assert "input digest could not be computed" in result.stderr

        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "Bash"
        assert entry["details"]["input_sha256"] == "unavailable"
        assert self.SECRET not in (tmp_path / ".claude" / "audit.log").read_text()
        assert verify_log(tmp_path / ".claude" / "audit.log", self.KEY) == (1, 1, [])

    def test_no_openssl_writes_nothing_and_exits_1(self, tmp_path: Path) -> None:
        """Without openssl no line can be signed: none is written (an
        unsigned one would break the chain), and the hook says why."""
        bin_dir = self._bin_dir(tmp_path, {"openssl"})
        result = self._log(tmp_path, bin_dir)
        assert result.returncode == 1
        assert "openssl is not installed" in result.stderr
        assert read_entries(tmp_path) == []

    def test_no_jq_reports_and_exits_1(self, tmp_path: Path) -> None:
        bin_dir = self._bin_dir(tmp_path, {"jq"})
        result = self._log(tmp_path, bin_dir)
        assert result.returncode == 1
        assert "jq is not installed" in result.stderr
        assert read_entries(tmp_path) == []

    def test_entry_build_failure_exits_1(self, tmp_path: Path) -> None:
        """A jq that cannot build the line (-n fails): nothing is written,
        and the hook says why."""
        bin_dir = self._bin_dir(tmp_path, {"jq"})
        fake = bin_dir / "jq"
        fake.write_text(
            f"#!{shutil.which('bash')}\n"
            'for arg in "$@"; do [ "$arg" = "-n" ] && exit 5; done\n'
            f'exec {shutil.which("jq")} "$@"\n'
        )
        fake.chmod(0o755)
        result = self._log(tmp_path, bin_dir)
        assert result.returncode == 1
        assert "could not be built" in result.stderr
        assert read_entries(tmp_path) == []

    def test_unreadable_last_line_starts_new_chain_and_exits_1(
        self, tmp_path: Path
    ) -> None:
        bin_dir = self._bin_dir(tmp_path, set())
        log = tmp_path / ".claude" / "audit.log"
        log.parent.mkdir()
        log.write_text("not json\n")
        result = self._log(tmp_path, bin_dir)
        assert result.returncode == 1
        assert "starts a new chain" in result.stderr
        line = json.loads(log.read_text().splitlines()[-1])
        assert line["prev_hmac"] == ""
        assert re.fullmatch(r"[0-9a-f]{64}", line["hmac"])

    def test_the_line_is_an_action_record(self, tmp_path: Path) -> None:
        """The line is an ActionRecord (STANDARD v1.2 §6.4) with the chain
        fields; recorded_by names the layer (§5.18.8)."""
        from tests.action_record_schema import problems

        bin_dir = self._bin_dir(tmp_path, set())
        assert self._log(tmp_path, bin_dir).returncode == 0
        (entry,) = read_entries(tmp_path)
        assert problems(entry) == []
        assert list(entry)[:6] == [
            "action_id",
            "timestamp",
            "actor",
            "intent",
            "status",
            "tool",
        ]
        assert entry["intent"] == "Bash call"
        assert entry["status"] == "executed"
        assert entry["recorded_by"]["name"] == "agent-capability-standard plugin hooks"
        assert set(entry["recorded_by"]) == {
            "name",
            "version",
            "config_sha256",
            "settings",
        }


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
        """hooks.json PreToolUse matcher must route all SDK mutation tools
        ("*" routes every tool)."""
        hooks_json_path = ROOT / "hooks" / "hooks.json"
        hooks_data = json.loads(hooks_json_path.read_text())

        matcher = hooks_data["hooks"]["PreToolUse"][0]["matcher"]
        matcher_tools = set(matcher.split("|"))

        for tool_name in self.PYTHON_MUTATION_TOOLS:
            assert matcher == "*" or tool_name in matcher_tools, (
                f"hooks.json matcher is missing mutation tool '{tool_name}'; "
                f"current matcher: {matcher}"
            )

    def test_hooks_json_matcher_includes_bash(self) -> None:
        """hooks.json PreToolUse matcher must route Bash for sub-command
        gating ("*" routes every tool)."""
        hooks_json_path = ROOT / "hooks" / "hooks.json"
        hooks_data = json.loads(hooks_json_path.read_text())

        matcher = hooks_data["hooks"]["PreToolUse"][0]["matcher"]
        matcher_tools = set(matcher.split("|"))

        assert matcher == "*" or "Bash" in matcher_tools, (
            f"hooks.json matcher must include 'Bash' to gate destructive sub-commands; "
            f"current matcher: {matcher}"
        )

    @pytest.mark.parametrize("event", ["PostToolUse", "PostToolUseFailure"])
    def test_hooks_json_audit_hook_matches_every_tool(self, event: str) -> None:
        """The audit hook runs after every tool call, succeeded or failed."""
        hooks_data = json.loads((ROOT / "hooks" / "hooks.json").read_text())

        logging = [
            group
            for group in hooks_data["hooks"][event]
            if any(
                h["command"].endswith("/hooks/posttooluse_log_tool.sh")
                for h in group["hooks"]
            )
        ]
        (group,) = logging
        assert group["matcher"] == "*", "`*` matches every tool"
        (hook,) = group["hooks"]
        assert hook["type"] == "command"


# ─── Names in records and diagnostics (security round 5, batch 2) ───

# Credential shapes the secret scan recognises, as a skill or tool name.
GITHUB_TOKEN = "ghp_A1b2C3d4E5A1b2C3d4E5A1b2C3d4E5A1b2C3d4E5AbCdEf"
SECRET_NAMES = [
    GITHUB_TOKEN,
    "AKIAIOSFODNN7EXAMPLE",
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz012345",
    f"docs-srv:skill://x/{GITHUB_TOKEN}/SKILL.md",
    f"x_{GITHUB_TOKEN}",
    "token:abcdef123456789",
]
# Names outside the plain grammar: shown [REDACTED] whatever they hold.
ODD_NAMES = ["a" * 129, "two words", "a/b", "user@host", "prüfen", ""]
PLAIN_NAMES = ["checkpoint", "anthropic-skills:pdf", "my.skill_v2", "a" * 128]


def _block(path: Path, begin: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.count(begin) == 1, path
    start = text.index(begin)
    return text[start : text.index(end, start) + len(end)]


def _plain_name(name: str, path: str | None = None) -> str:
    """plain_name of the log hook, with its copy of the secret scan."""
    scan = _block(POSTTOOLUSE_HOOK, "# BEGIN secret-scan", "# END secret-scan")
    plain = _block(POSTTOOLUSE_HOOK, "# BEGIN plain-name", "# END plain-name")
    env = {**os.environ, "LC_ALL": "C.UTF-8"}
    if path is not None:
        env["PATH"] = path
    bash = shutil.which("bash")
    assert bash is not None
    done = subprocess.run(
        [bash, "-c", f'set -euo pipefail\n{scan}\n{plain}\nplain_name "$1"', "x", name],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


class TestNamesHoldNoSecret:
    """The log hook wrote the Skill call's skill name, which the model
    chooses (an MCP skill address is any text after a server's name), into
    details.skill unchecked, and the tool's name into tool and intent: a
    credential there reached an HMAC-signed line of .claude/audit.log
    (STANDARD 1.2.0 §6.7, §6.4). Both now show a name only when it is
    plain (1 to 128 ASCII letters, digits, `.`, `_`, `:`, `-`) and the
    secret scan finds nothing in it, else [REDACTED]; the pre-tool-use
    hook's diagnostics name the tool the same way."""

    def test_the_two_hooks_hold_one_rule(self) -> None:
        log = _block(POSTTOOLUSE_HOOK, "# BEGIN plain-name", "# END plain-name")
        pre = _block(PRETOOLUSE_HOOK, "# BEGIN plain-name", "# END plain-name")
        assert log == pre
        source = (ROOT / "hooks" / "secret_scan.sh").read_text(encoding="utf-8")
        scan = source[source.index("# BEGIN secret-scan") :].strip()
        assert (
            _block(POSTTOOLUSE_HOOK, "# BEGIN secret-scan", "# END secret-scan") == scan
        )

    @pytest.mark.parametrize("name", SECRET_NAMES + ODD_NAMES)
    def test_a_skill_name_that_may_hold_a_secret_is_redacted(
        self, tmp_path: Path, name: str
    ) -> None:
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "AUDIT_HMAC_KEY": "unit-test-key"}
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Skill",
            "tool_use_id": "toolu_01",
            "tool_input": {"skill": name, "args": "x"},
            "tool_response": "Unknown skill",
        }
        assert run_hook(POSTTOOLUSE_HOOK, payload, env).returncode == 0
        (entry,) = read_entries(tmp_path)
        expected = "unknown" if name == "" else "[REDACTED]"
        assert entry["details"]["skill"] == expected
        assert entry["tool"] == "Skill"
        log_file = tmp_path / ".claude" / "audit.log"
        if name:
            assert name not in log_file.read_text(encoding="utf-8")
        assert GITHUB_TOKEN not in log_file.read_text(encoding="utf-8")
        assert verify_log(log_file, "unit-test-key") == (1, 1, [])

    @pytest.mark.parametrize(
        "name", [f"mcp__srv__{GITHUB_TOKEN}", "mcp__s__AKIAIOSFODNN7EXAMPLE"]
    )
    def test_a_tool_name_that_holds_a_secret_is_redacted(
        self, tmp_path: Path, name: str
    ) -> None:
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "AUDIT_HMAC_KEY": "unit-test-key"}
        payload = {"tool_name": name, "tool_use_id": "toolu_02", "tool_input": {}}
        assert run_hook(POSTTOOLUSE_HOOK, payload, env).returncode == 0
        (entry,) = read_entries(tmp_path)
        assert entry["tool"] == "[REDACTED]"
        assert entry["intent"] == "[REDACTED] call"
        log_file = tmp_path / ".claude" / "audit.log"
        assert name not in log_file.read_text(encoding="utf-8")
        assert verify_log(log_file, "unit-test-key") == (1, 1, [])

    @pytest.mark.parametrize("name", PLAIN_NAMES)
    def test_a_plain_name_is_kept(self, tmp_path: Path, name: str) -> None:
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "AUDIT_HMAC_KEY": "unit-test-key"}
        for payload in (
            {"tool_name": "Skill", "tool_input": {"skill": name}},
            {"tool_name": f"mcp__srv__{name}"[:128], "tool_input": {}},
        ):
            assert run_hook(POSTTOOLUSE_HOOK, payload, env).returncode == 0
        skill, tool = read_entries(tmp_path)
        assert skill["details"]["skill"] == name
        assert tool["tool"] == f"mcp__srv__{name}"[:128]

    def test_a_scan_that_cannot_run_redacts(self) -> None:
        """With no grep the scan cannot answer (status 127): the name is
        [REDACTED], never shown unscanned; Claude Code's own tools' names
        need no scan."""
        assert _plain_name("checkpoint") == "checkpoint"
        assert _plain_name("checkpoint", path="/nonexistent") == "[REDACTED]"
        assert _plain_name("Bash", path="/nonexistent") == "Bash"
        assert _plain_name(GITHUB_TOKEN) == "[REDACTED]"

    @pytest.mark.parametrize("name", ["prüfen", "ａbc", "ǅx"])
    def test_the_grammar_is_ascii_in_any_locale(self, name: str) -> None:
        assert _plain_name(name) == "[REDACTED]"

    def test_the_pre_tool_use_hooks_approval_request_names_no_secret(
        self, tmp_path: Path
    ) -> None:
        """The F502 reason for an unbound tool named its name verbatim."""
        marker_dir = tmp_path / ".claude"
        marker_dir.mkdir()
        now = int(time.time())
        (marker_dir / "checkpoint.ok").write_text(
            json.dumps(
                {"checkpoint_id": "chk_1", "created_at": now, "expires_at": now + 1800}
            )
        )
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        name = f"mcp__srv__{GITHUB_TOKEN}"
        result = run_hook(PRETOOLUSE_HOOK, call(name, x="y"), env)
        assert result.returncode == 0, result.stderr
        reason = json.loads(result.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert reason.startswith("F502 APPROVAL_REQUIRED: [REDACTED] (unbound")
        assert GITHUB_TOKEN not in result.stdout + result.stderr

    def test_the_pre_tool_use_hook_names_a_plain_tool(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / ".claude"
        marker_dir.mkdir()
        now = int(time.time())
        (marker_dir / "checkpoint.ok").write_text(
            json.dumps(
                {"checkpoint_id": "chk_1", "created_at": now, "expires_at": now + 1800}
            )
        )
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = run_hook(PRETOOLUSE_HOOK, call("mcp__github__push_files"), env)
        assert result.returncode == 0, result.stderr
        reason = json.loads(result.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert reason.startswith("F502 APPROVAL_REQUIRED: mcp__github__push_files (")
