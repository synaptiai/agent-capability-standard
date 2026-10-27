"""
Running workflows with the reference executor (design-114 §16).

The executor in the Rust core is a deterministic state machine with no I/O:
it says what to do next (an *action*), the host does it and reports back (a
*response*), and time enters only through the timestamps the host passes.
:class:`WorkflowRunner` drives it, dispatching each action to a
:class:`Host` you subclass with your capability implementations, approval
channel and event source.

Example::

    engine = WorkflowEngine("schemas/capability_ontology.yaml")
    engine.load_catalog("schemas/workflow_catalog.yaml")

    class MyHost(Host):
        def invoke_capability(self, action):
            value = my_tools[action["capability"]](**action["inputs"])
            return {"kind": "Output", "value": value}

    result = WorkflowRunner(engine).run("debug_code_change", {...}, MyHost())
    if result.ok:
        print(result.outputs)
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .. import _core
from ..state.checkpoint_tracker import CheckpointTracker
from .engine import WorkflowEngine

Action = dict[str, Any]
Response = dict[str, Any]

TERMINAL = frozenset({"Completed", "Failed"})


class Host:
    """What a run asks of its environment.

    Override the methods your workflows need; each receives the action (a
    dict with ``kind``, ``id``, ``frame`` and the action's fields) and
    returns a response dict, or ``None`` when there is nothing yet (the
    runner waits a poll interval and asks again, until the action's deadline
    passes). An exception raised by :meth:`invoke_capability` is reported to
    the run as a failed step (R402) — except ``NotImplementedError``, which
    means the host lacks the capability and stops the runner. The clock
    methods default to wall-clock time.

    With a :class:`CheckpointTracker`, :meth:`create_checkpoint` records
    checkpoints in it.
    """

    def __init__(self, checkpoint_tracker: CheckpointTracker | None = None) -> None:
        self.checkpoint_tracker = checkpoint_tracker

    def now_ms(self) -> int:
        """The current time in milliseconds since the Unix epoch."""
        return time.time_ns() // 1_000_000

    def sleep_until(self, until_ms: int) -> None:
        """Block until ``until_ms`` (a retry backoff)."""
        delay = until_ms - self.now_ms()
        if delay > 0:
            time.sleep(delay / 1000)

    def invoke_capability(self, action: Action) -> Response:
        """Run ``action["capability"]`` with ``action["inputs"]``; return
        ``{"kind": "Output", "value": {...}}`` or ``{"kind": "Error", "code":
        "R401" | "R402", "message": ...}``."""
        raise NotImplementedError(f"no implementation for {action['capability']}")

    def create_checkpoint(self, action: Action) -> Response:
        """Take a checkpoint before ``action["step"]``; return ``{"kind":
        "Checkpoint", "checkpoint_id": ...}``."""
        if self.checkpoint_tracker is None:
            raise NotImplementedError("no checkpoint store")
        checkpoint_id = self.checkpoint_tracker.create_checkpoint(
            scope=["*"],
            reason=f"before step {action['step']} of {'/'.join(action['frame'])}",
        )
        return {"kind": "Checkpoint", "checkpoint_id": checkpoint_id}

    def rollback(self, action: Action) -> Response:
        """Restore ``action["checkpoint_id"]``; return ``{"kind":
        "RolledBack"}``, or an ``Error`` (the run fails with F503)."""
        raise NotImplementedError("no rollback")

    def request_approval(self, action: Action) -> Response:
        """Ask ``action["approver"]`` to approve ``action["shown"]``; return
        ``{"kind": "Decision", "decision_id", "decision": "approved" |
        "rejected", "approvers": [...], "digest": action["digest"]}``."""
        raise NotImplementedError("no approval channel")

    def recheck_source(self, action: Action) -> Response:
        """Re-read ``action["source"]`` now; return ``{"kind": "Current",
        "value": ...}``."""
        raise NotImplementedError("no recheck")

    def await_event(self, action: Action) -> Response | None:
        """Wait for an event matching ``action`` until ``action["deadline"]``;
        return ``{"kind": "Event", "event": {...}, "principal": ...}``,
        ``{"kind": "LivenessLost"}`` when the source stopped answering (the
        step fails with R406), or ``None`` when nothing arrived (the run then
        times out, R401, once the deadline has passed)."""
        raise NotImplementedError("no event source")


@dataclass(frozen=True)
class RunResult:
    """How a run ended."""

    outcome: str | None
    """``completed``, ``escalated``, ``deferred`` or ``replan_required``;
    ``None`` when the run failed."""
    code: str | None
    """The failure code (``R40x``/``F50x``) when the run failed."""
    message: str
    outputs: dict[str, Any] = field(default_factory=dict)
    action_records: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    cause: str | None = None
    """The code that caused an escalation."""

    @property
    def ok(self) -> bool:
        return self.outcome == "completed"


class RunIncomplete(RuntimeError):
    """The run did not finish within the runner's action budget. ``run`` is
    the live run: snapshot it, or drive it again."""

    def __init__(self, message: str, run: _core.Run) -> None:
        super().__init__(message)
        self.run = run


class RunStartError(ValueError):
    """The run did not start: the catalog does not validate, or the inputs
    do not match the workflow's. ``diagnostics`` lists the errors."""

    def __init__(self, message: str, diagnostics: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class WorkflowRunner:
    """Runs workflows loaded into a :class:`WorkflowEngine` on the core's
    executor."""

    def __init__(
        self,
        engine: WorkflowEngine,
        *,
        max_actions: int = 100_000,
        poll_interval_ms: int = 1_000,
    ) -> None:
        """
        Args:
            engine: Holds the catalog to run.
            max_actions: Most actions to answer before giving up on a run
                (:class:`RunIncomplete`). Polls that got no answer do not
                count.
            poll_interval_ms: How long to wait before asking the host again
                when a handler returns ``None`` (nothing yet).
        """
        self._engine = engine
        self._max_actions = max_actions
        self._poll_ms = poll_interval_ms

    def catalog(self) -> dict[str, Any]:
        """The catalog the engine holds, as the executor sees it."""
        return self._engine.catalog_data()

    def start(
        self,
        workflow: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        attendance: str = "attended",
        run_id: str | None = None,
        now_ms: int | None = None,
    ) -> _core.Run:
        """Start a run without driving it (drive it with :meth:`drive`, or
        step it yourself)."""
        try:
            return _core.Run.start(
                self._engine.core_validator(),
                self.catalog(),
                workflow,
                dict(inputs or {}),
                attendance=attendance,
                run_id=run_id or uuid.uuid4().hex,
                now_ms=time.time_ns() // 1_000_000 if now_ms is None else now_ms,
            )
        except ValueError as e:
            diagnostics = e.args[1] if len(e.args) > 1 else []
            raise RunStartError(str(e.args[0]), diagnostics) from None

    def restore(
        self, snapshot: Mapping[str, Any], key: bytes | None = None
    ) -> _core.Run:
        """Resume a run from ``run.snapshot(key)``, against the same catalog."""
        return _core.Run.restore(
            self._engine.core_validator(), self.catalog(), dict(snapshot), key
        )

    def run(
        self,
        workflow: str,
        inputs: Mapping[str, Any] | None,
        host: Host,
        *,
        attendance: str = "attended",
        run_id: str | None = None,
    ) -> RunResult:
        """Start ``workflow`` and drive it to its end with ``host``."""
        run = self.start(
            workflow, inputs, attendance=attendance, run_id=run_id, now_ms=host.now_ms()
        )
        return self.drive(run, host)

    def drive(self, run: _core.Run, host: Host) -> RunResult:
        """Drive a started or restored run to its end.

        Raises:
            RunIncomplete: after ``max_actions`` answered actions; the run is
                attached, so it can be snapshotted or driven further.
        """
        answered = 0
        while answered < self._max_actions:
            action = run.next()
            kind = action["kind"]
            if kind in TERMINAL:
                return self._result(run, action)
            if kind == "Sleep":
                host.sleep_until(action["until"])
                run.tick(host.now_ms())
                answered += 1
                continue
            response = self._dispatch(host, action)
            if response is None:
                # Nothing yet: wait a poll interval (or until the action's
                # deadline, if sooner), then let the run time it out.
                now = host.now_ms()
                until = now + self._poll_ms
                deadline = action.get("deadline") or action.get("expires_at")
                if deadline is not None:
                    until = min(until, deadline + 1)
                host.sleep_until(until)
                run.tick(host.now_ms())
                continue
            run.submit(action["id"], response, host.now_ms())
            answered += 1
        raise RunIncomplete(
            f"the run did not finish within {self._max_actions} actions", run
        )

    @staticmethod
    def _dispatch(host: Host, action: Action) -> Response | None:
        kind = action["kind"]
        if kind == "InvokeCapability":
            try:
                return host.invoke_capability(action)
            except NotImplementedError:
                raise
            except Exception as e:  # the step failed, not the runner
                return {
                    "kind": "Error",
                    "code": "R402",
                    "message": f"{type(e).__name__}: {e}",
                }
        handlers = {
            "CreateCheckpoint": host.create_checkpoint,
            "Rollback": host.rollback,
            "RequestApproval": host.request_approval,
            "RecheckSource": host.recheck_source,
            "AwaitEvent": host.await_event,
        }
        if kind not in handlers:
            raise ValueError(f"unknown action kind {kind!r}")
        return handlers[kind](action)

    @staticmethod
    def _result(run: _core.Run, action: Action) -> RunResult:
        trace = run.trace()
        if action["kind"] == "Completed":
            return RunResult(
                outcome=action["outcome"],
                code=None,
                message="",
                outputs=action["outputs"],
                action_records=action["action_records"],
                trace=trace,
                cause=action.get("cause"),
            )
        return RunResult(
            outcome=None,
            code=action["code"],
            message=action["message"],
            action_records=action["action_records"],
            trace=trace,
        )
