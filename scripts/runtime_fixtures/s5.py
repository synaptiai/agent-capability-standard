"""Runtime fixtures of workstream S5 (checkpoint, rollback, send and memory; RFC-0009).

Define each with add(name, description, catalog, script, end, trace, ...),
the function of scripts/gen_runtime_fixtures.py; the building blocks are in
runtime_fixtures.helpers. They pin the idempotency key of a pass (STANDARD
v1.2 §4.4.2), the destination check (§4.4.2), what a rollback reports
(§4.4.1, §5.15.4) and the memory scope echo (§4.5). Every harness starts
its runs with run_id "run-1", so a key is "run-1:<id>".
"""

from runtime_fixtures.helpers import CP, POLICY, approve, err, inv, mutate, out, st, wf

SAVE = st("checkpoint", "cp", input_bindings={"scope": "report_state"})
HOOKS = [["https://hooks.example.com/*"]]
NO_RETRY_WAIT = {"backoff": "none"}


def send(destination="ops", **kw):
    return st(
        "send",
        "s",
        input_bindings={"destination": destination, "payload": {"report": 1}},
        **kw,
    )


def profile(domain, patterns):
    return {"domain": domain, "version": "1.0.0", "allowed_destinations": patterns}


def refused(step=1):
    return {
        "kind": "Failed",
        "code": "F504",
        "step": step,
        "reason": "destination_not_allowed",
    }


def checkpoint_taken(cp="cp1"):
    return {"expect": inv("checkpoint", step=0), "respond": out(checkpoint_id=cp)}


def waiting_delegate():
    return st(
        "delegate",
        "d",
        timeout="2h",
        retry={"max": 1, **NO_RETRY_WAIT},
        input_bindings={"task": {"review": "c1"}, "agent": "a"},
        wait={
            "event_type": "review.done",
            "liveness": {"mode": "push", "interval": "10m", "failure_threshold": 3},
        },
    )


def memory(capability, scope=None, **kw):
    bindings = {"key": "k"}
    if capability == "persist":
        bindings["data"] = {"a": 1}
    if scope is not None:
        bindings["scope"] = scope
    return {
        "w": wf(
            [st(capability, "m", input_bindings=bindings, **kw)], spec_version="1.2"
        )
    }


def register(add):
    _sends(add)
    _destinations(add)
    _rollbacks(add)
    _memory(add)


def _sends(add):
    add(
        "send_retry_one_key",
        "A send is approved once; its retry after R401 carries the same idempotency"
        " key as its first attempt (the id of the pass's first InvokeCapability), so"
        " a host transmits at most once under the one approval (§4.4.2).",
        {"w": wf([SAVE, send(retry={"max": 1, **NO_RETRY_WAIT})])},
        [
            checkpoint_taken(),
            {
                "expect": {"kind": "RequestApproval", "step": 1},
                "respond": approve("d1"),
            },
            {
                "expect": inv("send", step=1, attempt=1, idempotency_key="run-1:3"),
                "respond": err("R401", "no answer"),
            },
            {
                "expect": inv("send", step=1, attempt=2, idempotency_key="run-1:3"),
                "respond": out(sent=True),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [{"status": "executed", "idempotency_key": "run-1:3"}],
        },
        ["approval_requested", "retry", "step_completed"],
    )

    add(
        "send_loop_new_key",
        "A recovery loop runs the send again: a new pass, with a new approval and a"
        " new idempotency key (§4.4.2).",
        {
            "w": wf(
                [
                    SAVE,
                    send(
                        failure_modes=[
                            {
                                "condition": "the send failed",
                                "on_error": "R402",
                                "action": "request_more_context",
                                "recovery": {"goto_step": "cp", "max_loops": 1},
                            }
                        ]
                    ),
                ],
                requires=["recovery@1"],
            )
        },
        [
            checkpoint_taken(),
            {
                "expect": {"kind": "RequestApproval", "step": 1},
                "respond": approve("d1"),
            },
            {
                "expect": inv("send", step=1, attempt=1, idempotency_key="run-1:3"),
                "respond": err("R402", "refused"),
            },
            checkpoint_taken("cp2"),
            {
                "expect": {"kind": "RequestApproval", "step": 1},
                "respond": approve("d2"),
            },
            {
                "expect": inv("send", step=1, attempt=1, idempotency_key="run-1:6"),
                "respond": out(sent=True),
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["failure_mode_fired", "loop"],
    )

    add(
        "send_outcome_unknown",
        "A host that cannot tell whether an earlier attempt under the key"
        " transmitted does not send again: it answers an Error with reason"
        " outcome_unknown, and the step fails R402 with that reason (§4.4.2).",
        {"w": wf([SAVE, send(retry={"max": 1, **NO_RETRY_WAIT})])},
        [
            checkpoint_taken(),
            {
                "expect": {"kind": "RequestApproval", "step": 1},
                "respond": approve("d1"),
            },
            {
                "expect": inv("send", step=1, attempt=1, idempotency_key="run-1:3"),
                "respond": err("R401", "no answer"),
            },
            {
                "expect": inv("send", step=1, attempt=2, idempotency_key="run-1:3"),
                "respond": err("R402", "may have been sent", reason="outcome_unknown"),
            },
        ],
        {"kind": "Failed", "code": "R402", "step": 1, "reason": "outcome_unknown"},
        ["retry", "step_failed"],
    )

    add(
        "delegate_replaces_new_key",
        "A waiting delegate whose delegate went silent (R406) delegates again: the"
        " new delegation names the one it replaces and has a key of its own, built"
        " from its own id (§4.4.2).",
        {"w": wf([waiting_delegate()], requires=["wait@1"])},
        [
            {
                "expect": inv("delegate", step=0, attempt=1, idempotency_key="run-1:1"),
                "respond": out(accepted=True, task_id="t1"),
            },
            {
                "expect": {
                    "kind": "AwaitEvent",
                    "step": 0,
                    "correlate": {"task_id": "t1"},
                },
                "respond": {"kind": "LivenessLost"},
            },
            {
                "expect": inv(
                    "delegate",
                    step=0,
                    attempt=2,
                    replaces="t1",
                    idempotency_key="run-1:3",
                ),
                "respond": out(accepted=True, task_id="t2"),
            },
            {
                "expect": {
                    "kind": "AwaitEvent",
                    "step": 0,
                    "correlate": {"task_id": "t2"},
                },
                "respond": {
                    "kind": "Event",
                    "event": {"event_type": "review.done", "task_id": "t2"},
                    "principal": "a",
                },
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["delegated", "retry", "event_received"],
    )


def _destinations(add):
    add(
        "destination_policy_refuses",
        "Under the host's destination policy, a send to a destination it does not"
        " allow fails F504 (destination_not_allowed) when its inputs are resolved:"
        " no one is asked to approve it, and the checkpoint is not used (§4.4.2).",
        {"w": wf([SAVE, send("https://evil.example.net/x")])},
        [checkpoint_taken()],
        refused(),
        ["step_failed", "run_failed"],
        destinations=HOOKS,
    )

    add(
        "destination_policy_allows",
        "A destination the policy allows is asked for approval and sent (§4.4.2).",
        {"w": wf([SAVE, send("https://hooks.example.com/r")])},
        [
            checkpoint_taken(),
            {
                "expect": {"kind": "RequestApproval", "step": 1},
                "respond": approve("d1"),
            },
            {
                "expect": inv(
                    "send",
                    step=1,
                    inputs={"destination": "https://hooks.example.com/r"},
                ),
                "respond": out(sent=True),
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["checkpoint_consumed", "step_completed"],
        destinations=HOOKS,
    )

    add(
        "destination_policy_on_error",
        "The destination refusal is an F504 a failure mode can match with on_error:"
        " it escalates to the handler (§4.4.2, §5.12).",
        {
            "w": wf(
                [
                    SAVE,
                    send(
                        "https://evil.example.net/x",
                        failure_modes=[
                            {
                                "condition": "the destination is not allowed",
                                "on_error": "F504",
                                "action": "escalate",
                                "recovery": {"goto_step": "page"},
                            }
                        ],
                    ),
                    st(
                        "invoke",
                        "page",
                        handler=True,
                        workflow_id="oncall",
                        input_bindings={
                            "workflow": "oncall",
                            "input": {"why": "a send was refused"},
                        },
                    ),
                ],
                requires=["recovery@1"],
            ),
            "oncall": wf(
                [st("inquire", "q", input_bindings={"ambiguous_input": "${why}"})],
                inputs={"why": {"type": "string", "required": True}},
            ),
        },
        [
            checkpoint_taken(),
            {
                "expect": inv(
                    "inquire",
                    frame=["w", "oncall"],
                    inputs={"ambiguous_input": "a send was refused"},
                ),
                "respond": out(questions=[], ambiguity_analysis={}, confidence=1),
            },
        ],
        {"kind": "Completed", "outcome": "escalated", "cause": "F504"},
        ["step_failed", "failure_mode_fired", "escalated"],
        destinations=HOOKS,
    )

    add(
        "destination_two_policies",
        "Two policies in force: a send must be allowed by each, so a destination"
        " only the wider one allows is refused (§4.4.2).",
        {"w": wf([SAVE, send("https://a.example/y")])},
        [checkpoint_taken()],
        refused(),
        ["step_failed"],
        destinations=[["https://a.example/*"], ["https://a.example/x/*"]],
    )

    add(
        "destination_suffix_url_refused",
        "A suffix pattern names a host or address suffix, not a URL: a URL that"
        " ends with the suffix is refused (§4.4.2).",
        {"w": wf([SAVE, send("https://evil.net/?.example.com")])},
        [checkpoint_taken()],
        refused(),
        ["step_failed"],
        destinations=[["*.example.com"]],
    )

    add(
        "destination_profile_policy_refuses",
        "With no host policy, an applied profile's allowed_destinations alone is in"
        " force: a send it does not allow fails F504 before approval (§4.4.2,"
        " §5.21.3).",
        {"w": wf([SAVE, send("https://evil.example.net/x")])},
        [checkpoint_taken()],
        refused(),
        ["step_failed"],
        profiles=[profile("dest-test", ["https://hooks.example.com/*"])],
    )

    add(
        "profile_destinations_refuse",
        "A profile that allows only mailto: destinations refuses a send to an https"
        " URL (§5.21.3, §4.4.2).",
        {"w": wf([SAVE, send("https://x.example/")])},
        [checkpoint_taken()],
        refused(),
        ["step_failed"],
        profiles=[profile("mail-only", ["mailto:*"])],
    )

    add(
        "profile_destinations_none",
        "An empty allowed_destinations allows no send (§5.21.3, §4.4.2).",
        {"w": wf([SAVE, send("mailto:ops@example.com")])},
        [checkpoint_taken()],
        refused(),
        ["step_failed"],
        profiles=[profile("no-send", [])],
    )


def _rollbacks(add):
    def rollback_catalog(**rollback):
        return {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate(),
                    st(
                        "rollback",
                        "rb",
                        input_bindings={"checkpoint_id": "${cp.checkpoint_id}"},
                        **rollback,
                    ),
                    st("audit", "a", input_bindings={"event": {"what": "rolled back"}}),
                ]
            )
        }

    to_rollback = [
        {"expect": inv("checkpoint", step=0), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain", step=1), "respond": out(compliant=True)},
        {"expect": {"kind": "RequestApproval", "step": 2}, "respond": approve("d1")},
        {"expect": inv("mutate", step=2), "respond": out(success=True)},
        {
            "expect": inv("rollback", step=3, inputs={"checkpoint_id": "cp1"}),
            "respond": out(
                restored=False, unrestored=[{"item": "cfg", "reason": "failed"}]
            ),
        },
    ]

    add(
        "rollback_step_not_restored_completes",
        "A rollback step completes whether or not it restored everything: its"
        " output says restored false, and the run goes on (§4.4.1, as in 1.1).",
        rollback_catalog(),
        [
            *to_rollback,
            {"expect": inv("audit", step=4), "respond": out(recorded=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"rb": {"restored": False}},
        },
        ["step_completed"],
    )

    add(
        "rollback_step_checked",
        "An after-gate on the rollback's restored stops the run when it did not"
        " restore everything (§12.5, Checked Rollback).",
        rollback_catalog(
            gates=[
                {
                    "when": "${rb.restored} == false",
                    "phase": "after",
                    "action": "stop",
                    "message": "The rollback did not restore everything.",
                }
            ]
        ),
        to_rollback,
        {"kind": "Failed", "code": "R403", "step": 3},
        ["gate_fired", "step_failed"],
    )

    add(
        "rolled_back_not_covered",
        "The executor's own rollback after a send: the host restored what the"
        " checkpoint captured and lists the transmission as not covered"
        " (transmitted); the run records it and ends as the failure mode says"
        " (§4.4.1, §4.4.2).",
        {
            "w": wf(
                [
                    SAVE,
                    send(),
                    st(
                        "verify",
                        "v",
                        input_bindings={"conditions": ["delivered"]},
                        failure_modes=[
                            {
                                "condition": "not delivered",
                                "when": "${v.passed} == false",
                                "action": "rollback",
                            }
                        ],
                    ),
                ]
            )
        },
        [
            checkpoint_taken(),
            {
                "expect": {"kind": "RequestApproval", "step": 1},
                "respond": approve("d1"),
            },
            {
                "expect": inv("send", step=1, idempotency_key="run-1:3"),
                "respond": out(sent=True),
            },
            {
                "expect": inv("verify", step=2),
                "respond": out(passed=False, confidence=1),
            },
            {
                "expect": {"kind": "Rollback", "step": 2, "checkpoint_id": "cp1"},
                "respond": {
                    "kind": "RolledBack",
                    "not_covered": [
                        {"item": "send to ops (run-1:3)", "reason": "transmitted"}
                    ],
                },
            },
        ],
        {"kind": "Failed", "code": "R402", "step": 2},
        ["failure_mode_fired", "rolled_back"],
    )

    add(
        "delegate_rollback_own_state",
        "A rollback after a plain delegation restores the delegator's checkpoint"
        " only: the executor sends Rollback for cp1, and the host lists the"
        " delegate's change as not covered (delegated) (§5.15.4).",
        {
            "w": wf(
                [
                    SAVE,
                    st(
                        "delegate",
                        "d",
                        input_bindings={"task": {"fix": "x"}, "agent": "a"},
                    ),
                    st(
                        "verify",
                        "v",
                        input_bindings={"conditions": ["fixed"]},
                        failure_modes=[
                            {
                                "condition": "not fixed",
                                "when": "${v.passed} == false",
                                "action": "rollback",
                            }
                        ],
                    ),
                ]
            )
        },
        [
            checkpoint_taken(),
            {
                "expect": inv("delegate", step=1, idempotency_key="run-1:2"),
                "respond": out(
                    accepted=True, task_id="t1", effective={"checkpointed": True}
                ),
            },
            {
                "expect": inv("verify", step=2),
                "respond": out(passed=False, confidence=1),
            },
            {
                "expect": {"kind": "Rollback", "step": 2, "checkpoint_id": "cp1"},
                "respond": {
                    "kind": "RolledBack",
                    "not_covered": [{"item": "task t1", "reason": "delegated"}],
                },
            },
        ],
        {"kind": "Failed", "code": "R402", "step": 2},
        ["failure_mode_fired", "rolled_back"],
    )


def _memory(add):
    add(
        "persist_stored_false_completes",
        "A persist step whose output says stored false completes: nothing was"
        " written, and the workflow checks stored when it depends on the write"
        " (§4.5).",
        {
            "w": wf(
                [
                    st("persist", "p", input_bindings={"data": {"a": 1}, "key": "k"}),
                    st("recall", "r", input_bindings={"key": "k"}),
                ]
            )
        },
        [
            {"expect": inv("persist", step=0), "respond": out(stored=False)},
            {"expect": inv("recall", step=1), "respond": out(data=None, found=False)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"p": {"stored": False}, "r": {"found": False}},
        },
        ["step_completed"],
    )

    add(
        "persist_scope_echo",
        "A persist step that binds scope session completes when the output's scope"
        " is session (§4.5).",
        memory("persist", "session"),
        [
            {
                "expect": inv("persist", inputs={"scope": "session"}),
                "respond": out(stored=True, key="k", scope="session"),
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["step_completed"],
    )

    add(
        "persist_scope_mismatch",
        "A persist step that binds scope session fails when the output says it"
        " used another scope: R402 with reason unsupported_scope (§4.5).",
        memory("persist", "session"),
        [
            {
                "expect": inv("persist", inputs={"scope": "session"}),
                "respond": out(stored=True, key="k", scope="global"),
            }
        ],
        {"kind": "Failed", "code": "R402", "step": 0, "reason": "unsupported_scope"},
        ["step_failed"],
    )

    add(
        "recall_scope_absent",
        "A recall step that binds scope run gets an output with no scope: the R402"
        " is retried, and the retry's output echoes the scope (§4.5).",
        memory("recall", "run", retry={"max": 1, **NO_RETRY_WAIT}),
        [
            {
                "expect": inv("recall", attempt=1, inputs={"scope": "run"}),
                "respond": out(data=1, found=True),
            },
            {
                "expect": inv("recall", attempt=2, inputs={"scope": "run"}),
                "respond": out(data=1, found=True, scope="run"),
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["retry", "step_completed"],
    )

    add(
        "persist_scope_unbound",
        "A persist step that binds no scope is not checked: an output without"
        " scope completes, as in 1.1 (§4.5).",
        {"w": wf([st("persist", "p", input_bindings={"data": {"a": 1}, "key": "k"})])},
        [{"expect": inv("persist"), "respond": out(stored=True, key="k")}],
        {"kind": "Completed", "outcome": "completed"},
        ["step_completed"],
    )
