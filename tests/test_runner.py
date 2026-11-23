"""The reference executor through Python (design-114 §16): the shared
runtime fixtures on ``_core.Run``, and :class:`WorkflowRunner` driving a
host end to end."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core
from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.workflows import (
    Host,
    RunResult,
    RunStartError,
    WorkflowEngine,
    WorkflowRunner,
)
from tests.runtime_replay import (
    FIXTURES,
    ONTOLOGY,
    ROOT,
    RUNTIME,
    fill,
    load,
    matches,
    play,
    start,
)


@pytest.fixture(scope="module")
def validator() -> _core.Validator:
    return _core.Validator(ONTOLOGY, ROOT)


def test_fixtures_exist() -> None:
    assert len(FIXTURES) >= 20


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_runtime_fixture(validator: _core.Validator, path: Path) -> None:
    f = load(path)

    def expect(i: int, expected: Any, action: dict[str, Any]) -> None:
        assert matches(expected, action), (i, expected, action)

    run = play(start(validator, f), f, expect)
    end = run.next()
    assert matches(f["end"], end), end
    assert end["run_id"] == "run-1"
    if "run_record" in f:
        assert matches(f["run_record"], run.run_record()), run.run_record()
    kinds = {t["kind"] for t in run.trace()}
    assert set(f["trace_kinds"]) <= kinds


def test_replacement_is_per_run(validator: _core.Validator) -> None:
    """A parent loop that runs an invoke again starts a new child run: its
    waiting delegate does not name the old run's delegation (§5.13). Fixture
    matching is by subset, so the absent key is checked here."""
    f = load(RUNTIME / "delegate_wait_replaced_per_run.json")
    run = start(validator, f)
    delegations = []
    for entry in f["script"]:
        action = run.next()
        if action["kind"] == "InvokeCapability" and action["capability"] == "delegate":
            delegations.append(action)
        run.submit(action["id"], fill(entry["respond"], action), 0)
    assert len(delegations) == 2
    assert all("replaces" not in d for d in delegations)


def test_no_binding_without_identity(validator: _core.Validator) -> None:
    """Without identity@1 a waiting delegate's wait carries no
    delegate_principal (§5.17); fixture matching is by subset, so the absent
    key is checked here."""
    name = "delegate_identity_needs_identity_extension.json"
    f = load(RUNTIME / name)
    run = start(validator, f)
    waits = []
    for entry in f["script"]:
        action = run.next()
        if action["kind"] == "AwaitEvent":
            waits.append(action)
        run.submit(action["id"], fill(entry["respond"], action), 0)
    assert waits and all("delegate_principal" not in w for w in waits)


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


@pytest.mark.parametrize(
    "response",
    [
        {"kind": "Output"},
        ["not", "a", "dict"],
        {"kind": "Output", "value": {"x": float("nan")}},
        {"kind": "Output", "value": {"x": 2**64}},
        {"kind": "Output", "value": {"when": datetime.date(2026, 1, 1)}},
        {"kind": "Decision", "decision": "approved"},
    ],
    ids=["no-value", "list", "nan", "huge-int", "date", "wrong-kind"],
)
def test_malformed_capability_responses_fail_the_step(
    runner: WorkflowRunner, response: Any
) -> None:
    """A response the run refuses fails the step (R402), as a host exception
    does, instead of escaping drive() and losing the run."""

    class Garbled(FakeHost):
        def invoke_capability(self, action: dict[str, Any]) -> Any:
            return response

    result = runner.run("change_config", {"setting": "x"}, Garbled(Clock()))
    assert result.code == "R402"
    assert "refused" in result.message


def test_malformed_other_responses_keep_the_run(runner: WorkflowRunner) -> None:
    from grounded_agency.workflows import HostResponseError, RunIncomplete

    class BadApprover(FakeHost):
        def request_approval(self, action: dict[str, Any]) -> Any:
            return {"kind": "Decision", "decision": "approved"}

    with pytest.raises(HostResponseError) as caught:
        runner.run("change_config", {"setting": "x"}, BadApprover(Clock()))
    assert isinstance(caught.value, RunIncomplete)
    assert caught.value.action["kind"] == "RequestApproval"
    run = caught.value.run
    assert not run.finished
    assert run.next()["id"] == caught.value.action["id"]  # still waiting
    assert runner.drive(run, FakeHost(Clock())).ok


def test_unanswered_actions_without_deadline_are_bounded(
    runner: WorkflowRunner,
) -> None:
    """An approval with no expiry that the host never answers ends the
    drive after max_polls polls, with the live run attached."""
    from grounded_agency.workflows import RunIncomplete

    class Absent(FakeHost):
        def request_approval(self, action: dict[str, Any]) -> Any:
            return None

    limited = WorkflowRunner(runner._engine, max_polls=5)
    host = Absent(Clock())
    with pytest.raises(RunIncomplete, match="after 5 polls") as caught:
        limited.run("change_config", {"setting": "x"}, host)
    assert len(host.slept) == 5
    assert runner.drive(caught.value.run, FakeHost(Clock())).ok


def test_polls_are_bounded_per_action(runner: WorkflowRunner) -> None:
    """Each action has its own poll budget: a host that answers every
    capability on its third ask finishes with max_polls=2, though the run
    polls far more than twice in all."""

    class Slow(FakeHost):
        def __init__(self, clock: Clock) -> None:
            super().__init__(clock)
            self.asks: dict[str, int] = {}

        def invoke_capability(self, action: dict[str, Any]) -> Any:
            n = self.asks[action["id"]] = self.asks.get(action["id"], 0) + 1
            return None if n < 3 else super().invoke_capability(action)

    host = Slow(Clock())
    result = WorkflowRunner(runner._engine, max_polls=2).run(
        "change_config", {"setting": "x"}, host
    )
    assert result.ok
    assert len(host.slept) > 2


def test_a_bad_clock_is_not_blamed_on_the_run(runner: WorkflowRunner) -> None:
    """A clock that returns a float is the host's bug: a TypeError, not a
    RunStartError or a refused response."""

    class FloatClock(FakeHost):
        def now_ms(self) -> int:
            return 1.5  # type: ignore[return-value]

    with pytest.raises(TypeError, match="clock reading"):
        runner.run("change_config", {"setting": "x"}, FloatClock(Clock()))
    with pytest.raises(ValueError, match="clock reading"):
        runner.start("change_config", {"setting": "x"}, now_ms=-1)
    with pytest.raises(TypeError, match="key must be bytes"):
        runner.restore({}, key="secret")  # type: ignore[arg-type]


def test_non_json_inputs_refuse_the_start(runner: WorkflowRunner) -> None:
    with pytest.raises(RunStartError, match="workflow data") as caught:
        runner.start("change_config", {"setting": {1, 2}})
    assert caught.value.diagnostics == []


def test_restore_errors_are_run_start_errors(
    runner: WorkflowRunner, tmp_path: Path
) -> None:
    run = runner.start("change_config", {"setting": "x"}, now_ms=1_000)
    snapshot = run.snapshot()
    with pytest.raises(RunStartError, match="malformed snapshot"):
        runner.restore({"state": "nonsense"})
    with pytest.raises(RunStartError):
        runner.restore({**snapshot, "extra": object()})

    # A catalog that no longer validates: the diagnostics, not a tuple.
    catalog = tmp_path / "bad.yaml"
    catalog.write_text(CATALOG.replace("capability: mutate", "capability: teleport"))
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    with pytest.raises(RunStartError) as caught:
        WorkflowRunner(engine).restore(snapshot)
    assert not str(caught.value).startswith("(")
    assert [d["code"] for d in caught.value.diagnostics] == ["V101"]


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


def test_runtime_fixtures_are_generated() -> None:
    """The JSON fixtures are the output of scripts/gen_runtime_fixtures.py."""
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_runtime_fixtures.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_identities_on_records_and_received_items(tmp_path: Path) -> None:
    """identity@1 (STANDARD v1.1 §5.17): the run's actor identity is on every
    action record, and a kept item carries the identity the host reported;
    one from another trust class is dropped."""
    from grounded_agency.coordination.registry import AgentDescriptor

    catalog = tmp_path / "identity.yaml"
    catalog.write_text(
        """\
# Standard version: 1.1.0
answer_then_act:
  goal: Act on the owner's answer.
  risk: high
  workflow_extensions:
    requires: [wait@1, identity@1]
  steps:
  - capability: receive
    purpose: Wait for the owner's answer.
    store_as: answer
    timeout: 1h
    input_bindings:
      sender_check: [session_id]
      accept_trust_classes: [owner]
    wait:
      event_type: answer
  - capability: checkpoint
    purpose: Save a restore point.
    store_as: cp
    input_bindings:
      scope: config
  - capability: mutate
    purpose: Apply the answer.
    store_as: applied
    input_bindings:
      target: config
      operation:
        answer: "${answer.data: array<object>}"
"""
    )
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    clock = Clock()
    owner = {
        "principal": "dana",
        "kind": "human",
        "authenticated_by": "session_id",
        "trust_class": "owner",
    }
    peer = {
        **owner,
        "principal": "agent-7",
        "kind": "agent",
        "trust_class": "peer_agent",
    }

    class Answers(FakeHost):
        def __init__(self, clock: Clock) -> None:
            super().__init__(clock)
            self.events = [peer, owner]

        def await_event(self, action: dict[str, Any]) -> dict[str, Any] | None:
            identity = self.events.pop(0)
            return {
                "kind": "Event",
                "event": {"event_type": "answer"},
                "identity": identity,
            }

    agent = AgentDescriptor(
        agent_id="orchestrator",
        capabilities=frozenset({"receive"}),
        metadata={"model_family": "claude", "trust_class": "own_subagent_report"},
    )
    result = WorkflowRunner(engine).run(
        "answer_then_act", None, Answers(clock), actor_identity=agent.identity()
    )
    assert result.ok, result
    assert result.outputs["answer"]["data"] == [
        {"event_type": "answer", "sender": "dana", "sender_identity": owner}
    ]
    assert [r["actor_identity"] for r in result.action_records] == [agent.identity()]
    dropped = [t for t in result.trace if t["kind"] == "event_dropped"]
    assert [t["detail"]["reason"] for t in dropped] == ["accept_trust_classes"]
    received = next(t for t in result.trace if t["kind"] == "event_received")
    assert received["detail"]["dropped"] == {"accept_trust_classes": 1}


def test_a_malformed_actor_identity_refuses_the_start(runner: WorkflowRunner) -> None:
    with pytest.raises(RunStartError, match="actor_identity"):
        runner.start(
            "change_config", {"setting": "x"}, actor_identity={"kind": "agent"}
        )


def test_an_end_gate_and_a_delay(tmp_path: Path) -> None:
    """A delay sleeps through the host's clock before the step, and a gate
    with action end ends the run successfully (RunResult.ended)."""
    catalog = tmp_path / "end.yaml"
    catalog.write_text(
        """\
# Standard version: 1.1.0
sample_twice:
  goal: Sample, wait a minute, sample again, stop if nothing changed.
  risk: low
  workflow_extensions:
    requires: [wait@1]
  steps:
  - capability: retrieve
    purpose: First sample.
    store_as: first
    input_bindings: {target: queue}
  - capability: retrieve
    purpose: Second sample, a minute later.
    store_as: second
    delay: 1m
    input_bindings: {target: queue}
    gates:
    - when: ${second.data} == ${first.data}
      phase: after
      action: end
      message: Nothing changed.
  - capability: search
    purpose: Look into the change.
    store_as: found
    input_bindings: {query: change}
"""
    )
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    host = FakeHost(Clock())
    result = WorkflowRunner(engine).run("sample_twice", None, host)
    assert result.ok, result
    assert result.ended == {"step": 1, "message": "Nothing changed."}
    assert host.calls == ["retrieve", "retrieve"]
    # The second sample waited a minute after the first.
    assert host.slept == [1_000 + 10 + 60_000]


# ---------------------------------------------------------------------------
# Resuming a deferred run (STANDARD v1.2 §5.14.1), the restore actor and
# approver identities (§5.17)
# ---------------------------------------------------------------------------


class NoMandates(FakeHost):
    """Holds no mandates, as the default host: a mandate is unavailable."""

    request_approval = Host.request_approval


class Approves(FakeHost):
    """Approves every request, recording what it was asked."""

    def __init__(self, clock: Clock) -> None:
        super().__init__(clock)
        self.asked: list[dict[str, Any]] = []

    def request_approval(self, action: dict[str, Any]) -> dict[str, Any]:
        self.asked.append(action)
        return super().request_approval(action)

    def create_checkpoint(self, action: dict[str, Any]) -> dict[str, Any]:
        return {"kind": "Checkpoint", "checkpoint_id": f"cp-{action['id']}"}


def deferred_nightly(runner: WorkflowRunner) -> tuple[dict[str, Any], Any]:
    """The nightly sync run unattended by a host without mandates: it ends
    deferred, saved with a key."""
    clock = Clock()
    run = runner.start(
        "nightly_sync", {"setting": "x"}, attendance="unattended", now_ms=clock.now
    )
    result = runner.drive(run, NoMandates(clock))
    assert result.outcome == "deferred" and result.resumable
    return run.snapshot(b"secret"), result


def test_resume_a_deferred_run(mandate_runner: WorkflowRunner) -> None:
    saved, first = deferred_nightly(mandate_runner)
    queued = first.action_records[0]["action_id"]
    host = Approves(Clock())
    run = mandate_runner.resume(saved, b"secret", attendance="attended")
    result = mandate_runner.drive(run, host)
    assert result.ok, result
    # Asked of a person (attended), naming the queued action; the mutate
    # gets a new checkpoint; the report, which ran ahead, reads nothing it
    # changed and is not run again.
    [asked] = host.asked
    assert asked["approver"] == {"kind": "human"}
    assert asked["queued_action_id"] == queued
    assert host.calls == ["mutate"]
    assert [(r["action_id"], r["status"]) for r in result.action_records] == [
        (queued, "executed")
    ]
    assert result.action_records[0]["approval"]["mandate_ref"] is None
    assert result.deferred == []
    assert any(t["kind"] == "run_resumed" for t in result.trace)


def test_resumed_mandate_step_asks_a_person(mandate_runner: WorkflowRunner) -> None:
    """Subset matching cannot show a key is absent: the request of an
    attended resumption names no mandate_ref (§5.14.1)."""
    saved, _ = deferred_nightly(mandate_runner)
    host = Approves(Clock())
    mandate_runner.drive(mandate_runner.resume(saved, b"secret"), host)
    assert "mandate_ref" not in host.asked[0]["approver"]


def test_resume_refuses_other_outcomes(
    runner: WorkflowRunner, validator: _core.Validator
) -> None:
    clock = Clock()
    run = runner.start("change_config", {"setting": "x"}, now_ms=clock.now)
    with pytest.raises(RunStartError, match="has not finished"):
        runner.resume(run.snapshot())
    runner.drive(run, FakeHost(clock))
    with pytest.raises(RunStartError, match="ended completed"):
        runner.resume(run.snapshot())


def test_resume_refuses_a_failed_run_with_planned_records(
    validator: _core.Validator,
) -> None:
    """A run that fails after deferring keeps its planned record, but it
    cannot be resumed: the queued action is abandoned (§5.14.1)."""
    f = load(RUNTIME / "failure_after_deferral.json")
    run = play(start(validator, f), f)
    end = run.next()
    assert end["kind"] == "Failed"
    assert [r["status"] for r in end["action_records"]] == ["planned"]
    saved = run.snapshot()
    with pytest.raises(ValueError, match="failed with R402"):
        run.resume(now_ms=1)
    assert run.snapshot() == saved


def test_resume_refuses_an_old_state(mandate_runner: WorkflowRunner) -> None:
    """A state saved before the executor kept which steps ran ahead cannot
    be resumed: cancel the run and start a new one."""
    import hashlib
    import json

    saved, _ = deferred_nightly(mandate_runner)
    state = json.loads(saved["state"])
    for frame in state["frames"]:
        frame.pop("ahead", None)
    text = _core.canonical_json(state)
    old = {
        "state": text,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "hmac": None,
    }
    with pytest.raises(RunStartError, match="ran after its first deferral"):
        mandate_runner.resume(old)


def test_restore_refuses_another_actor(runner: WorkflowRunner) -> None:
    a = {"principal": "agent-a", "kind": "agent"}
    run = runner.start("change_config", {"setting": "x"}, now_ms=1, actor_identity=a)
    saved = run.snapshot()
    assert runner.restore(saved, actor_identity=a).next() == run.next()
    with pytest.raises(RunStartError, match="agent-a"):
        runner.restore(saved, actor_identity={"principal": "agent-b", "kind": "agent"})
    anonymous = runner.start("change_config", {"setting": "x"}, now_ms=1).snapshot()
    with pytest.raises(RunStartError, match="without an actor"):
        runner.restore(anonymous, actor_identity=a)


def test_resume_under_a_new_actor(mandate_runner: WorkflowRunner) -> None:
    """A handoff of a deferred run: resumed under the agent that took over,
    which the trace and the queued record show (§5.17)."""
    clock = Clock()
    a = {"principal": "agent-a", "kind": "agent"}
    b = {"principal": "agent-b", "kind": "agent"}
    run = mandate_runner.start(
        "nightly_sync",
        {"setting": "x"},
        attendance="unattended",
        now_ms=clock.now,
        actor_identity=a,
    )
    mandate_runner.drive(run, NoMandates(clock))
    resumed = mandate_runner.resume(run.snapshot(), actor_identity=b)
    result = mandate_runner.drive(resumed, Approves(clock))
    [record] = result.action_records
    assert record["actor_identity"] == b
    [event] = [t for t in result.trace if t["kind"] == "run_resumed"]
    assert event["step"] is None
    assert event["detail"] == {
        "attendance": "attended",
        "actor": "agent-b",
        "previous_actor": "agent-a",
    }


def _played(validator: _core.Validator, name: str) -> tuple[Any, list[dict[str, Any]]]:
    f = load(RUNTIME / f"{name}.json")
    seen: list[dict[str, Any]] = []
    run = play(start(validator, f), f, lambda i, e, a: seen.append(a))
    return run, seen


SUPERSEDED = {
    "resume_skipped_supersedes": [
        "superseded: the step did not reach its approval when its run resumed"
    ],
    "resume_gate_end_supersedes": [
        "superseded: a gate ended the resumed run before the step"
    ],
    "resume_loop_supersedes": ["superseded: a recovery loop ran the step again"],
    "deferral_superseded_by_loop": ["superseded: a recovery loop ran the step again"],
    "resume_nested_failure_supersedes": [
        "superseded: the nested run it was queued in failed"
    ],
    "resume_escalation_supersedes_handler": [
        "superseded: another escalation took precedence"
    ],
    "resume_new_actor_supersedes": [
        "superseded: the step did not reach its approval when its run resumed"
    ],
    # A loop over a deferred handler does not run it: nothing is superseded.
    "resume_loop_keeps_handler_run": [],
    # A loop back to a step whose queued action was carried out keeps it.
    "resume_carried_out_then_loop": [],
}


@pytest.mark.parametrize("name", sorted(SUPERSEDED))
def test_superseded_records_say_why(validator: _core.Validator, name: str) -> None:
    """Each rule of §5.14 and §5.14.1 that supersedes a queued action says
    which, in the record's reason."""
    run, _ = _played(validator, name)
    rejected = [r for r in run.next()["action_records"] if r["status"] == "rejected"]
    assert [r["reason"] for r in rejected] == SUPERSEDED[name]


def _requests(seen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in seen if a["kind"] == "RequestApproval"]


@pytest.mark.parametrize(
    "name",
    [
        "resume_loop_keeps_queue",
        "resume_recheck_reask",
    ],
)
def test_a_queued_step_names_its_action_until_it_goes_on(
    validator: _core.Validator, name: str
) -> None:
    """A re-entered queued step keeps its queued action through a recovery
    loop before it calls its capability and a re-ask after a recheck: every
    request names it and, in an attended resumption, is put to a person,
    with no mandate_ref; its decisions land on the queued record, the only
    record of the step (§5.14.1)."""
    run, seen = _played(validator, name)
    first, *again = [a for a in _requests(seen) if "queued_action_id" in a]
    assert again, name
    ids = {a["queued_action_id"] for a in [first, *again]}
    assert len(ids) == 1, ids
    for request in [first, *again]:
        assert request["approver"]["kind"] == "human", request
        assert "mandate_ref" not in request["approver"], request
    records = run.next()["action_records"]
    [record] = [r for r in records if r["action_id"] in ids]
    assert record["status"] == "executed"
    assert "reason" not in record and "reason_code" not in record, record


def test_requests_outside_the_queue_name_no_queued_action(
    validator: _core.Validator,
) -> None:
    """A step whose queued action was carried out, run again by a recovery
    loop, is asked afresh as a new action: its request names no queued
    action, and the queued step after the loop still names its own
    (§5.14.1). So is a handler that runs for a new escalation."""
    _, seen = _played(validator, "resume_loop_goes_on")
    queued = [(a["step"], a.get("queued_action_id")) for a in _requests(seen)]
    assert queued == [(2, "run-1/w/2/0"), (2, None), (4, "run-1/w/4/1")]
    _, seen = _played(validator, "resume_escalation_supersedes_handler")
    queued = [(a["frame"], a.get("queued_action_id")) for a in _requests(seen)]
    assert queued == [(["w"], "run-1/w/2/0"), (["w", "repair"], None)]
    # A loop back to the step itself, after its queued action was carried
    # out, asks for a new action too (a `when` failure mode).
    _, seen = _played(validator, "resume_carried_out_then_loop")
    queued = [(a["step"], a.get("queued_action_id")) for a in _requests(seen)]
    assert queued == [(2, "run-1/w/2/0"), (2, None)]


@pytest.mark.parametrize(
    ("name", "queued"),
    [
        ("resume_failed_call_then_loop", "run-1/w/2/0"),
        ("resume_failed_call_then_loop_actions", "run-1/w/2/2"),
    ],
)
def test_a_queued_step_whose_call_failed_carried_its_action_out(
    validator: _core.Validator, name: str, queued: str
) -> None:
    """A re-entered queued step that called its capability carried its
    queued action out, though the call failed: the queued record keeps that
    pass, failed, with its decision and idempotency key, and the recovery
    loop's pass is a new action, asked without the queued action, with a
    record, decision and key of its own (§5.14.1 items 6, 7; §6.4)."""
    run, seen = _played(validator, name)
    calls = [
        a["idempotency_key"]
        for a in seen
        if a["kind"] == "InvokeCapability" and a["capability"] == "mutate"
    ]
    assert len(set(calls)) == 2, calls
    first, again = _requests(seen)
    assert first["queued_action_id"] == queued
    assert "queued_action_id" not in again
    mutates = [r for r in run.next()["action_records"] if r["capability"] == "mutate"]
    assert mutates[0]["action_id"] == queued
    assert [r["status"] for r in mutates] == ["failed", "executed"]
    assert [r["idempotency_key"] for r in mutates] == calls
    assert [r["approval"]["decision_id"] for r in mutates] == ["d1", "d2"]


def test_a_loop_during_a_resumption_does_not_run_the_deferred_handler(
    validator: _core.Validator,
) -> None:
    """A loop whose range holds the deferred handler leaves the handler, its
    kept nested run and that run's queued action as they were: the nested
    run continues, so its first step does not run twice and its request
    names the queued action (§5.14.1 items 3, 6 and 7)."""
    run, seen = _played(validator, "resume_loop_keeps_handler_run")
    calls = [
        (a["frame"], a["capability"]) for a in seen if a["kind"] == "InvokeCapability"
    ]
    assert calls.count((["w", "oncall"], "persist")) == 1, calls
    nested = [a for a in _requests(seen) if a["frame"] == ["w", "oncall"]]
    assert [a.get("queued_action_id") for a in nested] == ["run-1/w/oncall/3/1"]
    end = run.next()
    assert (end["kind"], end["outcome"]) == ("Completed", "escalated"), end
    records = {r["action_id"]: r["status"] for r in end["action_records"]}
    assert records == {
        "run-1/w/3/0": "failed",
        "run-1/w/oncall/3/1": "executed",
        "run-1/w/3/2": "executed",
    }


def test_a_resumed_run_stamps_what_it_supersedes(
    validator: _core.Validator,
) -> None:
    """A queued record the resumed run supersedes takes the time and the
    actor of then, as a decided one does; a run that was never resumed
    leaves a superseded record's as they were (§5.14.1, §5.17)."""
    run, _ = _played(validator, "resume_new_actor_supersedes")
    records = {r["action_id"]: r for r in run.next()["action_records"]}
    superseded = records["run-1/w/3/1"]
    assert superseded["status"] == "rejected"
    assert superseded["actor_identity"]["principal"] == "agent-b"
    assert superseded["timestamp"] == "1970-01-01T01:01:00.000Z"
    # Carrying the action out changes the decided record's status only.
    assert records["run-1/w/2/0"]["timestamp"] == "1970-01-01T01:00:00.000Z"
    # Never resumed (1.1): a loop that supersedes a deferral a minute later
    # leaves the record's time.
    f = load(RUNTIME / "deferral_superseded_by_loop.json")
    f["script"][3]["at"] = 60000
    run = play(start(validator, f), f)
    [first] = [r for r in run.next()["action_records"] if r["status"] == "rejected"]
    assert first["timestamp"] == "1970-01-01T00:00:00.000Z"


def test_a_loop_during_a_resumption_does_not_repeat_what_ran_ahead(
    validator: _core.Validator,
) -> None:
    """A recovery loop during a resumption runs the step again and goes on
    with the resumption: a step that ran in the first run and declares
    after_deferral: run is not run again, so it delegates once (§5.14.1)."""
    run, seen = _played(validator, "resume_failed_call_then_loop")
    calls = [a["capability"] for a in seen if a["kind"] == "InvokeCapability"]
    assert calls.count("delegate") == 1
    assert calls.count("mutate") == 2
    # Nothing else is asked for once the script is played.
    end = run.next()
    assert (end["kind"], end["outcome"]) == ("Completed", "completed"), end


def test_refused_approvers_are_named(validator: _core.Validator) -> None:
    run, _ = _played(validator, "approver_identity_role")
    [record] = run.next()["action_records"]
    assert record["approval"]["approvers"] == ["alice"]
    assert "bob" in record["reason"]
    assert "role 'ops' is not 'release-manager'" in record["reason"]


def test_identities_are_not_kept_without_the_extension(
    validator: _core.Validator,
) -> None:
    run, _ = _played(validator, "approver_identities_without_identity_ext")
    [record] = run.next()["action_records"]
    assert "approver_identities" not in record["approval"]


def test_contradictory_approver_identities_are_malformed(
    validator: _core.Validator,
) -> None:
    """Two different identities for one principal make a decision malformed:
    it is refused and changes nothing (§5.17)."""
    f = load(RUNTIME / "approver_identity_role_met.json")
    run = start(validator, f)
    for entry in f["script"]:
        if entry["expect"]["kind"] == "RequestApproval":
            break
        action = run.next()
        run.submit(action["id"], fill(entry["respond"], action), 0)
    action = run.next()
    saved = run.snapshot()
    alice = {"principal": "alice", "kind": "human", "role": "release-manager"}
    decision = {
        "kind": "Decision",
        "decision_id": "d1",
        "decision": "approved",
        "approvers": [],
        "digest": action["digest"],
        "approver_identities": [alice, {**alice, "role": "ops"}],
    }
    with pytest.raises(ValueError, match="two different identities for 'alice'"):
        run.submit(action["id"], decision, 0)
    assert run.snapshot() == saved


# ---------------------------------------------------------------------------
# The host protocol's run operations (STANDARD v1.2 §5.19): turns, wake-up
# times, saving, withdrawal, cancellation, run records, triggers, run_ids.
# ---------------------------------------------------------------------------

TRIGGERED = """\
# Standard version: 1.1.0
nightly:
  goal: Read the configuration on a schedule or an event.
  risk: low
  workflow_extensions:
    requires: [triggers@1]
  inputs:
    ev: {type: object, ref: schemas/event_schema.yaml#/event}
  triggers:
  - kind: schedule
    schedule: {cron: "0 2 * * *", timezone: UTC}
  - kind: event
    event: {event_type: deploy.finished, delivers_to: ev}
  - kind: manual
  - kind: invoke
  steps:
  - capability: retrieve
    purpose: Read the configuration.
    store_as: current
    input_bindings:
      target: config
"""


def _event(event_id: str, event_type: str = "deploy.finished") -> dict[str, Any]:
    return {
        "event_id": event_id,
        "timestamp": "2026-11-15T12:00:00Z",
        "source": {"kind": "agent", "name": "ci"},
        "event_type": event_type,
        "raw": {},
        "canonical": {},
        "anchors": [],
        "provenance": {"transformer": "ci", "transform_version": "1"},
    }


@pytest.fixture()
def triggered(tmp_path: Path) -> WorkflowRunner:
    catalog = tmp_path / "triggered.yaml"
    catalog.write_text(TRIGGERED)
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    return WorkflowRunner(engine)


def _wait_catalog(tmp_path: Path, timeout: str = "10s") -> WorkflowEngine:
    catalog = tmp_path / "wait.yaml"
    catalog.write_text(
        f"""\
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
    timeout: {timeout}
    wait:
      event_type: job.done
"""
    )
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    return engine


class Withdrawing(FakeHost):
    """Records what it was asked to withdraw; never answers a wait."""

    def __init__(self, clock: Clock) -> None:
        super().__init__(clock)
        self.withdrawn: list[tuple[str, str]] = []

    def await_event(self, action: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def withdraw(self, action: dict[str, Any], why: str) -> None:
        self.withdrawn.append((action["kind"], why))


def test_advance_returns_wake_at(tmp_path: Path) -> None:
    runner = WorkflowRunner(_wait_catalog(tmp_path))
    clock = Clock()
    host = Withdrawing(clock)
    run = runner.start("wait_for_job", None, now_ms=clock.now)
    turn = runner.advance(run, host)
    assert turn.result is None
    assert turn.pending is not None and turn.pending["kind"] == "AwaitEvent"
    assert turn.wake_at == clock.now + 10_000 + 1
    # At the wake-up time, the next turn times the wait out and ends the run.
    clock.now = turn.wake_at
    turn = runner.advance(run, host)
    assert turn.result is not None and turn.result.code == "R401"
    assert host.withdrawn == [("AwaitEvent", "timed out")]


def test_drive_uses_wake_at(tmp_path: Path) -> None:
    runner = WorkflowRunner(_wait_catalog(tmp_path, "1h"), poll_interval_ms=600_000)
    clock = Clock()
    host = Withdrawing(clock)
    result = runner.run("wait_for_job", None, host)
    assert result.code == "R401"
    # Polls every ten minutes, then exactly at the wake-up time.
    assert host.slept[-1] == 1_000 + 3_600_000 + 1
    assert host.slept[0] == 1_000 + 600_000


def test_drive_saves_after_every_change(runner: WorkflowRunner) -> None:
    saved: list[dict[str, Any]] = []
    host = FakeHost(Clock())
    run = runner.start("change_config", {"setting": "x"}, now_ms=host.now_ms())
    result = runner.drive(run, host, save=saved.append, key=b"k")
    assert result.ok
    # Five answered actions: four capabilities and one approval.
    assert len(saved) == 5
    assert all(s["hmac"] for s in saved)
    # run() saves after the start too.
    saved.clear()
    runner.run("change_config", {"setting": "x"}, FakeHost(Clock()), save=saved.append)
    assert len(saved) == 6


def test_withdraw_on_timeout(tmp_path: Path) -> None:
    runner = WorkflowRunner(_wait_catalog(tmp_path))
    host = Withdrawing(Clock())
    result = runner.run("wait_for_job", None, host)
    assert result.code == "R401"
    assert host.withdrawn == [("AwaitEvent", "timed out")]


def test_withdraw_on_cancel(tmp_path: Path) -> None:
    runner = WorkflowRunner(_wait_catalog(tmp_path, "1h"))
    clock = Clock()
    host = Withdrawing(clock)
    run = runner.start("wait_for_job", None, now_ms=clock.now)
    assert runner.advance(run, host).pending is not None
    result = runner.cancel(run, "operator stop", host=host)
    assert host.withdrawn == [("AwaitEvent", "cancelled")]
    assert result.cancelled


def test_cancel_result(runner: WorkflowRunner) -> None:
    clock = Clock()
    host = FakeHost(clock)
    run = runner.start("change_config", {"setting": "x"}, now_ms=clock.now)
    for _ in range(2):  # retrieve, then the checkpoint step
        action = run.next()
        run.submit(action["id"], host.invoke_capability(action), clock.now)
    result = runner.cancel(run, "operator stop", now_ms=clock.now)
    assert result.code == "R408" and result.cancelled and not result.ok
    assert result.message == "operator stop"
    assert result.checkpoint_id == "cp-1"
    assert result.run_record is not None
    assert result.run_record["status"] == "cancelled"
    assert result.run_record["action_id"] == result.run_id
    with pytest.raises(ValueError, match="R408"):
        runner.cancel(run, "again")


def test_host_cannot_serve_reason(runner: WorkflowRunner) -> None:
    from grounded_agency.workflows import HostCannotServe

    class NoAudio(FakeHost):
        def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
            raise HostCannotServe("unsupported_domain", "no audio here")

    result = runner.run("change_config", {"setting": "x"}, NoAudio(Clock()))
    assert result.code == "R402"
    assert result.reason == "unsupported_domain"
    assert result.run_record is not None
    assert result.run_record["reason_code"] == "unsupported_domain"


@pytest.mark.parametrize(
    "answer",
    [
        "cannot_serve_free_text",
        "reason_text",
        "reason_object",
        "malformed_output",
        "malformed_output_url",
    ],
)
def test_no_secret_in_a_failed_step(runner: WorkflowRunner, answer: str) -> None:
    """§6.7: neither the ``reason`` of a host's ``Error`` (a token or not:
    the core traces any other value as ``reason_ignored``) nor the ``Error``
    the runner builds for a response the run refused (the core's account
    repeats the value) reaches the trace, the result, the run record or the
    snapshot with a secret in it."""
    from grounded_agency.workflows import HostCannotServe

    secret = "Hunter2SuperSecret99"
    dsn = f"postgres://app:{secret}@db.internal/prod"

    class Leaky(FakeHost):
        def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
            if action["capability"] != "retrieve":
                return super().invoke_capability(action)
            value = {"data": {"v": 1}, "confidence": 1.0, "evidence_anchors": []}
            if answer == "cannot_serve_free_text":
                raise HostCannotServe(f"backend {dsn} unreachable")
            if answer == "reason_text":
                return {
                    "kind": "Error",
                    "code": "R402",
                    "message": "db down",
                    "reason": f"connect {dsn}",
                }
            if answer == "reason_object":
                return {
                    "kind": "Error",
                    "code": "R402",
                    "message": "db down",
                    "reason": {"password": secret},
                }
            if answer == "malformed_output":
                return {
                    "kind": "Output",
                    "value": value,
                    "evidence_seen": f"Authorization: Bearer {secret}",
                }
            return {
                "kind": "Output",
                "value": value,
                "evidence_seen": f"https://app:{secret}@files.internal/x",
            }

    run = runner.start("change_config", {"setting": "x"}, run_id="r1", now_ms=1_000)
    result = runner.drive(run, Leaky(Clock()))
    assert result.code == "R402"
    (failed,) = [e for e in result.trace if e["kind"] == "step_failed"]
    assert "[REDACTED]" in json.dumps(failed)
    for kept in (
        result.trace,
        result.message,
        result.reason,
        result.action_records,
        result.run_record,
        run.run_record(),
        run.snapshot(b"k"),
    ):
        assert secret not in json.dumps(kept, default=str)


def test_start_from_schedule_trigger_is_unattended(triggered: WorkflowRunner) -> None:
    run = triggered.start("nightly", trigger=0, now_ms=0)
    assert json.loads(run.snapshot()["state"])["attendance"] == "unattended"
    manual = triggered.start("nightly", trigger=2, now_ms=0)
    assert json.loads(manual.snapshot()["state"])["attendance"] == "attended"


def test_start_from_trigger_refuses_conflicting_attendance(
    triggered: WorkflowRunner,
) -> None:
    with pytest.raises(RunStartError, match="trigger's attendance is unattended"):
        triggered.start("nightly", trigger=0, attendance="attended", now_ms=0)
    with pytest.raises(RunStartError, match="no trigger 9"):
        triggered.start("nightly", trigger=9, now_ms=0)


def test_start_from_event_trigger_delivers_event(triggered: WorkflowRunner) -> None:
    run = triggered.start("nightly", trigger=1, event=_event("e1"), now_ms=0)
    state = json.loads(run.snapshot()["state"])
    assert state["frames"][0]["inputs"]["ev"]["event_id"] == "e1"
    assert state["attendance"] == "unattended"


def test_start_from_event_trigger_refuses_mismatched_event(
    triggered: WorkflowRunner,
) -> None:
    with pytest.raises(RunStartError, match="does not match"):
        triggered.start("nightly", trigger=1, event=_event("e1", "x"), now_ms=0)
    with pytest.raises(RunStartError, match="pass it"):
        triggered.start("nightly", trigger=1, now_ms=0)
    with pytest.raises(RunStartError, match="only an event trigger"):
        triggered.start("nightly", trigger=0, event=_event("e1"), now_ms=0)
    with pytest.raises(RunStartError, match="through an event trigger"):
        triggered.start("nightly", event=_event("e1"), now_ms=0)


def test_start_from_event_trigger_redelivery_refused(triggered: WorkflowRunner) -> None:
    triggered.start("nightly", trigger=1, event=_event("e1"), now_ms=0)
    with pytest.raises(RunStartError, match="already started a run"):
        triggered.start("nightly", trigger=1, event=_event("e1"), now_ms=0)
    triggered.start("nightly", trigger=1, event=_event("e2"), now_ms=0)


def test_event_not_consumed_when_start_fails(triggered: WorkflowRunner) -> None:
    with pytest.raises(RunStartError, match="delivers_to"):
        triggered.start(
            "nightly", {"ev": {"x": 1}}, trigger=1, event=_event("e1"), now_ms=0
        )
    triggered.start("nightly", trigger=1, event=_event("e1"), now_ms=0)


def test_start_from_invoke_trigger_refused(triggered: WorkflowRunner) -> None:
    with pytest.raises(RunStartError, match="nested runs only"):
        triggered.start("nightly", trigger=3, now_ms=0)


def test_restore_reissues_same_id_and_run_id(runner: WorkflowRunner) -> None:
    """A restored run's pending action is the one pending when the state was
    saved, with the same run_id and id: the delivery key (§5.19.4)."""
    run = runner.start("change_config", {"setting": "x"}, run_id="r-once", now_ms=0)
    before = run.next()
    again = runner.restore(run.snapshot(b"k"), b"k").next()
    assert (
        (again["run_id"], again["id"])
        == (before["run_id"], before["id"])
        == (
            "r-once",
            1,
        )
    )
    assert again == before


def test_run_id_reuse_refused(runner: WorkflowRunner) -> None:
    run = runner.start("change_config", {"setting": "x"}, run_id="r-1", now_ms=0)
    with pytest.raises(RunStartError, match="already used"):
        runner.start("change_config", {"setting": "x"}, run_id="r-1", now_ms=0)
    a = runner.start("change_config", {"setting": "x"}, now_ms=0)
    b = runner.start("change_config", {"setting": "x"}, now_ms=0)
    assert a.run_id != b.run_id
    # A restored run keeps its id: not a reuse.
    assert runner.restore(run.snapshot()).run_id == "r-1"


def test_run_result_has_run_record(runner: WorkflowRunner) -> None:
    ok = runner.run("change_config", {"setting": "x"}, FakeHost(Clock()), run_id="ok")
    assert ok.run_record is not None
    assert ok.run_record["status"] == "executed"
    assert ok.run_record["details"]["records"] == 1
    failed = runner.run(
        "change_config",
        {"setting": "x"},
        FakeHost(Clock(), fail={"retrieve"}),
        run_id="failed",
    )
    assert failed.action_records == []
    assert failed.run_record is not None
    assert failed.run_record["status"] == "failed"
    assert failed.run_record["details"]["records"] == 0


def test_archive_called_once_per_end(runner: WorkflowRunner, tmp_path: Path) -> None:
    archived: list[Any] = []
    keeping = WorkflowRunner(runner._engine, archive=archived.append)
    result = keeping.run("change_config", {"setting": "x"}, FakeHost(Clock()))
    assert archived == [result]
    assert result.run_record is not None
    assert result.run_record["action_id"] == result.run_id
    run = keeping.start("change_config", {"setting": "x"}, now_ms=0)
    keeping.cancel(run, "stop")
    assert len(archived) == 2 and archived[1].cancelled
    clock = Clock()
    host = FakeHost(clock)
    run = keeping.start("change_config", {"setting": "x"}, now_ms=clock.now)
    turn = keeping.advance(run, host)
    assert turn.result is not None and archived[-1] is turn.result
    assert len(archived) == 3


def test_archive_failure_keeps_run(runner: WorkflowRunner) -> None:
    from grounded_agency.workflows import RunArchiveError

    def broken(result: Any) -> None:
        raise OSError("archive offline")

    keeping = WorkflowRunner(runner._engine, archive=broken)
    with pytest.raises(RunArchiveError) as caught:
        keeping.run("change_config", {"setting": "x"}, FakeHost(Clock()))
    error = caught.value
    assert error.result.ok
    assert error.run.finished
    # The state was not discarded: it snapshots, and can be archived again.
    assert error.run.snapshot()["sha256"]
    archived: list[Any] = []
    again = WorkflowRunner(runner._engine, archive=archived.append)
    assert again.drive(again.restore(error.run.snapshot()), FakeHost(Clock())).ok
    assert len(archived) == 1


def test_records_actions_through_the_runner(runner: WorkflowRunner) -> None:
    result = runner.run(
        "change_config", {"setting": "x"}, FakeHost(Clock()), records="actions"
    )
    assert [r["capability"] for r in result.action_records] == [
        "retrieve",
        "checkpoint",
        "constrain",
        "mutate",
    ]
    with pytest.raises(RunStartError, match="records must be"):
        runner.start("change_config", {"setting": "x"}, records="everything")


def test_take_trace_and_records_with_chain_heads(runner: WorkflowRunner) -> None:
    """A host may take the trace and the settled records out of the state
    (§5.19.4); the state's chain heads cover what it took."""
    import hashlib

    clock = Clock()
    host = FakeHost(clock)
    run = runner.start(
        "change_config", {"setting": "x"}, now_ms=clock.now, records="actions"
    )
    taken_records: list[dict[str, Any]] = []
    taken_trace: list[dict[str, Any]] = []
    while not run.finished:
        taken_trace += run.take_trace()
        taken_records += run.take_records()
        action = run.next()
        if action["kind"] == "RequestApproval":
            run.submit(action["id"], host.request_approval(action), clock.now)
        else:
            run.submit(action["id"], host.invoke_capability(action), clock.now)

    def fold(items: list[dict[str, Any]]) -> str:
        h = ""
        for item in items:
            h = hashlib.sha256((h + _core.canonical_json(item)).encode()).hexdigest()
        return h

    assert run.taken_sha256 == {
        "records": fold(taken_records),
        "trace": fold(taken_trace),
    }
    assert run.run_record()["details"]["records"] == len(taken_records) + len(
        run.action_records()
    )


def _engine(tmp_path: Path, text: str) -> WorkflowEngine:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(text)
    engine = WorkflowEngine(ONTOLOGY, schema_root=ROOT)
    engine.load_catalog(catalog)
    return engine


def test_resume_saves_before_acting(mandate_runner: WorkflowRunner) -> None:
    """With save=, resume saves the resumed state before it returns, so the
    host acts on no action of the resumption unsaved (§5.19.4)."""
    saved, _ = deferred_nightly(mandate_runner)
    events: list[tuple[str, int]] = []

    class Logging(Approves):
        def request_approval(self, action: dict[str, Any]) -> dict[str, Any]:
            events.append(("act", action["id"]))
            return super().request_approval(action)

    def save(state: dict[str, Any]) -> None:
        pending = mandate_runner.restore(state, b"secret").next()
        events.append(("save", pending["id"]))

    run = mandate_runner.resume(saved, b"secret", save=save)
    assert events == [("save", run.next()["id"])]
    assert mandate_runner.drive(run, Logging(Clock()), save=save, key=b"secret").ok
    first_act = next(i for i, e in enumerate(events) if e[0] == "act")
    assert events[first_act - 1] == ("save", events[first_act][1])


def test_cancel_saves_before_withdrawing(tmp_path: Path) -> None:
    runner = WorkflowRunner(_wait_catalog(tmp_path, "1h"))
    order: list[str] = []

    class Logging(Withdrawing):
        def withdraw(self, action: dict[str, Any], why: str) -> None:
            order.append("withdraw")
            super().withdraw(action, why)

    clock = Clock()
    host = Logging(clock)
    run = runner.start("wait_for_job", None, now_ms=clock.now)
    assert runner.advance(run, host).pending is not None
    saved: list[dict[str, Any]] = []

    def save(state: dict[str, Any]) -> None:
        order.append("save")
        saved.append(state)

    result = runner.cancel(run, "operator stop", host=host, save=save, key=b"k")
    assert result.cancelled
    assert order == ["save", "withdraw"]
    end = runner.restore(saved[0], b"k").next()
    assert (end["kind"], end["code"]) == ("Failed", "R408")


def test_run_ids_come_from_the_hosts_store(tmp_path: Path) -> None:
    """A run_id must be unique among the runs whose records and keys the
    host keeps (§5.19.2): the runner checks, and adds to, the host's store,
    so a restarted runner over the same store refuses one used before."""
    used = {"r-old"}
    engine = _engine(tmp_path, CATALOG)
    runner = WorkflowRunner(engine, run_ids=used)
    with pytest.raises(RunStartError, match="already used"):
        runner.start("change_config", {"setting": "x"}, run_id="r-old", now_ms=0)
    run = runner.start("change_config", {"setting": "x"}, now_ms=0)
    assert used == {"r-old", run.run_id}
    restarted = WorkflowRunner(engine, run_ids=used)
    with pytest.raises(RunStartError, match="already used"):
        restarted.start("change_config", {"setting": "x"}, run_id=run.run_id, now_ms=0)


def test_event_dedup_survives_a_restart(tmp_path: Path) -> None:
    """With event_seen, the event_ids that started runs are in the host's
    stores: an event delivered again after a restart starts no run
    (§5.10.2)."""
    stores: dict[tuple[str, int], set[str]] = {}

    def event_seen(workflow: str, index: int) -> set[str]:
        return stores.setdefault((workflow, index), set())

    engine = _engine(tmp_path, TRIGGERED)
    WorkflowRunner(engine, event_seen=event_seen).start(
        "nightly", trigger=1, event=_event("e1"), now_ms=0
    )
    assert stores == {("nightly", 1): {"e1"}}
    restarted = WorkflowRunner(engine, event_seen=event_seen)
    with pytest.raises(RunStartError, match="already started a run"):
        restarted.start("nightly", trigger=1, event=_event("e1"), now_ms=0)
    restarted.start("nightly", trigger=1, event=_event("e2"), now_ms=0)
    assert stores == {("nightly", 1): {"e1", "e2"}}


def test_event_driven_recipe_keeps_each_record_once(tmp_path: Path) -> None:
    """The event-driven host of RUNNING_WORKFLOWS.md takes records while the
    run goes on and archives the result when it ends: the result's records
    are those not taken before, so each record is kept once. Taking an ended
    run's records as well would keep them twice."""

    class Later(FakeHost):
        """Has no decision on its first turn."""

        def __init__(self, clock: Clock) -> None:
            super().__init__(clock)
            self.waited = False

        def request_approval(self, action: dict[str, Any]) -> dict[str, Any] | None:  # type: ignore[override]
            if not self.waited:
                self.waited = True
                return None
            return super().request_approval(action)

    archived: list[RunResult] = []
    runner = WorkflowRunner(_engine(tmp_path, CATALOG), archive=archived.append)
    clock = Clock()
    host = Later(clock)
    run = runner.start(
        "change_config", {"setting": "x"}, now_ms=clock.now, records="actions"
    )
    audit_store: list[dict[str, Any]] = []
    while True:
        turn = runner.advance(run, host)
        if turn.result is None:
            audit_store.extend(run.take_records())
            continue
        break
    assert len(audit_store) == 3  # retrieve, checkpoint, constrain
    [result] = archived
    kept = audit_store + result.action_records
    ids = [r["action_id"] for r in kept]
    assert len(ids) == len(set(ids)) == result.run_record["details"]["records"] == 4
    assert run.take_records() == result.action_records
