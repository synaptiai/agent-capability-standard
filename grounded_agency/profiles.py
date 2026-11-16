"""Domain profiles applied by a host, a safety layer or a validator
(STANDARD v1.2 §5.21).

A profile tightens what the Standard requires of steps and calls in one
domain: which need a checkpoint, which need approval and from whom, what
counts as evidence, how confident an output must be and where a ``send``
may go; its ``trust_weights`` replace the trust model's weights (§8.3). A
workflow does not select one: its ``profile`` field applies nothing.

:class:`AppliedProfiles` checks profiles and answers what they change. Every
rule is the core's (``_core.Validator.check_profiles``, ``profile_flags``
and ``profile_policy``), the same implementation the executor and the
validator apply: this module computes nothing itself.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from . import _core

__all__ = [
    "AppliedProfiles",
    "EffectiveFlags",
    "ProfileError",
    "load_profile",
]

logger = logging.getLogger(__name__)

ProfileSource = Mapping[str, Any] | str | os.PathLike[str]

# The rules a profile puts in force that an applier may not apply, by the
# name AppliedProfiles.refuse_unapplied takes: what each is, and the member
# that sets it (under a top-level member, or top-level). Every other rule
# (grounding, minimum confidence, destinations) is applied by every applier.
_RULES: dict[str, tuple[str, str, str | None]] = {
    "checkpoints": (
        "a checkpoint policy that raises requires_checkpoint (§5.21.3)",
        "checkpoint_policy",
        None,
    ),
}


def load_profile(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read a profile file (YAML or JSON) with the core's hardened loader.

    Raises:
        OSError: the file cannot be read.
        ValueError: it is not YAML, or not a mapping.
    """
    loaded = _core.load_yaml(str(path))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: a domain profile must be a mapping")
    return loaded


class ProfileError(ValueError):
    """Profiles that do not load (§5.21.2).

    Attributes:
        diagnostics: Every diagnostic of the profiles, as the core reports
            them (``code``, ``message``, ``location.profile``,
            ``location.field``).
    """

    def __init__(self, message: str, diagnostics: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


@dataclass(frozen=True, slots=True)
class EffectiveFlags:
    """A step's or call's effective flags under the applied profiles
    (§5.2.1, §5.21.3)."""

    risk: str
    mutation: bool
    requires_checkpoint: bool
    requires_approval: bool
    person: bool
    """A person must decide, each time: no standing mandate covers it."""


def _sets(document: Mapping[str, Any], rule: str) -> bool:
    """Whether a loaded profile puts ``rule`` (a key of ``_RULES``) in
    force: a ``checkpoint_policy`` raises a flag only with a value other
    than ``never`` (§5.21.3)."""
    _, member, under = _RULES[rule]
    holder = document.get(under) if under else document
    value = holder.get(member) if isinstance(holder, Mapping) else None
    return isinstance(value, Mapping) and any(v != "never" for v in value.values())


@cache
def _default_validator() -> _core.Validator:
    from .adapter import get_default_ontology_path

    ontology = Path(get_default_ontology_path())
    return _core.Validator(str(ontology), str(ontology.parent.parent))


class AppliedProfiles:
    """Profiles to apply, checked when constructed (§5.21.2).

    Several profiles apply together: each applies on its own, so the
    strictest result holds (§5.21.1).
    """

    def __init__(
        self,
        profiles: Sequence[ProfileSource],
        *,
        validator: _core.Validator | None = None,
    ) -> None:
        """
        Args:
            profiles: Each a loaded profile (a mapping) or the path of a
                profile file.
            validator: Whose ontology the profiles are checked against. The
                default: the packaged ontology.

        Raises:
            ProfileError: a profile has an error (S303, S304, V101, V109).
                Warnings (W602, W603, W604) are kept in :attr:`warnings`
                and logged: a misspelled top-level member is W604 and
                ignored (§5.21.2), so the log names it with the member
                meant.
            OSError: a profile file cannot be read.
        """
        documents: list[dict[str, Any]] = []
        for p in profiles:
            if isinstance(p, Mapping):
                documents.append(dict(p))
            else:
                documents.append(load_profile(p))
        self._given = validator
        diagnostics: list[dict[str, Any]] = (
            self._checker().check_profiles(documents)["diagnostics"]
            if documents
            else []
        )
        errors = [d for d in diagnostics if d["severity"] == "error"]
        if errors:
            first = errors[0]
            where = first.get("location", {})
            raise ProfileError(
                f"{first['code']} {first['message']} (profile "
                f"{where.get('profile')}, field {where.get('field')!r}; "
                f"STANDARD v1.2 §5.21.2)",
                diagnostics,
            )
        self.documents: list[dict[str, Any]] = documents
        """The profiles as given: what ``Run.start(profiles=...)`` takes."""
        self.warnings: list[dict[str, Any]] = diagnostics
        for w in diagnostics:
            where = w.get("location", {})
            hint = w.get("suggestion")
            logger.warning(
                "%s %s (profile %s, field %r; STANDARD v1.2 §5.21.2)%s",
                w["code"],
                w["message"],
                where.get("profile"),
                where.get("field"),
                f": {hint}" if hint else "",
            )
        policy = self._checker().profile_policy(documents) if documents else {}
        self.minimum_confidence: float | None = policy.get("minimum_confidence")
        """The highest ``minimum_confidence`` (§5.21.3), if any sets one."""
        self.grounding: list[dict[str, Any]] = policy.get("grounding", [])
        """One grounding policy (§5.20) per profile with
        ``require_grounding``: ``{"require", "kinds"}``."""
        self.destinations: list[list[str]] = policy.get("destinations", [])
        """The profiles' destination policies (§4.4.2), each in force."""
        self.trust_weights: dict[str, float] = policy.get("trust_weights", {})
        """The trust weight overrides (§8.3), the lowest per key."""
        self._flags: dict[tuple[str, tuple[tuple[str, Any], ...]], EffectiveFlags] = {}

    def refuse_unapplied(self, rules: Iterable[str], applier: str) -> None:
        """Refuse these profiles where one puts in force a rule of
        ``rules`` that ``applier`` does not apply: ``"checkpoints"`` (a
        ``checkpoint_policy`` that raises ``requires_checkpoint``), which
        the adapter with ``strict_mode=False`` does not enforce. Applied
        without the rule, a call would go ahead as if it were absent. Every
        applier applies the other rules a profile sets (grounding, a
        minimum confidence, destinations).

        Raises:
            ProfileError: a profile sets one of ``rules``; its
                ``diagnostics`` is empty (the profiles load, ``applier``
                cannot apply them).
            KeyError: a name in ``rules`` is not ``"checkpoints"``.
        """
        for rule in rules:
            what, member, under = _RULES[rule]
            setting = [str(d.get("domain")) for d in self.documents if _sets(d, rule)]
            if setting:
                path = f"{under}.{member}" if under else member
                raise ProfileError(
                    f"{applier} does not apply {what}, and profile "
                    f"{', '.join(setting)} sets one ({path}): the profiles are "
                    f"refused rather than applied without it (STANDARD v1.2 "
                    f"§5.21.4)",
                    [],
                )

    def _checker(self) -> _core.Validator:
        """The validator given, or the packaged ontology's, loaded only when
        a profile needs it."""
        if self._given is None:
            self._given = _default_validator()
        return self._given

    def __bool__(self) -> bool:
        return bool(self.documents)

    def flags(
        self, capability: str, declared: Mapping[str, Any] | None = None
    ) -> EffectiveFlags:
        """The effective flags of a step or call of ``capability`` with its
        own ``declared`` flags (``risk``, ``mutation``,
        ``requires_checkpoint``, ``requires_approval``), under these
        profiles (§5.21.3).

        Raises:
            ValueError: the ontology has no such capability.
        """
        key = (capability, tuple(sorted((declared or {}).items())))
        hit = self._flags.get(key)
        if hit is None:
            got = self._checker().profile_flags(
                self.documents, capability, dict(declared or {})
            )
            hit = EffectiveFlags(
                risk=got["risk"],
                mutation=got["mutation"],
                requires_checkpoint=got["requires_checkpoint"],
                requires_approval=got["requires_approval"],
                person=got["person"],
            )
            self._flags[key] = hit
        return hit
