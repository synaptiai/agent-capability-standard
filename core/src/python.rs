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
/// The same limits as for YAML apply: nesting at most [`yaml::MAX_DEPTH`]
/// levels, and at most [`yaml::MAX_ALIAS_WEIGHT`] nodes in all, so a
/// structure that shares or cycles through its own containers cannot expand
/// without bound.
pub(crate) fn from_py(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    from_py_inner(obj, 0, &mut 0)
}

fn from_py_inner(obj: &Bound<'_, PyAny>, depth: usize, nodes: &mut usize) -> PyResult<Value> {
    if depth > yaml::MAX_DEPTH {
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
/// `$ref`s, `output_conforms_to`) are re-read on every call.
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
        let catalog = from_py(catalog)?;
        let report = py.detach(|| {
            self.ctx.schemas.clear_cache();
            validate::validate_catalog(&self.ctx, &catalog, header.as_deref())
        });
        report_to_py(py, &report)
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
