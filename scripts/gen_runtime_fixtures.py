"""Generate the runtime conformance fixtures, tests/conformance/runtime/*.json
(design-114 §16.6).

Each fixture is a scripted run of the reference executor: a catalog, inputs,
the actions expected and the responses given, and the expected end and
trace. Edit the fixtures here, not the JSON, then regenerate:

    python scripts/gen_runtime_fixtures.py          # write the fixtures
    python scripts/gen_runtime_fixtures.py --check  # fail if they differ (CI)

Writing also deletes any JSON file in the directory that this script does
not generate, so the directory holds exactly the fixtures defined here.
"""

import argparse
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "conformance" / "runtime"


def st(cap, store, **kw):
    s = {"capability": cap, "purpose": f"{cap} step", "store_as": store}
    s.update(kw)
    return s


def wf(steps, inputs=None, requires=None, **kw):
    w = {"goal": "g", "risk": "high", "spec_version": "1.1", "steps": steps}
    if inputs is not None:
        w["inputs"] = inputs
    if requires:
        w["workflow_extensions"] = {"requires": requires}
    w.update(kw)
    return w


def out(**v):
    v.setdefault("evidence_anchors", [])
    return {"kind": "Output", "value": v}


def inv(cap, **kw):
    e = {"kind": "InvokeCapability", "capability": cap}
    e.update(kw)
    return e


def approve(d, who=("alice",), digest="{{digest}}"):
    return {
        "kind": "Decision",
        "decision_id": d,
        "decision": "approved",
        "approvers": list(who),
        "digest": digest,
    }


CP = st("checkpoint", "cp", input_bindings={"scope": "repo"})


def mutate(store="m", **kw):
    return st(
        "mutate",
        store,
        input_bindings={"target": "config", "operation": {"set": 1}},
        **kw,
    )


POLICY = st(
    "constrain",
    "policy",
    input_bindings={"target": "config", "constraints": ["policy"]},
)

fixtures = {}


def add(
    name,
    description,
    catalog,
    script,
    end,
    trace=(),
    workflow="w",
    inputs=None,
    attendance="attended",
):
    fixtures[name] = {
        "description": description,
        "catalog": catalog,
        "workflow": workflow,
        "inputs": inputs or {},
        "attendance": attendance,
        "start": 0,
        "script": script,
        "end": end,
        "trace_kinds": list(trace),
    }


add(
    "linear_bindings",
    "Bindings resolve to the referenced values; interpolation inside longer strings.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "${topic}"}),
                st(
                    "transform",
                    "t",
                    input_bindings={
                        "input": "${r.data: object}",
                        "target_format": "summary of ${topic}",
                    },
                ),
            ],
            inputs={"topic": {"type": "string", "required": True}},
        )
    },
    [
        {
            "expect": inv("retrieve", step=0, attempt=1, inputs={"target": "rust"}),
            "respond": out(data={"n": 1}, confidence=1),
        },
        {
            "expect": inv(
                "transform",
                step=1,
                inputs={"input": {"n": 1}, "target_format": "summary of rust"},
            ),
            "respond": out(output="s", confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {"r": {"data": {"n": 1}}, "t": {"output": "s"}},
    },
    ["run_started", "step_started", "step_completed", "run_finished"],
    inputs={"topic": "rust"},
)

add(
    "condition_skip",
    "A false condition skips the step; later references to its output read null.",
    {
        "w": wf(
            [
                st(
                    "retrieve",
                    "r",
                    condition="${flag} == true",
                    input_bindings={"target": "x"},
                ),
                st(
                    "transform",
                    "t",
                    input_bindings={"input": "${r.data: object}", "target_format": "f"},
                ),
            ],
            inputs={"flag": {"type": "boolean", "required": True}},
        )
    },
    [
        {
            "expect": inv("transform", step=1, inputs={"input": None}),
            "respond": out(output="s", confidence=1),
        }
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["step_skipped"],
    inputs={"flag": False},
)

add(
    "condition_false_fails",
    "skip_if_false: false turns a false condition into R403.",
    {
        "w": wf(
            [
                st(
                    "retrieve",
                    "r",
                    condition="${flag} == true",
                    skip_if_false=False,
                    input_bindings={"target": "x"},
                )
            ],
            inputs={"flag": {"type": "boolean", "required": True}},
        )
    },
    [],
    {"kind": "Failed", "code": "R403", "step": 0},
    ["step_failed"],
    inputs={"flag": False},
)

add(
    "gate_stop",
    "A before-gate that fires with action stop raises R403.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "y"},
                    gates=[
                        {
                            "when": "${r.confidence} < 0.5",
                            "action": "stop",
                            "message": "low confidence",
                        }
                    ],
                ),
            ]
        )
    },
    [{"expect": inv("retrieve"), "respond": out(data=1, confidence=0.2)}],
    {"kind": "Failed", "code": "R403", "step": 1, "message": "low confidence"},
    ["gate_fired"],
)

add(
    "gate_error_fires",
    "A gate whose expression errors fires (fail-safe); a warn gate lets the step run.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "y"},
                    gates=[{"when": "${r.data: number} > 1", "action": "warn"}],
                ),
            ]
        )
    },
    [
        {"expect": inv("retrieve"), "respond": out(data="text", confidence=1)},
        {"expect": inv("observe"), "respond": out(observation=1, confidence=1)},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["expression_error", "gate_fired"],
)

add(
    "gate_rollback",
    "A rollback gate rolls back to the latest checkpoint, then raises R403.",
    {
        "w": wf(
            [
                CP,
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "y"},
                    gates=[{"when": "true", "action": "rollback"}],
                ),
            ]
        )
    },
    [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {
            "expect": {"kind": "Rollback", "checkpoint_id": "cp1", "step": 1},
            "respond": {"kind": "RolledBack"},
        },
    ],
    {"kind": "Failed", "code": "R403", "step": 1},
    ["gate_fired", "rolled_back"],
)

add(
    "checkpoint_per_mutation",
    "One checkpoint authorises one mutation; the second asks for a new one.",
    {"w": wf([CP, POLICY, mutate("m1"), mutate("m2")])},
    [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 2,
                "mode": "in_session",
                "shown": [{"target": "config", "operation": {"set": 1}}],
            },
            "respond": approve("d1"),
        },
        {"expect": inv("mutate", step=2), "respond": out(success=True)},
        {"expect": {"kind": "RequestApproval", "step": 3}, "respond": approve("d2")},
        {
            "expect": {"kind": "CreateCheckpoint", "step": 3},
            "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
        },
        {"expect": inv("mutate", step=3), "respond": out(success=True)},
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "action_records": [
            {
                "status": "executed",
                "approval": {"decision": "approved", "approvers": ["alice"]},
            },
            {"status": "executed"},
        ],
    },
    [
        "checkpoint_consumed",
        "checkpoint_created",
        "approval_requested",
        "approval_decided",
    ],
)


def approval_case(name, description, decision, end, trace=(), approval=None, extra=()):
    m = mutate()
    requires = None
    if approval is not None:
        m["approval"] = approval
        requires = ["approval@1"]
    add(
        name,
        description,
        {"w": wf([CP, POLICY, m], requires=requires)},
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
            *extra,
            decision,
        ],
        end,
        trace,
    )


approval_case(
    "approval_rejected",
    "A rejected approval is F502 with a rejected record.",
    {
        "expect": {"kind": "RequestApproval"},
        "respond": {
            "kind": "Decision",
            "decision_id": "d1",
            "decision": "rejected",
            "approvers": ["alice"],
            "digest": "{{digest}}",
        },
    },
    {"kind": "Failed", "code": "F502", "action_records": [{"status": "rejected"}]},
)

approval_case(
    "approval_wrong_digest",
    "A decision for other values than were shown is F502.",
    {"expect": {"kind": "RequestApproval"}, "respond": approve("d1", digest="0" * 64)},
    {"kind": "Failed", "code": "F502"},
)

approval_case(
    "approval_min_approvers",
    "Approvers are counted once each against min_approvers.",
    {
        "expect": {
            "kind": "RequestApproval",
            "approver": {"kind": "human", "min_approvers": 2},
        },
        "respond": approve("d1", who=("alice", "alice")),
    },
    {"kind": "Failed", "code": "F502"},
    approval={"approver": {"kind": "human", "min_approvers": 2}},
)

approval_case(
    "approval_expired",
    "No decision before expires: F502 with an expired record.",
    {"tick": 3600001},
    {"kind": "Failed", "code": "F502", "action_records": [{"status": "expired"}]},
    ["approval_expired"],
    approval={"approver": {"kind": "human"}, "expires": "1h"},
    extra=[{"expect": {"kind": "RequestApproval", "expires_at": 3600000}}],
)


def unattended(name, description, plan, end, trace=()):
    m = mutate()
    requires = None
    if plan is not None:
        m["approval"] = {"approver": {"kind": "human"}, "when_unattended": plan}
        requires = ["approval@1"]
    add(
        name,
        description,
        {"w": wf([CP, POLICY, m], requires=requires)},
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
        ],
        end,
        trace,
        attendance="unattended",
    )


unattended(
    "unattended_defer",
    "defer_to_queue records a planned action; the run ends deferred.",
    "defer_to_queue",
    {
        "kind": "Completed",
        "outcome": "deferred",
        "action_records": [{"status": "planned"}],
    },
    ["approval_unattended"],
)
unattended(
    "unattended_skip",
    "skip skips the step that needs approval.",
    "skip",
    {"kind": "Completed", "outcome": "completed"},
    ["step_skipped"],
)
unattended(
    "unattended_fail",
    "Without when_unattended an unattended run fails (F502).",
    None,
    {"kind": "Failed", "code": "F502"},
)


def recheck(name, description, on_change, script_tail, end, trace=()):
    m = mutate()
    m["approval"] = {
        "approver": {"kind": "human"},
        "recheck": {"source": "${p.steps}", "on_change": on_change},
    }
    add(
        name,
        description,
        {
            "w": wf(
                [st("plan", "p", input_bindings={"goal": "g"}), CP, POLICY, m],
                requires=["approval@1"],
            )
        },
        [
            {"expect": inv("plan"), "respond": out(steps=[1], confidence=1)},
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
            {"expect": {"kind": "RequestApproval"}, "respond": approve("d1")},
            {
                "expect": {
                    "kind": "RecheckSource",
                    "source": "${p.steps}",
                    "compare": "digest",
                },
                "respond": {"kind": "Current", "value": [2]},
            },
            *script_tail,
        ],
        end,
        trace,
    )


recheck(
    "recheck_reask",
    "A changed source asks again; the first approval lapses.",
    "reask",
    [
        {
            "expect": {
                "kind": "RequestApproval",
                "shown": [
                    {"target": "config", "operation": {"set": 1}},
                    {"recheck": {"previous": [1], "current": [2]}},
                ],
            },
            "respond": approve("d2"),
        },
        {
            "expect": {"kind": "RecheckSource"},
            "respond": {"kind": "Current", "value": [2]},
        },
        {"expect": inv("mutate"), "respond": out(success=True)},
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "action_records": [{"status": "expired"}, {"status": "executed"}],
    },
    ["recheck"],
)
recheck(
    "recheck_replan",
    "A changed source with on_change: replan ends the run for replanning.",
    "replan",
    [],
    {"kind": "Completed", "outcome": "replan_required"},
)

add(
    "wait_for_event",
    "Events that do not match are dropped; the match is the output, and earlier checkpoints lapse.",
    {
        "w": wf(
            [
                CP,
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    wait={"event_type": "job.done", "correlate": {"job": "${job}"}},
                ),
                POLICY,
                mutate(),
            ],
            inputs={"job": {"type": "string", "required": True}},
            requires=["wait@1"],
        )
    },
    [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {
            "expect": {
                "kind": "AwaitEvent",
                "event_type": "job.done",
                "correlate": {"job": "j1"},
                "deadline": 3600000,
            },
            "respond": {
                "kind": "Event",
                "event": {"event_type": "job.done", "canonical": {"job": "j2"}},
            },
        },
        {
            "expect": {"kind": "AwaitEvent"},
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "job.done",
                    "canonical": {"job": "j1"},
                    "timestamp": "t",
                    "anchors": [],
                },
            },
            "at": 1000,
        },
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {"expect": {"kind": "RequestApproval"}, "respond": approve("d1")},
        {
            "expect": {"kind": "CreateCheckpoint", "step": 3},
            "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
        },
        {"expect": inv("mutate"), "respond": out(success=True)},
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {
            "r": {"data": [{"event_type": "job.done", "canonical": {"job": "j1"}}]}
        },
    },
    ["event_dropped", "event_received", "checkpoints_invalidated"],
    inputs={"job": "j1"},
)

add(
    "wait_timeout",
    "A wait that outlasts its timeout is R401.",
    {
        "w": wf(
            [st("receive", "r", timeout="10s", wait={"event_type": "job.done"})],
            requires=["wait@1"],
        )
    },
    [{"expect": {"kind": "AwaitEvent", "deadline": 10000}}, {"tick": 10001}],
    {"kind": "Failed", "code": "R401"},
)

add(
    "retry_backoff",
    "R402 is retried with exponential backoff, then succeeds.",
    {
        "w": wf(
            [
                st(
                    "retrieve",
                    "r",
                    input_bindings={"target": "x"},
                    retry={"max": 2, "backoff": "exponential"},
                )
            ]
        )
    },
    [
        {
            "expect": inv("retrieve", attempt=1),
            "respond": {"kind": "Error", "code": "R402", "message": "boom"},
        },
        {"expect": {"kind": "Sleep", "until": 1000}},
        {"tick": 1000},
        {
            "expect": inv("retrieve", attempt=2),
            "respond": {"kind": "Error", "code": "R402"},
        },
        {"expect": {"kind": "Sleep", "until": 3000}},
        {"tick": 3000},
        {"expect": inv("retrieve", attempt=3), "respond": out(data=1, confidence=1)},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["retry"],
)

add(
    "late_result",
    "A result after the step's timeout is R401.",
    {"w": wf([st("retrieve", "r", timeout="10s", input_bindings={"target": "x"})])},
    [
        {
            "expect": inv("retrieve", deadline=10000),
            "respond": out(data=1, confidence=1),
            "at": 20000,
        }
    ],
    {"kind": "Failed", "code": "R401"},
)

add(
    "output_contract",
    "An output missing a required field is R402.",
    {"w": wf([st("retrieve", "r", input_bindings={"target": "x"})])},
    [{"expect": inv("retrieve"), "respond": {"kind": "Output", "value": {"data": 1}}}],
    {"kind": "Failed", "code": "R402"},
)

add(
    "recovery_loop_exhausted",
    "A failure mode loops back with injected context, then exhausts (R404).",
    {
        "w": wf(
            [
                st(
                    "plan",
                    "p",
                    input_bindings={
                        "goal": "g",
                        "constraints": {"why": "${_recovery.why: boolean}"},
                    },
                ),
                st(
                    "verify",
                    "v",
                    input_bindings={"conditions": ["ok"]},
                    failure_modes=[
                        {
                            "condition": "verification failed",
                            "action": "request_more_context",
                            "when": "${v.passed} == false",
                            "recovery": {
                                "goto_step": "p",
                                "inject_context": {"why": "${v.passed}"},
                                "max_loops": 1,
                            },
                        }
                    ],
                ),
            ]
        )
    },
    [
        {
            "expect": inv("plan", inputs={"goal": "g", "constraints": {"why": None}}),
            "respond": out(steps=[], confidence=1),
        },
        {"expect": inv("verify"), "respond": out(passed=False, confidence=1)},
        {
            "expect": inv("plan", inputs={"goal": "g", "constraints": {"why": False}}),
            "respond": out(steps=[], confidence=1),
        },
        {"expect": inv("verify"), "respond": out(passed=False, confidence=1)},
    ],
    {"kind": "Failed", "code": "R404"},
    ["failure_mode_fired", "loop", "recovery_exhausted"],
)

add(
    "escalation",
    "An escalation runs the handler as a nested run and ends the run escalated.",
    {
        "w": wf(
            [
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "x"},
                    failure_modes=[
                        {
                            "condition": "observation failed",
                            "action": "escalate",
                            "on_error": "R402",
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
                        "input": {"why": "observe failed"},
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
        {
            "expect": inv("observe", frame=["w"]),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        },
        {
            "expect": inv(
                "inquire",
                frame=["w", "oncall"],
                inputs={"ambiguous_input": "observe failed"},
            ),
            "respond": out(questions=[], ambiguity_analysis={}, confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "escalated",
        "cause": "R402",
        "outputs": {"page": {"result": {"q": {"questions": []}}}},
    },
    ["failure_mode_fired", "escalated", "invoke_started", "invoke_returned"],
)

add(
    "nested_invoke",
    "An invoke step runs its target as a nested run; its outputs are the result.",
    {
        "w": wf(
            [
                st(
                    "invoke",
                    "i",
                    workflow_id="child",
                    input_bindings={
                        "workflow": "child",
                        "input": {"topic": "${topic}"},
                    },
                ),
                st(
                    "transform",
                    "t",
                    input_bindings={"input": "${i.result}", "target_format": "f"},
                ),
            ],
            inputs={"topic": {"type": "string", "required": True}},
        ),
        "child": wf(
            [st("retrieve", "r", input_bindings={"target": "${topic}"})],
            inputs={"topic": {"type": "string", "required": True}},
        ),
    },
    [
        {
            "expect": inv("retrieve", frame=["w", "child"], inputs={"target": "rust"}),
            "respond": out(data=7, confidence=1),
        },
        {
            "expect": inv(
                "transform", frame=["w"], inputs={"input": {"r": {"data": 7}}}
            ),
            "respond": out(output="ok", confidence=1),
        },
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["invoke_started", "invoke_returned"],
    inputs={"topic": "rust"},
)


def quorum_case(
    name,
    description,
    verdicts,
    end,
    trace=("quorum",),
    eff_b=None,
    skip_b=False,
    q=None,
):
    def reviewer(store, agent, family):
        r = st(
            "delegate",
            store,
            input_bindings={
                "task": {"diff": "${diff.data: string}"},
                "agent": agent,
                "fresh_context": True,
                "model_family": family,
                "role": "reviewer",
            },
        )
        if skip_b and store == "rb":
            r["condition"] = '${change} == "never"'
        return r

    add(
        name,
        description,
        {
            "w": wf(
                [
                    st("retrieve", "diff", input_bindings={"target": "${change}"}),
                    reviewer("ra", "a", "claude"),
                    reviewer("rb", "b", "gpt"),
                    st(
                        "receive",
                        "verdicts",
                        input_bindings={"accept_from": ["a", "b"]},
                    ),
                    st(
                        "constrain",
                        "gate",
                        input_bindings={
                            "target": "${verdicts.data}",
                            "constraints": ["two approvals"],
                            "action_on_violation": "block",
                        },
                        quorum={
                            "verdicts": "${verdicts.data}",
                            "reviewers": ["ra", "rb"],
                            "vocabulary": ["approve", "request_changes", "abstain"],
                            "pass_values": ["approve"],
                            "blocking_values": ["request_changes"],
                            "min_pass": 2,
                            "pinned_to": "${change}",
                            "require_fresh_context": True,
                            "require_model_families": ["claude", "gpt"],
                            **(q or {}),
                        },
                    ),
                ],
                inputs={"change": {"type": "string", "required": True}},
                requires=["delegation@1", "quorum@1"],
            )
        },
        [
            {"expect": inv("retrieve"), "respond": out(data="diff text", confidence=1)},
            {
                "expect": inv("delegate", inputs={"agent": "a", "fresh_context": True}),
                "respond": out(
                    accepted=True,
                    effective={"fresh_context": True, "model_family": "claude"},
                ),
            },
            *(
                []
                if skip_b
                else [
                    {
                        "expect": inv("delegate", inputs={"agent": "b"}),
                        "respond": out(
                            accepted=True,
                            effective=eff_b
                            or {"fresh_context": True, "model_family": "gpt"},
                        ),
                    }
                ]
            ),
            {
                "expect": inv("receive", inputs={"accept_from": ["a", "b"]}),
                "respond": out(data=verdicts),
            },
        ],
        end,
        trace,
        inputs={"change": "c1"},
    )


quorum_case(
    "quorum_met",
    "Two pinned approvals from distinct, fresh reviewers on two families.",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
        {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
        {"reviewer_id": "x", "value": "approve", "pinned": "c1"},
        {"reviewer_id": "b", "value": "approve", "pinned": "c1"},
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {
            "gate": {
                "compliant": True,
                "tally": {
                    "passes": 2,
                    "blocks": 0,
                    "abstains": 0,
                    "voters": ["a", "b"],
                },
            }
        },
    },
)
quorum_case(
    "quorum_full_sweep",
    "min_full: one passing verdict must cover the whole change (scope: full); a verdict without a scope is a delta.",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
        {"reviewer_id": "b", "value": "approve", "pinned": "c1", "scope": "full"},
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {
            "gate": {"compliant": True, "tally": {"passes": 2, "full_passes": 1}}
        },
    },
    q={"min_full": 1},
)
quorum_case(
    "quorum_no_full_sweep",
    "Two delta reviews do not meet min_full (F504).",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c1", "scope": "delta"},
        {"reviewer_id": "b", "value": "approve", "pinned": "c1"},
    ],
    {"kind": "Failed", "code": "F504", "step": 4},
    q={"min_full": 1},
)
quorum_case(
    "quorum_full_sweep_abstains",
    "A full sweep counts towards min_full only when it passes (F504).",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
        {"reviewer_id": "b", "value": "abstain", "pinned": "c1", "scope": "full"},
    ],
    {"kind": "Failed", "code": "F504", "step": 4},
    q={"min_full": 1, "min_pass": 1},
)
quorum_case(
    "quorum_bad_scope",
    "A scope that is neither full nor delta counts as a delta: never a full sweep (F504).",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
        {"reviewer_id": "b", "value": "approve", "pinned": "c1", "scope": "Full"},
    ],
    {"kind": "Failed", "code": "F504", "step": 4},
    q={"min_full": 1},
)
quorum_case(
    "quorum_bad_scope_still_blocks",
    "A blocking verdict with an unknown scope still vetoes (F504).",
    [
        {
            "reviewer_id": "a",
            "value": "request_changes",
            "pinned": "c1",
            "scope": "Full",
        },
        {"reviewer_id": "b", "value": "approve", "pinned": "c1", "scope": "full"},
    ],
    {"kind": "Failed", "code": "F504", "step": 4},
    q={"min_pass": 1},
)
quorum_case(
    "quorum_float_counts",
    "min_full written as an integral float counts as an integer: two delta passes are not enough (F504).",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
        {"reviewer_id": "b", "value": "approve", "pinned": "c1"},
    ],
    {"kind": "Failed", "code": "F504", "step": 4},
    q={"min_pass": 2.0, "min_full": 1.0},
)
quorum_case(
    "quorum_float_min_pass",
    "min_pass: 2.0 needs two passes; one pass and one abstention fail (F504).",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c1", "scope": "full"},
        {"reviewer_id": "b", "value": "abstain", "pinned": "c1"},
    ],
    {"kind": "Failed", "code": "F504", "step": 4},
    q={"min_pass": 2.0},
)
quorum_case(
    "quorum_blocked",
    "One blocking verdict vetoes the quorum (F504).",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
        {"reviewer_id": "b", "value": "request_changes", "pinned": "c1"},
    ],
    {"kind": "Failed", "code": "F504", "step": 4},
)
quorum_case(
    "quorum_wrong_pin",
    "Verdicts pinned to something else do not count (F504).",
    [
        {"reviewer_id": "a", "value": "approve", "pinned": "c0"},
        {"reviewer_id": "b", "value": "approve", "pinned": "c1"},
    ],
    {"kind": "Failed", "code": "F504"},
)


add(
    "failure_rollback_loop",
    "A failure mode rolls back, then loops back to the same step, which succeeds.",
    {
        "w": wf(
            [
                CP,
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "y"},
                    failure_modes=[
                        {
                            "condition": "observation failed",
                            "action": "rollback",
                            "on_error": "R402",
                            "recovery": {"goto_step": "o"},
                        }
                    ],
                ),
            ]
        )
    },
    [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("observe"), "respond": {"kind": "Error", "code": "R402"}},
        {
            "expect": {"kind": "Rollback", "checkpoint_id": "cp1"},
            "respond": {"kind": "RolledBack"},
        },
        {"expect": inv("observe"), "respond": out(observation=1, confidence=1)},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["failure_mode_fired", "rolled_back", "loop"],
)

add(
    "pause_and_checkpoint",
    "pause_and_checkpoint takes a checkpoint, then (with no recovery) ends the run.",
    {
        "w": wf(
            [
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "y"},
                    failure_modes=[
                        {
                            "condition": "low confidence",
                            "action": "pause_and_checkpoint",
                            "when": "${o.confidence} < 0.5",
                        }
                    ],
                )
            ]
        )
    },
    [
        {"expect": inv("observe"), "respond": out(observation=1, confidence=0.1)},
        {
            "expect": {"kind": "CreateCheckpoint", "step": 0},
            "respond": {"kind": "Checkpoint", "checkpoint_id": "pause-1"},
        },
    ],
    {"kind": "Failed", "code": "R402"},
    ["failure_mode_fired", "checkpoint_created"],
)

add(
    "exhausted_escalation",
    "An exhausted loop escalates to its on_exhausted handler; the cause is R404.",
    {
        "w": wf(
            [
                st("plan", "p", input_bindings={"goal": "g"}),
                st(
                    "verify",
                    "v",
                    input_bindings={"conditions": ["ok"]},
                    failure_modes=[
                        {
                            "condition": "verification failed",
                            "action": "stop",
                            "when": "${v.passed} == false",
                            "recovery": {
                                "goto_step": "p",
                                "max_loops": 1,
                                "on_exhausted": {"goto_step": "page"},
                            },
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
                        "input": {"why": "verification failed"},
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
        {"expect": inv("plan"), "respond": out(steps=[], confidence=1)},
        {"expect": inv("verify"), "respond": out(passed=False, confidence=1)},
        {"expect": inv("plan"), "respond": out(steps=[], confidence=1)},
        {"expect": inv("verify"), "respond": out(passed=False, confidence=1)},
        {
            "expect": inv("inquire", frame=["w", "oncall"]),
            "respond": out(questions=[], ambiguity_analysis={}, confidence=1),
        },
    ],
    {"kind": "Completed", "outcome": "escalated", "cause": "R404"},
    ["recovery_exhausted", "escalated"],
)

recheck(
    "recheck_stop",
    "A changed source with on_change: stop is F502.",
    "stop",
    [],
    {"kind": "Failed", "code": "F502", "action_records": [{"status": "expired"}]},
)

add(
    "wait_liveness_lost",
    "A source that stops answering ends the wait with R406, not the R401 of a timeout.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    wait={
                        "event_type": "job.done",
                        "liveness": {"mode": "probe", "interval": "1m"},
                    },
                )
            ],
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": {
                "kind": "AwaitEvent",
                "liveness": {"mode": "probe", "interval": "1m"},
            },
            "respond": {"kind": "LivenessLost"},
        }
    ],
    {"kind": "Failed", "code": "R406"},
)


def watched_wait():
    """A wait whose lost liveness is re-checked once (a loop back to the wait
    itself), and whose expiry escalates."""
    return {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    wait={
                        "event_type": "job.done",
                        "liveness": {"mode": "probe", "interval": "1m"},
                    },
                    failure_modes=[
                        {
                            "condition": "the worker went quiet",
                            "on_error": "R406",
                            "action": "request_more_context",
                            "recovery": {
                                "goto_step": "r",
                                "max_loops": 1,
                                "on_exhausted": {"goto_step": "page"},
                            },
                        },
                        {
                            "condition": "the wait expired",
                            "on_error": "R401",
                            "action": "escalate",
                            "recovery": {"goto_step": "page"},
                        },
                    ],
                ),
                st(
                    "invoke",
                    "page",
                    handler=True,
                    workflow_id="oncall",
                    input_bindings={
                        "workflow": "oncall",
                        "input": {"why": "the worker is silent"},
                    },
                ),
            ],
            requires=["wait@1", "recovery@1"],
        ),
        "oncall": wf(
            [st("inquire", "q", input_bindings={"ambiguous_input": "${why}"})],
            inputs={"why": {"type": "string", "required": True}},
        ),
    }


DONE = {
    "kind": "Event",
    "event": {"event_type": "job.done", "canonical": {"job": "j1"}},
}
PAGED = {
    "expect": inv("inquire", frame=["w", "oncall"]),
    "respond": out(questions=[], ambiguity_analysis={}, confidence=1),
}

add(
    "liveness_recheck",
    "Lost liveness (R406) loops back to the wait itself: a re-check, after which the event arrives.",
    watched_wait(),
    [
        {
            "expect": {"kind": "AwaitEvent", "step": 0, "deadline": 3600000},
            "respond": {"kind": "LivenessLost"},
            "at": 60000,
        },
        {
            "expect": {"kind": "AwaitEvent", "step": 0, "deadline": 3660000},
            "respond": DONE,
            "at": 120000,
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {"r": {"data": [{"event_type": "job.done"}]}},
    },
    ["failure_mode_fired", "loop", "event_received"],
)

add(
    "liveness_recheck_exhausted",
    "A worker still silent after its re-check escalates; the cause is R404.",
    watched_wait(),
    [
        {
            "expect": {"kind": "AwaitEvent", "step": 0},
            "respond": {"kind": "LivenessLost"},
            "at": 60000,
        },
        {
            "expect": {"kind": "AwaitEvent", "step": 0},
            "respond": {"kind": "LivenessLost"},
            "at": 120000,
        },
        PAGED,
    ],
    {"kind": "Completed", "outcome": "escalated", "cause": "R404"},
    ["loop", "recovery_exhausted", "escalated"],
)

add(
    "liveness_retry",
    "retry covers R406 as it covers R401 and R402: after the backoff the wait starts again, with a new deadline.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    retry={"max": 1, "backoff": "linear"},
                    wait={
                        "event_type": "job.done",
                        "liveness": {"mode": "push", "interval": "1m"},
                    },
                )
            ],
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": {"kind": "AwaitEvent", "step": 0, "deadline": 3600000},
            "respond": {"kind": "LivenessLost"},
            "at": 60000,
        },
        {"expect": {"kind": "Sleep", "until": 61000}},
        {"tick": 61000},
        {
            "expect": {"kind": "AwaitEvent", "step": 0, "deadline": 3661000},
            "respond": DONE,
            "at": 90000,
        },
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["retry", "event_received"],
)

add(
    "liveness_lost_late",
    "Lost liveness reported after the deadline is R401: the wait had already lapsed, so it escalates rather than re-checking.",
    watched_wait(),
    [
        {
            "expect": {"kind": "AwaitEvent", "step": 0, "deadline": 3600000},
            "respond": {"kind": "LivenessLost"},
            "at": 3600001,
        },
        PAGED,
    ],
    {"kind": "Completed", "outcome": "escalated", "cause": "R401"},
    ["failure_mode_fired", "escalated"],
)

add(
    "liveness_error_code",
    "A host may report lost liveness on a wait as an Error with code R406; it keeps that code.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    wait={
                        "event_type": "job.done",
                        "liveness": {"mode": "probe", "interval": "1m"},
                    },
                )
            ],
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": {"kind": "AwaitEvent", "step": 0},
            "respond": {"kind": "Error", "code": "R406", "message": "probes failed"},
        }
    ],
    {"kind": "Failed", "code": "R406"},
)

add(
    "capability_error_r406",
    "R406 is a wait's code only: a capability call that reports it has failed (R402).",
    {"w": wf([st("retrieve", "r", input_bindings={"target": "x"})])},
    [
        {
            "expect": inv("retrieve"),
            "respond": {"kind": "Error", "code": "R406", "message": "?"},
        }
    ],
    {"kind": "Failed", "code": "R402"},
)

add(
    "wait_expiry_escalates",
    "An expired wait (R401) escalates, unlike lost liveness, which re-checks.",
    watched_wait(),
    [
        {"expect": {"kind": "AwaitEvent", "step": 0, "deadline": 3600000}},
        {"tick": 3600001},
        PAGED,
    ],
    {"kind": "Completed", "outcome": "escalated", "cause": "R401"},
    ["failure_mode_fired", "escalated"],
)

add(
    "decision_reused",
    "A decision can be used once; reusing it is F502.",
    {"w": wf([CP, POLICY, mutate("m1"), mutate("m2")])},
    [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {"expect": {"kind": "RequestApproval", "step": 2}, "respond": approve("d1")},
        {"expect": inv("mutate", step=2), "respond": out(success=True)},
        {"expect": {"kind": "RequestApproval", "step": 3}, "respond": approve("d1")},
    ],
    {
        "kind": "Failed",
        "code": "F502",
        "step": 3,
        "action_records": [{"status": "executed"}, {"status": "rejected"}],
    },
)


def deferred_child():
    m = mutate()
    m["approval"] = {"approver": {"kind": "human"}, "when_unattended": "defer_to_queue"}
    return {
        "w": wf(
            [
                st(
                    "invoke",
                    "i",
                    workflow_id="child",
                    input_bindings={"workflow": "child"},
                ),
                st("observe", "o", input_bindings={"target": "after"}),
                st(
                    "verify",
                    "v",
                    input_bindings={
                        "target": "${i.result: object}",
                        "conditions": ["applied"],
                    },
                ),
            ]
        ),
        "child": wf([CP, POLICY, m], requires=["approval@1"]),
    }


add(
    "deferred_in_child",
    "A nested run that defers some steps defers its invoke step: the parent runs what does not read it, and ends deferred.",
    deferred_child(),
    [
        {
            "expect": inv("checkpoint", frame=["w", "child"]),
            "respond": out(checkpoint_id="cp1"),
        },
        {
            "expect": inv("constrain", frame=["w", "child"]),
            "respond": out(compliant=True),
        },
        {
            "expect": inv("observe", frame=["w"], step=1),
            "respond": out(observation={}, confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "action_records": [{"status": "planned"}],
        "outputs": {"o": {"observation": {}}},
    },
    ["step_deferred"],
    attendance="unattended",
)


def queued_sweep(approval):
    """An unattended sweep: an approved send, an independent observation, and
    two steps that depend on the send, directly and through each other."""
    m = mutate()
    m["approval"] = approval
    return {
        "w": wf(
            [
                CP,
                POLICY,
                m,
                st("observe", "other", input_bindings={"target": "elsewhere"}),
                st(
                    "verify",
                    "v",
                    input_bindings={
                        "target": "${m.success: boolean}",
                        "conditions": ["applied"],
                    },
                ),
                st("explain", "e", input_bindings={"conclusion": "${v.passed}"}),
            ],
            requires=["approval@1"],
        )
    }


SWEEP_START = [
    {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
    {"expect": inv("constrain"), "respond": out(compliant=True)},
]

add(
    "deferral_continues",
    "defer_to_queue defers the step and every step that reads it, directly or transitively; the rest runs, and the run ends deferred.",
    queued_sweep({"approver": {"kind": "human"}, "when_unattended": "defer_to_queue"}),
    SWEEP_START
    + [
        {"expect": inv("observe", step=3), "respond": out(observation={}, confidence=1)}
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "outputs": {"other": {"observation": {}}},
        "action_records": [{"status": "planned"}],
        "deferred": [
            {"frame": ["w"], "step": 2, "store_as": "m"},
            {"step": 4, "store_as": "v", "reason": "it reads 'm', which was deferred"},
            {"step": 5, "store_as": "e", "reason": "it reads 'v', which was deferred"},
        ],
    },
    ["approval_unattended", "step_deferred"],
    attendance="unattended",
)

DEFER = {"approver": {"kind": "human"}, "when_unattended": "defer_to_queue"}


def effects_sweep():
    """After a deferred mutation: a second mutation that reads nothing from
    it, a verify the ontology orders after mutate, an observation gated on
    the deferred output, and read-only steps that do not depend on it."""
    m = mutate()
    m["approval"] = DEFER
    m2 = mutate("m2")
    m2["approval"] = {"approver": {"kind": "human"}}
    return {
        "w": wf(
            [
                CP,
                POLICY,
                m,
                st("observe", "other", input_bindings={"target": "elsewhere"}),
                m2,
                st(
                    "verify",
                    "v",
                    input_bindings={"target": "config", "conditions": ["applied"]},
                ),
                st(
                    "observe",
                    "gated",
                    input_bindings={"target": "x"},
                    gates=[{"when": "${m.success} == false", "action": "warn"}],
                ),
                st("audit", "log", input_bindings={"event": "sweep done"}),
                st("observe", "tail", input_bindings={"target": "elsewhere"}),
            ],
            requires=["approval@1"],
        )
    }


add(
    "deferral_defers_effects",
    "After a deferral, steps that may act on the world (here a second mutate) and steps the ontology orders after a deferred one, transitively (verify after mutate, audit after verify and so after mutate) wait too, as does a step whose gate reads the deferred output; read-only steps that depend on none of them run.",
    effects_sweep(),
    SWEEP_START
    + [
        {
            "expect": inv("observe", step=3),
            "respond": out(observation={}, confidence=1),
        },
        {
            "expect": inv("observe", step=8),
            "respond": out(observation={}, confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "action_records": [
            {"status": "planned"},
            {
                "status": "planned",
                "reason": "it may act on the world, after a deferred step",
            },
        ],
        "deferred": [
            {"step": 2},
            {"step": 4, "reason": "it may act on the world, after a deferred step"},
            {
                "step": 5,
                "reason": "the ontology orders verify after mutate, which was deferred",
            },
            {"step": 6, "reason": "it reads 'm', which was deferred"},
            {
                "step": 7,
                "reason": "the ontology orders audit after mutate, which was deferred",
            },
        ],
    },
    ["step_deferred"],
    attendance="unattended",
)


def looped_sweep():
    m = mutate()
    m["approval"] = DEFER
    return {
        "w": wf(
            [
                st("plan", "p", input_bindings={"goal": "g"}),
                CP,
                POLICY,
                m,
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "elsewhere"},
                    failure_modes=[
                        {
                            "condition": "observation failed",
                            "on_error": "R402",
                            "action": "request_more_context",
                            "recovery": {"goto_step": "p", "max_loops": 1},
                        }
                    ],
                ),
            ],
            requires=["approval@1"],
        )
    }


add(
    "deferral_superseded_by_loop",
    "A recovery loop back over a deferred step runs it again: its earlier planned record is superseded, so the queue holds one action, not two.",
    looped_sweep(),
    [
        {"expect": inv("plan"), "respond": out(steps=[], confidence=1)},
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {
            "expect": inv("observe"),
            "respond": {"kind": "Error", "code": "R402", "message": "flaky"},
        },
        {"expect": inv("plan"), "respond": out(steps=[], confidence=1)},
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp2")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {"expect": inv("observe"), "respond": out(observation={}, confidence=1)},
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "action_records": [
            {
                "status": "rejected",
                "reason": "superseded: a recovery loop ran the step again",
            },
            {"status": "planned"},
        ],
        "deferred": [{"step": 3, "store_as": "m"}],
    },
    ["loop", "step_deferred"],
    attendance="unattended",
)


def escalating_sweep(handler_input):
    """handler_input: the handler's input mapping."""
    m = mutate()
    m["approval"] = DEFER
    return {
        "w": wf(
            [
                CP,
                POLICY,
                m,
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "elsewhere"},
                    failure_modes=[
                        {
                            "condition": "observation failed",
                            "on_error": "R402",
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
                    input_bindings={"workflow": "oncall", "input": handler_input},
                ),
            ],
            requires=["approval@1", "recovery@1"],
        ),
        "oncall": wf(
            [st("inquire", "q", input_bindings={"ambiguous_input": "${why}"})],
            inputs={
                "why": {"type": "string", "required": True},
                "applied": {"type": "boolean"},
            },
        ),
    }


add(
    "deferred_handler",
    "A handler that reads a deferred step's output is deferred too: the run ends deferred, keeping the escalation's cause, not escalated.",
    escalating_sweep({"why": "observation failed", "applied": "${m.success: boolean}"}),
    SWEEP_START
    + [
        {
            "expect": inv("observe", step=3),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        }
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "cause": "R402",
        "deferred": [
            {"step": 2},
            {"step": 4, "reason": "it reads 'm', which was deferred"},
        ],
    },
    ["escalated", "step_deferred"],
    attendance="unattended",
)

add(
    "escalation_after_deferral",
    "A handler is the escalation path: one that does not read a deferred output runs, and the run ends escalated, still listing what it deferred.",
    escalating_sweep({"why": "observation failed"}),
    SWEEP_START
    + [
        {
            "expect": inv("observe", step=3),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        },
        PAGED,
    ],
    {
        "kind": "Completed",
        "outcome": "escalated",
        "cause": "R402",
        "action_records": [{"status": "planned"}],
        "deferred": [{"step": 2, "store_as": "m"}],
    },
    ["escalated", "invoke_started"],
    attendance="unattended",
)

add(
    "failure_after_deferral",
    "A run that fails after deferring keeps the planned records and lists the deferrals.",
    {
        "w": wf(
            [
                CP,
                POLICY,
                dict(mutate(), approval=DEFER),
                st("observe", "o", input_bindings={"target": "elsewhere"}),
            ],
            requires=["approval@1"],
        )
    },
    SWEEP_START
    + [
        {
            "expect": inv("observe", step=3),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        }
    ],
    {
        "kind": "Failed",
        "code": "R402",
        "action_records": [{"status": "planned"}],
        "deferred": [{"step": 2, "store_as": "m"}],
    },
    attendance="unattended",
)

MANDATE = {"kind": "standing_mandate", "mandate_ref": "mandates/nightly-sync"}


def unavailable(d):
    return {
        "kind": "Decision",
        "decision_id": d,
        "decision": "unavailable",
        "approvers": [],
        "digest": "{{digest}}",
    }


add(
    "mandate_unattended",
    "An unattended run still asks a standing mandate; an approval lets the step run.",
    queued_sweep({"approver": MANDATE}),
    SWEEP_START
    + [
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 2,
                "approver": {"kind": "standing_mandate"},
            },
            "respond": approve("d1", who=("mandate",)),
        },
        {"expect": inv("mutate", step=2), "respond": out(success=True)},
        {
            "expect": inv("observe", step=3),
            "respond": out(observation={}, confidence=1),
        },
        {"expect": inv("verify", step=4), "respond": out(passed=True, confidence=1)},
        {
            "expect": inv("explain", step=5),
            "respond": out(explanation="ok", confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "action_records": [
            {
                "status": "executed",
                "approval": {
                    "mandate_ref": "mandates/nightly-sync",
                    "decision": "approved",
                },
            }
        ],
    },
    ["approval_requested", "approval_decided"],
    attendance="unattended",
)

add(
    "mandate_unavailable_defers",
    "When no mandate covers the step, when_unattended applies: here the action is queued, with the unavailable decision on its record.",
    queued_sweep({"approver": MANDATE, "when_unattended": "defer_to_queue"}),
    SWEEP_START
    + [
        {
            "expect": {"kind": "RequestApproval", "step": 2},
            "respond": unavailable("d1"),
        },
        {
            "expect": inv("observe", step=3),
            "respond": out(observation={}, confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "action_records": [
            {"status": "planned", "approval": {"decision": "unavailable"}}
        ],
    },
    ["approval_unattended", "step_deferred"],
    attendance="unattended",
)

add(
    "mandate_unavailable_fails",
    "When no mandate covers the step and there is no plan, the unattended run fails (F502).",
    queued_sweep({"approver": MANDATE}),
    SWEEP_START
    + [
        {"expect": {"kind": "RequestApproval", "step": 2}, "respond": unavailable("d1")}
    ],
    {
        "kind": "Failed",
        "code": "F502",
        "action_records": [
            {"status": "rejected", "approval": {"decision": "unavailable"}}
        ],
    },
    ["approval_unattended"],
    attendance="unattended",
)

add(
    "mandate_unavailable_skips",
    "A mandate that answers unavailable with when_unattended: skip skips the step; a skipped step defers nothing.",
    queued_sweep({"approver": MANDATE, "when_unattended": "skip"}),
    SWEEP_START
    + [
        {
            "expect": {"kind": "RequestApproval", "step": 2},
            "respond": unavailable("d1"),
        },
        {
            "expect": inv("observe", step=3),
            "respond": out(observation={}, confidence=1),
        },
        {"expect": inv("verify", step=4), "respond": out(passed=True, confidence=1)},
        {
            "expect": inv("explain", step=5),
            "respond": out(explanation="ok", confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "action_records": [
            {
                "status": "rejected",
                "reason": "no standing mandate covers the action (when_unattended: skip); the step was skipped",
                "approval": {"decision": "unavailable", "approvers": []},
            }
        ],
        "deferred": [],
    },
    ["approval_unattended", "step_skipped"],
    attendance="unattended",
)


def handler_first(handler_input):
    """The handler is listed before the deferred step it escalates from."""
    m = mutate()
    m["approval"] = DEFER
    return {
        "w": wf(
            [
                CP,
                POLICY,
                st(
                    "invoke",
                    "page",
                    handler=True,
                    workflow_id="oncall",
                    input_bindings={"workflow": "oncall", "input": handler_input},
                ),
                m,
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "elsewhere"},
                    failure_modes=[
                        {
                            "condition": "observation failed",
                            "on_error": "R402",
                            "action": "escalate",
                            "recovery": {"goto_step": "page"},
                        }
                    ],
                ),
            ],
            requires=["approval@1", "recovery@1"],
        ),
        "oncall": wf(
            [st("inquire", "q", input_bindings={"ambiguous_input": "${why}"})],
            inputs={
                "why": {"type": "string", "required": True},
                "applied": {"type": "boolean"},
            },
        ),
    }


add(
    "handler_before_deferral",
    "A handler listed before a deferred step runs on escalation, and its run survives snapshot and restore.",
    handler_first({"why": "observation failed"}),
    SWEEP_START
    + [
        {
            "expect": inv("observe", step=4),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        },
        PAGED,
    ],
    {
        "kind": "Completed",
        "outcome": "escalated",
        "cause": "R402",
        "deferred": [{"step": 3, "store_as": "m"}],
    },
    ["escalated"],
    attendance="unattended",
)

add(
    "deferred_handler_before_deferral",
    "A handler listed before the deferred step it reads is deferred on escalation: the run ends deferred with the cause.",
    handler_first({"why": "observation failed", "applied": "${m.success: boolean}"}),
    SWEEP_START
    + [
        {
            "expect": inv("observe", step=4),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        }
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "cause": "R402",
        "deferred": [
            {"step": 3},
            {"step": 2, "reason": "it reads 'm', which was deferred"},
        ],
    },
    ["escalated", "step_deferred"],
    attendance="unattended",
)


def nested_sweep(parent_steps, retry=None, invoke_approval=None):
    """A parent that invokes a child whose mutate a standing mandate may or
    may not cover (when_unattended: defer_to_queue)."""
    m = mutate()
    m["approval"] = {"approver": MANDATE, "when_unattended": "defer_to_queue"}
    inv_step = st(
        "invoke", "i", workflow_id="child", input_bindings={"workflow": "child"}
    )
    if retry:
        inv_step["retry"] = retry
    if invoke_approval:
        inv_step["requires_approval"] = True
        inv_step["approval"] = invoke_approval
    return {
        "w": wf([inv_step] + parent_steps, requires=["approval@1"]),
        "child": wf(
            [CP, POLICY, m, st("search", "s", input_bindings={"query": "status"})],
            requires=["approval@1"],
        ),
    }


CHILD_START = [
    {
        "expect": inv("checkpoint", frame=["w", "child"]),
        "respond": out(checkpoint_id="cp1"),
    },
    {"expect": inv("constrain", frame=["w", "child"]), "respond": out(compliant=True)},
]

add(
    "invoke_retry_supersedes",
    "A retried invoke runs its workflow again: what the failed attempt deferred is superseded, so the queue does not hold an action that then ran.",
    nested_sweep([], retry={"max": 1, "backoff": "none"}),
    CHILD_START
    + [
        {
            "expect": {"kind": "RequestApproval", "frame": ["w", "child"]},
            "respond": unavailable("d1"),
        },
        {
            "expect": inv("search", frame=["w", "child"]),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        },
    ]
    + CHILD_START
    + [
        {
            "expect": {"kind": "RequestApproval", "frame": ["w", "child"]},
            "respond": approve("d2", who=("mandate",)),
        },
        {"expect": inv("mutate", frame=["w", "child"]), "respond": out(success=True)},
        {
            "expect": inv("search", frame=["w", "child"]),
            "respond": out(results=[], total_count=0, confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "deferred": [],
        "action_records": [
            {
                "status": "rejected",
                "reason": "superseded: the invoke step ran its workflow again",
            },
            {"status": "executed"},
        ],
    },
    ["retry"],
    attendance="unattended",
)

add(
    "nested_deferral_orders_parent",
    "A nested run that defers a mutate defers its invoke step; the invoke, approved and run, stays executed, the nested run's record is the queued action, and a parent verify waits because the ontology orders verify after the mutate deferred below.",
    nested_sweep(
        [
            st(
                "verify",
                "v",
                input_bindings={"target": "config", "conditions": ["applied"]},
            ),
            st("observe", "o", input_bindings={"target": "elsewhere"}),
        ],
        invoke_approval={"approver": MANDATE},
    ),
    [
        {
            "expect": {"kind": "RequestApproval", "frame": ["w"], "step": 0},
            "respond": approve("d0", who=("mandate",)),
        }
    ]
    + CHILD_START
    + [
        {
            "expect": {"kind": "RequestApproval", "frame": ["w", "child"]},
            "respond": unavailable("d1"),
        },
        {
            "expect": inv("search", frame=["w", "child"]),
            "respond": out(results=[], total_count=0, confidence=1),
        },
        {
            "expect": inv("observe", frame=["w"], step=2),
            "respond": out(observation={}, confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "action_records": [
            {
                "status": "executed",
                "reason": "its nested run deferred steps, which are queued separately",
            },
            {"status": "planned"},
        ],
        "deferred": [
            {"frame": ["w", "child"], "step": 2},
            {"frame": ["w"], "step": 0},
            {
                "frame": ["w"],
                "step": 1,
                "reason": "the ontology orders verify after mutate, which was deferred",
            },
        ],
    },
    ["step_deferred"],
    attendance="unattended",
)

add(
    "nested_escalation_with_deferred_handler",
    "A nested run that escalates but defers its handler is an escalated nested run: R402 in the parent.",
    {
        "w": wf(
            [
                st(
                    "invoke",
                    "i",
                    workflow_id="sweep",
                    input_bindings={"workflow": "sweep"},
                )
            ]
        ),
        **{
            ("sweep" if k == "w" else k): v
            for k, v in escalating_sweep(
                {"why": "observation failed", "applied": "${m.success: boolean}"}
            ).items()
        },
    },
    [
        {
            "expect": inv("checkpoint", frame=["w", "sweep"]),
            "respond": out(checkpoint_id="cp1"),
        },
        {
            "expect": inv("constrain", frame=["w", "sweep"]),
            "respond": out(compliant=True),
        },
        {
            "expect": inv("observe", frame=["w", "sweep"]),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        },
    ],
    {"kind": "Failed", "code": "R402"},
    attendance="unattended",
)

add(
    "approver_unavailable_attended",
    "In an attended run an unavailable approver means the step cannot go ahead (F502).",
    queued_sweep({"approver": {"kind": "human"}}),
    SWEEP_START
    + [
        {"expect": {"kind": "RequestApproval", "step": 2}, "respond": unavailable("d1")}
    ],
    {
        "kind": "Failed",
        "code": "F502",
        "action_records": [
            {"status": "rejected", "reason": "the approver was unavailable"}
        ],
    },
)


for implicit in (False, True):
    gate = {
        "when": "${r.confidence} < 0.5",
        "action": "stop",
        "message": "low confidence",
    }
    if not implicit:
        gate["phase"] = "after"
    add(
        "after_gate_implicit" if implicit else "after_gate",
        (
            "A gate without a phase that reads the step's own output runs after it (1.0 form)."
            if implicit
            else "An after-gate reads the step's output; stop is R403, the output is kept."
        ),
        {"w": wf([st("retrieve", "r", input_bindings={"target": "x"}, gates=[gate])])},
        [{"expect": inv("retrieve"), "respond": out(data=1, confidence=0.2)}],
        {"kind": "Failed", "code": "R403", "message": "low confidence"},
        ["step_completed", "gate_fired"],
    )

add(
    "wait_source_and_sender",
    "Events from the wrong source kind or principal are dropped (counted once each); the sender is kept.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    input_bindings={"accept_from": ["a"]},
                    wait={"event_type": "review.verdict", "source_kind": "agent"},
                )
            ],
            requires=["wait@1", "delegation@1"],
        )
    },
    [
        {
            "expect": {
                "kind": "AwaitEvent",
                "source_kind": "agent",
                "accept_from": ["a"],
            },
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.verdict", "source": {"kind": "api"}},
                "principal": "a",
            },
        },
        {
            "expect": {"kind": "AwaitEvent"},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.verdict", "source": {"kind": "agent"}},
                "principal": "b",
            },
        },
        {
            "expect": {"kind": "AwaitEvent"},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.verdict", "source": {"kind": "agent"}},
                "principal": "b",
            },
        },
        {
            "expect": {"kind": "AwaitEvent"},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.verdict", "source": {"kind": "agent"}},
                "principal": "a",
            },
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {"r": {"source": "agent", "data": [{"sender": "a"}]}},
    },
    ["event_dropped", "event_received"],
)

add(
    "synchronize_wait",
    "A synchronize step waits for agreement; the event's state is the agreed state.",
    {
        "w": wf(
            [
                st(
                    "synchronize",
                    "s",
                    timeout="1h",
                    input_bindings={"agents": ["a", "b"], "state": {"v": 1}},
                    wait={"event_type": "state.agreed"},
                )
            ],
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": {"kind": "AwaitEvent", "event_type": "state.agreed"},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "state.agreed", "canonical": {"v": 1}},
            },
        }
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {
            "s": {
                "synchronized": True,
                "agreed_state": {"v": 1},
                "participants": ["a", "b"],
            }
        },
    },
)

add(
    "wait_error",
    "An error from the event source fails the wait (R402).",
    {
        "w": wf(
            [st("receive", "r", timeout="1h", wait={"event_type": "e"})],
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": {"kind": "AwaitEvent"},
            "respond": {"kind": "Error", "code": "boom", "message": "x"},
        }
    ],
    {"kind": "Failed", "code": "R402"},
)


def recheck_version():
    m = mutate()
    m["approval"] = {
        "approver": {"kind": "human"},
        "recheck": {"source": "${p}", "compare": "version", "on_change": "stop"},
    }
    return {
        "w": wf(
            [st("plan", "p", input_bindings={"goal": "g"}), CP, POLICY, m],
            requires=["approval@1"],
        )
    }


add(
    "recheck_version",
    "compare: version ignores changes that keep the version.",
    recheck_version(),
    [
        {"expect": inv("plan"), "respond": out(steps=[1], version=3, confidence=1)},
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {"expect": {"kind": "RequestApproval"}, "respond": approve("d1")},
        {
            "expect": {"kind": "RecheckSource", "compare": "version"},
            "respond": {"kind": "Current", "value": {"steps": [9], "version": 3}},
        },
        {"expect": inv("mutate"), "respond": out(success=True)},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["recheck"],
)

add(
    "expression_errors_are_fail_safe",
    "A condition that errors is false (skip); a failure-mode when that errors does not fire.",
    {
        "w": wf(
            [
                st(
                    "retrieve",
                    "r",
                    input_bindings={"target": "x"},
                    failure_modes=[
                        {
                            "condition": "c",
                            "action": "stop",
                            "when": "${r.data: number} > 1",
                        }
                    ],
                ),
                st(
                    "observe",
                    "o",
                    condition="${r.data: number} > 1",
                    input_bindings={"target": "y"},
                ),
            ]
        )
    },
    [{"expect": inv("retrieve"), "respond": out(data="text", confidence=1)}],
    {"kind": "Completed", "outcome": "completed"},
    ["expression_error", "step_skipped"],
)

add(
    "invoke_timeout",
    "A capability call that outlasts its timeout times out on tick (R401).",
    {"w": wf([st("retrieve", "r", timeout="10s", input_bindings={"target": "x"})])},
    [
        {"expect": inv("retrieve", deadline=10000)},
        {"tick": 10000},
        {"expect": inv("retrieve")},
        {"tick": 10001},
    ],
    {"kind": "Failed", "code": "R401"},
)

add(
    "retry_linear",
    "Linear backoff waits 1 s × the attempt number.",
    {
        "w": wf(
            [
                st(
                    "retrieve",
                    "r",
                    input_bindings={"target": "x"},
                    retry={"max": 1, "backoff": "linear"},
                )
            ]
        )
    },
    [
        {
            "expect": inv("retrieve", attempt=1),
            "respond": {"kind": "Error", "code": "R401"},
        },
        {"expect": {"kind": "Sleep", "until": 1000}},
        {"tick": 1000},
        {"expect": inv("retrieve", attempt=2), "respond": out(data=1, confidence=1)},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["retry"],
)

add(
    "child_failure_retried",
    "A failed nested run is the invoke step's R402, retried by the parent.",
    {
        "w": wf(
            [
                st(
                    "invoke",
                    "i",
                    workflow_id="child",
                    retry={"max": 1},
                    input_bindings={"workflow": "child"},
                )
            ]
        ),
        "child": wf([st("retrieve", "r", input_bindings={"target": "x"})]),
    },
    [
        {
            "expect": inv("retrieve", frame=["w", "child"]),
            "respond": {"kind": "Error", "code": "R402"},
        },
        {
            "expect": inv("retrieve", frame=["w", "child"]),
            "respond": out(data=1, confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {"i": {"steps_executed": ["r"]}},
    },
    ["retry", "invoke_returned"],
)

add(
    "handler_failure",
    "A handler that fails ends the run failed, not escalated.",
    {
        "w": wf(
            [
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "x"},
                    failure_modes=[
                        {
                            "condition": "c",
                            "action": "escalate",
                            "on_error": "R402",
                            "recovery": {"goto_step": "page"},
                        }
                    ],
                ),
                st(
                    "invoke",
                    "page",
                    handler=True,
                    workflow_id="oncall",
                    input_bindings={"workflow": "oncall"},
                ),
            ],
            requires=["recovery@1"],
        ),
        "oncall": wf([st("inquire", "q", input_bindings={"ambiguous_input": "x"})]),
    },
    [
        {"expect": inv("observe"), "respond": {"kind": "Error", "code": "R402"}},
        {
            "expect": inv("inquire"),
            "respond": {"kind": "Error", "code": "R402", "message": "pager down"},
        },
    ],
    {"kind": "Failed", "code": "R402"},
    ["escalated"],
)

add(
    "invoke_input_mismatch",
    "A nested run missing a required input fails the invoke step (R402). The input is computed, so only the executor can check it.",
    {
        "w": wf(
            [
                st(
                    "invoke",
                    "i",
                    workflow_id="child",
                    input_bindings={"workflow": "child", "input": "${payload}"},
                )
            ],
            inputs={"payload": {"type": "object", "required": True}},
        ),
        "child": wf(
            [st("retrieve", "r", input_bindings={"target": "${topic}"})],
            inputs={"topic": {"type": "string", "required": True}},
        ),
    },
    [],
    {"kind": "Failed", "code": "R402"},
    inputs={"payload": {}},
)

add(
    "checkpoint_error",
    "A checkpoint that cannot be taken fails the step (F501).",
    {"w": wf([CP, POLICY, mutate("m1"), mutate("m2")])},
    [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {"expect": {"kind": "RequestApproval", "step": 2}, "respond": approve("d1")},
        {"expect": inv("mutate", step=2), "respond": out(success=True)},
        {"expect": {"kind": "RequestApproval", "step": 3}, "respond": approve("d2")},
        {
            "expect": {"kind": "CreateCheckpoint", "step": 3},
            "respond": {"kind": "Error", "code": "F501", "message": "disk full"},
        },
    ],
    {
        "kind": "Failed",
        "code": "F501",
        "action_records": [{"status": "executed"}, {"status": "failed"}],
    },
)

add(
    "rollback_error",
    "A rollback that fails ends the run (F503).",
    {
        "w": wf(
            [
                CP,
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "y"},
                    gates=[{"when": "true", "action": "rollback"}],
                ),
            ]
        )
    },
    [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {
            "expect": {"kind": "Rollback"},
            "respond": {"kind": "Error", "code": "F503", "message": "gone"},
        },
    ],
    {"kind": "Failed", "code": "F503"},
)


def recheck_err():
    m = mutate()
    m["approval"] = {"approver": {"kind": "human"}, "recheck": {"source": "${p.steps}"}}
    return {
        "w": wf(
            [st("plan", "p", input_bindings={"goal": "g"}), CP, POLICY, m],
            requires=["approval@1"],
        )
    }


add(
    "recheck_error",
    "A source that cannot be re-read stops the step (F502).",
    recheck_err(),
    [
        {"expect": inv("plan"), "respond": out(steps=[1], confidence=1)},
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {"expect": {"kind": "RequestApproval"}, "respond": approve("d1")},
        {
            "expect": {"kind": "RecheckSource"},
            "respond": {"kind": "Error", "code": "R402"},
        },
    ],
    {"kind": "Failed", "code": "F502"},
)


def shows():
    m = mutate()
    m["approval"] = {
        "approver": {"kind": "standing_mandate", "mandate_ref": "mandates/nightly"},
        "mode": "out_of_band",
        "shows": ["${p.steps}"],
    }
    return {
        "w": wf(
            [st("plan", "p", input_bindings={"goal": "g"}), CP, POLICY, m],
            requires=["approval@1"],
        )
    }


add(
    "approval_shows",
    "shows decides what the approver sees, and the digest binds to it.",
    shows(),
    [
        {"expect": inv("plan"), "respond": out(steps=["a", "b"], confidence=1)},
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {
            "expect": {
                "kind": "RequestApproval",
                "mode": "out_of_band",
                "shown": [["a", "b"]],
                "approver": {
                    "kind": "standing_mandate",
                    "mandate_ref": "mandates/nightly",
                },
            },
            "respond": approve("d1", who=("mandates/nightly",)),
        },
        {"expect": inv("mutate"), "respond": out(success=True)},
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "action_records": [
            {
                "status": "executed",
                "approval": {"mode": "out_of_band", "mandate_ref": "mandates/nightly"},
            }
        ],
    },
)

BOTH = [
    {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
    {"reviewer_id": "b", "value": "approve", "pinned": "c1"},
]
quorum_case(
    "quorum_not_fresh",
    "A reviewer that did not run fresh does not count (F504).",
    BOTH,
    {"kind": "Failed", "code": "F504"},
    eff_b={"fresh_context": False, "model_family": "gpt"},
)
quorum_case(
    "quorum_missing_family",
    "Counted reviewers must cover the required families (F504).",
    BOTH,
    {"kind": "Failed", "code": "F504"},
    eff_b={"fresh_context": True, "model_family": "claude"},
)
quorum_case(
    "quorum_skipped_reviewer",
    "A reviewer whose step never ran does not count (F504).",
    BOTH,
    {"kind": "Failed", "code": "F504"},
    skip_b=True,
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the fixtures on disk differ"
    )
    check = parser.parse_args(argv).check
    rendered = {
        f"{name}.json": json.dumps(f, indent=2) + "\n" for name, f in fixtures.items()
    }
    on_disk = {p.name: p.read_text() for p in OUT.glob("*.json")}
    stale = sorted(n for n in rendered if on_disk.get(n) != rendered[n])
    extra = sorted(set(on_disk) - set(rendered))
    if check:
        for n in stale:
            print(f"out of date: {OUT / n}")
        for n in extra:
            print(f"not generated by this script: {OUT / n}")
        if stale or extra:
            print("run: python scripts/gen_runtime_fixtures.py")
            return 1
        print(f"{len(rendered)} runtime fixtures up to date")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n in stale:
        (OUT / n).write_text(rendered[n])
    for n in extra:
        (OUT / n).unlink()
    print(f"{len(rendered)} fixtures ({len(stale)} written, {len(extra)} removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
