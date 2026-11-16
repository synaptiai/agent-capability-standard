"""Reference arithmetic for the authority trust model.

STANDARD v1.2.0 §8.1 to §8.3 and ``schemas/authority_trust_model.yaml``
state how evidence is weighed. This module computes those values and nothing
else, with the standard library only:

- :func:`decay_factor`: the time decay of §8.1, a true half-life (``0.5`` at
  one half-life), not below ``decay_model.min_trust`` when that is set
- :func:`static_weight`: the static weight of §8.3 for a source type, a
  sender trust class, or both (the lower of the two), with a domain
  profile's ``trust_weights`` overrides
- :func:`trust_score`: the product that the schema's
  ``conflict_resolution_function.formula`` names
- :class:`TrustModel`: the values of ``authority_trust_model.yaml``, with the
  three functions applied to them
- :func:`manual_override`: a manual override (§8.4), refused or recorded as
  the model's ``overrides`` say, before it takes effect

``tests/conformance/trust/*.json`` holds language-neutral vectors for the
three functions.

The module reads no file. The caller passes the loaded trust model and,
where a domain profile applies, that profile's ``trust_weights``; nothing in
this package chooses or loads a profile.

What the Standard leaves open is refused, not guessed: an age below zero, a
source type or trust class with no weight, evidence with neither. Field
authority (§8.1) and the strategies of §8.2 have no stated arithmetic and
are not implemented here.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "TRUST_CLASS_PREFIX",
    "OverrideRefused",
    "TrustModel",
    "decay_factor",
    "half_life_days",
    "manual_override",
    "static_weight",
    "trust_score",
]

TRUST_CLASS_PREFIX = "trust_class:"
"""A domain profile's ``trust_weights`` key that begins with this prefix
overrides the weight of the trust class named after it (§8.3). Any other key
is a source key."""

# `decay_model.half_life` is an ISO 8601 duration of whole days; the
# canonical-schema validator accepts no other form.
_ISO_DAYS = re.compile(r"P(\d+)D")


def _is_number(value: Any) -> bool:
    """Whether ``value`` is an ``int`` or a ``float``, not a ``bool``."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _unit(value: Any, what: str) -> float:
    """``value`` as a number in [0.0, 1.0]. A ``bool`` is not a weight."""
    if not _is_number(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{what} must be a number in [0.0, 1.0], got {value!r}")
    return float(value)


def half_life_days(half_life: str) -> int:
    """``decay_model.half_life`` as a number of days.

    The schema writes the half-life as ``P<n>D`` with ``n`` at least one,
    e.g. ``P10D``.

    Raises:
        ValueError: ``half_life`` has another form, or is zero days.
    """
    match = _ISO_DAYS.fullmatch(half_life) if isinstance(half_life, str) else None
    if match is None:
        raise ValueError(
            f"half_life must be an ISO 8601 duration of whole days (P<n>D), "
            f"got {half_life!r}"
        )
    days = int(match.group(1))
    if days < 1:
        raise ValueError(f"half_life must be at least one day, got {half_life!r}")
    return days


def decay_factor(age: float, half_life: float, min_trust: float | None = None) -> float:
    """The decay factor of an observation of the given age (§8.1).

    ``0.5 ** (age / half_life)``: ``1.0`` at age zero and exactly ``0.5`` at
    one half-life. ``min_trust``, when given, is a floor on this factor, so
    age alone never takes it to zero: the result is
    ``max(0.5 ** (age / half_life), min_trust)``, the schema's
    ``recency_factor``. A ``min_trust`` above ``0.5`` therefore holds the
    factor at ``min_trust`` at one half-life.

    Args:
        age: Time since the observation, zero or more.
        half_life: The configured half-life, above zero, in the unit of
            ``age``.
        min_trust: ``decay_model.min_trust``, in [0.0, 1.0]. ``None``: the
            model sets no floor.

    Raises:
        ValueError: ``age`` is not a number, is NaN or is below zero,
            ``half_life`` is not a finite number above zero, or
            ``min_trust`` is outside [0.0, 1.0]. A ``bool`` is not a number
            here. The Standard does not say what an observation dated in the
            future decays to.
    """
    if not _is_number(age) or math.isnan(age) or age < 0:
        raise ValueError(f"age must be zero or more, got {age!r}")
    if not (_is_number(half_life) and math.isfinite(half_life) and half_life > 0):
        raise ValueError(f"half_life must be above zero, got {half_life!r}")
    factor: float = 0.5 ** (age / half_life)
    if min_trust is None:
        return factor
    return max(factor, _unit(min_trust, "min_trust"))


def static_weight(
    source_weights: Mapping[str, float],
    class_weights: Mapping[str, float],
    *,
    source_type: str | None = None,
    trust_class: str | None = None,
    profile_trust_weights: Mapping[str, float] | None = None,
) -> float:
    """The static weight of a piece of evidence (§8.1 source ranking, §8.3).

    - Evidence from an item whose sender's identity has a trust class weighs
      the class weight.
    - Evidence with a source type weighs the source weight.
    - With both, the lower of the two applies, so a trusted channel cannot
      lift an untrusted sender.

    A domain profile overrides a class weight with the ``trust_weights`` key
    ``trust_class:<class>``, kept apart from source keys of the same name
    (§8.3): the key ``system_of_record`` is the source,
    ``trust_class:system_of_record`` the class.

    §8.3 states the class override only. Any other ``trust_weights`` key is
    taken here as the weight of the source it names: it replaces the model's
    weight for that source, and it weighs a source the model does not name.
    That reading rests on the comment on ``trust_classes`` in
    ``authority_trust_model.yaml`` (a profile's ``trust_weights`` "may
    override any class, as it may any source") and on the description of
    ``trust_weights`` in ``schemas/profiles/profile_schema.yaml``.

    Args:
        source_weights: ``source_ranking.weights`` of the trust model.
        class_weights: ``trust_classes.weights`` of the trust model. Its
            keys are the trust classes.
        source_type: The evidence's source type, if it has one.
        trust_class: The trust class of the sender's identity, if it has one.
        profile_trust_weights: A domain profile's ``trust_weights``.

    Raises:
        ValueError: neither a source type nor a trust class is given, the
            trust class is not one of the model's, the source type has no
            weight in the profile or the model, or a weight is not a number
            in [0.0, 1.0].
    """
    profile = profile_trust_weights or {}
    weights: list[float] = []
    if trust_class is not None:
        if trust_class not in class_weights:
            raise ValueError(f"unknown trust class {trust_class!r}")
        key = TRUST_CLASS_PREFIX + trust_class
        if key in profile:
            weights.append(_unit(profile[key], f"trust_weights[{key!r}]"))
        else:
            weights.append(
                _unit(class_weights[trust_class], f"the weight of {trust_class!r}")
            )
    if source_type is not None:
        if source_type.startswith(TRUST_CLASS_PREFIX):
            raise ValueError(f"{source_type!r} is a trust class key, not a source type")
        if source_type in profile:
            weights.append(
                _unit(profile[source_type], f"trust_weights[{source_type!r}]")
            )
        elif source_type in source_weights:
            weights.append(
                _unit(source_weights[source_type], f"the weight of {source_type!r}")
            )
        else:
            raise ValueError(f"no weight for source type {source_type!r}")
    if not weights:
        raise ValueError("evidence needs a source type or a trust class to be weighed")
    return min(weights)


def trust_score(
    trust_weight: float, recency_factor: float, confidence: float = 1.0
) -> float:
    """``trust_weight * confidence * recency_factor``, the score of
    ``conflict_resolution_function.formula`` in the trust model.

    Args:
        trust_weight: The static weight (:func:`static_weight`).
        recency_factor: The decay factor (:func:`decay_factor`).
        confidence: The confidence the source reports, in [0.0, 1.0]. The
            default, ``1.0``, leaves the factor out.

    Raises:
        ValueError: an argument is not a number in [0.0, 1.0].
    """
    return (
        _unit(trust_weight, "trust_weight")
        * _unit(confidence, "confidence")
        * _unit(recency_factor, "recency_factor")
    )


@dataclass(frozen=True, slots=True)
class TrustModel:
    """The values of ``authority_trust_model.yaml`` that the trust score
    reads."""

    source_weights: Mapping[str, float]
    """``source_ranking.weights``: the static weight of each source type."""
    class_weights: Mapping[str, float]
    """``trust_classes.weights``: the default weight of each trust class."""
    half_life_days: int
    """``decay_model.half_life``, in days."""
    min_trust: float | None = None
    """``decay_model.min_trust``: the floor on the decay factor, if set."""
    overrides: Mapping[str, Any] = field(default_factory=dict)
    """``overrides``: what a manual override needs (§8.4)."""

    @classmethod
    def from_mapping(cls, model: Mapping[str, Any]) -> TrustModel:
        """Read a loaded ``authority_trust_model.yaml``.

        Raises:
            ValueError: ``decay_model.half_life`` is missing or malformed,
                or a weight or ``min_trust`` is not a number in [0.0, 1.0].
        """
        decay: Mapping[str, Any] = model.get("decay_model") or {}
        sources = (model.get("source_ranking") or {}).get("weights") or {}
        classes = (model.get("trust_classes") or {}).get("weights") or {}
        # Not checked yet: half_life_days refuses what is not a string.
        half_life: Any = decay.get("half_life")
        min_trust = decay.get("min_trust")
        return cls(
            source_weights={
                str(name): _unit(weight, f"source_ranking.weights[{name!r}]")
                for name, weight in sources.items()
            },
            class_weights={
                str(name): _unit(weight, f"trust_classes.weights[{name!r}]")
                for name, weight in classes.items()
            },
            half_life_days=half_life_days(half_life),
            min_trust=(
                None if min_trust is None else _unit(min_trust, "decay_model.min_trust")
            ),
            overrides=dict(model.get("overrides") or {}),
        )

    def decay_factor(self, age_days: float) -> float:
        """:func:`decay_factor` with the model's half-life and floor, for an
        age in days."""
        return decay_factor(age_days, self.half_life_days, self.min_trust)

    def static_weight(
        self,
        *,
        source_type: str | None = None,
        trust_class: str | None = None,
        profile_trust_weights: Mapping[str, float] | None = None,
    ) -> float:
        """:func:`static_weight` with the model's weights."""
        return static_weight(
            self.source_weights,
            self.class_weights,
            source_type=source_type,
            trust_class=trust_class,
            profile_trust_weights=profile_trust_weights,
        )

    def score(
        self,
        age_days: float,
        *,
        source_type: str | None = None,
        trust_class: str | None = None,
        confidence: float = 1.0,
        profile_trust_weights: Mapping[str, float] | None = None,
    ) -> float:
        """:func:`trust_score` of evidence of the given age, source type and
        trust class."""
        return trust_score(
            self.static_weight(
                source_type=source_type,
                trust_class=trust_class,
                profile_trust_weights=profile_trust_weights,
            ),
            self.decay_factor(age_days),
            confidence,
        )

    def manual_override(
        self,
        *,
        target: str,
        previous: Any,
        value: Any,
        actor_identity: Mapping[str, Any] | None,
        anchors: Sequence[Mapping[str, Any]],
        record: Callable[[dict[str, Any]], None],
        now: str | None = None,
    ) -> dict[str, Any]:
        """:func:`manual_override` under the model's ``overrides``."""
        return manual_override(
            {"overrides": self.overrides},
            target=target,
            previous=previous,
            value=value,
            actor_identity=actor_identity,
            anchors=anchors,
            record=record,
            now=now,
        )


class OverrideRefused(ValueError):
    """A manual override the trust model's ``overrides`` do not allow
    (STANDARD v1.2 §8.4): overrides are off, or it cites no anchor where one
    is required."""


def manual_override(
    model: Mapping[str, Any],
    *,
    target: str,
    previous: Any,
    value: Any,
    actor_identity: Mapping[str, Any] | None,
    anchors: Sequence[Mapping[str, Any]],
    record: Callable[[dict[str, Any]], None],
    now: str | None = None,
) -> dict[str, Any]:
    """A manual override of ``target`` (a trust score, or which value won a
    conflict), from ``previous`` to ``value``, by ``actor_identity``
    (STANDARD v1.2 §8.4), under the loaded trust model's ``overrides``.

    It is refused (:class:`OverrideRefused`) when ``allow_manual_override``
    is false, or ``requires_anchors`` is true and ``anchors`` is empty. With
    ``audit_required`` (the default), its action record is handed to
    ``record`` before this returns, and an exception ``record`` raises
    propagates: the override then does not take effect. Apply the value only
    after this returns. Returns the action record.
    """
    rules: Mapping[str, Any] = model.get("overrides") or {}
    if rules.get("allow_manual_override") is False:
        raise OverrideRefused("the trust model allows no manual override (§8.4)")
    if rules.get("requires_anchors", True) and not anchors:
        raise OverrideRefused(
            "a manual override cites at least one evidence anchor for the value "
            "it sets (§8.4)"
        )
    timestamp = now or datetime.now(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    rec: dict[str, Any] = {
        "action_id": uuid.uuid4().hex,
        "timestamp": timestamp,
        "actor": (actor_identity or {}).get("kind", "agent"),
        "intent": f"manual trust override of {target}",
        "status": "executed",
        "details": {"target": target, "previous": previous, "value": value},
        "anchors": [dict(a) for a in anchors],
    }
    if actor_identity is not None:
        rec["actor_identity"] = dict(actor_identity)
    if rules.get("audit_required", True):
        record(rec)
    return rec
