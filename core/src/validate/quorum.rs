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
    "require_read_only",
    "require_model_families",
    "min_full",
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
/// stores each distinct list of forbidden inputs taints, so many quorum
/// steps cost one pass per distinct list rather than one walk each.
pub(crate) struct Independence<'a> {
    steps: &'a [Value],
    /// Root (store or input) → the stores whose steps read it. Context a
    /// recovery loop injects is read through the root `_recovery`.
    readers: Option<HashMap<String, Vec<String>>>,
    /// Store → the roots its steps read, in document order: `readers`
    /// reversed, for walks from one reviewer.
    reads: Option<HashMap<String, Vec<String>>>,
    taints: HashMap<Vec<String>, HashMap<String, Path>>,
}

impl<'a> Independence<'a> {
    pub(crate) fn new(steps: &'a [Value]) -> Independence<'a> {
        Independence {
            steps,
            readers: None,
            reads: None,
            taints: HashMap::new(),
        }
    }

    /// Store → roots read, as `build_readers` sees them (every step with a
    /// name, duplicates included; injected context under `_recovery`).
    fn build_reads(steps: &[Value]) -> HashMap<String, Vec<String>> {
        let mut reads: HashMap<String, Vec<String>> = HashMap::new();
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
            let Some(store) = step.get("store_as").and_then(Value::as_str) else {
                continue;
            };
            let roots = reads.entry(store.to_string()).or_default();
            if let Some(b) = step.get("input_bindings") {
                collect_roots(b, roots, 0);
            }
        }
        reads
            .entry(super::recovery::RECOVERY_ROOT.to_string())
            .or_default()
            .extend(injected);
        reads
    }

    /// Whether `reviewer` depends, directly or transitively, on one of
    /// `forbidden`: a breadth-first walk over what it reads, so the nearest
    /// forbidden root is found, with the root the reviewer reads on the
    /// way. Nothing is cached: each call is linear in the bindings.
    fn reaches(&mut self, reviewer: &str, forbidden: &HashSet<&str>) -> Option<Path> {
        let steps = self.steps;
        let reads = self.reads.get_or_insert_with(|| Self::build_reads(steps));
        let mut seen: HashSet<&str> = HashSet::new();
        let mut queue: VecDeque<(&str, &str)> = VecDeque::new();
        for r in reads.get(reviewer).into_iter().flatten() {
            if seen.insert(r) {
                queue.push_back((r, r));
            }
        }
        while let Some((node, via)) = queue.pop_front() {
            if forbidden.contains(node) {
                return Some(Path {
                    via: via.to_string(),
                    forbidden: node.to_string(),
                });
            }
            for r in reads.get(node).into_iter().flatten() {
                if seen.insert(r) {
                    queue.push_back((r, via));
                }
            }
        }
        None
    }

    /// Whether any of `roots` is one of `targets` or depends on one through
    /// bindings, directly or transitively.
    pub(crate) fn reads_any(&mut self, roots: &[String], targets: &HashSet<&str>) -> bool {
        roots
            .iter()
            .any(|r| targets.contains(r.as_str()) || self.reaches(r, targets).is_some())
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
#[derive(Clone)]
struct Path {
    via: String,
    forbidden: String,
}

pub(crate) fn collect_roots(v: &Value, out: &mut Vec<String>, depth: usize) {
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
    string_list(q.get(key)?, &format!("quorum.{key}"), at, report)
}

/// `v` as a list of distinct strings, or S303 at `field`.
fn string_list<'v>(
    v: &'v Value,
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> Option<Vec<&'v str>> {
    let Some(items) = v
        .as_array()
        .and_then(|a| a.iter().map(Value::as_str).collect::<Option<Vec<&str>>>())
    else {
        report.push(s303(
            at,
            field,
            format!(
                "{field} must be a list of strings, found {}",
                yaml::kind_of(v)
            ),
        ));
        return None;
    };
    let unique: HashSet<&str> = items.iter().copied().collect();
    if unique.len() != items.len() {
        report.push(s303(at, field, format!("{field} lists a value twice")));
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
            // Verdicts may come from several steps (one per reviewer that
            // waits for its result): a non-empty list of references.
            let parts: Vec<(String, &Value)> = match v {
                Value::Array(items) if key == "verdicts" && !items.is_empty() => items
                    .iter()
                    .enumerate()
                    .map(|(i, x)| (format!("{field}[{i}]"), x))
                    .collect(),
                _ => vec![(field.clone(), v)],
            };
            for (f, x) in parts {
                if wait::references(x, &f, &at, report) {
                    checker.scan(x, scope, Mode::Existence, &f, report);
                }
            }
        }
    }

    let parsed = strings(q, "reviewers", &at, report);
    let mut reviewers = parsed.clone().unwrap_or_default();
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
    // Bound min_pass and min_full by the reviewers as listed: a duplicate is
    // already S303, and should not also make a bound look unreachable.
    vocabulary(q, parsed.as_ref().map_or(0, Vec::len), &at, report);

    forbidden_inputs(
        q,
        parsed.is_some().then_some(reviewers.as_slice()),
        &delegates,
        earlier,
        independence,
        scope,
        &at,
        report,
    );

    for (requirement, input) in [
        ("require_fresh_context", "fresh_context"),
        ("require_read_only", "read_only"),
    ] {
        let field = format!("quorum.{requirement}");
        match q.get(requirement) {
            None | Some(Value::Bool(false)) => {}
            Some(Value::Bool(true)) => {
                for (r, s) in &delegates {
                    let bound = s.get("input_bindings").and_then(|b| b.get(input));
                    if bound != Some(&Value::Bool(true)) {
                        report.push(
                            at(Diagnostic::new(
                                Code::ConstraintViolated,
                                format!("reviewer '{r}' does not bind {input}: true"),
                            ))
                            .at("field", field.clone()),
                        );
                    }
                }
            }
            Some(other) => report.push(s303(
                &at,
                &field,
                format!("{field} must be a boolean, found {}", yaml::kind_of(other)),
            )),
        }
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

/// `forbidden_inputs`: a list every reviewer must be independent of, or a
/// mapping of reviewers to their own lists. Names must be inputs or stores
/// of steps that run before the quorum step (V107); a reviewer that
/// depends on one of its forbidden names, directly or through bindings, is
/// F504.
///
/// A list is one forbidden set for every reviewer, propagated once (and
/// cached across quorum steps). A mapping can give every reviewer its own
/// set, so each reviewer is checked by a forward walk over what it reads,
/// with nothing kept afterwards: O(reviewers × bindings) time, O(bindings)
/// memory.
#[allow(clippy::too_many_arguments)]
fn forbidden_inputs(
    q: &Map<String, Value>,
    reviewers: Option<&[&str]>,
    delegates: &[(&str, &Map<String, Value>)],
    earlier: &Earlier<'_>,
    independence: &mut Independence<'_>,
    scope: &Scope,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let field = "quorum.forbidden_inputs";
    let resolves = |f: &str| {
        earlier.step(f).is_some_and(|s| !earlier.concurrent(s)) || scope.inputs.contains_key(f)
    };
    // Every name must resolve; each unresolved one is reported once, where
    // it is listed.
    let mut reported = HashSet::new();
    let mut unresolved = |names: &[&str], at_field: &str, report: &mut Report| {
        for f in names.iter().copied().filter(|f| !resolves(f)) {
            if reported.insert(f.to_string()) {
                report.push(
                    at(Diagnostic::new(
                        Code::UnresolvedTarget,
                        format!(
                            "{field}: '{f}' is neither an input nor the store_as of a step that runs before this one"
                        ),
                    ))
                    .at("field", at_field.to_string()),
                );
            }
        }
    };
    let independent = |r: &str, found: Option<Path>, report: &mut Report| {
        let Some(p) = found else {
            return;
        };
        let how = if p.via == r {
            format!("reviewer '{r}' is itself a forbidden input")
        } else if p.via == p.forbidden {
            format!("reviewer '{r}' reads forbidden input '{}'", p.forbidden)
        } else {
            format!(
                "reviewer '{r}' reads forbidden input '{}' through '{}'",
                p.forbidden, p.via
            )
        };
        report.push(
            at(Diagnostic::new(
                Code::ConstraintViolated,
                format!("{how}, so its review is not independent"),
            ))
            .at("field", field),
        );
    };
    let itself = |r: &str| Path {
        via: r.to_string(),
        forbidden: r.to_string(),
    };
    match q.get("forbidden_inputs") {
        None => {}
        Some(Value::Array(_)) => {
            let Some(names) = strings(q, "forbidden_inputs", at, report) else {
                return;
            };
            unresolved(&names, field, report);
            let known: HashSet<&str> = names.iter().copied().filter(|f| resolves(f)).collect();
            if known.is_empty() {
                return;
            }
            let paths = independence.taint(&known);
            let found: Vec<(&str, Option<Path>)> = delegates
                .iter()
                .map(|(r, _)| {
                    let p = if known.contains(r) {
                        Some(itself(r))
                    } else {
                        paths.get(*r).cloned()
                    };
                    (*r, p)
                })
                .collect();
            for (r, p) in found {
                independent(r, p, report);
            }
        }
        Some(Value::Object(map)) => {
            let mut lists: HashMap<&str, Vec<&str>> = HashMap::new();
            for (r, list) in map {
                let entry = format!("{field}.{r}");
                // Keys are checked only against a well-formed reviewers list.
                if reviewers.is_some_and(|rs| !rs.contains(&r.as_str())) {
                    report.push(
                        at(Diagnostic::new(
                            Code::UnresolvedTarget,
                            format!("{field}: '{r}' is not one of the quorum's reviewers"),
                        ))
                        .at("field", entry.clone()),
                    );
                }
                if let Some(names) = string_list(list, &entry, at, report) {
                    unresolved(&names, &entry, report);
                    lists.insert(r.as_str(), names);
                }
            }
            for (r, _) in delegates {
                let Some(list) = lists.get(r) else {
                    continue;
                };
                let known: HashSet<&str> = list.iter().copied().filter(|f| resolves(f)).collect();
                if known.is_empty() {
                    continue;
                }
                let p = if known.contains(r) {
                    Some(itself(r))
                } else {
                    independence.reaches(r, &known)
                };
                independent(r, p, report);
            }
        }
        Some(other) => report.push(s303(
            at,
            field,
            format!(
                "{field} must be a list of names, or a mapping of reviewers to lists, found {}",
                yaml::kind_of(other)
            ),
        )),
    }
}

/// vocabulary, pass_values, blocking_values, min_pass and min_full (S303).
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
    for key in ["min_pass", "min_full"] {
        let Some(n) = q.get(key) else {
            continue;
        };
        let ok = count(n).is_some_and(|n| n >= 1 && (reviewers == 0 || n <= reviewers as u64));
        if !ok {
            report.push(s303(
                at,
                &format!("quorum.{key}"),
                format!(
                    "quorum.{key} must be an integer from 1 to the number of reviewers ({reviewers}), found {n}"
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
    fn read_only_reviewers() {
        let ro = json!({"read_only": true});
        assert!(
            run_with(
                reviewer("ra", "a", "claude", ro.clone()),
                reviewer("rb", "b", "gpt", ro.clone()),
                with(json!({"require_read_only": true}))
            )
            .is_empty()
        );
        assert_eq!(
            run_with(
                reviewer("ra", "a", "claude", ro.clone()),
                reviewer("rb", "b", "gpt", json!({})),
                with(json!({"require_read_only": true}))
            ),
            ["F504"]
        );
        assert_eq!(run(with(json!({"require_read_only": "yes"}))), ["S303"]);
    }

    #[test]
    fn verdicts_from_several_steps() {
        // One reference per reviewer step that waits for its result.
        assert!(
            run(with(
                json!({"verdicts": ["${ra.result: object}", "${rb.result: object}"]})
            ))
            .is_empty()
        );
        assert_eq!(run(with(json!({"verdicts": []}))), ["S303"]);
        assert_eq!(
            run(with(json!({"verdicts": ["${ra.result}", "ra"]}))),
            ["S303"]
        );
        assert_eq!(run(with(json!({"verdicts": ["${nope}"]}))), ["B202"]);
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
    fn independence_per_reviewer() {
        // Reviewer a verifies fixes and may read the earlier round; b
        // reviews fresh and must not.
        let reads = |r: &str, a: &str, f: &str| {
            reviewer(r, a, f, json!({"task": {"notes": "${author_notes}"}}))
        };
        let per = |map: Value| with(json!({"forbidden_inputs": map}));
        let plain = |r: &str, a: &str, f: &str| reviewer(r, a, f, json!({}));
        assert!(
            run_with(
                reads("ra", "a", "claude"),
                plain("rb", "b", "gpt"),
                per(json!({"rb": ["author_notes"]}))
            )
            .is_empty()
        );
        assert_eq!(
            run_with(
                reads("ra", "a", "claude"),
                plain("rb", "b", "gpt"),
                per(json!({"ra": ["author_notes"]}))
            ),
            ["F504"]
        );
        // A reviewer with no list, or an empty one, has nothing forbidden.
        assert!(run(per(json!({}))).is_empty());
        assert!(run(per(json!({"ra": []}))).is_empty());
        // Keys name reviewers; values are lists of resolvable names.
        assert_eq!(run(per(json!({"rc": ["author_notes"]}))), ["V107"]);
        assert_eq!(run(per(json!({"rb": ["nothing"]}))), ["V107"]);
        assert_eq!(
            run(per(json!({"ra": ["nothing"], "rb": ["nothing"]}))),
            ["V107"]
        );
        assert_eq!(run(per(json!({"rb": "author_notes"}))), ["S303"]);
        assert_eq!(run(per(json!(5))), ["S303"]);
        // A list in the mapping is checked like the list form.
        assert_eq!(
            run(per(json!({"rb": ["author_notes", "author_notes"]}))),
            ["S303"]
        );
        let catalog_of = |q: Value| {
            catalog(
                steps(plain("ra", "a", "claude"), plain("rb", "b", "gpt"), q),
                &["delegation@1", "quorum@1"],
            )
        };
        let report = super::super::validate_catalog(
            &super::super::tests::ctx(),
            &catalog_of(per(json!({"rb": ["nothing"]}))),
            None,
        );
        assert_eq!(
            report.diagnostics[0].location["field"],
            "quorum.forbidden_inputs.rb"
        );
        // Names are checked even when reviewers is malformed; mapping keys
        // are not, since there is nothing to check them against.
        let bad_reviewers = |fi: Value| {
            let mut q = with(json!({"forbidden_inputs": fi}));
            q["reviewers"] = json!("ra");
            codes(catalog_of(q))
        };
        assert!(bad_reviewers(json!(["nothing"])).contains(&"V107"));
        assert!(!bad_reviewers(json!({"ra": ["author_notes"]})).contains(&"V107"));
    }

    #[test]
    fn per_reviewer_independence_scales() {
        // Every reviewer forbids a different link of one long chain that
        // they all read: no shared set, so no cache helps.
        let n = 600;
        let mut s = vec![
            json!({"capability": "retrieve", "purpose": "p", "store_as": "c0",
                                "input_bindings": {"target": "x"}}),
        ];
        for i in 1..n {
            s.push(json!({"capability": "retrieve", "purpose": "p",
                          "store_as": format!("c{i}"),
                          "input_bindings": {"target": format!("${{c{}.data}}", i - 1)}}));
        }
        let mut names = Vec::new();
        let mut map = serde_json::Map::new();
        for i in 0..n {
            let mut r = reviewer(&format!("r{i}"), &format!("agent{i}"), "claude", json!({}));
            r["input_bindings"]["task"] = json!({"x": format!("${{c{}.data}}", n - 1)});
            s.push(r);
            names.push(format!("r{i}"));
            map.insert(format!("r{i}"), json!([format!("c{i}")]));
        }
        s.push(json!({"capability": "receive", "purpose": "p", "store_as": "verdicts"}));
        s.push(gate(with(json!({"reviewers": names, "min_pass": 1,
                                 "pinned_to": "${c0.data}", "forbidden_inputs": map,
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
    fn min_full() {
        assert!(run(with(json!({"min_full": 1}))).is_empty());
        assert!(run(with(json!({"min_full": 2}))).is_empty());
        for bad in [json!(0), json!(3), json!("1"), json!(1.5)] {
            assert_eq!(run(with(json!({"min_full": bad}))), ["S303"]);
        }
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
        assert_eq!(
            run_with(
                reviewer("ra", "a", "claude", json!({})),
                reviewer("rb", "b", "gpt", json!({})),
                with(json!({"reviewers": ["ra", "ra"], "min_pass": 2,
                            "require_model_families": null}))
            ),
            ["S303"]
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
