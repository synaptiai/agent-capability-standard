//! Checks for checkpoints, rollbacks, sends and memory (STANDARD v1.2
//! §4.4.1, §4.4.2, §4.5): W624 for a rollback whose `restored` nothing
//! reads, W625 for a `send` approval that hides its destination, W626 for a
//! memory scope that is not one, and the `persist` cases of W614 (`ttl`)
//! and W603 (`timestamp`).

use std::collections::HashSet;

use serde_json::{Map, Value};

use super::extensions::{self, Declared, Positive};
use super::{Report, StepLoc};
use crate::diag::Code;
use crate::refs::{self, Ref, Seg};

/// The memory scopes §4.5 defines.
pub(crate) const MEMORY_SCOPES: [&str; 5] = ["run", "session", "user", "project", "global"];

/// Whether `s` is an `x-` name: `x-`, a lowercase letter or a digit, then at
/// most 61 lowercase letters, digits, `_`, `.` or `-` (§4.4.1).
pub(crate) fn x_name(s: &str) -> bool {
    crate::grounding::vendor(s) && s.len() <= 2 + 1 + 61
}

/// W626 for a literal `scope` of a `persist` or `recall` step that is
/// neither a defined scope nor an `x-` name, and W614 for a `persist` step's
/// literal `ttl` outside the duration grammar or of zero (§4.5). A
/// reference is passed on unchecked: the host refuses what it does not
/// provide (`unsupported_scope`, `unsupported_ttl`).
pub(crate) fn memory_inputs(loc: &StepLoc<'_>, step: &Map<String, Value>, report: &mut Report) {
    if let Some(Value::String(scope)) = step.get("input_bindings").and_then(|b| b.get("scope"))
        && !scope.contains("${")
        && !MEMORY_SCOPES.contains(&scope.as_str())
        && !x_name(scope)
    {
        let mut d = loc
            .diag(
                Code::UnknownMemoryScope,
                format!(
                    "scope '{scope}' is not a memory scope; use one of {} or an x- name the host defines (§4.5)",
                    MEMORY_SCOPES.join(", ")
                ),
            )
            .at("field", "input_bindings.scope");
        if let Some(near) = super::semantics::closest(scope, &MEMORY_SCOPES) {
            d = d.suggest(format!("scope: {near}"));
        }
        report.push(d);
    }
    if loc.capability == "persist" {
        extensions::literal_duration(
            step,
            "ttl",
            Positive::Required,
            "a host cannot end the entry (§4.5)",
            &|d| loc.locate(d),
            report,
        );
    }
}

/// W625 for a `send` step whose `approval.shows` leaves out a destination
/// given by reference (§4.4.2), in a workflow that targets 1.2 or later and
/// declares `approval@1`: each reference in `destination` must be shown, or
/// have a shown reference with the same root whose path is a prefix of its
/// own (`${request}` shows `${request.url}`). A literal destination is part
/// of the workflow and needs no `shows` entry; without `shows` the inputs,
/// which hold the destination, are shown (§5.14).
pub(crate) fn destination_shown(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    declared: &Declared,
    report: &mut Report,
) {
    if !declared.has("approval@1") {
        return;
    }
    let Some(Value::Array(shows)) = step.get("approval").and_then(|a| a.get("shows")) else {
        return;
    };
    let Some(Value::String(destination)) = step
        .get("input_bindings")
        .and_then(|b| b.get("destination"))
    else {
        return;
    };
    let shown: Vec<Ref> = shows
        .iter()
        .filter_map(Value::as_str)
        .flat_map(refs::find_refs)
        .filter_map(|m| m.parsed.ok())
        .collect();
    for r in refs::find_refs(destination)
        .into_iter()
        .filter_map(|m| m.parsed.ok())
    {
        let covered = shown
            .iter()
            .any(|s| s.root == r.root && r.path.starts_with(&s.path));
        if !covered {
            let name = match r.path_text() {
                p if p.is_empty() => r.root.clone(),
                p if p.starts_with('[') => format!("{}{p}", r.root),
                p => format!("{}.{p}", r.root),
            };
            report.push(
                loc.diag(
                    Code::DestinationNotShown,
                    format!(
                        "the send's destination reads ${{{name}}}, which approval.shows leaves out: the approver would not see where the data goes (§4.4.2)"
                    ),
                )
                .at("field", "approval.shows")
                .at("ref", r.raw.as_str())
                .suggest(format!("add \"${{{name}}}\" to approval.shows")),
            );
        }
    }
}

/// The references in a step's `condition`, gate `when`s and failure-mode
/// `when`s: what decides whether the run goes on.
fn deciding_refs(step: &Map<String, Value>) -> Vec<Ref> {
    let mut texts: Vec<&str> = Vec::new();
    if let Some(Value::String(c)) = step.get("condition") {
        texts.push(c);
    }
    for list in ["gates", "failure_modes"] {
        if let Some(Value::Array(items)) = step.get(list) {
            texts.extend(
                items
                    .iter()
                    .filter_map(|i| i.get("when"))
                    .filter_map(Value::as_str),
            );
        }
    }
    texts
        .into_iter()
        .flat_map(refs::find_refs)
        .filter_map(|m| m.parsed.ok())
        .collect()
}

/// W624 for each `rollback` step whose `restored` no `condition`, gate
/// `when` or failure-mode `when` of the workflow reads (§4.4.1), in a
/// workflow that targets 1.2 or later: the step completes whether or not it
/// restored, so a rollback that did not would go unnoticed.
pub(crate) fn unchecked_rollbacks(name: &str, steps: &[Value], report: &mut Report) {
    let checked: HashSet<String> = steps
        .iter()
        .filter_map(Value::as_object)
        .flat_map(deciding_refs)
        .filter(|r| matches!(r.path.first(), Some(Seg::Field(f)) if f == "restored"))
        .map(|r| r.root)
        .collect();
    for (i, step) in steps.iter().enumerate() {
        let Some(step) = step.as_object() else {
            continue;
        };
        if step.get("capability").and_then(Value::as_str) != Some("rollback") {
            continue;
        }
        let store = step.get("store_as").and_then(Value::as_str);
        if store.is_some_and(|s| checked.contains(s)) {
            continue;
        }
        let (message, suggestion) = match store {
            Some(s) => (
                format!(
                    "no condition, gate or failure mode reads ${{{s}.restored}}: the step completes whether or not the rollback restored everything (§4.4.1)"
                ),
                format!(
                    "add an after-gate: when: ${{{s}.restored}} == false, phase: after, action: stop (§12.5, Checked Rollback)"
                ),
            ),
            None => (
                "the rollback stores no output, so nothing can read whether it restored everything; the step completes either way (§4.4.1)".to_string(),
                "give it a store_as and an after-gate on its restored (§12.5, Checked Rollback)".to_string(),
            ),
        };
        let loc = StepLoc {
            workflow: name,
            step: i,
            capability: "rollback",
        };
        report.push(
            loc.diag(Code::UncheckedRollback, message)
                .at("field", "store_as")
                .suggest(suggestion),
        );
    }
}

/// W603 for each reference to a `persist` step's `timestamp`, which §4.5
/// deprecates for `stored_at` (the same instant), in every executable field
/// of every step.
pub(crate) fn persist_timestamp_refs(name: &str, steps: &[Value], report: &mut Report) {
    let stores: HashSet<&str> = steps
        .iter()
        .filter_map(Value::as_object)
        .filter(|s| s.get("capability").and_then(Value::as_str) == Some("persist"))
        .filter_map(|s| s.get("store_as").and_then(Value::as_str))
        .collect();
    if stores.is_empty() {
        return;
    }
    for (i, step) in steps.iter().enumerate() {
        let Some(step) = step.as_object() else {
            continue;
        };
        let capability = step
            .get("capability")
            .and_then(Value::as_str)
            .unwrap_or_default();
        for at in refs::executable_roots(step) {
            if !stores.contains(at.root.as_str()) {
                continue;
            }
            let Ok(r) = refs::parse_ref(&at.text) else {
                continue;
            };
            if !matches!(r.path.first(), Some(Seg::Field(f)) if f == "timestamp") {
                continue;
            }
            let replaced = format!("{}.stored_at{}", r.root, rest_after_first(&r));
            let loc = StepLoc {
                workflow: name,
                step: i,
                capability,
            };
            report.push(
                loc.diag(
                    Code::DeprecatedForm,
                    format!(
                        "${{{}}}: 'timestamp' of persist is deprecated; read 'stored_at', the same instant (§4.5)",
                        r.raw
                    ),
                )
                .at("field", at.field.as_str())
                .at("ref", r.raw.as_str())
                .suggest(format!("${{{replaced}}}")),
            );
        }
    }
}

/// The path of `r` after its first segment, as written.
fn rest_after_first(r: &Ref) -> String {
    r.path.iter().skip(1).map(Seg::to_string).collect()
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    fn catalog(version: &str, extensions: &[&str], steps: Value) -> Value {
        let mut wf = json!({"goal": "g", "risk": "high", "spec_version": version, "steps": steps});
        if !extensions.is_empty() {
            wf["workflow_extensions"] = json!({"requires": extensions});
        }
        json!({"w": wf})
    }

    /// The codes of the checks of this module (and W614).
    fn codes(catalog: Value) -> Vec<&'static str> {
        crate::validate::tests::codes(catalog)
            .into_iter()
            .filter(|c| ["W603", "W614", "W624", "W625", "W626"].contains(c))
            .collect()
    }

    fn rollback_steps(gate: Option<&str>) -> Value {
        let mut rollback = json!({"capability": "rollback", "store_as": "rb",
            "input_bindings": {"checkpoint_id": "${cp.checkpoint_id}"}});
        if let Some(w) = gate {
            rollback["gates"] = json!([{"when": w, "phase": "after", "action": "stop"}]);
        }
        json!([
            {"capability": "checkpoint", "store_as": "cp", "input_bindings": {"scope": "*"}},
            rollback,
            {"capability": "audit", "store_as": "au",
             "input_bindings": {"event": "rolled back", "details": {"r": "${rb.restored}"}}}
        ])
    }

    #[test]
    fn w624_unchecked_rollback_in_1_2_only() {
        assert!(codes(catalog("1.2", &[], rollback_steps(None))).contains(&"W624"));
        assert!(!codes(catalog("1.1", &[], rollback_steps(None))).contains(&"W624"));
        let checked = rollback_steps(Some("${rb.restored} == false"));
        assert!(!codes(catalog("1.2", &[], checked)).contains(&"W624"));
        // Reading another member does not check it.
        let other = rollback_steps(Some("${rb.unrestored} == null"));
        assert!(codes(catalog("1.2", &[], other)).contains(&"W624"));
    }

    fn send_steps(destination: &str, shows: Value) -> Value {
        json!([
            {"capability": "checkpoint", "store_as": "cp", "input_bindings": {"scope": "*"}},
            {"capability": "send", "store_as": "s",
             "input_bindings": {"destination": destination, "payload": "${inputs.body}"},
             "approval": {"approver": {"kind": "human", "role": "ops"}, "shows": shows}}
        ])
    }

    fn with_inputs(mut c: Value) -> Value {
        c["w"]["inputs"] = json!({"url": {"type": "string"}, "body": {"type": "string"},
            "request": {"type": "object"}});
        c
    }

    #[test]
    fn w625_destination_not_shown() {
        let w625 = |destination: &str, shows: Value, version: &str| {
            codes(with_inputs(catalog(
                version,
                &["approval@1"],
                send_steps(destination, shows),
            )))
            .contains(&"W625")
        };
        assert!(w625("${inputs.url}", json!(["${inputs.body}"]), "1.2"));
        assert!(!w625("${inputs.url}", json!(["${inputs.body}"]), "1.1"));
        assert!(!w625("${inputs.url}", json!(["${inputs.url}"]), "1.2"));
        // A shown root covers its members.
        assert!(!w625(
            "${inputs.request.url}",
            json!(["${inputs.request}"]),
            "1.2"
        ));
        assert!(!w625("${inputs}", json!(["${inputs}"]), "1.2"));
        assert!(w625("${inputs}", json!(["${inputs.url}"]), "1.2"));
        // A literal destination needs no entry.
        assert!(!w625(
            "https://hooks.example.com/r",
            json!(["${inputs.body}"]),
            "1.2"
        ));
    }

    #[test]
    fn w626_and_w614_memory_inputs() {
        let steps = |scope: &str, ttl: Option<&str>| {
            let mut b = json!({"data": "${inputs.body}", "key": "k", "scope": scope});
            if let Some(t) = ttl {
                b["ttl"] = json!(t);
            }
            json!([{"capability": "persist", "store_as": "p", "input_bindings": b}])
        };
        let c = |scope: &str, ttl: Option<&str>| {
            codes(with_inputs(catalog("1.2", &[], steps(scope, ttl))))
        };
        assert_eq!(c("team", None), ["W626"]);
        assert!(c("x-team", None).is_empty());
        assert!(c("session", Some("PT1H")).is_empty());
        assert!(c("${inputs.body}", None).is_empty());
        assert_eq!(c("session", Some("five fortnights")), ["W614"]);
        assert_eq!(c("session", Some("0s")), ["W614"]);
        assert!(c("session", Some("${inputs.body}")).is_empty());
    }

    #[test]
    fn memory_scope_below_1_2_is_w616_at_its_step() {
        // §11.5: the persist and recall input `scope` is new in 1.2; a 1.1
        // workflow that binds it gets one W616, located at its first such
        // step with the step's capability and a step-relative field.
        let steps = json!([
            {"capability": "observe", "store_as": "o", "input_bindings": {"target": "t"}},
            {"capability": "recall", "store_as": "r", "input_bindings": {"key": "k", "scope": "user"}},
            {"capability": "persist", "store_as": "p",
             "input_bindings": {"data": "${r}", "key": "k", "scope": "user"}}
        ]);
        let report = crate::validate::validate_catalog(
            &crate::validate::tests::ctx(),
            &catalog("1.1", &[], steps.clone()),
            None,
        );
        let w616: Vec<_> = report
            .diagnostics
            .iter()
            .filter(|d| d.code.as_str() == "W616")
            .collect();
        assert_eq!(w616.len(), 1, "{w616:?}");
        let loc = &w616[0].location;
        assert_eq!(loc["step"], json!(1));
        assert_eq!(loc["capability"], json!("recall"));
        assert_eq!(loc["field"], json!("input_bindings.scope"));
        assert!(
            w616[0]
                .message
                .contains("the persist and recall input 'scope'")
        );
        // From 1.2 it is a base member.
        let report = crate::validate::validate_catalog(
            &crate::validate::tests::ctx(),
            &catalog("1.2", &[], steps),
            None,
        );
        assert!(report.diagnostics.iter().all(|d| d.code.as_str() != "W616"));
    }

    #[test]
    fn w603_persist_timestamp() {
        let steps = |field: &str| {
            json!([
                {"capability": "persist", "store_as": "p",
                 "input_bindings": {"data": "${inputs.body}"}},
                {"capability": "audit", "store_as": "a",
                 "input_bindings": {"event": "stored", "details": {"at": format!("${{p.{field}}}")}}}
            ])
        };
        let c = |field: &str| codes(with_inputs(catalog("1.1", &[], steps(field))));
        assert_eq!(c("timestamp"), ["W603"]);
        assert!(c("stored_at").is_empty());
    }

    #[test]
    fn x_names() {
        assert!(super::x_name("x-team"));
        assert!(!super::x_name("x-"));
        assert!(!super::x_name("x-Team"));
        assert!(!super::x_name(&format!("x-{}", "a".repeat(63))));
        assert!(super::x_name(&format!("x-{}", "a".repeat(62))));
    }
}
