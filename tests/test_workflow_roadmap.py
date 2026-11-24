"""The workflow roadmap lists what the reference catalog defines.

`docs/WORKFLOW_ROADMAP.md`, section "Current Workflows", says it lists the
workflows of `schemas/workflow_catalog.yaml`, each with its goal, declared
risk and step capabilities in order (a step's domain in brackets, an
`invoke` step's workflow in parentheses). Nothing else writes that list
down, so it is compared here with the catalog, which a rename of a step
domain (`plan-invalidation` to `plan_invalidation`) once left behind.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
ROADMAP = ROOT / "docs" / "WORKFLOW_ROADMAP.md"
CATALOG = ROOT / "schemas" / "workflow_catalog.yaml"


def _current() -> tuple[int, dict[str, str]]:
    """The section's stated count, and each workflow's entry by name."""
    text = ROADMAP.read_text(encoding="utf-8")
    heading = re.search(r"^## Current Workflows \((\d+)\)\n", text, re.M)
    assert heading, "no 'Current Workflows (N)' section"
    section = text[heading.end() :].split("\n## ", 1)[0]
    entries = re.findall(
        r"^### \d+\. `([a-z0-9_]+)`\n(.*?)(?=^### |\Z)", section, re.M | re.S
    )
    return int(heading.group(1)), dict(entries)


def _field(body: str, label: str) -> str:
    found = re.search(rf"^- \*\*{label}:\*\* (.+)$", body, re.M)
    assert found, label
    return found.group(1).strip()


def _steps(workflow: dict[str, Any]) -> str:
    shown = []
    for step in workflow["steps"]:
        text = step["capability"]
        if step.get("domain"):
            text += f"[{step['domain']}]"
        if step["capability"] == "invoke" and step.get("workflow_id"):
            text += f"({step['workflow_id']})"
        shown.append(text)
    return " → ".join(shown)


def test_the_roadmap_lists_every_workflow_of_the_catalog() -> None:
    catalog = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    count, entries = _current()
    assert count == len(entries) == len(catalog)
    assert set(entries) == set(catalog)


def test_each_entry_states_the_catalog_s_goal_risk_and_steps() -> None:
    catalog = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    _, entries = _current()
    for name, body in entries.items():
        workflow = catalog[name]
        assert _field(body, "Goal") == workflow["goal"].strip(), name
        assert _field(body, "Declared risk") == workflow["risk"], name
        assert _field(body, "Steps") == _steps(workflow), name
