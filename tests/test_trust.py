"""The trust arithmetic of STANDARD v1.2.0 §8.1 to §8.3
(``grounded_agency/trust.py``) against the normative vectors in
``tests/conformance/trust/``, against ``schemas/authority_trust_model.yaml``,
and against the benchmark scenario
``benchmarks/scenarios/conflicting_sources.py``, which resolves its
conflicts with :func:`grounded_agency.trust.resolve`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from benchmarks.scenarios import conflicting_sources as benchmark
from grounded_agency import _core
from grounded_agency.trust import (
    TIE_BREAKERS,
    TRUST_CLASS_PREFIX,
    Candidate,
    TrustModel,
    decay_factor,
    half_life_days,
    merge_trust_weights,
    resolve,
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
RESOLVE = load("resolve.json")
FILES = {
    "decay.json": DECAY,
    "weight.json": WEIGHT,
    "score.json": SCORE,
    "resolve.json": RESOLVE,
}


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


def test_the_directory_holds_the_four_files() -> None:
    assert sorted(p.name for p in VECTORS.glob("*.json")) == sorted(FILES)


@pytest.mark.parametrize("name", sorted(FILES))
def test_a_vector_file_states_its_status_tolerance_and_fields(name: str) -> None:
    doc = FILES[name]
    assert doc["standard"] == "1.2.0"
    assert doc["status"] == "normative"
    assert 0 < doc["tolerance"] <= 1e-9
    names = [v["name"] for v in doc["vectors"]]
    assert len(set(names)) == len(names)
    for vector in doc["vectors"]:
        assert set(vector) <= set(doc["fields"]), vector["name"]
    # ASCII, so no tool that normalises or transcodes text can change it.
    assert (VECTORS / name).read_text(encoding="utf-8").isascii()
    # 1.2 decides every case 1.1 left open (§8.1): nothing is left out.
    assert "not_covered" not in doc


def test_an_error_vector_expects_no_value() -> None:
    """A vector that expects a refusal states no numeric result."""
    for doc, results in (
        (DECAY, {"decay_factor"}),
        (WEIGHT, {"weight"}),
        (SCORE, {"decay_factor", "weight", "score"}),
    ):
        for vector in doc["vectors"]:
            if vector.get("expect_error"):
                assert not results & set(vector), vector["name"]
            else:
                assert results <= set(vector), vector["name"]


@pytest.mark.parametrize("name", ["weight.json", "score.json", "resolve.json"])
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


def profile_weights(vector: dict[str, Any]) -> dict[str, float] | None:
    """A vector's ``profile_trust_weights``: one profile's, or a list of
    several profiles' merged (the lowest per key, §8.3)."""
    given = vector.get("profile_trust_weights")
    if isinstance(given, list):
        return merge_trust_weights(*given)
    return given


def vector_weight(vector: dict[str, Any], model: dict[str, Any]) -> float:
    return static_weight(
        model["source_ranking"]["weights"],
        model["trust_classes"]["weights"],
        source_type=vector.get("source_type"),
        trust_class=vector.get("trust_class"),
        profile_trust_weights=profile_weights(vector),
    )


@pytest.mark.parametrize("vector", cases(DECAY))
def test_decay_vector(vector: dict[str, Any]) -> None:
    if vector.get("expect_error"):
        with pytest.raises(ValueError):
            vector_decay(vector, vector["half_life"], vector.get("min_trust"))
        return
    got = vector_decay(vector, vector["half_life"], vector.get("min_trust"))
    assert got == within(DECAY, vector["decay_factor"])


@pytest.mark.parametrize("vector", cases(WEIGHT))
def test_weight_vector(vector: dict[str, Any]) -> None:
    if vector.get("expect_error"):
        with pytest.raises(ValueError):
            vector_weight(vector, WEIGHT["model"])
        return
    assert vector_weight(vector, WEIGHT["model"]) == within(WEIGHT, vector["weight"])


@pytest.mark.parametrize("vector", cases(SCORE))
def test_score_vector(vector: dict[str, Any]) -> None:
    settings = SCORE["model"]["decay_model"]
    if vector.get("expect_error"):
        with pytest.raises(ValueError):
            vector_weight(vector, SCORE["model"])
        return
    decay = vector_decay(vector, settings["half_life"], settings.get("min_trust"))
    weight = vector_weight(vector, SCORE["model"])
    assert decay == within(SCORE, vector["decay_factor"])
    assert weight == within(SCORE, vector["weight"])
    assert trust_score(weight, decay, vector.get("confidence", 1.0)) == within(
        SCORE, vector["score"]
    )


@pytest.mark.parametrize("vector", cases(SCORE))
def test_score_vector_through_the_model(vector: dict[str, Any]) -> None:
    """``TrustModel`` composes the three functions, with ages in days."""
    model = TrustModel.from_mapping(SCORE["model"])

    def score() -> float:
        return model.score(
            vector["age_hours"] / 24,
            source_type=vector.get("source_type"),
            trust_class=vector.get("trust_class"),
            confidence=vector.get("confidence", 1.0),
            profile_trust_weights=profile_weights(vector),
        )

    if vector.get("expect_error"):
        with pytest.raises(ValueError):
            score()
        return
    assert score() == within(SCORE, vector["score"])


@pytest.mark.parametrize("vector", cases(RESOLVE))
def test_resolve_vector(vector: dict[str, Any]) -> None:
    """§8.2: each strategy's result, ties and refusals."""
    model = TrustModel.from_mapping(RESOLVE["model"])
    candidates = [
        Candidate(
            age_days=c["age_hours"] / 24,
            source_type=c.get("source_type"),
            trust_class=c.get("trust_class"),
            confidence=c.get("confidence"),
        )
        for c in vector["candidates"]
    ]

    def run() -> Any:
        return resolve(
            model,
            candidates,
            field=vector.get("field"),
            strategy=vector["strategy"],
            profile_trust_weights=vector.get("profile_trust_weights"),
            tie_breakers=vector.get("tie_breakers"),
        )

    expect = vector["expect"]
    if expect.get("error"):
        with pytest.raises(ValueError):
            run()
        return
    got = run()
    assert got.outcome == expect["outcome"]
    assert got.winner == expect.get("winner")
    assert list(got.order) == expect.get("order", [])
    assert list(got.tied) == expect.get("tied", [])
    if "scores" in expect:
        assert list(got.scores) == [within(RESOLVE, x) for x in expect["scores"]]


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


def test_an_age_below_zero_counts_as_zero() -> None:
    """§8.1: a future-dated observation is never fresher than a present
    one; refusing it would make clock skew between sources an error."""
    assert decay_factor(-1, 240) == 1.0
    assert decay_factor(-1e-9, 240, 0.25) == 1.0
    assert decay_factor(-math.inf, 240) == 1.0


@pytest.mark.parametrize(
    ("age", "half_life", "min_trust"),
    [
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
    "text",
    [
        "P0D",
        "P00D",
        "10D",
        "P10",
        "P1W",
        "PT240H",
        "P1.5D",
        "P-1D",
        "",
        10,
        # Digits outside ASCII, which `\\d` and int() would read as 10
        "P\u0661\u0660D",
        "P\uff11\uff10D",
    ],
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
    assert benchmark._TRUST_MODEL == model


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


# ---------------------------------------------------------------------------
# §8.2: field authority, tie-breakers and the strategies
# ---------------------------------------------------------------------------


def test_the_model_reads_field_authority_fields_not_examples(
    schema: dict[str, Any],
) -> None:
    model = TrustModel.from_mapping(schema)
    fields = schema["field_authority"]["fields"]
    assert model.field_authority == {
        f["field"]: tuple(f["authorities"]) for f in fields
    }
    assert model.tie_breakers == tuple(
        schema["conflict_resolution_function"]["tie_breakers"]
    )
    # examples that differ from fields change nothing: they are illustrative.
    changed = {
        **schema,
        "field_authority": {
            "fields": [{"field": "serial_number", "authorities": ["human_note"]}],
            "examples": [
                {"field": "serial_number", "authorities": ["hardware_sensor"]}
            ],
        },
    }
    other = TrustModel.from_mapping(changed)
    assert other.field_authority == {"serial_number": ("human_note",)}
    pick = other.resolve(
        [
            Candidate(age_days=0, source_type="hardware_sensor"),
            Candidate(age_days=0, source_type="human_note"),
        ],
        field="serial_number",
        strategy="prefer_authoritative_sources",
    )
    assert pick.winner == 1
    # A model without fields has no field authorities.
    assert (
        TrustModel.from_mapping(
            {k: v for k, v in schema.items() if k != "field_authority"}
        ).field_authority
        == {}
    )


@pytest.mark.parametrize(
    "authority",
    [
        {"fields": [{"field": "x", "authorities": ["no_such_source"]}]},
        {"fields": [{"field": "x", "authorities": []}]},
        {"fields": [{"field": "x", "authorities": ["human_note", "human_note"]}]},
        {"fields": [{"authorities": ["human_note"]}]},
        {
            "fields": [
                {"field": "x", "authorities": ["human_note"]},
                {"field": "x", "authorities": ["primary_api"]},
            ]
        },
        {"fields": "serial_number"},
    ],
)
def test_from_mapping_refuses_malformed_field_authorities(
    schema: dict[str, Any], authority: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        TrustModel.from_mapping({**schema, "field_authority": authority})


def test_from_mapping_refuses_an_unknown_tie_breaker(schema: dict[str, Any]) -> None:
    bad = {
        **schema,
        "conflict_resolution_function": {"tie_breakers": ["prefer_loudest"]},
    }
    with pytest.raises(ValueError):
        TrustModel.from_mapping(bad)
    assert set(schema["conflict_resolution_function"]["tie_breakers"]) <= set(
        TIE_BREAKERS
    )


def test_resolve_refuses_unknown_names_and_empty_conflicts(model: TrustModel) -> None:
    one = [Candidate(age_days=0, source_type="human_note")]
    with pytest.raises(ValueError):
        resolve(model, one, strategy="prefer_loudest")
    with pytest.raises(ValueError):
        resolve(model, one, tie_breakers=["coin_toss"])
    with pytest.raises(ValueError):
        resolve(model, [])


def test_merge_trust_weights_keeps_the_lowest_per_key() -> None:
    assert merge_trust_weights({"a": 0.9, "b": 0.2}, None, {"a": 0.7}) == {
        "a": 0.7,
        "b": 0.2,
    }
    with pytest.raises(ValueError):
        merge_trust_weights({"a": 1.5})
