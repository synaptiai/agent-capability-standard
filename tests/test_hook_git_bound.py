"""The hooks' own reads are bounded in time (security round 5, batch 1, #4).

git reads the files a repository's configuration includes, and the hooks
read the project's settings files: a FIFO there, or a terminal such as
``/dev/ptmx``, holds the read until someone writes. The pre-tool-use hook
then gave no verdict within hooks.json's 30 seconds, and a Claude Code
without ``onFailure: "block"`` runs such a call unchecked; the log hook
wrote no line. Each git and settings read now runs for at most 5 seconds,
and a read that did not answer counts as one the layer cannot complete
(R407, F501 or a gated call), never as "no repository".
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
PRE = HOOKS / "pretooluse_require_checkpoint.sh"
TAKE = HOOKS / "posttooluse_take_checkpoint.sh"
LOG = HOOKS / "posttooluse_log_tool.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None
    or shutil.which("jq") is None
    or shutil.which("openssl") is None
    or not hasattr(os, "mkfifo"),
    reason="needs git, jq, openssl and FIFOs",
)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}
# Well inside hooks.json's 30 seconds: each stalled read is stopped after 5.
LIMIT_S = 20


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def fresh_marker(project: Path) -> Path:
    claude = project / ".claude"
    claude.mkdir(exist_ok=True)
    now = int(time.time())
    marker = claude / "checkpoint.ok"
    marker.write_text(
        json.dumps({"checkpoint_id": "c1", "created_at": now, "expires_at": now + 600})
    )
    return marker


def run(
    hook: Path, project: Path, payload: dict[str, Any]
) -> tuple[subprocess.CompletedProcess[str], float]:
    """The hook as Claude Code starts it; returns it and its time."""
    start = time.monotonic()
    result = subprocess.run(
        ["/bin/sh", "-c", str(hook)],
        input=json.dumps({"cwd": str(project), "tool_use_id": "toolu_x", **payload}),
        capture_output=True,
        text=True,
        cwd=project,
        env={
            **os.environ,
            **GIT_ENV,
            "CLAUDE_PROJECT_DIR": str(project),
            # A key: without one the log hook writes unsigned lines and says so
            "AUDIT_HMAC_KEY": "git-bound-test-key",
        },
        timeout=60,
    )
    return result, time.monotonic() - start


@pytest.fixture
def stalled(tmp_path: Path) -> Path:
    """A repository whose own configuration includes a FIFO no one writes."""
    project = tmp_path / "proj"
    project.mkdir()
    git(project, "init", "-q")
    (project / "a.txt").write_text("a\n")
    git(project, "add", "a.txt")
    git(project, "commit", "-q", "-m", "init")
    os.mkfifo(project / ".git" / "inc.fifo")
    git(project, "config", "include.path", "inc.fifo")
    return project


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Write", {"file_path": "x.txt", "content": "x"}),
        ("Bash", {"command": "rm -rf src"}),
        ("Bash", {"command": "git status"}),
        ("Bash", {"command": "git stash create"}),
    ],
)
def test_a_stalled_git_blocks_the_call_in_time(
    stalled: Path, tool: str, tool_input: dict[str, Any]
) -> None:
    marker = fresh_marker(stalled)
    result, took = run(
        PRE,
        stalled,
        {"tool_name": tool, "tool_input": tool_input, "permission_mode": "default"},
    )
    assert took < LIMIT_S, took
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith("R407 SAFETY_CHECK_FAILED: "), result.stderr
    assert "did not say in time" in result.stderr
    assert marker.exists()


def test_a_read_that_answers_is_unchanged(stalled: Path) -> None:
    """Control: the same repository without the include asks as before."""
    config = stalled / ".git" / "config"
    text = config.read_text()
    assert "\tpath = inc.fifo\n" in text
    config.write_text(text.replace("[include]\n\tpath = inc.fifo\n", ""))
    fresh_marker(stalled)
    result, took = run(
        PRE,
        stalled,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "x.txt", "content": "x"},
            "permission_mode": "default",
        },
    )
    assert took < 5
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == (
        "ask"
    )


@pytest.mark.skipif(not os.path.exists("/dev/ptmx"), reason="needs /dev/ptmx")
def test_a_shipped_git_directory_that_includes_a_terminal_authorises_nothing(
    tmp_path: Path,
) -> None:
    """The verifier's clone: .claude holds HEAD, objects/, refs/ and a
    config that includes /dev/ptmx. The marker's git directory cannot be
    asked: F501, in time (before: no verdict, past 30 seconds)."""
    project = tmp_path / "proj"
    project.mkdir()
    git(project, "init", "-q")
    claude = project / ".claude"
    (claude / "objects").mkdir(parents=True)
    (claude / "refs").mkdir()
    (claude / "HEAD").write_text("ref: refs/heads/main\n")
    (claude / "config").write_text("[include]\n\tpath = /dev/ptmx\n")
    fresh_marker(project)
    result, took = run(
        PRE,
        project,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "x.txt", "content": "x"},
            "permission_mode": "bypassPermissions",
        },
    )
    assert took < LIMIT_S, took
    assert result.returncode == 2, result.stdout
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), result.stderr
    assert "did not say in time" in result.stderr


def test_the_take_hook_writes_no_marker_in_time(stalled: Path) -> None:
    result, took = run(
        TAKE,
        stalled,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git stash create"},
            "tool_response": {"stdout": ""},
        },
    )
    assert took < LIMIT_S, took
    assert result.returncode == 0
    assert not (stalled / ".claude" / "checkpoint.ok").exists()


def test_the_log_hook_logs_the_call_and_says_why_it_kept_no_anchor(
    stalled: Path,
) -> None:
    result, took = run(
        LOG,
        stalled,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "a.txt"},
        },
    )
    assert took < LIMIT_S, took
    assert result.returncode == 1
    assert "did not say in time" in result.stderr
    lines = (stalled / ".claude" / "audit.log").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["tool"] == "Read"


@pytest.mark.parametrize("hook", [PRE, TAKE, LOG])
@pytest.mark.parametrize("kind", ["fifo", "ptmx"])
def test_a_settings_file_that_waits_for_a_writer_is_unreadable(
    tmp_path: Path, hook: Path, kind: str
) -> None:
    """A FIFO, or a link to /dev/ptmx, at .claude/settings.json: the
    pre-tool-use hook refuses every call (R407), the take hook writes no
    marker and the log hook no line, each at once."""
    if kind == "ptmx" and not os.path.exists("/dev/ptmx"):
        pytest.skip("needs /dev/ptmx")
    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    git(project, "init", "-q")
    settings = project / ".claude" / "settings.json"
    if kind == "fifo":
        os.mkfifo(settings)
    else:
        settings.symlink_to("/dev/ptmx")
    payload: dict[str, Any] = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git stash create"},
        "tool_response": {"stdout": ""},
        "permission_mode": "default",
    }
    result, took = run(hook, project, payload)
    assert took < 5, took
    if hook == PRE:
        assert result.returncode == 2
        assert result.stderr.startswith("R407 SAFETY_CHECK_FAILED: "), result.stderr
        assert "settings.json (unreadable)" in result.stderr
    elif hook == TAKE:
        assert result.returncode == 0
        assert not (project / ".claude" / "checkpoint.ok").exists()
    else:
        assert result.returncode == 1
        assert not (project / ".claude" / "audit.log").exists()


def test_the_three_hooks_bound_their_reads_alike() -> None:
    """One bounded runner, in the block the three hooks share; every git
    the hooks run goes through it."""
    for path in (PRE, TAKE, LOG):
        text = path.read_text(encoding="utf-8")
        start = text.index("# BEGIN hook-environment")
        end = text.index("# END hook-environment")
        assert "bounded() {" in text[start:end], path.name
        body = text[end:]
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            words = stripped.replace("(", " ").replace("$", " ").split()
            for i, word in enumerate(words):
                if (
                    word == "git"
                    and i + 1 < len(words)
                    and words[i + 1].startswith("-")
                ):
                    assert "bounded git" in stripped or stripped.startswith(
                        ("hgit", "GIT_NO_LAZY_FETCH=1 bounded")
                    ), (path.name, stripped)


@pytest.mark.parametrize("kind", ["fifo", "ptmx"])
def test_the_sdk_reads_such_a_settings_file_as_unreadable(
    tmp_path: Path, kind: str
) -> None:
    """The SDK adapter's reading of the same file (every call refused with
    R407 while it is unreadable), in a process of its own so that a read
    that waits fails the test instead of holding it."""
    if kind == "ptmx" and not os.path.exists("/dev/ptmx"):
        pytest.skip("needs /dev/ptmx")
    (tmp_path / ".claude").mkdir()
    settings = tmp_path / ".claude" / "settings.json"
    if kind == "fifo":
        os.mkfifo(settings)
    else:
        settings.symlink_to("/dev/ptmx")
    code = (
        "import sys\n"
        "from grounded_agency.utils.project_settings import refused_project_env\n"
        "print(refused_project_env(sys.argv[1], None))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=20,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['.claude/settings.json (unreadable)']"


# ---------------------------------------------------------------------------
# The rollback skill's command hook bounds its git calls the same way (#145)
# ---------------------------------------------------------------------------

ROLLBACK_SKILL = ROOT / "skills" / "rollback" / "SKILL.md"
SHELLS = [shell for shell in ("sh", "bash") if shutil.which(shell)]


def rollback_hook() -> str:
    """The rollback skill's PreToolUse command hook on Bash, as Claude Code
    registers it from the skill's frontmatter."""
    import yaml

    text = ROLLBACK_SKILL.read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---\n", 2)[1])
    (command,) = [
        hook["command"]
        for group in front["hooks"]["PreToolUse"]
        if group.get("matcher") == "Bash"
        for hook in group["hooks"]
        if hook["type"] == "command"
    ]
    assert isinstance(command, str)
    return command


def run_rollback_hook(
    shell: str, project: Path, cwd: Path, command: str
) -> tuple[int | None, str, float]:
    """The hook under `shell`, in a process group of its own, so that a hook
    that waits on git is stopped with every git it started; returns its
    status (None when it gave no verdict within LIMIT_S), its stderr and its
    time."""
    import signal

    start = time.monotonic()
    proc = subprocess.Popen(
        [shell, "-c", rollback_hook()],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=project,
        env={
            **os.environ,
            **GIT_ENV,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "CLAUDE_PROJECT_DIR": str(project),
        },
        start_new_session=True,
    )
    payload = json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(cwd),
        }
    )
    try:
        _, err = proc.communicate(payload, timeout=LIMIT_S)
        status: int | None = proc.returncode
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        _, err = proc.communicate()
        status = None
    return status, err, time.monotonic() - start


def recorded_checkpoint(project: Path) -> str:
    """A checkpoint as the plugin takes it: `git stash create`, its commit
    entered under <git dir>/acs/checkpoints/commits/ with its HMAC."""
    from tests.conftest import enter_checkpoint_commit

    git(project, "init", "-q")
    (project / "a.txt").write_text("one\n")
    git(project, "add", "a.txt")
    git(project, "commit", "-q", "-m", "first")
    (project / "a.txt").write_text("two\n")
    sha = git(project, "stash", "create", "checkpoint:x")
    enter_checkpoint_commit(project / ".git", sha)
    return sha


def include_that_waits(repo: Path, kind: str) -> None:
    """Make the repository's own configuration include a file that holds a
    read until someone writes: a FIFO, or the terminal /dev/ptmx."""
    if kind == "fifo":
        os.mkfifo(repo / ".git" / "inc.fifo")
        target = "inc.fifo"
    else:
        target = "/dev/ptmx"
    with (repo / ".git" / "config").open("a", encoding="utf-8") as config:
        config.write(f"[include]\n\tpath = {target}\n")


@pytest.mark.skipif(not SHELLS, reason="needs sh or bash")
@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("kind", ["fifo", "ptmx"])
def test_the_rollback_hook_refuses_a_restore_in_time_when_git_stalls(
    tmp_path: Path, shell: str, kind: str
) -> None:
    """The project's git directory cannot be asked: the restore is refused
    (F503, naming the stall), within LIMIT_S (before: no verdict until the
    hook's 30-second timeout)."""
    if kind == "ptmx" and not os.path.exists("/dev/ptmx"):
        pytest.skip("needs /dev/ptmx")
    project = tmp_path / "proj"
    project.mkdir()
    sha = recorded_checkpoint(project)
    include_that_waits(project, kind)
    status, err, took = run_rollback_hook(
        shell, project, project, f"git stash apply {sha}"
    )
    assert status == 2, (status, err, took)
    assert err.startswith("F503 ROLLBACK_FAILED: "), err
    # The refusal names the stall, not a missing checkpoint: the
    # checkpoint was recorded.
    assert "git did not answer within 5 seconds" in err, err
    assert "restores no checkpoint" not in err, err
    assert took < LIMIT_S, took


@pytest.mark.skipif(not SHELLS, reason="needs sh or bash")
@pytest.mark.parametrize("shell", SHELLS)
def test_the_rollback_hook_bounds_its_read_of_the_calls_directory(
    tmp_path: Path, shell: str
) -> None:
    """The second git call, for the call's directory, is bounded too: a
    call whose cwd is a repository that stalls is refused in time."""
    project = tmp_path / "proj"
    project.mkdir()
    sha = recorded_checkpoint(project)
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q")
    include_that_waits(other, "fifo")
    status, err, took = run_rollback_hook(
        shell, project, other, f"git stash apply {sha}"
    )
    assert status == 2, (status, err, took)
    assert err.startswith("F503 ROLLBACK_FAILED: "), err
    # The refusal names the stall, not a missing checkpoint: the
    # checkpoint was recorded.
    assert "git did not answer within 5 seconds" in err, err
    assert "restores no checkpoint" not in err, err
    assert took < LIMIT_S, took


@pytest.mark.skipif(not SHELLS, reason="needs sh or bash")
@pytest.mark.parametrize("shell", SHELLS)
def test_the_rollback_hook_accepts_a_recorded_restore_at_once(
    tmp_path: Path, shell: str
) -> None:
    """Control: without the include the recorded restore is allowed, and
    the bound adds no wait (the watchdog holds no output pipe)."""
    project = tmp_path / "proj"
    project.mkdir()
    sha = recorded_checkpoint(project)
    status, err, took = run_rollback_hook(
        shell, project, project, f"git stash apply {sha}"
    )
    assert status == 0, (status, err)
    assert took < 4, took


def test_every_git_the_rollback_hook_runs_is_bounded() -> None:
    """One git command line in the hook, inside rb_git; every git call goes
    through rb_git."""
    hook = rollback_hook()
    # The jq program the hook embeds names git as text it reads, not as a
    # program it runs.
    start = hook.index("cat <<'JQ'")
    end = hook.index("\nJQ\n", start)
    code = hook[:start] + hook[end:]
    runs = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("printf "):
            continue
        if re.search(r"(^|[\s;&|($])git(\s|$)", stripped):
            runs.append(stripped)
    assert runs == [
        'exec git -c core.fsmonitor=false -c core.hooksPath=/dev/null "$@"'
    ], runs
    assert "GIT_NO_LAZY_FETCH=1" in hook
    assert hook.count("rb_git -C ") == 2
    assert "$G " not in hook
