"""Reference arithmetic for the authority trust model.

STANDARD v1.2.0 §8.1 to §8.3 and ``schemas/authority_trust_model.yaml``
state how evidence is weighed and how conflicts are resolved. This module
computes those values and nothing else, with the standard library only:

- :func:`decay_factor`: the time decay of §8.1, a true half-life (``0.5`` at
  one half-life), not below ``decay_model.min_trust`` when that is set; an
  age below zero counts as zero
- :func:`static_weight`: the static weight of §8.3 for a source type, a
  sender trust class, or both (the lower of the two), with a domain
  profile's ``trust_weights`` overrides
- :func:`merge_trust_weights`: the overrides of several applied profiles,
  the lowest per key (§8.3)
- :func:`trust_score`: ``weight × confidence × decay`` (§8.1)
- :func:`resolve`: the conflict strategies of §8.2, with tie-breaking by the
  model's ``tie_breakers``
- :class:`TrustModel`: the values of ``authority_trust_model.yaml``, with the
  functions applied to them
- :func:`manual_override`: a manual override (§8.4), refused or recorded as
  the model's ``overrides`` say, before it takes effect

``tests/conformance/trust/*.json`` holds the normative vectors (§10.3).

The module reads no file. The caller passes the loaded trust model and,
where domain profiles apply, their ``trust_weights``; nothing in this
package chooses or loads a profile here (``grounded_agency.profiles`` checks
and merges them through the core).

Every case 1.1 left open is decided (§8.1): a score with no reported
confidence uses 1; an age below zero counts as zero; a ``min_trust`` above
0.5 floors the factor; evidence without a static weight has no score and is
refused; field authority is not a factor of the score but ranks sources in
§8.2 (``field_authority.fields``; ``field_authority.examples`` is
illustrative and not read).
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cmp_to_key
from typing import Any, Literal

__all__ = [
    "STRATEGIES",
    "TIE",
    "TIE_BREAKERS",
    "TRUST_CLASS_PREFIX",
    "Candidate",
    "OverrideRefused",
    "Resolution",
    "TrustModel",
    "decay_factor",
    "half_life_days",
    "manual_override",
    "merge_trust_weights",
    "resolve",
    "static_weight",
    "trust_score",
]

TRUST_CLASS_PREFIX = "trust_class:"
"""A domain profile's ``trust_weights`` key that begins with this prefix
overrides the weight of the trust class named after it (§8.3). Any other key
is a source key."""

# `decay_model.half_life` is an ISO 8601 duration of whole days; the
# canonical-schema validator accepts no other form.
_ISO_DAYS = re.compile(r"P([0-9]+)D")


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
    ``recency_factor``. A ``min_trust`` above ``0.5`` holds the factor at
    ``min_trust`` from the age at which the curve reaches it.

    Args:
        age: Time since the observation. An age below zero (evidence dated
            after the time the score is computed) counts as zero.
        half_life: The configured half-life, above zero, in the unit of
            ``age``.
        min_trust: ``decay_model.min_trust``, in [0.0, 1.0]. ``None``: the
            model sets no floor.

    Raises:
        ValueError: ``age`` is not a number or is NaN, ``half_life`` is not a
            finite number above zero, or ``min_trust`` is outside
            [0.0, 1.0]. A ``bool`` is not a number here.
    """
    if not _is_number(age) or math.isnan(age):
        raise ValueError(f"age must be a number, got {age!r}")
    age = max(age, 0)
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

    Any other ``trust_weights`` key replaces the weight of the source type
    it names, or gives a weight to a source type the model does not name
    (§8.3). A replacement may be higher or lower than the model's weight.
    With several profiles, merge their weights first
    (:func:`merge_trust_weights`).

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


def merge_trust_weights(*weights: Mapping[str, float] | None) -> dict[str, float]:
    """The ``trust_weights`` of several applied profiles as one mapping: the
    lowest weight any of them gives each key (§8.3). ``None`` stands for a
    profile without ``trust_weights``.

    Raises:
        ValueError: a weight is not a number in [0.0, 1.0].
    """
    merged: dict[str, float] = {}
    for mapping in weights:
        for key, value in (mapping or {}).items():
            weight = _unit(value, f"trust_weights[{key!r}]")
            merged[key] = min(merged.get(key, weight), weight)
    return merged


def trust_score(
    trust_weight: float, recency_factor: float, confidence: float = 1.0
) -> float:
    """``trust_weight * confidence * recency_factor``, in that order (§8.1),
    the score of ``conflict_resolution_function.formula`` in the trust
    model.

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
    field_authority: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    """``field_authority.fields``: for a field, the source types
    authoritative for it (§8.2). ``field_authority.examples`` is not read."""
    tie_breakers: tuple[str, ...] = ()
    """``conflict_resolution_function.tie_breakers``, in order (§8.2)."""
    overrides: Mapping[str, Any] = field(default_factory=dict)
    """``overrides``: what a manual override needs (§8.4)."""

    @classmethod
    def from_mapping(cls, model: Mapping[str, Any]) -> TrustModel:
        """Read a loaded ``authority_trust_model.yaml``.

        Field authorities come from ``field_authority.fields`` (a model
        without it has none) and tie-breakers from
        ``conflict_resolution_function.tie_breakers``.

        Raises:
            ValueError: ``decay_model.half_life`` is missing or malformed, a
                weight or ``min_trust`` is not a number in [0.0, 1.0], a
                ``fields`` entry is malformed, repeats a field or names an
                authority that is not a weighted source type, or a
                tie-breaker is not one of :data:`TIE_BREAKERS`.
        """
        decay: Mapping[str, Any] = model.get("decay_model") or {}
        sources = (model.get("source_ranking") or {}).get("weights") or {}
        classes = (model.get("trust_classes") or {}).get("weights") or {}
        # Not checked yet: half_life_days refuses what is not a string.
        half_life: Any = decay.get("half_life")
        min_trust = decay.get("min_trust")
        weighted = {str(name) for name in sources}
        authorities = _field_authorities(model.get("field_authority"), weighted)
        resolution = model.get("conflict_resolution_function") or {}
        breakers = resolution.get("tie_breakers") or []
        if not isinstance(breakers, list) or any(
            b not in TIE_BREAKERS for b in breakers
        ):
            raise ValueError(
                f"conflict_resolution_function.tie_breakers must list names of "
                f"{', '.join(TIE_BREAKERS)}; got {breakers!r}"
            )
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
            field_authority=authorities,
            tie_breakers=tuple(breakers),
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

    def resolve(
        self,
        candidates: Sequence[Candidate],
        *,
        field: str | None = None,
        strategy: str | None = None,
        profile_trust_weights: Mapping[str, float] | None = None,
        tie_breakers: Sequence[str] | None = None,
    ) -> Resolution:
        """:func:`resolve` with this model."""
        return resolve(
            self,
            candidates,
            field=field,
            strategy=strategy,
            profile_trust_weights=profile_trust_weights,
            tie_breakers=tie_breakers,
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


def _field_authorities(section: Any, weighted: set[str]) -> dict[str, tuple[str, ...]]:
    """``field_authority.fields`` as ``{field: authorities}``."""
    if section is None:
        return {}
    if not isinstance(section, Mapping):
        raise ValueError("field_authority must be a mapping")
    entries = section.get("fields")
    if entries is None:
        return {}
    if not isinstance(entries, list):
        raise ValueError("field_authority.fields must be a list")
    out: dict[str, tuple[str, ...]] = {}
    for i, entry in enumerate(entries):
        where = f"field_authority.fields[{i}]"
        if not isinstance(entry, Mapping) or not isinstance(entry.get("field"), str):
            raise ValueError(f"{where} must be a mapping with a string 'field'")
        name = entry["field"]
        if name in out:
            raise ValueError(f"{where}: the field {name!r} is listed twice")
        listed = entry.get("authorities")
        if (
            not isinstance(listed, list)
            or not listed
            or len(set(map(str, listed))) != len(listed)
        ):
            raise ValueError(
                f"{where}.authorities must be a non-empty list of distinct source types"
            )
        unknown = [a for a in listed if a not in weighted]
        if unknown:
            raise ValueError(
                f"{where}.authorities names {unknown!r}, which source_ranking.weights does not weigh"
            )
        out[name] = tuple(listed)
    return out


# ---------------------------------------------------------------------------
# §8.2: conflict resolution
# ---------------------------------------------------------------------------

STRATEGIES = (
    "highest_score",
    "prefer_authoritative_sources",
    "prefer_recent",
    "prefer_high_confidence",
    "merge_with_uncertainty",
    "escalate_to_human",
)
"""The strategies of §8.2; ``highest_score`` is the default."""

TIE_BREAKERS = (
    "prefer_authoritative_source",
    "prefer_high_confidence",
    "prefer_recent",
    "escalate_to_human",
)
"""The tie-breakers a model's ``tie_breakers`` may list (§8.2)."""

TIE = 1e-12
"""Two values within this of each other are equal (§8.2)."""


@dataclass(frozen=True, slots=True)
class Candidate:
    """One value for the conflicting field, with its evidence (§8.2)."""

    age_days: float
    """The evidence's age in days; below zero counts as zero."""
    source_type: str | None = None
    trust_class: str | None = None
    confidence: float | None = None
    """The confidence the source reports; ``None``: none (1 in the score)."""


@dataclass(frozen=True, slots=True)
class Resolution:
    """The result of a strategy (§8.2)."""

    outcome: Literal["chosen", "merged", "escalated"]
    winner: int | None = None
    """``chosen``: the index of the chosen candidate."""
    order: tuple[int, ...] = ()
    """``merged``: every candidate, highest score first."""
    tied: tuple[int, ...] = ()
    """``escalated``: the candidates left tied (every one for
    ``escalate_to_human``). A single candidate is ``chosen`` whatever the
    strategy."""
    scores: tuple[float, ...] = ()
    """Every candidate's trust score (§8.1), in the order given."""


def _best(indices: list[int], key: Sequence[float]) -> list[int]:
    """Those of ``indices`` whose ``key`` is within :data:`TIE` of the
    largest."""
    top = max(key[i] for i in indices)
    return [i for i in indices if top - key[i] <= TIE]


def resolve(
    model: TrustModel,
    candidates: Sequence[Candidate],
    *,
    field: str | None = None,
    strategy: str | None = None,
    profile_trust_weights: Mapping[str, float] | None = None,
    tie_breakers: Sequence[str] | None = None,
) -> Resolution:
    """Resolve a conflict between candidates for one field (§8.2).

    Args:
        model: The trust model.
        candidates: The values in conflict, with their evidence.
        field: The field in conflict, for the model's field authorities.
        strategy: One of :data:`STRATEGIES`; ``None`` is ``highest_score``.
        profile_trust_weights: The applied profiles' ``trust_weights``,
            merged (:func:`merge_trust_weights`).
        tie_breakers: Replaces the model's ``tie_breakers``.

    Raises:
        ValueError: there is no candidate; a candidate has no static weight
            (refused whatever the strategy: §8.1 gives it no score); or the
            strategy or a tie-breaker is unknown.
    """
    strategy = "highest_score" if strategy is None else strategy
    if strategy not in STRATEGIES:
        raise ValueError(
            f"unknown strategy {strategy!r}; one of {', '.join(STRATEGIES)}"
        )
    breakers = tuple(model.tie_breakers if tie_breakers is None else tie_breakers)
    unknown = [b for b in breakers if b not in TIE_BREAKERS]
    if unknown:
        raise ValueError(f"unknown tie-breakers {unknown!r}")
    if not candidates:
        raise ValueError("a conflict needs at least one candidate")
    weights = [
        model.static_weight(
            source_type=c.source_type,
            trust_class=c.trust_class,
            profile_trust_weights=profile_trust_weights,
        )
        for c in candidates
    ]
    confidence = [
        1.0 if c.confidence is None else _unit(c.confidence, "confidence")
        for c in candidates
    ]
    for c in candidates:
        if not _is_number(c.age_days) or math.isnan(c.age_days):
            raise ValueError(f"age_days must be a number, got {c.age_days!r}")
    ages = [max(float(c.age_days), 0.0) for c in candidates]
    scores = tuple(
        trust_score(w, model.decay_factor(a), k)
        for w, a, k in zip(weights, ages, confidence, strict=True)
    )
    authorities = model.field_authority.get(field, ()) if field is not None else ()
    authority = [
        c.source_type is not None and c.source_type in authorities for c in candidates
    ]
    if len(candidates) == 1:
        # One candidate is no conflict: it is chosen, whatever the strategy.
        return Resolution("chosen", winner=0, scores=scores)
    every = list(range(len(candidates)))
    if strategy == "escalate_to_human":
        return Resolution("escalated", tied=tuple(every), scores=scores)
    if strategy == "merge_with_uncertainty":

        def by_score(i: int, j: int) -> int:
            if abs(scores[i] - scores[j]) <= TIE:
                return i - j
            return -1 if scores[i] > scores[j] else 1

        return Resolution(
            "merged",
            order=tuple(sorted(every, key=cmp_to_key(by_score))),
            scores=scores,
        )
    competing = every
    if strategy == "highest_score":
        best = _best(competing, scores)
    elif strategy == "prefer_authoritative_sources":
        if any(authority):
            competing = [i for i in every if authority[i]]
        best = _best(competing, weights)
    elif strategy == "prefer_recent":
        best = _best(competing, [-a for a in ages])
    else:  # prefer_high_confidence
        best = _best(competing, confidence)
    for breaker in breakers:
        if len(best) == 1 or breaker == "escalate_to_human":
            break
        if breaker == "prefer_authoritative_source":
            if any(authority[i] for i in best):
                best = [i for i in best if authority[i]]
        elif breaker == "prefer_high_confidence":
            best = _best(best, confidence)
        else:  # prefer_recent
            best = _best(best, [-a for a in ages])
    if len(best) == 1:
        return Resolution("chosen", winner=best[0], scores=scores)
    return Resolution("escalated", tied=tuple(best), scores=scores)


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
