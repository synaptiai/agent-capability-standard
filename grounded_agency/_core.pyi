"""Type stubs for the compiled Rust core (``core/src/python.rs``).

Keep in sync with the ``#[pyfunction]``/``#[pyclass]`` items in that file.
"""

from os import PathLike
from typing import Any, final

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

@final
class Validator:
    """Raises ``FileNotFoundError`` (or another ``OSError``) when the
    ontology cannot be read, ``ValueError`` when it does not load."""

    def __new__(
        cls, ontology_path: str | PathLike[str], schema_root: str | PathLike[str]
    ) -> Validator: ...
    def validate_file(self, path: str | PathLike[str]) -> dict[str, Any]: ...
    def validate(self, catalog: Any, header: str | None = None) -> dict[str, Any]: ...

@final
class Run:
    """A run of one workflow by the reference executor (design-114 §16)."""

    @staticmethod
    def start(
        validator: Validator,
        catalog: Any,
        workflow: str,
        inputs: dict[str, Any] | None = None,
        *,
        attendance: str = "attended",
        run_id: str,
        now_ms: int,
        actor_identity: dict[str, Any] | None = None,
    ) -> Run: ...
    @staticmethod
    def restore(
        validator: Validator,
        catalog: Any,
        snapshot: dict[str, Any],
        key: bytes | None = None,
    ) -> Run: ...
    def next(self) -> dict[str, Any]: ...
    def submit(self, action_id: int, response: dict[str, Any], now_ms: int) -> None: ...
    def tick(self, now_ms: int) -> None: ...
    @property
    def finished(self) -> bool: ...
    def trace(self) -> list[dict[str, Any]]: ...
    def action_records(self) -> list[dict[str, Any]]: ...
    def snapshot(self, key: bytes | None = None) -> dict[str, Any]: ...
