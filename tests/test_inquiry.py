"""Answers to an inquiry (STANDARD v1.2 §5.13.1): the vectors of
``tests/conformance/inquiry/answers.json`` and the SDK orchestrator's
``inquire`` output against the capability's contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.coordination.inquiry import AnswerError, match_answers

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads(
    (ROOT / "tests" / "conformance" / "inquiry" / "answers.json").read_text()
)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_answer_vectors(case: dict[str, Any]) -> None:
    if "error" in case:
        with pytest.raises(AnswerError) as e:
            match_answers(case["inquiry"], case["item"])
        assert e.value.reason == case["error"]
    else:
        assert match_answers(case["inquiry"], case["item"]) == case["expect"]


def test_orchestrator_inquire_output_meets_the_contract() -> None:
    import jsonschema

    from grounded_agency.capabilities.registry import CapabilityRegistry
    from grounded_agency.coordination.orchestrator import OrchestrationRuntime
    from grounded_agency.workflows.engine import WorkflowStep

    schema = json.loads(
        (
            ROOT / "schemas" / "generated" / "capability_contracts.schema.json"
        ).read_text()
    )
    runtime = OrchestrationRuntime(
        CapabilityRegistry(ROOT / "schemas" / "capability_ontology.yaml")
    )
    step = WorkflowStep(capability="inquire", purpose="p", store_as="q")
    out = runtime.execute_workflow_step(step, {"ambiguous_input": "which table"}).output
    assert out["inquiry_id"]
    assert out["questions"][0]["id"] == "q1"
    jsonschema.validate(out, {**schema, "$ref": "#/$defs/inquire.output"})
