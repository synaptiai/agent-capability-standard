"""Print the GitHub Release notes for a version tag (used by release.yml).

    python scripts/release_notes.py v2.0.0 > notes.md

The tag must be vMAJOR.MINOR.PATCH, optionally with a pre-release suffix
(v2.0.0-rc.1), and must equal ``v`` + the version in
``.claude-plugin/plugin.json`` (CLAUDE.md, Releasing). The notes are the
tag's section of CHANGELOG.md (``## [v2.0.0] — date`` up to the next
``## [``), which must exist and not be empty; a pre-release may fall back to
its release's section.

GitHub refuses a release body over LIMIT characters. For a longer section
the notes are its opening (the text before its first line that starts with
``**``), its "Before you upgrade" list (the paragraph that starts with
BEFORE, up to the next line that starts with ``**``) and a link to the full
section in CHANGELOG.md at the tag. Nothing is cut from the middle of a
text: a long section without that list, or whose shortened notes are still
too long, is refused.

Links are made absolute at the tag, since a Release page resolves no
relative link: ``(#anchor)`` points into CHANGELOG.md and ``(path)`` to the
file. The repository is ``repository`` (release.yml passes
GITHUB_REPOSITORY), else the GitHub URL in plugin.json's ``repository``.

Exits non-zero, with the reason on stderr, when the notes are refused.
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = re.compile(r"v(\d+\.\d+\.\d+)(-[0-9A-Za-z.-]+)?")
LIMIT = 125_000
BEFORE = "**Before you upgrade.**"
GITHUB = re.compile(r"https://github\.com/([^/\s]+/[^/\s]+?)(?:\.git)?/?")
# A Markdown link's target: "](" up to the closing ")" or a title.
LINK = re.compile(r"\]\(([^)\s]+)")


def find(changelog: str, version: str) -> tuple[str, str] | None:
    """The heading and body of ``## [version]`` in a Keep a Changelog file."""
    lines = changelog.splitlines()
    heading = re.compile(rf"## \[{re.escape(version)}\](\s|$)")
    for i, line in enumerate(lines):
        if heading.match(line):
            body = []
            for rest in lines[i + 1 :]:
                if rest.startswith("## ["):
                    break
                body.append(rest)
            return line, "\n".join(body).strip()
    return None


def section(changelog: str, version: str) -> str | None:
    """The body of ``## [version]`` in a Keep a Changelog file, if any."""
    found = find(changelog, version)
    return found[1] if found else None


def slug(heading: str) -> str:
    """The anchor GitHub gives a Markdown heading (``## [v2.0.0] — x``)."""
    text = heading.lstrip("#").strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def absolute(text: str, base: str) -> str:
    """``text`` with its relative link targets resolved against ``base``
    (``https://github.com/o/r/blob/<tag>/``): ``#x`` into CHANGELOG.md."""

    def resolve(m: re.Match[str]) -> str:
        target = m.group(1)
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("/"):
            return m.group(0)
        if target.startswith("#"):
            target = "CHANGELOG.md" + target
        return f"]({base}{target.removeprefix('./')}"

    return LINK.sub(resolve, text)


def shortened(body: str, url: str) -> str | None:
    """The section's opening, its "Before you upgrade" list and a link to
    ``url``, the full section; None when it has no such list."""
    lines = body.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(BEFORE)), None)
    if start is None:
        return None
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("**")),
        len(lines),
    )
    first = next(
        (i for i, line in enumerate(lines) if line.startswith("**")), len(lines)
    )
    opening = "\n".join(lines[:first]).strip()
    before = "\n".join(lines[start:end]).strip()
    link = (
        "These notes are shortened to fit a GitHub Release. Every change, and "
        f"every entry under Upgrading, is in [CHANGELOG.md]({url})."
    )
    return "\n\n".join(part for part in (opening, before, link) if part)


def plugin_repository(plugin: dict[str, object]) -> str | None:
    """``owner/repo`` from plugin.json's ``repository``, if it is GitHub's."""
    value = plugin.get("repository")
    url = value.get("url") if isinstance(value, dict) else value
    match = GITHUB.fullmatch(url) if isinstance(url, str) else None
    return match.group(1) if match else None


def notes(tag: str, root: Path = ROOT, repository: str | None = None) -> str:
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"tag {tag!r} is not vMAJOR.MINOR.PATCH[-prerelease]")
    plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
    if plugin.get("version") != tag[1:]:
        raise ValueError(
            f"tag {tag} does not match .claude-plugin/plugin.json version "
            f"{plugin.get('version')!r}"
        )
    changelog = (root / "CHANGELOG.md").read_text()
    found = find(changelog, tag)
    if found is None and match.group(2):
        found = find(changelog, f"v{match.group(1)}")
    if not found or not found[1]:
        raise ValueError(f"CHANGELOG.md has no non-empty section for {tag}")
    heading, body = found
    repository = repository or plugin_repository(plugin)
    base = f"https://github.com/{repository}/blob/{tag}/" if repository else ""
    return render(tag, heading, body, base)


def render(tag: str, heading: str, body: str, base: str) -> str:
    """The Release notes for section ``heading`` with ``body``, with links
    absolute at ``base`` (empty when no repository is known): the whole
    section when it fits in LIMIT, else its shortened notes."""
    if base:
        body = absolute(body, base)
        full = f"{body}\n\nSee [CHANGELOG.md]({base}CHANGELOG.md) for every release.\n"
    else:
        full = body + "\n"
    if len(full) <= LIMIT:
        return full
    if not base:
        raise ValueError(
            f"the notes for {tag} are {len(full)} characters, over GitHub's "
            f"{LIMIT}, and no repository is known to link the full section"
        )
    short = shortened(body, f"{base}CHANGELOG.md#{slug(heading)}")
    if short is None:
        raise ValueError(
            f"the notes for {tag} are {len(full)} characters, over GitHub's "
            f"{LIMIT}, and the section has no paragraph starting {BEFORE!r} "
            "to shorten them to"
        )
    short += "\n"
    if len(short) > LIMIT:
        raise ValueError(
            f"the shortened notes for {tag} are {len(short)} characters, "
            f"still over GitHub's {LIMIT}"
        )
    return short


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: release_notes.py TAG", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(notes(argv[0], repository=os.environ.get("GITHUB_REPOSITORY")))
    except (ValueError, OSError) as e:
        print(f"release_notes: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
