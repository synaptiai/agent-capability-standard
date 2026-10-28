//! Sender identity checks (STANDARD v1.1 §5.17, RFC-0004; `identity@1`).
//! The inputs are typed by the ontology like any binding; binding them
//! needs the extension declared, and literal values must come from the
//! vocabularies of `schemas/agent_identity_schema.yaml`.

use serde_json::{Map, Value};

use super::extensions::{Declared, s303};
use super::{Report, StepLoc};

/// Capability inputs that belong to `identity@1`.
const INPUTS: &[&str] = &[
    "sender_check",
    "accept_trust_classes",
    "always_ask_trust_classes",
];

/// `agent_identity.authenticated_by` values; `x-` values are vendor ones.
pub(crate) const MECHANISMS: &[&str] = &[
    "session_id",
    "chat_user_id",
    "code_host_login",
    "directory_id",
    "api_key",
    "signed_token",
];

/// `agent_identity.trust_class` values.
pub(crate) const TRUST_CLASSES: &[&str] = &[
    "owner",
    "decision_person",
    "system_of_record",
    "own_subagent_report",
    "peer_agent",
    "colleague",
    "external",
];

/// An `authenticated_by` value: a standard mechanism or a vendor one.
pub(crate) fn known_mechanism(m: &str) -> bool {
    MECHANISMS.contains(&m) || vendor(m)
}

/// A vendor mechanism: `x-` then a lower-case letter or digit, then lower-case
/// letters, digits, `_`, `.` or `-` (the schema's pattern).
fn vendor(m: &str) -> bool {
    let Some(rest) = m.strip_prefix("x-") else {
        return false;
    };
    let mut chars = rest.chars();
    chars
        .next()
        .is_some_and(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || "_.-".contains(c))
}

/// A string that is one whole `${...}` reference.
fn is_reference(s: &str) -> bool {
    let refs = crate::refs::find_refs(s);
    refs.len() == 1 && refs[0].start == 0 && refs[0].end == s.len() && refs[0].parsed.is_ok()
}

/// V106 for each `identity@1` input bound without the declaration; S303 for
/// a literal value outside its vocabulary.
pub(crate) fn check(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    declared: &Declared,
    report: &mut Report,
) {
    if !matches!(loc.capability, "receive" | "synchronize" | "delegate") {
        return;
    }
    let Some(Value::Object(bindings)) = step.get("input_bindings") else {
        return;
    };
    for key in INPUTS {
        let Some(value) = bindings.get(*key) else {
            continue;
        };
        let field = format!("input_bindings.{key}");
        declared.require(
            "identity@1",
            &format!("input '{key}' of '{}'", loc.capability),
            |d| loc.locate(d).at("field", field.clone()),
            report,
        );
        // Literal values are checked here; values references supply are
        // checked when the step runs (R402).
        let items = match value {
            Value::Array(items) => items,
            Value::String(s) if is_reference(s) => continue,
            other => {
                report.push(s303(
                    &|d| loc.locate(d),
                    &field,
                    format!(
                        "{key} must be a list, found {}",
                        crate::yaml::kind_of(other)
                    ),
                ));
                continue;
            }
        };
        // An empty list of accepted values accepts nothing: every item is
        // dropped and the wait can only time out.
        if items.is_empty() && *key != "always_ask_trust_classes" {
            report.push(s303(
                &|d| loc.locate(d),
                &field,
                format!("an empty {key} accepts no sender; leave it out to accept all"),
            ));
        }
        for (i, item) in items.iter().enumerate() {
            let Some(s) = item.as_str() else {
                report.push(s303(
                    &|d| loc.locate(d),
                    &format!("{field}[{i}]"),
                    format!("{key} values are strings, found {item}"),
                ));
                continue;
            };
            // A value with a reference in it is checked when the step runs.
            if crate::refs::find_refs(s).iter().any(|m| m.parsed.is_ok()) {
                continue;
            }
            let known = if *key == "sender_check" {
                known_mechanism(s)
            } else {
                TRUST_CLASSES.contains(&s)
            };
            if !known {
                let vocabulary = if *key == "sender_check" {
                    format!("{}, or x-<vendor>", MECHANISMS.join(", "))
                } else {
                    TRUST_CLASSES.join(", ")
                };
                report.push(s303(
                    &|d| loc.locate(d),
                    &format!("{field}[{i}]"),
                    format!("'{s}' is not one of the {key} values ({vocabulary})"),
                ));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::super::tests::codes;
    use super::{MECHANISMS, TRUST_CLASSES};

    fn catalog(bindings: Value, requires: &[&str]) -> Value {
        json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
                     "workflow_extensions": {"requires": requires},
                     "steps": [{"capability": "receive", "purpose": "p", "store_as": "r",
                                "input_bindings": bindings}]}})
    }

    #[test]
    fn inputs_need_the_declaration() {
        let b = json!({"sender_check": ["session_id"], "accept_trust_classes": ["owner"],
                       "always_ask_trust_classes": ["external"]});
        assert!(codes(catalog(b.clone(), &["identity@1"])).is_empty());
        assert_eq!(codes(catalog(b, &[])), ["V106", "V106", "V106"]);
        let sync = json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
            "steps": [{"capability": "synchronize", "purpose": "p", "store_as": "s",
                       "input_bindings": {"agents": ["a", "b"], "state": {},
                                          "accept_trust_classes": ["owner"]}}]}});
        assert_eq!(codes(sync), ["V106"]);
    }

    #[test]
    fn literal_values_come_from_the_vocabularies() {
        let ok = json!({"sender_check": ["api_key", "x-acme.sso", "x-9"],
                        "accept_trust_classes": ["peer_agent"]});
        assert!(codes(catalog(ok, &["identity@1"])).is_empty());
        // Nothing to ask about is harmless.
        assert!(
            codes(catalog(
                json!({"always_ask_trust_classes": []}),
                &["identity@1"]
            ))
            .is_empty()
        );
        for bad in [
            json!({"sender_check": ["password"]}),
            json!({"sender_check": ["x-"]}),
            json!({"sender_check": ["x-Upper"]}),
            json!({"accept_trust_classes": ["stranger"]}),
            json!({"always_ask_trust_classes": ["Owner"]}),
            json!({"accept_trust_classes": "owner"}),
            json!({"accept_trust_classes": ["owner", 5]}),
            json!({"sender_check": {"a": 1}}),
            json!({"sender_check": []}),
            json!({"accept_trust_classes": []}),
        ] {
            assert_eq!(codes(catalog(bad, &["identity@1"])), ["S303"]);
        }
        // References are not checked statically.
        let refs = json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
            "workflow_extensions": {"requires": ["identity@1"]},
            "inputs": {"classes": {"type": "array", "items": {"type": "string"}},
                       "one": {"type": "string"}},
            "steps": [{"capability": "receive", "purpose": "p", "store_as": "r",
                       "input_bindings": {"accept_trust_classes": "${classes}",
                                          "sender_check": ["${one}", "x-${one}"]}}]}});
        assert!(codes(refs).is_empty());
    }

    #[test]
    fn vocabularies_match_the_identity_schema() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
        let text =
            std::fs::read_to_string(root.join("schemas/agent_identity_schema.yaml")).unwrap();
        let doc: Value = crate::yaml::load_str(&text).unwrap();
        let props = &doc["agent_identity"]["properties"];
        let classes: Vec<&str> = props["trust_class"]["enum"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        assert_eq!(classes, TRUST_CLASSES);
        let pattern = props["authenticated_by"]["pattern"].as_str().unwrap();
        for m in MECHANISMS {
            assert!(
                pattern.contains(&format!("{m}|")),
                "{m} missing from the pattern"
            );
        }
    }
}
