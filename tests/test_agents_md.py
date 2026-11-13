"""AGENTS.md repeats commands from CLAUDE.md and the CI workflows; it must not drift from them.

Expected values come from CLAUDE.md and .github/workflows/*.yml as committed:
every command line in a fenced block of AGENTS.md (its trailing comment
removed) must appear, as written, in one of those files.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _fenced_lines(text: str) -> list[str]:
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if re.match(r"^\s*```", line):
            inside = not inside
            continue
        if inside and line.strip():
            lines.append(re.sub(r"\s+#\s.*$", "", line).strip())
    return lines


def _normalise(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text)


def test_agents_md_commands_come_from_claude_md_or_ci() -> None:
    sources = [
        ROOT / "CLAUDE.md",
        *sorted((ROOT / ".github" / "workflows").glob("*.yml")),
    ]
    haystack = "\n".join(_normalise(p.read_text(encoding="utf-8")) for p in sources)
    commands = _fenced_lines((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    assert commands, "AGENTS.md has no fenced commands"
    missing = [c for c in commands if _normalise(c) not in haystack]
    assert missing == [], (
        f"AGENTS.md commands found in neither CLAUDE.md nor CI: {missing}"
    )


def test_agents_md_links_claude_md() -> None:
    assert "](CLAUDE.md)" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
