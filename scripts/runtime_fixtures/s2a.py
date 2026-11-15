"""Runtime fixtures of workstream S2a (approval, deferral and run identity;
RFC-0006 Part A): the default approval request and its digest (§5.14),
approver identities (§5.17) and resumption of a deferred run (§5.14.1).

Define each with add(name, description, catalog, script, end, trace, ...),
the function of scripts/gen_runtime_fixtures.py; the building blocks are in
runtime_fixtures.helpers. Record and deferral `reason`s are not pinned here;
tests/test_runner.py asserts the "superseded" ones.
"""

from runtime_fixtures.helpers import (
    CP,
    POLICY,
    approve,
    inv,
    mutate,
    out,
    resume,
    st,
    wf,
)

HUMAN = {"kind": "human"}
DEFER = {"approver": HUMAN, "when_unattended": "defer_to_queue"}
INPUTS = {"target": "config", "operation": {"set": 1}}
NIGHTLY = {"kind": "standing_mandate", "mandate_ref": "m/nightly"}

ALICE = {
    "principal": "alice",
    "kind": "human",
    "role": "release-manager",
    "authenticated_by": "directory_id",
    "trust_class": "decision_person",
}
CAROL = dict(ALICE, principal="carol")
BOB = dict(ALICE, principal="bob", role="ops")
BOT = {"principal": "bot", "kind": "agent"}

CHECKPOINTED = [
    {"expect": inv("checkpoint"), "respond": out(checkpoint_id="cp1")},
    {"expect": inv("constrain"), "respond": out(compliant=True)},
]


def attested(d, identities, who=()):
    """An approval decision that attests its approvers (identity@1)."""
    decision = approve(d, who=who)
    decision["approver_identities"] = list(identities)
    return decision


def rejected(d):
    return {
        "kind": "Decision",
        "decision_id": d,
        "decision": "rejected",
        "approvers": ["alice"],
        "digest": "{{digest}}",
    }


def guarded(approval=None, requires=None, **kw):
    """checkpoint, constrain, then a mutate with `approval`, if any."""
    m = mutate()
    if approval is not None:
        m["approval"] = approval
    return {"w": wf([CP, POLICY, m], requires=requires, **kw)}


def register(add):
    """Add this workstream's fixtures."""
    _requests(add)
    _approvers(add)
    _resumption(add)


# ---------------------------------------------------------------------------
# The request and its digest (ACS-10, ACS-11, ACS-44)
# ---------------------------------------------------------------------------


def _requests(add):
    add(
        "approval_defaults_partial",
        "A partial approval field takes the default of each member it leaves out: the request is in session, shows the step's resolved inputs as an array and expires one hour after the request (STANDARD v1.2 §5.14).",
        guarded(
            {"approver": {"kind": "human", "role": "ops"}, "expires": "1h"},
            requires=["approval@1"],
        ),
        CHECKPOINTED
        + [
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 2,
                    "approver": {"kind": "human", "role": "ops"},
                    "mode": "in_session",
                    "shown": [INPUTS],
                    "expires_at": 3600000,
                },
                "respond": approve("d1"),
            },
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {
                    "status": "executed",
                    "approval": {"decision": "approved", "mode": "in_session"},
                }
            ],
        },
        ["approval_requested", "approval_decided"],
    )
    add(
        "approval_out_of_band_unattended",
        "An out_of_band mode does not change the unattended rule: a human approver is not asked in an unattended run, and when_unattended applies (here skip; §5.14).",
        guarded(
            {"approver": HUMAN, "mode": "out_of_band", "when_unattended": "skip"},
            requires=["approval@1"],
        ),
        CHECKPOINTED,
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [{"status": "rejected"}],
        },
        ["approval_unattended", "step_skipped"],
        attendance="unattended",
    )
    add(
        "approval_digest_any_case",
        "A decision's digest is compared with the request's without regard to the case of its hexadecimal letters (§5.14).",
        guarded(),
        CHECKPOINTED
        + [
            {
                "expect": {"kind": "RequestApproval", "step": 2},
                "respond": approve("d1", digest="{{digest_upper}}"),
            },
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [{"status": "executed"}],
        },
        ["approval_decided"],
    )
    observe = st(
        "observe",
        "o",
        input_bindings={"target": "t"},
        condition="${flag}",
    )
    m = mutate()
    m["approval"] = {"approver": HUMAN, "shows": ["${o.observation}", "${flag}"]}
    add(
        "approval_shows_unresolved",
        "A shows reference that resolves to nothing (here the output of a skipped step) is null in the shown values: one element per reference, in order (§5.14).",
        {
            "w": wf(
                [observe, CP, POLICY, m],
                inputs={"flag": {"type": "boolean", "required": True}},
                requires=["approval@1"],
            )
        },
        [
            {"expect": inv("checkpoint", step=1), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain", step=2), "respond": out(compliant=True)},
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 3,
                    "shown": [None, False],
                },
                "respond": approve("d1"),
            },
            {"expect": inv("mutate", step=3), "respond": out(success=True)},
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["step_skipped", "approval_requested"],
        inputs={"flag": False},
    )


# ---------------------------------------------------------------------------
# Approver identities (ACS-12)
# ---------------------------------------------------------------------------


def _approvers(add):
    both = ["approval@1", "identity@1"]
    two = {"kind": "human", "min_approvers": 2}
    managers = {"kind": "human", "role": "release-manager", "min_approvers": 2}

    def case(
        name,
        description,
        approver,
        decision,
        end,
        requires=both,
        spec="1.1",
        expect=None,
    ):
        add(
            name,
            description,
            guarded({"approver": approver}, requires=requires, spec_version=spec),
            CHECKPOINTED
            + [
                {
                    "expect": expect or {"kind": "RequestApproval", "step": 2},
                    "respond": decision,
                },
            ]
            + (
                [{"expect": inv("mutate", step=2), "respond": out(success=True)}]
                if end["kind"] == "Completed"
                else []
            ),
            end,
            ["approval_decided"],
        )

    case(
        "approver_identities_by_principal",
        "With identity@1, approvers are counted by principal: two identical identities for one principal are one approver, short of min_approvers 2 (STANDARD v1.2 §5.17).",
        two,
        attested("d1", [ALICE, ALICE]),
        {
            "kind": "Failed",
            "code": "F502",
            "action_records": [
                {
                    "status": "rejected",
                    "approval": {
                        "approvers": ["alice"],
                        "approver_identities": [ALICE],
                    },
                }
            ],
        },
    )
    case(
        "approver_identity_role",
        "An attested approver counts only if its role is the requested one: bob's ops role does not count toward a release-manager approval, and the record lists only the approver that counted (§5.17).",
        managers,
        attested("d1", [ALICE, BOB]),
        {
            "kind": "Failed",
            "code": "F502",
            "action_records": [
                {
                    "status": "rejected",
                    "approval": {
                        "approvers": ["alice"],
                        "approver_identities": [ALICE],
                    },
                }
            ],
        },
    )
    case(
        "approver_identity_role_met",
        "Two attested approvers holding the requested role meet min_approvers 2; the record lists their principals and identities (§5.17).",
        managers,
        attested("d1", [ALICE, CAROL]),
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {
                    "status": "executed",
                    "approval": {
                        "approvers": ["alice", "carol"],
                        "approver_identities": [ALICE, CAROL],
                    },
                }
            ],
        },
    )
    case(
        "approver_identity_kind",
        "For a human approver, an attested identity whose kind is not human does not count (§5.17).",
        HUMAN,
        attested("d1", [BOT]),
        {
            "kind": "Failed",
            "code": "F502",
            "action_records": [
                {
                    "status": "rejected",
                    "approval": {"approvers": [], "approver_identities": []},
                }
            ],
        },
    )
    case(
        "approver_sender_check_needs_identities",
        "In a workflow that targets 1.2, an approver's sender_check makes attested identities required: a decision without them counts no approvers (§5.17).",
        {"kind": "human", "sender_check": ["directory_id"]},
        approve("d1"),
        {
            "kind": "Failed",
            "code": "F502",
            "action_records": [{"status": "rejected", "approval": {"approvers": []}}],
        },
        spec="1.2",
    )
    case(
        "approver_sender_check_met",
        "In a workflow that targets 1.2, an identity authenticated by a listed mechanism and of an accepted trust class counts (§5.17).",
        {
            "kind": "human",
            "sender_check": ["directory_id"],
            "accept_trust_classes": ["decision_person"],
        },
        attested("d1", [ALICE]),
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"status": "executed", "approval": {"approvers": ["alice"]}}
            ],
        },
        spec="1.2",
    )
    case(
        "approver_sender_check_mismatch",
        "An identity authenticated by a mechanism sender_check does not list does not count (§5.17).",
        {"kind": "human", "sender_check": ["directory_id"]},
        attested("d1", [dict(ALICE, authenticated_by="session_id")]),
        {
            "kind": "Failed",
            "code": "F502",
            "action_records": [{"status": "rejected", "approval": {"approvers": []}}],
        },
        spec="1.2",
    )
    case(
        "approver_trust_class_mismatch",
        "An identity of a trust class accept_trust_classes does not list does not count (§5.17).",
        {"kind": "human", "accept_trust_classes": ["decision_person"]},
        attested("d1", [dict(ALICE, trust_class="colleague")]),
        {
            "kind": "Failed",
            "code": "F502",
            "action_records": [{"status": "rejected", "approval": {"approvers": []}}],
        },
        spec="1.2",
    )
    case(
        "approver_fields_ignored_1_1",
        "In a workflow that targets 1.1, the approver's sender_check is an unknown field, as in 1.1 (W604, W616): the request carries the approver as declared and the decision is counted by its approvers, unattested (§5.17, §11.5).",
        {"kind": "human", "sender_check": ["directory_id"]},
        approve("d1"),
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"status": "executed", "approval": {"approvers": ["alice"]}}
            ],
        },
        requires=["approval@1"],
        expect={
            "kind": "RequestApproval",
            "step": 2,
            "approver": {"kind": "human", "sender_check": ["directory_id"]},
        },
    )
    case(
        "approver_identities_without_identity_ext",
        "Without identity@1 a decision's approver_identities are ignored: approvers are counted as the host names them, and the record carries no identities (§5.17).",
        HUMAN,
        attested("d1", [BOT], who=("alice",)),
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"status": "executed", "approval": {"approvers": ["alice"]}}
            ],
        },
        requires=["approval@1"],
    )


# ---------------------------------------------------------------------------
# Resuming a deferred run (ACS-13, ACS-35)
# ---------------------------------------------------------------------------


def deferred_end(*deferred, **kw):
    """The terminal action of a run that ended deferred, as a script entry."""
    e = {"kind": "Completed", "outcome": "deferred", "deferred": list(deferred)}
    e.update(kw)
    return {"expect": e}


def queued_request(step, action_id, **kw):
    e = {"kind": "RequestApproval", "step": step, "queued_action_id": action_id}
    e.update(kw)
    return e


def _resumption(add):
    m = mutate(approval=DEFER)
    retrieve = st("retrieve", "r", input_bindings={"target": "config"})
    queued = {"w": wf([retrieve, CP, POLICY, m], requires=["approval@1"])}
    first = [
        {
            "expect": inv("retrieve", step=0),
            "respond": out(data="before", confidence=1),
        },
        {"expect": inv("checkpoint", step=1), "respond": out(checkpoint_id="cp1")},
        {"expect": inv("constrain", step=2), "respond": out(compliant=True)},
        deferred_end({"step": 3, "action_id": "run-1/w/3/0"}),
    ]
    add(
        "resume_deferred_attended",
        "A run that ended deferred is resumed attended: its queued step is asked afresh of a person, the request names the queued action, a checkpoint taken before the resumption authorises nothing after it, and the planned record is updated in place; the step that ran before the deferral is not asked again (STANDARD v1.2 §5.14.1).",
        queued,
        first
        + [
            resume(at=3600000),
            {
                "expect": queued_request(
                    3,
                    "run-1/w/3/0",
                    approver=HUMAN,
                    mode="in_session",
                    shown=[INPUTS],
                ),
                "respond": approve("d1"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 3},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {"expect": inv("mutate", step=3), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {
                    "action_id": "run-1/w/3/0",
                    "status": "executed",
                    "approval": {"decision": "approved"},
                }
            ],
        },
        ["run_resumed", "checkpoints_invalidated", "checkpoint_created"],
        attendance="unattended",
    )
    add(
        "resume_deferred_rejected",
        "A queued action whose resumed request is rejected fails its step (F502); the queued record becomes rejected (§5.14.1).",
        queued,
        first
        + [
            resume(at=3600000),
            {"expect": queued_request(3, "run-1/w/3/0"), "respond": rejected("d1")},
        ],
        {
            "kind": "Failed",
            "code": "F502",
            "action_records": [{"action_id": "run-1/w/3/0", "status": "rejected"}],
        },
        ["run_resumed"],
        attendance="unattended",
    )
    add(
        "resume_unattended_defers_again",
        "Resumed unattended, a queued step with a human approver is not asked: when_unattended applies again, the run ends deferred, and the queued action keeps its planned record (§5.14.1).",
        queued,
        first + [resume(attendance="unattended", at=3600000)],
        {
            "kind": "Completed",
            "outcome": "deferred",
            "deferred": [{"step": 3, "action_id": "run-1/w/3/0"}],
            "action_records": [{"action_id": "run-1/w/3/0", "status": "planned"}],
        },
        ["run_resumed", "step_deferred"],
        attendance="unattended",
    )
    add(
        "resume_new_actor",
        "A deferred run may be resumed under a new actor (§5.17): the trace records the change, and the queued record, updated in place, carries the new actor.",
        queued,
        first
        + [
            resume(at=3600000, actor={"principal": "agent-b", "kind": "agent"}),
            {"expect": queued_request(3, "run-1/w/3/0"), "respond": approve("d1")},
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
                    "action_id": "run-1/w/3/0",
                    "status": "executed",
                    "actor": "agent",
                    "actor_identity": {"principal": "agent-b"},
                }
            ],
        },
        ["run_resumed"],
        attendance="unattended",
        actor_identity={"principal": "agent-a", "kind": "agent"},
    )

    # Steps that ran ahead of a deferral.
    verify_r = st(
        "verify",
        "v",
        input_bindings={"target": "${r.data: string}", "conditions": ["applied"]},
    )
    add(
        "resume_reruns_read_ahead",
        "A step that ran ahead of a deferral and that a re-entered step reads runs again, in step order, after the queued mutation: the verify reads the world after the change (§5.14.1).",
        {
            "w": wf(
                [CP, POLICY, mutate(approval=DEFER), retrieve, verify_r],
                requires=["approval@1"],
            )
        },
        [
            {"expect": inv("checkpoint", step=0), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain", step=1), "respond": out(compliant=True)},
            {
                "expect": inv("retrieve", step=3),
                "respond": out(data="before", confidence=1),
            },
            deferred_end({"step": 2}, {"step": 4}),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
            {
                "expect": inv("retrieve", step=3),
                "respond": out(data="after", confidence=1),
            },
            {
                "expect": inv(
                    "verify",
                    step=4,
                    inputs={"target": "after", "conditions": ["applied"]},
                ),
                "respond": out(passed=True, confidence=1),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"r": {"data": "after"}},
        },
        ["run_resumed"],
        attendance="unattended",
    )
    observe = st("observe", "o", input_bindings={"target": "elsewhere"})
    verify_m = st(
        "verify",
        "v",
        input_bindings={"target": "${m.success: boolean}", "conditions": ["applied"]},
    )
    add(
        "resume_keeps_unread_ahead",
        "A step that ran ahead of a deferral and that no re-entered step reads keeps its output: it is not run again (§5.14.1).",
        {
            "w": wf(
                [CP, POLICY, mutate(approval=DEFER), observe, verify_m],
                requires=["approval@1"],
            )
        },
        [
            {"expect": inv("checkpoint", step=0), "respond": out(checkpoint_id="cp1")},
            {"expect": inv("constrain", step=1), "respond": out(compliant=True)},
            {
                "expect": inv("observe", step=3),
                "respond": out(observation={"n": 1}, confidence=1),
            },
            deferred_end({"step": 2}, {"step": 4}),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
            {
                "expect": inv("verify", step=4),
                "respond": out(passed=True, confidence=1),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"o": {"observation": {"n": 1}}},
        },
        ["run_resumed"],
        attendance="unattended",
    )
    bound = mutate(approval=DEFER)
    bound["input_bindings"] = dict(INPUTS, checkpoint_id="${cp.checkpoint_id}")
    add(
        "resume_reruns_bound_checkpoint",
        "Safe Mutation resumed: the checkpoint step whose checkpoint the resumption invalidated runs again, because the queued mutate binds its id, so the mutate binds and uses the new checkpoint (§5.14.1, §12.5).",
        {"w": wf([POLICY, CP, bound], requires=["approval@1"])},
        [
            {"expect": inv("constrain", step=0), "respond": out(compliant=True)},
            {"expect": inv("checkpoint", step=1), "respond": out(checkpoint_id="cp1")},
            deferred_end({"step": 2}),
            resume(at=3600000),
            {"expect": inv("checkpoint", step=1), "respond": out(checkpoint_id="cp2")},
            {
                "expect": queued_request(
                    2, "run-1/w/2/0", shown=[dict(INPUTS, checkpoint_id="cp2")]
                ),
                "respond": approve("d1"),
            },
            {
                "expect": inv(
                    "mutate", step=2, inputs=dict(INPUTS, checkpoint_id="cp2")
                ),
                "respond": out(success=True),
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["checkpoints_invalidated", "checkpoint_created", "checkpoint_consumed"],
        attendance="unattended",
    )

    # A standing mandate's queued step.
    mandated = guarded(
        {"approver": NIGHTLY, "when_unattended": "defer_to_queue"},
        requires=["approval@1"],
    )
    unavailable = {
        "kind": "Decision",
        "decision_id": "d0",
        "decision": "unavailable",
        "approvers": [],
        "digest": "{{digest}}",
    }
    mandate_first = CHECKPOINTED + [
        {
            "expect": {"kind": "RequestApproval", "step": 2, "approver": NIGHTLY},
            "respond": unavailable,
        },
        deferred_end({"step": 2, "action_id": "run-1/w/2/0"}),
    ]
    mandate_tail = [
        {
            "expect": {"kind": "CreateCheckpoint", "step": 2},
            "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
        },
        {"expect": inv("mutate", step=2), "respond": out(success=True)},
    ]
    add(
        "resume_unattended_mandate",
        "Resumed unattended, a queued step whose approver is a standing mandate asks the mandate again, and the request names the queued action (§5.14.1).",
        mandated,
        mandate_first
        + [
            resume(attendance="unattended", at=3600000),
            {
                "expect": queued_request(2, "run-1/w/2/0", approver=NIGHTLY),
                "respond": approve("d1", who=("nightly",)),
            },
        ]
        + mandate_tail,
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {
                    "action_id": "run-1/w/2/0",
                    "status": "executed",
                    "approval": {"mandate_ref": "m/nightly", "approvers": ["nightly"]},
                }
            ],
        },
        ["run_resumed"],
        attendance="unattended",
    )
    add(
        "resume_asks_person_for_mandate",
        "Resumed attended, a queued step whose approver is a standing mandate is asked of a person: the request's approver is human and names no mandate_ref (§5.14.1).",
        mandated,
        mandate_first
        + [
            resume(at=3600000),
            {
                "expect": queued_request(2, "run-1/w/2/0", approver=HUMAN),
                "respond": approve("d1"),
            },
        ]
        + mandate_tail,
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {
                    "action_id": "run-1/w/2/0",
                    "status": "executed",
                    "approval": {"mandate_ref": None, "approvers": ["alice"]},
                }
            ],
        },
        ["run_resumed"],
        attendance="unattended",
    )

    # A nested run that ended deferred.
    nested = {
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
        "child": wf(
            [retrieve, CP, POLICY, mutate(approval=DEFER)], requires=["approval@1"]
        ),
    }
    add(
        "resume_nested_continues",
        "A deferred invoke step whose nested run ended deferred continues that nested run: no step of it or of the parent runs again, the queued step is asked, and then the steps that waited for the invoke step run (§5.14.1).",
        nested,
        [
            {
                "expect": inv("retrieve", frame=["w", "child"]),
                "respond": out(data="x", confidence=1),
            },
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
            deferred_end(
                {"frame": ["w", "child"], "step": 3},
                {"frame": ["w"], "step": 0},
                {"frame": ["w"], "step": 2},
            ),
            resume(at=3600000),
            {
                "expect": queued_request(3, "run-1/w/child/3/0", frame=["w", "child"]),
                "respond": approve("d1"),
            },
            {
                "expect": {
                    "kind": "CreateCheckpoint",
                    "step": 3,
                    "frame": ["w", "child"],
                },
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {
                "expect": inv("mutate", frame=["w", "child"]),
                "respond": out(success=True),
            },
            {
                "expect": inv("verify", frame=["w"], step=2),
                "respond": out(passed=True, confidence=1),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/child/3/0", "status": "executed"}
            ],
        },
        ["run_resumed", "invoke_resumed", "invoke_returned"],
        attendance="unattended",
    )

    # A deferred handler.
    def escalating(handler_first, loop_on_mutate=False):
        mm = mutate(approval=DEFER)
        if loop_on_mutate:
            mm["failure_modes"] = [
                {
                    "condition": "the change failed",
                    "on_error": "R402",
                    "action": "request_more_context",
                    "recovery": {"goto_step": "m", "max_loops": 1},
                }
            ]
        page = st(
            "invoke",
            "page",
            handler=True,
            workflow_id="oncall",
            input_bindings={
                "workflow": "oncall",
                "input": {
                    "why": "observation failed",
                    "applied": "${m.success: boolean}",
                },
            },
        )
        o = st(
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
        )
        steps = (
            [CP, POLICY, page, mm, o] if handler_first else [CP, POLICY, mm, o, page]
        )
        return {
            "w": wf(steps, requires=["approval@1", "recovery@1"]),
            "oncall": wf(
                [st("inquire", "q", input_bindings={"ambiguous_input": "${why}"})],
                inputs={
                    "why": {"type": "string", "required": True},
                    "applied": {"type": "boolean"},
                },
            ),
        }

    paged = {
        "expect": inv("inquire", frame=["w", "oncall"]),
        "respond": out(questions=[], ambiguity_analysis={}, confidence=1),
    }
    down = {"kind": "Error", "code": "R402", "message": "down"}
    add(
        "resume_deferred_handler",
        "A run whose handler was deferred is resumed: the queued step runs first, then the handler with the escalation's cause, and the run ends escalated (§5.14.1).",
        escalating(handler_first=False),
        CHECKPOINTED
        + [
            {"expect": inv("observe", step=3), "respond": down},
            deferred_end({"step": 2}, {"step": 4}, cause="R402"),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
            paged,
        ],
        {
            "kind": "Completed",
            "outcome": "escalated",
            "cause": "R402",
            "deferred": [],
            "action_records": [{"action_id": "run-1/w/2/0", "status": "executed"}],
        },
        ["run_resumed", "invoke_started"],
        attendance="unattended",
    )
    add(
        "resume_deferred_handler_loop",
        "A recovery loop during a resumption returns the run to normal flow: the deferred handler below the loop's target is superseded and its escalation dropped, the step is asked again with no queued action, and the run completes (§5.14.1).",
        escalating(handler_first=True, loop_on_mutate=True),
        CHECKPOINTED
        + [
            {"expect": inv("observe", step=4), "respond": down},
            deferred_end({"step": 3}, {"step": 2}, cause="R402"),
            resume(at=3600000),
            {"expect": queued_request(3, "run-1/w/3/0"), "respond": approve("d1")},
            {
                "expect": {"kind": "CreateCheckpoint", "step": 3},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp2"},
            },
            {"expect": inv("mutate", step=3), "respond": down},
            {
                "expect": {"kind": "RequestApproval", "step": 3},
                "respond": approve("d2"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 3},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp3"},
            },
            {"expect": inv("mutate", step=3), "respond": out(success=True)},
            {
                "expect": inv("observe", step=4),
                "respond": out(observation={}, confidence=1),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "cause": None,
            "deferred": [],
            "action_records": [{"status": "failed"}, {"status": "executed"}],
        },
        ["run_resumed", "loop"],
        attendance="unattended",
    )

    # Loops, failures, skips and gates during a resumption.
    verify_loop = st(
        "verify",
        "v",
        input_bindings={"target": "${m1.success: boolean}", "conditions": ["applied"]},
        failure_modes=[
            {
                "condition": "the check failed",
                "on_error": "R402",
                "action": "request_more_context",
                "recovery": {"goto_step": "m1", "max_loops": 1},
            }
        ],
    )
    cp_answer = {"kind": "Checkpoint", "checkpoint_id": "cp2"}
    add(
        "resume_loop_supersedes",
        "A recovery loop during a resumption to a step before a queued one supersedes that queued action; the steps from the loop's target run as in normal flow, asked afresh (§5.14.1).",
        {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate("m1", approval=DEFER),
                    verify_loop,
                    mutate("m2", approval=DEFER),
                ],
                requires=["approval@1"],
            )
        },
        CHECKPOINTED
        + [
            deferred_end({"step": 2}, {"step": 3}, {"step": 4}),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
            {"expect": inv("verify", step=3), "respond": down},
            {
                "expect": {"kind": "RequestApproval", "step": 2},
                "respond": approve("d2"),
            },
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
            {
                "expect": inv("verify", step=3),
                "respond": out(passed=True, confidence=1),
            },
            {
                "expect": {"kind": "RequestApproval", "step": 4},
                "respond": approve("d3"),
            },
            {"expect": {"kind": "CreateCheckpoint", "step": 4}, "respond": cp_answer},
            {"expect": inv("mutate", step=4), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "executed"},
                {"action_id": "run-1/w/4/1", "status": "rejected"},
                {"status": "executed"},
                {"status": "executed"},
            ],
        },
        ["run_resumed", "loop"],
        attendance="unattended",
    )
    two_queued = {
        "w": wf(
            [CP, POLICY, mutate("m1", approval=DEFER), mutate("m2", approval=DEFER)],
            requires=["approval@1"],
        )
    }
    add(
        "resume_failure_keeps_queue",
        "A resumed run that fails leaves the queued steps it did not reach deferred, listed with planned records; the run cannot be resumed, so they are abandoned (§5.14.1).",
        two_queued,
        CHECKPOINTED
        + [
            deferred_end({"step": 2}, {"step": 3}),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": down},
        ],
        {
            "kind": "Failed",
            "code": "R402",
            "step": 2,
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "failed"},
                {"action_id": "run-1/w/3/1", "status": "planned"},
            ],
            "deferred": [{"step": 3, "action_id": "run-1/w/3/1"}],
        },
        ["run_resumed", "run_failed"],
        attendance="unattended",
    )
    m2 = mutate("m2", condition="${m1.success} == false", skip_if_false=True)
    add(
        "resume_skipped_supersedes",
        "A re-entered queued step whose condition is now false is skipped and supersedes its queued action (§5.14.1).",
        {
            "w": wf(
                [CP, POLICY, mutate("m1", approval=DEFER), m2],
                requires=["approval@1"],
            )
        },
        CHECKPOINTED
        + [
            deferred_end({"step": 2}, {"step": 3}),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "executed"},
                {"action_id": "run-1/w/3/1", "status": "rejected"},
            ],
        },
        ["run_resumed", "step_skipped"],
        attendance="unattended",
    )
    m1_end = mutate(
        "m1",
        approval=DEFER,
        gates=[{"when": "${m1.success} == true", "action": "end", "phase": "after"}],
    )
    add(
        "resume_gate_end_supersedes",
        "A gate end during a resumption ends the run before the queued steps after it, whose queued actions are superseded (§5.14.1).",
        {
            "w": wf(
                [CP, POLICY, m1_end, mutate("m2", approval=DEFER)],
                requires=["approval@1"],
            )
        },
        CHECKPOINTED
        + [
            deferred_end({"step": 2}, {"step": 3}),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "ended": {"step": 2},
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "executed"},
                {"action_id": "run-1/w/3/1", "status": "rejected"},
            ],
        },
        ["run_resumed", "run_ended"],
        attendance="unattended",
    )
