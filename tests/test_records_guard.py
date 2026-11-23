"""The pre-tool-use hook's records guard reads every path a call names
(spec/SECURITY.md section 5.1; security round 3, batch 1).

The layer's records (the checkpoint marker, the checkpoint key and commit
entries, the audit log's head) are written by the plugin's hooks alone. A
repository can ship a symbolic link into them (round 2, #4), so the guard
resolves each path a call names. Round 3 found paths it did not read:

- the forms of ``~`` the shell expands besides ``~/`` (``~+``, ``~-``,
  ``~user``), and a path attached to a short option (``-tdir``,
  ``-ofile``);
- the command a quoted word holds for a shell that reads it again
  (``sh -c 'cp x notes/k/'``);
- every argument of a tool other than Bash, Skill and the file tools: an
  MCP filesystem server's path, an MCP shell server's command;
- the directory that holds the records (``rm -rf .claude`` removes the
  audit log with its head).
"""

from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

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

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}

# A stash-shaped commit id the repository could ship.
M = "ff02ae9eaf930b6da829774d2a2e192f9ef81d0c"


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


def run_pre(
    project: Path, tool: str, tool_input: Any, mode: str = "default", **env: str
) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": str(project),
        "permission_mode": mode,
        "tool_use_id": "toolu_x",
    }
    return subprocess.run(
        ["bash", str(PRE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **ENV, "CLAUDE_PROJECT_DIR": str(project), **env},
        timeout=120,
    )


def fresh_marker(project: Path) -> Path:
    claude = project / ".claude"
    claude.mkdir(exist_ok=True)
    now = int(time.time())
    marker = claude / "checkpoint.ok"
    marker.write_text(
        json.dumps({"checkpoint_id": "c1", "created_at": now, "expires_at": now + 600})
    )
    return marker


def asked(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode != 0 or not result.stdout:
        return False
    return (
        json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"
    )


def refused_f504(result: subprocess.CompletedProcess[str]) -> bool:
    return result.returncode == 2 and result.stderr.startswith(
        "F504 CONSTRAINT_VIOLATED: "
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """The verifier's setup: a repository whose take hook entered one
    checkpoint (so the key exists), shipping a link ``notes/k`` to the
    checkpoint records, ``notes/todo.md`` to the key, a ``lnk`` to .claude,
    and fixtures that would forge an entry for M under their own key."""
    project = tmp_path / "proj"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    (project / "app.txt").write_text("app\n")
    git(project, "add", "app.txt")
    git(project, "commit", "-q", "-m", "init")
    (project / "app.txt").write_text("changed\n")
    stash = git(project, "stash", "create")
    taken = subprocess.run(
        ["bash", str(TAKE)],
        input=json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git stash create"},
                "tool_response": {"stdout": stash},
                "cwd": str(project),
            }
        ),
        capture_output=True,
        text=True,
        env={**os.environ, **ENV, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=60,
    )
    assert taken.returncode == 0
    assert (project / ".git" / "acs" / "checkpoints" / "key").is_file()
    notes = project / "notes"
    notes.mkdir()
    (notes / "k").symlink_to("../.git/acs/checkpoints")
    (notes / "todo.md").symlink_to("../.git/acs/checkpoints/key")
    (project / "lnk").symlink_to(".claude")
    fixtures = project / "fixtures"
    (fixtures / "commits").mkdir(parents=True)
    (fixtures / "key").write_text("a" * 64)
    (fixtures / "commits" / M).write_text("b" * 64)
    (project / "a.txt").write_text("a\n")
    # The take hook's marker ends (a turn boundary).
    (project / ".claude" / "checkpoint.ok").unlink()
    return project


def _home_path(project: Path, rel: str) -> str:
    """``~<user>/`` then the path from that user's home directory to
    ``project/rel``: what the shell expands ``~user`` to leads there, and
    the same text read as written (``<cwd>/~user/...``) does not."""
    entry = pwd.getpwuid(os.getuid())
    return f"~{entry.pw_name}/" + os.path.relpath(project / rel, entry.pw_dir) + "/"


class TestShellExpandedPaths:
    """Defect 1: the paths the shell reads differently from their text."""

    @pytest.mark.parametrize(
        "command",
        [
            "cp -r fixtures/key fixtures/commits ~+/notes/k/",
            "cp -r -tnotes/k fixtures/key fixtures/commits",
            "cp -rtnotes/k fixtures/key fixtures/commits",
            "sort -onotes/todo.md a.txt",
            "touch ~+/notes/todo.md",
            "touch -- ~+/notes/todo.md",
        ],
    )
    def test_a_path_the_shell_reads_through_a_link_is_refused(
        self, project: Path, command: str
    ) -> None:
        marker = fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stdout, result.stderr)
        assert marker.exists()

    def test_home_is_expanded(self, project: Path) -> None:
        fresh_marker(project)
        result = run_pre(
            project, "Bash", {"command": "touch ~/notes/todo.md"}, HOME=str(project)
        )
        assert refused_f504(result), result.stderr

    def test_a_users_home_is_expanded(self, project: Path) -> None:
        fresh_marker(project)
        command = "cp -r fixtures/key fixtures/commits " + _home_path(
            project, "notes/k/"
        )
        assert len(command) < 4096
        assert refused_f504(run_pre(project, "Bash", {"command": command}))

    @pytest.mark.parametrize(
        "command",
        [
            "cp -r fixtures/key fixtures/commits ~-/proj/notes/k/",
            "touch ~-",
            "touch ~1/x",
            "touch ~+2/x",
        ],
    )
    def test_a_tilde_form_the_hook_cannot_expand_is_refused(
        self, project: Path, command: str
    ) -> None:
        """~- is the shell's previous directory, ~N its directory stack:
        the hook cannot know where they lead."""
        fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), command
        assert "cannot expand" in result.stderr

    @pytest.mark.parametrize(
        "command",
        [
            "sh -c 'cp -r fixtures/key fixtures/commits notes/k/'",
            'bash -c "touch notes/todo.md"',
            "bash -c \"echo 'x y' > notes/todo.md\"",
            "git -c alias.x='!touch notes/todo.md' x",
            "env sh -c 'cp x ~+/notes/todo.md'",
            "ssh host 'sh -c \"cp x notes/todo.md\"'",
        ],
    )
    def test_the_command_a_quoted_word_holds_is_read(
        self, project: Path, command: str
    ) -> None:
        fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stderr)

    @pytest.mark.parametrize(
        "command",
        [
            "touch ~nosuchuser0/x",
            "cp app.txt notes/",
            "sort -o out.txt a.txt",
            "touch -t 202001010000 app.txt",
            'git commit -m "fix the hook: read paths"',
            "sh -c 'cp a.txt notes/copy.txt'",
            "touch -- -x",
        ],
    )
    def test_other_paths_are_asked(self, project: Path, command: str) -> None:
        fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert asked(result), (command, result.stderr)

    def test_the_approved_copy_no_longer_forges_a_restore(self, project: Path) -> None:
        """The verifier's chain: with no marker, a restore of M is F501
        before and after the refused copy (nothing was written)."""
        result = run_pre(
            project,
            "Bash",
            {"command": f"git stash apply {M}"},
            "bypassPermissions",
        )
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")
        fresh_marker(project)
        copy = run_pre(
            project,
            "Bash",
            {"command": "cp -r fixtures/key fixtures/commits ~+/notes/k/"},
        )
        assert refused_f504(copy)
        assert not (project / ".git" / "acs" / "checkpoints" / "commits" / M).exists()

    def test_a_long_option_cluster_is_read_in_bounded_time(self, project: Path) -> None:
        fresh_marker(project)
        start = time.monotonic()
        result = run_pre(project, "Bash", {"command": "touch -" + "a" * 4000 + "/b"})
        assert result.returncode in (0, 2)
        assert time.monotonic() - start < 20


class TestEveryToolsArguments:
    """Defect 2: an MCP tool's (and every other unbound tool's) arguments
    are read: each string whole, as a path, and as words."""

    @pytest.mark.parametrize(
        ("tool", "tool_input"),
        [
            (
                "mcp__filesystem__write_file",
                {"path": ".git/acs/checkpoints/key", "content": "x"},
            ),
            (
                "mcp__filesystem__edit_file",
                {"path": ".claude/checkpoint.ok", "edits": []},
            ),
            (
                "mcp__filesystem__move_file",
                {"source": ".claude/audit.head", "destination": "x"},
            ),
            ("mcp__filesystem__write_file", {"path": "notes/todo.md", "content": "x"}),
            ("mcp__filesystem__write_file", {"path": "notes/k/commits/" + M}),
            ("mcp__filesystem__write_file", {"path": "~+/notes/todo.md"}),
            ("mcp__shell__run", {"command": "touch notes/todo.md"}),
            ("mcp__shell__run", {"argv": ["cp", "x", "notes/todo.md"]}),
            ("mcp__x__y", {"files": {"notes/todo.md": "x"}}),
            ("Monitor", {"command": "tail -f notes/todo.md"}),
            ("PowerShell", {"command": "Set-Content notes/todo.md x"}),
        ],
    )
    def test_a_path_into_the_records_is_refused(
        self, project: Path, tool: str, tool_input: dict[str, Any]
    ) -> None:
        marker = fresh_marker(project)
        result = run_pre(project, tool, tool_input)
        assert refused_f504(result), (tool, tool_input, result.stderr)
        assert marker.exists()

    @pytest.mark.parametrize(
        ("tool", "tool_input"),
        [
            ("mcp__filesystem__write_file", {"path": "notes/ok.md", "content": "hi"}),
            ("mcp__shell__run", {"command": "touch notes/ok.md"}),
            ("mcp__github__create_issue", {"title": "t", "body": "x " * 3000}),
            # A subagent's prompt is not read: its own calls come here.
            ("Agent", {"prompt": "look at notes/todo.md"}),
        ],
    )
    def test_other_arguments_are_asked(
        self, project: Path, tool: str, tool_input: dict[str, Any]
    ) -> None:
        fresh_marker(project)
        result = run_pre(project, tool, tool_input)
        assert asked(result), (tool, result.stderr)

    def test_more_than_64_kb_of_short_strings_is_refused_quickly(
        self, project: Path
    ) -> None:
        fresh_marker(project)
        files = [{"path": f"d{i}/f.txt", "content": "word " * 19} for i in range(800)]
        start = time.monotonic()
        result = run_pre(project, "mcp__github__push_files", {"files": files})
        assert refused_f504(result)
        assert "65536" in result.stderr
        assert time.monotonic() - start < 10

    def test_the_most_it_reads_is_read_in_bounded_time(self, project: Path) -> None:
        """Just under the budget, strings that each hold quoted words: the
        slowest reading the hook does."""
        fresh_marker(project)
        content = ('a/b "c d" e ' * 370)[:4090]
        files = [{"path": f"d{i}/f.txt", "content": content} for i in range(15)]
        start = time.monotonic()
        result = run_pre(project, "mcp__github__push_files", {"files": files})
        assert asked(result), result.stderr
        assert time.monotonic() - start < 25

    def test_a_string_over_4096_bytes_is_not_read_as_a_path(
        self, project: Path
    ) -> None:
        """As a Bash command over 4096 bytes: a path cannot be that long."""
        fresh_marker(project)
        result = run_pre(project, "mcp__x__y", {"body": "notes/todo.md " + "x" * 5000})
        assert asked(result), result.stderr


class TestTheDirectoryThatHoldsThem:
    """Defect 4: removing .claude removes the audit log with its head."""

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf .claude",
            "rm -rf ./.claude/",
            "mv .claude x",
            "rm -rf lnk/",
            "rm -rf .git/acs",
            "cp -r fixtures/. .claude/",
            "sh -c 'rm -rf .claude'",
            "rm -rf ~+/.claude",
        ],
    )
    def test_naming_it_is_refused(self, project: Path, command: str) -> None:
        marker = fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stderr)
        assert "holds the layer's records" in result.stderr
        assert marker.exists()

    def test_an_mcp_tool_naming_it_is_refused(self, project: Path) -> None:
        fresh_marker(project)
        result = run_pre(
            project,
            "mcp__filesystem__move_file",
            {"source": ".claude", "destination": "x"},
        )
        assert refused_f504(result)

    @pytest.mark.parametrize(
        "command",
        ["rm -rf .claude/commands", "rm -rf other/.claude", "rm -f .claude/audit.log"],
    )
    def test_other_paths_are_asked(self, project: Path, command: str) -> None:
        fresh_marker(project)
        assert asked(run_pre(project, "Bash", {"command": command}))
