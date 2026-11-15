//! Grounding policies and the evidence-anchor kind grammar (STANDARD v1.2
//! §5.20, §6.5).
//!
//! Foundation: the policy's shape, its checks and the kind grammar, which
//! the profile loader (S6) and the executor's start options use. Workstream
//! S4 adds the check of an output against a policy (`check`), anchors,
//! inference methods and coverage; its design is
//! `tasks/standard-1.2/designs/S4.md` part 5.1.

use serde::{Deserialize, Serialize};

use crate::ontology::Ontology;

/// The evidence-anchor kinds §6.5 defines. Any other kind is a vendor kind
/// (`x-…`, [`vendor`]).
pub const KINDS: &[&str] = &[
    "file",
    "url",
    "tool",
    "log",
    "sensor",
    "human_note",
    "api",
    "record",
];

/// A vendor name: `x-`, then a lowercase letter or a digit, then lowercase
/// letters, digits, `_`, `.` or `-`.
pub fn vendor(v: &str) -> bool {
    let Some(rest) = v.strip_prefix("x-") else {
        return false;
    };
    let mut chars = rest.chars();
    chars
        .next()
        .is_some_and(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || "_.-".contains(c))
}

/// Whether `k` is an evidence-anchor kind (§6.5): one of [`KINDS`] or a
/// vendor kind. The one grammar of anchor kinds: grounding policies,
/// profiles' `required_anchor_types` and anchors all use it.
pub fn is_kind(k: &str) -> bool {
    KINDS.contains(&k) || vendor(k)
}

/// A grounding policy (§5.20): the outputs of the capabilities it
/// `require`s must be grounded, by anchors of the `kinds` it lists (any
/// kind when absent), attested by the host when `attested`.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct Policy {
    pub require: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kinds: Option<Vec<String>>,
    #[serde(default)]
    pub attested: bool,
}

impl Policy {
    /// A policy, with its shape checked: `require` a non-empty list of
    /// distinct capability ids; `kinds`, when given, a non-empty list of
    /// distinct anchor kinds ([`is_kind`]). Whether the ids are the
    /// ontology's is [`Policy::check_ids`]'s question.
    pub fn new(
        require: Vec<String>,
        kinds: Option<Vec<String>>,
        attested: bool,
    ) -> Result<Policy, String> {
        if require.is_empty() {
            return Err("require must list at least one capability".into());
        }
        if let Some((i, id)) = repeated(&require) {
            return Err(format!("require[{i}]: '{id}' is listed twice"));
        }
        if let Some(kinds) = &kinds {
            if kinds.is_empty() {
                return Err("kinds, when given, must list at least one anchor kind".into());
            }
            if let Some((i, k)) = kinds.iter().enumerate().find(|(_, k)| !is_kind(k)) {
                return Err(format!(
                    "kinds[{i}]: '{k}' is not an anchor kind ({}, or a vendor kind x-...)",
                    KINDS.join(", ")
                ));
            }
            if let Some((i, k)) = repeated(kinds) {
                return Err(format!("kinds[{i}]: '{k}' is listed twice"));
            }
        }
        Ok(Policy {
            require,
            kinds,
            attested,
        })
    }

    /// `Err` names the first required id the ontology does not define
    /// (V101), with the closest id as a hint.
    pub fn check_ids(&self, ontology: &Ontology) -> Result<(), String> {
        let Some((i, id)) = self
            .require
            .iter()
            .enumerate()
            .find(|(_, id)| ontology.get(id).is_none())
        else {
            return Ok(());
        };
        let known: Vec<&str> = ontology.capabilities.keys().map(String::as_str).collect();
        let hint = crate::validate::semantics::closest(id, &known)
            .map(|c| format!("; did you mean '{c}'?"))
            .unwrap_or_default();
        Err(format!(
            "require[{i}]: '{id}' is not a capability of the ontology (V101){hint}"
        ))
    }

    /// Whether the policy covers outputs of `capability`.
    pub fn requires(&self, capability: &str) -> bool {
        self.require.iter().any(|r| r == capability)
    }
}

/// The first item equal to an earlier one, with its index.
fn repeated(items: &[String]) -> Option<(usize, &str)> {
    items
        .iter()
        .enumerate()
        .find(|(i, x)| items[..*i].contains(x))
        .map(|(i, x)| (i, x.as_str()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn kinds() {
        for k in KINDS {
            assert!(is_kind(k));
        }
        for k in ["x-scan", "x-0", "x-a.b_c-d"] {
            assert!(is_kind(k), "{k}");
        }
        for k in ["", "File", "x-", "x-A", "x-_a", "x-a b", "document", "x-é"] {
            assert!(!is_kind(k), "{k}");
        }
    }

    #[test]
    fn policy_shape() {
        let s = |v: &[&str]| v.iter().map(|x| x.to_string()).collect::<Vec<_>>();
        let p = Policy::new(s(&["search", "retrieve"]), Some(s(&["file", "x-db"])), true).unwrap();
        assert!(p.requires("search") && !p.requires("send"));
        assert!(Policy::new(s(&["search"]), None, false).is_ok());
        for (require, kinds) in [
            (s(&[]), None),
            (s(&["a", "a"]), None),
            (s(&["a"]), Some(s(&[]))),
            (s(&["a"]), Some(s(&["file", "file"]))),
            (s(&["a"]), Some(s(&["paper"]))),
        ] {
            assert!(
                Policy::new(require.clone(), kinds.clone(), false).is_err(),
                "{require:?} {kinds:?}"
            );
        }
        // Absent kinds stay absent, not empty.
        let v = serde_json::to_value(Policy::new(s(&["a"]), None, false).unwrap()).unwrap();
        assert_eq!(v, json!({"require": ["a"], "attested": false}));
        let back: Policy = serde_json::from_value(json!({"require": ["a"]})).unwrap();
        assert_eq!(back, Policy::new(s(&["a"]), None, false).unwrap());
    }

    #[test]
    fn ids_against_the_ontology() {
        let ontology = Ontology::from_value(&json!({"nodes": [
            {"id": "classify", "layer": "UNDERSTAND"},
            {"id": "search", "layer": "PERCEIVE"}
        ]}))
        .unwrap();
        let p = |ids: &[&str]| {
            Policy::new(ids.iter().map(|x| x.to_string()).collect(), None, false).unwrap()
        };
        assert!(p(&["search", "classify"]).check_ids(&ontology).is_ok());
        let e = p(&["search", "clasify"]).check_ids(&ontology).unwrap_err();
        assert!(
            e.contains("require[1]") && e.contains("V101") && e.contains("'classify'"),
            "{e}"
        );
    }
}
