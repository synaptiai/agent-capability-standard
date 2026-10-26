"""Type stubs for the compiled Rust core (``core/src/python.rs``).

Keep in sync with the ``#[pyfunction]`` signatures in that file.
"""

from os import PathLike
from typing import Any

__version__: str
DEFAULT_MAX_BYTES: int
ONTOLOGY_MAX_BYTES: int

def load_yaml(path: str | PathLike[str], max_bytes: int = ...) -> Any: ...
def load_yaml_str(text: str) -> Any: ...
def validate_catalog(
    catalog_path: str | PathLike[str],
    ontology_path: str | PathLike[str],
    schema_root: str | PathLike[str],
) -> dict[str, Any]: ...
