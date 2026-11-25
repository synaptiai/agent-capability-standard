"""Each Standard document states a status GOVERNANCE allows, as the ROADMAP does.

`spec/GOVERNANCE.md` names the statuses a Standard document can have in the
sentence "A Standard document's status is A, B, C or D." under "Standard
versions". The header of each `spec/STANDARD-v*.md` states one of them on its
`**Status:**` line (the first clause, before a dash or a semicolon), and its
`**Date:**` line gives the date GOVERNANCE defines for that status. The
Standard table in `spec/ROADMAP.md` lists every version with the same status
and date, and the version whose status is Standard is the one its sentence
"Plugin X implements Standard Y" names, released with that plugin.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec"
GOVERNANCE = SPEC / "GOVERNANCE.md"
ROADMAP = SPEC / "ROADMAP.md"
SPEC_CHANGELOG = SPEC / "CHANGELOG.md"

SEMVER = r"\d+\.\d+\.\d+"
DATE = r"\d{4}-\d{2}-\d{2}"
RELEASED = {"Standard", "Supported", "Unsupported"}


def allowed_statuses() -> list[str]:
    text = re.sub(r"\s+", " ", GOVERNANCE.read_text("utf-8"))
    match = re.search(r"A Standard document's status is ([^.]+)\.", text)
    assert match, (
        'spec/GOVERNANCE.md has no "A Standard document\'s status is" sentence'
    )
    return [s.strip() for s in re.split(r"\s*,\s*(?:or\s+)?|\s+or\s+", match.group(1))]


def standard_files() -> dict[str, Path]:
    files = {
        match.group(1): path
        for path in SPEC.glob("STANDARD-v*.md")
        if (match := re.fullmatch(rf"STANDARD-v({SEMVER})\.md", path.name))
    }
    assert files, "no spec/STANDARD-v*.md file"
    return files


def header(path: Path) -> tuple[str, str]:
    """The status (first clause of `**Status:**`) and the `**Date:**` value."""
    text = path.read_text("utf-8")
    status = re.search(r"^\*\*Status:\*\*\s*(.+)$", text, re.MULTILINE)
    date = re.search(r"^\*\*Date:\*\*\s*(\S+)\s*$", text, re.MULTILINE)
    assert status, f"{path.name} has no **Status:** line"
    assert date, f"{path.name} has no **Date:** line"
    return re.split(r"\s+[—–-]\s+|;", status.group(1))[0].strip(), date.group(1)


def roadmap_rows() -> dict[str, tuple[str, str]]:
    """Version -> (date, status) from the table under "## Standard"."""
    text = ROADMAP.read_text("utf-8")
    section = re.search(
        r"^## Standard\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert section, 'spec/ROADMAP.md has no "## Standard" section'
    lines = [line for line in section.group(1).splitlines() if line.startswith("|")]
    header_row, _separator, *body = (
        [cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines
    )
    assert header_row == ["Version", "Date", "Status"]
    rows = {}
    for version, date, status in body:
        link = re.fullmatch(rf"\[({SEMVER})\]\(STANDARD-v({SEMVER})\.md\)", version)
        assert link and link.group(1) == link.group(2), version
        rows[link.group(1)] = (date, re.split(r"\s*\(|,", status)[0].strip())
    return rows


def test_governance_names_the_four_statuses() -> None:
    assert allowed_statuses() == [
        "Candidate Standard",
        "Standard",
        "Supported",
        "Unsupported",
    ]


@pytest.mark.parametrize("version", sorted(standard_files()))
def test_header_status_is_allowed_and_matches_the_roadmap(version: str) -> None:
    status, date = header(standard_files()[version])
    assert status in allowed_statuses(), f"STANDARD-v{version}.md: {status!r}"
    rows = roadmap_rows()
    assert version in rows, f"the ROADMAP's Standard table has no row for {version}"
    assert rows[version] == (date, status), (
        f"STANDARD-v{version}.md says {status} and {date}; "
        f"the ROADMAP says {rows[version][1]} and {rows[version][0]}"
    )


def test_roadmap_lists_exactly_the_standard_files() -> None:
    assert set(roadmap_rows()) == set(standard_files())


def test_one_version_is_the_released_standard() -> None:
    """At most one version is "Standard", and it is newer than every other
    released version."""
    statuses = {v: header(p)[0] for v, p in standard_files().items()}

    def key(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))

    current = [v for v, s in statuses.items() if s == "Standard"]
    assert len(current) <= 1, current
    released = [v for v, s in statuses.items() if s in RELEASED]
    if released:
        assert current and max(released, key=key) == current[0]


@pytest.mark.parametrize("version", sorted(standard_files()))
def test_date_is_the_one_governance_defines(version: str) -> None:
    """A released version's date is its release section's date in the
    specification changelog; a Candidate's is a date, and it has no release
    section with a date."""
    status, date = header(standard_files()[version])
    assert re.fullmatch(DATE, date), f"STANDARD-v{version}.md: Date {date!r}"
    changelog = SPEC_CHANGELOG.read_text("utf-8")
    section = re.search(rf"^## v{re.escape(version)}\b(.*)$", changelog, re.MULTILINE)
    if status in RELEASED:
        assert section, f"spec/CHANGELOG.md has no section for v{version}"
        assert re.search(rf"\b{re.escape(date)}\b", section.group(1)), (
            f"STANDARD-v{version}.md says {date}; "
            f"spec/CHANGELOG.md says {section.group(1).strip()}"
        )
    elif section:
        assert not re.search(DATE, section.group(1)), (
            f"v{version} is a {status} but spec/CHANGELOG.md dates its section"
        )


def test_the_released_standard_is_the_one_the_roadmap_sentence_names() -> None:
    """GOVERNANCE's last release criterion: a plugin release carries the
    Standard, and the ROADMAP's sentence "Plugin X implements Standard Y"
    names both. The row of that version says it was released with plugin X."""
    text = ROADMAP.read_text("utf-8")
    sentence = re.search(rf"Plugin ({SEMVER}) implements\s+Standard ({SEMVER})", text)
    assert sentence, 'spec/ROADMAP.md has no "Plugin X implements Standard Y" sentence'
    plugin, version = sentence.groups()
    released = [v for v, p in standard_files().items() if header(p)[0] == "Standard"]
    assert released == [version], (
        f'the ROADMAP says "Plugin {plugin} implements Standard {version}"; '
        f"the version whose header says Standard is {released}"
    )
    section = re.search(
        r"^## Standard\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert section
    row = re.search(
        rf"^\| \[{re.escape(version)}\]\(STANDARD-v{re.escape(version)}\.md\) \|[^|]*\|([^|]*)\|",
        section.group(1),
        re.MULTILINE,
    )
    assert row, f"the ROADMAP's Standard table has no row for {version}"
    assert f"released with plugin {plugin}" in row.group(1), row.group(1)
