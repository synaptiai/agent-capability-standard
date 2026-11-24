"""The repository's five version lines are stated the same way everywhere.

The Standard, the capability ontology, the plugin, the Python package and the
TypeScript package are numbered independently, and each number is declared in
one file. The table under "Versions" in `spec/ROADMAP.md` lists all five. This test compares the
table with the declaring files, so that a release which changes one of them
has to change the table too. `grounded_agency.__version__` repeats the package
version and is compared with it.

The OASF interop files name the Standard and ontology versions their mapping
is for. Their capability ids are checked against the ontology as it stands, so
the versions they name are checked against the declared ones as well, and the
coverage report is checked against the mapping file it describes.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "spec" / "ROADMAP.md"
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
PYPROJECT = ROOT / "pyproject.toml"
PACKAGE_INIT = ROOT / "grounded_agency" / "__init__.py"
TS_PACKAGE = ROOT / "packages" / "acs-core" / "package.json"
OASF_MAPPING = ROOT / "schemas" / "interop" / "oasf_mapping.yaml"
OASF_COVERAGE = ROOT / "docs" / "integrations" / "oasf_coverage.md"

SEMVER = r"\d+\.\d+\.\d+"


def current_standard() -> tuple[Path, str]:
    """The newest `spec/STANDARD-v*.md` and the version its header declares."""
    files = {
        tuple(int(part) for part in match.group(1).split(".")): path
        for path in (ROOT / "spec").glob("STANDARD-v*.md")
        if (match := re.fullmatch(rf"STANDARD-v({SEMVER})\.md", path.name))
    }
    assert files, "no spec/STANDARD-v*.md file"
    newest = max(files)
    path = files[newest]
    declared = re.search(
        rf"^\*\*Version:\*\*\s*({SEMVER})\s*$", path.read_text("utf-8"), re.MULTILINE
    )
    assert declared, f"{path.name} has no **Version:** line"
    assert declared.group(1) == ".".join(map(str, newest)), path.name
    return path, declared.group(1)


def ontology_version() -> str:
    with open(ONTOLOGY, encoding="utf-8") as f:
        version = yaml.safe_load(f)["meta"]["version"]
    assert isinstance(version, str), "the ontology's meta.version must be a string"
    return version


@pytest.fixture(scope="module")
def declared() -> dict[str, tuple[str, Path]]:
    """Each version line: the version, and the file that declares it."""
    standard_file, standard = current_standard()
    project = tomllib.loads(PYPROJECT.read_text("utf-8"))["project"]
    plugin = json.loads(PLUGIN.read_text("utf-8"))["version"]
    ts_package = json.loads(TS_PACKAGE.read_text("utf-8"))
    return {
        "Standard": (standard, standard_file),
        "Capability ontology": (ontology_version(), ONTOLOGY),
        "Plugin": (plugin, PLUGIN),
        f"Python package `{project['name']}`": (project["version"], PYPROJECT),
        f"TypeScript package `{ts_package['name']}`": (
            ts_package["version"],
            TS_PACKAGE,
        ),
    }


def version_table() -> list[tuple[str, str, str]]:
    """The rows of the table under "## Versions" in the roadmap."""
    text = ROADMAP.read_text("utf-8")
    section = re.search(
        r"^## Versions\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert section, 'spec/ROADMAP.md has no "## Versions" section'
    lines = [line for line in section.group(1).splitlines() if line.startswith("|")]
    assert len(lines) > 2, "the Versions section has no table"
    header, separator, *body = (
        tuple(cell.strip() for cell in line.strip("|").split("|")) for line in lines
    )
    assert header == ("Version line", "Current", "Declared in")
    assert all(set(cell) <= set("-: ") for cell in separator)
    rows = []
    for cells in body:
        assert len(cells) == 3, cells
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def test_roadmap_table_lists_the_five_version_lines(
    declared: dict[str, tuple[str, Path]],
) -> None:
    assert [name for name, _, _ in version_table()] == list(declared)


def test_roadmap_table_states_the_declared_versions(
    declared: dict[str, tuple[str, Path]],
) -> None:
    stated = {name: version for name, version, _ in version_table()}
    assert stated == {name: version for name, (version, _) in declared.items()}


def test_roadmap_table_links_each_declaring_file(
    declared: dict[str, tuple[str, Path]],
) -> None:
    for name, _, where in version_table():
        links = re.findall(r"\]\(([^)\s]+)\)", where)
        assert len(links) == 1, name
        assert (ROADMAP.parent / links[0]).resolve() == declared[name][1], name


def test_roadmap_introduction_names_the_same_pair(
    declared: dict[str, tuple[str, Path]],
) -> None:
    """The opening paragraph says which Standard the plugin implements.

    Between releases the current Standard can be ahead of the released
    plugin: the work on main implements a Candidate that no plugin release
    does yet. The pair then names an earlier Standard that has its own text,
    and the introduction names the current Standard in a sentence of its own.
    """
    intro = ROADMAP.read_text("utf-8").split("\n## ", 1)[0]
    pair = rf"Plugin ({SEMVER}) implements\s+Standard ({SEMVER})"
    pairs = re.findall(pair, intro)
    message = (
        "the introduction of spec/ROADMAP.md must say once "
        "'Plugin X.Y.Z implements Standard X.Y.Z', with the declared plugin "
        "version and a Standard no later than the current one"
    )
    assert len(pairs) == 1, message
    plugin, implemented = pairs[0]
    current = declared["Standard"][0]
    assert plugin == declared["Plugin"][0], message

    def key(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))

    assert key(implemented) <= key(current), message
    assert (ROADMAP.parent / f"STANDARD-v{implemented}.md").is_file(), message
    if implemented != current:
        rest = re.sub(pair, "", intro)
        assert re.search(rf"\bStandard\s+{re.escape(current)}\b", rest), (
            f"the introduction of spec/ROADMAP.md names Standard {implemented} "
            f"for the plugin, so it must also name the current Standard {current}"
        )


def test_package_module_repeats_the_declared_version() -> None:
    """`grounded_agency.__version__` is a copy of the version in pyproject.toml."""
    project = tomllib.loads(PYPROJECT.read_text("utf-8"))["project"]
    source = PACKAGE_INIT.read_text("utf-8")
    copies = re.findall(r'^__version__ = "([^"]+)"$', source, re.MULTILINE)
    assert copies == [project["version"]]


@pytest.fixture(scope="module")
def oasf_meta() -> dict[str, Any]:
    with open(OASF_MAPPING, encoding="utf-8") as f:
        meta: dict[str, Any] = yaml.safe_load(f)["meta"]
    return meta


def test_oasf_mapping_names_the_standard_and_the_ontology(
    oasf_meta: dict[str, Any], declared: dict[str, tuple[str, Path]]
) -> None:
    """Two versions, not one "Grounded Agency version" that could mean either."""
    assert "grounded_agency_version" not in oasf_meta
    assert oasf_meta["agent_capability_standard"] == {
        "standard": declared["Standard"][0],
        "ontology": declared["Capability ontology"][0],
    }


def test_oasf_coverage_report_states_the_mapping_files_versions(
    oasf_meta: dict[str, Any],
) -> None:
    text = OASF_COVERAGE.read_text("utf-8")

    def header(label: str) -> str:
        match = re.search(rf"^\*\*{label}:\*\*\s*(.+)$", text, re.MULTILINE)
        assert match, f"docs/integrations/oasf_coverage.md has no {label} line"
        return match.group(1)

    assert header("Mapping Version") == oasf_meta["version"]
    assert header("OASF Target Version") == oasf_meta["oasf_version"]
    acs = re.match(
        rf"Standard ({SEMVER}), ontology ({SEMVER})\b",
        header("Agent Capability Standard"),
    )
    assert acs, "expected 'Standard X.Y.Z, ontology X.Y.Z'"
    assert {
        "standard": acs.group(1),
        "ontology": acs.group(2),
    } == oasf_meta["agent_capability_standard"]


def artifact_table() -> list[tuple[str, str, str, str]]:
    """The rows of §11.7 of the newest Standard: artifact, file, version,
    sections."""
    path, _ = current_standard()
    text = path.read_text("utf-8")
    section = text[text.index("### 11.7 Artifacts of This Version") :]
    section = section[: section.index("\n## ")]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[1].startswith("`"):
            rows.append((cells[0], cells[1], cells[2], cells[3]))
    assert rows, "§11.7 has no table"
    return rows


def test_standard_artifact_table() -> None:
    """Standard 1.2 §11.7: every file the table names exists; a row with a
    version names the version the file declares (`meta.version` or
    `schema.version`); the ontology row is the ontology's version, which §4
    opens by naming; the conformance row is the one directory every vector
    file the Standard names (§10.3: trust, profile and entity id vectors,
    runtime fixtures, ...) is in, and each of those files exists."""
    path, _ = current_standard()
    text = path.read_text("utf-8")
    listed: list[str] = []
    for _, files, version, _ in artifact_table():
        names = re.findall(r"`([^`]+)`", files)
        listed += names
        for name in names:
            assert (ROOT / name).exists(), name
        if version == "—":
            continue
        assert len(names) == 1, files
        doc = yaml.safe_load((ROOT / names[0]).read_text("utf-8"))
        stated = (doc.get("meta") or {}).get("version") or (
            doc.get("schema") or {}
        ).get("version")
        assert str(stated) == version, names[0]
    ontology_rows = [r for r in artifact_table() if "capability_ontology.yaml" in r[1]]
    assert [r[2] for r in ontology_rows] == [ontology_version()]
    opening = text[text.index("## 4. Capability Ontology") :][:400]
    assert f"capability ontology {ontology_version()}" in opening
    conformance = [n for n in listed if n.startswith("tests/conformance")]
    assert conformance == ["tests/conformance/"]
    named = set(re.findall(r"`(tests/conformance/[^`]+)`", text)) - {conformance[0]}
    for vector in ("trust/", "profiles/", "entities/ids.json", "runtime/*.json"):
        assert f"{conformance[0]}{vector}" in named, vector
    for name in sorted(named):
        if "*" in name:
            assert sorted(ROOT.glob(name)), f"{name} names no file"
        elif name.endswith("/"):
            assert sorted((ROOT / name).glob("*.json")), f"{name} holds no vector"
        else:
            json.loads((ROOT / name).read_text("utf-8"))
