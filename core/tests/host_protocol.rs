//! The host protocol's run operations (STANDARD v1.2 §5.19): ticks and
//! wake-up times, cancellation, taking records and the trace out of a run's
//! state, the run record, and snapshots of version 1.

use std::path::{Path, PathBuf};

use acs_core::exec::canonical::{canonical, chain, sha256_hex};
use acs_core::exec::{
    Attendance, CancelError, MAX_TIME, RecordMode, ResumeOptions, Run, Snapshot, StartOptions,
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

fn opts(records: RecordMode) -> StartOptions {
    StartOptions {
        attendance: Attendance::Attended,
        run_id: "r".into(),
        now_ms: 0,
        actor_identity: None,
        header: None,
        records,
        profiles: Vec::new(),
        grounding: Vec::new(),
        destinations: Vec::new(),
    }
}

fn wf(steps: Value) -> Value {
    json!({"w": {"goal": "g", "risk": "high", "spec_version": "1.1", "steps": steps,
                 "workflow_extensions": {"requires": ["approval@1"]}}})
}

fn retrieve(extra: Value) -> Value {
    let mut s = json!({"capability": "retrieve", "purpose": "get it", "store_as": "r",
                       "input_bindings": {"target": "t"}});
    for (k, v) in extra.as_object().unwrap() {
        s[k] = v.clone();
    }
    s
}

fn checkpoint() -> Value {
    json!({"capability": "checkpoint", "purpose": "save", "store_as": "cp",
           "input_bindings": {"scope": "repo"}})
}

fn policy() -> Value {
    json!({"capability": "constrain", "purpose": "check", "store_as": "policy",
           "input_bindings": {"target": "config", "constraints": ["policy"]}})
}

fn mutate(extra: Value) -> Value {
    let mut s = json!({"capability": "mutate", "purpose": "change it", "store_as": "m",
                       "input_bindings": {"target": "config", "operation": {"set": 1}}});
    for (k, v) in extra.as_object().unwrap() {
        s[k] = v.clone();
    }
    s
}

fn start(catalog: &Value, records: RecordMode) -> Run {
    Run::start(&ctx(), catalog, "w", Map::new(), opts(records)).unwrap()
}

fn output(value: Value) -> acs_core::exec::Response {
    let mut v = value;
    v["evidence_anchors"] = json!([]);
    acs_core::exec::Response::Output { value: v }
}

fn error(code: &str) -> acs_core::exec::Response {
    acs_core::exec::Response::Error {
        code: code.into(),
        message: "no".into(),
        reason: None,
    }
}

fn answer(run: &mut Run, response: acs_core::exec::Response, now: u64) {
    let id = run.next().id;
    run.submit(id, response, now).unwrap();
}

fn approve(run: &mut Run, decision_id: &str, now: u64) {
    let action = serde_json::to_value(run.next()).unwrap();
    let decision = serde_json::from_value(json!({"kind": "Decision", "decision_id": decision_id,
        "decision": "approved", "approvers": ["alice"], "digest": action["digest"]}))
    .unwrap();
    run.submit(action["id"].as_u64().unwrap(), decision, now)
        .unwrap();
}

fn end(run: &Run) -> Value {
    serde_json::to_value(run.next()).unwrap()
}

// ---- ticks and wake-up times (§5.19.3) ----

#[test]
fn tick_reports_change() {
    let mut run = start(
        &wf(json!([retrieve(json!({"timeout": "10s"}))])),
        RecordMode::Approvals,
    );
    assert!(!run.tick(10_000), "at the deadline the action is in time");
    assert!(run.tick(10_001), "after it, the step times out");
    assert_eq!(end(&run)["code"], "R401");
    assert!(!run.tick(20_000), "an ended run does not change");
}

#[test]
fn wake_at_per_action() {
    // A retry's Sleep: its `until`.
    let mut run = start(
        &wf(json!([retrieve(
            json!({"retry": {"max": 1, "backoff": "linear"}})
        )])),
        RecordMode::Approvals,
    );
    assert_eq!(run.wake_at(), None, "a call without a timeout has none");
    answer(&mut run, error("R402"), 5);
    assert_eq!(end(&run)["kind"], "Sleep");
    assert_eq!(run.wake_at(), Some(1005));
    // An approval's expiry, plus one millisecond.
    let mut run = start(
        &wf(json!([
            checkpoint(),
            policy(),
            mutate(json!({"approval": {"approver": {"kind": "human"}, "expires": "1h"}}))
        ])),
        RecordMode::Approvals,
    );
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    answer(&mut run, output(json!({"compliant": true})), 0);
    assert_eq!(end(&run)["kind"], "RequestApproval");
    assert_eq!(run.wake_at(), Some(3_600_001));
    // A checkpoint, a recheck or a rollback has none; nor has an ended run.
    let mut run = start(&wf(json!([checkpoint()])), RecordMode::Approvals);
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    assert_eq!(run.wake_at(), None);
}

#[test]
fn wake_at_max_deadline_is_none() {
    let catalog = wf(json!([retrieve(json!({"timeout": "10s"}))]));
    let mut late = opts(RecordMode::Approvals);
    late.now_ms = MAX_TIME;
    let run = Run::start(&ctx(), &catalog, "w", Map::new(), late).unwrap();
    assert_eq!(end(&run)["deadline"], json!(MAX_TIME));
    assert_eq!(run.wake_at(), None, "no tick can pass the maximum time");
}

// ---- cancellation (§5.19.5) ----

#[test]
fn cancel_refuses_completed_run() {
    let mut run = start(&wf(json!([retrieve(json!({}))])), RecordMode::Approvals);
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 0);
    assert!(matches!(run.cancel("stop", 1), Err(CancelError::Ended(_))));
    let mut failed = start(&wf(json!([retrieve(json!({}))])), RecordMode::Approvals);
    answer(&mut failed, error("R402"), 0);
    assert!(matches!(
        failed.cancel("stop", 1),
        Err(CancelError::Ended(_))
    ));
}

#[test]
fn cancel_twice_refused() {
    let mut run = start(&wf(json!([retrieve(json!({}))])), RecordMode::Approvals);
    run.cancel("stop", 3).unwrap();
    let e = run.cancel("again", 4).unwrap_err();
    assert!(e.to_string().contains("R408"), "{e}");
}

#[test]
fn submit_after_cancel_refused() {
    let mut run = start(&wf(json!([retrieve(json!({}))])), RecordMode::Approvals);
    let id = run.next().id;
    run.cancel("stop", 3).unwrap();
    assert_eq!(
        run.submit(id, output(json!({"data": [], "confidence": 1})), 4),
        Err(SubmitError::Finished)
    );
    let end = end(&run);
    assert_eq!(end["kind"], "Failed");
    assert_eq!(end["code"], "R408");
    assert_eq!(end["message"], "stop");
    assert_eq!(end["step"], 0);
    assert!(
        end.get("checkpoint_id").is_none(),
        "no checkpoint was known"
    );
    assert_eq!(end["id"], id + 1);
    assert!(!run.tick(10), "a cancelled run does not tick");
}

fn deferred_run() -> (Value, Run) {
    let catalog = wf(json!([
        checkpoint(),
        policy(),
        mutate(json!({"approval": {
        "approver": {"kind": "human"}, "when_unattended": "defer_to_queue"}}))
    ]));
    let mut o = opts(RecordMode::Approvals);
    o.attendance = Attendance::Unattended;
    let mut run = Run::start(&ctx(), &catalog, "w", Map::new(), o).unwrap();
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    answer(&mut run, output(json!({"compliant": true})), 0);
    (catalog, run)
}

#[test]
fn cancel_deferred_then_resume_refused() {
    let (_, mut run) = deferred_run();
    assert_eq!(end(&run)["outcome"], "deferred");
    run.cancel("queue dropped", 9).unwrap();
    let end = end(&run);
    assert_eq!(end["code"], "R408");
    assert_eq!(end["step"], Value::Null, "the run had ended");
    assert_eq!(end["action_records"][0]["status"], "cancelled");
    assert_eq!(end["action_records"][0]["code"], "R408");
    assert_eq!(
        end["deferred"].as_array().unwrap().len(),
        1,
        "deferrals kept"
    );
    let resumed = run.resume(ResumeOptions {
        attendance: Attendance::Attended,
        now_ms: 10,
        actor_identity: None,
    });
    assert!(resumed.is_err());
    // The cancelled state still restores.
    let snap = run.snapshot(None);
    let (catalog, _) = deferred_run();
    assert!(Run::restore(&ctx(), &catalog, &snap, None).is_ok());
}

#[test]
fn cancel_records_started_steps_in_every_frame() {
    let catalog = json!({
        "w": {"goal": "g", "risk": "high", "spec_version": "1.1", "steps": [
            {"capability": "invoke", "purpose": "run it", "store_as": "i",
             "workflow_id": "child", "input_bindings": {"workflow": "child"}}]},
        "child": {"goal": "g", "risk": "low", "spec_version": "1.1", "steps": [
            {"capability": "retrieve", "purpose": "get it", "store_as": "r",
             "input_bindings": {"target": "t"}}]}
    });
    let mut run = start(&catalog, RecordMode::Actions);
    assert_eq!(end(&run)["frame"], json!(["w", "child"]));
    run.cancel("stop", 1).unwrap();
    let end = end(&run);
    assert_eq!(end["frame"], json!(["w", "child"]));
    let records = end["action_records"].as_array().unwrap();
    assert_eq!(records.len(), 2);
    assert_eq!(records[0]["frame"], json!(["w"]));
    assert_eq!(records[0]["capability"], "invoke");
    assert_eq!(records[1]["frame"], json!(["w", "child"]));
    assert_eq!(records[1]["capability"], "retrieve");
    for r in records {
        assert_eq!(r["status"], "cancelled");
        assert_eq!(r["code"], "R408");
        assert_eq!(r["reason"], "stop");
        assert_eq!(r["run_id"], "r");
    }
    assert_eq!(records[1]["action_id"], "r/w/child/0/1");
}

#[test]
fn cancel_does_not_record_unstarted_step() {
    // Waiting for its approval.
    let mut run = start(
        &wf(json!([
            checkpoint(),
            policy(),
            mutate(json!({"approval": {"approver": {"kind": "human"}}}))
        ])),
        RecordMode::Actions,
    );
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    answer(&mut run, output(json!({"compliant": true})), 0);
    assert_eq!(end(&run)["kind"], "RequestApproval");
    run.cancel("stop", 1).unwrap();
    let end_ = end(&run);
    let statuses: Vec<&str> = end_["action_records"]
        .as_array()
        .unwrap()
        .iter()
        .map(|r| r["status"].as_str().unwrap())
        .collect();
    assert_eq!(
        statuses,
        ["executed", "executed"],
        "only the steps that ran"
    );
    assert_eq!(end_["checkpoint_id"], "cp1");
    // Waiting out a delay.
    let catalog = json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
        "workflow_extensions": {"requires": ["wait@1"]},
        "steps": [retrieve(json!({"delay": "1m"}))]}});
    let mut run = start(&catalog, RecordMode::Actions);
    assert_eq!(end(&run)["kind"], "Sleep");
    run.cancel("stop", 1).unwrap();
    assert_eq!(end(&run)["action_records"], json!([]));
}

#[test]
fn cancel_backoff_records_once() {
    let mut run = start(
        &wf(json!([retrieve(
            json!({"retry": {"max": 2, "backoff": "linear"}})
        )])),
        RecordMode::Actions,
    );
    answer(&mut run, error("R402"), 0);
    assert_eq!(end(&run)["kind"], "Sleep");
    run.cancel("stop", 1).unwrap();
    let records = end(&run)["action_records"].clone();
    assert_eq!(records.as_array().unwrap().len(), 1);
    assert_eq!(records[0]["status"], "cancelled");
    assert_eq!(records[0]["capability"], "retrieve");
}

#[test]
fn cancel_failure_checkpoint_records_it() {
    let mut run = start(
        &wf(json!([retrieve(
            json!({"failure_modes": [{"condition": "it fails",
            "on_error": ["R402"], "action": "pause_and_checkpoint",
            "recovery": {"goto_step": "r", "max_loops": 1}}]})
        )])),
        RecordMode::Actions,
    );
    answer(&mut run, error("R402"), 0);
    assert_eq!(end(&run)["kind"], "CreateCheckpoint");
    run.cancel("stop", 1).unwrap();
    let records = end(&run)["action_records"].clone();
    assert_eq!(records.as_array().unwrap().len(), 2);
    assert_eq!(records[0]["status"], "failed");
    assert_eq!(records[0]["code"], "R402");
    assert_eq!(records[1]["capability"], "checkpoint");
    assert_eq!(records[1]["status"], "cancelled");
    assert_eq!(records[1]["code"], "R408");
    assert_eq!(records[1]["step"], 0);
    assert_eq!(records[1]["intent"], "get it");
}

#[test]
fn cancel_approved_record_becomes_cancelled() {
    let mut run = start(
        &wf(json!([
            checkpoint(),
            policy(),
            mutate(json!({"approval": {"approver": {"kind": "human"}}}))
        ])),
        RecordMode::Approvals,
    );
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    answer(&mut run, output(json!({"compliant": true})), 0);
    approve(&mut run, "d1", 0);
    assert_eq!(end(&run)["kind"], "InvokeCapability");
    run.cancel("operator stop", 2).unwrap();
    let end = end(&run);
    assert_eq!(end["checkpoint_id"], "cp1");
    let r = &end["action_records"][0];
    assert_eq!(r["status"], "cancelled");
    assert_eq!(r["code"], "R408");
    assert_eq!(r["checkpoint_id"], "cp1");
    assert_eq!(r["approval"]["decision_id"], "d1");
}

// ---- taking the trace and the records (§5.19.4) ----

#[test]
fn take_trace_keeps_seq() {
    let mut run = start(
        &wf(json!([
            retrieve(json!({})),
            retrieve(json!({"store_as": "r2"}))
        ])),
        RecordMode::Approvals,
    );
    let first = run.take_trace();
    assert!(!first.is_empty());
    assert!(run.trace().is_empty());
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 1);
    let next = run.trace().to_vec();
    assert_eq!(next[0]["seq"], json!(first.len()), "seq goes on");
    // A restored run keeps counting.
    let snap = run.snapshot(None);
    let catalog = wf(json!([
        retrieve(json!({})),
        retrieve(json!({"store_as": "r2"}))
    ]));
    let mut restored = Run::restore(&ctx(), &catalog, &snap, None).unwrap();
    answer(
        &mut restored,
        output(json!({"data": [], "confidence": 1})),
        2,
    );
    let all: Vec<Value> = restored.trace().to_vec();
    for (i, e) in all.iter().enumerate() {
        assert_eq!(e["seq"], json!(first.len() + i));
    }
}

#[test]
fn take_records_keeps_referenced() {
    // An approved record of the step in flight stays; so does a planned one.
    let mut run = start(
        &wf(json!([
            retrieve(json!({})),
            checkpoint(),
            policy(),
            mutate(json!({"approval": {"approver": {"kind": "human"}}}))
        ])),
        RecordMode::Actions,
    );
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 0);
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    answer(&mut run, output(json!({"compliant": true})), 0);
    approve(&mut run, "d1", 0);
    let taken = run.take_records();
    assert_eq!(taken.len(), 3, "the three settled records");
    assert_eq!(run.action_records().len(), 1);
    assert_eq!(run.action_records()[0]["status"], "approved");
    assert!(run.take_records().is_empty(), "the approved one stays");
    answer(&mut run, output(json!({"success": true})), 1);
    let end = end(&run);
    assert_eq!(end["action_records"].as_array().unwrap().len(), 1);
    assert_eq!(end["action_records"][0]["status"], "executed");
    assert_eq!(end["action_records"][0]["action_id"], "r/w/3/3");
    // A deferred run's planned record stays.
    let (_, mut deferred) = deferred_run();
    assert!(deferred.take_records().is_empty());
}

#[test]
fn action_id_counts_taken_records() {
    let mut run = start(
        &wf(json!([
            retrieve(json!({})),
            retrieve(json!({"store_as": "r2"}))
        ])),
        RecordMode::Actions,
    );
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 0);
    assert_eq!(run.take_records().len(), 1);
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 0);
    assert_eq!(run.action_records()[0]["action_id"], "r/w/1/1");
    assert_eq!(run.run_record().unwrap()["details"]["records"], 2);
}

#[test]
fn taken_heads_chain() {
    let catalog = wf(json!([
        retrieve(json!({})),
        retrieve(json!({"store_as": "r2"}))
    ]));
    let mut run = start(&catalog, RecordMode::Actions);
    assert_eq!(run.taken_heads(), ("", ""));
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 0);
    let records = run.take_records();
    let trace = run.take_trace();
    let fold = |items: &[Value]| items.iter().fold(String::new(), |h, item| chain(&h, item));
    assert_eq!(run.taken_heads().0, fold(&records));
    assert_eq!(run.taken_heads().1, fold(&trace));
    let manual = sha256_hex(&(String::new() + &canonical(&records[0])));
    assert_eq!(run.taken_heads().0, manual);
    // A snapshot after taking restores with the same heads.
    let snap = run.snapshot(Some(b"k"));
    let restored = Run::restore(&ctx(), &catalog, &snap, Some(b"k")).unwrap();
    assert_eq!(restored.taken_heads(), run.taken_heads());
    // Editing a head breaks the digest, and with a key the HMAC.
    let mut state: Value = serde_json::from_str(&snap.state).unwrap();
    state["records_taken_sha256"] = json!("0".repeat(64));
    let edited = canonical(&state);
    let unkeyed = Snapshot {
        state: edited.clone(),
        sha256: snap.sha256.clone(),
        hmac: None,
    };
    assert!(Run::restore(&ctx(), &catalog, &unkeyed, None).is_err());
    let rehashed = Snapshot {
        sha256: sha256_hex(&edited),
        state: edited,
        hmac: snap.hmac.clone(),
    };
    assert!(Run::restore(&ctx(), &catalog, &rehashed, Some(b"k")).is_err());
    // A head that is not a head, or one without a base, is refused.
    for (key, value) in [
        ("records_taken_sha256", json!("abc")),
        ("trace_taken_sha256", json!("")),
        ("records_base", json!(0)),
    ] {
        let mut state: Value = serde_json::from_str(&snap.state).unwrap();
        state[key] = value;
        let text = canonical(&state);
        let forged = Snapshot {
            sha256: sha256_hex(&text),
            state: text,
            hmac: None,
        };
        assert!(
            Run::restore(&ctx(), &catalog, &forged, None).is_err(),
            "{key}"
        );
    }
}

// ---- the run record (§5.19.8) ----

#[test]
fn run_record_none_while_running() {
    let run = start(&wf(json!([retrieve(json!({}))])), RecordMode::Approvals);
    assert_eq!(run.run_record(), None);
}

#[test]
fn run_record_completed() {
    let mut run = start(&wf(json!([retrieve(json!({}))])), RecordMode::Approvals);
    answer(
        &mut run,
        output(json!({"data": [], "confidence": 1})),
        1_000,
    );
    let r = run.run_record().unwrap();
    assert_eq!(r["action_id"], "r");
    assert_eq!(r["run_id"], "r");
    assert_eq!(r["frame"], json!(["w"]));
    assert!(r.get("step").is_none());
    assert_eq!(r["timestamp"], "1970-01-01T00:00:01.000Z");
    assert_eq!(r["actor"], "agent");
    assert!(r.get("actor_identity").is_none());
    assert_eq!(r["intent"], "run w");
    assert_eq!(r["status"], "executed");
    assert_eq!(
        r["details"],
        json!({"kind": "Completed", "outcome": "completed", "cause": null,
               "deferred": [], "records": 0})
    );
}

#[test]
fn run_record_failed_without_records() {
    let mut run = start(&wf(json!([retrieve(json!({}))])), RecordMode::Approvals);
    let id = run.next().id;
    let response = acs_core::exec::Response::Error {
        code: "R402".into(),
        message: "no".into(),
        reason: Some(json!("unsupported_domain")),
    };
    run.submit(id, response, 5).unwrap();
    let r = run.run_record().unwrap();
    assert_eq!(r["status"], "failed");
    assert_eq!(r["code"], "R402");
    assert_eq!(r["reason_code"], "unsupported_domain");
    assert_eq!(r["step"], 0);
    assert_eq!(r["details"]["kind"], "Failed");
    assert_eq!(r["details"]["records"], 0);
    assert!(r["details"]["message"].is_string());
}

#[test]
fn run_record_cancelled() {
    let mut run = start(
        &wf(json!([checkpoint(), retrieve(json!({}))])),
        RecordMode::Approvals,
    );
    answer(&mut run, output(json!({"checkpoint_id": "cp9"})), 0);
    run.cancel("operator stop", 7).unwrap();
    let r = run.run_record().unwrap();
    assert_eq!(r["status"], "cancelled");
    assert_eq!(r["code"], "R408");
    assert_eq!(r["checkpoint_id"], "cp9");
    assert_eq!(r["step"], 1);
    assert_eq!(r["details"]["message"], "operator stop");
}

#[test]
fn run_record_deferred_is_planned() {
    let (catalog, mut run) = deferred_run();
    let r = run.run_record().unwrap();
    assert_eq!(r["status"], "planned");
    assert_eq!(r["details"]["outcome"], "deferred");
    assert_eq!(r["details"]["records"], 1);
    assert_eq!(r["details"]["deferred"].as_array().unwrap().len(), 1);
    // Resumed and ended again: the record keeps its action_id.
    let snap = run.snapshot(None);
    run = Run::restore(&ctx(), &catalog, &snap, None).unwrap();
    run.resume(ResumeOptions {
        attendance: Attendance::Unattended,
        now_ms: 5,
        actor_identity: None,
    })
    .unwrap();
    assert_eq!(run.run_record().unwrap()["action_id"], "r");
}

#[test]
fn run_record_counts_taken_records() {
    let mut run = start(
        &wf(json!([
            retrieve(json!({})),
            retrieve(json!({"store_as": "r2"}))
        ])),
        RecordMode::Actions,
    );
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 0);
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 0);
    assert_eq!(run.take_records().len(), 2);
    let r = run.run_record().unwrap();
    assert_eq!(r["details"]["records"], 2);
    assert_eq!(end(&run)["action_records"], json!([]));
}

#[test]
fn run_record_names_the_actor() {
    let catalog = wf(json!([retrieve(json!({}))]));
    let mut o = opts(RecordMode::Approvals);
    o.actor_identity = Some(json!({"principal": "svc-1", "kind": "service"}));
    let mut run = Run::start(&ctx(), &catalog, "w", Map::new(), o).unwrap();
    answer(&mut run, output(json!({"data": [], "confidence": 1})), 0);
    let r = run.run_record().unwrap();
    assert_eq!(r["actor"], "service");
    assert_eq!(r["actor_identity"]["principal"], "svc-1");
}

// ---- record mode `actions` and record members (§6.4) ----

#[test]
fn records_carry_correlation_members() {
    let mut run = start(
        &wf(json!([
            checkpoint(),
            policy(),
            mutate(json!({"approval": {"approver": {"kind": "human"}}}))
        ])),
        RecordMode::Approvals,
    );
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    answer(&mut run, output(json!({"compliant": true})), 0);
    approve(&mut run, "d7", 0);
    answer(&mut run, output(json!({"success": true})), 0);
    let records = end(&run)["action_records"].clone();
    assert_eq!(records.as_array().unwrap().len(), 1, "as in 1.1");
    let r = &records[0];
    assert_eq!(r["run_id"], "r");
    assert_eq!(r["frame"], json!(["w"]));
    assert_eq!(r["step"], 2);
    assert_eq!(r["capability"], "mutate");
    assert_eq!(r["checkpoint_id"], "cp1");
    assert_eq!(r["approval"]["decision_id"], "d7");
    assert_eq!(r["intent"], "change it");
}

#[test]
fn records_actions_write_one_per_pass() {
    let mut run = start(
        &wf(json!([
            checkpoint(),
            policy(),
            mutate(json!({"approval": {"approver": {"kind": "human"}}}))
        ])),
        RecordMode::Actions,
    );
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    answer(&mut run, output(json!({"compliant": true})), 0);
    approve(&mut run, "d7", 0);
    answer(&mut run, output(json!({"success": true})), 0);
    let records = end(&run)["action_records"].clone();
    let caps: Vec<&str> = records
        .as_array()
        .unwrap()
        .iter()
        .map(|r| r["capability"].as_str().unwrap())
        .collect();
    assert_eq!(caps, ["checkpoint", "constrain", "mutate"]);
    assert_eq!(records[0]["checkpoint_id"], "cp1", "the checkpoint it took");
    assert!(records[1].get("checkpoint_id").is_none());
    assert!(
        records
            .as_array()
            .unwrap()
            .iter()
            .all(|r| r["status"] == "executed")
    );
}

#[test]
fn require_record_fails_an_audit_step_that_did_not_record() {
    let catalog = wf(
        json!([{"capability": "audit", "purpose": "log it", "store_as": "a",
        "input_bindings": {"event": {"what": "x"}, "require_record": true}}]),
    );
    let mut run = start(&catalog, RecordMode::Approvals);
    answer(&mut run, output(json!({"recorded": false})), 0);
    let end = end(&run);
    assert_eq!(end["code"], "R402");
    assert_eq!(end["reason"], "not_recorded");
    // Without it the step completes.
    let catalog = wf(
        json!([{"capability": "audit", "purpose": "log it", "store_as": "a",
        "input_bindings": {"event": {"what": "x"}}}]),
    );
    let mut run = start(&catalog, RecordMode::Approvals);
    answer(&mut run, output(json!({"recorded": false})), 0);
    assert_eq!(
        serde_json::to_value(run.next()).unwrap()["outcome"],
        "completed"
    );
}

// ---- snapshots (§5.19.4) ----

fn recorded_v1() -> Vec<Value> {
    let text = std::fs::read_to_string(root().join("core/tests/data/snapshots_v1.json")).unwrap();
    let file: Value = serde_json::from_str(&text).unwrap();
    file["cases"].as_array().unwrap().clone()
}

fn snapshot_of(case: &Value) -> Snapshot {
    serde_json::from_value(case["snapshot"].clone()).unwrap()
}

#[test]
fn snapshot_v1_restores() {
    let cases = recorded_v1();
    assert!(cases.len() >= 4);
    for case in cases {
        let name = case["name"].as_str().unwrap();
        let snap = snapshot_of(&case);
        assert!(snap.state.contains("\"version\":1"), "{name}");
        let run = Run::restore(&ctx(), &case["catalog"], &snap, None)
            .unwrap_or_else(|e| panic!("{name}: {e}"));
        // The action is the one recorded then, with the run's id.
        let mut expected = case["next"].clone();
        let actual = serde_json::to_value(run.next()).unwrap();
        expected["run_id"] = actual["run_id"].clone();
        assert_eq!(actual, expected, "{name}");
        assert!(!actual["run_id"].as_str().unwrap().is_empty(), "{name}");
        // Saved again, it is version 2.
        assert!(run.snapshot(None).state.contains("\"version\":2"), "{name}");
    }
}

#[test]
fn snapshot_v1_tampered_terminal_refused() {
    for case in recorded_v1() {
        let name = case["name"].as_str().unwrap();
        let snap = snapshot_of(&case);
        let mut state: Value = serde_json::from_str(&snap.state).unwrap();
        if state["finished"].is_null() {
            continue;
        }
        state["finished"]["action_records"] = json!([{"action_id": "x", "timestamp": "t",
            "actor": "agent", "intent": "forged", "status": "executed"}]);
        let text = canonical(&state);
        let forged = Snapshot {
            sha256: sha256_hex(&text),
            state: text,
            hmac: None,
        };
        assert!(
            Run::restore(&ctx(), &case["catalog"], &forged, None).is_err(),
            "{name}: a terminal action that differs from the state was restored"
        );
    }
}

#[test]
fn finished_snapshot_has_no_duplicate_records() {
    let mut run = start(
        &wf(json!([
            checkpoint(),
            policy(),
            mutate(json!({"approval": {"approver": {"kind": "human"}}}))
        ])),
        RecordMode::Approvals,
    );
    answer(&mut run, output(json!({"checkpoint_id": "cp1"})), 0);
    answer(&mut run, output(json!({"compliant": true})), 0);
    approve(&mut run, "d1", 0);
    answer(
        &mut run,
        output(json!({"success": true, "written": true})),
        0,
    );
    let state = run.snapshot(None).state;
    assert_eq!(
        state.matches("\"intent\":\"change it\"").count(),
        1,
        "records once"
    );
    let state: Value = serde_json::from_str(&state).unwrap();
    assert!(state["finished"].get("action_records").is_none());
    assert!(state["finished"].get("outputs").is_none());
    assert_eq!(state["version"], 2);
}
