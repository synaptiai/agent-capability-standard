//! Counting a review quorum at run time (STANDARD v1.1 §5.16, design-114
//! §16.4). The executor evaluates it itself; there is no host call.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value, json};

use super::Frame;
use super::machine::resolve;
use crate::expr::eval::{self, Bindings};
use crate::validate::count;

pub(crate) struct Verdict {
    pub output: Value,
    pub compliant: bool,
    pub message: String,
}

struct Reviewer {
    agent: Option<String>,
    family: Option<String>,
    fresh: bool,
}

/// The values a frame's references read (as in the step algorithm).
struct Read<'a>(&'a Frame);

impl Bindings for Read<'_> {
    fn get(&self, root: &str) -> Option<&Value> {
        if root == "_recovery" {
            return self.0.recovery.as_ref();
        }
        self.0.stores.get(root).or_else(|| self.0.inputs.get(root))
    }
}

fn strings(q: &Map<String, Value>, key: &str) -> Vec<String> {
    q.get(key)
        .and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

pub(crate) fn evaluate(q: &Map<String, Value>, frame: &Frame) -> Verdict {
    let b = Read(frame);
    let verdicts = q
        .get("verdicts")
        .map(|v| resolve(v, &b))
        .unwrap_or(Value::Null);
    let pinned_to = q
        .get("pinned_to")
        .map(|v| resolve(v, &b))
        .unwrap_or(Value::Null);
    let vocabulary: BTreeSet<String> = strings(q, "vocabulary").into_iter().collect();
    let pass: BTreeSet<String> = strings(q, "pass_values").into_iter().collect();
    let block: BTreeSet<String> = strings(q, "blocking_values").into_iter().collect();
    // Read as the validator reads them: an integral float is an integer.
    let min_pass = q.get("min_pass").and_then(count).unwrap_or(1);
    let min_full = q.get("min_full").and_then(count).unwrap_or(0);
    let need_fresh = q.get("require_fresh_context") == Some(&Value::Bool(true));
    let families: BTreeSet<String> = strings(q, "require_model_families").into_iter().collect();

    // Reviewer delegates: the agent each was bound to, and what the host
    // attested it used.
    let mut reviewers: BTreeMap<String, Reviewer> = BTreeMap::new();
    for store in strings(q, "reviewers") {
        // A reviewer counts only if its delegate step ran, judged by the
        // inputs it ran with.
        let (Some(out), Some(bound)) = (frame.stores.get(&store), frame.ran_inputs.get(&store))
        else {
            continue;
        };
        let out = Some(out);
        let effective = out.and_then(|o| o.get("effective"));
        let agent = bound
            .get("agent")
            .or_else(|| out.and_then(|o| o.get("agent")))
            .and_then(Value::as_str)
            .map(str::to_string);
        let family = effective
            .and_then(|e| e.get("model_family"))
            .or_else(|| bound.get("model_family"))
            .and_then(Value::as_str)
            .map(str::to_string);
        let fresh = effective
            .and_then(|e| e.get("fresh_context"))
            .and_then(Value::as_bool)
            .unwrap_or(false);
        reviewers.insert(
            store,
            Reviewer {
                agent,
                family,
                fresh,
            },
        );
    }
    let by_agent: BTreeMap<&str, &Reviewer> = reviewers
        .values()
        .filter_map(|r| r.agent.as_deref().map(|a| (a, r)))
        .collect();

    let mut counted: BTreeSet<String> = BTreeSet::new();
    let (mut passes, mut blocks, mut abstains, mut full_passes) = (0u64, 0u64, 0u64, 0u64);
    let mut covered: BTreeSet<String> = BTreeSet::new();
    let mut violations: Vec<Value> = Vec::new();
    for v in verdicts.as_array().into_iter().flatten() {
        let id = v.get("reviewer_id").and_then(Value::as_str);
        let value = v.get("value").and_then(Value::as_str);
        let reject = |why: &str| json!({"reviewer_id": id, "ignored": why});
        let Some(reviewer) = id.and_then(|i| by_agent.get(i)) else {
            violations.push(reject("not a reviewer"));
            continue;
        };
        let id = id.unwrap_or_default();
        if !eval::deep_eq(v.get("pinned").unwrap_or(&Value::Null), &pinned_to) {
            violations.push(reject("pinned to something else"));
            continue;
        }
        let Some(value) = value.filter(|x| vocabulary.contains(*x)) else {
            violations.push(reject("value outside the vocabulary"));
            continue;
        };
        // A verdict without a scope reviewed only a delta. An unknown scope
        // is a delta too: it still counts (a blocking verdict still vetoes),
        // but never as a full sweep.
        let full = match v.get("scope") {
            None => false,
            Some(Value::String(s)) if s == "full" => true,
            Some(Value::String(s)) if s == "delta" => false,
            Some(_) => {
                violations.push(json!({"reviewer_id": id,
                    "note": "scope is neither full nor delta; counted as delta"}));
                false
            }
        };
        if need_fresh && !reviewer.fresh {
            violations.push(reject("the reviewer did not run with a fresh context"));
            continue;
        }
        if !counted.insert(id.to_string()) {
            violations.push(reject("a second verdict from the same reviewer"));
            continue;
        }
        if let Some(f) = &reviewer.family {
            covered.insert(f.clone());
        }
        if block.contains(value) {
            blocks += 1;
        } else if pass.contains(value) {
            passes += 1;
            if full {
                full_passes += 1;
            }
        } else {
            abstains += 1;
        }
    }
    let missing: Vec<&String> = families.difference(&covered).collect();
    let mut reasons = Vec::new();
    if blocks > 0 {
        reasons.push(format!("{blocks} blocking verdict(s)"));
    }
    if passes < min_pass {
        reasons.push(format!("{passes} pass(es), {min_pass} needed"));
    }
    if full_passes < min_full {
        reasons.push(format!(
            "{full_passes} full-sweep pass(es), {min_full} needed"
        ));
    }
    if !missing.is_empty() {
        let names: Vec<&str> = missing.iter().map(|s| s.as_str()).collect();
        reasons.push(format!(
            "no counted verdict from model family {}",
            names.join(", ")
        ));
    }
    for r in &reasons {
        violations.push(json!({"quorum": r}));
    }
    let compliant = reasons.is_empty();
    Verdict {
        output: json!({
            "compliant": compliant,
            "violations": violations,
            "tally": {
                "passes": passes,
                "blocks": blocks,
                "abstains": abstains,
                "full_passes": full_passes,
                "voters": counted.iter().collect::<Vec<_>>(),
            },
            "evidence_anchors": [],
        }),
        compliant,
        message: if compliant {
            String::new()
        } else {
            format!("the review quorum is not met: {}", reasons.join("; "))
        },
    }
}
