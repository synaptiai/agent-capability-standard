"""Skill frontmatter keys and their owners (ACS-59).

Every `skills/*/SKILL.md` follows the ownership table of `skills/README.md`
("Skill Structure"): `name` equals the directory and matches the Agent
Skills name grammar; `description` is 1-1024 characters; every key is one
the table lists for Agent Skills or Claude Code; no skill declares `layer`
(the ontology gives a capability's layer); `metadata`, if present, maps
`acs-*` keys to strings. The table lists exactly the keys the skills use.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))
README = (ROOT / "skills" / "README.md").read_text(encoding="utf-8")

AGENT_SKILLS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
CLAUDE_CODE = {
    "argument-hint",
    "disable-model-invocation",
    "user-invocable",
    "context",
    "agent",
    "hooks",
}
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path} has no frontmatter"
    loaded: dict[str, Any] = yaml.safe_load(match.group(1))
    return loaded


def test_there_are_42_skills() -> None:
    assert len(SKILLS) == 42


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter_follows_the_ownership_table(path: Path) -> None:
    fm = frontmatter(path)
    name = fm.get("name")
    assert name == path.parent.name, "name is the directory name"
    assert isinstance(name, str) and len(name) <= 64 and NAME.match(name)
    description = fm.get("description")
    assert isinstance(description, str) and 1 <= len(description) <= 1024
    assert set(fm) <= AGENT_SKILLS | CLAUDE_CODE, set(fm) - (AGENT_SKILLS | CLAUDE_CODE)
    assert "layer" not in fm
    metadata = fm.get("metadata")
    if metadata is not None:
        assert isinstance(metadata, dict)
        for key, value in metadata.items():
            assert str(key).startswith("acs-") and isinstance(value, str), key


def test_the_readme_table_names_exactly_the_keys() -> None:
    section = README[README.index("## Skill Structure") :]
    section = section[: section.index("## Layer Execution Flow")]
    rows = [line for line in section.splitlines() if line.startswith("| `")]
    named = {
        key for row in rows for key in re.findall(r"`([a-z-]+)`", row.split("|")[1])
    }
    assert named == AGENT_SKILLS | CLAUDE_CODE
    used = {key for path in SKILLS for key in frontmatter(path)}
    assert used <= named
