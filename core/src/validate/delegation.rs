//! Delegation hints and sender filtering (STANDARD v1.1 §5.15, design-114
//! §14; `delegation@1`). The inputs themselves are typed by the ontology
//! and checked like any binding; binding them needs the extension declared.

use serde_json::{Map, Value};

use super::extensions::Declared;
use super::inputs::check_names;
use super::semantics::closest;
use super::{Report, StepLoc};
use crate::agents::{self, Agents, Target};
use crate::diag::{Code, Diagnostic};
use crate::{names, yaml};

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

/// V106 for each `delegation@1` input bound without the declaration;
/// in a workflow that targets 1.2 or later (`targets_1_2`), S303 for
/// `continues` with a literal `fresh_context: true` (§5.15.3: below 1.2,
/// `continues` is W616 and an input the executor passes on, as 1.1 did).
pub(crate) fn check(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    declared: &Declared,
    targets_1_2: bool,
    report: &mut Report,
) {
    let Some(Value::Object(bindings)) = step.get("input_bindings") else {
        return;
    };
    if loc.capability == "delegate" {
        // A continued delegation keeps what its delegate did before
        // (§5.15.3), so it never has a fresh context.
        if targets_1_2
            && bindings.contains_key("continues")
            && bindings.get("fresh_context") == Some(&Value::Bool(true))
        {
            report.push(
                loc.diag(
                    Code::SchemaValidationFailed,
                    "a continued delegation never has a fresh context: 'continues' and fresh_context: true contradict each other; drop one of them",
                )
                .at("field", "input_bindings.continues"),
            );
        }
        // A literal model family is lowercase (§5.15).
        if let Some(Value::String(f)) = bindings.get("model_family")
            && !f.contains("${")
            && !names::is_model_family(f)
        {
            let mut d = loc
                .diag(
                    Code::NoncanonicalName,
                    format!(
                        "model family '{f}' is not canonical: [a-z][a-z0-9_-]*, compared exactly (§5.15)"
                    ),
                )
                .at("field", "input_bindings.model_family");
            let lower = f.to_ascii_lowercase();
            if names::is_model_family(&lower) {
                d = d.suggest(format!("write it '{lower}'"));
            }
            report.push(d);
        }
    }
    let Some((_, keys)) = INPUTS.iter().find(|(cap, _)| *cap == loc.capability) else {
        return;
    };
    for key in keys.iter().filter(|k| bindings.contains_key(**k)) {
        declared.require(
            "delegation@1",
            &format!("input '{key}' of '{}'", loc.capability),
            |d| loc.locate(d).at_field_key("input_bindings", key),
            report,
        );
    }
    // An empty allow-list drops every sender: the step can only time out.
    // (On a delegate that does not wait, the missing wait is the error.)
    let waits = loc.capability != "delegate" || step.get("wait").is_some_and(Value::is_object);
    if waits
        && bindings
            .get("accept_from")
            .and_then(Value::as_array)
            .is_some_and(Vec::is_empty)
    {
        report.push(
            loc.diag(
                Code::SchemaValidationFailed,
                "an empty accept_from accepts no sender; leave it out to accept all",
            )
            .at("field", "input_bindings.accept_from"),
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
                .at_field_key("input_bindings", key),
            );
        }
    }
}

/// The workflow field `agents` (§5.15.2) of a workflow that targets 1.2 or
/// later: a non-empty list of distinct non-empty strings (S303 otherwise).
/// Below 1.2, or with no version, the field is ignored, by the executor as by
/// an older consumer: it is W616 there (`semantics::FEATURES`), or W605.
pub(crate) fn check_agents_field(
    wf: &Map<String, Value>,
    target: Option<(u64, u64)>,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let Some(v) = wf.get("agents") else {
        return;
    };
    if target.is_none_or(|t| t < (1, 2)) {
        return;
    }
    let s303 = |field: String, message: String| {
        at(Diagnostic::new(Code::SchemaValidationFailed, message)).at("field", field)
    };
    let Value::Array(items) = v else {
        report.push(s303(
            "agents".into(),
            format!(
                "'agents' must be a list of agent names, found {}",
                yaml::kind_of(v)
            ),
        ));
        return;
    };
    if items.is_empty() {
        report.push(s303(
            "agents".into(),
            "'agents' declares no agent; leave it out".into(),
        ));
        return;
    }
    let mut seen: Vec<&str> = Vec::new();
    for (i, item) in items.iter().enumerate() {
        match item.as_str() {
            Some(a) if !a.is_empty() => {
                if seen.contains(&a) {
                    report.push(s303(
                        format!("agents[{i}]"),
                        format!("'agents' lists '{a}' twice"),
                    ));
                } else {
                    seen.push(a);
                }
            }
            _ => report.push(s303(
                format!("agents[{i}]"),
                "an 'agents' entry must be a non-empty agent name".into(),
            )),
        }
    }
}

/// A `delegate` step against the agents its workflow declares and the
/// manifests given (§5.15.2): V107 for a literal agent not listed, V101 for
/// a manifest capability the ontology lacks, S303/S304 for a literal task
/// against a literal agent's declaration; in a workflow that targets 1.2 or
/// later, W621 for unknown target maxima and W622 for a computed agent
/// without `agents`.
#[allow(clippy::too_many_arguments)]
pub(crate) fn check_targets(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    declared: Option<&[&str]>,
    agents: &Agents,
    target: &Target,
    requires_approval: bool,
    targets_1_2: bool,
    report: &mut Report,
) {
    let literal = agents::literal_agent(step);
    if let Some(listed) = declared {
        if let Some(a) = literal
            && !listed.contains(&a)
        {
            let mut d = loc
                .diag(
                    Code::UnresolvedTarget,
                    format!("agent '{a}' is not one of the workflow's agents"),
                )
                .at("field", "input_bindings.agent");
            if let Some(k) = closest(a, listed) {
                d = d.suggest(format!("did you mean '{k}'?"));
            }
            report.push(d);
        }
        if let Target::Unknown { unknown, .. } = target {
            for (agent, id) in unknown {
                report.push(
                    loc.diag(
                        Code::UnknownCapability,
                        format!(
                            "the manifest of '{agent}' lists '{id}', which the ontology does not define; the target maxima of this delegation are unknown (§11.6)"
                        ),
                    )
                    .at("field", "input_bindings.agent"),
                );
            }
        }
        if let Some(a) = literal
            && let Some(decl) = agents.get(a).and_then(|m| m.task.as_ref())
            && let Some(Value::Object(task)) =
                step.get("input_bindings").and_then(|b| b.get("task"))
        {
            let given: Vec<String> = task.keys().cloned().collect();
            check_names(
                decl,
                &given,
                |name| {
                    loc.diag(
                        Code::SchemaValidationFailed,
                        format!(
                            "'{a}' has no task input '{name}'; the executor refuses undeclared inputs (R402)"
                        ),
                    )
                    .at_field_key("input_bindings.task", name)
                },
                |name| {
                    loc.diag(
                        Code::MissingRequiredField,
                        format!("'{a}' needs task input '{name}', which the task does not give"),
                    )
                    .at("field", "input_bindings.task")
                },
                report,
            );
        }
    }
    if !targets_1_2 {
        return;
    }
    let unbounded = match (declared, target) {
        (Some(_), Target::Unknown { .. }) => target.why_unknown().map(|why| {
            format!("{why}; the executor will not delegate without the target agents' manifests")
        }),
        (None, _) if !agents::binds_read_only(step) && !requires_approval => Some(
            "the target's maxima are unknown, so the delegate may act on the world with no checkpoint or approval".to_string(),
        ),
        _ => None,
    };
    if let Some(why) = unbounded {
        report.push(
            loc.diag(Code::UnboundedDelegation, format!("unbounded delegation: {why}"))
                .at("field", "input_bindings.agent")
                .suggest(if declared.is_some() {
                    "give the validator the manifests of the agents the step may delegate to"
                } else {
                    "declare the workflow's agents and give their manifests, bind read_only: true, or require approval"
                }),
        );
    }
    if declared.is_none() && literal.is_none() {
        report.push(
            loc.diag(
                Code::UndeclaredDelegate,
                "the delegation target is computed and the workflow declares no 'agents': a host that composes agents statically cannot check it before the run",
            )
            .at("field", "input_bindings.agent")
            .suggest("declare the agents the workflow may delegate to in 'agents'"),
        );
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
        let empty = json!({"capability": "receive", "purpose": "p", "store_as": "r",
                           "input_bindings": {"accept_from": []}});
        assert_eq!(codes(catalog(json!([empty]), &["delegation@1"])), ["S303"]);
        // On a delegate that does not wait, only the missing wait is reported.
        let d = delegate(json!({"accept_from": []}));
        assert_eq!(codes(catalog(json!([d]), &["delegation@1"])), ["S303"]);
        let sync = json!({"capability": "synchronize", "purpose": "p", "store_as": "s",
                          "input_bindings": {"agents": ["a", "b"], "state": {},
                                             "accept_from": ["a"]}});
        assert_eq!(codes(catalog(json!([sync]), &[])), ["V106"]);
    }

    /// Below 1.2, `agents` is ignored (by this executor as by a 1.1
    /// consumer): W616, whatever its shape, never S303; with no version,
    /// W605 alone. From 1.2, its shape is checked (S303).
    #[test]
    fn agents_below_1_2_is_a_version_warning() {
        let with = |version: Option<&str>, agents: Value| {
            let mut w = json!({"goal": "g", "risk": "low", "agents": agents,
                               "steps": [delegate(json!({}))]});
            if let Some(v) = version {
                w["spec_version"] = json!(v);
            }
            codes(json!({"w": w}))
        };
        assert_eq!(with(Some("1.1"), json!(["a"])), ["W616"]);
        assert_eq!(with(Some("1.0"), json!(42)), ["W616"]);
        assert_eq!(with(None, json!(["a"])), ["W605"]);
        assert_eq!(with(Some("1.2"), json!(42)), ["S303", "W621"]);
    }

    /// Below 1.2, `continues` is an input a 1.1 consumer passes on: W616,
    /// and no S303 with `fresh_context: true` (§5.15.3 applies from 1.2).
    #[test]
    fn continues_rules_apply_from_1_2() {
        let step = delegate(json!({"continues": "t0", "fresh_context": true}));
        assert_eq!(
            codes(catalog(json!([step.clone()]), &["delegation@1"])),
            ["W616"]
        );
        let mut w = catalog(json!([step]), &["delegation@1"]);
        w["w"]["spec_version"] = json!("1.2");
        assert_eq!(codes(w), ["S303", "W621"]);
    }
}
