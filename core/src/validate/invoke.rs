//! Invocations between catalog workflows (STANDARD v1.1 §5.10, §5.12):
//! unknown targets (W607), invoke cycles (V105), targets whose triggers
//! do not allow being invoked (V107), literal inputs the target does not
//! declare (S303) or that miss a required one (S304), and a qualified
//! target in a workflow that targets 1.0 or 1.1 (W616, STANDARD v1.2
//! §11.5).

use std::collections::{HashMap, HashSet};

use serde_json::{Map, Value};

use super::{Report, StepLoc, semantics};
use crate::catalogs::{Namespace, Resolved};
use crate::diag::{Code, Diagnostic};
use crate::names;

/// One invoke step and the workflow it names.
pub(crate) struct Invocation {
    pub workflow: String,
    pub step: usize,
    pub target: String,
    /// Where the target was named: `workflow_id` or
    /// `input_bindings.workflow`.
    pub field: &'static str,
    /// What the step passes as the workflow's inputs.
    pub input: Input,
}

/// An invoke step's `input_bindings.input`, as the validator can see it.
pub(crate) enum Input {
    /// The names of a literal mapping; none when `input` is absent or null
    /// (the executor then passes no inputs).
    Literal(Vec<String>),
    /// A `${...}` reference: only the executor can check it.
    Computed,
    /// Any other value; the executor would pass no inputs (B203 reports it).
    Malformed,
}

/// What an invoke step passes to its workflow.
pub(crate) fn input(step: &Map<String, Value>) -> Input {
    match step.get("input_bindings").and_then(|b| b.get("input")) {
        None | Some(Value::Null) => Input::Literal(Vec::new()),
        Some(Value::Object(m)) => Input::Literal(m.keys().cloned().collect()),
        Some(Value::String(s)) if super::refs_whole(s) => Input::Computed,
        Some(_) => Input::Malformed,
    }
}

/// The workflow an invoke step names, and where: `workflow_id`, else a
/// literal `input_bindings.workflow` (the capability's input). `None` when
/// the target is computed at runtime.
pub(crate) fn target(step: &Map<String, Value>) -> Option<(&str, &'static str)> {
    if let Some(Value::String(id)) = step.get("workflow_id") {
        return Some((id, "workflow_id"));
    }
    step.get("input_bindings")
        .and_then(|b| b.get("workflow"))
        .and_then(Value::as_str)
        .filter(|w| !w.contains("${"))
        .map(|w| (w, "input_bindings.workflow"))
}

/// S303 when a step names its target twice, in `workflow_id` and in
/// `input_bindings.workflow`, and the two differ: `workflow_id` would win
/// unseen.
pub(crate) fn check_target(loc: &StepLoc<'_>, step: &Map<String, Value>, report: &mut Report) {
    // A name that is not a string is a shape error reported elsewhere.
    let (Some(Value::String(id)), Some(Value::String(bound))) = (
        step.get("workflow_id"),
        step.get("input_bindings").and_then(|b| b.get("workflow")),
    ) else {
        return;
    };
    if id != bound {
        report.push(
            loc.diag(
                Code::SchemaValidationFailed,
                format!(
                    "names its target twice: workflow_id '{id}' and input_bindings.workflow '{bound}'; name it once"
                ),
            )
            .at("field", "input_bindings.workflow"),
        );
    }
}

/// The catalog-level invoke checks over the catalog set (§5.1.1, §5.12):
/// resolution (W607, V107), the target's triggers (V107), literal inputs
/// (S303, S304) and cycles (V105), across the catalogs of the set.
pub(crate) fn check(ns: &Namespace<'_>, invocations: &[Invocation], report: &mut Report) {
    let at = |inv: &Invocation, code: Code, message: String| {
        Diagnostic::new(code, message)
            .at("workflow", inv.workflow.as_str())
            .at("step", inv.step)
            .at("capability", "invoke")
            .at("field", inv.field)
    };
    let mut edges: HashMap<&str, Vec<&str>> = HashMap::new();
    let mut resolved: Vec<(&Invocation, &str)> = Vec::new();
    let mut qualified_reported = HashSet::new();
    for inv in invocations {
        if ns.resolver.is_qualified(&inv.workflow, &inv.target)
            && qualified_reported.insert(inv.workflow.as_str())
        {
            qualified_feature(ns, inv, report);
        }
        let key = match ns.resolver.resolve(&inv.workflow, &inv.target) {
            Resolved::Key(k) => k,
            Resolved::Unresolved => {
                let message = match names::split_qualified(&inv.target) {
                    Some((id, _)) => format!(
                        "invokes '{}': catalog '{id}' is not loaded; it cannot be checked here",
                        inv.target
                    ),
                    None => format!(
                        "invokes '{}', which is not in this catalog; it cannot be checked here",
                        inv.target
                    ),
                };
                report.push(at(inv, Code::UnresolvedWorkflow, message));
                continue;
            }
            Resolved::Missing { catalog, name } => {
                report.push(at(
                    inv,
                    Code::UnresolvedTarget,
                    format!(
                        "invokes '{}': catalog '{catalog}' has no workflow '{name}'",
                        inv.target
                    ),
                ));
                continue;
            }
            Resolved::NotExported { catalog, name } => {
                report.push(at(
                    inv,
                    Code::UnresolvedTarget,
                    format!(
                        "invokes '{}': catalog '{catalog}' does not export '{name}'; only exported workflows can be invoked from another catalog",
                        inv.target
                    ),
                ));
                continue;
            }
        };
        let (Some(key), Some(target)) = (ns.get_key(&key), ns.get(&key)) else {
            continue;
        };
        if let Some(Value::Array(triggers)) = target.get("triggers") {
            let invocable = triggers
                .iter()
                .any(|t| t.get("kind").and_then(Value::as_str) == Some("invoke"));
            if !invocable {
                report.push(at(
                    inv,
                    Code::UnresolvedTarget,
                    format!(
                        "invokes '{}', whose triggers do not include kind 'invoke'",
                        inv.target
                    ),
                ));
            }
        }
        check_input(inv, target, report);
        edges.entry(inv.workflow.as_str()).or_default().push(key);
        resolved.push((inv, key));
    }
    // An invocation closes a cycle when its target can reach its caller:
    // it calls itself, or both lie in one strongly connected component.
    // Each workflow in a cycle is reported once, at its first such
    // invocation, so a densely connected cycle is not O(edges) reports.
    let component = components(&edges);
    let mut reported = HashSet::new();
    for (inv, target) in resolved {
        let caller = inv.workflow.as_str();
        if (caller == target || component.get(caller) == component.get(target))
            && reported.insert(caller)
        {
            report.push(at(
                inv,
                Code::CircularDependency,
                format!(
                    "invoking '{}' forms a cycle back to '{}'; invoked workflows must not invoke their callers",
                    inv.target,
                    ns.name_of(caller)
                ),
            ));
        }
    }
}

/// W616 at `inv`, the first invoke step of its workflow whose target is a
/// qualified id (§5.1.1), when the workflow targets a version before 1.2
/// (§11.5): a 1.1 consumer resolves names in one catalog only. Whether the
/// target resolves does not matter (W607 or V107 says when it does not), so
/// the warning does not depend on the catalogs given. Located at the step,
/// as the other features are; nothing for a workflow that declares no
/// supported version (W605 or V109 says so).
fn qualified_feature(ns: &Namespace<'_>, inv: &Invocation, report: &mut Report) {
    const SINCE: (u64, u64) = (1, 2);
    let Some(Value::Object(wf)) = ns.get(&inv.workflow) else {
        return;
    };
    let (version, by_header) = match wf.get("spec_version") {
        Some(Value::String(v)) => (v.as_str(), false),
        Some(_) => return,
        None => match ns.header_of(&inv.workflow) {
            Some(h) => (h, true),
            None => return,
        },
    };
    let supported = semantics::parse_version(version)
        .filter(|v| semantics::SUPPORTED_VERSIONS.contains(v) && *v < SINCE);
    if supported.is_none() {
        return;
    }
    report.push(semantics::version_feature_diag(
        "an invoke target that is a qualified id",
        SINCE,
        version,
        by_header,
        |d| {
            d.at("workflow", inv.workflow.as_str())
                .at("step", inv.step)
                .at("capability", "invoke")
        },
        inv.field,
    ));
}

/// A literal invocation input against the target's declared inputs. The
/// executor refuses undeclared names and missing required ones (R402), so
/// both are errors here. Workflow inputs have no `x-` exemption: they are
/// names the target declares, not fields of the step.
fn check_input(inv: &Invocation, target: &Value, report: &mut Report) {
    let given: &[String] = match &inv.input {
        Input::Computed => return,
        Input::Literal(names) => names,
        // Not a mapping: B203 against the capability's `input` contract
        // already says so, and no input could be checked.
        Input::Malformed => return,
    };
    let empty = Map::new();
    let declared = target
        .get("inputs")
        .and_then(Value::as_object)
        .unwrap_or(&empty);
    let at = |code: Code, message: String| {
        Diagnostic::new(code, message)
            .at("workflow", inv.workflow.as_str())
            .at("step", inv.step)
            .at("capability", "invoke")
    };
    super::inputs::check_names(
        declared,
        given,
        |name| {
            at(
                Code::SchemaValidationFailed,
                format!(
                    "'{}' has no input '{name}'; the executor refuses undeclared inputs (R402)",
                    inv.target
                ),
            )
            .at_field_key("input_bindings.input", name)
        },
        |name| {
            at(
                Code::MissingRequiredField,
                format!(
                    "'{}' needs input '{name}', which input_bindings.input does not give",
                    inv.target
                ),
            )
            .at("field", "input_bindings.input")
        },
        report,
    );
}

/// Tarjan's algorithm state.
#[derive(Default)]
struct Tarjan<'a> {
    index: HashMap<&'a str, usize>,
    low: HashMap<&'a str, usize>,
    stack: Vec<&'a str>,
    on_stack: HashSet<&'a str>,
    component: HashMap<&'a str, usize>,
    found: usize,
}

impl<'a> Tarjan<'a> {
    fn visit(&mut self, w: &'a str, calls: &mut Vec<(&'a str, usize)>) {
        let n = self.index.len();
        self.index.insert(w, n);
        self.low.insert(w, n);
        self.stack.push(w);
        self.on_stack.insert(w);
        calls.push((w, 0));
    }
}

/// The strongly connected components of the invocation graph (Tarjan's
/// algorithm, iterative, linear): workflow → component number.
fn components<'a>(edges: &HashMap<&'a str, Vec<&'a str>>) -> HashMap<&'a str, usize> {
    let mut t = Tarjan::default();
    let mut roots: Vec<&str> = edges.keys().copied().collect();
    roots.sort_unstable();
    for root in roots {
        if t.index.contains_key(root) {
            continue;
        }
        // (workflow, next outgoing invocation to follow)
        let mut calls: Vec<(&str, usize)> = Vec::new();
        t.visit(root, &mut calls);
        while let Some(&(v, next)) = calls.last() {
            let out = edges.get(v).map(Vec::as_slice).unwrap_or_default();
            if let Some(&w) = out.get(next) {
                if let Some(top) = calls.last_mut() {
                    top.1 += 1;
                }
                match t.index.get(w) {
                    None => t.visit(w, &mut calls),
                    Some(&wi) if t.on_stack.contains(w) => {
                        let lv = t.low.entry(v).or_default();
                        *lv = (*lv).min(wi);
                    }
                    Some(_) => {}
                }
                continue;
            }
            calls.pop();
            let lv = t.low[v];
            if let Some(&(u, _)) = calls.last() {
                let lu = t.low.entry(u).or_default();
                *lu = (*lu).min(lv);
            }
            if lv == t.index[v] {
                while let Some(w) = t.stack.pop() {
                    t.on_stack.remove(w);
                    t.component.insert(w, t.found);
                    if w == v {
                        break;
                    }
                }
                t.found += 1;
            }
        }
    }
    t.component
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::super::tests::codes;

    fn wf(steps: Value) -> Value {
        json!({"goal": "g", "risk": "low", "spec_version": "1.1", "steps": steps})
    }

    fn invoke(target: &str, store: &str) -> Value {
        json!({"capability": "invoke", "purpose": "p", "store_as": store, "workflow_id": target})
    }

    #[test]
    fn unknown_target_warns() {
        assert_eq!(
            codes(json!({"a": wf(json!([invoke("elsewhere", "i")]))})),
            ["W607"]
        );
        let literal = json!({"capability": "invoke", "purpose": "p", "store_as": "i",
                             "input_bindings": {"workflow": "elsewhere"}});
        assert_eq!(codes(json!({"a": wf(json!([literal]))})), ["W607"]);
    }

    /// A qualified target in a workflow that targets 1.1 is W616 whatever
    /// the catalogs given (§11.5), located at its step (§9.8); a name of the
    /// workflow's own catalog, or a legacy name that is not a qualified id,
    /// is not.
    #[test]
    fn a_qualified_target_below_1_2_is_a_version_warning() {
        use crate::diag::Code;
        let ctx = super::super::tests::ctx();
        let report = super::super::validate_catalog(
            &ctx,
            &json!({"a": wf(json!([invoke("other.cat/x", "i")]))}),
            None,
        );
        let found: Vec<_> = report.diagnostics.iter().map(|d| d.code.as_str()).collect();
        assert_eq!(found, ["W616", "W607"]);
        let d = &report.diagnostics[0];
        assert_eq!(d.code, Code::VersionFeatureMismatch);
        assert_eq!(
            Value::Object(d.location.clone()),
            json!({"workflow": "a", "step": 0, "capability": "invoke",
                   "field": "workflow_id", "path": "/a/steps/0/workflow_id"})
        );
        // From 1.2, only the unresolved target.
        let mut v12 = wf(json!([invoke("other.cat/x", "i")]));
        v12["spec_version"] = json!("1.2");
        assert_eq!(codes(json!({"a": v12})), ["W607"]);
        // Not a qualified id: no catalog id before the '/'.
        assert_eq!(
            codes(json!({"a": wf(json!([invoke("Other/x", "i")]))})),
            ["W607"]
        );
    }

    #[test]
    fn a_target_is_named_once() {
        let catalog = |bound: Value| {
            let mut step = invoke("t", "i");
            step["input_bindings"] = json!({"workflow": bound});
            let mut caller = wf(json!([step]));
            caller["inputs"] = json!({"name": {"type": "string"}});
            codes(json!({"a": caller, "t": wf(json!([]))}))
        };
        assert!(catalog(json!("t")).is_empty());
        assert_eq!(catalog(json!("u")), ["S303"]);
        assert_eq!(catalog(json!("${name}")), ["S303"]);
        // A non-string name is only its type error.
        assert_eq!(catalog(json!(5)), ["B203"]);
    }

    #[test]
    fn literal_inputs_match_the_target() {
        let catalog = |step: Value| {
            let mut caller = wf(json!([step]));
            caller["inputs"] = json!({"given": {"type": "object"}, "name": {"type": "string"}});
            let mut target = wf(json!([]));
            target["inputs"] = json!({"user_input": {"type": "object", "required": true},
                                      "previous": {"type": "object"}});
            json!({"a": caller, "t": target})
        };
        let call = |input: Option<Value>| {
            let mut step = invoke("t", "i");
            if let Some(input) = input {
                step["input_bindings"] = json!({"input": input});
            }
            codes(catalog(step))
        };
        assert!(call(Some(json!({"user_input": {}, "previous": {}}))).is_empty());
        assert!(call(Some(json!({"user_input": {}}))).is_empty());
        // Computed inputs are checked at runtime only.
        assert!(call(Some(json!("${given}"))).is_empty());
        assert_eq!(call(Some(json!({"user_inptu": {}}))), ["S303", "S304"]);
        // Workflow inputs have no x- exemption: the executor refuses them.
        assert_eq!(
            call(Some(json!({"user_input": {}, "x-trace": 1}))),
            ["S303"]
        );
        // No input, an empty one or null all pass nothing.
        assert_eq!(call(None), ["S304"]);
        assert_eq!(call(Some(json!({}))), ["S304"]);
        assert_eq!(call(Some(Value::Null)), ["S304"]);
        // Anything else is not a mapping (B203, from the capability's own
        // contract), and nothing more is said about its inputs.
        assert_eq!(call(Some(json!([]))), ["B203"]);
        assert_eq!(call(Some(json!("user_input"))), ["B203"]);

        // The suggestion names the closest declared input.
        let mut step = invoke("t", "i");
        step["input_bindings"] = json!({"input": {"user_inptu": {}}});
        let report =
            super::super::validate_catalog(&super::super::tests::ctx(), &catalog(step), None);
        let d = report
            .diagnostics
            .iter()
            .find(|d| d.code.as_str() == "S303")
            .unwrap();
        assert_eq!(d.suggestion.as_deref(), Some("did you mean 'user_input'?"));
        assert_eq!(d.location["field"], "input_bindings.input.user_inptu");

        // A target named by input_bindings.workflow is checked too; a
        // computed or unknown target is not.
        let named = |workflow: &str| {
            json!({"capability": "invoke", "purpose": "p", "store_as": "i",
                   "input_bindings": {"workflow": workflow, "input": {"nope": 1}}})
        };
        assert_eq!(codes(catalog(named("t"))), ["S303", "S304"]);
        assert!(codes(catalog(named("${name}"))).is_empty());
        assert_eq!(codes(catalog(named("elsewhere"))), ["W607"]);
    }

    #[test]
    fn cycles() {
        let catalog = json!({
            "a": wf(json!([invoke("b", "i")])),
            "b": wf(json!([invoke("a", "i")])),
            "c": wf(json!([invoke("c", "i")])),
            "d": wf(json!([invoke("a", "i")])),
        });
        // a→b and b→a close the cycle; c invokes itself; d only reaches it.
        assert_eq!(codes(catalog), ["V105", "V105", "V105"]);
    }

    #[test]
    fn longer_cycles_and_chains() {
        // a→b→c→a is one cycle; d→a and a chain into it are not.
        let catalog = json!({
            "a": wf(json!([invoke("b", "i")])),
            "b": wf(json!([invoke("c", "i")])),
            "c": wf(json!([invoke("a", "i"), invoke("e", "j")])),
            "d": wf(json!([invoke("a", "i")])),
            "e": wf(json!([{"capability": "observe", "purpose": "p", "store_as": "o"}])),
        });
        assert_eq!(codes(catalog), ["V105", "V105", "V105"]);
    }

    #[test]
    fn diagnostics_name_the_field_that_names_the_target() {
        let literal = json!({"capability": "invoke", "purpose": "p", "store_as": "i",
                             "input_bindings": {"workflow": "elsewhere"}});
        let report = super::super::validate_catalog(
            &super::super::tests::ctx(),
            &json!({"a": wf(json!([literal]))}),
            None,
        );
        assert_eq!(
            report.diagnostics[0].location["field"],
            json!("input_bindings.workflow")
        );
    }

    #[test]
    fn cycle_detection_scales_linearly() {
        // A chain w0 → w1 → … → wN closed back to w0.
        let n = 8_000;
        let mut catalog = serde_json::Map::new();
        for i in 0..n {
            let next = format!("w{}", (i + 1) % n);
            catalog.insert(format!("w{i}"), wf(json!([invoke(&next, "i")])));
        }
        let start = std::time::Instant::now();
        let c = codes(Value::Object(catalog));
        assert_eq!(c.iter().filter(|c| **c == "V105").count(), n);
        assert!(
            start.elapsed() < std::time::Duration::from_secs(5),
            "{:?}",
            start.elapsed()
        );
    }

    #[test]
    fn a_dense_cycle_is_reported_once_per_workflow() {
        // Every workflow invokes every other: n² edges, n reports.
        let n = 30;
        let mut catalog = serde_json::Map::new();
        for i in 0..n {
            let steps: Vec<Value> = (0..n)
                .filter(|&j| j != i)
                .map(|j| invoke(&format!("w{j}"), &format!("i{j}")))
                .collect();
            catalog.insert(format!("w{i}"), wf(Value::Array(steps)));
        }
        let c = codes(Value::Object(catalog));
        assert_eq!(c.iter().filter(|c| **c == "V105").count(), n);
    }

    #[test]
    fn invocable_targets() {
        let target = |kinds: Value| {
            let mut t = wf(json!([{"capability": "observe", "purpose": "p", "store_as": "o"}]));
            t["triggers"] = kinds;
            t["workflow_extensions"] = json!({"requires": ["triggers@1"]});
            codes(json!({"a": wf(json!([invoke("t", "i")])), "t": t}))
        };
        assert_eq!(target(json!([{"kind": "manual"}])), ["V107"]);
        assert!(target(json!([{"kind": "manual"}, {"kind": "invoke"}])).is_empty());
    }
}
