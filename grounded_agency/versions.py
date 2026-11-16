"""The versions a document outside a workflow cites (STANDARD v1.2 §11.6).

A document that names capabilities by id (a domain profile, a tool binding
record, an agent or catalog manifest, an interoperability mapping) cites the
Standard and ontology versions it was written against as ``standard`` and
``ontology``. A consumer refuses one whose ``ontology`` has another major
than its own ontology's, or whose ``standard`` it does not support (V109);
a value that is not ``MAJOR.MINOR[.PATCH]`` is S303. The rule is the core's
(``_core.check_cited_versions``): no version arithmetic here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import _core

__all__ = ["SPEC_VERSIONS", "CitedVersionError", "check_cited"]

SPEC_VERSIONS: tuple[str, ...] = tuple(_core.SPEC_VERSIONS)
"""The Standard versions this implementation supports (§11.5)."""


class CitedVersionError(ValueError):
    """A document cites versions this implementation does not accept.

    Attributes:
        code: The first diagnostic's code: ``V109`` (another ontology major,
            an unsupported Standard) or ``S303`` (not a version).
        diagnostics: Every diagnostic, each located with the document.
    """

    def __init__(self, message: str, code: str, diagnostics: list[dict[str, Any]]):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def check_cited(
    cited: Mapping[str, Any], *, ontology_version: str, document: str
) -> None:
    """Check the ``standard`` and ``ontology`` a document cites (§11.6).

    Args:
        cited: The mapping that holds the two members (a profile's top
            level; a mapping's ``meta.agent_capability_standard``). A member
            that is absent is not checked.
        ontology_version: The version of the ontology this consumer uses.
        document: Names the document in the diagnostics' location.

    Raises:
        CitedVersionError: on any diagnostic.
    """
    diagnostics: list[dict[str, Any]] = _core.check_cited_versions(
        cited.get("standard"), cited.get("ontology"), ontology_version
    )
    if not diagnostics:
        return
    for d in diagnostics:
        d.setdefault("location", {})["document"] = document
    first = diagnostics[0]
    raise CitedVersionError(
        f"{document}: {first['code']} {first['message']}",
        str(first["code"]),
        diagnostics,
    )
