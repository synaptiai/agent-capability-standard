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
    err,
    inv,
    mutate,
    out,
    resume,
    st,
    tick,
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
        "A partial approval field takes the default of each member it leaves out: the request is in session, shows the step's resolved inputs as an array and expires one hour after the request, which is made a second after the run started (STANDARD v1.2 §5.14).",
        guarded(
            {"approver": {"kind": "human", "role": "ops"}, "expires": "1h"},
            requires=["approval@1"],
        ),
        [
            CHECKPOINTED[0],
            dict(CHECKPOINTED[1], at=1000),
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 2,
                    "approver": {"kind": "human", "role": "ops"},
                    "mode": "in_session",
                    "shown": [INPUTS],
                    "expires_at": 3601000,
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
        "A recovery loop back to a re-entered queued step whose call failed runs that step again and then goes on with the resumption: the step carried its queued action out, so the second request names no queued action and its pass has a record of its own beside the failed one; the step that escalated in the first run is not run again, and the deferred handler still runs last, with the escalation's cause (§5.14.1).",
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
                "expect": {"kind": "RequestApproval", "step": 3, "approver": HUMAN},
                "absent": ["queued_action_id"],
                "respond": approve("d2"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 3},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp3"},
            },
            {"expect": inv("mutate", step=3), "respond": out(success=True)},
            paged,
        ],
        {
            "kind": "Completed",
            "outcome": "escalated",
            "cause": "R402",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/3/0", "status": "failed", "code": "R402"},
                {"action_id": "run-1/w/3/1", "status": "executed"},
            ],
        },
        ["run_resumed", "loop", "invoke_started"],
        attendance="unattended",
    )

    # A nested queue that waits through two resumptions: the first escalates
    # before the invoke step continues its nested run, and the handler's own
    # nested run defers, so the run ends deferred again.
    m0 = mutate(
        "m0",
        approval={"approver": NIGHTLY, "when_unattended": "defer_to_queue"},
        failure_modes=[
            {
                "condition": "the change failed",
                "on_error": "R402",
                "action": "escalate",
                "recovery": {"goto_step": "page"},
            }
        ],
    )
    invoke_child = st(
        "invoke",
        "i",
        workflow_id="child",
        after_deferral="run",
        input_bindings={"workflow": "child"},
    )
    page = st(
        "invoke",
        "page",
        handler=True,
        workflow_id="oncall",
        input_bindings={"workflow": "oncall", "input": {"why": "the change failed"}},
    )
    queued_child = wf([CP, POLICY, mutate(approval=DEFER)], requires=["approval@1"])
    oncall = dict(queued_child, inputs={"why": {"type": "string", "required": True}})
    twice = {
        "w": wf(
            [CP, POLICY, m0, invoke_child, page], requires=["approval@1", "recovery@1"]
        ),
        "child": queued_child,
        "oncall": oncall,
    }
    child = ["w", "child"]
    paging = ["w", "oncall"]
    nested_cp = {"kind": "Checkpoint", "checkpoint_id": "cp9"}
    add(
        "resume_nested_queue_after_escalation",
        "A resumption that escalates before an invoke step continues its nested run puts the step back among the deferred; when the run ends deferred again (here because the handler's own nested run deferred), the next resumption continues that nested run with its queued action intact, then the handler's (§5.14.1).",
        twice,
        CHECKPOINTED
        + [
            {
                "expect": {"kind": "RequestApproval", "step": 2, "approver": NIGHTLY},
                "respond": unavailable,
            },
            {
                "expect": inv("checkpoint", frame=child),
                "respond": out(checkpoint_id="cp2"),
            },
            {"expect": inv("constrain", frame=child), "respond": out(compliant=True)},
            deferred_end({"step": 2}, {"frame": child, "step": 2}, {"step": 3}),
            resume(attendance="unattended", at=3600000),
            {
                "expect": queued_request(2, "run-1/w/2/0", approver=NIGHTLY),
                "respond": approve("d1", who=("nightly",)),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp4"},
            },
            {"expect": inv("mutate", step=2), "respond": down},
            {
                "expect": inv("checkpoint", frame=paging),
                "respond": out(checkpoint_id="cp3"),
            },
            {"expect": inv("constrain", frame=paging), "respond": out(compliant=True)},
            deferred_end(
                {"frame": child, "step": 2},
                {"step": 3},
                {"frame": paging, "step": 2},
                {"step": 4},
                cause="R402",
            ),
            resume(at=7200000),
            {
                "expect": queued_request(
                    2, "run-1/w/child/2/1", frame=child, approver=HUMAN
                ),
                "respond": approve("d2"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2, "frame": child},
                "respond": nested_cp,
            },
            {"expect": inv("mutate", frame=child), "respond": out(success=True)},
            {
                "expect": queued_request(2, "run-1/w/oncall/2/2", frame=paging),
                "respond": approve("d3"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2, "frame": paging},
                "respond": nested_cp,
            },
            {"expect": inv("mutate", frame=paging), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "escalated",
            "cause": "R402",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "failed"},
                {"action_id": "run-1/w/child/2/1", "status": "executed"},
                {"action_id": "run-1/w/oncall/2/2", "status": "executed"},
            ],
        },
        ["run_resumed", "invoke_resumed", "escalated"],
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
        "resume_loop_goes_on",
        "A recovery loop during a resumption runs the steps from its target to the step that looped again, as in normal flow, and the resumption then goes on: the queued step after the loop keeps its queued action. A step whose queued action was carried out runs again as a new action, asked with no queued action (§5.14.1).",
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
            {"expect": queued_request(4, "run-1/w/4/1"), "respond": approve("d3")},
            {"expect": {"kind": "CreateCheckpoint", "step": 4}, "respond": cp_answer},
            {"expect": inv("mutate", step=4), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "executed"},
                {"action_id": "run-1/w/4/1", "status": "executed"},
                {"action_id": "run-1/w/2/2", "status": "executed"},
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

    # A queued step keeps its queued action until it goes on or carries it
    # out (calls its capability, whatever the result): a recovery loop that
    # runs it again before then and a re-ask after a recheck continue it;
    # once it has called its capability, a loop runs it as a new action. A
    # loop runs only that step again.
    paging_task = st(
        "delegate",
        "d",
        after_deferral="run",
        input_bindings={"task": {"page": "oncall"}, "agent": "pager"},
    )
    refused_again = mutate(
        approval=DEFER,
        failure_modes=[
            {
                "condition": "the change was refused",
                "on_error": "F502",
                "action": "request_more_context",
                "recovery": {"goto_step": "m", "max_loops": 1},
            }
        ],
    )

    def paged_first(queued):
        """The first run delegates and defers the mutate, then resumes."""
        return CHECKPOINTED + [
            {
                "expect": inv("delegate", step=3),
                "respond": out(task_id="t1", accepted=True),
            },
            deferred_end({"step": 2, "action_id": queued}),
            resume(at=3600000),
        ]

    add(
        "resume_loop_keeps_queue",
        "A recovery loop back to a re-entered queued step that has not called its capability (its request was rejected, F502) runs that step again and nothing after it: the second request names the same queued action and is put to a person, the record is updated in place again, and the step that declares after_deferral: run, which ran in the first run, does not delegate again (§5.14.1).",
        {"w": wf([CP, POLICY, refused_again, paging_task], requires=["approval@1"])},
        paged_first("run-1/w/2/0")
        + [
            {
                "expect": queued_request(2, "run-1/w/2/0", approver=HUMAN),
                "respond": rejected("d1"),
            },
            {
                "expect": queued_request(2, "run-1/w/2/0", approver=HUMAN),
                "respond": approve("d2"),
            },
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "outputs": {"d": {"task_id": "t1"}},
            "action_records": [
                {
                    "action_id": "run-1/w/2/0",
                    "status": "executed",
                    "approval": {"decision_id": "d2"},
                }
            ],
        },
        ["run_resumed", "loop"],
        attendance="unattended",
    )
    retried = mutate(
        approval=DEFER,
        failure_modes=[
            {
                "condition": "the change failed",
                "on_error": "R402",
                "action": "request_more_context",
                "recovery": {"goto_step": "m", "max_loops": 1},
            }
        ],
    )

    def failed_call(queued):
        """Resumed: the queued mutate's call fails, a loop runs it again."""
        return paged_first(queued) + [
            {
                "expect": queued_request(2, queued, approver=HUMAN),
                "respond": approve("d1"),
            },
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {
                "expect": inv("mutate", step=2, idempotency_key="run-1:7"),
                "respond": err("R402", "applied half the change, then failed"),
            },
            {
                "expect": {"kind": "RequestApproval", "step": 2, "approver": HUMAN},
                "absent": ["queued_action_id"],
                "respond": approve("d2"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp3"},
            },
            {
                "expect": inv("mutate", step=2, idempotency_key="run-1:10"),
                "respond": out(success=True),
            },
        ]

    first_pass = {
        "action_id": "run-1/w/2/0",
        "status": "failed",
        "code": "R402",
        "idempotency_key": "run-1:7",
        "checkpoint_id": "cp2",
        "approval": {"decision_id": "d1"},
    }
    second_pass = {
        "status": "executed",
        "capability": "mutate",
        "idempotency_key": "run-1:10",
        "checkpoint_id": "cp3",
        "approval": {"decision_id": "d2"},
    }
    add(
        "resume_failed_call_then_loop",
        "A re-entered queued step whose call fails has carried its queued action out, whatever the result: a recovery loop that runs it again asks for a new action, whose request names no queued action, and writes a record of its own. The queued record keeps the failed pass, with its decision, checkpoint and idempotency key; the new one the next pass's. The step that declares after_deferral: run, which ran in the first run, does not delegate again (§5.14.1, §6.4).",
        {"w": wf([CP, POLICY, retried, paging_task], requires=["approval@1"])},
        failed_call("run-1/w/2/0"),
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "outputs": {"d": {"task_id": "t1"}},
            "action_records": [first_pass, dict(second_pass, action_id="run-1/w/2/1")],
        },
        ["run_resumed", "loop"],
        attendance="unattended",
    )
    add(
        "resume_failed_call_then_loop_actions",
        "In record mode actions, a re-entered queued step whose call fails and that a recovery loop runs again has one record for each pass: the queued record, failed with the first decision and key, and a new one for the loop's pass (§5.14.1, §6.4).",
        {"w": wf([CP, POLICY, retried, paging_task], requires=["approval@1"])},
        failed_call("run-1/w/2/2"),
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {"capability": "checkpoint", "status": "executed"},
                {"capability": "constrain", "status": "executed"},
                dict(first_pass, action_id="run-1/w/2/2"),
                {"capability": "delegate", "status": "executed"},
                dict(second_pass, action_id="run-1/w/2/4"),
            ],
        },
        ["run_resumed", "loop"],
        attendance="unattended",
        records="actions",
    )
    # Every way a step performs its capability carries its queued action
    # out: starting its nested run, waiting for its event, evaluating its
    # quorum. Each, failing and looped back to, asks for a new action.
    looped = {
        "condition": "it failed",
        "on_error": ["R401", "R402", "F504"],
        "action": "request_more_context",
        "recovery": {"goto_step": "x", "max_loops": 1},
    }
    nested_fails = st(
        "invoke",
        "x",
        approval=DEFER,
        requires_approval=True,
        workflow_id="child",
        input_bindings={"workflow": "child"},
        failure_modes=[looped],
    )
    child = wf([st("retrieve", "r", input_bindings={"target": "config"})])
    add(
        "resume_failed_invoke_then_loop",
        "A re-entered queued invoke step carries its queued action out when its nested run starts: a nested run that fails, looped back to, asks for a new action with a record of its own beside the failed one (§5.14.1).",
        {
            "w": wf([nested_fails], requires=["approval@1"]),
            "child": child,
        },
        [
            deferred_end({"step": 0, "action_id": "run-1/w/0/0"}),
            resume(at=3600000),
            {"expect": queued_request(0, "run-1/w/0/0"), "respond": approve("d1")},
            {"expect": inv("retrieve", frame=["w", "child"]), "respond": down},
            {
                "expect": {"kind": "RequestApproval", "step": 0},
                "absent": ["queued_action_id"],
                "respond": approve("d2"),
            },
            {
                "expect": inv("retrieve", frame=["w", "child"]),
                "respond": out(data=[1], confidence=1),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/0/0", "status": "failed", "code": "R402"},
                {"action_id": "run-1/w/0/1", "status": "executed"},
            ],
        },
        ["run_resumed", "loop"],
        attendance="unattended",
    )
    waits = st(
        "receive",
        "x",
        approval=DEFER,
        requires_approval=True,
        timeout="1h",
        wait={"event_type": "job.done"},
        failure_modes=[looped],
    )
    add(
        "resume_failed_wait_then_loop",
        "A re-entered queued step that waits for its event carries its queued action out when the wait starts: a wait that times out, looped back to, asks for a new action with a record of its own beside the failed one (§5.14.1).",
        {"w": wf([waits], requires=["approval@1", "wait@1"])},
        [
            deferred_end({"step": 0, "action_id": "run-1/w/0/0"}),
            resume(at=3600000),
            {"expect": queued_request(0, "run-1/w/0/0"), "respond": approve("d1")},
            {"expect": {"kind": "AwaitEvent", "step": 0, "deadline": 7200000}},
            tick(7200001),
            {
                "expect": {"kind": "RequestApproval", "step": 0},
                "absent": ["queued_action_id"],
                "respond": approve("d2"),
            },
            {
                "expect": {"kind": "AwaitEvent", "step": 0},
                "respond": {"kind": "Event", "event": {"event_type": "job.done"}},
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/0/0", "status": "failed", "code": "R401"},
                {"action_id": "run-1/w/0/1", "status": "executed"},
            ],
        },
        ["run_resumed", "loop"],
        attendance="unattended",
    )
    quorum_gate = st(
        "constrain",
        "x",
        approval=DEFER,
        requires_approval=True,
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
        failure_modes=[looped],
    )
    reviewers = [
        st(
            "delegate",
            name,
            input_bindings={"task": {"diff": "${change}"}, "agent": agent},
        )
        for name, agent in (("ra", "a"), ("rb", "b"))
    ]
    verdicts = st("receive", "verdicts", input_bindings={"accept_from": ["a", "b"]})
    add(
        "resume_failed_quorum_then_loop",
        "A re-entered queued quorum step carries its queued action out when the executor evaluates its quorum: a quorum that is not met (F504), looped back to, asks for a new action with a record of its own beside the failed one (§5.14.1, §5.16).",
        {
            "w": wf(
                [*reviewers, verdicts, quorum_gate],
                inputs={"change": {"type": "string", "required": True}},
                requires=["approval@1", "delegation@1", "quorum@1"],
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
                        {
                            "reviewer_id": "b",
                            "value": "request_changes",
                            "pinned": "c1",
                        },
                    ]
                ),
            },
            deferred_end({"step": 3, "action_id": "run-1/w/3/0"}),
            resume(at=3600000),
            {"expect": queued_request(3, "run-1/w/3/0"), "respond": approve("d1")},
            {
                "expect": {"kind": "RequestApproval", "step": 3},
                "absent": ["queued_action_id"],
                "respond": approve("d2"),
            },
        ],
        {
            "kind": "Failed",
            "code": "R404",
            "action_records": [
                {"action_id": "run-1/w/3/0", "status": "failed", "code": "F504"},
                {"action_id": "run-1/w/3/1", "status": "failed", "code": "F504"},
            ],
        },
        ["run_resumed", "quorum", "loop", "recovery_exhausted"],
        inputs={"change": "c1"},
        attendance="unattended",
    )
    rechecked = guarded(
        {
            "approver": NIGHTLY,
            "when_unattended": "defer_to_queue",
            "recheck": {"source": "${policy}", "on_change": "reask"},
        },
        requires=["approval@1"],
    )
    changed = {"kind": "Current", "value": {"compliant": False}}
    add(
        "resume_recheck_reask",
        "Resumed attended, a queued step whose recheck sees its source change is asked again of a person, not of its standing mandate, and the request names the same queued action; the decision lands on the queued record, updated in place, which ends executed (§5.14.1).",
        rechecked,
        mandate_first
        + [
            resume(at=3600000),
            {
                "expect": queued_request(2, "run-1/w/2/0", approver=HUMAN),
                "respond": approve("d1"),
            },
            {"expect": {"kind": "RecheckSource", "step": 2}, "respond": changed},
            {
                "expect": queued_request(
                    2,
                    "run-1/w/2/0",
                    approver=HUMAN,
                    shown=[
                        INPUTS,
                        {
                            "recheck": {
                                "previous": {"compliant": True},
                                "current": {"compliant": False},
                            }
                        },
                    ],
                ),
                "respond": approve("d2"),
            },
            {"expect": {"kind": "RecheckSource", "step": 2}, "respond": changed},
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
        ["run_resumed", "recheck"],
        attendance="unattended",
    )

    # A loop supersedes only what it runs again.
    looping_observe = st(
        "observe",
        "o",
        input_bindings={"target": "elsewhere"},
        failure_modes=[
            {
                "condition": "the observation failed",
                "on_error": "R402",
                "action": "request_more_context",
                "recovery": {"goto_step": "m1", "max_loops": 1},
            }
        ],
    )
    m2_reads = mutate("m2", approval=DEFER)
    m2_reads["input_bindings"] = {
        "target": "config",
        "operation": "${o.observation: object}",
    }
    add(
        "resume_loop_supersedes",
        "A recovery loop during an unattended resumption supersedes only what it runs again: the queued step it runs again, deferred again earlier in the resumption, gets a new queued action, and the queued step after the loop keeps its own (§5.14.1).",
        {
            "w": wf(
                [CP, POLICY, mutate("m1", approval=DEFER), looping_observe, m2_reads],
                requires=["approval@1"],
            )
        },
        CHECKPOINTED
        + [
            {
                "expect": inv("observe", step=3),
                "respond": out(observation={"n": 1}, confidence=1),
            },
            deferred_end(
                {"step": 2, "action_id": "run-1/w/2/0"},
                {"step": 4, "action_id": "run-1/w/4/1"},
            ),
            resume(attendance="unattended", at=3600000),
            {"expect": inv("observe", step=3), "respond": down},
            {
                "expect": inv("observe", step=3),
                "respond": out(observation={"n": 2}, confidence=1),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "deferred",
            "deferred": [
                {"step": 2, "action_id": "run-1/w/2/2"},
                {"step": 4, "action_id": "run-1/w/4/1"},
            ],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "rejected"},
                {"action_id": "run-1/w/4/1", "status": "planned"},
                {"action_id": "run-1/w/2/2", "status": "planned"},
            ],
        },
        ["run_resumed", "loop", "step_deferred"],
        attendance="unattended",
    )

    # The queued actions a resumption supersedes, and those it leaves
    # deferred.
    failing_invoke = st(
        "invoke",
        "i",
        workflow_id="child",
        after_deferral="run",
        input_bindings={"workflow": "child"},
        failure_modes=[
            {
                "condition": "the nested run failed",
                "on_error": "R402",
                "action": "escalate",
                "recovery": {"goto_step": "page"},
            }
        ],
    )
    page_after_m0 = st(
        "invoke",
        "page",
        handler=True,
        workflow_id="oncall",
        input_bindings={
            "workflow": "oncall",
            "input": {
                "why": "the nested run failed",
                "applied": "${m0.success: boolean}",
            },
        },
    )
    failing_child = wf(
        [
            CP,
            POLICY,
            mutate(approval=DEFER),
            st(
                "retrieve",
                "r",
                after_deferral="run",
                input_bindings={"target": "config"},
            ),
        ],
        requires=["approval@1"],
    )
    pager = escalating(handler_first=False)["oncall"]
    add(
        "resume_nested_failure_supersedes",
        "A nested run that deferred a step and then failed under an invoke step that runs after a deferral escalates to a handler, which is deferred; when the run resumes, the nested run's queued action is superseded, because the nested run it was queued in failed, and the handler runs last (§5.14.1).",
        {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate("m0", approval=DEFER),
                    failing_invoke,
                    page_after_m0,
                ],
                requires=["approval@1", "recovery@1"],
            ),
            "child": failing_child,
            "oncall": pager,
        },
        CHECKPOINTED
        + [
            {
                "expect": inv("checkpoint", frame=["w", "child"]),
                "respond": out(checkpoint_id="cp5"),
            },
            {
                "expect": inv("constrain", frame=["w", "child"]),
                "respond": out(compliant=True),
            },
            {"expect": inv("retrieve", frame=["w", "child"]), "respond": down},
            deferred_end(
                {"step": 2, "action_id": "run-1/w/2/0"},
                {"frame": ["w", "child"], "step": 2, "action_id": "run-1/w/child/2/1"},
                {"step": 4},
                cause="R402",
            ),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
            paged,
        ],
        {
            "kind": "Completed",
            "outcome": "escalated",
            "cause": "R402",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "executed"},
                {"action_id": "run-1/w/child/2/1", "status": "rejected"},
            ],
        },
        ["run_resumed", "escalated", "invoke_started"],
        attendance="unattended",
    )
    escalates = [
        {
            "condition": "it failed",
            "on_error": "R402",
            "action": "escalate",
            "recovery": {"goto_step": "fix"},
        }
    ]
    repair = ["w", "repair"]
    add(
        "resume_escalation_supersedes_handler",
        "A re-entered step that escalates during a resumption takes precedence over the deferred handler: the queued action of the handler's nested run is superseded, and the handler runs for the new escalation, its nested run's step asked as a new action, with no queued action (§5.14.1).",
        {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate(approval=DEFER, failure_modes=escalates),
                    st(
                        "observe",
                        "o",
                        input_bindings={"target": "elsewhere"},
                        failure_modes=escalates,
                    ),
                    st(
                        "invoke",
                        "fix",
                        handler=True,
                        workflow_id="repair",
                        input_bindings={"workflow": "repair"},
                    ),
                ],
                requires=["approval@1", "recovery@1"],
            ),
            "repair": wf([CP, POLICY, mutate(approval=DEFER)], requires=["approval@1"]),
        },
        CHECKPOINTED
        + [
            {"expect": inv("observe", step=3), "respond": down},
            {
                "expect": inv("checkpoint", frame=repair),
                "respond": out(checkpoint_id="cp5"),
            },
            {"expect": inv("constrain", frame=repair), "respond": out(compliant=True)},
            deferred_end(
                {"step": 2, "action_id": "run-1/w/2/0"},
                {"frame": repair, "step": 2, "action_id": "run-1/w/repair/2/1"},
                {"step": 4},
                cause="R402",
            ),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": down},
            {
                "expect": inv("checkpoint", frame=repair),
                "respond": out(checkpoint_id="cp6"),
            },
            {"expect": inv("constrain", frame=repair), "respond": out(compliant=True)},
            {
                "expect": {
                    "kind": "RequestApproval",
                    "frame": repair,
                    "step": 2,
                    "approver": HUMAN,
                },
                "respond": approve("d2"),
            },
            {"expect": inv("mutate", frame=repair), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "escalated",
            "cause": "R402",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "failed"},
                {"action_id": "run-1/w/repair/2/1", "status": "rejected"},
                {"action_id": "run-1/w/repair/2/2", "status": "executed"},
            ],
        },
        ["run_resumed", "escalated"],
        attendance="unattended",
    )
    add(
        "resume_replan_keeps_queue",
        "A resumed run that needs a replan (a recheck saw the source change, on_change: replan) leaves the queued steps it did not reach deferred, listed with planned records; the run cannot be resumed, so they are abandoned (§5.14.1).",
        {
            "w": wf(
                [
                    CP,
                    POLICY,
                    mutate(
                        "m1",
                        approval=dict(
                            DEFER,
                            recheck={"source": "${policy}", "on_change": "replan"},
                        ),
                    ),
                    mutate("m2", approval=DEFER),
                ],
                requires=["approval@1"],
            )
        },
        CHECKPOINTED
        + [
            deferred_end({"step": 2}, {"step": 3}),
            resume(at=3600000),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {"expect": {"kind": "RecheckSource", "step": 2}, "respond": changed},
        ],
        {
            "kind": "Completed",
            "outcome": "replan_required",
            "deferred": [{"step": 3, "action_id": "run-1/w/3/1"}],
            "action_records": [
                {"action_id": "run-1/w/2/0", "status": "expired"},
                {"action_id": "run-1/w/3/1", "status": "planned"},
            ],
        },
        ["run_resumed", "recheck"],
        attendance="unattended",
    )
    _resumption_records_and_loops(add, unavailable, down, cp_answer)


def _resumption_records_and_loops(add, unavailable, down, cp_answer):
    """The time and actor of what a resumption supersedes, expires from the
    new request, a loop over a deferred handler, and a queued action
    carried out before a loop (§5.14, §5.14.1, §5.17)."""
    agent_b = {"principal": "agent-b", "kind": "agent"}
    m2 = mutate("m2", condition="${m1.success} == false", skip_if_false=True)
    first_written = {
        "timestamp": "1970-01-01T00:00:00.000Z",
        "actor_identity": {"principal": "agent-a"},
    }
    add(
        "resume_new_actor_supersedes",
        "Under a new actor, a resumed run writes again each queued record it changes: the decided one takes the time of its decision, and the one it supersedes (its step's condition is now false) the time of the supersession; both take the new actor, where the first run's records had the first (§5.14.1, §5.17).",
        {
            "w": wf(
                [CP, POLICY, mutate("m1", approval=DEFER), m2],
                requires=["approval@1"],
            )
        },
        CHECKPOINTED
        + [
            deferred_end(
                {"step": 2},
                {"step": 3},
                action_records=[
                    dict(first_written, action_id="run-1/w/2/0"),
                    dict(first_written, action_id="run-1/w/3/1"),
                ],
            ),
            resume(at=3600000, actor=agent_b),
            {"expect": queued_request(2, "run-1/w/2/0"), "respond": approve("d1")},
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {
                "expect": inv("mutate", step=2),
                "respond": out(success=True),
                "at": 3660000,
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {
                    "action_id": "run-1/w/2/0",
                    "status": "executed",
                    "timestamp": "1970-01-01T01:00:00.000Z",
                    "actor_identity": {"principal": "agent-b"},
                },
                {
                    "action_id": "run-1/w/3/1",
                    "status": "rejected",
                    "timestamp": "1970-01-01T01:01:00.000Z",
                    "actor": "agent",
                    "actor_identity": {"principal": "agent-b"},
                },
            ],
        },
        ["run_resumed", "step_skipped"],
        attendance="unattended",
        actor_identity={"principal": "agent-a", "kind": "agent"},
    )
    expiring = guarded(
        {"approver": NIGHTLY, "when_unattended": "defer_to_queue", "expires": "1h"},
        requires=["approval@1"],
    )
    add(
        "resume_expires_from_request",
        "A re-entered queued step's expires runs from its new request: the mandate asked in the first run had until an hour after the start, the person asked when the run resumed an hour later has until two hours after it, and a decision between the two counts (§5.14, §5.14.1).",
        expiring,
        CHECKPOINTED
        + [
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 2,
                    "approver": NIGHTLY,
                    "expires_at": 3600000,
                },
                "respond": unavailable,
            },
            deferred_end({"step": 2, "action_id": "run-1/w/2/0"}),
            resume(at=3600000),
            {
                "expect": queued_request(
                    2, "run-1/w/2/0", approver=HUMAN, expires_at=7200000
                ),
                "respond": approve("d1"),
                "at": 5400000,
            },
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {
                    "action_id": "run-1/w/2/0",
                    "status": "executed",
                    "approval": {
                        "decided_at": "1970-01-01T01:30:00.000Z",
                        "expires_at": "1970-01-01T02:00:00.000Z",
                    },
                }
            ],
        },
        ["run_resumed", "approval_decided"],
        attendance="unattended",
    )

    # A loop during a resumption whose range holds the deferred handler.
    page = st(
        "invoke",
        "page",
        handler=True,
        workflow_id="oncall",
        input_bindings={"workflow": "oncall", "input": {"why": "observation failed"}},
    )
    m = mutate(
        approval=DEFER,
        failure_modes=[
            {
                "condition": "the change failed",
                "on_error": "R402",
                "action": "request_more_context",
                "recovery": {"goto_step": "policy", "max_loops": 1},
            }
        ],
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
    noted = st("persist", "p", input_bindings={"data": {"paged": True}, "key": "page"})
    oncall = wf(
        [noted, CP, POLICY, mutate("n", approval=DEFER)],
        inputs={"why": {"type": "string", "required": True}},
        requires=["approval@1"],
    )
    paging = ["w", "oncall"]
    add(
        "resume_loop_keeps_handler_run",
        "A recovery loop during a resumption whose range holds the deferred handler does not run the handler: the handler keeps its place last, its kept nested run and that run's queued action, so the nested run continues without running its first step again, and its request names the queued action. The step that looped had called its capability, so its loop pass is a new action (§5.14.1).",
        {
            "w": wf([CP, POLICY, page, m, o], requires=["approval@1", "recovery@1"]),
            "oncall": oncall,
        },
        CHECKPOINTED
        + [
            {"expect": inv("observe", step=4), "respond": down},
            {
                "expect": inv("persist", frame=paging, step=0),
                "respond": out(stored=True),
            },
            {
                "expect": inv("checkpoint", frame=paging),
                "respond": out(checkpoint_id="cp5"),
            },
            {"expect": inv("constrain", frame=paging), "respond": out(compliant=True)},
            deferred_end(
                {"step": 3, "action_id": "run-1/w/3/0"},
                {"frame": paging, "step": 3, "action_id": "run-1/w/oncall/3/1"},
                {"step": 2},
                cause="R402",
            ),
            resume(at=3600000),
            {"expect": queued_request(3, "run-1/w/3/0"), "respond": approve("d1")},
            {"expect": {"kind": "CreateCheckpoint", "step": 3}, "respond": cp_answer},
            {"expect": inv("mutate", step=3), "respond": down},
            {"expect": inv("constrain", step=1), "respond": out(compliant=True)},
            {
                "expect": {"kind": "RequestApproval", "step": 3, "approver": HUMAN},
                "absent": ["queued_action_id"],
                "respond": approve("d2"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 3},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp3"},
            },
            {"expect": inv("mutate", step=3), "respond": out(success=True)},
            {
                "expect": queued_request(
                    3, "run-1/w/oncall/3/1", frame=paging, approver=HUMAN
                ),
                "respond": approve("d3"),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 3, "frame": paging},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp9"},
            },
            {"expect": inv("mutate", frame=paging), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "escalated",
            "cause": "R402",
            "deferred": [],
            "action_records": [
                {"action_id": "run-1/w/3/0", "status": "failed", "code": "R402"},
                {"action_id": "run-1/w/oncall/3/1", "status": "executed"},
                {"action_id": "run-1/w/3/2", "status": "executed"},
            ],
        },
        ["run_resumed", "loop", "invoke_resumed"],
        attendance="unattended",
    )

    # A queued action carried out, then a loop back to its step.
    again = mutate(
        approval=DEFER,
        failure_modes=[
            {
                "condition": "the change did not apply",
                "when": "${m.success} == false",
                "action": "request_more_context",
                "recovery": {"goto_step": "m", "max_loops": 1},
            }
        ],
    )
    add(
        "resume_carried_out_then_loop",
        "A re-entered queued step whose action is carried out, and which a failure mode's when then loops back to, runs again as a new action: the second request names no queued action, and the action carried out keeps its record and approval beside the new one's, as in a run that never deferred (§5.14.1).",
        {"w": wf([CP, POLICY, again], requires=["approval@1", "recovery@1"])},
        CHECKPOINTED
        + [
            deferred_end({"step": 2, "action_id": "run-1/w/2/0"}),
            resume(at=3600000),
            {
                "expect": queued_request(2, "run-1/w/2/0", approver=HUMAN),
                "respond": approve("d1"),
            },
            {"expect": {"kind": "CreateCheckpoint", "step": 2}, "respond": cp_answer},
            {"expect": inv("mutate", step=2), "respond": out(success=False)},
            {
                "expect": {"kind": "RequestApproval", "step": 2, "approver": HUMAN},
                "respond": approve("d2", who=("bob",)),
            },
            {
                "expect": {"kind": "CreateCheckpoint", "step": 2},
                "respond": {"kind": "Checkpoint", "checkpoint_id": "cp3"},
            },
            {"expect": inv("mutate", step=2), "respond": out(success=True)},
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "deferred": [],
            "action_records": [
                {
                    "action_id": "run-1/w/2/0",
                    "status": "executed",
                    "approval": {"approvers": ["alice"]},
                },
                {
                    "action_id": "run-1/w/2/1",
                    "status": "executed",
                    "approval": {"approvers": ["bob"]},
                },
            ],
        },
        ["run_resumed", "loop"],
        attendance="unattended",
    )
