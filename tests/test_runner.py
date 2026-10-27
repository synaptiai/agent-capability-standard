"""The reference executor through Python (design-114 §16): the shared
runtime fixtures on ``_core.Run``, and :class:`WorkflowRunner` driving a
host end to end."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core
from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.workflows import (
    Host,
    RunStartError,
    WorkflowEngine,
    WorkflowRunner,
)

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
RUNTIME = ROOT / "tests" / "conformance" / "runtime"
FIXTURES = sorted(RUNTIME.glob("*.json"))


def matches(expected: Any, actual: Any) -> bool:
    """Every key ``expected`` names matches (arrays element by element)."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and matches(v, actual[k]) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(expected) == len(actual)
            and all(matches(x, y) for x, y in zip(expected, actual, strict=True))
        )
    return bool(expected == actual) and type(expected) is type(actual)


def fill(response: Any, action: dict[str, Any]) -> Any:
    if response == "{{digest}}":
        return action["digest"]
    if isinstance(response, dict):
        return {k: fill(v, action) for k, v in response.items()}
    if isinstance(response, list):
        return [fill(v, action) for v in response]
    return response


@pytest.fixture(scope="module")
def validator() -> _core.Validator:
    return _core.Validator(ONTOLOGY, ROOT)


def test_fixtures_exist() -> None:
    assert len(FIXTURES) >= 20


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_runtime_fixture(validator: _core.Validator, path: Path) -> None:
    f = json.loads(path.read_text())
    now = f["start"]
    run = _core.Run.start(
        validator,
        f["catalog"],
        f["workflow"],
        f["inputs"],
        attendance=f["attendance"],
        run_id="run-1",
        now_ms=now,
    )
    for i, entry in enumerate(f["script"]):
        if "tick" in entry:
            now = entry["tick"]
            run.tick(now)
            continue
        action = run.next()
        if "expect" in entry:
            assert matches(entry["expect"], action), (i, entry["expect"], action)
        if "respond" in entry:
            now = entry.get("at", now)
            run.submit(action["id"], fill(entry["respond"], action), now)
    end = run.next()
    assert matches(f["end"], end), end
    kinds = {t["kind"] for t in run.trace()}
    assert set(f["trace_kinds"]) <= kinds


# ---------------------------------------------------------------------------
# WorkflowRunner with a host
# ---------------------------------------------------------------------------

CATALOG = """\
# Standard version: 1.1.0
change_config:
  goal: Change a setting after checking policy.
  risk: high
  inputs:
    setting: {type: string, required: true}
  steps:
  - capability: retrieve
    purpose: Read the current configuration.
    store_as: current
    input_bindings:
      target: ${setting}
  - capability: checkpoint
    purpose: Save a restore point.
    store_as: cp
    input_bindings:
      scope: config
  - capability: constrain
    purpose: Check the change against policy.
    store_as: policy
    input_bindings:
      target: ${setting}
      constraints: [policy]
  - capability: mutate
    purpose: Apply the change.
    store_as: applied
    input_bindings:
      target: ${setting}
      operation: {set: true}
"""


class Clock:
    def __init__(self) -> None:
        self.now = 1_000

    def advance(self, ms: int) -> None:
        self.now += ms


class FakeHost(Host):
    """Answers every capability; approves when told to."""

    def __init__(
        self,
        clock: Clock,
        approve: bool = True,
        fail: set[str] | None = None,
        tracker: CheckpointTracker | None = None,
    ) -> None:
        super().__init__(tracker)
        self.clock = clock
        self.approve = approve
        self.fail = fail or set()
        self.calls: list[str] = []
        self.slept: list[int] = []

    def now_ms(self) -> int:
        return self.clock.now

    def sleep_until(self, until_ms: int) -> None:
        self.slept.append(until_ms)
        self.clock.now = max(self.clock.now, until_ms)

    def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
        cap = action["capability"]
        self.calls.append(cap)
        self.clock.advance(10)
        if cap in self.fail:
            raise RuntimeError(f"{cap} is down")
        outputs = {
            "retrieve": {"data": {"value": 1}, "confidence": 1.0},
            "checkpoint": {"checkpoint_id": "cp-1"},
            "constrain": {"compliant": True},
            "mutate": {"success": True},
        }
        return {"kind": "Output", "value": {**outputs[cap], "evidence_anchors": []}}

    def request_approval(self, action: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "Decision",
            "decision_id": f"d{action['id']}",
            "decision": "approved" if self.approve else "rejected",
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


def test_runner_completes(runner: WorkflowRunner) -> None:
    host = FakeHost(Clock())
    result = runner.run("change_config", {"setting": "x"}, host, run_id="r1")
    assert result.ok, result
    assert host.calls == ["retrieve", "checkpoint", "constrain", "mutate"]
    assert result.outputs["applied"]["success"] is True
    assert [r["status"] for r in result.action_records] == ["executed"]
    assert result.action_records[0]["approval"]["approvers"] == ["alice"]
    assert any(t["kind"] == "checkpoint_consumed" for t in result.trace)


def test_runner_reports_rejection(runner: WorkflowRunner) -> None:
    result = runner.run(
        "change_config", {"setting": "x"}, FakeHost(Clock(), approve=False)
    )
    assert not result.ok
    assert result.code == "F502"
    assert [r["status"] for r in result.action_records] == ["rejected"]


def test_host_exceptions_fail_the_step(runner: WorkflowRunner) -> None:
    result = runner.run(
        "change_config", {"setting": "x"}, FakeHost(Clock(), fail={"retrieve"})
    )
    assert result.code == "R402"
    assert "retrieve is down" in result.message


def test_unattended_runs_need_a_plan(runner: WorkflowRunner) -> None:
    result = runner.run(
        "change_config", {"setting": "x"}, FakeHost(Clock()), attendance="unattended"
    )
    assert result.code == "F502"


def test_start_errors_carry_diagnostics(runner: WorkflowRunner) -> None:
    with pytest.raises(RunStartError, match="needs input 'setting'"):
        runner.run("change_config", {}, FakeHost(Clock()))
    with pytest.raises(RunStartError):
        runner.run("missing", {}, FakeHost(Clock()))


def test_invalid_catalog_is_not_run(tmp_path: Path) -> None:
    catalog = tmp_path / "bad.yaml"
    catalog.write_text(CATALOG.replace("capability: mutate", "capability: teleport"))
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    with pytest.raises(RunStartError) as caught:
        WorkflowRunner(engine).run("change_config", {"setting": "x"}, FakeHost(Clock()))
    assert [d["code"] for d in caught.value.diagnostics] == ["V101"]


def test_snapshot_and_resume(runner: WorkflowRunner) -> None:
    clock = Clock()
    host = FakeHost(clock)
    run = runner.start("change_config", {"setting": "x"}, run_id="r2", now_ms=clock.now)
    action = run.next()
    run.submit(action["id"], host.invoke_capability(action), clock.now)
    snapshot = run.snapshot(b"secret")
    with pytest.raises(ValueError, match="HMAC"):
        runner.restore(snapshot, b"wrong")
    resumed = runner.restore(snapshot, b"secret")
    result = runner.drive(resumed, host)
    assert result.ok
    assert host.calls == ["retrieve", "checkpoint", "constrain", "mutate"]


def test_tracker_backed_checkpoints(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    # Two mutations after one checkpoint: the second needs a fresh one.
    catalog.write_text(
        CATALOG
        + """\
  - capability: mutate
    purpose: Apply a second change.
    store_as: applied_again
    input_bindings:
      target: ${setting}
      operation: {set: false}
"""
    )
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    tracker = CheckpointTracker(checkpoint_dir=str(tmp_path / ".checkpoints"))
    result = WorkflowRunner(engine).run(
        "change_config", {"setting": "x"}, FakeHost(Clock(), tracker=tracker)
    )
    assert result.ok, result
    created = [t for t in result.trace if t["kind"] == "checkpoint_created"]
    assert len(created) == 2
    assert (
        tracker.get_checkpoint_by_id(created[1]["detail"]["checkpoint_id"]) is not None
    )


def test_waits_time_out_through_the_host(tmp_path: Path) -> None:
    catalog = tmp_path / "wait.yaml"
    catalog.write_text(
        """\
# Standard version: 1.1.0
wait_for_job:
  goal: Wait for a job.
  risk: low
  workflow_extensions:
    requires: [wait@1]
  steps:
  - capability: receive
    purpose: Wait for the job to finish.
    store_as: done
    timeout: 5s
    wait:
      event_type: job.done
"""
    )
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    clock = Clock()

    class Quiet(FakeHost):
        def await_event(self, action: dict[str, Any]) -> dict[str, Any] | None:
            clock.advance(2_000)
            return None

    result = WorkflowRunner(engine).run("wait_for_job", None, Quiet(clock))
    assert result.code == "R401"


def test_unanswered_waits_poll_until_the_deadline(tmp_path: Path) -> None:
    """A host that has nothing yet is asked again after a poll interval, not
    in a busy loop; the wait then times out at its deadline."""
    catalog = tmp_path / "wait.yaml"
    catalog.write_text(
        """\
# Standard version: 1.1.0
wait_for_job:
  goal: Wait for a job.
  risk: low
  workflow_extensions:
    requires: [wait@1]
  steps:
  - capability: receive
    purpose: Wait for the job to finish.
    store_as: done
    timeout: 1h
    wait:
      event_type: job.done
"""
    )
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    clock = Clock()

    class Silent(FakeHost):
        polls = 0

        def await_event(self, action: dict[str, Any]) -> dict[str, Any] | None:
            Silent.polls += 1
            return None

    host = Silent(clock)
    result = WorkflowRunner(engine, max_actions=10, poll_interval_ms=60_000).run(
        "wait_for_job", None, host
    )
    assert result.code == "R401"
    # One poll a minute for an hour, not a spin.
    assert 55 <= Silent.polls <= 62
    assert host.slept[-1] == 1_000 + 3_600_000 + 1


def test_running_out_of_actions_keeps_the_run(runner: WorkflowRunner) -> None:
    from grounded_agency.workflows import RunIncomplete

    limited = WorkflowRunner(runner._engine, max_actions=1)
    with pytest.raises(RunIncomplete) as caught:
        limited.run("change_config", {"setting": "x"}, FakeHost(Clock()))
    resumed = caught.value.run
    assert not resumed.finished
    assert runner.drive(resumed, FakeHost(Clock())).ok


MANDATE_CATALOG = """\
# Standard version: 1.1.0
nightly_sync:
  goal: Sync a setting overnight, then report.
  risk: high
  workflow_extensions:
    requires: [approval@1]
  inputs:
    setting: {type: string, required: true}
  steps:
  - capability: checkpoint
    purpose: Save a restore point.
    store_as: cp
    input_bindings:
      scope: config
  - capability: constrain
    purpose: Check the change against policy.
    store_as: policy
    input_bindings:
      target: ${setting}
      constraints: [policy]
  - capability: mutate
    purpose: Apply the change.
    store_as: applied
    input_bindings:
      target: ${setting}
      operation: {set: true}
    approval:
      approver: {kind: standing_mandate, mandate_ref: mandates/nightly}
      when_unattended: defer_to_queue
  - capability: retrieve
    purpose: Read the current configuration for the report.
    store_as: report
    input_bindings:
      target: ${setting}
"""


@pytest.fixture()
def mandate_runner(tmp_path: Path) -> WorkflowRunner:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(MANDATE_CATALOG)
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    return WorkflowRunner(engine)


def test_unattended_mandate_is_asked(mandate_runner: WorkflowRunner) -> None:
    """A standing mandate is asked even when nobody is present (§5.14)."""
    host = FakeHost(Clock())
    result = mandate_runner.run(
        "nightly_sync", {"setting": "x"}, host, attendance="unattended"
    )
    assert result.ok, result
    assert host.calls == ["checkpoint", "constrain", "mutate", "retrieve"]
    assert result.deferred == []


def test_hosts_without_mandates_defer(mandate_runner: WorkflowRunner) -> None:
    """The default host holds no mandates: the action is queued, and the
    read-only report still runs."""

    class NoApprovals(FakeHost):
        request_approval = Host.request_approval

    host = NoApprovals(Clock())
    result = mandate_runner.run(
        "nightly_sync", {"setting": "x"}, host, attendance="unattended"
    )
    assert result.outcome == "deferred"
    assert host.calls == ["checkpoint", "constrain", "retrieve"]
    assert [(d["step"], d["store_as"]) for d in result.deferred] == [(2, "applied")]
    assert [r["status"] for r in result.action_records] == ["planned"]
    assert result.action_records[0]["approval"]["decision"] == "unavailable"
    assert result.deferred[0]["action_id"] == result.action_records[0]["action_id"]
