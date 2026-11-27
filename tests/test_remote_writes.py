"""The plugin's typed remote-write tools (grounded_agency/remote_writes.py).

Every remote here is a local bare repository, and gh is a fake program that
records its arguments, its working directory and its environment: no test
reaches a real remote or uses a real credential.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from grounded_agency import remote_writes as rw
from grounded_agency.capabilities import mapper
from grounded_agency.utils.git import SAFE_GIT_OPTIONS, git_dir_is_made

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "grounded_agency" / "remote_writes.py"
HOOK = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
SYSTEM_PYTHON = "/usr/bin/python3"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def git(*args: str, cwd: Path | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GH_"))} | {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return done.stdout.strip()


class Setup:
    """A project with one commit on main, a bare remote recorded as its
    origin, a home directory holding the record, and a directory holding a
    fake gh that logs each call."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.project = base / "project"
        self.remote = base / "remote.git"
        self.home = base / "home"
        self.bin = base / "bin"
        self.log = base / "gh-calls.jsonl"
        self.home.mkdir()
        self.bin.mkdir()
        git("init", "-q", "--bare", "-b", "main", str(self.remote))
        git("init", "-q", "-b", "main", str(self.project))
        (self.project / "a.txt").write_text("a\n")
        git("add", "a.txt", cwd=self.project)
        git("commit", "-q", "-m", "first", cwd=self.project)
        git("remote", "add", "origin", str(self.remote), cwd=self.project)
        gh = self.bin / "gh"
        gh.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            f"with open({str(self.log)!r}, 'a') as f:\n"
            "    f.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(),"
            " 'env': dict(os.environ)}) + '\\n')\n"
            "print('https://github.example/owner/repo/pull/7')\n"
        )
        gh.chmod(0o755)
        path_entries = [str(self.bin)] + [
            d for d in os.environ.get("PATH", "").split(os.pathsep) if d
        ]
        self.path = os.pathsep.join(path_entries)

    def ctx(self) -> rw.Context:
        return rw.Context(
            str(self.project), str(self.home), self.path, (str(self.project),)
        )

    def git_program(self) -> str:
        return rw.find_program("git", self.ctx())

    def record(
        self,
        url: str | None = None,
        github: str | None = None,
        git_program: str | None = None,
    ) -> None:
        repo = rw.find_repository(self.git_program(), self.ctx(), str(self.base))
        self.write_entry(
            repo.top, repo.common_dir, url or str(self.remote), github, git_program
        )

    def write_entry(
        self,
        project: str,
        git_dir: str,
        url: str,
        github: str | None = None,
        git_program: str | None = None,
    ) -> None:
        rw.write_record(
            str(self.home),
            {
                "project": project,
                "git_dir": git_dir,
                "url": url,
                "github": github,
                "git": git_program or self.git_program(),
                "gh": str(self.bin / "gh"),
                "recorded_at": "2026-11-26T00:00:00Z",
            },
        )

    def work(self) -> Path:
        return self.home / ".config" / "acs" / "work"

    def calls(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def remote_ref(self, ref: str) -> str | None:
        try:
            return git("rev-parse", "--verify", "--quiet", ref, cwd=self.remote)
        except subprocess.CalledProcessError:
            return None


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    return Setup(tmp_path)


@pytest.fixture
def recorded(setup: Setup) -> Setup:
    setup.record(github="github.example/owner/repo")
    return setup


# --- argument validation ----------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["main", "feat/185-typed", "v1.2.0", "a+b", "user@x", "a_b.c", "x" * 200],
)
def test_ref_names_git_accepts_are_accepted(name: str) -> None:
    assert rw.validate_ref_name(name, "branch") == name
    git("check-ref-format", "refs/heads/" + name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "-f",
        "--force",
        "HEAD",
        "@",
        "a b",
        "a\nb",
        "a..b",
        "a~1",
        "a^",
        "a:b",
        "a?",
        "a*",
        "a[b",
        "a\\b",
        "a@{1}",
        "/a",
        "a/",
        "a//b",
        "a.",
        ".a",
        "a/.b",
        "a.lock",
        "a/b.lock/c",
        "é",
        "a;b",
        "x$(id)",
        "a|b&c",
        "q'uote",
        "a{b}",
        "a`b`",
        "a=b",
        "x" * 201,
        5,
        None,
        ["main"],
    ],
)
def test_ref_names_are_refused(name: Any) -> None:
    with pytest.raises(rw.RemoteWriteError):
        rw.validate_ref_name(name, "branch")


@pytest.mark.parametrize(
    "ref", ["refs/heads/a..b;id", "refs/heads/a b", "refs/heads/x.lock"]
)
def test_git_refuses_what_the_server_asks_it_to_check(setup: Setup, ref: str) -> None:
    ctx = setup.ctx()
    with pytest.raises(rw.RemoteWriteError, match="check-ref-format"):
        rw._git_checks_ref(rw.find_program("git", ctx), ctx, str(setup.base), ref)


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("push", {}, "needs branch"),
        ("push", {"branch": "main", "remote": "evil"}, "takes no argument"),
        ("push", {"branch": "main", "repository": "o/r"}, "takes no argument"),
        ("push", {"branch": "main", "force_with_lease": True}, "full object id"),
        ("push", {"branch": "main", "force_with_lease": "abc"}, "full object id"),
        ("pr_merge", {"number": "7", "method": "merge"}, "integer"),
        ("pr_merge", {"number": 7.0, "method": "merge"}, "integer"),
        ("pr_merge", {"number": True, "method": "merge"}, "integer"),
        ("pr_merge", {"number": 0, "method": "merge"}, "from 1"),
        ("pr_merge", {"number": 2**31, "method": "merge"}, "from 1"),
        ("pr_merge", {"number": 7, "method": "admin"}, "one of merge, squash, rebase"),
        ("pr_merge", {"number": 7, "method": "--admin"}, "one of"),
        (
            "pr_merge",
            {"number": 7, "method": "merge", "delete_branch": True},
            "takes no",
        ),
        ("issue_assign", {"number": 1, "assignee": "-x"}, "GitHub login"),
        ("issue_assign", {"number": 1, "assignee": "a b"}, "GitHub login"),
        ("issue_create", {"title": "t\nx", "body": "b"}, "control characters"),
        ("issue_create", {"title": "t", "body": "b\x1b[2J"}, "control characters"),
        ("issue_create", {"title": " ", "body": "b"}, "may not be empty"),
        ("issue_create", {"title": "t" * 257, "body": "b"}, "at most 256"),
        (
            "release_create",
            {"tag": "v1", "title": "t", "notes": "n", "draft": "yes"},
            "true or false",
        ),
    ],
)
def test_arguments_are_checked(
    tool: str, arguments: dict[str, Any], message: str
) -> None:
    with pytest.raises(rw.RemoteWriteError, match=re.escape(message)):
        rw.validate_arguments(rw.TOOLS[tool], arguments)


def test_arguments_must_be_an_object() -> None:
    with pytest.raises(rw.RemoteWriteError, match="object"):
        rw.validate_arguments(rw.TOOLS["push"], ["main"])


def test_input_schemas_refuse_unknown_members() -> None:
    for tool in rw.TOOLS.values():
        schema = tool.input_schema()
        assert schema["additionalProperties"] is False
        assert "repository" not in schema["properties"]
        assert "repo" not in schema["properties"]


# --- the origin record ------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "github"),
    [
        ("https://github.com/owner/repo.git", "github.com/owner/repo"),
        ("https://github.com/owner/repo", "github.com/owner/repo"),
        ("git@github.com:owner/repo.git", "github.com/owner/repo"),
        ("ssh://git@github.com/owner/repo.git", "github.com/owner/repo"),
        ("https://GHE.example.com/o/r", "ghe.example.com/o/r"),
        ("/srv/git/repo.git", None),
        ("file:///srv/git/repo.git", None),
    ],
)
def test_origin_urls_accepted(url: str, github: str | None) -> None:
    assert rw.parse_origin(url) == (url, github)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:ghp_secret@github.com/o/r.git",
        "https://user@github.com/o/r.git",
        "http://github.com/o/r.git",
        "ext::sh -c touch% /tmp/x",
        "ext::sh",
        "fd::3",
        "-uhelp",
        "--upload-pack=touch x",
        "relative/path",
        "/srv/../etc",
        "https://github.com/o/r/extra",
        "https://github.com/../r",
        "/srv/git repo",
        "",
        None,
    ],
)
def test_origin_urls_refused(url: Any) -> None:
    with pytest.raises(rw.RemoteWriteError):
        rw.parse_origin(url)


def test_no_record_refuses_every_tool(setup: Setup) -> None:
    with pytest.raises(rw.RemoteWriteError, match="no origin is recorded"):
        rw.call_tool("push", {"branch": "main"}, setup.ctx())
    with pytest.raises(rw.RemoteWriteError, match="no origin is recorded"):
        rw.call_tool("issue_create", {"title": "t", "body": "b"}, setup.ctx())
    assert setup.remote_ref("refs/heads/main") is None
    assert setup.calls() == []


def test_the_repositorys_own_origin_is_not_the_target(setup: Setup) -> None:
    """The record names the target: changing remote.origin.url in the
    project's configuration, which the agent can write, changes nothing."""
    setup.record()
    evil = setup.base / "evil.git"
    git("init", "-q", "--bare", str(evil))
    git("remote", "set-url", "origin", str(evil), cwd=setup.project)
    rw.call_tool("push", {"branch": "main"}, setup.ctx())
    assert setup.remote_ref("refs/heads/main") is not None
    assert not list((evil / "refs" / "heads").iterdir())


def test_a_record_for_another_git_directory_is_refused(setup: Setup) -> None:
    setup.record()
    data = json.loads((setup.home / ".config/acs/remotes.json").read_text())
    data["repositories"][0]["git_dir"] = "/elsewhere/.git"
    (setup.home / ".config/acs/remotes.json").write_text(json.dumps(data))
    with pytest.raises(rw.RemoteWriteError, match="record it again"):
        rw.call_tool("push", {"branch": "main"}, setup.ctx())


@pytest.mark.parametrize("mode", [0o620, 0o602, 0o666])
def test_a_record_others_can_write_is_refused(setup: Setup, mode: int) -> None:
    setup.record()
    (setup.home / ".config/acs/remotes.json").chmod(mode)
    with pytest.raises(rw.RemoteWriteError, match="writable by no one else"):
        rw.call_tool("push", {"branch": "main"}, setup.ctx())


def test_a_linked_record_is_refused(setup: Setup) -> None:
    setup.record()
    record = setup.home / ".config/acs/remotes.json"
    real = setup.base / "real.json"
    record.rename(real)
    record.symlink_to(real)
    with pytest.raises(rw.RemoteWriteError, match="not a regular file"):
        rw.call_tool("push", {"branch": "main"}, setup.ctx())


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        '{"version": 1, "repositories": [], "x": 1}',
        '{"version": 2, "repositories": []}',
        '{"version": 1, "version": 1, "repositories": []}',
        '{"version": 1, "repositories": [{"project": "/p"}]}',
        '{"version": 1, "repositories": [{"project": "/p", "git_dir": "/p/.git",'
        ' "url": "ext::sh", "github": null, "recorded_at": "x"}]}',
    ],
)
def test_a_record_of_another_form_is_refused(setup: Setup, text: str) -> None:
    path = setup.home / ".config/acs/remotes.json"
    path.parent.mkdir(parents=True)
    path.write_text(text)
    path.chmod(0o600)
    with pytest.raises(rw.RemoteWriteError):
        rw.read_records(str(setup.home))


def _record(
    setup: Setup, *extra: str, path: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [
            SYSTEM_PYTHON if os.path.exists(SYSTEM_PYTHON) else sys.executable,
            "-I",
            str(MODULE),
            "--home",
            str(setup.home),
            "record",
            *extra,
        ],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=env,
        timeout=60,
        check=False,
    )


GITHUB_URL = "https://github.example/owner/repo.git"


def test_the_record_command_writes_a_private_file(setup: Setup) -> None:
    git("remote", "set-url", "origin", GITHUB_URL, cwd=setup.project)
    done = _record(setup, "--project", str(setup.project), "--yes")
    assert done.returncode == 0, done.stderr
    assert f"Origin URL:         {GITHUB_URL}" in done.stdout
    record = setup.home / ".config" / "acs" / "remotes.json"
    assert record.stat().st_mode & 0o777 == 0o600
    assert (record.parent.stat().st_mode & 0o777) == 0o700
    (entry,) = rw.read_records(str(setup.home))
    assert entry["url"] == GITHUB_URL
    assert entry["project"] == os.path.realpath(setup.project)
    assert os.path.isabs(entry["git"])
    assert f"git:                {entry['git']}" in done.stdout


def test_the_record_command_skips_programs_in_the_plugins_directory(
    setup: Setup,
) -> None:
    """Another plugin's shims, first on PATH in a session, are not what the
    record names."""
    shims = setup.home / ".claude" / "plugins" / "x" / "shims"
    shims.mkdir(parents=True)
    for name in ("git", "gh"):
        (shims / name).write_text("#!/bin/sh\nexit 0\n")
        (shims / name).chmod(0o755)
    done = _record(
        setup,
        "--project",
        str(setup.project),
        "--url",
        GITHUB_URL,
        "--yes",
        path=os.pathsep.join([str(shims), os.environ.get("PATH", "")]),
    )
    assert done.returncode == 0, done.stderr
    (entry,) = rw.read_records(str(setup.home))
    for name in ("git", "gh"):
        assert entry[name] is None or not entry[name].startswith(str(shims)), name


def test_the_record_command_refuses_a_local_origin_in_a_temporary_directory(
    setup: Setup,
) -> None:
    done = _record(setup, "--project", str(setup.project), "--yes")
    assert done.returncode == 2
    assert "where the agent's commands can change" in done.stderr
    assert not (setup.home / ".config" / "acs" / "remotes.json").exists()


def test_the_record_command_refuses_a_project_holding_home(setup: Setup) -> None:
    done = _record(setup, "--project", str(setup.base), "--url", GITHUB_URL, "--yes")
    assert done.returncode == 2
    assert "contains the home directory" in done.stderr
    assert not (setup.home / ".config" / "acs" / "remotes.json").exists()


def test_the_record_command_asks_unless_told(setup: Setup) -> None:
    done = _record(setup, "--project", str(setup.project), "--url", GITHUB_URL)
    assert done.returncode == 2
    assert "not asked" in done.stderr
    assert not (setup.home / ".config" / "acs" / "remotes.json").exists()


def test_the_record_command_refuses_a_url_with_a_password(setup: Setup) -> None:
    git(
        "remote",
        "set-url",
        "origin",
        "https://u:ghp_x@github.com/o/r",
        cwd=setup.project,
    )
    done = _record(setup, "--project", str(setup.project), "--yes")
    assert done.returncode == 2
    assert "ghp_x" not in done.stdout + done.stderr
    assert not (setup.home / ".config" / "acs" / "remotes.json").exists()


# --- push and tag_push against a local bare repository ----------------------


def test_push_fast_forward(recorded: Setup) -> None:
    head = git("rev-parse", "HEAD", cwd=recorded.project)
    out = rw.call_tool("push", {"branch": "main"}, recorded.ctx())
    assert recorded.remote_ref("refs/heads/main") == head
    assert "refs/heads/main" in out


def test_push_refuses_a_non_fast_forward_without_a_lease(recorded: Setup) -> None:
    rw.call_tool("push", {"branch": "main"}, recorded.ctx())
    first = recorded.remote_ref("refs/heads/main")
    git("commit", "-q", "--amend", "-m", "rewritten", cwd=recorded.project)
    with pytest.raises(rw.RemoteWriteError, match="git push failed"):
        rw.call_tool("push", {"branch": "main"}, recorded.ctx())
    assert recorded.remote_ref("refs/heads/main") == first


def test_force_with_lease_holds_only_at_the_named_object(recorded: Setup) -> None:
    rw.call_tool("push", {"branch": "main"}, recorded.ctx())
    first = recorded.remote_ref("refs/heads/main")
    assert first is not None
    git("commit", "-q", "--amend", "-m", "rewritten", cwd=recorded.project)
    rewritten = git("rev-parse", "HEAD", cwd=recorded.project)
    stale = "0" * len(first)
    with pytest.raises(rw.RemoteWriteError, match="git push failed"):
        rw.call_tool(
            "push", {"branch": "main", "force_with_lease": stale}, recorded.ctx()
        )
    assert recorded.remote_ref("refs/heads/main") == first
    rw.call_tool("push", {"branch": "main", "force_with_lease": first}, recorded.ctx())
    assert recorded.remote_ref("refs/heads/main") == rewritten


def test_push_of_a_branch_the_project_lacks_is_refused(recorded: Setup) -> None:
    with pytest.raises(rw.RemoteWriteError, match="no refs/heads/nope"):
        rw.call_tool("push", {"branch": "nope"}, recorded.ctx())


def test_a_ref_with_shell_text_is_one_argument(recorded: Setup) -> None:
    """The tools refuse such a name; below them, a ref holding shell syntax
    reaches git as one argument: the ref of that exact name is pushed, and
    no shell runs the text."""
    name = "x;touch${IFS}pwned$(touch${IFS}pwned2)`touch${IFS}pwned3`"
    with pytest.raises(rw.RemoteWriteError):
        rw.call_tool("push", {"branch": name}, recorded.ctx())
    git("branch", name, cwd=recorded.project)
    ctx = recorded.ctx()
    git_program = rw.find_program("git", ctx)
    work = recorded.base / "work"
    work.mkdir()
    repo = rw.find_repository(git_program, ctx, str(work))
    oid = git("rev-parse", "refs/heads/" + name, cwd=recorded.project)
    rw._push(
        ctx,
        str(work),
        git_program,
        repo,
        str(recorded.remote),
        oid,
        "refs/heads/" + name,
        None,
    )
    assert recorded.remote_ref("refs/heads/" + name) == oid
    for where in (recorded.project, recorded.base, work, Path.cwd()):
        assert not list(where.glob("pwned*"))


def test_push_runs_no_hook_and_no_program_of_the_repositorys_config(
    recorded: Setup,
) -> None:
    """The project's hooks, a core.hooksPath in its configuration or in the
    user's, and the programs its configuration names (core.sshCommand,
    credential.helper, an insteadOf that redirects the push) take no part."""
    git("tag", "-a", "-m", "t", "unpushed", cwd=recorded.project)
    marks = recorded.base / "marks"
    marks.mkdir()
    # The user's hooks directory holds only pre-push: the remote here is a
    # local repository, whose receiving side runs with the user's own
    # configuration as a remote host's would with its own.
    for hooks, names in (
        (recorded.project / ".git" / "hooks", HOOK_NAMES),
        (recorded.base / "repo-hooks", HOOK_NAMES),
        (recorded.base / "user-hooks", ("pre-push",)),
    ):
        hooks.mkdir(exist_ok=True)
        for name in names:
            (hooks / name).write_text(
                f"#!/bin/sh\ntouch {marks}/{hooks.name}-$(basename $0)-$$\n"
            )
            (hooks / name).chmod(0o755)
    evil = recorded.base / "evil.git"
    git("init", "-q", "--bare", str(evil))
    cfg = recorded.project / ".git" / "config"
    for key, value in (
        ("core.hooksPath", str(recorded.base / "repo-hooks")),
        ("core.sshCommand", f"touch {marks}/ssh"),
        ("credential.helper", f"!touch {marks}/credential"),
        (f"url.{evil}.pushInsteadOf", str(recorded.remote)),
        (f"url.{evil}.insteadOf", str(recorded.remote)),
        (f"remote.{recorded.remote}.receivepack", f"touch {marks}/receivepack;"),
        ("push.followTags", "true"),
    ):
        git("config", "--file", str(cfg), key, value)
    (recorded.home / ".gitconfig").write_text(
        f"[core]\n\thooksPath = {recorded.base / 'user-hooks'}\n"
    )
    rw.call_tool("push", {"branch": "main"}, recorded.ctx())
    assert recorded.remote_ref("refs/heads/main") is not None
    assert recorded.remote_ref("refs/tags/unpushed") is None
    assert not list((evil / "refs" / "heads").iterdir())
    assert list(marks.iterdir()) == []


@pytest.mark.parametrize(
    ("safe_options", "no_verify", "runs"),
    [(True, False, False), (False, True, False), (False, False, True)],
)
def test_the_pre_push_hook_is_stopped_by_each_option(
    recorded: Setup,
    monkeypatch: pytest.MonkeyPatch,
    safe_options: bool,
    no_verify: bool,
    runs: bool,
) -> None:
    """core.hooksPath=/dev/null alone stops the pre-push hook the user's
    configuration names, as --no-verify alone does; with neither it runs
    (the control)."""
    marks = recorded.base / "marks"
    marks.mkdir()
    hooks = recorded.base / "user-hooks"
    hooks.mkdir()
    (hooks / "pre-push").write_text(f"#!/bin/sh\ntouch {marks}/pre-push\n")
    (hooks / "pre-push").chmod(0o755)
    (recorded.home / ".gitconfig").write_text(f"[core]\n\thooksPath = {hooks}\n")
    if not safe_options:
        monkeypatch.setattr(rw, "_SAFE_GIT_OPTIONS", ())
    if not no_verify:
        monkeypatch.setattr(
            rw,
            "_PUSH_OPTIONS",
            tuple(o for o in rw._PUSH_OPTIONS if o != "--no-verify"),
        )
    rw.call_tool("push", {"branch": "main"}, recorded.ctx())
    assert recorded.remote_ref("refs/heads/main") is not None
    assert [p.name for p in marks.iterdir()] == (["pre-push"] if runs else [])


HOOK_NAMES = ("pre-push", "reference-transaction", "post-update", "pre-receive")


def test_tag_push_never_replaces_a_tag(recorded: Setup) -> None:
    git("tag", "-a", "-m", "one", "v1", cwd=recorded.project)
    tag = git("rev-parse", "refs/tags/v1", cwd=recorded.project)
    rw.call_tool("tag_push", {"tag": "v1"}, recorded.ctx())
    assert recorded.remote_ref("refs/tags/v1") == tag
    (recorded.project / "b.txt").write_text("b\n")
    git("add", "b.txt", cwd=recorded.project)
    git("commit", "-q", "-m", "second", cwd=recorded.project)
    git("tag", "-f", "-a", "-m", "two", "v1", cwd=recorded.project)
    with pytest.raises(rw.RemoteWriteError, match="git push failed"):
        rw.call_tool("tag_push", {"tag": "v1"}, recorded.ctx())
    assert recorded.remote_ref("refs/tags/v1") == tag


def test_a_git_directory_that_is_content_is_refused(setup: Setup) -> None:
    """A project whose git directory is not one git made for a work tree
    (an embedded bare repository a checkout can ship) is refused."""
    assert git_dir_is_made(str(setup.project / ".git"))
    work_tree = setup.base / "content"
    git("init", "-q", f"--separate-git-dir={setup.base / 'shipped'}", str(work_tree))
    setup.write_entry(
        os.path.realpath(work_tree),
        os.path.realpath(setup.base / "shipped"),
        str(setup.remote),
    )
    ctx = rw.Context(str(work_tree), str(setup.home), setup.path, ())
    with pytest.raises(rw.RemoteWriteError, match="not one git made for a work tree"):
        rw.call_tool("push", {"branch": "main"}, ctx)
    bare_project = setup.base / "bare"
    git("init", "-q", "--bare", str(bare_project))
    setup.write_entry(
        os.path.realpath(bare_project),
        os.path.realpath(bare_project),
        str(setup.remote),
    )
    ctx = rw.Context(str(bare_project), str(setup.home), setup.path, ())
    with pytest.raises(rw.RemoteWriteError, match="not in a git repository"):
        rw.call_tool("push", {"branch": "main"}, ctx)


# --- the gh tools, with a fake gh -------------------------------------------


GH_CASES: list[tuple[str, dict[str, Any], list[str]]] = [
    (
        "pr_create",
        {"head": "feat/x", "base": "main", "title": "--title=evil", "body": "-b\nline"},
        [
            "pr",
            "create",
            "--head=feat/x",
            "--base=main",
            "--title=--title=evil",
            "--body=-b\nline",
        ],
    ),
    (
        "pr_create",
        {"head": "user@x+y", "base": "main", "title": "t", "body": "b", "draft": True},
        [
            "pr",
            "create",
            "--head=user@x+y",
            "--base=main",
            "--title=t",
            "--body=b",
            "--draft",
        ],
    ),
    ("pr_merge", {"number": 7, "method": "squash"}, ["pr", "merge", "7", "--squash"]),
    (
        "pr_merge",
        {"number": 7, "method": "rebase", "match_head_commit": "a" * 40},
        ["pr", "merge", "7", "--rebase", "--match-head-commit=" + "a" * 40],
    ),
    (
        "release_create",
        {"tag": "v1.0.0", "title": "One", "notes": "$(id)", "prerelease": True},
        [
            "release",
            "create",
            "v1.0.0",
            "--verify-tag",
            "--title=One",
            "--notes=$(id)",
            "--prerelease",
        ],
    ),
    (
        "issue_create",
        {"title": "A bug", "body": "`id`"},
        ["issue", "create", "--title=A bug", "--body=`id`"],
    ),
    (
        "issue_assign",
        {"number": 3, "assignee": "octo-cat"},
        ["issue", "edit", "3", "--add-assignee=octo-cat"],
    ),
]


@pytest.mark.parametrize(("tool", "arguments", "argv"), GH_CASES)
def test_gh_tools_run_one_command_by_argument_list(
    recorded: Setup,
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    arguments: dict[str, Any],
    argv: list[str],
) -> None:
    for name, value in (
        ("GH_REPO", "evil/repo"),
        ("GH_HOST", "evil.example"),
        ("GH_CONFIG_DIR", str(recorded.base)),
        ("GIT_DIR", str(recorded.project / ".git")),
        ("GIT_CONFIG_GLOBAL", str(recorded.base / "x")),
        ("XDG_CONFIG_HOME", str(recorded.base)),
        ("HOME", str(recorded.base / "elsewhere")),
        ("GH_TOKEN", "test-token-not-real"),
    ):
        monkeypatch.setenv(name, value)
    out = rw.call_tool(tool, arguments, recorded.ctx())
    assert "pull/7" in out
    (call,) = recorded.calls()
    assert call["argv"] == [*argv, "--repo=github.example/owner/repo"]
    assert call["cwd"] != str(recorded.project)
    assert Path(call["cwd"]).parent == recorded.work()
    assert not Path(call["cwd"]).exists()  # an empty directory, removed after
    assert call["env"]["TMPDIR"] == call["cwd"]
    assert call["env"]["PATH"].split(os.pathsep)[:1] == [str(recorded.bin)]
    assert call["env"]["PATH"].endswith("/usr/bin:/bin:/usr/sbin:/sbin")
    env = call["env"]
    for name in (
        "GH_REPO",
        "GH_HOST",
        "GH_CONFIG_DIR",
        "GIT_DIR",
        "GIT_CONFIG_GLOBAL",
        "XDG_CONFIG_HOME",
    ):
        assert name not in env, name
    assert env["HOME"] == str(recorded.home)
    assert env["GH_TOKEN"] == "test-token-not-real"
    assert env["GH_PROMPT_DISABLED"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_gh_failure_is_reported(recorded: Setup) -> None:
    gh = recorded.bin / "gh"
    gh.write_text("#!/bin/sh\necho 'not found' >&2\nexit 1\n")
    with pytest.raises(rw.RemoteWriteError, match="gh failed:\nnot found"):
        rw.call_tool("pr_merge", {"number": 1, "method": "merge"}, recorded.ctx())


def test_gh_tools_need_a_github_origin(setup: Setup) -> None:
    setup.record()  # a local path: no GitHub repository
    with pytest.raises(rw.RemoteWriteError, match="not a GitHub repository"):
        rw.call_tool("issue_create", {"title": "t", "body": "b"}, setup.ctx())
    assert setup.calls() == []


def test_the_github_repository_comes_from_the_recorded_url(setup: Setup) -> None:
    setup.record(url="git@github.com:owner/name.git")
    rw.call_tool("issue_assign", {"number": 1, "assignee": "me"}, setup.ctx())
    (call,) = setup.calls()
    assert call["argv"][-1] == "--repo=github.com/owner/name"


def test_a_gh_in_the_project_or_a_temporary_directory_is_not_run(
    recorded: Setup,
) -> None:
    inside = recorded.project / "bin"
    inside.mkdir()
    shutil.copy(recorded.bin / "gh", inside / "gh")
    ctx = rw.Context(
        str(recorded.project),
        str(recorded.home),
        os.pathsep.join([str(inside), "relative/bin", ""]),
        (os.path.realpath(recorded.project),),
    )
    with pytest.raises(rw.RemoteWriteError, match="gh was not found"):
        rw.find_program("gh", ctx)
    ctx = rw.Context(
        str(recorded.project),
        str(recorded.home),
        str(recorded.bin),
        (os.path.realpath(recorded.bin),),
    )
    with pytest.raises(rw.RemoteWriteError, match="gh was not found"):
        rw.find_program("gh", ctx)
    link_dir = recorded.base.parent / (recorded.base.name + "-links")
    link_dir.mkdir()
    (link_dir / "gh").symlink_to(inside / "gh")
    ctx = rw.Context(
        str(recorded.project),
        str(recorded.home),
        str(link_dir),
        (os.path.realpath(recorded.project),),
    )
    with pytest.raises(rw.RemoteWriteError, match="links into the project"):
        rw.find_program("gh", ctx)


def test_the_server_distrusts_temporary_and_plugin_directories(
    tmp_path: Path,
) -> None:
    ctx = rw.Context.from_process(str(tmp_path))
    roots = ctx.untrusted
    assert os.path.realpath(os.getcwd()) in roots
    assert os.path.realpath("/tmp") in roots
    assert os.path.realpath(tmp_path / ".claude" / "plugins") in roots


# --- the bindings and the hook ----------------------------------------------


def _hook_array(name: str) -> list[str]:
    text = HOOK.read_text(encoding="utf-8")
    match = re.search(rf"^{name}=\((.*)\)$", text, re.MULTILINE)
    assert match
    return shlex.split(match.group(1))


def test_the_tool_lists_agree() -> None:
    """The server's tools, its binding records, the hook's list and the
    mapper's table name the same seven tools."""
    names = list(rw.TOOLS)
    assert names == [
        "push",
        "tag_push",
        "pr_create",
        "pr_merge",
        "release_create",
        "issue_create",
        "issue_assign",
    ]
    assert _hook_array("REMOTE_WRITE_TOOLS") == names
    text = HOOK.read_text(encoding="utf-8")
    assert f'REMOTE_WRITE_PREFIX="{rw.PLUGIN_TOOL_PREFIX}"' in text
    full = [rw.PLUGIN_TOOL_PREFIX + n for n in names]
    assert [r["tool"] for r in rw.binding_records()] == full
    listed = [t["name"] for t in rw._tool_list()]
    assert listed == names
    for name in full:
        assert mapper._TOOL_MAPPINGS[name] == "mutate"
        assert name not in _hook_array("UNGATED_TOOLS")


def test_the_plugin_declares_the_server() -> None:
    plugin = json.loads(PLUGIN.read_text())
    assert plugin["name"] == rw.PLUGIN_NAME
    server = plugin["mcpServers"][rw.SERVER_NAME]
    # /usr/bin/python3 is a shim on macOS that runs the interpreter
    # DEVELOPER_DIR, TOOLCHAINS or SDKROOT choose; a project's settings env
    # reaches the server, so env removes them before the shim runs.
    assert server == {
        "command": "/usr/bin/env",
        "args": [
            "-u",
            "DEVELOPER_DIR",
            "-u",
            "TOOLCHAINS",
            "-u",
            "SDKROOT",
            "/usr/bin/python3",
            "-I",
            "${CLAUDE_PLUGIN_ROOT}/grounded_agency/remote_writes.py",
            "serve",
        ],
    }
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    (entry,) = hooks["hooks"]["PreToolUse"]
    assert re.fullmatch(entry["matcher"].replace("*", ".*"), full_name("push"))


def full_name(tool: str) -> str:
    return rw.PLUGIN_TOOL_PREFIX + tool


def test_binding_records_follow_the_schema_and_load() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "interop" / "tool_binding.schema.json").read_text()
    )
    records = rw.binding_records()
    for record in records:
        jsonschema.validate(record, schema)
    classify = mapper.ToolCapabilityMapper()
    assert classify.load_bindings(rw.binding_records("mcp__remote__")) == []
    for record in records:
        for name in (
            record["tool"],
            "mcp__remote__" + record["tool"].rsplit("__", 1)[1],
        ):
            mapping = classify.map_tool(name, {})
            assert mapping.capabilities == ("mutate",)
            assert mapping.risk == "high"
            assert mapping.requires_checkpoint and mapping.requires_approval


def test_the_versions_are_the_repositorys() -> None:
    import yaml

    from grounded_agency.versions import SPEC_VERSIONS

    ontology = yaml.safe_load(
        (ROOT / "schemas" / "capability_ontology.yaml").read_text(encoding="utf-8")
    )
    assert rw.ONTOLOGY_VERSION == ontology["meta"]["version"]
    assert rw.STANDARD_VERSION.rsplit(".", 1)[0] in SPEC_VERSIONS


def test_safe_git_options_are_the_packages() -> None:
    assert rw._SAFE_GIT_OPTIONS == SAFE_GIT_OPTIONS


@pytest.mark.parametrize(
    "path",
    [
        "/p/.git",
        "/p/.git/worktrees/w",
        "/p/.git/modules/m",
        "/p/repo.git",
        "/p/.gitx",
        "/p/content",
        "/p/a.git/worktrees/w",
    ],
)
def test_git_dir_is_made_is_the_packages(path: str) -> None:
    assert rw.git_dir_is_made(path) == git_dir_is_made(path)


def test_the_hook_shows_exactly_the_values_the_server_accepts() -> None:
    """The class of values the hook shows in an approval request is the
    class of branch and tag names the server accepts, so no target the
    server acts on is hidden from the person who approves it."""
    text = HOOK.read_text(encoding="utf-8")
    match = re.search(r'\[\[ "\$value" =~ \^(\[[^]]+\])\{1,200\}\$ \]\]', text)
    assert match, "remote_write_value's pattern not found"
    assert match.group(1) + "+" == rw.REF_CHARACTERS


def _run_hook(
    project: Path, tool: str, tool_input: dict[str, Any], mode: str = "default"
) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": full_name(tool),
        "tool_input": tool_input,
        "permission_mode": mode,
        "tool_use_id": "toolu_test",
        "cwd": str(project),
    }
    env = {k: v for k, v in os.environ.items() if k != "ACS_HOOK_APPROVAL"}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _marker(project: Path) -> None:
    (project / ".claude").mkdir(exist_ok=True)
    now = int(time.time())
    (project / ".claude" / "checkpoint.ok").write_text(
        json.dumps(
            {"checkpoint_id": "chk_t", "created_at": now, "expires_at": now + 600}
        )
    )


HOOK_CASES: list[tuple[str, dict[str, Any], str]] = [
    (
        "push",
        {"branch": "feat/x"},
        "push branch 'feat/x' to the recorded origin, fast-forward only",
    ),
    (
        "push",
        {"branch": "main", "force_with_lease": "b" * 40},
        f"force-push branch 'main' to the recorded origin, only while it is at '{'b' * 40}'",
    ),
    (
        "push",
        {
            "branch": "user@feat/a+b_c.d",
            "force_with_lease": "1d7f08acd66d6b5ab3407213fe108f8f629a9753",
        },
        "force-push branch 'user@feat/a+b_c.d' to the recorded origin, only while "
        "it is at '1d7f08acd66d6b5ab3407213fe108f8f629a9753'",
    ),
    (
        "push",
        {"branch": "main", "force_with_lease": "9f" * 32},
        f"force-push branch 'main' to the recorded origin, only while it is at "
        f"'{'9f' * 32}'",
    ),
    ("tag_push", {"tag": "v1.2.0"}, "push tag 'v1.2.0' to the recorded origin"),
    (
        "pr_create",
        {"head": "feat/x", "base": "main", "title": "t", "body": "b"},
        "open a pull request from 'feat/x' into 'main' on the recorded origin",
    ),
    (
        "pr_merge",
        {"number": 42, "method": "squash"},
        "merge pull request '42' by 'squash' on the recorded origin",
    ),
    (
        "release_create",
        {"tag": "v1", "title": "t", "notes": "n"},
        "create a release for tag 'v1' on the recorded origin",
    ),
    (
        "issue_create",
        {"title": "t", "body": "b"},
        "open an issue on the recorded origin",
    ),
    (
        "issue_assign",
        {"number": 3, "assignee": "octocat"},
        "assign 'octocat' to issue '3' on the recorded origin",
    ),
    (
        "push",
        {"branch": "a b;$(id)"},
        "push branch (a value not shown) to the recorded origin, fast-forward only",
    ),
    (
        "pr_merge",
        {"number": "1 2", "method": ["x"]},
        "merge pull request (a value not shown) by (a value not shown) on the "
        "recorded origin",
    ),
]


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize(("tool", "tool_input", "target"), HOOK_CASES)
def test_the_hook_gates_each_tool_as_mutate(
    tmp_path: Path, tool: str, tool_input: dict[str, Any], target: str
) -> None:
    """Each call needs a checkpoint (F501 without one), is refused where no
    person can be asked (F502), and is put to a person with its target
    named; a checkpoint covers one call."""
    project = tmp_path / "p"
    project.mkdir()
    done = _run_hook(project, tool, tool_input)
    assert done.returncode == 2
    assert done.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")

    _marker(project)
    done = _run_hook(project, tool, tool_input, mode="bypassPermissions")
    assert done.returncode == 2
    assert done.stderr.startswith("F502 APPROVAL_REQUIRED: ")

    done = _run_hook(project, tool, tool_input)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "ask"
    assert out["permissionDecisionReason"] == (
        f"F502 APPROVAL_REQUIRED: {full_name(tool)} (capability 'mutate': {target}) "
        "requires approval; it runs only if this call is approved."
    )
    done = _run_hook(project, tool, tool_input)
    assert done.returncode == 2
    assert done.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
def test_the_hook_does_not_show_a_secret_in_the_target(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    _marker(project)
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    done = _run_hook(project, "push", {"branch": token})
    assert done.returncode == 0, done.stderr
    assert token not in done.stdout + done.stderr
    assert "(a value not shown)" in done.stdout


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
def test_another_servers_tool_stays_unbound(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    _marker(project)
    payload = {
        "tool_name": "mcp__plugin_other_remote__push",
        "tool_input": {"branch": "main"},
        "permission_mode": "default",
    }
    done = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=30,
    )
    assert done.returncode == 0, done.stderr
    assert "(unbound: treated as a mutation" in done.stdout


# --- the server over stdio, under the system's Python -----------------------


def _serve(setup: Setup, messages: list[Any]) -> list[dict[str, Any]]:
    python = SYSTEM_PYTHON if os.path.exists(SYSTEM_PYTHON) else sys.executable
    lines = "".join(
        (m if isinstance(m, str) else json.dumps(m)) + "\n" for m in messages
    )
    done = subprocess.run(
        [python, "-I", str(MODULE), "--home", str(setup.home), "serve"],
        input=lines,
        capture_output=True,
        text=True,
        cwd=setup.project,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return [json.loads(line) for line in done.stdout.splitlines()]


def test_the_server_speaks_mcp(recorded: Setup) -> None:
    responses = _serve(
        recorded,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "push", "arguments": {"branch": "main"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "push", "arguments": {"branch": "--mirror"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "shell", "arguments": {}},
            },
            "not json",
            {"jsonrpc": "2.0", "id": 6, "method": "resources/list"},
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        ],
    )
    by_id = {r["id"]: r for r in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-06-18"
    assert by_id[1]["result"]["serverInfo"]["name"] == "remote"
    tools = by_id[2]["result"]["tools"]
    assert [t["name"] for t in tools] == list(rw.TOOLS)
    for t in tools:
        assert t["_meta"]["acs/tool_binding"]["tool"] == full_name(t["name"])
    # Under the server's own roots the bare remote, in pytest's temporary
    # directory, is a local origin the sandbox could write: refused.
    assert by_id[3]["result"]["isError"] is True
    assert (
        "where the agent's commands can change"
        in (by_id[3]["result"]["content"][0]["text"])
    )
    assert recorded.remote_ref("refs/heads/main") is None
    assert by_id[4]["result"]["isError"] is True
    assert "may not start with '-'" in by_id[4]["result"]["content"][0]["text"]
    assert by_id[5]["error"]["code"] == -32602
    assert by_id[None]["error"]["code"] == -32700
    assert by_id[6]["error"]["code"] == -32601
    assert by_id[7]["result"] == {}
    assert len(responses) == 8  # no answer to the notification


def test_the_server_performs_a_call(recorded: Setup) -> None:
    """The same server loop, in this process, with the test's roots: the
    push is made."""
    import io

    out = io.StringIO()
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "push", "arguments": {"branch": "main"}},
    }
    rw.serve(recorded.ctx, io.StringIO(json.dumps(message) + "\n"), out)
    (response,) = [json.loads(line) for line in out.getvalue().splitlines()]
    assert response["result"]["isError"] is False, response
    assert recorded.remote_ref("refs/heads/main") is not None


# --- what the server trusts -------------------------------------------------


def _planted(directory: Path, name: str, marks: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / name
    program.write_text(f'#!/bin/sh\ntouch "{marks}/{name}-ran"\nexit 0\n')
    program.chmod(0o755)
    return program


def test_a_project_holding_home_is_refused_before_anything_runs(
    setup: Setup,
) -> None:
    """Claude Code started in the home directory: the sandbox can write
    every directory under it, ~/.local/bin included."""
    marks = setup.base / "marks"
    marks.mkdir()
    home = setup.base
    _planted(home / ".local" / "bin", "git", marks)
    path = os.pathsep.join([str(home / ".local" / "bin"), setup.path])
    for project in (home, home.parent):
        ctx = rw.Context(str(project), str(home), path, (str(project),))
        with pytest.raises(rw.RemoteWriteError, match="contains the home directory"):
            rw.call_tool("issue_create", {"title": "t", "body": "b"}, ctx)
    assert list(marks.iterdir()) == []
    ctx = rw.Context(str(home), str(home), str(home / ".local" / "bin"), (str(home),))
    with pytest.raises(rw.RemoteWriteError, match="git was not found"):
        rw.find_program("git", ctx)


def test_another_plugins_shims_are_not_found(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    marks = setup.base / "marks"
    marks.mkdir()
    real = setup.git_program()
    config = setup.base / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    for shims in (
        setup.home / ".claude" / "plugins" / "x" / "hooks" / "shims",
        config / "plugins" / "y" / "shims",
    ):
        _planted(shims, "git", marks)
        roots = rw._plugin_roots(str(setup.home))
        ctx = rw.Context(
            str(setup.project),
            str(setup.home),
            os.pathsep.join([str(shims), os.path.dirname(real)]),
            roots,
        )
        assert rw.find_program("git", ctx) == real
        with pytest.raises(rw.RemoteWriteError, match="plugins directory"):
            rw.recorded_program(str(shims / "git"), "git", ctx)
    assert list(marks.iterdir()) == []


def test_the_recorded_git_is_run_not_one_on_path(recorded: Setup) -> None:
    marks = recorded.base / "marks"
    marks.mkdir()
    earlier = _planted(recorded.base / "earlier", "git", marks)
    ctx = rw.Context(
        str(recorded.project),
        str(recorded.home),
        os.pathsep.join([str(earlier.parent), recorded.path]),
        (str(recorded.project),),
    )
    rw.call_tool("push", {"branch": "main"}, ctx)
    assert recorded.remote_ref("refs/heads/main") is not None
    assert list(marks.iterdir()) == []


def test_a_recorded_program_now_in_the_project_is_refused(setup: Setup) -> None:
    marks = setup.base / "marks"
    marks.mkdir()
    planted = _planted(setup.project / "bin", "git", marks)
    setup.record(github="github.example/owner/repo", git_program=str(planted))
    with pytest.raises(
        rw.RemoteWriteError, match="recorded git .* lies in the project"
    ):
        rw.call_tool("push", {"branch": "main"}, setup.ctx())
    link = setup.base / "elsewhere" / "git"
    link.parent.mkdir()
    link.symlink_to(planted)
    setup.record(github="github.example/owner/repo", git_program=str(link))
    with pytest.raises(rw.RemoteWriteError, match="lies in the project"):
        rw.call_tool("issue_create", {"title": "t", "body": "b"}, setup.ctx())
    assert list(marks.iterdir()) == []
    assert setup.calls() == []


@pytest.mark.parametrize("where", ["project", "temporary"])
def test_a_local_origin_the_sandbox_can_write_is_refused(
    setup: Setup, where: str
) -> None:
    """git's local transport runs the receiving repository's hooks, with
    its own configuration: core.hooksPath=/dev/null does not reach it."""
    marks = setup.base / "marks"
    marks.mkdir()
    if where == "project":
        origin = setup.project / "origin.git"
        untrusted: tuple[str, ...] = (str(setup.project),)
    else:
        origin = setup.base / "scratch" / "origin.git"
        untrusted = (str(setup.project), str(setup.base / "scratch"))
    git("init", "-q", "--bare", str(origin))
    _planted(origin / "hooks", "pre-receive", marks)
    setup.record(url=str(origin))
    ctx = rw.Context(str(setup.project), str(setup.home), setup.path, untrusted)
    with pytest.raises(rw.RemoteWriteError, match="local origin .* lies in"):
        rw.call_tool("push", {"branch": "main"}, ctx)
    assert list(marks.iterdir()) == []


def test_the_local_origins_hooks_run_where_it_is_allowed(setup: Setup) -> None:
    """The control for the test above: outside the untrusted roots the push
    is made, and the receiving repository's own hook runs."""
    marks = setup.base / "marks"
    marks.mkdir()
    _planted(setup.remote / "hooks", "pre-receive", marks)
    setup.record()
    rw.call_tool("push", {"branch": "main"}, setup.ctx())
    assert [p.name for p in marks.iterdir()] == ["pre-receive-ran"]


def test_the_work_directory_is_not_the_environments_tmpdir(
    recorded: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    inside = recorded.project / "tmp"
    inside.mkdir()
    monkeypatch.setenv("TMPDIR", str(inside))
    monkeypatch.setattr(tempfile, "tempdir", None)
    assert tempfile.gettempdir() == str(inside)
    rw.call_tool("push", {"branch": "main"}, recorded.ctx())
    rw.call_tool("issue_create", {"title": "t", "body": "b"}, recorded.ctx())
    assert list(inside.iterdir()) == []
    (call,) = recorded.calls()
    assert Path(call["cwd"]).parent == recorded.work()
    assert recorded.work().stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("problem", ["link", "group-writable"])
def test_a_work_directory_others_can_change_is_refused(
    recorded: Setup, problem: str
) -> None:
    work = recorded.work()
    work.parent.mkdir(parents=True, exist_ok=True)
    if problem == "link":
        target = recorded.base / "shared"
        target.mkdir()
        work.symlink_to(target)
    else:
        work.mkdir(mode=0o700)
        work.chmod(0o770)
    with pytest.raises(rw.RemoteWriteError, match="no one else can write, not a link"):
        rw.call_tool("push", {"branch": "main"}, recorded.ctx())
    assert recorded.remote_ref("refs/heads/main") is None


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
def test_the_hook_refuses_a_text_that_names_the_records(tmp_path: Path) -> None:
    """The hook's records guard reads every string of an MCP tool's input,
    so an issue whose body names .claude/checkpoint.ok is refused F504
    although the server passes the body to gh only as a value."""
    project = tmp_path / "p"
    project.mkdir()
    _marker(project)
    done = _run_hook(
        project,
        "issue_create",
        {"title": "t", "body": "The hook reads .claude/checkpoint.ok"},
    )
    assert done.returncode == 2
    assert done.stderr.startswith("F504 CONSTRAINT_VIOLATED: ")
