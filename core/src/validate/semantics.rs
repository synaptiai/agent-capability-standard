//! Ontology edges, safety flags, unknown fields and spec versions
//! (design-114 §4–§5).

use std::collections::HashSet;

use serde_json::{Map, Value};

use super::{Context, Report, StepLoc};
use crate::diag::{Code, Diagnostic};
use crate::ontology::{Capability, EdgeType, Risk};

/// Fields a workflow may carry (STANDARD v1.1 §5.1 plus recognised de-facto
/// fields). Anything else is W604.
pub(crate) const WORKFLOW_KEYS: &[&str] = &[
    "goal",
    "risk",
    "steps",
    "inputs",
    "success",
    "description",
    "spec_version",
    "workflow_extensions",
    "domain",
    "profile",
    "risk_propagation",
    "data_flow",
];

/// Fields a step may carry (§5.2 plus recognised de-facto fields).
pub(crate) const STEP_KEYS: &[&str] = &[
    "capability",
    "purpose",
    "store_as",
    "input_bindings",
    "condition",
    "skip_if_false",
    "gates",
    "failure_modes",
    "timeout",
    "retry",
    "parallel_group",
    "join",
    "mapping_ref",
    "output_conforms_to",
    "mutation",
    "requires_checkpoint",
    "requires_approval",
    "risk",
    "domain",
    "workflow_id",
    "resolution_strategy",
    "conflict_resolution_strategies",
];

pub(crate) const GATE_KEYS: &[&str] = &["when", "action", "message", "phase"];
pub(crate) const FAILURE_MODE_KEYS: &[&str] = &["condition", "action", "recovery", "when"];
pub(crate) const RECOVERY_KEYS: &[&str] = &["goto_step", "inject_context", "max_loops"];
pub(crate) const RETRY_KEYS: &[&str] = &["max", "backoff"];
pub(crate) const WORKFLOW_EXTENSIONS_KEYS: &[&str] = &[
    "supports_input_bindings",
    "supports_conditions",
    "supports_parallel_groups",
    "supports_recovery_loops",
    "supports_gates",
];

/// Standard versions this validator implements (GOVERNANCE: the last two
/// minors of the current major).
pub(crate) const SUPPORTED_VERSIONS: &[(u64, u64)] = &[(1, 0), (1, 1)];

/// Optimal-string-alignment distance (Levenshtein plus adjacent
/// transpositions, so `stpes` is one edit from `steps`).
fn distance(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let mut d = vec![vec![0usize; b.len() + 1]; a.len() + 1];
    for (i, row) in d.iter_mut().enumerate() {
        row[0] = i;
    }
    for (j, cell) in d[0].iter_mut().enumerate() {
        *cell = j;
    }
    for i in 1..=a.len() {
        for j in 1..=b.len() {
            let cost = usize::from(a[i - 1] != b[j - 1]);
            let mut v = (d[i - 1][j] + 1)
                .min(d[i][j - 1] + 1)
                .min(d[i - 1][j - 1] + cost);
            if i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1] {
                v = v.min(d[i - 2][j - 2] + 1);
            }
            d[i][j] = v;
        }
    }
    d[a.len()][b.len()]
}

/// The known key closest to `key`, if it is close enough to be a typo.
fn closest<'k>(key: &str, known: &[&'k str]) -> Option<&'k str> {
    let limit = (key.chars().count() / 3).max(1);
    known
        .iter()
        .map(|k| (distance(key, k), *k))
        .filter(|(d, _)| *d <= limit)
        .min_by_key(|(d, _)| *d)
        .map(|(_, k)| k)
}

/// W604 for every key of `map` not in `known`; `x-` keys are vendor data.
pub(crate) fn unknown_fields(
    map: &Map<String, Value>,
    known: &[&str],
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    for key in map.keys() {
        if known.contains(&key.as_str()) || key.starts_with("x-") {
            continue;
        }
        let path = if field.is_empty() {
            key.clone()
        } else {
            format!("{field}.{key}")
        };
        let mut d = Diagnostic::new(
            Code::UnknownField,
            format!("unknown field '{path}' is ignored"),
        );
        if let Some(k) = closest(key, known) {
            d = d.suggest(format!("did you mean '{k}'?"));
        }
        report.push(at(d).at("field", path));
    }
}

/// W602: a step declares a safety flag less safe than the ontology. The
/// declaration has no effect — the ontology value applies — but it misleads.
pub(crate) fn flag_downgrades(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    cap: &Capability,
    report: &mut Report,
) {
    let declared_false = |k: &str| step.get(k) == Some(&Value::Bool(false));
    let mut downgrade = |flag: &str, consequence: &str| {
        report.push(
            loc.diag(
                Code::SafetyFlagDowngrade,
                format!(
                    "ontology declares {flag}=true but step downgrades to {flag}=false; the ontology value applies ({consequence})"
                ),
            )
            .at("field", flag),
        );
    };
    if cap.mutation && !cap.mutation_overridable && declared_false("mutation") {
        downgrade("mutation", "the step is treated as a mutation");
    }
    if cap.requires_checkpoint && declared_false("requires_checkpoint") {
        downgrade("requires_checkpoint", "F501 if no checkpoint precedes it");
    }
    if cap.requires_approval && declared_false("requires_approval") {
        downgrade("requires_approval", "F502 if it is not approved");
    }
    if let Some(declared) = step
        .get("risk")
        .and_then(Value::as_str)
        .and_then(Risk::parse)
    {
        if declared < cap.risk {
            report.push(
                loc.diag(
                    Code::SafetyFlagDowngrade,
                    format!(
                        "ontology declares risk={} but step declares risk={}; the ontology value applies",
                        cap.risk.as_str(),
                        declared.as_str()
                    ),
                )
                .at("field", "risk"),
            );
        }
    }
}

/// One step's position for edge checks.
pub(crate) struct Placed<'a> {
    pub index: usize,
    pub capability: &'a str,
    pub parallel_group: Option<&'a str>,
}

/// `precedes` (order, V102), `soft_requires` (presence, any-of, W601) and
/// `conflicts_with` (concurrency, F504) over the workflow's steps in order.
pub(crate) fn check_edges(
    ctx: &Context,
    workflow: &str,
    placed: &[Placed<'_>],
    report: &mut Report,
) {
    let at = |p: &Placed<'_>, code: Code, msg: String| {
        Diagnostic::new(code, msg)
            .at("workflow", workflow)
            .at("step", p.index)
            .at("capability", p.capability)
    };
    let first = |cap: &str| placed.iter().position(|p| p.capability == cap);
    for (pos, p) in placed.iter().enumerate() {
        let before = &placed[..pos];
        // precedes: when both are present, `from` must come first.
        for from in ctx.ontology.incoming(p.capability, EdgeType::Precedes) {
            if before.iter().any(|q| q.capability == from) {
                continue;
            }
            if let Some(later) = first(from).filter(|&f| f > pos) {
                report.push(at(
                    p,
                    Code::MissingPrerequisite,
                    format!(
                        "'{}' must come after '{from}' (precedes), but '{from}' first appears at step {}",
                        p.capability, placed[later].index
                    ),
                ));
            }
        }
        // soft_requires: any one source of the group should come earlier.
        let sources = ctx.ontology.incoming(p.capability, EdgeType::SoftRequires);
        if !sources.is_empty() && !before.iter().any(|q| sources.contains(&q.capability)) {
            report.push(at(
                p,
                Code::SoftRequirementUnmet,
                format!(
                    "'{}' should be preceded by {} (soft_requires)",
                    p.capability,
                    if sources.len() == 1 {
                        format!("'{}'", sources[0])
                    } else {
                        format!("one of {}", sources.join(", "))
                    }
                ),
            ));
        }
    }
    // conflicts_with: never in the same parallel group. The edges are
    // symmetric, so compare unordered pairs once.
    let pairs: HashSet<(&str, &str)> = ctx
        .ontology
        .edges
        .iter()
        .filter(|e| e.kind == EdgeType::ConflictsWith)
        .map(|e| {
            let (a, b) = (e.from.as_str(), e.to.as_str());
            if a <= b { (a, b) } else { (b, a) }
        })
        .collect();
    for (j, b) in placed.iter().enumerate() {
        let Some(group) = b.parallel_group else {
            continue;
        };
        for a in placed[..j]
            .iter()
            .filter(|a| a.parallel_group == Some(group))
        {
            let key = if a.capability <= b.capability {
                (a.capability, b.capability)
            } else {
                (b.capability, a.capability)
            };
            if pairs.contains(&key) {
                report.push(at(
                    b,
                    Code::ConstraintViolated,
                    format!(
                        "'{}' conflicts with '{}' (step {}) and they share parallel_group '{group}'; conflicting capabilities must not run concurrently",
                        b.capability, a.capability, a.index
                    ),
                ));
            }
        }
    }
}

/// Parse `major.minor[.patch]`.
fn parse_version(v: &str) -> Option<(u64, u64)> {
    let mut parts = v.trim().split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    match parts.next() {
        None => {}
        Some(p) => {
            p.parse::<u64>().ok()?;
        }
    }
    parts.next().is_none().then_some((major, minor))
}

/// W605 when neither `spec_version` nor the file header names a version;
/// V109 when the named version is not supported.
pub(crate) fn spec_version(
    wf: &Map<String, Value>,
    header: Option<&str>,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let (version, field) = match wf.get("spec_version") {
        Some(Value::String(v)) => (v.as_str(), "spec_version"),
        Some(other) => {
            report.push(
                at(Diagnostic::new(
                    Code::SchemaValidationFailed,
                    format!("'spec_version' must be a string such as \"1.1\", found {other}"),
                ))
                .at("field", "spec_version"),
            );
            return;
        }
        None => match header {
            Some(h) => (h, "# Standard version"),
            None => {
                report.push(
                    at(Diagnostic::new(
                        Code::MissingSpecVersion,
                        "no 'spec_version' and no '# Standard version:' header; declare the standard version the workflow targets",
                    ))
                    .at("field", "spec_version"),
                );
                return;
            }
        },
    };
    match parse_version(version) {
        Some(mm) if SUPPORTED_VERSIONS.contains(&mm) => {}
        _ => report.push(
            at(Diagnostic::new(
                Code::UnsupportedSpecVersion,
                format!(
                    "standard version '{version}' is not supported (supported: {})",
                    SUPPORTED_VERSIONS
                        .iter()
                        .map(|(a, b)| format!("{a}.{b}"))
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            ))
            .at("field", field),
        ),
    }
}

/// The version named by a `# Standard version: X.Y.Z` comment among the
/// file's leading comment lines.
pub fn header_version(text: &str) -> Option<String> {
    for line in text.lines() {
        let t = line.trim();
        if t.is_empty() {
            continue;
        }
        let Some(comment) = t.strip_prefix('#') else {
            break;
        };
        if let Some(v) = comment.trim().strip_prefix("Standard version:") {
            return Some(v.trim().to_string());
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn did_you_mean() {
        assert_eq!(closest("stpes", WORKFLOW_KEYS), Some("steps"));
        assert_eq!(
            closest("requires_aproval", STEP_KEYS),
            Some("requires_approval")
        );
        assert_eq!(closest("zzzzzz", STEP_KEYS), None);
        assert_eq!(distance("kitten", "sitting"), 3);
        assert_eq!(distance("stpes", "steps"), 1);
    }

    #[test]
    fn versions() {
        assert_eq!(parse_version("1.1"), Some((1, 1)));
        assert_eq!(parse_version("1.0.0"), Some((1, 0)));
        assert_eq!(parse_version("1"), None);
        assert_eq!(parse_version("1.1.0.0"), None);
        assert_eq!(parse_version("v1.1"), None);
        assert_eq!(
            header_version("# Standard version: 1.1.0\n# Workflow Catalog\nw: {}\n").as_deref(),
            Some("1.1.0")
        );
        assert_eq!(header_version("w: {}\n# Standard version: 1.1.0\n"), None);
    }
}
