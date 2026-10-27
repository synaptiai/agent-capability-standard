//! What the executor needs from a validated catalog, prepared once: each
//! reachable workflow's steps with their effective safety flags, output
//! contracts and parsed expressions. Rebuilt from the catalog on restore, so
//! it is never part of a snapshot.

use std::collections::BTreeMap;
use std::time::Duration;

use serde_json::{Map, Value};

use super::canonical;
use crate::duration;
use crate::expr::{self, ast::Expr};
use crate::validate::Context;

/// A gate or failure-mode action.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateAction {
    Stop,
    Rollback,
    Skip,
    Warn,
}

pub struct Gate {
    pub when: Expr,
    pub action: GateAction,
    pub after: bool,
    pub message: Option<String>,
}

pub struct FailureMode {
    pub action: String,
    pub on_error: Vec<String>,
    pub when: Option<Expr>,
    /// `recovery` as written, when it is an object.
    pub recovery: Option<Map<String, Value>>,
    pub goto: Option<usize>,
    pub on_exhausted: Option<usize>,
    pub max_loops: u64,
}

pub struct Retry {
    pub max: u32,
    pub backoff: String,
}

pub struct Step {
    pub index: usize,
    pub capability: String,
    pub store_as: Option<String>,
    pub raw: Map<String, Value>,
    pub requires_checkpoint: bool,
    pub requires_approval: bool,
    pub required_outputs: Vec<String>,
    pub handler: bool,
    pub condition: Option<Expr>,
    pub skip_if_false: bool,
    pub gates: Vec<Gate>,
    pub failure_modes: Vec<FailureMode>,
    pub timeout: Option<Duration>,
    pub retry: Option<Retry>,
}

pub struct Workflow {
    pub name: String,
    pub raw: Map<String, Value>,
    pub steps: Vec<Step>,
    pub declared: Vec<String>,
}

impl Workflow {
    pub fn extension(&self, name: &str) -> bool {
        self.declared.iter().any(|d| d == name)
    }
}

pub struct Program {
    pub workflows: BTreeMap<String, Workflow>,
    /// SHA-256 of the canonical JSON of the catalog and the ontology
    /// contracts its steps use: a snapshot is only restored against what it
    /// was taken from.
    pub digest: String,
}

fn parse(src: &str) -> Result<Expr, String> {
    expr::parse(src).map_err(|e| format!("{} at {}", e.msg, e.pos))
}

/// A `goto_step` target: a `store_as`, else (legacy) a capability held by
/// exactly one non-handler step. Validation has already resolved it.
fn target(steps: &[Value], name: &str) -> Option<usize> {
    let store = |s: &Value| s.get("store_as").and_then(Value::as_str) == Some(name);
    if let Some(i) = steps.iter().position(store) {
        return Some(i);
    }
    let held: Vec<usize> = steps
        .iter()
        .enumerate()
        .filter(|(_, s)| {
            s.get("capability").and_then(Value::as_str) == Some(name)
                && s.get("handler") != Some(&Value::Bool(true))
        })
        .map(|(i, _)| i)
        .collect();
    match held.as_slice() {
        [i] => Some(*i),
        _ => None,
    }
}

impl Program {
    /// Prepare every workflow of the catalog (an `invoke` may name its
    /// target at run time). The catalog must already have passed validation.
    pub fn build(ctx: &Context, catalog: &Value, root: &str) -> Result<Program, String> {
        let entries = catalog
            .as_object()
            .ok_or_else(|| "the catalog is not a mapping".to_string())?;
        let mut workflows = BTreeMap::new();
        for (name, value) in entries {
            let Value::Object(raw) = value else { continue };
            if name.starts_with("x-") || !raw.contains_key("steps") {
                continue;
            }
            workflows.insert(name.clone(), Self::workflow(ctx, name, raw)?);
        }
        if !workflows.contains_key(root) {
            return Err(format!("workflow '{root}' is not in the catalog"));
        }
        // What a restored run depends on: the catalog, and what the ontology
        // says about the capabilities it uses.
        let mut contracts = serde_json::Map::new();
        for step in workflows.values().flat_map(|w| &w.steps) {
            contracts.insert(
                step.capability.clone(),
                serde_json::json!({
                    "requires_checkpoint": ctx.ontology.get(&step.capability).map(|n| n.requires_checkpoint),
                    "requires_approval": ctx.ontology.get(&step.capability).map(|n| n.requires_approval),
                    "required_outputs": step.required_outputs,
                }),
            );
        }
        let digest = canonical::digest(&serde_json::json!({
            "catalog": catalog,
            "contracts": contracts,
        }));
        Ok(Program { workflows, digest })
    }

    fn workflow(ctx: &Context, name: &str, raw: &Map<String, Value>) -> Result<Workflow, String> {
        let declared = raw
            .get("workflow_extensions")
            .and_then(|e| e.get("requires"))
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();
        let list: &[Value] = raw
            .get("steps")
            .and_then(Value::as_array)
            .map(Vec::as_slice)
            .unwrap_or_default();
        let recovery_declared = raw
            .get("workflow_extensions")
            .and_then(|e| e.get("requires"))
            .and_then(Value::as_array)
            .is_some_and(|a| a.iter().any(|x| x.as_str() == Some("recovery@1")));
        let mut steps = Vec::with_capacity(list.len());
        for (index, value) in list.iter().enumerate() {
            let Some(step) = value.as_object() else {
                return Err(format!("{name}: step {index} is not a mapping"));
            };
            steps.push(Self::step(ctx, name, index, step, list, recovery_declared)?);
        }
        Ok(Workflow {
            name: name.to_string(),
            raw: raw.clone(),
            steps,
            declared,
        })
    }

    fn step(
        ctx: &Context,
        wf: &str,
        index: usize,
        raw: &Map<String, Value>,
        all: &[Value],
        recovery_declared: bool,
    ) -> Result<Step, String> {
        let at = |what: &str| format!("{wf}: step {index}: {what}");
        let capability = raw
            .get("capability")
            .and_then(Value::as_str)
            .ok_or_else(|| at("no capability"))?
            .to_string();
        let node = ctx
            .ontology
            .get(&capability)
            .ok_or_else(|| at(&format!("unknown capability '{capability}'")))?;
        let flag = |k: &str| raw.get(k) == Some(&Value::Bool(true));
        let required_outputs = ctx
            .contracts
            .get(&capability)
            .and_then(|c| c.output.get("required"))
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();
        let condition = match raw.get("condition") {
            Some(Value::String(c)) => Some(parse(c).map_err(|e| at(&format!("condition: {e}")))?),
            _ => None,
        };
        let mut gates = Vec::new();
        for (g, gate) in raw
            .get("gates")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .enumerate()
        {
            let when = gate
                .get("when")
                .and_then(Value::as_str)
                .ok_or_else(|| at(&format!("gates[{g}] has no when")))?;
            let action = match gate.get("action").and_then(Value::as_str) {
                Some("stop") => GateAction::Stop,
                Some("rollback") => GateAction::Rollback,
                Some("skip") => GateAction::Skip,
                Some("warn") => GateAction::Warn,
                other => return Err(at(&format!("gates[{g}].action {other:?}"))),
            };
            let when = parse(when).map_err(|e| at(&format!("gates[{g}].when: {e}")))?;
            // A gate with no phase that reads the step's own output is an
            // after-gate (§5.6; the validator warns W603).
            let store = raw.get("store_as").and_then(Value::as_str);
            let after = match gate.get("phase").and_then(Value::as_str) {
                Some(p) => p == "after",
                None => store.is_some_and(|s| when.refs().iter().any(|r| r.r.root == s)),
            };
            gates.push(Gate {
                when,
                action,
                after,
                message: gate
                    .get("message")
                    .and_then(Value::as_str)
                    .map(str::to_string),
            });
        }
        let mut failure_modes = Vec::new();
        for (f, fm) in raw
            .get("failure_modes")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .enumerate()
        {
            let on_error = match fm.get("on_error") {
                Some(Value::String(c)) => vec![c.clone()],
                Some(Value::Array(a)) => a
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect(),
                _ => Vec::new(),
            };
            let when = match fm.get("when") {
                Some(Value::String(w)) => {
                    Some(parse(w).map_err(|e| at(&format!("failure_modes[{f}].when: {e}")))?)
                }
                _ => None,
            };
            let recovery = fm.get("recovery").and_then(Value::as_object).cloned();
            let goto_name = recovery
                .as_ref()
                .and_then(|r| r.get("goto_step"))
                .and_then(Value::as_str);
            let goto = goto_name.and_then(|n| target(all, n));
            let on_exhausted = recovery
                .as_ref()
                .and_then(|r| r.get("on_exhausted"))
                .and_then(|e| e.get("goto_step"))
                .and_then(Value::as_str)
                .and_then(|n| target(all, n));
            let max_loops = recovery
                .as_ref()
                .and_then(|r| r.get("max_loops"))
                .and_then(|m| m.as_u64().or_else(|| m.as_f64().map(|f| f as u64)))
                .unwrap_or(1);
            failure_modes.push(FailureMode {
                action: fm
                    .get("action")
                    .and_then(Value::as_str)
                    .unwrap_or("stop")
                    .to_string(),
                on_error,
                when,
                recovery,
                goto,
                on_exhausted,
                max_loops,
            });
        }
        let timeout = match raw.get("timeout") {
            Some(Value::String(t)) => duration::parse(t).ok(),
            _ => None,
        };
        let retry = raw.get("retry").and_then(Value::as_object).map(|r| Retry {
            max: r
                .get("max")
                .and_then(Value::as_u64)
                .map_or(0, |m| u32::try_from(m).unwrap_or(u32::MAX)),
            backoff: r
                .get("backoff")
                .and_then(Value::as_str)
                .unwrap_or("none")
                .to_string(),
        });
        Ok(Step {
            index,
            store_as: raw
                .get("store_as")
                .and_then(Value::as_str)
                .map(str::to_string),
            requires_checkpoint: node.requires_checkpoint || flag("requires_checkpoint"),
            requires_approval: node.requires_approval || flag("requires_approval"),
            required_outputs,
            handler: recovery_declared && capability == "invoke" && flag("handler"),
            capability,
            raw: raw.clone(),
            condition,
            skip_if_false: raw.get("skip_if_false") != Some(&Value::Bool(false)),
            gates,
            failure_modes,
            timeout,
            retry,
        })
    }
}

/// The workflow an invoke step names: `workflow_id`, else a literal
/// `input_bindings.workflow`.
pub fn invoke_target(step: &Map<String, Value>) -> Option<&str> {
    if let Some(Value::String(id)) = step.get("workflow_id") {
        return Some(id);
    }
    step.get("input_bindings")
        .and_then(|b| b.get("workflow"))
        .and_then(Value::as_str)
}
