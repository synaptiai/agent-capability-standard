//! Runtime conformance fixtures (design-114 §16.6): every scripted run must
//! produce the expected actions, end and trace — and the same again when
//! the run is snapshotted and restored before every step.

use std::path::{Path, PathBuf};

use acs_core::exec::canonical::canonical;
use acs_core::exec::{Attendance, RecordMode, Response, Run, StartOptions, read_json};
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

/// Replace `"{{digest}}"` in a response with the pending action's digest.
fn fill(response: &Value, action: &Value) -> Value {
    match response {
        Value::String(s) if s == "{{digest}}" => action["digest"].clone(),
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
    // Catalog sets and agent manifests are start members of workstream S3.
    for key in ["catalogs", "agents"] {
        assert!(
            f.get(key).is_none(),
            "{name}: this harness does not pass '{key}' yet"
        );
    }
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

/// Run one fixture; with `restore`, snapshot and restore before each step.
/// Returns every action seen and the end, as canonical JSON (RFC 8785, so
/// object key order does not matter but array order does), and the trace.
fn play(ctx: &Context, name: &str, f: &Value, restore: bool) -> (Vec<String>, Value, Vec<Value>) {
    let catalog = &f["catalog"];
    let inputs: Map<String, Value> = f["inputs"].as_object().cloned().unwrap_or_default();
    let mut now = f["start"].as_u64().unwrap_or(0);
    let mut run = Run::start(
        ctx,
        catalog,
        f["workflow"].as_str().unwrap(),
        inputs,
        fixture_options(name, f, now),
    )
    .unwrap_or_else(|e| panic!("{name}: start: {e}"));
    let mut seen = Vec::new();
    for (i, entry) in f["script"].as_array().unwrap().iter().enumerate() {
        if restore {
            let snap = run.snapshot(Some(b"key"));
            run = Run::restore(ctx, catalog, &snap, Some(b"key"))
                .unwrap_or_else(|e| panic!("{name}: restore before {i}: {e}"));
        }
        if let Some(t) = entry.get("tick").and_then(Value::as_u64) {
            now = t;
            run.tick(t);
            continue;
        }
        let action = serde_json::to_value(run.next()).unwrap();
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
    let end = serde_json::to_value(run.next()).unwrap();
    seen.push(canonical(&end));
    (seen, end, run.trace().to_vec())
}

#[test]
fn runtime_fixtures() {
    let root = root();
    let ctx = Context::load(&root.join("schemas/capability_ontology.yaml"), &root).unwrap();
    let dir = root.join("tests/conformance/runtime");
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
    for path in names {
        let name = path.file_stem().unwrap().to_string_lossy().to_string();
        // Read as a host's JSON is read: no integer beyond 2^53.
        let f: Value = read_json(&std::fs::read_to_string(&path).unwrap())
            .unwrap_or_else(|e| panic!("{name}: {e}"));
        let (seen, end, trace) = play(&ctx, &name, &f, false);
        assert!(
            matches(&f["end"], &end),
            "{name}: expected end {}\n  got {end}",
            f["end"]
        );
        let kinds: Vec<&str> = trace.iter().filter_map(|t| t["kind"].as_str()).collect();
        for k in f["trace_kinds"].as_array().unwrap() {
            assert!(
                kinds.contains(&k.as_str().unwrap()),
                "{name}: trace lacks {k}: {kinds:?}"
            );
        }
        // Snapshots are complete: restoring before every step changes
        // nothing.
        let (seen2, _, trace2) = play(&ctx, &name, &f, true);
        assert_eq!(seen, seen2, "{name}: restore changed an action or the end");
        assert_eq!(
            canonical(&Value::Array(trace)),
            canonical(&Value::Array(trace2)),
            "{name}: restore changed the trace"
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
            records: RecordMode::Actions,
            ..opts()
        },
        StartOptions {
            profiles: vec![serde_json::json!({"domain": "d"})],
            ..opts()
        },
        StartOptions {
            grounding: vec![
                acs_core::grounding::Policy::new(vec!["search".into()], None, false).unwrap(),
            ],
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
        ("records_mode", serde_json::json!("actions")),
        ("profiles", serde_json::json!([{"domain": "d"}])),
        ("grounding", serde_json::json!([{"require": ["search"]}])),
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
fn read_json_refuses_inexact_integers() {
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
    // Malformed JSON and values beyond I-JSON's depth are refused as well.
    assert!(read_json("{").is_err());
    assert!(read_json(&format!("{}1{}", "[".repeat(110), "]".repeat(110))).is_err());
    assert!(read_json("\"unterminated").is_err());
}
