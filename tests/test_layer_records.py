"""The layer's records: the deny rules that keep the agent from them, and the
pre-tool-use hook's refusal of every gated call while a record has another
name outside the records (a hard link made outside the boundary)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from grounded_agency.layer_records import (
    GIT_DIR_RECORDS,
    PROJECT_RECORDS,
    LayerRecord,
    LayerRecordsError,
    deny_settings,
    layer_records,
    main,
)
from grounded_agency.utils.git import SAFE_GIT_OPTIONS

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
MODULE = ROOT / "grounded_agency" / "layer_records.py"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **_GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _repo(path: Path) -> Path:
    """A git repository with one commit, at its physical path."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "app.txt").write_text("app\n")
    _git(path, "add", "app.txt")
    _git(path, "commit", "-q", "-m", "init")
    return Path(os.path.realpath(path))


def _rules(settings: dict) -> list[str]:
    deny = settings["permissions"]["deny"]
    assert isinstance(deny, list)
    return deny


# ─── The deny rules ───


@needs_git
class TestDenySettings:
    def test_a_repository(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "p")
        settings = deny_settings(project)
        assert set(settings) == {"permissions", "sandbox"}
        assert set(settings["sandbox"]) == {"filesystem"}
        p = str(project)
        assert _rules(settings) == [
            f"Edit(/{p}/.claude/checkpoint.ok)",
            f"Edit(/{p}/.claude/checkpoints/**)",
            f"Edit(/{p}/.claude/audit.log)",
            f"Edit(/{p}/.claude/audit.head)",
            f"Edit(/{p}/.git/acs/**)",
            f"Read(/{p}/.git/acs/**)",
        ]
        assert settings["sandbox"]["filesystem"]["denyWrite"] == [
            f"{p}/.claude/checkpoint.ok",
            f"{p}/.claude/checkpoints",
            f"{p}/.claude/audit.log",
            f"{p}/.claude/audit.head",
            f"{p}/.git/acs",
        ]

    def test_every_path_is_literal_and_absolute(self, tmp_path: Path) -> None:
        settings = deny_settings(_repo(tmp_path / "p"))
        for rule in _rules(settings):
            m = re.fullmatch(r"(Edit|Read)\((//[^*?\[\]{}()\\]+?)(/\*\*)?\)", rule)
            assert m, rule
        for path in settings["sandbox"]["filesystem"]["denyWrite"]:
            assert path.startswith("/") and not path.startswith("//")
            assert not set(path) & set("*?[]{}")

    def test_a_worktree_names_its_own_git_directory(self, tmp_path: Path) -> None:
        main_repo = _repo(tmp_path / "main")
        _git(main_repo, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "w")
        wt = Path(os.path.realpath(tmp_path / "wt"))
        assert (wt / ".git").is_file()
        records = layer_records(wt)
        git_dir = f"{main_repo}/.git/worktrees/wt"
        assert LayerRecord(f"{git_dir}/acs", True, True) in records
        assert not any(r.path.startswith(f"{wt}/.git") for r in records)
        rules = _rules(deny_settings(wt))
        assert f"Edit(/{git_dir}/acs/**)" in rules
        # And the main checkout's, which the worktree's session could reach.
        assert f"Edit(/{main_repo}/.git/acs/**)" in rules
        assert f"Read(/{main_repo}/.git/acs/**)" in rules

    def test_a_main_checkout_names_its_worktrees_git_directories(
        self, tmp_path: Path
    ) -> None:
        """A worktree's key and commit entries are in the main checkout's
        .git, which a session in the main checkout can write."""
        main_repo = _repo(tmp_path / "main")
        _git(main_repo, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "w")
        rules = _rules(deny_settings(main_repo))
        for kind in ("Edit", "Read"):
            assert f"{kind}(/{main_repo}/.git/worktrees/wt/acs/**)" in rules
        assert (
            f"{main_repo}/.git/worktrees/wt/acs"
            in deny_settings(main_repo)["sandbox"]["filesystem"]["denyWrite"]
        )

    def test_submodule_git_directories_nested_ones_included(
        self, tmp_path: Path
    ) -> None:
        """git keeps a submodule's git directory at .git/modules/<path>
        (a path may have several names), and a nested submodule's in its
        parent's modules/; a directory that holds no HEAD is a name level."""
        main_repo = _repo(tmp_path / "main")
        modules = main_repo / ".git" / "modules"
        for d in ("libs/a", "libs/a/modules/b", "c", "c/worktrees/x"):
            (modules / d).mkdir(parents=True)
        for d in ("libs/a", "libs/a/modules/b", "c"):
            (modules / d / "HEAD").write_text("ref: refs/heads/main\n")
        # The object store of a module is not walked as a name level.
        (modules / "c" / "objects" / "pack").mkdir(parents=True)
        paths = [r.path for r in layer_records(main_repo) if r.in_git_dir]
        assert paths == [
            f"{main_repo}/.git/acs",
            f"{modules}/c/acs",
            f"{modules}/c/worktrees/x/acs",
            f"{modules}/libs/a/acs",
            f"{modules}/libs/a/modules/b/acs",
        ]

    def test_read_rules_only_for_the_git_directorys_records(
        self, tmp_path: Path
    ) -> None:
        """The key is in acs/; the project's records hold no secret, and the
        audit skill reads the audit log for its evidence."""
        project = _repo(tmp_path / "p")
        records = layer_records(project)
        reads = [r for r in _rules(deny_settings(project)) if r.startswith("Read(")]
        assert reads == [
            f"Read(/{r.path}/**)" for r in records if r.in_git_dir and r.directory
        ]
        assert [r.path for r in records if r.in_git_dir] == [f"{project}/.git/acs"]
        audit_skill = (ROOT / "skills" / "audit" / "SKILL.md").read_text()
        assert ".claude/audit.log" in audit_skill
        assert not any(".claude/audit.log" in r for r in reads)

    def test_paths_with_spaces(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "my project dir")
        settings = deny_settings(project)
        assert f"Edit(/{project}/.claude/audit.log)" in _rules(settings)
        assert f"{project}/.git/acs" in settings["sandbox"]["filesystem"]["denyWrite"]
        # The printed JSON keeps them as one string each.
        out = subprocess.run(
            [sys.executable, "-I", str(MODULE), str(project)],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
        assert json.loads(out) == settings

    def test_a_linked_project_path_gives_both_spellings(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "real")
        link = tmp_path / "linked"
        link.symlink_to(project)
        records = layer_records(link)
        paths = [r.path for r in records]
        for base in (str(link), str(project)):
            assert f"{base}/.claude/checkpoint.ok" in paths
            assert f"{base}/.git/acs" in paths
        # A git directory inside the project gets both spellings too.
        _git(project, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "w")
        paths = [r.path for r in layer_records(link)]
        for base in (str(link), str(project)):
            assert f"{base}/.git/worktrees/wt/acs" in paths
        assert len(paths) == len(set(paths))

    def test_no_repository_no_git_directory_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = Path(os.path.realpath(tmp_path)) / "plain"
        project.mkdir()
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(project.parent))
        records = layer_records(project)
        assert [r.path for r in records] == [
            f"{project}/{rel}" for rel, _ in PROJECT_RECORDS
        ]

    @pytest.mark.parametrize(
        "name", ["p*", "p?", "p[1]", "p{a}", "p(x)", "p\\q", "p\nq"]
    )
    def test_a_path_a_rule_reads_as_a_pattern_is_refused(
        self, tmp_path: Path, name: str
    ) -> None:
        project = tmp_path / name
        project.mkdir()
        with pytest.raises(LayerRecordsError, match="literal rule"):
            layer_records(project)

    def test_git_that_does_not_answer_is_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
        with pytest.raises(LayerRecordsError, match="git is not installed"):
            layer_records(tmp_path)
        assert main([str(tmp_path)]) == 2


def test_the_hook_holds_the_same_records() -> None:
    """The hook's LAYER_RECORDS and GIT_DIR_RECORDS are the module's."""
    text = HOOK.read_text()
    block = text.split("# BEGIN layer-records", 1)[1].split("# END layer-records", 1)[0]
    project = re.search(r"^LAYER_RECORDS=\(([^)]*)\)$", block, re.M)
    git_dir = re.search(r"^GIT_DIR_RECORDS=\(([^)]*)\)$", block, re.M)
    assert project and git_dir
    assert project.group(1).split() == [rel for rel, _ in PROJECT_RECORDS]
    assert git_dir.group(1).split() == [rel for rel, _ in GIT_DIR_RECORDS]


def test_the_git_options_are_the_layers() -> None:
    from grounded_agency import layer_records as module

    assert module._SAFE_GIT_OPTIONS == SAFE_GIT_OPTIONS


def test_the_module_runs_without_the_package(tmp_path: Path) -> None:
    """The setup skill runs the file from a plugin checkout, where the
    compiled extension the package imports may be missing: the file imports
    the standard library alone."""
    source = MODULE.read_text()
    imports = re.findall(r"^(?:from|import) (\S+)", source, re.M)
    assert all(not name.startswith(("grounded_agency", ".")) for name in imports)
    copy = tmp_path / "layer_records.py"
    shutil.copy(MODULE, copy)
    result = subprocess.run(
        [sys.executable, "-I", str(copy), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "usage: layer_records.py" in result.stderr


# ─── The hook's link count ───

needs_bash_and_jq = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the hook needs bash and jq",
)

# What the hook runs on these paths, apart from perl and stat.
_HOOK_TOOLS = [
    "bash",
    "jq",
    "git",
    "find",
    "awk",
    "sleep",
    "grep",
    "cat",
    "mv",
    "mkdir",
    "mktemp",
    "rmdir",
    "rm",
    "tr",
    "cut",
    "date",
    "head",
    "od",
    "readlink",
    "sed",
    "ls",
]


def _stat_flavour(path: str) -> str | None:
    def ok(*args: str) -> bool:
        return (
            subprocess.run(
                [path, *args, "/"], capture_output=True, timeout=10
            ).returncode
            == 0
        )

    if ok("-c", "%h"):
        return "gnu"
    if ok("-f", "%l"):
        return "bsd"
    return None


def _stats() -> dict[str, str]:
    """The stat programs installed, by flavour."""
    found: dict[str, str] = {}
    for name in ("stat", "gstat", "/usr/bin/stat"):
        path = shutil.which(name)
        if path:
            flavour = _stat_flavour(path)
            if flavour and flavour not in found:
                found[flavour] = path
    return found


_STATS = _stats()


def _outside(tmp_path: Path, name: str) -> Path:
    """A directory beside the project, not in it: the hook drops from PATH
    every directory in the project."""
    d = tmp_path.parent / f"{tmp_path.name}-{name}"
    d.mkdir()
    return d


def _bin_without_perl(tmp_path: Path, stat: str) -> str:
    bin_dir = _outside(tmp_path, "bin")
    for tool in _HOOK_TOOLS:
        path = shutil.which(tool)
        if path:
            (bin_dir / tool).symlink_to(path)
    (bin_dir / "stat").symlink_to(stat)
    return str(bin_dir)


def _run(
    tool_call: dict, project: Path, path: str | None = None, **extra: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["ACS_HOOK_APPROVAL"] = "off"
    env.update(extra)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [shutil.which("bash") or "bash", str(HOOK)],
        input=json.dumps({"cwd": str(project), **tool_call}),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _write_marker(project: Path) -> Path:
    marker = project / ".claude" / "checkpoint.ok"
    marker.parent.mkdir(exist_ok=True)
    now = int(time.time())
    marker.write_text(
        json.dumps({"checkpoint_id": "c1", "created_at": now, "expires_at": now + 600})
    )
    return marker


def _audit_log(project: Path) -> Path:
    log = project / ".claude" / "audit.log"
    log.parent.mkdir(exist_ok=True)
    log.write_text("{}\n")
    return log


WRITE = {"tool_name": "Write", "tool_input": {"file_path": "a.txt", "content": ""}}
BASH_WRITE = {"tool_name": "Bash", "tool_input": {"command": "touch a.txt"}}
MCP = {"tool_name": "mcp__fs__write", "tool_input": {"path": "a.txt"}}
LINKED = "F504 CONSTRAINT_VIOLATED: the layer's record "


# perl, then stat of each flavour installed with no perl on PATH.
_COUNTERS = ["perl", *(f"stat-{f}" for f in sorted(_STATS))]


def _path_for(counter: str, tmp_path: Path) -> str | None:
    if counter == "perl":
        if shutil.which("perl") is None:
            pytest.skip("perl not installed")
        return None
    return _bin_without_perl(tmp_path, _STATS[counter.removeprefix("stat-")])


@needs_bash_and_jq
@needs_git
@pytest.mark.parametrize("counter", _COUNTERS)
class TestHookRefusesALinkedRecord:
    def test_a_link_outside_the_records_refuses_every_gated_call(
        self, tmp_path: Path, counter: str
    ) -> None:
        project = _repo(tmp_path / "p")
        path = _path_for(counter, tmp_path)
        marker = _write_marker(project)
        log = _audit_log(project)
        os.link(log, project / "notes.txt")
        for call in (WRITE, BASH_WRITE, MCP):
            result = _run(call, project, path)
            assert result.returncode == 2, result.stderr
            assert result.stderr.startswith(LINKED), result.stderr
            assert f"{project}/.claude/audit.log has 2 links" in result.stderr
        # Refused before the marker is taken.
        assert marker.exists()

    def test_a_link_to_the_git_directorys_records(
        self, tmp_path: Path, counter: str
    ) -> None:
        project = _repo(tmp_path / "p")
        path = _path_for(counter, tmp_path)
        key = project / ".git" / "acs" / "checkpoints" / "key"
        key.parent.mkdir(parents=True)
        key.write_text("0" * 64)
        os.link(key, tmp_path / "copy-of-key")
        result = _run(WRITE, project, path)
        assert result.returncode == 2
        assert f"{key} has 2 links" in result.stderr

    def test_a_link_to_the_key_refuses_reads_too(
        self, tmp_path: Path, counter: str
    ) -> None:
        """A hard link made outside the boundary gets past a Read deny rule
        too (the Linux spike): every call is refused while the key has one,
        a Read tool call and a read-only command included."""
        project = _repo(tmp_path / "p")
        path = _path_for(counter, tmp_path)
        key = project / ".git" / "acs" / "checkpoints" / "key"
        key.parent.mkdir(parents=True)
        key.write_text("0" * 64)
        reads = (
            {"tool_name": "Read", "tool_input": {"file_path": "notes.txt"}},
            {"tool_name": "Grep", "tool_input": {"pattern": "0"}},
            {"tool_name": "Bash", "tool_input": {"command": "cat notes.txt"}},
        )
        for call in reads:
            assert _run(call, project, path).returncode == 0, call
        os.link(key, project / "notes.txt")
        for call in reads:
            result = _run(call, project, path)
            assert result.returncode == 2, (call, result.stderr)
            assert result.stderr.startswith(LINKED), result.stderr
            assert f"{key} has 2 links" in result.stderr
            assert "so every call is refused" in result.stderr

    def test_a_link_in_a_worktrees_git_directory(
        self, tmp_path: Path, counter: str
    ) -> None:
        main_repo = _repo(tmp_path / "main")
        _git(main_repo, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "w")
        wt = Path(os.path.realpath(tmp_path / "wt"))
        path = _path_for(counter, tmp_path)
        head = main_repo / ".git" / "worktrees" / "wt" / "acs" / "audit.head"
        head.parent.mkdir()
        head.write_text("{}\n")
        os.link(head, wt / "h.txt")
        result = _run(WRITE, wt, path)
        assert result.returncode == 2
        assert f"{head} has 2 links" in result.stderr

    def test_names_among_the_records_are_not_counted(
        self, tmp_path: Path, counter: str
    ) -> None:
        """Two names, both records: the take hook enters the key with ln,
        and a hook stopped between its ln and its rm leaves both."""
        project = _repo(tmp_path / "p")
        path = _path_for(counter, tmp_path)
        records = project / ".git" / "acs" / "checkpoints"
        records.mkdir(parents=True)
        (records / "key.AbC123").write_text("0" * 64)
        os.link(records / "key.AbC123", records / "key")
        log = _audit_log(project)
        used = project / ".claude" / "checkpoints" / "used"
        used.mkdir(parents=True)
        os.link(log, used / "same-file")
        _write_marker(project)
        result = _run(WRITE, project, path)
        assert result.returncode == 0, result.stderr

    def test_no_link_and_calls_that_need_no_checkpoint(
        self, tmp_path: Path, counter: str
    ) -> None:
        project = _repo(tmp_path / "p")
        path = _path_for(counter, tmp_path)
        _audit_log(project)
        # An empty file, as the sandbox runtime leaves at a path it mounts.
        (project / ".claude" / "checkpoint.ok").write_text("")
        result = _run(WRITE, project, path)
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        os.link(project / ".claude" / "audit.log", project / "notes.txt")
        for call in (
            {"tool_name": "Read", "tool_input": {"file_path": "notes.txt"}},
            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        ):
            assert _run(call, project, path).returncode == 0

    def test_reads_in_no_repository_pass(self, tmp_path: Path, counter: str) -> None:
        project = Path(os.path.realpath(tmp_path)) / "plain"
        project.mkdir()
        path = _path_for(counter, tmp_path)
        call = {"tool_name": "Read", "tool_input": {"file_path": "a.txt"}}
        result = _run(call, project, path, GIT_CEILING_DIRECTORIES=str(project.parent))
        assert result.returncode == 0, result.stderr

    def test_a_record_directory_that_cannot_be_read_blocks(
        self, tmp_path: Path, counter: str
    ) -> None:
        """A record linked outside, in a directory made unreadable: neither
        counter may pass the call (find's error is not dropped)."""
        if os.geteuid() == 0:
            pytest.skip("root reads every directory")
        project = _repo(tmp_path / "p")
        path = _path_for(counter, tmp_path)
        hidden = project / ".claude" / "checkpoints" / "ended" / "x"
        hidden.mkdir(parents=True)
        (hidden / "f").write_text("{}")
        os.link(hidden / "f", project / "outside")
        _write_marker(project)
        hidden.chmod(0)
        try:
            result = _run(WRITE, project, path)
        finally:
            hidden.chmod(0o700)
        assert result.returncode == 2
        assert result.stderr.startswith(
            "R407 SAFETY_CHECK_FAILED: the checkpoint hook could not count the links"
        ), result.stderr
        # Readable again: the link is found.
        result = _run(WRITE, project, path)
        assert result.returncode == 2
        assert result.stderr.startswith(LINKED), result.stderr


# ─── The runtime's empty mount-point files ───

LOG_HOOK = ROOT / "hooks" / "posttooluse_log_tool.sh"
_KEY = "test-key-for-mount-points"
CUT = "no longer holds the entry its head records"


def _log_call(project: Path, call_id: str) -> subprocess.CompletedProcess[str]:
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Read",
        "tool_use_id": call_id,
        "tool_input": {"file_path": "a"},
    }
    return subprocess.run(
        [shutil.which("bash") or "bash", str(LOG_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), "AUDIT_HMAC_KEY": _KEY},
        timeout=60,
    )


@pytest.mark.skipif(
    shutil.which("bash") is None
    or shutil.which("jq") is None
    or shutil.which("openssl") is None,
    reason="the log hook needs bash, jq and openssl",
)
@needs_git
class TestMountPointFiles:
    """While a sandboxed command runs, the Linux sandbox runtime puts an
    empty file at a denied path that does not exist (and leaves it when the
    command is killed). The log hook reads an empty audit.head as none; the
    anchor in the git directory still shows a cut."""

    @staticmethod
    def _three(project: Path) -> tuple[Path, Path, Path]:
        for call_id in ("toolu_1", "toolu_2", "toolu_3"):
            assert _log_call(project, call_id).returncode == 0
        return (
            project / ".claude" / "audit.log",
            project / ".claude" / "audit.head",
            project / ".git" / "acs" / "audit.head",
        )

    def test_an_empty_head_with_an_anchor_is_rewritten(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "p")
        _log, head, anchor = self._three(project)
        head.write_text("")
        result = _log_call(project, "toolu_4")
        assert result.returncode == 0, result.stderr
        assert CUT not in result.stderr
        assert json.loads(head.read_text())["entries"] == 4
        assert head.read_text() == anchor.read_text()

    def test_an_empty_head_and_a_cut_log_is_still_a_cut(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "p")
        log, head, _anchor = self._three(project)
        log.write_text("\n".join(log.read_text().splitlines()[:2]) + "\n")
        head.write_text("")
        result = _log_call(project, "toolu_4")
        assert result.returncode == 1
        assert CUT in result.stderr

    def test_an_empty_anchor_is_a_cut(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "p")
        _log, _head, anchor = self._three(project)
        anchor.write_text("")
        result = _log_call(project, "toolu_4")
        assert result.returncode == 1
        assert CUT in result.stderr

    def test_an_empty_log_whose_anchor_records_entries_is_a_cut(
        self, tmp_path: Path
    ) -> None:
        project = _repo(tmp_path / "p")
        log, head, _anchor = self._three(project)
        log.write_text("")
        head.unlink()
        result = _log_call(project, "toolu_4")
        assert result.returncode == 1
        assert CUT in result.stderr

    def test_an_empty_log_and_head_in_a_new_project(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "p")
        claude = project / ".claude"
        claude.mkdir()
        (claude / "audit.log").write_text("")
        (claude / "audit.head").write_text("")
        result = _log_call(project, "toolu_1")
        assert result.returncode == 0, result.stderr
        assert json.loads((claude / "audit.head").read_text())["entries"] == 1


# ─── The hooks' temporary files ───

# Where a hook may create a file it then renames onto a record: inside a
# directory the deny rules cover as a whole, so no command can link or
# change it first.
_TEMP_PLACES = (
    "${claude_dir}/checkpoints/",
    "$log_dir/checkpoints/",
    "${ended_dir}/",
    "${used_dir}/",
    "${records}/",
    "${commits_dir}/",
    "${anchor_file%/*}/",
)
# And the variables those places are made from.
_TEMP_DIRS = {
    "ended_dir": "/checkpoints/ended",
    "used_dir": "/checkpoints/used",
    "records": "/acs/checkpoints",
    "commits_dir": "${records}/commits",
}


def test_every_temporary_file_is_under_a_record_directory() -> None:
    seen = 0
    for hook in sorted((ROOT / "hooks").glob("*.sh")):
        for line in hook.read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            for m in re.finditer(r"mktemp(?: -d)? \"([^\"]+)\"", line):
                seen += 1
                assert m.group(1).startswith(_TEMP_PLACES), (hook.name, line)
            assert not re.search(r"mktemp(?: -d)?\s*(\)|$)", line), (hook.name, line)
            for m in re.finditer(r"\b\w*_tmp=\"([^\"]+)\"", line):
                seen += 1
                assert m.group(1).startswith(_TEMP_PLACES), (hook.name, line)
            for name, part in _TEMP_DIRS.items():
                m = re.match(rf"\s*(?:local )?{name}=\"([^\"]*)\"", line)
                if m:
                    assert part in m.group(1), (hook.name, line)
    assert seen >= 8


# ─── Nothing else in the guard changed ───


def _without_link_count(directory: Path) -> Path:
    """The hook with every link-count block taken out: the guard as it was
    before the count was added."""
    text = HOOK.read_text()
    pattern = re.compile(r"^# BEGIN link-count.*?^# END link-count\n", re.S | re.M)
    stripped, n = pattern.subn("", text)
    assert n == 2
    assert "records_linked" not in stripped
    copy = directory / "pretooluse_without_link_count.sh"
    copy.write_text(stripped)
    for bash in {"/bin/bash", shutil.which("bash")}:
        if bash and os.path.exists(bash):
            subprocess.run([bash, "-n", str(copy)], check=True, timeout=30)
    return copy


_SAME_CASES = [
    ("Bash", {"command": "ls -la"}),
    ("Bash", {"command": "cat notes/todo.md"}),
    ("Bash", {"command": "touch notes/todo.md"}),
    ("Bash", {"command": "cp app.txt notes/"}),
    ("Bash", {"command": "rm -r .claude"}),
    ("Bash", {"command": "sh -c 'cp -r fixtures/key fixtures/commits notes/k/'"}),
    ("Bash", {"command": "git stash create"}),
    ("Bash", {"command": "echo hi > a.txt"}),
    ("Write", {"file_path": "a.txt", "content": "x"}),
    ("Write", {"file_path": "lnk/checkpoint.ok", "content": "x"}),
    ("Edit", {"file_path": "notes/todo.md", "old_string": "a", "new_string": "b"}),
    ("Read", {"file_path": "notes/todo.md"}),
    ("mcp__fs__write_file", {"path": "notes/k/key", "content": "x"}),
    ("TodoWrite", {"todos": []}),
]


@needs_bash_and_jq
@needs_git
@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs openssl")
@pytest.mark.parametrize("marker", [True, False], ids=["marker", "no-marker"])
@pytest.mark.parametrize("mode", ["default", "bypassPermissions"])
def test_the_guard_gives_the_same_verdicts_without_a_foreign_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: bool, mode: str
) -> None:
    """With no record linked outside, the hook decides every call as the
    hook without the link count does, on the records guard's project (a
    key, links into the records, a marker or none)."""
    import tests.test_records_guard as guard

    project = guard.project.__wrapped__(tmp_path)
    copy = _without_link_count(_outside(tmp_path, "copy"))
    for tool, tool_input in _SAME_CASES:
        verdicts = []
        for hook in (HOOK, copy):
            monkeypatch.setattr(guard, "PRE", hook)
            path = project / ".claude" / "checkpoint.ok"
            if marker:
                guard.fresh_marker(project)
            elif path.exists():
                path.unlink()
            r = guard.run_pre(project, tool, tool_input, mode=mode)
            verdicts.append((r.returncode, r.stdout, r.stderr))
        assert verdicts[0] == verdicts[1], (tool, tool_input)
