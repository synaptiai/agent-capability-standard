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
