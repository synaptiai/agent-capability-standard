"""At most one effect per idempotency key (STANDARD v1.2 §4.4.2):
:class:`~grounded_agency.workflows.idempotency.IdempotencyLog`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.workflows.idempotency import IdempotencyLog


def action(key: str = "r1:3", **inputs: Any) -> dict[str, Any]:
    return {
        "kind": "InvokeCapability",
        "capability": "send",
        "idempotency_key": key,
        "inputs": inputs or {"destination": "ops", "payload": {"a": 1}},
    }


class Effect:
    def __init__(self, response: dict[str, Any] | Exception | None = None) -> None:
        self.calls = 0
        self.response = response or {"kind": "Output", "value": {"sent": True}}

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_done_answers_the_earlier_output() -> None:
    log, effect = IdempotencyLog(), Effect()
    first = log.perform(action(), effect)
    again = log.perform(action(), effect)
    assert first == again == {"kind": "Output", "value": {"sent": True}}
    assert effect.calls == 1


def test_started_is_outcome_unknown_and_an_exception_keeps_it() -> None:
    log = IdempotencyLog()
    with pytest.raises(TimeoutError):
        log.perform(action(), Effect(TimeoutError("no answer")))
    effect = Effect()
    answer = log.perform(action(), effect)
    assert (answer["kind"], answer["code"], answer["reason"]) == (
        "Error",
        "R402",
        "outcome_unknown",
    )
    assert effect.calls == 0


def test_an_error_clears_the_key() -> None:
    log = IdempotencyLog()
    log.perform(action(), Effect({"kind": "Error", "code": "R402", "message": "no"}))
    effect = Effect()
    assert log.perform(action(), effect)["kind"] == "Output"
    assert effect.calls == 1


def test_a_reused_key_is_a_conflict_and_never_replayed() -> None:
    log = IdempotencyLog()
    log.perform(action(destination="ops", payload=1), Effect())
    effect = Effect()
    other = log.perform(action(destination="elsewhere", payload=1), effect)
    assert (other["kind"], other["reason"]) == ("Error", "key_conflict")
    assert effect.calls == 0
    capability = {**action(destination="ops", payload=1), "capability": "mutate"}
    assert log.perform(capability, effect)["reason"] == "key_conflict"
    # The entry is unchanged: the original attempt is still answered.
    assert log.perform(action(destination="ops", payload=1), effect)["kind"] == "Output"


def test_member_order_does_not_matter() -> None:
    log = IdempotencyLog()
    log.perform(action(destination="ops", payload={"a": 1, "b": 2}), Effect())
    effect = Effect()
    reordered = {
        **action(),
        "inputs": {"payload": {"b": 2, "a": 1}, "destination": "ops"},
    }
    assert log.perform(reordered, effect)["kind"] == "Output"
    assert effect.calls == 0


def test_a_file_backed_log_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "keys.jsonl"
    log = IdempotencyLog(path)
    assert log.durable and not IdempotencyLog().durable
    log.perform(action(), Effect({"kind": "Output", "value": {"sent": True, "n": 7}}))
    effect = Effect()
    again = IdempotencyLog(path).perform(action(), effect)
    assert again == {"kind": "Output", "value": {"sent": True, "n": 7}}
    assert effect.calls == 0
    assert path.stat().st_mode & 0o777 == 0o600


def test_the_destination_in_the_file_is_redacted(tmp_path: Path) -> None:
    path = tmp_path / "keys.jsonl"
    IdempotencyLog(path).perform(
        action(destination="https://u:p4ssw0rd-secret@x.example/", payload=1), Effect()
    )
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert all("p4ssw0rd" not in json.dumps(line) for line in lines)
    assert "[REDACTED]" in lines[-1]["destination"]


def test_replaces_and_unkeyed_pass_through() -> None:
    log, effect = IdempotencyLog(), Effect()
    log.perform({**action(), "replaces": "t1"}, effect)
    log.perform({**action(), "replaces": "t1"}, effect)
    log.perform({"capability": "send", "inputs": {}}, effect)
    assert effect.calls == 3


def test_performed_since_lists_the_runs_own_keys() -> None:
    now = [0]
    log = IdempotencyLog(clock=lambda: now[0])
    for key, at in (("r1:3", 5), ("r2:3", 6), ("r1:9", 7), ("r1:1", 1)):
        now[0] = at
        log.perform(action(key, destination=key, payload=1), Effect())
    keys = [e["key"] for e in log.performed_since(5, run_id="r1")]
    assert keys == ["r1:3", "r1:9"]
    assert log.performed_since(0, run_id="r10") == []


def test_a_torn_last_line_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "keys.jsonl"
    IdempotencyLog(path).perform(action(), Effect())
    with path.open("a") as f:
        f.write('{"key": "r1:4", "sta')
    effect = Effect()
    assert IdempotencyLog(path).perform(action(), effect)["kind"] == "Output"
    assert effect.calls == 0
