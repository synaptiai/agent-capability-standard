"""Type stubs for the compiled Rust core (``core/src/python.rs``).

Keep in sync with the ``#[pyfunction]``/``#[pyclass]`` items in that file.
"""

from os import PathLike
from typing import Any

__version__: str
DEFAULT_MAX_BYTES: int
ONTOLOGY_MAX_BYTES: int
CODES: list[tuple[str, str, str]]
"""Every diagnostic code as ``(code, name, severity)``, severity being
``"error"`` or ``"warning"``."""

def load_yaml(path: str | PathLike[str], max_bytes: int = ...) -> Any: ...
def load_yaml_str(text: str) -> Any: ...
def load_catalog(
    path: str | PathLike[str], max_bytes: int = ...
) -> tuple[Any, str | None]: ...
def validate_catalog(
    catalog_path: str | PathLike[str],
    ontology_path: str | PathLike[str],
    schema_root: str | PathLike[str],
) -> dict[str, Any]: ...

class Validator:
    def __init__(
        self, ontology_path: str | PathLike[str], schema_root: str | PathLike[str]
    ) -> None: ...
    def validate_file(self, path: str | PathLike[str]) -> dict[str, Any]: ...
    def validate(self, catalog: Any, header: str | None = None) -> dict[str, Any]: ...
