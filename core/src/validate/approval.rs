//! Structured approval (STANDARD v1.1 §5.14, design-114 §13; `approval@1`)
//! and unattended runs that reach an approval (W606).

use serde_json::{Map, Value};

use super::bindings::{Checker, Mode};
use super::extensions::{Declared, count, duration_field, enum_field, s303, s304, string_field};
use super::{Report, Scope, StepLoc, semantics, wait};
use crate::diag::{Code, Diagnostic};
use crate::yaml;

const APPROVAL_KEYS: &[&str] = &[
    "approver",
    "mode",
    "shows",
    "binds_to",
    "recheck",
    "expires",
    "when_unattended",
];
const APPROVER_KEYS: &[&str] = &["kind", "role", "min_approvers", "mandate_ref"];
const RECHECK_KEYS: &[&str] = &["source", "compare", "on_change"];

/// Check a step's `approval` block; `requires_approval` is the step's
/// effective flag.
pub(crate) fn check(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    requires_approval: bool,
    declared: &Declared,
    checker: &Checker<'_>,
    scope: &Scope,
    report: &mut Report,
) {
    let Some(value) = step.get("approval") else {
        return;
    };
    if !declared.require(
        "approval@1",
        "'approval'",
        |d| loc.locate(d).at("field", "approval"),
        report,
    ) {
        return;
    }
    let at = |d: Diagnostic| loc.locate(d);
    let Value::Object(a) = value else {
        report.push(s303(
            &at,
            "approval",
            format!(
                "'approval' must be a mapping, found {}",
                yaml::kind_of(value)
            ),
        ));
        return;
    };
    if !requires_approval {
        report.push(s303(
            &at,
            "approval",
            format!(
                "'approval' applies only to a step that requires approval; '{}' does not (set requires_approval: true to require it)",
                loc.capability
            ),
        ));
    }
    semantics::unknown_fields(a, APPROVAL_KEYS, "approval", &at, report);
    match a.get("approver") {
        None => report.push(s304(
            &at,
            "approval.approver",
            "approval has no 'approver'".into(),
        )),
        Some(v) => approver(v, &at, report),
    }
    enum_field(
        a,
        "mode",
        &["in_session", "out_of_band"],
        "approval",
        &at,
        report,
    );
    enum_field(a, "binds_to", &["digest"], "approval", &at, report);
    match a.get("shows") {
        None => {}
        Some(Value::Array(items)) => {
            for (i, item) in items.iter().enumerate() {
                let field = format!("approval.shows[{i}]");
                if wait::references(item, &field, &at, report) {
                    checker.scan(item, scope, Mode::Existence, &field, report);
                }
            }
        }
        Some(other) => report.push(s303(
            &at,
            "approval.shows",
            format!(
                "approval.shows must be a list of references, found {}",
                yaml::kind_of(other)
            ),
        )),
    }
    if let Some(r) = a.get("recheck") {
        recheck(r, checker, scope, &at, report);
    }
    if let Some(e) = a.get("expires") {
        if duration_field(e, "approval.expires", &at, report).is_some_and(|d| d.is_zero()) {
            report.push(s303(
                &at,
                "approval.expires",
                "approval.expires must be longer than zero".into(),
            ));
        }
    }
    enum_field(
        a,
        "when_unattended",
        &["defer_to_queue", "skip", "fail"],
        "approval",
        &at,
        report,
    );
}

fn approver(value: &Value, at: &dyn Fn(Diagnostic) -> Diagnostic, report: &mut Report) {
    let field = "approval.approver";
    let Value::Object(ap) = value else {
        report.push(s303(
            at,
            field,
            format!("{field} must be a mapping, found {}", yaml::kind_of(value)),
        ));
        return;
    };
    semantics::unknown_fields(ap, APPROVER_KEYS, field, at, report);
    if !ap.contains_key("kind") {
        report.push(s304(
            at,
            &format!("{field}.kind"),
            format!("{field} has no 'kind'"),
        ));
    }
    let kind = enum_field(
        ap,
        "kind",
        &["human", "standing_mandate"],
        field,
        at,
        report,
    );
    string_field(ap, "role", field, at, report);
    if let Some(n) = ap.get("min_approvers") {
        if !count(n).is_some_and(|n| n >= 1) {
            report.push(s303(
                at,
                &format!("{field}.min_approvers"),
                format!("{field}.min_approvers must be an integer of at least 1, found {n}"),
            ));
        }
    }
    string_field(ap, "mandate_ref", field, at, report);
    match (kind, ap.contains_key("mandate_ref")) {
        (Some("standing_mandate"), false) => report.push(s304(
            at,
            &format!("{field}.mandate_ref"),
            format!("{field} is a standing mandate but names no 'mandate_ref'"),
        )),
        (Some("human"), true) => report.push(s303(
            at,
            &format!("{field}.mandate_ref"),
            format!("{field}.mandate_ref applies only to kind 'standing_mandate'"),
        )),
        _ => {}
    }
}

fn recheck(
    value: &Value,
    checker: &Checker<'_>,
    scope: &Scope,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let field = "approval.recheck";
    let Value::Object(r) = value else {
        report.push(s303(
            at,
            field,
            format!("{field} must be a mapping, found {}", yaml::kind_of(value)),
        ));
        return;
    };
    semantics::unknown_fields(r, RECHECK_KEYS, field, at, report);
    match r.get("source") {
        None => report.push(s304(
            at,
            &format!("{field}.source"),
            format!("{field} has no 'source' (the reference to re-read before acting)"),
        )),
        Some(source) => {
            let sfield = format!("{field}.source");
            if wait::references(source, &sfield, at, report) {
                checker.scan(source, scope, Mode::Existence, &sfield, report);
            }
        }
    }
    enum_field(r, "compare", &["version", "digest"], field, at, report);
    enum_field(
        r,
        "on_change",
        &["reask", "replan", "stop"],
        field,
        at,
        report,
    );
}

/// Whether a workflow's triggers include an unattended start: a trigger's
/// `attendance`, else its kind's default (schedule and event: unattended).
pub(crate) fn has_unattended_trigger(wf: &Map<String, Value>, declared: &Declared) -> bool {
    if !declared.has("triggers@1") {
        return false;
    }
    let Some(Value::Array(triggers)) = wf.get("triggers") else {
        return false;
    };
    triggers
        .iter()
        .any(|t| match t.get("attendance").and_then(Value::as_str) {
            Some(a) => a == "unattended",
            None => matches!(
                t.get("kind").and_then(Value::as_str),
                Some("schedule" | "event")
            ),
        })
}

/// W606 for a step that needs approval in a workflow an unattended trigger
/// can start, when it does not say what to do then
/// (`approval.when_unattended`) and has no standing mandate to ask.
pub(crate) fn unattended(loc: &StepLoc<'_>, report: &mut Report) {
    report.push(
        loc.diag(
            Code::UnattendedApproval,
            "this step needs approval, but a trigger starts the workflow unattended and the step has neither approval.when_unattended (defer_to_queue, skip or fail) nor a standing_mandate approver (needs approval@1), so an unattended run fails here with F502",
        )
        .at("field", "approval.when_unattended"),
    );
}

/// W606 for a step whose only plan for an unattended run is a standing
/// mandate, when it may use an item from an always-ask trust class
/// (`identity@1`, §5.17): no mandate covers that, so the run fails here.
pub(crate) fn unattended_always_ask(loc: &StepLoc<'_>, report: &mut Report) {
    report.push(
        loc.diag(
            Code::UnattendedApproval,
            "this step relies on a standing mandate in unattended runs, but it uses data from a step with always_ask_trust_classes; no mandate covers an action on such an item, so an unattended run that brings one fails here with F502 unless approval.when_unattended says otherwise",
        )
        .at("field", "approval.when_unattended"),
    );
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::super::tests::codes;

    fn catalog(steps: Value, requires: &[&str], triggers: Option<Value>) -> Value {
        let mut w = json!({"goal": "g", "risk": "high", "spec_version": "1.1",
                           "workflow_extensions": {"requires": requires},
                           "steps": steps});
        if let Some(t) = triggers {
            w["triggers"] = t;
        }
        json!({ "w": w })
    }

    fn st(cap: &str, store: &str) -> Value {
        json!({"capability": cap, "purpose": "p", "store_as": store})
    }

    /// constrain, checkpoint, then a mutate carrying `approval`.
    fn guarded(approval: Value) -> Value {
        json!([
            {"capability": "plan", "purpose": "p", "store_as": "p",
             "input_bindings": {"goal": "g"}},
            {"capability": "constrain", "purpose": "p", "store_as": "k",
             "input_bindings": {"target": "${p}", "constraints": ["c"]}},
            st("checkpoint", "c"),
            {"capability": "mutate", "purpose": "p", "store_as": "m",
             "input_bindings": {"target": "t", "operation": "${p}"},
             "approval": approval}
        ])
    }

    fn run(approval: Value) -> Vec<&'static str> {
        codes(catalog(guarded(approval), &["approval@1"], None))
    }

    #[test]
    fn a_full_approval() {
        let a = json!({
            "approver": {"kind": "human", "role": "release-manager", "min_approvers": 2},
            "mode": "out_of_band",
            "shows": ["${p.steps}"],
            "binds_to": "digest",
            "recheck": {"source": "${p}", "compare": "digest", "on_change": "reask"},
            "expires": "24h",
            "when_unattended": "defer_to_queue"
        });
        assert_eq!(run(a), Vec::<&str>::new());
        let mandate = json!({"approver": {"kind": "standing_mandate",
                                          "mandate_ref": "mandates/nightly"}});
        assert_eq!(run(mandate), Vec::<&str>::new());
    }

    #[test]
    fn approver() {
        assert_eq!(run(json!({})), ["S304"]);
        assert_eq!(run(json!({"approver": "ops"})), ["S303"]);
        assert_eq!(run(json!({"approver": {}})), ["S304"]);
        assert_eq!(run(json!({"approver": {"kind": "robot"}})), ["S303"]);
        assert_eq!(
            run(json!({"approver": {"kind": "standing_mandate"}})),
            ["S304"]
        );
        assert_eq!(
            run(json!({"approver": {"kind": "human", "mandate_ref": "m"}})),
            ["S303"]
        );
        assert_eq!(
            run(json!({"approver": {"kind": "human", "min_approvers": 0}})),
            ["S303"]
        );
        // JSON Schema's integer accepts 2.0.
        assert_eq!(
            run(json!({"approver": {"kind": "human", "min_approvers": 2.0}})),
            Vec::<&str>::new()
        );
        assert_eq!(
            run(json!({"approver": {"kind": "human", "team": "x"}})),
            ["W604"]
        );
    }

    #[test]
    fn fields() {
        let with = |extra: Value| {
            let mut a = json!({"approver": {"kind": "human"}});
            for (k, v) in extra.as_object().unwrap() {
                a[k] = v.clone();
            }
            run(a)
        };
        assert_eq!(with(json!({"mode": "telepathy"})), ["S303"]);
        assert_eq!(with(json!({"binds_to": "hash"})), ["S303"]);
        assert_eq!(with(json!({"shows": "${p}"})), ["S303"]);
        assert_eq!(with(json!({"shows": ["${nope}"]})), ["B202"]);
        assert_eq!(with(json!({"shows": ["the plan"]})), ["S303"]);
        assert_eq!(with(json!({"shows": [3]})), ["S303"]);
        assert_eq!(with(json!({"recheck": {"source": "plan"}})), ["S303"]);
        assert_eq!(with(json!({"recheck": {"compare": "digest"}})), ["S304"]);
        assert_eq!(with(json!({"recheck": {"source": 3}})), ["S303"]);
        assert_eq!(
            with(json!({"recheck": {"source": "${p}", "on_change": "ignore"}})),
            ["S303"]
        );
        assert_eq!(with(json!({"recheck": "${p}"})), ["S303"]);
        assert_eq!(with(json!({"expires": "0s"})), ["S303"]);
        assert_eq!(with(json!({"expires": "a day"})), ["S303"]);
        assert_eq!(with(json!({"when_unattended": "hope"})), ["S303"]);
        assert_eq!(with(json!({"color": "red"})), ["W604"]);
        assert_eq!(run(json!("yes")), ["S303"]);
    }

    #[test]
    fn only_where_approval_is_required() {
        let mut steps = guarded(json!({"approver": {"kind": "human"}}));
        steps[0]["approval"] = json!({"approver": {"kind": "human"}});
        assert_eq!(
            codes(catalog(steps.clone(), &["approval@1"], None)),
            ["S303"]
        );
        // Raising requires_approval makes it apply.
        steps[0]["requires_approval"] = json!(true);
        assert_eq!(
            codes(catalog(steps, &["approval@1"], None)),
            Vec::<&str>::new()
        );
        let undeclared = codes(catalog(
            guarded(json!({"approver": {"kind": "human"}})),
            &[],
            None,
        ));
        assert_eq!(undeclared, ["V106"]);
    }

    #[test]
    fn always_ask_items_defeat_a_mandate_unattended() {
        let mandate = json!({"kind": "standing_mandate", "mandate_ref": "m"});
        let run = |code: &str, approval: Value| {
            let steps = json!([
                {"capability": "receive", "purpose": "p", "store_as": "r",
                 "input_bindings": {"always_ask_trust_classes": ["external"]}},
                {"capability": "generate", "purpose": "p", "store_as": "g",
                 "input_bindings": {"specification": "${r.data: array<object>}"}},
                {"capability": "execute", "purpose": "p", "store_as": "x",
                 "input_bindings": {"code": code}, "approval": approval}
            ]);
            codes(catalog(
                steps,
                &["triggers@1", "approval@1", "identity@1"],
                Some(json!([{"kind": "schedule", "schedule": {"every": "1h"}}])),
            ))
            .into_iter()
            .filter(|c| *c != "W601") // execute without a constrain before it
            .collect::<Vec<_>>()
        };
        // Through the generate step, the action uses the received item.
        assert_eq!(
            run("${g.content: string}", json!({"approver": mandate})),
            ["W606"]
        );
        // A plan for unattended runs, or no use of the item, is fine.
        assert!(
            run(
                "${g.content: string}",
                json!({"approver": mandate, "when_unattended": "defer_to_queue"})
            )
            .is_empty()
        );
        assert!(run("rotate-logs", json!({"approver": mandate})).is_empty());
    }

    #[test]
    fn unattended_runs_need_a_plan() {
        let run = |triggers: Value, approval: Option<Value>| {
            let mut steps = guarded(json!(null));
            match approval {
                Some(a) => steps[3]["approval"] = a,
                None => {
                    steps[3].as_object_mut().unwrap().remove("approval");
                }
            }
            codes(catalog(
                steps,
                &["triggers@1", "approval@1"],
                Some(triggers),
            ))
        };
        let schedule = json!([{"kind": "schedule", "schedule": {"every": "1h"}}]);
        assert_eq!(run(schedule.clone(), None), ["W606"]);
        assert_eq!(
            run(
                schedule.clone(),
                Some(json!({"approver": {"kind": "human"}}))
            ),
            ["W606"]
        );
        assert_eq!(
            run(
                schedule.clone(),
                Some(json!({"approver": {"kind": "human"}, "when_unattended": "skip"}))
            ),
            Vec::<&str>::new()
        );
        // A standing mandate is asked even in an unattended run.
        assert_eq!(
            run(
                schedule,
                Some(json!({"approver": {"kind": "standing_mandate", "mandate_ref": "m"}}))
            ),
            Vec::<&str>::new()
        );
        // Attended starts, and an explicit attended schedule, are fine.
        assert_eq!(run(json!([{"kind": "manual"}]), None), Vec::<&str>::new());
        assert_eq!(
            run(
                json!([{"kind": "schedule", "schedule": {"every": "1h"},
                        "attendance": "attended"}]),
                None
            ),
            Vec::<&str>::new()
        );
        assert_eq!(
            run(
                json!([{"kind": "manual", "attendance": "unattended"}]),
                None
            ),
            ["W606"]
        );
        // A malformed approval block is reported once, not again as W606.
        assert_eq!(
            run(
                json!([{"kind": "manual", "attendance": "unattended"}]),
                Some(json!("yes"))
            ),
            ["S303"]
        );
    }
}
