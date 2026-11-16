//! Ontology edges, safety flags, unknown fields and spec versions
//! (design-114 §4–§5).

use std::collections::{HashMap, HashSet};

use serde_json::{Map, Value};

use super::{Context, Report, StepLoc};
use crate::diag::{Code, Diagnostic};
use crate::expr::ast::{CmpOp, Expr};
use crate::ontology::{Capability, EdgeType, Risk};
use crate::profile::Policy;

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
    "grounding",
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
    "delay",
    "approval",
    "after_deferral",
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

/// Standard versions this validator implements (STANDARD v1.2 §11.5: a
/// validator for 1.2 supports 1.0, 1.1 and 1.2).
pub(crate) const SUPPORTED_VERSIONS: &[(u64, u64)] = &[(1, 0), (1, 1), (1, 2)];

/// [`SUPPORTED_VERSIONS`] as text, for messages: `1.0, 1.1, 1.2`.
fn supported_list() -> String {
    SUPPORTED_VERSIONS
        .iter()
        .map(|(a, b)| format!("{a}.{b}"))
        .collect::<Vec<_>>()
        .join(", ")
}

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

/// A step's safety flags (§5.2.1): its risk and the three booleans.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Flags {
    pub risk: Risk,
    pub mutation: bool,
    pub requires_checkpoint: bool,
    pub requires_approval: bool,
}

impl Flags {
    /// The least strict flags: low risk, every boolean false. The identity
    /// of [`Flags::join`].
    pub const NONE: Flags = Flags {
        risk: Risk::Low,
        mutation: false,
        requires_checkpoint: false,
        requires_approval: false,
    };

    /// The ontology's flags for a capability.
    pub fn of(node: &Capability) -> Flags {
        Flags {
            risk: node.risk,
            mutation: node.mutation,
            requires_checkpoint: node.requires_checkpoint,
            requires_approval: node.requires_approval,
        }
    }

    /// The stricter of each flag: the higher risk, each boolean true when
    /// either is.
    #[must_use]
    pub fn join(self, other: Flags) -> Flags {
        Flags {
            risk: self.risk.max(other.risk),
            mutation: self.mutation || other.mutation,
            requires_checkpoint: self.requires_checkpoint || other.requires_checkpoint,
            requires_approval: self.requires_approval || other.requires_approval,
        }
    }
}

/// A step's effective flags (§5.2.1), and whether an applied profile
/// requires a person for it (§5.21.3).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Effective {
    pub flags: Flags,
    pub person: bool,
}

/// The effective flags of `step`, a step of capability `node` (§5.2.1):
/// the ontology's, joined with `maxima` (the delegation targets' manifests,
/// §5.15.2, when known), then the step's stricter declarations (a higher
/// `risk`, a boolean declared `true`; `mutation: false` only where the
/// ontology lets a step override it and no maximum sets it), then what the
/// applied profiles raise for the capability at that risk (§5.21.3).
///
/// Every site that needs a step's effective `requires_checkpoint` or
/// `requires_approval` calls this, so that the validator and the executor
/// agree. With `maxima = None` and an empty policy it gives the 1.1 flags.
pub(crate) fn effective(
    node: &Capability,
    step: &Map<String, Value>,
    maxima: Option<Flags>,
    policy: &Policy,
) -> Effective {
    let maxima = maxima.unwrap_or(Flags::NONE);
    let base = Flags::of(node).join(maxima);
    let declared = |k: &str| step.get(k).and_then(Value::as_bool);
    let risk = step
        .get("risk")
        .and_then(Value::as_str)
        .and_then(Risk::parse)
        .map_or(base.risk, |r| r.max(base.risk));
    let mutation = match declared("mutation") {
        Some(true) => true,
        Some(false) if node.mutation_overridable => maxima.mutation,
        _ => base.mutation,
    };
    let mut flags = Flags {
        risk,
        mutation,
        requires_checkpoint: base.requires_checkpoint
            || declared("requires_checkpoint") == Some(true),
        requires_approval: base.requires_approval || declared("requires_approval") == Some(true),
    };
    let raised = policy.raise(&node.id, risk);
    flags.requires_checkpoint |= raised.requires_checkpoint;
    flags.requires_approval |= raised.requires_approval;
    Effective {
        flags,
        person: raised.person,
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
        && declared < cap.risk
    {
        let message = format!(
            "ontology declares risk={} but step declares risk={}; the ontology value applies",
            cap.risk.as_str(),
            declared.as_str()
        );
        report.push(
            loc.diag(Code::SafetyFlagDowngrade, message)
                .at("field", "risk"),
        );
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
    /// Whether the step waits for an event (`wait`) or for time (`delay`)
    /// (§5.13).
    pub waits: bool,
    /// Whether it waits for time before anything else it does (`delay`).
    pub delays: bool,
    /// Whether its only wait is in the workflow it invokes (W608).
    pub nested: bool,
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
                    "'{from}' (step {}) shares parallel_group '{}' with it, so it is not ordered before it",
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

/// Parse `major.minor[.patch]` (digits only; §11.5).
pub(crate) fn parse_version(v: &str) -> Option<(u64, u64)> {
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

/// The version a workflow targets (§11.5): its `spec_version` when that is
/// a string that parses, else the catalog header's version when that parses,
/// else none. Rules this Standard applies only to workflows that target 1.2
/// or later compare this with `(1, 2)`; a workflow that declares no version
/// gets none of them.
pub(crate) fn target(wf: &Map<String, Value>, header: Option<&str>) -> Option<(u64, u64)> {
    wf.get("spec_version")
        .and_then(Value::as_str)
        .and_then(parse_version)
        .or_else(|| header.and_then(parse_version))
}

/// The §11.6 check of the versions a document cites (a profile, an agent
/// manifest, an interoperability mapping): `standard` and `ontology`, each
/// when given. A value that is not a string `MAJOR.MINOR[.PATCH]` is S303; a
/// `standard` this implementation does not support is V109; an `ontology`
/// of another major than `ontology_version` (the loaded ontology's) is V109.
/// A later minor or patch of the same major is accepted. `at` places each
/// diagnostic, given the member it is about (`standard` or `ontology`).
pub fn check_cited(
    standard: Option<&Value>,
    ontology: Option<&Value>,
    ontology_version: &str,
    at: impl Fn(Diagnostic, &str) -> Diagnostic,
) -> Vec<Diagnostic> {
    let mut out = Vec::new();
    let mut cited = |member: &str, v: Option<&Value>| -> Option<(String, (u64, u64))> {
        let v = v?;
        match v.as_str().and_then(|s| parse_version(s).map(|mm| (s, mm))) {
            Some((s, mm)) => Some((s.to_string(), mm)),
            None => {
                let shown = match v {
                    Value::String(s) => format!("'{s}'"),
                    other => other.to_string(),
                };
                out.push(at(
                    Diagnostic::new(
                        Code::SchemaValidationFailed,
                        format!(
                            "'{member}' must be a version string MAJOR.MINOR[.PATCH], such as \"1.2.0\"; found {shown}"
                        ),
                    ),
                    member,
                ));
                None
            }
        }
    };
    let standard = cited("standard", standard);
    let ontology = cited("ontology", ontology);
    if let Some((s, mm)) = standard
        && !SUPPORTED_VERSIONS.contains(&mm)
    {
        out.push(at(
            Diagnostic::new(
                Code::UnsupportedSpecVersion,
                format!(
                    "the document cites standard {s}, which is not supported (supported: {})",
                    supported_list()
                ),
            ),
            "standard",
        ));
    }
    let loaded_major = ontology_version
        .split('.')
        .next()
        .and_then(|m| m.parse::<u64>().ok());
    if let (Some((o, (major, _))), Some(loaded)) = (ontology, loaded_major)
        && major != loaded
    {
        out.push(at(
            Diagnostic::new(
                Code::UnsupportedSpecVersion,
                format!(
                    "the document cites ontology {o}, but this implementation uses ontology {ontology_version}; another major is not compatible (§11.6)"
                ),
            ),
            "ontology",
        ));
    }
    out
}

/// W605 when neither `spec_version` nor the file header names a version;
/// V109 when the named version is not supported; W616 for each feature
/// newer than the version a workflow targets ([`FEATURES`]).
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
        Some(mm) if SUPPORTED_VERSIONS.contains(&mm) => {
            newer_features(wf, mm, version, field == "# Standard version", at, report);
        }
        _ => report.push(
            at(Diagnostic::new(
                Code::UnsupportedSpecVersion,
                format!(
                    "standard version '{version}' is not supported (supported: {})",
                    supported_list()
                ),
            ))
            .at("field", field),
        ),
    }
}

/// A feature a Standard version after 1.0 added (§11.5): a workflow that
/// targets an earlier version and uses it gets W616 at its first use.
pub(crate) struct Feature {
    /// The version that added it.
    pub since: (u64, u64),
    /// How a message names it.
    pub name: &'static str,
    /// The field of its first use in a workflow, if the workflow uses it.
    pub first_use: fn(&Map<String, Value>) -> Option<String>,
}

/// §11.5's table of features new after 1.0, in the order W616 reports them.
/// Features that need an extension are covered by
/// `workflow_extensions.requires`; the advisory `supports_*` flags and
/// `invoke`'s `workflow_id` are 1.0. Each 1.2 workstream appends its
/// entries (S2a, S2b, S3, S4, S5; RECONCILIATION C12).
pub(crate) const FEATURES: &[Feature] = &[
    Feature {
        since: (1, 1),
        name: "'workflow_extensions.requires'",
        first_use: |wf| {
            matches!(wf.get("workflow_extensions"), Some(Value::Object(ext)) if ext.contains_key("requires"))
                .then(|| "workflow_extensions.requires".to_string())
        },
    },
    Feature {
        since: (1, 1),
        name: "gate 'phase'",
        first_use: |wf| first_in_items(wf, "gates", |g| g.contains_key("phase").then_some("phase")),
    },
    Feature {
        since: (1, 1),
        name: "gate action 'end'",
        first_use: |wf| {
            first_in_items(wf, "gates", |g| {
                (g.get("action").and_then(Value::as_str) == Some("end")).then_some("action")
            })
        },
    },
    Feature {
        since: (1, 1),
        name: "the 'in' operator",
        first_use: |wf| {
            for (i, step) in objects(wf.get("steps")) {
                if uses_in(step.get("condition")) {
                    return Some(format!("steps[{i}].condition"));
                }
                for (g, gate) in objects(step.get("gates")) {
                    if uses_in(gate.get("when")) {
                        return Some(format!("steps[{i}].gates[{g}].when"));
                    }
                }
                for (f, fm) in objects(step.get("failure_modes")) {
                    if uses_in(fm.get("when")) {
                        return Some(format!("steps[{i}].failure_modes[{f}].when"));
                    }
                }
            }
            None
        },
    },
    Feature {
        since: (1, 1),
        name: "failure-mode 'when'",
        first_use: |wf| {
            first_in_items(wf, "failure_modes", |fm| {
                fm.contains_key("when").then_some("when")
            })
        },
    },
    Feature {
        since: (1, 1),
        name: "failure-mode 'on_error'",
        first_use: |wf| {
            first_in_items(wf, "failure_modes", |fm| {
                fm.contains_key("on_error").then_some("on_error")
            })
        },
    },
    // S2a (§5.14, §5.17): the approver's identity requirements.
    Feature {
        since: (1, 2),
        name: "approver 'sender_check'",
        first_use: |wf| first_approver_field(wf, "sender_check"),
    },
    Feature {
        since: (1, 2),
        name: "approver 'accept_trust_classes'",
        first_use: |wf| first_approver_field(wf, "accept_trust_classes"),
    },
    // S2b (§6.4): an `audit` step's `require_record`, which the executor
    // itself reads (an earlier consumer would let the step complete).
    Feature {
        since: (1, 2),
        name: "the audit input 'require_record'",
        first_use: |wf| {
            objects(wf.get("steps")).into_iter().find_map(|(i, step)| {
                (step.get("capability").and_then(Value::as_str) == Some("audit")
                    && step
                        .get("input_bindings")
                        .and_then(|b| b.get("require_record"))
                        .is_some())
                .then(|| format!("steps[{i}].input_bindings.require_record"))
            })
        },
    },
    // S4 (§5.20, §5.12): the grounding extension with its field, and F505
    // as a code a failure mode fires on.
    Feature {
        since: (1, 2),
        name: "extension 'grounding@1' and its field 'grounding'",
        first_use: |wf| {
            wf.get("workflow_extensions")
                .and_then(|e| e.get("requires"))
                .and_then(Value::as_array)
                .and_then(|r| r.iter().position(|x| x == "grounding@1"))
                .map(|i| format!("workflow_extensions.requires[{i}]"))
        },
    },
    Feature {
        since: (1, 2),
        name: "F505 in a failure mode's 'on_error'",
        first_use: |wf| {
            first_in_items(wf, "failure_modes", |fm| {
                let fires = match fm.get("on_error") {
                    Some(Value::String(c)) => c == "F505",
                    Some(Value::Array(a)) => a.iter().any(|c| c == "F505"),
                    _ => false,
                };
                fires.then_some("on_error")
            })
        },
    },
    // S5 (§4.5): a memory step's `scope`, which the executor itself checks
    // against the output (an earlier consumer would store elsewhere).
    Feature {
        since: (1, 2),
        name: "the persist and recall input 'scope'",
        first_use: |wf| {
            objects(wf.get("steps")).into_iter().find_map(|(i, step)| {
                (matches!(
                    step.get("capability").and_then(Value::as_str),
                    Some("persist" | "recall")
                ) && step
                    .get("input_bindings")
                    .and_then(|b| b.get("scope"))
                    .is_some())
                .then(|| format!("steps[{i}].input_bindings.scope"))
            })
        },
    },
];

/// The field `steps[i].approval.approver.<key>` of the first step whose
/// approval's approver names `key`.
fn first_approver_field(wf: &Map<String, Value>, key: &str) -> Option<String> {
    objects(wf.get("steps")).into_iter().find_map(|(i, step)| {
        step.get("approval")
            .and_then(|a| a.get("approver"))
            .and_then(Value::as_object)
            .is_some_and(|ap| ap.contains_key(key))
            .then(|| format!("steps[{i}].approval.approver.{key}"))
    })
}

/// The mappings in a list, with their indices.
fn objects(v: Option<&Value>) -> Vec<(usize, &Map<String, Value>)> {
    match v {
        Some(Value::Array(a)) => a
            .iter()
            .enumerate()
            .filter_map(|(i, v)| Some((i, v.as_object()?)))
            .collect(),
        _ => Vec::new(),
    }
}

/// The field `steps[i].<list>[j].<key>` of the first item, in step order,
/// of a step's `list` (`gates`, `failure_modes`) for which `key` names one.
fn first_in_items(
    wf: &Map<String, Value>,
    list: &str,
    key: impl Fn(&Map<String, Value>) -> Option<&'static str>,
) -> Option<String> {
    objects(wf.get("steps")).into_iter().find_map(|(i, step)| {
        objects(step.get(list))
            .into_iter()
            .find_map(|(j, item)| key(item).map(|k| format!("steps[{i}].{list}[{j}].{k}")))
    })
}

/// Whether an expression that parses uses the `in` operator.
fn uses_in(v: Option<&Value>) -> bool {
    let Some(Ok(e)) = v.and_then(Value::as_str).map(crate::expr::parse) else {
        return false;
    };
    let mut stack = vec![&e];
    while let Some(e) = stack.pop() {
        match e {
            Expr::Cmp(CmpOp::In, ..) => return true,
            Expr::Cmp(_, l, r, _) => stack.extend([&**l, &**r]),
            Expr::Not(x, _) => stack.push(x),
            Expr::And(v) | Expr::Or(v) => stack.extend(v),
            Expr::Lit(..) | Expr::Ref(_) => {}
        }
    }
    false
}

/// W616 for a feature new in `since` used at `field` by something that
/// targets `version` (as declared: `1.0` or `1.0.0`), declared by a
/// workflow's `spec_version` or, when `by_header`, by the file's header.
/// Shared by the workflow check and S3's catalog-manifest check.
pub(crate) fn version_feature_diag(
    name: &str,
    since: (u64, u64),
    version: &str,
    by_header: bool,
    field: impl Into<String>,
) -> Diagnostic {
    let (since_major, since_minor) = since;
    let target = parse_version(version).map_or_else(
        || version.to_string(),
        |(major, minor)| format!("{major}.{minor}"),
    );
    // A header cannot override a workflow's own spec_version.
    let (declared_in, fix) = if by_header {
        (
            "the file's '# Standard version' header",
            format!(
                "declare spec_version \"{since_major}.{since_minor}\" or a {since_major}.{since_minor} header"
            ),
        )
    } else {
        (
            "its 'spec_version'",
            format!("declare spec_version \"{since_major}.{since_minor}\""),
        )
    };
    Diagnostic::new(
        Code::VersionFeatureMismatch,
        format!(
            "the workflow targets standard {version} by {declared_in}, but {name} is new in {since_major}.{since_minor} and a {target} consumer does not know it"
        ),
    )
    .at("field", field.into())
    .suggest(fix)
}

/// W616, once per feature at its first use, for each feature of
/// [`FEATURES`] newer than `target` (§11.5).
fn newer_features(
    wf: &Map<String, Value>,
    target: (u64, u64),
    version: &str,
    by_header: bool,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    for feature in FEATURES.iter().filter(|f| f.since > target) {
        if let Some(field) = (feature.first_use)(wf) {
            report.push(at(version_feature_diag(
                feature.name,
                feature.since,
                version,
                by_header,
                field,
            )));
        }
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

    #[test]
    fn targets() {
        let wf = |v: Value| v.as_object().unwrap().clone();
        let t = |w: Value, h: Option<&str>| target(&wf(w), h);
        assert_eq!(
            t(serde_json::json!({"spec_version": "1.2"}), None),
            Some((1, 2))
        );
        // spec_version takes precedence over the header.
        assert_eq!(
            t(serde_json::json!({"spec_version": "1.1.0"}), Some("1.2.0")),
            Some((1, 1))
        );
        assert_eq!(t(serde_json::json!({}), Some("1.2.0")), Some((1, 2)));
        // A spec_version that is not a version string leaves the header.
        assert_eq!(
            t(serde_json::json!({"spec_version": 1.2}), Some("1.0")),
            Some((1, 0))
        );
        assert_eq!(
            t(serde_json::json!({"spec_version": "x"}), Some("1.1")),
            Some((1, 1))
        );
        assert_eq!(t(serde_json::json!({}), Some("one")), None);
        assert_eq!(t(serde_json::json!({}), None), None);
        assert_eq!(SUPPORTED_VERSIONS, [(1, 0), (1, 1), (1, 2)]);
    }

    #[test]
    fn cited_versions() {
        let check = |s: Option<Value>, o: Option<Value>| {
            check_cited(s.as_ref(), o.as_ref(), "2.2.0", |d, f| d.at("field", f))
                .into_iter()
                .map(|d| {
                    (
                        d.code.as_str().to_string(),
                        d.location["field"].as_str().unwrap().to_string(),
                    )
                })
                .collect::<Vec<_>>()
        };
        let pair = |c: &str, f: &str| (c.to_string(), f.to_string());
        let j = |s: &str| Some(Value::String(s.into()));
        assert!(check(None, None).is_empty());
        assert!(check(j("1.2.0"), j("2.2.0")).is_empty());
        assert!(check(j("1.0"), j("2.0")).is_empty());
        // A later minor or patch of the same ontology major is accepted.
        assert!(check(j("1.1"), j("2.9.4")).is_empty());
        assert_eq!(check(j("1.3"), None), [pair("V109", "standard")]);
        assert_eq!(check(j("2.0.0"), None), [pair("V109", "standard")]);
        assert_eq!(check(None, j("3.0")), [pair("V109", "ontology")]);
        assert_eq!(check(None, j("1.9.0")), [pair("V109", "ontology")]);
        for bad in [
            j("1"),
            j("v1.2"),
            j("1.2.0.0"),
            Some(serde_json::json!(1.2)),
            Some(Value::Null),
        ] {
            assert_eq!(
                check(bad.clone(), None),
                [pair("S303", "standard")],
                "{bad:?}"
            );
            assert_eq!(
                check(None, bad.clone()),
                [pair("S303", "ontology")],
                "{bad:?}"
            );
        }
        // Both members are checked, standard first.
        assert_eq!(
            check(j("9.9"), j("x")),
            [pair("S303", "ontology"), pair("V109", "standard")]
        );
    }

    fn node(
        id: &str,
        risk: Risk,
        mutation: bool,
        cp: bool,
        ap: bool,
        overridable: bool,
    ) -> Capability {
        Capability {
            id: id.into(),
            layer: "L".into(),
            risk,
            mutation,
            requires_checkpoint: cp,
            requires_approval: ap,
            mutation_overridable: overridable,
            input_schema: serde_json::json!({}),
            output_schema: serde_json::json!({}),
        }
    }

    #[test]
    fn flags_join() {
        let mutate = node("mutate", Risk::High, true, true, true, false);
        let retrieve = node("retrieve", Risk::Low, false, false, false, false);
        assert_eq!(Flags::of(&retrieve), Flags::NONE);
        let m = Flags::of(&mutate);
        assert_eq!(Flags::NONE.join(m), m);
        assert_eq!(m.join(Flags::NONE), m);
        let a = Flags {
            risk: Risk::Medium,
            requires_approval: true,
            ..Flags::NONE
        };
        let b = Flags {
            mutation: true,
            requires_checkpoint: true,
            ..Flags::NONE
        };
        assert_eq!(
            a.join(b),
            Flags {
                risk: Risk::Medium,
                mutation: true,
                requires_checkpoint: true,
                requires_approval: true
            }
        );
    }

    #[test]
    fn effective_flags() {
        let none = Policy::default();
        let step = |v: Value| v.as_object().unwrap().clone();
        let eff =
            |n: &Capability, s: Value, maxima: Option<Flags>| effective(n, &step(s), maxima, &none);
        let retrieve = node("retrieve", Risk::Low, false, false, false, false);
        let mutate = node("mutate", Risk::High, true, true, true, false);
        let audit = node("audit", Risk::Low, true, false, false, true);
        // The ontology's flags, with no person.
        let e = eff(&mutate, serde_json::json!({}), None);
        assert_eq!(e.flags, Flags::of(&mutate));
        assert!(!e.person);
        // Stricter declarations take effect; weaker ones do not (W602).
        let e = eff(
            &retrieve,
            serde_json::json!({"risk": "medium", "requires_checkpoint": true, "requires_approval": true, "mutation": true}),
            None,
        );
        assert_eq!(
            e.flags,
            Flags {
                risk: Risk::Medium,
                mutation: true,
                requires_checkpoint: true,
                requires_approval: true
            }
        );
        let e = eff(
            &mutate,
            serde_json::json!({"risk": "low", "requires_checkpoint": false, "requires_approval": false, "mutation": false}),
            None,
        );
        assert_eq!(e.flags, Flags::of(&mutate));
        // An unknown risk or a non-boolean flag declares nothing.
        let e = eff(
            &retrieve,
            serde_json::json!({"risk": "extreme", "requires_approval": "yes"}),
            None,
        );
        assert_eq!(e.flags, Flags::NONE);
        // mutation: false is honoured where the ontology allows it...
        assert!(
            !eff(&audit, serde_json::json!({"mutation": false}), None)
                .flags
                .mutation
        );
        assert!(eff(&audit, serde_json::json!({}), None).flags.mutation);
        // ...unless a maximum sets it: the exception is the ontology's only.
        let maxima = Flags {
            mutation: true,
            ..Flags::NONE
        };
        assert!(
            eff(&audit, serde_json::json!({"mutation": false}), Some(maxima))
                .flags
                .mutation
        );
        // Maxima join the ontology's flags.
        let maxima = Flags {
            risk: Risk::High,
            requires_approval: true,
            ..Flags::NONE
        };
        let e = eff(&retrieve, serde_json::json!({}), Some(maxima));
        assert_eq!(
            e.flags,
            Flags {
                risk: Risk::High,
                requires_approval: true,
                ..Flags::NONE
            }
        );
    }

    #[test]
    fn feature_table() {
        // The 1.1 features, in report order; a 1.1 or 1.2 target gets none
        // of them.
        let names: Vec<_> = FEATURES
            .iter()
            .filter(|f| f.since == (1, 1))
            .map(|f| f.name)
            .collect();
        assert_eq!(names.len(), 6);
        assert!(
            FEATURES
                .iter()
                .all(|f| f.since > (1, 0) && SUPPORTED_VERSIONS.contains(&f.since))
        );
        let wf = serde_json::json!({"workflow_extensions": {"requires": []}, "steps": [
            {"condition": "\"a\" in [\"a\"]", "gates": [{"when": "true", "phase": "after"}]}]});
        let wf = wf.as_object().unwrap();
        let fields = |target: (u64, u64), version: &str| {
            let mut report = Report::default();
            newer_features(wf, target, version, false, &|d| d, &mut report);
            report
                .diagnostics
                .iter()
                .map(|d| d.location["field"].as_str().unwrap().to_string())
                .collect::<Vec<_>>()
        };
        assert_eq!(
            fields((1, 0), "1.0"),
            [
                "workflow_extensions.requires",
                "steps[0].gates[0].phase",
                "steps[0].condition"
            ]
        );
        assert!(fields((1, 1), "1.1").is_empty());
        assert!(fields((1, 2), "1.2.0").is_empty());
        let d = version_feature_diag("gate 'phase'", (1, 1), "1.0.0", true, "f");
        assert_eq!(
            d.message,
            "the workflow targets standard 1.0.0 by the file's '# Standard version' header, but gate 'phase' is new in 1.1 and a 1.0 consumer does not know it"
        );
        assert_eq!(
            d.suggestion.as_deref(),
            Some("declare spec_version \"1.1\" or a 1.1 header")
        );
    }
}
