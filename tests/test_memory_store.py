"""The memory store (STANDARD v1.2 §4.5): the normative vectors of
``tests/conformance/memory/store.json``, run by
:class:`~grounded_agency.state.memory.MemoryStore` in memory and on file, and
its refusal of secrets (§6.7)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.state.memory import (
    SCOPES,
    MemoryContext,
    MemoryError,
    MemoryStore,
)
from grounded_agency.state.redaction import Redactor

ROOT = Path(__file__).resolve().parent.parent
VECTORS = json.loads((ROOT / "tests/conformance/memory/store.json").read_text())
DEFAULT = "session"
UNPROVIDED = "x-unprovided"


class Clock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now


def fill(value: Any, keys: list[Any]) -> Any:
    if isinstance(value, str):
        if value == "{{default}}":
            return DEFAULT
        if value == "{{unprovided}}":
            return UNPROVIDED
        if value.startswith("{{key:") and value.endswith("}}"):
            return keys[int(value[6:-2])]
        return value
    if isinstance(value, dict):
        return {k: fill(v, keys) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, keys) for v in value]
    return value


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        for k, v in expected.items():
            if k not in actual:
                return False
            if k == "data":
                if actual[k] != v or type(actual[k]) is not type(v):
                    return False
            elif k in ("stored_at", "expires_at"):
                if instant(actual[k]) != instant(v):
                    return False
            elif not matches(v, actual[k]):
                return False
        return True
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(expected) == len(actual)
            and all(matches(e, a) for e, a in zip(expected, actual, strict=True))
        )
    return bool(expected == actual)


def provided(case: dict[str, Any]) -> bool:
    return all(fill(s, []) in SCOPES for s in case["scopes"])


CASES = [c for c in VECTORS["cases"] if provided(c)]


def test_the_vectors_are_normative_and_ascii() -> None:
    text = (ROOT / "tests/conformance/memory/store.json").read_text()
    assert text.isascii()
    assert VECTORS["status"] == "normative"
    assert len(CASES) == len(VECTORS["cases"]), "this store provides every scope"


@pytest.mark.parametrize("on_file", [False, True], ids=["memory", "file"])
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_memory_vectors(case: dict[str, Any], on_file: bool, tmp_path: Path) -> None:
    clock = Clock()
    path = tmp_path / "memory.json" if on_file else None

    def store() -> MemoryStore:
        # On file, every op reads a store opened afresh: a restart.
        return MemoryStore(path, clock=clock, **case.get("config", {}))

    one = store()
    keys: list[Any] = []
    for i, op in enumerate(case["ops"]):
        clock.now = op["at"]
        s = store() if on_file else one
        if "end" in op:
            s.end_scope(op["end"]["scope"], op["end"]["instance"])
            keys.append(None)
            continue
        context = {**VECTORS["context"], **op.get("context", {})}
        ctx = MemoryContext(
            run=context["run"],
            session=context["session"],
            user=context["user"],
            project=context["project"],
        )
        kind = "persist" if "persist" in op else "recall"
        inputs = fill(op[kind], keys)
        if "error" in op:
            with pytest.raises(MemoryError) as refused:
                getattr(s, kind)(inputs, ctx)
            assert refused.value.reason == op["error"], f"op {i}"
            keys.append(None)
            continue
        out = getattr(s, kind)(inputs, ctx)
        assert matches(fill(op["expect"], keys), out), f"op {i}: {out}"
        keys.append(out.get("key"))


def test_a_restart_keeps_entries_only_on_file(tmp_path: Path) -> None:
    ctx = MemoryContext(session="s1")
    on_file = MemoryStore(tmp_path / "m.json")
    on_file.persist({"key": "k", "data": 1}, ctx)
    assert MemoryStore(tmp_path / "m.json").recall({"key": "k"}, ctx)["found"]
    assert MemoryStore(tmp_path / "m.json").statement()["scopes"]["session"][
        "survives_restart"
    ]
    assert not MemoryStore().statement()["scopes"]["session"]["survives_restart"]
    assert (tmp_path / "m.json").stat().st_mode & 0o777 == 0o600


def test_persist_deprecated_timestamp_is_stored_at() -> None:
    out = MemoryStore(clock=lambda: 1234).persist(
        {"key": "k", "data": 1}, MemoryContext(session="s")
    )
    assert out["timestamp"] == out["stored_at"] == "1970-01-01T00:00:01.234Z"


@pytest.mark.parametrize(
    "inputs, where",
    [
        ({"key": "k", "data": {"token": "ghp_" + "a" * 36}}, "/token"),
        (
            {
                "key": "k",
                "data": {
                    "req": {
                        "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwx"}
                    }
                },
            },
            "/req/headers/Authorization",
        ),
        ({"key": "pw-s3cret-value", "data": 1}, "the key"),
        (
            {
                "key": "k",
                "data": {
                    "headers": [
                        {"name": "Authorization", "value": "Basic dXNlcjpodW50ZXIyMDI2"}
                    ]
                },
            },
            "/headers/0/value",
        ),
        (
            {"key": "k", "data": {"headers": [["X-Api-Key", "k3y9f8e7d6c5b4a3"]]}},
            "/headers/0/1",
        ),
    ],
    ids=[
        "github_token",
        "bearer_header",
        "registered_secret_key",
        "header_pair",
        "header_tuple",
    ],
)
def test_a_secret_is_refused_not_stored(inputs: dict[str, Any], where: str) -> None:
    """Data or a key holding a secret the host recognises is refused
    (secret_in_data, §4.5, §6.7): nothing is stored, and the message names
    where, never the value."""
    store = MemoryStore(redactor=Redactor(secret_values=["s3cret-value"]))
    ctx = MemoryContext(session="s1")
    with pytest.raises(MemoryError) as refused:
        store.persist(inputs, ctx)
    assert refused.value.reason == "secret_in_data"
    assert where in refused.value.message
    assert "ghp_" not in refused.value.message
    assert "abcdefghijklmnop" not in refused.value.message
    assert "s3cret" not in refused.value.message
    key = inputs["key"]
    assert not store.recall({"key": key}, ctx)["found"]


@pytest.mark.parametrize(
    "data",
    [{"card": 4111111111111111}, {"cards": [7, 4111111111111111]}, 4111111111111111],
    ids=["member", "list_item", "whole"],
)
def test_a_registered_secret_given_as_a_number_is_refused(data: Any) -> None:
    """A registered secret given as a JSON number (a card number, a PIN) is
    refused as its string form is: the JSON text the store keeps would hold
    it (§6.7; security round 4, batch 5)."""
    store = MemoryStore(redactor=Redactor(secret_values=["4111111111111111"]))
    ctx = MemoryContext(session="s1")
    with pytest.raises(MemoryError) as refused:
        store.persist({"key": "card", "data": data}, ctx)
    assert refused.value.reason == "secret_in_data"
    assert "4111111111111111" not in refused.value.message
    assert not store.recall({"key": "card"}, ctx)["found"]
    # A number that holds none is stored.
    assert store.persist({"key": "n", "data": {"count": 4111}}, ctx)["stored"]


@pytest.mark.parametrize(
    "data",
    [
        {
            "how_to_query": "curl -H 'Authorization: ApiKey VnVhQ2ZHY0JDZGJrUXctN1A6dWkybGp0YjU0' https://es.example.com"
        },
        {
            "key": "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nlQOYBGVhY2sBCADKx3mYq\n=AbCd\n-----END PGP PRIVATE KEY BLOCK-----"
        },
        {
            "key": "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ"
        },
        {"key": "-----BEGIN OPENSSH PRIVATE KEY-----"},
    ],
    ids=["apikey_header", "pgp_block", "key_without_end", "key_header_alone"],
)
def test_a_credential_the_refusal_rule_recognises_is_refused(data: Any) -> None:
    """Data the refusal rule says holds a credential is refused whether or
    not redaction would replace part of it (security round 4, batch 5: a
    key's opening line alone, which redaction leaves as it is, was stored),
    an Authorization header with any scheme and an OpenPGP key included."""
    store = MemoryStore()
    ctx = MemoryContext(session="s1")
    with pytest.raises(MemoryError) as refused:
        store.persist({"key": "k", "data": data}, ctx)
    assert refused.value.reason == "secret_in_data"
    assert "VnVh" not in refused.value.message and "lQOY" not in refused.value.message
    assert not store.recall({"key": "k"}, ctx)["found"]


def test_a_scope_with_no_instance_is_refused() -> None:
    with pytest.raises(MemoryError) as refused:
        MemoryStore().persist({"key": "k", "data": 1, "scope": "user"}, MemoryContext())
    assert refused.value.reason == "unsupported_scope"


def test_entry_count_limit() -> None:
    store = MemoryStore(max_entries=1)
    ctx = MemoryContext(session="s")
    store.persist({"key": "a", "data": 1}, ctx)
    store.persist({"key": "a", "data": 2}, ctx)  # a replacement is no new entry
    with pytest.raises(MemoryError) as refused:
        store.persist({"key": "b", "data": 1}, ctx)
    assert refused.value.reason == "over_capacity"
    assert "1 entries" in refused.value.message


def test_a_stored_value_is_a_copy() -> None:
    """A recall returns the value stored (§4.5): what the caller later does
    with the value it persisted, or with a recall's data, changes nothing."""
    store = MemoryStore()
    ctx = MemoryContext(session="s")
    data: dict[str, Any] = {"a": [1]}
    store.persist({"key": "k", "data": data}, ctx)
    data["a"].append(2)
    first = store.recall({"key": "k"}, ctx)["data"]
    assert first == {"a": [1]}
    first["a"].append(3)
    assert store.recall({"key": "k"}, ctx)["data"] == {"a": [1]}


@pytest.mark.parametrize("on_file", [False, True], ids=["memory", "file"])
def test_an_unrepresentable_ttl_stores_nothing(on_file: bool, tmp_path: Path) -> None:
    """A ttl that would end the entry after the last instant a date-time
    states is refused before anything is written (§4.5): no entry, and the
    key can still be recalled and written."""
    path = tmp_path / "memory.json" if on_file else None
    store = MemoryStore(path)
    ctx = MemoryContext(session="s")
    with pytest.raises(MemoryError) as refused:
        store.persist({"key": "k", "data": 1, "ttl": "P3000000D"}, ctx)
    assert refused.value.reason == "unsupported_ttl"
    assert store.recall({"key": "k"}, ctx)["found"] is False
    if path is not None:
        assert not path.exists()
    assert store.persist({"key": "k", "data": 2, "ttl": "P1D"}, ctx)["stored"]
    assert store.recall({"key": "k"}, ctx)["data"] == 2
