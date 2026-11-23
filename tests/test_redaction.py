"""The secret redactor (STANDARD v1.2 §6.7), against
``tests/conformance/secrets/redact.json``, which the TypeScript redactor
(``packages/acs-core/src/redact.ts``) reads too."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.state.redaction import (
    DEFAULT_PATTERNS,
    DEFAULT_REDACTOR,
    MARKER,
    Redactor,
    holds_secret,
    redact,
    redact_text,
)

VECTORS = Path(__file__).resolve().parent / "conformance" / "secrets" / "redact.json"
DOC = json.loads(VECTORS.read_text(encoding="utf-8"))


def test_the_vector_file() -> None:
    assert DOC["standard"] == "1.2.0"
    assert DOC["status"] == "informative"
    names = [v["name"] for v in DOC["vectors"]]
    assert len(names) == len(set(names))
    # Non-ASCII text is written as escapes.
    assert VECTORS.read_text(encoding="utf-8").isascii()


@pytest.mark.parametrize("vector", DOC["vectors"], ids=lambda v: v["name"])
def test_vector(vector: dict[str, Any]) -> None:
    redactor = Redactor(vector["secret_values"])
    given = copy.deepcopy(vector["input"])
    output, pointers = redactor.redact(given)
    assert output == vector["expect"]["output"]
    assert pointers == vector["expect"]["pointers"]
    # The value given is not modified.
    assert given == vector["input"]
    assert redactor.holds_secret(vector["input"]) == bool(pointers)
    # Redacting again changes nothing: the marker is not a secret.
    assert redactor.redact(output) == (output, [])
    if isinstance(vector["input"], str):
        assert redactor.redact_text(vector["input"]) == (output, bool(pointers))


def test_defaults() -> None:
    assert MARKER == "[REDACTED]"
    assert all("secret" in p.groupindex for p in DEFAULT_PATTERNS)
    assert redact_text("password=hunter22") == ("password=[REDACTED]", True)
    assert redact({"a": "plain"}) == ({"a": "plain"}, [])
    assert holds_secret(["x", "Bearer abcdefgh12345678"])
    assert not holds_secret([1, None, True])
    assert DEFAULT_REDACTOR.redact_text("nothing here") == ("nothing here", False)


def test_registered_values() -> None:
    r = Redactor()
    r.add_secret("abc")  # shorter than four characters: ignored
    r.add_secret("hunter")
    r.add_secret("hunter22")
    # The longest first, so a value that holds another is replaced whole.
    assert r.redact_text("hunter22 and hunter") == ("[REDACTED] and [REDACTED]", True)
    assert r.redact_text("abc") == ("abc", False)
    with pytest.raises(TypeError):
        r.add_secret(1234)  # type: ignore[arg-type]
    # A redactor's values are its own.
    assert DEFAULT_REDACTOR.redact_text("hunter22") == ("hunter22", False)


def test_patterns_name_their_secret() -> None:
    with pytest.raises(ValueError, match="secret"):
        Redactor(patterns=[re.compile("token")])
    only = Redactor(patterns=[re.compile(r"pin (?P<secret>\d{4})")])
    assert only.redact_text("pin 1234, password=hunter22") == (
        "pin [REDACTED], password=hunter22",
        True,
    )


def test_pointers_escape_and_tuples() -> None:
    value = {"a~b": ("Bearer abcdefgh12345678",), "c": {"client_secret": "s3cr3t!"}}
    output, pointers = redact(value)
    assert output == {"a~b": ["Bearer [REDACTED]"], "c": {"client_secret": MARKER}}
    assert pointers == ["/a~0b/0", "/c/client_secret"]


# Runs a pattern could read again from each of their positions: a URL
# scheme's characters, JWT starts (`eyJ`, after `-`), PEM headers with no end,
# base64url and hex text. Each took minutes or more at 1 MB before the
# patterns read a run once (security round 1, batch 5).
_LONG_RUNS = [
    "a.",
    "a-",
    "a+",
    "f0",
    "x",
    "eyJ",
    "eyJ-",
    "a-eyJ",
    "eyJaaaaaaaa.",
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----x",
    "a://b:",
    # Pairs and tuples in text (security round 1, batch 6): an attempt
    # starts at each quote or bracket and reads to the next one.
    '"x',
    '"token", "',
    "['token', '",
    '"cookie", "value": "Basic ',
    '["',
]


@pytest.mark.parametrize("unit", _LONG_RUNS)
def test_a_long_text_is_read_in_time_in_proportion_to_its_length(unit: str) -> None:
    import time

    from grounded_agency.state.redaction import holds_credential

    text = (unit * (1_000_000 // len(unit) + 1))[:1_000_000]
    started = time.perf_counter()
    holds_credential({"data": text})
    redact_text(text)
    holds_secret({"data": text})
    # About 1 s here; the old patterns took 20 s at 100 KB.
    assert time.perf_counter() - started < 20


def test_the_patterns_read_a_run_once_and_match_as_before() -> None:
    # A JWT starts at a word boundary: the run's start or after `-`.
    assert redact_text("abc-eyJhbGciOi.eyJzdWIi.sig1") == ("abc-[REDACTED]", True)
    assert redact_text("aeyJhbGciOi.eyJzdWIi.sig1") == (
        "aeyJhbGciOi.eyJzdWIi.sig1",
        False,
    )
    assert redact_text("aeyJ-eyJhbGciOi.x.y") == ("aeyJ-[REDACTED]", True)
    # A PEM header with no end: nothing is replaced, and a key after it ...
    assert redact_text("-----BEGIN PRIVATE KEY----- x") == (
        "-----BEGIN PRIVATE KEY----- x",
        False,
    )
    # ... is read as before, from the first header to the first end.
    two = "-----BEGIN PRIVATE KEY-----a-----BEGIN PRIVATE KEY-----b-----END PRIVATE KEY-----"
    assert redact_text(two) == (
        "-----BEGIN PRIVATE KEY-----[REDACTED]-----END PRIVATE KEY-----",
        True,
    )
    # A URL's scheme is a run of scheme characters holding a letter, read
    # from its start, so a scheme inside a word is read too.
    assert redact_text("x_https://deploy:hunter22@h") == (
        "x_https://deploy:[REDACTED]@h",
        True,
    )
    assert redact_text("1.2+https://deploy:hunter22@h") == (
        "1.2+https://deploy:[REDACTED]@h",
        True,
    )
    assert redact_text("12://deploy:hunter22@h") == ("12://deploy:hunter22@h", False)


# ---------------------------------------------------------------------------
# Where the SDK applies the redactor (STANDARD v1.2 §6.7)
# ---------------------------------------------------------------------------


def test_redact_anchor() -> None:
    from grounded_agency.state.evidence_store import EvidenceAnchor

    redactor = Redactor(["s3cr3t-value"])
    clean = EvidenceAnchor(ref="file:a", kind="file", timestamp=None)
    assert redactor.redact_anchor(clean) is clean
    dirty = EvidenceAnchor(
        ref="https://u:s3cr3t-value@example.org/",
        kind="url",
        timestamp=None,
        metadata={"header": "Authorization: Bearer abcdefghijkl"},
        excerpt="the key is s3cr3t-value",
    )
    out = redactor.redact_anchor(dirty)
    text = json.dumps({**out.to_dict(), "metadata": out.metadata})
    assert "s3cr3t-value" not in text and "abcdefghijkl" not in text
    # The caller's anchor is not changed.
    assert "s3cr3t-value" in dirty.ref


def test_coordination_audit_log_redacts_details() -> None:
    from grounded_agency.coordination.audit import CoordinationAuditLog

    log = CoordinationAuditLog(redactor=Redactor(["s3cr3t-value"]))
    event = log.record(
        "delegation",
        "a",
        ["b"],
        details={"note": "use s3cr3t-value", "api_key": "abcdefgh1234"},
    )
    text = json.dumps(event.to_action_record())
    assert "s3cr3t-value" not in text and "abcdefgh1234" not in text
    assert MARKER in text


def test_runner_redacts_a_host_exception(tmp_path: Path) -> None:
    """A host's exception becomes the step's Error message, redacted: the
    failed step's message and the trace hold the marker, not the token."""
    from grounded_agency.workflows import Host, WorkflowEngine, WorkflowRunner

    root = Path(__file__).resolve().parents[1]

    class Failing(Host):
        def now_ms(self) -> int:
            return 1_000

        def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("token=abcd1234")

    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        "# Standard version: 1.1.0\n"
        "w:\n"
        "  goal: g\n"
        "  risk: low\n"
        "  steps:\n"
        "  - capability: retrieve\n"
        "    purpose: p\n"
        "    store_as: r\n"
        "    input_bindings: {target: t}\n"
    )
    engine = WorkflowEngine(
        str(root / "schemas" / "capability_ontology.yaml"), schema_root=str(root)
    )
    engine.load_catalog(catalog)
    result = WorkflowRunner(engine).run("w", {}, Failing())
    assert result.code == "R402"
    trace = json.dumps(result.trace)
    assert "abcd1234" not in result.message and "abcd1234" not in trace
    assert MARKER in result.message and MARKER in trace


def _read_call(content: str) -> dict[str, Any]:
    return {
        "tool_name": "Read",
        "tool_input": {"file_path": "creds.txt"},
        "tool_response": content,
    }


@pytest.mark.parametrize(
    "content, secret",
    [
        ("AKIAABCDEFGHIJKLMNOP", True),
        ("s3cr3t-value", True),
        ("hello, world", False),
    ],
)
def test_collector_omits_the_digest_of_a_secret(content: str, secret: bool) -> None:
    """A digest of a whole response that is, or holds, a secret could be
    inverted by guessing: the collector keeps none, and says why."""
    import asyncio
    import hashlib

    from grounded_agency.hooks.evidence_collector import create_evidence_collector
    from grounded_agency.state.evidence_store import EvidenceStore

    store = EvidenceStore(redactor=Redactor(["s3cr3t-value"]))
    hook = create_evidence_collector(store)
    asyncio.run(hook(_read_call(content), "r1", None))
    (tool,) = [r.anchor for r in store.records() if r.anchor.ref.startswith("tool:")]
    if secret:
        assert tool.digest is None
        assert tool.metadata["digest_omitted"] == "secret"
    else:
        expected = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        assert tool.digest == expected
        assert "digest_omitted" not in tool.metadata
    exported = json.dumps(list(store.export()))
    assert "AKIAABCDEFGHIJKLMNOP" not in exported and "s3cr3t-value" not in exported


# ---------------------------------------------------------------------------
# The layer refuses persist and audit data that holds a credential
# (§5.18.10) and redacts what it records
# ---------------------------------------------------------------------------

CREDENTIALS = json.loads(
    (VECTORS.parent / "credentials.json").read_text(encoding="utf-8")
)
"""``tests/conformance/secrets/credentials.json``: the refusal rule's
vectors, which ``packages/acs-core`` and ``hooks/secret_scan.sh``
(``tests/test_skill_hooks.py``) run too."""
_TEXT = [
    v
    for v in CREDENTIALS["vectors"]
    if isinstance(v["input"], str) and not v["secret_values"]
]
BLOCKED = [v["input"] for v in _TEXT if v["expect"]["holds"]]
ALLOWED = [v["input"] for v in _TEXT if not v["expect"]["holds"]]


def test_the_credential_vector_file() -> None:
    assert CREDENTIALS["standard"] == "1.2.0"
    assert CREDENTIALS["status"] == "informative"
    names = [v["name"] for v in CREDENTIALS["vectors"]]
    assert len(names) == len(set(names))
    assert BLOCKED and ALLOWED


@pytest.mark.parametrize("vector", CREDENTIALS["vectors"], ids=lambda v: v["name"])
def test_holds_credential_vector(vector: dict[str, Any]) -> None:
    redactor = Redactor(vector["secret_values"])
    expected = vector["expect"]["holds"]
    assert redactor.holds_credential(vector["input"]) is expected
    if isinstance(vector["input"], str):
        wrapped = {"todos": [{"content": vector["input"]}]}
        assert redactor.holds_credential(wrapped) is expected


@pytest.mark.parametrize("text", BLOCKED)
def test_holds_credential_blocks(text: str) -> None:
    from grounded_agency.state.redaction import holds_credential

    assert holds_credential(text)
    assert holds_credential({"todos": [{"content": text}]})


@pytest.mark.parametrize("text", ALLOWED)
def test_holds_credential_lets_prose_pass(text: str) -> None:
    from grounded_agency.state.redaction import holds_credential

    assert not holds_credential(text)
    assert not holds_credential({"todos": [{"content": text}]})


def test_what_a_refusal_recognises_the_redactor_redacts() -> None:
    """Every credential the refusal rule recognises in text is a secret the
    same layer redacts (§6.7), except a PEM key's opening line alone: the
    redactor replaces a key's body, and the line has none."""
    for text in BLOCKED:
        if text.startswith("-----BEGIN"):
            continue
        assert holds_secret(text), text


def _adapter(tmp_path: Path, **more: Any) -> Any:
    from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

    root = Path(__file__).resolve().parents[1]
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(root / "schemas" / "capability_ontology.yaml"),
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            **more,
        )
    )


def _todo(text: str) -> dict[str, Any]:
    return {
        "tool_name": "TodoWrite",
        "tool_input": {"todos": [{"content": text, "status": "pending"}]},
    }


@pytest.mark.parametrize("text", BLOCKED)
def test_layer_refuses_persist_data_that_holds_a_credential(
    tmp_path: Path, text: str
) -> None:
    import asyncio

    adapter = _adapter(tmp_path)
    hook = adapter._make_pretooluse_safety_hook()
    out = asyncio.run(hook(_todo(text), "t1", None))
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert reason.startswith("F504 CONSTRAINT_VIOLATED:")
    # The refusal and the record it leaves hold no secret either.
    assert text not in reason or text.startswith("-----BEGIN")
    assert "AKIAABCDEFGHIJKLMNOP" not in json.dumps(list(adapter.call_records))


@pytest.mark.parametrize("text", ALLOWED)
def test_layer_lets_persist_prose_pass(tmp_path: Path, text: str) -> None:
    import asyncio

    adapter = _adapter(tmp_path)
    hook = adapter._make_pretooluse_safety_hook()
    out = asyncio.run(hook(_todo(text), "t1", None))
    assert out.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"


def test_layer_registers_the_hosts_secrets(tmp_path: Path) -> None:
    import asyncio

    adapter = _adapter(tmp_path, secret_values=("s3cr3t-value",))
    hook = adapter._make_pretooluse_safety_hook()
    out = asyncio.run(hook(_todo("deploy with s3cr3t-value"), "t1", None))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    # The store the adapter made redacts with the same values, and no
    # secret enters recorded_by.
    assert adapter.evidence_store.redactor is adapter.redactor
    assert "s3cr3t-value" not in json.dumps(adapter.recorded_by)
