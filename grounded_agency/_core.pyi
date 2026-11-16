"""Type stubs for the compiled Rust core (``core/src/python.rs``).

Keep in sync with the ``#[pyfunction]``/``#[pyclass]`` items in that file.
"""

from collections.abc import Sequence
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
    *,
    catalogs: Sequence[Any] | None = None,
    agents: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """``catalogs``: the other catalogs of the catalog set (§5.1.1), each a
    path, a mapping or a ``(mapping, header)`` pair; ``agents``: agent
    manifests (§5.15.1), each a path or a mapping. A refused set or manifest
    raises ``ValueError``."""

def model_family(model_id: str) -> str | None:
    """The model family a host derives from a model identifier (§5.15), or
    None when the rule gives none."""

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

def next_fire(schedule: dict[str, Any], after_ms: int) -> int | None:
    """The first fire time of a validated schedule trigger strictly after
    ``after_ms``, or None (STANDARD v1.2 §5.10.2). ``ValueError`` when the
    schedule cannot be read."""

def check_grounding(
    output: Any,
    policy: dict[str, Any],
    bound_refs: list[str] | None = None,
    evidence_seen: list[str] | None = None,
) -> dict[str, Any]:
    """STANDARD v1.2 §5.20's check of one output against a grounding policy
    (``{kinds?, attested?}``; ``require`` is not needed). ``bound_refs`` are
    the reference bodies the step's ``input_bindings`` make (for a call, its
    argument names); ``evidence_seen`` None is absent, an empty list attests
    that nothing was seen. Returns ``{status: grounded|inferred|refused,
    code: None|"F505", message, counted, legacy, unattested}`` (the counts
    are 0 for a refused output). ``ValueError`` for a malformed policy or a
    bound reference that is not a reference body."""

@final
class Validator:
    """Raises ``FileNotFoundError`` (or another ``OSError``) when the
    ontology cannot be read, ``ValueError`` when it does not load."""

    def __new__(
        cls, ontology_path: str | PathLike[str], schema_root: str | PathLike[str]
    ) -> Validator: ...
    def validate_file(
        self,
        path: str | PathLike[str],
        *,
        catalogs: Sequence[Any] | None = None,
        agents: Sequence[Any] | None = None,
    ) -> dict[str, Any]: ...
    def validate(
        self,
        catalog: Any,
        header: str | None = None,
        *,
        catalogs: Sequence[Any] | None = None,
        agents: Sequence[Any] | None = None,
    ) -> dict[str, Any]: ...
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
        catalogs: Sequence[Any] | None = None,
        agents: Sequence[Any] | None = None,
    ) -> Run:
        """``header`` is required: the version the catalog's header declares,
        or None for a catalog without one (§11.5). ``records`` is the record
        mode (§6.4): ``approvals`` or ``actions``. ``grounding`` is a list of
        grounding policies ``{require, kinds?, attested?}`` the host applies
        to the run and its nested runs (§5.20): a malformed policy, or one
        that requires a capability the ontology does not define (V101), is
        a ``ValueError``. ``catalogs`` and ``agents`` are the other catalogs of
        the catalog set (§5.1.1) and agent manifests (§5.15.1), as for
        ``validate_catalog``. ``profiles`` and ``destinations`` are refused
        (``ValueError``) until the 1.2 workstreams implement them."""

    @staticmethod
    def restore(
        validator: Validator,
        catalog: Any,
        snapshot: dict[str, Any],
        key: bytes | None = None,
        *,
        actor_identity: dict[str, Any] | None = None,
        catalogs: Sequence[Any] | None = None,
        agents: Sequence[Any] | None = None,
    ) -> Run:
        """With ``actor_identity``, the actor the host continues the run
        for: another principal than the run's, or any actor for a run started
        without one, is refused (``ValueError``; §5.17). ``catalogs`` and
        ``agents`` must be the ones the run started with."""

    def resume(
        self,
        *,
        attendance: str = "attended",
        now_ms: int,
        actor_identity: dict[str, Any] | None = None,
    ) -> None:
        """Resume a run that ended ``deferred`` (§5.14.1), as the same run,
        under ``attendance`` and, with ``actor_identity``, a new actor.
        ``ValueError`` when the run did not end deferred, the actor is not an
        ``agent_identity``, or the state does not keep what resuming needs."""

    def next(self) -> dict[str, Any]: ...
    def submit(self, action_id: int, response: dict[str, Any], now_ms: int) -> None: ...
    def tick(self, now_ms: int) -> bool:
        """True when the tick changed the run (STANDARD v1.2 §5.19.2)."""
    @property
    def run_id(self) -> str: ...
    def wake_at(self) -> int | None:
        """The earliest time at which a tick changes the run, or None
        (§5.19.3)."""
    def cancel(self, reason: str, now_ms: int) -> None:
        """End the run with ``Failed`` R408 (§5.19.5). ``ValueError`` when it
        ended otherwise than ``deferred``."""
    def take_trace(self) -> list[dict[str, Any]]:
        """Take the trace out of the run's state (§5.19.4)."""
    def take_records(self) -> list[dict[str, Any]]:
        """Take the settled action records out of the run's state (§5.19.4)."""
    @property
    def taken_sha256(self) -> dict[str, str]:
        """The chain heads over what was taken: ``{"records", "trace"}``."""
    def run_record(self) -> dict[str, Any] | None:
        """The run's record (§5.19.8), or None while the run goes on."""
    @property
    def finished(self) -> bool: ...
    @property
    def trace_seq(self) -> int:
        """The ``seq`` the run's next trace event gets."""
    def trace(self, since: int | None = None) -> list[dict[str, Any]]:
        """The trace events the run holds; with ``since``, those whose
        ``seq`` is at least ``since``."""
    def action_records(self) -> list[dict[str, Any]]: ...
    def snapshot(self, key: bytes | None = None) -> dict[str, Any]: ...
