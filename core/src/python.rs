//! The `grounded_agency._core` extension module.

use std::path::PathBuf;

use pyo3::exceptions::{
    PyFileNotFoundError, PyIsADirectoryError, PyOSError, PyPermissionError, PyTypeError,
    PyValueError,
};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};
use serde_json::{Map, Value, json};

use crate::diag::{Code, Diagnostic, Severity};
use crate::exec::{self, Attendance, RecordMode, Response, RestoreError, StartError, StartOptions};
use crate::validate::{self, Context, LoadError, Report};
use crate::yaml::{self, YamlError};
use crate::{destination, duration, grounding};

pub(crate) fn to_py(py: Python<'_>, v: &Value) -> PyResult<Py<PyAny>> {
    Ok(match v {
        Value::Null => py.None(),
        Value::Bool(b) => PyBool::new(py, *b).to_owned().into_any().unbind(),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.into_pyobject(py)?.into_any().unbind()
            } else if let Some(u) = n.as_u64() {
                u.into_pyobject(py)?.into_any().unbind()
            } else {
                PyFloat::new(py, n.as_f64().unwrap_or(f64::NAN))
                    .into_any()
                    .unbind()
            }
        }
        Value::String(s) => PyString::new(py, s).into_any().unbind(),
        Value::Array(a) => {
            let items = a
                .iter()
                .map(|x| to_py(py, x))
                .collect::<PyResult<Vec<_>>>()?;
            PyList::new(py, items)?.into_any().unbind()
        }
        Value::Object(m) => {
            let d = PyDict::new(py);
            for (k, x) in m {
                d.set_item(k, to_py(py, x)?)?;
            }
            d.into_any().unbind()
        }
    })
}

/// Convert plain Python data (what a YAML or JSON loader produces) to a
/// value: `None`, `bool`, `int` within 64 bits, finite `float`, `str`, `list`
/// or `tuple`, and `dict` with `str` keys. Anything else is a `TypeError`.
///
/// Containers nest at most [`yaml::MAX_DEPTH`] levels, as in YAML, and a
/// value holds at most [`yaml::MAX_ALIAS_WEIGHT`] nodes, so a structure that
/// shares or cycles through its own containers cannot expand without bound.
/// (YAML budgets only alias expansion; Python data has no aliases to tell
/// apart from plain nodes, so every node counts.)
pub(crate) fn from_py(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    from_py_inner(obj, 0, &mut 0)
}

/// [`from_py`] for a catalog: each workflow under its own node budget, so
/// several large workflows validated together are not refused.
fn catalog_from_py(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    let Ok(d) = obj.cast::<PyDict>() else {
        return from_py(obj);
    };
    let mut m = Map::new();
    for (k, v) in d.iter() {
        let Ok(key) = k.cast::<PyString>() else {
            return Err(PyTypeError::new_err(format!(
                "mapping keys must be strings, found {}",
                k.get_type().name()?
            )));
        };
        m.insert(key.to_str()?.to_owned(), from_py_inner(&v, 1, &mut 0)?);
    }
    Ok(Value::Object(m))
}

fn from_py_inner(obj: &Bound<'_, PyAny>, depth: usize, nodes: &mut usize) -> PyResult<Value> {
    // A container at `depth` opens nesting level depth + 1.
    let container = obj.is_instance_of::<PyDict>()
        || obj.is_instance_of::<PyList>()
        || obj.is_instance_of::<PyTuple>();
    if container && depth >= yaml::MAX_DEPTH {
        return Err(PyValueError::new_err(format!(
            "nesting deeper than {} levels",
            yaml::MAX_DEPTH
        )));
    }
    *nodes += 1;
    if *nodes > yaml::MAX_ALIAS_WEIGHT {
        return Err(PyValueError::new_err(format!(
            "more than {} values in all",
            yaml::MAX_ALIAS_WEIGHT
        )));
    }
    if obj.is_none() {
        return Ok(Value::Null);
    }
    // bool before int: in Python, bool is a subclass of int.
    if let Ok(b) = obj.cast::<PyBool>() {
        return Ok(Value::Bool(b.is_true()));
    }
    if let Ok(i) = obj.cast::<PyInt>() {
        if let Ok(v) = i.extract::<i64>() {
            return Ok(Value::from(v));
        }
        if let Ok(v) = i.extract::<u64>() {
            return Ok(Value::from(v));
        }
        return Err(PyValueError::new_err(format!(
            "integer {i} does not fit in 64 bits"
        )));
    }
    if let Ok(f) = obj.cast::<PyFloat>() {
        let v = f.value();
        return serde_json::Number::from_f64(v)
            .map(Value::Number)
            .ok_or_else(|| PyValueError::new_err(format!("non-finite number {v}")));
    }
    if let Ok(s) = obj.cast::<PyString>() {
        return Ok(Value::String(s.to_str()?.to_owned()));
    }
    if let Ok(d) = obj.cast::<PyDict>() {
        let mut m = Map::new();
        for (k, v) in d.iter() {
            let Ok(key) = k.cast::<PyString>() else {
                return Err(PyTypeError::new_err(format!(
                    "mapping keys must be strings, found {}",
                    k.get_type().name()?
                )));
            };
            m.insert(
                key.to_str()?.to_owned(),
                from_py_inner(&v, depth + 1, nodes)?,
            );
        }
        return Ok(Value::Object(m));
    }
    if let Ok(l) = obj.cast::<PyList>() {
        return l
            .iter()
            .map(|x| from_py_inner(&x, depth + 1, nodes))
            .collect();
    }
    if let Ok(t) = obj.cast::<PyTuple>() {
        return t
            .iter()
            .map(|x| from_py_inner(&x, depth + 1, nodes))
            .collect();
    }
    Err(PyTypeError::new_err(format!(
        "cannot use a {} as workflow data",
        obj.get_type().name()?
    )))
}

fn report_to_py(py: Python<'_>, report: &Report) -> PyResult<Py<PyAny>> {
    let value = serde_json::to_value(report).map_err(|e| PyValueError::new_err(e.to_string()))?;
    to_py(py, &value)
}

/// Map loader errors onto the exceptions `safe_yaml.safe_yaml_load` raises:
/// OSError subclasses for the filesystem, ValueError for symlinks, size and
/// malformed or unsupported YAML.
fn yaml_err(e: YamlError) -> PyErr {
    let msg = e.to_string();
    yaml_exc(&e, msg)
}

/// The exception [`yaml_err`] raises for `e`, carrying `msg`.
fn yaml_exc(e: &YamlError, msg: String) -> PyErr {
    match e {
        YamlError::NotFound(_) => PyFileNotFoundError::new_err(msg),
        YamlError::Io { kind, .. } => match *kind {
            std::io::ErrorKind::PermissionDenied => PyPermissionError::new_err(msg),
            std::io::ErrorKind::IsADirectory => PyIsADirectoryError::new_err(msg),
            _ => PyOSError::new_err(msg),
        },
        YamlError::Symlink(_) | YamlError::TooLarge { .. } | YamlError::Parse { .. } => {
            PyValueError::new_err(msg)
        }
    }
}

/// A catalog or context load error: a file error raises as [`yaml_err`]
/// does, so a missing or unreadable file is the same `OSError` subclass as
/// from `load_yaml`; unusable content (a bad ontology) is a ValueError.
fn load_err(e: LoadError) -> PyErr {
    let msg = e.to_string();
    match e {
        LoadError::File { err, .. } => yaml_exc(&err, msg),
        LoadError::Invalid(_) => PyValueError::new_err(msg),
    }
}

/// Load a YAML file with the core's guards and return plain Python data.
#[pyfunction]
#[pyo3(signature = (path, max_bytes = yaml::DEFAULT_MAX_BYTES))]
fn load_yaml(py: Python<'_>, path: std::path::PathBuf, max_bytes: u64) -> PyResult<Py<PyAny>> {
    let v = py
        .detach(|| yaml::load_file(&path, max_bytes))
        .map_err(yaml_err)?;
    to_py(py, &v)
}

/// Parse a YAML string with the core's rules and return plain Python data.
#[pyfunction]
fn load_yaml_str(py: Python<'_>, text: String) -> PyResult<Py<PyAny>> {
    let v = py.detach(|| yaml::load_str(&text)).map_err(yaml_err)?;
    to_py(py, &v)
}

/// Load a workflow catalog file with the core's guards. Returns the data
/// and the version named by its `# Standard version:` header, if any.
#[pyfunction]
#[pyo3(signature = (path, max_bytes = yaml::ONTOLOGY_MAX_BYTES))]
fn load_catalog(
    py: Python<'_>,
    path: PathBuf,
    max_bytes: u64,
) -> PyResult<(Py<PyAny>, Option<String>)> {
    let (v, header) = py
        .detach(|| {
            let text = yaml::read_guarded(&path, max_bytes)?;
            Ok((yaml::load_str(&text)?, validate::header_version(&text)))
        })
        .map_err(yaml_err)?;
    Ok((to_py(py, &v)?, header))
}

/// Validate a workflow catalog file. Returns `{"diagnostics": [...],
/// "suggestions": [...]}`; raises if the ontology or catalog cannot be
/// loaded: FileNotFoundError and the other OSError subclasses for the
/// filesystem, as `load_yaml` does, ValueError otherwise.
///
/// `profiles`: domain profiles to apply (STANDARD v1.2 §5.21), as dicts;
/// their diagnostics come first in the report.
#[pyfunction]
#[pyo3(signature = (catalog_path, ontology_path, schema_root, profiles = None))]
fn validate_catalog(
    py: Python<'_>,
    catalog_path: PathBuf,
    ontology_path: PathBuf,
    schema_root: PathBuf,
    profiles: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyAny>> {
    let profiles = profiles_from_py(profiles)?;
    let report = py
        .detach(|| {
            let ctx = Context::load(&ontology_path, &schema_root)?;
            validate::validate_catalog_file_with(&ctx, &catalog_path, &profiles)
        })
        .map_err(load_err)?;
    report_to_py(py, &report)
}

/// Domain profiles given from Python: a list (of dicts, normally; anything
/// else in it is reported by the profile checks, S303).
fn profiles_from_py(obj: Option<&Bound<'_, PyAny>>) -> PyResult<Vec<Value>> {
    match obj.map(from_py).transpose()? {
        None => Ok(Vec::new()),
        Some(Value::Array(a)) => Ok(a),
        Some(_) => Err(PyTypeError::new_err("profiles must be a list")),
    }
}

/// `ValueError((message, diagnostics))` when `report` has an error.
fn refuse_profiles(py: Python<'_>, report: &Report) -> PyResult<()> {
    let errors: Vec<&Diagnostic> = report.errors().collect();
    if errors.is_empty() {
        return Ok(());
    }
    let value = serde_json::to_value(&errors).unwrap_or(Value::Null);
    let first = errors
        .first()
        .map(|d| format!("{}: {}", d.code.as_str(), d.message))
        .unwrap_or_default();
    Err(PyValueError::new_err((
        format!("the domain profiles are refused (STANDARD v1.2 §5.21.2): {first}"),
        to_py(py, &value)?,
    )))
}

/// A validator bound to one ontology, loaded once. The ontology's contracts
/// are a snapshot taken at construction; other schema files (workflow input
/// `$ref`s, `output_conforms_to`) are re-read on every call. Calls release
/// the GIL; when threads share one validator, a call may see a schema file
/// re-read by another call partway through, so give each thread its own
/// validator if files change during validation.
#[pyclass(frozen, module = "grounded_agency._core")]
struct Validator {
    ctx: Context,
}

#[pymethods]
impl Validator {
    #[new]
    fn new(py: Python<'_>, ontology_path: PathBuf, schema_root: PathBuf) -> PyResult<Self> {
        let ctx = py
            .detach(|| Context::load(&ontology_path, &schema_root))
            .map_err(load_err)?;
        Ok(Validator { ctx })
    }

    /// Validate a catalog file; same result as `validate_catalog`.
    #[pyo3(signature = (path, profiles = None))]
    fn validate_file(
        &self,
        py: Python<'_>,
        path: PathBuf,
        profiles: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        let profiles = profiles_from_py(profiles)?;
        let report = py
            .detach(|| {
                self.ctx.schemas.clear_cache();
                validate::validate_catalog_file_with(&self.ctx, &path, &profiles)
            })
            .map_err(load_err)?;
        report_to_py(py, &report)
    }

    /// Check domain profiles (STANDARD v1.2 §5.21.2): their diagnostics, in
    /// a report of the `validate` shape.
    fn check_profiles(&self, py: Python<'_>, profiles: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let profiles = profiles_from_py(Some(profiles))?;
        let mut report = Report::default();
        crate::profile::Policy::load(&profiles, &self.ctx.ontology, &mut report);
        report_to_py(py, &report)
    }

    /// The effective flags of a step or call of `capability` under
    /// `profiles` (STANDARD v1.2 §5.2.1, §5.21.3), with the step's own
    /// `declared` flags: `{"risk", "mutation", "requires_checkpoint",
    /// "requires_approval", "person", "warnings"}`. Raises ValueError, with
    /// the diagnostics, when the profiles have an error or the capability is
    /// unknown.
    #[pyo3(signature = (profiles, capability, declared = None))]
    fn profile_flags(
        &self,
        py: Python<'_>,
        profiles: &Bound<'_, PyAny>,
        capability: &str,
        declared: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        let profiles = profiles_from_py(Some(profiles))?;
        let declared = match declared.map(from_py).transpose()? {
            None => None,
            Some(Value::Object(m)) => Some(m),
            Some(_) => return Err(PyTypeError::new_err("declared must be a dict")),
        };
        let mut report = Report::default();
        let policy = crate::profile::Policy::load(&profiles, &self.ctx.ontology, &mut report);
        refuse_profiles(py, &report)?;
        let mut flags = policy
            .flags_json(&self.ctx.ontology, capability, declared.as_ref())
            .ok_or_else(|| {
                PyValueError::new_err(format!(
                    "capability '{capability}' not found in ontology (V101)"
                ))
            })?;
        flags["warnings"] = serde_json::to_value(&report.diagnostics).unwrap_or(Value::Null);
        to_py(py, &flags)
    }

    /// The rules `profiles` put in force besides flags (STANDARD v1.2
    /// §5.21.3): `{"minimum_confidence", "grounding": [{"require",
    /// "kinds"}], "destinations", "trust_weights"}`. Raises ValueError, with
    /// the diagnostics, when the profiles have an error.
    fn profile_policy(&self, py: Python<'_>, profiles: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let profiles = profiles_from_py(Some(profiles))?;
        let mut report = Report::default();
        let policy = crate::profile::Policy::load(&profiles, &self.ctx.ontology, &mut report);
        refuse_profiles(py, &report)?;
        to_py(py, &policy.rules_json())
    }

    /// The ontology's contracts with every `$ref` resolved, by capability in
    /// ontology order: `{id: {"input": schema, "output": schema}}`.
    fn contracts(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        to_py(py, &self.ctx.contracts_json())
    }

    /// Validate an in-memory catalog (a mapping of workflow name to
    /// workflow). `header` stands in for a file's `# Standard version:`;
    /// `profiles` are domain profiles to apply (STANDARD v1.2 §5.21).
    #[pyo3(signature = (catalog, header = None, profiles = None))]
    fn validate(
        &self,
        py: Python<'_>,
        catalog: &Bound<'_, PyAny>,
        header: Option<String>,
        profiles: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        let catalog = catalog_from_py(catalog)?;
        let profiles = profiles_from_py(profiles)?;
        let options = validate::Options {
            header,
            profiles,
            ..validate::Options::default()
        };
        let report = py
            .detach(|| {
                self.ctx.schemas.clear_cache();
                validate::validate_with(&self.ctx, &catalog, &options)
            })
            .map_err(load_err)?;
        report_to_py(py, &report)
    }
}

fn start_err(py: Python<'_>, e: StartError) -> PyErr {
    let message = e.to_string();
    match e {
        StartError::Invalid(diagnostics) => {
            let value = serde_json::to_value(&diagnostics).unwrap_or(Value::Null);
            match to_py(py, &value) {
                Ok(d) => PyValueError::new_err((message, d)),
                Err(err) => err,
            }
        }
        StartError::Inputs(_)
        | StartError::Program(_)
        | StartError::Identity(_)
        | StartError::Unsupported(_)
        | StartError::Grounding(_)
        | StartError::Policy(_)
        | StartError::Header(_) => PyValueError::new_err(message),
    }
}

/// Catalog sets (§5.1.1) and agent manifests (§5.15.1) are start members of
/// workstream S3; until it implements them, giving one is refused rather
/// than ignored.
fn unimplemented_sets(
    catalogs: Option<&Bound<'_, PyAny>>,
    agents: Option<&Bound<'_, PyAny>>,
) -> PyResult<()> {
    for (name, value) in [
        ("catalog sets (catalogs)", catalogs),
        ("agent manifests (agents)", agents),
    ] {
        if let Some(v) = value
            && (!v.is_none() && v.len().map_or(true, |n| n > 0))
        {
            return Err(PyValueError::new_err(format!(
                "this executor does not implement {name} yet"
            )));
        }
    }
    Ok(())
}

/// Grounding policies (§5.20) from a list of dicts `{require, kinds?,
/// attested?}`: each checked for its shape and against the ontology.
fn grounding_from_py(
    obj: Option<&Bound<'_, PyAny>>,
    ctx: &Context,
) -> PyResult<Vec<grounding::Policy>> {
    let Some(obj) = obj else {
        return Ok(Vec::new());
    };
    let Value::Array(items) = from_py(obj)? else {
        return Err(PyTypeError::new_err("grounding must be a list of dicts"));
    };
    items
        .into_iter()
        .enumerate()
        .map(|(i, item)| {
            let p: grounding::Policy = serde_json::from_value(item)
                .map_err(|e| PyValueError::new_err(format!("grounding[{i}]: {e}")))?;
            let p = grounding::Policy::new(p.require, p.kinds, p.attested)
                .map_err(|e| PyValueError::new_err(format!("grounding[{i}].{e}")))?;
            p.check_ids(&ctx.ontology)
                .map_err(|e| PyValueError::new_err(format!("grounding[{i}].{e}")))?;
            Ok(p)
        })
        .collect()
}

fn response_from_py(obj: &Bound<'_, PyAny>) -> PyResult<Response> {
    let value = from_py(obj)?;
    serde_json::from_value(value)
        .map_err(|e| PyValueError::new_err(format!("malformed response: {e}")))
}

/// A run of one workflow by the reference executor (design-114 §16): a
/// deterministic state machine with no I/O. Ask `next()` what to do, do it,
/// and `submit()` the result; pass the time with every call.
#[pyclass(name = "Run", module = "grounded_agency._core")]
struct PyRun {
    run: exec::Run,
}

#[pymethods]
impl PyRun {
    /// Validate `catalog` and start `workflow`. Raises ValueError when the
    /// catalog does not validate (with the error diagnostics as the second
    /// argument), the inputs do not match the workflow's, `actor_identity`
    /// is not an `agent_identity` (§5.17), or an option is malformed or not
    /// implemented yet.
    ///
    /// `header` is required: the version the catalog's `# Standard
    /// version:` header declares, or None for a catalog without one
    /// (STANDARD v1.2 §11.5); the catalog is validated with it.
    #[staticmethod]
    #[pyo3(signature = (validator, catalog, workflow, inputs = None, *, header, attendance = "attended", run_id, now_ms, actor_identity = None, records = "approvals", profiles = None, grounding = None, destinations = None, catalogs = None, agents = None))]
    #[allow(clippy::too_many_arguments)]
    fn start(
        py: Python<'_>,
        validator: PyRef<'_, Validator>,
        catalog: &Bound<'_, PyAny>,
        workflow: String,
        inputs: Option<&Bound<'_, PyAny>>,
        header: Option<String>,
        attendance: &str,
        run_id: String,
        now_ms: u64,
        actor_identity: Option<&Bound<'_, PyAny>>,
        records: &str,
        profiles: Option<&Bound<'_, PyAny>>,
        grounding: Option<&Bound<'_, PyAny>>,
        destinations: Option<&Bound<'_, PyAny>>,
        catalogs: Option<&Bound<'_, PyAny>>,
        agents: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        unimplemented_sets(catalogs, agents)?;
        let catalog = catalog_from_py(catalog)?;
        let actor_identity = actor_identity.map(from_py).transpose()?;
        let inputs = match inputs.map(from_py).transpose()? {
            None => Map::new(),
            Some(Value::Object(m)) => m,
            Some(_) => return Err(PyTypeError::new_err("inputs must be a dict")),
        };
        let attendance = match attendance {
            "attended" => Attendance::Attended,
            "unattended" => Attendance::Unattended,
            other => {
                return Err(PyValueError::new_err(format!(
                    "attendance must be 'attended' or 'unattended', not '{other}'"
                )));
            }
        };
        let records = match records {
            "approvals" => RecordMode::Approvals,
            "actions" => RecordMode::Actions,
            other => {
                return Err(PyValueError::new_err(format!(
                    "records must be 'approvals' or 'actions', not '{other}'"
                )));
            }
        };
        let ctx = &validator.ctx;
        let profiles = profiles_from_py(profiles)?;
        let grounding = grounding_from_py(grounding, ctx)?;
        let destinations = match destinations {
            None => Vec::new(),
            Some(d) => d.extract::<Vec<Vec<String>>>().map_err(|_| {
                PyTypeError::new_err("destinations must be a list of lists of strings")
            })?,
        };
        let options = StartOptions {
            attendance,
            run_id,
            now_ms,
            actor_identity,
            header,
            records,
            profiles,
            grounding,
            destinations,
        };
        let run = py
            .detach(|| {
                ctx.schemas.clear_cache();
                exec::Run::start(ctx, &catalog, &workflow, inputs, options)
            })
            .map_err(|e| start_err(py, e))?;
        Ok(PyRun { run })
    }

    /// Continue a run from `snapshot()`, against the same catalog. With a
    /// key, the snapshot's HMAC must match. The catalog's header, and the
    /// other start options, are the ones the run started with (kept in the
    /// state). With `actor_identity`, the actor the host continues the run
    /// for: a principal other than the run's is refused (ValueError), as is
    /// any actor for a run started without one (STANDARD v1.2 §5.17).
    #[staticmethod]
    #[pyo3(signature = (validator, catalog, snapshot, key = None, *, actor_identity = None, catalogs = None, agents = None))]
    #[allow(clippy::too_many_arguments)]
    fn restore(
        py: Python<'_>,
        validator: PyRef<'_, Validator>,
        catalog: &Bound<'_, PyAny>,
        snapshot: &Bound<'_, PyAny>,
        key: Option<Vec<u8>>,
        actor_identity: Option<&Bound<'_, PyAny>>,
        catalogs: Option<&Bound<'_, PyAny>>,
        agents: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        unimplemented_sets(catalogs, agents)?;
        let catalog = catalog_from_py(catalog)?;
        let snapshot: exec::Snapshot = serde_json::from_value(from_py(snapshot)?)
            .map_err(|e| PyValueError::new_err(format!("malformed snapshot: {e}")))?;
        let options = exec::RestoreOptions {
            actor_identity: actor_identity.map(from_py).transpose()?,
        };
        let ctx = &validator.ctx;
        let run = py
            .detach(|| exec::Run::restore_with(ctx, &catalog, &snapshot, key.as_deref(), options))
            .map_err(|e| match e {
                RestoreError::Start(s) => start_err(py, s),
                other => PyValueError::new_err(other.to_string()),
            })?;
        Ok(PyRun { run })
    }

    /// Resume a run that ended `deferred` (STANDARD v1.2 §5.14.1): it
    /// continues, as the same run, with the steps it deferred, under
    /// `attendance` from now on and, with `actor_identity`, a new actor
    /// (§5.17). ValueError when the run did not end deferred, the actor is
    /// not an `agent_identity`, or the state does not keep what resuming
    /// needs (a state saved before this executor kept it). Resume one saved
    /// state once.
    #[pyo3(signature = (*, attendance = "attended", now_ms, actor_identity = None))]
    fn resume(
        &mut self,
        py: Python<'_>,
        attendance: &str,
        now_ms: u64,
        actor_identity: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let attendance = match attendance {
            "attended" => Attendance::Attended,
            "unattended" => Attendance::Unattended,
            other => {
                return Err(PyValueError::new_err(format!(
                    "attendance must be 'attended' or 'unattended', not '{other}'"
                )));
            }
        };
        let options = exec::ResumeOptions {
            attendance,
            now_ms,
            actor_identity: actor_identity.map(from_py).transpose()?,
        };
        let run = &mut self.run;
        py.detach(|| run.resume(options))
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// The pending action, or the terminal one (`Completed`/`Failed`).
    fn next(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let value = serde_json::to_value(self.run.next())
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        to_py(py, &value)
    }

    /// Answer action `action_id`; raises ValueError (changing nothing) when
    /// the response does not answer it.
    fn submit(
        &mut self,
        py: Python<'_>,
        action_id: u64,
        response: &Bound<'_, PyAny>,
        now_ms: u64,
    ) -> PyResult<()> {
        let response = response_from_py(response)?;
        let run = &mut self.run;
        py.detach(|| run.submit(action_id, response, now_ms))
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// Pass the time: ends a due `Sleep`, times out a pending action.
    /// True when it changed the run (STANDARD v1.2 §5.19.2): a new action is
    /// pending, or the run ended.
    fn tick(&mut self, py: Python<'_>, now_ms: u64) -> bool {
        let run = &mut self.run;
        py.detach(|| run.tick(now_ms))
    }

    #[getter]
    fn finished(&self) -> bool {
        self.run.is_finished()
    }

    /// The `seq` the run's next trace event gets: read it before a submit,
    /// and `trace(since=...)` gives what the submit added.
    #[getter]
    fn trace_seq(&self) -> u64 {
        self.run.trace_seq()
    }

    /// The trace events the run holds; with `since`, those whose `seq` is
    /// at least `since` (a runner reads what one submit added).
    #[pyo3(signature = (since = None))]
    fn trace(&self, py: Python<'_>, since: Option<u64>) -> PyResult<Py<PyAny>> {
        let events = self.run.trace();
        let from = since.map_or(0, |s| {
            events.partition_point(|e| e["seq"].as_u64().is_some_and(|q| q < s))
        });
        to_py(py, &Value::Array(events[from..].to_vec()))
    }

    fn action_records(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        to_py(py, &Value::Array(self.run.action_records().to_vec()))
    }

    /// `{"state": canonical JSON, "sha256": ..., "hmac": ... or None}`.
    #[pyo3(signature = (key = None))]
    fn snapshot(&self, py: Python<'_>, key: Option<Vec<u8>>) -> PyResult<Py<PyAny>> {
        let value = serde_json::to_value(self.run.snapshot(key.as_deref()))
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        to_py(py, &value)
    }

    // ---- the host protocol's run operations (STANDARD v1.2 §5.19) ----

    /// The run's identifier (§5.19.2).
    #[getter]
    fn run_id(&self) -> String {
        self.run.run_id().to_string()
    }

    /// The earliest time at which a tick changes the run, or None (§5.19.3).
    fn wake_at(&self) -> Option<u64> {
        self.run.wake_at()
    }

    /// Cancel the run (§5.19.5): it ends with `Failed` R408, `reason` as
    /// its message. ValueError when it ended otherwise than `deferred`.
    fn cancel(&mut self, py: Python<'_>, reason: &str, now_ms: u64) -> PyResult<()> {
        let run = &mut self.run;
        py.detach(|| run.cancel(reason, now_ms))
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// Take the trace out of the run's state (§5.19.4); `seq` goes on.
    fn take_trace(&mut self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        to_py(py, &Value::Array(self.run.take_trace()))
    }

    /// Take the settled action records out of the run's state (§5.19.4).
    fn take_records(&mut self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        to_py(py, &Value::Array(self.run.take_records()))
    }

    /// The chain heads over what was taken (§5.19.4): `{"records": ...,
    /// "trace": ...}`, each empty while nothing was taken.
    #[getter]
    fn taken_sha256(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let (records, trace) = self.run.taken_heads();
        to_py(py, &serde_json::json!({"records": records, "trace": trace}))
    }

    /// The run's record (§5.19.8), or None while the run goes on.
    fn run_record(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        match self.run.run_record() {
            Some(r) => to_py(py, &r),
            None => Ok(py.None()),
        }
    }
}

/// The first fire time of a validated schedule trigger (`{cron|every,
/// timezone}`) strictly after `after_ms`, or None (STANDARD v1.2 §5.10.2).
/// ValueError when the schedule cannot be read.
#[pyfunction]
fn next_fire(schedule: &Bound<'_, PyAny>, after_ms: u64) -> PyResult<Option<u64>> {
    let schedule = from_py(schedule)?;
    crate::trigger::next_fire(&schedule, after_ms).map_err(PyValueError::new_err)
}

/// A value as I-JSON (RFC 7493): plain Python data within ±2^53 and at most
/// `MAX_VALUE_DEPTH` levels deep, or a ValueError.
fn ijson_from_py(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    let value = from_py(obj)?;
    exec::ijson(&value).map_err(PyValueError::new_err)?;
    Ok(value)
}

/// The canonical JSON (RFC 8785) of a value, as the executor writes it for
/// snapshots and approval digests. Any other digest of a value is the
/// SHA-256 of this text.
#[pyfunction]
fn canonical_json(value: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(exec::canonical::canonical(&ijson_from_py(value)?))
}

/// The approval digest of what a request shows (§5.14): the SHA-256 (hex)
/// of its canonical JSON.
#[pyfunction]
fn approval_digest(shown: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(exec::canonical::digest(&ijson_from_py(shown)?))
}

/// The §11.6 check of the versions a document cites: the diagnostics for
/// `standard` and `ontology` (each a value or None), located by `field`.
#[pyfunction]
#[pyo3(signature = (standard, ontology, ontology_version))]
fn check_cited_versions(
    py: Python<'_>,
    standard: Option<&Bound<'_, PyAny>>,
    ontology: Option<&Bound<'_, PyAny>>,
    ontology_version: &str,
) -> PyResult<Py<PyAny>> {
    let standard = standard.filter(|v| !v.is_none()).map(from_py).transpose()?;
    let ontology = ontology.filter(|v| !v.is_none()).map(from_py).transpose()?;
    let diagnostics: Vec<Diagnostic> = validate::check_cited(
        standard.as_ref(),
        ontology.as_ref(),
        ontology_version,
        |d, field| d.at("field", field),
    );
    let value =
        serde_json::to_value(&diagnostics).map_err(|e| PyValueError::new_err(e.to_string()))?;
    to_py(py, &value)
}

/// A duration of the §5.10.1 grammar in whole milliseconds, rounded up (so
/// only a zero duration is 0). ValueError when it is not a duration.
#[pyfunction]
fn duration_ms(text: &str) -> PyResult<u64> {
    let d = duration::parse(text).map_err(PyValueError::new_err)?;
    u64::try_from(d.as_nanos().div_ceil(1_000_000))
        .map_err(|_| PyValueError::new_err(format!("'{text}' is too large")))
}

/// Check a destination pattern (§4.4.2); ValueError says what is wrong.
#[pyfunction]
fn check_destination_pattern(pattern: &str) -> PyResult<()> {
    destination::check_pattern(pattern)
        .map(|_| ())
        .map_err(PyValueError::new_err)
}

/// Whether every destination policy allows `destination` (§4.4.2); with no
/// policy, every destination is allowed.
#[pyfunction]
fn destination_allowed(policies: Vec<Vec<String>>, destination: &str) -> bool {
    destination::allowed(&policies, destination)
}

/// §5.20's check of one output against a grounding policy (STANDARD
/// v1.2): `policy` is `{kinds?, attested?}` (a `require` is not needed for
/// one output); `bound_refs` the reference bodies the step's
/// `input_bindings` make (for a call, its argument names); `evidence_seen`
/// the host's attestation, None when absent (an empty list attests that the
/// producer saw nothing). Returns `{status: grounded|inferred|refused, code:
/// None|"F505", message, counted, legacy, unattested}` (the counts are 0 for
/// a refused output). ValueError for a malformed policy (a member other
/// than `require`, `kinds`, `attested` and `x-...` included) or a bound
/// reference that is not a reference body.
#[pyfunction]
#[pyo3(signature = (output, policy, bound_refs = None, evidence_seen = None))]
fn check_grounding(
    py: Python<'_>,
    output: &Bound<'_, PyAny>,
    policy: &Bound<'_, PyAny>,
    bound_refs: Option<Vec<String>>,
    evidence_seen: Option<Vec<String>>,
) -> PyResult<Py<PyAny>> {
    let output = from_py(output)?;
    let Value::Object(p) = from_py(policy)? else {
        return Err(PyTypeError::new_err("policy must be a dict"));
    };
    if let Some(e) = grounding::unknown_member(p.keys()) {
        return Err(PyValueError::new_err(format!("policy: {e}")));
    }
    let kinds: Option<Vec<String>> = match p.get("kinds") {
        None | Some(Value::Null) => None,
        Some(k) => Some(
            serde_json::from_value(k.clone())
                .map_err(|_| PyValueError::new_err("policy.kinds must be a list of strings"))?,
        ),
    };
    let attested = match p.get("attested") {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(_) => return Err(PyValueError::new_err("policy.attested must be a boolean")),
    };
    // The policy's shape; its `require` does not matter for one output.
    let policy = grounding::Policy::new(vec!["output".into()], kinds, attested)
        .map_err(|e| PyValueError::new_err(format!("policy.{e}")))?;
    let bound =
        grounding::parse_bound(&bound_refs.unwrap_or_default()).map_err(PyValueError::new_err)?;
    let result = match grounding::check(&output, &policy, &bound, evidence_seen.as_deref()) {
        Ok(c) => json!({
            "status": c.status,
            "code": null,
            "message": "",
            "counted": c.counted,
            "legacy": c.legacy,
            "unattested": c.unattested,
        }),
        Err(message) => json!({
            "status": "refused",
            "code": "F505",
            "message": message,
            "counted": 0,
            "legacy": 0,
            "unattested": 0,
        }),
    };
    to_py(py, &result)
}

/// A domain profile's minimum confidence applied to one output (STANDARD
/// v1.2 §5.21.3): None when the output passes (it is not an object, has no
/// `confidence`, or one at or above `minimum`), else `{code: "F504",
/// reason: below_minimum_confidence|invalid_confidence, message}`.
#[pyfunction]
fn check_confidence(
    py: Python<'_>,
    output: &Bound<'_, PyAny>,
    minimum: f64,
) -> PyResult<Py<PyAny>> {
    if !(0.0..=1.0).contains(&minimum) {
        return Err(PyValueError::new_err(
            "minimum must be a number from 0 to 1",
        ));
    }
    match crate::profile::check_confidence(&from_py(output)?, minimum) {
        None => Ok(py.None()),
        Some(fault) => to_py(
            py,
            &json!({"code": "F504", "reason": fault.reason(), "message": fault.message(minimum)}),
        ),
    }
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("DEFAULT_MAX_BYTES", yaml::DEFAULT_MAX_BYTES)?;
    m.add("ONTOLOGY_MAX_BYTES", yaml::ONTOLOGY_MAX_BYTES)?;
    m.add_function(wrap_pyfunction!(load_yaml, m)?)?;
    m.add_function(wrap_pyfunction!(load_yaml_str, m)?)?;
    m.add_function(wrap_pyfunction!(load_catalog, m)?)?;
    m.add_function(wrap_pyfunction!(validate_catalog, m)?)?;
    m.add_function(wrap_pyfunction!(canonical_json, m)?)?;
    m.add_function(wrap_pyfunction!(approval_digest, m)?)?;
    m.add_function(wrap_pyfunction!(check_cited_versions, m)?)?;
    m.add_function(wrap_pyfunction!(duration_ms, m)?)?;
    m.add_function(wrap_pyfunction!(check_destination_pattern, m)?)?;
    m.add_function(wrap_pyfunction!(destination_allowed, m)?)?;
    m.add_function(wrap_pyfunction!(next_fire, m)?)?;
    m.add_function(wrap_pyfunction!(check_grounding, m)?)?;
    m.add_function(wrap_pyfunction!(check_confidence, m)?)?;
    let spec_versions: Vec<String> = validate::semantics::SUPPORTED_VERSIONS
        .iter()
        .map(|(a, b)| format!("{a}.{b}"))
        .collect();
    m.add(
        "SPEC_VERSIONS",
        pyo3::types::PyTuple::new(m.py(), spec_versions)?,
    )?;
    m.add_class::<Validator>()?;
    m.add_class::<PyRun>()?;
    let codes: Vec<(&str, &str, &str)> = Code::ALL
        .iter()
        .map(|c| {
            let severity = match c.severity() {
                Severity::Error => "error",
                Severity::Warning => "warning",
            };
            (c.as_str(), c.name(), severity)
        })
        .collect();
    m.add("CODES", codes)?;
    Ok(())
}
