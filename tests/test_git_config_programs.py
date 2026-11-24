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
gates nothing a read runs. The take hook's and the recorder's clean-tree
check run with the repository's filters turned off.

Security round 5, batch 2: a filter's smudge or process command in any
scope runs when git writes the work tree, and git-lfs's, which `git lfs
install` writes to the user's configuration, asks the LFS server the
repository's `.lfsconfig` names for each object its store lacks, sending
the object's id. A git change that writes the tree (`git reset`, `git
checkout --`, `git stash`) takes the worst case in the SDK mapper, and a
restore of a recorded checkpoint the worst case there and a gated `mutate`
in the plugin's hook, wherever one is configured (but the two commands `git
lfs install --skip-smudge` writes, which ask no server).
"""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import tarfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.capabilities import mapper as mapper_module
from grounded_agency.capabilities.mapper import ToolCapabilityMapper
from grounded_agency.hooks import skill_tracker
from tests.conftest import enter_checkpoint_commit, pre_tool_use

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
    """The environment with ``home`` as the user's: its ``.gitconfig`` is the
    global configuration (not the empty one tests/conftest.py names)."""
    return {
        **{k: v for k, v in os.environ.items() if k != "GIT_CONFIG_GLOBAL"},
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
    monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
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
        assert mapping.capabilities == ("checkpoint", "execute", "mutate", "send")
        assert mapping.requires_checkpoint and mapping.requires_approval

    def test_a_recorded_restore_takes_the_worst_case(
        self, home: Path, tmp_path: Path
    ) -> None:
        """The program it runs may send anywhere: `send` beside `mutate`,
        so a destination policy refuses it (it was `mutate` alone)."""
        project, _ = delivered(tmp_path, CONFIGS["merge driver"])
        classify = ToolCapabilityMapper()
        classify.is_checkpoint_commit = lambda commit: True
        commit = "0123456789abcdef0123456789abcdef01234567"
        mapping = classify.map_tool(
            "Bash", {"command": f"git stash apply {commit}"}, str(project)
        )
        assert mapping.capabilities == ("mutate", "send")
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


# What `git lfs install` writes to the user's configuration, and what `git
# lfs install --skip-smudge` writes (the smudge and process commands then
# write the pointer and ask no server).
LFS_FILTER = {
    "filter.lfs.clean": "git-lfs clean -- %f",
    "filter.lfs.smudge": "git-lfs smudge -- %f",
    "filter.lfs.process": "git-lfs filter-process",
    "filter.lfs.required": "true",
}
LFS_SKIP_SMUDGE = {
    **LFS_FILTER,
    "filter.lfs.smudge": "git-lfs smudge --skip -- %f",
    "filter.lfs.process": "git-lfs filter-process --skip",
}
COMMIT = "0123456789abcdef0123456789abcdef01234567"
# Local changes that write files of the work tree from objects.
TREE_WRITERS = [
    "git reset --hard HEAD",
    "git reset -q HEAD~0",
    "git checkout -- a.txt",
    "git stash push",
    "git stash",
    "git stash pop",
    f"git stash apply {'89abcdef' * 5}",
    "ls && git reset --hard",
]


def configure_globally(tmp_path: Path, values: dict[str, str]) -> None:
    for key, value in values.items():
        git(tmp_path, "config", "--global", key, value)


class _LfsServer(BaseHTTPRequestHandler):
    """An LFS server that logs each request and has no object."""

    log: list[str] = []

    def do_POST(self) -> None:  # noqa: N802 (http.server's name)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(length, 65536)).decode("utf-8", "replace")
        type(self).log.append(f"{self.command} {self.path} {body}")
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST  # noqa: N815

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def lfs_server() -> Any:
    _LfsServer.log = []
    server = HTTPServer(("127.0.0.1", 0), _LfsServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def lfs_clone(tmp_path: Path, port: int) -> Path:
    """A clone of a repository whose main branch names git-lfs's filter in
    its .gitattributes and an LFS server in its .lfsconfig, and whose branch
    `data` adds an LFS pointer (an object no store here holds)."""
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / ".gitattributes").write_text(
        "*.bin filter=lfs diff=lfs merge=lfs -text\n"
    )
    (origin / ".lfsconfig").write_text(f"[lfs]\n\turl = http://127.0.0.1:{port}/lfs\n")
    git(origin, "add", ".")
    git(origin, "commit", "-q", "-m", "base")
    git(origin, "checkout", "-q", "-b", "data")
    (origin / "data.bin").write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{'4d7a2146' * 8}\nsize 12\n"
    )
    git(origin, "add", "data.bin")
    git(origin, "commit", "-q", "-m", "data")
    git(origin, "checkout", "-q", "main")
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    return work


class TestFiltersInAnyScope:
    """Security round 5, batch 2: a smudge filter the user's configuration
    names, git-lfs's, sends what the repository chooses."""

    @pytest.mark.skipif(shutil.which("git-lfs") is None, reason="needs git-lfs")
    @pytest.mark.parametrize("skip", [False, True], ids=["smudge", "skip-smudge"])
    def test_git_lfs_asks_the_server_the_repository_names(
        self,
        home: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        lfs_server: HTTPServer,
        skip: bool,
    ) -> None:
        """The premise: with git-lfs's filter in the user's configuration,
        `git reset --hard` to a commit holding a pointer asks the LFS server
        the repository's .lfsconfig names for its object, sending its id;
        with the commands `--skip-smudge` writes, it asks nothing."""
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("NO_PROXY", "*")
        configure_globally(tmp_path, LFS_SKIP_SMUDGE if skip else LFS_FILTER)
        git(tmp_path, "config", "--global", "lfs.transfer.maxretries", "1")
        work = lfs_clone(tmp_path, lfs_server.server_port)
        # As the call is classified: git-lfs has installed no hook yet (the
        # clone checked out no LFS file), so nothing else gates it.
        assert not (work / ".git" / "hooks" / "post-checkout").exists()
        mapping = ToolCapabilityMapper().map_tool(
            "Bash", {"command": "git reset --hard origin/data"}, str(work)
        )
        assert mapping.capabilities == (("mutate",) if skip else ("mutate", "send"))
        subprocess.run(
            ["git", "reset", "--hard", "origin/data"],
            cwd=work,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if skip:
            assert _LfsServer.log == []
            return
        assert _LfsServer.log, "git-lfs asked no server"
        assert _LfsServer.log[0].startswith("POST /lfs/objects/batch ")
        assert "4d7a2146" * 8 in _LfsServer.log[0]

    @pytest.mark.parametrize("command", TREE_WRITERS)
    def test_a_change_that_writes_the_tree_takes_the_worst_case(
        self, home: Path, tmp_path: Path, command: str
    ) -> None:
        """They were `mutate` alone: a destination policy did not see the
        request."""
        configure_globally(tmp_path, LFS_FILTER)
        project = base_repository(tmp_path / "proj")
        mapping = ToolCapabilityMapper().map_tool(
            "Bash", {"command": command}, str(project)
        )
        assert mapping.capabilities == ("mutate", "send"), command
        assert mapping.requires_checkpoint and mapping.requires_approval

    @pytest.mark.parametrize(
        "configure",
        [
            {"filter.lfs.smudge": "git-lfs smudge -- %f"},
            {"filter.lfs.process": "git-lfs filter-process"},
            {"filter.x.smudge": "cat"},
            {"filter.x.smudge": ""},
            {
                "filter.lfs.smudge": "git-lfs smudge --skip -- %f",
                "filter.x.process": "p",
            },
        ],
    )
    def test_a_recorded_restore_takes_the_worst_case(
        self, home: Path, tmp_path: Path, configure: dict[str, str]
    ) -> None:
        """It was `rollback`, needing nothing: a restore of a checkpoint
        holding a pointer the store lacks asked the server."""
        configure_globally(tmp_path, configure)
        project = base_repository(tmp_path / "proj")
        classify = ToolCapabilityMapper()
        classify.is_checkpoint_commit = {COMMIT}.__contains__
        mapping = classify.map_tool(
            "Bash", {"command": f"git stash apply {COMMIT}"}, str(project)
        )
        assert mapping.capabilities == ("mutate", "send")
        assert mapping.requires_checkpoint and mapping.requires_approval

    def test_the_system_and_command_scopes_count(
        self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = base_repository(tmp_path / "proj")
        assert not mapper_module.git_filter_may_run(str(project))
        system = tmp_path / "system.gitconfig"
        system.write_text('[filter "lfs"]\n\tprocess = git-lfs filter-process\n')
        monkeypatch.delenv("GIT_CONFIG_NOSYSTEM")
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(system))
        assert mapper_module.git_filter_may_run(str(project))
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "filter.y.smudge")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "cat")
        assert mapper_module.git_filter_may_run(str(project))

    def test_the_skip_smudge_commands_and_other_changes_stay(
        self, home: Path, tmp_path: Path
    ) -> None:
        """The controls: the commands `--skip-smudge` writes ask no server,
        a clean filter runs on no write, and `git clean`, `git branch -d`,
        a read and `git stash create` write no file from an object."""
        configure_globally(tmp_path, LFS_SKIP_SMUDGE)
        git(tmp_path, "config", "--global", "filter.c.clean", "cat")
        project = base_repository(tmp_path / "proj")
        classify = ToolCapabilityMapper()
        classify.is_checkpoint_commit = {COMMIT}.__contains__
        assert not mapper_module.git_filter_may_run(str(project))
        for command, capabilities in [
            (f"git stash apply {COMMIT}", ("rollback",)),
            ("git reset --hard HEAD", ("mutate",)),
            ("git checkout -- a.txt", ("mutate",)),
        ]:
            mapping = classify.map_tool("Bash", {"command": command}, str(project))
            assert mapping.capabilities == capabilities, command
        configure_globally(tmp_path, LFS_FILTER)
        for command, capabilities in [
            ("git clean -fd", ("mutate",)),
            ("git branch -d x", ("mutate",)),
            ("git status", ("observe",)),
            ("git log -p -1", ("observe",)),
            ("git stash create", ("checkpoint",)),
        ]:
            mapping = classify.map_tool("Bash", {"command": command}, str(project))
            assert mapping.capabilities == capabilities, command

    def test_no_repository_is_a_no_and_a_failed_lookup_a_yes(
        self, home: Path, tmp_path: Path
    ) -> None:
        configure_globally(tmp_path, LFS_FILTER)
        nowhere = tmp_path / "nothing-here"
        nowhere.mkdir()
        assert not mapper_module.git_filter_may_run(str(nowhere))
        project = base_repository(tmp_path / "proj")
        git(tmp_path, "config", "--global", "--unset-all", "filter.lfs.smudge")
        git(tmp_path, "config", "--global", "--unset-all", "filter.lfs.process")
        classify = ToolCapabilityMapper()
        classify.is_checkpoint_commit = {COMMIT}.__contains__

        def broken(cwd: str | None) -> bool:
            raise RuntimeError("no")

        classify.git_filter_may_run = broken
        for command in ("git reset --hard HEAD", f"git stash apply {COMMIT}"):
            mapping = classify.map_tool("Bash", {"command": command}, str(project))
            assert mapping.capabilities == ("mutate", "send"), command

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "command", ["git reset --hard HEAD", f"git stash apply {COMMIT}"]
    )
    async def test_a_destination_policy_refuses_them(
        self, home: Path, tmp_path: Path, ontology_path: str, command: str
    ) -> None:
        """With a policy in force they are refused (F504): the layer cannot
        tell which server the filter asks. Without the filter they pass."""
        project = base_repository(tmp_path / "proj")

        async def decide() -> tuple[str | None, str]:
            adapter = GroundedAgentAdapter(
                GroundedAgentConfig(
                    ontology_path=ontology_path,
                    checkpoint_dir=str(tmp_path / "checkpoints"),
                    approval="off",
                    allowed_destinations=["https://hooks.example.com/*"],
                )
            )
            adapter.checkpoint_tracker.create_checkpoint(
                ["*"], "git stash create", metadata={"commit": COMMIT}
            )
            out = await pre_tool_use(
                adapter, "Bash", {"command": command}, "t1", cwd=str(project)
            )
            specific = out.get("hookSpecificOutput") or {}
            return (
                specific.get("permissionDecision"),
                str(specific.get("permissionDecisionReason")),
            )

        assert (await decide())[0] is None
        configure_globally(tmp_path, LFS_FILTER)
        decision, reason = await decide()
        assert decision == "deny" and reason.startswith("F504 CONSTRAINT_VIOLATED:")

    @pytest.mark.parametrize(
        ("configure", "gated"),
        [
            (LFS_FILTER, True),
            ({"filter.x.smudge": "cat"}, True),
            (LFS_SKIP_SMUDGE, False),
        ],
        ids=["git-lfs", "other smudge", "skip-smudge"],
    )
    def test_the_hook_gates_a_recorded_restore_as_the_mapper_does(
        self, home: Path, tmp_path: Path, configure: dict[str, str], gated: bool
    ) -> None:
        """The plugin's hook let it pass with no checkpoint and no approval,
        in every permission mode."""
        configure_globally(tmp_path, configure)
        project = base_repository(tmp_path / "proj")
        git(project, "checkout", "--", "a.txt")
        enter_checkpoint_commit(project / ".git", COMMIT)
        result = run_hook(
            PRE,
            bash(f"git stash apply {COMMIT}", project, "bypassPermissions"),
            project,
        )
        classify = ToolCapabilityMapper()
        classify.is_checkpoint_commit = {COMMIT}.__contains__
        mapping = classify.map_tool(
            "Bash", {"command": f"git stash apply {COMMIT}"}, str(project)
        )
        if gated:
            assert result.returncode == 2, result.stdout
            assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
            assert mapping.capabilities == ("mutate", "send")
        else:
            assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
            assert mapping.capabilities == ("rollback",)

    def test_the_hook_and_the_mapper_hold_one_pattern_and_one_exception(
        self,
    ) -> None:
        """The two layers must agree: the hook's GIT_SMUDGE_KEYS is the
        mapper's _SMUDGE_CONFIG, and the hook counts as none the same two
        commands as _SKIPPING_SMUDGE."""
        text = PRE.read_text(encoding="utf-8")
        assert f"GIT_SMUDGE_KEYS='{mapper_module._SMUDGE_CONFIG}'" in text
        start = text.index("git_filter_runs() {")
        body = text[start : text.index("\n}\n", start)]
        for command in mapper_module._SKIPPING_SMUDGE:
            assert f'value != "{command.decode()}"' in body
        assert body.count("value != ") == len(mapper_module._SKIPPING_SMUDGE)

    def test_the_hook_reads_a_value_that_is_not_one_line(
        self, home: Path, tmp_path: Path
    ) -> None:
        """A value holding a line break that ends as a skip command is no
        skip command."""
        configure_globally(
            tmp_path,
            {"filter.lfs.process": "p\ngit-lfs filter-process --skip"},
        )
        project = base_repository(tmp_path / "proj")
        git(project, "checkout", "--", "a.txt")
        enter_checkpoint_commit(project / ".git", COMMIT)
        result = run_hook(
            PRE,
            bash(f"git stash apply {COMMIT}", project, "bypassPermissions"),
            project,
        )
        assert result.returncode == 2
        assert mapper_module.git_filter_may_run(str(project))
