//! Orchestration extensions (STANDARD v1.1 §5.9–§5.16, design-114 §4,
//! §10–§15): declarations, triggers and durations.

use std::collections::HashSet;

use serde_json::{Map, Value};

use super::{Context, Report, semantics};
use crate::cron::Cron;
use crate::diag::{Code, Diagnostic};
use crate::{duration, yaml};

/// Extensions Standard v1.1 defines, as `name@major` (§5.9).
pub(crate) const SPECIFIED: &[&str] = &[
    "triggers@1",
    "recovery@1",
    "wait@1",
    "approval@1",
    "delegation@1",
    "quorum@1",
];

/// The extensions this validator implements. A workflow that requires any
/// other is refused (V106): must-understand only works if a consumer never
/// claims an extension it does not check.
pub(crate) const IMPLEMENTED: &[&str] = &["triggers@1", "recovery@1"];

const TRIGGER_KEYS: &[&str] = &["kind", "schedule", "event", "attendance"];
const SCHEDULE_KEYS: &[&str] = &["cron", "every", "timezone", "overlap"];
const EVENT_KEYS: &[&str] = &["event_type", "source_kind", "delivers_to"];

/// Where the event schema keeps the source kinds a trigger may name.
/// The event schema file and the pointer to its event object, which an event
/// trigger's `delivers_to` input must reference.
const EVENT_SCHEMA_FILE: &str = "event_schema.yaml";
const EVENT_POINTER: &str = "/event";
/// Below the event object: where it keeps its source kinds.
const SOURCE_KINDS_POINTER: &str = "/properties/source/properties/kind/enum";

/// The extensions a workflow declares in `workflow_extensions.requires`.
#[derive(Default)]
pub(crate) struct Declared {
    names: HashSet<String>,
    /// The declaration itself is malformed (already reported). Extension
    /// fields are then not reported again as undeclared.
    malformed: bool,
}

impl Declared {
    /// Read `workflow_extensions.requires`: S303 for a wrong shape or a
    /// repeated entry, V106 for an extension this validator does not know.
    pub(crate) fn read(
        wf: &Map<String, Value>,
        at: &dyn Fn(Diagnostic) -> Diagnostic,
        report: &mut Report,
    ) -> Declared {
        let mut declared = Declared::default();
        let ext = match wf.get("workflow_extensions") {
            None => return declared,
            Some(Value::Object(ext)) => ext,
            Some(other) => {
                declared.malformed = true;
                report.push(
                    at(Diagnostic::new(
                        Code::SchemaValidationFailed,
                        format!(
                            "'workflow_extensions' must be a mapping (e.g. {{requires: [triggers@1]}}), found {}",
                            yaml::kind_of(other)
                        ),
                    ))
                    .at("field", "workflow_extensions"),
                );
                return declared;
            }
        };
        let Some(requires) = ext.get("requires") else {
            return declared;
        };
        let field = "workflow_extensions.requires";
        let Value::Array(items) = requires else {
            declared.malformed = true;
            report.push(
                at(Diagnostic::new(
                    Code::SchemaValidationFailed,
                    format!(
                        "'{field}' must be a list of 'name@major' strings, found {}",
                        yaml::kind_of(requires)
                    ),
                ))
                .at("field", field),
            );
            return declared;
        };
        let mut seen = HashSet::new();
        for (i, item) in items.iter().enumerate() {
            let at_item = |d: Diagnostic| at(d).at("field", format!("{field}[{i}]"));
            let Value::String(name) = item else {
                declared.malformed = true;
                report.push(at_item(Diagnostic::new(
                    Code::SchemaValidationFailed,
                    format!(
                        "{field}[{i}] must be a 'name@major' string, found {}",
                        yaml::kind_of(item)
                    ),
                )));
                continue;
            };
            if !seen.insert(name.as_str()) {
                report.push(at_item(Diagnostic::new(
                    Code::SchemaValidationFailed,
                    format!("extension '{name}' is listed twice"),
                )));
            } else if !SPECIFIED.contains(&name.as_str()) {
                report.push(at_item(Diagnostic::new(
                    Code::UnsupportedExtension,
                    format!(
                        "extension '{name}' is not defined by the standard ({}); a consumer must not run a workflow that requires an extension it does not implement",
                        SPECIFIED.join(", ")
                    ),
                )));
            } else if !IMPLEMENTED.contains(&name.as_str()) {
                report.push(at_item(Diagnostic::new(
                    Code::UnsupportedExtension,
                    format!(
                        "extension '{name}' is not implemented by this validator (implemented: {}), so it cannot check the workflow's use of it",
                        IMPLEMENTED.join(", ")
                    ),
                )));
            } else {
                declared.names.insert(name.clone());
            }
        }
        declared
    }

    /// Whether `extension` is declared.
    pub(crate) fn has(&self, extension: &str) -> bool {
        self.names.contains(extension)
    }

    /// V106 unless `extension` is declared: its fields must not be used by a
    /// workflow that does not say it depends on them.
    pub(crate) fn require(
        &self,
        extension: &str,
        what: &str,
        diag: impl FnOnce(Diagnostic) -> Diagnostic,
        report: &mut Report,
    ) -> bool {
        if self.has(extension) {
            return true;
        }
        if self.malformed {
            return false; // the declaration's own error says enough
        }
        report.push(diag(Diagnostic::new(
            Code::UnsupportedExtension,
            format!(
                "{what} belongs to extension '{extension}'; list it in workflow_extensions.requires"
            ),
        )));
        false
    }
}

pub(crate) fn s303(
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    field: &str,
    message: String,
) -> Diagnostic {
    at(Diagnostic::new(Code::SchemaValidationFailed, message)).at("field", field)
}

pub(crate) fn s304(
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    field: &str,
    message: String,
) -> Diagnostic {
    at(Diagnostic::new(Code::MissingRequiredField, message)).at("field", field)
}

/// A string field of `map`: S303 when present but not a string.
pub(crate) fn string_field<'a>(
    map: &'a Map<String, Value>,
    key: &str,
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> Option<&'a str> {
    match map.get(key)? {
        Value::String(s) => Some(s),
        other => {
            report.push(s303(
                at,
                &format!("{field}.{key}"),
                format!(
                    "{field}.{key} must be a string, found {}",
                    yaml::kind_of(other)
                ),
            ));
            None
        }
    }
}

/// A string field that must be one of `allowed`.
pub(crate) fn enum_field<'a>(
    map: &'a Map<String, Value>,
    key: &str,
    allowed: &[&str],
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> Option<&'a str> {
    let v = string_field(map, key, field, at, report)?;
    if allowed.contains(&v) {
        Some(v)
    } else {
        report.push(s303(
            at,
            &format!("{field}.{key}"),
            format!("{field}.{key} '{v}' is not one of {}", allowed.join(", ")),
        ));
        None
    }
}

/// A non-negative integer: an integer, or a number with no fraction (JSON
/// Schema's `integer` accepts `2.0`).
pub(crate) fn count(value: &Value) -> Option<u64> {
    value.as_u64().or_else(|| {
        value
            .as_f64()
            .filter(|f| f.fract() == 0.0 && *f >= 0.0 && *f <= 9_007_199_254_740_992.0)
            .map(|f| f as u64)
    })
}

/// Validate a duration-valued extension field (S303 when invalid).
pub(crate) fn duration_field(
    value: &Value,
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> Option<std::time::Duration> {
    let Value::String(text) = value else {
        report.push(s303(
            at,
            field,
            format!(
                "{field} must be a duration string, found {}",
                yaml::kind_of(value)
            ),
        ));
        return None;
    };
    match duration::parse(text) {
        Ok(d) => Some(d),
        Err(e) => {
            report.push(s303(at, field, format!("{field}: {e}")));
            None
        }
    }
}

/// W614: a legacy step `timeout` outside the duration grammar. It stays
/// accepted (1.0 allowed any string), but cannot be enforced.
pub(crate) fn legacy_timeout(
    step: &Map<String, Value>,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    if let Some(Value::String(t)) = step.get("timeout") {
        if let Err(e) = duration::parse(t) {
            report.push(
                at(Diagnostic::new(
                    Code::InvalidDuration,
                    format!("timeout: {e}; it cannot be enforced"),
                ))
                .at("field", "timeout"),
            );
        }
    }
}

/// `triggers` (§5.10): S303/S304 for shape, V106 without `triggers@1`, V107
/// for a `delivers_to` that is not an event input.
pub(crate) fn triggers(
    ctx: &Context,
    wf: &Map<String, Value>,
    declared: &Declared,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let Some(value) = wf.get("triggers") else {
        return;
    };
    if !declared.require(
        "triggers@1",
        "'triggers'",
        |d| at(d).at("field", "triggers"),
        report,
    ) {
        return;
    }
    let Value::Array(list) = value else {
        report.push(s303(
            at,
            "triggers",
            format!("'triggers' must be a list, found {}", yaml::kind_of(value)),
        ));
        return;
    };
    let inputs = wf.get("inputs").and_then(Value::as_object);
    for (i, t) in list.iter().enumerate() {
        let field = format!("triggers[{i}]");
        let Value::Object(t) = t else {
            report.push(s303(
                at,
                &field,
                format!("{field} must be a mapping, found {}", yaml::kind_of(t)),
            ));
            continue;
        };
        semantics::unknown_fields(t, TRIGGER_KEYS, &field, at, report);
        let kind = match t.get("kind") {
            None => {
                report.push(s304(
                    at,
                    &format!("{field}.kind"),
                    format!("{field} has no 'kind'"),
                ));
                None
            }
            Some(_) => enum_field(
                t,
                "kind",
                &["schedule", "event", "manual", "invoke"],
                &field,
                at,
                report,
            ),
        };
        enum_field(
            t,
            "attendance",
            &["attended", "unattended"],
            &field,
            at,
            report,
        );
        for block in ["schedule", "event"] {
            let bfield = format!("{field}.{block}");
            match (t.get(block), kind) {
                (None, Some(k)) if k == block => report.push(s304(
                    at,
                    &bfield,
                    format!("{field} has kind '{k}' but no '{block}'"),
                )),
                // A block for another kind is reported, not checked.
                (Some(_), Some(k)) if k != block => report.push(s303(
                    at,
                    &bfield,
                    format!("{field} has kind '{k}', so '{block}' does not apply"),
                )),
                (Some(b), _) if block == "schedule" => schedule(b, &bfield, at, report),
                (Some(b), _) => event(ctx, b, &bfield, inputs, at, report),
                (None, _) => {}
            }
        }
    }
}

fn schedule(
    value: &Value,
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let Value::Object(s) = value else {
        report.push(s303(
            at,
            field,
            format!("{field} must be a mapping, found {}", yaml::kind_of(value)),
        ));
        return;
    };
    semantics::unknown_fields(s, SCHEDULE_KEYS, field, at, report);
    match (s.get("cron"), s.get("every")) {
        (Some(_), Some(_)) => report.push(s303(
            at,
            field,
            format!("{field} has both 'cron' and 'every'; give one"),
        )),
        (None, None) => report.push(s304(at, field, format!("{field} needs 'cron' or 'every'"))),
        (Some(_), None) => {
            if let Some(c) = string_field(s, "cron", field, at, report) {
                if let Err(e) = Cron::parse(c) {
                    report.push(s303(
                        at,
                        &format!("{field}.cron"),
                        format!("{field}.cron: {e}"),
                    ));
                }
            }
        }
        (None, Some(every)) => {
            let f = format!("{field}.every");
            if duration_field(every, &f, at, report).is_some_and(|d| d.is_zero()) {
                report.push(s303(at, &f, format!("{f} must be longer than zero")));
            }
        }
    }
    if let Some(tz) = string_field(s, "timezone", field, at, report) {
        if tz.parse::<chrono_tz::Tz>().is_err() {
            report.push(s303(
                at,
                &format!("{field}.timezone"),
                format!("{field}.timezone '{tz}' is not an IANA time zone name (e.g. 'Europe/Lisbon', 'UTC')"),
            ));
        }
    }
    enum_field(
        s,
        "overlap",
        &["skip", "buffer_one", "allow_all"],
        field,
        at,
        report,
    );
}

fn event(
    ctx: &Context,
    value: &Value,
    field: &str,
    inputs: Option<&Map<String, Value>>,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let Value::Object(e) = value else {
        report.push(s303(
            at,
            field,
            format!("{field} must be a mapping, found {}", yaml::kind_of(value)),
        ));
        return;
    };
    semantics::unknown_fields(e, EVENT_KEYS, field, at, report);
    for key in ["event_type", "delivers_to"] {
        if !e.contains_key(key) {
            report.push(s304(
                at,
                &format!("{field}.{key}"),
                format!("{field} has no '{key}'"),
            ));
        }
    }
    string_field(e, "event_type", field, at, report);
    // The event schema `delivers_to` names (resolved under the schema root)
    // also lists the source kinds a trigger may name.
    let event_ref = string_field(e, "delivers_to", field, at, report)
        .and_then(|target| delivers_to(target, inputs, field, at, report));
    if let Some(kind) = string_field(e, "source_kind", field, at, report) {
        let Some(event_ref) = event_ref else {
            return; // delivers_to is already reported
        };
        let kinds_ref = format!("{event_ref}{SOURCE_KINDS_POINTER}");
        let Some(Value::Array(kinds)) = ctx.schemas.resolve_ref(&kinds_ref) else {
            report.push(
                at(Diagnostic::new(
                    Code::SchemaNotFound,
                    format!(
                        "{field}.source_kind: cannot load the event source kinds from '{kinds_ref}'"
                    ),
                ))
                .at("field", format!("{field}.source_kind")),
            );
            return;
        };
        if !kinds.iter().any(|k| k.as_str() == Some(kind)) {
            let names: Vec<&str> = kinds.iter().filter_map(Value::as_str).collect();
            report.push(s303(
                at,
                &format!("{field}.source_kind"),
                format!(
                    "{field}.source_kind '{kind}' is not an event source kind ({})",
                    names.join(", ")
                ),
            ));
        }
    }
}

/// The `ref` of the input an event trigger delivers to, if it is the
/// canonical event (`…event_schema.yaml#/event`); else V107.
fn delivers_to<'a>(
    target: &str,
    inputs: Option<&'a Map<String, Value>>,
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> Option<&'a str> {
    let input = inputs.and_then(|i| i.get(target));
    let event_ref = input
        .and_then(|i| i.get("ref").or_else(|| i.get("$ref")))
        .and_then(Value::as_str)
        .filter(|r| is_event_ref(r));
    let wrong_type = input
        .and_then(|i| i.get("type"))
        .is_some_and(|t| t.as_str() != Some("object"));
    let why = match (input, event_ref) {
        (None, _) => "no such workflow input",
        (Some(_), None) => {
            "that input's 'ref' is not the canonical event (…event_schema.yaml#/event)"
        }
        (Some(_), Some(_)) if wrong_type => "that input's type is not 'object'",
        (Some(_), Some(r)) => return Some(r),
    };
    report.push(
        at(Diagnostic::new(
            Code::UnresolvedTarget,
            format!("{field}.delivers_to '{target}': {why}"),
        ))
        .at("field", format!("{field}.delivers_to")),
    );
    None
}

/// `event_schema.yaml#/event`, possibly under a directory.
fn is_event_ref(r: &str) -> bool {
    let Some((file, pointer)) = r.split_once('#') else {
        return false;
    };
    pointer == EVENT_POINTER
        && (file == EVENT_SCHEMA_FILE || file.ends_with(&format!("/{EVENT_SCHEMA_FILE}")))
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::super::tests::{codes, ctx};
    use super::super::validate_catalog;

    fn wf(extra: serde_json::Value) -> serde_json::Value {
        let mut w = json!({"goal": "g", "risk": "low", "spec_version": "1.1",
            "steps": [{"capability": "observe", "purpose": "p", "store_as": "o"}]});
        for (k, v) in extra.as_object().unwrap() {
            w[k] = v.clone();
        }
        json!({ "w": w })
    }

    fn declared(extra: serde_json::Value) -> serde_json::Value {
        let mut e = extra;
        e["workflow_extensions"] = json!({"requires": ["triggers@1"]});
        wf(e)
    }

    #[test]
    fn declarations() {
        assert!(
            codes(wf(
                json!({"workflow_extensions": {"requires": ["triggers@1", "recovery@1"]}})
            ))
            .is_empty()
        );
        // Specified, but this validator cannot check it yet: refused.
        assert_eq!(
            codes(wf(
                json!({"workflow_extensions": {"requires": ["quorum@1"]}})
            )),
            ["V106"]
        );
        assert_eq!(
            codes(wf(json!({"workflow_extensions": ["triggers@1"]}))),
            ["S303"]
        );
        assert!(codes(wf(json!({"workflow_extensions": {"requires": null}}))).len() == 1);
        assert_eq!(
            codes(wf(
                json!({"workflow_extensions": {"requires": ["teleport@1"]}})
            )),
            ["V106"]
        );
        assert_eq!(
            codes(wf(json!({"workflow_extensions": {"requires": ["wait@2"]}}))),
            ["V106"]
        );
        assert_eq!(
            codes(wf(json!({"workflow_extensions": {"requires": "wait@1"}}))),
            ["S303"]
        );
        assert_eq!(
            codes(wf(json!({"workflow_extensions": {"requires": [1]}}))),
            ["S303"]
        );
        assert_eq!(
            codes(wf(
                json!({"workflow_extensions": {"requires": ["triggers@1", "triggers@1"]}})
            )),
            ["S303"]
        );
    }

    #[test]
    fn malformed_declarations_do_not_cascade() {
        let t = json!([{"kind": "manual"}]);
        assert_eq!(
            codes(wf(
                json!({"workflow_extensions": {"requires": "triggers@1"}, "triggers": t})
            )),
            ["S303"]
        );
        assert_eq!(
            codes(wf(
                json!({"workflow_extensions": ["triggers@1"], "triggers": t})
            )),
            ["S303"]
        );
        // A duplicate of an unknown extension is S303, reported once.
        assert_eq!(
            codes(wf(
                json!({"workflow_extensions": {"requires": ["x@1", "x@1"]}})
            )),
            ["V106", "S303"]
        );
    }

    #[test]
    fn triggers_need_their_extension() {
        let t = json!({"triggers": [{"kind": "manual"}]});
        assert_eq!(codes(wf(t.clone())), ["V106"]);
        assert!(codes(declared(t)).is_empty());
    }

    #[test]
    fn schedules() {
        let ok = |s: serde_json::Value| {
            codes(declared(
                json!({"triggers": [{"kind": "schedule", "schedule": s}]}),
            ))
        };
        assert!(ok(json!({"cron": "0 6 * * MON-FRI", "timezone": "Europe/Lisbon"})).is_empty());
        assert!(ok(json!({"every": "PT15M", "overlap": "buffer_one"})).is_empty());
        assert_eq!(ok(json!({"cron": "0 6 * *"})), ["S303"]);
        assert_eq!(ok(json!({"cron": "0 0 * * *", "every": "1h"})), ["S303"]);
        assert_eq!(ok(json!({})), ["S304"]);
        assert!(ok(json!({"cron": "0 0 * * *", "timezone": "UTC"})).is_empty());
        // IANA names are case-sensitive.
        assert_eq!(
            ok(json!({"cron": "0 0 * * *", "timezone": "utc"})),
            ["S303"]
        );
        assert_eq!(ok(json!({"every": "0s"})), ["S303"]);
        assert_eq!(ok(json!({"every": "15 minutes"})), ["S303"]);
        assert_eq!(
            ok(json!({"cron": "0 0 * * *", "timezone": "Mars/Olympus"})),
            ["S303"]
        );
        assert_eq!(
            ok(json!({"cron": "0 0 * * *", "overlap": "queue"})),
            ["S303"]
        );
        assert_eq!(ok(json!({"cron": "0 0 * * *", "jitter": "5m"})), ["W604"]);
    }

    #[test]
    fn trigger_shapes() {
        let t = |v: serde_json::Value| codes(declared(json!({"triggers": v})));
        assert_eq!(t(json!({"kind": "manual"})), ["S303"]);
        assert_eq!(t(json!(["manual"])), ["S303"]);
        assert_eq!(t(json!([{}])), ["S304"]);
        assert_eq!(t(json!([{"kind": "cron"}])), ["S303"]);
        assert_eq!(t(json!([{"kind": "schedule"}])), ["S304"]);
        assert_eq!(
            t(json!([{"kind": "manual", "schedule": {"every": "1h"}}])),
            ["S303"]
        );
        assert_eq!(
            t(json!([{"kind": "manual", "attendance": "sometimes"}])),
            ["S303"]
        );
        assert!(t(json!([{"kind": "invoke", "attendance": "attended"}])).is_empty());
    }

    #[test]
    fn event_triggers() {
        let inputs = json!({
            "deploy_event": {"type": "object", "ref": "schemas/event_schema.yaml#/event"},
            "plain": {"type": "string"}
        });
        let t = |e: serde_json::Value| {
            codes(declared(
                json!({"inputs": inputs, "triggers": [{"kind": "event", "event": e}]}),
            ))
        };
        assert!(
            t(
                json!({"event_type": "deploy.finished", "source_kind": "agent",
            "delivers_to": "deploy_event"})
            )
            .is_empty()
        );
        assert_eq!(
            t(json!({"event_type": "x", "delivers_to": "plain"})),
            ["V107"]
        );
        assert_eq!(
            t(json!({"event_type": "x", "delivers_to": "missing"})),
            ["V107"]
        );
        assert_eq!(t(json!({"delivers_to": "deploy_event"})), ["S304"]);
        assert_eq!(
            t(
                json!({"event_type": "x", "source_kind": "carrier_pigeon", "delivers_to": "deploy_event"})
            ),
            ["S303"]
        );
    }

    #[test]
    fn event_trigger_targets() {
        let run = |input: serde_json::Value, kind: &str| {
            codes(declared(json!({
                "inputs": {"ev": input},
                "triggers": [{"kind": "event", "event": {"event_type": "x",
                    "source_kind": kind, "delivers_to": "ev"}}]
            })))
        };
        // A co-located copy of the event schema (as skills vendor it).
        let vendored = json!({"type": "object",
            "ref": "skills/receive/reference/event_schema.yaml#/event"});
        assert!(run(vendored.clone(), "agent").is_empty());
        assert_eq!(run(vendored, "pigeon"), ["S303"]);
        // Look-alike file names and wrong types are not the canonical event.
        let lookalike = json!({"type": "object", "ref": "schemas/my_event_schema.yaml#/event"});
        // (S302: the input's own ref does not resolve either.)
        assert_eq!(run(lookalike, "agent"), ["V107", "S302"]);
        let array = json!({"type": "array", "ref": "schemas/event_schema.yaml#/event"});
        assert_eq!(run(array, "agent"), ["V107"]);
        let dollar = json!({"type": "object", "$ref": "schemas/event_schema.yaml#/event"});
        assert!(run(dollar, "agent").is_empty());
        // The schema cannot be loaded: say so rather than skip the check.
        let missing = json!({"type": "object", "ref": "nowhere/event_schema.yaml#/event"});
        assert_eq!(run(missing, "agent"), ["S301", "S302"]);
    }

    #[test]
    fn a_block_for_another_kind_is_not_checked() {
        let t = |v: serde_json::Value| codes(declared(json!({"triggers": [v]})));
        assert_eq!(t(json!({"kind": "manual", "schedule": {}})), ["S303"]);
        assert_eq!(
            t(json!({"kind": "schedule", "schedule": {"every": "1h"}, "event": {}})),
            ["S303"]
        );
    }

    #[test]
    fn unknown_fields_in_triggers_and_events() {
        let t = |v: serde_json::Value| codes(declared(json!({"triggers": [v]})));
        assert_eq!(t(json!({"kind": "manual", "priority": 1})), ["W604"]);
        let mut d = declared(
            json!({"triggers": [{"kind": "event", "event": {"event_type": "x",
            "delivers_to": "ev", "filter": "y"}}]}),
        );
        d["w"]["inputs"] =
            json!({"ev": {"type": "object", "ref": "schemas/event_schema.yaml#/event"}});
        assert_eq!(codes(d), ["W604"]);
    }

    #[test]
    fn legacy_timeouts() {
        let step = |timeout: serde_json::Value| {
            let catalog = json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
                "steps": [{"capability": "observe", "purpose": "p", "store_as": "o",
                    "timeout": timeout}]}});
            validate_catalog(&ctx(), &catalog, None)
                .diagnostics
                .iter()
                .map(|d| d.code.as_str())
                .collect::<Vec<_>>()
        };
        assert!(step(json!("5m")).is_empty());
        assert!(step(json!("PT90S")).is_empty());
        assert!(step(json!(null)).is_empty());
        assert_eq!(step(json!("five minutes")), ["W614"]);
    }
}
