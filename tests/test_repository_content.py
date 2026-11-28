"""Repository content does not steer the safety layers (STANDARD 1.2.0
sections 5.18.3, 5.18.6, 5.18.8; spec/SECURITY.md section 5.5).

A repository can ship what git reads as a git directory: a directory that
holds ``HEAD``, ``objects/`` and ``refs/`` (an embedded bare repository),
whose ``config`` names programs git runs (``core.fsmonitor`` when it
refreshes the index, a textconv driver when it shows a diff). It can ship a
symbolic link into the layer's records, and a superproject whose submodules
are partial clones. These tests check, for the plugin's hooks and the SDK:

- the layer's own git commands run no program a repository names, and a
  marker in a git directory the repository may have shipped authorises
  nothing (the pre-tool-use hook's tracked-marker check, the tracker's
  state file);
- a git command the classifier would let pass (a read, ``git stash
  create``) is gated where the git directory may be repository content;
- a git read is gated in a repository with submodules, whose object stores
  a read can fetch into;
- a commit entry is a pass for a restore only when it holds the commit's
  HMAC under the project's key, and a call whose path leads into the
  records through a symbolic link is refused.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.capabilities import mapper as mapper_module
from grounded_agency.capabilities.mapper import ToolCapabilityMapper
from grounded_agency.state import checkpoint_tracker
from tests.conftest import enter_checkpoint_commit

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
TAKE = ROOT / "hooks" / "posttooluse_take_checkpoint.sh"

# The Bash classifier relaxes a call only under a verified sandbox; these
# tests are about the classifier itself (conftest.bash_under_sandbox).
pytestmark = [
    pytest.mark.usefixtures("bash_under_sandbox"),
    pytest.mark.skipif(
        shutil.which("git") is None
        or shutil.which("bash") is None
        or shutil.which("jq") is None
        or shutil.which("openssl") is None,
        reason="needs git, bash, jq and openssl",
    ),
]

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **ENV, **(env or {})},
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    (path / "app.txt").write_text("app\n")
    git(path, "add", "app.txt")
    git(path, "commit", "-q", "-m", "init")
    return path


def run_hook(
    hook: Path, payload: dict[str, Any], project: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **ENV, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=60,
    )


def bash(command: str, cwd: Path, mode: str = "default") -> dict[str, Any]:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
        "permission_mode": mode,
    }


def fresh_marker(project: Path) -> Path:
    claude = project / ".claude"
    claude.mkdir(exist_ok=True)
    now = int(time.time())
    marker = claude / "checkpoint.ok"
    marker.write_text(
        json.dumps({"checkpoint_id": "c1", "created_at": now, "expires_at": now + 600})
    )
    return marker


def embedded_git_dir(
    project: Path, rel: str, sentinels: Path, track: list[str] | None = None
) -> Path:
    """Make ``project/rel`` a git directory as a repository can ship one: two
    commits of a.txt, info/attributes giving every file the diff driver x,
    and a config whose core.fsmonitor and diff.x.textconv touch a file in
    ``sentinels``; with ``track``, an index tracking those files of it. Then
    commit it all to ``project`` as ordinary files."""
    gd = project / rel
    gd.parent.mkdir(parents=True, exist_ok=True)
    git(project, "init", "-q", "--bare", rel)
    work = project.parent / f"work-{gd.name}"
    work.mkdir()
    genv = {"GIT_DIR": str(gd), "GIT_WORK_TREE": str(work)}
    for content in ("one", "two"):
        (work / "a.txt").write_text(content + "\n")
        git(work, "add", "a.txt", env=genv)
        git(work, "commit", "-q", "-m", content, env=genv)
    shutil.rmtree(work)
    (gd / "index").unlink(missing_ok=True)
    (gd / "info").mkdir(exist_ok=True)
    (gd / "info" / "attributes").write_text("* diff=x\n")
    for name in ("objects", "refs"):
        (gd / name / ".keep").touch()
    for key, value in (
        ("core.bare", "false"),
        ("core.worktree", "."),
        ("core.fsmonitor", f"touch {sentinels}/fsmonitor; true"),
        ("diff.x.textconv", f"touch {sentinels}/textconv; cat"),
    ):
        git(project, "config", "-f", str(gd / "config"), key, value)
    if track:
        tenv = {"GIT_DIR": str(gd), "GIT_WORK_TREE": str(gd)}
        git(gd, "-c", "core.fsmonitor=false", "add", "--", *track, env=tenv)
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "ship")
    return gd


@pytest.fixture
def sentinels(tmp_path: Path) -> Path:
    path = tmp_path / "sentinels"
    path.mkdir()
    return path


# ---------------------------------------------------------------------------
# .claude shipped as a git directory
# ---------------------------------------------------------------------------


class TestShippedClaudeGitDir:
    """A repository ships .claude as a git directory whose index tracks
    checkpoint.ok and whose config names an fsmonitor program."""

    def _project(self, tmp_path: Path, sentinels: Path) -> Path:
        project = repo(tmp_path / "proj")
        claude = project / ".claude"
        claude.mkdir()
        (claude / "checkpoint.ok").write_text("{}")
        embedded_git_dir(project, ".claude", sentinels, track=["checkpoint.ok"])
        return project

    def test_the_hook_runs_no_program_and_the_marker_authorises_nothing(
        self, tmp_path: Path, sentinels: Path
    ) -> None:
        project = self._project(tmp_path, sentinels)
        fresh_marker(project)
        result = run_hook(
            PRE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "notes.txt"},
                "cwd": str(project),
                "permission_mode": "default",
            },
            project,
        )
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert "did not make for a work tree" in result.stderr
        assert not (sentinels / "fsmonitor").exists()
        assert (project / ".claude" / "checkpoint.ok").exists()  # not used

    def test_a_shipped_marker_under_a_bare_git_dir_authorises_nothing(
        self, tmp_path: Path, sentinels: Path
    ) -> None:
        """The project tracks a fresh marker, and .claude holds HEAD,
        objects/ and refs/ with no config: git takes .claude for a bare
        repository, which cannot answer for the marker."""
        project = repo(tmp_path / "proj")
        claude = project / ".claude"
        claude.mkdir()
        (claude / "HEAD").write_text("ref: refs/heads/main\n")
        for name in ("objects", "refs"):
            (claude / name).mkdir()
            (claude / name / ".keep").touch()
        fresh_marker(project)
        git(project, "add", "-A")
        git(project, "commit", "-q", "-m", "ship")
        result = run_hook(
            PRE, bash("touch newfile", project, "bypassPermissions"), project
        )
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert (claude / "checkpoint.ok").exists()

    def test_the_trackers_state_file_there_is_not_trusted(
        self, tmp_path: Path, sentinels: Path
    ) -> None:
        project = repo(tmp_path / "proj")
        state = project / ".checkpoints"
        state.mkdir()
        (state / "tracker_state.json").write_text("{}")
        embedded_git_dir(
            project, ".checkpoints", sentinels, track=["tracker_state.json"]
        )
        assert checkpoint_tracker._tracked_by_git(state / "tracker_state.json")
        assert not (sentinels / "fsmonitor").exists()

    def test_an_ordinary_untracked_marker_still_passes(self, tmp_path: Path) -> None:
        project = repo(tmp_path / "proj")
        fresh_marker(project)
        result = run_hook(PRE, bash("touch newfile", project), project)
        assert result.returncode == 0, result.stderr
        assert (
            json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]
            == "ask"
        )
        assert not checkpoint_tracker._tracked_by_git(
            project / ".claude" / "checkpoint.ok"
        )


# ---------------------------------------------------------------------------
# A git command in a git directory the repository ships
# ---------------------------------------------------------------------------

READS = [
    "git status",
    "git ls-files",
    "git log -p",
    "git show",
    "git diff main~1 main",
    "git rev-parse HEAD",
    "git stash list",
    "git stash show -p",
]


class TestEmbeddedGitDir:
    @pytest.fixture
    def evil(self, tmp_path: Path, sentinels: Path) -> tuple[Path, Path]:
        project = repo(tmp_path / "proj")
        gd = embedded_git_dir(project, "vendor/evil.git", sentinels)
        return project, gd

    def test_the_fixture_runs_what_its_config_names(
        self, evil: tuple[Path, Path], sentinels: Path
    ) -> None:
        _, gd = evil
        git(gd, "status")
        assert (sentinels / "fsmonitor").exists()
        git(gd, "log", "-p")
        assert (sentinels / "textconv").exists()

    @pytest.mark.parametrize("command", [*READS, "git stash create"])
    def test_a_git_command_there_is_gated(
        self, evil: tuple[Path, Path], sentinels: Path, command: str
    ) -> None:
        project, gd = evil
        for cwd in (gd, gd / "objects"):
            result = run_hook(PRE, bash(command, cwd, "bypassPermissions"), project)
            assert result.returncode == 2, (command, cwd)
            assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command
            mapping = ToolCapabilityMapper().map_tool(
                "Bash", {"command": command}, str(cwd)
            )
            assert mapping.capabilities == ("mutate", "send"), (command, cwd)
        assert not (sentinels / "fsmonitor").exists()
        assert not (sentinels / "textconv").exists()

    @pytest.mark.parametrize("command", READS)
    def test_in_the_project_they_still_observe(
        self, evil: tuple[Path, Path], command: str
    ) -> None:
        project, _ = evil
        result = run_hook(PRE, bash(command, project, "bypassPermissions"), project)
        assert (result.returncode, result.stdout, result.stderr) == (0, "", ""), command
        mapping = ToolCapabilityMapper().map_tool(
            "Bash", {"command": command}, str(project)
        )
        assert mapping.capabilities == ("observe",), command

    def test_the_mapper_lookups_answer_alike(self, evil: tuple[Path, Path]) -> None:
        project, gd = evil
        assert mapper_module.git_dir_may_be_content(str(gd))
        assert not mapper_module.git_dir_may_be_content(str(project))
        assert not mapper_module.git_dir_may_be_content(str(project.parent))


# ---------------------------------------------------------------------------
# A superproject with a partial-clone submodule
# ---------------------------------------------------------------------------

# file:// for the submodule's remote, in this process and every git it starts.
FILE_OK = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "protocol.file.allow",
    "GIT_CONFIG_VALUE_0": "always",
}


def missing(repository: Path) -> int:
    listed = git(repository, "rev-list", "--objects", "--missing=print", "--all")
    return sum(line.startswith("?") for line in listed.splitlines())


class TestSubmodules:
    @pytest.fixture
    def superproject(self, tmp_path: Path) -> Path:
        """A full clone of a superproject whose submodule `sub` was set up
        with --filter=blob:none from a file:// upstream (a promisor
        remote, as another host would be)."""
        up = tmp_path / "up"
        up.mkdir()
        git(up, "init", "-q", "-b", "main")
        git(up, "config", "uploadpack.allowFilter", "true")
        upstream_commits = []
        for content in ("one", "two", "three"):
            (up / "a.txt").write_text(content + "\n")
            git(up, "add", "a.txt")
            git(up, "commit", "-q", "-m", content)
            upstream_commits.append(git(up, "rev-parse", "HEAD"))
        sup = repo(tmp_path / "super")
        git(sup, "submodule", "add", "-q", up.as_uri(), "sub", env=FILE_OK)
        git(sup, "commit", "-q", "-m", "add sub")
        for commit in upstream_commits[:2]:
            git(sup / "sub", "checkout", "-q", commit)
            git(sup, "add", "sub")
            git(sup, "commit", "-q", "-m", f"sub at {commit}")
        clone = tmp_path / "clone"
        git(tmp_path, "clone", "-q", str(sup), str(clone))
        git(
            clone,
            "submodule",
            "update",
            "-q",
            "--init",
            "--filter=blob:none",
            env=FILE_OK,
        )
        # The superproject itself is no partial clone; its submodule is.
        assert (
            subprocess.run(
                ["git", "config", "--get-regexp", "promisor"],
                cwd=clone,
                capture_output=True,
                timeout=60,
            ).returncode
            == 1
        )
        assert git(clone / "sub", "config", "remote.origin.promisor") == "true"
        return clone

    def test_the_fixture_fetches_into_the_submodule(self, superproject: Path) -> None:
        before = missing(superproject / "sub")
        assert before > 0
        git(superproject, "log", "-p", "--submodule=diff", env=FILE_OK)
        assert missing(superproject / "sub") < before

    @pytest.mark.parametrize(
        "command",
        [
            "git log -p --submodule=diff",
            "git log -p --sub=diff",
            "git diff HEAD~2 --submodule=diff",
            "git show --submodule=diff",
            "git log -p",
            "git status",
            "git stash list",
        ],
    )
    def test_a_git_read_there_is_gated(self, superproject: Path, command: str) -> None:
        result = run_hook(
            PRE, bash(command, superproject, "bypassPermissions"), superproject
        )
        assert result.returncode == 2, command
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command
        mapping = ToolCapabilityMapper().map_tool(
            "Bash", {"command": command}, str(superproject)
        )
        assert mapping.capabilities == ("mutate", "send"), command
        assert mapper_module.git_may_fetch(str(superproject))

    def test_an_uninitialised_gitlink_counts_too(self, tmp_path: Path) -> None:
        """A gitlink in the index is a submodule, initialised or not."""
        project = repo(tmp_path / "proj")
        commit = git(project, "rev-parse", "HEAD")
        git(project, "update-index", "--add", "--cacheinfo", f"160000,{commit},lib")
        result = run_hook(
            PRE, bash("git log -p", project, "bypassPermissions"), project
        )
        assert result.returncode == 2
        assert mapper_module.git_may_fetch(str(project))

    def test_without_submodules_a_read_observes(self, tmp_path: Path) -> None:
        project = repo(tmp_path / "proj")
        result = run_hook(
            PRE, bash("git log -p", project, "bypassPermissions"), project
        )
        assert (result.returncode, result.stderr) == (0, "")
        assert not mapper_module.git_may_fetch(str(project))


# ---------------------------------------------------------------------------
# Commit entries: signed, and no path through a link into the records
# ---------------------------------------------------------------------------

M = "0123456789abcdef0123456789abcdef01234567"


class TestCommitEntries:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        """A project whose take hook has entered one checkpoint, and which
        ships links into its git directory's records."""
        project = repo(tmp_path / "proj")
        (project / "app.txt").write_text("changed\n")
        stash = git(project, "stash", "create")
        taken = run_hook(
            TAKE,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git stash create"},
                "tool_response": {"stdout": stash},
                "cwd": str(project),
            },
            project,
        )
        assert taken.returncode == 0
        assert (project / ".git" / "acs" / "checkpoints" / "commits" / stash).is_file()
        notes = project / "notes"
        notes.mkdir()
        (notes / "todo.md").symlink_to(f"../.git/acs/checkpoints/commits/{M}")
        (notes / "key.md").symlink_to("../.git/acs/checkpoints/key")
        (project / "docs").symlink_to(".git/acs/checkpoints")
        (project / "deep").symlink_to("notes")
        (project / "stash.txt").write_text(stash)
        # The take hook's marker ends (a turn boundary): a restore uses none.
        (project / ".claude" / "checkpoint.ok").unlink()
        return project

    def test_a_signed_entry_restores(self, project: Path) -> None:
        stash = (project / "stash.txt").read_text()
        result = run_hook(
            PRE, bash(f"git stash apply {stash}", project, "bypassPermissions"), project
        )
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")

    @pytest.mark.parametrize("content", ["", "x", "0" * 64])
    def test_a_file_made_there_is_no_entry(self, project: Path, content: str) -> None:
        """What an approved `touch notes/todo.md` or `cp x notes/todo.md`
        leaves through the link: a file with no signature."""
        (project / ".git" / "acs" / "checkpoints" / "commits" / M).write_text(content)
        for mode in ("bypassPermissions", "default"):
            result = run_hook(PRE, bash(f"git stash apply {M}", project, mode), project)
            assert result.returncode == 2, mode
            assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), mode

    def test_an_entry_signed_under_another_key_is_no_entry(self, project: Path) -> None:
        gd = project / ".git"
        enter_checkpoint_commit(gd, M)
        (gd / "acs" / "checkpoints" / "key").write_text("f" * 64)
        result = run_hook(
            PRE, bash(f"git stash apply {M}", project, "bypassPermissions"), project
        )
        assert result.returncode == 2

    @pytest.mark.parametrize(
        "command",
        [
            "touch notes/todo.md",
            "cp README notes/key.md",
            'cat x > "notes/key.md"',
            "touch docs/commits/abc",
            "touch ./deep/../notes/todo.md",
            "touch deep/todo.md",
            "echo k >notes/key.md",
            "cp --target-directory=docs x",
        ],
    )
    def test_a_path_through_a_link_into_the_records_is_refused(
        self, project: Path, command: str
    ) -> None:
        fresh_marker(project)
        result = run_hook(PRE, bash(command, project), project)
        assert result.returncode == 2, command
        assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: "), command
        assert "symbolic link" in result.stderr, command
        assert (project / ".claude" / "checkpoint.ok").exists()

    @pytest.mark.parametrize("path", ["docs/key", "deep/todo.md", "notes/key.md"])
    def test_a_file_tool_through_a_link_is_refused(
        self, project: Path, path: str
    ) -> None:
        fresh_marker(project)
        for absolute in (False, True):
            target = str(project / path) if absolute else path
            result = run_hook(
                PRE,
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": target, "content": "x"},
                    "cwd": str(project),
                    "permission_mode": "default",
                },
                project,
            )
            assert result.returncode == 2, target
            assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: "), target

    def test_a_link_loop_is_refused(self, project: Path) -> None:
        (project / "loop").symlink_to("loop")
        fresh_marker(project)
        result = run_hook(PRE, bash("touch loop", project), project)
        assert result.returncode == 2
        assert result.stderr.startswith("F504 CONSTRAINT_VIOLATED: ")

    def test_a_call_follows_200_links_at_most(self, project: Path) -> None:
        """Each link costs a readlink: a command that names a chain of 40
        links many times is refused once the call has followed 200, rather
        than hold the hook past its time limit."""
        for i in range(40):
            (project / f"l{i}").symlink_to(f"l{i + 1}" if i < 39 else "app.txt")
        fresh_marker(project)
        start = time.monotonic()
        four = run_hook(PRE, bash("touch " + " ".join(["l0"] * 4), project), project)
        assert four.returncode == 0, four.stderr
        six = run_hook(PRE, bash("touch " + " ".join(["l0"] * 6), project), project)
        assert six.returncode == 2
        assert six.stderr.startswith("F504 CONSTRAINT_VIOLATED: ")
        assert "more than 200 in the call" in six.stderr
        assert time.monotonic() - start < 20

    @pytest.mark.parametrize(
        "command", ["touch notes/other.md", "touch app.txt", "cp app.txt notes/"]
    )
    def test_other_paths_pass(self, project: Path, command: str) -> None:
        fresh_marker(project)
        result = run_hook(PRE, bash(command, project), project)
        assert result.returncode == 0, result.stderr
        assert (
            json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]
            == "ask"
        )

    def test_many_words_are_resolved_quickly(self, project: Path) -> None:
        fresh_marker(project)
        command = "touch " + " ".join(f"d{i}/f{i}" for i in range(400))
        assert len(command) <= 4096
        start = time.monotonic()
        result = run_hook(PRE, bash(command, project), project)
        assert result.returncode == 0, result.stderr
        assert time.monotonic() - start < 10

    def test_the_take_hook_enters_nothing_in_a_shipped_git_dir(
        self, tmp_path: Path, sentinels: Path
    ) -> None:
        """A project whose git directory is repository content: no key, no
        entry, no marker naming a commit, and no program run."""
        outer = repo(tmp_path / "outer")
        gd = embedded_git_dir(outer, "vendor/evil.git", sentinels)
        result = run_hook(
            TAKE,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git stash create"},
                "tool_response": {"stdout": M},
                "cwd": str(gd),
            },
            gd,
        )
        assert result.returncode == 0
        assert not (gd / "acs").exists()
        assert not (gd / ".claude" / "checkpoint.ok").exists()
        assert not (sentinels / "fsmonitor").exists()
