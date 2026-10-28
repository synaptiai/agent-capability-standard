//! The `grounded_agency._core` extension module.

use std::path::PathBuf;

use pyo3::exceptions::{
    PyFileNotFoundError, PyIsADirectoryError, PyOSError, PyPermissionError, PyTypeError,
    PyValueError,
};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};
use serde_json::{Map, Value};

use crate::diag::{Code, Severity};
use crate::exec::{self, Attendance, Response, RestoreError, StartError, StartOptions};
use crate::validate::{self, Context, Report};
use crate::yaml::{self, YamlError};

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
    match e {
        YamlError::NotFound(_) => PyFileNotFoundError::new_err(msg),
        YamlError::Io { kind, .. } => match kind {
            std::io::ErrorKind::PermissionDenied => PyPermissionError::new_err(msg),
            std::io::ErrorKind::IsADirectory => PyIsADirectoryError::new_err(msg),
            _ => PyOSError::new_err(msg),
        },
        YamlError::Symlink(_) | YamlError::TooLarge { .. } | YamlError::Parse { .. } => {
            PyValueError::new_err(msg)
        }
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
/// "suggestions": [...]}`; raises if the ontology or catalog cannot be loaded.
#[pyfunction]
fn validate_catalog(
    py: Python<'_>,
    catalog_path: PathBuf,
    ontology_path: PathBuf,
    schema_root: PathBuf,
) -> PyResult<Py<PyAny>> {
    let report = py
        .detach(|| {
            let ctx = Context::load(&ontology_path, &schema_root)?;
            validate::validate_catalog_file(&ctx, &catalog_path)
        })
        .map_err(PyValueError::new_err)?;
    report_to_py(py, &report)
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
            .map_err(PyValueError::new_err)?;
        Ok(Validator { ctx })
    }

    /// Validate a catalog file; same result as `validate_catalog`.
    fn validate_file(&self, py: Python<'_>, path: PathBuf) -> PyResult<Py<PyAny>> {
        let report = py
            .detach(|| {
                self.ctx.schemas.clear_cache();
                validate::validate_catalog_file(&self.ctx, &path)
            })
            .map_err(PyValueError::new_err)?;
        report_to_py(py, &report)
    }

    /// Validate an in-memory catalog (a mapping of workflow name to
    /// workflow). `header` stands in for a file's `# Standard version:`.
    #[pyo3(signature = (catalog, header = None))]
    fn validate(
        &self,
        py: Python<'_>,
        catalog: &Bound<'_, PyAny>,
        header: Option<String>,
    ) -> PyResult<Py<PyAny>> {
        let catalog = catalog_from_py(catalog)?;
        let report = py.detach(|| {
            self.ctx.schemas.clear_cache();
            validate::validate_catalog(&self.ctx, &catalog, header.as_deref())
        });
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
        StartError::Inputs(_) | StartError::Program(_) | StartError::Identity(_) => {
            PyValueError::new_err(message)
        }
    }
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
    /// argument), the inputs do not match the workflow's, or
    /// `actor_identity` is not an `agent_identity` (§5.17).
    #[staticmethod]
    #[pyo3(signature = (validator, catalog, workflow, inputs = None, *, attendance = "attended", run_id, now_ms, actor_identity = None))]
    #[allow(clippy::too_many_arguments)]
    fn start(
        py: Python<'_>,
        validator: PyRef<'_, Validator>,
        catalog: &Bound<'_, PyAny>,
        workflow: String,
        inputs: Option<&Bound<'_, PyAny>>,
        attendance: &str,
        run_id: String,
        now_ms: u64,
        actor_identity: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
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
        let ctx = &validator.ctx;
        let options = StartOptions {
            attendance,
            run_id,
            now_ms,
            actor_identity,
        };
        let run = py
            .detach(|| {
                ctx.schemas.clear_cache();
                exec::Run::start(ctx, &catalog, &workflow, inputs, options)
            })
            .map_err(|e| start_err(py, e))?;
        Ok(PyRun { run })
    }

    /// Resume a run from `snapshot()`, against the same catalog. With a key,
    /// the snapshot's HMAC must match.
    #[staticmethod]
    #[pyo3(signature = (validator, catalog, snapshot, key = None))]
    fn restore(
        py: Python<'_>,
        validator: PyRef<'_, Validator>,
        catalog: &Bound<'_, PyAny>,
        snapshot: &Bound<'_, PyAny>,
        key: Option<Vec<u8>>,
    ) -> PyResult<Self> {
        let catalog = catalog_from_py(catalog)?;
        let snapshot: exec::Snapshot = serde_json::from_value(from_py(snapshot)?)
            .map_err(|e| PyValueError::new_err(format!("malformed snapshot: {e}")))?;
        let ctx = &validator.ctx;
        let run = py
            .detach(|| exec::Run::restore(ctx, &catalog, &snapshot, key.as_deref()))
            .map_err(|e| match e {
                RestoreError::Start(s) => start_err(py, s),
                other => PyValueError::new_err(other.to_string()),
            })?;
        Ok(PyRun { run })
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
    fn tick(&mut self, py: Python<'_>, now_ms: u64) {
        let run = &mut self.run;
        py.detach(|| run.tick(now_ms));
    }

    #[getter]
    fn finished(&self) -> bool {
        self.run.is_finished()
    }

    fn trace(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        to_py(py, &Value::Array(self.run.trace().to_vec()))
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
