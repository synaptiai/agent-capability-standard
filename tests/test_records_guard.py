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

from tests.brace_readings import BY_VERSION, assert_reading
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


class TestBracesAndAnsiCQuoting:
    """Security round 4, batch 1, #3: path_words split at `{`, `}` and `$`
    and kept `\\xNN` in `$'...'` as written, so the path bash builds from
    `{a,b}` or `$'...'` was never read; one approved `cp -rT
    {fixtures/,.git/acs/check}points` wrote a key and an entry of the
    repository's, after which a shipped commit restored with nothing."""

    @pytest.mark.parametrize(
        "command",
        [
            "cp -rT {fixtures/,.git/acs/check}points",
            "cp -rT fixtures $'.git/acs/check\\x70oints'",
            "cp -rT fixtures $'.git/acs/check\\160oints'",
            "cp -rT fixtures $'.git/acs/check\\u0070oints'",
            "cp -rT fixtures $'.git/acs/check\\U00000070oints'",
            "cp a.txt $'.claude/checkpoint\\x2eok'",
            'cp a.txt $".claude/checkpoint.ok"',
            "touch .claude/audit.he{ad,x}",
            "cp -rT fixtures .git/acs/check{points,}",
            "cp -rT fixtures .git/{acs,x}/checkpoints",
            "cp -r fixtures/. .claud{e..e}/checkpoints/",
            "cp -r fixtures/. .{claude,x}/{a,check{points,x}}/",
            "sh -c 'touch .claude/audit.he{ad,x}'",
            "cp -rT fixtures notes/{k,x}",
        ],
    )
    def test_a_records_path_bash_builds_is_refused(
        self, project: Path, command: str
    ) -> None:
        marker = fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stdout, result.stderr)
        assert marker.exists()

    @pytest.mark.parametrize(
        "command", ["rm -rf .{claude,x}", "mv .git/{acs,old}", "rm -rf $'.cl\\x61ude'"]
    )
    def test_the_directory_that_holds_them(self, project: Path, command: str) -> None:
        fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stderr)

    def test_bash_builds_those_paths(self, project: Path) -> None:
        """The premise, from bash itself."""
        out = subprocess.run(
            [
                "bash",
                "-c",
                "printf '%s\\n' {fixtures/,.git/acs/check}points "
                + "$'.git/acs/check\\x70oints' .claude/audit.he{ad,x} "
                + "$'.cl\\0aude'x",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.split()
        assert ".git/acs/checkpoints" in out
        assert out.count(".git/acs/checkpoints") == 2
        assert ".claude/audit.head" in out
        assert ".clx" in out

    @pytest.mark.parametrize(
        "command",
        [
            "touch file{1..3}.txt",
            "cp a.txt{,.bak}",
            "printf $'a\\tb\\n' > out.txt",
            "touch $'.cl\\0aude'x",
            "mkdir -p src/{a,b}/{c,d}",
            "jq '{a,b}' a.txt > b.txt",
            "touch $'\\u00e9t\\u00e9' {A..z}",
            "echo {a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}",
        ],
    )
    def test_other_braces_and_quotes_are_asked(
        self, project: Path, command: str
    ) -> None:
        fresh_marker(project)
        assert asked(run_pre(project, "Bash", {"command": command})), command

    @pytest.mark.parametrize(
        "command",
        [
            "touch x{1..100000}",
            "touch {a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}",
        ],
    )
    def test_an_expansion_past_the_budget_is_refused(
        self, project: Path, command: str
    ) -> None:
        fresh_marker(project)
        start = time.monotonic()
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), result.stderr
        assert "8192 words" in result.stderr
        assert time.monotonic() - start < 10

    def test_an_mcp_tools_argument_is_read_alike(self, project: Path) -> None:
        fresh_marker(project)
        result = run_pre(
            project,
            "mcp__shell__run",
            {"command": "cp -rT {fixtures/,.git/acs/check}points"},
        )
        assert refused_f504(result), result.stderr

    def test_the_reported_route_end_to_end(self, project: Path) -> None:
        """The copy is refused before it runs; run anyway, it writes the key
        and the entry, after which a restore of M would be a rollback."""
        (project / "fixtures" / "points").mkdir()
        (project / "fixtures" / "points" / "key").write_text("0" * 64)
        fresh_marker(project)
        command = "cp -rT {fixtures/,.git/acs/check}points"
        assert refused_f504(run_pre(project, "Bash", {"command": command}))
        subprocess.run(["bash", "-c", command], cwd=project, check=True, timeout=30)
        key = project / ".git" / "acs" / "checkpoints" / "key"
        assert key.read_text() == "0" * 64


# Words whose brace expansion bash makes in ways a simpler reading gets
# wrong: groups bash closes late, opens later, or leaves as written.
BRACE_CASES = [
    "a{b,c}d",
    "{a},b}",
    "x{a}y,z}",
    "{a{b,c}",
    "{a}{b,c}",
    "{x{a},b}",
    "{a,{b},c}",
    "cu{z},r}l",
    "{-u},cu{r,r}l}",
    ".cl{x},a}ude/aud{y},i}t",
    "{a..c}",
    "{a,b}{c,d}",
    "{{a,b},c}",
    "a{,}b",
    "{}",
    "{},a}",
    "x{},a}",
    "{a}",
    "a{b}c",
    "{a,b",
    "a,b}",
    "{a.,.b}",
    "{a..}",
    "{..a}",
    "{a..},b}",
    "{a...},b}",
    "{a}/../b}",
    "{a},{b},c}",
    "f{a,b}g{,x}",
    "{ab..}x,y}",
    "{a{b},c}d}",
    "{a,b}}",
    "}{a,b}",
    "{{{a,b}",
    "a{b,c,d{e,f}}g",
    "{1..3}",
    "{01..10..3}",
    "{z..a..5}",
    "x{1..3},y}",
    "{a},.claude/check}point.ok",
    "{fixtures/,.git/acs/check}points",
    ".{claude,x}/{a,check{points,x}}/",
    "x" * 62 + "{a..},b}",
]


def _bash_words(word: str) -> list[str]:
    """The non-empty words bash makes of ``word`` (no quotes in it)."""
    out = subprocess.run(
        ["bash", "-c", f"printf '%s\\n' {word}"],
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        timeout=30,
    ).stdout
    return sorted(w for w in out.split("\n") if w)


class TestLateClosingBraceGroups:
    """Security round 4, batch 2 (a sibling of #3, the verifier's brace
    finding): bash closes no group at a `}` before its first comma, so
    `{a},.claude/check}point.ok` gives `a}point.ok` and
    `.claude/checkpoint.ok`. The guard paired each `}` with the nearest `{`,
    kept `{a}` as written and read neither, so the call went to the
    ordinary approval. It now finds each group as bash does (brace_group)
    and expands it as bash does (brace_expand)."""

    def test_bash_builds_those_paths(self, project: Path) -> None:
        """The premise, from bash itself."""
        out = subprocess.run(
            [
                "bash",
                "-c",
                "printf '%s\\n' {a},.claude/check}point.ok "
                + "{a},.git/acs/check}points {a}y,.claude/audit.he}ad {x},.cl}aude",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.split()
        for path in (
            ".claude/checkpoint.ok",
            ".git/acs/checkpoints",
            ".claude/audit.head",
            ".claude",
        ):
            assert path in out, (path, out)

    @staticmethod
    def _driver(tmp_path: Path, call: str) -> Path:
        """The hook's brace functions on their own, then ``call`` on the
        word $1 with its unquoted braces and commas marked as path_words
        marks them (in ``m``)."""
        text = PRE.read_text(encoding="utf-8")
        functions = []
        for name in (
            "ansi_byte",
            "brace_marks",
            "brace_group",
            "brace_expand",
            "brace_words",
        ):
            start = text.index(f"\n{name}() {{\n") + 1
            functions.append(text[start : text.index("\n}\n", start) + 3])
        driver = tmp_path / "braces.sh"
        driver.write_text(
            "export LC_ALL=C\nset -euo pipefail\n"
            + "".join(functions)
            + "RESOLVE_LEFT=262144 BRACE_LEFT=8192 BRACE_SCAN_LEFT=65536\n"
            + "PATH_WORDS=()\n"
            + "m=\"${1//\\{/$'\\001'}\"; m=\"${m//,/$'\\002'}\"; "
            + "m=\"${m//\\}/$'\\003'}\"\n"
            + call,
            encoding="utf-8",
        )
        return driver

    @staticmethod
    def _run(driver: Path, *args: str) -> list[str]:
        ours = subprocess.run(
            ["bash", str(driver), *args], capture_output=True, text=True, timeout=30
        )
        assert ours.returncode == 0, (args, ours.stderr)
        return sorted(w for w in ours.stdout.split("\n") if w)

    def test_the_reading_is_bashs(self, tmp_path: Path) -> None:
        """The hook's brace_words gives the words the installed bash gives,
        for each case; for a word bash 5.2 and 5.3 read differently, the
        words of both, which hold the installed bash's (brace_readings)."""
        driver = self._driver(
            tmp_path, 'brace_words "$m"\nprintf \'%s\\n\' "${PATH_WORDS[@]}"\n'
        )
        for word in [*BRACE_CASES, *BY_VERSION]:
            assert_reading(word, self._run(driver, word), _bash_words(word))

    def test_each_pass_is_one_versions_reading(self, tmp_path: Path) -> None:
        """brace_expand read as bash 5.2 and as bash 5.3: each version's
        words of a word the two read differently, and the same words of
        every other case (so brace_words gives bash's own there, whichever
        bash is installed)."""
        driver = self._driver(
            tmp_path,
            'BRACE_MODE="$2"\nbrace_expand "$m"\n'
            + 'for w in "${BRACED[@]}"; do w="${w//$\'\\001\'/\\{}"; '
            + "w=\"${w//$'\\002'/,}\"; printf '%s\\n' \"${w//$'\\003'/\\}}\"; done\n",
        )
        for word in BRACE_CASES:
            assert self._run(driver, word, "5.2") == self._run(driver, word, "5.3"), (
                word
            )
        for word, (v52, v53) in BY_VERSION.items():
            assert self._run(driver, word, "5.2") == sorted(v52), word
            assert self._run(driver, word, "5.3") == sorted(v53), word

    @pytest.mark.parametrize(
        "command",
        [
            "tee {a},.claude/check}point.ok",
            "cp -rT fixtures {a},.git/acs/check}points",
            "touch {a}y,.claude/audit.he}ad",
            "rm -rf {x},.cl}aude",
            "cp -rT fixtures {a}..,.git/acs/check}points",
            "sh -c 'tee {a},.claude/check}point.ok'",
        ],
    )
    def test_a_records_path_a_late_group_builds_is_refused(
        self, project: Path, command: str
    ) -> None:
        """They were asked (the ordinary approval)."""
        marker = fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stdout, result.stderr)
        assert marker.exists()

    @pytest.mark.parametrize(
        ("link", "command"),
        [
            # Bash 5.3: {x..ya}/key (and {x..yb}/key); 5.2 keeps the word
            # as written.
            ("{x..ya}", "touch {x..y{a..b}}/key"),
            # Bash 5.2: x..yc/key (and x..yd/key); 5.3 keeps the braces:
            # {x..yc}/key.
            ("x..yc", "touch {x..y{c,d}}/key"),
        ],
    )
    def test_a_records_path_one_bash_version_builds_is_refused(
        self, project: Path, link: str, command: str
    ) -> None:
        """The hook runs under whichever bash the user has, so a word is
        read as bash 5.2 and as bash 5.3 expand it. Read as 5.2 alone, the
        first was asked: on bash 5.3 it writes the checkpoint key through
        the link to the git directory's acs/checkpoints/ the repository
        ships."""
        (project / link).symlink_to(".git/acs/checkpoints")
        marker = fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stdout, result.stderr)
        assert marker.exists()

    @pytest.mark.parametrize(
        "command",
        [
            "touch {x} a{b}c",
            "touch {x},y",
            "jq '{a},b}' a.txt > b.txt",
            "touch {a,b},c}",
            "touch {x{a},b}",
            'jq \'{"a":{"b":1},"c":2}\' a.txt > b.txt',
            "jq '{name: .a, meta: {x: .b}, y: 1}' a.txt > b.txt",
        ],
    )
    def test_other_braces_are_asked(self, project: Path, command: str) -> None:
        """Bash builds no records path from these (the jq filters are read
        again, as a shell would read them)."""
        fresh_marker(project)
        assert asked(run_pre(project, "Bash", {"command": command})), command


class TestTheReadingsTime:
    """Security round 4, batch 1, #2: within the 65536-byte budget, a word
    that opens with `-` gave one candidate per position of its option
    cluster (up to 4090 texts of up to 4 KB, none charged to the budget),
    and empty strings, which count no bytes, had no bound: the reported
    MCP edit took 44 s (rc 124 under hooks.json's 30 s), the verifier's
    quoted sibling 51.7 s, 110,000 empty strings 32 s."""

    def _mcp(self, project: Path, tool_input: Any) -> subprocess.CompletedProcess[str]:
        start = time.monotonic()
        result = run_pre(
            project, "mcp__filesystem__edit_file", tool_input, "bypassPermissions"
        )
        assert time.monotonic() - start < 15, result.stderr
        return result

    def test_long_option_clusters(self, project: Path) -> None:
        edits = [
            {"oldText": "-" + "a" * 4070, "newText": "-" + "b" * 4070} for _ in range(8)
        ]
        result = self._mcp(project, {"path": "src/app.py", "edits": edits})
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), result.stderr

    def test_quoted_option_clusters(self, project: Path) -> None:
        """Three readings of each: the text, its dequoted word, the word
        nested in that."""
        text = "-" + "a" * 4060 + "'\"'"
        result = self._mcp(project, {"path": "src/app.py", "edits": [text] * 16})
        assert result.returncode == 2
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), result.stderr

    @pytest.mark.parametrize("count", [4097, 110_000])
    def test_more_than_4096_strings_are_refused(
        self, project: Path, count: int
    ) -> None:
        result = self._mcp(project, {"path": "x.txt", "args": [""] * count})
        assert refused_f504(result), result.stderr
        assert "4096 strings" in result.stderr

    def test_the_most_strings_it_reads(self, project: Path) -> None:
        """4096 strings of quoted words, each read whole, as words and
        nested: the slowest shape found at the count bound (about 4 s
        here)."""
        fresh_marker(project)
        start = time.monotonic()
        result = run_pre(project, "mcp__x__y", {"args": ["'a b' \"c d\""] * 4094})
        assert asked(result), result.stderr
        assert time.monotonic() - start < 25

    def test_a_cluster_still_names_a_path_it_holds(self, project: Path) -> None:
        """Only the texts after an option letter that can name a file are
        read: one whose first component exists, or an absolute one."""
        fresh_marker(project)
        for command in (
            "cp -r -" + "r" * 300 + "tnotes/k fixtures/key",
            "sort -" + "u" * 300 + "onotes/todo.md a.txt",
            "rm -" + "f" * 300 + "r.claude",
        ):
            assert refused_f504(run_pre(project, "Bash", {"command": command})), command


# Words enough that the resolved paths (each <project>/<word>) pass the 64 KB
# a pipe holds, whatever the temporary directory's length.
PAD = " && echo {1..4000} > /dev/null"
GROUPS = " z{a,b}" + "z{a,b}" * 11


class TestManyResolvedPaths:
    """Security round 5, batch 1, #1: the guard piped the resolved paths
    into `grep -q` under pipefail. grep stopped at the first match, printf
    (more than a pipe holds still to write) died of SIGPIPE, and pipefail
    read the pipeline as no match: a call that names a records path and a
    few thousand more words was asked as an ordinary mutate."""

    @pytest.mark.parametrize(
        "command",
        [
            "cp fixtures/key notes/todo.md" + PAD,
            "cp -r fixtures/key fixtures/commits notes/k/" + PAD,
            "cat a.txt > .claude/check{p,q}oint.ok" + GROUPS,
            "cp a.txt .git/acs/check{points,}/key" + PAD,
            "touch ~+/notes/todo.md" + PAD,
        ],
    )
    def test_a_records_path_among_many_is_refused(
        self, project: Path, command: str
    ) -> None:
        marker = fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stdout, result.stderr)
        assert "leads there" in result.stderr
        assert marker.exists()

    @pytest.mark.parametrize(
        "command",
        ["rm -rf .clau{d,x}e" + GROUPS, "rm -rf lnk" + PAD, "rm -rf .git/acs" + PAD],
    )
    def test_the_directory_that_holds_them_among_many_is_refused(
        self, project: Path, command: str
    ) -> None:
        marker = fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stdout, result.stderr)
        assert "holds the layer's records" in result.stderr
        assert marker.exists()

    def test_an_mcp_tools_many_arguments_are_read_alike(self, project: Path) -> None:
        marker = fresh_marker(project)
        tool_input = {"path": "notes/todo.md", "pad": [str(i) for i in range(4000)]}
        result = run_pre(project, "mcp__filesystem__write_file", tool_input)
        assert refused_f504(result), result.stderr
        assert marker.exists()

    def test_many_other_paths_are_asked(self, project: Path) -> None:
        fresh_marker(project)
        result = run_pre(project, "Bash", {"command": "cp a.txt notes/x.txt" + PAD})
        assert asked(result), result.stderr

    def test_a_grep_that_cannot_answer_blocks(
        self, project: Path, tmp_path: Path
    ) -> None:
        """Any answer of grep but a match or none (here an error, 2)
        blocks: the guard cannot tell."""
        tools = tmp_path / "tools"
        tools.mkdir()
        grep = tools / "grep"
        grep.write_text("#!/bin/sh\nexit 2\n")
        grep.chmod(0o755)
        fresh_marker(project)
        result = run_pre(
            project,
            "Bash",
            {"command": "touch notes/x.txt"},
            PATH=f"{tools}:{os.environ['PATH']}",
        )
        assert result.returncode == 2, result.stdout
        assert result.stderr.startswith("R407 SAFETY_CHECK_FAILED: "), result.stderr


class TestPathsReadExactly:
    """Security round 5, batch 1, #2: `$(readlink ...)` strips every line
    break that ends the output, so a link to `evil\\n` was followed to `evil`,
    another file: one approved write to a shipped name forged the key and a
    commit entry. The same stripping read a cwd, and git's answers, as
    another directory."""

    def _links(self, project: Path) -> None:
        os.symlink("evil\n", project / "nl")
        os.symlink(".git/acs/checkpoints/key", project / "evil\n")
        os.symlink("e2\n", project / "nl2")
        os.symlink(f".git/acs/checkpoints/commits/{M}", project / "e2\n")

    @pytest.mark.parametrize(
        "command",
        [
            "touch nl",
            "cat fixtures/key > nl; cat fixtures/commits/* > nl2",
            "cp a.txt ./nl2",
        ],
    )
    def test_a_link_to_a_name_ending_in_a_line_break_is_followed(
        self, project: Path, command: str
    ) -> None:
        self._links(project)
        marker = fresh_marker(project)
        result = run_pre(project, "Bash", {"command": command})
        assert refused_f504(result), (command, result.stdout, result.stderr)
        assert "leads there" in result.stderr
        assert marker.exists()

    @pytest.mark.parametrize("tool", ["Write", "mcp__filesystem__write_file"])
    def test_other_tools_follow_it_alike(self, project: Path, tool: str) -> None:
        self._links(project)
        fresh_marker(project)
        key = "file_path" if tool == "Write" else "path"
        result = run_pre(project, tool, {key: str(project / "nl"), "content": "a" * 64})
        assert refused_f504(result), result.stderr

    def test_a_link_to_another_such_name_is_asked(self, project: Path) -> None:
        os.symlink("plain\n", project / "nl")
        (project / "plain\n").write_text("x")
        (project / "plain").symlink_to(".git/acs/checkpoints/key")
        fresh_marker(project)
        assert asked(run_pre(project, "Bash", {"command": "touch nl"}))

    def test_a_cwd_ending_in_a_line_break_is_that_directory(
        self, project: Path
    ) -> None:
        here = project / "d\n"
        here.mkdir()
        (here / "n").symlink_to("../.git/acs/checkpoints/key")
        fresh_marker(project)
        payload_cwd = {"cwd": str(here)}
        result = subprocess.run(
            ["bash", str(PRE)],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "touch n"},
                    "permission_mode": "default",
                    "tool_use_id": "toolu_x",
                    **payload_cwd,
                }
            ),
            capture_output=True,
            text=True,
            env={**os.environ, **ENV, "CLAUDE_PROJECT_DIR": str(project)},
            timeout=120,
        )
        assert refused_f504(result), result.stderr

    def _other_repository(self, project: Path) -> tuple[Path, str]:
        """`r\\n`, a repository of its own holding the project's recorded
        commit, beside a plain directory `r` of the project."""
        (project / "r").mkdir()
        other = project / "r\n"
        git(project, "clone", "-q", str(project), str(other))
        (other / "app.txt").write_text("other\n")
        commit = git(other, "stash", "create")
        enter_checkpoint_commit(project / ".git", commit)
        return other, commit

    def test_a_restore_run_in_another_repository_is_no_rollback(
        self, project: Path
    ) -> None:
        """The commit is recorded in the project, but the call runs in `r\\n`,
        another repository: a mutate (here F501, no marker), not a rollback."""
        other, commit = self._other_repository(project)
        result = subprocess.run(
            ["bash", str(PRE)],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": f"git stash apply {commit}"},
                    "cwd": str(other),
                    "permission_mode": "bypassPermissions",
                    "tool_use_id": "toolu_x",
                }
            ),
            capture_output=True,
            text=True,
            env={**os.environ, **ENV, "CLAUDE_PROJECT_DIR": str(project)},
            timeout=120,
        )
        assert result.returncode == 2, result.stdout
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), result.stderr

    def test_a_checkpoint_taken_in_another_repository_writes_no_marker(
        self, project: Path
    ) -> None:
        other, commit = self._other_repository(project)
        taken = subprocess.run(
            ["bash", str(TAKE)],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "git stash create"},
                    "tool_response": {"stdout": commit},
                    "cwd": str(other),
                }
            ),
            capture_output=True,
            text=True,
            env={**os.environ, **ENV, "CLAUDE_PROJECT_DIR": str(project)},
            timeout=60,
        )
        assert taken.returncode == 0
        assert not (project / ".claude" / "checkpoint.ok").exists()
