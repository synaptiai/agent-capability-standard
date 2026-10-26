//! Static workflow validation (STANDARD §5, §9, §10).
//!
//! [`Context`] holds what validation needs besides the catalog: the ontology
//! (with each capability's contracts resolved once), the schema store and the
//! coercion registry. [`validate_catalog`] returns a [`Report`] of diagnostics
//! and machine-usable fix suggestions.

mod bindings;

use std::collections::HashMap;
use std::path::Path;

use indexmap::IndexMap;
use serde::Serialize;
use serde_json::{Map, Value, json};

use crate::diag::{Code, Diagnostic};
use crate::ontology::{EdgeType, Ontology, Risk};
use crate::refs;
use crate::schema::SchemaStore;
use crate::types::{self, Type};
use crate::yaml;

pub use bindings::Mode;

/// Where the coercion registry lives under the schema root.
pub const COERCION_REGISTRY: &str = "schemas/transforms/transform_coercion_registry.yaml";

/// One registry entry: a transform from one type to another.
pub struct Coercion {
    pub from_text: String,
    pub to_text: String,
    pub from: Type,
    pub to: Type,
    pub mapping_ref: String,
}

/// A capability's contracts with every `$ref` resolved.
pub struct Contracts {
    pub input: Value,
    pub output: Value,
    /// Sources of incoming `requires` edges.
    pub requires: Vec<String>,
}

/// Everything validation needs besides the catalog itself.
pub struct Context {
    pub ontology: Ontology,
    pub schemas: SchemaStore,
    pub coercions: Vec<Coercion>,
    pub contracts: HashMap<String, Contracts>,
}

impl Context {
    /// Load the ontology and coercion registry; `schema_root` anchors every
    /// relative schema, mapping and input reference.
    pub fn load(ontology_path: &Path, schema_root: &Path) -> Result<Context, String> {
        let ontology = Ontology::load(ontology_path)?;
        let schemas = SchemaStore::new(schema_root);
        let mut coercions = Vec::new();
        if let Some(reg) = schemas.document(COERCION_REGISTRY) {
            for c in reg
                .get("coercions")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
            {
                let s = |k: &str| c.get(k).and_then(Value::as_str).map(str::to_string);
                let (Some(from_text), Some(to_text), Some(mapping_ref)) =
                    (s("from"), s("to"), s("mapping_ref"))
                else {
                    continue;
                };
                let (Ok(from), Ok(to)) = (
                    types::parse_annotation(&from_text),
                    types::parse_annotation(&to_text),
                ) else {
                    return Err(format!(
                        "coercion registry entry {from_text} -> {to_text} does not name valid types"
                    ));
                };
                coercions.push(Coercion {
                    from_text,
                    to_text,
                    from,
                    to,
                    mapping_ref,
                });
            }
        }
        let empty = || json!({"type": "object", "properties": {}});
        let contracts = ontology
            .capabilities
            .values()
            .map(|cap| {
                let resolve = |v: &Value| {
                    if v.is_object() {
                        schemas.resolve_node(v)
                    } else {
                        empty()
                    }
                };
                let requires = ontology
                    .incoming(&cap.id, EdgeType::Requires)
                    .into_iter()
                    .map(str::to_string)
                    .collect();
                let c = Contracts {
                    input: resolve(&cap.input_schema),
                    output: resolve(&cap.output_schema),
                    requires,
                };
                (cap.id.clone(), c)
            })
            .collect();
        Ok(Context {
            ontology,
            schemas,
            coercions,
            contracts,
        })
    }

    /// The registry transform turning `actual` into something `expected`
    /// accepts: an exact match on the printed types first, then the first
    /// entry whose types are compatible.
    pub fn coercion_for(&self, actual: &Type, expected: &Type) -> Option<&Coercion> {
        let (a, e) = (actual.to_string(), expected.to_string());
        self.coercions
            .iter()
            .find(|c| c.from_text == a && c.to_text == e)
            .or_else(|| {
                self.coercions.iter().find(|c| {
                    types::compatible(&c.from, actual) && types::compatible(expected, &c.to)
                })
            })
    }
}

/// The result of validating a catalog.
#[derive(Debug, Default, Serialize)]
pub struct Report {
    pub diagnostics: Vec<Diagnostic>,
    pub suggestions: Vec<Value>,
}

impl Report {
    pub fn push(&mut self, d: Diagnostic) {
        self.diagnostics.push(d);
    }

    pub fn errors(&self) -> impl Iterator<Item = &Diagnostic> {
        self.diagnostics.iter().filter(|d| d.is_error())
    }

    pub fn warnings(&self) -> impl Iterator<Item = &Diagnostic> {
        self.diagnostics.iter().filter(|d| !d.is_error())
    }

    /// Valid: no errors (or, when `strict`, no diagnostics at all).
    pub fn passed(&self, strict: bool) -> bool {
        if strict {
            self.diagnostics.is_empty()
        } else {
            self.errors().next().is_none()
        }
    }
}

/// Load and validate a catalog file. Load failures are returned as `Err`.
pub fn validate_catalog_file(ctx: &Context, path: &Path) -> Result<Report, String> {
    let catalog = yaml::load_file(path, yaml::ONTOLOGY_MAX_BYTES)
        .map_err(|e| format!("cannot load workflow catalog: {e}"))?;
    Ok(validate_catalog(ctx, &catalog))
}

/// Validate a parsed catalog: a mapping of workflow name to workflow.
pub fn validate_catalog(ctx: &Context, catalog: &Value) -> Report {
    let mut report = Report::default();
    let workflows = match catalog {
        Value::Object(m) => m,
        Value::Null => return report,
        other => {
            report.push(Diagnostic::new(
                Code::SchemaValidationFailed,
                format!(
                    "a workflow catalog must be a mapping of workflow names, found {}",
                    yaml::kind_of(other)
                ),
            ));
            return report;
        }
    };
    for (name, wf) in workflows {
        // `x-` keys are reserved for vendor data and never validated.
        if name.starts_with("x-") {
            continue;
        }
        match wf {
            Value::Object(wf) => WorkflowCheck {
                ctx,
                name,
                wf,
                report: &mut report,
            }
            .run(),
            other => report.push(
                Diagnostic::new(
                    Code::SchemaValidationFailed,
                    format!(
                        "workflow '{name}' must be a mapping, found {}",
                        yaml::kind_of(other)
                    ),
                )
                .at("workflow", name.as_str()),
            ),
        }
    }
    report
}

/// Names and schemas visible to a binding: earlier steps' outputs and the
/// workflow's declared inputs.
#[derive(Default)]
pub(crate) struct Scope {
    /// store_as → resolved producer output schema.
    pub stores: IndexMap<String, Value>,
    /// input name → resolved input schema.
    pub inputs: IndexMap<String, Value>,
}

/// Where a diagnostic about one step is located.
pub(crate) struct StepLoc<'a> {
    pub workflow: &'a str,
    pub step: usize,
    pub capability: &'a str,
}

impl StepLoc<'_> {
    pub fn diag(&self, code: Code, message: impl Into<String>) -> Diagnostic {
        Diagnostic::new(code, message)
            .at("workflow", self.workflow)
            .at("step", self.step)
            .at("capability", self.capability)
    }
}

/// The JSON type a §5.2 step field must have.
#[derive(Clone, Copy)]
enum Shape {
    Str,
    Bool,
    List,
    Mapping,
    /// A string or `null` (`timeout`).
    StrOrNull,
    /// A mapping or `null` (`retry`).
    MappingOrNull,
}

impl Shape {
    fn accepts(self, v: &Value) -> bool {
        match self {
            Shape::Str => v.is_string(),
            Shape::Bool => v.is_boolean(),
            Shape::List => v.is_array(),
            Shape::Mapping => v.is_object(),
            Shape::StrOrNull => v.is_string() || v.is_null(),
            Shape::MappingOrNull => v.is_object() || v.is_null(),
        }
    }

    fn name(self) -> &'static str {
        match self {
            Shape::Str => "a string",
            Shape::Bool => "a boolean",
            Shape::List => "a list",
            Shape::Mapping => "a mapping",
            Shape::StrOrNull => "a string or null",
            Shape::MappingOrNull => "a mapping or null",
        }
    }
}

const STEP_FIELD_SHAPES: &[(&str, Shape)] = &[
    ("purpose", Shape::Str),
    ("store_as", Shape::Str),
    ("input_bindings", Shape::Mapping),
    ("condition", Shape::Str),
    ("skip_if_false", Shape::Bool),
    ("gates", Shape::List),
    ("failure_modes", Shape::List),
    ("timeout", Shape::StrOrNull),
    ("retry", Shape::MappingOrNull),
    ("parallel_group", Shape::Str),
    ("join", Shape::Str),
    ("mapping_ref", Shape::Str),
    ("output_conforms_to", Shape::Str),
    ("mutation", Shape::Bool),
    ("requires_checkpoint", Shape::Bool),
    ("requires_approval", Shape::Bool),
    ("risk", Shape::Str),
    ("domain", Shape::Str),
    ("workflow_id", Shape::Str),
];

struct WorkflowCheck<'a> {
    ctx: &'a Context,
    name: &'a str,
    wf: &'a Map<String, Value>,
    report: &'a mut Report,
}

impl WorkflowCheck<'_> {
    fn wdiag(&self, code: Code, message: impl Into<String>) -> Diagnostic {
        Diagnostic::new(code, message).at("workflow", self.name)
    }

    fn run(mut self) {
        self.check_header();
        let mut scope = Scope {
            inputs: self.resolve_inputs(),
            ..Scope::default()
        };
        let steps: &[Value] = match self.wf.get("steps") {
            Some(Value::Array(a)) => a,
            Some(other) => {
                let d = self.wdiag(
                    Code::SchemaValidationFailed,
                    format!("'steps' must be a list, found {}", yaml::kind_of(other)),
                );
                self.report.push(d.at("field", "steps"));
                return;
            }
            None => return,
        };
        let mut seen: Vec<&str> = Vec::new();
        let mut first_use: HashMap<&str, usize> = HashMap::new();
        for (i, step) in steps.iter().enumerate() {
            let Some(step) = step.as_object() else {
                let d = self.wdiag(Code::InvalidStep, format!("step {i} is not a mapping"));
                self.report.push(d.at("step", i));
                continue;
            };
            let cap = match step.get("capability") {
                Some(Value::String(c)) => c.as_str(),
                Some(_) => {
                    let d = self.wdiag(
                        Code::InvalidStep,
                        format!("step {i}: 'capability' must be a string"),
                    );
                    self.report.push(d.at("step", i).at("field", "capability"));
                    continue;
                }
                None => {
                    let d = self.wdiag(
                        Code::InvalidStep,
                        format!("step {i} is invalid (missing 'capability' key)"),
                    );
                    self.report.push(d.at("step", i));
                    continue;
                }
            };
            let loc = StepLoc {
                workflow: self.name,
                step: i,
                capability: cap,
            };
            let Some(contracts) = self.ctx.contracts.get(cap) else {
                self.report.push(
                    loc.diag(
                        Code::UnknownCapability,
                        format!("capability '{cap}' not found in ontology"),
                    )
                    .at("field", "capability"),
                );
                continue;
            };
            self.check_step_fields(&loc, step);
            for req in &contracts.requires {
                if !seen.contains(&req.as_str()) {
                    self.report.push(
                        loc.diag(
                            Code::MissingPrerequisite,
                            format!(
                                "capability '{cap}' missing required prerequisite '{req}' before it"
                            ),
                        )
                        .at("prerequisite", req.as_str()),
                    );
                }
            }
            self.check_files(&loc, step);

            let store = step.get("store_as").and_then(Value::as_str);
            if let Some(store) = store {
                if let Some(first) = first_use.get(store) {
                    self.report.push(
                        loc.diag(
                            Code::DuplicateStoreAs,
                            format!("duplicate store_as '{store}' (first used at step {first})"),
                        )
                        .at("store_as", store)
                        .at("first_step", *first),
                    );
                } else {
                    first_use.insert(store, i);
                }
            }

            let checker = bindings::Checker {
                ctx: self.ctx,
                loc: &loc,
            };
            // A step's own output is not visible to its inputs or condition...
            if let Some(b) = step.get("input_bindings") {
                checker.scan(b, &scope, Mode::Full, "input_bindings", self.report);
            }
            if let Some(Value::String(c)) = step.get("condition") {
                checker.check_string(c, &scope, Mode::Full, "condition", self.report);
            }
            checker.consumer_check(step, &contracts.input, &scope, self.report);

            // ...but gates and recovery run once the step can have produced it.
            if let Some(store) = store {
                scope
                    .stores
                    .insert(store.to_string(), contracts.output.clone());
            }
            if let Some(Value::Array(gates)) = step.get("gates") {
                for (g, gate) in gates.iter().enumerate() {
                    if let Some(Value::String(w)) = gate.get("when") {
                        let field = format!("gates[{g}].when");
                        checker.check_string(w, &scope, Mode::Full, &field, self.report);
                    }
                }
            }
            if let Some(Value::Array(fms)) = step.get("failure_modes") {
                for (f, fm) in fms.iter().enumerate() {
                    if let Some(inject) = fm.get("recovery").and_then(|r| r.get("inject_context")) {
                        let field = format!("failure_modes[{f}].recovery.inject_context");
                        checker.scan(inject, &scope, Mode::Existence, &field, self.report);
                    }
                }
            }
            seen.push(cap);
        }
    }

    /// §5.1 required workflow fields and their types.
    fn check_header(&mut self) {
        for key in ["goal", "risk", "steps"] {
            if !self.wf.contains_key(key) {
                let d = self.wdiag(
                    Code::MissingRequiredField,
                    format!("workflow is missing required field '{key}'"),
                );
                self.report.push(d.at("field", key));
            }
        }
        if let Some(r) = self.wf.get("risk") {
            if !r.as_str().is_some_and(|r| Risk::parse(r).is_some()) {
                let d = self.wdiag(
                    Code::SchemaValidationFailed,
                    "'risk' must be one of low, medium, high",
                );
                self.report.push(d.at("field", "risk"));
            }
        }
        if let Some(g) = self.wf.get("goal") {
            if !g.is_string() {
                let d = self.wdiag(Code::SchemaValidationFailed, "'goal' must be a string");
                self.report.push(d.at("field", "goal"));
            }
        }
    }

    /// §5.2: required fields present, every known field of the right type,
    /// `store_as` usable as a reference root, gates and failure modes shaped.
    fn check_step_fields(&mut self, loc: &StepLoc<'_>, step: &Map<String, Value>) {
        for key in ["purpose", "store_as"] {
            match step.get(key) {
                None => self.report.push(
                    loc.diag(
                        Code::MissingRequiredField,
                        format!("step is missing required field '{key}'"),
                    )
                    .at("field", key),
                ),
                Some(Value::String(s)) if s.is_empty() => self.report.push(
                    loc.diag(
                        Code::SchemaValidationFailed,
                        format!("'{key}' must not be empty"),
                    )
                    .at("field", key),
                ),
                _ => {}
            }
        }
        for &(key, shape) in STEP_FIELD_SHAPES {
            if let Some(v) = step.get(key) {
                if !shape.accepts(v) {
                    self.report.push(
                        loc.diag(
                            Code::SchemaValidationFailed,
                            format!(
                                "'{key}' must be {}, found {}",
                                shape.name(),
                                yaml::kind_of(v)
                            ),
                        )
                        .at("field", key),
                    );
                }
            }
        }
        if let Some(Value::String(s)) = step.get("store_as") {
            if !s.is_empty() && !refs::is_identifier(s) {
                self.report.push(
                    loc.diag(
                        Code::SchemaValidationFailed,
                        format!(
                            "store_as '{s}' is not an identifier (letters, digits, '_' and '-', not starting with a digit or '-'), so no reference can name it"
                        ),
                    )
                    .at("field", "store_as"),
                );
            }
        }
        if let Some(Value::String(r)) = step.get("risk") {
            if Risk::parse(r).is_none() {
                self.report.push(
                    loc.diag(
                        Code::SchemaValidationFailed,
                        "'risk' must be one of low, medium, high",
                    )
                    .at("field", "risk"),
                );
            }
        }
        for (list, required) in [
            ("gates", ["when", "action"]),
            ("failure_modes", ["condition", "action"]),
        ] {
            let Some(Value::Array(items)) = step.get(list) else {
                continue;
            };
            for (n, item) in items.iter().enumerate() {
                let field = format!("{list}[{n}]");
                let Some(item) = item.as_object() else {
                    self.report.push(
                        loc.diag(
                            Code::SchemaValidationFailed,
                            format!("{field} must be a mapping"),
                        )
                        .at("field", field),
                    );
                    continue;
                };
                for key in required {
                    match item.get(key) {
                        Some(Value::String(_)) => {}
                        Some(other) => self.report.push(
                            loc.diag(
                                Code::SchemaValidationFailed,
                                format!(
                                    "{field}.{key} must be a string, found {}",
                                    yaml::kind_of(other)
                                ),
                            )
                            .at("field", format!("{field}.{key}")),
                        ),
                        None => self.report.push(
                            loc.diag(
                                Code::MissingRequiredField,
                                format!("{field} is missing required field '{key}'"),
                            )
                            .at("field", format!("{field}.{key}")),
                        ),
                    }
                }
            }
        }
    }

    fn check_files(&mut self, loc: &StepLoc<'_>, step: &Map<String, Value>) {
        if let Some(Value::String(m)) = step.get("mapping_ref") {
            if !self.ctx.schemas.file_exists(m) {
                self.report.push(
                    loc.diag(
                        Code::SchemaNotFound,
                        format!("mapping_ref missing file: {m}"),
                    )
                    .at("field", "mapping_ref"),
                );
            }
        }
        if let Some(Value::String(c)) = step.get("output_conforms_to") {
            let file = c.split('#').next().unwrap_or_default();
            if !self.ctx.schemas.file_exists(file) {
                self.report.push(
                    loc.diag(
                        Code::SchemaNotFound,
                        format!("output_conforms_to missing file: {file}"),
                    )
                    .at("field", "output_conforms_to"),
                );
            } else if c.contains('#') && self.ctx.schemas.resolve_ref(c).is_none() {
                self.report.push(
                    loc.diag(
                        Code::InvalidRef,
                        format!("output_conforms_to does not resolve: {c}"),
                    )
                    .at("field", "output_conforms_to"),
                );
            }
        }
    }

    /// Resolve the declared inputs to schemas (S302 on a broken `ref`, S303 on
    /// a malformed declaration).
    fn resolve_inputs(&mut self) -> IndexMap<String, Value> {
        let mut out = IndexMap::new();
        let empty_object = || json!({"type": "object", "properties": {}});
        let inputs = match self.wf.get("inputs") {
            None => return out,
            Some(Value::Object(m)) => m,
            Some(other) => {
                let d = self.wdiag(
                    Code::SchemaValidationFailed,
                    format!(
                        "'inputs' must be a mapping of input names, found {}",
                        yaml::kind_of(other)
                    ),
                );
                self.report.push(d.at("field", "inputs"));
                return out;
            }
        };
        for (key, spec) in inputs {
            let field = format!("inputs.{key}");
            let schema = match spec {
                Value::Object(m) => match m.get("ref") {
                    None => self.ctx.schemas.resolve_node(spec),
                    Some(Value::String(r)) => match self.ctx.schemas.resolve_ref(r) {
                        Some(resolved @ Value::Object(_)) => {
                            self.ctx.schemas.resolve_node(&resolved)
                        }
                        _ => {
                            let d = self.wdiag(
                                Code::InvalidRef,
                                format!("{field} ref could not be resolved: {r}"),
                            );
                            self.report.push(d.at("field", format!("{field}.ref")));
                            empty_object()
                        }
                    },
                    Some(other) => {
                        let d = self.wdiag(
                            Code::SchemaValidationFailed,
                            format!(
                                "{field}.ref must be a string, found {}",
                                yaml::kind_of(other)
                            ),
                        );
                        self.report.push(d.at("field", format!("{field}.ref")));
                        empty_object()
                    }
                },
                other => {
                    let d = self.wdiag(
                        Code::SchemaValidationFailed,
                        format!(
                            "{field} must be a schema mapping, found {}",
                            yaml::kind_of(other)
                        ),
                    );
                    self.report.push(d.at("field", field));
                    empty_object()
                }
            };
            out.insert(key.clone(), schema);
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::diag::Code;
    use serde_json::json;

    fn ctx() -> Context {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
        Context::load(&root.join("schemas/capability_ontology.yaml"), &root).unwrap()
    }

    fn codes(catalog: Value) -> Vec<&'static str> {
        validate_catalog(&ctx(), &catalog)
            .diagnostics
            .iter()
            .map(|d| d.code.as_str())
            .collect()
    }

    fn wf(steps: Value) -> Value {
        json!({"w": {"goal": "g", "risk": "low", "steps": steps}})
    }

    #[test]
    fn minimal_workflow_is_clean() {
        assert!(
            codes(wf(
                json!([{"capability": "observe", "purpose": "p", "store_as": "o"}])
            ))
            .is_empty()
        );
    }

    #[test]
    fn structural_errors() {
        assert_eq!(codes(json!({"w": [1]})), ["S303"]);
        assert_eq!(codes(json!({"x-notes": [1]})), Vec::<&str>::new());
        assert_eq!(codes(json!({"w": {"risk": "low", "steps": []}})), ["S304"]);
        assert_eq!(
            codes(json!({"w": {"goal": "g", "risk": "extreme", "steps": []}})),
            ["S303"]
        );
        assert_eq!(
            codes(wf(json!([{"purpose": "p", "store_as": "o"}]))),
            ["V103"]
        );
        assert_eq!(
            codes(wf(
                json!([{"capability": "nope", "purpose": "p", "store_as": "o"}])
            )),
            ["V101"]
        );
        assert_eq!(
            codes(wf(json!([{"capability": "observe", "store_as": "o"}]))),
            ["S304"]
        );
    }

    #[test]
    fn prerequisites_and_duplicates() {
        let steps = json!([
            {"capability": "mutate", "purpose": "p", "store_as": "m"},
            {"capability": "observe", "purpose": "p", "store_as": "o"},
            {"capability": "observe", "purpose": "p", "store_as": "o"},
        ]);
        let c = codes(wf(steps));
        assert!(c.contains(&"V102"), "{c:?}");
        assert!(c.contains(&"V104"), "{c:?}");
    }

    #[test]
    fn binding_errors() {
        let base = |binding: &str| {
            wf(json!([
                {"capability": "search", "purpose": "p", "store_as": "s", "input_bindings": {"query": "q"}},
                {"capability": "compare", "purpose": "p", "store_as": "c", "input_bindings": {"options": binding}},
            ]))
        };
        assert_eq!(
            codes(base("${s.results: array<object>}")),
            Vec::<&str>::new()
        );
        assert_eq!(codes(base("${nobody.x}")), ["B202"]);
        assert_eq!(codes(base("${s.nope}")), ["B201"]);
        assert_eq!(codes(base("${s.results}")), ["B204"]);
        assert_eq!(codes(base("${s.results: banana}")), ["B205"]);
        assert!(codes(base("${s.confidence: string}")).contains(&"B203"));
    }

    #[test]
    fn consumer_mismatch_suggests_a_transform() {
        let catalog = wf(json!([
            {"capability": "search", "purpose": "p", "store_as": "s", "input_bindings": {"query": "q"}},
            {"capability": "search", "purpose": "p", "store_as": "t", "input_bindings": {"query": "q", "scope": "${s.total_count}"}},
        ]));
        let report = validate_catalog(&ctx(), &catalog);
        assert!(
            report
                .diagnostics
                .iter()
                .any(|d| d.code == Code::TypeMismatch)
        );
        assert_eq!(
            report.suggestions[0]["kind"],
            "consumer_input_type_mismatch"
        );
        assert_eq!(report.suggestions[0]["from_type"], "integer");
    }

    #[test]
    fn mangled_list_reference_is_flagged_and_still_checked() {
        let catalog = wf(json!([
            {"capability": "search", "purpose": "p", "store_as": "s", "input_bindings": {"query": "q"}},
            {"capability": "integrate", "purpose": "p", "store_as": "i",
             "input_bindings": {"sources": [{"${s.nope": "array<object>}"}]}},
        ]));
        let c = codes(catalog);
        assert!(c.contains(&"W612") && c.contains(&"B201"), "{c:?}");
    }

    #[test]
    fn coercion_lookup_uses_type_compatibility() {
        let catalog = wf(json!([
            {"capability": "search", "purpose": "p", "store_as": "s", "input_bindings": {"query": "q"}},
            {"capability": "search", "purpose": "p", "store_as": "t", "input_bindings": {"query": "q", "scope": "${s.total_count}"}},
        ]));
        let report = validate_catalog(&ctx(), &catalog);
        // integer → string uses the registry's number → string transform.
        assert_eq!(
            report.suggestions[0]["suggested_mapping_ref"],
            "schemas/transforms/transform_mapping_coerce_number_to_string.yaml"
        );
    }

    #[test]
    fn field_shapes_and_inputs_are_checked() {
        let step = |extra: Value| {
            let mut s = json!({"capability": "observe", "purpose": "p", "store_as": "o"});
            s.as_object_mut()
                .unwrap()
                .extend(extra.as_object().unwrap().clone());
            wf(json!([s]))
        };
        assert_eq!(codes(step(json!({"mapping_ref": ["a.yaml"]}))), ["S303"]);
        assert_eq!(codes(step(json!({"condition": 5}))), ["S303"]);
        assert_eq!(
            codes(step(json!({"gates": [{"action": "stop"}]}))),
            ["S304"]
        );
        assert_eq!(
            codes(step(json!({"gates": [{"when": 1, "action": "stop"}]}))),
            ["S303"]
        );
        assert_eq!(codes(step(json!({"failure_modes": ["x"]}))), ["S303"]);
        assert_eq!(codes(step(json!({"store_as": "o.p"}))), ["S303"]);
        assert_eq!(codes(step(json!({"risk": "extreme"}))), ["S303"]);
        let with_inputs = |inputs: Value| {
            json!({"w": {"goal": "g", "risk": "low", "inputs": inputs,
                "steps": [{"capability": "observe", "purpose": "p", "store_as": "o"}]}})
        };
        assert_eq!(codes(with_inputs(json!(["a"]))), ["S303"]);
        assert_eq!(codes(with_inputs(json!({"a": "string"}))), ["S303"]);
        assert_eq!(codes(with_inputs(json!({"a": {"ref": 5}}))), ["S303"]);
        assert_eq!(
            codes(with_inputs(json!({"a": {"ref": "schemas/nope.yaml#/x"}}))),
            ["S302"]
        );
    }

    #[test]
    fn hyphenated_store_names_are_referencable() {
        let catalog = wf(json!([
            {"capability": "search", "purpose": "p", "store_as": "s-1", "input_bindings": {"query": "q"}},
            {"capability": "compare", "purpose": "p", "store_as": "c", "input_bindings": {"options": "${s-1.results: array<object>}"}},
        ]));
        assert!(codes(catalog).is_empty());
    }

    #[test]
    fn report_passes_unless_errors_or_strict_warnings() {
        let mut r = Report::default();
        assert!(r.passed(true));
        r.push(Diagnostic::new(Code::MangledReference, "w"));
        assert!(r.passed(false) && !r.passed(true));
        r.push(Diagnostic::new(Code::UnknownCapability, "e"));
        assert!(!r.passed(false));
    }
}
