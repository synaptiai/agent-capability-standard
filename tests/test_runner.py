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
        actor_identity=f.get("actor_identity"),
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


def test_replacement_is_per_run(validator: _core.Validator) -> None:
    """A parent loop that runs an invoke again starts a new child run: its
    waiting delegate does not name the old run's delegation (§5.13). Fixture
    matching is by subset, so the absent key is checked here."""
    f = json.loads((RUNTIME / "delegate_wait_replaced_per_run.json").read_text())
    run = _core.Run.start(
        validator, f["catalog"], f["workflow"], f["inputs"], run_id="run-1", now_ms=0
    )
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
    f = json.loads((RUNTIME / name).read_text())
    run = _core.Run.start(
        validator, f["catalog"], f["workflow"], f["inputs"], run_id="run-1", now_ms=0
    )
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
