"""scripts/release_notes.py: the checks release.yml relies on before it
publishes a GitHub Release."""

import functools
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "release_notes", ROOT / "scripts" / "release_notes.py"
)
assert spec and spec.loader
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## [Unreleased]

## [v2.0.0] — 2026-10-29

Highlights.

### Added
- A thing

## [v1.2.0] — 2026-02-04

### Fixed
- Another thing
"""


def repo(tmp_path: Path, version: str, changelog: str = CHANGELOG) -> Path:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": version})
    )
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    return tmp_path


def test_notes_are_the_tags_section(tmp_path: Path) -> None:
    body = release_notes.notes("v2.0.0", repo(tmp_path, "2.0.0"), "o/r")
    assert body.startswith("Highlights.")
    assert "- A thing" in body and "Another thing" not in body
    assert body.endswith(
        "See [CHANGELOG.md](https://github.com/o/r/blob/v2.0.0/CHANGELOG.md)"
        " for every release.\n"
    )


def test_last_section_runs_to_the_end(tmp_path: Path) -> None:
    body = release_notes.notes("v1.2.0", repo(tmp_path, "1.2.0"))
    assert body == "### Fixed\n- Another thing\n"


def test_prerelease_falls_back_to_its_release(tmp_path: Path) -> None:
    body = release_notes.notes("v2.0.0-rc.1", repo(tmp_path, "2.0.0-rc.1"))
    assert body.startswith("Highlights.")


@pytest.mark.parametrize(
    ("tag", "version", "changelog", "why"),
    [
        ("2.0.0", "2.0.0", CHANGELOG, "is not vMAJOR"),
        ("v2.0", "2.0", CHANGELOG, "is not vMAJOR"),
        ("v2.0.0", "1.2.0", CHANGELOG, "does not match"),
        ("v3.0.0", "3.0.0", CHANGELOG, "no non-empty section"),
        (
            "v2.0.0",
            "2.0.0",
            "## [v2.0.0] — 2026-10-29\n\n## [v1.0.0]\n",
            "no non-empty",
        ),
    ],
)
def test_refuses(
    tmp_path: Path, tag: str, version: str, changelog: str, why: str
) -> None:
    with pytest.raises(ValueError, match=why):
        release_notes.notes(tag, repo(tmp_path, version, changelog))


def test_the_repository_is_ready_for_its_version() -> None:
    """The tag for plugin.json's version would publish notes."""
    version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())[
        "version"
    ]
    assert release_notes.notes(f"v{version}").strip()


LONG = """## [v2.0.0] — 2026-10-29

Opening paragraph, see [the guide](docs/guide.md).

**Upgrading from v1.2.0.** Every change, by component.

**Before you upgrade.** The changes to read first.

- Python 3.14 is required ([requirements](#upgrade-requirements)).
- A command is renamed.

**Requirements.**

- <a id="upgrade-requirements"></a>Python 3.14.
{filler}
## [v1.2.0] — 2026-02-04

### Fixed
- Another thing
"""


def long_changelog(filler: int = release_notes.LIMIT) -> str:
    return LONG.replace("{filler}", "- x\n" * (filler // 4))


def test_long_section_is_shortened(tmp_path: Path) -> None:
    body = release_notes.notes(
        "v2.0.0", repo(tmp_path, "2.0.0", long_changelog()), "o/r"
    )
    base = "https://github.com/o/r/blob/v2.0.0/"
    assert len(body) <= release_notes.LIMIT
    assert body == (
        f"Opening paragraph, see [the guide]({base}docs/guide.md).\n\n"
        "**Before you upgrade.** The changes to read first.\n\n"
        f"- Python 3.14 is required ([requirements]({base}CHANGELOG.md"
        "#upgrade-requirements)).\n"
        "- A command is renamed.\n\n"
        "These notes are shortened to fit a GitHub Release. Every change, and "
        f"every entry under Upgrading, is in [CHANGELOG.md]({base}CHANGELOG.md"
        "#v200--2026-10-29).\n"
    )


def test_a_section_at_the_limit_is_not_shortened(tmp_path: Path) -> None:
    text = "## [v2.0.0] — 2026-10-29\n\n" + "y" * (release_notes.LIMIT - 1) + "\n"
    body = release_notes.notes("v2.0.0", repo(tmp_path, "2.0.0", text))
    assert len(body) == release_notes.LIMIT


def test_links_resolve_at_the_tag(tmp_path: Path) -> None:
    text = (
        "## [v2.0.0] — 2026-10-29\n\n[a](docs/a.md) [b](./b.md) [c](#c) "
        '[d](https://e.org/x) [e](mailto:x@e.org) [f](/abs) [g](h.md "t")\n'
    )
    body = release_notes.notes("v2.0.0", repo(tmp_path, "2.0.0", text), "o/r")
    base = "https://github.com/o/r/blob/v2.0.0/"
    assert body.splitlines()[0] == (
        f"[a]({base}docs/a.md) [b]({base}b.md) [c]({base}CHANGELOG.md#c) "
        f'[d](https://e.org/x) [e](mailto:x@e.org) [f](/abs) [g]({base}h.md "t")'
    )


def test_repository_from_plugin_json(tmp_path: Path) -> None:
    root = repo(tmp_path, "2.0.0", long_changelog())
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": "2.0.0", "repository": "https://github.com/o/r"})
    )
    body = release_notes.notes("v2.0.0", root)
    assert "(https://github.com/o/r/blob/v2.0.0/CHANGELOG.md#v200--2026-10-29)" in body


@pytest.mark.parametrize(
    ("changelog", "repository", "why"),
    [
        (
            long_changelog().replace("**Before you upgrade.**", "**Read.**"),
            "o/r",
            "no paragraph starting",
        ),
        (long_changelog(), None, "no repository is known"),
        (
            long_changelog().replace(
                "- A command is renamed.\n",
                "- A command is renamed.\n" + "  z\n" * (release_notes.LIMIT // 4),
            ),
            "o/r",
            "still over",
        ),
    ],
)
def test_refuses_long_notes(
    tmp_path: Path, changelog: str, repository: str | None, why: str
) -> None:
    with pytest.raises(ValueError, match=why):
        release_notes.notes("v2.0.0", repo(tmp_path, "2.0.0", changelog), repository)


def test_main_exits_non_zero_rather_than_truncate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path, "2.0.0", long_changelog().replace("**Before", "**After"))
    monkeypatch.setattr(
        release_notes, "notes", functools.partial(release_notes.notes, root=root)
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    assert release_notes.main(["v2.0.0"]) == 1
    out = capsys.readouterr()
    assert out.out == "" and "over GitHub's 125000" in out.err


def test_the_unreleased_section_fits_a_release() -> None:
    """The [Unreleased] section, the next release's notes, shortens to fit,
    and each link of its "Before you upgrade" list names an anchor of
    CHANGELOG.md."""
    changelog = (ROOT / "CHANGELOG.md").read_text()
    found = release_notes.find(changelog, "Unreleased")
    assert found
    heading, body = found
    short = release_notes.shortened(body, "URL")
    assert short is not None, "no 'Before you upgrade' list in [Unreleased]"
    assert len(short) + 1 <= release_notes.LIMIT
    before = short[short.index(release_notes.BEFORE) :]
    fragments = re.findall(r"\]\(#([^)]+)\)", before)
    assert fragments
    anchors = set(re.findall(r'<a id="([^"]+)"></a>', changelog))
    assert sorted(set(fragments) - anchors) == []
