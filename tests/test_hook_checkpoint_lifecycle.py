"""The plugin's checkpoint lifecycle (STANDARD 1.2.0 section 5.18.6): a
successful `git stash create` writes the marker (posttooluse_take_checkpoint.sh),
a gated call uses it (pretooluse_require_checkpoint.sh), and the end of a turn
ends its validity (stop_end_checkpoints.sh). A marker whose validity ended
unused (expired, turn ended, replaced) is filed under
.claude/checkpoints/ended/, so its commit, entered in the project's git
directory (<git dir>/acs/checkpoints/commits/), can still be restored."""

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


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=path,
        env={**os.environ, **_GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _commits(project: Path) -> Path:
    """Where the take hook enters the commits it records: the project's git
    directory, outside the work tree."""
    return project / ".git" / "acs" / "checkpoints" / "commits"


def _clean_repo(path: Path) -> Path:
    """A repository with one commit and a tree that is HEAD's."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "a.txt").write_text("a\n")
    _git(path, "add", "a.txt")
    _git(path, "commit", "-q", "-m", "init")
    return path


def test_a_successful_stash_create_writes_the_marker(tmp_path: Path) -> None:
    _clean_repo(tmp_path)
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
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": ""}), tmp_path)
    marker = _marker(tmp_path)
    assert marker is not None
    assert marker["commit"] == "HEAD"
    assert marker["checkpoint_id"].startswith("clean-")


@pytest.mark.parametrize("change", ["worktree", "index"])
def test_empty_output_over_a_changed_tree_writes_no_marker(
    tmp_path: Path, change: str
) -> None:
    """Empty output means nothing was saved: HEAD restores the state only
    when the tracked files and the index are HEAD's. Over a changed tree a
    'clean' marker would let the next write pass with a checkpoint that
    cannot bring the change back."""
    _clean_repo(tmp_path)
    (tmp_path / "a.txt").write_text("uncommitted\n")
    if change == "index":
        _git(tmp_path, "add", "a.txt")
    result = _run(TAKE, _stash("git stash create", {"stdout": ""}), tmp_path)
    assert result.returncode == 0
    assert _marker(tmp_path) is None


def test_empty_output_outside_a_repository_writes_no_marker(tmp_path: Path) -> None:
    _run(TAKE, _stash("git stash create", {"stdout": ""}), tmp_path)
    assert _marker(tmp_path) is None


@pytest.mark.parametrize("stdout", ["", SHA])
def test_a_call_run_in_the_background_writes_no_marker(
    tmp_path: Path, stdout: str
) -> None:
    """A background call has not finished when the hook runs: its output is
    not the command's, so it records nothing."""
    _clean_repo(tmp_path)
    payload = _stash("git stash create", {"stdout": stdout})
    payload["tool_input"]["run_in_background"] = True
    assert _run(TAKE, payload, tmp_path).returncode == 0
    assert _marker(tmp_path) is None


@pytest.mark.parametrize("stdout", ["", SHA])
def test_a_stash_of_another_repository_writes_no_marker(
    tmp_path: Path, stdout: str
) -> None:
    project = _clean_repo(tmp_path / "project")
    elsewhere = _clean_repo(tmp_path / "elsewhere")
    payload = {**_stash("git stash create", {"stdout": stdout}), "cwd": str(elsewhere)}
    assert _run(TAKE, payload, project).returncode == 0
    assert _marker(project) is None
    # Run in the project (a subdirectory of it included), the same call writes it.
    (project / "sub").mkdir()
    payload["cwd"] = str(project / "sub")
    assert _run(TAKE, payload, project).returncode == 0
    marker = _marker(project)
    assert marker is not None and marker["commit"] == (stdout or "HEAD")


def test_output_that_is_not_a_commit_writes_no_marker(tmp_path: Path) -> None:
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": "warning: x"}), tmp_path)
    assert _marker(tmp_path) is None


def test_a_long_line_is_read_in_bounded_time_and_writes_no_marker(
    tmp_path: Path,
) -> None:
    """split_words reads a line of at most 4096 bytes; a longer one is not
    read (and a UTF-8 locale does not slow the reading)."""
    _clean_repo(tmp_path)
    command = "git stash create " + "a" * 100_000
    result = _run(TAKE, _stash(command, {"stdout": SHA}), tmp_path, LC_ALL="C.UTF-8")
    assert result.returncode == 0
    assert _marker(tmp_path) is None


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
    _clean_repo(tmp_path)
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
    _clean_repo(tmp_path)
    stashed = _git(tmp_path, "stash", "create")
    assert stashed == ""

    payload = {**_stash("git stash create", {"stdout": stashed}), "cwd": str(tmp_path)}
    _run(TAKE, payload, tmp_path)
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


OTHER = "fedcba9876543210fedcba9876543210fedcba98"


def _ended(project: Path) -> list[dict[str, Any]]:
    ended = project / ".claude" / "checkpoints" / "ended"
    return [json.loads(f.read_text()) for f in sorted(ended.iterdir())]


def _restore(project: Path, commit: str) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": f"git stash apply {commit}"},
        "permission_mode": "default",
        "tool_use_id": "r1",
    }
    return _run(PRE, payload, project, ACS_HOOK_APPROVAL="off")


def test_stop_ends_the_marker_and_keeps_the_history(tmp_path: Path) -> None:
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    used = tmp_path / ".claude" / "checkpoints" / "used"
    used.mkdir(parents=True)
    (used / "old.c1.x").write_text("{}")
    result = _run(STOP, {"hook_event_name": "Stop"}, tmp_path)
    assert result.returncode == 0
    assert _marker(tmp_path) is None
    assert (used / "old.c1.x").exists()
    assert [m["commit"] for m in _ended(tmp_path)] == [SHA]


def test_a_checkpoint_whose_turn_ended_can_still_be_restored(tmp_path: Path) -> None:
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    _run(STOP, {"hook_event_name": "Stop"}, tmp_path)
    assert _restore(tmp_path, SHA).returncode == 0
    # Restoring a commit no marker recorded is a gated mutate: no marker.
    other = _restore(tmp_path, OTHER)
    assert other.returncode == 2
    assert other.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")


def test_an_expired_checkpoint_can_still_be_restored(tmp_path: Path) -> None:
    _clean_repo(tmp_path)
    now = int(time.time())
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    marker = _marker(tmp_path)
    assert marker is not None
    (tmp_path / ".claude" / "checkpoint.ok").write_text(
        json.dumps({**marker, "created_at": now - 120, "expires_at": now - 60})
    )
    write = {
        "tool_name": "Write",
        "tool_input": {"file_path": "a.txt"},
        "permission_mode": "default",
        "tool_use_id": "w1",
    }
    refused = _run(PRE, write, tmp_path, ACS_HOOK_APPROVAL="off")
    assert refused.returncode == 2
    assert "checkpoint has expired" in refused.stderr
    assert _marker(tmp_path) is None
    assert [m["commit"] for m in _ended(tmp_path)] == [SHA]
    assert _restore(tmp_path, SHA).returncode == 0


def test_a_replaced_checkpoint_can_still_be_restored(tmp_path: Path) -> None:
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": OTHER}), tmp_path)
    marker = _marker(tmp_path)
    assert marker is not None and marker["commit"] == OTHER
    assert [m["commit"] for m in _ended(tmp_path)] == [SHA]
    assert _restore(tmp_path, SHA).returncode == 0
    # The restore used nothing: the newer marker is still there.
    assert _marker(tmp_path) == marker


def test_stop_removes_a_marker_that_is_not_a_regular_file(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps({"checkpoint_id": SHA, "commit": SHA}))
    (claude / "checkpoint.ok").symlink_to(target)
    assert _run(STOP, {"hook_event_name": "Stop"}, tmp_path).returncode == 0
    assert not (claude / "checkpoint.ok").is_symlink()
    assert not (claude / "checkpoints" / "ended").exists()
    assert target.exists()


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


def test_a_restore_looks_up_one_entry_not_the_history(tmp_path: Path) -> None:
    """A successful `git stash create` enters its commit in
    <git dir>/acs/checkpoints/commits/, and a restore looks that entry up:
    it reads no file of the history (used/, ended/), which grows with every
    checkpoint taken, so the check takes the same time however long the
    history is (a check that ran past the hook's timeout would let the
    call run)."""
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    entry = _commits(tmp_path) / SHA
    assert entry.is_file() and entry.read_text() == ""
    _run(STOP, {"hook_event_name": "Stop"}, tmp_path)
    assert _marker(tmp_path) is None
    assert _restore(tmp_path, SHA).returncode == 0
    # A record in the history alone, which nothing entered, restores nothing.
    ended = tmp_path / ".claude" / "checkpoints" / "ended"
    ended.mkdir(parents=True, exist_ok=True)
    (ended / "planted.1").write_text(
        json.dumps({"checkpoint_id": OTHER, "commit": OTHER})
    )
    other = _restore(tmp_path, OTHER)
    assert other.returncode == 2
    assert other.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")


def test_a_clean_tree_enters_no_commit(tmp_path: Path) -> None:
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": ""}), tmp_path)
    assert _marker(tmp_path) is not None
    assert not _commits(tmp_path).exists()
    assert not (tmp_path / ".claude" / "checkpoints" / "commits").exists()


def test_a_commit_outside_a_repository_writes_no_marker(tmp_path: Path) -> None:
    """A commit is entered in the project's git directory; with none, the
    take hook enters nothing and writes no marker that names it."""
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    assert _marker(tmp_path) is None
    assert not (tmp_path / ".claude" / "checkpoints" / "commits").exists()


@pytest.mark.parametrize(
    "command",
    [
        "git stash create" + " " * 50_000,
        " " * 200_000 + "git stash create",
        "git stash create" + "\t" * 50_000,
    ],
)
def test_long_blank_runs_are_not_trimmed_and_write_no_marker(
    tmp_path: Path, command: str
) -> None:
    """The trims' cost grows with the line times its run of blanks: the
    length is checked first, so a padded line is not read, in bounded time
    (50,000 trailing blanks took 44 s to trim before)."""
    _clean_repo(tmp_path)
    started = time.monotonic()
    result = _run(TAKE, _stash(command, {"stdout": SHA}), tmp_path)
    assert time.monotonic() - started < 10
    assert result.returncode == 0
    assert _marker(tmp_path) is None


BOUNDARIES = ["Stop", "StopFailure", "UserPromptSubmit", "SessionStart", "SessionEnd"]


def test_every_boundary_event_ends_the_marker() -> None:
    """The end and the start of a turn and of a session are execution
    boundaries (STANDARD 1.2.0 §5.18.6): Claude Code runs StopFailure in
    place of Stop when an API error ended the turn, and a turn that was
    interrupted or a session that was killed reaches neither, so the next
    prompt or session ends a marker they left."""
    hooks = json.loads((HOOKS / "hooks.json").read_text())["hooks"]
    for event in BOUNDARIES:
        commands = [h["command"] for group in hooks[event] for h in group["hooks"]]
        assert commands == ["${CLAUDE_PLUGIN_ROOT}/hooks/stop_end_checkpoints.sh"], (
            event
        )


@pytest.mark.parametrize("event", BOUNDARIES)
def test_a_marker_left_by_an_earlier_turn_authorises_nothing(
    tmp_path: Path, event: str
) -> None:
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    boundary = {"hook_event_name": event, "session_id": "s2", "prompt": "next"}
    result = _run(STOP, boundary, tmp_path)
    assert (result.returncode, result.stdout) == (0, "")
    assert _marker(tmp_path) is None
    assert [m["commit"] for m in _ended(tmp_path)] == [SHA]
    write = {
        "tool_name": "Write",
        "tool_input": {"file_path": "a.txt"},
        "permission_mode": "acceptEdits",
        "tool_use_id": "w2",
    }
    refused = _run(PRE, write, tmp_path)
    assert refused.returncode == 2
    assert refused.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
    # Its commit can still be restored.
    assert _restore(tmp_path, SHA).returncode == 0


def test_the_layer_maximum_age_applies_to_a_marker_written_under_a_longer_one(
    tmp_path: Path,
) -> None:
    """A marker written under ACS_CHECKPOINT_MAX_AGE=1800 (or by another
    writer) is held to the maximum age in force when it is used, the one
    the log hook records (STANDARD 1.2.0 §5.18.6, §5.18.8)."""
    _clean_repo(tmp_path)
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    marker = _marker(tmp_path)
    assert marker is not None
    path = tmp_path / ".claude" / "checkpoint.ok"
    path.write_text(
        json.dumps(
            {
                **marker,
                "created_at": marker["created_at"] - 600,
                "expires_at": marker["expires_at"] - 600,
            }
        )
    )
    write = {
        "tool_name": "Write",
        "tool_input": {"file_path": "a.txt"},
        "permission_mode": "default",
        "tool_use_id": "w1",
    }
    refused = _run(PRE, write, tmp_path, ACS_CHECKPOINT_MAX_AGE="60")
    assert refused.returncode == 2
    assert refused.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
    assert "expired" in refused.stderr
    assert not path.exists()
    assert [m["commit"] for m in _ended(tmp_path)] == [SHA]
    # Within the maximum age the same marker authorises the call.
    _run(TAKE, _stash("git stash create", {"stdout": SHA}), tmp_path)
    allowed = _run(PRE, write, tmp_path, ACS_CHECKPOINT_MAX_AGE="60")
    assert allowed.returncode == 0
    assert not path.exists()
