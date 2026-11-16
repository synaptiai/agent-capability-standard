//! Runtime conformance fixtures (design-114 §16.6): every scripted run must
//! produce the expected actions, end and trace — and the same again when
//! the run is snapshotted and restored before every step.

use std::path::{Path, PathBuf};

use acs_core::exec::canonical::canonical;
use acs_core::exec::{
    Attendance, RecordMode, Response, ResumeOptions, Run, SetOptions, StartOptions, read_json,
};
use acs_core::validate::Context;
use serde_json::{Map, Value};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..")
}

/// `expected` matches `actual` when every key it names matches (objects
/// recursively; arrays element by element, of the same length).
fn matches(expected: &Value, actual: &Value) -> bool {
    match (expected, actual) {
        (Value::Object(e), Value::Object(a)) => e
            .iter()
            .all(|(k, v)| a.get(k).is_some_and(|x| matches(v, x))),
        (Value::Array(e), Value::Array(a)) => {
            e.len() == a.len() && e.iter().zip(a).all(|(x, y)| matches(x, y))
        }
        _ => expected == actual,
    }
}

/// Replace `"{{digest}}"` in a response with the pending action's digest,
/// and `"{{digest_upper}}"` with it in uppercase.
fn fill(response: &Value, action: &Value) -> Value {
    match response {
        Value::String(s) if s == "{{digest}}" => action["digest"].clone(),
        Value::String(s) if s == "{{digest_upper}}" => {
            Value::String(action["digest"].as_str().unwrap_or_default().to_uppercase())
        }
        Value::Object(m) => Value::Object(
            m.iter()
                .map(|(k, v)| (k.clone(), fill(v, action)))
                .collect(),
        ),
        Value::Array(a) => Value::Array(a.iter().map(|v| fill(v, action)).collect()),
        other => other.clone(),
    }
}

/// The start options a fixture states (`tests/conformance/runtime/schema/
/// fixture.schema.json`): every member it gives is passed to start. The
/// catalog's `header` is required, as the start operation requires it.
fn fixture_options(name: &str, f: &Value, now: u64) -> StartOptions {
    let attendance = match f["attendance"].as_str() {
        Some("unattended") => Attendance::Unattended,
        _ => Attendance::Attended,
    };
    let header = match f.get("header") {
        Some(Value::String(h)) => Some(h.clone()),
        Some(Value::Null) => None,
        other => panic!(
            "{name}: a fixture states its catalog's header (a version or null), found {other:?}"
        ),
    };
    let records = match f.get("records").and_then(Value::as_str) {
        None | Some("approvals") => RecordMode::Approvals,
        Some("actions") => RecordMode::Actions,
        Some(other) => panic!("{name}: records '{other}'"),
    };
    let list = |key: &str| -> Vec<Value> {
        f.get(key)
            .map(|v| {
                v.as_array()
                    .cloned()
                    .unwrap_or_else(|| panic!("{name}: {key} is not a list"))
            })
            .unwrap_or_default()
    };
    StartOptions {
        attendance,
        run_id: "run-1".into(),
        now_ms: now,
        actor_identity: f.get("actor_identity").cloned(),
        header,
        records,
        profiles: list("profiles"),
        grounding: list("grounding")
            .into_iter()
            .map(|g| serde_json::from_value(g).unwrap_or_else(|e| panic!("{name}: grounding: {e}")))
            .collect(),
        destinations: f
            .get("destinations")
            .map(|v| {
                serde_json::from_value(v.clone())
                    .unwrap_or_else(|e| panic!("{name}: destinations: {e}"))
            })
            .unwrap_or_default(),
    }
}

/// The other catalogs of a fixture's catalog set, each with its header
/// (`[{catalog, header}]`, §5.1.1), and its agent manifests (§5.15.1).
fn fixture_set(name: &str, f: &Value) -> SetOptions {
    let catalogs = f
        .get("catalogs")
        .map(|v| {
            v.as_array()
                .unwrap_or_else(|| panic!("{name}: catalogs is not a list"))
                .iter()
                .map(|c| {
                    let header = match c.get("header") {
                        Some(Value::String(h)) => Some(h.clone()),
                        Some(Value::Null) => None,
                        other => panic!(
                            "{name}: a catalog of the set states its header, found {other:?}"
                        ),
                    };
                    (c["catalog"].clone(), header)
                })
                .collect()
        })
        .unwrap_or_default();
    let agents = f
        .get("agents")
        .map(|v| {
            v.as_array()
                .cloned()
                .unwrap_or_else(|| panic!("{name}: agents is not a list"))
        })
        .unwrap_or_default();
    SetOptions { catalogs, agents }
}

/// How a fixture is replayed (§10.5): as scripted, with the run's state
/// saved and restored before every entry, or with the trace and the settled
/// records taken out of the state before every entry (§5.19.4).
#[derive(Clone, Copy, PartialEq)]
enum Replay {
    Plain,
    Restore,
    Drain,
}

/// What a replay saw: every action and the end, as canonical JSON (RFC 8785,
/// so object key order does not matter but array order does); the end; the
/// trace and the records taken (a drain replay), with the trace left in the
/// run; and the run record derived from the end.
struct Played {
    seen: Vec<String>,
    end: Value,
    trace: Vec<Value>,
    taken_trace: Vec<Value>,
    taken_records: Vec<Value>,
    run_record: Option<Value>,
}

/// Fold items into a chain head from the empty string (§5.19.4).
fn fold(items: &[Value]) -> String {
    items.iter().fold(String::new(), |h, item| {
        acs_core::exec::canonical::chain(&h, item)
    })
}

/// Run one fixture in the given replay mode. At every `tick` entry the tick
/// must change the run exactly when its time reaches the run's wake-up time
/// (§5.19.3), and as the entry says when it gives `changed`.
fn play(ctx: &Context, name: &str, f: &Value, mode: Replay) -> Played {
    let catalog = &f["catalog"];
    let inputs: Map<String, Value> = f["inputs"].as_object().cloned().unwrap_or_default();
    let mut now = f["start"].as_u64().unwrap_or(0);
    let set = fixture_set(name, f);
    let mut run = Run::start_set(
        ctx,
        catalog,
        &set,
        f["workflow"].as_str().unwrap(),
        inputs,
        fixture_options(name, f, now),
    )
    .unwrap_or_else(|e| panic!("{name}: start: {e}"));
    let mut seen = Vec::new();
    let mut taken_trace = Vec::new();
    let mut taken_records = Vec::new();
    for (i, entry) in f["script"].as_array().unwrap().iter().enumerate() {
        match mode {
            Replay::Plain => {}
            Replay::Restore => {
                let snap = run.snapshot(Some(b"key"));
                run = Run::restore_set(ctx, catalog, &set, &snap, Some(b"key"), Default::default())
                    .unwrap_or_else(|e| panic!("{name}: restore before {i}: {e}"));
            }
            Replay::Drain => {
                taken_trace.extend(run.take_trace());
                taken_records.extend(run.take_records());
                let (records, trace) = run.taken_heads();
                assert_eq!(
                    records,
                    fold(&taken_records),
                    "{name}: before {i}: the records' chain head"
                );
                assert_eq!(
                    trace,
                    fold(&taken_trace),
                    "{name}: before {i}: the trace's chain head"
                );
            }
        }
        if let Some(t) = entry.get("tick").and_then(Value::as_u64) {
            now = t;
            let wake = run.wake_at();
            let changed = run.tick(t);
            assert_eq!(
                changed,
                wake.is_some_and(|w| t >= w),
                "{name}: script[{i}]: tick {t} with wake-up time {wake:?}"
            );
            if let Some(c) = entry.get("changed") {
                assert_eq!(Some(changed), c.as_bool(), "{name}: script[{i}]: changed");
            }
            continue;
        }
        if let Some(w) = entry.get("wake_at") {
            assert_eq!(
                run.wake_at(),
                w.as_u64(),
                "{name}: script[{i}]: wake_at {w}"
            );
            continue;
        }
        if let Some(c) = entry.get("cancel") {
            if let Some(at) = c.get("at").and_then(Value::as_u64) {
                now = at;
            }
            let reason = c["reason"].as_str().unwrap_or_default();
            run.cancel(reason, now)
                .unwrap_or_else(|e| panic!("{name}: script[{i}]: cancel: {e}"));
            continue;
        }
        // A resume entry (§5.14.1): the host keeps the run's state while it
        // waits, restores it, and resumes it.
        if let Some(resume) = entry.get("resume") {
            if let Some(at) = resume.get("at").and_then(Value::as_u64) {
                now = at;
            }
            let snap = run.snapshot(Some(b"key"));
            run = Run::restore_set(ctx, catalog, &set, &snap, Some(b"key"), Default::default())
                .unwrap_or_else(|e| panic!("{name}: restore at {i}: {e}"));
            let attendance = match resume.get("attendance").and_then(Value::as_str) {
                Some("unattended") => Attendance::Unattended,
                _ => Attendance::Attended,
            };
            run.resume(ResumeOptions {
                attendance,
                now_ms: now,
                actor_identity: resume.get("actor_identity").cloned(),
            })
            .unwrap_or_else(|e| panic!("{name}: resume at {i}: {e}"));
            continue;
        }
        let mut action = serde_json::to_value(run.next()).unwrap();
        assert_eq!(action["run_id"], "run-1", "{name}: script[{i}]: run_id");
        if mode == Replay::Drain {
            restore_taken(&mut action, &taken_records);
        }
        seen.push(canonical(&action));
        if let Some(expect) = entry.get("expect") {
            assert!(
                matches(expect, &action),
                "{name}: script[{i}]: expected {expect}\n  got {action}"
            );
        }
        if let Some(respond) = entry.get("respond") {
            if let Some(at) = entry.get("at").and_then(Value::as_u64) {
                now = at;
            }
            let response: Response = serde_json::from_value(fill(respond, &action))
                .unwrap_or_else(|e| panic!("{name}: script[{i}]: bad response: {e}"));
            let id = action["id"].as_u64().unwrap();
            run.submit(id, response, now)
                .unwrap_or_else(|e| panic!("{name}: script[{i}]: submit: {e}"));
        }
    }
    let mut end = serde_json::to_value(run.next()).unwrap();
    assert_eq!(end["run_id"], "run-1", "{name}: the end's run_id");
    if mode == Replay::Drain {
        restore_taken(&mut end, &taken_records);
    }
    seen.push(canonical(&end));
    if mode == Replay::Drain {
        // The final state vouches for everything taken: its heads are the
        // fold, and a keyed snapshot of it restores.
        let snap = run.snapshot(Some(b"key"));
        let restored =
            Run::restore_set(ctx, catalog, &set, &snap, Some(b"key"), Default::default())
                .unwrap_or_else(|e| panic!("{name}: restore after draining: {e}"));
        assert_eq!(restored.taken_heads().0, fold(&taken_records), "{name}");
        assert_eq!(restored.taken_heads().1, fold(&taken_trace), "{name}");
    }
    Played {
        seen,
        end,
        trace: run.trace().to_vec(),
        taken_trace,
        taken_records,
        run_record: run.run_record(),
    }
}

/// A terminal action of a run whose host took records holds the records not
/// taken (§5.19.1): with the taken ones before them, it is the action of a
/// run that took none.
fn restore_taken(action: &mut Value, taken: &[Value]) {
    if let Some(left) = action.get("action_records").and_then(Value::as_array) {
        let mut all = taken.to_vec();
        all.extend(left.iter().cloned());
        action["action_records"] = Value::Array(all);
    }
}

/// The matching of class EX (§10.5): as [`matches`], but text the executor
/// composes is not compared: `message` (except `ended.message`), `reason`
/// in an item of `action_records` or `deferred`, and `ignored`, `note` and
/// `quorum` in an item of a `violations` list under `outputs`.
fn ex_matches(expected: &Value, actual: &Value, path: &mut Vec<String>) -> bool {
    let under = |path: &[String], list: &str| {
        path.len() >= 2 && path[path.len() - 1] == "[]" && path[path.len() - 2] == list
    };
    match (expected, actual) {
        (Value::Object(e), Value::Object(a)) => e.iter().all(|(k, v)| {
            let prose = (k == "message" && path.last().is_none_or(|p| p != "ended"))
                || (k == "reason" && (under(path, "action_records") || under(path, "deferred")))
                || (matches!(k.as_str(), "ignored" | "note" | "quorum")
                    && under(path, "violations")
                    && path.iter().any(|p| p == "outputs"));
            if prose {
                return true;
            }
            path.push(k.clone());
            let ok = a.get(k).is_some_and(|x| ex_matches(v, x, path));
            path.pop();
            ok
        }),
        (Value::Array(e), Value::Array(a)) => {
            path.push("[]".into());
            let ok = e.len() == a.len() && e.iter().zip(a).all(|(x, y)| ex_matches(x, y, path));
            path.pop();
            ok
        }
        _ => expected == actual,
    }
}

fn fixtures() -> Vec<(String, Value)> {
    let dir = root().join("tests/conformance/runtime");
    let mut names: Vec<PathBuf> = std::fs::read_dir(&dir)
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    names.sort();
    assert!(
        names.len() >= 20,
        "runtime fixtures missing in {}",
        dir.display()
    );
    names
        .into_iter()
        .map(|path| {
            let name = path.file_stem().unwrap().to_string_lossy().to_string();
            // Read as a host's JSON is read: no integer beyond 2^53.
            let f: Value = read_json(&std::fs::read_to_string(&path).unwrap())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            (name, f)
        })
        .collect()
}

#[test]
fn runtime_fixtures() {
    let root = root();
    let ctx = Context::load(&root.join("schemas/capability_ontology.yaml"), &root).unwrap();
    for (name, f) in fixtures() {
        let plain = play(&ctx, &name, &f, Replay::Plain);
        assert!(
            matches(&f["end"], &plain.end),
            "{name}: expected end {}\n  got {}",
            f["end"],
            plain.end
        );
        if let Some(expected) = f.get("run_record") {
            let actual = plain.run_record.clone().unwrap_or(Value::Null);
            assert!(
                matches(expected, &actual),
                "{name}: expected run_record {expected}\n  got {actual}"
            );
        }
        let kinds: Vec<&str> = plain
            .trace
            .iter()
            .filter_map(|t| t["kind"].as_str())
            .collect();
        for k in f["trace_kinds"].as_array().unwrap() {
            assert!(
                kinds.contains(&k.as_str().unwrap()),
                "{name}: trace lacks {k}: {kinds:?}"
            );
        }
        // Snapshots are complete: restoring before every step changes
        // nothing.
        let restored = play(&ctx, &name, &f, Replay::Restore);
        assert_eq!(
            plain.seen, restored.seen,
            "{name}: restore changed an action or the end"
        );
        assert_eq!(
            canonical(&Value::Array(plain.trace.clone())),
            canonical(&Value::Array(restored.trace)),
            "{name}: restore changed the trace"
        );
        assert_eq!(plain.run_record, restored.run_record, "{name}: run record");
        // Taking the trace and the settled records out changes no action:
        // the records taken, with those a terminal action holds, are the
        // records of a run that took none.
        let drained = play(&ctx, &name, &f, Replay::Drain);
        assert_eq!(
            plain.seen, drained.seen,
            "{name}: taking records or the trace changed an action"
        );
        let mut trace = drained.taken_trace.clone();
        trace.extend(drained.trace.iter().cloned());
        assert_eq!(
            canonical(&Value::Array(trace)),
            canonical(&Value::Array(plain.trace.clone())),
            "{name}: the taken trace and the rest are not the run's trace"
        );
        let count = |r: &Option<Value>| r.as_ref().map(|r| r["details"]["records"].clone());
        assert_eq!(
            count(&drained.run_record),
            count(&plain.run_record),
            "{name}: the run record's count"
        );
        assert_eq!(
            count(&plain.run_record),
            Some(serde_json::json!(
                plain.end["action_records"].as_array().unwrap().len()
            )),
            "{name}: the run record counts the run's records"
        );
        // Dropping or editing any one taken item breaks the fold.
        for items in [&drained.taken_records, &drained.taken_trace] {
            let head = fold(items);
            for i in 0..items.len() {
                let mut dropped = items.clone();
                dropped.remove(i);
                assert_ne!(fold(&dropped), head, "{name}: dropping item {i}");
                let mut edited = items.clone();
                edited[i]["edited"] = Value::Bool(true);
                assert_ne!(fold(&edited), head, "{name}: editing item {i}");
            }
        }
    }
}

#[test]
fn runtime_fixtures_ex_matching() {
    // Every fixture passes under the EX rule (§10.5), and the rule leaves
    // out executor prose only.
    let ctx = ctx();
    for (name, f) in fixtures() {
        let plain = play(&ctx, &name, &f, Replay::Plain);
        assert!(
            ex_matches(&f["end"], &plain.end, &mut Vec::new()),
            "{name}: EX end"
        );
    }
    let actual = serde_json::json!({
        "kind": "Failed", "code": "R402", "message": "the executor's words", "reason": "not_recorded",
        "action_records": [{"status": "rejected", "reason": "words"}],
        "deferred": [{"step": 1, "reason": "words"}],
        "ended": {"step": 0, "message": "the author's"},
        "outputs": {"q": {"violations": [{"reviewer_id": "r", "note": "words"}, {"quorum": "words"}]}}
    });
    let prose = serde_json::json!({
        "message": "other words",
        "action_records": [{"status": "rejected", "reason": "other"}],
        "deferred": [{"step": 1, "reason": "other"}],
        "outputs": {"q": {"violations": [{"reviewer_id": "r", "note": "other"}, {"quorum": "other"}]}}
    });
    assert!(ex_matches(&prose, &actual, &mut Vec::new()));
    assert!(!matches(&prose, &actual));
    for compared in [
        serde_json::json!({"reason": "unsupported_domain"}),
        serde_json::json!({"ended": {"message": "another"}}),
        serde_json::json!({"action_records": [{"status": "executed"}]}),
        serde_json::json!({"outputs": {"q": {"violations": [{"reviewer_id": "s"}, {}]}}}),
    ] {
        assert!(
            !ex_matches(&compared, &actual, &mut Vec::new()),
            "{compared}"
        );
    }
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

fn one_step() -> Value {
    serde_json::json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
        "inputs": {"topic": {"type": "string", "required": true}},
        "steps": [{"capability": "retrieve", "purpose": "p", "store_as": "r",
                   "input_bindings": {"target": "${topic}"}}]}})
}

fn topic() -> Map<String, Value> {
    serde_json::json!({"topic": "x"})
        .as_object()
        .unwrap()
        .clone()
}

#[test]
fn start_refuses_invalid_catalogs_and_inputs() {
    let ctx = ctx();
    let mut bad = one_step();
    bad["w"]["steps"][0]["capability"] = serde_json::json!("teleport");
    assert!(matches!(
        Run::start(&ctx, &bad, "w", topic(), opts()),
        Err(acs_core::exec::StartError::Invalid(_))
    ));
    let missing = Run::start(&ctx, &one_step(), "w", Map::new(), opts());
    assert!(matches!(
        missing,
        Err(acs_core::exec::StartError::Inputs(_))
    ));
    let mut extra = topic();
    extra.insert("other".into(), serde_json::json!(1));
    assert!(Run::start(&ctx, &one_step(), "w", extra, opts()).is_err());
    assert!(Run::start(&ctx, &one_step(), "nope", topic(), opts()).is_err());
}

#[test]
fn submit_refuses_responses_that_do_not_answer() {
    let ctx = ctx();
    let mut run = Run::start(&ctx, &one_step(), "w", topic(), opts()).unwrap();
    let id = run.next().id;
    let before = run.snapshot(None);
    let wrong_id = run.submit(id + 1, Response::RolledBack, 0);
    assert!(matches!(
        wrong_id,
        Err(acs_core::exec::SubmitError::WrongAction { .. })
    ));
    let wrong_kind = run.submit(id, Response::RolledBack, 0);
    assert!(matches!(
        wrong_kind,
        Err(acs_core::exec::SubmitError::Unexpected { .. })
    ));
    assert_eq!(
        run.snapshot(None),
        before,
        "a refused response changes nothing"
    );
    let ok = Response::Output {
        value: serde_json::json!({"data": 1, "evidence_anchors": [], "confidence": 1}),
        evidence_seen: None,
    };
    run.submit(id, ok.clone(), 5).unwrap();
    assert!(run.is_finished());
    assert!(matches!(
        run.submit(run.next().id, ok, 6),
        Err(acs_core::exec::SubmitError::Finished)
    ));
    // Ticks after the end change nothing.
    let done = run.snapshot(None);
    run.tick(1_000_000);
    assert_eq!(run.snapshot(None), done);
}

#[test]
fn restore_checks_digest_hmac_and_catalog() {
    let ctx = ctx();
    let catalog = one_step();
    let run = Run::start(&ctx, &catalog, "w", topic(), opts()).unwrap();
    let snap = run.snapshot(Some(b"k"));
    assert!(Run::restore(&ctx, &catalog, &snap, Some(b"k")).is_ok());
    // A signed snapshot is only trusted with its key.
    assert!(matches!(
        Run::restore(&ctx, &catalog, &snap, None),
        Err(acs_core::exec::RestoreError::Hmac)
    ));
    assert!(Run::restore(&ctx, &catalog, &run.snapshot(None), None).is_ok());
    let mut tampered = run.snapshot(None);
    tampered.state = tampered.state.replace("\"now\":0", "\"now\":1");
    assert_ne!(tampered.state, snap.state);
    assert!(matches!(
        Run::restore(&ctx, &catalog, &tampered, None),
        Err(acs_core::exec::RestoreError::Digest)
    ));
    assert!(matches!(
        Run::restore(&ctx, &catalog, &snap, Some(b"other")),
        Err(acs_core::exec::RestoreError::Hmac)
    ));
    let unsigned = run.snapshot(None);
    assert!(matches!(
        Run::restore(&ctx, &catalog, &unsigned, Some(b"k")),
        Err(acs_core::exec::RestoreError::Hmac)
    ));
    let mut changed = catalog.clone();
    changed["w"]["goal"] = serde_json::json!("another goal");
    assert!(matches!(
        Run::restore(&ctx, &changed, &snap, Some(b"k")),
        Err(acs_core::exec::RestoreError::Catalog)
    ));
}

#[test]
fn nesting_is_bounded() {
    // a → b → c → d → e: the fifth run would exceed MAX_FRAMES.
    let ctx = ctx();
    let names = ["a", "b", "c", "d", "e"];
    let mut catalog = Map::new();
    for (i, n) in names.iter().enumerate() {
        let step = if let Some(next) = names.get(i + 1) {
            serde_json::json!({"capability": "invoke", "purpose": "p", "store_as": "i",
                               "workflow_id": next, "input_bindings": {"workflow": next}})
        } else {
            serde_json::json!({"capability": "observe", "purpose": "p", "store_as": "o",
                               "input_bindings": {"target": "t"}})
        };
        catalog.insert(
            n.to_string(),
            serde_json::json!({"goal": "g", "risk": "low", "spec_version": "1.1", "steps": [step]}),
        );
    }
    let run = Run::start(&ctx, &Value::Object(catalog), "a", Map::new(), opts()).unwrap();
    let end = serde_json::to_value(run.next()).unwrap();
    assert_eq!(end["kind"], "Failed", "{end}");
    assert_eq!(end["code"], "R402");
    assert_eq!(end["frame"], serde_json::json!(["a"]));
}

#[test]
fn runs_are_deterministic() {
    let ctx = ctx();
    let play = || {
        let mut run = Run::start(&ctx, &one_step(), "w", topic(), opts()).unwrap();
        let id = run.next().id;
        run.submit(
            id,
            Response::Output {
                value: serde_json::json!({"data": [1.5, "é"], "evidence_anchors": [], "confidence": 1}),
                evidence_seen: None,
            },
            42,
        )
        .unwrap();
        run.snapshot(Some(b"k"))
    };
    assert_eq!(play(), play());
}

/// A snapshot whose state was rewritten and its digest recomputed: it is
/// self-consistent, so only the structural check can refuse it.
fn forged(snap: &acs_core::exec::Snapshot, edit: impl Fn(&mut Value)) -> acs_core::exec::Snapshot {
    let mut state: Value = serde_json::from_str(&snap.state).unwrap();
    edit(&mut state);
    let text = canonical(&state);
    acs_core::exec::Snapshot {
        sha256: acs_core::exec::canonical::sha256_hex(&text),
        state: text,
        hmac: None,
    }
}

#[test]
fn restore_refuses_malformed_states() {
    let ctx = ctx();
    let catalog = one_step();
    let run = Run::start(&ctx, &catalog, "w", topic(), opts()).unwrap();
    let snap = run.snapshot(None);
    type Edit = Box<dyn Fn(&mut Value)>;
    let cases: Vec<(&str, Edit)> = vec![
        (
            "no frames",
            Box::new(|s| s["frames"] = serde_json::json!([])),
        ),
        (
            "step out of range",
            Box::new(|s| s["frames"][0]["step"] = serde_json::json!(7)),
        ),
        (
            "unknown workflow",
            Box::new(|s| s["frames"][0]["workflow"] = serde_json::json!("x")),
        ),
        (
            "pending and finished",
            Box::new(|s| {
                let p = s["pending"]["action"].clone();
                s["finished"] = p;
            }),
        ),
        ("no action at all", Box::new(|s| s["pending"] = Value::Null)),
        (
            "malformed actor identity",
            Box::new(|s| s["actor_identity"] = serde_json::json!({"kind": "agent"})),
        ),
        (
            "missing record",
            Box::new(|s| s["frames"][0]["cur"]["record"] = serde_json::json!(3)),
        ),
        (
            "deferred step out of range",
            Box::new(|s| s["frames"][0]["deferred"] = serde_json::json!([5])),
        ),
        (
            "deferred step twice",
            Box::new(|s| s["frames"][0]["deferred"] = serde_json::json!([0, 0])),
        ),
        (
            "deferral in an unknown workflow",
            Box::new(|s| {
                s["deferrals"] = serde_json::json!([{"frame": ["x"], "path": [0],
                    "store_as": null, "reason": "r", "record": null}]);
            }),
        ),
        (
            "deferral with a missing record",
            Box::new(|s| {
                s["deferrals"] = serde_json::json!([{"frame": ["w"], "path": [0],
                    "store_as": null, "reason": "r", "record": 3}]);
            }),
        ),
        (
            "deferral path of the wrong length",
            Box::new(|s| {
                s["deferrals"] = serde_json::json!([{"frame": ["w"], "path": [0, 0],
                    "store_as": null, "reason": "r", "record": null}]);
            }),
        ),
        (
            "purpose that does not fit the action",
            Box::new(|s| s["pending"]["purpose"] = serde_json::json!({"purpose": "Event"})),
        ),
        (
            "a failure mode that does not exist",
            Box::new(|s| {
                s["pending"]["action"]["kind"] = serde_json::json!("Rollback");
                s["pending"]["action"]["checkpoint_id"] = serde_json::json!("cp");
                s["pending"]["purpose"] =
                    serde_json::json!({"purpose": "FailureRollback", "mode": 7});
            }),
        ),
        (
            "record that is not an object",
            Box::new(|s| {
                s["records"] = serde_json::json!([5]);
                s["frames"][0]["cur"]["record"] = serde_json::json!(0);
            }),
        ),
        (
            "pending action past the last step",
            Box::new(|s| {
                s["frames"][0]["step"] = serde_json::json!(1);
                s["frames"][0]["stage"] = serde_json::json!({"stage": "Begin"});
                s["pending"]["action"]["step"] = serde_json::json!(1);
            }),
        ),
        (
            "sleep outside a backoff",
            Box::new(|s| {
                let id = s["pending"]["action"]["id"].clone();
                s["pending"]["action"] =
                    serde_json::json!({"id": id, "frame": ["w"], "kind": "Sleep", "until": 5});
                s["pending"]["purpose"] = serde_json::json!({"purpose": "Sleep"});
            }),
        ),
        (
            "terminal action that is not terminal",
            Box::new(|s| {
                s["finished"] = s["pending"]["action"].clone();
                s["pending"] = Value::Null;
            }),
        ),
        (
            "bad version",
            Box::new(|s| s["version"] = serde_json::json!(99)),
        ),
        (
            "not a state",
            Box::new(|s| *s = serde_json::json!({"hello": 1})),
        ),
    ];
    for (what, edit) in cases {
        let bad = forged(&snap, edit);
        assert!(
            Run::restore(&ctx, &catalog, &bad, None).is_err(),
            "{what}: a forged state was restored"
        );
    }
    // A state saved before deferrals were tracked still restores.
    let older = forged(&snap, |s| {
        s.as_object_mut().unwrap().remove("deferrals");
        s["frames"][0].as_object_mut().unwrap().remove("deferred");
    });
    assert!(Run::restore(&ctx, &catalog, &older, None).is_ok());
}

#[test]
fn values_must_be_ijson() {
    let ctx = ctx();
    let mut run = Run::start(&ctx, &one_step(), "w", topic(), opts()).unwrap();
    let id = run.next().id;
    let before = run.snapshot(None);
    let big = Response::Output {
        value: serde_json::json!({"data": 9007199254740993u64, "evidence_anchors": [], "confidence": 1}),
        evidence_seen: None,
    };
    assert!(matches!(
        run.submit(id, big, 1),
        Err(acs_core::exec::SubmitError::Malformed(_))
    ));
    let mut deep = serde_json::json!(1);
    for _ in 0..120 {
        deep = serde_json::json!([deep]);
    }
    let deep = Response::Output {
        value: serde_json::json!({"data": deep, "evidence_anchors": [], "confidence": 1}),
        evidence_seen: None,
    };
    assert!(matches!(
        run.submit(id, deep, 1),
        Err(acs_core::exec::SubmitError::Malformed(_))
    ));
    assert_eq!(run.snapshot(None), before);
    let mut inputs = topic();
    inputs.insert("topic".into(), serde_json::json!(-9007199254740993i64));
    assert!(Run::start(&ctx, &one_step(), "w", inputs, opts()).is_err());
    // Times beyond 2^53 are capped, so they still snapshot exactly.
    let mut late = StartOptions {
        now_ms: u64::MAX,
        ..opts()
    };
    late.run_id = "late".into();
    let run = Run::start(&ctx, &one_step(), "w", topic(), late).unwrap();
    let snap = run.snapshot(None);
    assert!(Run::restore(&ctx, &one_step(), &snap, None).is_ok());
}

#[test]
fn restore_refuses_a_parent_frame_that_is_not_invoking() {
    // A nested run is pending; the parent frame must sit at its invoke step.
    let ctx = ctx();
    let catalog = serde_json::json!({
        "a": {"goal": "g", "risk": "low", "spec_version": "1.1", "steps": [
            {"capability": "invoke", "purpose": "p", "store_as": "i",
             "workflow_id": "b", "input_bindings": {"workflow": "b"}}]},
        "b": {"goal": "g", "risk": "low", "spec_version": "1.1", "steps": [
            {"capability": "observe", "purpose": "p", "store_as": "o",
             "input_bindings": {"target": "t"}}]}
    });
    let run = Run::start(&ctx, &catalog, "a", Map::new(), opts()).unwrap();
    let snap = run.snapshot(None);
    assert!(Run::restore(&ctx, &catalog, &snap, None).is_ok());
    for (what, edit) in [
        (
            "parent past its steps",
            Box::new(|s: &mut Value| {
                s["frames"][0]["step"] = serde_json::json!(1);
                s["frames"][0]["stage"] = serde_json::json!({"stage": "Begin"});
            }) as Box<dyn Fn(&mut Value)>,
        ),
        (
            "parent not executing",
            Box::new(|s: &mut Value| {
                s["frames"][0]["stage"] = serde_json::json!({"stage": "Begin"})
            }),
        ),
    ] {
        let bad = forged(&snap, edit);
        assert!(
            Run::restore(&ctx, &catalog, &bad, None).is_err(),
            "{what}: a forged state was restored"
        );
    }
}

/// A run waiting on a receive with `identity@1` inputs.
fn waiting() -> (Context, Run) {
    let ctx = ctx();
    let catalog = serde_json::json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
        "workflow_extensions": {"requires": ["wait@1", "identity@1"]},
        "steps": [{"capability": "receive", "purpose": "p", "store_as": "r", "timeout": "1h",
                   "input_bindings": {"accept_trust_classes": ["owner"]},
                   "wait": {"event_type": "answer"}}]}});
    let run = Run::start(&ctx, &catalog, "w", Map::new(), opts()).unwrap();
    (ctx, run)
}

#[test]
fn submit_refuses_a_malformed_or_contradictory_identity() {
    let (_ctx, mut run) = waiting();
    let id = run.next().id;
    let before = run.snapshot(None);
    let owner = serde_json::json!({"principal": "dana", "kind": "human", "trust_class": "owner"});
    let event = serde_json::json!({"event_type": "answer"});
    for (principal, identity) in [
        // The principal names someone else than the identity.
        (Some("eve"), owner.clone()),
        // Not an agent_identity.
        (None, serde_json::json!({"principal": "dana"})),
        (
            None,
            serde_json::json!({"principal": "dana", "kind": "robot"}),
        ),
        (None, serde_json::json!({"principal": 7, "kind": "human"})),
        (
            None,
            serde_json::json!({"principal": "dana", "kind": "human", "trust_class": "boss"}),
        ),
        (
            None,
            serde_json::json!({"principal": "dana", "kind": "human", "authenticated_by": "password"}),
        ),
        (None, serde_json::json!("dana")),
    ] {
        let r = run.submit(
            id,
            Response::Event {
                event: event.clone(),
                principal: principal.map(str::to_string),
                identity: Some(identity.clone()),
            },
            0,
        );
        assert!(
            matches!(r, Err(acs_core::exec::SubmitError::Malformed(_))),
            "{identity}: {r:?}"
        );
    }
    assert_eq!(
        run.snapshot(None),
        before,
        "a refused response changes nothing"
    );
    // The same principal twice is fine.
    run.submit(
        id,
        Response::Event {
            event,
            principal: Some("dana".into()),
            identity: Some(owner),
        },
        0,
    )
    .unwrap();
    assert!(run.is_finished());
}

#[test]
fn start_refuses_a_malformed_actor_identity() {
    let ctx = ctx();
    for bad in [
        serde_json::json!({"kind": "agent"}),
        serde_json::json!({"principal": "a", "kind": "agent", "role": 1}),
    ] {
        let options = StartOptions {
            actor_identity: Some(bad),
            ..opts()
        };
        assert!(matches!(
            Run::start(&ctx, &one_step(), "w", topic(), options),
            Err(acs_core::exec::StartError::Identity(_))
        ));
    }
}

#[test]
fn without_identity_at_1_an_identity_is_ignored() {
    // A host that reports identities to a workflow that does not declare
    // identity@1 changes nothing: the identity is neither checked nor kept.
    let ctx = ctx();
    let catalog = serde_json::json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
        "workflow_extensions": {"requires": ["wait@1"]},
        "steps": [{"capability": "receive", "purpose": "p", "store_as": "r", "timeout": "1h",
                   "wait": {"event_type": "answer"}}]}});
    let mut run = Run::start(&ctx, &catalog, "w", Map::new(), opts()).unwrap();
    let id = run.next().id;
    run.submit(
        id,
        Response::Event {
            event: serde_json::json!({"event_type": "answer"}),
            principal: Some("dana".into()),
            identity: Some(serde_json::json!({"principal": "someone-else"})),
        },
        0,
    )
    .unwrap();
    let end = serde_json::to_value(run.next()).unwrap();
    assert_eq!(
        end["outputs"]["r"]["data"],
        serde_json::json!([{"event_type": "answer", "sender": "dana"}])
    );
}

#[test]
fn resolved_inputs_must_be_ijson_and_states_stay_restorable() {
    let ctx = ctx();
    // A stored value nested 98 deep, bound under 30 more levels: the
    // resolved inputs would be too deep to send or snapshot (R402).
    let mut deep = serde_json::json!(1);
    for _ in 0..98 {
        deep = serde_json::json!([deep]);
    }
    let mut wrapper = serde_json::json!("${r.data: array<any>}");
    for _ in 0..30 {
        wrapper = serde_json::json!({"k": wrapper});
    }
    let catalog = serde_json::json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
        "steps": [
            {"capability": "retrieve", "purpose": "p", "store_as": "r",
             "input_bindings": {"target": "t"}},
            {"capability": "transform", "purpose": "p", "store_as": "x",
             "input_bindings": {"input": wrapper, "target_format": "f"}}]}});
    let mut run = Run::start(&ctx, &catalog, "w", Map::new(), opts()).unwrap();
    let id = run.next().id;
    run.submit(
        id,
        Response::Output {
            value: serde_json::json!({"data": deep, "evidence_anchors": [], "confidence": 1}),
            evidence_seen: None,
        },
        0,
    )
    .unwrap();
    let end = serde_json::to_value(run.next()).unwrap();
    assert_eq!(end["kind"], "Failed");
    assert_eq!(end["code"], "R402");
    let snap = run.snapshot(None);
    assert!(Run::restore(&ctx, &catalog, &snap, None).is_ok());
}

#[test]
fn a_huge_min_approvers_still_snapshots() {
    let ctx = ctx();
    let catalog = serde_json::json!({"w": {"goal": "g", "risk": "high", "spec_version": "1.1",
        "workflow_extensions": {"requires": ["approval@1"]},
        "steps": [{"capability": "execute", "purpose": "p", "store_as": "x",
                   "input_bindings": {"code": "c"},
                   "approval": {"approver": {"kind": "human",
                                             "min_approvers": 18446744073709551615u64}}}]}});
    let run = Run::start(&ctx, &catalog, "w", Map::new(), opts()).unwrap();
    let snap = run.snapshot(None);
    assert!(Run::restore(&ctx, &catalog, &snap, None).is_ok());
}

#[test]
fn the_executors_own_refusals_are_not_retried() {
    let ctx = ctx();
    let catalog = serde_json::json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
        "steps": [{"capability": "invoke", "purpose": "p", "store_as": "i",
                   "retry": {"max": 1000, "backoff": "none"},
                   "input_bindings": {"workflow": "child", "input": {"nope": 1}}}]},
        "child": {"goal": "g", "risk": "low", "spec_version": "1.1",
                  "steps": [{"capability": "observe", "purpose": "p", "store_as": "o",
                             "input_bindings": {"target": "t"}}]}});
    // The literal input is checked statically too; drive it past the
    // validator by resolving it from an input instead.
    let mut c = catalog.clone();
    c["w"]["inputs"] = serde_json::json!({"payload": {"type": "object"}});
    c["w"]["steps"][0]["input_bindings"]["input"] = serde_json::json!("${payload: object}");
    let mut inputs = Map::new();
    inputs.insert("payload".into(), serde_json::json!({"nope": 1}));
    let run = Run::start(&ctx, &c, "w", inputs, opts()).unwrap();
    let end = serde_json::to_value(run.next()).unwrap();
    assert_eq!(end["code"], "R402");
    assert!(!run.trace().iter().any(|t| t["kind"] == "retry"));
}

#[test]
fn contributed_fixtures_state_their_header() {
    // The contributed fixtures run in pytest; here only their format: each
    // states its catalog's header, as the start operation requires.
    let dir = root().join("tests/conformance/contrib");
    for entry in std::fs::read_dir(&dir).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().is_none_or(|x| x != "json") {
            continue;
        }
        let f = read_json(&std::fs::read_to_string(&path).unwrap()).unwrap();
        let header = f.get("header");
        assert!(
            header.is_some_and(|h| h.is_null() || h.is_string()),
            "{}: no header",
            path.display()
        );
    }
}

/// A one-step catalog that declares no version: only a header can.
fn undeclared() -> Value {
    let mut c = one_step();
    c["w"].as_object_mut().unwrap().remove("spec_version");
    c
}

#[test]
fn the_header_is_validated_and_kept() {
    let ctx = ctx();
    let with = |header: Option<&str>| StartOptions {
        header: header.map(str::to_string),
        ..opts()
    };
    // A header the executor does not support refuses the start (V109), as
    // a validator reading the file would.
    let refused = Run::start(&ctx, &undeclared(), "w", topic(), with(Some("2.0")));
    match refused {
        Err(acs_core::exec::StartError::Invalid(d)) => {
            assert_eq!(
                d.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
                ["V109"]
            );
        }
        other => panic!("{other:?}", other = other.map(|_| ())),
    }
    // A workflow's own spec_version takes precedence over the header.
    assert!(Run::start(&ctx, &one_step(), "w", topic(), with(Some("2.0"))).is_ok());
    for header in [None, Some("1.0"), Some("1.1.0"), Some("1.2.0")] {
        let run = Run::start(&ctx, &undeclared(), "w", topic(), with(header)).unwrap();
        let snap = run.snapshot(Some(b"k"));
        // The snapshot keeps the header (and leaves it out when there is
        // none, as a 1.1 snapshot did), and a restore validates with it.
        assert_eq!(
            snap.state.contains("\"header\""),
            header.is_some(),
            "{header:?}"
        );
        let restored = Run::restore(&ctx, &undeclared(), &snap, Some(b"k")).unwrap();
        assert_eq!(restored.snapshot(Some(b"k")), snap);
    }
    // A forged state whose header the executor does not support is refused
    // at restore, by validation.
    let run = Run::start(&ctx, &undeclared(), "w", topic(), with(Some("1.1"))).unwrap();
    let forged_header = forged(&run.snapshot(None), |s| {
        s["header"] = serde_json::json!("2.0")
    });
    assert!(matches!(
        Run::restore(&ctx, &undeclared(), &forged_header, None),
        Err(acs_core::exec::RestoreError::Start(_))
    ));
    let not_a_version = forged(&run.snapshot(None), |s| {
        s["header"] = serde_json::json!("one")
    });
    assert!(Run::restore(&ctx, &undeclared(), &not_a_version, None).is_err());
    // A header that is not a version is refused at start, even where the
    // workflow's own spec_version would make validation ignore it.
    for header in ["one", "", "1", "v1.2"] {
        assert!(matches!(
            Run::start(&ctx, &one_step(), "w", topic(), with(Some(header))),
            Err(acs_core::exec::StartError::Header(_))
        ));
    }
}

#[test]
fn start_refuses_options_not_implemented_yet() {
    let ctx = ctx();
    let cases = [
        StartOptions {
            profiles: vec![serde_json::json!({"domain": "d"})],
            ..opts()
        },
        StartOptions {
            destinations: vec![vec!["ops".into()]],
            ..opts()
        },
    ];
    for options in cases {
        assert!(matches!(
            Run::start(&ctx, &one_step(), "w", topic(), options),
            Err(acs_core::exec::StartError::Unsupported(_))
        ));
    }
    // Nor does a restore accept a state that holds one.
    let run = Run::start(&ctx, &one_step(), "w", topic(), opts()).unwrap();
    for (key, value) in [
        ("profiles", serde_json::json!([{"domain": "d"}])),
        ("destinations", serde_json::json!([["ops"]])),
    ] {
        let snap = forged(&run.snapshot(None), |s| s[key] = value.clone());
        assert!(
            matches!(
                Run::restore(&ctx, &one_step(), &snap, None),
                Err(acs_core::exec::RestoreError::Malformed(_))
            ),
            "{key}"
        );
    }
}

#[test]
fn grounding_policies_at_start_and_restore() {
    let ctx = ctx();
    let policy = |ids: &[&str]| {
        acs_core::grounding::Policy::new(ids.iter().map(|s| s.to_string()).collect(), None, false)
            .unwrap()
    };
    // A policy that requires a capability the ontology lacks is refused, not
    // applied to nothing (§5.20).
    let bad = StartOptions {
        grounding: vec![policy(&["search"]), policy(&["retrieve", "clasify"])],
        ..opts()
    };
    match Run::start(&ctx, &one_step(), "w", topic(), bad) {
        Err(acs_core::exec::StartError::Grounding(m)) => assert!(
            m.starts_with("grounding[1].require[1]")
                && m.contains("V101")
                && m.contains("'classify'"),
            "{m}"
        ),
        other => panic!("{:?}", other.err()),
    }
    // A run started with policies keeps them across a snapshot.
    let good = StartOptions {
        grounding: vec![policy(&["search"])],
        ..opts()
    };
    let run = Run::start(&ctx, &one_step(), "w", topic(), good).unwrap();
    let snap = run.snapshot(None);
    let state: Value = serde_json::from_str(&snap.state).unwrap();
    assert_eq!(
        state["grounding"],
        serde_json::json!([{"require": ["search"], "attested": false}])
    );
    let restored = Run::restore(&ctx, &one_step(), &snap, None).unwrap();
    assert_eq!(restored.snapshot(None).state, snap.state);
    // A state whose policy is malformed or names an unknown id is refused.
    for value in [
        serde_json::json!([{"require": ["clasify"]}]),
        serde_json::json!([{"require": []}]),
    ] {
        let forged_snap = forged(&snap, |s| s["grounding"] = value.clone());
        assert!(matches!(
            Run::restore(&ctx, &one_step(), &forged_snap, None),
            Err(acs_core::exec::RestoreError::Malformed(_))
        ));
    }
}

#[test]
fn evidence_seen_absent_and_empty_differ() {
    let absent: Response =
        serde_json::from_value(serde_json::json!({"kind": "Output", "value": {}})).unwrap();
    let empty: Response = serde_json::from_value(
        serde_json::json!({"kind": "Output", "value": {}, "evidence_seen": []}),
    )
    .unwrap();
    assert_ne!(absent, empty);
    assert_eq!(
        serde_json::to_value(&absent).unwrap(),
        serde_json::json!({"kind": "Output", "value": {}})
    );
    assert_eq!(
        serde_json::to_value(&empty).unwrap()["evidence_seen"],
        serde_json::json!([])
    );
}

/// A run of `one_step()` whose step fails with the host's `reason`, under
/// `retry` when `retry` is set.
fn failed_with(reason: Option<Value>, retry: bool) -> (Value, Vec<Value>) {
    let ctx = ctx();
    let mut catalog = one_step();
    if retry {
        catalog["w"]["steps"][0]["retry"] = serde_json::json!({"max": 1});
    }
    let mut run = Run::start(&ctx, &catalog, "w", topic(), opts()).unwrap();
    let mut error = serde_json::json!({"kind": "Error", "code": "R402", "message": "no"});
    if let Some(r) = reason {
        error["reason"] = r;
    }
    while !run.is_finished() {
        let id = run.next().id;
        let response: Response = serde_json::from_value(error.clone()).unwrap();
        run.submit(id, response, 0).unwrap();
    }
    (
        serde_json::to_value(run.next()).unwrap(),
        run.trace().to_vec(),
    )
}

fn detail<'t>(trace: &'t [Value], kind: &str) -> &'t Value {
    &trace.iter().find(|t| t["kind"] == kind).unwrap()["detail"]
}

#[test]
fn reason_grammar() {
    // The defined tokens and vendor reasons are kept: on the step's failure
    // trace and on the Failed action.
    for token in [
        "unsupported_capability",
        "not_recorded",
        "outcome_unknown",
        "x-acme.audio",
        "x-0",
    ] {
        let (end, trace) = failed_with(Some(serde_json::json!(token)), false);
        assert_eq!(end["kind"], "Failed");
        assert_eq!(end["code"], "R402");
        assert_eq!(end["reason"], token, "{token}");
        assert_eq!(detail(&trace, "step_failed")["reason"], token);
        assert_eq!(detail(&trace, "run_failed")["reason"], token);
    }
    // Under retry, the retry trace shows it too.
    let (end, trace) = failed_with(Some(serde_json::json!("over_capacity")), true);
    assert_eq!(detail(&trace, "retry")["reason"], "over_capacity");
    assert_eq!(end["reason"], "over_capacity");
}

#[test]
fn reason_outside_grammar_is_ignored() {
    let (plain, plain_trace) = failed_with(None, false);
    assert!(plain.get("reason").is_none());
    assert!(
        detail(&plain_trace, "step_failed")
            .get("reason_ignored")
            .is_none()
    );
    let long = format!("x-{}", "a".repeat(63));
    for bad in [
        serde_json::json!("Unsupported"),
        serde_json::json!("x-"),
        serde_json::json!(long),
        serde_json::json!(5),
        serde_json::json!({"a": 1}),
        Value::Null,
    ] {
        let (end, trace) = failed_with(Some(bad.clone()), false);
        // The run fails as without a reason; the value is only traced.
        assert_eq!(end["code"], plain["code"], "{bad}");
        assert!(end.get("reason").is_none(), "{bad}");
        let d = detail(&trace, "step_failed");
        assert!(d.get("reason").is_none(), "{bad}");
        assert_eq!(d["reason_ignored"], bad, "{bad}");
    }
    // 64 characters in all is the longest vendor reason.
    let longest = format!("x-{}", "a".repeat(62));
    assert_eq!(
        failed_with(Some(serde_json::json!(longest)), false).0["reason"],
        longest
    );
}

#[test]
fn response_unknown_members_ignored() {
    let output: Response = serde_json::from_value(serde_json::json!(
        {"kind": "Output", "value": 1, "extra": true}
    ))
    .unwrap();
    assert!(matches!(output, Response::Output { .. }));
    let error: Response = serde_json::from_value(serde_json::json!(
        {"kind": "Error", "code": "R402", "message": "m", "extra": [1], "reason": {"a": 1}}
    ))
    .unwrap();
    assert!(matches!(
        error,
        Response::Error {
            reason: Some(_),
            ..
        }
    ));
    // A response without a reason serialises as in 1.1.
    let plain: Response =
        serde_json::from_value(serde_json::json!({"kind": "Error", "code": "R402"})).unwrap();
    assert_eq!(
        serde_json::to_value(plain).unwrap(),
        serde_json::json!({"kind": "Error", "code": "R402", "message": ""})
    );
}

#[test]
fn read_json_refuses_values_outside_i_json() {
    let ok = read_json(
        r#"{"a": [9007199254740992, -9007199254740992, 1.5e300, "99999999999999999999"]}"#,
    )
    .unwrap();
    assert_eq!(ok["a"][0], serde_json::json!(9007199254740992u64));
    // A string that looks like a number is a string; a fraction or an
    // exponent is not an integer literal.
    assert_eq!(ok["a"][3], "99999999999999999999");
    for bad in [
        "9007199254740993",
        "-9007199254740993",
        "[18446744073709551616]",
        "{\"x\": 123456789012345678901234567890}",
        "{\"s\": \"a\\\"b\", \"n\": 90071992547409930}",
    ] {
        let e = read_json(bad).unwrap_err();
        assert!(e.contains("2^53"), "{bad}: {e}");
    }
    // A member name twice in one object, at any depth: parsed, the value
    // would keep the last and no longer show it (§5.14).
    for bad in [
        r#"{"a":1,"a":2}"#,
        r#"{"a":1,"a":1}"#,
        r#"[{"b":{"x":[],"y":0,"x":[]}}]"#,
        r#"{"\u0061":1,"a":2}"#,
    ] {
        let e = read_json(bad).unwrap_err();
        assert!(e.contains("appears twice"), "{bad}: {e}");
    }
    let distinct = read_json(r#"{"a":{"a":1},"b":[{"a":2},{"a":3}]}"#).unwrap();
    assert_eq!(distinct["b"][1]["a"], 3);
    // Malformed JSON and values beyond I-JSON's depth are refused as well.
    assert!(read_json("{").is_err());
    assert!(read_json(&format!("{}1{}", "[".repeat(110), "]".repeat(110))).is_err());
    assert!(read_json("\"unterminated").is_err());
}

// ---------------------------------------------------------------------------
// Resuming a deferred run (§5.14.1), the restore actor (§5.17) and approver
// identities (§5.17)
// ---------------------------------------------------------------------------

fn fixture(name: &str) -> Value {
    let path = root().join(format!("tests/conformance/runtime/{name}.json"));
    read_json(&std::fs::read_to_string(path).unwrap()).unwrap()
}

/// Play a fixture's script up to its first `resume` entry (or to its end):
/// the run as a host holds it then.
fn played(ctx: &Context, name: &str) -> Run {
    let f = fixture(name);
    let inputs: Map<String, Value> = f["inputs"].as_object().cloned().unwrap_or_default();
    let mut run = Run::start(
        ctx,
        &f["catalog"],
        f["workflow"].as_str().unwrap(),
        inputs,
        fixture_options(name, &f, 0),
    )
    .unwrap();
    for entry in f["script"].as_array().unwrap() {
        if entry.get("resume").is_some() {
            break;
        }
        if let Some(t) = entry.get("tick").and_then(Value::as_u64) {
            run.tick(t);
            continue;
        }
        let action = serde_json::to_value(run.next()).unwrap();
        if let Some(respond) = entry.get("respond") {
            let response: Response = serde_json::from_value(fill(respond, &action)).unwrap();
            run.submit(action["id"].as_u64().unwrap(), response, 0)
                .unwrap();
        }
    }
    run
}

fn resume_options() -> ResumeOptions {
    ResumeOptions {
        attendance: Attendance::Attended,
        now_ms: 0,
        actor_identity: None,
    }
}

#[test]
fn resume_needs_a_deferred_end() {
    use acs_core::exec::ResumeError;
    let ctx = ctx();
    // A run still pending, one that completed, and one that failed after
    // deferring (its planned record is abandoned, not resumable).
    let mut pending = Run::start(&ctx, &one_step(), "w", topic(), opts()).unwrap();
    let mut completed = played(&ctx, "linear_bindings");
    let mut failed = played(&ctx, "failure_after_deferral");
    assert!(
        failed
            .action_records()
            .iter()
            .any(|r| r["status"] == "planned")
    );
    for (run, says) in [
        (&mut pending, "has not finished"),
        (&mut completed, "ended completed"),
        (&mut failed, "failed with R402"),
    ] {
        let before = run.snapshot(None);
        match run.resume(resume_options()) {
            Err(ResumeError::NotDeferred(m)) => assert!(m.contains(says), "{m}"),
            other => panic!("{other:?}"),
        }
        assert_eq!(
            run.snapshot(None),
            before,
            "a refused resume changes nothing"
        );
    }
}

#[test]
fn resume_refuses_a_malformed_actor() {
    use acs_core::exec::ResumeError;
    let ctx = ctx();
    let mut run = played(&ctx, "resume_deferred_attended");
    let before = run.snapshot(None);
    for bad in [
        serde_json::json!({"kind": "agent"}),
        serde_json::json!({"principal": "b", "kind": "robot"}),
    ] {
        let o = ResumeOptions {
            actor_identity: Some(bad),
            ..resume_options()
        };
        assert!(matches!(run.resume(o), Err(ResumeError::Identity(_))));
    }
    assert_eq!(run.snapshot(None), before);
}

/// The state of `run`'s snapshot without the members an executor before
/// resumption did not keep (`remove`: member names), at any depth.
fn without(run: &Run, remove: &[&str]) -> acs_core::exec::Snapshot {
    fn strip(v: &mut Value, remove: &[&str]) {
        match v {
            Value::Object(m) => {
                for k in remove {
                    m.remove(*k);
                }
                m.values_mut().for_each(|x| strip(x, remove));
            }
            Value::Array(a) => a.iter_mut().for_each(|x| strip(x, remove)),
            _ => {}
        }
    }
    forged(&run.snapshot(None), |s| strip(s, remove))
}

#[test]
fn resume_refuses_states_it_did_not_keep() {
    use acs_core::exec::ResumeError;
    let ctx = ctx();
    let old = ["ahead", "parked", "resume", "pending_escalation", "queued"];
    for (name, remove, says) in [
        (
            "deferral_continues",
            &old[..],
            "ran after its first deferral",
        ),
        (
            "deferred_in_child",
            &old[..],
            "ran after its first deferral",
        ),
        (
            "deferred_in_child",
            &["parked"][..],
            "the nested run of step 0",
        ),
    ] {
        let f = fixture(name);
        let run = played(&ctx, name);
        let snap = without(&run, remove);
        // A state saved before resumption existed restores and reports its
        // end; it cannot be resumed (cancel it and start a new run).
        let mut restored = Run::restore(&ctx, &f["catalog"], &snap, None)
            .unwrap_or_else(|e| panic!("{name}: {e}"));
        assert_eq!(restored.next(), run.next());
        match restored.resume(resume_options()) {
            Err(ResumeError::NotKept(m)) => assert!(m.contains(says), "{name}: {m}"),
            other => panic!("{name}: {other:?}"),
        }
    }
}

#[test]
fn states_without_resumption_members_restore() {
    // A state of a run that never deferred has none of the members
    // resumption added: it is the state an earlier executor wrote, and it
    // restores and runs to its end.
    let ctx = ctx();
    let run = Run::start(&ctx, &one_step(), "w", topic(), opts()).unwrap();
    let snap = run.snapshot(None);
    for member in [
        "\"ahead\"",
        "\"parked\"",
        "\"resume\"",
        "\"queued\"",
        "\"pending_escalation\"",
    ] {
        assert!(!snap.state.contains(member), "{member}");
    }
    let mut restored = Run::restore(&ctx, &one_step(), &snap, None).unwrap();
    let id = restored.next().id;
    restored
        .submit(
            id,
            Response::Output {
                value: serde_json::json!({"data": 1, "evidence_anchors": [], "confidence": 1}),
                evidence_seen: None,
            },
            1,
        )
        .unwrap();
    assert!(restored.is_finished());
    // A deferred end keeps which steps ran ahead.
    let deferred = played(&ctx, "deferral_continues").snapshot(None);
    assert!(deferred.state.contains("\"ahead\""));
}

#[test]
fn resume_twice_is_two_runs() {
    // Resuming two copies of one saved state gives two identical requests:
    // each could carry out the same queued action, which is why a host
    // resumes a saved state once (§5.14.1).
    let ctx = ctx();
    let f = fixture("resume_deferred_attended");
    let snap = played(&ctx, "resume_deferred_attended").snapshot(Some(b"k"));
    let resumed = || {
        let mut run = Run::restore(&ctx, &f["catalog"], &snap, Some(b"k")).unwrap();
        run.resume(resume_options()).unwrap();
        serde_json::to_value(run.next()).unwrap()
    };
    let (a, b) = (resumed(), resumed());
    assert_eq!(a, b);
    assert_eq!(a["kind"], "RequestApproval");
    assert_eq!(a["queued_action_id"], "run-1/w/3/0");
}

#[test]
fn restore_checks_the_actor() {
    use acs_core::exec::{RestoreError, RestoreOptions};
    let ctx = ctx();
    let a = serde_json::json!({"principal": "agent-a", "kind": "agent"});
    let b = serde_json::json!({"principal": "agent-b", "kind": "agent"});
    let as_a = StartOptions {
        actor_identity: Some(a.clone()),
        ..opts()
    };
    let snap = Run::start(&ctx, &one_step(), "w", topic(), as_a)
        .unwrap()
        .snapshot(None);
    let restore = |actor: Option<Value>| {
        Run::restore_with(
            &ctx,
            &one_step(),
            &snap,
            None,
            RestoreOptions {
                actor_identity: actor,
            },
        )
    };
    assert!(restore(Some(a.clone())).is_ok());
    // The same principal under other attributes is the same party.
    assert!(
        restore(Some(
            serde_json::json!({"principal": "agent-a", "kind": "agent", "role": "r"})
        ))
        .is_ok()
    );
    assert!(matches!(
        restore(Some(b.clone())),
        Err(RestoreError::Actor(_))
    ));
    assert!(matches!(
        restore(Some(serde_json::json!({"kind": "agent"}))),
        Err(RestoreError::Actor(_))
    ));
    assert!(restore(None).is_ok());
    assert!(Run::restore(&ctx, &one_step(), &snap, None).is_ok());
    // A run started without an actor cannot be restored for one.
    let anonymous = Run::start(&ctx, &one_step(), "w", topic(), opts())
        .unwrap()
        .snapshot(None);
    assert!(matches!(
        Run::restore_with(
            &ctx,
            &one_step(),
            &anonymous,
            None,
            RestoreOptions {
                actor_identity: Some(a)
            }
        ),
        Err(RestoreError::Actor(_))
    ));
}

/// A run asking a human approver, with `identity@1` declared or not.
fn asking(identity: bool) -> Run {
    let mut requires = vec!["approval@1"];
    if identity {
        requires.push("identity@1");
    }
    let catalog = serde_json::json!({"w": {"goal": "g", "risk": "high", "spec_version": "1.1",
        "workflow_extensions": {"requires": requires},
        "steps": [{"capability": "execute", "purpose": "p", "store_as": "x",
                   "input_bindings": {"code": "c"},
                   "approval": {"approver": {"kind": "human"}}}]}});
    Run::start(&ctx(), &catalog, "w", Map::new(), opts()).unwrap()
}

fn decision(digest: &Value, approvers: &[&str], identities: Value) -> Response {
    serde_json::from_value(serde_json::json!({
        "kind": "Decision", "decision_id": "d1", "decision": "approved",
        "approvers": approvers, "digest": digest, "approver_identities": identities,
    }))
    .unwrap()
}

#[test]
fn decision_identities_must_be_well_formed() {
    let alice = serde_json::json!({"principal": "alice", "kind": "human"});
    let alice_lead = serde_json::json!({"principal": "alice", "kind": "human", "role": "lead"});
    let malformed = [
        (vec![], serde_json::json!("alice")),
        (vec![], serde_json::json!([{"principal": "alice"}])),
        (
            vec![],
            serde_json::json!([alice, {"principal": "bob", "kind": "robot"}]),
        ),
        (vec![], serde_json::json!([alice, alice_lead])),
        (vec!["bob"], serde_json::json!([alice])),
        (vec!["alice", "bob"], serde_json::json!([alice])),
    ];
    let mut run = asking(true);
    let action = serde_json::to_value(run.next()).unwrap();
    let id = action["id"].as_u64().unwrap();
    let before = run.snapshot(None);
    for (approvers, identities) in malformed {
        let r = run.submit(
            id,
            decision(&action["digest"], &approvers, identities.clone()),
            0,
        );
        assert!(
            matches!(r, Err(acs_core::exec::SubmitError::Malformed(_))),
            "{identities}: {r:?}"
        );
        assert_eq!(
            run.snapshot(None),
            before,
            "a refused response changes nothing"
        );
    }
    // Two identical identities are one approver; approvers may be empty or
    // name exactly their principals.
    for approvers in [vec![], vec!["alice"], vec!["alice", "alice"]] {
        let mut run = asking(true);
        let ok = run.submit(
            id,
            decision(
                &action["digest"],
                &approvers,
                serde_json::json!([alice, alice]),
            ),
            0,
        );
        assert!(ok.is_ok(), "{approvers:?}: {ok:?}");
        let record = &run.action_records()[0];
        assert_eq!(
            record["approval"]["approvers"],
            serde_json::json!(["alice"])
        );
        assert_eq!(
            record["approval"]["approver_identities"],
            serde_json::json!([alice])
        );
    }
    // Without identity@1 the member is neither checked nor kept.
    let mut plain = asking(false);
    plain
        .submit(
            id,
            decision(
                &action["digest"],
                &["carol"],
                serde_json::json!("not a list"),
            ),
            0,
        )
        .unwrap();
    let record = &plain.action_records()[0];
    assert_eq!(
        record["approval"]["approvers"],
        serde_json::json!(["carol"])
    );
    assert!(record["approval"].get("approver_identities").is_none());
}

#[test]
fn read_json_bounds_integer_literals() {
    // §5.14: an integer, a number written without a fraction or an
    // exponent, has a magnitude of at most 2^53; any other number is a
    // binary64 value, so 1e21 reads although its value is beyond 2^53.
    for ok in [
        "[9007199254740992]",
        "[-9007199254740992]",
        "[1e21]",
        "[1.5]",
        "[\"123456789012345678901\"]",
    ] {
        assert!(read_json(ok).is_ok(), "{ok}");
    }
    for bad in [
        "[9007199254740993]",
        "[100000000000000000000000]",
        "{\"a\":-9007199254740993}",
    ] {
        assert!(read_json(bad).is_err(), "{bad}");
    }
}

#[test]
fn a_resumed_step_keeps_its_queued_action_in_the_state() {
    // While a re-entered step is asked, the state names the queued action
    // it continues (§5.14.1), and a restore asks the same; a state that
    // names a step or a record that does not exist is refused.
    let ctx = ctx();
    let f = fixture("resume_deferred_attended");
    let mut run = played(&ctx, "resume_deferred_attended");
    run.resume(resume_options()).unwrap();
    let asked = serde_json::to_value(run.next()).unwrap();
    assert_eq!(asked["queued_action_id"], "run-1/w/3/0");
    let snap = run.snapshot(None);
    let state: Value = serde_json::from_str(&snap.state).unwrap();
    assert_eq!(
        state["frames"][0]["queued"],
        serde_json::json!({"step": 3, "record": 0})
    );
    let restored = Run::restore(&ctx, &f["catalog"], &snap, None).unwrap();
    assert_eq!(serde_json::to_value(restored.next()).unwrap(), asked);
    for (what, queued) in [
        ("a step", serde_json::json!({"step": 9, "record": 0})),
        ("a record", serde_json::json!({"step": 3, "record": 9})),
    ] {
        let bad = forged(&snap, |s| s["frames"][0]["queued"] = queued.clone());
        assert!(
            Run::restore(&ctx, &f["catalog"], &bad, None).is_err(),
            "a queued action naming {what} that does not exist was restored"
        );
    }
}

/// The `grounding` trace events of the S4 fixtures (§5.20): the check is
/// traced once per checked output, and an unchecked output (a capability no
/// policy requires, a delegation that waits) has none.
#[test]
fn grounding_fixture_traces() {
    let root = root();
    let ctx = Context::load(&root.join("schemas/capability_ontology.yaml"), &root).unwrap();
    let all: std::collections::BTreeMap<String, Value> = fixtures().into_iter().collect();
    let grounding = |name: &str| -> Vec<Value> {
        let f = &all[name];
        play(&ctx, name, f, Replay::Plain)
            .trace
            .into_iter()
            .filter(|t| t["kind"] == "grounding")
            .map(|t| t["detail"].clone())
            .collect()
    };
    let one = |name: &str| {
        let events = grounding(name);
        assert_eq!(events.len(), 1, "{name}: {events:?}");
        events[0].clone()
    };
    let d = one("grounding_grounded_output");
    assert_eq!(
        (&d["status"], &d["counted"], &d["policies"]),
        (
            &serde_json::json!("grounded"),
            &serde_json::json!(1),
            &serde_json::json!(1)
        )
    );
    assert_eq!(one("grounding_inferred_output")["status"], "inferred");
    assert_eq!(one("grounding_acs_bound")["counted"], 1);
    assert_eq!(one("grounding_attested_seen")["unattested"], 0);
    for name in [
        "grounding_not_required",
        "grounding_delegate_wait_exempt",
        "grounding_quorum_exempt",
        "grounding_invoke_fills_anchors",
        "grounding_workflow_policy_not_nested",
    ] {
        assert!(grounding(name).is_empty(), "{name}");
    }
    // The host's policy reaches the nested run: its step fails F505 there.
    let nested = play(
        &ctx,
        "grounding_host_policy_nested",
        &all["grounding_host_policy_nested"],
        Replay::Plain,
    );
    assert!(nested.trace.iter().any(|t| t["kind"] == "step_failed"
        && t["frame"] == serde_json::json!(["w", "child"])
        && t["detail"]["code"] == "F505"));
}
