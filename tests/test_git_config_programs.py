"""git commands the layers let pass run no program the repository names
(STANDARD 1.2.0 sections 5.18.3, 5.18.8; security round 3, batch 1).

A repository delivered with its ``.git`` (an archive, a copied checkout)
brings its own configuration and hooks, and one approved `git config
core.fsmonitor ./x` writes such configuration: ``core.fsmonitor`` runs when
`git status`, `git diff` or `git stash create` refreshes the index, a
textconv driver when `git log -p`, `git show` or `git diff` shows a diff, a
clean filter when a changed file is hashed, and a ``post-index-change`` hook
when `git status` writes the index. Where the repository's own configuration
(local and worktree scopes, with the files they include) names such a
program, or its hooks directory holds that hook, the plugin's hook and the
SDK mapper gate every git read and restore, and `git stash create` needs
approval (the hook) or the worst case beside its checkpoint (the mapper).
The user's own configuration (global, system) is not repository content and
gates nothing. The take hook's and the recorder's clean-tree check run with
the repository's filters turned off.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.capabilities import mapper as mapper_module
from grounded_agency.capabilities.mapper import ToolCapabilityMapper
from grounded_agency.hooks import skill_tracker
from tests.conftest import enter_checkpoint_commit

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
TAKE = ROOT / "hooks" / "posttooluse_take_checkpoint.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None
    or shutil.which("bash") is None
    or shutil.which("jq") is None
    or shutil.which("openssl") is None,
    reason="needs git, bash, jq and openssl",
)

READS = [
    "git status",
    "git diff",
    "git log -p -1",
    "git show",
    "git ls-files",
    "git rev-parse HEAD",
    "git stash list",
    "git stash show",
]


def env_for(home: Path) -> dict[str, str]:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
    }


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME of the test's own, so the user's configuration is known."""
    path = tmp_path / "home"
    path.mkdir()
    for key, value in env_for(path).items():
        monkeypatch.setenv(key, value)
    return path


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def sentinel_script(path: Path, sentinel: Path, passthrough: bool = False) -> Path:
    """A program that appends a line to ``sentinel`` (and copies its input
    through, as a filter or textconv would)."""
    body = f'#!/bin/sh\necho ran >> "{sentinel}"\n'
    body += 'cat "$@"\n' if passthrough else "exit 1\n"
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def runs(sentinel: Path) -> int:
    return len(sentinel.read_text().splitlines()) if sentinel.exists() else 0


def run_hook(
    hook: Path, payload: dict[str, Any], project: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=60,
    )


def bash(command: str, cwd: Path, mode: str) -> dict[str, Any]:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
        "permission_mode": mode,
        "tool_use_id": "toolu_x",
    }


def base_repository(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / ".gitattributes").write_text("*.txt diff=t filter=f\n")
    (path / "a.txt").write_text("one\n")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "one")
    (path / "a.txt").write_text("two\n")
    return path


def delivered(tmp_path: Path, configure: dict[str, str]) -> tuple[Path, Path]:
    """A repository as an archive delivers it: its .git configured with
    ``configure`` (values may name ``{prog}``, a program writing the
    sentinel), put in a tar archive and extracted elsewhere."""
    sentinel = tmp_path / "sentinel"
    source = base_repository(tmp_path / "source")
    prog = sentinel_script(source / ".prog", sentinel, passthrough=True)
    for key, value in configure.items():
        git(source, "config", key, value.format(prog="./.prog"))
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tar:
        tar.add(source, arcname="proj")
    data.seek(0)
    target = tmp_path / "delivered"
    target.mkdir()
    with tarfile.open(fileobj=data) as tar:
        tar.extractall(target, filter="tar")
    shutil.rmtree(source)
    assert prog.name == ".prog"
    return target / "proj", sentinel


CONFIGS = {
    "fsmonitor": {"core.fsmonitor": "{prog}"},
    "textconv": {"diff.t.textconv": "{prog}"},
    "clean filter": {"filter.f.clean": "{prog}"},
    "external diff": {"diff.external": "{prog}"},
    "merge driver": {"merge.m.driver": "{prog}"},
    "signature program": {"gpg.program": "{prog}"},
    "pager": {"core.pager": "{prog}"},
}


class TestTheFixture:
    def test_the_delivered_config_runs_its_programs(
        self, home: Path, tmp_path: Path
    ) -> None:
        project, sentinel = delivered(
            tmp_path, {"core.fsmonitor": "{prog}", "diff.t.textconv": "{prog}"}
        )
        git(project, "status")
        after_status = runs(sentinel)
        assert after_status >= 1
        git(project, "log", "-p", "-1")
        assert runs(sentinel) > after_status

    def test_a_post_index_change_hook_runs_on_git_status(
        self, home: Path, tmp_path: Path
    ) -> None:
        project = base_repository(tmp_path / "proj")
        sentinel = tmp_path / "sentinel"
        sentinel_script(project / ".git" / "hooks" / "post-index-change", sentinel)
        os.utime(project / "a.txt", (1_000_000_000, 1_000_000_000))
        git(project, "status")
        assert runs(sentinel) >= 1


class TestPluginHook:
    @pytest.mark.parametrize("config", CONFIGS)
    @pytest.mark.parametrize("command", READS)
    def test_a_read_is_gated_and_runs_nothing(
        self, home: Path, tmp_path: Path, config: str, command: str
    ) -> None:
        project, sentinel = delivered(tmp_path, CONFIGS[config])
        result = run_hook(PRE, bash(command, project, "bypassPermissions"), project)
        assert result.returncode == 2, (config, command, result.stdout)
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        assert runs(sentinel) == 0

    def test_git_stash_create_is_put_to_a_person_without_a_marker(
        self, home: Path, tmp_path: Path
    ) -> None:
        project, sentinel = delivered(tmp_path, CONFIGS["fsmonitor"])
        blocked = run_hook(
            PRE, bash("git stash create", project, "bypassPermissions"), project
        )
        assert blocked.returncode == 2
        assert blocked.stderr.startswith("F502 APPROVAL_REQUIRED: ")
        asked = run_hook(PRE, bash("git stash create", project, "default"), project)
        assert asked.returncode == 0, asked.stderr
        decision = json.loads(asked.stdout)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "ask"
        assert "configuration" in decision["permissionDecisionReason"]
        assert not (project / ".claude" / "checkpoints" / "used").exists()
        assert runs(sentinel) == 0

    def test_a_recorded_restore_needs_a_checkpoint(
        self, home: Path, tmp_path: Path
    ) -> None:
        project, _ = delivered(tmp_path, CONFIGS["clean filter"])
        commit = "0123456789abcdef0123456789abcdef01234567"
        enter_checkpoint_commit(project / ".git", commit)
        result = run_hook(
            PRE,
            bash(f"git stash apply {commit}", project, "bypassPermissions"),
            project,
        )
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")

    def test_an_included_file_counts(self, home: Path, tmp_path: Path) -> None:
        project = base_repository(tmp_path / "proj")
        (project / "inc.cfg").write_text('[core]\n\tfsmonitor = "./x"\n')
        git(project, "config", "include.path", "../inc.cfg")
        result = run_hook(
            PRE, bash("git status", project, "bypassPermissions"), project
        )
        assert result.returncode == 2

    def test_a_post_index_change_hook_counts(self, home: Path, tmp_path: Path) -> None:
        project = base_repository(tmp_path / "proj")
        sentinel = tmp_path / "sentinel"
        sentinel_script(project / ".git" / "hooks" / "post-index-change", sentinel)
        result = run_hook(
            PRE, bash("git status", project, "bypassPermissions"), project
        )
        assert result.returncode == 2
        assert runs(sentinel) == 0

    @pytest.mark.parametrize("value", ["true", "false", "yes", "0"])
    def test_git_s_own_fsmonitor_gates_nothing(
        self, home: Path, tmp_path: Path, value: str
    ) -> None:
        project = base_repository(tmp_path / "proj")
        git(project, "config", "core.fsmonitor", value)
        result = run_hook(
            PRE, bash("git status", project, "bypassPermissions"), project
        )
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")

    def test_the_users_own_configuration_gates_nothing(
        self, home: Path, tmp_path: Path
    ) -> None:
        git(tmp_path, "config", "--global", "diff.t.textconv", "cat")
        git(tmp_path, "config", "--global", "filter.f.clean", "cat")
        project = base_repository(tmp_path / "proj")
        for command in ("git status", "git log -p -1", "git stash create"):
            result = run_hook(PRE, bash(command, project, "bypassPermissions"), project)
            assert (result.returncode, result.stderr) == (0, ""), command


class TestSdkMapper:
    @pytest.mark.parametrize("config", CONFIGS)
    def test_a_read_takes_the_worst_case(
        self, home: Path, tmp_path: Path, config: str
    ) -> None:
        project, sentinel = delivered(tmp_path, CONFIGS[config])
        classify = ToolCapabilityMapper()
        for command in READS:
            mapping = classify.map_tool("Bash", {"command": command}, str(project))
            assert mapping.capabilities == ("mutate", "send"), (config, command)
        assert runs(sentinel) == 0

    def test_git_stash_create_is_a_checkpoint_with_the_worst_case(
        self, home: Path, tmp_path: Path
    ) -> None:
        project, _ = delivered(tmp_path, CONFIGS["fsmonitor"])
        mapping = ToolCapabilityMapper().map_tool(
            "Bash", {"command": "git stash create"}, str(project)
        )
        assert mapping.capabilities == ("checkpoint", "execute", "send")
        assert mapping.requires_checkpoint and mapping.requires_approval

    def test_a_recorded_restore_is_a_gated_mutation(
        self, home: Path, tmp_path: Path
    ) -> None:
        project, _ = delivered(tmp_path, CONFIGS["merge driver"])
        classify = ToolCapabilityMapper()
        classify.is_checkpoint_commit = lambda commit: True
        commit = "0123456789abcdef0123456789abcdef01234567"
        mapping = classify.map_tool(
            "Bash", {"command": f"git stash apply {commit}"}, str(project)
        )
        assert mapping.capability_id == "mutate"
        assert mapping.requires_checkpoint and mapping.requires_approval

    def test_the_lookup_answers_as_the_hook_does(
        self, home: Path, tmp_path: Path
    ) -> None:
        delivered_project, _ = delivered(tmp_path / "a", CONFIGS["textconv"])
        assert mapper_module.git_config_may_run(str(delivered_project))
        plain = base_repository(tmp_path / "plain")
        assert not mapper_module.git_config_may_run(str(plain))
        git(plain, "config", "core.fsmonitor", "true")
        assert not mapper_module.git_config_may_run(str(plain))
        sentinel_script(plain / ".git" / "hooks" / "post-index-change", tmp_path / "s")
        assert mapper_module.git_config_may_run(str(plain))
        assert not mapper_module.git_config_may_run(str(tmp_path / "nothing-here"))

    def test_in_a_plain_repository_reads_still_observe(
        self, home: Path, tmp_path: Path
    ) -> None:
        git(tmp_path, "config", "--global", "diff.t.textconv", "cat")
        project = base_repository(tmp_path / "proj")
        classify = ToolCapabilityMapper()
        for command in READS:
            mapping = classify.map_tool("Bash", {"command": command}, str(project))
            assert mapping.capabilities == ("observe",), command
        mapping = classify.map_tool(
            "Bash", {"command": "git stash create"}, str(project)
        )
        assert mapping.capabilities == ("checkpoint",)

    def test_a_failed_lookup_is_a_yes(self, home: Path, tmp_path: Path) -> None:
        classify = ToolCapabilityMapper()

        def broken(cwd: str | None) -> bool:
            raise RuntimeError("no")

        classify.git_config_may_run = broken
        project = base_repository(tmp_path / "proj")
        mapping = classify.map_tool("Bash", {"command": "git status"}, str(project))
        assert mapping.capabilities == ("mutate", "send")


class TestCleanTreeCheck:
    """The take hook and the SDK recorder check that a tree is clean before
    they write a marker restoring HEAD: with the repository's filters off."""

    @pytest.fixture
    def clean(self, home: Path, tmp_path: Path) -> tuple[Path, Path]:
        project = base_repository(tmp_path / "proj")
        git(project, "checkout", "--", "a.txt")
        sentinel = tmp_path / "sentinel"
        prog = sentinel_script(tmp_path / "prog", sentinel, passthrough=True)
        git(project, "config", "filter.f.clean", str(prog))
        # Changed times, the same content: git hashes the file again.
        os.utime(project / "a.txt", (1_000_000_000, 1_000_000_000))
        return project, sentinel

    def test_the_take_hook_runs_no_filter_and_writes_the_marker(
        self, clean: tuple[Path, Path]
    ) -> None:
        project, sentinel = clean
        result = run_hook(
            TAKE,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git stash create"},
                "tool_response": {"stdout": ""},
                "cwd": str(project),
            },
            project,
        )
        assert result.returncode == 0
        assert runs(sentinel) == 0
        marker = json.loads((project / ".claude" / "checkpoint.ok").read_text())
        assert marker["commit"] == "HEAD"

    def test_the_recorder_runs_no_filter(self, clean: tuple[Path, Path]) -> None:
        project, sentinel = clean
        assert skill_tracker._tree_is_head(str(project))
        assert runs(sentinel) == 0

    def test_a_changed_tree_still_writes_no_marker(
        self, clean: tuple[Path, Path]
    ) -> None:
        project, sentinel = clean
        (project / "a.txt").write_text("three\n")
        assert not skill_tracker._tree_is_head(str(project))
        time.sleep(0)
        result = run_hook(
            TAKE,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git stash create"},
                "tool_response": {"stdout": ""},
                "cwd": str(project),
            },
            project,
        )
        assert result.returncode == 0
        assert not (project / ".claude" / "checkpoint.ok").exists()
        assert runs(sentinel) == 0
