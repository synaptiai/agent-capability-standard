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
import copy
import json
import sys
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "conformance" / "runtime"


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
    actor_identity=None,
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
    if actor_identity is not None:
        fixtures[name]["actor_identity"] = actor_identity


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
    "condition_membership",
    "`in` tests list membership and map keys; an `in` gate whose right operand"
    " is a string errors and so fires.",
    {
        "w": wf(
            [
                st(
                    "retrieve",
                    "r",
                    condition='"urgent" in ${labels}',
                    input_bindings={"target": "x"},
                ),
                st(
                    "observe",
                    "o",
                    condition='"high" in ${severity}',
                    input_bindings={"target": "y"},
                ),
                st(
                    "search",
                    "s",
                    input_bindings={"query": "z"},
                    gates=[
                        {"when": '"a" in ${r.data: array<string>}', "action": "warn"}
                    ],
                ),
            ],
            inputs={
                "labels": {"type": "array", "required": True},
                "severity": {"type": "object", "required": True},
            },
        )
    },
    [
        {"expect": inv("retrieve", step=0), "respond": out(data="text", confidence=1)},
        {"expect": inv("search", step=2), "respond": out(results=[], confidence=1)},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["step_skipped", "expression_error", "gate_fired"],
    inputs={"labels": ["urgent", "infra"], "severity": {"low": 1}},
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
                st("audit", "log", input_bindings={"event": {"type": "sweep_done"}}),
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
    "gate_skip",
    "A before-gate with action skip skips the step; later steps run and read null.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "y"},
                    gates=[{"when": "${r.data} == 0", "action": "skip"}],
                ),
                st("search", "s", input_bindings={"query": "${o.observation}"}),
            ]
        )
    },
    [
        {"expect": inv("retrieve"), "respond": out(data=0, confidence=1)},
        {
            "expect": inv("search", step=2, inputs={"query": None}),
            "respond": out(results=[], confidence=1),
        },
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["gate_fired", "step_skipped"],
)

add(
    "after_gate_and_failure_mode",
    "An after-gate's R403 goes to the step's failure modes: a rollback gate and"
    " a rollback failure mode on the same condition roll back twice (§5.6).",
    {
        "w": wf(
            [
                CP,
                st(
                    "verify",
                    "v",
                    input_bindings={"target": "t", "conditions": ["ok"]},
                    gates=[
                        {
                            "when": "${v.passed} == false",
                            "phase": "after",
                            "action": "rollback",
                        }
                    ],
                    failure_modes=[
                        {
                            "condition": "verification failed",
                            "when": "${v.passed} == false",
                            "action": "rollback",
                        }
                    ],
                ),
            ]
        )
    },
    [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("verify"), "respond": out(passed=False, confidence=1)},
        {
            "expect": {"kind": "Rollback", "checkpoint_id": "cp1", "step": 1},
            "respond": {"kind": "RolledBack"},
        },
        {
            "expect": {"kind": "Rollback", "checkpoint_id": "cp1", "step": 1},
            "respond": {"kind": "RolledBack"},
        },
    ],
    {"kind": "Failed", "code": "R403", "step": 1},
    ["gate_fired", "rolled_back", "failure_mode_fired", "rolled_back"],
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

OWNER = {
    "principal": "dana",
    "kind": "human",
    "authenticated_by": "session_id",
    "trust_class": "owner",
}
PEER = {
    "principal": "agent-7",
    "kind": "agent",
    "authenticated_by": "session_id",
    "trust_class": "peer_agent",
}
OUTSIDER = {
    "principal": "mail:someone@example.com",
    "kind": "human",
    "authenticated_by": "x-mail-dkim",
    "trust_class": "external",
}


def verdict_event(identity=None, principal=None):
    r = {"kind": "Event", "event": {"event_type": "answer"}}
    if principal is not None:
        r["principal"] = principal
    if identity is not None:
        r["identity"] = identity
    return r


add(
    "identity_sender_check",
    "sender_check and accept_trust_classes drop items whose sender identity is missing,"
    " was authenticated otherwise, or is of another class (counted per reason); a kept"
    " item carries its sender and sender_identity, and the principal defaults to the"
    " identity's.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    input_bindings={
                        "sender_check": ["session_id"],
                        "accept_trust_classes": ["owner", "decision_person"],
                    },
                    wait={"event_type": "answer"},
                )
            ],
            requires=["wait@1", "identity@1"],
        )
    },
    [
        {
            "expect": {
                "kind": "AwaitEvent",
                "sender_check": ["session_id"],
                "accept_trust_classes": ["owner", "decision_person"],
            },
            "respond": verdict_event(principal="dana"),
        },
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(OUTSIDER)},
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(PEER)},
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(OWNER)},
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {"r": {"data": [{"sender": "dana", "sender_identity": OWNER}]}},
    },
    ["event_dropped", "event_received"],
)

add(
    "identity_synchronize",
    "A synchronize wait records the identity that delivered the agreed state.",
    {
        "w": wf(
            [
                st(
                    "synchronize",
                    "s",
                    timeout="1h",
                    input_bindings={
                        "agents": ["a", "b"],
                        "state": {"v": 1},
                        "accept_trust_classes": ["peer_agent"],
                    },
                    wait={"event_type": "state.agreed"},
                )
            ],
            requires=["wait@1", "identity@1"],
        )
    },
    [
        {
            "expect": {"kind": "AwaitEvent", "accept_trust_classes": ["peer_agent"]},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "state.agreed", "canonical": {"v": 1}},
                "principal": "agent-7",
                "identity": PEER,
            },
        }
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {"s": {"sender": "agent-7", "sender_identity": PEER}},
    },
    ["event_received"],
)

OPS_MANDATE = {"kind": "standing_mandate", "mandate_ref": "mandates/ops"}


def always_ask_catalog(when_unattended=None):
    """An answer from anyone; a summary of it; an action on the summary and an
    action on something else, both covered by a standing mandate."""
    approval = {"approver": OPS_MANDATE}
    if when_unattended:
        approval["when_unattended"] = when_unattended
    return {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    input_bindings={"always_ask_trust_classes": ["external"]},
                    wait={"event_type": "answer"},
                ),
                st(
                    "generate",
                    "g",
                    input_bindings={"specification": "${r.data: array<object>}"},
                ),
                st(
                    "execute",
                    "routine",
                    input_bindings={"code": "rotate-logs"},
                    approval=approval,
                ),
                st(
                    "execute",
                    "act",
                    input_bindings={"code": "${g.content: string}"},
                    approval=approval,
                ),
            ],
            requires=["wait@1", "identity@1", "approval@1"],
        )
    }


AGENT = {"principal": "orchestrator", "kind": "agent", "model_family": "claude"}

add(
    "always_ask_overrides_mandate",
    "An action on an item from an always-ask trust class, here through a generate"
    " step, is asked of a person despite its standing mandate; an action that uses"
    " no such item still uses the mandate. Action records carry the run's actor"
    " identity.",
    always_ask_catalog(),
    [
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(OUTSIDER)},
        {
            "expect": inv("generate", step=1),
            "respond": out(content="restart web", confidence=1),
        },
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 2,
                "approver": OPS_MANDATE,
            },
            "respond": approve("d1", who=("mandate",)),
        },
        {"expect": inv("execute", step=2), "respond": out(result="ok")},
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 3,
                "approver": {"kind": "human", "always_ask": True},
            },
            "respond": approve("d2", who=("dana",)),
        },
        {"expect": inv("execute", step=3), "respond": out(result="ok")},
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "action_records": [
            {
                "status": "executed",
                "actor": "agent",
                "actor_identity": AGENT,
                "approval": {"mandate_ref": "mandates/ops", "approvers": ["mandate"]},
            },
            {
                "status": "executed",
                "actor": "agent",
                "actor_identity": AGENT,
                "always_ask": True,
                "approval": {"mandate_ref": None, "approvers": ["dana"]},
            },
        ],
    },
    ["always_ask", "approval_requested"],
    actor_identity=AGENT,
)

add(
    "always_ask_unattended",
    "Unattended, the action that uses no always-ask item is approved by its mandate;"
    " the one on an external item follows when_unattended (here, queued).",
    always_ask_catalog("defer_to_queue"),
    [
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(OUTSIDER)},
        {
            "expect": inv("generate", step=1),
            "respond": out(content="restart web", confidence=1),
        },
        {
            "expect": {"kind": "RequestApproval", "step": 2, "approver": OPS_MANDATE},
            "respond": approve("d1", who=("mandate",)),
        },
        {"expect": inv("execute", step=2), "respond": out(result="ok")},
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "action_records": [
            {"status": "executed"},
            {"status": "planned", "always_ask": True},
        ],
        "deferred": [{"step": 3, "store_as": "act"}],
    },
    ["always_ask", "approval_unattended", "step_deferred"],
    attendance="unattended",
)

add(
    "always_ask_unmarked_item",
    "An item from a class that is not always-ask leaves the mandate in force.",
    always_ask_catalog(),
    [
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(OWNER)},
        {
            "expect": inv("generate", step=1),
            "respond": out(content="restart web", confidence=1),
        },
        {
            "expect": {"kind": "RequestApproval", "step": 2, "approver": OPS_MANDATE},
            "respond": approve("d1", who=("mandate",)),
        },
        {"expect": inv("execute", step=2), "respond": out(result="ok")},
        {
            "expect": {"kind": "RequestApproval", "step": 3, "approver": OPS_MANDATE},
            "respond": approve("d2", who=("mandate",)),
        },
        {"expect": inv("execute", step=3), "respond": out(result="ok")},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["approval_requested"],
)

add(
    "always_ask_through_invoke",
    "The mark crosses an invoke: a nested run given an always-ask item asks a person"
    " for its own mandate-covered action.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    input_bindings={"always_ask_trust_classes": ["external"]},
                    wait={"event_type": "answer"},
                ),
                st(
                    "invoke",
                    "child",
                    input_bindings={
                        "workflow": "act_on",
                        "input": {"answer": "${r.data: array<object>}"},
                    },
                ),
            ],
            requires=["wait@1", "identity@1"],
        ),
        "act_on": wf(
            [
                st(
                    "execute",
                    "act",
                    input_bindings={"code": "apply"},
                    condition="${answer} != null",
                    approval={"approver": OPS_MANDATE},
                )
            ],
            inputs={"answer": {"type": "array", "required": True}},
            requires=["approval@1"],
        ),
    },
    [
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(OUTSIDER)},
        {
            "expect": {
                "kind": "RequestApproval",
                "frame": ["w", "act_on"],
                "approver": {"kind": "human", "always_ask": True},
            },
            "respond": approve("d1", who=("dana",)),
        },
        {"expect": inv("execute", frame=["w", "act_on"]), "respond": out(result="ok")},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["always_ask", "invoke_started", "invoke_returned"],
)

NO_CLASS = {"principal": "relay", "kind": "service"}

add(
    "always_ask_fails_closed",
    "With always_ask_trust_classes bound, an item with no identity, or whose"
    " identity has no trust class, counts as always-ask.",
    always_ask_catalog(),
    [
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(NO_CLASS)},
        {
            "expect": inv("generate", step=1),
            "respond": out(content="restart web", confidence=1),
        },
        {
            "expect": {"kind": "RequestApproval", "step": 2, "approver": OPS_MANDATE},
            "respond": approve("d1", who=("mandate",)),
        },
        {"expect": inv("execute", step=2), "respond": out(result="ok")},
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 3,
                "approver": {"kind": "human", "always_ask": True},
            },
            "respond": approve("d2", who=("dana",)),
        },
        {"expect": inv("execute", step=3), "respond": out(result="ok")},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["always_ask"],
)

add(
    "always_ask_through_recovery",
    "Context a recovery loop injects from an always-ask item is marked: the"
    " step it loops back to is asked of a person the second time.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    input_bindings={"always_ask_trust_classes": ["external"]},
                    wait={"event_type": "answer"},
                ),
                st(
                    "execute",
                    "act",
                    input_bindings={"code": "${_recovery.hint: string}"},
                    approval={"approver": OPS_MANDATE},
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
                                "goto_step": "act",
                                "inject_context": {"hint": "${r.data: array<object>}"},
                                "max_loops": 1,
                            },
                        }
                    ],
                ),
            ],
            requires=["wait@1", "identity@1", "approval@1"],
        )
    },
    [
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(OUTSIDER)},
        {
            "expect": {"kind": "RequestApproval", "step": 1, "approver": OPS_MANDATE},
            "respond": approve("d1", who=("mandate",)),
        },
        {"expect": inv("execute", step=1), "respond": out(result="ok")},
        {"expect": inv("verify", step=2), "respond": out(passed=False, confidence=1)},
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 1,
                "approver": {"kind": "human", "always_ask": True},
            },
            "respond": approve("d2", who=("dana",)),
        },
        {"expect": inv("execute", step=1), "respond": out(result="ok")},
        {"expect": inv("verify", step=2), "respond": out(passed=True, confidence=1)},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["loop", "always_ask"],
)

add(
    "always_ask_invoke_condition",
    "An invoke marked only by its condition marks every step of its nested run.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    input_bindings={"always_ask_trust_classes": ["external"]},
                    wait={"event_type": "answer"},
                ),
                st(
                    "invoke",
                    "child",
                    condition="${r.data: array<object>} != []",
                    input_bindings={"workflow": "act_now", "input": {}},
                ),
            ],
            requires=["wait@1", "identity@1"],
        ),
        "act_now": wf(
            [
                st(
                    "execute",
                    "act",
                    input_bindings={"code": "apply"},
                    approval={"approver": OPS_MANDATE},
                )
            ],
            requires=["approval@1"],
        ),
    },
    [
        {"expect": {"kind": "AwaitEvent"}, "respond": verdict_event(OUTSIDER)},
        {
            "expect": {
                "kind": "RequestApproval",
                "frame": ["w", "act_now"],
                "approver": {"kind": "human", "always_ask": True},
            },
            "respond": approve("d1", who=("dana",)),
        },
        {"expect": inv("execute", frame=["w", "act_now"]), "respond": out(result="ok")},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["always_ask"],
)

add(
    "identity_input_unresolved",
    "An identity@1 input whose reference resolves to something that is not a"
    " list of known values fails the step (R402) rather than turning the check"
    " off.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    input_bindings={"accept_trust_classes": "${classes}"},
                    wait={"event_type": "answer"},
                )
            ],
            inputs={"classes": {"type": "array", "items": {"type": "string"}}},
            requires=["wait@1", "identity@1"],
        )
    },
    [],
    {"kind": "Failed", "code": "R402", "step": 0},
    ["step_failed"],
)


def waiting_reviewer(store, agent, read_only=True):
    """A reviewer delegated and then awaited in one step (wait on delegate):
    a retry delegates again, so a reviewer that hangs is replaced alone."""
    return st(
        "delegate",
        store,
        timeout="2h",
        retry={"max": 1, "backoff": "none"},
        input_bindings={
            "task": {"review": "${change}"},
            "agent": agent,
            "read_only": read_only,
        },
        wait={
            "event_type": "review.done",
            "liveness": {"mode": "push", "interval": "10m", "failure_threshold": 3},
        },
    )


def waiting_quorum(read_only_b=True):
    return {
        "w": wf(
            [
                waiting_reviewer("ra", "a"),
                waiting_reviewer("rb", "b", read_only=read_only_b),
                st(
                    "constrain",
                    "gate",
                    input_bindings={
                        "target": "${change}",
                        "constraints": ["two approvals"],
                        "action_on_violation": "block",
                    },
                    quorum={
                        "verdicts": ["${ra.result: object}", "${rb.result: object}"],
                        "reviewers": ["ra", "rb"],
                        "vocabulary": ["approve", "request_changes"],
                        "pass_values": ["approve"],
                        "blocking_values": ["request_changes"],
                        "min_pass": 2,
                        "pinned_to": "${change}",
                        "require_read_only": True,
                    },
                ),
            ],
            inputs={"change": {"type": "string", "required": True}},
            requires=["wait@1", "delegation@1", "quorum@1"],
        )
    }


def delegated(task, agent, read_only=True):
    return out(
        accepted=True, task_id=task, agent=agent, effective={"read_only": read_only}
    )


def review_done(task, agent):
    return {
        "kind": "Event",
        "event": {
            "event_type": "review.done",
            "task_id": task,
            "reviewer_id": agent,
            "value": "approve",
            "pinned": "c1",
        },
        "principal": agent,
    }


add(
    "delegate_wait_replaces_hung_reviewer",
    "A delegate step that waits delegates, then awaits that delegation's result"
    " (correlated by task_id). When reviewer b goes silent (R406), its retry"
    " delegates again; reviewer a is not asked again, and the quorum counts both"
    " results.",
    waiting_quorum(),
    [
        {
            "expect": inv("delegate", step=0, attempt=1, inputs={"read_only": True}),
            "respond": delegated("t1", "a"),
        },
        {
            "expect": {"kind": "AwaitEvent", "step": 0, "correlate": {"task_id": "t1"}},
            "respond": review_done("t1", "a"),
        },
        {"expect": inv("delegate", step=1, attempt=1), "respond": delegated("t2", "b")},
        {
            "expect": {"kind": "AwaitEvent", "step": 1, "correlate": {"task_id": "t2"}},
            "respond": {"kind": "LivenessLost"},
        },
        {
            "expect": inv("delegate", step=1, attempt=2, replaces="t2"),
            "respond": delegated("t3", "b"),
        },
        {
            "expect": {"kind": "AwaitEvent", "step": 1, "correlate": {"task_id": "t3"}},
            "respond": review_done("t3", "b"),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {
            "ra": {"task_id": "t1", "result": {"reviewer_id": "a", "sender": "a"}},
            "rb": {"task_id": "t3", "result": {"reviewer_id": "b"}},
            "gate": {"compliant": True, "tally": {"passes": 2, "voters": ["a", "b"]}},
        },
    },
    ["delegated", "retry", "event_received", "quorum"],
    inputs={"change": "c1"},
)

add(
    "delegate_wait_not_accepted",
    "A delegation the host did not accept is an R402, retried like any other:"
    " the step delegates again before it waits.",
    {
        "w": wf(
            [
                st(
                    "delegate",
                    "ra",
                    timeout="2h",
                    retry={"max": 1, "backoff": "none"},
                    input_bindings={"task": {"review": "x"}, "agent": "a"},
                    wait={"event_type": "review.done"},
                )
            ],
            requires=["wait@1"],
        )
    },
    [
        {"expect": inv("delegate", attempt=1), "respond": out(accepted=False)},
        {
            "expect": inv("delegate", attempt=2),
            "respond": out(accepted=True, task_id="t9"),
        },
        {
            "expect": {"kind": "AwaitEvent", "correlate": {"task_id": "t9"}},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.done", "task_id": "t9"},
            },
        },
    ],
    {"kind": "Completed", "outcome": "completed", "outputs": {"ra": {"task_id": "t9"}}},
    ["retry", "delegated"],
)

add(
    "quorum_requires_read_only",
    "With require_read_only, a verdict from a reviewer the host did not attest"
    " read-only is not counted: the quorum fails (F504).",
    waiting_quorum(),
    [
        {"expect": inv("delegate", step=0), "respond": delegated("t1", "a")},
        {
            "expect": {"kind": "AwaitEvent", "step": 0},
            "respond": review_done("t1", "a"),
        },
        {
            "expect": inv("delegate", step=1),
            "respond": delegated("t2", "b", read_only=False),
        },
        {
            "expect": {"kind": "AwaitEvent", "step": 1},
            "respond": review_done("t2", "b"),
        },
    ],
    {"kind": "Failed", "code": "F504", "step": 2},
    ["quorum", "step_failed"],
    inputs={"change": "c1"},
)

add(
    "delegate_wait_one_timeout",
    "One timeout bounds the delegation and the wait: a delegation that answers"
    " after 50 minutes leaves 10 minutes of a 1h timeout to wait.",
    {
        "w": wf(
            [
                st(
                    "delegate",
                    "ra",
                    timeout="1h",
                    input_bindings={"task": {"review": "x"}, "agent": "a"},
                    wait={"event_type": "review.done"},
                )
            ],
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": inv("delegate", deadline=3_600_000),
            "at": 3_000_000,
            "respond": out(accepted=True, task_id="t1"),
        },
        {
            "expect": {"kind": "AwaitEvent", "deadline": 3_600_000},
            "at": 4_000_000,
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.done", "task_id": "t1"},
            },
        },
    ],
    {"kind": "Failed", "code": "R401", "step": 0},
    ["delegated", "step_failed"],
)

add(
    "delegate_wait_needs_task_id",
    "A delegation the step waits on must return a task_id to match its result (R402).",
    {
        "w": wf(
            [
                st(
                    "delegate",
                    "ra",
                    timeout="1h",
                    input_bindings={"task": {"review": "x"}, "agent": "a"},
                    wait={"event_type": "review.done"},
                )
            ],
            requires=["wait@1"],
        )
    },
    [{"expect": inv("delegate"), "respond": out(accepted=True)}],
    {"kind": "Failed", "code": "R402", "step": 0},
    ["step_failed"],
)

add(
    "quorum_result_names_another_reviewer",
    "A verdict read from a reviewer step's result is that reviewer's: one that"
    " names another reviewer is not counted.",
    waiting_quorum(),
    [
        {"expect": inv("delegate", step=0), "respond": delegated("t1", "a")},
        {
            "expect": {"kind": "AwaitEvent", "step": 0},
            "respond": review_done("t1", "b"),
        },
        # Each result claims to be the other reviewer's: neither counts.
        {"expect": inv("delegate", step=1), "respond": delegated("t2", "b")},
        {
            "expect": {"kind": "AwaitEvent", "step": 1},
            "respond": review_done("t2", "a"),
        },
    ],
    {
        "kind": "Failed",
        "code": "F504",
        "step": 2,
    },
    ["quorum", "step_failed"],
    inputs={"change": "c1"},
)

add(
    "quorum_single_result",
    "verdicts may be one reference to a single verdict, such as one reviewer's result.",
    {
        "w": wf(
            [
                waiting_reviewer("ra", "a"),
                st(
                    "constrain",
                    "gate",
                    input_bindings={
                        "target": "${change}",
                        "constraints": ["one approval"],
                        "action_on_violation": "block",
                    },
                    quorum={
                        "verdicts": "${ra.result: object}",
                        "reviewers": ["ra"],
                        "vocabulary": ["approve", "request_changes"],
                        "pass_values": ["approve"],
                        "min_pass": 1,
                        "pinned_to": "${change}",
                    },
                ),
            ],
            inputs={"change": {"type": "string", "required": True}},
            requires=["wait@1", "delegation@1", "quorum@1"],
        )
    },
    [
        {"expect": inv("delegate", step=0), "respond": delegated("t1", "a")},
        {
            "expect": {"kind": "AwaitEvent", "step": 0},
            "respond": review_done("t1", "a"),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {"gate": {"compliant": True, "tally": {"passes": 1}}},
    },
    ["quorum"],
    inputs={"change": "c1"},
)

add(
    "always_ask_delegate_result",
    "A waiting delegate's result from an always-ask class marks what uses it.",
    {
        "w": wf(
            [
                st(
                    "delegate",
                    "ask",
                    timeout="1h",
                    input_bindings={
                        "task": {"question": "which host?"},
                        "agent": "helper",
                        "always_ask_trust_classes": ["external"],
                    },
                    wait={"event_type": "answer"},
                ),
                st(
                    "execute",
                    "act",
                    input_bindings={"code": "${ask.result.answer: string}"},
                    approval={"approver": OPS_MANDATE},
                ),
            ],
            requires=["wait@1", "identity@1", "approval@1"],
        )
    },
    [
        {"expect": inv("delegate"), "respond": out(accepted=True, task_id="t1")},
        {
            "expect": {"kind": "AwaitEvent", "correlate": {"task_id": "t1"}},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "answer", "task_id": "t1"},
                "identity": OUTSIDER,
            },
        },
        {
            "expect": {
                "kind": "RequestApproval",
                "approver": {"kind": "human", "always_ask": True},
            },
            "respond": approve("d1", who=("dana",)),
        },
        {"expect": inv("execute"), "respond": out(result="ok")},
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["always_ask"],
)

add(
    "wait_correlate_key_order",
    "An event that fails several correlate keys is dropped for the first key in"
    " sorted order, so a restored run reports the same reason.",
    {
        "w": wf(
            [
                st(
                    "receive",
                    "r",
                    timeout="1h",
                    wait={
                        "event_type": "done",
                        "correlate": {"zz": "${z}", "aa": "${a}"},
                    },
                )
            ],
            inputs={
                "z": {"type": "string", "required": True},
                "a": {"type": "string", "required": True},
            },
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": {"kind": "AwaitEvent", "correlate": {"zz": "1", "aa": "2"}},
            "respond": {"kind": "Event", "event": {"event_type": "done"}},
        },
        {
            "expect": {"kind": "AwaitEvent"},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "done", "zz": "1", "aa": "2"},
            },
        },
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["event_dropped", "event_received"],
    inputs={"z": "1", "a": "2"},
)

add(
    "delegate_loop_replaces",
    "A recovery loop back to a waiting delegate delegates again and names the"
    " delegation it replaces, as a retry does.",
    {
        "w": wf(
            [
                st(
                    "delegate",
                    "ra",
                    timeout="2h",
                    input_bindings={"task": {"review": "x"}, "agent": "a"},
                    wait={
                        "event_type": "review.done",
                        "liveness": {"mode": "push", "interval": "10m"},
                    },
                    failure_modes=[
                        {
                            "condition": "The reviewer went silent.",
                            "on_error": "R406",
                            "action": "request_more_context",
                            "recovery": {"goto_step": "ra", "max_loops": 1},
                        }
                    ],
                )
            ],
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": inv("delegate", attempt=1),
            "respond": out(accepted=True, task_id="t1"),
        },
        {"expect": {"kind": "AwaitEvent"}, "respond": {"kind": "LivenessLost"}},
        {
            "expect": inv("delegate", replaces="t1"),
            "respond": out(accepted=True, task_id="t2"),
        },
        {
            "expect": {"kind": "AwaitEvent", "correlate": {"task_id": "t2"}},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.done", "task_id": "t2"},
            },
        },
    ],
    {"kind": "Completed", "outcome": "completed", "outputs": {"ra": {"task_id": "t2"}}},
    ["loop", "delegated"],
)

add(
    "delegate_loop_from_earlier_step",
    "A recovery loop to a step before a waiting delegate runs the delegate again,"
    " naming the delegation it replaces; the steps in between do not take it.",
    {
        "w": wf(
            [
                st("plan", "p", input_bindings={"goal": "review x"}),
                st(
                    "delegate",
                    "ra",
                    timeout="2h",
                    input_bindings={"task": {"review": "x"}, "agent": "a"},
                    wait={
                        "event_type": "review.done",
                        "liveness": {"mode": "push", "interval": "10m"},
                    },
                    failure_modes=[
                        {
                            "condition": "The reviewer went silent.",
                            "on_error": "R406",
                            "action": "request_more_context",
                            "recovery": {"goto_step": "p", "max_loops": 1},
                        }
                    ],
                ),
            ],
            requires=["wait@1"],
        )
    },
    [
        {"expect": inv("plan"), "respond": out(steps=[], confidence=1)},
        {
            "expect": inv("delegate", attempt=1),
            "respond": out(accepted=True, task_id="t1"),
        },
        {"expect": {"kind": "AwaitEvent"}, "respond": {"kind": "LivenessLost"}},
        {"expect": inv("plan"), "respond": out(steps=[], confidence=1)},
        {
            "expect": inv("delegate", replaces="t1"),
            "respond": out(accepted=True, task_id="t2"),
        },
        {
            "expect": {"kind": "AwaitEvent", "correlate": {"task_id": "t2"}},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.done", "task_id": "t2"},
            },
        },
    ],
    {"kind": "Completed", "outcome": "completed", "outputs": {"ra": {"task_id": "t2"}}},
    ["loop", "delegated"],
)

add(
    "delegate_loop_after_failed_redelegation",
    "When a retry's re-delegation fails and a recovery loop delegates again,"
    " the new delegation still names the one it replaces.",
    {
        "w": wf(
            [
                st(
                    "delegate",
                    "ra",
                    timeout="2h",
                    retry={"max": 1},
                    input_bindings={"task": {"review": "x"}, "agent": "a"},
                    wait={
                        "event_type": "review.done",
                        "liveness": {"mode": "push", "interval": "10m"},
                    },
                    failure_modes=[
                        {
                            "condition": "The replacement could not be delegated.",
                            "on_error": "R402",
                            "action": "request_more_context",
                            "recovery": {"goto_step": "ra", "max_loops": 1},
                        }
                    ],
                )
            ],
            requires=["wait@1"],
        )
    },
    [
        {
            "expect": inv("delegate", attempt=1),
            "respond": out(accepted=True, task_id="t1"),
        },
        {"expect": {"kind": "AwaitEvent"}, "respond": {"kind": "LivenessLost"}},
        {
            "expect": inv("delegate", attempt=2, replaces="t1"),
            "respond": {"kind": "Error", "code": "R402", "message": "busy"},
        },
        {
            "expect": inv("delegate", replaces="t1"),
            "respond": out(accepted=True, task_id="t3"),
        },
        {
            "expect": {"kind": "AwaitEvent", "correlate": {"task_id": "t3"}},
            "respond": {
                "kind": "Event",
                "event": {"event_type": "review.done", "task_id": "t3"},
            },
        },
    ],
    {"kind": "Completed", "outcome": "completed", "outputs": {"ra": {"task_id": "t3"}}},
    ["retry", "failure_mode_fired", "loop", "delegated"],
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


# ---------------------------------------------------------------------------
# H4 (#114 findings): gate `end`, `delay`, fail-fast wait filters and
# `after_deferral`.
# ---------------------------------------------------------------------------

END_GATE = {"when": "${r.data} == 0", "action": "end", "message": "nothing to do"}

add(
    "gate_end_before",
    "A before-gate with action end ends the run successfully: the step and every later one are not run, and the end records which step ended it.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st("observe", "o", input_bindings={"target": "y"}, gates=[END_GATE]),
                st("search", "s", input_bindings={"query": "z"}),
            ]
        )
    },
    [{"expect": inv("retrieve", step=0), "respond": out(data=0, confidence=1)}],
    {
        "kind": "Completed",
        "outcome": "completed",
        "ended": {"step": 1, "message": "nothing to do"},
        "outputs": {"r": {"data": 0}},
    },
    ["gate_fired", "run_ended"],
)

add(
    "gate_end_after",
    "An after-gate with action end keeps the step's output and ends the run; later steps are not run.",
    {
        "w": wf(
            [
                st(
                    "retrieve",
                    "r",
                    input_bindings={"target": "x"},
                    gates=[dict(END_GATE, phase="after")],
                ),
                st("observe", "o", input_bindings={"target": "y"}),
            ]
        )
    },
    [{"expect": inv("retrieve", step=0), "respond": out(data=0, confidence=1)}],
    {
        "kind": "Completed",
        "outcome": "completed",
        "ended": {"step": 0, "message": "nothing to do"},
        "outputs": {"r": {"data": 0}},
    },
    ["step_completed", "gate_fired", "run_ended"],
)

add(
    "gate_end_nested",
    "An end gate in an invoked workflow ends that run only: the invoke step completes with its stores and the caller goes on.",
    {
        "w": wf(
            [
                st(
                    "invoke",
                    "i",
                    workflow_id="child",
                    input_bindings={"workflow": "child", "input": {}},
                ),
                st("search", "s", input_bindings={"query": "z"}),
            ]
        ),
        "child": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st("observe", "o", input_bindings={"target": "y"}, gates=[END_GATE]),
            ]
        ),
    },
    [
        {
            "expect": inv("retrieve", step=0, frame=["w", "child"]),
            "respond": out(data=0, confidence=1),
        },
        {
            "expect": inv("search", step=1, frame=["w"]),
            "respond": out(results=[], confidence=1),
        },
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {"i": {"result": {"r": {"data": 0}}, "steps_executed": ["r"]}},
    },
    ["run_ended", "invoke_returned"],
)

add(
    "delay_waits",
    "A delay sleeps before the step; like a wait it invalidates the checkpoint taken before it, so the later mutation needs a new one.",
    {
        "w": wf(
            [
                CP,
                st("observe", "o", input_bindings={"target": "y"}, delay="1m"),
                POLICY,
                mutate("m"),
            ],
            requires=["wait@1"],
        )
    },
    [
        {"expect": inv("checkpoint", step=0), "respond": out(checkpoint_id="cp1")},
        {"expect": {"kind": "Sleep", "until": 60_000}},
        {"tick": 60_000},
        {
            "expect": inv("observe", step=1),
            "respond": out(observation={}, confidence=1),
        },
        {"expect": inv("constrain", step=2), "respond": out(compliant=True)},
        {"expect": {"kind": "RequestApproval", "step": 3}, "respond": approve("d1")},
        {
            "expect": {"kind": "CreateCheckpoint", "step": 3},
            "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
        },
        {"expect": inv("mutate", step=3), "respond": out(success=True)},
    ],
    {"kind": "Completed", "outcome": "completed"},
    [
        "delay_started",
        "delay_finished",
        "checkpoints_invalidated",
        "checkpoint_created",
    ],
)

add(
    "wait_accept_from_empty",
    "An accept_from that resolves to an empty list fails the step (R402) at once, instead of dropping every sender until the timeout.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st(
                    "receive",
                    "inbox",
                    timeout="1h",
                    input_bindings={"accept_from": "${r.data: array<string>}"},
                    wait={"event_type": "answer"},
                ),
            ],
            requires=["wait@1", "delegation@1"],
        )
    },
    [{"expect": inv("retrieve", step=0), "respond": out(data=[], confidence=1)}],
    {"kind": "Failed", "code": "R402", "step": 1},
    ["step_failed"],
)

add(
    "wait_correlate_null",
    "A correlate value that resolves to null fails the step (R402): it would match every event that lacks the key.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st(
                    "receive",
                    "inbox",
                    timeout="1h",
                    wait={"event_type": "answer", "correlate": {"job": "${r.data}"}},
                ),
            ],
            requires=["wait@1"],
        )
    },
    [{"expect": inv("retrieve", step=0), "respond": out(data=None, confidence=1)}],
    {"kind": "Failed", "code": "R402", "step": 1},
    ["step_failed"],
)

add(
    "wait_correlate_null_delegate",
    "A waiting delegate whose correlate resolves to null fails before it delegates: nothing is sent and then abandoned.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st(
                    "delegate",
                    "d",
                    timeout="1h",
                    input_bindings={"task": {"t": 1}, "agent": "a"},
                    wait={"event_type": "done", "correlate": {"ticket": "${r.data}"}},
                ),
            ],
            requires=["wait@1"],
        )
    },
    [{"expect": inv("retrieve", step=0), "respond": out(data=None, confidence=1)}],
    {"kind": "Failed", "code": "R402", "step": 1},
    ["step_failed"],
)

add(
    "receive_accept_from_empty",
    "A receive that does not wait still fails (R402) when its accept_from resolves to an empty list: the host would drop every sender.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st(
                    "receive",
                    "inbox",
                    input_bindings={"accept_from": "${r.data: array<string>}"},
                ),
            ],
            requires=["delegation@1"],
        )
    },
    [{"expect": inv("retrieve", step=0), "respond": out(data=[], confidence=1)}],
    {"kind": "Failed", "code": "R402", "step": 1},
    ["step_failed"],
)

add(
    "gate_end_failure_mode_wins",
    "An after-gate end waits for the step's failure modes: one whose when holds fires instead (here it rolls back), so the run does not end as a success.",
    {
        "w": wf(
            [
                CP,
                POLICY,
                mutate("m"),
                st(
                    "verify",
                    "v",
                    input_bindings={"target": "config", "conditions": ["applied"]},
                    gates=[
                        {
                            "when": "${v.confidence} < 0.5",
                            "phase": "after",
                            "action": "end",
                            "message": "unsure; stop here",
                        }
                    ],
                    failure_modes=[
                        {
                            "condition": "verification failed",
                            "when": "${v.passed} == false",
                            "action": "rollback",
                        }
                    ],
                ),
            ]
        )
    },
    [
        *SWEEP_START,
        {"expect": {"kind": "RequestApproval", "step": 2}, "respond": approve("d1")},
        {"expect": inv("mutate", step=2), "respond": out(success=True)},
        {
            "expect": inv("verify", step=3),
            "respond": out(passed=False, confidence=0.3),
        },
        {
            "expect": {"kind": "Rollback", "checkpoint_id": "cp1", "step": 3},
            "respond": {"kind": "RolledBack"},
        },
    ],
    {"kind": "Failed", "code": "R402", "step": 3},
    ["gate_fired", "failure_mode_fired", "rolled_back"],
)

add(
    "gate_end_error_does_not_fire",
    "An end gate whose expression errors (R405) does not fire, unlike other gates: it would report the run a success. The run goes on.",
    {
        "w": wf(
            [
                st("retrieve", "r", input_bindings={"target": "x"}),
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "y"},
                    gates=[{"when": "${r.data: number} < 1", "action": "end"}],
                ),
            ]
        )
    },
    [
        {"expect": inv("retrieve", step=0), "respond": out(data="oops", confidence=1)},
        {
            "expect": inv("observe", step=1),
            "respond": out(observation={}, confidence=1),
        },
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["expression_error"],
)

add(
    "gate_end_while_escalated",
    "An end gate in a handler ends the run escalated, as the handler's own end would, with the cause and the ending step recorded.",
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
                    input_bindings={"workflow": "oncall", "input": {}},
                    gates=[
                        {"when": "true", "action": "end", "message": "on-call is paged"}
                    ],
                ),
            ],
            requires=["recovery@1"],
        ),
        "oncall": wf([st("inquire", "q", input_bindings={"ambiguous_input": "x"})]),
    },
    [
        {
            "expect": inv("observe", step=0),
            "respond": {"kind": "Error", "code": "R402", "message": "down"},
        },
    ],
    {
        "kind": "Completed",
        "outcome": "escalated",
        "cause": "R402",
        "ended": {"step": 1, "message": "on-call is paged"},
    },
    ["escalated", "run_ended"],
)

add(
    "gate_end_after_deferral",
    "An end gate after a deferral ends the run deferred: the queued action still waits.",
    {
        "w": wf(
            [
                CP,
                POLICY,
                dict(mutate("m"), approval=DEFER),
                st(
                    "observe",
                    "o",
                    input_bindings={"target": "elsewhere"},
                    gates=[
                        {"when": "true", "action": "end", "message": "done for now"}
                    ],
                ),
                st("search", "s", input_bindings={"query": "z"}),
            ],
            requires=["approval@1"],
        )
    },
    SWEEP_START,
    {
        "kind": "Completed",
        "outcome": "deferred",
        "ended": {"step": 3, "message": "done for now"},
        "deferred": [{"step": 2}],
    },
    ["step_deferred", "run_ended"],
    attendance="unattended",
)

add(
    "after_deferral_precedes",
    "after_deferral: run also lifts the ordering rule: a verify the ontology orders after a deferred mutate runs.",
    {
        "w": wf(
            [
                CP,
                POLICY,
                dict(mutate("m"), approval=DEFER),
                st(
                    "verify",
                    "v",
                    input_bindings={"target": "config", "conditions": ["unchanged"]},
                    after_deferral="run",
                ),
            ],
            requires=["approval@1"],
        )
    },
    SWEEP_START
    + [{"expect": inv("verify", step=3), "respond": out(passed=True, confidence=1)}],
    {"kind": "Completed", "outcome": "deferred", "deferred": [{"step": 2}]},
    ["step_deferred"],
    attendance="unattended",
)


def after_deferral_sweep():
    """A deferred mutation, then: a delegation that opted out of dependent
    deferral, one that did not, and an observation that opted out but reads
    the deferred output."""
    m = mutate()
    m["approval"] = DEFER

    def delegate(store, **kw):
        return st(
            "delegate", store, input_bindings={"task": {"t": 1}, "agent": "a"}, **kw
        )

    return {
        "w": wf(
            [
                CP,
                POLICY,
                m,
                delegate("independent", after_deferral="run"),
                delegate("dependent"),
                st(
                    "observe",
                    "reader",
                    input_bindings={"target": "x"},
                    gates=[{"when": "${m.success} == false", "action": "warn"}],
                    after_deferral="run",
                ),
            ],
            requires=["approval@1"],
        )
    }


add(
    "after_deferral_runs",
    "after_deferral: run lets a step that acts on the world run after a deferral; a step without it is deferred, and so is one that opted out but reads the deferred output.",
    after_deferral_sweep(),
    SWEEP_START
    + [
        {
            "expect": inv("delegate", step=3),
            "respond": out(accepted=True, task_id="t1"),
        }
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "deferred": [
            {"step": 2},
            {"step": 4, "reason": "it may act on the world, after a deferred step"},
            {"step": 5, "reason": "it reads 'm', which was deferred"},
        ],
    },
    ["step_deferred"],
    attendance="unattended",
)


# ---------------------------------------------------------------------------
# The orchestrator port (#114): scripted runs of the workflows in
# tests/fixtures/pass_orchestrator_port.workflow_catalog.yaml, as contributed.
# Each fixture carries the workflow and every workflow it invokes. A host
# output is the capability's required fields with placeholder values, plus
# what the scenario sets: what matters is the path the run takes.
# ---------------------------------------------------------------------------

ORCHESTRATOR = (
    ROOT / "tests" / "fixtures" / "pass_orchestrator_port.workflow_catalog.yaml"
)
PLACEHOLDER = {
    "string": "x",
    "number": 1.0,
    "integer": 1,
    "boolean": True,
    "array": [],
    "object": {},
}


@cache
def orchestrator_catalog():
    return yaml.safe_load(ORCHESTRATOR.read_text())


@cache
def required_outputs():
    """Each capability's required output fields with placeholder values
    (`any` fields are null)."""
    ontology = yaml.safe_load(
        (ROOT / "schemas" / "capability_ontology.yaml").read_text()
    )
    out = {}
    for node in ontology["nodes"]:
        schema = node.get("output_schema", {})
        props = schema.get("properties", {})
        fields = {}
        for name in schema.get("required", []):
            t = props.get(name, {}).get("type")
            t = t.split("|")[0] if isinstance(t, str) else t
            if t != "any" and t not in PLACEHOLDER:
                raise ValueError(f"{node['id']}.{name}: no placeholder for type {t!r}")
            fields[name] = PLACEHOLDER.get(t)
        out[node["id"]] = fields
    return out


def orch_value(cap, over=None):
    v = copy.deepcopy(required_outputs()[cap])
    v["evidence_anchors"] = []
    v.update(over or {})
    return v


def orch_steps(frame, *steps):
    """Capability calls of one run (`frame`, outermost first): each is
    (step, capability) or (step, capability, {output fields})."""
    entries = []
    for step, cap, *over in steps:
        expect = inv(cap, step=step, frame=list(frame))
        entries.append(
            {
                "expect": expect,
                "respond": {"kind": "Output", "value": orch_value(cap, *over)},
            }
        )
    return entries


def orch_closure(workflow):
    """`workflow` and every workflow it invokes, directly or not."""
    catalog = orchestrator_catalog()
    found, todo = {}, [workflow]
    while todo:
        name = todo.pop()
        if name in found:
            continue
        found[name] = catalog[name]
        for step in catalog[name]["steps"]:
            target = step.get("workflow_id") or (step.get("input_bindings") or {}).get(
                "workflow"
            )
            if step.get("capability") == "invoke" and target in catalog:
                todo.append(target)
    return {name: catalog[name] for name in catalog if name in found}


def orchestrator(name, description, workflow, script, end, trace, **kw):
    add(
        name,
        description,
        orch_closure(workflow),
        script,
        end,
        trace,
        workflow=workflow,
        **kw,
    )


orchestrator(
    "orchestrator_intake_delegates",
    "Intake routes a compliant item to delegate_to_thread, which runs nested: a report from another session is dropped and the thread's own is kept; asking the owner is skipped.",
    "intake_triage",
    [
        *orch_steps(
            ["intake_triage"],
            (0, "receive"),
            (1, "retrieve"),
            (2, "transform"),
            (3, "classify"),
            (4, "classify"),
            (5, "search"),
            (6, "constrain", {"compliant": True}),
            (7, "plan"),
            (8, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (9, "persist"),
        ),
        *orch_steps(
            ["intake_triage", "delegate_to_thread"],
            (0, "retrieve"),
            (1, "search"),
            (2, "compare"),
            (3, "decompose"),
            (4, "plan"),
            (5, "constrain"),
            (6, "generate"),
            (7, "constrain"),
            (8, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (9, "delegate", {"accepted": True, "task_id": "th-1"}),
            (10, "persist"),
            (11, "observe"),
        ),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["intake_triage", "delegate_to_thread"],
                "event_type": "thread.turn_end",
                "correlate": {"task_id": "th-1"},
                "accept_from": ["th-1"],
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "thread.turn_end",
                    "source": {"kind": "agent"},
                    "task_id": "th-1",
                },
                "principal": "intruder",
            },
        },
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["intake_triage", "delegate_to_thread"],
                "event_type": "thread.turn_end",
                "correlate": {"task_id": "th-1"},
                "accept_from": ["th-1"],
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "thread.turn_end",
                    "source": {"kind": "agent"},
                    "task_id": "th-1",
                },
                "principal": "th-1",
            },
        },
        *orch_steps(
            ["intake_triage", "delegate_to_thread"],
            (13, "ground"),
            (14, "verify"),
            (15, "persist"),
            (16, "audit"),
        ),
        *orch_steps(["intake_triage"], (12, "verify"), (13, "audit")),
    ],
    {"kind": "Completed", "outcome": "completed"},
    [
        "invoke_started",
        "invoke_returned",
        "event_dropped",
        "event_received",
        "step_skipped",
    ],
    inputs={
        "event": {"event_type": "intake.item", "source": {"kind": "human"}},
        "profile": {"owner_id": "owner"},
    },
)

orchestrator(
    "orchestrator_delegate_liveness",
    "A thread that stops answering liveness probes (R406) gets a checkpoint, a fresh liveness check and a second wait, which its report ends.",
    "delegate_to_thread",
    [
        *orch_steps(
            ["delegate_to_thread"],
            (0, "retrieve"),
            (1, "search"),
            (2, "compare"),
            (3, "decompose"),
            (4, "plan"),
            (5, "constrain"),
            (6, "generate"),
            (7, "constrain"),
            (8, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (9, "delegate", {"accepted": True, "task_id": "th-1"}),
            (10, "persist"),
            (11, "observe"),
        ),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["delegate_to_thread"],
                "event_type": "thread.turn_end",
                "correlate": {"task_id": "th-1"},
                "accept_from": ["th-1"],
            },
            "respond": {"kind": "LivenessLost"},
        },
        {
            "expect": {
                "kind": "CreateCheckpoint",
                "step": 12,
                "frame": ["delegate_to_thread"],
            },
            "respond": {"kind": "Checkpoint", "checkpoint_id": "cp1"},
        },
        *orch_steps(["delegate_to_thread"], (11, "observe")),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["delegate_to_thread"],
                "event_type": "thread.turn_end",
                "correlate": {"task_id": "th-1"},
                "accept_from": ["th-1"],
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "thread.turn_end",
                    "source": {"kind": "agent"},
                    "task_id": "th-1",
                },
                "principal": "th-1",
            },
        },
        *orch_steps(
            ["delegate_to_thread"],
            (13, "ground"),
            (14, "verify"),
            (15, "persist"),
            (16, "audit"),
        ),
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["failure_mode_fired", "loop", "event_received"],
    inputs={"task": {"id": "T-7", "goal": "fix the flaky test"}},
)

orchestrator(
    "orchestrator_review_blessed",
    "Two fresh reviewers of different families both bless the pinned head: the verdict post is approved under the mandate after a recheck, and the quorum passes.",
    "review_gate",
    [
        *orch_steps(
            ["review_gate"],
            (0, "observe", {"observation": {"head_sha": "abc123"}}),
            (1, "retrieve"),
            (2, "classify"),
            (3, "plan"),
            (4, "constrain", {"compliant": True}),
            (5, "generate"),
            (6, "generate"),
            (7, "constrain", {"compliant": True}),
            (8, "checkpoint", {"checkpoint_id": "cp-worktree_ckpt_out"}),
            (
                9,
                "delegate",
                {
                    "accepted": True,
                    "task_id": "rv-a",
                    "effective": {"fresh_context": True, "model_family": "family_a"},
                },
            ),
            (
                10,
                "delegate",
                {
                    "accepted": True,
                    "task_id": "rv-b",
                    "effective": {"fresh_context": True, "model_family": "family_b"},
                },
            ),
        ),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 11,
                "frame": ["review_gate"],
                "event_type": "thread.turn_end",
                "correlate": {"head_sha": "abc123"},
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "thread.turn_end",
                    "source": {"kind": "agent"},
                    "head_sha": "abc123",
                },
                "principal": "peer",
            },
        },
        *orch_steps(
            ["review_gate"],
            (
                12,
                "receive",
                {
                    "data": [
                        {
                            "reviewer_id": "reviewer-a",
                            "value": "BLESSED",
                            "pinned": "abc123",
                            "scope": "full",
                        },
                        {
                            "reviewer_id": "reviewer-b",
                            "value": "BLESSED",
                            "pinned": "abc123",
                            "scope": "full",
                        },
                    ]
                },
            ),
            (13, "classify"),
            (14, "critique"),
            (15, "constrain", {"compliant": True}),
            (16, "checkpoint", {"checkpoint_id": "cp-post_ckpt_out"}),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 17,
                "frame": ["review_gate"],
                "approver": {"kind": "standing_mandate", "mandate_ref": "mandates"},
            },
            "respond": approve("d1", who=("mandate",)),
        },
        {
            "expect": {"kind": "RecheckSource", "step": 17, "frame": ["review_gate"]},
            "respond": {
                "kind": "Current",
                "value": orch_value("observe", {"observation": {"head_sha": "abc123"}}),
            },
        },
        *orch_steps(["review_gate"], (17, "send"), (18, "verify"), (20, "audit")),
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {
            "quorum_out": {
                "compliant": True,
                "tally": {"passes": 2, "blocks": 0, "full_passes": 2},
            }
        },
    },
    ["quorum", "recheck", "approval_decided"],
    inputs={"change": {"head_sha": "abc123", "number": "42"}},
)

orchestrator(
    "orchestrator_review_rethink",
    "A RETHINK blocks the quorum (F504); the failure mode loops back to the change, and the second round passes with one full sweep (min_full 1).",
    "review_gate",
    [
        *orch_steps(
            ["review_gate"],
            (0, "observe", {"observation": {"head_sha": "abc123"}}),
            (1, "retrieve"),
            (2, "classify"),
            (3, "plan"),
            (4, "constrain", {"compliant": True}),
            (5, "generate"),
            (6, "generate"),
            (7, "constrain", {"compliant": True}),
            (8, "checkpoint", {"checkpoint_id": "cp-worktree_ckpt_out"}),
            (
                9,
                "delegate",
                {
                    "accepted": True,
                    "task_id": "rv-a",
                    "effective": {"fresh_context": True, "model_family": "family_a"},
                },
            ),
            (
                10,
                "delegate",
                {
                    "accepted": True,
                    "task_id": "rv-b",
                    "effective": {"fresh_context": True, "model_family": "family_b"},
                },
            ),
        ),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 11,
                "frame": ["review_gate"],
                "event_type": "thread.turn_end",
                "correlate": {"head_sha": "abc123"},
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "thread.turn_end",
                    "source": {"kind": "agent"},
                    "head_sha": "abc123",
                },
                "principal": "peer",
            },
        },
        *orch_steps(
            ["review_gate"],
            (
                12,
                "receive",
                {
                    "data": [
                        {
                            "reviewer_id": "reviewer-a",
                            "value": "RETHINK",
                            "pinned": "abc123",
                            "scope": "full",
                        },
                        {
                            "reviewer_id": "reviewer-b",
                            "value": "BLESSED",
                            "pinned": "abc123",
                            "scope": "full",
                        },
                    ]
                },
            ),
            (13, "classify"),
            (14, "critique"),
            (15, "constrain", {"compliant": True}),
            (16, "checkpoint", {"checkpoint_id": "cp-post_ckpt_out"}),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 17,
                "frame": ["review_gate"],
                "approver": {"kind": "standing_mandate", "mandate_ref": "mandates"},
            },
            "respond": approve("d1", who=("mandate",)),
        },
        {
            "expect": {"kind": "RecheckSource", "step": 17, "frame": ["review_gate"]},
            "respond": {
                "kind": "Current",
                "value": orch_value("observe", {"observation": {"head_sha": "abc123"}}),
            },
        },
        *orch_steps(
            ["review_gate"],
            (17, "send"),
            (18, "verify"),
            (0, "observe", {"observation": {"head_sha": "abc123"}}),
            (1, "retrieve"),
            (2, "classify"),
            (3, "plan"),
            (4, "constrain", {"compliant": True}),
            (5, "generate"),
            (6, "generate"),
            (7, "constrain", {"compliant": True}),
            (8, "checkpoint", {"checkpoint_id": "cp-worktree_ckpt_out"}),
            (
                9,
                "delegate",
                {
                    "accepted": True,
                    "task_id": "rv-a",
                    "effective": {"fresh_context": True, "model_family": "family_a"},
                },
            ),
            (
                10,
                "delegate",
                {
                    "accepted": True,
                    "task_id": "rv-b",
                    "effective": {"fresh_context": True, "model_family": "family_b"},
                },
            ),
        ),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 11,
                "frame": ["review_gate"],
                "event_type": "thread.turn_end",
                "correlate": {"head_sha": "abc123"},
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "thread.turn_end",
                    "source": {"kind": "agent"},
                    "head_sha": "abc123",
                },
                "principal": "peer",
            },
        },
        *orch_steps(
            ["review_gate"],
            (
                12,
                "receive",
                {
                    "data": [
                        {
                            "reviewer_id": "reviewer-a",
                            "value": "BLESSED",
                            "pinned": "abc123",
                            "scope": "delta",
                        },
                        {
                            "reviewer_id": "reviewer-b",
                            "value": "BLESSED",
                            "pinned": "abc123",
                            "scope": "full",
                        },
                    ]
                },
            ),
            (13, "classify"),
            (14, "critique"),
            (15, "constrain", {"compliant": True}),
            (16, "checkpoint", {"checkpoint_id": "cp-post_ckpt_out"}),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 17,
                "frame": ["review_gate"],
                "approver": {"kind": "standing_mandate", "mandate_ref": "mandates"},
            },
            "respond": approve("d2", who=("mandate",)),
        },
        {
            "expect": {"kind": "RecheckSource", "step": 17, "frame": ["review_gate"]},
            "respond": {
                "kind": "Current",
                "value": orch_value("observe", {"observation": {"head_sha": "abc123"}}),
            },
        },
        *orch_steps(["review_gate"], (17, "send"), (18, "verify"), (20, "audit")),
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {
            "quorum_out": {"compliant": True, "tally": {"passes": 2, "full_passes": 1}}
        },
    },
    ["quorum", "failure_mode_fired", "loop"],
    inputs={"change": {"head_sha": "abc123", "number": "42"}},
)

orchestrator(
    "orchestrator_merge_self",
    "A self-merge: the build and the merge are each approved under a mandate (the merge after a recheck), CI on the merged head passes, and the hand-off to another merger is skipped.",
    "merge_ship",
    [
        *orch_steps(
            ["merge_ship"],
            (0, "observe", {"observation": {"head_sha": "abc123"}}),
            (1, "retrieve"),
            (2, "retrieve"),
            (3, "retrieve"),
            (4, "classify"),
            (5, "plan"),
            (6, "constrain", {"compliant": True}),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 7,
                "frame": ["merge_ship"],
                "approver": {"kind": "standing_mandate", "mandate_ref": "mandates"},
            },
            "respond": approve("d1", who=("mandate",)),
        },
        *orch_steps(
            ["merge_ship"],
            (7, "execute", {"exit_code": 0}),
            (8, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 9,
                "frame": ["merge_ship"],
                "approver": {"kind": "standing_mandate", "mandate_ref": "merge_gates"},
            },
            "respond": approve("d2", who=("mandate",)),
        },
        {
            "expect": {"kind": "RecheckSource", "step": 9, "frame": ["merge_ship"]},
            "respond": {
                "kind": "Current",
                "value": orch_value("observe", {"observation": {"head_sha": "abc123"}}),
            },
        },
        *orch_steps(["merge_ship"], (9, "mutate"), (11, "verify")),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["merge_ship"],
                "event_type": "ci.complete",
                "correlate": {"sha": "abc123"},
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "ci.complete",
                    "source": {"kind": "api"},
                    "sha": "abc123",
                },
                "principal": "peer",
            },
        },
        *orch_steps(
            ["merge_ship"],
            (13, "observe"),
            (14, "verify", {"passed": True}),
            (15, "synchronize"),
            (16, "persist"),
            (17, "audit"),
        ),
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "action_records": [{"status": "executed"}, {"status": "executed"}],
    },
    ["recheck", "event_received", "step_skipped"],
    inputs={
        "change": {
            "merger": "self",
            "head_sha": "abc123",
            "base": "main",
            "number": "42",
        }
    },
)

orchestrator(
    "orchestrator_merge_base_red",
    "Post-merge CI fails twice: the verify failure mode waits for CI once more, then escalates to the incident_triage handler, which delegates a fix and sends a notice; the run ends escalated (R404).",
    "merge_ship",
    [
        *orch_steps(
            ["merge_ship"],
            (0, "observe", {"observation": {"head_sha": "abc123"}}),
            (1, "retrieve"),
            (2, "retrieve"),
            (3, "retrieve"),
            (4, "classify"),
            (5, "plan"),
            (6, "constrain"),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 7,
                "frame": ["merge_ship"],
                "approver": {"kind": "standing_mandate", "mandate_ref": "mandates"},
            },
            "respond": approve("d1", who=("mandate",)),
        },
        *orch_steps(
            ["merge_ship"],
            (7, "execute", {"exit_code": 0}),
            (8, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 9,
                "frame": ["merge_ship"],
                "approver": {"kind": "standing_mandate", "mandate_ref": "merge_gates"},
            },
            "respond": approve("d2", who=("mandate",)),
        },
        {
            "expect": {"kind": "RecheckSource", "step": 9, "frame": ["merge_ship"]},
            "respond": {
                "kind": "Current",
                "value": orch_value("observe", {"observation": {"head_sha": "abc123"}}),
            },
        },
        *orch_steps(["merge_ship"], (9, "mutate"), (11, "verify")),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["merge_ship"],
                "event_type": "ci.complete",
                "correlate": {"sha": "abc123"},
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "ci.complete",
                    "source": {"kind": "api"},
                    "sha": "abc123",
                },
                "principal": "peer",
            },
        },
        *orch_steps(["merge_ship"], (13, "observe"), (14, "verify", {"passed": False})),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["merge_ship"],
                "event_type": "ci.complete",
                "correlate": {"sha": "abc123"},
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "ci.complete",
                    "source": {"kind": "api"},
                    "sha": "abc123",
                },
                "principal": "peer",
            },
        },
        *orch_steps(["merge_ship"], (13, "observe"), (14, "verify", {"passed": False})),
        *orch_steps(
            ["merge_ship", "incident_triage"],
            (0, "receive"),
            (1, "observe"),
            (2, "detect"),
            (3, "classify"),
            (4, "search"),
            (5, "attribute"),
            (6, "ground"),
            (7, "plan"),
            (8, "constrain"),
            (9, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
        ),
        *orch_steps(
            ["merge_ship", "incident_triage", "delegate_to_thread"],
            (0, "retrieve"),
            (1, "search"),
            (2, "compare"),
            (3, "decompose"),
            (4, "plan"),
            (5, "constrain"),
            (6, "generate"),
            (7, "constrain"),
            (8, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (9, "delegate", {"accepted": True, "task_id": "th-1"}),
            (10, "persist"),
            (11, "observe"),
        ),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["merge_ship", "incident_triage", "delegate_to_thread"],
                "event_type": "thread.turn_end",
                "correlate": {"task_id": "th-1"},
                "accept_from": ["th-1"],
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "thread.turn_end",
                    "source": {"kind": "agent"},
                    "task_id": "th-1",
                },
                "principal": "th-1",
            },
        },
        *orch_steps(
            ["merge_ship", "incident_triage", "delegate_to_thread"],
            (13, "ground"),
            (14, "verify"),
            (15, "persist"),
            (16, "audit"),
        ),
        *orch_steps(
            ["merge_ship", "incident_triage", "outbound_message"],
            (0, "retrieve"),
            (1, "search"),
            (2, "recall"),
            (3, "constrain"),
            (4, "plan"),
            (5, "generate"),
            (6, "critique"),
            (7, "ground"),
            (8, "constrain"),
            (9, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (10, "persist"),
            (11, "retrieve"),
            (12, "compare"),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 13,
                "frame": ["merge_ship", "incident_triage", "outbound_message"],
                "approver": {"kind": "human", "role": "owner"},
            },
            "respond": approve("d3", who=("owner",)),
        },
        {
            "expect": {
                "kind": "RecheckSource",
                "step": 13,
                "frame": ["merge_ship", "incident_triage", "outbound_message"],
            },
            "respond": {"kind": "Current", "value": orch_value("retrieve")},
        },
        *orch_steps(
            ["merge_ship", "incident_triage", "outbound_message"],
            (13, "send"),
            (14, "verify"),
            (15, "persist"),
            (16, "audit"),
        ),
        *orch_steps(
            ["merge_ship", "incident_triage"],
            (13, "synchronize"),
            (14, "verify"),
            (15, "persist"),
            (16, "audit"),
        ),
    ],
    {"kind": "Completed", "outcome": "escalated", "cause": "R404"},
    ["loop", "recovery_exhausted", "escalated", "invoke_started"],
    inputs={
        "change": {
            "merger": "self",
            "head_sha": "abc123",
            "base": "main",
            "number": "42",
        }
    },
)

orchestrator(
    "orchestrator_outbound_sent",
    "The owner approves the drafted message in session; the recheck finds the source unchanged and the message is sent and read back.",
    "outbound_message",
    [
        *orch_steps(
            ["outbound_message"],
            (0, "retrieve"),
            (1, "search"),
            (2, "recall"),
            (3, "constrain"),
            (4, "plan"),
            (5, "generate"),
            (6, "critique", {"severity": {"blocking": 0}}),
            (7, "ground", {"grounded": True}),
            (8, "constrain", {"compliant": True}),
            (9, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (10, "persist"),
            (11, "retrieve"),
            (12, "compare", {"recommendation": "send"}),
        ),
        {
            "expect": {
                "kind": "RequestApproval",
                "step": 13,
                "frame": ["outbound_message"],
                "approver": {"kind": "human", "role": "owner"},
            },
            "respond": approve("d1", who=("owner",)),
        },
        {
            "expect": {
                "kind": "RecheckSource",
                "step": 13,
                "frame": ["outbound_message"],
            },
            "respond": {"kind": "Current", "value": orch_value("retrieve")},
        },
        *orch_steps(
            ["outbound_message"],
            (13, "send", {"sent": True}),
            (14, "verify"),
            (15, "persist"),
            (16, "audit"),
        ),
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "action_records": [{"status": "executed"}],
    },
    ["approval_decided", "recheck"],
    inputs={
        "request": {
            "recipients": [{"id": "dana"}],
            "channel": "mail",
            "source_refs": ["doc-1"],
        },
        "run": {"unattended": False},
    },
)

orchestrator(
    "orchestrator_outbound_unattended",
    "Unattended, the send waits in the queue (when_unattended: defer_to_queue) and the steps that read it are deferred with it. The run passes no `run.unattended` flag: the adopter's own skip gate on that flag would skip the send before the deferral.",
    "outbound_message",
    [
        *orch_steps(
            ["outbound_message"],
            (0, "retrieve"),
            (1, "search"),
            (2, "recall"),
            (3, "constrain"),
            (4, "plan"),
            (5, "generate"),
            (6, "critique", {"severity": {"blocking": 0}}),
            (7, "ground"),
            (8, "constrain"),
            (9, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (10, "persist"),
            (11, "retrieve"),
            (12, "compare", {"recommendation": "send"}),
        ),
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "action_records": [{"status": "planned"}],
        "deferred": [
            {"store_as": "send_out"},
            {"store_as": "readback_out"},
            {"store_as": "log_out"},
            {"store_as": "audit_out"},
        ],
    },
    ["approval_unattended", "step_deferred"],
    inputs={
        "request": {
            "recipients": [{"id": "dana"}],
            "channel": "mail",
            "source_refs": ["doc-1"],
        }
    },
    attendance="unattended",
)

orchestrator(
    "orchestrator_owner_answer",
    "The owner is asked; an answer from anyone else is dropped, the owner's is kept, and the decision is applied through delegate_to_thread.",
    "owner_decision",
    [
        *orch_steps(
            ["owner_decision"],
            (0, "classify", {"labels": ["owner_only"], "confidence": 0.9}),
            (1, "search"),
            (2, "retrieve"),
            (3, "plan"),
            (4, "critique", {"confidence": 0.9}),
            (5, "compare"),
            (6, "constrain"),
            (7, "inquire", {"confidence": 0.9}),
        ),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 8,
                "frame": ["owner_decision"],
                "event_type": "owner.answer",
                "correlate": {"question": "release-date"},
                "accept_from": ["owner"],
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "owner.answer",
                    "source": {"kind": "human"},
                    "question": "release-date",
                    "answer": "ship it",
                },
                "principal": "intruder",
            },
        },
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 8,
                "frame": ["owner_decision"],
                "event_type": "owner.answer",
                "correlate": {"question": "release-date"},
                "accept_from": ["owner"],
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "owner.answer",
                    "source": {"kind": "human"},
                    "question": "release-date",
                    "answer": "next week",
                },
                "principal": "owner",
            },
        },
        *orch_steps(
            ["owner_decision"],
            (9, "integrate"),
            (10, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (11, "persist"),
        ),
        *orch_steps(
            ["owner_decision", "delegate_to_thread"],
            (0, "retrieve"),
            (1, "search"),
            (2, "compare"),
            (3, "decompose"),
            (4, "plan"),
            (5, "constrain"),
            (6, "generate"),
            (7, "constrain"),
            (8, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (9, "delegate", {"accepted": True, "task_id": "th-1"}),
            (10, "persist"),
            (11, "observe"),
        ),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 12,
                "frame": ["owner_decision", "delegate_to_thread"],
                "event_type": "thread.turn_end",
                "correlate": {"task_id": "th-1"},
                "accept_from": ["th-1"],
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "thread.turn_end",
                    "source": {"kind": "agent"},
                    "task_id": "th-1",
                },
                "principal": "th-1",
            },
        },
        *orch_steps(
            ["owner_decision", "delegate_to_thread"],
            (13, "ground"),
            (14, "verify"),
            (15, "persist"),
            (16, "audit"),
        ),
        *orch_steps(["owner_decision"], (13, "verify"), (14, "audit")),
    ],
    {
        "kind": "Completed",
        "outcome": "completed",
        "outputs": {
            "answer_out": {"data": [{"answer": "next week", "sender": "owner"}]}
        },
    },
    ["event_dropped", "event_received", "invoke_started"],
    inputs={"question": {"topic": "release-date"}},
)

orchestrator(
    "orchestrator_checkin_sweep",
    "An unattended sweep skips restarts the policy refuses and defers the reminder's send; the invoke that ran it is deferred too, then the escalation and the next check-in (they may act on the world after a deferred step), verify (the ontology orders it after mutate) and the steps that read verify.",
    "checkin_recovery",
    [
        *orch_steps(["checkin_recovery"], (0, "recall"), (1, "observe")),
        {
            "expect": {
                "kind": "AwaitEvent",
                "step": 2,
                "frame": ["checkin_recovery"],
                "event_type": "sweep.sample_delay",
            },
            "respond": {
                "kind": "Event",
                "event": {
                    "event_type": "sweep.sample_delay",
                    "source": {"kind": "message_bus"},
                },
                "principal": "peer",
            },
        },
        *orch_steps(
            ["checkin_recovery"],
            (3, "observe"),
            (4, "detect"),
            (5, "classify"),
            (6, "attribute"),
            (7, "plan"),
            (8, "constrain", {"compliant": False}),
            (9, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
        ),
        *orch_steps(
            ["checkin_recovery", "outbound_message"],
            (0, "retrieve"),
            (1, "search"),
            (2, "recall"),
            (3, "constrain"),
            (4, "plan"),
            (5, "generate"),
            (6, "critique", {"severity": {"blocking": 0}}),
            (7, "ground"),
            (8, "constrain"),
            (9, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
            (10, "persist"),
            (11, "retrieve"),
            (12, "compare"),
        ),
    ],
    {
        "kind": "Completed",
        "outcome": "deferred",
        "deferred": [
            {"store_as": "send_out"},
            {"store_as": "readback_out"},
            {"store_as": "log_out"},
            {"store_as": "audit_out"},
            {"store_as": "reminders_out"},
            {"store_as": "escalations_out"},
            {"store_as": "next_checkin_out"},
            {"store_as": "verify_out"},
            {"store_as": "board_out"},
            {"store_as": "audit_out"},
        ],
        "action_records": [{"status": "planned"}, {"status": "planned"}],
    },
    ["step_deferred", "approval_unattended", "step_skipped"],
    attendance="unattended",
)

orchestrator(
    "orchestrator_incident_prod",
    "A prod incident stops at the containment gate (R403) before any change is approved or made.",
    "incident_triage",
    [
        *orch_steps(
            ["incident_triage"],
            (0, "receive"),
            (1, "observe"),
            (2, "detect"),
            (3, "classify"),
            (4, "search"),
            (5, "attribute"),
            (6, "ground"),
            (7, "plan"),
            (8, "constrain"),
            (9, "checkpoint", {"checkpoint_id": "cp-checkpoint_out"}),
        ),
    ],
    {
        "kind": "Failed",
        "code": "R403",
        "step": 10,
        "message": "Prod - report and ask; do not act.",
    },
    ["gate_fired"],
    inputs={
        "signal": {"event_type": "alert.fired", "source": {"kind": "api"}},
        "environment": {"name": "prod-eu", "own_resource": True, "is_prod": True},
    },
)

orchestrator(
    "orchestrator_daily_digest",
    "A brief reads the calendar; the text is checked, grounded and verified, then saved.",
    "daily_digest",
    [
        *orch_steps(
            ["daily_digest"],
            (0, "recall"),
            (1, "retrieve"),
            (2, "retrieve"),
            (3, "search"),
            (4, "integrate"),
            (5, "classify"),
            (6, "measure"),
            (7, "constrain", {"compliant": True}),
            (8, "generate"),
            (9, "ground", {"grounded": True}),
            (10, "constrain", {"compliant": True}),
            (11, "verify", {"passed": True}),
            (12, "persist"),
            (13, "audit"),
        ),
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["step_completed", "run_finished"],
    inputs={"report": {"kind": "brief"}},
)

orchestrator(
    "orchestrator_daily_digest_other",
    "A report that is not a brief skips the calendar and goes on.",
    "daily_digest",
    [
        *orch_steps(
            ["daily_digest"],
            (0, "recall"),
            (1, "retrieve"),
            (3, "search"),
            (4, "integrate"),
            (5, "classify"),
            (6, "measure"),
            (7, "constrain", {"compliant": True}),
            (8, "generate"),
            (9, "ground", {"grounded": True}),
            (10, "constrain", {"compliant": True}),
            (11, "verify", {"passed": True}),
            (12, "persist"),
            (13, "audit"),
        ),
    ],
    {"kind": "Completed", "outcome": "completed"},
    ["step_skipped", "run_finished"],
    inputs={"report": {"kind": "digest"}},
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
