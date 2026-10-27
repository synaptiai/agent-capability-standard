//! Review quorums on `constrain` (STANDARD v1.1 §5.16, design-114 §15;
//! `quorum@1`): structure, reviewer resolution and reviewer independence.

use std::collections::hash_map::Entry;
use std::collections::{HashMap, HashSet, VecDeque};

use serde_json::{Map, Value};

use super::bindings::{Checker, Mode};
use super::extensions::{Declared, count, s303, s304};
use super::{Report, Scope, StepLoc, semantics, wait};
use crate::diag::{Code, Diagnostic};
use crate::{refs, yaml};

const QUORUM_KEYS: &[&str] = &[
    "verdicts",
    "reviewers",
    "vocabulary",
    "pass_values",
    "blocking_values",
    "min_pass",
    "pinned_to",
    "forbidden_inputs",
    "require_fresh_context",
    "require_model_families",
];
const REQUIRED: &[&str] = &[
    "verdicts",
    "reviewers",
    "vocabulary",
    "pass_values",
    "min_pass",
    "pinned_to",
];

/// The steps that run before the quorum step, by `store_as`.
pub(crate) struct Earlier<'a> {
    steps: &'a [Value],
    /// `store_as` → the first step (list index) that uses it.
    owners: &'a HashMap<&'a str, usize>,
    /// The quorum step's index and parallel group.
    before: usize,
    group: Option<&'a str>,
}

impl<'a> Earlier<'a> {
    pub(crate) fn new(
        steps: &'a [Value],
        owners: &'a HashMap<&'a str, usize>,
        before: usize,
    ) -> Earlier<'a> {
        let group = steps[before].get("parallel_group").and_then(Value::as_str);
        Earlier {
            steps,
            owners,
            before,
            group,
        }
    }

    /// The step that stores `store`, if it comes earlier in the list.
    fn step(&self, store: &str) -> Option<&'a Map<String, Value>> {
        self.owners
            .get(store)
            .filter(|&&j| j < self.before)
            .and_then(|&j| self.steps[j].as_object())
    }

    /// Whether `step` runs alongside the quorum step (same parallel group).
    fn concurrent(&self, step: &Map<String, Value>) -> bool {
        self.group.is_some() && step.get("parallel_group").and_then(Value::as_str) == self.group
    }
}

/// Who reads what across a workflow (built once, on first use), and the
/// stores each distinct set of forbidden inputs taints, so many quorum
/// steps cost one pass per distinct set rather than one walk each.
pub(crate) struct Independence<'a> {
    steps: &'a [Value],
    /// Root (store or input) → the stores whose steps read it. Context a
    /// recovery loop injects is read through the root `_recovery`.
    readers: Option<HashMap<String, Vec<String>>>,
    taints: HashMap<Vec<String>, HashMap<String, Path>>,
}

impl<'a> Independence<'a> {
    pub(crate) fn new(steps: &'a [Value]) -> Independence<'a> {
        Independence {
            steps,
            readers: None,
            taints: HashMap::new(),
        }
    }

    fn build_readers(steps: &[Value]) -> HashMap<String, Vec<String>> {
        let mut readers: HashMap<String, Vec<String>> = HashMap::new();
        let mut injected = Vec::new();
        for step in steps.iter().filter_map(Value::as_object) {
            for fm in step
                .get("failure_modes")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
            {
                if let Some(inject) = fm.get("recovery").and_then(|r| r.get("inject_context")) {
                    collect_roots(inject, &mut injected, 0);
                }
            }
            // Every step with a name counts, duplicates included: reading a
            // name may read either of them.
            let Some(store) = step.get("store_as").and_then(Value::as_str) else {
                continue;
            };
            let mut roots = Vec::new();
            if let Some(b) = step.get("input_bindings") {
                collect_roots(b, &mut roots, 0);
            }
            for r in roots {
                readers.entry(r).or_default().push(store.to_string());
            }
        }
        for r in injected {
            readers
                .entry(r)
                .or_default()
                .push(super::recovery::RECOVERY_ROOT.to_string());
        }
        readers
    }

    /// Every store that depends, directly or transitively, on one of
    /// `forbidden`, with the next hop towards it: a breadth-first pass over
    /// the readers, linear in the bindings and safe on cycles.
    fn taint(&mut self, forbidden: &HashSet<&str>) -> &HashMap<String, Path> {
        let mut key: Vec<String> = forbidden.iter().map(|f| f.to_string()).collect();
        key.sort_unstable();
        let steps = self.steps;
        let readers = self
            .readers
            .get_or_insert_with(|| Self::build_readers(steps));
        self.taints.entry(key).or_insert_with_key(|key| {
            let mut paths: HashMap<String, Path> = HashMap::new();
            let mut queue: std::collections::VecDeque<String> = VecDeque::new();
            for f in key {
                paths.insert(
                    f.clone(),
                    Path {
                        via: f.clone(),
                        forbidden: f.clone(),
                    },
                );
                queue.push_back(f.clone());
            }
            while let Some(r) = queue.pop_front() {
                let end = paths[&r].forbidden.clone();
                for s in readers.get(&r).into_iter().flatten() {
                    if !paths.contains_key(s) {
                        paths.insert(
                            s.clone(),
                            Path {
                                via: r.clone(),
                                forbidden: end.clone(),
                            },
                        );
                        queue.push_back(s.clone());
                    }
                }
            }
            paths
        })
    }
}

/// Where a store's dependency on a forbidden store goes: the store it
/// reads on the way, and the forbidden store at the end.
struct Path {
    via: String,
    forbidden: String,
}

fn collect_roots(v: &Value, out: &mut Vec<String>, depth: usize) {
    if depth > 64 {
        return;
    }
    match v {
        Value::String(s) => out.extend(
            refs::find_refs(s)
                .into_iter()
                .filter_map(|m| m.parsed.ok())
                .map(|r| r.root),
        ),
        Value::Array(a) => a.iter().for_each(|x| collect_roots(x, out, depth + 1)),
        Value::Object(m) => m.values().for_each(|x| collect_roots(x, out, depth + 1)),
        _ => {}
    }
}

/// A list of distinct strings, or S303.
fn strings<'v>(
    q: &'v Map<String, Value>,
    key: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> Option<Vec<&'v str>> {
    let field = format!("quorum.{key}");
    let v = q.get(key)?;
    let Some(items) = v
        .as_array()
        .and_then(|a| a.iter().map(Value::as_str).collect::<Option<Vec<&str>>>())
    else {
        report.push(s303(
            at,
            &field,
            format!(
                "{field} must be a list of strings, found {}",
                yaml::kind_of(v)
            ),
        ));
        return None;
    };
    let unique: HashSet<&str> = items.iter().copied().collect();
    if unique.len() != items.len() {
        report.push(s303(at, &field, format!("{field} lists a value twice")));
    }
    Some(items)
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn check(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    earlier: &Earlier<'_>,
    independence: &mut Independence<'_>,
    declared: &Declared,
    checker: &Checker<'_>,
    scope: &Scope,
    report: &mut Report,
) {
    let Some(value) = step.get("quorum") else {
        return;
    };
    if !declared.require(
        "quorum@1",
        "'quorum'",
        |d| loc.locate(d).at("field", "quorum"),
        report,
    ) {
        return;
    }
    let at = |d: Diagnostic| loc.locate(d);
    let Value::Object(q) = value else {
        report.push(s303(
            &at,
            "quorum",
            format!("'quorum' must be a mapping, found {}", yaml::kind_of(value)),
        ));
        return;
    };
    let blocks = step
        .get("input_bindings")
        .and_then(|b| b.get("action_on_violation"))
        .and_then(Value::as_str)
        == Some("block");
    if loc.capability != "constrain" || !blocks {
        report.push(s303(
            &at,
            "quorum",
            "'quorum' belongs on a constrain step that binds action_on_violation: block, so a failed quorum stops the run".into(),
        ));
    }
    semantics::unknown_fields(q, QUORUM_KEYS, "quorum", &at, report);
    for key in REQUIRED.iter().filter(|k| !q.contains_key(**k)) {
        report.push(s304(
            &at,
            &format!("quorum.{key}"),
            format!("quorum has no '{key}'"),
        ));
    }
    for key in ["verdicts", "pinned_to"] {
        if let Some(v) = q.get(key) {
            let field = format!("quorum.{key}");
            if wait::references(v, &field, &at, report) {
                checker.scan(v, scope, Mode::Existence, &field, report);
            }
        }
    }

    let mut reviewers = strings(q, "reviewers", &at, report).unwrap_or_default();
    // A duplicate is reported once (S303), then counted once.
    let mut seen = HashSet::new();
    reviewers.retain(|r| seen.insert(*r));
    if q.contains_key("reviewers") && reviewers.is_empty() && q["reviewers"].is_array() {
        report.push(s303(
            &at,
            "quorum.reviewers",
            "quorum.reviewers is empty".into(),
        ));
    }
    let mut delegates: Vec<(&str, &Map<String, Value>)> = Vec::new();
    for r in &reviewers {
        let problem = match earlier.step(r) {
            None => Some("is no earlier step's store_as"),
            Some(s) if s.get("capability").and_then(Value::as_str) != Some("delegate") => {
                Some("is not a delegate step")
            }
            Some(s) if earlier.concurrent(s) => {
                Some("runs alongside this step (same parallel_group), so its review is not in yet")
            }
            Some(s) => {
                delegates.push((r, s));
                None
            }
        };
        if let Some(problem) = problem {
            report.push(
                at(Diagnostic::new(
                    Code::UnresolvedTarget,
                    format!("quorum.reviewers: '{r}' {problem}"),
                ))
                .at("field", "quorum.reviewers"),
            );
        }
    }

    // A verdict counts once per agent, so reviewers must be distinct
    // agents; literal ones can be checked now.
    let mut agents: HashMap<&str, &str> = HashMap::new();
    for (r, s) in &delegates {
        let agent = s
            .get("input_bindings")
            .and_then(|b| b.get("agent"))
            .and_then(Value::as_str)
            .filter(|a| !a.contains("${"));
        if let Some(agent) = agent {
            match agents.entry(agent) {
                Entry::Vacant(v) => {
                    v.insert(r);
                }
                Entry::Occupied(first) => report.push(
                    at(Diagnostic::new(
                        Code::ConstraintViolated,
                        format!(
                            "reviewers '{}' and '{r}' both delegate to agent '{agent}'; a verdict counts once per agent",
                            first.get()
                        ),
                    ))
                    .at("field", "quorum.reviewers"),
                ),
            }
        }
    }
    vocabulary(q, reviewers.len(), &at, report);

    if let Some(forbidden) = strings(q, "forbidden_inputs", &at, report) {
        let known: HashSet<&str> = forbidden
            .iter()
            .copied()
            .filter(|f| {
                earlier.step(f).is_some_and(|s| !earlier.concurrent(s))
                    || scope.inputs.contains_key(*f)
            })
            .collect();
        for f in forbidden.iter().filter(|f| !known.contains(**f)) {
            report.push(
                at(Diagnostic::new(
                    Code::UnresolvedTarget,
                    format!(
                        "quorum.forbidden_inputs: '{f}' is neither an input nor the store_as of a step that runs before this one"
                    ),
                ))
                .at("field", "quorum.forbidden_inputs"),
            );
        }
        let paths = independence.taint(&known);
        for (r, _) in &delegates {
            let how = if known.contains(r) {
                Some(format!("reviewer '{r}' is itself a forbidden input"))
            } else {
                paths.get(*r).map(|p| {
                    let via = if p.via == p.forbidden {
                        String::new()
                    } else {
                        format!(" through '{}'", p.via)
                    };
                    format!(
                        "reviewer '{r}' reads forbidden input '{}'{via}",
                        p.forbidden
                    )
                })
            };
            if let Some(how) = how {
                report.push(
                    at(Diagnostic::new(
                        Code::ConstraintViolated,
                        format!("{how}, so its review is not independent"),
                    ))
                    .at("field", "quorum.forbidden_inputs"),
                );
            }
        }
    }

    match q.get("require_fresh_context") {
        None | Some(Value::Bool(false)) => {}
        Some(Value::Bool(true)) => {
            for (r, s) in &delegates {
                let fresh = s.get("input_bindings").and_then(|b| b.get("fresh_context"));
                if fresh != Some(&Value::Bool(true)) {
                    report.push(
                        at(Diagnostic::new(
                            Code::ConstraintViolated,
                            format!("reviewer '{r}' does not bind fresh_context: true"),
                        ))
                        .at("field", "quorum.require_fresh_context"),
                    );
                }
            }
        }
        Some(other) => report.push(s303(
            &at,
            "quorum.require_fresh_context",
            format!(
                "quorum.require_fresh_context must be a boolean, found {}",
                yaml::kind_of(other)
            ),
        )),
    }

    if let Some(families) = strings(q, "require_model_families", &at, report) {
        // Literal model families can be checked now; any other reviewer's
        // family is only known at runtime.
        let literal: Option<HashSet<&str>> = delegates
            .iter()
            .map(|(_, s)| {
                s.get("input_bindings")
                    .and_then(|b| b.get("model_family"))
                    .and_then(Value::as_str)
                    .filter(|f| !f.contains("${"))
            })
            .collect();
        if let Some(have) = literal {
            let missing: Vec<&str> = families
                .iter()
                .copied()
                .filter(|f| !have.contains(f))
                .collect();
            if !missing.is_empty() && !delegates.is_empty() && delegates.len() == reviewers.len() {
                report.push(
                    at(Diagnostic::new(
                        Code::ConstraintViolated,
                        format!(
                            "no reviewer binds model family {}; require_model_families cannot be met",
                            missing.join(", ")
                        ),
                    ))
                    .at("field", "quorum.require_model_families"),
                );
            }
        }
    }
}

/// vocabulary, pass_values, blocking_values and min_pass (S303).
fn vocabulary(
    q: &Map<String, Value>,
    reviewers: usize,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let listed = strings(q, "vocabulary", at, report);
    let vocab: HashSet<&str> = listed.iter().flatten().copied().collect();
    if listed.is_some() && vocab.len() < 2 {
        report.push(s303(
            at,
            "quorum.vocabulary",
            "quorum.vocabulary needs at least two distinct values".into(),
        ));
    }
    let pass = strings(q, "pass_values", at, report).unwrap_or_default();
    let block = strings(q, "blocking_values", at, report).unwrap_or_default();
    if q.contains_key("pass_values") && pass.is_empty() && q["pass_values"].is_array() {
        report.push(s303(
            at,
            "quorum.pass_values",
            "quorum.pass_values is empty".into(),
        ));
    }
    for (key, values) in [("pass_values", &pass), ("blocking_values", &block)] {
        for v in values
            .iter()
            .filter(|v| !vocab.is_empty() && !vocab.contains(**v))
        {
            report.push(s303(
                at,
                &format!("quorum.{key}"),
                format!("quorum.{key}: '{v}' is not in the vocabulary"),
            ));
        }
    }
    for v in block.iter().filter(|v| pass.contains(v)) {
        report.push(s303(
            at,
            "quorum.blocking_values",
            format!("quorum.blocking_values: '{v}' is also a pass value"),
        ));
    }
    if let Some(n) = q.get("min_pass") {
        let ok = count(n).is_some_and(|n| n >= 1 && (reviewers == 0 || n <= reviewers as u64));
        if !ok {
            report.push(s303(
                at,
                "quorum.min_pass",
                format!(
                    "quorum.min_pass must be an integer from 1 to the number of reviewers ({reviewers}), found {n}"
                ),
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::super::tests::codes;

    fn catalog(steps: Value, requires: &[&str]) -> Value {
        json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
                     "inputs": {"author_notes": {"type": "string"}},
                     "workflow_extensions": {"requires": requires},
                     "steps": steps}})
    }

    fn reviewer(store: &str, agent: &str, family: &str, extra: Value) -> Value {
        let mut bindings = json!({"task": {"diff": "${diff}"}, "agent": agent,
                                  "fresh_context": true, "model_family": family});
        for (k, v) in extra.as_object().unwrap() {
            bindings[k] = v.clone();
        }
        json!({"capability": "delegate", "purpose": "p", "store_as": store,
               "input_bindings": bindings})
    }

    fn quorum() -> Value {
        json!({"verdicts": "${verdicts.data}", "reviewers": ["ra", "rb"],
               "vocabulary": ["approve", "request_changes", "abstain"],
               "pass_values": ["approve"], "blocking_values": ["request_changes"],
               "min_pass": 2, "pinned_to": "${diff.data}",
               "forbidden_inputs": ["author_notes"],
               "require_fresh_context": true,
               "require_model_families": ["claude", "gpt"]})
    }

    fn gate(q: Value) -> Value {
        json!({"capability": "constrain", "purpose": "p", "store_as": "gate",
               "input_bindings": {"target": "${verdicts.data}", "constraints": ["c"],
                                  "action_on_violation": "block"},
               "quorum": q})
    }

    fn steps(ra: Value, rb: Value, q: Value) -> Value {
        json!([
            {"capability": "retrieve", "purpose": "p", "store_as": "diff",
             "input_bindings": {"target": "changes/1"}},
            ra,
            rb,
            {"capability": "receive", "purpose": "p", "store_as": "verdicts",
             "input_bindings": {"accept_from": ["a", "b"]}},
            gate(q)
        ])
    }

    fn run_with(ra: Value, rb: Value, q: Value) -> Vec<&'static str> {
        codes(catalog(steps(ra, rb, q), &["delegation@1", "quorum@1"]))
    }

    fn run(q: Value) -> Vec<&'static str> {
        run_with(
            reviewer("ra", "a", "claude", json!({})),
            reviewer("rb", "b", "gpt", json!({})),
            q,
        )
    }

    fn with(changes: Value) -> Value {
        let mut q = quorum();
        for (k, v) in changes.as_object().unwrap() {
            if v.is_null() {
                q.as_object_mut().unwrap().remove(k);
            } else {
                q[k] = v.clone();
            }
        }
        q
    }

    #[test]
    fn a_valid_quorum() {
        assert_eq!(run(quorum()), Vec::<&str>::new());
    }

    #[test]
    fn placement() {
        let mut s = steps(
            reviewer("ra", "a", "claude", json!({})),
            reviewer("rb", "b", "gpt", json!({})),
            quorum(),
        );
        s[4]["input_bindings"]["action_on_violation"] = json!("warn");
        assert_eq!(
            codes(catalog(s.clone(), &["delegation@1", "quorum@1"])),
            ["S303"]
        );
        s[4]["capability"] = json!("verify");
        s[4]["input_bindings"] = json!({"target": "${verdicts.data}", "conditions": ["c"]});
        assert_eq!(codes(catalog(s, &["delegation@1", "quorum@1"])), ["S303"]);
        let undeclared = codes(catalog(
            steps(
                reviewer("ra", "a", "claude", json!({})),
                reviewer("rb", "b", "gpt", json!({})),
                quorum(),
            ),
            &["delegation@1"],
        ));
        assert_eq!(undeclared, ["V106"]);
    }

    #[test]
    fn structure() {
        assert_eq!(run(json!("two approvals")), ["S303"]);
        assert_eq!(
            run(with(json!({"min_pass": null, "pinned_to": null}))),
            ["S304", "S304"]
        );
        assert_eq!(
            run(with(
                json!({"vocabulary": ["approve"], "pass_values": ["approve"],
                                     "blocking_values": []})
            )),
            ["S303"]
        );
        assert_eq!(run(with(json!({"pass_values": ["ship_it"]}))), ["S303"]);
        assert_eq!(run(with(json!({"pass_values": []}))), ["S303"]);
        assert_eq!(run(with(json!({"blocking_values": ["approve"]}))), ["S303"]);
        assert_eq!(run(with(json!({"min_pass": 3}))), ["S303"]);
        assert_eq!(run(with(json!({"min_pass": 0}))), ["S303"]);
        assert_eq!(
            run(with(json!({"vocabulary": ["a", "a", "b"],
                                     "pass_values": ["a"], "blocking_values": ["b"]}))),
            ["S303"]
        );
        assert_eq!(run(with(json!({"verdicts": "${nope}"}))), ["B202"]);
        assert_eq!(run(with(json!({"pinned_to": ["x"]}))), ["S303"]);
        assert_eq!(run(with(json!({"pinned_to": "main"}))), ["S303"]);
        assert_eq!(run(with(json!({"quorate": true}))), ["W604"]);
    }

    #[test]
    fn reviewers_are_earlier_delegates() {
        assert_eq!(
            run(with(json!({"reviewers": ["ra", "nobody"], "min_pass": 1}))),
            ["V107"]
        );
        assert_eq!(
            run(with(json!({"reviewers": ["ra", "diff"], "min_pass": 1}))),
            ["V107"]
        );
        assert_eq!(run(with(json!({"reviewers": [], "min_pass": 1}))), ["S303"]);
        // Two reviewers that are the same agent count once.
        assert_eq!(
            run_with(
                reviewer("ra", "a", "claude", json!({})),
                reviewer("rb", "a", "gpt", json!({})),
                quorum()
            ),
            ["F504"]
        );
        // A reviewer running alongside the quorum has not reported yet.
        let mut s = steps(
            reviewer("ra", "a", "claude", json!({})),
            reviewer("rb", "b", "gpt", json!({})),
            quorum(),
        );
        s[2]["parallel_group"] = json!("g");
        s[4]["parallel_group"] = json!("g");
        let c = codes(catalog(s, &["delegation@1", "quorum@1"]));
        assert!(c.contains(&"V107"), "{c:?}");
    }

    #[test]
    fn independence() {
        // A reviewer that reads the author's notes is not independent,
        // directly or through another step.
        let direct = reviewer(
            "rb",
            "b",
            "gpt",
            json!({"task": {"notes": "${author_notes}"}}),
        );
        assert_eq!(
            run_with(reviewer("ra", "a", "claude", json!({})), direct, quorum()),
            ["F504"]
        );
        let mut s = steps(
            reviewer("ra", "a", "claude", json!({})),
            reviewer("rb", "b", "gpt", json!({"task": {"s": "${summary}"}})),
            quorum(),
        );
        s.as_array_mut().unwrap().insert(
            1,
            json!({"capability": "transform", "purpose": "p", "store_as": "summary",
                   "input_bindings": {"source": "${author_notes}", "target_schema": "s"}}),
        );
        let c = codes(catalog(s, &["delegation@1", "quorum@1"]));
        assert_eq!(c.iter().filter(|c| **c == "F504").count(), 1, "{c:?}");
        assert_eq!(
            run(with(json!({"forbidden_inputs": ["nothing"]}))),
            ["V107"]
        );
        // Fresh context and model families, when bound literally.
        assert_eq!(
            run_with(
                reviewer("ra", "a", "claude", json!({"fresh_context": false})),
                reviewer("rb", "b", "gpt", json!({})),
                quorum()
            ),
            ["F504"]
        );
        assert_eq!(
            run_with(
                reviewer("ra", "a", "claude", json!({})),
                reviewer("rb", "b", "claude", json!({})),
                quorum()
            ),
            ["F504"]
        );
        // A family known only at runtime is checked then.
        assert_eq!(
            run_with(
                reviewer("ra", "a", "claude", json!({})),
                reviewer("rb", "b", "${diff.data: string}", json!({})),
                quorum()
            ),
            Vec::<&str>::new()
        );
    }

    #[test]
    fn independence_checks_scale_linearly() {
        // A long chain every reviewer depends on, and many reviewers.
        let n = 3_000;
        let mut s = vec![
            json!({"capability": "retrieve", "purpose": "p", "store_as": "c0",
                                "input_bindings": {"target": "${author_notes}"}}),
        ];
        for i in 1..n {
            s.push(json!({"capability": "retrieve", "purpose": "p",
                          "store_as": format!("c{i}"),
                          "input_bindings": {"target": format!("${{c{}.data}}", i - 1)}}));
        }
        let mut names = Vec::new();
        for i in 0..n {
            let mut r = reviewer(&format!("r{i}"), &format!("agent{i}"), "claude", json!({}));
            r["input_bindings"]["task"] = json!({"x": format!("${{c{}.data}}", n - 1)});
            s.push(r);
            names.push(format!("r{i}"));
        }
        s.push(json!({"capability": "receive", "purpose": "p", "store_as": "verdicts"}));
        s.push(gate(with(json!({"reviewers": names, "min_pass": 1,
                                 "pinned_to": "${c0.data}",
                                 "require_model_families": null}))));
        let start = std::time::Instant::now();
        let c = codes(catalog(Value::Array(s), &["delegation@1", "quorum@1"]));
        assert_eq!(c.iter().filter(|c| **c == "F504").count(), n);
        assert!(
            start.elapsed() < std::time::Duration::from_secs(5),
            "{:?}",
            start.elapsed()
        );
    }

    #[test]
    fn injected_context_counts_as_a_read() {
        // A recovery loop hands the author's notes to a reviewer on retry.
        let mut s = steps(
            reviewer(
                "ra",
                "a",
                "claude",
                json!({"task": {"why": "${_recovery.why: string}"}}),
            ),
            reviewer("rb", "b", "gpt", json!({})),
            quorum(),
        );
        s[4]["failure_modes"] = json!([{
            "condition": "the quorum failed", "action": "stop",
            "when": "${gate.compliant} == false",
            "recovery": {"goto_step": "ra", "inject_context": {"why": "${author_notes}"},
                         "max_loops": 2}
        }]);
        let c = codes(catalog(s, &["delegation@1", "quorum@1"]));
        assert_eq!(c, ["F504"]);
    }

    #[test]
    fn many_quorum_steps_scale_linearly() {
        let n = 2_000;
        let mut s = vec![
            json!({"capability": "retrieve", "purpose": "p", "store_as": "c0",
                                "input_bindings": {"target": "${author_notes}"}}),
        ];
        for i in 1..n {
            s.push(json!({"capability": "retrieve", "purpose": "p",
                          "store_as": format!("c{i}"),
                          "input_bindings": {"target": format!("${{c{}.data}}", i - 1)}}));
        }
        let mut r = reviewer("ra", "a", "claude", json!({}));
        r["input_bindings"]["task"] = json!({"x": format!("${{c{}.data}}", n - 1)});
        s.push(r);
        s.push(json!({"capability": "receive", "purpose": "p", "store_as": "verdicts"}));
        for i in 0..n {
            let mut g = gate(with(json!({"reviewers": ["ra"], "min_pass": 1,
                                         "pinned_to": "${c0.data}",
                                         "require_model_families": null})));
            g["store_as"] = json!(format!("gate{i}"));
            s.push(g);
        }
        let start = std::time::Instant::now();
        let c = codes(catalog(Value::Array(s), &["delegation@1", "quorum@1"]));
        assert_eq!(c.iter().filter(|c| **c == "F504").count(), n);
        assert!(
            start.elapsed() < std::time::Duration::from_secs(5),
            "{:?}",
            start.elapsed()
        );
    }

    #[test]
    fn cycles_do_not_hide_dependencies() {
        // Forward references (B202) make a cycle; both reviewers still
        // reach the notes.
        let mut s = steps(
            reviewer("ra", "a", "claude", json!({"task": {"y": "${y.output}"}})),
            reviewer("rb", "b", "gpt", json!({"task": {"z": "${z.output}"}})),
            quorum(),
        );
        s.as_array_mut().unwrap().insert(
            1,
            json!({"capability": "transform", "purpose": "p", "store_as": "y",
                   "input_bindings": {"input": ["${z.output}", "${author_notes}"],
                                      "target_format": "f"}}),
        );
        s.as_array_mut().unwrap().insert(
            2,
            json!({"capability": "transform", "purpose": "p", "store_as": "z",
                   "input_bindings": {"input": "${y.output}", "target_format": "f"}}),
        );
        let c = codes(catalog(s, &["delegation@1", "quorum@1"]));
        assert_eq!(c.iter().filter(|c| **c == "F504").count(), 2, "{c:?}");
    }

    #[test]
    fn malformed_lists_are_reported_once() {
        // A duplicate reviewer: one S303, and the reviewer judged once.
        assert_eq!(
            run_with(
                reviewer("ra", "a", "claude", json!({"fresh_context": false})),
                reviewer("rb", "b", "gpt", json!({})),
                with(json!({"reviewers": ["ra", "ra", "rb"]}))
            ),
            ["S303", "F504"]
        );
        assert_eq!(run(with(json!({"vocabulary": "approve"}))), ["S303"]);
        assert_eq!(
            run(with(json!({"forbidden_inputs": "author_notes"}))),
            ["S303"]
        );
        assert_eq!(
            run(with(json!({"require_model_families": "claude"}))),
            ["S303"]
        );
        assert_eq!(run(with(json!({"require_fresh_context": "yes"}))), ["S303"]);
        assert_eq!(run(with(json!({"min_pass": 2.0}))), Vec::<&str>::new());
    }

    #[test]
    fn three_reviewers_on_one_agent_name_the_first() {
        let mut s = steps(
            reviewer("ra", "a", "claude", json!({})),
            reviewer("rb", "a", "gpt", json!({})),
            with(json!({"reviewers": ["ra", "rb", "rc"]})),
        );
        s.as_array_mut()
            .unwrap()
            .insert(3, reviewer("rc", "a", "gpt", json!({})));
        let report = super::super::validate_catalog(
            &super::super::tests::ctx(),
            &catalog(s, &["delegation@1", "quorum@1"]),
            None,
        );
        let messages: Vec<&str> = report
            .diagnostics
            .iter()
            .filter(|d| d.code.as_str() == "F504")
            .map(|d| d.message.as_str())
            .collect();
        assert_eq!(messages.len(), 2, "{messages:?}");
        assert!(messages.iter().all(|m| m.starts_with("reviewers 'ra' and")));
    }

    #[test]
    fn forbidden_inputs_must_run_before() {
        let mut s = steps(
            reviewer("ra", "a", "claude", json!({})),
            reviewer("rb", "b", "gpt", json!({})),
            with(json!({"forbidden_inputs": ["side"]})),
        );
        s.as_array_mut().unwrap().insert(
            4,
            json!({"capability": "retrieve", "purpose": "p", "store_as": "side",
                   "parallel_group": "g", "input_bindings": {"target": "t"}}),
        );
        s[5]["parallel_group"] = json!("g");
        assert_eq!(codes(catalog(s, &["delegation@1", "quorum@1"])), ["V107"]);
    }
}
