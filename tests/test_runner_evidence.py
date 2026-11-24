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


# §6.7: an anchor's ref is the host's text, and a presigned or signed URL is
# a natural one for a retrieve. Neither the core's diagnostic nor the run's
# state, outputs, trace, records or snapshot may hold its credential.
SIG = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY99"
SIGNED_REFS = {
    "s3_presigned": (
        "https://bucket.s3.amazonaws.com/report.csv?X-Amz-Credential="
        f"AKIAIOSFODNN7EXAMPLE%2F20261123&X-Amz-Signature={SIG}"
    ),
    "azure_sas": f"https://acct.blob.core.windows.net/c/r.csv?sv=2022-11-02&sig={SIG}",
    "userinfo": f"https://reader:{SIG}@files.example.com/r.csv",
}
ATTESTED = GroundingPolicy(require={"retrieve"}, attested=True)


def signed_runner(tmp_path: Path, store: Any, registered: bool) -> WorkflowRunner:
    from grounded_agency.state.redaction import Redactor

    path = tmp_path / "catalog.yaml"
    path.write_text(ONE)
    engine = WorkflowEngine(ONTOLOGY, schema_root=str(ROOT))
    engine.load_catalog(path)
    return WorkflowRunner(
        engine,
        evidence_store=store,
        redactor=Redactor([SIG]) if registered else None,
    )


def kept_by(run: Any, result: Any) -> list[Any]:
    return [
        result.trace,
        result.message,
        result.outputs,
        result.action_records,
        result.run_record,
        run.run_record(),
        run.snapshot(b"k"),
    ]


@pytest.mark.parametrize("registered", [False, True])
@pytest.mark.parametrize("ref", sorted(SIGNED_REFS))
def test_no_secret_from_an_anchor_in_a_step_refused_with_f505(
    tmp_path: Path, ref: str, registered: bool
) -> None:
    """The reported route: the host's evidence_seen does not list the
    anchor, so the step fails F505, and the core's account of why names the
    anchor by its index and kind, never by the ref it cites."""
    import json

    store = EvidenceStore()
    url = SIGNED_REFS[ref]
    anchor = {"ref": url, "kind": "url"}
    host = ScriptedHost(
        [
            lambda _a: {
                "kind": "Output",
                "value": {
                    "data": {"rows": 1},
                    "confidence": 1.0,
                    "evidence_anchors": [anchor],
                },
                "evidence_seen": [],
            }
        ]
    )
    runner = signed_runner(tmp_path, store, registered)
    run = runner.start("w", {}, run_id="r1", now_ms=1_000, grounding=ATTESTED)
    result = runner.drive(run, host)
    assert result.code == "F505"
    assert "evidence_anchors[0] (kind 'url')" in result.message
    for kept in kept_by(run, result):
        text = json.dumps(kept, default=str)
        assert SIG not in text and "AKIAIOSFODNN7EXAMPLE" not in text
    assert store.records() == []


@pytest.mark.parametrize("ref", sorted(SIGNED_REFS))
def test_an_accepted_anchor_is_kept_redacted_and_still_attested(
    tmp_path: Path, ref: str
) -> None:
    """The host lists the anchor in evidence_seen: the output passes the
    attested policy, and the run keeps the anchor with its secret replaced
    and no digest (§6.5, §6.7), as the evidence store does."""
    import json

    store = EvidenceStore()
    url = SIGNED_REFS[ref]
    anchor = {"ref": url, "kind": "url", "digest": "sha256:" + "ab" * 32}
    host = ScriptedHost(
        [
            lambda _a: {
                "kind": "Output",
                "value": {
                    "data": {"rows": 1},
                    "confidence": 1.0,
                    "evidence_anchors": [anchor],
                },
                "evidence_seen": [url, "file:other.txt"],
            }
        ]
    )
    runner = signed_runner(tmp_path, store, registered=True)
    run = runner.start("w", {}, run_id="r1", now_ms=1_000, grounding=ATTESTED)
    result = runner.drive(run, host)
    assert result.ok, result
    (kept_anchor,) = result.outputs["r"]["evidence_anchors"]
    assert "[REDACTED]" in kept_anchor["ref"]
    assert "digest" not in kept_anchor
    assert kept_anchor["metadata"] == {"digest_omitted": "secret"}
    for kept in kept_by(run, result):
        text = json.dumps(kept, default=str)
        assert SIG not in text and "AKIAIOSFODNN7EXAMPLE" not in text
    (record,) = store.records()
    assert SIG not in record.anchor.ref


def test_anchors_one_after_redaction_are_attested_only_when_both_were(
    tmp_path: Path,
) -> None:
    """Two signed URLs that differ only in their signatures are one ref
    once redacted: the host listing one of them does not let the other pass
    as seen. Listing both does."""
    first = f"https://acct.blob.core.windows.net/c/r.csv?sig={SIG}"
    second = "https://acct.blob.core.windows.net/c/r.csv?sig=OtherSignature0123456789abcdefXYZ"
    anchors = [{"ref": first, "kind": "url"}, {"ref": second, "kind": "url"}]

    def answer(seen: list[str]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        return lambda _a: {
            "kind": "Output",
            "value": {"data": 1, "confidence": 1.0, "evidence_anchors": anchors},
            "evidence_seen": seen,
        }

    for seen, code in (([first], "F505"), ([second], "F505"), ([first, second], None)):
        runner = signed_runner(tmp_path, EvidenceStore(), registered=True)
        run = runner.start(
            "w",
            {},
            run_id=f"r-{len(seen)}-{seen[0][-4:]}",
            now_ms=1_000,
            grounding=ATTESTED,
        )
        result = runner.drive(run, ScriptedHost([answer(seen)]))
        assert result.code == code, (seen, result.message)
