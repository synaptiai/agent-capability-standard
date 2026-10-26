//! The `grounded_agency._core` extension module.

use pyo3::exceptions::{
    PyFileNotFoundError, PyIsADirectoryError, PyOSError, PyPermissionError, PyValueError,
};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyList, PyString};
use serde_json::Value;

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

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("DEFAULT_MAX_BYTES", yaml::DEFAULT_MAX_BYTES)?;
    m.add("ONTOLOGY_MAX_BYTES", yaml::ONTOLOGY_MAX_BYTES)?;
    m.add_function(wrap_pyfunction!(load_yaml, m)?)?;
    m.add_function(wrap_pyfunction!(load_yaml_str, m)?)?;
    Ok(())
}
