"""`schemas/host_protocol.schema.json` (STANDARD v1.2 §5.19) against what the
reference executor does: every action it issues, every response a runtime
fixture gives, every trace event and every snapshot of a replay of all the
runtime fixtures validate, and every kind the schema defines occurs.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import typing
from typing import Any

import jsonschema
import pytest
from referencing import Registry, Resource

from grounded_agency import _core
from grounded_agency.workflows import protocol
from tests.action_record_schema import problems
from tests.runtime_replay import (
    FIXTURES,
    KEY,
    ONTOLOGY,
    ROOT,
    fill,
    load,
    resume,
    start,
)

SCHEMA = ROOT / "schemas" / "host_protocol.schema.json"
CATALOG_SCHEMA = ROOT / "schemas" / "workflow_catalog.schema.json"
FIXTURE_SCHEMA = (
    ROOT / "tests" / "conformance" / "runtime" / "schema" / "fixture.schema.json"
)

# The two fixtures whose responses carry members the protocol does not
# define, or a reason outside §5.19.7: the leniency of §5.19.1.
LENIENT = {"response_extra_members_ignored", "error_reason_outside_grammar_ignored"}


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _validator(ref: str, strict: bool = False) -> jsonschema.protocols.Validator:
    """A validator of `#/$defs/<ref>`; with `strict`, responses take no
    member the protocol does not define."""
    schema = _schema()
    if strict:
        for kind in protocol.RESPONSES:
            schema["$defs"][kind]["additionalProperties"] = False
        schema["$defs"]["Error"]["properties"]["reason"] = {"$ref": "#/$defs/reason"}
    catalog = json.loads(CATALOG_SCHEMA.read_text(encoding="utf-8"))
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema)),
            (catalog["$id"], Resource.from_contents(catalog)),
        ]
    )
    return jsonschema.Draft202012Validator(
        {"$ref": f"{schema['$id']}#/$defs/{ref}"}, registry=registry
    )


def _errors(validator: jsonschema.protocols.Validator, value: Any) -> list[str]:
    return [
        f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
        for e in validator.iter_errors(value)
    ]


def test_the_schema_is_valid_2020_12() -> None:
    jsonschema.Draft202012Validator.check_schema(_schema())
    jsonschema.Draft202012Validator.check_schema(
        json.loads(FIXTURE_SCHEMA.read_text(encoding="utf-8"))
    )


def test_every_fixture_file_validates() -> None:
    validator = jsonschema.Draft202012Validator(
        json.loads(FIXTURE_SCHEMA.read_text(encoding="utf-8"))
    )
    for path in FIXTURES:
        assert not _errors(validator, load(path)), path.stem


def _replay(validator: _core.Validator, f: dict[str, Any]) -> dict[str, list[Any]]:
    """Play a fixture, saving the run before every entry; collect every
    action, response, snapshot, trace event and the run record."""
    seen: dict[str, list[Any]] = {
        "actions": [],
        "responses": [],
        "snapshots": [],
        "trace": [],
        "run_records": [],
    }
    run = start(validator, f)
    now = f["start"]
    for entry in f["script"]:
        seen["snapshots"].append(run.snapshot(KEY))
        if "tick" in entry:
            now = entry["tick"]
            run.tick(now)
        elif "wake_at" in entry:
            pass
        elif "cancel" in entry:
            now = entry["cancel"].get("at", now)
            run.cancel(entry["cancel"]["reason"], now)
        elif "resume" in entry:
            now = entry["resume"].get("at", now)
            seen["trace"] += run.trace()
            run = resume(run, f, entry, now)
        else:
            action = run.next()
            seen["actions"].append(action)
            if "respond" in entry:
                response = fill(entry["respond"], action)
                seen["responses"].append(response)
                now = entry.get("at", now)
                run.submit(action["id"], response, now)
    seen["actions"].append(run.next())
    seen["snapshots"].append(run.snapshot(None))
    seen["trace"] += run.trace()
    seen["run_records"].append(run.run_record())
    return seen


@pytest.fixture(scope="module")
def replays() -> dict[str, dict[str, list[Any]]]:
    validator = _core.Validator(ONTOLOGY, ROOT)
    return {path.stem: _replay(validator, load(path)) for path in FIXTURES}


def test_every_action_validates(replays: dict[str, dict[str, list[Any]]]) -> None:
    v = _validator("action")
    for name, seen in replays.items():
        for action in seen["actions"]:
            assert not _errors(v, action), (name, action["kind"], _errors(v, action))


def test_every_response_validates(replays: dict[str, dict[str, list[Any]]]) -> None:
    lenient, strict = _validator("response"), _validator("response", strict=True)
    for name, seen in replays.items():
        for response in seen["responses"]:
            assert not _errors(lenient, response), (name, _errors(lenient, response))
            if name not in LENIENT:
                assert not _errors(strict, response), (name, _errors(strict, response))
    # The leniency fixtures send what only the lenient schema takes.
    for name in LENIENT:
        assert any(_errors(strict, r) for r in replays[name]["responses"]), name


def test_every_trace_event_and_snapshot_validates(
    replays: dict[str, dict[str, list[Any]]],
) -> None:
    events, snapshots = _validator("trace_event"), _validator("snapshot")
    for name, seen in replays.items():
        for event in seen["trace"]:
            assert not _errors(events, event), (name, _errors(events, event))
        for snap in seen["snapshots"]:
            assert not _errors(snapshots, snap), (name, _errors(snapshots, snap))


def test_every_record_is_an_action_record(
    replays: dict[str, dict[str, list[Any]]],
) -> None:
    for name, seen in replays.items():
        terminal = seen["actions"][-1]
        for record in terminal["action_records"]:
            assert not problems(record), (name, problems(record))
        for record in seen["run_records"]:
            assert record is not None, name
            assert not problems(record), (name, problems(record))


def test_every_kind_occurs(replays: dict[str, dict[str, list[Any]]]) -> None:
    schema = _schema()["$defs"]
    action_kinds = {r["$ref"].rsplit("/", 1)[1] for r in schema["action"]["oneOf"]}
    response_kinds = {r["$ref"].rsplit("/", 1)[1] for r in schema["response"]["oneOf"]}
    seen_actions = {a["kind"] for s in replays.values() for a in s["actions"]}
    seen_responses = {r["kind"] for s in replays.values() for r in s["responses"]}
    assert seen_actions == action_kinds
    assert seen_responses == response_kinds
    assert set(protocol.ACTIONS) == action_kinds
    assert set(protocol.RESPONSES) == response_kinds


def _keys(td: type) -> tuple[set[str], set[str]]:
    hints = typing.get_type_hints(td, include_extras=True)
    required = set(td.__required_keys__)  # type: ignore[attr-defined]
    return set(hints), required


def test_the_typed_dicts_match_the_schema() -> None:
    schema = _schema()["$defs"]
    head = schema["head"]
    for kind, td in protocol.ACTIONS.items():
        props = set(schema[kind]["properties"]) | set(head["properties"])
        required = set(schema[kind]["required"]) | set(head["required"])
        keys, td_required = _keys(td)
        assert keys == props, kind
        assert td_required == required, kind
    for kind, td in protocol.RESPONSES.items():
        keys, td_required = _keys(td)
        assert keys == set(schema[kind]["properties"]), kind
        assert td_required == set(schema[kind]["required"]), kind
    assert protocol.RECORD_MODES == tuple(
        schema["run_options"]["properties"]["records"]["enum"]
    )


def test_every_action_carries_the_run_id(
    replays: dict[str, dict[str, list[Any]]],
) -> None:
    for name, seen in replays.items():
        assert {a["run_id"] for a in seen["actions"]} == {"run-1"}, name


def _generator() -> Any:
    """scripts/gen_runtime_fixtures.py as a module (it builds its fixtures
    when imported)."""
    path = ROOT / "scripts" / "gen_runtime_fixtures.py"
    spec = importlib.util.spec_from_file_location("gen_runtime_fixtures", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


def test_a_fixture_may_pin_only_members_the_standard_defines() -> None:
    gen = _generator()
    end = {"kind": "Failed", "code": "R402", "message": "m"}
    assert gen.pinned_problems("f", end, "Failed") == []
    assert gen.pinned_problems("f", {**end, "elapsed_ms": 3}, "Failed")
    records = {
        "kind": "Completed",
        "action_records": [{"status": "executed", "internal": 1}],
    }
    assert gen.pinned_problems("f", records, "Completed")
    # Below an open member, anything goes.
    outputs = {"kind": "Completed", "outputs": {"r": {"anything": [1]}}}
    assert gen.pinned_problems("f", outputs, "Completed") == []
    assert gen.pinned_problems("f", {"details": {"x": 1}}, "run_record") == []


def test_the_reference_runner_answers_in_the_schema() -> None:
    """A response the runner composes for a host that cannot serve a step
    (`HostCannotServe`) validates against the strict schema."""
    from grounded_agency.workflows.runner import Host, HostCannotServe, WorkflowRunner

    class Refusing(Host):
        def now_ms(self) -> int:
            return 0

        def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any] | None:
            raise HostCannotServe("unsupported_domain", "no audio here")

    response = WorkflowRunner._dispatch(  # type: ignore[attr-defined]
        Refusing(), copy.deepcopy({"kind": "InvokeCapability", "id": 1})
    )
    strict = _validator("response", strict=True)
    assert not _errors(strict, response), _errors(strict, response)
    assert response["reason"] == "unsupported_domain"
