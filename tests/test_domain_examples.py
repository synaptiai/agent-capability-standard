"""The "Capability Usage" examples of the domain guides (docs/domains/*/README.md)
under their own profiles: each example's output passes the grounding policy
its domain profile puts in force (STANDARD v1.2 §5.20, §5.21.3), with its
evidence anchors in the §6.5 form, a `kind` and a `ref`, and an `acs:` ref
naming one of the example's inputs, as a call's argument (§5.20)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from grounded_agency.grounding import GroundingPolicy, check_output

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"^### (.+?)\n.*?```yaml\n(.*?)```", re.S | re.M)


def _examples() -> list[tuple[str, str, str, dict[str, Any]]]:
    found = []
    for readme in sorted((ROOT / "docs" / "domains").glob("*/README.md")):
        text = readme.read_text(encoding="utf-8")
        start = text.find("\n## Capability Usage")
        if start < 0:
            continue
        end = text.find("\n## ", start + 1)
        section = text[start : end if end > 0 else None]
        for heading, body in FENCE.findall(section):
            ((capability, spec),) = yaml.safe_load(body).items()
            found.append((readme.parent.name, heading.strip(), capability, spec))
    return found


EXAMPLES = _examples()


def test_there_are_examples() -> None:
    assert {domain for domain, *_ in EXAMPLES} >= {"vision", "audio", "multimodal"}


@pytest.mark.parametrize(
    "domain,heading,capability,spec",
    EXAMPLES,
    ids=[f"{d}-{h}" for d, h, *_ in EXAMPLES],
)
def test_an_example_is_grounded_under_its_profile(
    domain: str, heading: str, capability: str, spec: dict[str, Any]
) -> None:
    profile = yaml.safe_load(
        (ROOT / "schemas" / "profiles" / f"{domain}.yaml").read_text(encoding="utf-8")
    )
    policy = GroundingPolicy.from_profile(profile)
    output = spec["output"]
    for anchor in output.get("evidence_anchors", []):
        assert set(anchor) <= {"kind", "ref", "digest"}, anchor
    if policy is None or not policy.requires(capability):
        return
    result = check_output(output, policy, bound_refs=list(spec.get("input", {})))
    assert result.status == "grounded", (result.code, result.message)
