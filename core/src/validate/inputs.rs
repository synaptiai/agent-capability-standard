//! Named inputs given against a declaration in the form of workflow
//! `inputs` (STANDARD §5.1): an `invoke` step's literal input against its
//! target's inputs (§5.12), and a `delegate` step's literal task against its
//! agent's manifest (§5.15.2). Checked by name and `required` only.

use serde_json::{Map, Value};

use super::Report;
use super::semantics::closest;
use crate::diag::Diagnostic;

/// Report each name of `given` that `declared` does not declare
/// (`undeclared(name, suggestion)`), then each input `declared` marks
/// `required: true` that `given` lacks (`missing(name)`).
pub(crate) fn check_names(
    declared: &Map<String, Value>,
    given: &[String],
    undeclared: impl Fn(&str) -> Diagnostic,
    missing: impl Fn(&str) -> Diagnostic,
    report: &mut Report,
) {
    let names: Vec<&str> = declared.keys().map(String::as_str).collect();
    for name in given.iter().filter(|n| !declared.contains_key(*n)) {
        let mut d = undeclared(name);
        if let Some(k) = closest(name, &names) {
            d = d.suggest(format!("did you mean '{k}'?"));
        }
        report.push(d);
    }
    for (name, spec) in declared {
        if spec.get("required") == Some(&Value::Bool(true)) && !given.contains(name) {
            report.push(missing(name));
        }
    }
}
