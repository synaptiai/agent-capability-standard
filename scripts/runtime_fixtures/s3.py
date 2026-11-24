"""Runtime fixtures of workstream S3 (delegation, catalogs and diagnostics;
RFC-0007): delegation targets and agent manifests (STANDARD v1.2 §5.15.2),
continuing a delegation (§5.15.3), the model identifier an identity attests
(§5.17), exact model families (§5.16) and catalog sets (§5.1.1).

Define each with add(name, description, catalog, script, end, trace, ...),
the function of scripts/gen_runtime_fixtures.py; the building blocks are in
runtime_fixtures.helpers. A fixture gives `catalogs` (the other catalogs of
its catalog set, each with its header) and `agents` (agent manifests) when
it needs them. Executor prose (a `Failed` action's `message`) is not pinned.
"""

from runtime_fixtures.helpers import CP, approve, inv, out, st, wf

V12 = "1.2.0"
V11 = "1.1.0"

DB_WRITER = {
    "agent": "db-writer",
    "standard": "1.2",
    "ontology": "2.2",
    "capabilities": ["retrieve", "checkpoint", "mutate"],
    "task": {"table": {"type": "string", "required": True}, "rows": {"type": "array"}},
}
READER_A = {
    "agent": "a",
    "standard": "1.2",
    "ontology": "2.2",
    "capabilities": ["retrieve", "critique"],
}
READER_B = {**READER_A, "agent": "b"}

LIB = {
    "catalog": {
        "id": "acs.fixtures.lib",
        "version": "1.0.0",
        "exports": ["shared_check"],
    },
    "shared_check": {
        "goal": "g",
        "risk": "low",
        "steps": [
            st(
                "invoke",
                "inner_out",
                workflow_id="inner",
                input_bindings={"workflow": "inner"},
            )
        ],
    },
    "inner": {
        "goal": "g",
        "risk": "low",
        "steps": [st("retrieve", "lib_record", input_bindings={"target": "library"})],
    },
}
LIB_SET = [{"catalog": LIB, "header": V12}]

# A library whose exported workflow's name is not an identifier (W620 there,
# and reachable by qualified id all the same).
NAMES_LIB = {
    "catalog": {
        "id": "acs.fixtures.names",
        "version": "1.0.0",
        "exports": ["Shared Check"],
    },
    "Shared Check": {
        "goal": "g",
        "risk": "low",
        "steps": [st("retrieve", "lib_record", input_bindings={"target": "library"})],
    },
}
NAMES_SET = [{"catalog": NAMES_LIB, "header": V12}]


def v12(steps, **kw):
    """A workflow that targets 1.2."""
    return wf(steps, spec_version="1.2", **kw)


def delegate(store, agent, task=None, **kw):
    """A delegate step; keyword arguments that are step fields go on the
    step, the others into its input bindings."""
    fields = {k: kw.pop(k) for k in ("retry", "timeout", "wait") if k in kw}
    b = {"agent": agent, "task": task if task is not None else {"table": "t"}}
    b.update(kw)
    return st("delegate", store, input_bindings=b, **fields)


def accepted(task_id="t1", **effective):
    return out(accepted=True, task_id=task_id, effective=effective)


def done(task, **event):
    return {
        "kind": "Event",
        "event": {"event_type": "review.done", "task_id": task, **event},
    }


def register(add):
    """Add this workstream's fixtures."""
    _targets(add)
    _read_only(add)
    _continues(add)
    _catalogs(add)
    _families(add)
    _with_profiles(add)


def _targets(add):
    add(
        "agents_raise_checkpoint_approval",
        "In a workflow that declares agents, a delegation to an agent that may "
        "mutate takes its manifest's maxima: the step needs the checkpoint before "
        "it and is put to an approver before the host is asked (§5.15.2).",
        {"w": v12([CP, delegate("write", "db-writer")], agents=["db-writer"])},
        [
            {
                "expect": inv("checkpoint", step=0),
                "respond": out(checkpoint_id="c1"),
            },
            {
                "expect": {"kind": "RequestApproval", "step": 1},
                "respond": approve("d1"),
            },
            {
                "expect": inv("delegate", step=1, inputs={"agent": "db-writer"}),
                "respond": accepted(),
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        header=V12,
        agents=[DB_WRITER],
    )
    add(
        "agents_computed_unlisted",
        "A computed agent that the workflow's agents does not list is refused "
        "before the host is asked (R402, not retried; §5.15.2).",
        {
            "w": v12(
                [
                    delegate(
                        "pick",
                        "${who}",
                        task={"draft": "d"},
                        read_only=True,
                        retry={"max": 2, "backoff": "none"},
                    )
                ],
                inputs={"who": {"type": "string", "required": True}},
                agents=["a", "b"],
                requires=["delegation@1"],
                risk="low",
            )
        },
        [],
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "run_failed"],
        inputs={"who": "c"},
        header=V12,
        agents=[READER_A, READER_B],
    )
    add(
        "agents_manifest_missing",
        "A listed agent the host gave no manifest for has unknown target maxima: "
        "the executor does not delegate (R402, fail-closed; §5.15.2), and the "
        "failure names the missing manifest.",
        {
            "w": v12(
                [CP, delegate("ask", "ghost", task={"q": "x"})],
                agents=["db-writer", "ghost"],
            )
        },
        [
            {
                "expect": inv("checkpoint", step=0),
                "respond": out(checkpoint_id="c1"),
            },
        ],
        {"kind": "Failed", "code": "R402", "step": 1},
        ["step_failed", "run_failed"],
        header=V12,
        agents=[DB_WRITER],
    )
    add(
        "agents_task_refused",
        "A task given by reference that lacks an input the agent's manifest "
        "requires is refused before the delegation is put to an approver or the "
        "host is asked (R402; §5.15.2).",
        {
            "w": v12(
                [CP, delegate("write", "db-writer", task="${task_in}")],
                inputs={"task_in": {"type": "object", "required": True}},
                agents=["db-writer"],
            )
        },
        [
            {
                "expect": inv("checkpoint", step=0),
                "respond": out(checkpoint_id="c1"),
            },
        ],
        {"kind": "Failed", "code": "R402", "step": 1},
        ["step_failed", "run_failed"],
        inputs={"task_in": {"rows": []}},
        header=V12,
        agents=[DB_WRITER],
    )


def _read_only(add):
    add(
        "agents_read_only_not_attested",
        "A read-only delegation takes the read-only maxima; its host accepts it "
        "but does not attest read_only: R402 after one delegation, not retried "
        "though the step has retry (§5.15.2).",
        {
            "w": v12(
                [
                    delegate(
                        "read",
                        "db-writer",
                        read_only=True,
                        retry={"max": 2, "backoff": "none"},
                    )
                ],
                agents=["db-writer"],
                requires=["delegation@1"],
                risk="low",
            )
        },
        [
            {
                "expect": inv("delegate", step=0, attempt=1),
                "respond": accepted(read_only=False),
            }
        ],
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "run_failed"],
        header=V12,
        agents=[DB_WRITER],
    )
    add(
        "delegate_read_only_not_attested_v12",
        "In a 1.2 workflow without agents, an accepted read-only delegation its "
        "host does not attest fails too (R402; §5.15.2).",
        {
            "w": v12(
                [delegate("read", "x", task={"q": "d"}, read_only=True)],
                requires=["delegation@1"],
                risk="low",
            )
        },
        [{"expect": inv("delegate", step=0), "respond": accepted()}],
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "run_failed"],
        header=V12,
    )
    add(
        "delegate_read_only_v11_unchecked",
        "The same delegation in a 1.1 workflow runs as in 1.1: the attestation is "
        "not checked (§5.15.2).",
        {
            "w": wf(
                [delegate("read", "x", task={"q": "d"}, read_only=True)],
                requires=["delegation@1"],
                risk="low",
            )
        },
        [{"expect": inv("delegate", step=0), "respond": accepted()}],
        {"kind": "Completed", "outcome": "completed"},
        header=V11,
    )


def _continues(add):
    cont = {
        "w": v12(
            [
                delegate(
                    "rb", "x", task={"q": "d"}, continues="${prior}", read_only=True
                )
            ],
            inputs={"prior": {"type": ["string", "null"]}},
            requires=["delegation@1"],
            risk="low",
        )
    }
    add(
        "delegate_continues_fresh_refused",
        "A continued delegation whose host attests a fresh context fails (R402; "
        "§5.15.3).",
        cont,
        [
            {
                "expect": inv("delegate", step=0, inputs={"continues": "t1"}),
                "respond": accepted("t2", fresh_context=True, read_only=True),
            }
        ],
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "run_failed"],
        inputs={"prior": "t1"},
        header=V12,
    )
    add(
        "delegate_continues_null_delegates_anew",
        "continues that resolves to null delegates anew: a fresh context is "
        "allowed (§5.15.3).",
        cont,
        [
            {
                "expect": inv("delegate", step=0, inputs={"continues": None}),
                "respond": accepted("t2", fresh_context=True, read_only=True),
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
        inputs={"prior": None},
        header=V12,
    )
    add(
        "delegate_continues_same_task_id_refused",
        "Every delegation call returns its own task_id: a continuation that "
        "returns the one it continues fails (R402; §5.15.3).",
        cont,
        [
            {
                "expect": inv("delegate", step=0, inputs={"continues": "t1"}),
                "respond": accepted("t1", read_only=True),
            }
        ],
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "run_failed"],
        inputs={"prior": "t1"},
        header=V12,
    )
    add(
        "delegate_continues_v11_unchecked",
        "In a 1.1 workflow, continues is an input the executor passes on, as 1.1 "
        "did: a continuation that binds fresh_context: true, whose host attests a "
        "fresh context and returns the task_id it continues, completes (§5.15.3 "
        "applies from 1.2; W616).",
        {
            "w": wf(
                [
                    delegate(
                        "rb",
                        "x",
                        task={"q": "d"},
                        continues="${prior}",
                        fresh_context=True,
                    )
                ],
                inputs={"prior": {"type": "string", "required": True}},
                requires=["delegation@1"],
                risk="low",
            )
        },
        [
            {
                "expect": inv(
                    "delegate",
                    step=0,
                    inputs={"continues": "t0", "fresh_context": True},
                ),
                "respond": accepted("t0", fresh_context=True),
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
        inputs={"prior": "t0"},
        header=V11,
    )

    def waiting(store, **bindings):
        return delegate(
            store,
            "x",
            task={"q": "d"},
            read_only=True,
            timeout="2h",
            wait={"event_type": "review.done"},
            **bindings,
        )

    add(
        "delegate_continues_own_task_id",
        "A continuation's wait matches only its own call's result: the earlier "
        "call's result, delivered again, is dropped, and the continuation's "
        "result is matched by its own task_id (§5.13, §5.15.3).",
        {
            "w": v12(
                [
                    waiting("review_a"),
                    waiting("review_b", continues="${review_a.task_id}"),
                ],
                requires=["wait@1", "delegation@1"],
                risk="low",
            )
        },
        [
            {
                "expect": inv("delegate", step=0),
                "respond": accepted("t1", read_only=True),
            },
            {
                "expect": {
                    "kind": "AwaitEvent",
                    "step": 0,
                    "correlate": {"task_id": "t1"},
                },
                "respond": done("t1"),
            },
            {
                "expect": inv("delegate", step=1, inputs={"continues": "t1"}),
                "respond": accepted("t2", read_only=True),
            },
            {
                "expect": {
                    "kind": "AwaitEvent",
                    "step": 1,
                    "correlate": {"task_id": "t2"},
                },
                "respond": done("t1"),
            },
            {
                "expect": {
                    "kind": "AwaitEvent",
                    "step": 1,
                    "correlate": {"task_id": "t2"},
                },
                "respond": done("t2"),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "outputs": {"review_b": {"task_id": "t2", "result": {"task_id": "t2"}}},
        },
        ["event_dropped"],
        header=V12,
    )
    add(
        "delegate_identity_model_id_mismatch",
        "Under identity@1, an attested identity's model_id must equal "
        "effective.model_id (R402; §5.17).",
        {
            "w": v12(
                [delegate("rb", "x", task={"q": "d"}, read_only=True)],
                requires=["delegation@1", "identity@1"],
                risk="low",
            )
        },
        [
            {
                "expect": inv("delegate", step=0),
                "respond": accepted(
                    "t1",
                    read_only=True,
                    model_id="acme-large-2",
                    identity={
                        "principal": "agent:x",
                        "kind": "agent",
                        "model_id": "acme-small-1",
                    },
                ),
            }
        ],
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "run_failed"],
        header=V12,
    )
    add(
        "delegate_identity_model_id_v11_unchecked",
        "In a 1.1 workflow, model_id is not an agent_identity member (schema "
        "1.0.0 allows extra members), so the executor reads it neither for its "
        "type nor against effective.model_id, as 1.1 did: both delegations "
        "complete (§5.17's model_id applies from 1.2).",
        {
            "w": wf(
                [
                    delegate("ra", "x", task={"q": "d"}),
                    delegate("rb", "y", task={"q": "d"}),
                ],
                requires=["delegation@1", "identity@1"],
                risk="low",
            )
        },
        [
            {
                "expect": inv("delegate", step=0),
                "respond": accepted(
                    "t1",
                    model_id="acme-large-2",
                    identity={
                        "principal": "agent:x",
                        "kind": "agent",
                        "model_id": "acme-small-1",
                    },
                ),
            },
            {
                "expect": inv("delegate", step=1),
                "respond": accepted(
                    "t2",
                    identity={"principal": "agent:y", "kind": "agent", "model_id": 7},
                ),
            },
        ],
        {"kind": "Completed", "outcome": "completed"},
        header=V11,
    )


def _catalogs(add):
    add(
        "invoke_qualified_library",
        "An invoke of another catalog's exported workflow by qualified id runs it "
        "as a nested run; inside it a bare name means the library's own workflow, "
        "not the primary catalog's workflow of that name (§5.1.1).",
        {
            "w": v12(
                [
                    st(
                        "invoke",
                        "checked",
                        workflow_id="acs.fixtures.lib/shared_check",
                        input_bindings={"workflow": "acs.fixtures.lib/shared_check"},
                    )
                ],
                risk="low",
            ),
            "inner": {
                "goal": "g",
                "risk": "low",
                "steps": [
                    st(
                        "detect",
                        "primary_inner",
                        input_bindings={"data": "d", "pattern": "p"},
                    )
                ],
            },
        },
        [
            {
                "expect": inv(
                    "retrieve",
                    step=0,
                    frame=[
                        "w",
                        "acs.fixtures.lib/shared_check",
                        "acs.fixtures.lib/inner",
                    ],
                ),
                "respond": out(data={}, confidence=1),
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["invoke_started"],
        header=V12,
        catalogs=LIB_SET,
    )
    add(
        "invoke_computed_not_exported",
        "A computed invoke target that names another catalog's workflow it does "
        "not export is refused before the nested run starts (R402; §5.1.1).",
        {
            "w": v12(
                [st("invoke", "x", input_bindings={"workflow": "${target}"})],
                inputs={"target": {"type": "string", "required": True}},
                risk="low",
            )
        },
        [],
        {"kind": "Failed", "code": "R402", "step": 0},
        ["step_failed", "run_failed"],
        inputs={"target": "acs.fixtures.lib/inner"},
        header=V12,
        catalogs=LIB_SET,
    )
    add(
        "invoke_qualified_non_identifier_name",
        "A qualified id's name is any workflow name, not only an identifier: "
        "another catalog's exported 'Shared Check' runs as a nested run when "
        "invoked as acs.fixtures.names/Shared Check (§5.1, §5.1.1).",
        {
            "w": v12(
                [
                    st(
                        "invoke",
                        "checked",
                        workflow_id="acs.fixtures.names/Shared Check",
                        input_bindings={"workflow": "acs.fixtures.names/Shared Check"},
                    )
                ],
                risk="low",
            )
        },
        [
            {
                "expect": inv(
                    "retrieve",
                    step=0,
                    frame=["w", "acs.fixtures.names/Shared Check"],
                ),
                "respond": out(data={}, confidence=1),
            }
        ],
        {"kind": "Completed", "outcome": "completed"},
        ["invoke_started"],
        header=V12,
        catalogs=NAMES_SET,
    )


def _families(add):
    def reviewer(store, family):
        return delegate(
            store,
            store,
            task={"review": "${change}"},
            model_family=family.lower(),
            read_only=True,
            timeout="2h",
            wait={"event_type": "review.done"},
        )

    gate = st(
        "constrain",
        "gate",
        input_bindings={
            "target": "${change}",
            "constraints": ["two families"],
            "action_on_violation": "block",
        },
        quorum={
            "verdicts": ["${ra.result: object}", "${rb.result: object}"],
            "reviewers": ["ra", "rb"],
            "vocabulary": ["approve", "request_changes"],
            "pass_values": ["approve"],
            "min_pass": 2,
            "pinned_to": "${change}",
            "require_model_families": ["acme", "bolt"],
        },
    )
    add(
        "quorum_family_exact",
        "Model families compare exactly: a reviewer whose host attests 'Acme' "
        "does not cover 'acme' (F504; §5.15, §5.16).",
        {
            "w": wf(
                [reviewer("ra", "acme"), reviewer("rb", "bolt"), gate],
                inputs={"change": {"type": "string", "required": True}},
                requires=["wait@1", "delegation@1", "quorum@1"],
                risk="low",
            )
        },
        [
            {
                "expect": inv("delegate", step=0),
                "respond": accepted("t1", read_only=True, model_family="Acme"),
            },
            {
                "expect": {"kind": "AwaitEvent", "step": 0},
                "respond": done("t1", reviewer_id="ra", value="approve", pinned="c1"),
            },
            {
                "expect": inv("delegate", step=1),
                "respond": accepted("t2", read_only=True, model_family="bolt"),
            },
            {
                "expect": {"kind": "AwaitEvent", "step": 1},
                "respond": done("t2", reviewer_id="rb", value="approve", pinned="c1"),
            },
        ],
        {"kind": "Failed", "code": "F504", "step": 2},
        ["quorum"],
        inputs={"change": "c1"},
        header=V11,
    )


def _with_profiles(add):
    """Target maxima (§5.15.2) and domain profiles (§5.21.3) together: each
    raises the delegate step's flags, and the stricter of the two holds."""
    person_delegate = {
        "domain": "person-delegate",
        "version": "1.0.0",
        "risk_thresholds": {"block_autonomous": ["delegate"]},
    }
    add(
        "agents_maxima_with_profile_person",
        "A delegation to an agent that may mutate takes its manifest's maxima "
        "(a checkpoint before it, approval), and a profile that blocks autonomous "
        "delegation requires a person for that approval: it is asked of a human "
        "with always_ask and no mandate, and its record carries person_required "
        "(§5.15.2, §5.21.3).",
        {"w": v12([CP, delegate("write", "db-writer")], agents=["db-writer"])},
        [
            {
                "expect": inv("checkpoint", step=0),
                "respond": out(checkpoint_id="c1"),
            },
            {
                "expect": {
                    "kind": "RequestApproval",
                    "step": 1,
                    "approver": {"kind": "human", "always_ask": True},
                },
                "absent": ["approver.mandate_ref"],
                "respond": approve("d1", who=("dana",)),
            },
            {
                "expect": inv("delegate", step=1, inputs={"agent": "db-writer"}),
                "respond": accepted(),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {
                    "capability": "delegate",
                    "status": "executed",
                    "person_required": True,
                    "approval": {"approvers": ["dana"]},
                }
            ],
        },
        ["person_required", "approval_requested", "approval_decided"],
        header=V12,
        agents=[DB_WRITER],
        profiles=[person_delegate],
    )
    reviewer = {**READER_A, "agent": "reviewer"}
    checkpoint_delegate = {
        "domain": "checkpoint-delegate",
        "version": "1.0.0",
        "checkpoint_policy": {"delegate": "always"},
    }
    add(
        "agents_read_only_maxima_with_profile_checkpoint",
        "A delegation to a read-only agent needs no checkpoint by its maxima, "
        "but a profile's checkpoint policy for delegate raises it: the step "
        "needs the checkpoint before it, and its action record names it "
        "(§5.15.2, §5.21.3, §6.4).",
        {
            "w": v12(
                [CP, delegate("review", "reviewer", task={"draft": "d"})],
                agents=["reviewer"],
            )
        },
        [
            {
                "expect": inv("checkpoint", step=0),
                "respond": out(checkpoint_id="c1"),
            },
            {
                "expect": inv("delegate", step=1, inputs={"agent": "reviewer"}),
                "respond": accepted(),
            },
        ],
        {
            "kind": "Completed",
            "outcome": "completed",
            "action_records": [
                {"capability": "checkpoint", "checkpoint_id": "c1"},
                {"capability": "delegate", "status": "executed", "checkpoint_id": "c1"},
            ],
        },
        header=V12,
        agents=[reviewer],
        profiles=[checkpoint_delegate],
        records="actions",
    )
