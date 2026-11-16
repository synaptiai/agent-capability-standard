//! Domain profiles applied to a run, a safety layer's calls or a validation
//! (STANDARD v1.2 §5.21).
//!
//! [`Policy::load`] checks the profiles a host, layer or validator is given
//! (§5.21.2) and keeps them; [`Policy::raise`] is what they add to a step's
//! or call's effective flags (§5.21.3), which `semantics::effective` applies
//! for the validator and the executor alike. The other rules a profile puts
//! in force (grounding, minimum confidence, destinations, trust weights) are
//! read from the policy by whoever applies them.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value, json};

use crate::diag::{Code, Diagnostic};
use crate::ontology::{EdgeType, Ontology, Risk};
use crate::validate::Report;
use crate::validate::identity::TRUST_CLASSES;
use crate::validate::semantics;

/// A `risk_thresholds` value: a level, or `none` (no level).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Level {
    None,
    Low,
    Medium,
    High,
}

impl Level {
    fn parse(s: &str) -> Option<Level> {
        match s {
            "none" => Some(Level::None),
            "low" => Some(Level::Low),
            "medium" => Some(Level::Medium),
            "high" => Some(Level::High),
            _ => None,
        }
    }

    fn rank(self) -> u8 {
        self as u8
    }
}

fn rank(risk: Risk) -> u8 {
    match risk {
        Risk::Low => 1,
        Risk::Medium => 2,
        Risk::High => 3,
    }
}

/// A `checkpoint_policy` value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CheckpointRule {
    Always,
    HighRisk,
    MediumRisk,
    Never,
}

impl CheckpointRule {
    fn parse(s: &str) -> Option<CheckpointRule> {
        match s {
            "always" => Some(CheckpointRule::Always),
            "high_risk" => Some(CheckpointRule::HighRisk),
            "medium_risk" => Some(CheckpointRule::MediumRisk),
            "never" => Some(CheckpointRule::Never),
            _ => None,
        }
    }

    fn covers(self, risk: Risk) -> bool {
        match self {
            CheckpointRule::Always => true,
            CheckpointRule::HighRisk => risk == Risk::High,
            CheckpointRule::MediumRisk => risk >= Risk::Medium,
            CheckpointRule::Never => false,
        }
    }
}

/// The capability `checkpoint_policy` never applies to: a checkpoint step
/// cannot need a checkpoint before itself (§5.21.3). `*` does not cover it,
/// and the key is refused (S303).
pub const EXEMPT_FROM_CHECKPOINT_POLICY: &str = "checkpoint";

/// The members of `risk_thresholds` (closed, §5.21.2).
pub const THRESHOLD_KEYS: &[&str] = &[
    "auto_approve",
    "require_review",
    "require_human",
    "block_autonomous",
];

/// The members of `evidence_policy` (closed, §5.21.2).
pub const EVIDENCE_KEYS: &[&str] = &[
    "required_anchor_types",
    "minimum_confidence",
    "require_grounding",
];

/// The top-level members of a profile (§5.21.2); any other, but an `x-`
/// member, is W604.
pub const PROFILE_KEYS: &[&str] = &[
    "domain",
    "version",
    "standard",
    "ontology",
    "description",
    "trust_weights",
    "risk_thresholds",
    "checkpoint_policy",
    "evidence_policy",
    "allowed_destinations",
    "domain_sources",
    "workflows",
    "trust_model_reviewed",
    "trust_model_reviewed_at",
    "compliance",
];

/// The `type` values of a `domain_sources` entry.
const SOURCE_TYPES: &[&str] = &[
    "api",
    "sensor",
    "database",
    "human",
    "document",
    "system_log",
];

/// One loaded profile.
#[derive(Debug, Clone)]
pub struct Profile {
    /// Its `domain`, or `#<i>` (its position) when it has no valid one.
    pub label: String,
    auto_approve: Option<Level>,
    require_review: Option<Level>,
    require_human: Option<Level>,
    block_autonomous: BTreeSet<String>,
    checkpoint: BTreeMap<String, CheckpointRule>,
    pub require_grounding: Vec<String>,
    pub required_anchor_types: Option<Vec<String>>,
    pub minimum_confidence: Option<f64>,
    pub allowed_destinations: Option<Vec<String>>,
    pub trust_weights: BTreeMap<String, f64>,
}

/// The profiles applied to a run, a layer's calls or a validation, loaded
/// and checked. The default applies none.
#[derive(Debug, Clone, Default)]
pub struct Policy {
    profiles: Vec<Profile>,
    raw: Vec<Value>,
}

/// What the applied profiles add to one step's or call's flags (§5.21.3).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Raise {
    pub requires_checkpoint: bool,
    pub requires_approval: bool,
    /// A person must decide (§5.21.3 "A person").
    pub person: bool,
}

/// Why an output's `confidence` fails an applied minimum (§5.21.3).
#[derive(Debug, Clone, PartialEq)]
pub enum ConfidenceFault {
    /// Not a number from 0 to 1: the member's JSON text, cut to 64
    /// characters (F504, `invalid_confidence`).
    Invalid(String),
    /// A number below the minimum (F504, `below_minimum_confidence`).
    Below(f64),
}

/// A number from 0 to 1 (a boolean is not a number; JSON has no NaN).
fn unit(v: &Value) -> Option<f64> {
    v.as_f64().filter(|x| (0.0..=1.0).contains(x))
}

fn kebab(s: &str) -> bool {
    // ^[a-z][a-z0-9]*(-[a-z0-9]+)*$
    let mut words = s.split('-');
    let Some(first) = words.next() else {
        return false;
    };
    let mut chars = first.chars();
    chars.next().is_some_and(|c| c.is_ascii_lowercase())
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        && words.all(|w| {
            !w.is_empty()
                && w.chars()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        })
}

fn semver(s: &str) -> bool {
    let parts: Vec<&str> = s.split('.').collect();
    parts.len() == 3
        && parts
            .iter()
            .all(|p| !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()))
}

fn source_key(s: &str) -> bool {
    // ^[a-z][a-z0-9_.-]*$
    let mut chars = s.chars();
    chars.next().is_some_and(|c| c.is_ascii_lowercase())
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || "_.-".contains(c))
}

fn date(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 10
        && b.iter().enumerate().all(|(i, c)| match i {
            4 | 7 => *c == b'-',
            _ => c.is_ascii_digit(),
        })
}

fn shown(v: &Value) -> String {
    match v {
        Value::String(s) => format!("'{s}'"),
        other => other.to_string(),
    }
}

/// What a list member of a profile requires of its entries beyond their
/// type (§5.21.2).
#[derive(Clone, Copy, PartialEq, Eq)]
enum Entries {
    /// Any entries: a repeated one has no further effect.
    Any,
    /// Distinct entries: a repeated one is S303.
    Distinct,
    /// At least one entry, each distinct.
    DistinctNonEmpty,
}

/// Loads one profile, reporting its diagnostics.
struct Loader<'a> {
    ontology: &'a Ontology,
    label: String,
    report: &'a mut Report,
}

impl Loader<'_> {
    fn push(&mut self, code: Code, field: &str, message: String) {
        self.push_hint(code, field, message, None);
    }

    fn push_hint(&mut self, code: Code, field: &str, message: String, hint: Option<&str>) {
        let mut d = Diagnostic::new(code, message)
            .at("profile", self.label.clone())
            .at("field", field);
        if let Some(h) = hint {
            d = d.suggest(format!("did you mean '{h}'?"));
        }
        self.report.push(d);
    }

    /// V101 for an id the ontology does not define, with the closest one.
    fn capability(&mut self, field: &str, id: &str, what: &str) -> bool {
        if self.ontology.get(id).is_some() {
            return true;
        }
        let known: Vec<&str> = self
            .ontology
            .capabilities
            .keys()
            .map(String::as_str)
            .collect();
        let hint = semantics::closest(id, &known).map(str::to_string);
        self.push_hint(
            Code::UnknownCapability,
            field,
            format!("{what} '{id}', which is not a capability of the ontology"),
            hint.as_deref(),
        );
        false
    }

    /// A list of strings, each kept when `item` accepts it. `entries` says
    /// what §5.21.2 requires of the entries beyond their type: a list whose
    /// row does not say "distinct" may repeat one, to no further effect.
    fn strings(
        &mut self,
        field: &str,
        v: &Value,
        entries: Entries,
        mut item: impl FnMut(&mut Self, &str, &str) -> bool,
    ) -> Vec<String> {
        let Value::Array(items) = v else {
            self.push(
                Code::SchemaValidationFailed,
                field,
                format!("'{field}' must be a list, found {}", shown(v)),
            );
            return Vec::new();
        };
        if entries == Entries::DistinctNonEmpty && items.is_empty() {
            self.push(
                Code::SchemaValidationFailed,
                field,
                format!("'{field}' must list at least one entry"),
            );
        }
        let mut seen: Vec<&str> = Vec::new();
        let mut out = Vec::new();
        for (i, x) in items.iter().enumerate() {
            let at = format!("{field}[{i}]");
            let Some(s) = x.as_str() else {
                self.push(
                    Code::SchemaValidationFailed,
                    &at,
                    format!("'{at}' must be a string, found {}", shown(x)),
                );
                continue;
            };
            if entries != Entries::Any && seen.contains(&s) {
                self.push(
                    Code::SchemaValidationFailed,
                    &at,
                    format!("'{s}' is listed twice in '{field}'"),
                );
                continue;
            }
            seen.push(s);
            if item(self, &at, s) {
                out.push(s.to_string());
            }
        }
        out
    }

    /// A mapping member: `None` (reported) when it is not one.
    fn mapping<'v>(&mut self, field: &str, v: &'v Value) -> Option<&'v Map<String, Value>> {
        match v {
            Value::Object(m) => Some(m),
            other => {
                self.push(
                    Code::SchemaValidationFailed,
                    field,
                    format!("'{field}' must be a mapping, found {}", shown(other)),
                );
                None
            }
        }
    }

    /// Every member of a closed mapping that is not one of `known`: S303,
    /// an `x-` member included.
    fn closed(&mut self, field: &str, m: &Map<String, Value>, known: &[&str]) {
        for key in m.keys().filter(|k| !known.contains(&k.as_str())) {
            let hint = semantics::closest(key, known);
            self.push_hint(
                Code::SchemaValidationFailed,
                &format!("{field}.{key}"),
                format!(
                    "'{field}' has no member '{key}' in this version; its members are {}",
                    known.join(", ")
                ),
                hint,
            );
        }
    }

    fn unit_member(&mut self, field: &str, v: &Value) -> Option<f64> {
        let x = unit(v);
        if x.is_none() {
            self.push(
                Code::SchemaValidationFailed,
                field,
                format!("'{field}' must be a number from 0 to 1, found {}", shown(v)),
            );
        }
        x
    }

    fn level(&mut self, field: &str, v: &Value, critical: bool) -> Option<Level> {
        let s = v.as_str();
        if critical && s == Some("critical") {
            self.push(
                Code::DeprecatedForm,
                field,
                format!(
                    "'{field}: critical' is deprecated and read as none: no risk level is above high"
                ),
            );
            return Some(Level::None);
        }
        let level = s.and_then(Level::parse);
        if level.is_none() {
            self.push(
                Code::SchemaValidationFailed,
                field,
                format!(
                    "'{field}' must be none, low, medium or high, found {}",
                    shown(v)
                ),
            );
        }
        level
    }

    fn load(mut self, value: &Value) -> Profile {
        let mut p = Profile {
            label: self.label.clone(),
            auto_approve: None,
            require_review: None,
            require_human: None,
            block_autonomous: BTreeSet::new(),
            checkpoint: BTreeMap::new(),
            require_grounding: Vec::new(),
            required_anchor_types: None,
            minimum_confidence: None,
            allowed_destinations: None,
            trust_weights: BTreeMap::new(),
        };
        let Value::Object(m) = value else {
            self.push(
                Code::SchemaValidationFailed,
                "",
                format!("a domain profile must be a mapping, found {}", shown(value)),
            );
            return p;
        };
        match m.get("domain") {
            None => self.push(
                Code::MissingRequiredField,
                "domain",
                "a domain profile needs 'domain'".into(),
            ),
            Some(Value::String(d)) if kebab(d) => {}
            Some(other) => self.push(
                Code::SchemaValidationFailed,
                "domain",
                format!(
                    "'domain' must be lower-case letters and digits in words joined by '-', found {}",
                    shown(other)
                ),
            ),
        }
        match m.get("version") {
            None => self.push(
                Code::MissingRequiredField,
                "version",
                "a domain profile needs 'version'".into(),
            ),
            Some(Value::String(v)) if semver(v) => {}
            Some(other) => self.push(
                Code::SchemaValidationFailed,
                "version",
                format!(
                    "'version' must be the profile's version MAJOR.MINOR.PATCH, such as \"1.0.0\"; found {}",
                    shown(other)
                ),
            ),
        }
        // A run saves its profiles as given (§5.19.4) and every record's
        // digest covers them (§5.18.8): each member must have an exact JSON
        // form, as a run's inputs must (§5.14).
        for (key, v) in m {
            if let Err(e) = crate::exec::ijson(v) {
                self.push(
                    Code::SchemaValidationFailed,
                    key,
                    format!("'{key}' has no exact JSON (I-JSON, RFC 7493) form: {e}"),
                );
            }
        }
        let label = self.label.clone();
        let loaded = self.ontology.version.clone().unwrap_or_default();
        for d in semantics::check_cited(
            m.get("standard"),
            m.get("ontology"),
            &loaded,
            |d, member| d.at("profile", label.clone()).at("field", member),
        ) {
            self.report.push(d);
        }
        if let Some(v) = m.get("trust_weights")
            && let Some(weights) = self.mapping("trust_weights", v)
        {
            for (key, w) in weights {
                let field = format!("trust_weights.{key}");
                let key_ok = match key.strip_prefix("trust_class:") {
                    Some(class) if TRUST_CLASSES.contains(&class) => true,
                    Some(class) => {
                        self.push(
                            Code::SchemaValidationFailed,
                            &field,
                            format!(
                                "'{class}' is not a trust class ({})",
                                TRUST_CLASSES.join(", ")
                            ),
                        );
                        false
                    }
                    None if source_key(key) => true,
                    None => {
                        self.push(
                            Code::SchemaValidationFailed,
                            &field,
                            format!(
                                "'{key}' is neither trust_class:<class> nor a source key (a lower-case letter, then lower-case letters, digits, '_', '.' or '-')"
                            ),
                        );
                        false
                    }
                };
                if let Some(x) = self.unit_member(&field, w)
                    && key_ok
                {
                    p.trust_weights.insert(key.clone(), x);
                }
            }
        }
        if let Some(v) = m.get("risk_thresholds")
            && let Some(t) = self.mapping("risk_thresholds", v)
        {
            if let Some(v) = t.get("auto_approve") {
                p.auto_approve = self.level("risk_thresholds.auto_approve", v, false);
            }
            if let Some(v) = t.get("require_review") {
                p.require_review = self.level("risk_thresholds.require_review", v, true);
            }
            if let Some(v) = t.get("require_human") {
                p.require_human = self.level("risk_thresholds.require_human", v, true);
            }
            if let Some(v) = t.get("block_autonomous") {
                let ids = self.strings(
                    "risk_thresholds.block_autonomous",
                    v,
                    Entries::Any,
                    |l, at, id| l.capability(at, id, "block_autonomous names"),
                );
                p.block_autonomous = ids.into_iter().collect();
            }
            self.closed("risk_thresholds", t, THRESHOLD_KEYS);
        }
        if let Some(v) = m.get("checkpoint_policy")
            && let Some(c) = self.mapping("checkpoint_policy", v)
        {
            for (key, rule) in c {
                let field = format!("checkpoint_policy.{key}");
                let key_ok = if key == "*" {
                    true
                } else if key == EXEMPT_FROM_CHECKPOINT_POLICY {
                    self.push(
                        Code::SchemaValidationFailed,
                        &field,
                        "a checkpoint step never needs a checkpoint before it, so 'checkpoint' is not a checkpoint_policy key ('*' does not cover it either)".into(),
                    );
                    false
                } else {
                    self.capability(&field, key, "checkpoint_policy has the key")
                };
                let Some(parsed) = rule.as_str().and_then(CheckpointRule::parse) else {
                    self.push(
                        Code::SchemaValidationFailed,
                        &field,
                        format!(
                            "'{field}' must be always, high_risk, medium_risk or never, found {}",
                            shown(rule)
                        ),
                    );
                    continue;
                };
                // The ontology requires a checkpoint before `key` by the
                // capability's flag or by a `checkpoint` `requires` edge
                // (`rollback`, §4.3).
                if parsed == CheckpointRule::Never
                    && (self
                        .ontology
                        .get(key)
                        .is_some_and(|n| n.requires_checkpoint)
                        || self
                            .ontology
                            .incoming(key, EdgeType::Requires)
                            .contains(&EXEMPT_FROM_CHECKPOINT_POLICY))
                {
                    self.push(
                        Code::SafetyFlagDowngrade,
                        &field,
                        format!(
                            "'never' has no effect: the ontology requires a checkpoint before '{key}', and a profile only tightens"
                        ),
                    );
                }
                if key_ok {
                    p.checkpoint.insert(key.clone(), parsed);
                }
            }
        }
        if let Some(v) = m.get("evidence_policy")
            && let Some(e) = self.mapping("evidence_policy", v)
        {
            if let Some(v) = e.get("required_anchor_types") {
                let kinds = self.strings(
                    "evidence_policy.required_anchor_types",
                    v,
                    Entries::DistinctNonEmpty,
                    |l, at, k| {
                        let ok = crate::grounding::is_kind(k);
                        if !ok {
                            l.push(
                                Code::SchemaValidationFailed,
                                at,
                                format!(
                                    "'{k}' is not an anchor kind ({}, or a vendor kind x-...)",
                                    crate::grounding::KINDS.join(", ")
                                ),
                            );
                        }
                        ok
                    },
                );
                p.required_anchor_types = Some(kinds);
            }
            if let Some(v) = e.get("minimum_confidence") {
                p.minimum_confidence = self.unit_member("evidence_policy.minimum_confidence", v);
            }
            if let Some(v) = e.get("require_grounding") {
                p.require_grounding = self.strings(
                    "evidence_policy.require_grounding",
                    v,
                    Entries::Distinct,
                    |l, at, id| l.capability(at, id, "require_grounding names"),
                );
            }
            self.closed("evidence_policy", e, EVIDENCE_KEYS);
        }
        if let Some(v) = m.get("allowed_destinations") {
            let patterns =
                self.strings("allowed_destinations", v, Entries::Any, |l, at, pattern| {
                    match crate::destination::check_pattern(pattern) {
                        Ok(_) => true,
                        Err(e) => {
                            l.push(
                                Code::SchemaValidationFailed,
                                at,
                                format!("'{pattern}' is not a destination pattern (§4.4.2): {e}"),
                            );
                            false
                        }
                    }
                });
            if v.is_array() {
                p.allowed_destinations = Some(patterns);
            }
        }
        self.informative(m);
        for key in m.keys() {
            if PROFILE_KEYS.contains(&key.as_str()) || key.starts_with("x-") {
                continue;
            }
            let hint = semantics::closest(key, PROFILE_KEYS);
            self.push_hint(
                Code::UnknownField,
                key,
                format!("unknown profile member '{key}' is ignored"),
                hint,
            );
        }
        p
    }

    /// The informative members: no effect, but checked (§5.21.2).
    fn informative(&mut self, m: &Map<String, Value>) {
        let wrong = |l: &mut Self, field: &str, what: &str, v: &Value| {
            l.push(
                Code::SchemaValidationFailed,
                field,
                format!("'{field}' must be {what}, found {}", shown(v)),
            );
        };
        if let Some(v) = m.get("description")
            && !v.is_string()
        {
            wrong(self, "description", "a string", v);
        }
        if let Some(v) = m.get("domain_sources") {
            match v {
                Value::Array(items) => {
                    for (i, s) in items.iter().enumerate() {
                        let at = format!("domain_sources[{i}]");
                        let Value::Object(s) = s else {
                            wrong(self, &at, "a mapping", s);
                            continue;
                        };
                        if let Some(n) = s.get("name")
                            && !n.is_string()
                        {
                            wrong(self, &format!("{at}.name"), "a string", n);
                        }
                        if let Some(t) = s.get("type")
                            && !t.as_str().is_some_and(|t| SOURCE_TYPES.contains(&t))
                        {
                            let one_of = format!("one of {}", SOURCE_TYPES.join(", "));
                            wrong(self, &format!("{at}.type"), &one_of, t);
                        }
                        if let Some(d) = s.get("default_trust") {
                            self.unit_member(&format!("{at}.default_trust"), d);
                        }
                    }
                }
                other => wrong(self, "domain_sources", "a list", other),
            }
        }
        if let Some(v) = m.get("workflows") {
            self.strings("workflows", v, Entries::Any, |_, _, _| true);
        }
        if let Some(v) = m.get("trust_model_reviewed")
            && !v.is_boolean()
        {
            wrong(self, "trust_model_reviewed", "true or false", v);
        }
        if let Some(v) = m.get("trust_model_reviewed_at")
            && !v.as_str().is_some_and(date)
        {
            wrong(self, "trust_model_reviewed_at", "a date YYYY-MM-DD", v);
        }
        if let Some(v) = m.get("compliance")
            && !v.is_object()
        {
            wrong(self, "compliance", "a mapping", v);
        }
    }
}

impl Policy {
    /// Load and check `values`, the profiles given, in order (§5.21.2).
    /// Every diagnostic goes to `report`, located `{profile, field}`. A
    /// profile with an error is still kept, so [`Policy::raise`] stays
    /// total; whoever applies the policy refuses it when the report has an
    /// error.
    pub fn load(values: &[Value], ontology: &Ontology, report: &mut Report) -> Policy {
        let profiles = values
            .iter()
            .enumerate()
            .map(|(i, v)| {
                let label = v
                    .get("domain")
                    .and_then(Value::as_str)
                    .filter(|d| kebab(d))
                    .map_or_else(|| format!("#{i}"), str::to_string);
                Loader {
                    ontology,
                    label,
                    report: &mut *report,
                }
                .load(v)
            })
            .collect();
        Policy {
            profiles,
            raw: values.to_vec(),
        }
    }

    /// No profile is applied.
    pub fn is_empty(&self) -> bool {
        self.profiles.is_empty()
    }

    /// The profiles as given (what a run saves, §5.19.4).
    pub fn raw(&self) -> &[Value] {
        &self.raw
    }

    /// The flags the applied profiles raise for a step or call of
    /// `capability` whose effective risk before profiles is `risk`
    /// (§5.21.3). Each profile applies on its own; the strictest holds.
    pub fn raise(&self, capability: &str, risk: Risk) -> Raise {
        let mut out = Raise::default();
        for p in &self.profiles {
            let r = p.raise(capability, risk);
            out.requires_checkpoint |= r.requires_checkpoint;
            out.requires_approval |= r.requires_approval;
            out.person |= r.person;
        }
        out
    }

    /// The labels of the profiles that require a person for a step of
    /// `capability` at `risk` (the trace's `person_required`).
    pub fn labels_raising(&self, capability: &str, risk: Risk) -> Vec<String> {
        self.profiles
            .iter()
            .filter(|p| p.raise(capability, risk).person)
            .map(|p| p.label.clone())
            .collect()
    }

    /// The highest `minimum_confidence` of the profiles, if any sets one.
    pub fn minimum_confidence(&self) -> Option<f64> {
        self.profiles
            .iter()
            .filter_map(|p| p.minimum_confidence)
            .reduce(f64::max)
    }

    /// One grounding policy (§5.20) per profile with a non-empty
    /// `require_grounding`, in profile order: its `kinds` are the profile's
    /// `required_anchor_types` (any kind when absent).
    pub fn grounding(&self) -> Vec<crate::grounding::Policy> {
        self.profiles
            .iter()
            .filter(|p| !p.require_grounding.is_empty())
            .map(|p| crate::grounding::Policy {
                require: p.require_grounding.clone(),
                kinds: p.required_anchor_types.clone(),
                attested: false,
            })
            .collect()
    }

    /// The destination policies of the profiles that set one (§4.4.2), in
    /// profile order: a send must be allowed by each.
    pub fn destinations(&self) -> Vec<Vec<String>> {
        self.profiles
            .iter()
            .filter_map(|p| p.allowed_destinations.clone())
            .collect()
    }

    /// The first rule of these profiles that this implementation does not
    /// put in force yet, if any: an executor refuses to start or restore a
    /// run under it rather than run as if the rule were absent (§5.21.4).
    /// The grounding check (§5.20) and the destination check (§4.4.2) read
    /// [`Policy::grounding`] and [`Policy::destinations`]; each line goes
    /// when its check is wired to them.
    pub fn unenforced(&self) -> Option<&'static str> {
        if self
            .profiles
            .iter()
            .any(|p| !p.require_grounding.is_empty())
        {
            return Some("a profile's grounding policy (evidence_policy.require_grounding, §5.20)");
        }
        if self
            .profiles
            .iter()
            .any(|p| p.allowed_destinations.is_some())
        {
            return Some("a profile's destination policy (allowed_destinations, §4.4.2)");
        }
        None
    }

    /// The trust weight overrides (§8.3): the lowest any profile gives each
    /// key.
    pub fn trust_weights(&self) -> BTreeMap<String, f64> {
        let mut out: BTreeMap<String, f64> = BTreeMap::new();
        for (k, w) in self.profiles.iter().flat_map(|p| &p.trust_weights) {
            out.entry(k.clone())
                .and_modify(|x| *x = x.min(*w))
                .or_insert(*w);
        }
        out
    }

    /// The rules the profiles put in force besides flags, as JSON:
    /// `{minimum_confidence, grounding: [{require, kinds}], destinations,
    /// trust_weights}` (the shape of the profile `policy` vectors).
    pub fn rules_json(&self) -> Value {
        json!({
            "minimum_confidence": self.minimum_confidence(),
            "grounding": self.grounding().iter().map(|g| json!({
                "require": g.require,
                "kinds": g.kinds,
            })).collect::<Vec<_>>(),
            "destinations": self.destinations(),
            "trust_weights": self.trust_weights(),
        })
    }

    /// The effective flags of a step or call of `capability` under these
    /// profiles, with the step's own `declared` flags (§5.2.1, §5.21.3), as
    /// `{risk, mutation, requires_checkpoint, requires_approval, person}`.
    /// `None` when the ontology has no such capability.
    pub fn flags_json(
        &self,
        ontology: &Ontology,
        capability: &str,
        declared: Option<&Map<String, Value>>,
    ) -> Option<Value> {
        let node = ontology.get(capability)?;
        let mut step = declared.cloned().unwrap_or_default();
        step.insert("capability".into(), json!(capability));
        let e = semantics::effective(node, &step, None, self);
        Some(json!({
            "risk": e.flags.risk.as_str(),
            "mutation": e.flags.mutation,
            "requires_checkpoint": e.flags.requires_checkpoint,
            "requires_approval": e.flags.requires_approval,
            "person": e.person,
        }))
    }
}

impl Profile {
    fn raise(&self, capability: &str, risk: Risk) -> Raise {
        let r = rank(risk);
        let covers_up = |l: Option<Level>| l.is_some_and(|l| l != Level::None && r >= l.rank());
        let review = covers_up(self.require_review);
        let human = covers_up(self.require_human) || self.block_autonomous.contains(capability);
        let approval = self.auto_approve.is_some_and(|l| r > l.rank()) || review || human;
        let mut checkpoint = false;
        if capability != EXEMPT_FROM_CHECKPOINT_POLICY {
            for key in [capability, "*"] {
                if let Some(rule) = self.checkpoint.get(key) {
                    checkpoint |= rule.covers(risk);
                }
            }
        }
        Raise {
            requires_checkpoint: checkpoint,
            requires_approval: approval,
            person: human,
        }
    }
}

/// The check of an output's `confidence` against an applied minimum
/// (§5.21.3): `None` when the output is not an object, has no `confidence`
/// member, or its confidence meets the minimum.
pub fn check_confidence(output: &Value, min: f64) -> Option<ConfidenceFault> {
    let c = output.as_object()?.get("confidence")?;
    match unit(c) {
        None => Some(ConfidenceFault::Invalid(
            c.to_string().chars().take(64).collect(),
        )),
        Some(x) if x < min => Some(ConfidenceFault::Below(x)),
        Some(_) => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ontology() -> Ontology {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
        let doc = crate::yaml::load_file(
            &root.join("schemas/capability_ontology.yaml"),
            crate::yaml::ONTOLOGY_MAX_BYTES,
        )
        .unwrap();
        Ontology::from_value(&doc).unwrap()
    }

    fn load(values: &[Value]) -> (Policy, Vec<(String, String, String)>) {
        let o = ontology();
        let mut report = Report::default();
        let p = Policy::load(values, &o, &mut report);
        let found = report
            .diagnostics
            .iter()
            .map(|d| {
                (
                    d.code.as_str().to_string(),
                    d.location["profile"].as_str().unwrap().to_string(),
                    d.location["field"].as_str().unwrap().to_string(),
                )
            })
            .collect();
        (p, found)
    }

    fn one(profile: Value) -> Policy {
        let (p, found) = load(&[profile]);
        assert!(found.is_empty(), "{found:?}");
        p
    }

    #[test]
    fn an_empty_policy_raises_nothing() {
        let p = Policy::default();
        assert!(p.is_empty());
        for risk in [Risk::Low, Risk::Medium, Risk::High] {
            assert_eq!(p.raise("mutate", risk), Raise::default());
        }
    }

    #[test]
    fn thresholds_cover_sets_of_levels() {
        let base = |t: Value| one(json!({"domain": "d", "version": "1.0.0", "risk_thresholds": t}));
        let r = |p: &Policy, risk| p.raise("retrieve", risk);
        let auto_low = base(json!({"auto_approve": "low"}));
        assert!(!r(&auto_low, Risk::Low).requires_approval);
        assert!(r(&auto_low, Risk::Medium).requires_approval);
        let auto_none = base(json!({"auto_approve": "none"}));
        assert!(r(&auto_none, Risk::Low).requires_approval);
        let auto_high = base(json!({"auto_approve": "high"}));
        assert!(!r(&auto_high, Risk::High).requires_approval);
        let review_medium = base(json!({"require_review": "medium"}));
        assert!(!r(&review_medium, Risk::Low).requires_approval);
        assert!(r(&review_medium, Risk::High).requires_approval);
        assert!(!r(&review_medium, Risk::High).person);
        let human_high = base(json!({"require_human": "high"}));
        assert_eq!(
            r(&human_high, Risk::High),
            Raise {
                requires_checkpoint: false,
                requires_approval: true,
                person: true
            }
        );
        assert_eq!(r(&human_high, Risk::Medium), Raise::default());
        let none = base(json!({"require_human": "none", "require_review": "none"}));
        assert_eq!(r(&none, Risk::High), Raise::default());
        let block = base(json!({"block_autonomous": ["delegate"]}));
        assert!(block.raise("delegate", Risk::Medium).person);
        assert!(!block.raise("retrieve", Risk::High).person);
    }

    #[test]
    fn critical_is_deprecated_and_reads_as_none() {
        let (p, found) = load(&[json!({"domain": "d", "version": "1.0.0",
            "risk_thresholds": {"require_human": "critical"}})]);
        assert_eq!(
            found,
            [(
                "W603".into(),
                "d".into(),
                "risk_thresholds.require_human".into()
            )]
        );
        assert_eq!(p.raise("mutate", Risk::High), Raise::default());
    }

    #[test]
    fn checkpoint_rules_never_cover_a_checkpoint_step() {
        let p = one(json!({"domain": "d", "version": "1.0.0",
            "checkpoint_policy": {"*": "always", "retrieve": "never"}}));
        assert!(p.raise("retrieve", Risk::Low).requires_checkpoint);
        for risk in [Risk::Low, Risk::Medium, Risk::High] {
            assert!(!p.raise("checkpoint", risk).requires_checkpoint);
        }
        let medium = one(json!({"domain": "d", "version": "1.0.0",
            "checkpoint_policy": {"*": "medium_risk"}}));
        assert!(!medium.raise("retrieve", Risk::Low).requires_checkpoint);
        assert!(medium.raise("invoke", Risk::Medium).requires_checkpoint);
        let high = one(json!({"domain": "d", "version": "1.0.0",
            "checkpoint_policy": {"*": "high_risk"}}));
        assert!(!high.raise("invoke", Risk::Medium).requires_checkpoint);
        assert!(high.raise("retrieve", Risk::High).requires_checkpoint);
        assert!(!high.raise("checkpoint", Risk::High).requires_checkpoint);
    }

    #[test]
    fn load_checks_every_rule() {
        let (_, found) = load(&[json!({
            "domain": "d", "version": "1.0.0",
            "trust_weights": {"trust_class:robot": 0.2, "plc": true, "Bad Key": 0.5},
            "risk_thresholds": {"require_humen": "low", "block_autonomous": ["mutate", "mutatee"]},
            "checkpoint_policy": {"checkpoint": "always", "mutat": "always", "mutate": "never"},
            "evidence_policy": {"required_anchor_types": ["file", "timestamp", "file"], "x-note": 1},
            "allowed_destinations": ["*"],
            "foo": 1,
            "x-owner": "a",
        })]);
        let codes: Vec<(&str, &str)> = found
            .iter()
            .map(|(c, _, f)| (c.as_str(), f.as_str()))
            .collect();
        assert_eq!(
            codes,
            [
                ("S303", "trust_weights.trust_class:robot"),
                ("S303", "trust_weights.plc"),
                ("S303", "trust_weights.Bad Key"),
                ("V101", "risk_thresholds.block_autonomous[1]"),
                ("S303", "risk_thresholds.require_humen"),
                ("S303", "checkpoint_policy.checkpoint"),
                ("V101", "checkpoint_policy.mutat"),
                ("W602", "checkpoint_policy.mutate"),
                ("S303", "evidence_policy.required_anchor_types[1]"),
                ("S303", "evidence_policy.required_anchor_types[2]"),
                ("S303", "evidence_policy.x-note"),
                ("S303", "allowed_destinations[0]"),
                ("W604", "foo"),
            ]
        );
    }

    #[test]
    fn labels_and_rules() {
        let (p, found) = load(&[
            json!({"domain": "a", "version": "1.0.0",
                "risk_thresholds": {"require_human": "low"},
                "evidence_policy": {"minimum_confidence": 0.8,
                    "require_grounding": ["predict"], "required_anchor_types": ["file"]},
                "trust_weights": {"plc": 0.9, "trust_class:peer_agent": 0.2},
                "allowed_destinations": ["*@acme.example"]}),
            json!({"domain": "b", "version": "1.0.0",
                "evidence_policy": {"minimum_confidence": 0.9},
                "trust_weights": {"plc": 0.7, "peer_agent": 0.6}}),
        ]);
        assert!(found.is_empty(), "{found:?}");
        assert_eq!(p.labels_raising("retrieve", Risk::Low), ["a"]);
        assert_eq!(p.minimum_confidence(), Some(0.9));
        assert_eq!(p.grounding().len(), 1);
        assert_eq!(p.destinations().len(), 1);
        let w = p.trust_weights();
        assert_eq!(w["plc"], 0.7);
        assert_eq!(w["trust_class:peer_agent"], 0.2);
        assert_eq!(w["peer_agent"], 0.6);
    }

    #[test]
    fn confidence_checks() {
        let fault = |v: Value| check_confidence(&json!({"confidence": v}), 0.9);
        assert_eq!(fault(json!(0.5)), Some(ConfidenceFault::Below(0.5)));
        for bad in [
            json!("0.95"),
            Value::Null,
            json!(true),
            json!([0.9]),
            json!(1.5),
            json!(-0.1),
        ] {
            assert!(
                matches!(fault(bad.clone()), Some(ConfidenceFault::Invalid(_))),
                "{bad}"
            );
        }
        assert_eq!(fault(json!(0.9)), None);
        assert_eq!(fault(json!(1)), None);
        assert_eq!(check_confidence(&json!({"x": 1}), 0.9), None);
        assert_eq!(check_confidence(&json!([1]), 0.9), None);
        let Some(ConfidenceFault::Invalid(t)) = fault(json!("x".repeat(100))) else {
            panic!("a long string is invalid")
        };
        assert_eq!(t.chars().count(), 64);
    }
}
