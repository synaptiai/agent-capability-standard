"""Runtime fixtures of workstream S6 (profiles, trust, versioning and dialect; RFC-0010).

Define each with add(name, description, catalog, script, end, trace, ...),
the function of scripts/gen_runtime_fixtures.py; the building blocks are in
runtime_fixtures.helpers. Each fixture here applies domain profiles
(`profiles`, STANDARD v1.2 §5.21) and pins one rule of §5.21.3.
"""

from runtime_fixtures.helpers import CP, POLICY, approve, inv, mutate, out, st, wf


def profile(domain, **rules):
    p = {"domain": domain, "version": "1.0.0"}
    p.update(rules)
    return p


REVIEW_LOW = profile("review-low", risk_thresholds={"require_review": "low"})
REVIEW_MEDIUM = profile("review-medium", risk_thresholds={"require_review": "medium"})
HUMAN_LOW = profile("human-low", risk_thresholds={"require_human": "low"})
PERSON_MUTATE = profile(
    "person-mutate", risk_thresholds={"block_autonomous": ["mutate"]}
)
STAR_ALWAYS = profile("star-always", checkpoint_policy={"*": "always"})
STAR_MEDIUM = profile("star-medium", checkpoint_policy={"*": "medium_risk"})
CHECKPOINT_EXECUTE = profile(
    "checkpoint-execute", checkpoint_policy={"execute": "always"}
)
CONFIDENT = profile("confident", evidence_policy={"minimum_confidence": 0.9})
GROUNDED = profile(
    "grounded",
    evidence_policy={
        "require_grounding": ["classify"],
        "required_anchor_types": ["file"],
    },
)
GROUNDED_CONFIDENT = profile(
    "grounded-confident",
    evidence_policy={
        "require_grounding": ["classify"],
        "required_anchor_types": ["file"],
        "minimum_confidence": 0.9,
    },
)
FILE_ANCHOR = {"ref": "file:docs/item.md", "kind": "file"}
PERSON_INVOKE = profile(
    "person-invoke", risk_thresholds={"block_autonomous": ["invoke"]}
)
PERSON_VERIFY = profile(
    "person-verify", risk_thresholds={"block_autonomous": ["verify"]}
)

M1 = {"kind": "standing_mandate", "mandate_ref": "m1"}
PERSON = {"kind": "human", "always_ask": True}
# A person's request names no mandate, whatever the step's approver declares
# (§5.21.3): the subset rule of `expect` cannot say so, `absent` does.
NO_MANDATE = ["approver.mandate_ref"]


def retrieve(store="r", **kw):
    kw.setdefault("input_bindings", {"target": "x"})
    return st("retrieve", store, **kw)


def person_catalog(**approval):
    """A mutate step a profile requires a person for, its approver a mandate."""
    return {
        "w": wf(
            [CP, POLICY, mutate(approval={"approver": M1, **approval})],
            requires=["approval@1"],
        )
    }


def classify(**kw):
    return {"w": wf([st("classify", "c", input_bindings={"item": "x"}, **kw)])}


def invoke_child():
    return st("invoke", "i", workflow_id="child", input_bindings={"workflow": "child"})


def register(add):
    add(
        "profile_review_threshold",
        "require_review: low covers every risk level: a low-risk retrieve is asked"
        " for approval (a human, the default approver) before it runs.",
        {"w": wf([retrieve()])},
        [
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 0,
                    "approver": {"kind": "human"},
                },
                "respond": approve("d1"),
            },
            {"expect": inv("retrieve", step=0), "respond": out(data=1, confidence=1)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"status": "executed", "approval": {"decision": "approved"}}
            ],
        },
        ["approval_requested", "approval_decided"],
        profiles=[REVIEW_LOW],
    )

    add(
        "profile_person_overrides_mandate",
        "block_autonomous requires a person for the mutate step: it is asked of a"
        " human with always_ask and no mandate_ref (the request has none), though its"
        " approver is a standing mandate; its record carries person_required, and the"
        " decision no mandate_ref.",
        person_catalog(),
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
            {
                "expect": {"kind": "RequestApproval", "step": 2, "approver": PERSON},
                "absent": NO_MANDATE,
                "respond": approve("d1", who=("dana",)),
            },
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {
                    "status": "executed",
                    "person_required": True,
                    "approval": {"mandate_ref": None, "approvers": ["dana"]},
                }
            ],
        },
        ["person_required", "approval_requested", "approval_decided"],
        profiles=[PERSON_MUTATE],
    )

    add(
        "profile_person_does_not_mark_readers",
        "The person requirement belongs to the mutate step alone: a later step that"
        " reads its output is asked of its own approver, a standing mandate.",
        {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate(approval={"approver": {"kind": "human"}}),
                    retrieve(
                        "after",
                        requires_approval=True,
                        approval={"approver": M1},
                        input_bindings={"target": "after change ${m.success}"},
                    ),
                ],
                requires=["approval@1"],
            )
        },
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
            {
                "expect": {"kind": "RequestApproval", "step": 2, "approver": PERSON},
                "absent": NO_MANDATE,
                "respond": approve("d1", who=("dana",)),
            },
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
            {
                "expect": {"kind": "RequestApproval", "step": 3, "approver": M1},
                "absent": ["approver.always_ask"],
                "respond": approve("d2", who=("mandate",)),
            },
            {"expect": inv("retrieve", step=3), "respond": out(data=1, confidence=1)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"status": "executed", "person_required": True},
                {"status": "executed", "approval": {"mandate_ref": "m1"}},
            ],
        },
        ["person_required", "approval_requested"],
        profiles=[PERSON_MUTATE],
    )

    add(
        "profile_star_always_starts",
        'checkpoint_policy {"*": always} never covers a checkpoint step, so the run'
        " starts; the first retrieve uses the step's checkpoint and the second asks"
        " for its own.",
        {"w": wf([CP, retrieve("r1"), retrieve("r2")])},
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("retrieve", step=1), "respond": out(data=1, confidence=1)},
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {"expect": inv("retrieve", step=2), "respond": out(data=2, confidence=1)},
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["checkpoint_consumed", "checkpoint_created"],
        profiles=[STAR_ALWAYS],
    )

    add(
        "profile_person_unattended_deferred",
        "Unattended, a step a profile requires a person for is not asked, even of"
        " its mandate: when_unattended applies (here, queued).",
        person_catalog(when_unattended="defer_to_queue"),
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "deferred",
            "action_records": [{"status": "planned", "person_required": True}],
            "deferred": [{"step": 2, "store_as": "m"}],
        },
        ["person_required", "approval_unattended", "step_deferred"],
        attendance="unattended",
        profiles=[PERSON_MUTATE],
    )

    add(
        "profile_person_unattended_fails",
        "Unattended, with no when_unattended, a step a profile requires a person for"
        " fails with F502: its mandate does not cover it.",
        person_catalog(),
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain"), "respond": out(compliant=True)},
        ],
        {"kind": "Failed", "code": "F502", "step": 2},
        ["person_required"],
        attendance="unattended",
        profiles=[PERSON_MUTATE],
    )

    add(
        "profile_checkpoint_each_step",
        "checkpoint_policy {execute: always}: the first execute uses the step's"
        " checkpoint, the second asks for its own.",
        {
            "w": wf(
                [
                    CP,
                    st("execute", "e1", input_bindings={"code": "a"}),
                    st("execute", "e2", input_bindings={"code": "b"}),
                ]
            )
        },
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {
                "expect": {"kind": "RequestApproval", "step": 1},
                "respond": approve("d1"),
            },
            {"expect": inv("execute", step=1), "respond": out(result="ok")},
            {
                "expect": {"kind": "RequestApproval", "step": 2},
                "respond": approve("d2"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {"expect": inv("execute", step=2), "respond": out(result="ok")},
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["checkpoint_consumed", "checkpoint_created"],
        profiles=[CHECKPOINT_EXECUTE],
    )

    add(
        "profile_star_medium_risk",
        'checkpoint_policy {"*": medium_risk} covers the invoke step (medium) but not'
        " the low-risk retrieve of its nested run.",
        {"w": wf([CP, invoke_child()]), "child": wf([retrieve()])},
        [
            {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
            {
                "expect": inv("retrieve", frame=["w", "child"]),
                "respond": out(data=1, confidence=1),
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["checkpoint_consumed", "invoke_started", "invoke_returned"],
        profiles=[STAR_MEDIUM],
    )

    add(
        "profile_minimum_confidence_fails",
        "An output whose confidence is below the applied minimum fails its step:"
        " F504, reason below_minimum_confidence.",
        classify(),
        [{"expect": inv("classify"), "respond": out(labels=["a"], confidence=0.5)}],
        {
            "kind": "Failed",
            "code": "F504",
            "step": 0,
            "reason": "below_minimum_confidence",
        },
        ["step_failed"],
        profiles=[CONFIDENT],
    )

    add(
        "profile_minimum_confidence_not_a_number",
        "While a minimum applies, a confidence that is not a number from 0 to 1"
        ' (here the string "0.95") fails its step: F504, reason invalid_confidence.',
        classify(),
        [
            {
                "expect": inv("classify"),
                "respond": out(labels=["a"], confidence="0.95"),
            }
        ],
        {"kind": "Failed", "code": "F504", "step": 0, "reason": "invalid_confidence"},
        ["step_failed"],
        profiles=[CONFIDENT],
    )

    add(
        "profile_minimum_confidence_failure_mode",
        "F504 from a profile's minimum is matched by a failure mode's on_error; with"
        " no recovery the run ends with the step's code.",
        classify(
            failure_modes=[
                {"condition": "low confidence", "on_error": ["F504"], "action": "stop"}
            ]
        ),
        [{"expect": inv("classify"), "respond": out(labels=["a"], confidence=0.5)}],
        {"kind": "Failed", "code": "F504", "step": 0},
        ["step_failed", "failure_mode_fired"],
        profiles=[CONFIDENT],
    )

    add(
        "profile_minimum_confidence_waited_delegate",
        "A delegate step that waits: the output its host returns when it accepts the"
        " delegation becomes the step's output once the result arrives, so its"
        " confidence is checked at once; below the minimum, the step fails with F504"
        " (below_minimum_confidence) and no result is awaited.",
        {
            "w": wf(
                [
                    st(
                        "delegate",
                        "d",
                        input_bindings={"task": {"review": "x"}, "agent": "a"},
                        timeout="1h",
                        wait={"event_type": "review.done"},
                    )
                ],
                requires=["wait@1"],
            )
        },
        [
            {
                "expect": inv("delegate", step=0),
                "respond": out(accepted=True, task_id="t1", agent="a", confidence=0.5),
            }
        ],
        {
            "kind": "Failed",
            "code": "F504",
            "step": 0,
            "reason": "below_minimum_confidence",
        },
        ["step_failed"],
        profiles=[CONFIDENT],
    )

    add(
        "profile_minimum_confidence_met",
        "A confidence at or above the applied minimum passes.",
        classify(),
        [{"expect": inv("classify"), "respond": out(labels=["a"], confidence=0.95)}],
        {"kind": "Completed", "outcome": "completed"},
        profiles=[CONFIDENT],
    )

    add(
        "profile_applies_in_nested_run",
        "A run's profiles cover its nested runs: the invoke step and the retrieve"
        " it runs are each asked for approval.",
        {"w": wf([invoke_child()]), "child": wf([retrieve()])},
        [
            {
                "expect": {"kind": "RequestApproval", "step": 0, "frame": ["w"]},
                "respond": approve("d1"),
            },
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 0,
                    "frame": ["w", "child"],
                },
                "respond": approve("d2"),
            },
            {
                "expect": inv("retrieve", frame=["w", "child"]),
                "respond": out(data=1, confidence=1),
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["approval_requested", "invoke_started"],
        profiles=[REVIEW_LOW],
    )

    add(
        "profile_person_not_passed_to_nested_run",
        "A profile requires a person for the invoke step, not for the nested run it"
        " starts: the invoke is asked of a person, the child's retrieve of its own"
        " approver, a standing mandate, whose decision keeps its mandate_ref.",
        {
            "w": wf([invoke_child()]),
            "child": wf(
                [retrieve(requires_approval=True, approval={"approver": M1})],
                requires=["approval@1"],
            ),
        },
        [
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 0,
                    "frame": ["w"],
                    "approver": PERSON,
                },
                "absent": NO_MANDATE,
                "respond": approve("d1", who=("dana",)),
            },
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 0,
                    "frame": ["w", "child"],
                    "approver": M1,
                },
                "absent": ["approver.always_ask"],
                "respond": approve("d2", who=("mandate",)),
            },
            {
                "expect": inv("retrieve", frame=["w", "child"]),
                "respond": out(data=1, confidence=1),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {
                    "intent": "invoke step",
                    "person_required": True,
                    "approval": {"mandate_ref": None, "approvers": ["dana"]},
                },
                {"intent": "retrieve step", "approval": {"mandate_ref": "m1"}},
            ],
        },
        ["person_required", "approval_requested", "invoke_started"],
        profiles=[PERSON_INVOKE],
    )

    add(
        "profile_person_not_passed_to_recovery",
        "A profile requires a person for the verify step; the context its failure"
        " mode injects for recovery is not marked, so the step the loop returns to"
        " is asked of its own approver, a standing mandate, both times.",
        {
            "w": wf(
                [
                    st(
                        "plan",
                        "p",
                        requires_approval=True,
                        approval={"approver": M1},
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
                ],
                requires=["approval@1"],
            )
        },
        [
            {
                "expect": {"kind": "RequestApproval", "step": 0, "approver": M1},
                "absent": ["approver.always_ask"],
                "respond": approve("d1", who=("mandate",)),
            },
            {"expect": inv("plan", step=0), "respond": out(steps=[], confidence=1)},
            {
                "expect": {"kind": "RequestApproval", "step": 1, "approver": PERSON},
                "absent": NO_MANDATE,
                "respond": approve("d2", who=("dana",)),
            },
            {
                "expect": inv("verify", step=1),
                "respond": out(passed=False, confidence=1),
            },
            {
                "expect": {"kind": "RequestApproval", "step": 0, "approver": M1},
                "absent": ["approver.always_ask"],
                "respond": approve("d3", who=("mandate",)),
            },
            {
                "expect": inv(
                    "plan", step=0, inputs={"goal": "g", "constraints": {"why": False}}
                ),
                "respond": out(steps=[], confidence=1),
            },
            {
                "expect": {"kind": "RequestApproval", "step": 1, "approver": PERSON},
                "absent": NO_MANDATE,
                "respond": approve("d4", who=("dana",)),
            },
            {
                "expect": inv("verify", step=1),
                "respond": out(passed=True, confidence=1),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"intent": "plan step", "approval": {"mandate_ref": "m1"}},
                {"intent": "verify step", "person_required": True},
                {"intent": "plan step", "approval": {"mandate_ref": "m1"}},
                {"intent": "verify step", "person_required": True},
            ],
        },
        ["person_required", "failure_mode_fired", "loop"],
        profiles=[PERSON_VERIFY],
    )

    add(
        "profile_two_profiles_strictest",
        "Two profiles each apply: require_review: medium does not cover a low-risk"
        " retrieve, require_human: low does, so a person is asked.",
        {"w": wf([retrieve()])},
        [
            {
                "expect": {"kind": "RequestApproval", "step": 0, "approver": PERSON},
                "absent": NO_MANDATE,
                "respond": approve("d1"),
            },
            {"expect": inv("retrieve", step=0), "respond": out(data=1, confidence=1)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [{"status": "executed", "person_required": True}],
        },
        ["person_required", "approval_requested"],
        profiles=[REVIEW_MEDIUM, HUMAN_LOW],
    )

    # A profile's grounding policy (evidence_policy.require_grounding, with
    # required_anchor_types as its kinds) is checked as a host's is (§5.20,
    # §5.21.3): in every frame, after the required fields, before the
    # minimum confidence.
    add(
        "profile_grounding_required",
        "require_grounding: [classify] applies to a 1.1 workflow: a classify output"
        " with no anchors fails its step with F505.",
        classify(),
        [{"expect": inv("classify"), "respond": out(labels=["a"], confidence=1)}],
        {"kind": "Failed", "code": "F505", "step": 0},
        ["step_failed"],
        profiles=[GROUNDED],
    )

    add(
        "profile_grounding_met",
        "An output with an anchor of a kind the profile requires (file) passes the"
        " profile's grounding policy.",
        classify(),
        [
            {
                "expect": inv("classify"),
                "respond": out(
                    labels=["a"], confidence=1, evidence_anchors=[FILE_ANCHOR]
                ),
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["grounding", "step_completed"],
        profiles=[GROUNDED],
    )

    add(
        "profile_grounding_wrong_kind",
        "required_anchor_types are the policy's kinds: a log anchor does not count"
        " under [file], so the step fails with F505.",
        classify(),
        [
            {
                "expect": inv("classify"),
                "respond": out(
                    labels=["a"],
                    confidence=1,
                    evidence_anchors=[{"ref": "log:app#42", "kind": "log"}],
                ),
            }
        ],
        {"kind": "Failed", "code": "F505", "step": 0},
        ["step_failed"],
        profiles=[GROUNDED],
    )

    add(
        "profile_grounding_in_nested_run",
        "A profile's grounding policy covers the run's nested runs: the classify"
        " step an invoke runs fails with F505 without anchors, and the run fails at"
        " the invoke step (R402).",
        {
            "w": wf([invoke_child()]),
            "child": wf([st("classify", "c", input_bindings={"item": "x"})]),
        },
        [
            {
                "expect": inv("classify", frame=["w", "child"]),
                "respond": out(labels=["a"], confidence=1),
            }
        ],
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "invoke_returned"],
        profiles=[GROUNDED],
    )

    add(
        "profile_grounding_before_minimum_confidence",
        "The grounding check comes before the minimum confidence: an output with no"
        " anchors and a confidence below the minimum fails with F505, not F504.",
        classify(),
        [{"expect": inv("classify"), "respond": out(labels=["a"], confidence=0.5)}],
        {"kind": "Failed", "code": "F505", "step": 0},
        ["step_failed"],
        profiles=[GROUNDED_CONFIDENT],
    )

    # The catalog header's version, which the start operation takes (§11.5,
    # §5.19.2), decides a catalog's target when no workflow declares one: the
    # same catalog runs under 1.2's approver rules with a 1.2.0 header and
    # under 1.1's without one.
    header_catalog = {
        "w": {
            "goal": "g",
            "risk": "high",
            "workflow_extensions": {"requires": ["identity@1", "approval@1"]},
            "steps": [
                CP,
                POLICY,
                mutate(
                    approval={
                        "approver": {"kind": "human", "sender_check": ["directory_id"]}
                    }
                ),
            ],
        }
    }
    header_script = [
        {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain"), "respond": out(compliant=True)},
        {"expect": {"kind": "RequestApproval", "step": 2}, "respond": approve("d1")},
    ]
    add(
        "header_1_2_sender_check_needs_identities",
        "A catalog with no spec_version and a '# Standard version: 1.2.0' header"
        " targets 1.2 by its header alone: the approver's sender_check makes attested"
        " identities required, and a decision without them counts no approvers"
        " (F502, §5.17, §11.5).",
        header_catalog,
        header_script,
        {
            "kind": "Failed",
            "code": "F502",
            "action_records": [{"status": "rejected", "approval": {"approvers": []}}],
        },
        ["approval_decided"],
        header="1.2.0",
    )
    add(
        "header_null_sender_check_not_read",
        "The same catalog with no header targets no version: sender_check is not"
        " read (W604 at validation, as in 1.1), and the decision counts alice: the"
        " header, not the catalog, made the difference (§11.5).",
        header_catalog,
        header_script
        + [{"expect": inv("mutate", step=2), "respond": out(success=True)}],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"status": "executed", "approval": {"approvers": ["alice"]}}
            ],
        },
        ["approval_decided"],
    )
