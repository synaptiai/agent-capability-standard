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
SPEC_VERSIONS: tuple[str, ...]
"""The Standard versions this core supports, ``MAJOR.MINOR`` (§11.5)."""

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
def canonical_json(value: Any) -> str:
    """The canonical JSON (RFC 8785) of an I-JSON value; ``ValueError``
    outside I-JSON. Any digest of a value is the SHA-256 of this text."""

def approval_digest(shown: Any) -> str:
    """The approval digest (§5.14) of what a request shows."""

def check_cited_versions(
    standard: Any, ontology: Any, ontology_version: str
) -> list[dict[str, Any]]:
    """The §11.6 diagnostics (S303, V109) of a document's cited ``standard``
    and ``ontology`` (each a value or None), located by ``field``."""

def duration_ms(text: str) -> int:
    """A §5.10.1 duration in whole milliseconds, rounded up; ``ValueError``
    when it is not one."""

def check_destination_pattern(pattern: str) -> None:
    """``ValueError`` when ``pattern`` is not a destination pattern
    (§4.4.2)."""

def destination_allowed(policies: list[list[str]], destination: str) -> bool:
    """Whether every destination policy allows ``destination`` (§4.4.2)."""

@final
class Validator:
    """Raises ``FileNotFoundError`` (or another ``OSError``) when the
    ontology cannot be read, ``ValueError`` when it does not load."""

    def __new__(
        cls, ontology_path: str | PathLike[str], schema_root: str | PathLike[str]
    ) -> Validator: ...
    def validate_file(self, path: str | PathLike[str]) -> dict[str, Any]: ...
    def validate(self, catalog: Any, header: str | None = None) -> dict[str, Any]: ...
    def contracts(self) -> dict[str, dict[str, Any]]:
        """Every capability's ``{"input": ..., "output": ...}`` contracts with
        each ``$ref`` resolved, in ontology order."""

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
        header: str | None,
        attendance: str = "attended",
        run_id: str,
        now_ms: int,
        actor_identity: dict[str, Any] | None = None,
        records: str = "approvals",
        profiles: list[dict[str, Any]] | None = None,
        grounding: list[dict[str, Any]] | None = None,
        destinations: list[list[str]] | None = None,
        catalogs: list[Any] | None = None,
        agents: list[Any] | None = None,
    ) -> Run:
        """``header`` is required: the version the catalog's header declares,
        or None for a catalog without one (§11.5). ``records="actions"``,
        ``profiles``, ``grounding``, ``destinations``, ``catalogs`` and
        ``agents`` are refused (``ValueError``) until the 1.2 workstreams
        implement them."""

    @staticmethod
    def restore(
        validator: Validator,
        catalog: Any,
        snapshot: dict[str, Any],
        key: bytes | None = None,
        *,
        catalogs: list[Any] | None = None,
        agents: list[Any] | None = None,
    ) -> Run: ...
    def next(self) -> dict[str, Any]: ...
    def submit(self, action_id: int, response: dict[str, Any], now_ms: int) -> None: ...
    def tick(self, now_ms: int) -> None: ...
    @property
    def finished(self) -> bool: ...
    def trace(self) -> list[dict[str, Any]]: ...
    def action_records(self) -> list[dict[str, Any]]: ...
    def snapshot(self, key: bytes | None = None) -> dict[str, Any]: ...
