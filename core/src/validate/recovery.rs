//! Failure modes, recovery loops, escalation and handler steps (STANDARD
//! v1.1 §5.7, §5.11, §5.12; design-114 §9).
//!
//! A pre-pass over the steps resolves every recovery target before the
//! main loop runs, because a handler step is checked in the scope of the
//! earliest step that escalates to it, wherever it appears in the list.

use std::collections::{HashMap, HashSet};

use serde_json::{Map, Value, json};

use super::extensions::{Declared, count};
use super::{Report, Scope, StepLoc};
use crate::diag::Code;
use crate::yaml;

/// Failure-mode actions (§5.7).
const ACTIONS: &[&str] = &[
    "stop",
    "rollback",
    "request_more_context",
    "pause_and_checkpoint",
    "escalate",
];

/// Runtime codes a failure mode may fire on (§5.7).
const ON_ERROR: &[&str] = &["R401", "R402", "R403", "R405", "F502"];

/// The root under which injected recovery context is read.
pub(crate) const RECOVERY_ROOT: &str = "_recovery";

/// What the main loop needs to know about recovery.
#[derive(Default)]
pub(crate) struct Plan {
    /// Step indices in checking order: list order, with each targeted
    /// handler moved to right after the earliest step that escalates to it.
    pub order: Vec<usize>,
    /// Handler steps: `invoke` steps with `handler: true`, in a workflow
    /// that declares recovery@1.
    pub handlers: HashSet<usize>,
    /// Handler → the earliest step that escalates to it.
    pub targeted_by: HashMap<usize, usize>,
    /// (loop target, injected keys), sorted by target: from the target
    /// onward the keys are readable as `${_recovery.<key>}`.
    pub injections: Vec<(usize, Vec<String>)>,
}

/// Brings injected recovery context into scope as the main loop reaches
/// each loop target, in O(keys) overall.
pub(crate) struct Injected<'p> {
    injections: &'p [(usize, Vec<String>)],
    next: usize,
}

impl<'p> Injected<'p> {
    pub(crate) fn new(plan: &'p Plan) -> Injected<'p> {
        Injected {
            injections: &plan.injections,
            next: 0,
        }
    }

    /// Make `_recovery` readable as seen at step `index` (steps are reached
    /// in list order). It is absent before the first loop, so maybe-absent.
    pub(crate) fn advance(&mut self, index: usize, scope: &mut Scope) {
        while let Some((target, keys)) = self.injections.get(self.next) {
            if *target > index {
                break;
            }
            self.next += 1;
            let schema = scope
                .inputs
                .entry(RECOVERY_ROOT.to_string())
                .or_insert_with(|| json!({"type": "object", "properties": {}}));
            scope.maybe_absent.insert(RECOVERY_ROOT.to_string());
            if let Some(Value::Object(properties)) = schema.get_mut("properties") {
                for key in keys {
                    properties.insert(key.clone(), json!({"type": "any"}));
                }
            }
        }
    }
}

/// Puts the scope into a handler's view and back without copying it. A
/// handler is checked right after its earliest targeter, in that step's
/// scope, except that the targeter (which may have failed) and the steps
/// running concurrently with it may not have produced their output; and
/// the handler's own output is never visible to other steps.
pub(crate) struct HandlerView {
    absent: Vec<String>,
    store: Option<(String, Option<Value>, bool)>,
}

impl HandlerView {
    pub(crate) fn enter<'s>(
        scope: &mut Scope,
        maybe_absent: impl Iterator<Item = &'s str>,
        own_store: Option<&str>,
    ) -> HandlerView {
        let store = own_store.map(|s| {
            (
                s.to_string(),
                scope.stores.get(s).cloned(),
                scope.maybe_absent.contains(s),
            )
        });
        let absent = maybe_absent
            .filter(|s| scope.maybe_absent.insert((*s).to_string()))
            .map(str::to_string)
            .collect();
        HandlerView { absent, store }
    }

    pub(crate) fn leave(self, scope: &mut Scope) {
        for s in &self.absent {
            scope.maybe_absent.remove(s);
        }
        if let Some((name, prior, was_absent)) = self.store {
            match prior {
                // Re-inserting an existing key keeps its position.
                Some(schema) => {
                    scope.stores.insert(name.clone(), schema);
                }
                // The handler's store was appended last.
                None => {
                    scope.stores.swap_remove(&name);
                }
            }
            if was_absent {
                scope.maybe_absent.insert(name);
            } else {
                scope.maybe_absent.remove(&name);
            }
        }
    }
}

/// How a `goto_step` names its target.
enum Target {
    Store(usize),
    /// A capability id held by exactly one step (legacy, W603).
    Capability(usize),
}

impl Target {
    fn index(&self) -> usize {
        match self {
            Target::Store(i) | Target::Capability(i) => *i,
        }
    }
}

struct Steps<'a> {
    by_store: HashMap<&'a str, usize>,
    by_capability: HashMap<&'a str, Vec<usize>>,
    handlers: HashSet<usize>,
}

impl<'a> Steps<'a> {
    /// A `handler: true` flag makes a handler only where it is valid: on
    /// an `invoke` step, with recovery@1 declared. Anywhere else it is
    /// reported and the step stays in the normal flow.
    fn new(steps: &'a [Value], handlers_declared: bool) -> Steps<'a> {
        let mut s = Steps {
            by_store: HashMap::new(),
            by_capability: HashMap::new(),
            handlers: HashSet::new(),
        };
        for (i, step) in steps.iter().enumerate() {
            let Some(step) = step.as_object() else {
                continue;
            };
            if let Some(store) = step.get("store_as").and_then(Value::as_str) {
                s.by_store.entry(store).or_insert(i);
            }
            if handlers_declared
                && step.get("handler") == Some(&Value::Bool(true))
                && step.get("capability").and_then(Value::as_str) == Some("invoke")
            {
                s.handlers.insert(i);
            } else if let Some(cap) = step.get("capability").and_then(Value::as_str) {
                s.by_capability.entry(cap).or_default().push(i);
            }
        }
        s
    }

    /// Resolve a `goto_step`: a `store_as`, else (legacy) a capability id
    /// held by exactly one non-handler step.
    fn resolve(&self, name: &str) -> Result<Target, String> {
        if let Some(&i) = self.by_store.get(name) {
            return Ok(Target::Store(i));
        }
        match self.by_capability.get(name).map(Vec::as_slice) {
            Some([i]) => Ok(Target::Capability(*i)),
            Some(many) => Err(format!(
                "'{name}' is no step's store_as, and {} steps use that capability; name the target's store_as",
                many.len()
            )),
            None => Err(format!("'{name}' is no step's store_as")),
        }
    }
}

/// Validate every step's failure modes and handler flag, and work out the
/// checking order, handler scopes and injected recovery context.
pub(crate) fn plan(
    workflow: &str,
    steps: &[Value],
    declared: &Declared,
    report: &mut Report,
) -> Plan {
    let index = Steps::new(steps, declared.has("recovery@1"));
    let mut plan = Plan {
        handlers: index.handlers.clone(),
        ..Plan::default()
    };
    for (i, step) in steps.iter().enumerate() {
        let Some(step) = step.as_object() else {
            continue;
        };
        let capability = step
            .get("capability")
            .and_then(Value::as_str)
            .unwrap_or("?");
        let loc = StepLoc {
            workflow,
            step: i,
            capability,
        };
        handler_flag(&loc, step, declared, report);
        let Some(Value::Array(modes)) = step.get("failure_modes") else {
            continue;
        };
        for (f, fm) in modes.iter().enumerate() {
            let Some(fm) = fm.as_object() else {
                continue; // reported by the step field checks
            };
            failure_mode(&loc, i, f, fm, &index, declared, &mut plan, report);
        }
    }
    for &h in &plan.handlers {
        if !plan.targeted_by.contains_key(&h) {
            let capability = steps[h]
                .get("capability")
                .and_then(Value::as_str)
                .unwrap_or("?");
            let loc = StepLoc {
                workflow,
                step: h,
                capability,
            };
            report.push(
                loc.diag(
                    Code::UnreachableHandler,
                    "handler step is the target of no escalation, so it never runs",
                )
                .at("field", "handler"),
            );
        }
    }
    plan.injections.sort_by_key(|(target, _)| *target);
    // Checking order: each targeted handler right after its earliest
    // targeter; untargeted handlers stay where they are. Only normal steps
    // escalate (a handler's own failure modes cannot), so every targeter is
    // placed and so is every handler.
    let mut after: HashMap<usize, Vec<usize>> = HashMap::new();
    for (&h, &t) in &plan.targeted_by {
        after.entry(t).or_default().push(h);
    }
    for list in after.values_mut() {
        list.sort_unstable();
    }
    for i in 0..steps.len() {
        if plan.targeted_by.contains_key(&i) {
            continue;
        }
        plan.order.push(i);
        if let Some(hs) = after.get(&i) {
            plan.order.extend(hs);
        }
    }
    debug_assert_eq!(plan.order.len(), steps.len());
    plan
}

fn handler_flag(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    declared: &Declared,
    report: &mut Report,
) {
    let Some(flag) = step.get("handler") else {
        return;
    };
    if !declared.require(
        "recovery@1",
        "'handler'",
        |d| loc.locate(d).at("field", "handler"),
        report,
    ) {
        return;
    }
    match flag {
        Value::Bool(true) if loc.capability != "invoke" => report.push(
            loc.diag(
                Code::SchemaValidationFailed,
                format!(
                    "a handler step must invoke a workflow (capability 'invoke'), not '{}'",
                    loc.capability
                ),
            )
            .at("field", "handler"),
        ),
        Value::Bool(_) => {}
        other => report.push(
            loc.diag(
                Code::SchemaValidationFailed,
                format!(
                    "'handler' must be a boolean, found {}",
                    yaml::kind_of(other)
                ),
            )
            .at("field", "handler"),
        ),
    }
}

#[allow(clippy::too_many_arguments)]
fn failure_mode(
    loc: &StepLoc<'_>,
    i: usize,
    f: usize,
    fm: &Map<String, Value>,
    index: &Steps<'_>,
    declared: &Declared,
    plan: &mut Plan,
    report: &mut Report,
) {
    let field = format!("failure_modes[{f}]");
    let s303 = |msg: String, at: &str| {
        loc.diag(Code::SchemaValidationFailed, msg)
            .at("field", at.to_string())
    };
    let action = fm.get("action").and_then(Value::as_str);
    if let Some(a) = action {
        if !ACTIONS.contains(&a) {
            report.push(s303(
                format!("{field}.action '{a}' is not one of {}", ACTIONS.join(", ")),
                &format!("{field}.action"),
            ));
        }
    }
    // on_error is base 1.1, checked whether or not escalation is declared.
    if let Some(on_error) = fm.get("on_error") {
        on_error_codes(on_error, &format!("{field}.on_error"), loc, report);
    }
    let escalate = action == Some("escalate");
    if escalate
        && !declared.require(
            "recovery@1",
            "'action: escalate'",
            |d| loc.locate(d).at("field", format!("{field}.action")),
            report,
        )
    {
        return;
    }
    let triggered = fm.contains_key("on_error") || fm.contains_key("when");
    let recovery = fm.get("recovery");
    let rfield = format!("{field}.recovery");
    match recovery {
        None | Some(Value::String(_) | Value::Object(_)) => {}
        Some(other) => {
            report.push(s303(
                format!(
                    "{rfield} must be a description or a mapping, found {}",
                    yaml::kind_of(other)
                ),
                &rfield,
            ));
            return;
        }
    }
    let Some(Value::Object(rec)) = recovery else {
        if escalate {
            report.push(
                loc.diag(
                    Code::MissingRequiredField,
                    format!(
                        "{field} escalates but has no recovery.goto_step naming a handler step"
                    ),
                )
                .at("field", format!("{field}.recovery")),
            );
        }
        return;
    };
    // Running a handler ends the run (§5.11): its failures stop it, and
    // cannot loop back into the flow or escalate again.
    if index.handlers.contains(&i)
        && (rec.contains_key("goto_step") || rec.contains_key("on_exhausted"))
    {
        report.push(
            loc.diag(
                Code::UnresolvedTarget,
                format!(
                    "{rfield}: a handler step ends the run, so its failure modes cannot loop or escalate"
                ),
            )
            .at("field", rfield.clone()),
        );
        return;
    }
    if !triggered {
        report.push(
            loc.diag(
                Code::UntriggeredFailureMode,
                format!(
                    "{field} has a structured recovery but neither 'on_error' nor 'when', so it never fires"
                ),
            )
            .at("field", field.clone()),
        );
    }
    if escalate {
        // An escalation runs its handler once and ends the run; the loop
        // fields have no meaning there.
        for key in ["max_loops", "on_exhausted", "inject_context"] {
            if rec.contains_key(key) {
                report.push(s303(
                    format!(
                        "{rfield}.{key} applies to a recovery loop, not to an escalation (the handler can bind what it needs from the failed step)"
                    ),
                    &format!("{rfield}.{key}"),
                ));
            }
        }
    }
    if let Some(inject) = rec.get("inject_context") {
        if !inject.is_object() {
            report.push(s303(
                format!(
                    "{rfield}.inject_context must map keys to references, found {}",
                    yaml::kind_of(inject)
                ),
                &format!("{rfield}.inject_context"),
            ));
        }
    }
    if let Some(max) = rec.get("max_loops").filter(|_| !escalate) {
        if !count(max).is_some_and(|n| n >= 1) {
            report.push(s303(
                format!("{rfield}.max_loops must be an integer of at least 1, found {max}"),
                &format!("{rfield}.max_loops"),
            ));
        }
    }
    let goto = rec.get("goto_step");
    if goto.is_none() {
        let missing = if escalate {
            Some("an escalation needs recovery.goto_step naming a handler step")
        } else if rec.contains_key("max_loops") || rec.contains_key("on_exhausted") {
            Some("max_loops and on_exhausted need a recovery.goto_step loop")
        } else {
            None
        };
        if let Some(why) = missing {
            report.push(
                loc.diag(Code::MissingRequiredField, format!("{rfield}: {why}"))
                    .at("field", format!("{rfield}.goto_step")),
            );
        }
    }
    if let Some(goto) = goto {
        let gfield = format!("{rfield}.goto_step");
        if let Some(target) = resolve(goto, &gfield, loc, index, report) {
            let t = target.index();
            if escalate {
                expect_handler(t, &gfield, loc, index, i, plan, report);
            } else if index.handlers.contains(&t) {
                report.push(
                    loc.diag(
                        Code::UnresolvedTarget,
                        format!(
                            "{gfield} names a handler step; a recovery loop goes back to a step in the normal flow (use action: escalate to run a handler)"
                        ),
                    )
                    .at("field", gfield.clone()),
                );
            } else if t > i {
                report.push(
                    loc.diag(
                        Code::UnresolvedTarget,
                        format!("{gfield} names step {t}, after this one; a recovery loop goes back to this step or an earlier one"),
                    )
                    .at("field", gfield.clone()),
                );
            } else {
                let keys = rec
                    .get("inject_context")
                    .and_then(Value::as_object)
                    .map(|m| m.keys().cloned().collect())
                    .unwrap_or_default();
                plan.injections.push((t, keys));
            }
        }
    }
    if let Some(ex) = rec.get("on_exhausted").filter(|_| !escalate) {
        let efield = format!("{rfield}.on_exhausted");
        if !declared.require(
            "recovery@1",
            "'on_exhausted'",
            |d| loc.locate(d).at("field", efield.clone()),
            report,
        ) {
            return;
        }
        let Value::Object(ex) = ex else {
            report.push(s303(
                format!("{efield} must be a mapping, found {}", yaml::kind_of(ex)),
                &efield,
            ));
            return;
        };
        super::semantics::unknown_fields(ex, &["goto_step"], &efield, &|d| loc.locate(d), report);
        match ex.get("goto_step") {
            None => report.push(
                loc.diag(
                    Code::MissingRequiredField,
                    format!("{efield} needs goto_step naming a handler step"),
                )
                .at("field", format!("{efield}.goto_step")),
            ),
            Some(goto) => {
                let gfield = format!("{efield}.goto_step");
                if let Some(target) = resolve(goto, &gfield, loc, index, report) {
                    expect_handler(target.index(), &gfield, loc, index, i, plan, report);
                }
            }
        }
    }
}

fn on_error_codes(value: &Value, field: &str, loc: &StepLoc<'_>, report: &mut Report) {
    let codes: Vec<&Value> = match value {
        Value::Array(a) if !a.is_empty() => a.iter().collect(),
        Value::Array(_) => Vec::new(),
        other => vec![other],
    };
    if codes.is_empty() {
        report.push(
            loc.diag(
                Code::SchemaValidationFailed,
                format!("{field} must name at least one code"),
            )
            .at("field", field.to_string()),
        );
    }
    for code in codes {
        if !code.as_str().is_some_and(|c| ON_ERROR.contains(&c)) {
            report.push(
                loc.diag(
                    Code::SchemaValidationFailed,
                    format!(
                        "{field}: {code} is not a code a failure mode can fire on ({})",
                        ON_ERROR.join(", ")
                    ),
                )
                .at("field", field.to_string()),
            );
        }
    }
}

fn resolve(
    goto: &Value,
    field: &str,
    loc: &StepLoc<'_>,
    index: &Steps<'_>,
    report: &mut Report,
) -> Option<Target> {
    let Value::String(name) = goto else {
        report.push(
            loc.diag(
                Code::SchemaValidationFailed,
                format!("{field} must be a string, found {}", yaml::kind_of(goto)),
            )
            .at("field", field.to_string()),
        );
        return None;
    };
    match index.resolve(name) {
        Ok(target) => {
            if let Target::Capability(t) = target {
                report.push(
                    loc.diag(
                        Code::DeprecatedForm,
                        format!(
                            "{field} '{name}' names a capability; name the step's store_as instead (step {t})"
                        ),
                    )
                    .at("field", field.to_string()),
                );
            }
            Some(target)
        }
        Err(why) => {
            report.push(
                loc.diag(Code::UnresolvedTarget, format!("{field}: {why}"))
                    .at("field", field.to_string()),
            );
            None
        }
    }
}

fn expect_handler(
    target: usize,
    field: &str,
    loc: &StepLoc<'_>,
    index: &Steps<'_>,
    from: usize,
    plan: &mut Plan,
    report: &mut Report,
) {
    if index.handlers.contains(&target) {
        let earliest = plan.targeted_by.entry(target).or_insert(from);
        *earliest = (*earliest).min(from);
    } else {
        report.push(
            loc.diag(
                Code::UnresolvedTarget,
                format!(
                    "{field} names step {target}, which is not a handler step (an invoke step with handler: true)"
                ),
            )
            .at("field", field.to_string()),
        );
    }
}

/// `_recovery` is reserved (§5.3, Appendix B): S303 for a store_as or input
/// that takes it.
pub(crate) fn reserved_name(name: &str) -> bool {
    name == RECOVERY_ROOT
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::super::tests::codes;

    /// A catalog with workflow `w` (extensions declared) and an invocable
    /// workflow `h` for handler steps to run.
    fn catalog(steps: Value, requires: &[&str]) -> Value {
        json!({
            "w": {"goal": "g", "risk": "low", "spec_version": "1.1",
                  "workflow_extensions": {"requires": requires},
                  "steps": steps},
            "h": {"goal": "handle", "risk": "low", "spec_version": "1.1",
                  "steps": [{"capability": "observe", "purpose": "p", "store_as": "o"}]}
        })
    }

    fn st(cap: &str, store: &str) -> Value {
        json!({"capability": cap, "purpose": "p", "store_as": store})
    }

    fn with_fm(mut step: Value, fm: Value) -> Value {
        step["failure_modes"] = json!([fm]);
        step
    }

    fn handler(store: &str) -> Value {
        json!({"capability": "invoke", "purpose": "escalate", "store_as": store,
               "handler": true, "workflow_id": "h"})
    }

    fn loop_fm(goto: &str) -> Value {
        json!({"condition": "c", "action": "rollback", "when": "${v.passed} == false",
               "recovery": {"goto_step": goto, "max_loops": 2,
                            "inject_context": {"why": "${v.violations}"}}})
    }

    #[test]
    fn loops_resolve_by_store_as() {
        let ok = catalog(
            json!([st("plan", "p"), with_fm(st("verify", "v"), loop_fm("p"))]),
            &[],
        );
        assert!(codes(ok).is_empty());
        let legacy = catalog(
            json!([st("plan", "p"), with_fm(st("verify", "v"), loop_fm("plan"))]),
            &[],
        );
        assert_eq!(codes(legacy), ["W603"]);
        let unknown = catalog(
            json!([st("plan", "p"), with_fm(st("verify", "v"), loop_fm("nope"))]),
            &[],
        );
        assert_eq!(codes(unknown), ["V107"]);
        let forward = catalog(
            json!([with_fm(st("verify", "v"), loop_fm("p")), st("plan", "p")]),
            &[],
        );
        assert_eq!(codes(forward), ["V107"]);
        let ambiguous = catalog(
            json!([
                st("plan", "p1"),
                st("plan", "p2"),
                with_fm(st("verify", "v"), loop_fm("plan"))
            ]),
            &[],
        );
        assert_eq!(codes(ambiguous), ["V107"]);
    }

    #[test]
    fn failure_mode_fields() {
        let fm = |extra: Value| {
            let mut f = json!({"condition": "c", "action": "stop"});
            for (k, v) in extra.as_object().unwrap() {
                f[k] = v.clone();
            }
            codes(catalog(
                json!([st("plan", "p"), with_fm(st("verify", "v"), f)]),
                &[],
            ))
        };
        assert!(fm(json!({"on_error": "R401"})).is_empty());
        assert!(fm(json!({"on_error": ["R402", "F502"]})).is_empty());
        assert_eq!(fm(json!({"on_error": "R999"})), ["S303"]);
        assert_eq!(fm(json!({"on_error": []})), ["S303"]);
        assert_eq!(fm(json!({"action": "panic"})), ["S303"]);
        // A structured recovery that can never fire.
        assert_eq!(fm(json!({"recovery": {"goto_step": "p"}})), ["W609"]);
        assert_eq!(
            fm(json!({"when": "true", "recovery": {"goto_step": "p", "max_loops": 0}})),
            ["S303"]
        );
        assert_eq!(
            fm(json!({"when": "true", "recovery": {"max_loops": 2}})),
            ["S304"]
        );
        // Prose recovery is documentation; no trigger needed.
        assert!(fm(json!({"recovery": "Retry later."})).is_empty());
    }

    #[test]
    fn escalation_to_handlers() {
        let esc = |goto: &str| {
            json!({"condition": "c", "action": "escalate", "on_error": "R402",
                   "recovery": {"goto_step": goto}})
        };
        let ok = catalog(
            json!([with_fm(st("observe", "o"), esc("hand")), handler("hand")]),
            &["recovery@1"],
        );
        let c = codes(ok);
        assert!(c.is_empty(), "{c:?}");
        let undeclared = catalog(
            json!([with_fm(st("observe", "o"), esc("hand")), handler("hand")]),
            &[],
        );
        assert_eq!(codes(undeclared), ["V106", "V106"]);
        let not_handler = catalog(
            json!([
                st("plan", "p"),
                with_fm(st("observe", "o"), esc("p")),
                handler("hand")
            ]),
            &["recovery@1"],
        );
        assert_eq!(codes(not_handler), ["V107", "W613"]);
        let no_goto = catalog(
            json!([with_fm(
                st("observe", "o"),
                json!({"condition": "c", "action": "escalate", "on_error": "R402"})
            )]),
            &["recovery@1"],
        );
        assert_eq!(codes(no_goto), ["S304"]);
    }

    #[test]
    fn on_exhausted() {
        let fm = |ex: Value| {
            json!({"condition": "c", "action": "rollback", "when": "${v.passed} == false",
                   "recovery": {"goto_step": "p", "max_loops": 2, "on_exhausted": ex}})
        };
        let run = |ex: Value| {
            codes(catalog(
                json!([
                    st("plan", "p"),
                    with_fm(st("verify", "v"), fm(ex)),
                    handler("hand")
                ]),
                &["recovery@1"],
            ))
        };
        assert!(run(json!({"goto_step": "hand"})).is_empty());
        assert_eq!(run(json!({"goto_step": "p"})), ["V107", "W613"]);
        assert_eq!(run(json!({})), ["S304", "W613"]);
        assert_eq!(run(json!("hand")), ["S303", "W613"]);
    }

    #[test]
    fn handler_flag() {
        let run = |h: Value| codes(catalog(json!([st("observe", "o"), h]), &["recovery@1"]));
        assert_eq!(run(handler("hand")), ["W613"]);
        // A handler flag on another capability is reported, and the step
        // stays in the normal flow.
        let mut bad = st("observe", "x");
        bad["handler"] = json!(true);
        assert_eq!(run(bad), ["S303"]);
        let mut not_bool = handler("hand");
        not_bool["handler"] = json!("yes");
        assert_eq!(run(not_bool), ["S303"]);
        let undeclared = codes(catalog(json!([st("observe", "o"), handler("hand")]), &[]));
        assert_eq!(undeclared, ["V106"]);
    }

    #[test]
    fn handler_scope_and_edges() {
        let esc = json!({"condition": "c", "action": "escalate", "on_error": "R402",
                         "recovery": {"goto_step": "hand"}});
        // The handler (listed first) sees stores up to its targeter, which
        // may have failed: the targeter's own output may be absent.
        let mut h = handler("hand");
        h["input_bindings"] = json!({"input": {"seen": "${o}", "later": "${later}"}});
        let c = codes(catalog(
            json!([h, with_fm(st("observe", "o"), esc), st("detect", "later")]),
            &["recovery@1"],
        ));
        assert_eq!(c, ["B202"]);
        // Handlers are outside the edge sequence: an early handler invoke is
        // not ordered against anything, and no later step sees its output.
        let mut reader = st("verify", "v");
        reader["input_bindings"] = json!({"target": "${hand}", "conditions": ["c"]});
        let esc2 = json!({"condition": "c", "action": "escalate", "on_error": "R402",
                          "recovery": {"goto_step": "hand"}});
        let c = codes(catalog(
            json!([with_fm(st("observe", "o"), esc2), handler("hand"), reader]),
            &["recovery@1"],
        ));
        assert_eq!(c, ["B202"]);
    }

    #[test]
    fn injected_context_scope() {
        let mut before = st("observe", "o");
        before["input_bindings"] = json!({"target": "${_recovery.why}"});
        let mut after = st("plan", "p");
        // Injected values are untyped: annotate them where a type matters.
        after["input_bindings"] = json!({"goal": "${_recovery.why: string}"});
        let c = codes(catalog(
            json!([before, after, with_fm(st("verify", "v"), loop_fm("p"))]),
            &[],
        ));
        assert_eq!(
            c,
            ["B202"],
            "only steps from the loop target on see _recovery"
        );
        let mut cond = st("plan", "p");
        cond["condition"] = json!("${_recovery.why} != null");
        assert!(
            codes(catalog(
                json!([cond, with_fm(st("verify", "v"), loop_fm("p"))]),
                &[]
            ))
            .is_empty()
        );
    }

    #[test]
    fn reserved_names() {
        assert_eq!(
            codes(catalog(json!([st("observe", "_recovery")]), &[])),
            ["S303"]
        );
        let mut c = catalog(json!([st("observe", "o")]), &[]);
        c["w"]["inputs"] = json!({"_recovery": {"type": "object"}});
        assert_eq!(codes(c), ["S303"]);
    }

    fn esc(goto: &str) -> Value {
        json!({"condition": "c", "action": "escalate", "on_error": "R402",
               "recovery": {"goto_step": goto}})
    }

    #[test]
    fn handlers_cannot_loop_or_escalate() {
        // A handler ends the run. Escalating from one, to itself or to
        // another handler, is V107; the handler is still checked in full.
        let mut h = with_fm(handler("hand"), esc("hand"));
        h["bogus"] = json!(1);
        h["input_bindings"] = json!({"input": "${nope}"});
        let c = codes(catalog(json!([st("observe", "o"), h]), &["recovery@1"]));
        assert_eq!(c, ["V107", "W613", "W604", "B202"]);
        let chain = catalog(
            json!([
                with_fm(st("observe", "o"), esc("h1")),
                with_fm(handler("h1"), esc("h2")),
                handler("h2")
            ]),
            &["recovery@1"],
        );
        assert_eq!(codes(chain), ["V107", "W613"]);
        let looping = catalog(
            json!([
                st("plan", "p"),
                with_fm(st("observe", "o"), esc("hand")),
                with_fm(
                    handler("hand"),
                    json!({"condition": "c", "action": "rollback", "when": "true",
                           "recovery": {"goto_step": "p"}})
                )
            ]),
            &["recovery@1"],
        );
        assert_eq!(codes(looping), ["V107"]);
        // A handler that invokes its own workflow closes an invoke cycle.
        let mut self_invoking = handler("hand");
        self_invoking["workflow_id"] = json!("w");
        let c = codes(catalog(
            json!([with_fm(st("observe", "o"), esc("hand")), self_invoking]),
            &["recovery@1"],
        ));
        assert_eq!(c, ["V105"]);
    }

    #[test]
    fn escalations_take_no_loop_fields() {
        let run = |extra: Value| {
            let mut fm = esc("hand");
            for (k, v) in extra.as_object().unwrap() {
                fm["recovery"][k] = v.clone();
            }
            codes(catalog(
                json!([with_fm(st("observe", "o"), fm), handler("hand")]),
                &["recovery@1"],
            ))
        };
        assert_eq!(run(json!({"max_loops": 3})), ["S303"]);
        assert_eq!(
            run(json!({"on_exhausted": {"goto_step": "hand"}})),
            ["S303"]
        );
        assert_eq!(run(json!({"inject_context": {"k": "${o}"}})), ["S303"]);
    }

    #[test]
    fn recovery_shapes() {
        let run = |rec: Value| {
            let fm = json!({"condition": "c", "action": "rollback",
                            "when": "${v.passed} == false", "recovery": rec});
            codes(catalog(
                json!([st("plan", "p"), with_fm(st("verify", "v"), fm)]),
                &[],
            ))
        };
        assert_eq!(run(json!([1, 2])), ["S303"]);
        assert_eq!(run(json!(5)), ["S303"]);
        assert_eq!(
            run(json!({"goto_step": "p", "inject_context": "${v.violations}"})),
            ["S303"]
        );
        // JSON Schema's integer accepts 2.0.
        assert!(run(json!({"goto_step": "p", "max_loops": 2.0})).is_empty());
        assert_eq!(run(json!({"goto_step": "p", "max_loops": 2.5})), ["S303"]);
    }

    #[test]
    fn undeclared_escalation_still_checks_on_error() {
        let fm = json!({"condition": "c", "action": "escalate", "on_error": "R999",
                        "recovery": {"goto_step": "nowhere"}});
        let c = codes(catalog(json!([with_fm(st("observe", "o"), fm)]), &[]));
        assert_eq!(c, ["S303", "V106"]);
    }

    #[test]
    fn duplicates_are_judged_in_list_order() {
        // The handler is listed first but checked after its targeter; the
        // later list step is still the duplicate.
        let report = super::super::validate_catalog(
            &super::super::tests::ctx(),
            &catalog(
                json!([
                    handler("dup"),
                    st("observe", "dup"),
                    with_fm(st("detect", "d"), esc("dup"))
                ]),
                &["recovery@1"],
            ),
            None,
        );
        let v104: Vec<_> = report
            .diagnostics
            .iter()
            .filter(|d| d.code.as_str() == "V104")
            .collect();
        assert_eq!(v104.len(), 1);
        assert_eq!(v104[0].location["step"], json!(1));
        assert_eq!(v104[0].location["first_step"], json!(0));
    }

    #[test]
    fn handler_prerequisites_are_checked_at_the_targeter() {
        let mut h = handler("hand");
        h["requires_checkpoint"] = json!(true);
        let early = catalog(
            json!([
                with_fm(st("observe", "o"), esc("hand")),
                st("checkpoint", "c"),
                h.clone()
            ]),
            &["recovery@1"],
        );
        assert_eq!(codes(early), ["F501"]);
        let covered = catalog(
            json!([
                st("checkpoint", "c"),
                with_fm(st("observe", "o"), esc("hand")),
                h
            ]),
            &["recovery@1"],
        );
        assert!(codes(covered).is_empty());
    }

    #[test]
    fn concurrent_outputs_may_be_absent_in_a_handler() {
        let grouped = |mut s: Value, g: &str| {
            s["parallel_group"] = json!(g);
            s
        };
        let run = |mate_group: &str| {
            let mut h = handler("hand");
            h["condition"] = json!("${mate.confidence} > 0.5");
            codes(catalog(
                json!([
                    grouped(st("plan", "mate"), mate_group),
                    grouped(with_fm(st("observe", "o"), esc("hand")), "g"),
                    h
                ]),
                &["recovery@1"],
            ))
        };
        // A mate runs alongside the failed step and may not have finished;
        // a step in another group ran before it.
        assert_eq!(run("g"), ["W610"]);
        assert!(run("other").is_empty());
    }

    #[test]
    fn handlers_and_loops_scale_linearly() {
        let n = 4_000;
        let mut steps = Vec::new();
        for i in 0..n {
            steps.push(with_fm(
                st("observe", &format!("o{i}")),
                esc(&format!("h{i}")),
            ));
        }
        for i in 0..n {
            steps.push(handler(&format!("h{i}")));
        }
        for i in 0..n {
            let fm = json!({"condition": "c", "action": "rollback", "when": "true",
                            "recovery": {"goto_step": "o0",
                                         "inject_context": {format!("k{i}"): "${o0}"}}});
            steps.push(with_fm(st("observe", &format!("v{i}")), fm));
        }
        let start = std::time::Instant::now();
        let c = codes(catalog(Value::Array(steps), &["recovery@1"]));
        assert!(c.is_empty(), "{:?}", &c[..c.len().min(5)]);
        assert!(
            start.elapsed() < std::time::Duration::from_secs(5),
            "{:?}",
            start.elapsed()
        );
    }
}
