"""The row-level mapping to the Standard Agent Specification stays well formed.

`docs/research/analysis/standard_agents_mapping/` holds one file per concern,
the findings about each standard, and an index. The rows and findings are
analysis, pinned to a commit of each repository, so their wording is not
checked here. What is checked is what would rot unnoticed: the index and the
files agree, every entry has the fields the index documents, identifiers are
unique and cross-references resolve, and every reference to a file of this
repository names a file that exists.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MAPPING = Path(
    os.environ.get(
        "ACS_SA_MAPPING_DIR",
        ROOT / "docs" / "research" / "analysis" / "standard_agents_mapping",
    )
)
PROPOSALS = ROOT / "tasks" / "standard-agents-upstream"

# Where a reference to the Standard Agent Specification may point: its
# repository's content, site data and top-level files, or the published types.
SA_PREFIXES = (
    "content/0.2.0",
    "content/0.1.0",
    "src/data/",
    "README.md",
    "AGENTS.md",
    "@standardagents/",
    # Their repository's own build and test files, cited for versions and tests.
    "package.json",
    "astro.config.mjs",
    "public/",
    "tests/",
    "git ls-files",
)

# A reference to this repository starts with a path: `spec/STANDARD-v1.1.0.md
# §5.14 (lines 804-830)`.
PATH = re.compile(
    r"^(?:\.[\w-]+/)?[\w.-]+(?:/[\w.<>*-]+)*\.(?:md|ya?ml|json|py|rs|toml|sh|ts)\b"
    r"|^(?:spec|schemas|docs|grounded_agency|core|hooks|skills|tools|scripts|tests|examples|templates)/[\w./<>*-]*"
)

PRIORITIES = {"blocker", "important", "minor"}


def load(name: str) -> dict[str, Any]:
    with open(MAPPING / name, encoding="utf-8") as f:
        loaded: dict[str, Any] = yaml.safe_load(f)
    return loaded


@pytest.fixture(scope="module")
def index() -> dict[str, Any]:
    return load("index.yaml")


@pytest.fixture(scope="module")
def concerns(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["concern"]: load(entry["file"]) for entry in index["concerns"]}


@pytest.fixture(scope="module")
def findings(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {about: load(entry["file"]) for about, entry in index["findings"].items()}


def all_rows(concerns: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [(key, row) for key, doc in concerns.items() for row in doc["rows"]]


def missing_paths(refs: list[tuple[str, str]]) -> tuple[int, list[str]]:
    """Check the references that start with a path of this repository."""
    checked = 0
    missing = []
    for where, ref in refs:
        match = PATH.match(ref)
        if not match:
            continue
        target = match.group(0).rstrip("/.,;:")
        if any(c in target for c in "<>*"):
            target = re.split(r"[<*]", target)[0].rstrip("/")
        checked += 1
        if not (ROOT / target).exists():
            missing.append(f"{where}: {ref}")
    return checked, missing


def test_index_lists_exactly_the_files_present(index: dict[str, Any]) -> None:
    listed = sorted(
        [entry["file"] for entry in index["concerns"]]
        + [entry["file"] for entry in index["findings"].values()]
    )
    on_disk = sorted(p.name for p in MAPPING.glob("*.yaml") if p.name != "index.yaml")
    assert listed == on_disk


def test_index_counts_match_the_concern_files(
    index: dict[str, Any], concerns: dict[str, dict[str, Any]]
) -> None:
    for entry in index["concerns"]:
        doc = concerns[entry["concern"]]
        assert doc["concern"] == entry["concern"]
        assert doc["title"] == entry["title"]
        assert len(doc["rows"]) == entry["rows"], entry["concern"]
        counted: dict[str, int] = {}
        for row in doc["rows"]:
            counted[row["relation"]] = counted.get(row["relation"], 0) + 1
        assert counted == entry["relations"], entry["concern"]


def test_row_ids_are_unique_within_a_concern(
    concerns: dict[str, dict[str, Any]],
) -> None:
    for key, doc in concerns.items():
        ids = [row["id"] for row in doc["rows"]]
        assert sorted({i for i in ids if ids.count(i) > 1}) == [], key


def test_rows_have_the_documented_fields(
    index: dict[str, Any], concerns: dict[str, dict[str, Any]]
) -> None:
    relations = set(index["meta"]["relations"])
    allowed = set(index["meta"]["row_fields"])
    for key, row in all_rows(concerns):
        where = f"{key} {row.get('id')}"
        assert set(row) <= allowed, where
        assert {"id", "relation", "acs", "sa", "explanation"} <= set(row), where
        assert row["relation"] in relations, where
        assert row["explanation"].strip(), where
        for side in ("acs", "sa"):
            assert row[side]["concept"].strip(), where
            assert set(row[side]) <= {"concept", "refs", "quote"}, where


def test_see_also_names_rows_of_other_concerns(
    concerns: dict[str, dict[str, Any]],
) -> None:
    known = {f"{key}#{row['id']}" for key, row in all_rows(concerns)}
    for key, row in all_rows(concerns):
        for other in row.get("see_also", []):
            assert other in known, f"{key} {row['id']}: {other}"
            assert not other.startswith(f"{key}#"), f"{key} {row['id']}: {other}"


def test_no_local_paths_or_working_names_leak_into_the_mapping() -> None:
    for path in MAPPING.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        for marker in ("/tmp/", "/home/", "scratchpad", "sa_gaps", "acs_gaps"):
            assert marker not in text, f"{path.name} contains {marker}"


def test_references_to_this_repository_resolve(
    concerns: dict[str, dict[str, Any]], findings: dict[str, dict[str, Any]]
) -> None:
    refs = [
        (f"{key} {row['id']}", ref)
        for key, row in all_rows(concerns)
        for ref in row["acs"].get("refs", [])
    ]
    refs += [
        (finding["id"], ref)
        for finding in findings["agent_capability_standard"]["findings"]
        for ref in finding["refs"]
    ]
    checked, missing = missing_paths(refs)
    assert checked > 0
    assert missing == []


def test_references_to_their_specification_are_recognisable(
    concerns: dict[str, dict[str, Any]],
) -> None:
    odd = [
        f"{key} {row['id']}: {ref}"
        for key, row in all_rows(concerns)
        for ref in row["sa"].get("refs", [])
        if not ref.startswith(SA_PREFIXES)
    ]
    assert odd == []


def test_findings_match_the_index_and_have_the_documented_fields(
    index: dict[str, Any],
    concerns: dict[str, dict[str, Any]],
    findings: dict[str, dict[str, Any]],
) -> None:
    documented = set(index["meta"]["finding_fields"])
    for about, entry in index["findings"].items():
        doc = findings[about]
        assert doc["about"] == about
        items = doc["findings"]
        assert len(items) == entry["findings"]
        assert len(doc.get("questions", [])) == entry["questions"]
        ids = [f["id"] for f in items]
        assert len(ids) == len(set(ids)), about
        counted: dict[str, int] = {}
        for finding in items:
            where = finding["id"]
            assert finding["priority"] in PRIORITIES, where
            assert finding["summary"].strip() and finding["proposed_change"].strip(), (
                where
            )
            assert finding["refs"], where
            assert set(finding["concerns"]) <= set(concerns), where
            assert finding["concerns"], where
            # Every field is documented, apart from the grouping keys.
            assert set(finding) - documented <= {
                "title",
                "category",
                "area",
                "kind",
                "backwards_compatible",
                "proposal",
                "coverage",
                "disposition_note",
                "verified",
                "note",
            }, where
            for other in finding.get("related", []):
                assert other in ids and other != finding["id"], where
            counted[finding["priority"]] = counted.get(finding["priority"], 0) + 1
        assert counted == entry["priorities"], about
        if "status" in entry:
            statuses: dict[str, int] = {}
            for finding in items:
                statuses[finding["status"]] = statuses.get(finding["status"], 0) + 1
            stated = {k: v for k, v in entry["status"].items() if v}
            assert statuses == stated, about
        for q in doc.get("questions", []):
            assert q["question"].strip() and q["refs"], q["id"]
            if "finding" in q:
                assert q["finding"] in ids, q["id"]


def test_a_finding_covered_by_a_proposal_names_one_that_exists(
    findings: dict[str, dict[str, Any]],
) -> None:
    issues = {p.name for p in PROPOSALS.glob("[0-9][0-9]-*.md")}
    assert issues
    for finding in findings["standard_agent_specification"]["findings"]:
        where = finding["id"]
        assert finding["disposition"] in {"proposal", "not_proposed", "candidate"}, (
            where
        )
        if finding["disposition"] == "proposal":
            assert finding.get("proposal") in issues, where
            assert finding.get("coverage") in {"full", "partial"}, where
        else:
            assert "proposal" not in finding, where
