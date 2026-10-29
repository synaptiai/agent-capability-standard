"""scripts/release_notes.py: the checks release.yml relies on before it
publishes a GitHub Release."""

import importlib.util
import json
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
