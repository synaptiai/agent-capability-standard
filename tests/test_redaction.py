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

from grounded_agency.state.evidence_store import EvidenceAnchor, plain
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


def _kept_anchor(redactor: Redactor, data: dict[str, Any]) -> dict[str, Any]:
    """The anchor ``data`` as an evidence store keeps it, in its JSON form
    with its metadata (members that are None left out)."""
    anchor = redactor.redact_anchor(EvidenceAnchor.from_dict(data))
    out = {k: v for k, v in anchor.to_dict().items() if v is not None}
    if anchor.metadata:
        out["metadata"] = plain(anchor.metadata)
    return out


@pytest.mark.parametrize("vector", DOC["vectors"], ids=lambda v: v["name"])
def test_vector(vector: dict[str, Any]) -> None:
    redactor = Redactor(vector["secret_values"])
    given = copy.deepcopy(vector["input"])
    output, pointers = redactor.redact(given)
    if vector.get("anchor"):
        # Kept as an evidence anchor: no digest once it held a secret.
        assert redactor.redact_anchor_data(given) == (
            vector["expect"]["output"],
            vector["expect"]["pointers"],
        )
        output = _kept_anchor(redactor, given)
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


def test_a_text_found_clean_is_read_again_once_a_value_or_pattern_is_added() -> None:
    """A short text a redactor found clean is not read again (an evidence
    store redacts the same member names in every anchor it keeps), until a
    registered value or an included pattern could find a secret in it."""
    r = Redactor()
    assert r.redact_text("deploy hunter22") == ("deploy hunter22", False)
    assert r.redact({"hunter22": 1}) == ({"hunter22": 1}, [])
    r.add_secret("hunter22")
    assert r.redact_text("deploy hunter22") == ("deploy [REDACTED]", True)
    assert r.redact({"hunter22": 1}) == ({"[REDACTED]": 1}, ["/[REDACTED]"])
    assert r.redact_text("pin 1234") == ("pin 1234", False)
    r.include(Redactor(patterns=[re.compile(r"pin (?P<secret>\d{4})")]))
    assert r.redact_text("pin 1234") == ("pin [REDACTED]", True)
    # A text that held a secret is read every time.
    assert r.redact_text("pin 1234") == ("pin [REDACTED]", True)


def test_patterns_name_their_secret() -> None:
    with pytest.raises(ValueError, match="secret"):
        Redactor(patterns=[re.compile("token")])
    only = Redactor(patterns=[re.compile(r"pin (?P<secret>\d{4})")])
    assert only.redact_text("pin 1234, password=hunter22") == (
        "pin [REDACTED], password=hunter22",
        True,
    )


# The forms of a registered value, in order; packages/acs-core's
# test/redact.test.ts pins the same list for encodedForms.
_FORMS_PINNED = json.loads(
    r"""["p@ss/w~rd é!\"", "p@ss/w~rd é!\\\"", "p@ss/w~rd \\u00e9!\\\"", "p@ss\\/w~rd é!\\\"", "p@ss\\/w~rd \\u00e9!\\\"", "p@ss/w~rd é!\\\\\\\"", "p@ss/w~rd \\\\u00e9!\\\\\\\"", "p@ss/w~rd \\u00e9!\\u0022", "p@ss/w~rd \\u00E9!\\u0022", "p@ss/w~rd \\\\u00e9!\\\\u0022", "p@ss/w~rd \\\\u00E9!\\\\u0022", "p%40ss%2Fw~rd%20%C3%A9%21%22", "p%40ss/w~rd%20%C3%A9%21%22", "p%40ss%2Fw~rd%20%C3%A9!%22", "p%40ss%2Fw~rd+%C3%A9%21%22", "p%40ss%2Fw%7Erd+%C3%A9%21%22", "p%40ss%2fw~rd%20%c3%a9%21%22", "p%40ss/w~rd%20%c3%a9%21%22", "p%40ss%2fw~rd%20%c3%a9!%22", "p%40ss%2fw~rd+%c3%a9%21%22", "p%40ss%2fw%7erd+%c3%a9%21%22"]"""
)


def test_registered_values_in_the_forms_text_carries_them() -> None:
    """A registered value is replaced as it is, JSON-escaped and
    percent-encoded (security round 1, batch 8): the forms the standard
    library's encoders give are among those registered, and the order is
    the TypeScript redactor's."""
    import urllib.parse

    from grounded_agency.state.redaction import encoded_forms

    value = 'p@ss/w~rd \u00e9!"'
    forms = encoded_forms(value)
    assert forms == _FORMS_PINNED
    for encoded in (
        json.dumps(value)[1:-1],
        json.dumps(value, ensure_ascii=False)[1:-1],
        json.dumps(json.dumps(value)[1:-1])[1:-1],
        json.dumps(json.dumps(value, ensure_ascii=False)[1:-1], ensure_ascii=False)[
            1:-1
        ],
        urllib.parse.quote(value, safe=""),
        urllib.parse.quote(value),
        urllib.parse.quote_plus(value, safe=""),
        urllib.parse.urlencode({"k": value})[2:],
    ):
        assert encoded in forms, encoded
        assert Redactor([value]).redact_text(f"x={encoded};") == (f"x={MARKER};", True)
        assert Redactor([value]).holds_credential({"note": f"x={encoded}"})
    # A value with a lone surrogate has no UTF-8: its JSON forms only (.NET
    # writes the escape in upper-case hex).
    assert encoded_forms("ab\ud800cd") == [
        "ab\ud800cd",
        "ab\\ud800cd",
        "ab\\\\ud800cd",
        "ab\\uD800cd",
        "ab\\\\uD800cd",
    ]
    # A value of letters and digits has one form.
    assert encoded_forms("s3cr3tValue") == ["s3cr3tValue"]


@pytest.mark.parametrize(
    "encoded",
    [
        # Go's encoding/json: & < > (kubectl, docker, gh, terraform).
        "Zq8\\u0026mK\\u003c41\\u003epX'+w==",
        # Gson: also = and '.
        "Zq8\\u0026mK\\u003c41\\u003epX\\u0027+w\\u003d\\u003d",
        # .NET's System.Text.Json: also ' and +, in upper-case hex.
        "Zq8\\u0026mK\\u003C41\\u003EpX\\u0027\\u002Bw==",
        # Go's form inside JSON text inside a JSON string.
        "Zq8\\\\u0026mK\\\\u003c41\\\\u003epX'+w==",
    ],
    ids=["go", "gson", "dotnet", "go_twice"],
)
def test_a_registered_value_is_replaced_as_html_safe_encoders_write_it(
    encoded: str,
) -> None:
    """A registered value is replaced, and refused, as encoders that keep
    JSON safe inside HTML write it (security round 5, batch 6: the
    registered value was kept whenever it held &, <, >, ', + or =, since
    only the Python and JavaScript JSON forms were registered)."""
    from grounded_agency.state.redaction import encoded_forms

    value = "Zq8&mK<41>pX'+w=="
    assert encoded in encoded_forms(value)
    redactor = Redactor([value])
    text = f'terraform output failed: {{"db_conn":{{"value":"{encoded}"}}}}'
    assert redactor.redact_text(text) == (
        'terraform output failed: {"db_conn":{"value":"[REDACTED]"}}',
        True,
    )
    assert redactor.holds_credential({"note": text})
    assert not Redactor().holds_credential({"note": text})


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
    "-----BEGIN PGP PRIVATE KEY BLOCK-----",
    "a://b:",
    # Pairs and tuples in text (security round 1, batch 6): an attempt
    # starts at each quote or bracket and reads to the next one.
    '"x',
    '"token", "',
    "['token', '",
    '"cookie", "value": "Basic ',
    '["',
    # Escaped quotes, empty userinfo users and command options (security
    # round 1, batch 8): a run of backslashes is read once, and an option's
    # attempt starts at its dashes.
    "\\",
    "password=\\",
    '\\"token\\", \\"value\\": \\"',
    '[\\"token\\", \\"',
    "a://:",
    "-u ",
    "'-u', '",
    "-ua:",
    "--a-",
    "--password ",
    "--password --",
    # A user option's name, read for at most 256 characters: `.-u` starts
    # an attempt at each of its positions, each read to the run's end
    # (security round 4, batch 1: 48 s at 200 KB before).
    ".-u",
    ".-U=",
    "!-u ",
    # Quoted values read to their closing quote, whitespace and all: a run
    # ends at the next quote of its kind or a line break, and a run with no
    # closing quote is read once more as an unquoted value (security round
    # 1, batch 8's verification).
    'password: "a ',
    "password='a password=\"a ",
    'password: "\\ ',
    "password='\\\"a ",
    '"cookie", "value": "a ',
    "['token', 'a ",
    "-u 'a:b ",
    '--password "a ',
    # Authorization headers with any scheme, quoted or not (security round
    # 4, batch 5): an attempt starts at the header's name, or at the start of
    # a run of backslashes before its quote.
    "authorization: a b ",
    '"authorization: a',
    '\\"authorization: ',
    'authorization: "a ',
    "['authorization', 'a ",
    # Cookie headers, curl's cookie option, netrc entries, the JSON escapes
    # of quotes and slashes, and words after a quote's escape (security
    # round 5, batch 6): an attempt starts at a header's name, an option's
    # dashes, a netrc keyword or a quote, and reads to the next quote, blank
    # or line end.
    "cookie: a ",
    "set-cookie:",
    '"cookie": "a ',
    "'cookie: a ",
    "cookie=a ",
    ".-b",
    "-b 'a ",
    "--cookie a",
    "-ba",
    "login a ",
    "machine password ",
    "\\u0022",
    "\\u0022a",
    "password\\u0022:\\u0022a ",
    "[\\u0022token\\u0022, \\u0022",
    "a:\\/\\/b:",
    "token\\u003d",
    "\\/",
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


# A text that opens a quoted value and never closes it (on one line): the
# run is read to its end once for the quoted reading and once more as an
# unquoted value, not again from each of its positions.
_UNCLOSED_QUOTES = [
    ('password: "', "a "),
    ("password: '", 'password: "a '),
    ('"passphrase": "', "\\ "),
    ("['cookie', \"", "a ; "),
    ("-u 'a:", "b c "),
    ('--password "', "x\\y "),
    ('"Authorization: ', "a "),
    ('Authorization: "', "a b "),
    # A run of blanks after a quoted header line's colon, read once (security
    # round 5, batch 6: 67 s for 40 KB, each blank read again to the run's
    # end before), and a Cookie header's the same way.
    ('"Authorization:', " "),
    ('"Authorization: Basic', " "),
    ("'Cookie:", " "),
    ('"Cookie": "', "a; "),
    ("Cookie: a", " "),
    ("-b '", "a=b "),
    ("password\\u0022: \\u0022", "a "),
]


@pytest.mark.parametrize(("prefix", "tail"), _UNCLOSED_QUOTES)
def test_a_quoted_value_with_no_closing_quote_is_read_in_linear_time(
    prefix: str, tail: str
) -> None:
    import time

    from grounded_agency.state.redaction import holds_credential

    text = (prefix + tail * (1_000_000 // len(tail) + 1))[:1_000_000]
    started = time.perf_counter()
    holds_credential({"data": text})
    redact_text(text)
    holds_secret({"data": text})
    assert time.perf_counter() - started < 20


def test_a_quoted_credential_value_is_replaced_whole() -> None:
    # A passphrase's later words are no longer kept (security round 1,
    # batch 8's verification: only its first word was replaced).
    text = 'ValueError: bad config {"passphrase": "correct horse battery staple"}'
    assert redact_text(text) == (
        'ValueError: bad config {"passphrase": "[REDACTED]"}',
        True,
    )
    # The refusal rule is unchanged: prose with a quoted phrase passes.
    from grounded_agency.state.redaction import holds_credential

    assert not holds_credential('token: "rotate monthly"')


def test_the_patterns_read_a_run_once_and_match_as_before() -> None:
    # A JWT starts at a word boundary: the run's start or after `-`.
    assert redact_text("abc-eyJhbGciOi.eyJzdWIi.sig1") == ("abc-[REDACTED]", True)
    assert redact_text("aeyJhbGciOi.eyJzdWIi.sig1") == (
        "aeyJhbGciOi.eyJzdWIi.sig1",
        False,
    )
    assert redact_text("aeyJ-eyJhbGciOi.x.y") == ("aeyJ-[REDACTED]", True)
    # A PEM header with no end: the rest of the text is replaced, since an
    # excerpt of a key keeps its body (security round 4, batch 5: nothing
    # was replaced), and a key after it ...
    assert redact_text("-----BEGIN PRIVATE KEY----- x") == (
        "-----BEGIN PRIVATE KEY-----[REDACTED]",
        True,
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


def test_coordination_audit_log_redacts_every_member() -> None:
    """Not only ``details``: the record's ``intent``, its
    ``details.evidence_refs`` and the event's own members are redacted too
    (§6.7), in the event, its ``to_dict`` and its action record."""
    from grounded_agency.coordination.audit import CoordinationAuditLog

    log = CoordinationAuditLog(redactor=Redactor(["s3cr3t-value"]))
    key = "AKIAABCDEFGHIJKLMNOP"
    url = "https://api.example.com/report?access_token=Hunter2SuperSecret99"
    event = log.record(
        "rotation token=abcd1234efgh",
        "agent s3cr3t-value",
        ["worker password=hunter22"],
        capability_id="audit",
        details={"note": "plain"},
        evidence_refs=[url, "file:report.txt"],
        intent=f"rotated deploy key {key}",
    )
    for text in (
        json.dumps(event.to_action_record()),
        json.dumps(event.to_dict()),
        json.dumps(log.export_action_records()),
        json.dumps(log.to_list()),
        repr(event),
    ):
        for secret in (
            key,
            "Hunter2SuperSecret99",
            "abcd1234efgh",
            "s3cr3t-value",
            "hunter22",
        ):
            assert secret not in text
    assert event.intent == f"rotated deploy key {MARKER}"
    assert event.evidence_refs == (
        f"https://api.example.com/report?access_token={MARKER}",
        "file:report.txt",
    )
    # A value that holds no secret is kept as given.
    plain_event = log.record("delegation", "a", ["b"], evidence_refs=["file:x"])
    assert plain_event.to_dict()["evidence_refs"] == ["file:x"]
    assert plain_event.to_action_record()["intent"] == "delegation"


def test_coordination_records_redact_intent_and_evidence_refs() -> None:
    """Through the layer's own writers: an ``audit`` step's event intent (or
    event type), a shared anchor's ref and a delegate's anchor refs reach
    the action record redacted, as ``details`` already were."""
    from grounded_agency.capabilities.registry import CapabilityRegistry
    from grounded_agency.coordination.audit import CoordinationAuditLog
    from grounded_agency.coordination.evidence_bridge import (
        CrossAgentEvidenceBridge,
    )
    from grounded_agency.coordination.orchestrator import OrchestrationRuntime
    from grounded_agency.coordination.registry import AgentRegistry
    from grounded_agency.state.evidence_store import EvidenceAnchor, EvidenceStore
    from grounded_agency.workflows.engine import WorkflowStep

    ontology = str(
        Path(__file__).resolve().parents[1] / "schemas" / "capability_ontology.yaml"
    )
    key = "AKIAABCDEFGHIJKLMNOP"

    # The audit step: the event's intent, then its event type.
    runtime = OrchestrationRuntime(CapabilityRegistry(ontology))
    step = WorkflowStep(capability="audit", purpose="Record the rotation.")
    for event in (
        {"intent": f"rotated deploy key {key}", "event_type": "key_rotation"},
        {"event_type": "login with password=Sup3rS3cret!"},
    ):
        result = runtime.execute_workflow_step(step, {"event": event})
        record = result.output["record"]
        assert MARKER in record["intent"]
    text = json.dumps(runtime.audit_log.export_action_records()) + json.dumps(
        runtime.audit_log.to_list()
    )
    assert key not in text and "Sup3rS3cret!" not in text

    # Evidence shared between agents.
    secret = "Hunter2SuperSecret99"
    agents = AgentRegistry(CapabilityRegistry(ontology))
    agents.register("a1", {"retrieve"}, trust_score=0.9)
    agents.register("a2", {"retrieve"}, trust_score=0.9)
    log = CoordinationAuditLog()
    bridge = CrossAgentEvidenceBridge(agents, EvidenceStore(), log)
    bridge.share_evidence(
        EvidenceAnchor(
            ref=f"https://api.example.com/report?access_token={secret}",
            kind="url",
            timestamp="2026-11-01T00:00:00Z",
        ),
        "a1",
        ["a2"],
    )
    record = log.export_action_records()[0]
    assert record["details"]["evidence_refs"] == [record["details"]["evidence_ref"]]
    assert secret not in json.dumps(log.export_action_records()) + json.dumps(
        log.to_list()
    )

    # A delegate's anchors, at the task's completion.
    runtime = OrchestrationRuntime(CapabilityRegistry(ontology))
    runtime.register_agent("w1", {"retrieve"}, trust_score=0.9)
    task = runtime.delegation.delegate(
        description="fetch report",
        required_capabilities=["retrieve"],
        target_agent_id="w1",
        input_data={},
    )
    presigned = (
        "https://bucket.s3.amazonaws.com/r.csv?X-Amz-Credential="
        f"{key}%2F20261117&X-Amz-Signature=" + "a" * 64
    )
    runtime.delegation.complete_task(
        task.task_id,
        {"ok": True},
        [EvidenceAnchor(ref=presigned, kind="url", timestamp="2026-11-17T00:00:00Z")],
    )
    records = runtime.audit_log.export_action_records()
    [done] = [r for r in records if r["intent"] == "task_complete"]
    assert any(
        f"X-Amz-Credential={MARKER}" in r for r in done["details"]["evidence_refs"]
    )
    assert key not in json.dumps(records)


_INQUIRE_TOKEN = "ghp_Ab3dE5gH7jK9mN1pQ3sT5vW7yZ9aB1cD3eF5"
_INQUIRE_BODY = "MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gunVTLw"
_INQUIRE_SEED = "MC4CAQAwBQYDK2VwBCIEIGp3Xq9Lw2Zr7Tn4Ks8Vd1Fh6Yj0Mb5Nc3Pe9Rg2Uk7Wa"
_ASK = "which repo should I push to? "


@pytest.mark.parametrize(
    ("ambiguous_input", "fragment"),
    [
        # A token whose start the old 200-character cut kept, with 29 and
        # 34 of its 40 characters (the second: all of its random part).
        (_ASK + "x" * 141 + " " + _INQUIRE_TOKEN, _INQUIRE_TOKEN[4:20]),
        (_ASK + "x" * 136 + " " + _INQUIRE_TOKEN, _INQUIRE_TOKEN[4:20]),
        # A key whose end line the cut removed.
        (
            "use this deploy key? -----BEGIN RSA PRIVATE KEY-----\n"
            + (_INQUIRE_BODY + "\n") * 20
            + "-----END RSA PRIVATE KEY-----\n",
            _INQUIRE_BODY[:24],
        ),
        # A short key whose whole body the cut kept, but not its end line.
        (
            "x" * 95
            + " -----BEGIN PRIVATE KEY-----\n"
            + _INQUIRE_SEED
            + "\n-----END PRIVATE KEY-----\n",
            _INQUIRE_SEED[20:],
        ),
    ],
    ids=["token_29", "token_34", "rsa_key", "short_key"],
)
def test_an_inquire_steps_input_is_redacted_whole(
    ambiguous_input: str, fragment: str
) -> None:
    """The orchestrator records an inquire step's ambiguous input whole, in
    the anchor's metadata and the audit event, which redact it: a cut
    before their redaction kept the part of a token or a key their
    patterns no longer matched (STANDARD v1.2 §6.7; security round 4,
    batch 6), as task_goal is kept whole."""
    from grounded_agency.capabilities.registry import CapabilityRegistry
    from grounded_agency.coordination.orchestrator import OrchestrationRuntime
    from grounded_agency.state.evidence_store import EvidenceStore
    from grounded_agency.workflows.engine import WorkflowStep

    assert fragment not in DEFAULT_REDACTOR.redact_text(ambiguous_input)[0]
    ontology = str(
        Path(__file__).resolve().parents[1] / "schemas" / "capability_ontology.yaml"
    )
    store = EvidenceStore()
    runtime = OrchestrationRuntime(CapabilityRegistry(ontology), evidence_store=store)
    step = WorkflowStep(capability="inquire", purpose="Clarify the request.")
    result = runtime.execute_workflow_step(step, {"ambiguous_input": ambiguous_input})
    kept = json.dumps(list(store.export())) + json.dumps(
        [
            runtime.audit_log.to_list(),
            runtime.audit_log.export_action_records(),
            result.output["evidence_anchors"],
        ]
    )
    assert fragment not in kept
    assert MARKER in kept


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


def test_no_digest_of_a_response_holding_a_registered_number() -> None:
    """A registered PIN given as a number in a response: no digest of it
    is kept, as of its string form, and an anchor citing it loses its own
    (§6.7; security round 4, batch 5): a digest of a short PIN is inverted
    by guessing."""
    from grounded_agency.hooks.evidence_collector import response_digest

    redactor = Redactor(["4821"])
    assert response_digest({"pin": 4821}, redactor) is None
    assert response_digest({"pin": "4821"}, redactor) is None
    assert response_digest({"pin": 1234}, redactor) is not None
    anchor = {
        "ref": "tool:verify:call-3",
        "kind": "tool",
        "digest": "sha256:" + "0" * 64,
        "metadata": {"pin": 4821},
    }
    assert redactor.redact_anchor_data(anchor) == (
        {
            "ref": "tool:verify:call-3",
            "kind": "tool",
            "metadata": {"pin": MARKER, "digest_omitted": "secret"},
        },
        ["/metadata/pin"],
    )


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


@pytest.mark.parametrize(
    "name",
    [
        "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789",
        "mcp__srv__hk_live_9f8e7d6c5b4a39281706",
    ],
)
def test_layer_redacts_a_tool_name_that_holds_a_secret(
    tmp_path: Path, name: str
) -> None:
    """The name of a call is the model's (or an MCP server's): its call
    record, the audit record exported from it and the diagnostic hold the
    redacted name, as the binding's trace does (§6.7; security round 4,
    batch 5)."""
    import asyncio

    adapter = _adapter(tmp_path, secret_values=("hk_live_9f8e7d6c5b4a39281706",))
    hook = adapter._make_pretooluse_safety_hook()
    out = asyncio.run(hook({"tool_name": name, "tool_input": {}}, "t1", None))
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    kept = (
        reason
        + json.dumps(list(adapter.call_records))
        + json.dumps([[d.message, d.location] for d in adapter.diagnostics])
        + json.dumps(adapter.export_action_records("s"))
    )
    assert "ghp_aBc" not in kept and "hk_live" not in kept
    (record,) = adapter.export_action_records("s")
    assert "[REDACTED]" in record["tool"]
    assert record["intent"] == f"{record['tool']} call"


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789", "[REDACTED]"),
        ("mcp__srv__hk_live_9f8e7d6c5b4a39281706", "mcp__srv__[REDACTED]"),
    ],
)
def test_layer_asks_with_no_secret_in_its_reason(
    tmp_path: Path, name: str, shown: str
) -> None:
    """The reason of an ask (F502), the diagnostic a host's permission flow
    shows and passes on, named the tool verbatim, though the call record
    redacted it (§6.7; security round 5, batch 5, the sibling of the
    binding's unredacted refusals)."""
    import asyncio

    adapter = _adapter(tmp_path, secret_values=("hk_live_9f8e7d6c5b4a39281706",))
    record = {"tool": name, "ontology": "2.2.0", "capability": "execute"}
    assert adapter.mapper.load_bindings([record]) == []
    hook = adapter._make_pretooluse_safety_hook()
    out = asyncio.run(
        hook(
            {"tool_name": name, "tool_input": {}, "permission_mode": "default"},
            "t1",
            None,
        )
    )
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert reason.startswith(f"F502 APPROVAL_REQUIRED: {shown} (capability 'execute')")
    kept = reason + json.dumps(list(adapter.call_records))
    assert "ghp_aBc" not in kept and "hk_live" not in kept


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


def test_include_takes_another_redactors_values_and_patterns() -> None:
    """A store that writes records for a runner takes what the runner's
    redactor recognises (§6.7): its registered values, in every form, and
    its own patterns; the other redactor is not changed."""
    from grounded_agency.state.redaction import DEFAULT_REDACTOR, Redactor

    marker = re.compile(r"sig=(?P<secret>[A-Za-z0-9]{16,})")
    runner = Redactor(["reg-9f8e7d6c5b4a3210"], patterns=[marker])
    store = Redactor()
    store.include(runner)
    store.include(runner)
    store.include(store)
    assert store.redact_text("k=reg-9f8e7d6c5b4a3210")[0] == "k=[REDACTED]"
    # A form the value travels in (JSON-escaped), as the runner registered it.
    assert store.redact_text(json.dumps({"k": "reg-9f8e7d6c5b4a3210"}))[1]
    assert store.redact_text("u?sig=AbCdEf0123456789XyZ")[0] == "u?sig=[REDACTED]"
    # The store keeps its own (default) patterns.
    assert store.redact_text("password=hunter2hunter2")[1]
    # Nothing flows back, and the shared default learns nothing.
    assert runner.redact_text("password=hunter2hunter2")[1] is False
    assert DEFAULT_REDACTOR.redact_text("reg-9f8e7d6c5b4a3210")[1] is False
