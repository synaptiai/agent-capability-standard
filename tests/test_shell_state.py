"""A read-only command that sets shell state is not read-only (STANDARD
1.2.0 section 5.18.3).

bash's ``printf`` builtin takes one option, ``-v NAME``, which assigns its
output to the shell variable NAME instead of printing it, and the later
commands of the same line run with that variable: ``PATH`` or ``HOME``
(which program, or which configuration, a later command uses), or an array
element, whose subscript bash evaluates as arithmetic, which runs a
``$(...)`` the format wrote (``\\044`` and ``%s`` with ``$`` write one
without a ``$`` in the line). The SDK mapper classifies each simple command
of a line on its own, so a line of allow-listed commands was ``observe``.
``printf`` with any option, or with a word bash expands (which may become
``-v``), now takes the worst case in the mapper and is gated in the plugin's
hook, which reads only a line of one command."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.capabilities import mapper
from grounded_agency.capabilities.mapper import ToolCapabilityMapper
from tests.conftest import BASH_4

HOOK = (
    Path(__file__).resolve().parents[1] / "hooks" / "pretooluse_require_checkpoint.sh"
)

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
needs_hook = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the shell hook needs bash and jq",
)

ARITHMETIC = (
    "printf -v y 'a[\\044(echo PWNED > pwned_arith.txt)]' && printf -v 'z[y]' 1"
)
PERCENT = "printf -v y 'a[%s(echo PWNED > pwned_pct.txt)]' '$' && printf -v 'z[y]' 1"
PATH_LINE = "printf -v PATH . ; ls"
HOME_LINE = "printf -v HOME . && git status"

LINES = [
    ARITHMETIC,
    PERCENT,
    PATH_LINE,
    HOME_LINE,
    "printf -vPATH . && ls",
    "printf -v IFS x && ls",
    "printf -v LESSOPEN x && cat a",
    "printf -- x && ls",
    "printf * && ls",
]

# Single commands: the hook reads only these.
SINGLE = [
    "printf -v PATH .",
    "printf -vPATH .",
    "printf -- -v",
    "printf '-v' x y",
    "printf *",
    "printf -v[a] x",
]

READ_ONLY = ["printf x", "printf '%s' a -v b", 'printf "%d" 3']


@pytest.fixture
def shipped(tmp_path: Path) -> Path:
    """A directory as a repository can ship it: an executable ``ls`` and a
    ``.gitconfig`` whose core.fsmonitor writes a sentinel, in a git
    repository."""
    work = tmp_path / "work"
    work.mkdir()
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(tmp_path)}
    subprocess.run(
        ["git", "init", "-q"], cwd=work, env=env, check=True, capture_output=True
    )
    ls = work / "ls"
    ls.write_text("#!/bin/sh\necho PWNED > pwned_ls.txt\n")
    ls.chmod(ls.stat().st_mode | stat.S_IXUSR)
    (work / ".gitconfig").write_text(
        '[core]\n\tfsmonitor = "echo PWNED > pwned_fsmon.txt; false"\n'
    )
    return work


@needs_bash
@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
@pytest.mark.parametrize(
    ("line", "sentinel"),
    [
        pytest.param(ARITHMETIC, "pwned_arith.txt", marks=BASH_4),
        pytest.param(PERCENT, "pwned_pct.txt", marks=BASH_4),
        (PATH_LINE, "pwned_ls.txt"),
        (HOME_LINE, "pwned_fsmon.txt"),
    ],
)
def test_bash_runs_code_through_printf_v(
    shipped: Path, tmp_path: Path, line: str, sentinel: str
) -> None:
    """The fixture: bash runs each line's code (what the classifier must
    not call read-only)."""
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C",
    }
    subprocess.run(
        ["bash", "-c", line], cwd=shipped, env=env, capture_output=True, timeout=60
    )
    assert (shipped / sentinel).exists(), line


# The Bash classifier relaxes a call only under a verified sandbox; these
# tests are about the classifier itself (conftest.bash_under_sandbox).
@pytest.mark.usefixtures("bash_under_sandbox")
class TestMapper:
    @pytest.mark.parametrize("line", LINES + SINGLE)
    def test_the_line_takes_the_worst_case(self, line: str) -> None:
        mapping = ToolCapabilityMapper().map_tool("Bash", {"command": line})
        assert mapping.requires_checkpoint and mapping.requires_approval, line
        assert mapping.risk == "high", line
        assert "send" in mapping.capabilities, line

    @pytest.mark.parametrize("line", READ_ONLY)
    def test_printf_without_an_option_still_observes(self, line: str) -> None:
        mapping = ToolCapabilityMapper().map_tool("Bash", {"command": line})
        assert mapping.capability_id == "observe", line

    def test_printf_writes_with_an_option_or_an_expanded_word(self) -> None:
        assert mapper._writes(["printf", "-v", "x", "y"])
        assert mapper._writes(["printf", "--", "x"])
        assert mapper._writes(["printf", "x"], globbed=True)
        assert not mapper._writes(["printf", "x", "-v"])
        assert not mapper._writes(["printf"])


class TestAdapter:
    @staticmethod
    def _call(line: str, cwd: Path) -> dict[str, Any]:
        return {
            "tool_name": "Bash",
            "tool_input": {"command": line},
            "permission_mode": "default",
            "cwd": str(cwd),
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("line", [ARITHMETIC, PATH_LINE, HOME_LINE])
    async def test_it_needs_a_checkpoint_and_approval(
        self, ontology_path: str, tmp_path: Path, line: str
    ) -> None:
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                approval="ask",
            )
        )
        hook = adapter._make_pretooluse_safety_hook()
        refused = (await hook(self._call(line, tmp_path), "u1", None))[
            "hookSpecificOutput"
        ]
        assert refused["permissionDecision"] == "deny"
        assert refused["permissionDecisionReason"].startswith("F501 ")
        adapter.create_checkpoint(["*"], "t")
        asked = (await hook(self._call(line, tmp_path), "u2", None))[
            "hookSpecificOutput"
        ]
        assert asked["permissionDecision"] == "ask"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("line", [ARITHMETIC, PATH_LINE, HOME_LINE])
    async def test_a_destination_policy_refuses_it(
        self, ontology_path: str, tmp_path: Path, line: str
    ) -> None:
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                approval="ask",
                allowed_destinations=["https://hooks.example.com/*"],
            )
        )
        adapter.create_checkpoint(["*"], "t")
        hook = adapter._make_pretooluse_safety_hook()
        refused = (await hook(self._call(line, tmp_path), "u1", None))[
            "hookSpecificOutput"
        ]
        assert refused["permissionDecision"] == "deny"
        assert refused["permissionDecisionReason"].startswith("F504 ")


def _hook(project: Path, command: str, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": command},
                "permission_mode": mode,
                "cwd": str(project),
            }
        ),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=60,
    )


@needs_hook
class TestPluginHook:
    @pytest.mark.parametrize("command", SINGLE)
    def test_printf_with_an_option_is_gated(self, tmp_path: Path, command: str) -> None:
        result = _hook(tmp_path, command, "bypassPermissions")
        assert result.returncode == 2, command
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), command
        claude = tmp_path / ".claude"
        claude.mkdir(exist_ok=True)
        now = int(time.time())
        (claude / "checkpoint.ok").write_text(
            json.dumps(
                {"checkpoint_id": "c", "created_at": now, "expires_at": now + 60}
            )
        )
        asked = _hook(tmp_path, command, "default")
        assert asked.returncode == 0, asked.stderr
        decision = json.loads(asked.stdout)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "ask"

    @pytest.mark.parametrize("command", READ_ONLY)
    def test_printf_without_an_option_still_passes(
        self, tmp_path: Path, command: str
    ) -> None:
        result = _hook(tmp_path, command, "bypassPermissions")
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
