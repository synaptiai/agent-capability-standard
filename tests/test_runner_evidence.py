"""The runner records the evidence of the outputs the core kept (STANDARD
v1.2 §6.6), and nothing of an output the core refused, will retry, or that
is a waiting delegation's acceptance."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import GroundingPolicy
from grounded_agency.state.evidence_store import EvidenceStore
from grounded_agency.workflows import Host, WorkflowEngine, WorkflowRunner

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = str(ROOT / "schemas" / "capability_ontology.yaml")
FILE_A = {"ref": "file:a.txt", "kind": "file"}


class ScriptedHost(Host):
    """Answers each InvokeCapability with the next scripted output, and
    each AwaitEvent with the next scripted event."""

    def __init__(self, answers: list[Callable[[dict[str, Any]], dict[str, Any]]]):
        super().__init__()
        self.answers = list(answers)

    def now_ms(self) -> int:
        return 1_000

    def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
        return self.answers.pop(0)(action)

    def await_event(self, action: dict[str, Any]) -> dict[str, Any]:
        return self.answers.pop(0)(action)


def output(**value: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    value.setdefault("evidence_anchors", [])
    return lambda _action: {"kind": "Output", "value": value}


def runner_for(tmp_path: Path, catalog: str, store: Any) -> WorkflowRunner:
    path = tmp_path / "catalog.yaml"
    path.write_text(catalog)
    engine = WorkflowEngine(ONTOLOGY, schema_root=str(ROOT))
    engine.load_catalog(path)
    return WorkflowRunner(engine, evidence_store=store)


ONE = """\
# Standard version: 1.1.0
w:
  goal: g
  risk: low
  steps:
  - capability: retrieve
    purpose: Read.
    store_as: r
    retry: {max: 1}
    input_bindings: {target: t}
"""


def test_only_valid_anchors_are_recorded(tmp_path: Path) -> None:
    store = EvidenceStore()
    host = ScriptedHost(
        [
            output(
                data=1,
                confidence=1,
                evidence_anchors=[
                    "file:legacy.txt",
                    {"ref": ""},
                    # Not an anchor for the core: not recorded either.
                    {"ref": "file:b.txt", "kind": "file", "digest": None},
                    FILE_A,
                ],
            )
        ]
    )
    result = runner_for(tmp_path, ONE, store).run("w", {}, host, run_id="run-1")
    assert result.ok, result
    (record,) = store.records()
    assert record.anchor.ref == "file:a.txt"
    assert (record.run_id, record.frame, record.step, record.capability) == (
        "run-1",
        ("w",),
        0,
        "retrieve",
    )


def test_an_output_refused_with_f505_records_nothing(tmp_path: Path) -> None:
    store = EvidenceStore()
    host = ScriptedHost(
        [output(data=1, confidence=1, evidence_anchors=[{"ref": "x:1", "kind": "log"}])]
    )
    result = runner_for(tmp_path, ONE, store).run(
        "w",
        {},
        host,
        grounding=GroundingPolicy(require={"retrieve"}, kinds={"file"}),
    )
    assert result.code == "F505"
    assert store.records() == []


def test_a_retried_step_records_its_accepted_output_once(tmp_path: Path) -> None:
    store = EvidenceStore()
    host = ScriptedHost(
        [
            # Refused (R402: no confidence) and retried.
            output(data=1, evidence_anchors=[{"ref": "file:first", "kind": "file"}]),
            output(data=1, confidence=1, evidence_anchors=[FILE_A]),
        ]
    )
    result = runner_for(tmp_path, ONE, store).run("w", {}, host)
    assert result.ok, result
    assert [r.anchor.ref for r in store.records()] == ["file:a.txt"]


def test_an_output_refused_with_r402_records_nothing(tmp_path: Path) -> None:
    store = EvidenceStore()
    host = ScriptedHost(
        [
            output(data=1, evidence_anchors=[FILE_A]),
            output(data=1, evidence_anchors=[FILE_A]),
        ]
    )
    result = runner_for(tmp_path, ONE, store).run("w", {}, host)
    assert result.code == "R402"
    assert store.records() == []


DELEGATE = """\
# Standard version: 1.1.0
w:
  goal: g
  risk: low
  workflow_extensions:
    requires: [wait@1]
  steps:
  - capability: delegate
    purpose: Delegate and wait.
    store_as: d
    timeout: 1h
    input_bindings: {task: {review: x}, agent: a}
    wait: {event_type: delegation.result}
"""


def test_a_waiting_delegations_acceptance_records_nothing(tmp_path: Path) -> None:
    store = EvidenceStore()
    host = ScriptedHost(
        [
            output(accepted=True, task_id="t1", evidence_anchors=[FILE_A]),
            lambda _a: {
                "kind": "Event",
                "event": {"event_type": "delegation.result", "task_id": "t1"},
            },
        ]
    )
    result = runner_for(tmp_path, DELEGATE, store).run("w", {}, host)
    assert result.ok, result
    assert store.records() == []


NESTED = """\
# Standard version: 1.1.0
w:
  goal: g
  risk: low
  steps:
  - capability: invoke
    purpose: Run the child.
    store_as: i
    workflow_id: child
    input_bindings: {workflow: child}
child:
  goal: g
  risk: low
  steps:
  - capability: retrieve
    purpose: Read.
    store_as: r
    input_bindings: {target: t}
"""


def test_nested_steps_record_their_frame(tmp_path: Path) -> None:
    store = EvidenceStore()
    host = ScriptedHost([output(data=1, confidence=1, evidence_anchors=[FILE_A])])
    result = runner_for(tmp_path, NESTED, store).run("w", {}, host)
    assert result.ok, result
    (record,) = store.records()
    assert record.frame == ("w", "child") and record.step == 0


class BrokenStore(EvidenceStore):
    def append_many(self, anchors: Any, **context: Any) -> Any:
        raise OSError("disk full")


def test_a_store_that_raises_never_stops_the_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = BrokenStore()
    host = ScriptedHost([output(data=1, confidence=1, evidence_anchors=[FILE_A])])
    result = runner_for(tmp_path, ONE, store).run("w", {}, host)
    assert result.ok, result
    assert store.info().capture_failures == 1
    assert "disk full" in caplog.text
