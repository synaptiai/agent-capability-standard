//! Domain profile vectors (STANDARD v1.2 §5.21, §10.3):
//! `tests/conformance/profiles/load.json` (diagnostics) and
//! `effective.json` (flags and rules), and a run that applies a profile
//! saved and restored.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use acs_core::exec::{Attendance, RecordMode, Run, StartError, StartOptions};
use acs_core::profile::Policy;
use acs_core::validate::{Context, Options, Report, validate_with};
use serde_json::{Map, Value, json};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn ctx() -> Context {
    let root = root();
    Context::load(&root.join("schemas/capability_ontology.yaml"), &root).unwrap()
}

fn vectors(name: &str) -> Value {
    let text =
        std::fs::read_to_string(root().join("tests/conformance/profiles").join(name)).unwrap();
    serde_json::from_str(&text).unwrap()
}

type Found = BTreeSet<(String, String, String)>;

fn split(report: &Report) -> (Found, Found) {
    let mut errors = Found::new();
    let mut warnings = Found::new();
    for d in &report.diagnostics {
        assert!(
            !d.location.contains_key("workflow"),
            "a profile diagnostic has no workflow: {d:?}"
        );
        let key = (
            d.code.as_str().to_string(),
            d.location["profile"].as_str().unwrap().to_string(),
            d.location["field"].as_str().unwrap().to_string(),
        );
        if d.is_error() {
            errors.insert(key);
        } else {
            warnings.insert(key);
        }
    }
    (errors, warnings)
}

fn expected(list: &Value) -> Found {
    list.as_array()
        .unwrap()
        .iter()
        .map(|d| {
            (
                d["code"].as_str().unwrap().to_string(),
                d["profile"].as_str().unwrap().to_string(),
                d["field"].as_str().unwrap().to_string(),
            )
        })
        .collect()
}

#[test]
fn load_vectors() {
    let ctx = ctx();
    let doc = vectors("load.json");
    assert_eq!(doc["status"], "normative");
    for v in doc["vectors"].as_array().unwrap() {
        let profiles = v["profiles"].as_array().unwrap();
        let mut report = Report::default();
        Policy::load(profiles, &ctx.ontology, &mut report);
        let (errors, warnings) = split(&report);
        assert_eq!(errors, expected(&v["expect"]["errors"]), "{}", v["name"]);
        assert_eq!(
            warnings,
            expected(&v["expect"]["warnings"]),
            "{}",
            v["name"]
        );
    }
}

#[test]
fn a_misspelled_capability_id_gets_the_closest_one() {
    let ctx = ctx();
    let mut report = Report::default();
    Policy::load(
        &[json!({"domain": "d", "version": "1.0.0", "checkpoint_policy": {"mutat": "always"}})],
        &ctx.ontology,
        &mut report,
    );
    assert_eq!(
        report.diagnostics[0].suggestion.as_deref(),
        Some("did you mean 'mutate'?")
    );
}

#[test]
fn effective_vectors() {
    let ctx = ctx();
    let doc = vectors("effective.json");
    for v in doc["flags"].as_array().unwrap() {
        let mut report = Report::default();
        let policy = Policy::load(
            v["profiles"].as_array().unwrap(),
            &ctx.ontology,
            &mut report,
        );
        assert!(report.errors().next().is_none(), "{}", v["name"]);
        let declared: Option<Map<String, Value>> =
            v.get("declared").and_then(|d| d.as_object().cloned());
        let flags = policy
            .flags_json(
                &ctx.ontology,
                v["capability"].as_str().unwrap(),
                declared.as_ref(),
            )
            .unwrap();
        assert_eq!(flags, v["expect"], "{}", v["name"]);
    }
    for v in doc["policy"].as_array().unwrap() {
        let mut report = Report::default();
        let policy = Policy::load(
            v["profiles"].as_array().unwrap(),
            &ctx.ontology,
            &mut report,
        );
        assert!(report.diagnostics.is_empty(), "{}", v["name"]);
        assert_eq!(policy.rules_json(), v["expect"], "{}", v["name"]);
    }
}

fn catalog(steps: Value) -> Value {
    json!({"w": {"goal": "g", "risk": "medium", "spec_version": "1.1", "steps": steps}})
}

fn options(profiles: Vec<Value>) -> StartOptions {
    StartOptions {
        attendance: Attendance::Attended,
        run_id: "r".into(),
        now_ms: 0,
        actor_identity: None,
        header: None,
        records: RecordMode::Approvals,
        profiles,
        grounding: Vec::new(),
        destinations: Vec::new(),
    }
}

#[test]
fn a_validator_given_profiles_reports_them_first_and_checks_raised_flags() {
    let ctx = ctx();
    let cat = catalog(json!([
        {"capability": "constrain", "purpose": "p", "store_as": "c"},
        {"capability": "execute", "purpose": "p", "store_as": "e"},
    ]));
    let profile = json!({"domain": "d", "version": "1.0.0",
        "checkpoint_policy": {"execute": "always"}, "foo": 1});
    let report = validate_with(
        &ctx,
        &cat,
        &Options {
            profiles: vec![profile],
            ..Options::default()
        },
    )
    .unwrap();
    let codes: Vec<&str> = report.diagnostics.iter().map(|d| d.code.as_str()).collect();
    assert_eq!(codes.first(), Some(&"W604"));
    assert!(codes.contains(&"F501"), "{codes:?}");
    let plain = validate_with(&ctx, &cat, &Options::default()).unwrap();
    assert!(plain.diagnostics.iter().all(|d| d.code.as_str() != "F501"));
}

#[test]
fn a_run_refuses_an_invalid_profile_and_a_raised_checkpoint_it_cannot_meet() {
    let ctx = ctx();
    let cat = catalog(json!([{"capability": "execute", "purpose": "p", "store_as": "e"}]));
    let bad = json!({"domain": "d", "version": "1.0.0", "checkpoint_policy": {"mutat": "always"}});
    match Run::start(&ctx, &cat, "w", Map::new(), options(vec![bad])) {
        Err(StartError::Invalid(d)) => assert_eq!(d[0].code.as_str(), "V101"),
        other => panic!("{:?}", other.err()),
    }
    let cp = json!({"domain": "d", "version": "1.0.0", "checkpoint_policy": {"execute": "always"}});
    match Run::start(&ctx, &cat, "w", Map::new(), options(vec![cp])) {
        Err(StartError::Invalid(d)) => assert_eq!(d[0].code.as_str(), "F501"),
        other => panic!("{:?}", other.err()),
    }
}

#[test]
fn a_snapshot_keeps_the_profiles_and_one_without_them_restores_with_none() {
    let ctx = ctx();
    let cat = catalog(
        json!([{"capability": "retrieve", "purpose": "p", "store_as": "r",
        "input_bindings": {"target": "x"}}]),
    );
    let review = json!({"domain": "d", "version": "1.0.0",
        "risk_thresholds": {"require_review": "low"}});
    let run = Run::start(&ctx, &cat, "w", Map::new(), options(vec![review])).unwrap();
    assert_eq!(run.next().body.kind(), "RequestApproval");
    let snap = run.snapshot(None);
    assert!(snap.state.contains("\"profiles\""));
    let restored = Run::restore(&ctx, &cat, &snap, None).unwrap();
    assert_eq!(restored.next().body.kind(), "RequestApproval");
    let plain = Run::start(&ctx, &cat, "w", Map::new(), options(Vec::new())).unwrap();
    let snap = plain.snapshot(None);
    assert!(!snap.state.contains("\"profiles\""));
    let restored = Run::restore(&ctx, &cat, &snap, None).unwrap();
    assert_eq!(restored.next().body.kind(), "InvokeCapability");
}

#[test]
fn a_run_refuses_a_profile_without_an_exact_json_form() {
    // The run would save a profile other than the one given: its snapshot
    // and every record digest need I-JSON (§5.19.4, §5.18.8).
    let ctx = ctx();
    let cat = catalog(
        json!([{"capability": "retrieve", "purpose": "p", "store_as": "r",
        "input_bindings": {"target": "x"}}]),
    );
    let big = json!({"domain": "d", "version": "1.0.0", "x-n": (1u64 << 60) + 1});
    match Run::start(&ctx, &cat, "w", Map::new(), options(vec![big])) {
        Err(StartError::Invalid(d)) => {
            assert_eq!(d[0].code.as_str(), "S303");
            assert_eq!(d[0].location["field"], "x-n");
        }
        other => panic!("{:?}", other.err()),
    }
    let exact = json!({"domain": "d", "version": "1.0.0", "x-n": 1u64 << 53});
    Run::start(&ctx, &cat, "w", Map::new(), options(vec![exact])).unwrap();
}

#[test]
fn a_header_that_is_not_supported_refuses_the_start() {
    let ctx = ctx();
    let cat = json!({"w": {"goal": "g", "risk": "low", "steps": [
        {"capability": "retrieve", "purpose": "p", "store_as": "r", "input_bindings": {"target": "x"}}]}});
    let mut o = options(Vec::new());
    o.header = Some("9.9".into());
    match Run::start(&ctx, &cat, "w", Map::new(), o) {
        Err(StartError::Invalid(d)) => assert_eq!(d[0].code.as_str(), "V109"),
        other => panic!("{:?}", other.err()),
    }
}

/// `run`'s snapshot with `profile` put into its state as an applied profile.
fn holding(run: &Run, profile: &Value) -> acs_core::exec::Snapshot {
    let mut state: Value = serde_json::from_str(&run.snapshot(None).state).unwrap();
    state["profiles"] = json!([profile]);
    let text = acs_core::exec::canonical::canonical(&state);
    acs_core::exec::Snapshot {
        sha256: acs_core::exec::canonical::sha256_hex(&text),
        hmac: None,
        state: text,
    }
}

#[test]
fn a_profile_grounding_policy_is_checked_at_start_and_after_a_restore() {
    // §5.21.3: `require_grounding` is a grounding policy (§5.20) whose kinds
    // are `required_anchor_types`; it applies to a 1.1 workflow, and a run
    // restored from a state that holds the profile applies it too.
    let ctx = ctx();
    let cat = catalog(json!([
        {"capability": "classify", "purpose": "p", "store_as": "c",
         "input_bindings": {"item": "x"}}
    ]));
    let profile = json!({"domain": "d", "version": "1.0.0", "evidence_policy":
        {"require_grounding": ["classify"], "required_anchor_types": ["file"]}});
    let output = |anchors: Value| acs_core::exec::Response::Output {
        value: json!({"labels": ["a"], "confidence": 1, "evidence_anchors": anchors}),
        evidence_seen: None,
    };
    let fresh = || Run::start(&ctx, &cat, "w", Map::new(), options(vec![profile.clone()]));
    let restored = || {
        let plain = Run::start(&ctx, &cat, "w", Map::new(), options(Vec::new())).unwrap();
        Run::restore(&ctx, &cat, &holding(&plain, &profile), None)
            .map_err(|e| StartError::Unsupported(e.to_string()))
    };
    for start in [&fresh as &dyn Fn() -> Result<Run, StartError>, &restored] {
        let mut run = start().unwrap();
        let id = run.next().id;
        run.submit(id, output(json!([])), 0).unwrap();
        let end = serde_json::to_value(run.next()).unwrap();
        assert_eq!(
            (end["kind"].as_str(), end["code"].as_str()),
            (Some("Failed"), Some("F505"))
        );
        let mut run = start().unwrap();
        let id = run.next().id;
        let anchor = json!([{"ref": "file:docs/item.md", "kind": "file"}]);
        run.submit(id, output(anchor), 0).unwrap();
        assert_eq!(run.next().body.kind(), "Completed");
        let grounding = run
            .trace()
            .iter()
            .find(|t| t["kind"] == "grounding")
            .cloned();
        assert_eq!(grounding.unwrap()["detail"]["policies"], json!(1));
    }
}

#[test]
fn a_profile_destination_policy_is_checked_at_start_and_after_a_restore() {
    // §5.21.3: `allowed_destinations` is a destination policy in force
    // beside the host's (§4.4.2); a `send` it does not allow fails F504
    // before approval, in a fresh run and in one restored with the profile.
    let ctx = ctx();
    let cat = catalog(json!([
        {"capability": "checkpoint", "purpose": "p", "store_as": "cp",
         "input_bindings": {"scope": "*"}},
        {"capability": "send", "purpose": "p", "store_as": "s",
         "input_bindings": {"destination": "https://x.example/", "payload": "p"}}
    ]));
    for patterns in [json!(["mailto:*"]), json!([])] {
        let profile = json!({"domain": "d", "version": "1.0.0", "allowed_destinations": patterns});
        let fresh =
            Run::start(&ctx, &cat, "w", Map::new(), options(vec![profile.clone()])).unwrap();
        let plain = Run::start(&ctx, &cat, "w", Map::new(), options(Vec::new())).unwrap();
        let restored = Run::restore(&ctx, &cat, &holding(&plain, &profile), None).unwrap();
        for mut run in [fresh, restored] {
            let id = run.next().id;
            let out = json!({"checkpoint_id": "cp1", "evidence_anchors": []});
            run.submit(
                id,
                acs_core::exec::Response::Output {
                    value: out,
                    evidence_seen: None,
                },
                0,
            )
            .unwrap();
            let end = serde_json::to_value(run.next()).unwrap();
            assert_eq!(
                (
                    end["kind"].as_str(),
                    end["code"].as_str(),
                    end["reason"].as_str()
                ),
                (
                    Some("Failed"),
                    Some("F504"),
                    Some("destination_not_allowed")
                ),
                "{patterns}"
            );
        }
    }
}

#[test]
fn the_rules_a_run_applies_start_it() {
    // Thresholds, checkpoint rules, a minimum confidence, trust weights and
    // `required_anchor_types` alone (which has no effect) do not refuse.
    let ctx = ctx();
    let cat = catalog(json!([
        {"capability": "retrieve", "purpose": "p", "store_as": "r",
         "input_bindings": {"target": "x"}}
    ]));
    let profile = json!({"domain": "d", "version": "1.0.0",
        "risk_thresholds": {"auto_approve": "high"},
        "checkpoint_policy": {"mutate": "always"},
        "evidence_policy": {"minimum_confidence": 0.5, "required_anchor_types": ["file"]},
        "trust_weights": {"trust_class:peer_agent": 0.5}});
    let run = Run::start(&ctx, &cat, "w", Map::new(), options(vec![profile])).unwrap();
    assert_eq!(run.next().body.kind(), "InvokeCapability");
}
