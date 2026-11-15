"""The plugin's checkpoint lifecycle (STANDARD 1.2.0 section 5.18.6): a
successful `git stash create` writes the marker (posttooluse_take_checkpoint.sh),
a gated call uses it (pretooluse_require_checkpoint.sh), and the end of a turn
removes it (stop_end_checkpoints.sh)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
TAKE = HOOKS / "posttooluse_take_checkpoint.sh"
STOP = HOOKS / "stop_end_checkpoints.sh"
PRE = HOOKS / "pretooluse_require_checkpoint.sh"
SHA = "0123456789abcdef0123456789abcdef01234567"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the hooks need bash and jq",
)


def _run(
    script: Path, payload: dict[str, Any] | str, project: Path, **env: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), **env},
        timeout=30,
        cwd=project,
    )


def _stash(command: str, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": response,
    }


def _marker(project: Path) -> dict[str, Any] | None:
    path = project / ".claude" / "checkpoint.ok"
    return json.loads(path.read_text()) if path.exists() else None


def test_a_successful_stash_create_writes_the_marker(tmp_path: Path) -> None:
    before = int(time.time())
    result = _run(
        TAKE,
        _stash('git stash create "checkpoint:x"', {"stdout": SHA + "\n"}),
        tmp_path,
    )
    assert result.returncode == 0
    marker = _marker(tmp_path)
    assert marker is not None
    assert marker["checkpoint_id"] == SHA
    assert marker["commit"] == SHA
    assert marker["source"] == "git stash create"
    assert 0 < marker["expires_at"] - before <= 1800 + 2


def test_a_clean_tree_restores_to_head(tmp_path: Path) -> None:
    _run(TAKE, _stash("git stash create", {"stdout": ""}), tmp_path)
    marker = _marker(tmp_path)
    assert marker is not None
    assert marker["commit"] == "HEAD"
    assert marker["checkpoint_id"].startswith("clean-")


@pytest.mark.parametrize(
    "payload",
    [
        _stash("git stash create", {"is_error": True, "stdout": SHA}),
        _stash("git stash create", {"interrupted": True}),
        _stash(f"git stash store -m m {SHA}", {}),
        _stash("git stash create && rm -rf x", {"stdout": SHA}),
        _stash("git stash create --output=f", {}),
        "not json",
    ],
)
def test_nothing_else_writes_a_marker(tmp_path: Path, payload: Any) -> None:
    result = _run(TAKE, payload, tmp_path)
    assert result.returncode == 0
    assert _marker(tmp_path) is None


def test_the_maximum_age_is_capped(tmp_path: Path) -> None:
    before = int(time.time())
    _run(
        TAKE,
        _stash("git stash create", {"stdout": SHA}),
        tmp_path,
        ACS_CHECKPOINT_MAX_AGE="99999",
    )
    marker = _marker(tmp_path)
    assert marker is not None and marker["expires_at"] - before <= 1800 + 2
    _run(
        TAKE,
        _stash("git stash create", {"stdout": SHA}),
        tmp_path,
        ACS_CHECKPOINT_MAX_AGE="60",
    )
    marker = _marker(tmp_path)
    assert marker is not None and marker["expires_at"] - marker["created_at"] == 60


def test_a_clean_repository_then_a_write(tmp_path: Path) -> None:
    """In a real repository with a clean tree, `git stash create` prints
    nothing; the restore point is HEAD, and the Write that follows is
    allowed and uses the marker."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    run = {
        "cwd": tmp_path,
        "env": {**os.environ, **env},
        "check": True,
        "capture_output": True,
    }
    subprocess.run(["git", "init", "-q"], **run)
    (tmp_path / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "a.txt"], **run)
    subprocess.run(["git", "commit", "-q", "-m", "init"], **run)
    stashed = subprocess.run(["git", "stash", "create"], text=True, **run)
    assert stashed.stdout == ""

    _run(TAKE, _stash("git stash create", {"stdout": stashed.stdout}), tmp_path)
    marker = _marker(tmp_path)
    assert marker is not None and marker["commit"] == "HEAD"

    write = {
        "tool_name": "Write",
        "tool_input": {"file_path": "a.txt"},
        "permission_mode": "default",
        "tool_use_id": "w1",
    }
    allowed = _run(PRE, write, tmp_path, ACS_HOOK_APPROVAL="off")
    assert allowed.returncode == 0
    assert _marker(tmp_path) is None


def test_stop_removes_the_marker_and_keeps_the_history(tmp_path: Path) -> None:
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    used = tmp_path / ".claude" / "checkpoints" / "used"
    used.mkdir(parents=True)
    (used / "old.c1.x").write_text("{}")
    result = _run(STOP, {"hook_event_name": "Stop"}, tmp_path)
    assert result.returncode == 0
    assert _marker(tmp_path) is None
    assert (used / "old.c1.x").exists()


def test_stop_exits_0_without_a_claude_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(STOP)],
        input="",
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path / "missing")},
        timeout=30,
    )
    assert result.returncode == 0
