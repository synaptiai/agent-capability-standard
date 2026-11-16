"""Step domains (STANDARD v1.2 §5.2.4): the domain id grammar and the
selection vectors of ``tests/conformance/domains/match.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.workflows.domains import (
    UnsupportedDomain,
    is_domain_id,
    select_implementation,
)

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads(
    (ROOT / "tests" / "conformance" / "domains" / "match.json").read_text()
)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_selection_vectors(case: dict[str, Any]) -> None:
    available = [None if i == "" else i for i in case["implementations"]]
    if case["expect"] is None:
        with pytest.raises(UnsupportedDomain) as e:
            select_implementation(case["domain"], available)
        assert e.value.reason == "unsupported_domain"
        return
    got = select_implementation(case["domain"], available)
    assert (got if got is not None else "") == case["expect"]


def test_domain_id_grammar() -> None:
    for ok in ["text", "image.object", "image.3d", "multimodal.text_to_image"]:
        assert is_domain_id(ok), ok
    for bad in ["", "plan-invalidation", "Text.Feature", "a..b", ".a", "a."]:
        assert not is_domain_id(bad), bad


def test_every_shipped_step_domain_is_a_domain_id() -> None:
    """The repository's catalogs use domain ids only (the one exception,
    plan-invalidation, was renamed plan_invalidation)."""
    import yaml

    paths = [ROOT / "schemas" / "workflow_catalog.yaml"]
    paths += sorted((ROOT / "schemas" / "workflows").glob("*.yaml"))
    paths += sorted((ROOT / "examples").glob("*.workflow_catalog.yaml"))
    seen = set()
    for path in paths:
        for wf in (yaml.safe_load(path.read_text()) or {}).values():
            for step in (wf or {}).get("steps") or [] if isinstance(wf, dict) else []:
                if isinstance(step, dict) and isinstance(step.get("domain"), str):
                    seen.add(step["domain"])
    assert seen and all(is_domain_id(d) for d in seen), sorted(
        d for d in seen if not is_domain_id(d)
    )
