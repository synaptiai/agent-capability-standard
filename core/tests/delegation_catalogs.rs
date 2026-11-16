//! Delegation targets, catalog sets and diagnostic locations (STANDARD
//! v1.2 §5.1.1, §5.15, §9.8): the language-neutral vectors of agent maxima
//! and model families, and the validator and executor rules the fixtures do
//! not pin one by one.

use std::path::Path;

use acs_core::agents::Agents;
use acs_core::exec::{Attendance, RecordMode, Run, SetOptions, StartOptions};
use acs_core::names;
use acs_core::ontology::Risk;
use acs_core::validate::{self, Context, Flags, Options};
use serde_json::{Map, Value, json};

fn root() -> &'static Path {
    Path::new(concat!(env!("CARGO_MANIFEST_DIR"), "/.."))
}

fn ctx() -> Context {
    Context::load(&root().join("schemas/capability_ontology.yaml"), root()).unwrap()
}

fn vectors(rel: &str) -> Value {
    serde_json::from_str(&std::fs::read_to_string(root().join(rel)).unwrap()).unwrap()
}

fn flags(v: &Value) -> Option<Flags> {
    if v.is_null() {
        return None;
    }
    Some(Flags {
        risk: Risk::parse(v["risk"].as_str().unwrap()).unwrap(),
        mutation: v["mutation"].as_bool().unwrap(),
        requires_checkpoint: v["requires_checkpoint"].as_bool().unwrap(),
        requires_approval: v["requires_approval"].as_bool().unwrap(),
    })
}

fn manifest(agent: &str, caps: &Value) -> Value {
    json!({"agent": agent, "standard": "1.2", "ontology": "2.2", "capabilities": caps})
}

#[test]
fn maxima_vectors() {
    let ctx = ctx();
    let file = vectors("tests/conformance/agents/maxima.json");
    assert_eq!(
        file["ontology"],
        ctx.ontology.version.clone().unwrap().as_str()
    );
    for case in file["cases"].as_array().unwrap() {
        let agents = Agents::load(&[manifest("x", &case["capabilities"])], &ctx.ontology).unwrap();
        let read_only = case["read_only"].as_bool().unwrap();
        let got = agents.get("x").unwrap().maxima(&ctx.ontology, read_only);
        assert_eq!(got, flags(&case["maxima"]), "{}", case["name"]);
    }
    for join in file["joins"].as_array().unwrap() {
        let read_only = join["read_only"].as_bool().unwrap();
        let mut acc = Some(Flags::NONE);
        for (i, caps) in join["manifests"].as_array().unwrap().iter().enumerate() {
            let agents = Agents::load(&[manifest(&format!("m{i}"), caps)], &ctx.ontology).unwrap();
            let m = agents
                .get(&format!("m{i}"))
                .unwrap()
                .maxima(&ctx.ontology, read_only);
            acc = match (acc, m) {
                (Some(a), Some(b)) => Some(a.join(b)),
                _ => None,
            };
        }
        assert_eq!(acc, flags(&join["maxima"]), "{}", join["name"]);
    }
}

#[test]
fn family_vectors() {
    let file = vectors("tests/conformance/families/derive.json");
    let cases = file["cases"].as_array().unwrap();
    assert!(cases.len() >= 20);
    for case in cases {
        let id = case["model_id"].as_str().unwrap();
        assert_eq!(
            names::model_family(id).as_deref(),
            case["family"].as_str(),
            "{id}"
        );
        if let Some(f) = case["family"].as_str() {
            assert!(names::is_model_family(f), "{f} is not canonical");
        }
    }
}

fn report(catalog: Value, options: Options) -> Vec<Value> {
    let r = validate::validate_with(&ctx(), &catalog, &options).unwrap();
    serde_json::to_value(&r.diagnostics)
        .unwrap()
        .as_array()
        .unwrap()
        .clone()
}

fn codes(diags: &[Value]) -> Vec<&str> {
    diags.iter().map(|d| d["code"].as_str().unwrap()).collect()
}

fn delegate(agent: &str) -> Value {
    json!({"capability": "delegate", "purpose": "p", "store_as": "d",
           "input_bindings": {"agent": agent, "task": {"table": "t"}}})
}

fn writer() -> Value {
    json!({"agent": "db-writer", "standard": "1.2", "ontology": "2.2",
           "capabilities": ["retrieve", "checkpoint", "mutate"]})
}

#[test]
fn colliding_keys_get_exact_paths() {
    let catalog = json!({"w": {
        "goal": "g", "risk": "low", "spec_version": "1.1",
        "a": {"b": 1}, "a.b": 2,
        "steps": [{"capability": "retrieve", "purpose": "p", "store_as": "r",
                   "x.y": 1,
                   "input_bindings": {"target": "t", "a": {"b": 1}, "a.b": 2, "c/d": 3}}]}});
    let diags = report(catalog, Options::default());
    let paths: Vec<&str> = diags
        .iter()
        .map(|d| d["location"]["path"].as_str().unwrap())
        .collect();
    for want in [
        "/w/a",
        "/w/a.b",
        "/w/steps/0/x.y",
        "/w/steps/0/input_bindings/a",
        "/w/steps/0/input_bindings/a.b",
        "/w/steps/0/input_bindings/c~1d",
    ] {
        assert!(paths.contains(&want), "{want} not in {paths:?}");
    }
}

#[test]
fn agents_needs_a_1_2_target() {
    for version in [Some("1.1"), Some("1.0"), None] {
        let mut w = json!({"goal": "g", "risk": "low", "agents": ["db-writer"],
                           "steps": [delegate("db-writer")]});
        if let Some(v) = version {
            w["spec_version"] = json!(v);
        }
        let diags = report(json!({"w": w}), Options::default());
        assert!(
            diags
                .iter()
                .any(|d| d["code"] == "S303" && d["location"]["field"] == "agents"),
            "{version:?}: {diags:?}"
        );
        // Nothing the field switches on applies: no V107, W621 or W622.
        assert!(
            !codes(&diags)
                .iter()
                .any(|c| ["V107", "W621", "W622"].contains(c))
        );
    }
}

#[test]
fn an_approval_block_does_not_depend_on_the_manifests() {
    let w = json!({"w": {"goal": "g", "risk": "high", "spec_version": "1.2",
        "agents": ["db-writer"], "workflow_extensions": {"requires": ["approval@1"]},
        "steps": [
            {"capability": "checkpoint", "purpose": "p", "store_as": "cp",
             "input_bindings": {"scope": "s"}},
            {"capability": "delegate", "purpose": "p", "store_as": "d",
             "input_bindings": {"agent": "db-writer", "task": {}},
             "approval": {"approver": {"kind": "human"}, "when_unattended": "fail"}}]}});
    let with = report(
        w.clone(),
        Options {
            agents: vec![writer()],
            ..Options::default()
        },
    );
    assert!(codes(&with).is_empty(), "{with:?}");
    let without = report(w, Options::default());
    assert_eq!(codes(&without), ["W621"]);
}

#[test]
fn raised_flags_need_a_checkpoint_and_count_for_unattended_runs() {
    let w = json!({"w": {"goal": "g", "risk": "high", "spec_version": "1.2",
        "agents": ["db-writer"], "steps": [delegate("db-writer")]}});
    let diags = report(
        w,
        Options {
            agents: vec![writer()],
            ..Options::default()
        },
    );
    assert_eq!(codes(&diags), ["F501"]);
}

#[test]
fn concurrent_conflicts_follow_invokes_but_not_event_triggers() {
    let cp = json!({"capability": "checkpoint", "purpose": "p", "store_as": "cp",
                    "input_bindings": {"scope": "s"}});
    let persist = json!({"capability": "persist", "purpose": "p", "store_as": "s",
                         "input_bindings": {"data": "x"}});
    let rollback = json!({"capability": "rollback", "purpose": "p", "store_as": "rb",
                          "input_bindings": {"checkpoint_id": "${cp.checkpoint_id}"}});
    let invoke = |t: &str| {
        json!({"capability": "invoke", "purpose": "p", "store_as": format!("i_{t}"),
               "workflow_id": t, "input_bindings": {"workflow": t}})
    };
    let wf = |steps: Value, triggers: Value| {
        json!({"goal": "g", "risk": "medium", "spec_version": "1.1",
               "workflow_extensions": {"requires": ["triggers@1"]},
               "triggers": triggers, "steps": steps})
    };
    let allow_all =
        json!([{"kind": "schedule", "schedule": {"every": "1h", "overlap": "allow_all"}}]);
    let invoked = json!([{"kind": "invoke"}]);
    // Two levels of invoke, and a cycle between the two invoked workflows.
    let catalog = json!({
        "top": wf(json!([cp, persist, invoke("mid")]), allow_all.clone()),
        "mid": wf(json!([invoke("leaf")]), invoked.clone()),
        "leaf": wf(json!([cp, rollback, invoke("mid")]), invoked),
    });
    let diags = report(catalog, Options::default());
    let w623: Vec<&Value> = diags.iter().filter(|d| d["code"] == "W623").collect();
    assert_eq!(w623.len(), 1, "{diags:?}");
    assert_eq!(w623[0]["location"]["workflow"], "top");
    assert!(
        w623[0]["message"].as_str().unwrap().contains("'mid'"),
        "{}",
        w623[0]["message"]
    );
    let event = json!([{"kind": "event", "event": {"event_type": "e", "source_kind": "api"}}]);
    let catalog = json!({"w": wf(json!([cp, persist, rollback]), event)});
    assert!(!codes(&report(catalog, Options::default())).contains(&"W623"));
}

#[test]
fn columns_count_code_points() {
    let catalog = json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
        "steps": [{"capability": "retrieve", "purpose": "p", "store_as": "r",
                   "condition": "\"é\" == ${nope}",
                   "input_bindings": {"target": "t"}}]}});
    let diags = report(catalog, Options::default());
    let d = diags
        .iter()
        .find(|d| d["location"].get("column").is_some())
        .unwrap();
    // `${nope}` starts at the eighth code point (the ninth byte).
    assert_eq!(d["location"]["column"], 8, "{d}");
}

fn start(
    catalog: &Value,
    set: &SetOptions,
    workflow: &str,
    inputs: Map<String, Value>,
) -> Result<Run, String> {
    Run::start_set(
        &ctx(),
        catalog,
        set,
        workflow,
        inputs,
        StartOptions {
            attendance: Attendance::Attended,
            run_id: "r".into(),
            now_ms: 0,
            actor_identity: None,
            header: Some("1.2.0".into()),
            records: RecordMode::Approvals,
            profiles: Vec::new(),
            grounding: Vec::new(),
            destinations: Vec::new(),
        },
    )
    .map_err(|e| e.to_string())
}

#[test]
fn a_refused_set_or_manifest_refuses_the_start() {
    let catalog = json!({"w": {"goal": "g", "risk": "low",
        "steps": [{"capability": "retrieve", "purpose": "p", "store_as": "r",
                   "input_bindings": {"target": "t"}}]}});
    let no_manifest = SetOptions {
        catalogs: vec![(json!({"x": {}}), None)],
        agents: Vec::new(),
    };
    let err = start(&catalog, &no_manifest, "w", Map::new())
        .err()
        .unwrap();
    assert!(err.contains("manifest"), "{err}");
    let bad_agent = SetOptions {
        catalogs: Vec::new(),
        agents: vec![json!({"agent": "a"})],
    };
    assert!(start(&catalog, &bad_agent, "w", Map::new()).is_err());
    // A workflow of another catalog is not a root.
    let lib = json!({"catalog": {"id": "lib", "version": "1.0.0", "exports": ["v"]},
                     "v": catalog["w"].clone()});
    let set = SetOptions {
        catalogs: vec![(lib, Some("1.2.0".into()))],
        agents: Vec::new(),
    };
    assert!(start(&catalog, &set, "lib/v", Map::new()).is_err());
    assert!(start(&catalog, &set, "w", Map::new()).is_ok());
}

#[test]
fn the_digest_covers_the_set_only_when_given() {
    let catalog = json!({"w": {"goal": "g", "risk": "low",
        "steps": [{"capability": "retrieve", "purpose": "p", "store_as": "r",
                   "input_bindings": {"target": "t"}}]}});
    let plain = start(&catalog, &SetOptions::default(), "w", Map::new()).unwrap();
    let with = SetOptions {
        catalogs: Vec::new(),
        agents: vec![writer()],
    };
    let managed = start(&catalog, &with, "w", Map::new()).unwrap();
    let snap = plain.snapshot(None);
    // The same catalog without a set restores; with manifests it is
    // another program.
    assert!(Run::restore(&ctx(), &catalog, &snap, None).is_ok());
    assert!(Run::restore_set(&ctx(), &catalog, &with, &snap, None, Default::default()).is_err());
    let snap = managed.snapshot(None);
    assert!(Run::restore_set(&ctx(), &catalog, &with, &snap, None, Default::default()).is_ok());
    assert!(Run::restore(&ctx(), &catalog, &snap, None).is_err());
}
