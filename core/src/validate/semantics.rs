//! Ontology edges, safety flags, unknown fields and spec versions
//! (design-114 §4–§5).

use std::collections::{HashMap, HashSet};

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
    "triggers",
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
    "handler",
    "wait",
    "approval",
    "quorum",
    "resolution_strategy",
    "conflict_resolution_strategies",
];

pub(crate) const GATE_KEYS: &[&str] = &["when", "action", "message", "phase"];
pub(crate) const FAILURE_MODE_KEYS: &[&str] =
    &["condition", "action", "recovery", "when", "on_error"];
pub(crate) const RECOVERY_KEYS: &[&str] =
    &["goto_step", "inject_context", "max_loops", "on_exhausted"];
pub(crate) const RETRY_KEYS: &[&str] = &["max", "backoff"];
pub(crate) const WORKFLOW_EXTENSIONS_KEYS: &[&str] = &[
    "supports_input_bindings",
    "supports_conditions",
    "supports_parallel_groups",
    "supports_recovery_loops",
    "supports_gates",
    "requires",
];

/// Standard versions this validator implements (GOVERNANCE: the last two
/// minors of the current major).
pub(crate) const SUPPORTED_VERSIONS: &[(u64, u64)] = &[(1, 0), (1, 1)];

/// Keys longer than this get no did-you-mean hint: they are not typos of
/// a field name, and the distance is quadratic in the key's length.
const MAX_HINT_KEY_CHARS: usize = 64;

/// Optimal-string-alignment distance (Levenshtein plus adjacent
/// transpositions, so `stpes` is one edit from `steps`), in three rows.
fn distance(a: &[char], b: &[char]) -> usize {
    let mut before: Vec<usize> = vec![0; b.len() + 1];
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut cur: Vec<usize> = vec![0; b.len() + 1];
    for i in 1..=a.len() {
        cur[0] = i;
        for j in 1..=b.len() {
            let cost = usize::from(a[i - 1] != b[j - 1]);
            let mut v = (prev[j] + 1).min(cur[j - 1] + 1).min(prev[j - 1] + cost);
            if i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1] {
                v = v.min(before[j - 2] + 1);
            }
            cur[j] = v;
        }
        std::mem::swap(&mut before, &mut prev);
        std::mem::swap(&mut prev, &mut cur);
    }
    prev[b.len()]
}

/// The known key closest to `key`, if it is close enough to be a typo.
pub(crate) fn closest<'k>(key: &str, known: &[&'k str]) -> Option<&'k str> {
    let key: Vec<char> = key.chars().collect();
    if key.len() > MAX_HINT_KEY_CHARS {
        return None;
    }
    let limit = (key.len() / 3).max(1);
    known
        .iter()
        .filter_map(|k| {
            let k_chars: Vec<char> = k.chars().collect();
            // The length difference alone is a lower bound on the distance.
            if k_chars.len().abs_diff(key.len()) > limit {
                return None;
            }
            let d = distance(&key, &k_chars);
            (d <= limit).then_some((d, *k))
        })
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

/// W604 for every `input_bindings` key the capability's input schema does
/// not define (§5.2): the host receives it, but it is outside the contract,
/// so it is usually a typo or a parameter that belongs elsewhere. `x-` keys
/// are vendor data; a schema with `additionalProperties: true` accepts any.
pub(crate) fn unknown_inputs(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    cap: &Capability,
    report: &mut Report,
) {
    let Some(Value::Object(bindings)) = step.get("input_bindings") else {
        return;
    };
    let schema = &cap.input_schema;
    let Some(properties) = schema.get("properties").and_then(Value::as_object) else {
        return;
    };
    if schema.get("additionalProperties") == Some(&Value::Bool(true)) {
        return;
    }
    let known: Vec<&str> = properties.keys().map(String::as_str).collect();
    for key in bindings.keys() {
        if properties.contains_key(key) || key.starts_with("x-") {
            continue;
        }
        let mut d = loc.diag(
            Code::UnknownField,
            format!(
                "'{}' has no input '{key}'; the binding is outside its contract",
                cap.id
            ),
        );
        d = match closest(key, &known) {
            Some(k) => d.suggest(format!("did you mean '{k}'?")),
            None => d.suggest(format!("its inputs are: {}", known.join(", "))),
        };
        report.push(d.at("field", format!("input_bindings.{key}")));
    }
}

/// W615 for every input the capability requires that the step does not
/// bind (§5.5): the host would get no value for it. An invoke step's
/// `workflow_id` names its workflow, so it gives `workflow`. A malformed
/// `input_bindings` is reported elsewhere (S303).
pub(crate) fn missing_inputs(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    cap: &Capability,
    report: &mut Report,
) {
    let empty = Map::new();
    // The executor runs a wait (§5.13) or a quorum (§5.16) itself: no host
    // receives the step's inputs, so none is missing. A delegate that waits
    // still delegates first, with its inputs; a wait on any other capability
    // is S303 and does not excuse its inputs.
    if (matches!(cap.id.as_str(), "receive" | "synchronize")
        && step.get("wait").is_some_and(Value::is_object))
        || (cap.id == "constrain" && step.get("quorum").is_some_and(Value::is_object))
    {
        return;
    }
    let bindings = match step.get("input_bindings") {
        None => &empty,
        Some(Value::Object(b)) => b,
        // Malformed (null included): S303 already reports it.
        Some(_) => return,
    };
    let Some(required) = cap.input_schema.get("required").and_then(Value::as_array) else {
        return;
    };
    for key in required.iter().filter_map(Value::as_str) {
        let given = bindings.contains_key(key)
            || (key == "workflow" && cap.id == "invoke" && step.contains_key("workflow_id"));
        if !given {
            report.push(
                loc.diag(
                    Code::MissingInput,
                    format!(
                        "'{}' requires input '{key}', which the step does not bind",
                        cap.id
                    ),
                )
                .at("field", format!("input_bindings.{key}")),
            );
        }
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
    /// Effective `requires_checkpoint` (§5.2.1): the ontology's, or true
    /// when the step raises it.
    pub requires_checkpoint: bool,
    /// Whether the step waits for an event (`wait`, §5.13).
    pub waits: bool,
}

impl Placed<'_> {
    /// Steps of one parallel group run at the same time, so neither
    /// completes before the other starts.
    pub(crate) fn concurrent_with(&self, other: &Placed<'_>) -> bool {
        self.parallel_group.is_some() && self.parallel_group == other.parallel_group
    }
}

/// Where each capability occurs, for O(1) "ran before" queries.
struct Occurrences {
    /// First position of the capability.
    first: usize,
    /// First position not concurrent with the first one (a different
    /// group, or no group), if any.
    first_elsewhere: Option<usize>,
}

/// `requires` (V102), `precedes` (order, V102), `soft_requires` (presence,
/// any-of, W601) and `conflicts_with` (concurrency, F504) over the
/// workflow's steps in order. A step "runs before" another when it comes
/// earlier in the list and is not in the same parallel group.
///
/// `handlers` are handler steps (§5.11) with the position in `placed` of
/// their earliest targeter: a handler runs after that step fails, so its
/// `requires` and effective `requires_checkpoint` are checked against what
/// runs before the targeter. Handlers take no part in the other edges.
pub(crate) fn check_edges(
    ctx: &Context,
    workflow: &str,
    placed: &[Placed<'_>],
    handlers: &[(Placed<'_>, usize)],
    report: &mut Report,
) {
    let at = |p: &Placed<'_>, code: Code, msg: String| {
        Diagnostic::new(code, msg)
            .at("workflow", workflow)
            .at("step", p.index)
            .at("capability", p.capability)
    };
    let mut occurs: HashMap<&str, Occurrences> = HashMap::new();
    for (pos, p) in placed.iter().enumerate() {
        match occurs.get_mut(p.capability) {
            None => {
                occurs.insert(
                    p.capability,
                    Occurrences {
                        first: pos,
                        first_elsewhere: None,
                    },
                );
            }
            Some(o) => {
                if o.first_elsewhere.is_none() && !placed[o.first].concurrent_with(p) {
                    o.first_elsewhere = Some(pos);
                }
            }
        }
    }
    // Whether `cap` runs before the step at `pos`.
    let ran_before = |cap: &str, pos: usize| -> bool {
        let Some(o) = occurs.get(cap) else {
            return false;
        };
        let p = &placed[pos];
        if o.first >= pos {
            return false;
        }
        if !placed[o.first].concurrent_with(p) {
            return true;
        }
        // The first occurrence shares p's group; the first one outside it
        // is the earliest candidate left.
        o.first_elsewhere.is_some_and(|e| e < pos)
    };

    // requires (V102) and the effective requires_checkpoint (F501, §5.2.1)
    // of step `p`, given whether a capability ran before it. Where a
    // `requires checkpoint` edge exists, a missing checkpoint is V102.
    let prerequisites = |p: &Placed<'_>, ran: &dyn Fn(&str) -> bool, report: &mut Report| {
        let requires = ctx.ontology.incoming(p.capability, EdgeType::Requires);
        if p.requires_checkpoint && !requires.contains(&"checkpoint") && !ran("checkpoint") {
            report.push(
                at(
                    p,
                    Code::CheckpointRequired,
                    format!(
                        "'{}' requires a checkpoint (requires_checkpoint), but no checkpoint step runs before it",
                        p.capability
                    ),
                )
                .at("field", "requires_checkpoint"),
            );
        }
        for req in requires {
            if !ran(req) {
                report.push(
                    at(
                        p,
                        Code::MissingPrerequisite,
                        format!(
                            "capability '{}' missing required prerequisite '{req}' before it",
                            p.capability
                        ),
                    )
                    .at("prerequisite", req),
                );
            }
        }
    };
    for (h, targeter) in handlers {
        prerequisites(h, &|cap| ran_before(cap, *targeter), report);
    }

    let mut reported_precedes: HashSet<(&str, &str)> = HashSet::new();
    for (pos, p) in placed.iter().enumerate() {
        prerequisites(p, &|cap| ran_before(cap, pos), report);
        // precedes: when both are present, `from` must run first; reported
        // once per edge, at the first step that breaks it.
        for from in ctx.ontology.incoming(p.capability, EdgeType::Precedes) {
            if ran_before(from, pos) || reported_precedes.contains(&(from, p.capability)) {
                continue;
            }
            let Some(o) = occurs.get(from) else {
                continue;
            };
            reported_precedes.insert((from, p.capability));
            let first = &placed[o.first];
            let detail = if first.concurrent_with(p) {
                format!(
                    "'{from}' (step {}) runs concurrently in parallel_group '{}'",
                    first.index,
                    first.parallel_group.unwrap_or_default()
                )
            } else {
                format!("'{from}' first appears at step {}", first.index)
            };
            report.push(
                at(
                    p,
                    Code::MissingPrerequisite,
                    format!(
                        "'{}' must come after '{from}' (precedes), but {detail}",
                        p.capability
                    ),
                )
                .at("prerequisite", from),
            );
        }
        // soft_requires: any one source of the group should run earlier.
        let sources = ctx.ontology.incoming(p.capability, EdgeType::SoftRequires);
        if !sources.is_empty() && !sources.iter().any(|s| ran_before(s, pos)) {
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

    // conflicts_with: never in the same parallel group; reported once per
    // group and unordered pair, at the step that completes the pair.
    let mut partners: HashMap<&str, Vec<&str>> = HashMap::new();
    for e in ctx
        .ontology
        .edges
        .iter()
        .filter(|e| e.kind == EdgeType::ConflictsWith)
    {
        partners
            .entry(e.from.as_str())
            .or_default()
            .push(e.to.as_str());
        partners
            .entry(e.to.as_str())
            .or_default()
            .push(e.from.as_str());
    }
    let mut in_group: HashMap<(&str, &str), usize> = HashMap::new();
    let mut reported: HashSet<(&str, &str, &str)> = HashSet::new();
    for b in placed {
        let Some(group) = b.parallel_group else {
            continue;
        };
        for &other in partners.get(b.capability).into_iter().flatten() {
            let Some(&first) = in_group.get(&(group, other)) else {
                continue;
            };
            let pair = if other <= b.capability {
                (group, other, b.capability)
            } else {
                (group, b.capability, other)
            };
            if reported.insert(pair) {
                report.push(at(
                    b,
                    Code::ConstraintViolated,
                    format!(
                        "'{}' conflicts with '{other}' (step {first}) and they share parallel_group '{group}'; conflicting capabilities must not run concurrently",
                        b.capability
                    ),
                ));
            }
        }
        in_group.entry((group, b.capability)).or_insert(b.index);
    }
}

/// Parse `major.minor[.patch]`.
fn parse_version(v: &str) -> Option<(u64, u64)> {
    let number = |p: &str| -> Option<u64> {
        if p.is_empty() || !p.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
        p.parse().ok()
    };
    let mut parts = v.split('.');
    let major = number(parts.next()?)?;
    let minor = number(parts.next()?)?;
    if let Some(patch) = parts.next() {
        number(patch)?;
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
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    for line in text.lines() {
        let t = line.trim();
        // Blank lines, YAML directives and the document start marker may
        // come before or between the leading comments.
        if t.is_empty() || t.starts_with('%') || t == "---" {
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
    fn unknown_inputs_respect_the_schema() {
        let cap = |input_schema: Value| Capability {
            id: "c".into(),
            layer: "PERCEIVE".into(),
            risk: Risk::Low,
            mutation: false,
            requires_checkpoint: false,
            requires_approval: false,
            mutation_overridable: false,
            input_schema,
            output_schema: serde_json::json!({}),
        };
        let loc = StepLoc {
            workflow: "w",
            step: 0,
            capability: "c",
        };
        let run = |schema: Value, step: Value| {
            let mut report = Report::default();
            unknown_inputs(&loc, step.as_object().unwrap(), &cap(schema), &mut report);
            report
                .diagnostics
                .iter()
                .map(|d| d.location["field"].as_str().unwrap().to_string())
                .collect::<Vec<_>>()
        };
        let closed = serde_json::json!({"properties": {"a": {}}});
        let bound = serde_json::json!({"input_bindings": {"a": 1, "b": 2, "x-c": 3}});
        assert_eq!(run(closed.clone(), bound.clone()), ["input_bindings.b"]);
        // An open schema, or one without properties, accepts any key.
        let open = serde_json::json!({"properties": {"a": {}}, "additionalProperties": true});
        assert!(run(open, bound.clone()).is_empty());
        assert!(run(serde_json::json!({"type": "object"}), bound).is_empty());
        // Malformed bindings are reported elsewhere (S303), not here.
        assert!(run(closed, serde_json::json!({"input_bindings": ["b"]})).is_empty());
    }

    #[test]
    fn did_you_mean() {
        assert_eq!(closest("stpes", WORKFLOW_KEYS), Some("steps"));
        assert_eq!(
            closest("requires_aproval", STEP_KEYS),
            Some("requires_approval")
        );
        assert_eq!(closest("zzzzzz", STEP_KEYS), None);
        let d = |a: &str, b: &str| {
            let (a, b): (Vec<char>, Vec<char>) = (a.chars().collect(), b.chars().collect());
            distance(&a, &b)
        };
        assert_eq!(d("kitten", "sitting"), 3);
        assert_eq!(d("stpes", "steps"), 1);
        assert_eq!(d("ab", "ba"), 1);
        assert_eq!(d("", "abc"), 3);
        assert_eq!(d("abc", ""), 3);
        assert_eq!(d("ca", "abc"), 3);
    }

    #[test]
    fn long_keys_get_no_hint_and_stay_fast() {
        let key = "s".repeat(1_000_000);
        let start = std::time::Instant::now();
        assert_eq!(closest(&key, STEP_KEYS), None);
        assert!(start.elapsed() < std::time::Duration::from_secs(1));
        // At the cap a hint is still possible.
        let near = format!("{}x", "requires_approval");
        assert_eq!(closest(&near, STEP_KEYS), Some("requires_approval"));
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
        for text in [
            "\u{feff}# Standard version: 1.1.0\nw: {}\n",
            "---\n# Standard version: 1.1.0\nw: {}\n",
            "%YAML 1.2\n---\n# Standard version: 1.1.0\nw: {}\n",
            "\n# a comment\n\n# Standard version: 1.1.0\n",
        ] {
            assert_eq!(header_version(text).as_deref(), Some("1.1.0"), "{text:?}");
        }
        for bad in ["+1.+1", " 1.1 ", "1.1 ", "1..1", "1.1.", "-1.1", "1.x"] {
            assert_eq!(parse_version(bad), None, "{bad:?}");
        }
        // Leading zeros are digits; the version is still 1.1.
        assert_eq!(parse_version("01.01"), Some((1, 1)));
    }
}
