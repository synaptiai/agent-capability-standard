"""At most one effect per idempotency key (STANDARD v1.2 §4.4.2):
:class:`~grounded_agency.workflows.idempotency.IdempotencyLog`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import _core
from grounded_agency.workflows.idempotency import IdempotencyLog
from tests.runtime_replay import (
    KEY,
    RUNTIME,
    _validator,
    fill,
    load,
    set_options,
    start,
)


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


def test_the_output_in_the_file_is_redacted(tmp_path: Path) -> None:
    """The log is the host's record of what it did (§6.4): it keeps a send's
    output as a runner submits it, its anchors redacted without their digest
    and evidence_seen rewritten to match, and every other secret in the
    output replaced (§6.7). A replay answers with what it kept."""
    path = tmp_path / "keys.jsonl"
    signed = (
        "https://bucket.s3.amazonaws.com/r.json?X-Amz-Credential="
        "AKIAIOSFODNN7EXAMPLE%2F20261123%2Fus-east-1%2Fs3%2Faws4_request"
    )
    userinfo = "https://bot:Sup3rS3cretPassw0rd@status.example.com/msg/1"
    response = {
        "kind": "Output",
        "value": {
            "sent": True,
            "receipt": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz0123456789"},
            "evidence_anchors": [
                {"ref": signed, "kind": "url", "digest": "sha256:" + "ab" * 32},
                {"ref": userinfo, "kind": "url"},
                {"ref": "file:report.txt", "kind": "file"},
            ],
        },
        "evidence_seen": [signed, userinfo, "file:report.txt"],
    }
    first = IdempotencyLog(path).perform(action(), Effect(response))
    assert first == response  # what the host's effect gave, for the runner
    blob = path.read_bytes()
    for secret in (
        b"AKIAIOSFODNN7EXAMPLE",
        b"Sup3rS3cretPassw0rd",
        b"abcdefghijklmnopqrstuvwxyz0123456789",
    ):
        assert secret not in blob, secret
    effect = Effect()
    again = IdempotencyLog(path).perform(action(), effect)
    assert effect.calls == 0
    anchors = again["value"]["evidence_anchors"]
    # The whole credential is replaced: `credential` is a credential name
    # (security round 5, batch 6), not the access key id alone.
    assert [a["ref"] for a in anchors] == [
        "https://bucket.s3.amazonaws.com/r.json?X-Amz-Credential=[REDACTED]",
        "https://bot:[REDACTED]@status.example.com/msg/1",
        "file:report.txt",
    ]
    assert "digest" not in anchors[0]
    assert anchors[0]["metadata"] == {"digest_omitted": "secret"}
    assert again["evidence_seen"] == [a["ref"] for a in anchors]
    assert again["value"]["receipt"] == {"Authorization": "[REDACTED]"}


def test_an_unkeyed_action_passes_through() -> None:
    log, effect = IdempotencyLog(), Effect()
    log.perform({"capability": "send", "inputs": {}}, effect)
    log.perform({"capability": "send", "inputs": {}}, effect)
    assert effect.calls == 2


def test_evidence_seen_is_kept_and_replayed(tmp_path: Path) -> None:
    # The host's attestation is part of the answer (§5.20): a replay without
    # it would fail an attested grounding policy (F505) after the effect.
    path = tmp_path / "keys.jsonl"
    seen = {
        "kind": "Output",
        "value": {"sent": True},
        "evidence_seen": ["file:report.txt"],
    }
    IdempotencyLog(path).perform(action(), Effect(seen))
    effect = Effect()
    assert IdempotencyLog(path).perform(action(), effect) == seen
    assert effect.calls == 0
    # An output without one is replayed without one.
    log = IdempotencyLog()
    log.perform(action("r1:4"), Effect())
    assert "evidence_seen" not in log.perform(action("r1:4"), Effect())


def test_a_replacing_delegation_is_performed_once_per_key() -> None:
    # The executor gives a delegation that names the one it replaces a key
    # of its own (§4.4.2) and re-delivers that attempt with the same key
    # after a restore (§5.19.4): the log answers the re-delivery.
    fixture = load(RUNTIME / "delegate_replaces_new_key.json")
    run = start(_validator(), fixture)
    for entry in fixture["script"][:2]:
        pending = run.next()
        run.submit(pending["id"], fill(entry["respond"], pending), fixture["start"])
    replacing = run.next()
    assert (replacing["idempotency_key"], replacing["replaces"]) == ("run-1:3", "t1")
    saved = run.snapshot(KEY)
    log = IdempotencyLog()
    accepted = {
        "kind": "Output",
        "value": {"accepted": True, "task_id": "t2", "evidence_anchors": []},
    }
    first, again = Effect(accepted), Effect()
    log.perform(replacing, first)
    restored = _core.Run.restore(
        _validator(), fixture["catalog"], saved, KEY, **set_options(fixture)
    )
    redelivered = restored.next()
    assert redelivered["idempotency_key"] == "run-1:3"
    assert log.perform(redelivered, again) == accepted
    assert (first.calls, again.calls) == (1, 0)


def test_performed_since_lists_the_runs_own_keys() -> None:
    now = [0]
    log = IdempotencyLog(clock=lambda: now[0])
    for key, at in (("r1:3", 5), ("r2:3", 6), ("r1:9", 7), ("r1:1", 1)):
        now[0] = at
        log.perform(action(key, destination=key, payload=1), Effect())
    keys = [e["key"] for e in log.performed_since(5, run_id="r1")]
    assert keys == ["r1:3", "r1:9"]
    assert log.performed_since(0, run_id="r10") == []


def test_performed_since_does_not_list_a_run_whose_id_extends_this_one() -> None:
    # A run_id is any string (§5.19.2): run "a:1" is not run "a" (§4.4.1:
    # only the run's own transmissions).
    log = IdempotencyLog(clock=lambda: 100)
    for key in ("a:3", "a:1:3", "ab:4"):
        log.perform(action(key, destination=key, payload=1), Effect())
    assert [e["key"] for e in log.performed_since(0, run_id="a")] == ["a:3"]
    assert [e["key"] for e in log.performed_since(0, run_id="a:1")] == ["a:1:3"]


def test_performed_since_lists_a_send_whose_outcome_is_unknown() -> None:
    # The effect raised after the request may have gone out: the entry stays
    # started, a retry is answered outcome_unknown, and a rollback must
    # still list it as a transmission (§4.4.1).
    log = IdempotencyLog(clock=lambda: 5)
    with pytest.raises(TimeoutError):
        log.perform(action("r:3"), Effect(TimeoutError("no answer")))
    log.perform(action("r:4", destination="x", payload=1), Effect())
    log.perform(
        action("r:6", destination="y", payload=1),
        Effect({"kind": "Error", "code": "R401", "message": "refused"}),
    )
    assert [(e["key"], e["state"]) for e in log.performed_since(0, run_id="r")] == [
        ("r:3", "started"),
        ("r:4", "done"),
    ]


def test_a_torn_last_line_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "keys.jsonl"
    IdempotencyLog(path).perform(action(), Effect())
    with path.open("a") as f:
        f.write('{"key": "r1:4", "sta')
    effect = Effect()
    assert IdempotencyLog(path).perform(action(), effect)["kind"] == "Output"
    assert effect.calls == 0


def _a_line_is_one_that_does_not_parse(path: Path, line: bytes) -> None:
    """Last, ``line`` is skipped as a torn line and cut off; anywhere else
    it is a ValueError, as any line that does not parse."""
    IdempotencyLog(path).perform(action(), Effect())
    entry = path.read_bytes()
    with path.open("ab") as f:
        f.write(line)
    effect = Effect()
    assert IdempotencyLog(path).perform(action(), effect)["kind"] == "Output"
    assert effect.calls == 0
    assert path.read_bytes() == entry
    path.write_bytes(entry + line + b"\n" + entry)
    with pytest.raises(ValueError, match="line 3: a line "):
        IdempotencyLog(path)


def test_a_line_nested_too_deeply_is_one_that_does_not_parse(
    tmp_path: Path, deep_json: str
) -> None:
    """Security round 4, batch 2 (a sibling of defect 4): json.loads raises
    RecursionError, no ValueError, on such a line, or (with a larger C
    stack, as on GitHub's ubuntu-latest runner of November 2026) returns
    the nested lists, which the load then read as an entry and raised
    AttributeError on. Either way it is a line that does not parse."""
    _a_line_is_one_that_does_not_parse(tmp_path / "keys.jsonl", deep_json.encode())


@pytest.mark.parametrize(
    "line",
    [
        b"[1]",
        b"3",
        b'"x"',
        b"null",
        b"{}",
        b'{"key": 3, "state": "cleared"}',
        b'{"key": "r1:4", "state": "gone"}',
        b'{"key": "r1:4", "state": "started"}',
        b'{"key": "r1:4", "state": "started", "capability": "send", '
        b'"inputs_sha256": "x", "at": true}',
        b'{"key": "r1:4", "state": "done", "capability": "send", '
        b'"inputs_sha256": "x", "at": 1}',
    ],
)
def test_a_line_that_is_no_entry_is_one_that_does_not_parse(
    tmp_path: Path, line: bytes
) -> None:
    """A line that parses to anything but an entry the log writes (a list,
    a number, a string, null, or an object short of a member a lookup
    reads) was read as an entry: entry.get or entry["key"] raised, or a
    later lookup did."""
    _a_line_is_one_that_does_not_parse(tmp_path / "keys.jsonl", line)


def test_every_entry_the_log_writes_reads_back(tmp_path: Path) -> None:
    """The control: started, done (with evidence_seen) and cleared."""
    path = tmp_path / "keys.jsonl"
    log = IdempotencyLog(path)
    with pytest.raises(TimeoutError):
        log.perform(action("r:1"), Effect(TimeoutError("no answer")))
    log.perform(
        action("r:2"),
        Effect({"kind": "Output", "value": {"sent": True}, "evidence_seen": []}),
    )
    log.perform(action("r:3"), Effect({"kind": "Error", "code": "R402"}))
    states = [json.loads(line)["state"] for line in path.read_bytes().splitlines()]
    assert states == ["started", "started", "done", "started", "cleared"]
    reloaded = IdempotencyLog(path)
    effect = Effect()
    assert reloaded.perform(action("r:1"), effect)["reason"] == "outcome_unknown"
    assert reloaded.perform(action("r:2"), effect)["kind"] == "Output"
    assert reloaded.perform(action("r:3"), effect)["kind"] == "Output"
    assert effect.calls == 1


def test_an_entry_after_a_torn_line_survives_a_restart(tmp_path: Path) -> None:
    # The torn line is cut off on load, so the next entry is a line of its
    # own: a send whose outcome is unknown stays unknown after a restart,
    # and is not transmitted again (§4.4.2).
    path = tmp_path / "keys.jsonl"
    IdempotencyLog(path).perform(action("r:1"), Effect())
    with path.open("ab") as f:
        f.write(b'{"at": 1, "capability": "send", "inputs_sha')
    timeout = Effect(TimeoutError("no answer"))
    with pytest.raises(TimeoutError):
        IdempotencyLog(path).perform(action("r:3"), timeout)
    again = Effect()
    answer = IdempotencyLog(path).perform(action("r:3"), again)
    assert (answer["kind"], answer["reason"]) == ("Error", "outcome_unknown")
    assert (timeout.calls, again.calls) == (1, 0)
    # Every line of the file is whole.
    lines = path.read_bytes().split(b"\n")
    assert lines[-1] == b"" and all(json.loads(line) for line in lines[:-1])


def test_more_entries_after_a_torn_line_load(tmp_path: Path) -> None:
    path = tmp_path / "keys.jsonl"
    IdempotencyLog(path).perform(action("r:1"), Effect())
    with path.open("ab") as f:
        f.write(b'{"key": "r:2", "sta')
    log = IdempotencyLog(path)
    log.perform(action("r:4"), Effect())
    log.perform(action("r:5"), Effect())
    reloaded = IdempotencyLog(path)
    effect = Effect()
    for key in ("r:1", "r:4", "r:5"):
        assert reloaded.perform(action(key), effect)["kind"] == "Output"
    assert effect.calls == 0


def test_a_whole_last_entry_without_its_newline_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "keys.jsonl"
    IdempotencyLog(path).perform(action("r:1"), Effect())
    text = path.read_bytes()
    path.write_bytes(text[:-1])  # the newline was not written
    log = IdempotencyLog(path)
    log.perform(action("r:2"), Effect())
    effect = Effect()
    reloaded = IdempotencyLog(path)
    for key in ("r:1", "r:2"):
        assert reloaded.perform(action(key), effect)["kind"] == "Output"
    assert effect.calls == 0
