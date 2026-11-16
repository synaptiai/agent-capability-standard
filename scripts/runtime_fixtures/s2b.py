"""Runtime fixtures of workstream S2b (host protocol, runs and audit records;
RFC-0006 Part B): parallel groups (§5.2.3), `run_id` on actions and the
tick boundaries (§5.19.1, §5.19.3), cancellation (§5.19.5), record mode
`actions` (§6.4), run records (§5.19.8), error reasons (§5.19.7), response
members the protocol does not define, and `audit` `require_record`.

Define each with add(name, description, catalog, script, end, trace, ...),
the function of scripts/gen_runtime_fixtures.py; the building blocks are in
runtime_fixtures.helpers. Executor prose (a `Failed` action's `message`
other than a cancellation's, record and deferral `reason`s) is not pinned.
"""

from runtime_fixtures.helpers import (
    CP,
    POLICY,
    approve,
    cancel,
    err,
    inv,
    mutate,
    out,
    st,
    tick,
    wake,
    wf,
)

CHECKPOINTED = [
    {"expect": inv("checkpoint", step=0), "respond": out(checkpoint_id="cp1")},
    {"expect": inv("constrain", step=1), "respond": out(compliant=True)},
]
HUMAN = {"approver": {"kind": "human"}}


def retrieve(store="r", **kw):
    return st("retrieve", store, input_bindings={"target": "t"}, **kw)


def found():
    return out(data=[1], confidence=1)


def group(join=None):
    """Two members of group g, then a step that reads both."""
    joins = {"join": join} if join else {}
    return wf(
        [
            st(
                "retrieve",
                "a",
                input_bindings={"target": "x"},
                parallel_group="g",
                **joins,
            ),
            st(
                "search",
                "b",
                input_bindings={"query": "q"},
                parallel_group="g",
                join=join or "all_complete",
            ),
            st(
                "transform",
                "c",
                input_bindings={
                    "input": {
                        "a": "${a.data: object}",
                        "b": "${b.results: array<object>}",
                    },
                    "target_format": "json",
                },
            ),
        ]
    )


GROUP_SCRIPT = [
    {"expect": inv("retrieve", step=0), "respond": out(data={"x": 1}, confidence=1)},
    {"expect": inv("search", step=1), "respond": out(results=[], confidence=1)},
    {
        "expect": inv("transform", step=2, inputs={"input": {"a": {"x": 1}, "b": []}}),
        "respond": out(output={}, confidence=1),
    },
]


def audit(**bindings):
    return wf(
        [
            st(
                "audit",
                "a",
                input_bindings={"event": {"what": "deploy"}, **bindings},
            )
        ],
        spec_version="1.2",
    )


def delegate_waiting():
    return wf(
        [
            st(
                "delegate",
                "d",
                timeout="2h",
                input_bindings={"task": {"review": "x"}, "agent": "a"},
                wait={"event_type": "review.done"},
            )
        ],
        requires=["wait@1"],
    )


def child_catalog():
    return {
        "w": wf(
            [
                st(
                    "invoke",
                    "i",
                    workflow_id="child",
                    input_bindings={"workflow": "child"},
                )
            ]
        ),
        "child": wf([retrieve()]),
    }


def register(add):
    """Add this workstream's fixtures."""
    _groups(add)
    _time(add)
    _cancel(add)
    _records(add)
    _failed_records(add)
    _reasons(add)
    _invoke_attendance(add)


def _groups(add):
    add(
        "parallel_group_list_order",
        "A parallel group's members run one at a time, in list order, and a step "
        "after the group runs once both have finished (§5.2.3).",
        {"w": group()},
        GROUP_SCRIPT,
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "parallel_group_unknown_join",
        "A join other than all_complete is W618 and ignored: every member still "
        "runs, and the group joins when all have finished (§5.2.3).",
        {"w": group("any_complete")},
        GROUP_SCRIPT,
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "parallel_group_member_fails",
        "A member's failure is handled by its own failure modes; one that ends the "
        "run abandons the members that have not started (§5.2.3).",
        {
            "w": wf(
                [
                    retrieve(
                        "a",
                        parallel_group="g",
                        failure_modes=[
                            {
                                "condition": "it fails",
                                "on_error": "R402",
                                "action": "stop",
                            }
                        ],
                    ),
                    st(
                        "search",
                        "b",
                        input_bindings={"query": "q"},
                        parallel_group="g",
                    ),
                ]
            )
        },
        [{"expect": inv("retrieve", step=0), "respond": err("R402")}],
        {"kind": "Failed", "code": "R402", "step": 0},
        trace=["step_failed", "failure_mode_fired", "run_failed"],
    )


def _time(add):
    add(
        "action_has_run_id",
        "Every action, the terminal one included, carries the run's run_id (§5.19.1).",
        {"w": wf([retrieve()])},
        [{"expect": inv("retrieve", run_id="run-1", id=1), "respond": found()}],
        {"kind": "Completed", "run_id": "run-1", "id": 2},
    )
    add(
        "wake_at_backoff",
        "A retry's Sleep ends at a tick at its until, not before: the wake-up time "
        "is until (§5.19.3), and linear backoff waits attempt x 1 s (§5.2).",
        {"w": wf([retrieve(retry={"max": 1, "backoff": "linear"})])},
        [
            {"expect": inv("retrieve", attempt=1), "respond": err("R402")},
            {"expect": {"kind": "Sleep", "until": 1000}},
            wake(1000),
            tick(999, changed=False),
            tick(1000, changed=True),
            {"expect": inv("retrieve", attempt=2), "respond": found(), "at": 1000},
        ],
        {"kind": "Completed", "outcome": "completed"},
        trace=["retry"],
    )
    add(
        "wake_at_deadline",
        "An action times out at a tick after its deadline: the wake-up time is the "
        "deadline plus 1 ms, and a tick at the deadline changes nothing (§5.19.3).",
        {"w": wf([retrieve(timeout="10s")])},
        [
            {"expect": inv("retrieve", deadline=10000)},
            wake(10001),
            tick(10000, changed=False),
            tick(10001, changed=True),
        ],
        {"kind": "Failed", "code": "R401", "step": 0},
    )
    add(
        "wake_at_in_time_at_deadline",
        "An answer submitted at the deadline is in time (§5.19.3).",
        {"w": wf([retrieve(timeout="10s")])},
        [
            {
                "expect": inv("retrieve", deadline=10000),
                "respond": found(),
                "at": 10000,
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "wake_at_approval_expiry",
        "An approval lapses at a tick after its expires_at: the wake-up time is "
        "expires_at plus 1 ms (§5.19.3), and the step fails F502 with an expired "
        "record (§5.14).",
        {
            "w": wf(
                [CP, POLICY, mutate(approval={**HUMAN, "expires": "1h"})],
                requires=["approval@1"],
            )
        },
        [
            *CHECKPOINTED,
            {"expect": {"kind": "RequestApproval", "expires_at": 3600000}},
            wake(3600001),
            tick(3600000, changed=False),
            tick(3600001, changed=True),
        ],
        {
            "kind": "Failed",
            "code": "F502",
            "step": 2,
            "action_records": [{"status": "expired", "code": "F502"}],
        },
        trace=["approval_expired"],
    )
    add(
        "wake_at_none_without_expiry",
        "An approval with no expiry has no wake-up time: no tick changes the run "
        "(§5.19.3).",
        {"w": wf([CP, POLICY, mutate()])},
        [
            *CHECKPOINTED,
            {"expect": {"kind": "RequestApproval", "expires_at": None}},
            wake(None),
            tick(999999999, changed=False),
            {
                "expect": {"kind": "RequestApproval"},
                "respond": approve("d1"),
                "at": 999999999,
            },
            {"expect": inv("mutate"), "respond": out(success=True)},
        ],
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "wake_at_ignores_liveness",
        "Liveness is the host's to watch, never a wake-up time: a wait's wake-up "
        "time is its deadline plus 1 ms, whatever its probe interval (§5.19.3).",
        {
            "w": wf(
                [
                    st(
                        "receive",
                        "r",
                        timeout="2h",
                        wait={
                            "event_type": "job.done",
                            "liveness": {"mode": "probe", "interval": "10m"},
                        },
                    )
                ],
                requires=["wait@1"],
            )
        },
        [
            {"expect": {"kind": "AwaitEvent", "deadline": 7200000}},
            wake(7200001),
            tick(600000, changed=False),
            {
                "expect": {"kind": "AwaitEvent"},
                "respond": {"kind": "Event", "event": {"event_type": "job.done"}},
                "at": 600000,
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
    )


def _cancel(add):
    add(
        "cancel_pending_capability",
        "Cancelling ends the run with Failed R408 at once: no retry, failure mode "
        "or recovery loop runs; in record mode actions the started step has a "
        "cancelled record (§5.19.5).",
        {
            "w": wf(
                [
                    retrieve(
                        retry={"max": 3},
                        failure_modes=[
                            {
                                "condition": "it fails",
                                "on_error": ["R401", "R402"],
                                "action": "request_more_context",
                                "recovery": {"goto_step": "r", "max_loops": 2},
                            }
                        ],
                    )
                ]
            )
        },
        [{"expect": inv("retrieve", attempt=1)}, cancel("operator stop", at=5)],
        {
            "kind": "Failed",
            "code": "R408",
            "message": "operator stop",
            "step": 0,
            "action_records": [
                {
                    "status": "cancelled",
                    "capability": "retrieve",
                    "code": "R408",
                    "step": 0,
                }
            ],
        },
        trace=["run_cancelled"],
        records="actions",
        run_record={
            "action_id": "run-1",
            "run_id": "run-1",
            "status": "cancelled",
            "code": "R408",
            "step": 0,
            "intent": "run w",
            "details": {"kind": "Failed", "records": 1},
        },
    )
    add(
        "cancel_after_checkpoint_names_it",
        "A cancelled run's Failed action names the latest checkpoint the run knows "
        "of, which the host may restore itself: the executor does not roll back; "
        "the approved record becomes cancelled (§5.19.5).",
        {"w": wf([CP, POLICY, mutate()])},
        [
            *CHECKPOINTED,
            {
                "expect": {"kind": "RequestApproval", "step": 2},
                "respond": approve("d1"),
            },
            {"expect": inv("mutate")},
            cancel("operator stop"),
        ],
        {
            "kind": "Failed",
            "code": "R408",
            "step": 2,
            "checkpoint_id": "cp1",
            "action_records": [
                {
                    "status": "cancelled",
                    "code": "R408",
                    "checkpoint_id": "cp1",
                    "approval": {"decision": "approved", "decision_id": "d1"},
                }
            ],
        },
    )
    add(
        "cancel_pending_approval",
        "A step waiting for its approval has not started: cancelling leaves no "
        "record (§5.19.5).",
        {"w": wf([CP, POLICY, mutate()])},
        [*CHECKPOINTED, {"expect": {"kind": "RequestApproval"}}, cancel("stop")],
        {"kind": "Failed", "code": "R408", "step": 2, "action_records": []},
    )
    add(
        "cancel_deferred_run",
        "A run that ended deferred can be cancelled: its queued action is "
        "cancelled and will not be carried out; the deferrals stay in the report "
        "(§5.19.5).",
        {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate(approval={**HUMAN, "when_unattended": "defer_to_queue"}),
                ],
                requires=["approval@1"],
            )
        },
        [
            *CHECKPOINTED,
            {"expect": {"kind": "Completed", "outcome": "deferred"}},
            cancel("queue dropped", at=10),
        ],
        {
            "kind": "Failed",
            "code": "R408",
            "step": None,
            "action_records": [{"status": "cancelled", "code": "R408"}],
            "deferred": [{"step": 2, "store_as": "m"}],
        },
        attendance="unattended",
        run_record={"status": "cancelled", "details": {"records": 1}},
    )
    add(
        "cancel_nested",
        "Cancelling ends the nested runs with the run (§5.19.5).",
        child_catalog(),
        [
            {"expect": inv("retrieve", frame=["w", "child"])},
            cancel("stop"),
        ],
        {"kind": "Failed", "code": "R408", "frame": ["w", "child"], "step": 0},
    )
    add(
        "cancel_nested_records_actions",
        "In record mode actions, every frame's started step gets a cancelled "
        "record, root first (§5.19.5).",
        child_catalog(),
        [
            {"expect": inv("retrieve", frame=["w", "child"])},
            cancel("stop"),
        ],
        {
            "kind": "Failed",
            "code": "R408",
            "action_records": [
                {"status": "cancelled", "frame": ["w"], "capability": "invoke"},
                {
                    "status": "cancelled",
                    "frame": ["w", "child"],
                    "capability": "retrieve",
                },
            ],
        },
        records="actions",
    )
    add(
        "cancel_waiting_delegate",
        "A waiting delegate whose delegation was sent has started: cancelling "
        "records it (§5.19.5).",
        {"w": delegate_waiting()},
        [
            {
                "expect": inv("delegate"),
                "respond": out(task_id="t1", accepted=True),
            },
            {"expect": {"kind": "AwaitEvent", "correlate": {"task_id": "t1"}}},
            cancel("stop"),
        ],
        {
            "kind": "Failed",
            "code": "R408",
            "action_records": [
                {"status": "cancelled", "capability": "delegate", "code": "R408"}
            ],
        },
        records="actions",
    )
    add(
        "cancel_during_backoff",
        "A step waiting out a retry's backoff has started (its first attempt ran): "
        "cancelling records it once, and the run does not wait (§5.19.5).",
        {"w": wf([retrieve(retry={"max": 2, "backoff": "linear"})])},
        [
            {"expect": inv("retrieve"), "respond": err("R402")},
            {"expect": {"kind": "Sleep", "until": 1000}},
            cancel("stop", at=10),
        ],
        {
            "kind": "Failed",
            "code": "R408",
            "action_records": [{"status": "cancelled", "capability": "retrieve"}],
        },
        records="actions",
    )
    add(
        "cancel_pending_delay",
        "A step waiting out its delay has not started: cancelling leaves no record "
        "(§5.19.5).",
        {"w": wf([retrieve(delay="1m")], requires=["wait@1"])},
        [{"expect": {"kind": "Sleep", "until": 60000}}, cancel("stop")],
        {"kind": "Failed", "code": "R408", "action_records": []},
        records="actions",
    )
    add(
        "cancel_failure_checkpoint",
        "A pending failure-mode checkpoint gets its own cancelled record, after the "
        "step's failed one (§5.19.5, §6.4).",
        {"w": wf([retrieve(failure_modes=[_pause()])])},
        [
            {"expect": inv("retrieve"), "respond": err("R402")},
            {"expect": {"kind": "CreateCheckpoint", "step": 0}},
            cancel("stop"),
        ],
        {
            "kind": "Failed",
            "code": "R408",
            "action_records": [
                {"status": "failed", "capability": "retrieve", "code": "R402"},
                {
                    "status": "cancelled",
                    "capability": "checkpoint",
                    "code": "R408",
                    "step": 0,
                },
            ],
        },
        records="actions",
    )


def _pause():
    return {
        "condition": "it fails",
        "on_error": "R402",
        "action": "pause_and_checkpoint",
        "recovery": {"goto_step": "r", "max_loops": 1},
    }


def _record(capability, step, **members):
    return {
        "run_id": "run-1",
        "frame": ["w"],
        "step": step,
        "capability": capability,
        **members,
    }


def _records(add):
    add(
        "records_actions_failure_checkpoint",
        "Record mode actions: a failure-mode checkpoint has its own record, and the "
        "recovery loop's pass of the step a new one (§6.4).",
        {"w": wf([retrieve(failure_modes=[_pause()])])},
        [
            {"expect": inv("retrieve"), "respond": err("R402")},
            {
                "expect": {"kind": "CreateCheckpoint"},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {"expect": inv("retrieve"), "respond": found()},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"status": "failed", "capability": "retrieve", "code": "R402"},
                {
                    "status": "executed",
                    "capability": "checkpoint",
                    "checkpoint_id": "cp2",
                },
                {"status": "executed", "capability": "retrieve"},
            ],
        },
        records="actions",
    )
    add(
        "run_record_failed_no_records",
        "A run with no approval step that fails still has a record: the run record "
        "derived from its Failed action (§5.19.8).",
        {"w": wf([retrieve()])},
        [{"expect": inv("retrieve"), "respond": err("R402")}],
        {"kind": "Failed", "code": "R402", "action_records": []},
        run_record={
            "action_id": "run-1",
            "run_id": "run-1",
            "frame": ["w"],
            "intent": "run w",
            "actor": "agent",
            "status": "failed",
            "code": "R402",
            "step": 0,
            "timestamp": "1970-01-01T00:00:00.000Z",
            "details": {"kind": "Failed", "records": 0},
        },
    )
    add(
        "run_record_deferred_planned",
        "A run that ended deferred has a planned run record: it can still be "
        "resumed or cancelled (§5.19.8).",
        {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate(approval={**HUMAN, "when_unattended": "defer_to_queue"}),
                ],
                requires=["approval@1"],
            )
        },
        CHECKPOINTED,
        {"kind": "Completed", "outcome": "deferred"},
        attendance="unattended",
        run_record={
            "status": "planned",
            "details": {"kind": "Completed", "outcome": "deferred", "records": 1},
        },
    )
    add(
        "records_actions_steps",
        "Record mode actions: one record for every step that runs, each with its "
        "run_id, frame, step and capability; the checkpoint step's and the step "
        "that used it name the checkpoint; the approval names its decision (§6.4).",
        {"w": wf([retrieve(), CP, POLICY, mutate()])},
        [
            {"expect": inv("retrieve"), "respond": found()},
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
            {
                "expect": {"kind": "RequestApproval", "step": 3},
                "respond": approve("d1"),
            },
            {"expect": inv("mutate"), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                _record("retrieve", 0, status="executed"),
                _record("checkpoint", 1, status="executed", checkpoint_id="cp1"),
                _record("constrain", 2, status="executed"),
                _record(
                    "mutate",
                    3,
                    status="executed",
                    checkpoint_id="cp1",
                    approval={"decision": "approved", "decision_id": "d1"},
                ),
            ],
        },
        records="actions",
        run_record={
            "status": "executed",
            "details": {"kind": "Completed", "outcome": "completed", "records": 4},
        },
    )
    add(
        "records_actions_failed_once_per_pass",
        "Record mode actions: a retry is the same pass, so a step that fails after "
        "its retries has one failed record (§6.4).",
        {"w": wf([retrieve(retry={"max": 1})])},
        [
            {"expect": inv("retrieve", attempt=1), "respond": err("R402")},
            {"expect": inv("retrieve", attempt=2), "respond": err("R402")},
        ],
        {
            "kind": "Failed",
            "code": "R402",
            "action_records": [
                {"status": "failed", "code": "R402", "capability": "retrieve"}
            ],
        },
        records="actions",
    )
    add(
        "records_actions_loop_new_pass",
        "Record mode actions: a recovery loop that runs a step again starts a new "
        "pass, with a record of its own (§6.4).",
        {
            "w": wf(
                [
                    retrieve(
                        failure_modes=[
                            {
                                "condition": "it fails",
                                "on_error": "R402",
                                "action": "request_more_context",
                                "recovery": {"goto_step": "r", "max_loops": 1},
                            }
                        ]
                    )
                ]
            )
        },
        [
            {"expect": inv("retrieve"), "respond": err("R402")},
            {"expect": inv("retrieve"), "respond": found()},
        ],
        {
            "kind": "Completed",
            "action_records": [
                {"status": "failed", "code": "R402"},
                {"status": "executed"},
            ],
        },
        records="actions",
    )
    add(
        "records_actions_rollback",
        "Record mode actions: a Rollback a failure mode asks for has its own "
        "record, with the checkpoint it restored and the step's step (§6.4).",
        {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate(
                        failure_modes=[
                            {
                                "condition": "it fails",
                                "on_error": "R402",
                                "action": "rollback",
                            }
                        ]
                    ),
                ]
            )
        },
        [
            *CHECKPOINTED,
            {"expect": {"kind": "RequestApproval"}, "respond": approve("d1")},
            {"expect": inv("mutate"), "respond": err("R402")},
            {
                "expect": {"kind": "Rollback", "checkpoint_id": "cp1", "step": 2},
                "respond": {"kind": "RolledBack"},
            },
        ],
        {
            "kind": "Failed",
            "code": "R402",
            "action_records": [
                {"capability": "checkpoint", "status": "executed"},
                {"capability": "constrain", "status": "executed"},
                {"capability": "mutate", "status": "failed", "code": "R402"},
                {
                    "capability": "rollback",
                    "status": "executed",
                    "checkpoint_id": "cp1",
                    "step": 2,
                },
            ],
        },
        records="actions",
    )
    add(
        "records_actions_checkpoint_refused",
        "Record mode actions: a step whose checkpoint cannot be taken fails F501 "
        "after it started, with a failed record (§6.4).",
        {
            "w": wf(
                [
                    CP,
                    retrieve("a", requires_checkpoint=True),
                    retrieve("b", requires_checkpoint=True),
                ]
            )
        },
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("retrieve", step=1), "respond": found()},
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": err("F501"),
            },
        ],
        {
            "kind": "Failed",
            "code": "F501",
            "action_records": [
                {
                    "capability": "checkpoint",
                    "status": "executed",
                    "checkpoint_id": "cp1",
                },
                {
                    "capability": "retrieve",
                    "step": 1,
                    "status": "executed",
                    "checkpoint_id": "cp1",
                },
                {
                    "capability": "retrieve",
                    "step": 2,
                    "status": "failed",
                    "code": "F501",
                },
            ],
        },
        records="actions",
    )
    add(
        "records_default_unchanged",
        "The default record mode, approvals, writes the records 1.1 wrote, now with "
        "their correlation members (§6.4).",
        {"w": wf([retrieve(), CP, POLICY, mutate()])},
        [
            {"expect": inv("retrieve"), "respond": found()},
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
            {"expect": {"kind": "RequestApproval"}, "respond": approve("d1")},
            {"expect": inv("mutate"), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "action_records": [
                _record(
                    "mutate",
                    3,
                    status="executed",
                    checkpoint_id="cp1",
                    approval={"decision_id": "d1"},
                )
            ],
        },
    )
    add(
        "approval_record_decision_id",
        "An approval record names the host's decision_id (§5.19.1, §6.4).",
        {"w": wf([CP, POLICY, mutate()])},
        [
            *CHECKPOINTED,
            {"expect": {"kind": "RequestApproval"}, "respond": approve("d1")},
            {"expect": inv("mutate"), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "action_records": [
                {"approval": {"decision_id": "d1", "decision": "approved"}}
            ],
        },
    )
    add(
        "audit_require_record_fails",
        "An audit step that binds require_record: true fails R402, reason "
        "not_recorded, when its output's recorded is not true (§6.4).",
        {"w": audit(require_record=True)},
        [{"expect": inv("audit"), "respond": out(recorded=False)}],
        {"kind": "Failed", "code": "R402", "reason": "not_recorded", "step": 0},
    )
    add(
        "audit_require_record_retries",
        "require_record's failure is R402: retries apply (§6.4, §5.2).",
        {
            "w": wf(
                [
                    st(
                        "audit",
                        "a",
                        input_bindings={
                            "event": {"what": "deploy"},
                            "require_record": True,
                        },
                        retry={"max": 1},
                    )
                ],
                spec_version="1.2",
            )
        },
        [
            {"expect": inv("audit", attempt=1), "respond": out(recorded=False)},
            {"expect": inv("audit", attempt=2), "respond": out(recorded=True)},
        ],
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "audit_require_record_v11_unchecked",
        "In a 1.1 workflow, require_record is an input the executor passes on,"
        " as 1.1 did: an audit step that binds it completes on an output whose"
        " recorded is false (§6.4 applies from 1.2; W616).",
        {
            "w": wf(
                [
                    st(
                        "audit",
                        "a",
                        input_bindings={
                            "event": {"what": "deploy"},
                            "require_record": True,
                        },
                    )
                ]
            )
        },
        [
            {
                "expect": inv("audit", inputs={"require_record": True}),
                "respond": out(recorded=False),
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "audit_recorded_false_completes",
        "Without require_record an audit step that did not record completes, as in "
        "1.1 (§6.4).",
        {"w": audit()},
        [{"expect": inv("audit"), "respond": out(recorded=False)}],
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"a": {"recorded": False}},
        },
    )
    add(
        "audit_recorded_false_gate",
        "A workflow may stop on recorded == false with an after-gate instead (§6.4).",
        {
            "w": wf(
                [
                    st(
                        "audit",
                        "a",
                        input_bindings={"event": {"what": "deploy"}},
                        gates=[
                            {
                                "when": "${a.recorded} == false",
                                "phase": "after",
                                "action": "stop",
                            }
                        ],
                    )
                ]
            )
        },
        [{"expect": inv("audit"), "respond": out(recorded=False)}],
        {"kind": "Failed", "code": "R403", "step": 0},
    )


def _failing_mutate(failure_mode):
    """Checkpoint, constrain, then a mutation asked of a person whose
    failure mode answers R402 with `failure_mode`."""
    return {
        "w": wf(
            [
                CP,
                POLICY,
                mutate(
                    approval=HUMAN,
                    failure_modes=[
                        {"condition": "it fails", "on_error": "R402", **failure_mode}
                    ],
                ),
            ],
            requires=["approval@1"],
        )
    }


APPROVED_THEN_FAILS = [
    *CHECKPOINTED,
    {"expect": {"kind": "RequestApproval", "step": 2}, "respond": approve("d1")},
    {"expect": inv("mutate", step=2), "respond": err("R402")},
]


def _failed_records(add):
    """An approved step that fails has a failed record, also when its run
    then fails for another reason (§6.4)."""
    rollback = _failing_mutate({"action": "rollback"})
    rollback_fails = [
        *APPROVED_THEN_FAILS,
        {"expect": {"kind": "Rollback", "step": 2}, "respond": err("F503")},
    ]
    add(
        "records_actions_failure_rollback_fails",
        "Record mode actions: an approved step that fails, whose failure mode's "
        "Rollback then fails (F503), has a failed record with its own code, beside "
        "the failed record of the rollback (§6.4).",
        rollback,
        rollback_fails,
        {
            "kind": "Failed",
            "code": "F503",
            "action_records": [
                {"capability": "checkpoint", "status": "executed"},
                {"capability": "constrain", "status": "executed"},
                {"capability": "mutate", "status": "failed", "code": "R402"},
                {"capability": "rollback", "status": "failed", "code": "F503"},
            ],
        },
        records="actions",
    )
    add(
        "records_actions_failure_checkpoint_fails",
        "Record mode actions: an approved step that fails, whose failure mode's "
        "checkpoint then cannot be taken (F501), has a failed record with its own "
        "code, beside the failed record of the checkpoint (§6.4).",
        _failing_mutate(
            {
                "action": "pause_and_checkpoint",
                "recovery": {"goto_step": "m", "max_loops": 1},
            }
        ),
        [
            *APPROVED_THEN_FAILS,
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": err("F501")},
        ],
        {
            "kind": "Failed",
            "code": "F501",
            "action_records": [
                {"capability": "checkpoint", "status": "executed"},
                {"capability": "constrain", "status": "executed"},
                {"capability": "mutate", "status": "failed", "code": "R402"},
                {"capability": "checkpoint", "status": "failed", "code": "F501"},
            ],
        },
        records="actions",
    )
    add(
        "records_failure_rollback_fails",
        "The default record mode: an approved step that fails, whose failure mode's "
        "Rollback then fails (F503), has a failed record with its own code, as an "
        "approved step that fails has (§6.4).",
        rollback,
        rollback_fails,
        {
            "kind": "Failed",
            "code": "F503",
            "action_records": [
                {"capability": "mutate", "status": "failed", "code": "R402"}
            ],
        },
    )
    add(
        "records_failure_nothing_to_roll_back",
        "An approved step that fails, whose failure mode rolls back when the run "
        "has no checkpoint (F503), has a failed record with its own code (§6.4).",
        {
            "w": wf(
                [
                    retrieve(
                        approval=HUMAN,
                        requires_approval=True,
                        failure_modes=[
                            {
                                "condition": "it fails",
                                "on_error": "R402",
                                "action": "rollback",
                            }
                        ],
                    )
                ],
                requires=["approval@1"],
            )
        },
        [
            {
                "expect": {"kind": "RequestApproval", "step": 0},
                "respond": approve("d1"),
            },
            {"expect": inv("retrieve"), "respond": err("R402")},
        ],
        {
            "kind": "Failed",
            "code": "F503",
            "action_records": [
                {"capability": "retrieve", "status": "failed", "code": "R402"}
            ],
        },
    )


def _invoke_attendance(add):
    """A run an invoke step starts has its invoker's attendance, whatever its
    invoke trigger declares (§5.10, §5.10.2)."""

    def catalog(declared):
        return {
            "w": wf(
                [
                    st(
                        "invoke",
                        "i",
                        workflow_id="child",
                        input_bindings={"workflow": "child"},
                    )
                ]
            ),
            "child": wf(
                [retrieve(approval=HUMAN, requires_approval=True)],
                requires=["approval@1", "triggers@1"],
                triggers=[{"kind": "invoke", "attendance": declared}],
            ),
        }

    add(
        "invoke_trigger_attendance_ignored",
        "An invoke trigger's declared attendance has no effect: invoked from an "
        "attended run, a nested run whose invoke trigger declares unattended is "
        "attended, and its step is asked of a person (§5.10, §5.10.2).",
        catalog("unattended"),
        [
            {
                "expect": {
                    "kind": "RequestApproval",
                    "frame": ["w", "child"],
                    "approver": {"kind": "human"},
                },
                "respond": approve("d1"),
            },
            {"expect": inv("retrieve", frame=["w", "child"]), "respond": found()},
        ],
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "invoke_trigger_attendance_ignored_unattended",
        "Invoked from an unattended run, a nested run whose invoke trigger declares "
        "attended is unattended: its step's human approver is not asked, the step "
        "fails (F502), and so does the invoke step (R402) (§5.10, §5.10.2).",
        catalog("attended"),
        [],
        {"kind": "Failed", "code": "R402", "step": 0, "frame": ["w"]},
        trace=["approval_unattended", "invoke_returned"],
        attendance="unattended",
    )


def _reasons(add):
    add(
        "response_extra_members_ignored",
        "Response members the protocol does not define are ignored, as in 1.1 "
        "(§5.19.1): neither response is refused.",
        {"w": wf([retrieve(retry={"max": 1})])},
        [
            {
                "expect": inv("retrieve", attempt=1),
                "respond": err("R402", reason="Retry Later", x_trace="abc"),
            },
            {
                "expect": inv("retrieve", attempt=2),
                "respond": {
                    "kind": "Output",
                    "value": {"data": [1], "confidence": 1, "evidence_anchors": []},
                    "x_meta": {"n": 1},
                },
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "error_reason_outside_grammar_ignored",
        "A reason outside §5.19.7 is ignored, not refused: the step fails as if "
        "the Error carried none.",
        {"w": wf([retrieve()])},
        [
            {
                "expect": inv("retrieve"),
                "respond": err("R402", reason="Unsupported Domain"),
            }
        ],
        {"kind": "Failed", "code": "R402", "step": 0},
    )
    add(
        "error_reason_unsupported_domain",
        "A host that cannot serve the step's domain says so with reason "
        "unsupported_domain; the run's Failed action carries it (§5.19.7).",
        {"w": wf([retrieve(domain="audio")])},
        [
            {
                "expect": inv("retrieve", domain="audio"),
                "respond": err("R402", reason="unsupported_domain"),
            }
        ],
        {"kind": "Failed", "code": "R402", "reason": "unsupported_domain"},
        run_record={"reason_code": "unsupported_domain", "code": "R402"},
    )
    add(
        "error_reason_with_retry",
        "A reason does not stop retries: the code decides what the run does (§5.19.7).",
        {"w": wf([retrieve(domain="audio", retry={"max": 1})])},
        [
            {
                "expect": inv("retrieve", attempt=1),
                "respond": err("R402", reason="unsupported_domain"),
            },
            {"expect": inv("retrieve", attempt=2), "respond": found()},
        ],
        {"kind": "Completed", "outcome": "completed"},
        trace=["retry"],
    )
