"""A checkpoint is taken only by a call classified `checkpoint` where it ran
(security round 5, batch 3, #1; STANDARD 1.2.0 section 5.18.6).

The PreToolUse checks classify `git stash create` in the directory the call
runs in: where the git directory git finds there may be repository content
(a shipped `vendor/evil.git` whose core.worktree names another tree), or the
git the shell runs may be the repository's own, it is the worst case. The
SDK's checkpoint recorder classified it in this process's directory instead,
and the plugin's take hook compared work trees alone, so the stash such a
call printed, a commit of another object store, became a checkpoint that a
later gated call held. Both now take none there.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.capabilities.mapper import ToolCapabilityMapper
from grounded_agency.hooks.skill_tracker import create_checkpoint_recorder
from grounded_agency.state.checkpoint_tracker import CheckpointTracker

ROOT = Path(__file__).resolve().parents[1]
TAKE = ROOT / "hooks" / "posttooluse_take_checkpoint.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None
    or shutil.which("bash") is None
    or shutil.which("jq") is None
    or shutil.which("openssl") is None,
    reason="needs git, bash, jq and openssl",
)

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
STASH = "git stash create"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **ENV},
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "a.txt").write_text("a\n")
    git(path, "add", "a.txt")
    git(path, "commit", "-q", "-m", "init")
    return path


def shipped_git_dir(project: Path, worktree: Path) -> Path:
    """`project/vendor/evil.git`: a copy of another repository's `.git`
    (as an archive or a vendored checkout ships one) whose core.worktree
    is ``worktree``, committed to the project as ordinary files."""
    other = repo(project.parent / "other")
    evil = project / "vendor" / "evil.git"
    # A lock file git's background maintenance holds may come and go while
    # the copy runs; it is no part of the repository
    shutil.copytree(other / ".git", evil, ignore=shutil.ignore_patterns("*.lock"))
    config = str(evil / "config")
    git(project, "config", "-f", config, "core.bare", "false")
    git(project, "config", "-f", config, "core.worktree", str(worktree))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "ship")
    return evil


def stash(cwd: Path) -> str:
    """Run `git stash create` there, as the agent's shell would."""
    return git(cwd, "stash", "create")


def bash_post(cwd: Path | None, printed: str, call: str = "toolu_1") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool_name": "Bash",
        "tool_input": {"command": STASH},
        "tool_response": {"stdout": printed + "\n", "stderr": ""},
        "tool_use_id": call,
    }
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return payload


def take(project: Path, payload: dict[str, Any], path: str | None = None) -> bool:
    """Run the take hook as Claude Code starts it; whether it wrote a
    marker."""
    env = {**os.environ, **ENV, "CLAUDE_PROJECT_DIR": str(project)}
    if path is not None:
        env["PATH"] = path
    result = subprocess.run(
        ["/bin/sh", "-c", str(TAKE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=project,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return (project / ".claude" / "checkpoint.ok").exists()


def record(
    tracker: CheckpointTracker,
    payload: dict[str, Any],
    mapper: ToolCapabilityMapper | None = None,
) -> bool:
    """Run the SDK's checkpoint recorder on the call; whether it took one."""
    recorder = create_checkpoint_recorder(tracker, mapper or ToolCapabilityMapper())
    asyncio.run(recorder(payload, payload.get("tool_use_id"), None))
    return tracker.has_valid_checkpoint()


@pytest.fixture
def outside(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This process runs in a directory that is no repository, as a host's
    may: a git lookup made there finds none."""
    where = tmp_path / "host"
    where.mkdir()
    monkeypatch.chdir(where)
    return where


@pytest.fixture
def tracker(tmp_path: Path) -> CheckpointTracker:
    return CheckpointTracker(checkpoint_dir=str(tmp_path / ".cp"))


class TestAShippedGitDirectory:
    """The verifier's case: the stash prints a commit of the shipped git
    directory's object store."""

    def test_premise_the_stash_prints_a_commit_of_another_store(
        self, tmp_path: Path, outside: Path
    ) -> None:
        project = repo(tmp_path / "proj")
        src = repo(tmp_path / "src")
        (src / "a.txt").write_text("changed\n")
        evil = shipped_git_dir(project, src)
        printed = stash(evil)
        assert len(printed) == 40
        assert git(evil, "rev-parse", "--absolute-git-dir") == str(evil)
        missing = subprocess.run(
            ["git", "cat-file", "-e", printed],
            cwd=project,
            env={**os.environ, **ENV},
            capture_output=True,
            timeout=60,
        )
        assert missing.returncode != 0  # not in the project's object store
        mapper = ToolCapabilityMapper()
        assert mapper.map_tool("Bash", {"command": STASH}, str(evil)).capabilities == (
            "mutate",
            "send",
        )

    def test_the_recorder_takes_none(
        self, tmp_path: Path, outside: Path, tracker: CheckpointTracker
    ) -> None:
        project = repo(tmp_path / "proj")
        src = repo(tmp_path / "src")
        (src / "a.txt").write_text("changed\n")
        evil = shipped_git_dir(project, src)
        assert not record(tracker, bash_post(evil, stash(evil)))
        assert tracker.get_active_checkpoint() is None

    def test_the_recorder_takes_none_for_a_clean_stash_there(
        self, tmp_path: Path, outside: Path, tracker: CheckpointTracker
    ) -> None:
        """Empty output: HEAD would be the shipped repository's."""
        project = repo(tmp_path / "proj")
        src = repo(tmp_path / "src")
        evil = shipped_git_dir(project, src)
        assert not record(tracker, bash_post(evil, ""))

    def test_the_take_hook_writes_no_marker_where_the_tree_is_the_projects(
        self, tmp_path: Path
    ) -> None:
        """core.worktree names the project itself: the work trees agree,
        the git directories do not."""
        project = repo(tmp_path / "proj")
        evil = shipped_git_dir(project, project)
        (project / "a.txt").write_text("project change\n")
        printed = stash(evil)
        assert len(printed) == 40
        assert git(evil, "rev-parse", "--show-toplevel") == str(project)
        assert not take(project, bash_post(evil, printed))
        assert not (
            project / ".git" / "acs" / "checkpoints" / "commits" / printed
        ).exists()

    def test_controls_in_the_project_a_checkpoint_is_taken(
        self, tmp_path: Path, outside: Path, tracker: CheckpointTracker
    ) -> None:
        project = repo(tmp_path / "proj")
        src = repo(tmp_path / "src")
        shipped_git_dir(project, src)
        (project / "a.txt").write_text("project change\n")
        printed = stash(project)
        assert record(tracker, bash_post(project, printed))
        active = tracker.get_active_checkpoint()
        assert active is not None and active.metadata["commit"] == printed
        assert take(project, bash_post(project, printed))
        marker = json.loads((project / ".claude" / "checkpoint.ok").read_text())
        assert marker["commit"] == printed


class TestTheAdaptersRecorder:
    """The recorder wrap_options installs classifies a call where the
    PreToolUse hook did: the input's cwd, else the one that hook kept; a
    call that reports another directory takes none."""

    def _setup(
        self, tmp_path: Path
    ) -> tuple[Path, Path, GroundedAgentAdapter, Any, list[Any]]:
        project = repo(tmp_path / "proj")
        src = repo(tmp_path / "src")
        (src / "a.txt").write_text("changed\n")
        evil = shipped_git_dir(project, src)
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(checkpoint_dir=str(tmp_path / ".cp"), approval="off")
        )
        options = adapter.wrap_options(ClaudeAgentOptions())
        (pre,) = options.hooks["PreToolUse"][-1].hooks
        posts = [h for entry in options.hooks["PostToolUse"] for h in entry.hooks]
        return project, evil, adapter, pre, posts

    async def _call(
        self,
        adapter: GroundedAgentAdapter,
        pre: Any,
        posts: list[Any],
        checked_in: Path,
        post: dict[str, Any],
    ) -> None:
        """A checkpoint to hold, the PreToolUse hook in ``checked_in``,
        then every PostToolUse hook, in order, on ``post``."""
        adapter.create_checkpoint(["*"], "held by the call")
        call = post["tool_use_id"]
        out = await pre(
            {
                "tool_name": "Bash",
                "tool_input": {"command": STASH},
                "cwd": str(checked_in),
                "tool_use_id": call,
            },
            call,
            None,
        )
        decision = out.get("hookSpecificOutput", {}).get("permissionDecision")
        assert decision in (None, "allow"), out
        for hook in posts:
            await hook(post, call, None)

    def test_with_no_cwd_it_classifies_where_the_hook_did(
        self, tmp_path: Path, outside: Path
    ) -> None:
        _, evil, adapter, pre, posts = self._setup(tmp_path)
        printed = stash(evil)
        asyncio.run(self._call(adapter, pre, posts, evil, bash_post(None, printed)))
        assert not adapter.checkpoint_tracker.has_valid_checkpoint()

    def test_with_its_cwd_it_takes_none(self, tmp_path: Path, outside: Path) -> None:
        _, evil, adapter, pre, posts = self._setup(tmp_path)
        printed = stash(evil)
        asyncio.run(self._call(adapter, pre, posts, evil, bash_post(evil, printed)))
        assert not adapter.checkpoint_tracker.has_valid_checkpoint()

    def test_another_cwd_than_the_hooks_takes_none(
        self, tmp_path: Path, outside: Path
    ) -> None:
        project, evil, adapter, pre, posts = self._setup(tmp_path)
        (project / "a.txt").write_text("project change\n")
        printed = stash(project)
        asyncio.run(self._call(adapter, pre, posts, evil, bash_post(project, printed)))
        assert not adapter.checkpoint_tracker.has_valid_checkpoint()

    def test_control_the_project_takes_one(self, tmp_path: Path, outside: Path) -> None:
        project, _, adapter, pre, posts = self._setup(tmp_path)
        (project / "a.txt").write_text("project change\n")
        printed = stash(project)
        asyncio.run(self._call(adapter, pre, posts, project, bash_post(None, printed)))
        active = adapter.checkpoint_tracker.get_active_checkpoint()
        assert active is not None and active.metadata["commit"] == printed


class TestSiblings:
    def test_a_repository_git_on_path_takes_none(
        self, tmp_path: Path, outside: Path, tracker: CheckpointTracker
    ) -> None:
        """The git the agent's shell runs is the repository's (a relative
        PATH entry): it prints what it likes."""
        project = repo(tmp_path / "proj")
        fake = project / "node_modules" / ".bin" / "git"
        fake.parent.mkdir(parents=True)
        fake.write_text("#!/bin/sh\necho 0123456789abcdef0123456789abcdef01234567\n")
        fake.chmod(0o755)
        system = os.environ.get("PATH", "/usr/bin:/bin")
        path = f"node_modules/.bin:{system}"
        printed = "0123456789abcdef0123456789abcdef01234567"
        mapper = ToolCapabilityMapper()
        mapper.command_path = path
        mapper.project_dir = str(project)
        assert not record(tracker, bash_post(project, printed), mapper)
        assert not take(project, bash_post(project, printed), path)
        # Control: the system's git, the same call.
        (project / "a.txt").write_text("project change\n")
        real = stash(project)
        mapper.command_path = system
        assert record(tracker, bash_post(project, real), mapper)
        assert take(project, bash_post(project, real), system)

    def test_another_git_dir_with_the_projects_work_tree_takes_no_marker(
        self, tmp_path: Path
    ) -> None:
        """A nested repository made for a work tree (`sub/.git`) whose
        core.worktree is the project: the work trees agree, but the commit
        is in sub/.git's store."""
        project = repo(tmp_path / "proj")
        sub = project / "sub"
        sub.mkdir()
        git(sub, "init", "-q", "-b", "main")
        git(sub, "config", "core.worktree", str(project))
        git(sub, "add", "--", ":/a.txt")
        git(sub, "commit", "-q", "-m", "s")
        (project / "a.txt").write_text("project change\n")
        printed = stash(sub)
        assert len(printed) == 40
        assert git(sub, "rev-parse", "--show-toplevel") == str(project)
        assert not take(project, bash_post(sub, printed))
        # Control: from a subdirectory of the project, the same repository.
        (project / "docs").mkdir()
        assert take(project, bash_post(project / "docs", stash(project / "docs")))
