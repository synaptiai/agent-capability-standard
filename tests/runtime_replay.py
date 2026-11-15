"""Replay of the runtime conformance fixtures through ``_core.Run``, shared by
the tests that play them (``tests/test_runner.py``,
``tests/test_trace_kinds_doc.py``).

A fixture's format is ``tests/conformance/runtime/schema/fixture.schema.json``.
Every start member it states is passed to ``Run.start`` as it is
(:func:`start_options`); its ``header`` is required, as the start operation
requires it (STANDARD v1.2 §11.5).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

from grounded_agency import _core

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
RUNTIME = ROOT / "tests" / "conformance" / "runtime"
FIXTURES = sorted(RUNTIME.glob("*.json"))

# The fixture members that are start options, by the name ``Run.start``
# gives them (the same name in both).
START_MEMBERS = (
    "header",
    "attendance",
    "actor_identity",
    "records",
    "profiles",
    "grounding",
    "destinations",
    "catalogs",
    "agents",
)


def load(path: Path) -> dict[str, Any]:
    """A fixture file."""
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict), path
    return fixture


def matches(expected: Any, actual: Any) -> bool:
    """Every key ``expected`` names matches (arrays element by element)."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and matches(v, actual[k]) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(expected) == len(actual)
            and all(matches(x, y) for x, y in zip(expected, actual, strict=True))
        )
    return bool(expected == actual) and type(expected) is type(actual)


def fill(response: Any, action: dict[str, Any]) -> Any:
    """``response`` with ``"{{digest}}"`` replaced by the action's digest, and
    ``"{{digest_upper}}"`` by it in uppercase."""
    if response == "{{digest}}":
        return action["digest"]
    if response == "{{digest_upper}}":
        return action["digest"].upper()
    if isinstance(response, dict):
        return {k: fill(v, action) for k, v in response.items()}
    if isinstance(response, list):
        return [fill(v, action) for v in response]
    return response


def start_options(fixture: dict[str, Any]) -> dict[str, Any]:
    """The keyword arguments of ``Run.start`` the fixture states: ``header``
    always (a fixture without it is malformed), each other member when it
    is present."""
    if "header" not in fixture:
        raise KeyError("a runtime fixture states its catalog's header (or null)")
    return {k: fixture[k] for k in START_MEMBERS if k in fixture}


def start(
    validator: _core.Validator, fixture: dict[str, Any], run_id: str = "run-1"
) -> _core.Run:
    """Start the fixture's run."""
    return _core.Run.start(
        validator,
        fixture["catalog"],
        fixture["workflow"],
        fixture["inputs"],
        run_id=run_id,
        now_ms=fixture["start"],
        **start_options(fixture),
    )


@cache
def _validator() -> _core.Validator:
    return _core.Validator(ONTOLOGY, ROOT)


KEY = b"key"


def resume(
    run: _core.Run, fixture: dict[str, Any], entry: dict[str, Any], now: int
) -> _core.Run:
    """A ``resume`` entry (STANDARD v1.2 §5.14.1): the run's state is saved
    and restored, as a host keeps it while the run waits, and resumed with
    the entry's attendance (default attended), time and actor."""
    saved = run.snapshot(KEY)
    run = _core.Run.restore(_validator(), fixture["catalog"], saved, KEY)
    options = entry["resume"]
    run.resume(
        attendance=options.get("attendance", "attended"),
        now_ms=options.get("at", now),
        actor_identity=options.get("actor_identity"),
    )
    return run


def play(
    run: _core.Run,
    fixture: dict[str, Any],
    expect: Callable[[int, dict[str, Any], dict[str, Any]], None] | None = None,
) -> _core.Run:
    """Play the fixture's script on ``run``: each ``tick`` passes the time,
    each ``resume`` resumes the run (:func:`resume`; the run returned is
    the resumed one), each other entry reads the pending action
    (``expect(i, expected, action)`` checks it, when given) and submits the
    response, if any."""
    now = fixture["start"]
    for i, entry in enumerate(fixture["script"]):
        if "tick" in entry:
            now = entry["tick"]
            run.tick(now)
            continue
        if "resume" in entry:
            now = entry["resume"].get("at", now)
            run = resume(run, fixture, entry, now)
            continue
        action = run.next()
        if expect is not None and "expect" in entry:
            expect(i, entry["expect"], action)
        if "respond" in entry:
            now = entry.get("at", now)
            run.submit(action["id"], fill(entry["respond"], action), now)
    return run
