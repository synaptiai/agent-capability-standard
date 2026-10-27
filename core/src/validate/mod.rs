//! Static workflow validation (STANDARD §5, §9, §10).
//!
//! [`Context`] holds what validation needs besides the catalog: the ontology
//! (with each capability's contracts resolved once), the schema store and the
//! coercion registry. [`validate_catalog`] returns a [`Report`] of diagnostics
//! and machine-usable fix suggestions.

mod bindings;
mod exprs;
mod semantics;

pub use semantics::header_version;

use std::collections::{HashMap, HashSet};
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
    let load = |e: yaml::YamlError| format!("cannot load workflow catalog: {e}");
    let text = yaml::read_guarded(path, yaml::ONTOLOGY_MAX_BYTES).map_err(load)?;
    let catalog = yaml::load_str(&text).map_err(load)?;
    Ok(validate_catalog(
        ctx,
        &catalog,
        header_version(&text).as_deref(),
    ))
}

/// Validate a parsed catalog: a mapping of workflow name to workflow.
/// `header` is the version from the file's `# Standard version:` comment.
pub fn validate_catalog(ctx: &Context, catalog: &Value, header: Option<&str>) -> Report {
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
                header,
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
    /// Roots that may be absent at runtime: optional inputs and the outputs
    /// of steps that a condition or skip gate can skip.
    pub maybe_absent: HashSet<String>,
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
    header: Option<&'a str>,
    report: &'a mut Report,
}

impl WorkflowCheck<'_> {
    fn wdiag(&self, code: Code, message: impl Into<String>) -> Diagnostic {
        Diagnostic::new(code, message).at("workflow", self.name)
    }

    fn run(mut self) {
        self.check_header();
        let name = self.name;
        let at_wf = |d: Diagnostic| d.at("workflow", name);
        semantics::unknown_fields(self.wf, semantics::WORKFLOW_KEYS, "", &at_wf, self.report);
        semantics::spec_version(self.wf, self.header, &at_wf, self.report);
        if let Some(Value::Object(ext)) = self.wf.get("workflow_extensions") {
            semantics::unknown_fields(
                ext,
                semantics::WORKFLOW_EXTENSIONS_KEYS,
                "workflow_extensions",
                &at_wf,
                self.report,
            );
        }
        let (inputs, maybe_absent) = self.resolve_inputs();
        let mut scope = Scope {
            inputs,
            maybe_absent,
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
        let mut placed: Vec<semantics::Placed<'_>> = Vec::new();
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
            let (Some(node), Some(contracts)) =
                (self.ctx.ontology.get(cap), self.ctx.contracts.get(cap))
            else {
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
            self.check_step_keys(&loc, step);
            semantics::flag_downgrades(&loc, step, node, self.report);
            placed.push(semantics::Placed {
                index: i,
                capability: cap,
                parallel_group: step.get("parallel_group").and_then(Value::as_str),
            });
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
            let gates = exprs::gates(step, store, &loc, self.report);
            // A step's own output is not visible to its inputs, condition or
            // before-gates...
            if let Some(b) = step.get("input_bindings") {
                checker.scan(b, &scope, Mode::Full, "input_bindings", self.report);
            }
            if let Some(Value::String(c)) = step.get("condition") {
                exprs::check_expression(c, &scope, &loc, "condition", self.report);
            }
            for g in gates.iter().filter(|g| g.phase == exprs::Phase::Before) {
                if let Some(when) = &g.when {
                    exprs::check_parsed(when, &scope, &loc, &g.field, self.report);
                }
            }
            checker.consumer_check(step, &contracts.input, &scope, self.report);

            // ...but after-gates and failure modes run once the step has run,
            // so there its output is present; later steps see it as absent
            // if the step can be skipped.
            if let Some(store) = store {
                scope
                    .stores
                    .insert(store.to_string(), contracts.output.clone());
                scope.maybe_absent.remove(store);
            }
            for g in gates.iter().filter(|g| g.phase == exprs::Phase::After) {
                if let Some(when) = &g.when {
                    exprs::check_parsed(when, &scope, &loc, &g.field, self.report);
                }
            }
            if let Some(Value::Array(fms)) = step.get("failure_modes") {
                for (f, fm) in fms.iter().enumerate() {
                    match fm.get("when") {
                        Some(Value::String(w)) => {
                            let field = format!("failure_modes[{f}].when");
                            exprs::check_expression(w, &scope, &loc, &field, self.report);
                        }
                        Some(other) => self.report.push(
                            loc.diag(
                                Code::SchemaValidationFailed,
                                format!(
                                    "failure_modes[{f}].when must be a string, found {}",
                                    yaml::kind_of(other)
                                ),
                            )
                            .at("field", format!("failure_modes[{f}].when")),
                        ),
                        None => {}
                    }
                    if let Some(inject) = fm.get("recovery").and_then(|r| r.get("inject_context")) {
                        let field = format!("failure_modes[{f}].recovery.inject_context");
                        checker.scan(inject, &scope, Mode::Existence, &field, self.report);
                    }
                }
            }
            if let Some(store) = store {
                if exprs::skippable(step, &gates) {
                    scope.maybe_absent.insert(store.to_string());
                }
            }
            seen.push(cap);
        }
        semantics::check_edges(self.ctx, self.name, &placed, self.report);
    }

    /// W604 for unknown keys in a step and its gates, failure modes,
    /// recovery and retry blocks.
    fn check_step_keys(&mut self, loc: &StepLoc<'_>, step: &Map<String, Value>) {
        let at = |d: Diagnostic| {
            d.at("workflow", loc.workflow)
                .at("step", loc.step)
                .at("capability", loc.capability)
        };
        semantics::unknown_fields(step, semantics::STEP_KEYS, "", &at, self.report);
        if let Some(Value::Object(retry)) = step.get("retry") {
            semantics::unknown_fields(retry, semantics::RETRY_KEYS, "retry", &at, self.report);
        }
        for (list, keys) in [
            ("gates", semantics::GATE_KEYS),
            ("failure_modes", semantics::FAILURE_MODE_KEYS),
        ] {
            let Some(Value::Array(items)) = step.get(list) else {
                continue;
            };
            for (n, item) in items.iter().enumerate() {
                let Some(item) = item.as_object() else {
                    continue;
                };
                let field = format!("{list}[{n}]");
                semantics::unknown_fields(item, keys, &field, &at, self.report);
                if let Some(Value::Object(rec)) = item.get("recovery") {
                    semantics::unknown_fields(
                        rec,
                        semantics::RECOVERY_KEYS,
                        &format!("{field}.recovery"),
                        &at,
                        self.report,
                    );
                }
            }
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
    fn resolve_inputs(&mut self) -> (IndexMap<String, Value>, HashSet<String>) {
        let mut out = IndexMap::new();
        let mut optional = HashSet::new();
        let empty_object = || json!({"type": "object", "properties": {}});
        let inputs = match self.wf.get("inputs") {
            None => return (out, optional),
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
                return (out, optional);
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
            // An input is always supplied only if it is declared required.
            if spec.get("required") != Some(&Value::Bool(true)) {
                optional.insert(key.clone());
            }
            out.insert(key.clone(), schema);
        }
        (out, optional)
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
        validate_catalog(&ctx(), &catalog, None)
            .diagnostics
            .iter()
            .map(|d| d.code.as_str())
            .collect()
    }

    fn wf(steps: Value) -> Value {
        json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1", "steps": steps}})
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
        assert_eq!(
            codes(json!({"w": {"risk": "low", "spec_version": "1.1", "steps": []}})),
            ["S304"]
        );
        assert_eq!(
            codes(
                json!({"w": {"goal": "g", "risk": "extreme", "spec_version": "1.1", "steps": []}})
            ),
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
        let report = validate_catalog(&ctx(), &catalog, None);
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
        let report = validate_catalog(&ctx(), &catalog, None);
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
            json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1", "inputs": inputs,
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
    fn own_output_is_present_for_after_gates_even_if_skippable() {
        let catalog = wf(json!([{
            "capability": "verify", "purpose": "p", "store_as": "v",
            "condition": "true", "input_bindings": {"conditions": []},
            "gates": [{"when": "${v.confidence} < 0.5", "phase": "after", "action": "warn", "message": "m"}],
        }]));
        assert!(codes(catalog).is_empty());
    }

    #[test]
    fn skippable_producers_make_later_operands_nullable() {
        let steps = |skip_if_false: Value| {
            let mut v = json!({"capability": "verify", "purpose": "p", "store_as": "v",
                "condition": "true", "input_bindings": {"conditions": []}});
            if !skip_if_false.is_null() {
                v["skip_if_false"] = skip_if_false;
            }
            wf(
                json!([v, {"capability": "explain", "purpose": "p", "store_as": "e",
                "condition": "${v.confidence} > 0.5", "input_bindings": {"conclusion": "c"}}]),
            )
        };
        assert_eq!(codes(steps(Value::Null)), ["W610"]);
        assert_eq!(codes(steps(json!(true))), ["W610"]);
        // skip_if_false: false fails the run instead of skipping (§5.6).
        assert!(codes(steps(json!(false))).is_empty());
    }

    #[test]
    fn self_reference_inside_a_string_literal_is_not_a_read() {
        let catalog = wf(json!([
            {"capability": "verify", "purpose": "p", "store_as": "o", "input_bindings": {"conditions": []}},
            {"capability": "verify", "purpose": "p", "store_as": "me", "input_bindings": {"conditions": []},
             "gates": [{"when": "${o.passed} == \"${me}\"", "action": "skip", "message": "m"}]},
        ]));
        // W611 (boolean vs string), but neither W603 nor S303.
        assert_eq!(codes(catalog), ["W611"]);
    }

    #[test]
    fn binding_and_expression_paths_agree() {
        let gen_step = json!({"capability": "generate", "purpose": "p", "store_as": "g",
            "input_bindings": {"specification": "s"}});
        let binding = wf(
            json!([gen_step, {"capability": "explain", "purpose": "p", "store_as": "e",
            "input_bindings": {"conclusion": "${g.content.title: string}"}}]),
        );
        let condition = wf(
            json!([gen_step, {"capability": "explain", "purpose": "p", "store_as": "e",
            "condition": "${g.content.title: string} == \"x\"", "input_bindings": {"conclusion": "c"}}]),
        );
        // A field below `type: any` is allowed and untyped in both places.
        assert!(codes(binding).is_empty());
        assert!(codes(condition).is_empty());
    }

    fn st(cap: &str, store: &str) -> Value {
        json!({"capability": cap, "purpose": "p", "store_as": store})
    }

    #[test]
    fn precedes_is_order_only() {
        // observe precedes detect: absent observe is fine...
        assert!(!codes(wf(json!([st("detect", "d")]))).contains(&"V102"));
        // ...but observe after detect is not.
        assert!(codes(wf(json!([st("detect", "d"), st("observe", "o")]))).contains(&"V102"));
        assert!(!codes(wf(json!([st("observe", "o"), st("detect", "d")]))).contains(&"V102"));
    }

    #[test]
    fn soft_requires_is_any_of_presence() {
        let ground = |prior: Value| {
            let mut steps = prior.as_array().cloned().unwrap_or_default();
            steps.push(st("ground", "g"));
            codes(wf(Value::Array(steps)))
        };
        assert!(ground(json!([])).contains(&"W601"));
        assert!(!ground(json!([st("predict", "p")])).contains(&"W601"));
        assert!(!ground(json!([st("observe", "o")])).contains(&"W601"));
    }

    #[test]
    fn conflicts_only_within_a_parallel_group() {
        let step = |cap: &str, store: &str, group: Option<&str>| {
            let mut s = st(cap, store);
            if let Some(g) = group {
                s["parallel_group"] = json!(g);
            }
            s
        };
        let sequential = wf(json!([
            st("checkpoint", "c"),
            step("persist", "p", None),
            step("rollback", "r", None)
        ]));
        assert!(!codes(sequential).contains(&"F504"));
        let together = wf(json!([
            st("checkpoint", "c"),
            step("persist", "p", Some("g")),
            step("rollback", "r", Some("g"))
        ]));
        let c = codes(together);
        assert_eq!(c.iter().filter(|x| **x == "F504").count(), 1, "{c:?}");
    }

    #[test]
    fn safety_flag_downgrades_warn() {
        let send = |extra: Value| {
            let mut s = st("send", "s");
            s.as_object_mut()
                .unwrap()
                .extend(extra.as_object().unwrap().clone());
            codes(wf(json!([st("checkpoint", "c"), st("constrain", "k"), s])))
        };
        assert_eq!(send(json!({})), Vec::<&str>::new());
        assert_eq!(send(json!({"requires_approval": false})), ["W602"]);
        assert_eq!(
            send(json!({"mutation": false, "risk": "low"})),
            ["W602", "W602"]
        );
        // audit's mutation flag may be overridden.
        let audit = wf(
            json!([{"capability": "audit", "purpose": "p", "store_as": "a", "mutation": false}]),
        );
        assert!(codes(audit).is_empty());
    }

    #[test]
    fn unknown_fields_warn_with_a_hint() {
        let catalog = json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1", "stpes": [],
            "x-vendor": 1, "steps": [{"capability": "observe", "purpose": "p", "store_as": "o",
            "requires_aproval": true, "gates": [{"when": "true", "action": "warn", "mesage": "m"}]}]}});
        let report = validate_catalog(&ctx(), &catalog, None);
        let w: Vec<_> = report
            .diagnostics
            .iter()
            .filter(|d| d.code == Code::UnknownField)
            .collect();
        assert_eq!(w.len(), 3, "{w:?}");
        assert_eq!(w[0].suggestion.as_deref(), Some("did you mean 'steps'?"));
        assert_eq!(
            w[1].suggestion.as_deref(),
            Some("did you mean 'requires_approval'?")
        );
        assert_eq!(w[2].location["field"], "gates[0].mesage");
    }

    #[test]
    fn spec_versions() {
        let v = |version: Value, header: Option<&str>| {
            let mut w = json!({"goal": "g", "risk": "low", "steps": []});
            if !version.is_null() {
                w["spec_version"] = version;
            }
            validate_catalog(&ctx(), &json!({"w": w}), header)
                .diagnostics
                .iter()
                .map(|d| d.code.as_str())
                .collect::<Vec<_>>()
        };
        assert_eq!(v(Value::Null, None), ["W605"]);
        assert!(v(Value::Null, Some("1.0.0")).is_empty());
        assert!(v(json!("1.1"), None).is_empty());
        assert_eq!(v(json!("2.0"), None), ["V109"]);
        assert_eq!(v(Value::Null, Some("0.9")), ["V109"]);
        assert_eq!(v(json!(1.1), None), ["S303"]);
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
