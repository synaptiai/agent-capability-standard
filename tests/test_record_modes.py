"""The plugin's hooks keep the layer's records private to the user (#173,
DG-701-C): every directory they create is mode 0700 and every file 0600,
whatever umask Claude Code started with. The records are the audit log, its
head and the head's anchor, the checkpoint marker and its history under
``.claude/checkpoints/``, and the checkpoint key and commit entries under the
git directory's ``acs/``. Each test runs the hooks under umask 022, the usual
default, under which a plain ``mkdir`` gives 0755 and a redirection 0644.

A directory that already exists keeps its mode: spec/SECURITY.md section 8.3
gives the operator the commands that tighten one.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
LOG = HOOKS / "posttooluse_log_tool.sh"
TAKE = HOOKS / "posttooluse_take_checkpoint.sh"
PRE = HOOKS / "pretooluse_require_checkpoint.sh"
STOP = HOOKS / "stop_end_checkpoints.sh"
KEY = "0123456789abcdef" * 4


def _bashes() -> list[str]:
    """Each bash on this machine, once: CI runs macOS /bin/bash 3.2, and
    Homebrew's or Linux's bash 5."""
    found: dict[str, str] = {}
    for candidate in ("/bin/bash", "/opt/homebrew/bin/bash", "/usr/local/bin/bash"):
        if os.access(candidate, os.X_OK):
            found.setdefault(os.path.realpath(candidate), candidate)
    return list(found.values())


pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None
    or shutil.which("openssl") is None
    or shutil.which("git") is None
    or not _bashes(),
    reason="the hooks need bash, jq, openssl and git",
)

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _umask_022() -> None:
    os.umask(0o022)


def _git(project: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=project,
        env={**os.environ, **_GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
        preexec_fn=_umask_022,
    ).stdout.strip()


def _home(tmp_path: Path) -> Path:
    """A HOME with the audit key file, so the log hook writes the head and
    its anchor."""
    home = tmp_path / "home"
    directory = home / ".config" / "acs"
    directory.mkdir(parents=True)
    directory.chmod(0o700)
    key = directory / "audit.key"
    key.write_text(KEY, encoding="ascii")
    key.chmod(0o600)
    return home


def _project(tmp_path: Path) -> tuple[Path, str]:
    """A repository with one commit and a change, and the commit `git stash
    create` printed for it."""
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q")
    (project / "a.txt").write_text("a\n")
    _git(project, "add", "a.txt")
    _git(project, "commit", "-q", "-m", "init")
    (project / "a.txt").write_text("b\n")
    (project / "a.txt").chmod(0o644)
    return project, _git(project, "stash", "create")


def _run(
    bash: str, script: Path, payload: dict[str, Any], project: Path, home: Path
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "AUDIT_HMAC_KEY"}
    env.update({"HOME": str(home), "CLAUDE_PROJECT_DIR": str(project)})
    return subprocess.run(
        [bash, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=project,
        timeout=60,
        preexec_fn=_umask_022,
    )


def _take(bash: str, project: Path, home: Path, commit: str) -> None:
    result = _run(
        bash,
        TAKE,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git stash create"},
            "tool_response": {"stdout": commit + "\n"},
        },
        project,
        home,
    )
    assert result.returncode == 0, result.stderr
    assert (project / ".claude" / "checkpoint.ok").is_file(), result.stderr


def _write_call(event: str, call_id: str, project: Path) -> dict[str, Any]:
    return {
        "hook_event_name": event,
        "tool_name": "Write",
        "tool_use_id": call_id,
        "permission_mode": "default",
        "cwd": str(project),
        "tool_input": {"file_path": "x.txt", "content": "y"},
    }


def _modes(project: Path) -> dict[str, int]:
    """The mode of every path under .claude/ and the git directory's acs/,
    by its path relative to the project."""
    found: dict[str, int] = {}
    for top in (project / ".claude", project / ".git" / "acs"):
        assert top.is_dir(), top
        for path in [top, *top.rglob("*")]:
            found[str(path.relative_to(project))] = stat.S_IMODE(path.lstat().st_mode)
    return found


def _assert_private(modes: dict[str, int], project: Path) -> None:
    loose = {
        name: oct(mode)
        for name, mode in modes.items()
        if mode != (0o700 if (project / name).is_dir() else 0o600)
    }
    assert not loose, f"records not private to the user: {loose}"


@pytest.mark.parametrize("bash", _bashes())
def test_the_checkpoint_lifecycle_keeps_every_record_private(
    bash: str, tmp_path: Path
) -> None:
    """Take a checkpoint, replace it, end it at a turn's end, take another,
    use it for a gated call, and log the call: every record the four hooks
    created is 0700 or 0600."""
    home = _home(tmp_path)
    project, commit = _project(tmp_path)
    _take(bash, project, home, commit)
    _take(bash, project, home, commit)  # replaces the marker: ended/replaced.*
    stop = _run(bash, STOP, {"hook_event_name": "Stop"}, project, home)
    assert stop.returncode == 0, stop.stderr
    _take(bash, project, home, commit)
    pre = _run(bash, PRE, _write_call("PreToolUse", "toolu_m1", project), project, home)
    assert pre.returncode == 0, pre.stderr
    assert '"permissionDecision":"ask"' in pre.stdout, pre.stdout
    log = _run(
        bash, LOG, _write_call("PostToolUse", "toolu_m1", project), project, home
    )
    assert log.returncode == 0, log.stderr

    modes = _modes(project)
    for name in (
        ".claude",
        ".claude/audit.log",
        ".claude/audit.head",
        ".claude/checkpoints",
        ".claude/checkpoints/used",
        ".claude/checkpoints/ended",
        ".git/acs/audit.head",
        ".git/acs/checkpoints/key",
        f".git/acs/checkpoints/commits/{commit}",
    ):
        assert name in modes, f"{name} was not written: {sorted(modes)}"
    assert any(n.startswith(".claude/checkpoints/used/") for n in modes)
    assert any(n.startswith(".claude/checkpoints/ended/replaced.") for n in modes)
    assert any(n.startswith(".claude/checkpoints/ended/turn-ended.") for n in modes)
    _assert_private(modes, project)
    # The project's own files keep their modes: only the records change.
    assert stat.S_IMODE((project / "a.txt").stat().st_mode) == 0o644


@pytest.mark.parametrize("bash", _bashes())
def test_the_stop_hook_files_the_marker_in_a_private_directory(
    bash: str, tmp_path: Path
) -> None:
    """One checkpoint, then the turn ends: the stop hook creates ended/ and
    files the marker there."""
    home = _home(tmp_path)
    project, commit = _project(tmp_path)
    _take(bash, project, home, commit)
    assert not (project / ".claude" / "checkpoints" / "ended").exists()
    stop = _run(bash, STOP, {"hook_event_name": "Stop"}, project, home)
    assert stop.returncode == 0, stop.stderr
    assert not (project / ".claude" / "checkpoint.ok").exists()
    modes = _modes(project)
    assert ".claude/checkpoints/ended" in modes, sorted(modes)
    assert any(n.startswith(".claude/checkpoints/ended/turn-ended.") for n in modes)
    _assert_private(modes, project)


@pytest.mark.parametrize("bash", _bashes())
def test_the_log_hook_alone_creates_a_private_log(bash: str, tmp_path: Path) -> None:
    """The first call of a session in a new project: the log hook creates
    .claude/ itself."""
    home = _home(tmp_path)
    project, _ = _project(tmp_path)
    log = _run(
        bash, LOG, _write_call("PostToolUse", "toolu_m2", project), project, home
    )
    assert log.returncode == 0, log.stderr
    modes = _modes(project)
    for name in (
        ".claude",
        ".claude/audit.log",
        ".claude/audit.head",
        ".git/acs/audit.head",
    ):
        assert name in modes, f"{name} was not written: {sorted(modes)}"
    _assert_private(modes, project)


@pytest.mark.parametrize("bash", _bashes())
def test_an_expired_marker_is_filed_in_a_private_directory(
    bash: str, tmp_path: Path
) -> None:
    """The pre-tool-use hook files an expired marker under ended/, which it
    creates."""
    home = _home(tmp_path)
    project, commit = _project(tmp_path)
    _take(bash, project, home, commit)
    marker_path = project / ".claude" / "checkpoint.ok"
    marker = json.loads(marker_path.read_text())
    marker["created_at"] -= 4000
    marker["expires_at"] -= 4000
    marker_path.write_text(json.dumps(marker))
    marker_path.chmod(0o600)
    assert not (project / ".claude" / "checkpoints" / "ended").exists()
    pre = _run(bash, PRE, _write_call("PreToolUse", "toolu_m3", project), project, home)
    assert "F501" in pre.stdout + pre.stderr, pre.stdout + pre.stderr
    modes = _modes(project)
    assert any(n.startswith(".claude/checkpoints/ended/expired.") for n in modes), (
        sorted(modes)
    )
    _assert_private(modes, project)
