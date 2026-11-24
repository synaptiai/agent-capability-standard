"""The program a command name runs (security round 5, batch 1, #3).

A command the read-only list, `git stash create` or a recorded restore lets
pass names its program by a word with no slash, and bash runs the first
executable file of that name on PATH. Where PATH holds a relative entry
(`node_modules/.bin`), an empty one (a leading colon: the working
directory) or one in the project (an activated virtual environment), a file
the repository ships in place of `git`, `cat` or `ls` ran with no
checkpoint and no approval. The plugin's PreToolUse hook and the SDK mapper
now take the worst case there, alike.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from grounded_agency import GroundedAgentAdapter
from grounded_agency.capabilities import mapper as mapper_module
from grounded_agency.capabilities.mapper import ToolCapabilityMapper

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("jq") is None,
    reason="the hook needs jq; a repository needs git",
)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}
SYSTEM_PATH = os.environ.get("PATH", "/usr/bin:/bin")
# The programs the pre-tool-use hook runs on a Bash call with no marker.
HOOK_PROGRAMS = ("bash", "jq", "git", "cat", "readlink", "grep", "sleep")


def _program(path: Path) -> None:
    """A program that writes a file named for it when it runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\ntouch '{path.name}.RAN'\n")
    path.chmod(0o755)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A repository shipping node_modules/.bin/git and cat, and ./ls."""
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(
        ["git", "init", "-q", str(project)], check=True, env={**os.environ, **GIT_ENV}
    )
    _program(project / "node_modules" / ".bin" / "git")
    _program(project / "node_modules" / ".bin" / "cat")
    _program(project / "ls")
    (project / "README.md").write_text("r\n")
    return project


def hook(project: Path, command: str, path: str) -> subprocess.CompletedProcess[str]:
    """The pre-tool-use hook as Claude Code starts it, with that PATH in
    its environment (the one the agent's commands get too)."""
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(project),
        "permission_mode": "bypassPermissions",
        "tool_use_id": "toolu_x",
    }
    return subprocess.run(
        ["/bin/sh", "-c", str(PRE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=project,
        env={
            **os.environ,
            **GIT_ENV,
            "PATH": path,
            "CLAUDE_PROJECT_DIR": str(project),
        },
        timeout=120,
    )


def mapped(project: Path, command: str, path: str) -> tuple[str, ...]:
    mapper = ToolCapabilityMapper()
    mapper.command_path = path
    mapper.project_dir = str(project)
    return mapper.map_tool("Bash", {"command": command}, str(project)).capabilities


GATED = [
    ("node_modules/.bin:{system}", "git status"),
    ("node_modules/.bin:{system}", "git log -1"),
    ("node_modules/.bin:{system}", "cat README.md"),
    ("node_modules/.bin:{system}", "git stash create"),
    ("node_modules/.bin:{system}", "git stash list"),
    (":{system}", "ls"),
    ("/nonexistent::{system}", "ls -l"),
    ("./node_modules/.bin/:{system}", "cat README.md"),
    ("{project}/node_modules/.bin:{system}", "git status"),
    ("{project}/node_modules/.bin:{system}", "cat README.md"),
]


@pytest.mark.parametrize(("path", "command"), GATED)
def test_a_program_the_repository_may_hold_is_gated(
    project: Path, path: str, command: str
) -> None:
    """The hook refuses it (no marker: F501, before any approval), and the
    mapper gives it the worst case; neither runs the program."""
    spelled = path.format(system=SYSTEM_PATH, project=project)
    result = hook(project, command, spelled)
    assert result.returncode == 2, (command, spelled, result.stdout)
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), result.stderr
    assert mapped(project, command, spelled)[-2:] == ("mutate", "send")
    assert not list(project.glob("*.RAN"))


def test_a_link_out_of_the_project_into_it_is_followed(
    project: Path, tmp_path: Path
) -> None:
    """An entry outside the project whose `git` is a link to a file in it."""
    outside = tmp_path / "bin"
    outside.mkdir()
    (outside / "git").symlink_to(project / "node_modules" / ".bin" / "git")
    path = f"{outside}:{SYSTEM_PATH}"
    assert hook(project, "git status", path).returncode == 2
    assert mapped(project, "git status", path)[-2:] == ("mutate", "send")


@pytest.mark.parametrize(
    ("path", "command"),
    [
        ("{system}", "git status"),
        ("{system}", "cat README.md"),
        ("{system}", "ls"),
        # An empty entry after the system's: bash finds its program first.
        ("{system}:", "ls"),
        # A relative entry with no file of that name: bash goes on.
        ("node_modules/.bin:{system}", "ls"),
        ("nothere:{system}", "git status"),
        # An entry in the project with no file of that name.
        ("{project}/node_modules/.bin:{system}", "ls"),
    ],
)
def test_the_systems_program_still_reads(
    project: Path, path: str, command: str
) -> None:
    spelled = path.format(system=SYSTEM_PATH, project=project)
    result = hook(project, command, spelled)
    assert result.returncode == 0 and result.stdout == "", (command, result.stderr)
    assert mapped(project, command, spelled) == ("observe",)


def test_a_name_found_nowhere_is_gated(project: Path, tmp_path: Path) -> None:
    """bash cannot run it; the layer cannot tell which program would. The
    PATH holds the programs the hook runs, and no ls."""
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in HOOK_PROGRAMS:
        found = shutil.which(name)
        assert found, name
        (tools / name).symlink_to(found)
    result = hook(project, "ls", str(tools))
    assert result.returncode == 2, result.stdout
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), result.stderr
    assert mapped(project, "ls", str(tools))[-2:] == ("mutate", "send")


def test_a_project_that_holds_the_home_directory_keeps_its_programs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As the hooks' own PATH reads it: a home directory is no
    repository's, so its tools (~/.local/bin) are the user's."""
    home = tmp_path / "home"
    _program(home / ".local" / "bin" / "git")
    monkeypatch.setattr(mapper_module, "_home_directory", lambda: str(home))
    path = f"{home}/.local/bin:{SYSTEM_PATH}"
    assert not mapper_module.command_may_be_content("git", str(home), path, str(home))
    assert not mapper_module.command_may_be_content(
        "git", str(home), path, str(tmp_path)
    )
    assert mapper_module.command_may_be_content(
        "git", str(home), path, str(home / ".local")
    )


def test_the_adapter_reads_the_clis_path_and_project(
    adapter: GroundedAgentAdapter, project: Path
) -> None:
    """The CLI runs its commands with this process's environment and
    options.env over it, in options.cwd."""
    adapter.wrap_options(
        ClaudeAgentOptions(
            cwd=str(project), env={"PATH": f"node_modules/.bin:{SYSTEM_PATH}"}
        )
    )
    assert adapter.mapper.command_path == f"node_modules/.bin:{SYSTEM_PATH}"
    assert adapter.mapper.project_dir == str(project)
    mapping = adapter.mapper.map_tool("Bash", {"command": "git status"}, str(project))
    assert mapping.capabilities[-2:] == ("mutate", "send")
    adapter.wrap_options(ClaudeAgentOptions())
    assert adapter.mapper.command_path is None
    assert adapter.mapper.project_dir is None
