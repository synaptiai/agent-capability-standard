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
from collections.abc import Callable, Mapping, MutableSet
from dataclasses import dataclass, field
from typing import Any

from .. import _core
from ..state.checkpoint_tracker import CheckpointTracker
from .engine import WorkflowEngine
from .protocol import RECORD_MODES
from .triggers import EventGate, trigger_attendance

# An action or a response of the host protocol (STANDARD v1.2 §5.19.1;
# their typed shapes are in .protocol). At run time both are plain dicts.
Action = dict[str, Any]
Response = dict[str, Any]

TERMINAL = frozenset({"Completed", "Failed"})


class HostCannotServe(Exception):
    """Raised by :meth:`Host.invoke_capability` or :meth:`Host.await_event`
    when the host cannot serve the step: the runner answers the action with
    an ``Error`` R402 carrying ``reason`` (STANDARD v1.2 §5.19.7), such as
    ``unsupported_capability`` (the host does not perform the capability)
    or ``unsupported_domain`` (not for the step's ``domain``), or a vendor
    ``x-`` reason."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason
        self.message = message


class Host:
    """What a run asks of its environment.

    Override the methods your workflows need; each receives the action (a
    dict with ``kind``, ``run_id``, ``id``, ``frame`` and the action's
    fields, STANDARD v1.2 §5.19.1; ignore any member you do not know) and
    returns a response dict, or ``None`` when there is nothing yet (the
    runner waits a poll interval and asks again, until the action's deadline
    passes). An exception raised by :meth:`invoke_capability` is reported to
    the run as a failed step (R402) — except ``NotImplementedError``, which
    means the host lacks the capability and stops the runner, and
    :class:`HostCannotServe`, which fails the step with its reason — and so is a
    response from it the run cannot accept (malformed, not JSON data, or
    not an answer to the action). A response to any other action that the
    run cannot accept stops the runner with :class:`HostResponseError`.
    The clock methods default to wall-clock time.

    With a :class:`CheckpointTracker`, :meth:`create_checkpoint` records
    checkpoints in it.

    A run may ask for an action again after it was restored (STANDARD v1.2
    §5.19.4): make what you do for an action idempotent under its delivery
    key, ``(action["run_id"], action["id"])``, by keeping the response you
    gave for each key and giving it again. What you transmit to perform an
    approval request, a recheck, a wait or the run's end is protocol traffic
    (§5.19.6), not a ``send``: send only the action's values.
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
        """Run ``action["capability"]`` with ``action["inputs"]``, for
        ``action["domain"]`` when it is not None; return ``{"kind":
        "Output", "value": {...}}`` or ``{"kind": "Error", "code": "R401" |
        "R402", "message": ..., "reason": ...}``. ``reason`` is optional
        (STANDARD v1.2 §5.19.7): ``unsupported_capability`` or
        ``unsupported_domain`` when you cannot serve the step (or raise
        :class:`HostCannotServe`), or an ``x-`` vendor reason."""
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

        ``action["mode"]`` says where to ask (STANDARD v1.2 §5.14):
        ``in_session``, whoever attends the run, in its session;
        ``out_of_band``, through a channel separate from the session, whose
        approvers need not attend the run (keep the run's snapshot while
        you wait). A request for a queued action that a resumed run
        re-entered names it in ``queued_action_id``, the ``action_id`` of
        the record its deferral left, on every request of that step until
        the action is carried out: a re-ask after a recheck and a retry
        included (§5.14.1). With ``identity@1``, the decision
        may attest who decided: ``approver_identities``, one
        ``agent_identity`` per principal, with ``approvers`` empty or
        exactly their principals (§5.17); approvers are then counted by
        principal, and only those whose identity meets the request count.

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
        times out, R401, once the deadline has passed). Liveness is yours to
        watch (STANDARD v1.2 §5.19.3): answer ``LivenessLost`` once the
        source has missed ``failure_threshold`` heartbeats or probes."""
        raise NotImplementedError("no event source")

    def withdraw(self, action: Action, why: str) -> None:
        """The run no longer waits for ``action``: it timed out (``why`` is
        ``"timed out"``) or the run was cancelled (``"cancelled"``). Stop
        performing it: a response to it would be refused (STANDARD v1.2
        §5.19.3, §5.19.5). The default does nothing."""


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
    """The run's action records that were not taken out before it ended
    (``run.take_records()``): with those taken, all its records."""
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
    run_id: str | None = None
    """The run's identifier (STANDARD v1.2 §5.19.2)."""
    reason: str | None = None
    """Why the step that failed the run failed, as a token (§5.19.7), when
    the failure came with one."""
    checkpoint_id: str | None = None
    """For a cancelled run (R408): the latest checkpoint the run knew of,
    which the host may restore itself (§5.19.5)."""
    run_record: dict[str, Any] | None = None
    """The run's record (§5.19.8): an action record derived from how it
    ended, which every host keeps with :attr:`action_records`."""

    @property
    def ok(self) -> bool:
        return self.outcome == "completed"

    @property
    def cancelled(self) -> bool:
        """The host cancelled the run (R408, §5.19.5)."""
        return self.code == "R408"

    @property
    def resumable(self) -> bool:
        """The run ended ``deferred``: it can be resumed once
        (:meth:`WorkflowRunner.resume`), which carries out its queued
        actions (STANDARD v1.2 §5.14.1). The queued actions of a run with
        any other outcome are never carried out: their ``planned`` records
        are abandoned."""
        return self.outcome == "deferred"


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


class RunArchiveError(RunIncomplete):
    """The archive the runner hands each ended run to raised: the run's
    record and records were not kept (STANDARD v1.2 §5.19.8). The run's
    state was not discarded: ``run`` is the live run, ``result`` the result
    to archive again."""

    def __init__(self, message: str, run: _core.Run, result: RunResult) -> None:
        super().__init__(message, run)
        self.result = result


@dataclass(frozen=True)
class Turn:
    """One turn of an event-driven host (:meth:`WorkflowRunner.advance`):
    the run's ``result`` when it ended; else the ``pending`` action the host
    could not answer yet (a ``Sleep``, or one whose handler returned
    ``None``) and the run's ``wake_at`` time, when it has one (STANDARD v1.2
    §5.19.3): call ``advance`` again then, or when a response may have
    arrived."""

    result: RunResult | None
    wake_at: int | None
    pending: Action | None


class RunStartError(ValueError):
    """The run did not start, could not be restored or could not be
    resumed: the catalog does not validate, the inputs do not match the
    workflow's or are not JSON data, the snapshot is malformed or fails its
    HMAC check, the actor is not the run's, or the run did not end
    deferred. ``diagnostics`` lists the catalog's errors (empty for the
    other causes)."""

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
        archive: Callable[[RunResult], None] | None = None,
        run_ids: MutableSet[str] | None = None,
        event_seen: Callable[[str, int], MutableSet[str]] | None = None,
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
            archive: Called with the result of every run the runner sees
                end (:meth:`run`, :meth:`drive`, :meth:`advance`,
                :meth:`cancel`), before it returns: the host keeps the run's
                record and its action records there (STANDARD v1.2 §5.19.8).
                Without it, keep ``result.run_record`` and
                ``result.action_records`` yourself. ``action_records`` are
                the records not taken out before the end: keep those you
                took with ``run.take_records()`` yourself. A run restored
                after it ended and driven again is archived again, under
                the same ``run_record["action_id"]``.
            run_ids: The ``run_id``s already used, which :meth:`start`
                refuses and adds to. A ``run_id`` must differ from those of
                the runs whose records and keys the host keeps (§5.19.2),
                across restarts and processes too: that is the host's duty.
                Pass a store you persist, and prune as you drop runs'
                records and keys; the default is an in-memory set of the
                runs this runner started, which grows by one per run.
            event_seen: Called with a workflow and the index of one of its
                event triggers, it gives the store of the ``event_id``s that
                started runs of that trigger (:class:`EventGate`'s
                ``seen``), which :meth:`start` checks and adds to. Pass
                stores you persist, so an event delivered again after a
                restart starts no other run (§5.10.2); the default is an
                in-memory set per trigger.
        """
        self._engine = engine
        self._max_actions = max_actions
        self._poll_ms = poll_interval_ms
        self._max_polls = max_polls
        self._archive = archive
        # The run_ids used (§5.19.2: a run_id is unique).
        self._run_ids: MutableSet[str] = set() if run_ids is None else run_ids
        self._event_seen = event_seen
        # One gate per event trigger, (workflow, trigger index): it starts
        # at most one run per event_id (§5.10.2).
        self._event_gates: dict[tuple[str, int], EventGate] = {}

    def catalog(self) -> dict[str, Any]:
        """The catalog the engine holds, as the executor sees it."""
        return self._engine.catalog_data()

    def start(
        self,
        workflow: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        attendance: str | None = None,
        run_id: str | None = None,
        now_ms: int | None = None,
        actor_identity: Mapping[str, Any] | None = None,
        records: str = "approvals",
        trigger: int | None = None,
        event: Mapping[str, Any] | None = None,
    ) -> _core.Run:
        """Start a run without driving it (drive it with :meth:`drive`, or
        step it yourself; save it before you act on its first action,
        STANDARD v1.2 §5.19.4). ``actor_identity`` (an ``agent_identity``,
        STANDARD v1.1 §5.17, e.g. :meth:`AgentDescriptor.identity`) names who
        runs the workflow; every action record carries it.

        ``run_id`` must be fresh: it keys the run's records, its run record
        and the host's delivery and idempotency keys (§5.19.2), so the
        runner refuses one in its ``run_ids`` (the default is a random
        one). ``records`` is the record mode (§6.4): ``approvals`` (the
        records of approval steps, as in 1.1) or ``actions`` (a record of
        every step that runs).

        ``trigger`` starts the run from the workflow's trigger of that index
        (§5.10.2): its attendance applies (an ``attendance`` that differs is
        refused); an ``event`` trigger takes the ``event`` (a canonical
        event), which must match it and must not have started a run of it
        before (its ``event_id``), and is given as the input its
        ``delivers_to`` names. The runner applies no sender policy: apply
        yours before you start the run. Without ``trigger`` the run is
        attended unless ``attendance`` says otherwise.

        The executor is given no catalog header (``header=None``, STANDARD
        v1.2 §11.5), and loses nothing by it: the engine writes the header
        of each file it loads into that file's workflows as their
        ``spec_version`` (:meth:`WorkflowEngine.load_catalog`), which takes
        precedence over a header. One engine may hold workflows from files
        with different headers, which one ``header`` could not state.

        Raises:
            RunStartError: the catalog does not validate, ``inputs`` or
                ``actor_identity`` do not fit the workflow or are not JSON
                data, ``run_id`` was used before, or the trigger or the
                event does not start a run.
        """
        now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
        _check_ms(now)
        if records not in RECORD_MODES:
            raise RunStartError(
                f"records must be one of {RECORD_MODES}, not {records!r}", []
            )
        values = dict(inputs or {})
        gate: EventGate | None = None
        if trigger is not None:
            attendance, gate = self._from_trigger(
                workflow, trigger, attendance, event, values
            )
        elif event is not None:
            raise RunStartError(
                "an event starts a run only through an event trigger", []
            )
        rid = run_id or uuid.uuid4().hex
        if rid in self._run_ids:
            raise RunStartError(
                f"run_id {rid!r} was already used; a run_id must be "
                "unique among the runs whose records or idempotency keys the host "
                "keeps (STANDARD §5.19.2)",
                [],
            )
        try:
            run = _core.Run.start(
                self._engine.core_validator(),
                self.catalog(),
                workflow,
                values,
                header=None,
                attendance=attendance or "attended",
                run_id=rid,
                now_ms=now,
                actor_identity=None if actor_identity is None else dict(actor_identity),
                records=records,
            )
        except (TypeError, ValueError) as e:
            raise _start_error(e) from None
        self._run_ids.add(rid)
        if gate is not None and event is not None:
            gate.commit(event)
        return run

    def _from_trigger(
        self,
        workflow: str,
        index: int,
        attendance: str | None,
        event: Mapping[str, Any] | None,
        inputs: dict[str, Any],
    ) -> tuple[str, EventGate | None]:
        """The attendance of a run trigger ``index`` starts, and the event
        gate that admits ``event`` (put into ``inputs``), for an event
        trigger (STANDARD v1.2 §5.10.2)."""
        triggers = self.catalog().get(workflow, {}).get("triggers")
        if not isinstance(triggers, list) or not 0 <= index < len(triggers):
            raise RunStartError(f"workflow {workflow!r} has no trigger {index}", [])
        t = triggers[index]
        if t.get("kind") == "invoke":
            raise RunStartError("an invoke trigger starts nested runs only", [])
        effective = trigger_attendance(t)
        if attendance is not None and attendance != effective:
            raise RunStartError(
                f"the trigger's attendance is {effective}, not {attendance}: a host "
                "applies the trigger's attendance (STANDARD §5.10.2)",
                [],
            )
        if t.get("kind") != "event":
            if event is not None:
                raise RunStartError("only an event trigger takes an event", [])
            return effective, None
        if event is None:
            raise RunStartError(
                "an event trigger starts a run for an event: pass it", []
            )
        gate = self._event_gates.get((workflow, index))
        if gate is None:
            seen = (
                None if self._event_seen is None else self._event_seen(workflow, index)
            )
            gate = self._event_gates[(workflow, index)] = EventGate(
                t["event"], seen=seen
            )
        decision = gate.check(event)
        if decision == "no_match":
            raise RunStartError("the event does not match the trigger", [])
        if decision == "duplicate":
            raise RunStartError(
                f"event {event['event_id']!r} already started a run of this trigger "
                "(STANDARD §5.10.2)",
                [],
            )
        target = t["event"]["delivers_to"]
        if target in inputs:
            raise RunStartError(
                f"input {target!r} is the trigger's event (delivers_to); do not give it",
                [],
            )
        inputs[target] = dict(event)
        return effective, gate

    def restore(
        self,
        snapshot: Mapping[str, Any],
        key: bytes | None = None,
        *,
        actor_identity: Mapping[str, Any] | None = None,
    ) -> _core.Run:
        """Continue a run from ``run.snapshot(key)``, against the same
        catalog.

        A run keeps its actor while it continues (STANDARD v1.2 §5.17):
        name the actor you continue it for with ``actor_identity``, and a
        principal other than the run's, or any actor for a run started
        without one, is refused. When another agent takes over the
        conversation the run belongs to (a handoff), do not continue the run
        under it: cancel the run if it has not ended and start a new one
        under the new agent's identity; a run that ended ``deferred`` may
        instead be resumed under it (:meth:`resume`).

        Raises:
            RunStartError: the snapshot is malformed, has an unsupported
                version, fails its digest or HMAC check, or was taken
                against another catalog, the catalog does not validate, or
                ``actor_identity`` is not the run's actor.
            TypeError: ``key`` is not bytes.
        """
        _check_key(key)
        try:
            return _core.Run.restore(
                self._engine.core_validator(),
                self.catalog(),
                dict(snapshot),
                key,
                actor_identity=None if actor_identity is None else dict(actor_identity),
            )
        except (TypeError, ValueError) as e:
            raise _start_error(e) from None

    def resume(
        self,
        snapshot: Mapping[str, Any],
        key: bytes | None = None,
        *,
        attendance: str = "attended",
        now_ms: int | None = None,
        actor_identity: Mapping[str, Any] | None = None,
        save: Callable[[dict[str, Any]], None] | None = None,
    ) -> _core.Run:
        """Resume a run that ended ``deferred`` from its saved state
        (STANDARD v1.2 §5.14.1), and return it to drive with :meth:`drive`.
        With ``save``, the resumed state (``run.snapshot(key)``) is saved
        before this returns, so no action of the resumption is performed
        unsaved (§5.19.4); else save it yourself before you drive it.

        The run continues as the same run: its deferred steps run again,
        each asked afresh (of a person when ``attendance`` is attended, even
        where the approver is a standing mandate), with the steps that ran
        ahead of them and that they read; a nested run that ended deferred
        continues; checkpoints taken before are asked for again; and each
        queued action's ``planned`` record is updated in place, under the
        same ``action_id``, with every decision of its step until the action
        is carried out. A recovery loop runs again only the steps from its
        target to the step that looped, so nothing that ran ahead is
        repeated. ``actor_identity`` names a new actor, which the trace, the
        later records and the queued records the resumption decides or
        supersedes show.

        Resume one saved state once: each resumption could carry out the
        same queued action. A state saved by an executor before this
        release cannot be resumed (it did not keep the nested runs of
        deferred ``invoke`` steps or which steps ran ahead): cancel that run
        and start a new one.

        Raises:
            RunStartError: the snapshot cannot be restored, the run did not
                end ``deferred`` (a run that failed, escalated, needs a
                replan or was cancelled cannot be resumed, and its queued
                actions are abandoned), ``actor_identity`` is not an
                ``agent_identity``, or the state does not keep what resuming
                needs.
            TypeError: ``key`` is not bytes, or ``now_ms`` is not an int.
        """
        _check_key(key)
        now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
        _check_ms(now)
        # The resumer may be another party than the one that ran the run:
        # the actor is checked when it is named here, not on restore.
        run = self.restore(snapshot, key)
        try:
            run.resume(
                attendance=attendance,
                now_ms=now,
                actor_identity=None if actor_identity is None else dict(actor_identity),
            )
        except (TypeError, ValueError) as e:
            raise _start_error(e) from None
        if save is not None:
            save(run.snapshot(key))
        return run

    def run(
        self,
        workflow: str,
        inputs: Mapping[str, Any] | None,
        host: Host,
        *,
        attendance: str | None = None,
        run_id: str | None = None,
        actor_identity: Mapping[str, Any] | None = None,
        records: str = "approvals",
        trigger: int | None = None,
        event: Mapping[str, Any] | None = None,
        save: Callable[[dict[str, Any]], None] | None = None,
        key: bytes | None = None,
    ) -> RunResult:
        """Start ``workflow`` (as :meth:`start`) and drive it to its end with
        ``host``. With ``save``, the run's state is saved after it starts and
        after every change (:meth:`drive`). Without ``archive``, keep the
        result's ``run_record`` and ``action_records`` yourself (STANDARD
        v1.2 §5.19.8)."""
        run = self.start(
            workflow,
            inputs,
            attendance=attendance,
            run_id=run_id,
            now_ms=host.now_ms(),
            actor_identity=actor_identity,
            records=records,
            trigger=trigger,
            event=event,
        )
        if save is not None:
            save(run.snapshot(key))
        return self.drive(run, host, save=save, key=key)

    def advance(
        self,
        run: _core.Run,
        host: Host,
        *,
        save: Callable[[dict[str, Any]], None] | None = None,
        key: bytes | None = None,
    ) -> Turn:
        """One turn of an event-driven host (STANDARD v1.2 §5.19.3): give the
        run the time, then perform every action the host can answer now,
        until the run ends or waits. Returns the result when it ended, else
        the action it waits on and its wake-up time: set a timer for it, and
        call ``advance`` again when it fires or a response may have arrived
        (an approval decision, an event).

        A tick that times out the action the host was performing withdraws
        it (:meth:`Host.withdraw`). With ``save``, the state
        (``run.snapshot(key)``) is saved after every change, before the host
        acts on the next action (§5.19.4).

        Raises:
            RunIncomplete: after ``max_actions`` answered actions in this
                turn.
            HostResponseError: as :meth:`drive`.
            RunArchiveError: the archive raised.
        """
        turn, _ = self._turn(run, host, save, key, self._max_actions)
        if turn.result is None and turn.pending is None:
            raise RunIncomplete(
                f"the run did not finish within {self._max_actions} actions", run
            )
        return turn

    def _turn(
        self,
        run: _core.Run,
        host: Host,
        save: Callable[[dict[str, Any]], None] | None,
        key: bytes | None,
        budget: int,
    ) -> tuple[Turn, int]:
        """A turn and the actions it answered; an empty turn when it ran
        out of ``budget``."""
        _check_key(key)
        now = host.now_ms()
        _check_ms(now)
        before = run.next()
        if run.tick(now):
            if before["kind"] not in TERMINAL | {"Sleep"}:
                host.withdraw(before, "timed out")
            if save is not None:
                save(run.snapshot(key))
        answered = 0
        while answered < budget:
            action = run.next()
            if action["kind"] in TERMINAL:
                return Turn(self._ended(run, action), None, None), answered
            if action["kind"] == "Sleep":
                return Turn(None, run.wake_at(), action), answered
            response = self._dispatch(host, action)
            if response is None:
                return Turn(None, run.wake_at(), action), answered
            self._submit(run, action, response, host.now_ms())
            answered += 1
            if save is not None:
                save(run.snapshot(key))
        return Turn(None, None, None), answered

    def drive(
        self,
        run: _core.Run,
        host: Host,
        *,
        save: Callable[[dict[str, Any]], None] | None = None,
        key: bytes | None = None,
    ) -> RunResult:
        """Drive a started or restored run to its end: turns of
        :meth:`advance`, sleeping between them until the run's wake-up time
        or the next poll. With ``save``, the state is saved after every
        change, before the host acts on the next action (STANDARD v1.2
        §5.19.4).

        Raises:
            RunIncomplete: after ``max_actions`` answered actions, or
                ``max_polls`` unanswered polls of one action; the run is
                attached, so it can be snapshotted or driven further.
            HostResponseError: (a :class:`RunIncomplete`) the host answered
                an action other than ``InvokeCapability`` with a response
                the run cannot accept.
            RunArchiveError: (a :class:`RunIncomplete`) the archive raised.
        """
        answered = 0
        # Unanswered polls of the current action; a new action resets it.
        polls = 0
        polled: Any = None
        while True:
            turn, n = self._turn(run, host, save, key, self._max_actions - answered)
            answered += n
            if turn.result is not None:
                return turn.result
            action = turn.pending
            if action is None or answered >= self._max_actions:
                raise RunIncomplete(
                    f"the run did not finish within {self._max_actions} actions", run
                )
            if action["id"] != polled:
                polled, polls = action["id"], 0
            if action["kind"] == "Sleep":
                # A Sleep counts as an answered action.
                host.sleep_until(action["until"])
                answered += 1
                continue
            if polls >= self._max_polls:
                raise RunIncomplete(
                    f"no answer to action {action['id']} ({action['kind']}) after "
                    f"{self._max_polls} polls",
                    run,
                )
            polls += 1
            # Nothing yet: wait a poll interval, or until the run's wake-up
            # time if sooner, when the next turn's tick times the action out.
            until = host.now_ms() + self._poll_ms
            if turn.wake_at is not None:
                until = min(until, turn.wake_at)
            host.sleep_until(until)

    def cancel(
        self,
        run: _core.Run,
        reason: str,
        *,
        now_ms: int | None = None,
        host: Host | None = None,
        save: Callable[[dict[str, Any]], None] | None = None,
        key: bytes | None = None,
    ) -> RunResult:
        """Cancel ``run`` (STANDARD v1.2 §5.19.5): it ends at once with
        ``Failed`` R408, ``reason`` as its message; no retry, failure mode,
        recovery or rollback runs, and the result's ``checkpoint_id`` names
        the latest checkpoint, which you may restore yourself. A run that
        ended ``deferred`` can be cancelled too. With ``save``, the
        cancelled state (``run.snapshot(key)``) is saved first (§5.19.4);
        else save it yourself. With ``host``, the action it was performing
        is then withdrawn (:meth:`Host.withdraw`). The result is archived as
        any end.

        Raises:
            ValueError: the run ended otherwise than ``deferred``.
            RunArchiveError: the archive raised.
        """
        now = (
            (host.now_ms() if host else time.time_ns() // 1_000_000)
            if now_ms is None
            else now_ms
        )
        _check_ms(now)
        _check_key(key)
        before = run.next()
        run.cancel(reason, now)
        if save is not None:
            save(run.snapshot(key))
        if host is not None and before["kind"] not in TERMINAL | {"Sleep"}:
            host.withdraw(before, "cancelled")
        return self._ended(run, run.next())

    def _ended(self, run: _core.Run, action: Action) -> RunResult:
        """The result of an ended run, handed to the archive (§5.19.8)."""
        result = self._result(run, action)
        if self._archive is not None:
            try:
                self._archive(result)
            except Exception as e:
                raise RunArchiveError(
                    f"the run ended, but its record could not be archived: {e}",
                    run,
                    result,
                ) from e
        return result

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
            except HostCannotServe as e:
                return _cannot_serve(e)
            except Exception as e:  # the step failed, not the runner
                return {
                    "kind": "Error",
                    "code": "R402",
                    "message": f"{type(e).__name__}: {e}",
                }
        if kind == "AwaitEvent":
            try:
                return host.await_event(action)
            except HostCannotServe as e:
                return _cannot_serve(e)
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
                run_id=run.run_id,
                run_record=run.run_record(),
            )
        return RunResult(
            outcome=None,
            code=action["code"],
            message=action["message"],
            action_records=action["action_records"],
            trace=trace,
            deferred=action.get("deferred", []),
            run_id=run.run_id,
            reason=action.get("reason"),
            checkpoint_id=action.get("checkpoint_id"),
            run_record=run.run_record(),
        )


def _cannot_serve(e: HostCannotServe) -> Response:
    """The ``Error`` that says why a host cannot serve a step (§5.19.7)."""
    return {
        "kind": "Error",
        "code": "R402",
        "reason": e.reason,
        "message": e.message or f"the host cannot serve the step ({e.reason})",
    }


def _start_error(e: TypeError | ValueError) -> RunStartError:
    """The core's start/restore error as a :class:`RunStartError`: a
    ValueError from a catalog that does not validate carries its
    diagnostics as a second argument."""
    if isinstance(e, ValueError) and len(e.args) > 1:
        return RunStartError(str(e.args[0]), list(e.args[1] or []))
    return RunStartError(str(e.args[0]) if e.args else str(e), [])


def _check_key(key: Any) -> None:
    """A snapshot key must be bytes."""
    if key is not None and not isinstance(key, (bytes, bytearray)):
        raise TypeError(f"key must be bytes, not {type(key).__name__}")


def _check_ms(now: Any) -> None:
    """A clock reading must be whole milliseconds; anything else is the
    host's bug, raised as such rather than blamed on the run's data."""
    if isinstance(now, bool) or not isinstance(now, int):
        raise TypeError(
            f"a clock reading must be an int of milliseconds, not {type(now).__name__}"
        )
    if not 0 <= now < 2**64:
        raise ValueError(f"a clock reading must be from 0 to 2^64 - 1 ms, not {now}")
