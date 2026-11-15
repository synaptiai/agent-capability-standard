"""The trigger vectors (STANDARD v1.2 §5.10.2, normative under §10.3) against
the core's fire-time function and the host-side helpers of
``grounded_agency.workflows.triggers``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core
from grounded_agency.workflows.triggers import (
    EventGate,
    OverlapGate,
    next_fire,
    trigger_attendance,
)

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "tests" / "conformance" / "triggers"
GENERATOR = ROOT / "scripts" / "gen_trigger_vectors.py"


def _cases(name: str) -> dict[str, Any]:
    data = json.loads((VECTORS / name).read_text(encoding="utf-8"))
    assert data["standard"] == "1.2.0"
    assert data["status"] == "normative"
    cases: dict[str, Any] = data["cases"]
    assert cases
    return cases


FIRE = _cases("fire_times.json")
OVERLAP = _cases("overlap.json")
ATTENDANCE = _cases("attendance.json")
EVENTS = _cases("events.json")


@pytest.mark.parametrize("name", sorted(FIRE))
def test_fire_times(name: str) -> None:
    case = FIRE[name]
    after = case["after_ms"]
    got = []
    for _ in range(max(len(case["next_ms"]), 1)):
        t = _core.next_fire(case["schedule"], after)
        if t is None:
            break
        got.append(t)
        after = t
    release = json.loads((VECTORS / "fire_times.json").read_text())["tzdata"]
    assert got == case["next_ms"], (
        f"{name}: computed with tzdata {release}; the core's bundled release must "
        "agree on these dates (§10.3)"
    )
    # The module's next_fire is the core's.
    assert next_fire(case["schedule"], case["after_ms"]) == (got[0] if got else None)


@pytest.mark.parametrize("name", sorted(OVERLAP))
def test_overlap(name: str) -> None:
    case = OVERLAP[name]
    gate = OverlapGate(case["overlap"])
    actions = {
        "fire": gate.fire,
        "missed": gate.missed,
        "end": gate.ended,
        "resume": gate.resumed,
    }
    assert [actions[e]() for e in case["events"]] == case["expect"]


@pytest.mark.parametrize("name", sorted(ATTENDANCE))
def test_attendance(name: str) -> None:
    case = ATTENDANCE[name]
    assert trigger_attendance(case["trigger"], case.get("invoker")) == case["expect"]


@pytest.mark.parametrize("name", sorted(EVENTS))
def test_events(name: str) -> None:
    case = EVENTS[name]
    gate = EventGate(case["trigger"])
    assert [gate.offer(e) for e in case["events"]] == case["expect"]


def test_event_gate_policy_refuses() -> None:
    """An event the host's sender policy refuses is refused, and its
    event_id is not consumed."""
    case = EVENTS["type_matches"]
    event = case["events"][0]
    refusing = EventGate(case["trigger"], accept=lambda e: False)
    assert refusing.offer(event) == "refused"
    assert event["event_id"] not in refusing.seen
    admitting = EventGate(case["trigger"], accept=lambda e: True, seen=refusing.seen)
    assert admitting.offer(event) == "start"


def test_event_gate_persistent_seen() -> None:
    """A store of seen event_ids shared by two gates (a host's, kept across a
    restart): the second sees the duplicate."""
    case = EVENTS["type_matches"]
    seen: set[str] = set()
    assert EventGate(case["trigger"], seen=seen).offer(case["events"][0]) == "start"
    assert EventGate(case["trigger"], seen=seen).offer(case["events"][0]) == "duplicate"


def test_an_event_without_an_event_id_does_not_match() -> None:
    trigger = {"event_type": "e", "delivers_to": "ev"}
    assert EventGate(trigger).offer({"event_type": "e"}) == "no_match"


def test_bad_values_are_refused() -> None:
    with pytest.raises(ValueError):
        OverlapGate("sometimes")
    with pytest.raises(ValueError):
        trigger_attendance({"kind": "manual", "attendance": "maybe"})
    with pytest.raises(ValueError):
        trigger_attendance({"kind": "cron"})
    with pytest.raises(ValueError):
        OverlapGate().ended()
    with pytest.raises(ValueError):
        _core.next_fire({"every": "0s"}, 0)
    with pytest.raises(ValueError):
        _core.next_fire({"cron": "0 0 * * *", "timezone": "Mars/Base"}, 0)


def test_the_generator_is_current() -> None:
    done = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_generator_ignores_another_tzdata_name(tmp_path: Path) -> None:
    """--check fails on a value that differs, but not on a different tzdata
    release name alone (§10.3: any release that agrees on the dates)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_trigger_vectors", GENERATOR)
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    wanted = gen.fire_times()
    path = tmp_path / "fire_times.json"
    renamed = dict(wanted, tzdata="1999z")
    path.write_text(json.dumps(renamed), encoding="utf-8")
    assert gen.drift("fire_times.json", wanted, path) is None
    changed = json.loads(json.dumps(wanted))
    first = next(iter(changed["cases"]))
    changed["cases"][first]["next_ms"][0] += 1
    path.write_text(json.dumps(changed), encoding="utf-8")
    problem = gen.drift("fire_times.json", wanted, path)
    assert problem is not None and "tzdata" in problem
