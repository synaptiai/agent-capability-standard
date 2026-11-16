"""Runtime fixtures of workstream S4 (evidence, grounding and secrets; RFC-0008):
the grounding check of host outputs (STANDARD v1.2 §5.20, F505).

Every fixture's name starts with `grounding_` (§10.3). A fixture's host
outputs are scripted inputs to the executor: outside these fixtures no
grounding policy applies, and the `evidence_anchors: []` of other fixtures
is not a claim of a conforming producer.

Define each with add(name, description, catalog, script, end, trace, ...),
the function of scripts/gen_runtime_fixtures.py; the building blocks are in
runtime_fixtures.helpers. Executor prose (a `Failed` action's `message`) is
not pinned.
"""

from runtime_fixtures.helpers import inv, out, st, wf

FILE_A = {"ref": "file:a.txt", "kind": "file"}
FILE_B = {"ref": "file:b.txt", "kind": "file"}
URL = {"ref": "https://example.org/report", "kind": "url"}
EXT = ["grounding@1"]
RETRIEVE = {"require": ["retrieve"]}
TRANSFORM = {"require": ["transform"]}


def retrieve(store="r", **kw):
    return st("retrieve", store, input_bindings={"target": "t"}, **kw)


def grounded(policy, steps, requires=EXT, **kw):
    """A 1.2 workflow that declares grounding@1 with `policy`."""
    return wf(steps, requires=requires, spec_version="1.2", grounding=policy, **kw)


def found(anchors=(), **extra):
    """A retrieve output with these anchors."""
    return out(
        data={"items": [1, 2]}, confidence=1, evidence_anchors=list(anchors), **extra
    )


def transformed(anchors):
    return out(output={}, confidence=1, evidence_anchors=list(anchors))


def reads(binding, policy, cite):
    """Step 0 retrieves r; step 1 binds `binding` and its output cites `cite`."""
    return (
        {
            "w": grounded(
                policy,
                [
                    retrieve(),
                    st(
                        "transform",
                        "t",
                        input_bindings={"input": binding, "target_format": "json"},
                    ),
                ],
            )
        },
        [
            {"expect": inv("retrieve", step=0), "respond": found([FILE_A])},
            {"expect": inv("transform", step=1), "respond": transformed([cite])},
        ],
    )


def register(add):
    """Add this workstream's fixtures."""
    _outputs(add)
    _citations(add)
    _attestation(add)
    _exemptions(add)
    _nested(add)


def _outputs(add):
    add(
        "grounding_grounded_output",
        "Under a policy that requires retrieve, an output with an evidence anchor "
        "is grounded; the trace records the check (§5.20).",
        {"w": grounded(RETRIEVE, [retrieve()])},
        [{"expect": inv("retrieve", step=0), "respond": found([FILE_A])}],
        {"kind": "Completed", "outcome": "completed"},
        ["grounding"],
    )
    add(
        "grounding_empty_anchors",
        "An empty evidence_anchors grounds nothing, and the output is not marked "
        "inferred: F505. F505 is not retried, although the step has retry (§5.2).",
        {"w": grounded(RETRIEVE, [retrieve(retry={"max": 2})])},
        [{"expect": inv("retrieve", step=0, attempt=1), "respond": found()}],
        {"kind": "Failed", "code": "F505", "step": 0},
        ["step_failed", "run_failed"],
    )
    add(
        "grounding_inferred_output",
        "An output with no anchors that carries a vocabulary inference_method and "
        "a confidence is marked inferred, and passes (§3.1, §4.1.1).",
        {"w": grounded(RETRIEVE, [retrieve()])},
        [
            {
                "expect": inv("retrieve", step=0),
                "respond": out(
                    data={}, confidence=0.4, inference_method="model_knowledge"
                ),
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["grounding"],
    )
    add(
        "grounding_not_required",
        "A policy checks only the capabilities it requires: a retrieve output "
        "with no anchors passes a policy that requires classify, unchecked.",
        {"w": grounded({"require": ["classify"]}, [retrieve()])},
        [{"expect": inv("retrieve", step=0), "respond": found()}],
        {"kind": "Completed", "outcome": "completed"},
    )
    add(
        "grounding_legacy_forms",
        "A bare string and an object with a kind outside the vocabulary are the "
        "deprecated legacy forms: neither counts, neither is itself the failure; "
        "with nothing that counts and no inference marking, F505 (§6.5).",
        {"w": grounded(RETRIEVE, [retrieve()])},
        [
            {
                "expect": inv("retrieve", step=0),
                "respond": found(["file:a.txt", {"ref": "b", "kind": "tool_output"}]),
            }
        ],
        {"kind": "Failed", "code": "F505", "step": 0},
    )
    add(
        "grounding_kinds_filter",
        "Under kinds [file], a log anchor does not count: F505.",
        {"w": grounded({"require": ["retrieve"], "kinds": ["file"]}, [retrieve()])},
        [
            {
                "expect": inv("retrieve", step=0),
                "respond": found([{"ref": "log:app#42", "kind": "log"}]),
            }
        ],
        {"kind": "Failed", "code": "F505", "step": 0},
    )
    add(
        "grounding_failure_mode_loop",
        "A failure mode fires on F505 (§5.12) and loops back to the step, whose "
        "second output is grounded.",
        {
            "w": grounded(
                RETRIEVE,
                [
                    retrieve(
                        failure_modes=[
                            {
                                "condition": "the output is not grounded",
                                "on_error": "F505",
                                "action": "request_more_context",
                                "recovery": {"goto_step": "r", "max_loops": 1},
                            }
                        ]
                    )
                ],
            )
        },
        [
            {"expect": inv("retrieve", step=0), "respond": found()},
            {"expect": inv("retrieve", step=0), "respond": found([FILE_A])},
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["step_failed", "failure_mode_fired", "loop", "grounding"],
    )


def _citations(add):
    catalog, script = reads(
        "${r.data: object}", TRANSFORM, {"ref": "acs:r.data.items[0]", "kind": "record"}
    )
    add(
        "grounding_acs_bound",
        "An acs: citation that a reference the step binds covers (the bound path "
        "a prefix of the cited one) is established and counts (§5.20).",
        catalog,
        script,
        {"kind": "Completed", "outcome": "completed"},
        ["grounding"],
    )
    catalog, script = reads(
        "${r.data: object}", TRANSFORM, {"ref": "acs:other.data", "kind": "record"}
    )
    add(
        "grounding_acs_unbound",
        "An acs: citation of a value the step does not bind: its producer did not "
        "have it (§3.1), F505.",
        catalog,
        script,
        {"kind": "Failed", "code": "F505", "step": 1},
    )
    catalog, script = reads(
        "${r.data.items: array<integer>}",
        TRANSFORM,
        {"ref": "acs:r.confidence", "kind": "record"},
    )
    add(
        "grounding_acs_sibling_unbound",
        "A sibling of the bound path is not covered: binding r.data.items does not "
        "make r.confidence available, F505.",
        catalog,
        script,
        {"kind": "Failed", "code": "F505", "step": 1},
    )
    catalog, script = reads(
        "${r: object}",
        {"require": ["transform"], "kinds": ["file"]},
        {"ref": "acs:r.data", "kind": "file"},
    )
    add(
        "grounding_acs_wrong_kind",
        "A citation of a workflow value is of kind record: relabelled file to "
        "meet kinds [file], it fails (F505, §6.5).",
        catalog,
        script,
        {"kind": "Failed", "code": "F505", "step": 1},
    )


def _attestation(add):
    add(
        "grounding_evidence_seen_mismatch",
        "An Output whose evidence_seen does not list an anchor: its producer did "
        "not have that evidence (§3.1), F505.",
        {"w": grounded(RETRIEVE, [retrieve()])},
        [
            {
                "expect": inv("retrieve", step=0),
                "respond": {**found([FILE_A]), "evidence_seen": ["file:b.txt"]},
            }
        ],
        {"kind": "Failed", "code": "F505", "step": 0},
    )
    attested = {"require": ["retrieve"], "attested": True}
    add(
        "grounding_attested_unattested",
        "Under attested, an anchor the host does not attest does not count; not "
        "marked inferred, the output fails (F505).",
        {"w": grounded(attested, [retrieve()])},
        [{"expect": inv("retrieve", step=0), "respond": found([FILE_A])}],
        {"kind": "Failed", "code": "F505", "step": 0},
    )
    add(
        "grounding_attested_seen",
        "Under attested, an anchor the Output's evidence_seen lists counts.",
        {"w": grounded(attested, [retrieve()])},
        [
            {
                "expect": inv("retrieve", step=0),
                "respond": {**found([FILE_A]), "evidence_seen": ["file:a.txt"]},
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["grounding"],
    )


def _exemptions(add):
    waiting = st(
        "delegate",
        "d",
        timeout="1h",
        input_bindings={"task": {"review": "x"}, "agent": "a"},
        wait={"event_type": "delegation.result"},
    )
    add(
        "grounding_delegate_wait_exempt",
        "A delegate step that waits is not checked: its Output is the delegation's "
        "acceptance, not its claim, and its result is composed by the executor "
        "(§3.1, §5.20).",
        {
            "w": grounded(
                {"require": ["delegate"]}, [waiting], requires=["wait@1", "grounding@1"]
            )
        },
        [
            {
                "expect": inv("delegate", step=0),
                "respond": out(accepted=True, task_id="t1"),
            },
            {
                "expect": {
                    "kind": "AwaitEvent",
                    "step": 0,
                    "correlate": {"task_id": "t1"},
                },
                "respond": {
                    "kind": "Event",
                    "event": {
                        "event_type": "delegation.result",
                        "task_id": "t1",
                        "verdict": "done",
                    },
                },
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {
                "d": {"accepted": True, "task_id": "t1", "result": {"verdict": "done"}}
            },
        },
        ["delegated", "event_received"],
    )
    add(
        "grounding_delegate_no_wait_checked",
        "A delegation that does not wait is checked like any output: an acceptance "
        "with no anchors and no inference marking fails (F505).",
        {
            "w": grounded(
                {"require": ["delegate"]},
                [
                    st(
                        "delegate",
                        "d",
                        input_bindings={"task": {"review": "x"}, "agent": "a"},
                    )
                ],
            )
        },
        [
            {
                "expect": inv("delegate", step=0),
                "respond": out(accepted=True, task_id="t1"),
            }
        ],
        {"kind": "Failed", "code": "F505", "step": 0},
    )
    reviewer = lambda store, agent: st(  # noqa: E731
        "delegate", store, input_bindings={"task": {"diff": "d"}, "agent": agent}
    )
    add(
        "grounding_quorum_exempt",
        "A quorum's constrain output is built by the executor and not checked, "
        "though a policy requires constrain (§3.1).",
        {
            "w": grounded(
                {"require": ["constrain"]},
                [
                    reviewer("ra", "a"),
                    reviewer("rb", "b"),
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
                            "vocabulary": ["approve", "request_changes"],
                            "pass_values": ["approve"],
                            "blocking_values": ["request_changes"],
                            "min_pass": 2,
                            "pinned_to": "${change}",
                        },
                    ),
                ],
                inputs={"change": {"type": "string", "required": True}},
                requires=["delegation@1", "quorum@1", "grounding@1"],
            )
        },
        [
            {"expect": inv("delegate", step=0), "respond": out(accepted=True)},
            {"expect": inv("delegate", step=1), "respond": out(accepted=True)},
            {
                "expect": inv("receive", step=2),
                "respond": out(
                    data=[
                        {"reviewer_id": "a", "value": "approve", "pinned": "c1"},
                        {"reviewer_id": "b", "value": "approve", "pinned": "c1"},
                    ]
                ),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"gate": {"compliant": True, "evidence_anchors": []}},
        },
        ["quorum"],
        inputs={"change": "c1"},
    )


def parent(child, requires=None, policy=None, spec="1.2"):
    """`w` invokes `child`, with grounding@1 (and `policy`) when `requires`."""
    extra = {"grounding": policy} if policy else {}
    return {
        "w": wf(
            [
                st(
                    "invoke",
                    "i",
                    workflow_id="child",
                    input_bindings={"workflow": "child"},
                )
            ],
            requires=requires,
            spec_version=spec,
            **extra,
        ),
        "child": child,
    }


CHILD = wf(
    [
        retrieve(),
        st(
            "transform",
            "t",
            input_bindings={"input": "${r.data: object}", "target_format": "json"},
        ),
    ]
)
CHILD_SCRIPT = [
    {
        "expect": inv("retrieve", frame=["w", "child"], step=0),
        "respond": found([FILE_A, FILE_B]),
    },
    {
        "expect": inv("transform", frame=["w", "child"], step=1),
        "respond": transformed([{"ref": "acs:r.data", "kind": "record"}, FILE_A, URL]),
    },
]
EMPTY_CHILD = wf([retrieve()])
EMPTY_CHILD_SCRIPT = [
    {"expect": inv("retrieve", frame=["w", "child"], step=0), "respond": found()}
]


def _nested(add):
    add(
        "grounding_invoke_fills_anchors",
        "With grounding@1, a completed invoke step carries its nested run's anchors: "
        "in step order, each ref once, acs: anchors left out; the invoke step "
        "itself is not checked (§5.20).",
        parent(CHILD, requires=EXT, policy={"require": ["invoke"]}),
        CHILD_SCRIPT,
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"i": {"evidence_anchors": [FILE_A, FILE_B, URL]}},
        },
        ["invoke_returned"],
    )
    add(
        "grounding_invoke_without_extension",
        "Without grounding@1, an invoke step's evidence_anchors are empty, as in 1.1.",
        parent(CHILD, spec="1.1"),
        CHILD_SCRIPT,
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"i": {"evidence_anchors": []}},
        },
    )
    add(
        "grounding_host_policy",
        "A policy the host gives when the run starts applies without the "
        "extension, to a 1.1 workflow: an output with no anchors fails (F505).",
        {"w": wf([retrieve()])},
        [{"expect": inv("retrieve", step=0), "respond": found()}],
        {"kind": "Failed", "code": "F505", "step": 0},
        grounding=[RETRIEVE],
    )
    add(
        "grounding_host_policy_nested",
        "A host's policy applies to the steps of nested runs: the child's step fails "
        "F505, and the run fails at the invoke step (R402).",
        parent(EMPTY_CHILD, spec="1.1"),
        EMPTY_CHILD_SCRIPT,
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "invoke_returned"],
        grounding=[RETRIEVE],
    )
    add(
        "grounding_workflow_policy_not_nested",
        "A workflow's own policy covers its own steps, not those of a workflow it "
        "invokes: the child's ungrounded output passes.",
        parent(EMPTY_CHILD, requires=EXT, policy=RETRIEVE),
        EMPTY_CHILD_SCRIPT,
        {"kind": "Completed", "outcome": "completed"},
    )
