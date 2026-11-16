"""Evidence stores (STANDARD v1.2 §6.6): the in-memory ``EvidenceStore``
and the durable ``JsonlEvidenceStore`` meet the same duties, checked by one
suite, plus what is particular to each."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from grounded_agency.state.evidence_store import (
    EvidenceAnchor,
    EvidenceStore,
    EvidenceStoreProtocol,
)
from grounded_agency.state.jsonl_evidence_store import JsonlEvidenceStore
from grounded_agency.state.redaction import Redactor

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "interop" / "evidence.schema.json").read_text())


def validate(name: str, value: Any) -> None:
    """Validate ``value`` against ``$defs.<name>`` of the interop schema."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": SCHEMA["$defs"],
        "$ref": f"#/$defs/{name}",
    }
    jsonschema.Draft202012Validator(schema).validate(value)


Factory = Callable[[], EvidenceStoreProtocol]


@pytest.fixture(params=["memory", "jsonl"])
def make(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Factory]:
    stores: list[Any] = []

    def factory() -> EvidenceStoreProtocol:
        store: Any = (
            EvidenceStore()
            if request.param == "memory"
            else JsonlEvidenceStore(tmp_path / "evidence.jsonl")
        )
        stores.append(store)
        return store

    yield factory
    for s in stores:
        if isinstance(s, JsonlEvidenceStore):
            s.close()


def anchor(ref: str = "file:a.txt", kind: str = "file") -> EvidenceAnchor:
    return EvidenceAnchor(ref=ref, kind=kind, timestamp="2026-11-16T00:00:00+00:00")


def test_both_stores_implement_the_protocol(make: Factory) -> None:
    assert isinstance(make(), EvidenceStoreProtocol)


def test_append_get_filter_export(make: Factory) -> None:
    store = make()
    a = store.append(
        anchor(), capability="retrieve", run_id="run-1", frame=["w"], step=0
    )
    b, c = store.append_many(
        [anchor("tool:Read:1", "tool"), anchor("log:x", "log")],
        capability="search",
        tool="Read",
        call_id="toolu_1",
    )
    assert [r.record_id for r in (a, b, c)] == ["ev-0", "ev-1", "ev-2"]
    assert store.get("ev-1") == b
    assert store.get("ev-9") is None and store.get("nope") is None
    assert store.records(capability="search") == [b, c]
    assert store.records(kind="log") == [c]
    assert store.records(run_id="run-1") == [a]
    assert store.records(capability="search", kind="tool") == [b]
    lines = list(store.export())
    assert [line["record_id"] for line in lines] == ["ev-0", "ev-1", "ev-2"]
    for line in lines:
        validate("EvidenceRecord", line)
    assert lines[0]["frame"] == ["w"] and lines[0]["step"] == 0
    assert lines[1]["tool"] == "Read" and lines[1]["call_id"] == "toolu_1"
    info = store.info()
    validate("StoreInfo", info.to_dict())
    assert info.count == 3


def test_kept_anchors_are_frozen_copies(make: Factory) -> None:
    store = make()
    mine = anchor()
    mine.metadata["note"] = {"n": [1]}
    record = store.append(mine)
    kept = store.get(record.record_id)
    assert kept is not None
    with pytest.raises(FrozenInstanceError):
        kept.anchor.kind = "url"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        kept.anchor.mark_critical()
    with pytest.raises(TypeError):
        kept.anchor.metadata["x"] = 1  # type: ignore[index]
    # The caller's anchor stays mutable, and changing it changes nothing
    # the store holds.
    mine.kind = "url"
    mine.metadata["note"]["n"].append(2)
    again = store.get(record.record_id)
    assert again is not None and again.anchor.kind == "file"
    assert again.to_dict()["metadata"] == {"note": {"n": [1]}}


def test_subscribers(make: Factory, caplog: pytest.LogCaptureFixture) -> None:
    store = make()
    seen: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []

    def broken(payload: dict[str, Any]) -> None:
        raise RuntimeError("subscriber down")

    store.subscribe(broken)
    unsubscribe = store.subscribe(seen.append)
    store.subscribe(other.append)
    a = anchor()
    a.excerpt = "a quotation"
    with caplog.at_level(logging.WARNING):
        records = store.append_many([a, anchor("url:x", "url")], capability="retrieve")
    assert "subscriber raised" in caplog.text
    assert len(seen) == len(other) == 1  # one notification per append_many
    payload = seen[0]
    validate("EvidenceRecorded", payload)
    assert payload["type"] == "acs.evidence_recorded"
    assert payload["record_ids"] == [r.record_id for r in records]
    assert payload["capability"] == "retrieve"
    assert all("excerpt" not in x for x in payload["anchors"])
    unsubscribe()
    store.append(anchor())
    assert len(seen) == 1 and len(other) == 2


def test_capture_failures_are_counted(make: Factory) -> None:
    store = make()
    store.record_capture_failure("toolu_1", "disk full")
    assert store.info().capture_failures == 1
    assert store.info().to_dict()["x-capture_failures"] == 1


@pytest.mark.parametrize("kind", ["memory", "jsonl"])
def test_secrets_never_kept(kind: str, tmp_path: Path) -> None:
    """Every store redacts what it keeps (STANDARD v1.2 §6.7): a registered
    value and a recognised credential, in a ref, an excerpt and metadata
    (a tool input kept with ``include_tool_input``)."""
    redactor = Redactor(["s3cr3t-value"])
    path = tmp_path / "evidence.jsonl"
    store: Any = (
        EvidenceStore(redactor=redactor)
        if kind == "memory"
        else JsonlEvidenceStore(path, redactor=redactor)
    )
    a = EvidenceAnchor.from_tool_output(
        "Bash",
        "b1",
        {"command": "deploy --key s3cr3t-value"},
        "ok",
        include_tool_input=True,
    )
    a.excerpt = "Authorization: Bearer abcdefghijklmnop"
    store.append(anchor("https://u:s3cr3t-value@example.org/x", "url"))
    store.append(a)
    exported = json.dumps(list(store.export()))
    assert "s3cr3t-value" not in exported and "abcdefghijklmnop" not in exported
    assert "[REDACTED]" in exported
    if kind == "jsonl":
        store.close()
        assert b"s3cr3t-value" not in path.read_bytes()
        assert b"abcdefghijklmnop" not in path.read_bytes()


# ---------------------------------------------------------------------------
# The in-memory store
# ---------------------------------------------------------------------------


def test_memory_store_counts_removals_and_never_reuses_ids() -> None:
    store = EvidenceStore(max_anchors=3)
    for i in range(5):
        store.append(anchor(f"file:{i}"))
    info = store.info()
    assert (info.durability, info.bounded, info.count, info.removed) == (
        "memory",
        True,
        3,
        2,
    )
    store.clear()
    assert store.info().removed == 5
    assert store.append(anchor()).record_id == "ev-5"
    assert store.get("ev-0") is None


# ---------------------------------------------------------------------------
# The JSON Lines store
# ---------------------------------------------------------------------------


def test_jsonl_reopen_keeps_ids_and_continues(tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    with JsonlEvidenceStore(path) as store:
        store.append(anchor(), capability="retrieve")
        store.append(anchor("file:b"))
        assert store.info().to_dict()["durability"] == "durable"
        assert store.info().bounded is False
    assert os.stat(path).st_mode & 0o777 == 0o600
    with JsonlEvidenceStore(path) as again:
        assert [r.record_id for r in again.records()] == ["ev-0", "ev-1"]
        assert again.records(capability="retrieve")[0].anchor.ref == "file:a.txt"
        assert again.append(anchor("file:c")).record_id == "ev-2"
    for line in path.read_text().splitlines():
        validate("EvidenceRecord", json.loads(line))


def test_jsonl_repairs_a_torn_last_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "e.jsonl"
    with JsonlEvidenceStore(path) as store:
        store.append(anchor())
    torn = b'{"record_id":"ev-1","anchor":{"ref":"fi'
    with open(path, "ab") as f:
        f.write(torn)
    with caplog.at_level(logging.WARNING), JsonlEvidenceStore(path) as store:
        assert "dropped" in caplog.text
        assert store.info().to_dict()["x-torn_tail_bytes"] == len(torn)
        record = store.append(anchor("file:b"))
        assert record.record_id == "ev-1"
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_jsonl_skips_and_counts_an_unreadable_line(tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    with JsonlEvidenceStore(path) as store:
        store.append(anchor())
    with open(path, "ab") as f:
        f.write(b"not json\n")
    with JsonlEvidenceStore(path) as store:
        assert store.info().to_dict()["x-unreadable_lines"] == 1
        assert len(store.records()) == 1
        assert store.append(anchor("file:b")).record_id == "ev-1"


def test_jsonl_refuses_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "t.jsonl"
    target.write_text("")
    link = tmp_path / "l.jsonl"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        JsonlEvidenceStore(link)


def test_jsonl_has_no_clear(tmp_path: Path) -> None:
    with JsonlEvidenceStore(tmp_path / "e.jsonl") as store:
        assert not hasattr(store, "clear")
