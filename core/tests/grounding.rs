//! The grounding vectors of STANDARD v1.2 §5.20
//! (`tests/conformance/grounding/check.json`) against `grounding::check`.

use std::path::Path;

use acs_core::grounding::{self, Policy, Status};
use serde_json::Value;

#[test]
fn grounding_vectors() {
    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../tests/conformance/grounding/check.json");
    let file: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(file["status"], "normative");
    let vectors = file["vectors"].as_array().unwrap();
    assert!(vectors.len() >= 45, "grounding vectors missing");
    for v in vectors {
        let name = v["name"].as_str().unwrap();
        let kinds: Option<Vec<String>> =
            serde_json::from_value(v["policy"]["kinds"].clone()).unwrap();
        let attested = v["policy"]["attested"].as_bool().unwrap();
        // The policy's require is not needed for one output.
        let policy = Policy::new(vec!["any".into()], kinds, attested).unwrap();
        let bodies: Vec<String> = serde_json::from_value(v["bound_refs"].clone()).unwrap();
        let bound = grounding::parse_bound(&bodies).unwrap();
        let seen: Option<Vec<String>> = serde_json::from_value(v["evidence_seen"].clone()).unwrap();
        let got = grounding::check(&v["output"], &policy, &bound, seen.as_deref());
        let expect = &v["expect"];
        match (expect["status"].as_str().unwrap(), got) {
            ("refused", Err(message)) => {
                assert_eq!(expect["code"], "F505", "{name}");
                assert!(!message.is_empty(), "{name}");
            }
            (status, Ok(checked)) => {
                let want = match status {
                    "grounded" => Status::Grounded,
                    "inferred" => Status::Inferred,
                    other => panic!("{name}: status {other}"),
                };
                assert_eq!(checked.status, want, "{name}");
                assert!(expect["code"].is_null(), "{name}");
                assert_eq!(
                    checked.counted as u64,
                    expect["counted"].as_u64().unwrap(),
                    "{name}"
                );
                assert_eq!(
                    checked.legacy as u64,
                    expect["legacy"].as_u64().unwrap(),
                    "{name}"
                );
            }
            (status, got) => panic!("{name}: expected {status}, got {got:?}"),
        }
    }
}
