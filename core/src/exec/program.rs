//! What the executor needs from a validated catalog, prepared once: each
//! reachable workflow's steps with their effective safety flags, output
//! contracts and parsed expressions. Rebuilt from the catalog on restore, so
//! it is never part of a snapshot.

use std::collections::BTreeMap;
use std::time::Duration;

use serde_json::{Map, Value};

use super::canonical;
use crate::agents::Agents;
use crate::catalogs::{CatalogSet, Namespace, Resolver};
use crate::duration;
use crate::expr::{self, ast::Expr};
use crate::profile::Policy;
use crate::validate::Context;

/// A gate or failure-mode action.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateAction {
    Stop,
    Rollback,
    Skip,
    Warn,
    /// End the run successfully: no later step runs (§5.6).
    End,
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
    /// An applied profile requires a person for this step (§5.21.3): it
    /// is asked as an always-ask step is, but marks nothing.
    pub person: bool,
    /// The profiles that require the person (the trace's
    /// `person_required`).
    pub raised_by: Vec<String>,
    pub required_outputs: Vec<String>,
    pub handler: bool,
    pub condition: Option<Expr>,
    pub skip_if_false: bool,
    pub gates: Vec<Gate>,
    pub failure_modes: Vec<FailureMode>,
    pub timeout: Option<Duration>,
    /// `wait@1`: how long to wait before the step's approval, checkpoint
    /// and execution (§5.13).
    pub delay: Option<Duration>,
    /// `approval@1` `after_deferral: run`: only reading a deferred step's
    /// output defers this step (§5.14).
    pub after_deferral_runs: bool,
    pub retry: Option<Retry>,
    /// The roots the step reads in its executable fields (not `purpose` or
    /// a failure mode's prose), and the reviewers its quorum counts: a step
    /// that reads a deferred step's store is deferred too (§5.14).
    pub reads: Vec<String>,
    /// The step may act on, or wait on, the world: its effective
    /// `requires_checkpoint` or `requires_approval` is true, it waits, or it
    /// is an `invoke`, `delegate`, `synchronize` or `rollback`. After a
    /// deferral it is deferred too (§5.14).
    pub acts: bool,
    /// The references its `input_bindings` make (root and path, without
    /// annotations): what an `acs:` citation in its output may cite (§5.20).
    pub bound: Vec<crate::refs::Ref>,
    /// Capabilities the ontology orders before this one through `precedes`
    /// edges, transitively (as `mutate` before `verify`): after one of them
    /// is deferred, so is this step.
    pub after: Vec<String>,
    /// For a `delegate` step of a workflow that declares `agents`, why its
    /// target maxima are unknown: the executor then does not delegate
    /// (R402, §5.15.2).
    pub unbounded: Option<String>,
}

/// Every reference root in `v`, in document order.
pub(crate) fn roots(v: &Value, out: &mut Vec<String>) {
    match v {
        Value::String(s) => out.extend(
            crate::refs::find_refs(s)
                .into_iter()
                .filter_map(|m| m.parsed.ok())
                .map(|r| r.root),
        ),
        Value::Array(a) => a.iter().for_each(|x| roots(x, out)),
        Value::Object(m) => m.values().for_each(|x| roots(x, out)),
        _ => {}
    }
}

pub struct Workflow {
    pub name: String,
    pub raw: Map<String, Value>,
    pub steps: Vec<Step>,
    pub declared: Vec<String>,
    /// The workflow targets 1.2 or later (§11.5): by its `spec_version`,
    /// else by the catalog header's version. Rules for 1.2 targets only,
    /// such as the approver's `sender_check` (§5.17), apply.
    pub targets_1_2: bool,
    /// The workflow's grounding policy (`grounding@1`, §5.20): it applies to
    /// its own steps.
    pub grounding: Option<crate::grounding::Policy>,
    /// The agents its `delegate` steps may delegate to (§5.15.2), when it
    /// targets 1.2 or later and declares them.
    pub agents: Option<Vec<String>>,
}

impl Workflow {
    pub fn extension(&self, name: &str) -> bool {
        self.declared.iter().any(|d| d == name)
    }
}

pub struct Program {
    /// The catalog set's workflows by namespace key (§5.1.1): a name for
    /// the primary catalog's, `<catalog id>/<name>` for another's.
    pub workflows: BTreeMap<String, Workflow>,
    /// Resolves `invoke` targets over the catalog set (§5.1.1).
    pub resolver: Resolver,
    /// The agent manifests the run was started with (§5.15.1).
    pub agents: Agents,
    /// SHA-256 of the canonical JSON of the catalog and the ontology
    /// contracts its steps use: a snapshot is only restored against what it
    /// was taken from.
    pub digest: String,
    /// The domain profiles applied to the run (§5.21): saved with the run
    /// as given, and loaded again when it is restored.
    pub policy: Policy,
    /// The grounding policies the applied profiles put in force (§5.21.3,
    /// §5.20), one per profile with `require_grounding`: like a host's,
    /// they apply in every frame.
    pub grounding: Vec<crate::grounding::Policy>,
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
    /// target at run time). The catalog must already have passed validation,
    /// with `header`, the version its header declares (§11.5).
    pub fn build(
        ctx: &Context,
        catalog: &Value,
        root: &str,
        header: Option<&str>,
        policy: Policy,
    ) -> Result<Program, String> {
        Self::build_set(
            ctx,
            CatalogSet::single(catalog, header),
            &Agents::default(),
            root,
            policy,
        )
    }

    /// Prepare every workflow of a catalog set (§5.1.1) with the agent
    /// manifests `agents` (§5.15.1) and the applied profiles' `policy`
    /// (§5.21). `root` names a workflow of the primary catalog. The set must
    /// already have passed validation.
    pub fn build_set(
        ctx: &Context,
        set: CatalogSet<'_>,
        agents: &Agents,
        root: &str,
        policy: Policy,
    ) -> Result<Program, String> {
        if !set.primary.is_object() {
            return Err("the catalog is not a mapping".to_string());
        }
        let ns = Namespace::build(set)?;
        let mut workflows = BTreeMap::new();
        for (key, value) in ns.iter() {
            let Value::Object(raw) = value else { continue };
            if !raw.contains_key("steps") {
                continue;
            }
            let target = crate::validate::semantics::target(raw, ns.header_of(key));
            let declared = crate::agents::declared(raw, target);
            let mut workflow = Self::workflow(ctx, key, raw, agents, declared.as_deref(), &policy)?;
            workflow.targets_1_2 = target.is_some_and(|t| t >= (1, 2));
            workflow.agents = declared.map(|d| d.into_iter().map(str::to_string).collect());
            workflows.insert(key.to_string(), workflow);
        }
        if !workflows.contains_key(root) || ns.catalog_of(root) != 0 {
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
        // The other catalogs and the manifests are covered only when given,
        // so a single catalog's digest is what it was in 1.1.
        let mut covered = serde_json::json!({
            "catalog": set.primary,
            "contracts": contracts,
        });
        if !set.others.is_empty() {
            covered["catalogs"] = Value::Array(
                set.others
                    .iter()
                    .map(|(doc, header)| serde_json::json!([doc, header]))
                    .collect(),
            );
        }
        if !agents.is_empty() {
            covered["agents"] = agents.digest_value();
        }
        let digest = canonical::digest(&covered);
        Ok(Program {
            workflows,
            resolver: ns.resolver.clone(),
            agents: agents.clone(),
            digest,
            grounding: policy.grounding(),
            policy,
        })
    }

    fn workflow(
        ctx: &Context,
        name: &str,
        raw: &Map<String, Value>,
        agents: &Agents,
        delegable: Option<&[&str]>,
        policy: &Policy,
    ) -> Result<Workflow, String> {
        let declared: Vec<String> = raw
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
        let mut steps = Vec::with_capacity(list.len());
        for (index, value) in list.iter().enumerate() {
            let Some(step) = value.as_object() else {
                return Err(format!("{name}: step {index} is not a mapping"));
            };
            steps.push(Self::step(
                ctx, name, index, step, list, &declared, agents, delegable, policy,
            )?);
        }
        let grounding = declared
            .iter()
            .any(|d| d == "grounding@1")
            .then(|| {
                raw.get("grounding")
                    .and_then(crate::grounding::Policy::from_value)
            })
            .flatten();
        Ok(Workflow {
            name: name.to_string(),
            raw: raw.clone(),
            steps,
            declared,
            targets_1_2: false,
            grounding,
            agents: None,
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn step(
        ctx: &Context,
        wf: &str,
        index: usize,
        raw: &Map<String, Value>,
        all: &[Value],
        declared: &[String],
        agents: &Agents,
        delegable: Option<&[&str]>,
        policy: &Policy,
    ) -> Result<Step, String> {
        let at = |what: &str| format!("{wf}: step {index}: {what}");
        let has = |ext: &str| declared.iter().any(|d| d == ext);
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
                Some("end") => GateAction::End,
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
        let delay = match raw.get("delay") {
            Some(Value::String(d)) if has("wait@1") => duration::parse(d).ok(),
            _ => None,
        };
        let retry = raw.get("retry").and_then(Value::as_object).map(|r| Retry {
            max: r
                .get("max")
                .and_then(crate::validate::count)
                .map_or(0, |m| u32::try_from(m).unwrap_or(u32::MAX)),
            backoff: r
                .get("backoff")
                .and_then(Value::as_str)
                .unwrap_or("none")
                .to_string(),
        });
        let mut reads: Vec<String> = crate::refs::executable_roots(raw)
            .into_iter()
            .map(|r| r.root)
            .collect();
        if let Some(Value::Array(rs)) = raw.get("quorum").and_then(|q| q.get("reviewers")) {
            reads.extend(rs.iter().filter_map(Value::as_str).map(str::to_string));
        }
        reads.sort_unstable();
        reads.dedup();
        // A delegate step's target maxima (§5.15.2), as the validator
        // computes them; unknown ones stop the delegation.
        let target = if capability == "delegate" {
            crate::agents::target_maxima(agents, &ctx.ontology, delegable, raw)
        } else {
            crate::agents::Target::Free
        };
        let unbounded = target.why_unknown();
        // The effective flags (§5.2.1), as the validator computes them:
        // raised by the delegation targets' maxima (§5.15.2) and the
        // applied profiles (§5.21.3).
        let effective = crate::validate::effective(node, raw, target.maxima(), policy);
        let flags = effective.flags;
        let raised_by = if effective.person {
            policy.labels_raising(&capability, flags.risk)
        } else {
            Vec::new()
        };
        let (requires_checkpoint, requires_approval) =
            (flags.requires_checkpoint, flags.requires_approval);
        // Acting on the world: a checkpoint or approval requirement, a
        // wait, another agent or workflow, or a rollback.
        let acts = requires_checkpoint
            || requires_approval
            || raw.contains_key("wait")
            || delay.is_some()
            || matches!(
                capability.as_str(),
                "invoke" | "delegate" | "synchronize" | "rollback"
            );
        // `precedes` is transitive: everything ordered before this
        // capability, directly or through others.
        let mut after: Vec<String> = Vec::new();
        let mut queue = vec![capability.as_str()];
        while let Some(c) = queue.pop() {
            for from in ctx
                .ontology
                .incoming(c, crate::ontology::EdgeType::Precedes)
            {
                if from != capability && !after.iter().any(|a| a == from) {
                    after.push(from.to_string());
                    queue.push(from);
                }
            }
        }
        Ok(Step {
            unbounded,
            reads,
            acts,
            bound: crate::grounding::bound_refs(raw.get("input_bindings").unwrap_or(&Value::Null)),
            after,
            index,
            store_as: raw
                .get("store_as")
                .and_then(Value::as_str)
                .map(str::to_string),
            requires_checkpoint,
            requires_approval,
            person: effective.person,
            raised_by,
            required_outputs,
            handler: has("recovery@1") && capability == "invoke" && flag("handler"),
            delay,
            after_deferral_runs: has("approval@1")
                && raw.get("after_deferral").and_then(Value::as_str) == Some("run"),
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

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::Program;
    use crate::profile::Policy;
    use crate::validate::tests::ctx;

    #[test]
    fn bound_references_and_policy() {
        let catalog = json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.2",
        "workflow_extensions": {"requires": ["grounding@1"]},
        "grounding": {"require": ["transform"], "kinds": ["file"]},
        "steps": [
            {"capability": "retrieve", "purpose": "p", "store_as": "r",
             "input_bindings": {"target": "t"}},
            {"capability": "retrieve", "purpose": "p", "store_as": "s",
             "input_bindings": {"target": "t"}},
            {"capability": "transform", "purpose": "p", "store_as": "x",
             "input_bindings": {"input": "${r.data[0:2]: array<object>}",
                                "target_format": "x ${s.confidence} y"}}
        ]}});
        let program = Program::build(&ctx(), &catalog, "w", None, Policy::default()).unwrap();
        let w = &program.workflows["w"];
        let bodies: Vec<String> = w.steps[2]
            .bound
            .iter()
            .map(crate::grounding::body)
            .collect();
        assert_eq!(bodies, ["r.data[0:2]", "s.confidence"]);
        assert!(w.steps[0].bound.is_empty());
        let policy = w.grounding.as_ref().unwrap();
        assert!(policy.requires("transform") && policy.kinds.is_some());
        // Without grounding@1, the field is no policy.
        let mut plain = catalog.clone();
        plain["w"]["spec_version"] = json!("1.1");
        plain["w"]
            .as_object_mut()
            .unwrap()
            .remove("workflow_extensions");
        let program = Program::build(&ctx(), &plain, "w", None, Policy::default()).unwrap();
        assert!(program.workflows["w"].grounding.is_none());
    }
}
