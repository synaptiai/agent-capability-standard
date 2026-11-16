"""Model families (STANDARD v1.2 §5.15): the derivation vectors of
``tests/conformance/families/derive.json``, in Python and in the core, and
the identity an agent descriptor gives."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core
from grounded_agency.coordination.families import is_model_family, model_family
from grounded_agency.coordination.registry import AgentDescriptor

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads(
    (ROOT / "tests" / "conformance" / "families" / "derive.json").read_text()
)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["model_id"] or "''")
def test_derivation_vectors(case: dict[str, Any]) -> None:
    assert model_family(case["model_id"]) == case["family"]
    assert _core.model_family(case["model_id"]) == case["family"]
    if case["family"] is not None:
        assert is_model_family(case["family"])


def test_identity_derives_the_family_from_the_model_id() -> None:
    d = AgentDescriptor(
        "a", frozenset({"retrieve"}), metadata={"model_id": "acme-large-2"}
    )
    assert d.identity() == {
        "principal": "a",
        "kind": "agent",
        "model_id": "acme-large-2",
        "model_family": "acme",
    }


def test_identity_refuses_a_family_not_written_canonically() -> None:
    d = AgentDescriptor("a", frozenset(), metadata={"model_family": "Acme"})
    with pytest.raises(ValueError, match="model_family"):
        d.identity()
