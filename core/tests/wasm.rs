//! The WebAssembly JSON interface (`src/wasm.rs`), driven natively: the real
//! `acs_alloc` → write → `acs_call` → read → `acs_free` cycle, and the
//! dispatcher over the repository's documents, validator fixtures and a
//! runtime fixture.
#![cfg(feature = "wasm")]

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use acs_core::wasm::{acs_alloc, acs_call, acs_free, dispatch};
use acs_core::yaml;
use serde_json::{Map, Value, json};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..")
}

/// One request through the C ABI, as a host does it.
fn call_abi(request: &[u8]) -> Value {
    let ptr = acs_alloc(request.len());
    // SAFETY: acs_alloc returned a buffer of request.len() bytes.
    unsafe { std::ptr::copy_nonoverlapping(request.as_ptr(), ptr, request.len()) };
    // SAFETY: ptr[..len] is the initialised request.
    let out = unsafe { acs_call(ptr, request.len()) };
    // SAFETY: the result starts with a 4-byte length, then that many bytes.
    let n = u32::from_le_bytes(unsafe { *out.cast::<[u8; 4]>() }) as usize;
    // SAFETY: as above; the bytes after the length are the JSON.
    let body = unsafe { std::slice::from_raw_parts(out.add(4), n) }.to_vec();
    // SAFETY: both buffers are released once, with the lengths they have.
    unsafe {
        acs_free(ptr, request.len());
        acs_free(out, 4 + n);
    }
    serde_json::from_slice(&body).unwrap()
}

fn call(request: Value) -> Value {
    serde_json::from_str(&dispatch(request.to_string().as_bytes())).unwrap()
}

fn ok(request: Value) -> Value {
    let answer = call(request.clone());
    assert!(answer.get("error").is_none(), "{request} -> {answer}");
    answer["ok"].clone()
}

fn kind(answer: &Value) -> &str {
    answer["error"]["kind"].as_str().unwrap_or("")
}

#[test]
fn abi_empty_request() {
    let answer = call_abi(b"");
    assert_eq!(kind(&answer), "bad_request");
}

#[test]
fn abi_version() {
    let answer = call_abi(br#"{"op":"version"}"#);
    assert_eq!(answer["ok"]["standard"], "1.2.0");
    assert_eq!(answer["ok"]["spec_versions"], json!(["1.0", "1.1", "1.2"]));
}

#[test]
fn abi_malformed_and_large() {
    assert_eq!(kind(&call_abi(b"{")), "bad_request");
    assert_eq!(kind(&call_abi(br#"{"op": 1}"#)), "bad_request");
    assert_eq!(kind(&call_abi(br#"{"op": "nope"}"#)), "unknown_op");
    assert_eq!(kind(&call_abi(b"\xff\xfe")), "bad_request");
    // A request of 1 MiB round-trips.
    let text = format!(
        "{{\"op\":\"yaml.parse\",\"max_bytes\":4194304,\"text\":\"x: {}\"}}",
        "a".repeat(1 << 20)
    );
    let answer = call_abi(text.as_bytes());
    assert_eq!(answer["ok"]["x"].as_str().map(str::len), Some(1 << 20));
}

/// The repository's ontology and every schema document, as the TypeScript
/// package bundles them.
fn context() -> u64 {
    let root = root();
    let ontology = yaml::load_file(
        &root.join("schemas/capability_ontology.yaml"),
        yaml::ONTOLOGY_MAX_BYTES,
    )
    .unwrap();
    let mut documents = Map::new();
    let mut stack = vec![root.join("schemas")];
    while let Some(dir) = stack.pop() {
        for entry in std::fs::read_dir(&dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            let rel = path
                .strip_prefix(&root)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            let value = match path.extension().and_then(|e| e.to_str()) {
                Some("yaml" | "yml") => yaml::load_file(&path, yaml::ONTOLOGY_MAX_BYTES).ok(),
                Some("json") => serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).ok(),
                _ => None,
            };
            if let Some(v) = value {
                documents.insert(rel, v);
            }
        }
    }
    ok(json!({"op": "context.new", "ontology": ontology, "documents": documents}))["context"]
        .as_u64()
        .unwrap()
}

#[test]
fn every_validator_fixture_gives_its_expected_codes() {
    let root = root();
    let ctx = context();
    let fixtures = root.join("tests/fixtures");
    let expectations: Map<String, Value> =
        serde_json::from_str(&std::fs::read_to_string(fixtures.join("EXPECTATIONS.json")).unwrap())
            .unwrap();
    for (name, meta) in &expectations {
        let text = std::fs::read_to_string(fixtures.join(format!("{name}.workflow_catalog.yaml")))
            .unwrap();
        let parsed = ok(json!({"op": "catalog.parse", "text": text}));
        let profiles: Vec<Value> = meta
            .get("profiles")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .map(|p| {
                yaml::load_file(&root.join(p.as_str().unwrap()), yaml::DEFAULT_MAX_BYTES).unwrap()
            })
            .collect();
        let report = ok(
            json!({"op": "validate", "context": ctx, "catalog": parsed["catalog"],
            "header": parsed["header"], "profiles": profiles}),
        );
        let codes = |severity: &str| -> BTreeSet<String> {
            report["diagnostics"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|d| d["severity"] == severity)
                .map(|d| d["code"].as_str().unwrap().to_string())
                .collect()
        };
        let expected = |key: &str| -> BTreeSet<String> {
            meta.get(key)
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .map(|c| c.as_str().unwrap().to_string())
                .collect()
        };
        let errors = codes("error");
        assert_eq!(
            errors.is_empty(),
            meta["should_pass"].as_bool().unwrap(),
            "{name}"
        );
        if !errors.is_empty() {
            assert_eq!(errors, expected("expected_error_codes"), "{name}");
        }
        assert_eq!(
            codes("warning"),
            expected("expected_warning_codes"),
            "{name}"
        );
    }
}

#[test]
fn a_runtime_fixture_runs_through_the_interface() {
    let ctx = context();
    let f: Value = serde_json::from_str(
        &std::fs::read_to_string(
            root().join("tests/conformance/runtime/profile_person_overrides_mandate.json"),
        )
        .unwrap(),
    )
    .unwrap();
    let mut options = json!({"run_id": "r", "now_ms": f["start"], "attendance": f["attendance"],
        "header": f["header"]});
    options["profiles"] = f["profiles"].clone();
    let run = ok(
        json!({"op": "run.start", "context": ctx, "catalog": f["catalog"],
        "workflow": f["workflow"], "inputs": f["inputs"], "options": options}),
    )["run"]
        .clone();
    for entry in f["script"].as_array().unwrap() {
        let action = ok(json!({"op": "run.next", "run": run}));
        let mut response = entry["respond"].clone();
        if response.get("digest") == Some(&json!("{{digest}}")) {
            response["digest"] = action["digest"].clone();
        }
        // Saved and restored before every response.
        let snap = ok(json!({"op": "run.snapshot", "run": run, "key_hex": "0a0b"}));
        let restored = ok(
            json!({"op": "run.restore", "context": ctx, "catalog": f["catalog"],
            "snapshot": snap, "key_hex": "0a0b"}),
        )["run"]
            .clone();
        ok(
            json!({"op": "run.submit", "run": restored, "id": action["id"],
            "response": response, "now_ms": f["start"]}),
        );
        ok(json!({"op": "run.submit", "run": run, "id": action["id"],
            "response": response, "now_ms": f["start"]}));
        ok(json!({"op": "run.drop", "run": restored}));
    }
    assert_eq!(
        ok(json!({"op": "run.next", "run": run}))["kind"],
        "Completed"
    );
    assert_eq!(ok(json!({"op": "run.finished", "run": run})), json!(true));
    let records = ok(json!({"op": "run.action_records", "run": run}));
    assert_eq!(records[0]["person_required"], json!(true));
    let trace = ok(json!({"op": "run.trace", "run": run}));
    assert!(
        trace
            .as_array()
            .unwrap()
            .iter()
            .any(|t| t["kind"] == "person_required")
    );
}

#[test]
fn the_run_operations_through_the_interface() {
    // STANDARD v1.2 §5.19.2: wake-up time, tick, cancel, records and the
    // run record; resume refuses a run that did not end deferred.
    let ctx = context();
    let catalog = json!({"w": {"goal": "g", "risk": "low",
        "workflow_extensions": {"requires": ["wait@1"]}, "steps": [
        {"capability": "retrieve", "purpose": "p", "store_as": "r", "delay": "PT1M",
         "input_bindings": {"target": "x"}}]}});
    let run = ok(
        json!({"op": "run.start", "context": ctx, "catalog": catalog, "workflow": "w",
        "options": {"run_id": "run-9", "now_ms": 0, "header": "1.2.0"}}),
    )["run"]
        .clone();
    assert_eq!(ok(json!({"op": "run.run_id", "run": run})), "run-9");
    assert_eq!(ok(json!({"op": "run.next", "run": run}))["kind"], "Sleep");
    assert_eq!(ok(json!({"op": "run.wake_at", "run": run})), json!(60_000));
    let tick = ok(json!({"op": "run.tick", "run": run, "now_ms": 1}));
    assert_eq!(tick, json!({"changed": false}));
    let seq = ok(json!({"op": "run.trace_seq", "run": run}));
    let resume = call(json!({"op": "run.resume", "run": run, "now_ms": 1}));
    assert_eq!(kind(&resume), "run");
    assert_eq!(ok(json!({"op": "run.run_record", "run": run})), Value::Null);
    ok(json!({"op": "run.cancel", "run": run, "reason": "stop", "now_ms": 2}));
    let end = ok(json!({"op": "run.next", "run": run}));
    assert_eq!(
        (end["kind"].as_str(), end["code"].as_str()),
        (Some("Failed"), Some("R408"))
    );
    assert_eq!(ok(json!({"op": "run.wake_at", "run": run})), Value::Null);
    let again = call(json!({"op": "run.cancel", "run": run, "reason": "x", "now_ms": 3}));
    assert_eq!(kind(&again), "run");
    // What the cancel added is read from the seq taken before it.
    let added = ok(json!({"op": "run.trace", "run": run, "since": seq}));
    assert!(
        added
            .as_array()
            .unwrap()
            .iter()
            .any(|t| t["kind"] == "run_cancelled")
    );
    let record = ok(json!({"op": "run.run_record", "run": run}));
    assert_eq!(record["run_id"], "run-9");
    let trace = ok(json!({"op": "run.take_trace", "run": run}));
    assert!(!trace.as_array().unwrap().is_empty());
    assert_eq!(ok(json!({"op": "run.trace", "run": run})), json!([]));
    let heads = ok(json!({"op": "run.taken_sha256", "run": run}));
    assert!(heads["trace"].as_str().is_some_and(|h| !h.is_empty()));
    ok(json!({"op": "run.take_records", "run": run}));
}

#[test]
fn start_needs_the_header_member() {
    let ctx = context();
    let catalog = json!({"w": {"goal": "g", "risk": "low", "steps": [
        {"capability": "retrieve", "purpose": "p", "store_as": "r", "input_bindings": {"target": "x"}}]}});
    let answer = call(
        json!({"op": "run.start", "context": ctx, "catalog": catalog,
        "workflow": "w", "options": {"run_id": "r", "now_ms": 0}}),
    );
    assert_eq!(kind(&answer), "bad_request");
    assert!(
        answer["error"]["message"]
            .as_str()
            .unwrap()
            .contains("options.header is required")
    );
    let answer = call(json!({"op": "validate", "context": ctx, "catalog": catalog}));
    assert_eq!(kind(&answer), "bad_request");
    ok(
        json!({"op": "run.start", "context": ctx, "catalog": catalog,
        "workflow": "w", "options": {"run_id": "r", "now_ms": 0, "header": null}}),
    );
}

#[test]
fn profiles_through_the_interface() {
    let ctx = context();
    let profiles = json!([{"domain": "d", "version": "1.0.0",
        "risk_thresholds": {"block_autonomous": ["mutate"]}}]);
    let flags = ok(
        json!({"op": "profile.flags", "context": ctx, "profiles": profiles,
        "capability": "mutate"}),
    );
    assert_eq!(flags["person"], json!(true));
    let bad = json!([{"domain": "d"}]);
    let answer = call(json!({"op": "profile.policy", "context": ctx, "profiles": bad}));
    assert_eq!(kind(&answer), "bad_request");
    assert_eq!(answer["error"]["diagnostics"][0]["code"], "S304");
    let checked = ok(json!({"op": "profile.check", "context": ctx, "profiles": bad}));
    assert_eq!(checked["diagnostics"][0]["code"], "S304");
}

#[test]
fn a_run_reports_its_profiles_warnings() {
    // STANDARD v1.2 §5.21.4: a host that applies profiles only through
    // `run.start` sees their warnings (a misspelled member is W604, and
    // ignored); a run without profiles reports none.
    let ctx = context();
    let catalog = json!({"w": {"goal": "g", "risk": "low", "steps": [
        {"capability": "retrieve", "purpose": "p", "store_as": "r",
         "input_bindings": {"target": "x"}}]}});
    let start = |profiles: Value| {
        ok(
            json!({"op": "run.start", "context": ctx, "catalog": catalog,
            "workflow": "w", "options": {"run_id": "r", "now_ms": 0,
            "header": "1.2.0", "profiles": profiles}}),
        )
    };
    let started = start(json!([{"domain": "d", "version": "1.0.0",
        "risk_threshold": {"require_human": "low"}}]));
    assert!(started["run"].is_u64());
    let warnings = started["warnings"].as_array().unwrap();
    assert_eq!(warnings.len(), 1, "{warnings:?}");
    assert_eq!(
        (&warnings[0]["code"], &warnings[0]["severity"]),
        (&json!("W604"), &json!("warning"))
    );
    assert_eq!(start(json!([]))["warnings"], json!([]));
}

#[test]
fn unknown_handles_and_dropped_contexts() {
    assert_eq!(
        kind(&call(json!({"op": "run.next", "run": 999_999}))),
        "unknown_handle"
    );
    let ctx = context();
    ok(json!({"op": "context.drop", "context": ctx}));
    assert_eq!(
        kind(&call(json!({"op": "context.contracts", "context": ctx}))),
        "unknown_handle"
    );
    assert_eq!(
        kind(&call(json!({"op": "context.new", "ontology": {}}))),
        "load"
    );
}

#[test]
fn expressions_through_the_interface() {
    let value = ok(json!({"op": "expr.eval", "expr": "${a} > 1", "bindings": {"a": 2}}));
    assert_eq!(value, json!({"value": true}));
    let err = ok(json!({"op": "expr.eval", "expr": "(", "bindings": {}}));
    assert_eq!(err, json!({"error": "V108"}));
    let codes = ok(json!({"op": "expr.check", "expr": "${a} > 1", "scope": {}}));
    assert!(codes["codes"].is_array());
}
