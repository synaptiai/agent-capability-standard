"""Grounding policies and the check of one output (STANDARD v1.2 §3.1, §5.20).

A grounding policy says which capabilities' outputs must be grounded:
``require`` (ontology ids), optionally ``kinds`` (only anchors of these §6.5
kinds count) and ``attested`` (only anchors whose availability is
established count). A host applies a list of them to a run
(``WorkflowRunner.run(grounding=...)``, which the core applies to nested
runs too) or to the calls a safety layer covers
(``GroundedAgentConfig.grounding``). Every policy is checked against the
ontology when it is made: an id it does not define is a ``ValueError``
naming V101, never a check silently turned off.

:func:`check_output` is §5.20's check of one output, by the core
(``_core.check_grounding``), which the vectors of
``tests/conformance/grounding/check.json`` pin.
"""

from __future__ import annotations

import difflib
import functools
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from . import _core

__all__ = [
    "GroundingPolicy",
    "GroundingResult",
    "Policies",
    "as_policies",
    "check_output",
]


@functools.cache
def _ontology_ids() -> frozenset[str]:
    """The capability ids of the packaged ontology, read once."""
    from .adapter import get_default_ontology_path

    data = _core.load_yaml(get_default_ontology_path())
    return frozenset(
        n["id"] for n in data.get("nodes", []) if isinstance(n, dict) and "id" in n
    )


def _is_kind(kind: object) -> bool:
    from .state.evidence_store import is_anchor_kind

    return is_anchor_kind(kind)


def _strings(value: object, what: str) -> frozenset[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ValueError(f"grounding {what} must be a list of strings")
    items = list(value)
    if not all(isinstance(x, str) for x in items):
        raise ValueError(f"grounding {what} must be a list of strings")
    if not items:
        raise ValueError(f"grounding {what} must not be empty")
    return frozenset(items)


POLICY_KEYS = ("require", "kinds", "attested")
"""The members of a grounding policy (§5.20); any other but an extension
member ``x-...`` is refused."""


@dataclass(frozen=True, slots=True)
class GroundingPolicy:
    """A grounding policy (§5.20). ``require`` and ``kinds`` take any
    iterable of strings and are kept as frozensets."""

    require: frozenset[str]
    kinds: frozenset[str] | None = None
    attested: bool = False

    def __post_init__(self) -> None:
        """``ValueError`` for an empty ``require``, an id the ontology does
        not define ("V101 UNKNOWN_CAPABILITY: ..."), an empty ``kinds``, a
        kind outside §6.5's vocabulary, or an ``attested`` that is not a
        boolean."""
        require = _strings(self.require, "require")
        known = _ontology_ids()
        for cap in sorted(require):
            if cap not in known:
                hint = difflib.get_close_matches(cap, sorted(known), n=1)
                tip = f"; did you mean {hint[0]!r}?" if hint else ""
                raise ValueError(
                    f"V101 UNKNOWN_CAPABILITY: grounding require {cap!r} is not a "
                    f"capability of the ontology{tip}"
                )
        object.__setattr__(self, "require", require)
        if self.kinds is not None:
            kinds = _strings(self.kinds, "kinds")
            for k in sorted(kinds):
                if not _is_kind(k):
                    raise ValueError(
                        f"grounding kinds: {k!r} is not an evidence anchor kind "
                        "(STANDARD v1.2 §6.5: file, url, tool, log, sensor, "
                        "human_note, api, record, or a vendor kind x-...)"
                    )
            object.__setattr__(self, "kinds", kinds)
        if not isinstance(self.attested, bool):
            raise ValueError("grounding attested must be a boolean")

    def requires(self, capability: str) -> bool:
        """Whether the policy checks outputs of ``capability``."""
        return capability in self.require

    def to_dict(self) -> dict[str, Any]:
        """The policy as the core takes it (``{require, kinds?, attested}``,
        lists sorted)."""
        out: dict[str, Any] = {"require": sorted(self.require)}
        if self.kinds is not None:
            out["kinds"] = sorted(self.kinds)
        out["attested"] = self.attested
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GroundingPolicy:
        """A policy from ``{require, kinds?, attested?}``. A member other
        than those and extension members ``x-...`` is a ``ValueError``
        (S303): a misspelt ``kinds`` or ``attested`` would otherwise turn
        the check off without a word."""
        if not isinstance(data, Mapping):
            raise ValueError("a grounding policy is a mapping")
        for key in data:
            if key not in POLICY_KEYS and not (
                isinstance(key, str) and key.startswith("x-")
            ):
                raise ValueError(
                    f"S303 SCHEMA_VALIDATION_FAILED: grounding policy: {key!r} is "
                    f"not a member of a grounding policy ({', '.join(POLICY_KEYS)}, "
                    "or an extension member x-...)"
                )
        kinds = data.get("kinds")
        return cls(
            require=_strings(data.get("require"), "require"),
            kinds=None if kinds is None else _strings(kinds, "kinds"),
            attested=data.get("attested", False),
        )

    @classmethod
    def from_profile(cls, profile: Mapping[str, Any]) -> GroundingPolicy | None:
        """The grounding policy a domain profile states (§5.20):
        ``evidence_policy.require_grounding`` is its ``require`` and
        ``required_anchor_types`` its ``kinds``. Also accepts a policy entry
        of the form ``{require, kinds}``. None when the profile requires
        none; ``ValueError`` as the constructor (a ``required_anchor_types``
        value that is not a §6.5 kind included)."""
        if not isinstance(profile, Mapping):
            raise ValueError("a profile is a mapping")
        if "require" in profile:
            return cls.from_dict(profile)
        policy = profile.get("evidence_policy") or {}
        if not isinstance(policy, Mapping):
            raise ValueError("a profile's evidence_policy is a mapping")
        require = policy.get("require_grounding") or []
        if not require:
            return None
        kinds = policy.get("required_anchor_types") or None
        return cls(
            require=_strings(require, "require"),
            kinds=None if kinds is None else _strings(kinds, "kinds"),
        )


Policies = GroundingPolicy | Sequence[GroundingPolicy] | None
"""One policy, a list of them, or none."""


def as_policies(value: Policies) -> tuple[GroundingPolicy, ...]:
    """``None`` → ``()``, one policy → ``(policy,)``, a sequence → a tuple.
    ``TypeError`` for anything that is not a :class:`GroundingPolicy`."""
    if value is None:
        return ()
    if isinstance(value, GroundingPolicy):
        return (value,)
    out = tuple(value)
    for p in out:
        if not isinstance(p, GroundingPolicy):
            raise TypeError(f"a grounding policy, not {type(p).__name__}")
    return out


@dataclass(frozen=True, slots=True)
class GroundingResult:
    """The outcome of §5.20's check of one output."""

    status: Literal["grounded", "inferred", "refused"]
    code: str | None
    message: str
    counted: int
    legacy: int
    unattested: int = 0

    @property
    def ok(self) -> bool:
        """Whether the output passed (grounded or inferred)."""
        return self.code is None


def check_output(
    output: Mapping[str, Any],
    policy: GroundingPolicy,
    *,
    bound_refs: Iterable[str] = (),
    evidence_seen: Iterable[str] | None = None,
) -> GroundingResult:
    """STANDARD v1.2 §5.20 for one output, by the core's check. For a step,
    ``bound_refs`` are the reference bodies its ``input_bindings`` make; for
    a call, its argument names. ``evidence_seen=None`` (absent) attests
    nothing; ``()`` attests that nothing was seen. ``ValueError`` for a
    bound reference that is not a reference body."""
    r = _core.check_grounding(
        dict(output),
        policy.to_dict(),
        list(bound_refs),
        None if evidence_seen is None else list(evidence_seen),
    )
    return GroundingResult(
        status=r["status"],
        code=r["code"],
        message=r["message"],
        counted=r["counted"],
        legacy=r["legacy"],
        unattested=r["unattested"],
    )
