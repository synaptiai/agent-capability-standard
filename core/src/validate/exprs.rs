//! Expression sites in a step: `condition`, `gates[].when`,
//! `failure_modes[].when` (design-114 §7–§8).

use serde_json::{Map, Value};

use super::{Report, Scope, StepLoc};
use crate::diag::Code;
use crate::expr::{self, SyntaxError, ast::Expr, check};

impl check::Scope for Scope {
    fn root(&self, name: &str) -> Option<check::RootInfo<'_>> {
        let schema = self.stores.get(name).or_else(|| self.inputs.get(name))?;
        Some(check::RootInfo {
            schema: Some(schema),
            always_present: !self.maybe_absent.contains(name),
        })
    }
}

/// Report a parse result, or type-check the parsed expression.
pub(crate) fn check_parsed(
    parsed: &Result<Expr, SyntaxError>,
    scope: &Scope,
    loc: &StepLoc<'_>,
    field: &str,
    report: &mut Report,
) {
    let at = |d: crate::diag::Diagnostic, pos: usize| d.at("field", field).at("column", pos + 1);
    match parsed {
        Err(e) => {
            report.push(at(
                loc.diag(e.kind.code(), format!("{field}: {}", e.msg)),
                e.pos,
            ));
        }
        Ok(e) => {
            let mut checker = check::Checker::new(scope);
            checker.check_condition(e);
            for f in checker.findings {
                report.push(at(loc.diag(f.code, format!("{field}: {}", f.msg)), f.pos));
            }
        }
    }
}

/// Parse and type-check one expression.
pub(crate) fn check_expression(
    src: &str,
    scope: &Scope,
    loc: &StepLoc<'_>,
    field: &str,
    report: &mut Report,
) {
    check_parsed(&expr::parse(src), scope, loc, field, report);
}

/// When a gate is evaluated relative to its step.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Phase {
    Before,
    After,
}

/// One gate, parsed once.
pub(crate) struct Gate<'a> {
    pub field: String,
    pub phase: Phase,
    pub action: Option<&'a str>,
    /// `None` when `when` is missing or not a string (reported elsewhere).
    pub when: Option<Result<Expr, SyntaxError>>,
}

/// The gates of a step, each parsed and with its effective phase. Reports
/// S303 for a bad `action` or `phase`, and W603 when a gate that reads the
/// step's own output omits `phase` (it is then treated as `after`).
pub(crate) fn gates<'a>(
    step: &'a Map<String, Value>,
    store: Option<&str>,
    loc: &StepLoc<'_>,
    report: &mut Report,
) -> Vec<Gate<'a>> {
    let Some(Value::Array(list)) = step.get("gates") else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for (g, gate) in list.iter().enumerate() {
        let field = format!("gates[{g}]");
        let Some(gate) = gate.as_object() else {
            continue;
        };
        let action = gate.get("action").and_then(Value::as_str);
        if let Some(a) = action {
            if !matches!(a, "stop" | "rollback" | "skip" | "warn") {
                report.push(
                    loc.diag(
                        Code::SchemaValidationFailed,
                        format!("{field}.action '{a}' is not one of stop, rollback, skip, warn"),
                    )
                    .at("field", format!("{field}.action")),
                );
            }
        }
        let when = gate.get("when").and_then(Value::as_str).map(expr::parse);
        let reads_own = matches!((&when, store), (Some(Ok(e)), Some(s)) if e.refs().iter().any(|r| r.r.root == s));
        let phase = match gate.get("phase") {
            None if reads_own => {
                report.push(
                    loc.diag(
                        Code::DeprecatedForm,
                        format!(
                            "{field} reads the step's own output but declares no phase; it is evaluated after the step — add 'phase: after'"
                        ),
                    )
                    .at("field", format!("{field}.phase")),
                );
                Phase::After
            }
            None => Phase::Before,
            Some(Value::String(p)) if p == "before" => Phase::Before,
            Some(Value::String(p)) if p == "after" => Phase::After,
            Some(other) => {
                report.push(
                    loc.diag(
                        Code::SchemaValidationFailed,
                        format!("{field}.phase must be 'before' or 'after', found {other}"),
                    )
                    .at("field", format!("{field}.phase")),
                );
                Phase::Before
            }
        };
        if phase == Phase::After && action == Some("skip") {
            report.push(
                loc.diag(
                    Code::SchemaValidationFailed,
                    format!(
                        "{field} runs after the step, so it cannot skip it; use stop, rollback or warn"
                    ),
                )
                .at("field", format!("{field}.action")),
            );
        }
        out.push(Gate {
            field: format!("{field}.when"),
            phase,
            action,
            when,
        });
    }
    out
}

/// Whether the step may be skipped at runtime, leaving its output absent: a
/// `condition` that skips when false (`skip_if_false` true or absent), or a
/// before-gate whose action is `skip`.
pub(crate) fn skippable(step: &Map<String, Value>, gates: &[Gate<'_>]) -> bool {
    let condition_skips =
        step.contains_key("condition") && step.get("skip_if_false") != Some(&Value::Bool(false));
    condition_skips
        || gates
            .iter()
            .any(|g| g.phase == Phase::Before && g.action == Some("skip"))
}
