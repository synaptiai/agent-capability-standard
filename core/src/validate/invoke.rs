//! Invocations between catalog workflows (STANDARD v1.1 §5.10, §5.12):
//! unknown targets (W607), invoke cycles (V105), and targets whose triggers
//! do not allow being invoked (V107).

use std::collections::{HashMap, HashSet};

use serde_json::{Map, Value};

use super::Report;
use crate::diag::{Code, Diagnostic};

/// One invoke step and the workflow it names.
pub(crate) struct Invocation {
    pub workflow: String,
    pub step: usize,
    pub target: String,
    /// Where the target was named: `workflow_id` or
    /// `input_bindings.workflow`.
    pub field: &'static str,
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

pub(crate) fn check(
    workflows: &Map<String, Value>,
    invocations: &[Invocation],
    report: &mut Report,
) {
    let at = |inv: &Invocation, code: Code, message: String| {
        Diagnostic::new(code, message)
            .at("workflow", inv.workflow.as_str())
            .at("step", inv.step)
            .at("capability", "invoke")
            .at("field", inv.field)
    };
    let mut edges: HashMap<&str, Vec<&Invocation>> = HashMap::new();
    let mut resolved: Vec<&Invocation> = Vec::new();
    for inv in invocations {
        let Some(target) = workflows
            .get(&inv.target)
            .filter(|_| !inv.target.starts_with("x-"))
        else {
            report.push(at(
                inv,
                Code::UnresolvedWorkflow,
                format!(
                    "invokes '{}', which is not in this catalog; it cannot be checked here",
                    inv.target
                ),
            ));
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
        edges.entry(inv.workflow.as_str()).or_default().push(inv);
        resolved.push(inv);
    }
    // An invocation closes a cycle when its target can reach its caller:
    // it calls itself, or both lie in one strongly connected component.
    let component = components(&edges);
    for inv in resolved {
        let (caller, target) = (inv.workflow.as_str(), inv.target.as_str());
        if caller == target || component.get(caller) == component.get(target) {
            report.push(at(
                inv,
                Code::CircularDependency,
                format!(
                    "invoking '{}' forms a cycle back to '{}'; invoked workflows must not invoke their callers",
                    inv.target, inv.workflow
                ),
            ));
        }
    }
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
fn components<'a>(edges: &HashMap<&'a str, Vec<&'a Invocation>>) -> HashMap<&'a str, usize> {
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
            if let Some(inv) = out.get(next) {
                if let Some(top) = calls.last_mut() {
                    top.1 += 1;
                }
                let w = inv.target.as_str();
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
