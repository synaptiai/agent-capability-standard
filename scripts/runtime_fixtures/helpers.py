"""Building blocks of runtime fixtures: steps, workflows, responses and
expected actions, as scripts/gen_runtime_fixtures.py writes them."""


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


def resume(attendance="attended", at=None, actor=None):
    """A script entry that resumes a run that ended deferred (STANDARD v1.2
    §5.14.1): with `attendance` from then on, at time `at` (default: the
    script's time so far) and, with `actor`, a new actor_identity."""
    r = {"attendance": attendance}
    if at is not None:
        r["at"] = at
    if actor is not None:
        r["actor_identity"] = actor
    return {"resume": r}


def err(code, message="m", reason=None, **extra):
    """An Error response; `reason` (§5.19.7) and other members when given."""
    e = {"kind": "Error", "code": code, "message": message}
    if reason is not None:
        e["reason"] = reason
    e.update(extra)
    return e


def tick(t, changed=None):
    """A script entry that gives the run the time `t` (STANDARD v1.2
    §5.19.3); with `changed`, whether the tick must change the run."""
    e = {"tick": t}
    if changed is not None:
        e["changed"] = changed
    return e


def wake(at):
    """A script entry: the run's wake-up time is `at` (None: none)."""
    return {"wake_at": at}


def cancel(reason, at=None):
    """A script entry that cancels the run (§5.19.5)."""
    c = {"reason": reason}
    if at is not None:
        c["at"] = at
    return {"cancel": c}
