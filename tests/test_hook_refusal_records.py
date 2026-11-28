"""The plugin's audit log records the pre-tool-use hook's refusals and the
checkpoint each gated call used (STANDARD 1.2.0 sections 5.18.8 and 6.4).

A call the pre-tool-use hook refuses (F501, F502, F504, R407) is appended by
the log hook to the same HMAC chain as a ``rejected`` action record with its
code; a call that took a checkpoint marker is logged with the capability
``mutate`` and the marker's checkpoint id and commit, read from the marker
the pre-tool-use hook filed under ``.claude/checkpoints/used/``.
``tools/verify_audit_log.py`` accepts both.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from tests.action_record_schema import problems

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
LOG = ROOT / "hooks" / "posttooluse_log_tool.sh"
VERIFY = ROOT / "tools" / "verify_audit_log.py"
KEY = "refusal-records-test-key-0123456789abcdef"
COMMIT = "0123456789abcdef0123456789abcdef01234567"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None
    or shutil.which("openssl") is None
    or shutil.which("git") is None,
    reason="the hooks need jq, openssl and git",
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    path = tmp_path / "project"
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True, timeout=30)
    (tmp_path / "home").mkdir()
    return path


def _env(project: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in ("ACS_HOOK_APPROVAL", "ACS_CHECKPOINT_MAX_AGE", "CLAUDE_PLUGIN_ROOT"):
        env.pop(name, None)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    # No key file: the key is AUDIT_HMAC_KEY.
    env["HOME"] = str(project.parent / "home")
    env["AUDIT_HMAC_KEY"] = KEY
    return env


def _call(
    tool: str, tool_input: dict[str, Any], call: str, mode: str = "default"
) -> dict[str, Any]:
    return {
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_use_id": call,
        "permission_mode": mode,
    }


def _run(
    hook: Path, project: Path, payload: dict[str, Any], *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=_env(project),
        timeout=60,
        check=False,
    )


def _post(project: Path, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return _run(
        LOG,
        project,
        {**payload, "hook_event_name": "PostToolUse", "tool_response": {}},
    )


def _lines(project: Path) -> list[dict[str, Any]]:
    log = project / ".claude" / "audit.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _verify(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFY),
            "--log-file",
            str(project / ".claude" / "audit.log"),
            "--head-file",
            str(project / ".claude" / "audit.head"),
            "--anchor-file",
            str(project / ".git" / "acs" / "audit.head"),
            "--hmac-key",
            KEY,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _marker(
    project: Path, checkpoint_id: str = COMMIT, commit: str | None = COMMIT
) -> Path:
    now = int(time.time())
    path = project / ".claude" / "checkpoint.ok"
    path.parent.mkdir(exist_ok=True)
    marker: dict[str, Any] = {
        "checkpoint_id": checkpoint_id,
        "created_at": now,
        "expires_at": now + 600,
    }
    if commit is not None:
        marker |= {"commit": commit, "source": "git stash create"}
    path.write_text(json.dumps(marker))
    return path


def test_an_f501_refusal_is_a_rejected_record_in_the_chain(project: Path) -> None:
    """A refusal is one line, a rejected action record with its code, the
    tool, the call id and the capability; two refusals chain, and the
    verifier accepts the log with its head and anchor."""
    write = _call("Write", {"file_path": "a.txt", "content": "x"}, "toolu_1")
    result = _run(PRE, project, write)
    assert result.returncode == 2
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED:")
    (record,) = _lines(project)
    assert problems(record) == [], record
    assert record["status"] == "rejected"
    assert record["code"] == "F501"
    assert record["capability"] == "mutate"
    assert record["tool"] == "Write"
    assert record["action_id"] == record["call_id"] == "toolu_1"
    assert record["details"]["event"] == "PreToolUse"
    assert "checkpoint_id" not in record["details"]
    assert record["recorded_by"]["name"]

    result = _run(PRE, project, {**write, "tool_use_id": "toolu_2"})
    assert result.returncode == 2
    first, second = _lines(project)
    assert second["prev_hmac"] == first["hmac"]
    verified = _verify(project)
    assert verified.returncode == 0, verified.stdout + verified.stderr


def test_a_persist_refusal_names_persist(project: Path) -> None:
    token = "sk-" + "a1B2" * 6
    todo = _call("TodoWrite", {"todos": [{"content": f"key {token}"}]}, "toolu_3")
    result = _run(PRE, project, todo)
    assert result.returncode == 2
    assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED:")
    (record,) = _lines(project)
    assert problems(record) == [], record
    assert (record["status"], record["code"], record["capability"]) == (
        "rejected",
        "F504",
        "persist",
    )
    # The input is never written, only its digest.
    assert token not in (project / ".claude" / "audit.log").read_text()
    assert _verify(project).returncode == 0


@pytest.mark.parametrize(
    "text",
    ["feature/task-12345-update-readme-file", "risk-assessment-for-the-quarter-2026"],
)
def test_a_slug_in_a_todo_is_not_refused(project: Path, text: str) -> None:
    """`sk-` ends the words `task` and `risk`: the shell scan reads it only
    where a token starts, so the hook lets the TodoWrite pass, and records
    nothing for it (the log hook logs it once it ran)."""
    todo = _call("TodoWrite", {"todos": [{"content": text}]}, "toolu_4")
    result = _run(PRE, project, todo)
    assert result.returncode == 0, result.stderr
    assert _lines(project) == []


def test_an_f502_refusal_in_a_mode_that_asks_no_one(project: Path) -> None:
    """Approval needs a person: in bypassPermissions the call is refused
    with F502 before it takes the marker, and the refusal is recorded."""
    marker = _marker(project)
    write = _call(
        "Write", {"file_path": "a.txt", "content": "x"}, "toolu_5", "bypassPermissions"
    )
    result = _run(PRE, project, write)
    assert result.returncode == 2
    assert result.stderr.startswith("F502 APPROVAL_REQUIRED:")
    assert marker.exists()
    (record,) = _lines(project)
    assert problems(record) == [], record
    assert (record["status"], record["code"], record["capability"]) == (
        "rejected",
        "F502",
        "mutate",
    )
    assert _verify(project).returncode == 0


def test_the_project_settings_refusal_is_not_recorded(project: Path) -> None:
    """With the project's settings setting a variable in env, the log hook
    signs nothing, so that R407 refusal is not recorded."""
    settings = project / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"env": {"ACS_HOOK_APPROVAL": "off"}}))
    write = _call("Write", {"file_path": "a.txt", "content": "x"}, "toolu_6")
    result = _run(PRE, project, write)
    assert result.returncode == 2
    assert result.stderr.startswith("R407 SAFETY_CHECK_FAILED:")
    assert _lines(project) == []


def test_a_gated_call_names_the_checkpoint_it_used(project: Path) -> None:
    """The line of a call that took a marker names the capability, the
    checkpoint id and the commit to restore, from the used marker the
    pre-tool-use hook filed under its documented name."""
    checkpoint_id = "clean-1700000000-42"
    _marker(project, checkpoint_id)
    write = _call("Write", {"file_path": "a.txt", "content": "x"}, "toolu_7")
    result = _run(PRE, project, write)
    assert result.returncode == 0, result.stderr
    assert (
        json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"
    )
    (used,) = (project / ".claude" / "checkpoints" / "used").iterdir()
    name, call, suffix = used.name.rsplit(".", 2)
    assert (name, call, len(suffix)) == (checkpoint_id, "toolu_7", 6)

    assert _post(project, write).returncode == 0
    (record,) = _lines(project)
    assert problems(record) == [], record
    assert record["status"] == "executed"
    assert record["capability"] == "mutate"
    assert "code" not in record
    assert record["details"]["checkpoint_id"] == checkpoint_id
    assert record["details"]["commit"] == COMMIT
    assert _verify(project).returncode == 0


def test_a_marker_with_no_commit_names_its_checkpoint(project: Path) -> None:
    """The SDK's CheckpointTracker writes a marker with no commit: the line
    names its checkpoint id and the capability, and no commit."""
    checkpoint_id = "20261128_120000_" + "0f" * 16
    _marker(project, checkpoint_id, commit=None)
    write = _call("Write", {"file_path": "a.txt", "content": "x"}, "toolu_10")
    assert _run(PRE, project, write).returncode == 0
    assert _post(project, write).returncode == 0
    (record,) = _lines(project)
    assert problems(record) == [], record
    assert record["capability"] == "mutate"
    assert record["details"]["checkpoint_id"] == checkpoint_id
    assert "commit" not in record["details"]


def test_another_calls_marker_is_not_taken_for_this_one(project: Path) -> None:
    """A used marker whose name matches the call's id only as a pattern
    (another call's id holds a dot) is not this call's; a call with no
    marker carries no checkpoint and no capability."""
    used = project / ".claude" / "checkpoints" / "used"
    used.mkdir(parents=True)
    (used / f"{COMMIT}.x.toolu_8.AbCdEf").write_text(
        json.dumps({"checkpoint_id": COMMIT, "commit": COMMIT})
    )
    read = _call("Read", {"file_path": "a.txt"}, "toolu_8")
    assert _post(project, read).returncode == 0
    (record,) = _lines(project)
    assert problems(record) == [], record
    assert "capability" not in record
    assert "checkpoint_id" not in record["details"]
    assert "commit" not in record["details"]


@pytest.mark.parametrize("code", ["X999", "", "F503"])
def test_the_log_hook_takes_only_the_hooks_refusal_codes(
    project: Path, code: str
) -> None:
    write = _call("Write", {"file_path": "a.txt", "content": "x"}, "toolu_9")
    result = _run(LOG, project, write, "--refused", code)
    assert result.returncode == 1
    assert "not logged" in result.stderr
    assert _lines(project) == []
