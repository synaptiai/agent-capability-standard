//! The workflow's grounding policy (STANDARD v1.2 §5.20, `grounding@1`).

use serde_json::{Map, Value};

use super::extensions::{Declared, s303, s304};
use super::{Context, Report, semantics};
use crate::diag::{Code, Diagnostic};
use crate::grounding::{KINDS, is_kind};
use crate::yaml;

const KEYS: &[&str] = &["require", "kinds", "attested"];

/// Check `grounding`. Without `grounding@1` it is V106 in a workflow that
/// targets 1.2 or later, and in one that targets an earlier version or
/// declares none an unknown field (W604), as in 1.1.
pub(crate) fn check(
    ctx: &Context,
    wf: &Map<String, Value>,
    declared: &Declared,
    target: Option<(u64, u64)>,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let Some(value) = wf.get("grounding") else {
        return;
    };
    if !declared.has("grounding@1") {
        if target.is_some_and(|t| t >= (1, 2)) {
            declared.require(
                "grounding@1",
                "'grounding'",
                |d| at(d).at("field", "grounding"),
                report,
            );
        } else {
            report.push(
                at(Diagnostic::new(
                    Code::UnknownField,
                    "unknown field 'grounding' is ignored; it belongs to extension grounding@1 (§5.20), which this workflow does not declare",
                ))
                .at("field", "grounding"),
            );
        }
        return;
    }
    let Value::Object(policy) = value else {
        report.push(s303(
            at,
            "grounding",
            format!(
                "'grounding' must be a mapping (require, kinds, attested), found {}",
                yaml::kind_of(value)
            ),
        ));
        return;
    };
    semantics::unknown_fields(policy, KEYS, "grounding", at, report);
    match policy.get("require") {
        None => report.push(s304(
            at,
            "grounding.require",
            "'grounding' must name the capabilities whose outputs are checked in 'require'"
                .to_string(),
        )),
        Some(require) => {
            if let Some(ids) = string_list(require, "grounding.require", at, report) {
                let known: Vec<&str> = ctx
                    .ontology
                    .capabilities
                    .keys()
                    .map(String::as_str)
                    .collect();
                for (i, id) in ids.iter().enumerate() {
                    if ctx.ontology.get(id).is_some() {
                        continue;
                    }
                    let mut d = Diagnostic::new(
                        Code::UnknownCapability,
                        format!("grounding.require[{i}]: capability '{id}' not found in ontology"),
                    );
                    if let Some(c) = semantics::closest(id, &known) {
                        d = d.suggest(format!("did you mean '{c}'?"));
                    }
                    report.push(at(d).at("field", format!("grounding.require[{i}]")));
                }
            }
        }
    }
    if let Some(kinds) = policy.get("kinds")
        && let Some(kinds) = string_list(kinds, "grounding.kinds", at, report)
    {
        for (i, k) in kinds.iter().enumerate() {
            if !is_kind(k) {
                report.push(s303(
                    at,
                    &format!("grounding.kinds[{i}]"),
                    format!(
                        "grounding.kinds[{i}]: '{k}' is not an anchor kind (§6.5: {}, or a vendor kind x-...)",
                        KINDS.join(", ")
                    ),
                ));
            }
        }
    }
    if let Some(attested) = policy.get("attested")
        && !attested.is_boolean()
    {
        report.push(s303(
            at,
            "grounding.attested",
            format!(
                "grounding.attested must be a boolean, found {}",
                yaml::kind_of(attested)
            ),
        ));
    }
}

/// A non-empty list of distinct strings, else S303 (and `None`).
fn string_list<'a>(
    value: &'a Value,
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> Option<Vec<&'a str>> {
    let items: Option<Vec<&str>> = value
        .as_array()
        .filter(|a| !a.is_empty())
        .and_then(|a| a.iter().map(Value::as_str).collect());
    let Some(items) = items else {
        report.push(s303(
            at,
            field,
            format!("{field} must be a non-empty list of strings"),
        ));
        return None;
    };
    if let Some((i, x)) = items
        .iter()
        .enumerate()
        .find(|(i, x)| items[..*i].contains(x))
    {
        report.push(s303(
            at,
            &format!("{field}[{i}]"),
            format!("{field}[{i}]: '{x}' is listed twice"),
        ));
        return None;
    }
    Some(items)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    fn codes(wf: serde_json::Value) -> Vec<&'static str> {
        crate::validate::tests::codes(json!({ "w": wf }))
    }

    fn wf(
        spec: Option<&str>,
        requires: &[&str],
        grounding: serde_json::Value,
    ) -> serde_json::Value {
        let mut w = json!({
            "goal": "g",
            "risk": "low",
            "steps": [{"capability": "retrieve", "purpose": "p", "store_as": "r_out",
                       "input_bindings": {"target": "x"}}],
            "grounding": grounding,
        });
        if let Some(v) = spec {
            w["spec_version"] = json!(v);
        }
        if !requires.is_empty() {
            w["workflow_extensions"] = json!({"requires": requires});
        }
        w
    }

    #[test]
    fn undeclared() {
        let g = json!({"require": ["retrieve"]});
        assert_eq!(codes(wf(Some("1.2"), &[], g.clone())), ["V106"]);
        assert_eq!(codes(wf(Some("1.1"), &[], g.clone())), ["W604"]);
        // No declared version: W605 as ever, and the 1.1 W604.
        assert_eq!(codes(wf(None, &[], g)), ["W605", "W604"]);
    }

    #[test]
    fn declared() {
        let ok = json!({"require": ["retrieve", "classify"], "kinds": ["file", "x-lab"], "attested": true, "x-note": 1});
        assert!(codes(wf(Some("1.2"), &["grounding@1"], ok)).is_empty());
        let cases = [
            (json!(["retrieve"]), "S303"),
            (json!({"kinds": ["file"]}), "S304"),
            (json!({"require": []}), "S303"),
            (json!({"require": ["retrieve", "retrieve"]}), "S303"),
            (json!({"require": [1]}), "S303"),
            (json!({"require": ["summarize"]}), "V101"),
            (
                json!({"require": ["retrieve"], "kinds": ["tool_output"]}),
                "S303",
            ),
            (json!({"require": ["retrieve"], "kinds": []}), "S303"),
            (json!({"require": ["retrieve"], "attested": "yes"}), "S303"),
            (json!({"require": ["retrieve"], "atested": true}), "W604"),
        ];
        for (g, code) in cases {
            assert_eq!(
                codes(wf(Some("1.2"), &["grounding@1"], g.clone())),
                [code],
                "{g}"
            );
        }
    }
}
