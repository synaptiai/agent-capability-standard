"""The plugin hook's classification is derived from the SDK mapper's
(STANDARD 1.2.0 section 5.18.3): the tools it lets pass are mapper tools
whose capability needs neither a checkpoint nor approval, and every other
tool is unbound for both (section 5.18.2); its read-only list is a subset of
_READ_ONLY_COMMANDS, its git stash table equals _GIT_STASH_CLASSES, and for
each listed command that _writes has a rule for, an argument that writes
makes both the mapper and the hook treat the call as a gated mutation."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from grounded_agency.capabilities import mapper

HOOK = (
    Path(__file__).resolve().parents[1] / "hooks" / "pretooluse_require_checkpoint.sh"
)
TEXT = HOOK.read_text(encoding="utf-8")


def _array(name: str) -> list[str]:
    match = re.search(rf"^{name}=\((.*)\)$", TEXT, re.MULTILINE)
    assert match, f"{name}=(...) not found in {HOOK.name}"
    return shlex.split(match.group(1))


def test_read_only_list_is_a_subset_of_the_mappers() -> None:
    listed = _array("READ_ONLY")
    assert listed
    assert set(listed) <= mapper._READ_ONLY_COMMANDS


def test_ungated_tools_need_neither_a_checkpoint_nor_approval_in_the_mapper() -> None:
    listed = _array("UNGATED_TOOLS")
    assert listed
    classify = mapper.ToolCapabilityMapper()
    for name in listed:
        assert name in mapper._TOOL_MAPPINGS, name
        mapping = classify.map_tool(name, {})
        assert not mapping.requires_checkpoint and not mapping.requires_approval, name


def test_every_tool_the_mapper_gates_is_gated_by_the_hook() -> None:
    """A tool the mapper gates (Write, Edit, ..., and every tool it does not
    know: Monitor, PowerShell, MCP tools) is not on UNGATED_TOOLS, so the
    hook gates it too."""
    listed = set(_array("UNGATED_TOOLS"))
    classify = mapper.ToolCapabilityMapper()
    names = [*mapper._TOOL_MAPPINGS, "Monitor", "PowerShell", "mcp__github__push_files"]
    for name in names:
        mapping = classify.map_tool(name, {})
        if mapping.requires_checkpoint or mapping.requires_approval:
            assert name not in listed, name


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize("tool", ["Monitor", "PowerShell", "mcp__github__push_files"])
def test_an_unbound_tool_is_gated_in_both(tmp_path: Path, tool: str) -> None:
    classified = mapper.ToolCapabilityMapper().map_tool(tool, {"command": "ls"})
    assert classified is mapper.UNCLASSIFIED_TOOL
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": "ls"}}),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 2
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")


def test_stash_table_equals_the_mappers() -> None:
    table = dict(entry.split("=", 1) for entry in _array("GIT_STASH_CLASSES"))
    assert table == mapper._GIT_STASH_CLASSES


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize(
    "command",
    [
        "git log --output=f",
        "git status --output=x",
        "file -C x",
        "file -bC x",
        "file --compile x",
    ],
)
def test_an_argument_that_writes_is_gated_in_both(tmp_path: Path, command: str) -> None:
    assert mapper._writes(command.split())
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 2
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize(
    "command", ["ls -la", "git status", "git rev-parse HEAD", "file x"]
)
def test_read_only_in_both(tmp_path: Path, command: str) -> None:
    classified = mapper.ToolCapabilityMapper().map_tool("Bash", {"command": command})
    assert classified.capability_id == "observe"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0


def _hook(
    tmp_path: Path, command: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    payload: dict[str, object] = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "permission_mode": "bypassPermissions",
    }
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize(
    "command",
    [
        # Quotes the shell removes: the option is the same.
        'git log -1 "--format=%x7b%x22a%x22: 1%x7d" "--output=.claude/s.json"',
        'git diff "--output=pwn.txt"',
        "git diff --out''put=pwn.txt",
        'git stash show -p "--output=x"',
        "file '-C' -m f",
        # Abbreviations getopt_long and git accept.
        "git diff --outp=x",
        "git log --out=x",
        "file --compi -m mymagic",
        # A pathname expansion may be any file name, an option included.
        "git diff *",
        "file *",
        # An unbalanced quote.
        "git log 'x",
    ],
)
def test_a_quoted_abbreviated_or_expanded_option_is_gated_in_both(
    tmp_path: Path, command: str
) -> None:
    classified = mapper.ToolCapabilityMapper().map_tool("Bash", {"command": command})
    assert classified.requires_checkpoint and classified.requires_approval, command
    result = _hook(tmp_path, command)
    assert result.returncode == 2, command
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize(
    "command",
    [
        'grep "a b" f',
        'git log --format="%H %s" -3',
        "git log -- '*.py'",
        "ls *.md",
    ],
)
def test_quoted_and_expanded_read_only_words_stay_read_only(
    tmp_path: Path, command: str
) -> None:
    classified = mapper.ToolCapabilityMapper().map_tool("Bash", {"command": command})
    assert classified.capability_id == "observe", command
    assert _hook(tmp_path, command).returncode == 0, command


def test_both_checkpoint_hooks_split_words_alike() -> None:
    """posttooluse_take_checkpoint.sh reads a `git stash create` line as the
    pre-tool-use hook does: the same split_words function."""
    take = (HOOK.parent / "posttooluse_take_checkpoint.sh").read_text(encoding="utf-8")
    pattern = re.compile(r"^split_words\(\) \{\n.*?^\}\n", re.MULTILINE | re.DOTALL)
    pre_fn, take_fn = pattern.search(TEXT), pattern.search(take)
    assert pre_fn and take_fn
    assert pre_fn.group(0) == take_fn.group(0)


def test_both_checkpoint_hooks_run_git_alike() -> None:
    """Both hooks run git as hgit does (no fsmonitor program, no hook, no
    lazy fetch), the same options as the SDK's SAFE_GIT_OPTIONS, and take
    the same git directories for ones git made for a work tree."""
    from grounded_agency.utils.git import SAFE_GIT_OPTIONS

    take = (HOOK.parent / "posttooluse_take_checkpoint.sh").read_text(encoding="utf-8")
    pattern = re.compile(r"^hgit\(\) \{\n.*?^\}\n", re.MULTILINE | re.DOTALL)
    pre_fn, take_fn = pattern.search(TEXT), pattern.search(take)
    assert pre_fn and take_fn
    assert pre_fn.group(0) == take_fn.group(0)
    assert " ".join(SAFE_GIT_OPTIONS) in pre_fn.group(0)
    assert "GIT_NO_LAZY_FETCH=1" in pre_fn.group(0)
    made = "*/.git | */.git/worktrees/* | */.git/modules/*)"
    assert made in TEXT and made in take
    rollback = (HOOK.parents[1] / "skills" / "rollback" / "SKILL.md").read_text()
    assert made.replace(" ", "").rstrip(")") in rollback.replace(" ", "")
    assert "git -c core.fsmonitor=false -c core.hooksPath=/dev/null" in rollback


def test_the_tools_that_load_unseen_commands_are_gated_in_both() -> None:
    """Skill, Agent and Task: the hook gates them (they are not on
    UNGATED_TOOLS and its case names them), the mapper gives them the worst
    case."""
    listed = set(_array("UNGATED_TOOLS"))
    classify = mapper.ToolCapabilityMapper()
    for name in sorted(mapper._UNSEEN_COMMANDS):
        assert name not in listed, name
        assert classify.map_tool(name, {}).capabilities[1:] == ("mutate", "send")
    assert "  Skill | Agent | Task)\n" in TEXT


needs_git_and_jq = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("git") is None,
    reason="the hook needs jq; a repository needs git",
)


@needs_git_and_jq
@pytest.mark.parametrize(
    "command",
    [
        "git show HEAD~1:big.txt",
        "git show 7365637265742d646174612d6c65616b65642121",
        "git log -p",
        "git diff HEAD~1 --stat",
        "git status",
        "git stash list",
        "git stash show -p",
    ],
)
def test_a_git_read_in_a_partial_clone_is_gated_in_both(
    tmp_path: Path, partial_clone: Path, command: str
) -> None:
    """In a partial clone git fetches what a read lacks from the promisor
    remote (STANDARD 1.2.0 section 5.18.3): the call's directory, the hook
    input's `cwd`, decides it in both layers."""
    project = tmp_path / "project"
    project.mkdir()
    for cwd in (partial_clone, partial_clone / "sub"):
        cwd.mkdir(exist_ok=True)
        classified = mapper.ToolCapabilityMapper().map_tool(
            "Bash", {"command": command}, str(cwd)
        )
        assert classified.capabilities == ("mutate", "send"), command
        result = _hook(project, command, cwd)
        assert result.returncode == 2, command
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command


@needs_git_and_jq
def test_without_a_cwd_the_hook_asks_about_the_project(
    tmp_path: Path, partial_clone: Path
) -> None:
    result = _hook(partial_clone, "git log -p")
    assert result.returncode == 2
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")


@needs_git_and_jq
def test_a_directory_git_cannot_answer_for_is_gated_in_both(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-directory"
    classified = mapper.ToolCapabilityMapper().map_tool(
        "Bash", {"command": "git log"}, str(missing)
    )
    assert classified.capabilities == ("mutate", "send")
    result = _hook(tmp_path, "git log", missing)
    assert result.returncode == 2
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")


@needs_git_and_jq
def test_in_a_full_clone_and_for_other_commands_both_observe(
    tmp_path: Path, partial_clone: Path
) -> None:
    full = tmp_path / "full"
    full.mkdir()
    subprocess.run(["git", "init", "-q", str(full)], check=True, timeout=60)
    for cwd, command in (
        (full, "git log -p"),
        (full, "git stash list"),
        (partial_clone, "ls -la"),
    ):
        classified = mapper.ToolCapabilityMapper().map_tool(
            "Bash", {"command": command}, str(cwd)
        )
        assert classified.capabilities == ("observe",), command
        assert _hook(tmp_path, command, cwd).returncode == 0, command


@needs_git_and_jq
def test_a_checkpoint_stays_possible_in_a_partial_clone(
    tmp_path: Path, partial_clone: Path
) -> None:
    """`git stash create` reads only what the local state holds: it keeps
    its class in both, so the plugin can still take a checkpoint there."""
    classified = mapper.ToolCapabilityMapper().map_tool(
        "Bash", {"command": "git stash create"}, str(partial_clone)
    )
    assert classified.capabilities == ("checkpoint",)
    assert _hook(tmp_path, "git stash create", partial_clone).returncode == 0


# A first word that holds a blank names a program with that name, which bash
# looks up in PATH as it stands: `"git status"` is no git command.
QUOTED_NAMES = [
    '"git status"',
    '"git status" --output=/tmp/x',
    '"git log" -p',
    "'git status'",
    'g"it status"',
    'git" "status',
    '"git diff"',
    '"git show" HEAD',
    '"git rev-parse" HEAD',
    '"git ls-files"',
    '"git branch"',
    '"git remote" add o x',
    '"pip list"',
    '"pip show" x',
    '"git\tstatus"',
    "./ls",
    "/bin/ls",
]


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize("command", QUOTED_NAMES)
def test_a_command_name_with_a_blank_or_a_slash_is_gated_in_both(
    tmp_path: Path, command: str
) -> None:
    classified = mapper.ToolCapabilityMapper().map_tool("Bash", {"command": command})
    assert classified.capabilities == ("mutate", "send"), command
    assert classified.requires_checkpoint and classified.requires_approval
    result = _hook(tmp_path, command)
    assert result.returncode == 2, command
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize(
    "command", ["git status", 'git "status"', '"git" "status"', '"ls" -la', "pip list"]
)
def test_a_quoted_name_without_a_blank_is_still_the_command(
    tmp_path: Path, command: str
) -> None:
    classified = mapper.ToolCapabilityMapper().map_tool("Bash", {"command": command})
    assert classified.capabilities == ("observe",), command
    if not command.startswith("pip"):  # pip is on the mapper's list only
        assert _hook(tmp_path, command).returncode == 0, command


def test_bash_runs_a_program_named_with_a_blank(tmp_path: Path) -> None:
    """The premise: bash runs `"git status"` as the program of that name
    on PATH, not git."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    program = bin_dir / "git status"
    program.write_text('#!/bin/sh\necho "not git: $*"\n')
    program.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", '"git status" --output=x'],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        timeout=30,
    )
    assert result.stdout == "not git: --output=x\n"


# A quoted or escaped operator is a word the shell passes on (shlex gives it
# as the bare operator): it must not hide the word after it.
QUOTED_OPERATORS = [
    "find in.txt '<' -execdir sh -c 'id > PWNED' sh {} +",
    "find in.txt \\< -execdir sh {} +",
    'find in.txt "<" -execdir sh {} +',
    "find . ! -name '<' -delete",
    "find . -not -name '<' -execdir rm {} +",
    "find in.txt '<' -fprint OUTF",
    "sort '<' -o OUT in.txt",
    "git log '<' --output=FILE",
    "find . -name ';' -delete",
    "find . -name '|' -delete",
    "find . -name '&&' -delete",
    "find . -name \\; -delete",
    "find . -name '>' -fprint OUT",
    "sort ';' -o OUT f",
]


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
@pytest.mark.parametrize("command", QUOTED_OPERATORS)
def test_a_quoted_operator_hides_no_word_in_either(
    tmp_path: Path, command: str
) -> None:
    classified = mapper.ToolCapabilityMapper().map_tool("Bash", {"command": command})
    assert classified.capability_id != "observe", command
    assert classified.requires_checkpoint and classified.requires_approval, command
    result = _hook(tmp_path, command)
    assert result.returncode == 2, command
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command
