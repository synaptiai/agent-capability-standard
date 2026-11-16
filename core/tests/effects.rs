//! Checkpoints, rollbacks, sends and memory in the executor (STANDARD v1.2
//! §4.4.1, §4.4.2, §4.5): idempotency keys, the destination check, the
//! memory scope echo and `RolledBack.not_covered`.

use std::path::{Path, PathBuf};

use acs_core::exec::canonical::{canonical, sha256_hex};
use acs_core::exec::{
    Attendance, RecordMode, Response, RestoreError, Run, Snapshot, StartError, StartOptions,
    SubmitError,
};
use acs_core::validate::Context;
use serde_json::{Map, Value, json};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn ctx() -> Context {
    let root = root();
    Context::load(&root.join("schemas/capability_ontology.yaml"), &root).unwrap()
}

fn opts() -> StartOptions {
    StartOptions {
        attendance: Attendance::Attended,
        run_id: "r".into(),
        now_ms: 0,
        actor_identity: None,
        header: None,
        records: RecordMode::Approvals,
        profiles: Vec::new(),
        grounding: Vec::new(),
        destinations: Vec::new(),
    }
}

fn catalog(steps: Value, extensions: &[&str]) -> Value {
    let mut wf = json!({"goal": "g", "risk": "high", "spec_version": "1.1",
        "inputs": {"to": {"type": "string", "required": true}}, "steps": steps});
    if !extensions.is_empty() {
        wf["workflow_extensions"] = json!({"requires": extensions});
    }
    json!({"w": wf})
}

fn inputs(to: Value) -> Map<String, Value> {
    json!({"to": to}).as_object().unwrap().clone()
}

/// A checkpoint, then a send to `${to}` with `retry`.
fn send(retry: Option<Value>) -> Value {
    let mut s = json!({"capability": "send", "purpose": "p", "store_as": "s",
        "input_bindings": {"destination": "${to}", "payload": {"a": 1}}});
    if let Some(r) = retry {
        s["retry"] = r;
    }
    catalog(
        json!([
            {"capability": "checkpoint", "purpose": "p", "store_as": "cp",
             "input_bindings": {"scope": "*"}},
            s
        ]),
        &[],
    )
}

fn action(run: &Run) -> Value {
    serde_json::to_value(run.next()).unwrap()
}

fn output(value: Value) -> Response {
    Response::Output {
        value,
        evidence_seen: None,
    }
}

fn error(code: &str, reason: Option<&str>) -> Response {
    Response::Error {
        code: code.into(),
        message: "m".into(),
        reason: reason.map(|r| json!(r)),
    }
}

/// Answer the pending action and return the next one.
fn answer(run: &mut Run, response: Response) -> Value {
    let id = run.next().id;
    run.submit(id, response, 0).unwrap();
    action(run)
}

/// Take the checkpoint step and approve the send: the next action is the
/// send's first `InvokeCapability`.
fn to_send(run: &mut Run) -> Value {
    let a = action(run);
    assert_eq!(a["capability"], "checkpoint");
    let a = answer(
        run,
        output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
    );
    assert_eq!(a["kind"], "RequestApproval");
    let a = answer(
        run,
        Response::Decision {
            decision_id: format!("d{}", a["id"]),
            decision: "approved".into(),
            approvers: vec!["ops".into()],
            digest: a["digest"].as_str().unwrap().into(),
            approver_identities: None,
        },
    );
    assert_eq!(
        (a["kind"].as_str(), a["capability"].as_str()),
        (Some("InvokeCapability"), Some("send"))
    );
    a
}

fn sent() -> Response {
    output(json!({"sent": true, "evidence_anchors": []}))
}

#[test]
fn idempotency_key_same_across_retry() {
    let ctx = ctx();
    let mut run = Run::start(
        &ctx,
        &send(Some(json!({"max": 2}))),
        "w",
        inputs(json!("ops")),
        opts(),
    )
    .unwrap();
    let first = to_send(&mut run);
    let key = format!("r:{}", first["id"]);
    assert_eq!(first["idempotency_key"], json!(key));
    let second = answer(&mut run, error("R401", None));
    assert_eq!(
        (second["attempt"].as_u64(), &second["idempotency_key"]),
        (Some(2), &json!(key))
    );
    assert_ne!(second["id"], first["id"]);
    // A retry after an error the host gave keeps it too.
    let third = answer(&mut run, error("R402", Some("outcome_unknown")));
    assert_eq!(third["idempotency_key"], json!(key));
    let end = answer(&mut run, sent());
    assert_eq!(end["kind"], "Completed");
    // The step's approved record carries the pass's key (§6.4).
    assert_eq!(end["action_records"][0]["idempotency_key"], json!(key));
}

#[test]
fn idempotency_key_survives_restore() {
    let ctx = ctx();
    let cat = send(Some(json!({"max": 1})));
    let mut run = Run::start(&ctx, &cat, "w", inputs(json!("ops")), opts()).unwrap();
    let first = to_send(&mut run);
    let restored = Run::restore(&ctx, &cat, &run.snapshot(None), None).unwrap();
    assert_eq!(action(&restored), first);
    let mut run = restored;
    let second = answer(&mut run, error("R401", None));
    assert_eq!(second["idempotency_key"], first["idempotency_key"]);
}

/// `snap` with its state edited and its digest recomputed.
fn forged(snap: &Snapshot, edit: impl Fn(&mut Value)) -> Snapshot {
    let mut state: Value = serde_json::from_str(&snap.state).unwrap();
    edit(&mut state);
    let text = canonical(&state);
    Snapshot {
        sha256: sha256_hex(&text),
        state: text,
        hmac: None,
    }
}

#[test]
fn idempotency_key_filled_on_v1_restore() {
    // A version-1 state (before Standard 1.2) with a pending
    // InvokeCapability carries no key: the restored action gets
    // `<run_id>:<id>`, and the later attempts of its pass reuse it.
    let ctx = ctx();
    let cat = send(Some(json!({"max": 1})));
    let mut run = Run::start(&ctx, &cat, "w", inputs(json!("ops")), opts()).unwrap();
    let first = to_send(&mut run);
    let v1 = forged(&run.snapshot(None), |s| {
        s["version"] = json!(1);
        let action = s["pending"]["action"].as_object_mut().unwrap();
        action.remove("run_id");
        action.remove("idempotency_key");
        let frames = s["frames"].as_array_mut().unwrap();
        let cur = frames.last_mut().unwrap()["cur"].as_object_mut().unwrap();
        cur.remove("idempotency_key");
        // The send's approved record, written before the key existed.
        for record in s["records"].as_array_mut().unwrap() {
            record.as_object_mut().unwrap().remove("idempotency_key");
        }
    });
    let key = json!(format!("r:{}", first["id"]));
    let mut run = Run::restore(&ctx, &cat, &v1, None).unwrap();
    let pending = action(&run);
    assert_eq!(pending["idempotency_key"], key);
    // The record of the pass gets the key too (§6.4), although the
    // restored attempt succeeds and the step is not called again.
    let mut done = Run::restore(&ctx, &cat, &v1, None).unwrap();
    let end = answer(&mut done, sent());
    assert_eq!(end["kind"], "Completed");
    assert_eq!(
        (
            end["action_records"][0]["capability"].as_str(),
            &end["action_records"][0]["idempotency_key"]
        ),
        (Some("send"), &key)
    );
    let retry = answer(&mut run, error("R401", None));
    assert_eq!(retry["idempotency_key"], pending["idempotency_key"]);
}

#[test]
fn idempotency_key_new_per_loop() {
    // A recovery loop runs the step again: a new pass, a new key.
    let ctx = ctx();
    let cat = catalog(
        json!([
            {"capability": "checkpoint", "purpose": "p", "store_as": "cp",
             "input_bindings": {"scope": "*"}},
            {"capability": "send", "purpose": "p", "store_as": "s",
             "input_bindings": {"destination": "${to}", "payload": {"a": 1}},
             "failure_modes": [{"condition": "c", "on_error": "R402",
                 "action": "request_more_context",
                 "recovery": {"goto_step": "cp", "max_loops": 1}}]}
        ]),
        &["recovery@1"],
    );
    let mut run = Run::start(&ctx, &cat, "w", inputs(json!("ops")), opts()).unwrap();
    let first = to_send(&mut run);
    let after = answer(&mut run, error("R402", None));
    // Back to the checkpoint step, then the send again.
    assert_eq!(after["capability"], "checkpoint");
    let mut run2 = run;
    let second = to_send(&mut run2);
    assert_ne!(second["idempotency_key"], first["idempotency_key"]);
    assert_eq!(
        second["idempotency_key"],
        json!(format!("r:{}", second["id"]))
    );
}

#[test]
fn idempotency_key_new_on_replaces() {
    // A waiting delegate retried after its delegate went silent delegates
    // again: a new delegation, with a key of its own.
    let ctx = ctx();
    let cat = catalog(
        json!([
            {"capability": "delegate", "purpose": "p", "store_as": "d",
             "input_bindings": {"task": {"t": 1}, "agent": "a"},
             "timeout": "2h", "retry": {"max": 1, "backoff": "none"},
             "wait": {"event_type": "done",
                 "liveness": {"mode": "push", "interval": "10m", "failure_threshold": 3}}}
        ]),
        &["wait@1"],
    );
    let mut run = Run::start(&ctx, &cat, "w", inputs(json!("x")), opts()).unwrap();
    let first = action(&run);
    assert_eq!(first["kind"], "InvokeCapability");
    let key = first["idempotency_key"].clone();
    let wait = answer(
        &mut run,
        output(json!({"accepted": true, "task_id": "t1", "evidence_anchors": []})),
    );
    assert_eq!(wait["kind"], "AwaitEvent");
    let again = answer(&mut run, Response::LivenessLost);
    assert_eq!(again["replaces"], json!("t1"));
    assert_eq!(
        again["idempotency_key"],
        json!(format!("r:{}", again["id"]))
    );
    assert_ne!(again["idempotency_key"], key);
}

fn failed(a: &Value) -> (Option<&str>, Option<&str>) {
    assert_eq!(a["kind"], "Failed", "{a}");
    (a["code"].as_str(), a["reason"].as_str())
}

#[test]
fn destination_refused_before_approval() {
    let ctx = ctx();
    let options = StartOptions {
        destinations: vec![vec!["https://hooks.example.com/*".into()]],
        ..opts()
    };
    let mut run = Run::start(
        &ctx,
        &send(None),
        "w",
        inputs(json!("https://evil.example.net/x")),
        options.clone(),
    )
    .unwrap();
    let end = answer(
        &mut run,
        output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
    );
    assert_eq!(
        failed(&end),
        (Some("F504"), Some("destination_not_allowed"))
    );
    // The message does not repeat the destination (§6.7).
    assert!(!end["message"].as_str().unwrap().contains("evil"));
    // No checkpoint was used.
    assert!(
        run.trace()
            .iter()
            .all(|t| t["kind"] != "checkpoint_consumed")
    );
    // An allowed destination is asked for.
    let mut run = Run::start(
        &ctx,
        &send(None),
        "w",
        inputs(json!("https://hooks.example.com/r")),
        options,
    )
    .unwrap();
    let a = answer(
        &mut run,
        output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
    );
    assert_eq!(a["kind"], "RequestApproval");
}

#[test]
fn destination_not_string_refused() {
    let ctx = ctx();
    let options = StartOptions {
        destinations: vec![vec!["ops".into()]],
        ..opts()
    };
    // An optional input that is not given: the destination resolves to null.
    let mut cat = send(None);
    cat["w"]["inputs"]["to"] = json!({"type": "string"});
    let mut run = Run::start(&ctx, &cat, "w", Map::new(), options).unwrap();
    let end = answer(
        &mut run,
        output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
    );
    assert_eq!(
        failed(&end),
        (Some("F504"), Some("destination_not_allowed"))
    );
    // Without a policy, the destination is the host's to check (1.1).
    let mut run = Run::start(&ctx, &cat, "w", Map::new(), opts()).unwrap();
    let a = answer(
        &mut run,
        output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
    );
    assert_eq!(a["kind"], "RequestApproval");
}

fn profile(patterns: Value) -> Value {
    json!({"domain": "dest-test", "version": "1.0.0", "allowed_destinations": patterns})
}

#[test]
fn destination_profile_policy_only() {
    let ctx = ctx();
    for (patterns, to, allowed) in [
        (json!(["mailto:*"]), "https://x.example/", false),
        (json!(["mailto:*"]), "mailto:ops@example.com", true),
        (json!([]), "mailto:ops@example.com", false),
    ] {
        let options = StartOptions {
            profiles: vec![profile(patterns.clone())],
            ..opts()
        };
        let mut run = Run::start(&ctx, &send(None), "w", inputs(json!(to)), options).unwrap();
        let a = answer(
            &mut run,
            output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
        );
        if allowed {
            assert_eq!(a["kind"], "RequestApproval", "{patterns} {to}");
        } else {
            assert_eq!(failed(&a), (Some("F504"), Some("destination_not_allowed")));
        }
    }
}

#[test]
fn destination_profile_policy_after_restore() {
    // A state that holds the profile applies it as a fresh start does.
    let ctx = ctx();
    let options = StartOptions {
        profiles: vec![profile(json!(["mailto:*"]))],
        ..opts()
    };
    let run = Run::start(
        &ctx,
        &send(None),
        "w",
        inputs(json!("https://x.example/")),
        options,
    )
    .unwrap();
    let mut run = Run::restore(&ctx, &send(None), &run.snapshot(None), None).unwrap();
    let a = answer(
        &mut run,
        output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
    );
    assert_eq!(failed(&a), (Some("F504"), Some("destination_not_allowed")));
}

#[test]
fn destination_host_and_profile_intersect() {
    let ctx = ctx();
    let options = |to: &str| {
        (
            StartOptions {
                destinations: vec![vec!["https://a.example/*".into()]],
                profiles: vec![profile(json!(["https://a.example/x/*"]))],
                ..opts()
            },
            inputs(json!(to)),
        )
    };
    for (to, allowed) in [
        ("https://a.example/y", false),
        ("https://a.example/x/1", true),
    ] {
        let (o, i) = options(to);
        let mut run = Run::start(&ctx, &send(None), "w", i, o).unwrap();
        let a = answer(
            &mut run,
            output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
        );
        assert_eq!(a["kind"] == "RequestApproval", allowed, "{to}");
    }
}

#[test]
fn invalid_policy_refused_at_start() {
    let ctx = ctx();
    let options = StartOptions {
        destinations: vec![
            vec!["ops".into()],
            vec!["https://hooks.example.com:*".into()],
        ],
        ..opts()
    };
    match Run::start(&ctx, &send(None), "w", inputs(json!("ops")), options) {
        Err(StartError::Policy(m)) => assert!(m.starts_with("policy 1, pattern 0: "), "{m}"),
        other => panic!("{:?}", other.err()),
    }
    // A profile whose pattern is invalid is refused when it is loaded.
    let options = StartOptions {
        profiles: vec![profile(json!(["*"]))],
        ..opts()
    };
    match Run::start(&ctx, &send(None), "w", inputs(json!("ops")), options) {
        Err(StartError::Invalid(d)) => assert_eq!(d[0].code.as_str(), "S303"),
        other => panic!("{:?}", other.err()),
    }
}

#[test]
fn invalid_policy_refused_at_restore() {
    let ctx = ctx();
    let options = StartOptions {
        destinations: vec![vec!["ops".into()]],
        ..opts()
    };
    let run = Run::start(&ctx, &send(None), "w", inputs(json!("ops")), options).unwrap();
    let snap = run.snapshot(None);
    let state: Value = serde_json::from_str(&snap.state).unwrap();
    assert_eq!(state["destinations"], json!([["ops"]]));
    assert!(Run::restore(&ctx, &send(None), &snap, None).is_ok());
    let bad = forged(&snap, |s| s["destinations"] = json!([["a*b"]]));
    assert!(matches!(
        Run::restore(&ctx, &send(None), &bad, None),
        Err(RestoreError::Malformed(_))
    ));
    // A run with no policy keeps its snapshot without the member.
    let plain = Run::start(&ctx, &send(None), "w", inputs(json!("ops")), opts()).unwrap();
    let state: Value = serde_json::from_str(&plain.snapshot(None).state).unwrap();
    assert!(state.get("destinations").is_none());
}

/// A checkpoint, then a `verify` whose failure mode rolls back when it did
/// not pass.
fn verified(records: RecordMode) -> (Context, Run) {
    let ctx = ctx();
    let cat = catalog(
        json!([
            {"capability": "checkpoint", "purpose": "p", "store_as": "cp",
             "input_bindings": {"scope": "*"}},
            {"capability": "verify", "purpose": "p", "store_as": "v",
             "input_bindings": {"conditions": ["ok"]},
             "failure_modes": [{"condition": "c", "when": "${v.passed} == false",
                 "action": "rollback"}]}
        ]),
        &[],
    );
    let mut run = Run::start(
        &ctx,
        &cat,
        "w",
        inputs(json!("x")),
        StartOptions { records, ..opts() },
    )
    .unwrap();
    answer(
        &mut run,
        output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
    );
    let rollback = answer(
        &mut run,
        output(json!({"passed": false, "confidence": 1, "evidence_anchors": []})),
    );
    assert_eq!(rollback["kind"], "Rollback");
    (ctx, run)
}

#[test]
fn rolled_back_not_covered_traced() {
    let (_, mut run) = verified(RecordMode::Actions);
    let nc = json!([{"item": "send to ops (r:3)", "reason": "transmitted"},
        {"item": "task t1", "reason": "delegated", "detail": "d"},
        {"item": "x", "reason": "x-vendor"}]);
    let end = answer(
        &mut run,
        Response::RolledBack {
            not_covered: Some(nc.as_array().unwrap().clone()),
        },
    );
    assert_eq!(end["kind"], "Failed");
    let traced = run
        .trace()
        .iter()
        .find(|t| t["kind"] == "rolled_back")
        .cloned()
        .unwrap();
    assert_eq!(traced["detail"]["not_covered"], nc);
    let record = end["action_records"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["capability"] == "rollback")
        .cloned()
        .unwrap();
    assert_eq!(record["details"]["not_covered"], nc);
    assert!(record.get("idempotency_key").is_none());
    // Without `not_covered`, the event has no detail, as in 1.1.
    let (_, mut run) = verified(RecordMode::Approvals);
    answer(&mut run, Response::RolledBack { not_covered: None });
    let traced = run
        .trace()
        .iter()
        .find(|t| t["kind"] == "rolled_back")
        .cloned()
        .unwrap();
    assert_eq!(traced["detail"], json!({}));
}

#[test]
fn rolled_back_bad_reason_refused() {
    for bad in [
        json!({"item": "cfg", "reason": "failed"}),
        json!({"item": 1, "reason": "transmitted"}),
        json!({"item": "a", "reason": "transmitted", "extra": 1}),
        json!({"item": "a", "reason": "transmitted", "detail": 2}),
        json!("a"),
    ] {
        let (_, mut run) = verified(RecordMode::Approvals);
        let before = run.snapshot(None);
        let id = run.next().id;
        let refused = run.submit(
            id,
            Response::RolledBack {
                not_covered: Some(vec![bad.clone()]),
            },
            0,
        );
        assert!(matches!(refused, Err(SubmitError::Malformed(_))), "{bad}");
        assert_eq!(run.snapshot(None), before, "{bad}");
    }
    // A `not_covered` that is present but not a list is malformed (§5.19.1):
    // `null` is refused, not read as absent.
    for bad in [json!(null), json!({}), json!("a")] {
        let r =
            serde_json::from_value::<Response>(json!({"kind": "RolledBack", "not_covered": bad}));
        assert!(r.is_err(), "{bad}");
    }
    // A `RolledBack` without the member deserialises as in 1.1.
    let r: Response = serde_json::from_value(json!({"kind": "RolledBack"})).unwrap();
    assert_eq!(r, Response::RolledBack { not_covered: None });
    assert_eq!(
        serde_json::to_value(&r).unwrap(),
        json!({"kind": "RolledBack"})
    );
}

fn memory(capability: &str, scope: Option<Value>, retry: bool) -> Value {
    let mut b = match capability {
        "persist" => json!({"data": {"a": 1}, "key": "k"}),
        _ => json!({"key": "k"}),
    };
    if let Some(s) = scope {
        b["scope"] = s;
    }
    let mut step = json!({"capability": capability, "purpose": "p", "store_as": "m",
        "input_bindings": b});
    if retry {
        step["retry"] = json!({"max": 1});
    }
    let mut c = catalog(json!([step]), &[]);
    c["w"]["spec_version"] = json!("1.2");
    c
}

fn memory_output(capability: &str, scope: Option<&str>) -> Response {
    let mut v = match capability {
        "persist" => json!({"stored": true, "key": "k", "evidence_anchors": []}),
        _ => json!({"data": 1, "found": true, "evidence_anchors": []}),
    };
    if let Some(s) = scope {
        v["scope"] = json!(s);
    }
    output(v)
}

#[test]
fn scope_echo_mismatch_r402() {
    let ctx = ctx();
    let mut run = Run::start(
        &ctx,
        &memory("persist", Some(json!("session")), false),
        "w",
        inputs(json!("x")),
        opts(),
    )
    .unwrap();
    let end = answer(&mut run, memory_output("persist", Some("global")));
    assert_eq!(failed(&end), (Some("R402"), Some("unsupported_scope")));
}

#[test]
fn scope_echo_absent_r402() {
    // An absent echo is retried as any R402; an echo on the retry completes.
    let ctx = ctx();
    let mut run = Run::start(
        &ctx,
        &memory("recall", Some(json!("run")), true),
        "w",
        inputs(json!("x")),
        opts(),
    )
    .unwrap();
    let retry = answer(&mut run, memory_output("recall", None));
    assert_eq!(retry["attempt"], 2);
    let retried = run
        .trace()
        .iter()
        .find(|t| t["kind"] == "retry")
        .cloned()
        .unwrap();
    assert_eq!(retried["detail"]["reason"], "unsupported_scope");
    let end = answer(&mut run, memory_output("recall", Some("run")));
    assert_eq!(end["kind"], "Completed");
}

#[test]
fn scope_null_not_checked() {
    let ctx = ctx();
    // No `scope`, or one that resolves to null (an optional input not
    // given): nothing is checked, as in 1.1.
    for scope in [None, Some(json!("${maybe}"))] {
        let mut cat = memory("persist", scope, false);
        cat["w"]["inputs"]["maybe"] = json!({"type": "string"});
        let mut run = Run::start(&ctx, &cat, "w", inputs(json!("x")), opts()).unwrap();
        let end = answer(&mut run, memory_output("persist", None));
        assert_eq!(end["kind"], "Completed");
    }
}

#[test]
fn rollback_step_restored_false_completes() {
    // A rollback step completes whatever `restored` says (§4.4.1).
    let ctx = ctx();
    let cat = catalog(
        json!([
            {"capability": "checkpoint", "purpose": "p", "store_as": "cp",
             "input_bindings": {"scope": "*"}},
            {"capability": "rollback", "purpose": "p", "store_as": "rb",
             "input_bindings": {"checkpoint_id": "${cp.checkpoint_id}"}}
        ]),
        &[],
    );
    let mut run = Run::start(&ctx, &cat, "w", inputs(json!("x")), opts()).unwrap();
    answer(
        &mut run,
        output(json!({"checkpoint_id": "cp1", "evidence_anchors": []})),
    );
    let end = answer(
        &mut run,
        output(json!({"restored": false, "evidence_anchors": [],
            "unrestored": [{"item": "cfg", "reason": "failed"}]})),
    );
    assert_eq!(end["kind"], "Completed");
    assert_eq!(end["outputs"]["rb"]["restored"], false);
}
