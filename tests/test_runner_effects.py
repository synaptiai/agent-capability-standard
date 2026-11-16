"""The Python host's checkpoints, rollbacks, memory and sends (STANDARD v1.2
§4.4.1, §4.4.2, §4.5): :class:`Host`'s defaults with a snapshot store, a
memory store and an idempotency log, and :class:`WorkflowRunner`'s
destination policies, durable keys and the ``run`` memory scope."""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.state.memory import MemoryStore
from grounded_agency.state.snapshots import FileSnapshotStore
from grounded_agency.workflows import Host, WorkflowEngine, WorkflowRunner
from grounded_agency.workflows.idempotency import IdempotencyLog
from tests.runtime_replay import ONTOLOGY, ROOT

CATALOG = """\
# Standard version: 1.2.0
change_and_restore:
  goal: Change a file, remember it, and restore the file.
  risk: high
  steps:
  - capability: checkpoint
    purpose: Save the files.
    store_as: cp
    input_bindings:
      scope: "*"
  - capability: constrain
    purpose: Check the change.
    store_as: policy
    input_bindings:
      target: app.cfg
      constraints: [policy]
  - capability: mutate
    purpose: Change the file.
    store_as: changed
    input_bindings:
      target: app.cfg
      operation: {set: v1}
  - capability: persist
    purpose: Remember the change for this run.
    store_as: note
    input_bindings:
      key: change
      data: {file: app.cfg}
      scope: run
  - capability: recall
    purpose: Read it back.
    store_as: noted
    input_bindings:
      key: change
      scope: run
  - capability: rollback
    purpose: Restore the file.
    store_as: rb
    input_bindings:
      checkpoint_id: ${cp.checkpoint_id}
    gates:
    - when: ${rb.restored} == false
      phase: after
      action: stop
send_report:
  goal: Send a report.
  risk: high
  inputs:
    to:
      type: string
      required: true
  steps:
  - capability: checkpoint
    purpose: Save the agent's state.
    store_as: cp
    input_bindings:
      scope: "*"
  - capability: constrain
    purpose: Check the destination.
    store_as: policy
    input_bindings:
      target: ${to}
      constraints: [allowed destinations]
  - capability: send
    purpose: Send the report.
    store_as: sent
    input_bindings:
      destination: ${to}
      payload: {report: 1}
"""


class Files(Host):
    """Performs mutate on a file under ``root`` and send through
    :meth:`Host.send_once`; everything else by the defaults."""

    def __init__(self, root: Path, tracker: CheckpointTracker, **kw: Any) -> None:
        super().__init__(tracker, **kw)
        self.root = root
        self.sent: list[str] = []

    def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
        cap = action["capability"]
        if cap == "constrain":
            return {
                "kind": "Output",
                "value": {"compliant": True, "evidence_anchors": []},
            }
        if cap == "mutate":
            (self.root / action["inputs"]["target"]).write_text("v1")
            return {
                "kind": "Output",
                "value": {"success": True, "evidence_anchors": []},
            }
        if cap == "send":

            def transmit() -> dict[str, Any]:
                self.sent.append(action["inputs"]["destination"])
                return {
                    "kind": "Output",
                    "value": {"sent": True, "evidence_anchors": []},
                }

            return self.send_once(action, transmit)
        return super().invoke_capability(action)

    def request_approval(self, action: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "Decision",
            "decision_id": f"d{action['id']}",
            "decision": "approved",
            "approvers": ["alice"],
            "digest": action["digest"],
        }


@pytest.fixture()
def runner(tmp_path: Path) -> WorkflowRunner:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(CATALOG)
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    return WorkflowRunner(engine)


def files_host(tmp_path: Path, **kw: Any) -> tuple[Path, Files]:
    root = tmp_path / "work"
    root.mkdir(parents=True)
    (root / "app.cfg").write_text("v0")
    snapshots = FileSnapshotStore(root, tmp_path / "snapshots")
    tracker = CheckpointTracker(
        checkpoint_dir=tmp_path / ".checkpoints", snapshots=snapshots
    )
    return root, Files(root, tracker, **kw)


def test_checkpoint_rollback_persist_and_recall_steps(
    runner: WorkflowRunner, tmp_path: Path
) -> None:
    root, host = files_host(tmp_path, memory=MemoryStore())
    result = runner.run("change_and_restore", {}, host, run_id="r1")
    assert result.ok, result
    assert (root / "app.cfg").read_text() == "v0"
    cp = result.outputs["cp"]
    assert cp["mechanism"] == "file_copy" and cp["captured"] == ["app.cfg"]
    assert cp["digest"].startswith("sha256:")
    assert result.outputs["note"]["scope"] == "run"
    assert result.outputs["noted"]["data"] == {"file": "app.cfg"}
    rb = result.outputs["rb"]
    assert rb["restored"] is True and rb["verification"]["match"] is True
    assert rb["changes_reverted"] == [{"item": "app.cfg", "operation": "modify"}]
    # The run scope ended with the run (§4.5).
    assert host.memory is not None
    assert host.memory.end_scope("run", "r1") == 0


def test_the_executors_rollback_lists_this_runs_transmissions(tmp_path: Path) -> None:
    root, host = files_host(tmp_path, idempotency=IdempotencyLog())
    checkpoint = host.create_checkpoint({"step": 0, "frame": ["w"]})["checkpoint_id"]
    for key, destination in (
        ("r1:5", "https://u:p4ssw0rd-secret@hooks.example.com/x"),
        ("r2:5", "elsewhere"),
    ):
        host.send_once(
            {
                "run_id": key.split(":")[0],
                "capability": "send",
                "idempotency_key": key,
                "inputs": {"destination": destination, "payload": 1},
            },
            lambda: {"kind": "Output", "value": {"sent": True}},
        )
    (root / "app.cfg").write_text("v1")
    answer = host.rollback({"checkpoint_id": checkpoint, "run_id": "r1"})
    assert answer["kind"] == "RolledBack"
    assert (root / "app.cfg").read_text() == "v0"
    items = answer["not_covered"]
    assert [i["reason"] for i in items] == ["transmitted"]
    assert "r1:5" in items[0]["item"] and "p4ssw0rd" not in items[0]["item"]
    # Nothing transmitted since: no not_covered member.
    assert "not_covered" not in host.rollback(
        {"checkpoint_id": checkpoint, "run_id": "r3"}
    )


def test_a_rollback_lists_a_send_whose_outcome_is_unknown(tmp_path: Path) -> None:
    _, host = files_host(tmp_path, idempotency=IdempotencyLog())
    checkpoint = host.create_checkpoint({"step": 0, "frame": ["w"]})["checkpoint_id"]

    def timed_out() -> dict[str, Any]:
        raise TimeoutError("the request went out; no answer came back")

    with pytest.raises(TimeoutError):
        host.send_once(
            {
                "run_id": "r1",
                "capability": "send",
                "idempotency_key": "r1:4",
                "inputs": {"destination": "ops", "payload": 1},
            },
            timed_out,
        )
    answer = host.rollback({"checkpoint_id": checkpoint, "run_id": "r1"})
    assert answer["kind"] == "RolledBack"
    assert answer["not_covered"] == [
        {
            "item": "send to ops (r1:4)",
            "reason": "transmitted",
            "detail": "outcome unknown",
        }
    ]


def test_a_failed_restore_is_f503(tmp_path: Path) -> None:
    _, host = files_host(tmp_path)
    checkpoint = host.create_checkpoint({"step": 0, "frame": ["w"]})["checkpoint_id"]
    assert host.checkpoint_tracker is not None
    snapshots = host.checkpoint_tracker.snapshots
    assert snapshots is not None
    snapshots.discard(checkpoint)
    answer = host.rollback({"checkpoint_id": checkpoint, "run_id": "r1"})
    assert (answer["kind"], answer["code"]) == ("Error", "F503")
    assert "discarded" in answer["message"]
    unknown = host.rollback({"checkpoint_id": "nope", "run_id": "r1"})
    assert unknown["code"] == "F503"


def test_a_rollback_leaves_the_hosts_records(tmp_path: Path) -> None:
    root, host = files_host(
        tmp_path,
        idempotency=IdempotencyLog(tmp_path / "work" / "keys.jsonl"),
        protected_paths=[tmp_path / "work" / "runs"],
    )
    checkpoint = host.create_checkpoint({"step": 0, "frame": ["w"]})["checkpoint_id"]
    (root / "runs").mkdir()
    (root / "runs" / "r1.json").write_text("{}")
    host.send_once(
        {
            "run_id": "r1",
            "capability": "send",
            "idempotency_key": "r1:2",
            "inputs": {"destination": "ops", "payload": 1},
        },
        lambda: {"kind": "Output", "value": {"sent": True}},
    )
    shutil.copy(root / "keys.jsonl", tmp_path / "keys.before")
    assert (
        host.rollback({"checkpoint_id": checkpoint, "run_id": "r1"})["kind"]
        == "RolledBack"
    )
    assert filecmp.cmp(root / "keys.jsonl", tmp_path / "keys.before", shallow=False)
    assert (root / "runs" / "r1.json").read_text() == "{}"


def test_a_rollback_leaves_the_runners_evidence(tmp_path: Path) -> None:
    """The runner's evidence store, kept in a file under the snapshot
    root, is the record of what happened (§4.4.1): the rollback step and
    the executor's rollback leave it as it is, and later records reach it."""
    from grounded_agency.state.jsonl_evidence_store import JsonlEvidenceStore

    class Grounded(Files):
        def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
            response = super().invoke_capability(action)
            if action["capability"] == "mutate":
                response["value"]["evidence_anchors"] = [
                    {"ref": "file:app.cfg", "kind": "file"}
                ]
            return response

    root = tmp_path / "work"
    root.mkdir()
    (root / "app.cfg").write_text("v0")
    tracker = CheckpointTracker(
        checkpoint_dir=tmp_path / ".checkpoints",
        snapshots=FileSnapshotStore(root, tmp_path / "snapshots"),
    )
    host = Grounded(root, tracker, memory=MemoryStore())
    evidence = JsonlEvidenceStore(root / "evidence.jsonl")
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(CATALOG)
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    runner = WorkflowRunner(engine, evidence_store=evidence)
    result = runner.run("change_and_restore", {}, host, run_id="r1")
    assert result.ok, result
    assert (root / "app.cfg").read_text() == "v0"
    rb = result.outputs["rb"]
    assert rb["changes_reverted"] == [{"item": "app.cfg", "operation": "modify"}]
    assert "evidence.jsonl" in result.outputs["cp"]["excluded"]
    kept = len(evidence)
    assert kept >= 1
    lines = (root / "evidence.jsonl").read_text().splitlines()
    assert len(lines) == kept
    checkpoint = host.create_checkpoint({"step": 0, "frame": ["w"]})["checkpoint_id"]
    from grounded_agency.state.evidence_store import EvidenceAnchor

    evidence.add_anchor(EvidenceAnchor.from_tool_output("Read", "t", {"path": "x"}))
    assert host.rollback({"checkpoint_id": checkpoint, "run_id": "r1"})["kind"] == (
        "RolledBack"
    )
    evidence.add_anchor(EvidenceAnchor.from_tool_output("Read", "u", {"path": "x"}))
    lines = (root / "evidence.jsonl").read_text().splitlines()
    assert len(lines) == len(evidence) == kept + 2


@pytest.mark.parametrize("how", ["host", "profile"])
def test_destination_policies_reach_the_run(
    runner: WorkflowRunner, tmp_path: Path, how: str
) -> None:
    _, host = files_host(tmp_path)
    policy = ["https://hooks.example.com/*"]
    if how == "host":
        result = runner.run(
            "send_report",
            {"to": "https://evil.example.net/x"},
            host,
            destinations=[policy],
        )
    else:
        catalog = tmp_path / "catalog.yaml"
        engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
        engine.load_catalog(catalog)
        profile = {"domain": "d", "version": "1.0.0", "allowed_destinations": policy}
        result = WorkflowRunner(engine, profiles=[profile]).run(
            "send_report", {"to": "https://evil.example.net/x"}, host
        )
    assert (result.code, result.reason) == ("F504", "destination_not_allowed")
    assert host.sent == []
    assert not any(t["kind"] == "approval_requested" for t in result.trace)
    ok = runner.run(
        "send_report",
        {"to": "https://hooks.example.com/r"},
        host,
        destinations=[policy],
    )
    assert ok.ok and host.sent == ["https://hooks.example.com/r"]


def test_a_saving_runner_needs_durable_keys(
    runner: WorkflowRunner, tmp_path: Path
) -> None:
    saved: list[dict[str, Any]] = []
    _, host = files_host(tmp_path, idempotency=IdempotencyLog())
    with pytest.raises(ValueError, match="give IdempotencyLog a path"):
        runner.run("send_report", {"to": "ops"}, host, save=saved.append)
    assert saved == [] and host.sent == []
    run = runner.start("send_report", {"to": "ops"})
    with pytest.raises(ValueError, match="durably"):
        runner.drive(run, host, save=saved.append)
    assert host.sent == []
    _, durable = files_host(
        tmp_path / "2", idempotency=IdempotencyLog(tmp_path / "k.jsonl")
    )
    assert runner.run("send_report", {"to": "ops"}, durable, save=saved.append).ok
    assert saved


def test_a_deferred_end_keeps_the_run_scope(
    runner: WorkflowRunner, tmp_path: Path
) -> None:
    from grounded_agency.state.memory import MemoryContext

    _, host = files_host(tmp_path, memory=MemoryStore())
    assert host.memory is not None
    run = runner.start("send_report", {"to": "ops"}, run_id="r9")
    host.memory.persist(
        {"key": "k", "data": 1, "scope": "run"}, MemoryContext(run="r9")
    )
    deferred = {
        "kind": "Completed",
        "outcome": "deferred",
        "outputs": {},
        "action_records": [],
        "deferred": [],
    }
    runner._ended(run, deferred, host)
    assert host.memory.recall({"key": "k", "scope": "run"}, MemoryContext(run="r9"))[
        "found"
    ]
    runner._ended(run, {**deferred, "outcome": "completed"}, host)
    assert not host.memory.recall(
        {"key": "k", "scope": "run"}, MemoryContext(run="r9")
    )["found"]


def test_a_cancel_without_a_host_ends_the_run_scope(tmp_path: Path) -> None:
    """A deferred run's ``run`` entries last until it is resumed and ends,
    or is cancelled (§4.5): the runner ends them in its own ``memory``, so a
    cancel with no host at hand ends them too."""
    from grounded_agency.state.memory import MemoryContext

    memory = MemoryStore()
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(CATALOG)
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    runner = WorkflowRunner(engine, memory=memory)
    run = runner.start("send_report", {"to": "ops"}, run_id="r9")
    memory.persist({"key": "k", "data": 1, "scope": "run"}, MemoryContext(run="r9"))
    result = runner.cancel(run, "no longer needed", now_ms=1)
    assert result.cancelled
    assert not memory.recall({"key": "k", "scope": "run"}, MemoryContext(run="r9"))[
        "found"
    ]


def test_a_persist_without_a_key_is_idempotent_under_its_pass(tmp_path: Path) -> None:
    """A persist with no key gets one derived from the pass's idempotency
    key (§4.4.2, §5.19.4): a retry or a re-delivery of the pass replaces its
    entry and leaves no orphan; another pass gets another key."""
    memory = MemoryStore()
    _, host = files_host(tmp_path, memory=memory)
    action = {
        "capability": "persist",
        "run_id": "r1",
        "id": 4,
        "step": 0,
        "frame": ["w"],
        "idempotency_key": "r1:4",
        "inputs": {"data": {"n": 1}, "scope": "run"},
    }
    first = host.invoke_capability(action)["value"]["key"]
    again = host.invoke_capability({**action, "id": 5})["value"]["key"]
    assert first == again
    other = host.invoke_capability({**action, "idempotency_key": "r1:6"})
    assert other["value"]["key"] != first
    assert memory.end_scope("run", "r1") == 2
    # A key the step gives is kept.
    named = {**action, "inputs": {"key": "k", "data": 1, "scope": "run"}}
    assert host.invoke_capability(named)["value"]["key"] == "k"


def test_an_unrepresentable_ttl_is_an_error_with_its_reason(tmp_path: Path) -> None:
    memory = MemoryStore()
    _, host = files_host(tmp_path, memory=memory)
    answer = host.invoke_capability(
        {
            "capability": "persist",
            "run_id": "r1",
            "step": 0,
            "frame": ["w"],
            "inputs": {"key": "k", "data": 1, "ttl": "P3000000D"},
        }
    )
    assert (answer["kind"], answer["code"], answer["reason"]) == (
        "Error",
        "R402",
        "unsupported_ttl",
    )
    assert memory.end_scope("session", host.session_id) == 0


def test_a_memory_refusal_is_an_error_with_its_reason(tmp_path: Path) -> None:
    _, host = files_host(tmp_path, memory=MemoryStore(scopes=("session",)))
    answer = host.invoke_capability(
        {
            "capability": "persist",
            "run_id": "r1",
            "step": 0,
            "frame": ["w"],
            "inputs": {"key": "k", "data": 1, "scope": "global"},
        }
    )
    assert (answer["kind"], answer["code"], answer["reason"]) == (
        "Error",
        "R402",
        "unsupported_scope",
    )


ROLLBACK_ON_FAIL = {
    "w": {
        "goal": "g",
        "risk": "medium",
        "spec_version": "1.2",
        "steps": [
            {
                "capability": "checkpoint",
                "purpose": "p",
                "store_as": "cp",
                "input_bindings": {"scope": "*"},
            },
            {
                "capability": "verify",
                "purpose": "p",
                "store_as": "v",
                "input_bindings": {"target": "x", "criteria": ["c"]},
                "failure_modes": [
                    {
                        "condition": "c",
                        "when": "${v.passed} == false",
                        "action": "rollback",
                    }
                ],
            },
        ],
    }
}


@pytest.mark.parametrize("bad", [None, {}, "x", [1]])
def test_a_malformed_not_covered_is_refused(bad: Any) -> None:
    # §5.19.1: a `RolledBack` whose `not_covered` is not a list of objects
    # is refused as malformed; `null` is not read as absent.
    from grounded_agency import _core

    run = _core.Run.start(
        _core.Validator(ONTOLOGY, ROOT),
        ROLLBACK_ON_FAIL,
        "w",
        header=None,
        run_id="r",
        now_ms=0,
    )
    a = run.next()
    run.submit(
        a["id"],
        {"kind": "Output", "value": {"checkpoint_id": "cp1", "evidence_anchors": []}},
        0,
    )
    a = run.next()
    run.submit(
        a["id"],
        {
            "kind": "Output",
            "value": {"passed": False, "evidence_anchors": [], "confidence": 0.9},
        },
        0,
    )
    rollback = run.next()
    assert rollback["kind"] == "Rollback"
    with pytest.raises(ValueError, match="malformed"):
        run.submit(rollback["id"], {"kind": "RolledBack", "not_covered": bad}, 0)
    assert run.next() == rollback
    run.submit(rollback["id"], {"kind": "RolledBack"}, 0)
    assert run.next()["kind"] == "Failed"


@pytest.mark.parametrize(
    "destinations",
    [["ops@example.com"], ["https://hooks.example.com/*"], "ops", [["ok"], [1]]],
)
def test_a_flat_list_of_patterns_is_a_type_error(
    runner: WorkflowRunner, destinations: Any
) -> None:
    # A string is a sequence of strings: without the check, a flat list of
    # patterns became a policy of one-character patterns.
    with pytest.raises(TypeError, match="list of"):
        runner.start("send_report", {"to": "ops"}, destinations=destinations)
    assert runner.start(
        "send_report", {"to": "ops"}, destinations=[["ops@example.com"]]
    )


def test_unknown_members_of_a_not_covered_item_are_ignored() -> None:
    """§5.19.1: an item's members the protocol does not define, and a
    `detail` that is not a string, are ignored, not refused (a host may send
    members a later version defines); the trace keeps `item`, `reason` and a
    string `detail`."""
    from grounded_agency import _core

    run = _core.Run.start(
        _core.Validator(ONTOLOGY, ROOT),
        ROLLBACK_ON_FAIL,
        "w",
        header=None,
        run_id="r",
        now_ms=0,
    )
    a = run.next()
    run.submit(
        a["id"],
        {"kind": "Output", "value": {"checkpoint_id": "cp1", "evidence_anchors": []}},
        0,
    )
    a = run.next()
    run.submit(
        a["id"],
        {
            "kind": "Output",
            "value": {"passed": False, "evidence_anchors": [], "confidence": 0.9},
        },
        0,
    )
    rollback = run.next()
    sent = [
        {
            "item": "send to ops (r:3)",
            "reason": "transmitted",
            "since": "2026-11-16T00:00:00Z",
        },
        {"item": "task t1", "reason": "delegated", "detail": 5},
    ]
    run.submit(rollback["id"], {"kind": "RolledBack", "not_covered": sent}, 0)
    assert run.next()["kind"] == "Failed"
    traced = next(t for t in run.trace() if t["kind"] == "rolled_back")
    assert traced["detail"]["not_covered"] == [
        {"item": "send to ops (r:3)", "reason": "transmitted"},
        {"item": "task t1", "reason": "delegated"},
    ]
