//! Reference and binding checks (STANDARD §5.3–§5.5).

use serde_json::{Map, Value, json};

use super::{Context, Report, Scope, StepLoc};
use crate::diag::Code;
use crate::refs::{self, Ref};
use crate::schema;
use crate::types::{self, Type};

/// How thoroughly a reference is checked.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    /// Existence, path, annotation, and ambiguity (§5.4 rule 3).
    Full,
    /// Existence, path and annotation only: for references whose consumer
    /// has no typed contract (recovery context, extension blocks).
    Existence,
}

/// Maximum depth walked inside binding values.
const MAX_SCAN_DEPTH: usize = 64;

pub(crate) struct Checker<'a> {
    pub ctx: &'a Context,
    pub loc: &'a StepLoc<'a>,
}

/// What a reference's root names.
enum Producer<'s> {
    Store(&'s Value),
    Input(&'s Value),
}

fn resolve_root<'s>(scope: &'s Scope, root: &str) -> Option<Producer<'s>> {
    if let Some(s) = scope.stores.get(root) {
        return Some(Producer::Store(s));
    }
    scope.inputs.get(root).map(Producer::Input)
}

fn infer(schema: &Value, r: &Ref) -> (Type, bool) {
    match schema::node_at(schema, &r.path) {
        Some(node) => types::schema_type(node),
        None => (Type::Unknown, true),
    }
}

impl Checker<'_> {
    /// Check every reference in a binding value (strings, lists, mappings).
    pub fn scan(&self, value: &Value, scope: &Scope, mode: Mode, field: &str, report: &mut Report) {
        self.scan_inner(value, scope, mode, field, report, 0);
    }

    fn scan_inner(
        &self,
        value: &Value,
        scope: &Scope,
        mode: Mode,
        field: &str,
        report: &mut Report,
        depth: usize,
    ) {
        if depth > MAX_SCAN_DEPTH {
            report.push(
                self.loc
                    .diag(
                        Code::SchemaValidationFailed,
                        format!("{field} is nested deeper than {MAX_SCAN_DEPTH} levels"),
                    )
                    .at("field", field),
            );
            return;
        }
        match value {
            Value::String(s) => self.check_string(s, scope, mode, field, report),
            Value::Array(items) => {
                for (i, v) in items.iter().enumerate() {
                    self.scan_inner(v, scope, mode, &format!("{field}[{i}]"), report, depth + 1);
                }
            }
            Value::Object(m) => {
                if let Some(rebuilt) = mangled_reference(m) {
                    report.push(
                        self.loc
                            .diag(
                                Code::MangledReference,
                                format!(
                                    "YAML read '{rebuilt}' as a mapping because of ': ' inside the reference; quote the value"
                                ),
                            )
                            .at("field", field),
                    );
                    self.check_string(&rebuilt, scope, mode, field, report);
                    return;
                }
                for (k, v) in m {
                    self.scan_inner(v, scope, mode, &format!("{field}.{k}"), report, depth + 1);
                }
            }
            _ => {}
        }
    }

    /// Check each `${...}` in a string.
    pub fn check_string(
        &self,
        s: &str,
        scope: &Scope,
        mode: Mode,
        field: &str,
        report: &mut Report,
    ) {
        for m in refs::find_refs(s) {
            match m.parsed {
                Ok(r) => self.check_ref(&r, scope, mode, field, report),
                Err(e) => report.push(
                    self.loc
                        .diag(Code::InvalidBindingPath, e)
                        .at("field", field),
                ),
            }
        }
    }

    fn check_ref(&self, r: &Ref, scope: &Scope, mode: Mode, field: &str, report: &mut Report) {
        let at = |d: crate::diag::Diagnostic| d.at("field", field).at("ref", r.raw.as_str());
        let Some(producer) = resolve_root(scope, &r.root) else {
            report.push(at(self.loc.diag(
                Code::MissingProducer,
                format!("unknown reference store '{}' in ${{{}}}", r.root, r.raw),
            )));
            return;
        };
        let (schema, external) = match producer {
            Producer::Store(s) => (s, false),
            Producer::Input(s) => (s, true),
        };
        // An input declared without properties cannot be path-checked.
        let checkable = !external || schema.get("properties").is_some();
        if !r.path.is_empty() && checkable && schema::node_at(schema, &r.path).is_none() {
            let whose = if external {
                "inputs schema for"
            } else {
                "schema for"
            };
            report.push(at(self.loc.diag(
                Code::InvalidBindingPath,
                format!(
                    "bad reference ${{{}}}: path {} not in {whose} {}",
                    r.raw,
                    r.path_text(),
                    r.root
                ),
            )));
            return;
        }
        let (actual, ambiguous) = infer(schema, r);
        match &r.annotation {
            Some(text) => match types::parse_annotation(text) {
                Err(e) => report.push(at(self
                    .loc
                    .diag(Code::InvalidAnnotation, format!("{e} in ${{{}}}", r.raw)))),
                Ok(expected) => {
                    if !types::compatible(&expected, &actual) {
                        report.push(
                            at(self.loc.diag(
                                Code::TypeMismatch,
                                format!("type mismatch ${{{}}}: annotated {expected} but schema has {actual}", r.raw),
                            ))
                            .at("expected_type", expected.to_string())
                            .at("actual_type", actual.to_string()),
                        );
                        let (kind, hint) = if external {
                            (
                                "external_binding_type_mismatch",
                                "update_inputs_schema_or_transform",
                            )
                        } else {
                            ("binding_type_mismatch", "insert_transform")
                        };
                        report.suggestions.push(json!({
                            "kind": kind,
                            "workflow": self.loc.workflow,
                            "step_index": self.loc.step,
                            "ref": r.raw,
                            "expected": expected.to_string(),
                            "actual": actual.to_string(),
                            "hint": hint,
                        }));
                    }
                }
            },
            None => {
                if mode == Mode::Full && ambiguous {
                    // Injected recovery context has no schema to refine.
                    let extra = if external && r.root != super::recovery::RECOVERY_ROOT {
                        " or refine the inputs schema"
                    } else {
                        ""
                    };
                    report.push(at(self.loc.diag(
                        Code::AmbiguousType,
                        format!(
                            "ambiguous type for ${{{}}}: inferred {actual} is ambiguous or unknown; add a typed annotation{extra}",
                            r.raw
                        ),
                    )));
                }
            }
        }
    }

    /// §5.5(3): each top-level string binding against the consumer's input schema.
    pub fn consumer_check(
        &self,
        step: &Map<String, Value>,
        input_schema: &Value,
        scope: &Scope,
        report: &mut Report,
    ) {
        let Some(Value::Object(bindings)) = step.get("input_bindings") else {
            return;
        };
        for (key, val) in bindings {
            let Value::String(s) = val else { continue };
            for m in refs::find_refs(s) {
                let Ok(r) = m.parsed else { continue };
                let schema = match resolve_root(scope, &r.root) {
                    Some(Producer::Store(s)) => s,
                    Some(Producer::Input(s)) if s.is_object() => s,
                    _ => continue,
                };
                let (actual, _) = infer(schema, &r);
                let expected_node = input_schema
                    .get("properties")
                    .and_then(|p| p.get(key))
                    .unwrap_or(&Value::Null);
                let (expected, expected_ambiguous) = types::schema_type(expected_node);
                if expected_ambiguous || types::compatible(&expected, &actual) {
                    continue;
                }
                report.push(
                    self.loc
                        .diag(
                            Code::TypeMismatch,
                            format!(
                                "consumer input type mismatch: input '{key}' expects {expected} but got {actual} from ${{{}}}",
                                r.raw
                            ),
                        )
                        .at("field", format!("input_bindings.{key}"))
                        .at("input_key", key.as_str())
                        .at("ref", r.raw.as_str())
                        .at("expected_type", expected.to_string())
                        .at("actual_type", actual.to_string()),
                );
                let from_t = actual.to_string();
                let to_t = expected.to_string();
                let mapping = self
                    .ctx
                    .coercion_for(&actual, &expected)
                    .map(|c| c.mapping_ref.clone());
                let store = identifier(&format!(
                    "coerce_{}_{}_{}",
                    self.loc.workflow, self.loc.step, key
                ));
                report.suggestions.push(json!({
                    "kind": "consumer_input_type_mismatch",
                    "workflow": self.loc.workflow,
                    "step_index": self.loc.step,
                    "capability": self.loc.capability,
                    "input_key": key,
                    "binding_ref": r.raw,
                    "from_type": from_t,
                    "to_type": to_t,
                    "suggested_mapping_ref": mapping,
                    "patch": {
                        "action": "insert_transform_before_step",
                        "insert_at_step_index": self.loc.step,
                        "new_step": {
                            "capability": "transform",
                            "purpose": format!("Coerce {key} to {to_t} for consumer input contract"),
                            "mapping_ref": mapping.clone().unwrap_or_else(|| "docs/schemas/transform_mapping_<custom>.yaml".into()),
                            "input_bindings": {"source": format!("${{{}}}", r.raw)},
                            "store_as": store,
                        },
                        "update_step": {
                            "step_index": self.loc.step,
                            "input_bindings_update": {key: format!("${{{store}.transformed: {to_t}}}")},
                        },
                    },
                }));
            }
        }
    }
}

/// `- ${a.b: t}` in a YAML list is read as the mapping `{"${a.b": "t}"}`:
/// the `: ` inside the reference ends a plain-scalar key. Any key holding a
/// `${` that is not closed before the end of the key is that accident.
/// Rebuild the text the author wrote, so its references are still checked.
fn mangled_reference(m: &Map<String, Value>) -> Option<String> {
    if m.len() != 1 {
        return None;
    }
    let (k, v) = m.iter().next()?;
    let open = k.rfind("${")?;
    if k[open..].contains('}') {
        return None;
    }
    let rest = match v {
        Value::String(s) => s.clone(),
        Value::Null => String::new(),
        other => other.to_string(),
    };
    Some(format!("{k}: {rest}"))
}

/// `s` with every character a reference identifier cannot hold replaced by `_`.
fn identifier(s: &str) -> String {
    let mut out: String = s
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect();
    if !out.starts_with(|c: char| c.is_ascii_alphabetic() || c == '_') {
        out.insert(0, '_');
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_mangled_references() {
        let m = |k: &str, v: Value| {
            let mut map = Map::new();
            map.insert(k.into(), v);
            mangled_reference(&map)
        };
        assert_eq!(
            m("${a.b", json!("array<object>}")).as_deref(),
            Some("${a.b: array<object>}")
        );
        assert_eq!(m("x ${a.b", json!("t}")).as_deref(), Some("x ${a.b: t}"));
        assert_eq!(m("${a.b", Value::Null).as_deref(), Some("${a.b: "));
        assert_eq!(m("${a.b} done", json!("v")), None);
        assert_eq!(m("plain", json!("v")), None);
    }

    #[test]
    fn sanitises_identifiers() {
        assert_eq!(
            identifier("coerce_debug-code_3_scope"),
            "coerce_debug-code_3_scope"
        );
        assert_eq!(identifier("coerce_my wf_1_x.y"), "coerce_my_wf_1_x_y");
        assert_eq!(identifier("9lives"), "_9lives");
        assert!(crate::refs::is_identifier(&identifier("a b.c")));
    }
}
