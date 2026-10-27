//! Runs the language-neutral expression fixtures in
//! `tests/conformance/expressions/` against the core.

use std::path::PathBuf;

use acs_core::expr::check::{Checker, RootInfo, Scope};
use acs_core::expr::eval::eval_condition;
use acs_core::expr::{self};
use serde_json::{Map, Value};

fn fixture(name: &str) -> Value {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../tests/conformance/expressions")
        .join(name);
    serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
}

#[test]
fn evaluation_fixtures() {
    let doc = fixture("eval.json");
    let mut failures = Vec::new();
    for case in doc["cases"].as_array().unwrap() {
        let id = case["id"].as_str().unwrap();
        let src = case["expr"].as_str().unwrap();
        let bindings: Map<String, Value> =
            case["bindings"].as_object().cloned().unwrap_or_default();
        let expect = &case["expect"];
        let got = match expr::parse(src) {
            Err(_) => serde_json::json!({"error": "V108"}),
            Ok(e) => match eval_condition(&e, &bindings) {
                Ok(v) => serde_json::json!({"value": v}),
                Err(_) => serde_json::json!({"error": "R405"}),
            },
        };
        if &got != expect {
            failures.push(format!("{id}: expected {expect}, got {got} for {src:?}"));
        }
    }
    assert!(
        failures.is_empty(),
        "{} failures:\n{}",
        failures.len(),
        failures.join("\n")
    );
}

struct FixtureScope(Map<String, Value>);

impl Scope for FixtureScope {
    fn root(&self, name: &str) -> Option<RootInfo<'_>> {
        let r = self.0.get(name)?;
        Some(RootInfo {
            schema: r.get("schema"),
            always_present: r["always_present"].as_bool().unwrap_or(false),
        })
    }
}

#[test]
fn static_check_fixtures() {
    let doc = fixture("check.json");
    let scope = FixtureScope(doc["scope"].as_object().cloned().unwrap());
    let mut failures = Vec::new();
    for case in doc["cases"].as_array().unwrap() {
        let id = case["id"].as_str().unwrap();
        let src = case["expr"].as_str().unwrap();
        let expect: Vec<&str> = case["expect"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        let got: Vec<&'static str> = match expr::parse(src) {
            Err(e) if e.annotation => vec!["B205"],
            Err(_) => vec!["V108"],
            Ok(e) => {
                let mut c = Checker::new(&scope);
                c.check_condition(&e);
                c.findings.iter().map(|f| f.code.as_str()).collect()
            }
        };
        if got != expect {
            failures.push(format!(
                "{id}: expected {expect:?}, got {got:?} for {src:?}"
            ));
        }
    }
    assert!(
        failures.is_empty(),
        "{} failures:\n{}",
        failures.len(),
        failures.join("\n")
    );
}
