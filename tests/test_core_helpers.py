"""The pure functions and start options of ``grounded_agency._core`` that
the Standard 1.2 workstreams share: canonical JSON and approval digests,
the cited-version check (§11.6), durations (§5.10.1), destination policies
(§4.4.2), the catalog header at start (§11.5) and error reasons (§5.19.7)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
CONFORMANCE = ROOT / "tests" / "conformance"


@pytest.fixture(scope="module")
def validator() -> _core.Validator:
    return _core.Validator(ONTOLOGY, ROOT)


def test_spec_versions() -> None:
    assert _core.SPEC_VERSIONS == ("1.0", "1.1", "1.2")


DIGESTS = json.loads((CONFORMANCE / "approval" / "digests.json").read_text())


@pytest.mark.parametrize("vector", DIGESTS["vectors"], ids=lambda v: v["name"])
def test_canonical_json_and_approval_digest(vector: dict[str, Any]) -> None:
    text = _core.canonical_json(vector["shown"])
    assert text == vector["canonical"]
    assert _core.approval_digest(vector["shown"]) == vector["digest"]
    # Any other digest of a value is the SHA-256 of its canonical JSON.
    assert hashlib.sha256(text.encode()).hexdigest() == vector["digest"]


@pytest.mark.parametrize("value", [2**53 + 1, -(2**53) - 1, {"a": [2**60]}])
def test_canonical_json_refuses_inexact_numbers(value: Any) -> None:
    with pytest.raises(ValueError, match="2\\^53"):
        _core.canonical_json(value)
    with pytest.raises(ValueError, match="2\\^53"):
        _core.approval_digest(value)


def test_canonical_json_refuses_deep_values() -> None:
    deep: Any = 1
    for _ in range(120):
        deep = [deep]
    with pytest.raises(ValueError):
        _core.canonical_json(deep)


def cited(standard: Any, ontology: Any) -> list[tuple[str, str]]:
    return [
        (d["code"], d["location"]["field"])
        for d in _core.check_cited_versions(standard, ontology, "2.2.0")
    ]


def test_check_cited_versions() -> None:
    assert cited(None, None) == []
    assert cited("1.2.0", "2.2.0") == []
    assert cited("1.0", "2.9.1") == []
    assert cited("1.3", None) == [("V109", "standard")]
    assert cited(None, "3.0") == [("V109", "ontology")]
    assert cited("v1.2", None) == [("S303", "standard")]
    assert cited(1.2, None) == [("S303", "standard")]
    assert cited(None, "2") == [("S303", "ontology")]


@pytest.mark.parametrize(
    ("text", "ms"),
    [
        ("0s", 0),
        ("PT0S", 0),
        ("PT0.0005S", 1),
        ("1ms", 1),
        ("30s", 30_000),
        ("PT1H", 3_600_000),
        ("1d", 86_400_000),
    ],
)
def test_duration_ms(text: str, ms: int) -> None:
    assert _core.duration_ms(text) == ms


@pytest.mark.parametrize("text", ["", "a week", "1w", "P1Y", "-1s"])
def test_duration_ms_refuses(text: str) -> None:
    with pytest.raises(ValueError):
        _core.duration_ms(text)


MATCH = json.loads((CONFORMANCE / "destinations" / "match.json").read_text())


@pytest.mark.parametrize("case", MATCH["patterns"], ids=lambda c: repr(c["pattern"]))
def test_destination_pattern(case: dict[str, Any]) -> None:
    if case["valid"]:
        _core.check_destination_pattern(case["pattern"])
    else:
        with pytest.raises(ValueError):
            _core.check_destination_pattern(case["pattern"])


@pytest.mark.parametrize(
    "case", MATCH["matches"], ids=lambda c: f"{c['policies']}-{c['destination']!r}"
)
def test_destination_allowed(case: dict[str, Any]) -> None:
    assert (
        _core.destination_allowed(case["policies"], case["destination"])
        is case["allowed"]
    )


CATALOG = {
    "w": {
        "goal": "g",
        "risk": "low",
        "steps": [
            {
                "capability": "retrieve",
                "purpose": "p",
                "store_as": "r",
                "input_bindings": {"target": "x"},
            }
        ],
    }
}


def test_start_requires_the_header(validator: _core.Validator) -> None:
    with pytest.raises(TypeError, match="header"):
        _core.Run.start(validator, CATALOG, "w", run_id="r", now_ms=0)  # type: ignore[call-arg]
    assert _core.Run.start(validator, CATALOG, "w", header=None, run_id="r", now_ms=0)


def test_start_validates_with_the_header(validator: _core.Validator) -> None:
    with pytest.raises(ValueError) as refused:
        _core.Run.start(validator, CATALOG, "w", header="2.0", run_id="r", now_ms=0)
    assert [d["code"] for d in refused.value.args[1]] == ["V109"]
    run = _core.Run.start(validator, CATALOG, "w", header="1.1.0", run_id="r", now_ms=0)
    snap = run.snapshot()
    assert json.loads(snap["state"])["header"] == "1.1.0"
    restored = _core.Run.restore(validator, CATALOG, snap)
    assert restored.snapshot() == snap
    # A header that is not a version is refused, spec_version or not.
    with pytest.raises(ValueError, match="not a version"):
        _core.Run.start(validator, CATALOG, "w", header="one", run_id="r", now_ms=0)
    # Without a header, the state has none, as a 1.1 state had none.
    plain = _core.Run.start(validator, CATALOG, "w", header=None, run_id="r", now_ms=0)
    assert "header" not in json.loads(plain.snapshot()["state"])


def test_destination_policies_are_implemented(validator: _core.Validator) -> None:
    """Destination policies (STANDARD v1.2 §4.4.2) start a run, its state
    keeps them across a snapshot, and one with an invalid pattern is
    refused."""
    run = _core.Run.start(
        validator,
        CATALOG,
        "w",
        header=None,
        run_id="r",
        now_ms=0,
        destinations=[["ops"]],
    )
    snap = run.snapshot()
    assert json.loads(snap["state"])["destinations"] == [["ops"]]
    assert _core.Run.restore(validator, CATALOG, snap).snapshot() == snap
    with pytest.raises(ValueError, match="destination policy: policy 0, pattern 0"):
        _core.Run.start(
            validator,
            CATALOG,
            "w",
            header=None,
            run_id="r",
            now_ms=0,
            destinations=[["https://hooks.example.com:*"]],
        )


@pytest.mark.parametrize(
    ("option", "why"),
    [
        ({"catalogs": [{"x": {}}]}, "no manifest"),
        (
            {
                "catalogs": [
                    {"catalog": {"id": "a.b", "version": "1.0.0"}},
                    {"catalog": {"id": "a.b", "version": "2.0.0"}},
                ]
            },
            "two catalogs",
        ),
        ({"agents": [{"agent": "a"}]}, "no 'standard'"),
        (
            {
                "agents": [
                    {
                        "agent": "a",
                        "standard": "1.2",
                        "ontology": "3.0",
                        "capabilities": [],
                    }
                ]
            },
            "V109",
        ),
    ],
    ids=["set-without-manifest", "duplicate-id", "manifest-shape", "manifest-ontology"],
)
def test_start_refuses_a_refused_set_or_manifest(
    validator: _core.Validator, option: dict[str, Any], why: str
) -> None:
    """Catalog sets (STANDARD v1.2 §5.1.1) and agent manifests (§5.15.1)
    are implemented: one that cannot be used is refused, not ignored."""
    with pytest.raises(ValueError, match=why):
        _core.Run.start(
            validator, CATALOG, "w", header=None, run_id="r", now_ms=0, **option
        )
    with pytest.raises(ValueError, match=why):
        validator.validate(CATALOG, **option)


def test_grounding_policies_are_implemented(validator: _core.Validator) -> None:
    """Grounding policies (STANDARD v1.2 §5.20) start a run, and its state
    keeps them across a snapshot."""
    run = _core.Run.start(
        validator,
        CATALOG,
        "w",
        header=None,
        run_id="r",
        now_ms=0,
        grounding=[{"require": ["retrieve"], "kinds": ["file"]}],
    )
    snap = run.snapshot()
    assert json.loads(snap["state"])["grounding"] == [
        {"require": ["retrieve"], "kinds": ["file"], "attested": False}
    ]
    assert _core.Run.restore(validator, CATALOG, snap).snapshot() == snap


def test_record_mode_actions_is_implemented(validator: _core.Validator) -> None:
    """Record mode ``actions`` (STANDARD v1.2 §6.4) starts, and its state
    restores."""
    run = _core.Run.start(
        validator, CATALOG, "w", header=None, run_id="r", now_ms=0, records="actions"
    )
    restored = _core.Run.restore(validator, CATALOG, run.snapshot())
    assert restored.next() == run.next()


@pytest.mark.parametrize(
    "option",
    [
        {"records": "everything"},
        {"profiles": [{"domain": "d"}]},
        {
            "profiles": [
                {
                    "domain": "d",
                    "version": "1.0.0",
                    "checkpoint_policy": {"mutat": "always"},
                }
            ]
        },
        {"grounding": [{"require": ["retreive"]}]},
        {"grounding": [{"require": []}]},
        {"grounding": [{"require": ["retrieve"], "kinds": ["paper"]}]},
    ],
)
def test_start_refuses_malformed_options(
    validator: _core.Validator, option: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        _core.Run.start(
            validator, CATALOG, "w", header=None, run_id="r", now_ms=0, **option
        )


def test_empty_options_are_none(validator: _core.Validator) -> None:
    run = _core.Run.start(
        validator,
        CATALOG,
        "w",
        header=None,
        run_id="r",
        now_ms=0,
        records="approvals",
        profiles=[],
        grounding=[],
        destinations=[],
        catalogs=[],
        agents=[],
    )
    assert run.next()["kind"] == "InvokeCapability"
    assert _core.Run.restore(
        validator, CATALOG, run.snapshot(), catalogs=[], agents=None
    )


@pytest.mark.parametrize(
    ("reason", "kept"),
    [
        ("unsupported_capability", True),
        ("x-acme.audio", True),
        ("Unsupported", False),
        (5, False),
    ],
)
def test_error_reasons(validator: _core.Validator, reason: Any, kept: bool) -> None:
    run = _core.Run.start(validator, CATALOG, "w", header=None, run_id="r", now_ms=0)
    action = run.next()
    run.submit(
        action["id"],
        {"kind": "Error", "code": "R402", "message": "no", "reason": reason},
        0,
    )
    end = run.next()
    assert end["kind"] == "Failed"
    assert end["code"] == "R402"
    assert end.get("reason") == (reason if kept else None)
    (failed,) = [t for t in run.trace() if t["kind"] == "step_failed"]
    if kept:
        assert failed["detail"]["reason"] == reason
    else:
        assert failed["detail"]["reason_ignored"] == reason
