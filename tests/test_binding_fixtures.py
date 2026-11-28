"""The binding fixtures (tests/conformance/bindings/, STANDARD 1.2.0 section
10.4) through the Python loader: load_bindings, then check_offered.

The adapter's conformance statement lists offered_tools, so no fixture is
skipped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.capabilities.bindings import check_offered, load_bindings
from grounded_agency.capabilities.registry import CapabilityRegistry
from grounded_agency.errors import Severity

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "conformance" / "bindings"
STATEMENT = (
    ROOT
    / "tests"
    / "conformance"
    / "calls"
    / "statements"
    / "grounded_agency_adapter.json"
)
CASES = sorted(FIXTURES.glob("*.json"))


@pytest.fixture(scope="module")
def registry() -> CapabilityRegistry:
    return CapabilityRegistry(ROOT / "schemas" / "capability_ontology.yaml")


def test_there_are_fixtures() -> None:
    assert len(CASES) == 37


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_binding_fixture(path: Path, registry: CapabilityRegistry) -> None:
    fixture: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    features = json.loads(STATEMENT.read_text(encoding="utf-8"))["features"]
    missing = set(fixture.get("needs", [])) - set(features)
    if missing:
        pytest.skip(f"the adapter's statement lacks {sorted(missing)}")

    loaded, diagnostics = load_bindings(
        fixture["records"],
        {n.id: n for n in registry.all_capabilities()},
        [
            (e.from_cap, e.to_cap)
            for e in registry.all_edges()
            if e.edge_type == "requires"
        ],
        registry.version,
    )
    if "offered" in fixture or "host_actions" in fixture:
        diagnostics = diagnostics + check_offered(
            fixture.get("offered", {}),
            loaded,
            [(a["action"], a["tool"]) for a in fixture.get("host_actions", [])],
            host_takes_checkpoints=fixture.get("host_takes_checkpoints", False),
            shell_tools=fixture.get("shell_tools", {}),
        )

    def pairs(severity: Severity) -> list[tuple[str, str]]:
        return sorted(
            (d.code_str, str(d.location.get("tool", "")))
            for d in diagnostics
            if d.severity is severity
        )

    expect = fixture["expect"]
    assert pairs(Severity.ERROR) == sorted(
        (e["code"], e["tool"]) for e in expect["errors"]
    )
    assert pairs(Severity.WARNING) == sorted(
        (w["code"], w["tool"]) for w in expect["warnings"]
    )
    effective = {
        tool: {
            "risk": m.risk,
            "mutation": m.mutation,
            "requires_checkpoint": m.requires_checkpoint,
            "requires_approval": m.requires_approval,
        }
        for tool, m in loaded.items()
    }
    assert effective == expect["effective"]
