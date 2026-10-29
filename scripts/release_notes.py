"""Print the GitHub Release notes for a version tag (used by release.yml).

    python scripts/release_notes.py v2.0.0 > notes.md

The tag must be vMAJOR.MINOR.PATCH, optionally with a pre-release suffix
(v2.0.0-rc.1), and must equal ``v`` + the version in
``.claude-plugin/plugin.json`` (CLAUDE.md, Releasing). The notes are the
tag's section of CHANGELOG.md (``## [v2.0.0] — date`` up to the next
``## [``), which must exist and not be empty; a pre-release may fall back to
its release's section. Exits non-zero, with the reason on stderr, otherwise.
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = re.compile(r"v(\d+\.\d+\.\d+)(-[0-9A-Za-z.-]+)?")


def section(changelog: str, version: str) -> str | None:
    """The body of ``## [version]`` in a Keep a Changelog file, if any."""
    lines = changelog.splitlines()
    heading = re.compile(rf"## \[{re.escape(version)}\](\s|$)")
    for i, line in enumerate(lines):
        if heading.match(line):
            body = []
            for rest in lines[i + 1 :]:
                if rest.startswith("## ["):
                    break
                body.append(rest)
            return "\n".join(body).strip()
    return None


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
    body = section(changelog, tag)
    if body is None and match.group(2):
        body = section(changelog, f"v{match.group(1)}")
    if not body:
        raise ValueError(f"CHANGELOG.md has no non-empty section for {tag}")
    if repository:
        url = f"https://github.com/{repository}/blob/{tag}/CHANGELOG.md"
        body += f"\n\nSee [CHANGELOG.md]({url}) for every release."
    return body + "\n"


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
