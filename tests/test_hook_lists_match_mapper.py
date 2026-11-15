"""The plugin hook's classification is derived from the SDK mapper's
(STANDARD 1.2.0 section 5.18.3): its read-only list is a subset of
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
