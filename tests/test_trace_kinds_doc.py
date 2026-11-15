"""The trace section of the running-workflows guide lists what the executor records.

`docs/guides/RUNNING_WORKFLOWS.md`, section "The trace", lists the fields of
a trace event and every kind the reference executor records, with the
members of each kind's `detail`. The list is informative, and nothing else
writes it down, so it is compared here with its three sources:

- the kinds the executor's source passes to `trace()` and `trace_step()`
  (`core/src/exec/*.rs`),
- the kinds the runtime fixtures name in `trace_kinds`
  (`tests/conformance/runtime/*.json`),
- the events the fixtures' runs record, for the event fields and the
  members of each kind's `detail`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "guides" / "RUNNING_WORKFLOWS.md"
EXEC = ROOT / "core" / "src" / "exec"
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
RUNTIME = ROOT / "tests" / "conformance" / "runtime"

# The first argument of every call of trace() or trace_step().
TRACE_CALL = re.compile(r"\.trace(?:_step)?\(\s*([^,\s]+)\s*,")
NAME = re.compile(r"`([a-z_]+)`")


def _section(heading: str) -> list[str]:
    """The lines under `heading`, up to the next heading of its level or above."""
    lines = GUIDE.read_text(encoding="utf-8").splitlines()
    assert heading in lines, f"{GUIDE.name} has no heading {heading!r}"
    level = len(heading) - len(heading.lstrip("#"))
    out: list[str] = []
    for line in lines[lines.index(heading) + 1 :]:
        m = re.match(r"^(#+) ", line)
        if m and len(m.group(1)) <= level:
            break
        out.append(line)
    return out


def _rows(heading: str) -> list[list[str]]:
    """The cells of each table row under `heading` whose first cell is a name."""
    rows = []
    for line in _section(heading):
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if NAME.fullmatch(cells[0]):
            rows.append(cells)
    return rows


def documented_fields() -> list[str]:
    return [row[0].strip("`") for row in _rows("### Trace event fields")]


def documented_kinds() -> dict[str, set[str]]:
    """Each documented kind with the `detail` members its row lists."""
    kinds: dict[str, set[str]] = {}
    for row in _rows("### Trace kinds"):
        assert len(row) == 3, row
        kind, detail = row[0].strip("`"), row[2]
        assert kind not in kinds, f"{kind} is listed twice"
        members = set(NAME.findall(detail))
        assert members or detail == "none", f"{kind}: unreadable detail {detail!r}"
        kinds[kind] = members
    return kinds


def source_kinds() -> set[str]:
    """Every kind the executor's source passes to its trace."""
    kinds: set[str] = set()
    for path in sorted(EXEC.glob("*.rs")):
        for arg in TRACE_CALL.findall(path.read_text(encoding="utf-8")):
            if arg == "kind":
                # trace_step() handing its own parameter on to trace().
                continue
            assert re.fullmatch(r'"[a-z_]+"', arg), (
                f"{path.name}: a trace kind that is not a string literal ({arg}); "
                "this test cannot see which kinds it produces"
            )
            kinds.add(arg.strip('"'))
    return kinds


def source_fields() -> list[str]:
    """The keys of the event that trace() builds, in the order it writes them."""
    text = (EXEC / "machine.rs").read_text(encoding="utf-8")
    body = re.search(r"fn trace\(.*?json!\(\{(.*?)\}\);", text, re.S)
    assert body, "machine.rs: trace() no longer builds its event with json!"
    return re.findall(r'"([a-z_]+)":', body.group(1))


def fixture_kinds() -> set[str]:
    kinds: set[str] = set()
    for path in sorted(RUNTIME.glob("*.json")):
        kinds.update(json.loads(path.read_text(encoding="utf-8"))["trace_kinds"])
    return kinds


def _fill(response: Any, action: dict[str, Any]) -> Any:
    if response == "{{digest}}":
        return action["digest"]
    if isinstance(response, dict):
        return {k: _fill(v, action) for k, v in response.items()}
    if isinstance(response, list):
        return [_fill(v, action) for v in response]
    return response


@pytest.fixture(scope="module")
def recorded() -> list[dict[str, Any]]:
    """Every trace event of every runtime fixture's run.

    The script of each fixture is played as `tests/test_runner.py` plays it;
    what the run must do is asserted there, not here.
    """
    validator = _core.Validator(ONTOLOGY, ROOT)
    events: list[dict[str, Any]] = []
    for path in sorted(RUNTIME.glob("*.json")):
        f = json.loads(path.read_text(encoding="utf-8"))
        now = f["start"]
        run = _core.Run.start(
            validator,
            f["catalog"],
            f["workflow"],
            f["inputs"],
            attendance=f["attendance"],
            run_id="run-1",
            now_ms=now,
            actor_identity=f.get("actor_identity"),
        )
        for entry in f["script"]:
            if "tick" in entry:
                now = entry["tick"]
                run.tick(now)
                continue
            action = run.next()
            if "respond" in entry:
                now = entry.get("at", now)
                run.submit(action["id"], _fill(entry["respond"], action), now)
        events.extend(run.trace())
    return events


def test_the_guide_lists_the_kinds_the_executor_source_records() -> None:
    documented, source = set(documented_kinds()), source_kinds()
    assert source, "no trace call found under core/src/exec"
    assert documented - source == set(), "listed, but the executor records no such kind"
    assert source - documented == set(), (
        "recorded by the executor, but missing from 'Trace kinds' in "
        "docs/guides/RUNNING_WORKFLOWS.md"
    )


def test_the_guide_lists_the_kinds_the_runtime_fixtures_name() -> None:
    documented, fixtures = set(documented_kinds()), fixture_kinds()
    assert fixtures - documented == set(), "a fixture names a kind the guide lacks"
    assert documented - fixtures == set(), (
        "no runtime fixture names this kind in trace_kinds: add one in "
        "scripts/gen_runtime_fixtures.py"
    )


def test_the_guide_lists_the_fields_of_a_trace_event(
    recorded: list[dict[str, Any]],
) -> None:
    fields = documented_fields()
    assert fields == source_fields()
    assert recorded
    for event in recorded:
        assert set(event) == set(fields), event


def test_the_guide_lists_the_detail_members_of_each_kind(
    recorded: list[dict[str, Any]],
) -> None:
    seen: dict[str, set[str]] = {}
    for event in recorded:
        assert isinstance(event["detail"], dict), event
        seen.setdefault(event["kind"], set()).update(event["detail"])
    assert seen == documented_kinds()


def test_step_is_null_only_where_the_guide_says(
    recorded: list[dict[str, Any]],
) -> None:
    (row,) = [r for r in _rows("### Trace event fields") if r[0] == "`step`"]
    without_step = set(NAME.findall(row[2]))
    assert without_step, "the `step` row names no kind"
    assert {e["kind"] for e in recorded if e["step"] is None} == without_step
