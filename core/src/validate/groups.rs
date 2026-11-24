//! Parallel groups at run time (STANDARD v1.2 §5.2.3): the members of a
//! group are not ordered relative to each other. W618 for a `join` this
//! version does not define (it is ignored); W619 for a member that reads a
//! group mate's store, which exists only if the executor ran that mate
//! first.

use std::collections::{HashMap, HashSet};

use serde_json::Value;

use super::Report;
use crate::diag::{Code, Diagnostic};
use crate::refs;

/// The one `join` value this version defines.
const ALL_COMPLETE: &str = "all_complete";

/// Check every step of `workflow`. `groups` holds the normal steps of each
/// group in list order (handlers belong to no group).
pub(super) fn check(
    workflow: &str,
    steps: &[Value],
    groups: &HashMap<&str, Vec<usize>>,
    handlers: &HashSet<usize>,
    report: &mut Report,
) {
    let at = |i: usize, step: &serde_json::Map<String, Value>, d: Diagnostic| {
        let d = d.at("workflow", workflow).at("step", i);
        match step.get("capability").and_then(Value::as_str) {
            Some(c) => d.at("capability", c),
            None => d,
        }
    };
    for (i, step) in steps.iter().enumerate() {
        let Some(step) = step.as_object() else {
            continue;
        };
        let group = step.get("parallel_group").and_then(Value::as_str);
        // A join that is not a string is S303 already.
        if let Some(join) = step.get("join").and_then(Value::as_str) {
            let message = match group {
                None => Some("join without a parallel_group is ignored".to_string()),
                Some(_) if join != ALL_COMPLETE => Some(format!(
                    "join '{join}' is not defined (only '{ALL_COMPLETE}'); it is ignored and the group joins when every member has finished"
                )),
                Some(_) => None,
            };
            if let Some(m) = message {
                let d = Diagnostic::new(Code::UnknownJoin, m)
                    .at("field", "join")
                    .suggest(match group {
                        None => "remove 'join', or give the step a 'parallel_group'".to_string(),
                        Some(_) => format!("use join: {ALL_COMPLETE}, or remove it (§5.2.3)"),
                    });
                report.push(at(i, step, d));
            }
        }
        let Some(members) = group
            .filter(|_| !handlers.contains(&i))
            .and_then(|g| groups.get(g))
        else {
            continue;
        };
        let mates: Vec<(usize, &str)> = members
            .iter()
            .copied()
            .filter(|&j| j != i)
            .filter_map(|j| {
                steps[j]
                    .get("store_as")
                    .and_then(Value::as_str)
                    .map(|s| (j, s))
            })
            .collect();
        if mates.is_empty() {
            continue;
        }
        let mut reported: HashSet<usize> = HashSet::new();
        for r in refs::executable_roots(step) {
            let Some(&(mate, store)) = mates.iter().find(|(_, s)| *s == r.root) else {
                continue;
            };
            if !reported.insert(mate) {
                continue;
            }
            let d = Diagnostic::new(
                Code::GroupMateRead,
                format!(
                    "the step reads '{store}', the store of step {mate} in its parallel_group '{}', which need not have run yet (§5.2.3)",
                    group.unwrap_or_default()
                ),
            )
            .at("field", r.field)
            .at("ref", r.text)
            .at("mate", mate)
            .suggest("move the step after the group, or out of it");
            report.push(at(i, step, d));
        }
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use crate::validate::tests::codes;

    fn wf(steps: serde_json::Value) -> serde_json::Value {
        json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1", "steps": steps}})
    }

    fn retrieve(store: &str, extra: serde_json::Value) -> serde_json::Value {
        let mut s = json!({"capability": "retrieve", "purpose": "p", "store_as": store,
                           "input_bindings": {"target": "t"}});
        for (k, v) in extra.as_object().unwrap() {
            s[k] = v.clone();
        }
        s
    }

    #[test]
    fn join_other_value_warns() {
        let c = wf(json!([
            retrieve("a", json!({"parallel_group": "g", "join": "any_complete"})),
            retrieve("b", json!({"parallel_group": "g"})),
        ]));
        assert_eq!(codes(c), ["W618"]);
    }

    #[test]
    fn join_without_group_warns() {
        let c = wf(json!([retrieve("a", json!({"join": "all_complete"}))]));
        assert_eq!(codes(c), ["W618"]);
    }

    #[test]
    fn join_all_complete_is_silent() {
        let c = wf(json!([
            retrieve("a", json!({"parallel_group": "g", "join": "all_complete"})),
            retrieve("b", json!({"parallel_group": "g", "join": "all_complete"})),
        ]));
        assert!(codes(c).is_empty());
    }

    #[test]
    fn mate_read_warns_once_per_mate() {
        let c = wf(json!([
            retrieve("a", json!({"parallel_group": "g"})),
            retrieve(
                "b",
                json!({"parallel_group": "g",
                       "condition": "${a.confidence} > 0",
                       "gates": [{"when": "${a.confidence} < 0.5", "action": "stop"}]})
            ),
        ]));
        assert_eq!(codes(c.clone()), ["W619"]);
        let report = crate::validate::validate_catalog(&crate::validate::tests::ctx(), &c, None);
        let d = report
            .diagnostics
            .iter()
            .find(|d| d.code.as_str() == "W619")
            .unwrap();
        assert_eq!(d.location["mate"], json!(0));
        assert_eq!(d.location["ref"], json!("a.confidence"));
        assert_eq!(d.location["field"], json!("condition"));
        assert_eq!(d.location["step"], json!(1));
    }

    #[test]
    fn read_of_earlier_non_member_is_silent() {
        let c = wf(json!([
            retrieve("a", json!({})),
            retrieve(
                "b",
                json!({"parallel_group": "g",
                       "gates": [{"when": "${a.confidence} < 0.5", "action": "stop"}]})
            ),
            retrieve(
                "c",
                json!({"parallel_group": "g",
                       "gates": [{"when": "${a.confidence} < 0.5", "action": "stop"}]})
            ),
            retrieve("d", json!({"condition": "${b.confidence} > 0"})),
        ]));
        assert_eq!(codes(c), Vec::<&str>::new());
    }

    #[test]
    fn quorum_reviewer_mate_not_w619() {
        // A quorum names its reviewers by store, not by reference: their
        // order has its own rule (§5.16), which W619 does not repeat.
        let c = json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
        "workflow_extensions": {"requires": ["quorum@1"]},
        "steps": [
            {"capability": "critique", "purpose": "p", "store_as": "r1",
             "input_bindings": {"target": "t"}},
            {"capability": "constrain", "purpose": "p", "store_as": "q",
             "parallel_group": "g",
             "quorum": {"reviewers": ["r1"], "min_approvals": 1}},
            {"capability": "retrieve", "purpose": "p", "store_as": "x",
             "parallel_group": "g", "input_bindings": {"target": "t"}}
        ]}});
        assert!(!codes(c).contains(&"W619"));
    }
}
