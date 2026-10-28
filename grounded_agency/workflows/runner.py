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
    means the host lacks the capability and stops the runner — and so is a
    response from it the run cannot accept (malformed, not JSON data, or
    not an answer to the action). A response to any other action that the
    run cannot accept stops the runner with :class:`HostResponseError`.
    The clock methods default to wall-clock time.

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
        "rejected" | "unavailable", "approvers": [...], "digest":
        action["digest"]}``. ``unavailable`` means no one could decide (no
        standing mandate covers the action): an unattended run then follows
        the step's ``when_unattended``.

        By default a standing mandate is unavailable (this host holds no
        mandates), and any other approver raises ``NotImplementedError``."""
        if action["approver"].get("kind") == "standing_mandate":
            return {
                "kind": "Decision",
                "decision_id": f"no-mandate-{action['id']}",
                "decision": "unavailable",
                "approvers": [],
                "digest": action["digest"],
            }
        raise NotImplementedError("no approval channel")

    def recheck_source(self, action: Action) -> Response:
        """Re-read ``action["source"]`` now; return ``{"kind": "Current",
        "value": ...}``."""
        raise NotImplementedError("no recheck")

    def await_event(self, action: Action) -> Response | None:
        """Wait for an event matching ``action`` until ``action["deadline"]``;
        return ``{"kind": "Event", "event": {...}, "principal": ...}``, with
        the sender's ``identity`` (an ``agent_identity``) when the step uses
        ``identity@1`` inputs (STANDARD v1.1 §5.17),
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
    deferred: list[dict[str, Any]] = field(default_factory=list)
    """Steps deferred to a queue, or deferred because they depend on one
    (``frame``, ``step``, ``store_as``, ``reason``, ``action_id``), whatever
    the outcome."""
    ended: dict[str, Any] | None = None
    """When a gate with ``action: end`` ended the run early: the ``step``
    it ended at and the gate's ``message``."""

    @property
    def ok(self) -> bool:
        return self.outcome == "completed"


class RunIncomplete(RuntimeError):
    """The runner stopped before the run finished: it ran out of its action
    or poll budget (``max_actions``, ``max_polls``). ``run`` is the live
    run: snapshot it, or drive it again."""

    def __init__(self, message: str, run: _core.Run) -> None:
        super().__init__(message)
        self.run = run


class HostResponseError(RunIncomplete):
    """The host answered an action other than ``InvokeCapability`` with a
    response the run cannot accept (malformed, not JSON data, or not an
    answer to the action). The run is unchanged: ``run`` is still waiting
    for ``action``, so it can be snapshotted or driven again with a fixed
    host. ``response`` is what the host returned."""

    def __init__(
        self, message: str, run: _core.Run, action: Action, response: Any
    ) -> None:
        super().__init__(message, run)
        self.action = action
        self.response = response


class RunStartError(ValueError):
    """The run did not start or could not be restored: the catalog does not
    validate, the inputs do not match the workflow's or are not JSON data,
    or the snapshot is malformed or fails its HMAC check. ``diagnostics``
    lists the catalog's errors (empty for the other causes)."""

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
        max_polls: int = 100_000,
    ) -> None:
        """
        Args:
            engine: Holds the catalog to run.
            max_actions: Most actions to answer in one :meth:`drive` before
                giving up on a run (:class:`RunIncomplete`). Polls that got
                no answer do not count.
            poll_interval_ms: How long to wait before asking the host again
                when a handler returns ``None`` (nothing yet).
            max_polls: Most polls that got no answer for any one action
                before giving up on a run (:class:`RunIncomplete`). This
                bounds a host that never answers an action without a
                deadline (an approval with no expiry); about 28 hours at
                the default ``poll_interval_ms``. Each new action starts
                its count afresh. Raise it, or poll less often, for actions
                that wait longer, or drive the run again.
        """
        self._engine = engine
        self._max_actions = max_actions
        self._poll_ms = poll_interval_ms
        self._max_polls = max_polls

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
        actor_identity: Mapping[str, Any] | None = None,
    ) -> _core.Run:
        """Start a run without driving it (drive it with :meth:`drive`, or
        step it yourself). ``actor_identity`` (an ``agent_identity``, STANDARD
        v1.1 §5.17, e.g. :meth:`AgentDescriptor.identity`) names who runs the
        workflow; every action record carries it.

        Raises:
            RunStartError: the catalog does not validate, or ``inputs`` or
                ``actor_identity`` do not fit the workflow or are not JSON
                data.
        """
        now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
        _check_ms(now)
        try:
            return _core.Run.start(
                self._engine.core_validator(),
                self.catalog(),
                workflow,
                dict(inputs or {}),
                attendance=attendance,
                run_id=run_id or uuid.uuid4().hex,
                now_ms=now,
                actor_identity=None if actor_identity is None else dict(actor_identity),
            )
        except (TypeError, ValueError) as e:
            raise _start_error(e) from None

    def restore(
        self, snapshot: Mapping[str, Any], key: bytes | None = None
    ) -> _core.Run:
        """Resume a run from ``run.snapshot(key)``, against the same catalog.

        Raises:
            RunStartError: the snapshot is malformed, has an unsupported
                version, fails its digest or HMAC check, or was taken
                against another catalog, or the catalog does not validate.
            TypeError: ``key`` is not bytes.
        """
        if key is not None and not isinstance(key, (bytes, bytearray)):
            raise TypeError(f"key must be bytes, not {type(key).__name__}")
        try:
            return _core.Run.restore(
                self._engine.core_validator(), self.catalog(), dict(snapshot), key
            )
        except (TypeError, ValueError) as e:
            raise _start_error(e) from None

    def run(
        self,
        workflow: str,
        inputs: Mapping[str, Any] | None,
        host: Host,
        *,
        attendance: str = "attended",
        run_id: str | None = None,
        actor_identity: Mapping[str, Any] | None = None,
    ) -> RunResult:
        """Start ``workflow`` and drive it to its end with ``host``."""
        run = self.start(
            workflow,
            inputs,
            attendance=attendance,
            run_id=run_id,
            now_ms=host.now_ms(),
            actor_identity=actor_identity,
        )
        return self.drive(run, host)

    def drive(self, run: _core.Run, host: Host) -> RunResult:
        """Drive a started or restored run to its end.

        Raises:
            RunIncomplete: after ``max_actions`` answered actions, or
                ``max_polls`` unanswered polls of one action; the run is
                attached, so it can be snapshotted or driven further.
            HostResponseError: (a :class:`RunIncomplete`) the host answered
                an action other than ``InvokeCapability`` with a response
                the run cannot accept.
        """
        answered = 0
        # Unanswered polls of the current action; a new action resets it.
        polls = 0
        polled: Any = None
        while answered < self._max_actions:
            action = run.next()
            kind = action["kind"]
            if action.get("id") != polled:
                polled, polls = action.get("id"), 0
            if kind in TERMINAL:
                return self._result(run, action)
            if kind == "Sleep":
                host.sleep_until(action["until"])
                run.tick(host.now_ms())
                answered += 1
                continue
            response = self._dispatch(host, action)
            if response is None:
                if polls >= self._max_polls:
                    raise RunIncomplete(
                        f"no answer to action {action['id']} ({kind}) after "
                        f"{self._max_polls} polls",
                        run,
                    )
                polls += 1
                # Nothing yet: wait a poll interval (or until the action's
                # deadline, if sooner), then let the run time it out.
                now = host.now_ms()
                until = now + self._poll_ms
                deadline = action.get("deadline")
                if deadline is None:
                    deadline = action.get("expires_at")
                if deadline is not None:
                    until = min(until, deadline + 1)
                host.sleep_until(until)
                run.tick(host.now_ms())
                continue
            self._submit(run, action, response, host.now_ms())
            answered += 1
        raise RunIncomplete(
            f"the run did not finish within {self._max_actions} actions", run
        )

    @staticmethod
    def _submit(run: _core.Run, action: Action, response: Any, now: int) -> None:
        """Submit ``response`` at ``now``. One the run refuses (it changes
        nothing then) fails the step for a capability, as a host exception
        does, and stops the runner for anything else. ``now`` is read
        before, so a faulty clock is not mistaken for a refused response."""
        _check_ms(now)
        try:
            run.submit(action["id"], response, now)
            return
        except (TypeError, ValueError) as e:
            error = e
        if action["kind"] != "InvokeCapability":
            raise HostResponseError(
                f"the host's response to action {action['id']} "
                f"({action['kind']}) was refused: {error}",
                run,
                action,
                response,
            ) from error
        run.submit(
            action["id"],
            {
                "kind": "Error",
                "code": "R402",
                "message": f"the host's response was refused: {error}",
            },
            now,
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
                deferred=action.get("deferred", []),
                ended=action.get("ended"),
            )
        return RunResult(
            outcome=None,
            code=action["code"],
            message=action["message"],
            action_records=action["action_records"],
            trace=trace,
            deferred=action.get("deferred", []),
        )


def _start_error(e: TypeError | ValueError) -> RunStartError:
    """The core's start/restore error as a :class:`RunStartError`: a
    ValueError from a catalog that does not validate carries its
    diagnostics as a second argument."""
    if isinstance(e, ValueError) and len(e.args) > 1:
        return RunStartError(str(e.args[0]), list(e.args[1] or []))
    return RunStartError(str(e.args[0]) if e.args else str(e), [])


def _check_ms(now: Any) -> None:
    """A clock reading must be whole milliseconds; anything else is the
    host's bug, raised as such rather than blamed on the run's data."""
    if isinstance(now, bool) or not isinstance(now, int):
        raise TypeError(
            f"a clock reading must be an int of milliseconds, not {type(now).__name__}"
        )
    if not 0 <= now < 2**64:
        raise ValueError(f"a clock reading must be from 0 to 2^64 - 1 ms, not {now}")
