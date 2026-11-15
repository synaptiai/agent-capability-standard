"""The trust arithmetic of STANDARD v1.1.0 §8.1 to §8.3
(``grounded_agency/trust.py``) against the language-neutral vectors in
``tests/conformance/trust/``, against ``schemas/authority_trust_model.yaml``,
and against the one other place that computes the decay, the benchmark
scenario ``benchmarks/scenarios/conflicting_sources.py``.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import pytest

from benchmarks.scenarios import conflicting_sources as benchmark
from grounded_agency import _core
from grounded_agency.trust import (
    TRUST_CLASS_PREFIX,
    TrustModel,
    decay_factor,
    half_life_days,
    static_weight,
    trust_score,
)

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "tests" / "conformance" / "trust"
SCHEMA = ROOT / "schemas" / "authority_trust_model.yaml"
IDENTITY = ROOT / "schemas" / "agent_identity_schema.yaml"


def load(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((VECTORS / name).read_text(encoding="utf-8"))
    return doc


DECAY = load("decay.json")
WEIGHT = load("weight.json")
SCORE = load("score.json")
FILES = {"decay.json": DECAY, "weight.json": WEIGHT, "score.json": SCORE}


def cases(doc: dict[str, Any]) -> list[Any]:
    return [pytest.param(v, id=v["name"]) for v in doc["vectors"]]


def within(doc: dict[str, Any], expected: float) -> Any:
    """``expected``, to the tolerance the vector file states."""
    return pytest.approx(expected, abs=doc["tolerance"], rel=0)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    loaded: dict[str, Any] = _core.load_yaml(str(SCHEMA))
    return loaded


@pytest.fixture(scope="module")
def model(schema: dict[str, Any]) -> TrustModel:
    return TrustModel.from_mapping(schema)


# ---------------------------------------------------------------------------
# The vector files
# ---------------------------------------------------------------------------


def test_the_directory_holds_the_three_files() -> None:
    assert sorted(p.name for p in VECTORS.glob("*.json")) == sorted(FILES)


@pytest.mark.parametrize("name", sorted(FILES))
def test_a_vector_file_states_its_status_tolerance_and_fields(name: str) -> None:
    doc = FILES[name]
    assert doc["standard"] == "1.1.0"
    assert doc["status"] == "informative"
    assert 0 < doc["tolerance"] <= 1e-9
    names = [v["name"] for v in doc["vectors"]]
    assert len(set(names)) == len(names)
    for vector in doc["vectors"]:
        assert set(vector) <= set(doc["fields"]), vector["name"]
    # ASCII, so no tool that normalises or transcodes text can change it.
    assert (VECTORS / name).read_text(encoding="utf-8").isascii()
    # What the Standard leaves open is listed, not left unsaid.
    assert doc["not_covered"]
    assert all(isinstance(case, str) and case for case in doc["not_covered"])
    assert "`not_covered`" in doc["description"]


def test_the_decay_vectors_stay_out_of_what_the_standard_leaves_open() -> None:
    """No vector pins a reading of a case in ``not_covered``: a floor above
    0.5, where §8.1's two sentences conflict, or a negative age."""
    for vector in DECAY["vectors"]:
        assert vector.get("min_trust", 0.0) <= 0.5, vector["name"]
        assert vector["age_hours"] >= 0, vector["name"]
    assert SCORE["model"]["decay_model"]["min_trust"] <= 0.5
    for vector in SCORE["vectors"]:
        assert vector["age_hours"] >= 0, vector["name"]
        assert "confidence" in vector, vector["name"]


@pytest.mark.parametrize("name", ["weight.json", "score.json"])
def test_a_vector_file_reads_the_canonical_model(
    name: str, schema: dict[str, Any]
) -> None:
    """A change to the schema's weights or decay settings fails here until
    the vectors follow."""
    for section, values in FILES[name]["model"].items():
        assert values == {key: schema[section][key] for key in values}, section


def test_the_decay_vectors_include_the_canonical_settings(
    schema: dict[str, Any],
) -> None:
    decay = schema["decay_model"]
    assert any(
        v["half_life"] == decay["half_life"]
        and v.get("min_trust") == decay["min_trust"]
        for v in DECAY["vectors"]
    )


# ---------------------------------------------------------------------------
# The vectors
# ---------------------------------------------------------------------------


def vector_decay(vector: dict[str, Any], half_life: str, min_trust: Any) -> float:
    return decay_factor(vector["age_hours"], half_life_days(half_life) * 24, min_trust)


def vector_weight(vector: dict[str, Any], model: dict[str, Any]) -> float:
    return static_weight(
        model["source_ranking"]["weights"],
        model["trust_classes"]["weights"],
        source_type=vector.get("source_type"),
        trust_class=vector.get("trust_class"),
        profile_trust_weights=vector.get("profile_trust_weights"),
    )


@pytest.mark.parametrize("vector", cases(DECAY))
def test_decay_vector(vector: dict[str, Any]) -> None:
    got = vector_decay(vector, vector["half_life"], vector.get("min_trust"))
    assert got == within(DECAY, vector["decay_factor"])


@pytest.mark.parametrize("vector", cases(WEIGHT))
def test_weight_vector(vector: dict[str, Any]) -> None:
    assert vector_weight(vector, WEIGHT["model"]) == within(WEIGHT, vector["weight"])


@pytest.mark.parametrize("vector", cases(SCORE))
def test_score_vector(vector: dict[str, Any]) -> None:
    settings = SCORE["model"]["decay_model"]
    decay = vector_decay(vector, settings["half_life"], settings.get("min_trust"))
    weight = vector_weight(vector, SCORE["model"])
    assert decay == within(SCORE, vector["decay_factor"])
    assert weight == within(SCORE, vector["weight"])
    assert trust_score(weight, decay, vector["confidence"]) == within(
        SCORE, vector["score"]
    )


@pytest.mark.parametrize("vector", cases(SCORE))
def test_score_vector_through_the_model(vector: dict[str, Any]) -> None:
    """``TrustModel`` composes the three functions, with ages in days."""
    model = TrustModel.from_mapping(SCORE["model"])
    got = model.score(
        vector["age_hours"] / 24,
        source_type=vector.get("source_type"),
        trust_class=vector.get("trust_class"),
        confidence=vector["confidence"],
        profile_trust_weights=vector.get("profile_trust_weights"),
    )
    assert got == within(SCORE, vector["score"])


# ---------------------------------------------------------------------------
# §8.1: the decay factor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("half_life", [1, 24, 240, 0.1, 3.7, 1e-9, 1e12])
def test_the_factor_at_one_half_life_is_exactly_a_half(half_life: float) -> None:
    assert decay_factor(half_life, half_life) == 0.5
    assert decay_factor(0, half_life) == 1.0
    assert decay_factor(2 * half_life, half_life) == 0.25


def test_min_trust_floors_the_factor_and_nothing_else() -> None:
    assert decay_factor(1000, 10, 0.25) == 0.25
    assert decay_factor(1000, 10) == 0.5**100
    assert decay_factor(math.inf, 10) == 0.0
    assert decay_factor(math.inf, 10, 0.25) == 0.25
    # Above the floor, min_trust changes nothing.
    assert decay_factor(5, 10, 0.25) == decay_factor(5, 10)
    # A floor of zero is no floor.
    assert decay_factor(1000, 10, 0.0) == decay_factor(1000, 10)


def test_the_factor_never_rises_with_age() -> None:
    ages = [0, 0.5, 1, 10, 100, 240, 480, 481, 10_000]
    factors = [decay_factor(age, 240, 0.25) for age in ages]
    assert factors == sorted(factors, reverse=True)
    assert all(0.25 <= f <= 1.0 for f in factors)


@pytest.mark.parametrize(
    ("age", "half_life", "min_trust"),
    [
        (-1, 240, None),
        (-1e-9, 240, 0.25),
        (math.nan, 240, None),
        (1, 0, None),
        (1, -240, None),
        (1, math.inf, None),
        (1, math.nan, None),
        (1, 240, -0.1),
        (1, 240, 1.5),
        (1, 240, math.nan),
        (1, 240, True),
        ("1", 240, None),
        (True, 240, None),
        (None, 240, None),
        (1, "240", None),
        (1, True, None),
    ],
)
def test_decay_refuses_what_the_standard_does_not_define(
    age: float, half_life: float, min_trust: Any
) -> None:
    with pytest.raises(ValueError):
        decay_factor(age, half_life, min_trust)


@pytest.mark.parametrize(("text", "days"), [("P10D", 10), ("P1D", 1), ("P365D", 365)])
def test_half_life_days(text: str, days: int) -> None:
    assert half_life_days(text) == days


@pytest.mark.parametrize(
    "text", ["P0D", "P00D", "10D", "P10", "P1W", "PT240H", "P1.5D", "P-1D", "", 10]
)
def test_half_life_days_refuses_other_forms(text: Any) -> None:
    with pytest.raises(ValueError):
        half_life_days(text)


# ---------------------------------------------------------------------------
# §8.3: the static weight
# ---------------------------------------------------------------------------


def test_the_model_reads_the_canonical_schema(
    model: TrustModel, schema: dict[str, Any]
) -> None:
    assert model.source_weights == schema["source_ranking"]["weights"]
    assert model.class_weights == schema["trust_classes"]["weights"]
    assert f"P{model.half_life_days}D" == schema["decay_model"]["half_life"]
    assert model.min_trust == schema["decay_model"]["min_trust"]


def test_the_trust_classes_are_those_of_agent_identity(model: TrustModel) -> None:
    identity = _core.load_yaml(str(IDENTITY))
    classes = identity["agent_identity"]["properties"]["trust_class"]["enum"]
    assert set(model.class_weights) == set(classes)


def test_with_both_the_lower_weight_applies_for_every_pair(model: TrustModel) -> None:
    for source, source_weight in model.source_weights.items():
        assert model.static_weight(source_type=source) == source_weight
        for trust_class, class_weight in model.class_weights.items():
            assert model.static_weight(trust_class=trust_class) == class_weight
            both = model.static_weight(source_type=source, trust_class=trust_class)
            assert both == min(source_weight, class_weight)


def test_a_profile_override_applies_only_to_its_own_kind(model: TrustModel) -> None:
    name = "system_of_record"
    assert name in model.source_weights and name in model.class_weights
    source_key = {name: 0.1}
    class_key = {TRUST_CLASS_PREFIX + name: 0.1}
    assert (
        model.static_weight(source_type=name, profile_trust_weights=source_key) == 0.1
    )
    assert (
        model.static_weight(trust_class=name, profile_trust_weights=source_key)
        == (model.class_weights[name])
    )
    assert model.static_weight(trust_class=name, profile_trust_weights=class_key) == 0.1
    assert (
        model.static_weight(source_type=name, profile_trust_weights=class_key)
        == (model.source_weights[name])
    )


def test_every_shipped_profile_weighs_its_own_sources(model: TrustModel) -> None:
    profiles = sorted((ROOT / "schemas" / "profiles").glob("*.yaml"))
    seen = 0
    for path in profiles:
        profile = _core.load_yaml(str(path))
        weights = profile.get("trust_weights")
        if not isinstance(weights, dict):
            continue  # profile_schema.yaml
        for key, weight in weights.items():
            if key.startswith(TRUST_CLASS_PREFIX):
                trust_class = key.removeprefix(TRUST_CLASS_PREFIX)
                got = model.static_weight(
                    trust_class=trust_class, profile_trust_weights=weights
                )
            else:
                got = model.static_weight(
                    source_type=key, profile_trust_weights=weights
                )
            assert got == weight, (path.name, key)
            seen += 1
    assert seen > 0


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"source_type": "no_such_source"},
        {"trust_class": "no_such_class"},
        {"source_type": "primary_api", "trust_class": "no_such_class"},
        {"source_type": "no_such_source", "trust_class": "owner"},
        # A class key is not a source type, even when the profile holds it.
        {
            "source_type": "trust_class:owner",
            "profile_trust_weights": {"trust_class:owner": 0.5},
        },
        # A profile key for a class the model does not have adds no class.
        {
            "trust_class": "auditor",
            "profile_trust_weights": {"trust_class:auditor": 0.5},
        },
        {"source_type": "primary_api", "profile_trust_weights": {"primary_api": 1.5}},
        {"source_type": "primary_api", "profile_trust_weights": {"primary_api": True}},
        {"trust_class": "owner", "profile_trust_weights": {"trust_class:owner": -0.1}},
    ],
)
def test_weight_refuses_what_the_standard_does_not_define(
    model: TrustModel, arguments: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        model.static_weight(**arguments)


# ---------------------------------------------------------------------------
# The score, and the model
# ---------------------------------------------------------------------------


def test_the_score_is_the_product_the_schema_names(schema: dict[str, Any]) -> None:
    formula = schema["conflict_resolution_function"]["formula"]
    assert formula == "score = trust_weight(source) * confidence * recency_factor"
    assert trust_score(0.8, 0.5, 0.5) == 0.8 * 0.5 * 0.5
    # Without a confidence the factor is left out.
    assert trust_score(0.8, 0.5) == 0.8 * 0.5


@pytest.mark.parametrize(
    "arguments", [(1.5, 0.5, 0.5), (0.5, 1.5, 0.5), (0.5, 0.5, 1.5), (0.5, 0.5, -0.1)]
)
def test_the_score_refuses_factors_outside_the_unit_interval(
    arguments: tuple[float, float, float],
) -> None:
    with pytest.raises(ValueError):
        trust_score(*arguments)


def test_from_mapping_needs_a_half_life_and_unit_weights(
    schema: dict[str, Any],
) -> None:
    def changed(section: str, **values: Any) -> dict[str, Any]:
        return {**schema, section: {**schema[section], **values}}

    without_floor = {
        **schema,
        "decay_model": {"half_life": schema["decay_model"]["half_life"]},
    }
    assert TrustModel.from_mapping(without_floor).min_trust is None
    # A model from before trust classes has none.
    older = {k: v for k, v in schema.items() if k != "trust_classes"}
    assert TrustModel.from_mapping(older).class_weights == {}
    for bad in (
        {k: v for k, v in schema.items() if k != "decay_model"},
        changed("decay_model", half_life="P0D"),
        changed("decay_model", half_life="two weeks"),
        changed("decay_model", min_trust=25),
        changed("source_ranking", weights={"primary_api": 1.2}),
        changed("trust_classes", weights={"owner": "high"}),
    ):
        with pytest.raises(ValueError):
            TrustModel.from_mapping(bad)


# ---------------------------------------------------------------------------
# The benchmark scenario computes the same values
# ---------------------------------------------------------------------------


def test_the_benchmark_reads_the_same_model(model: TrustModel) -> None:
    assert benchmark._TRUST_WEIGHTS == model.source_weights
    assert benchmark._TRUST_HALF_LIFE_HOURS == model.half_life_days * 24
    assert benchmark._TRUST_MIN == model.min_trust


def test_the_decay_is_the_benchmark_scenarios() -> None:
    """Same arithmetic, so the same value to the last bit, also where the
    Standard's sentences pull apart: a ``min_trust`` above 0.5 holds the
    factor above 0.5 at one half-life."""
    rng = random.Random(8)
    ages = [0.0, 0.1, 1.0, 240.0, 480.0, 5000.0]
    ages += [rng.uniform(0, 2000) for _ in range(200)]
    for half_life in (24.0, 240.0, 717.5):
        for min_trust in (0.0, 0.25, 0.6, 1.0):
            for age in ages:
                assert decay_factor(age, half_life, min_trust) == (
                    benchmark._recency_weight(age, half_life, min_trust)
                )
    assert decay_factor(240, 240, 0.6) == 0.6


def test_the_score_is_the_benchmark_scenarios(model: TrustModel) -> None:
    """The scenario scores a source as weight times recency, with no
    confidence: the reference's default confidence of 1.0."""
    scenario = benchmark.ConflictingSourcesScenario(seed=42, num_cases=50)
    scenario.setup()
    results = scenario.run_ga()["results"]
    assert len(results) == len(scenario.test_cases) == 50
    for case, result in zip(scenario.test_cases, results, strict=True):
        for key in ("source1", "source2"):
            source = case[key]
            got = model.score(source["hours_ago"] / 24, source_type=source["type"])
            assert got == pytest.approx(result[f"score_{key}"], rel=1e-12, abs=0)
