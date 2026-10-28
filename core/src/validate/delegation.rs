//! Delegation hints and sender filtering (STANDARD v1.1 §5.15, design-114
//! §14; `delegation@1`). The inputs themselves are typed by the ontology
//! and checked like any binding; binding them needs the extension declared.

use serde_json::{Map, Value};

use super::extensions::Declared;
use super::{Report, StepLoc};
use crate::diag::Code;

/// Capability inputs that belong to `delegation@1`.
const INPUTS: &[(&str, &[&str])] = &[
    (
        "delegate",
        &[
            "fresh_context",
            "model_family",
            "role",
            "read_only",
            "accept_from",
        ],
    ),
    ("receive", &["accept_from"]),
    ("synchronize", &["accept_from"]),
];

/// V106 for each `delegation@1` input bound without the declaration.
pub(crate) fn check(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    declared: &Declared,
    report: &mut Report,
) {
    let Some(Value::Object(bindings)) = step.get("input_bindings") else {
        return;
    };
    let Some((_, keys)) = INPUTS.iter().find(|(cap, _)| *cap == loc.capability) else {
        return;
    };
    for key in keys.iter().filter(|k| bindings.contains_key(**k)) {
        declared.require(
            "delegation@1",
            &format!("input '{key}' of '{}'", loc.capability),
            |d| loc.locate(d).at("field", format!("input_bindings.{key}")),
            report,
        );
    }
    // Sender filters on a delegate apply to the result it waits for.
    if loc.capability == "delegate" && !step.get("wait").is_some_and(Value::is_object) {
        for key in [
            "accept_from",
            "sender_check",
            "accept_trust_classes",
            "always_ask_trust_classes",
        ]
        .iter()
        .filter(|k| bindings.contains_key(**k))
        {
            report.push(
                loc.diag(
                    Code::SchemaValidationFailed,
                    format!(
                        "'{key}' filters the result a delegate waits for, but this step has no 'wait'"
                    ),
                )
                .at("field", format!("input_bindings.{key}")),
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::super::tests::codes;

    fn catalog(steps: Value, requires: &[&str]) -> Value {
        json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
                     "workflow_extensions": {"requires": requires},
                     "steps": steps}})
    }

    fn delegate(extra: Value) -> Value {
        let mut bindings = json!({"task": {"t": 1}, "agent": "a"});
        for (k, v) in extra.as_object().unwrap() {
            bindings[k] = v.clone();
        }
        json!({"capability": "delegate", "purpose": "p", "store_as": "d",
               "input_bindings": bindings})
    }

    #[test]
    fn hints_need_the_declaration() {
        let hints = json!({"fresh_context": true, "model_family": "m", "role": "reviewer",
                           "read_only": true});
        assert!(codes(catalog(json!([delegate(hints.clone())]), &["delegation@1"])).is_empty());
        assert_eq!(
            codes(catalog(json!([delegate(hints)]), &[])),
            ["V106", "V106", "V106", "V106"]
        );
        assert!(codes(catalog(json!([delegate(json!({}))]), &[])).is_empty());
    }

    #[test]
    fn sender_filters_on_a_delegate_need_a_wait() {
        let mut d = delegate(json!({"accept_from": ["a"]}));
        assert_eq!(
            codes(catalog(json!([d.clone()]), &["delegation@1"])),
            ["S303"]
        );
        d["timeout"] = json!("1h");
        d["wait"] = json!({"event_type": "done"});
        assert!(codes(catalog(json!([d]), &["delegation@1", "wait@1"])).is_empty());
    }

    #[test]
    fn accept_from() {
        let receive = json!({"capability": "receive", "purpose": "p", "store_as": "r",
                             "input_bindings": {"accept_from": ["a", "b"]}});
        assert!(codes(catalog(json!([receive.clone()]), &["delegation@1"])).is_empty());
        assert_eq!(codes(catalog(json!([receive]), &[])), ["V106"]);
        let sync = json!({"capability": "synchronize", "purpose": "p", "store_as": "s",
                          "input_bindings": {"agents": ["a", "b"], "state": {},
                                             "accept_from": ["a"]}});
        assert_eq!(codes(catalog(json!([sync]), &[])), ["V106"]);
    }
}
