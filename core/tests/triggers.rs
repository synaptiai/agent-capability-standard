//! The fire-time vectors of STANDARD v1.2 §5.10.2
//! (`tests/conformance/triggers/fire_times.json`), computed independently
//! with Python's zoneinfo, against `trigger::next_fire`.

use std::path::Path;

use acs_core::trigger::next_fire;
use serde_json::Value;

#[test]
fn fire_time_vectors() {
    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../tests/conformance/triggers/fire_times.json");
    let file: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    let release = file["tzdata"].as_str().unwrap_or("?");
    let cases = file["cases"].as_object().unwrap();
    assert!(cases.len() >= 17, "fire-time vectors missing");
    for (name, case) in cases {
        let mut after = case["after_ms"].as_u64().unwrap();
        let expected = case["next_ms"].as_array().unwrap();
        let mut got = Vec::new();
        for _ in 0..expected.len().max(1) {
            match next_fire(&case["schedule"], after).unwrap() {
                Some(t) => {
                    got.push(Value::from(t));
                    after = t;
                }
                None => break,
            }
        }
        assert_eq!(
            &got,
            expected,
            "{name}: the vectors were computed with tzdata {release}, this core bundles {}; \
             they must agree on these dates (§10.3)",
            chrono_tz::IANA_TZDB_VERSION
        );
    }
}
