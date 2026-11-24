"""The SDK demos CLAUDE.md lists under "Run examples" show what they say:
a gated call that names itself (``tool_use_id``) and holds a checkpoint is
allowed once approved, and one without a checkpoint is F501."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run(name: str, cwd: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / name)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONWARNINGS": "ignore"},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        (
            "grounded_agent_demo.py",
            ["Blocked: F501 CHECKPOINT_REQUIRED", "Mutation ALLOWED with checkpoint"],
        ),
        (
            "checkpoint_enforcement_demo.py",
            [
                "Valid checkpoint exists: False",
                "Write: ALLOWED (checkpoint:",
                "F502 APPROVAL_REQUIRED: Write (capability 'mutate') requires "
                + "approval, and no one can give it",
            ],
        ),
        (
            "mcp_tools_demo.py",
            ["Without checkpoint: BLOCKED", "With checkpoint: ALLOWED"],
        ),
    ],
)
def test_a_demo_shows_what_it_says(tmp_path: Path, name: str, shown: list[str]) -> None:
    # Twice in one directory: no checkpoint of the first run is left over.
    for _ in range(2):
        out = run(name, tmp_path)
        for text in shown:
            assert text in out, (name, text)
        assert "R407" not in out
