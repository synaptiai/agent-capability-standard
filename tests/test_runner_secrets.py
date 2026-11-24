"""What a runner and its host write holds no secret their redactor
recognises (STANDARD v1.2 §6.4, §6.5, §6.7): the evidence anchors of an
``Event`` and of an ``Output`` that gives them as a tuple, a cancel's
reason, a rollback's ``not_covered``, and the host's idempotency log, which
the runner gives its registered secrets (security round 3, batch 4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.state.evidence_store import EvidenceStore
from grounded_agency.state.memory import MemoryStore
from grounded_agency.state.redaction import DEFAULT_REDACTOR, Redactor
from grounded_agency.state.snapshots import FileSnapshotStore
from grounded_agency.workflows import Host, WorkflowEngine, WorkflowRunner
from grounded_agency.workflows.idempotency import IdempotencyLog

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = str(ROOT / "schemas" / "capability_ontology.yaml")

PASSWORD = "Sup3rS3cretPassw0rd"
REGISTERED = "reg-9f8e7d6c5b4a3210"
KEY_ID = "AKIAIOSFODNN7EXAMPLE"
BEARER = "abcdefghijklmnopqrstuvwxyz0123456789"


def engine_for(tmp_path: Path, catalog: str) -> WorkflowEngine:
    path = tmp_path / "catalog.yaml"
    path.write_text(catalog)
    engine = WorkflowEngine(ONTOLOGY, schema_root=str(ROOT))
    engine.load_catalog(path)
    return engine


def kept(run: Any, result: Any) -> dict[str, str]:
    """Each place the run keeps what it was given, as text."""
    return {
        "message": result.message or "",
        "outputs": json.dumps(result.outputs, default=str),
        "trace": json.dumps(result.trace, default=str),
        "records": json.dumps(
            [result.action_records, result.run_record, run.run_record()], default=str
        ),
        "snapshot": json.dumps(run.snapshot(b"k"), default=str),
    }


def holding(places: dict[str, str], *secrets: str) -> list[tuple[str, str]]:
    return [(p, s) for p, text in places.items() for s in secrets if s in text]


WAIT = """\
# Standard version: 1.2.0
wait_for_job:
  goal: Wait for a job.
  risk: low
  workflow_extensions:
    requires: [wait@1]
  steps:
  - capability: receive
    purpose: Wait for the job to finish.
    store_as: done
    timeout: 1h
    wait:
      event_type: job.done
"""
REF = f"https://ci:{PASSWORD}@ci.example.com/jobs/42/log?k={REGISTERED}"


class EventHost(Host):
    def __init__(self, anchors: Any = None) -> None:
        super().__init__(None)
        self.anchors = anchors

    def now_ms(self) -> int:
        return 1_000

    def await_event(self, action: dict[str, Any]) -> dict[str, Any] | None:
        if self.anchors is None:
            return None
        return {
            "kind": "Event",
            "principal": "ci",
            "event": {
                "event_id": "e1",
                "timestamp": "2026-11-23T12:00:00Z",
                "source": {"kind": "agent", "name": "ci"},
                "event_type": "job.done",
                "raw": {},
                "canonical": {},
                "anchors": self.anchors,
                "provenance": {"transformer": "ci", "transform_version": "1"},
            },
        }


@pytest.mark.parametrize("shape", [list, tuple])
def test_an_events_anchors_are_redacted_before_the_core_copies_them(
    tmp_path: Path, shape: type
) -> None:
    """A receive step's output takes the event's anchors (its
    evidence_anchors, and the event under data): they are kept with their
    secrets replaced and no digest, in every place the run keeps them."""
    anchor = {
        "ref": REF,
        "kind": "url",
        "excerpt": f"log at {REF}",
        "digest": "sha256:" + "ab" * 32,
    }
    runner = WorkflowRunner(engine_for(tmp_path, WAIT), redactor=Redactor([REGISTERED]))
    run = runner.start("wait_for_job", None, records="actions", now_ms=1_000)
    result = runner.drive(run, EventHost(shape([anchor])))
    assert result.ok, result
    assert holding(kept(run, result), PASSWORD, REGISTERED) == []
    (out,) = result.outputs["done"]["evidence_anchors"]
    assert "[REDACTED]" in out["ref"] and "digest" not in out
    assert out["metadata"] == {"digest_omitted": "secret"}
    assert result.outputs["done"]["data"][0]["anchors"] == [out]


def test_an_events_anchors_without_a_secret_are_kept_as_given(tmp_path: Path) -> None:
    anchor = {"ref": "https://ci.example.com/jobs/42/log", "kind": "url"}
    runner = WorkflowRunner(engine_for(tmp_path, WAIT))
    run = runner.start("wait_for_job", None, now_ms=1_000)
    result = runner.drive(run, EventHost([anchor]))
    assert result.ok, result
    assert result.outputs["done"]["evidence_anchors"] == [anchor]


LOOK = """\
# Standard version: 1.2.0
look:
  goal: Read a status page.
  risk: low
  steps:
  - capability: retrieve
    purpose: Read the status page.
    store_as: page
    input_bindings:
      target: status
"""


class TupleHost(Host):
    def __init__(self, anchors: tuple[Any, ...], seen: Any = None) -> None:
        super().__init__(None)
        self.anchors = anchors
        self.seen = seen

    def now_ms(self) -> int:
        return 1_000

    def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
        response: dict[str, Any] = {
            "kind": "Output",
            "value": {
                "data": {"ok": True},
                "confidence": 0.9,
                "evidence_anchors": self.anchors,
            },
        }
        if self.seen is not None:
            response["evidence_seen"] = self.seen
        return response


def test_anchors_given_as_a_tuple_are_redacted_and_recorded(tmp_path: Path) -> None:
    """The core reads a tuple as an array: its anchors are redacted as a
    list's are, and the evidence store records them."""
    ref = f"https://bot:{PASSWORD}@status.example.com/v1/state"
    store = EvidenceStore()
    runner = WorkflowRunner(engine_for(tmp_path, LOOK), evidence_store=store)
    run = runner.start("look", {}, records="actions", now_ms=1_000)
    result = runner.drive(run, TupleHost(({"ref": ref, "kind": "url"},)))
    assert result.ok, result
    assert holding(kept(run, result), PASSWORD) == []
    (record,) = store.records()
    assert PASSWORD not in record.anchor.ref
    # An anchor that holds no secret is recorded from a tuple too.
    store = EvidenceStore()
    runner = WorkflowRunner(engine_for(tmp_path, LOOK), evidence_store=store)
    run = runner.start("look", {}, now_ms=1_000)
    plain = {"ref": "https://status.example.com/v1/state", "kind": "url"}
    assert runner.drive(run, TupleHost((plain,))).ok
    assert [r.anchor.ref for r in store.records()] == [plain["ref"]]


def test_a_tuple_of_seen_refs_is_rewritten_with_its_anchors(tmp_path: Path) -> None:
    """evidence_seen given as a tuple names the anchors' own refs: it is
    rewritten to their redacted refs, so the attested policy still passes."""
    from grounded_agency import GroundingPolicy

    ref = f"https://bot:{PASSWORD}@status.example.com/v1/state"
    runner = WorkflowRunner(engine_for(tmp_path, LOOK))
    run = runner.start(
        "look",
        {},
        now_ms=1_000,
        grounding=GroundingPolicy(require={"retrieve"}, attested=True),
    )
    result = runner.drive(run, TupleHost(({"ref": ref, "kind": "url"},), seen=(ref,)))
    assert result.ok, result
    assert holding(kept(run, result), PASSWORD) == []


def test_a_cancel_reason_is_redacted(tmp_path: Path) -> None:
    """The core makes the reason the R408 message and writes it into the
    trace, the records, the run record and the snapshot."""
    runner = WorkflowRunner(engine_for(tmp_path, WAIT), redactor=Redactor([REGISTERED]))
    host = EventHost()
    run = runner.start("wait_for_job", None, records="actions", now_ms=1_000)
    runner.advance(run, host)
    why = (
        f"operator stopped it: upstream https://ci:{PASSWORD}@ci.example.com "
        f"token {REGISTERED}"
    )
    result = runner.cancel(run, why, host=host)
    assert result.code == "R408"
    assert result.message.startswith("operator stopped it: upstream https://ci:")
    assert "[REDACTED]" in result.message
    assert holding(kept(run, result), PASSWORD, REGISTERED) == []


def test_a_cancel_reason_without_a_secret_is_kept(tmp_path: Path) -> None:
    runner = WorkflowRunner(engine_for(tmp_path, WAIT))
    run = runner.start("wait_for_job", None, now_ms=1_000)
    runner.advance(run, EventHost())
    assert runner.cancel(run, "no longer needed").message == "no longer needed"


SEND = """\
# Standard version: 1.2.0
send_report:
  goal: Send a report.
  risk: high
  inputs:
    to:
      type: string
      required: true
  steps:
  - capability: checkpoint
    purpose: Save the agent's state.
    store_as: cp
    input_bindings:
      scope: "*"
  - capability: constrain
    purpose: Check the destination.
    store_as: policy
    input_bindings:
      target: ${to}
      constraints: [allowed destinations]
  - capability: send
    purpose: Send the report.
    store_as: sent
    input_bindings:
      destination: ${to}
      payload: {report: 1}
  - capability: rollback
    purpose: Undo.
    store_as: rb
    input_bindings:
      checkpoint_id: ${cp.checkpoint_id}
"""
SIGNED = (
    "https://bucket.s3.amazonaws.com/receipt.json?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    f"&X-Amz-Credential={KEY_ID}%2F20261123%2Fus-east-1%2Fs3%2Faws4_request"
)
USERINFO = f"https://bot:{PASSWORD}@status.example.com/msg/1"
WEBHOOK = "T0000/B0000/XXXXXXXXXXXXXXXXXXXXXXXX"


class SendHost(Host):
    """Sends once per key through its idempotency log, with a receipt that
    holds a bearer token and anchors that hold a key id and a password."""

    def __init__(self, tmp_path: Path, log: IdempotencyLog, **kw: Any) -> None:
        root = tmp_path / "work"
        root.mkdir(exist_ok=True)
        (root / "a.txt").write_text("x")
        tracker = CheckpointTracker(
            checkpoint_dir=tmp_path / ".checkpoints",
            snapshots=FileSnapshotStore(root, tmp_path / "snapshots"),
        )
        super().__init__(tracker, idempotency=log, **kw)
        self.transmitted = 0

    def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
        if action["capability"] == "constrain":
            return {
                "kind": "Output",
                "value": {"compliant": True, "evidence_anchors": []},
            }
        if action["capability"] == "send":
            return self.send_once(action, self.transmit)
        return super().invoke_capability(action)

    def transmit(self) -> dict[str, Any]:
        self.transmitted += 1
        return {
            "kind": "Output",
            "value": {
                "sent": True,
                "receipt": {"Authorization": f"Bearer {BEARER}"},
                "evidence_anchors": (
                    {"ref": SIGNED, "kind": "url", "digest": "sha256:" + "cd" * 32},
                    {"ref": USERINFO, "kind": "url"},
                ),
            },
            "evidence_seen": [SIGNED, USERINFO],
        }

    def request_approval(self, action: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "Decision",
            "decision_id": f"d{action['id']}",
            "decision": "approved",
            "approvers": ["alice"],
            "digest": action["digest"],
        }


@pytest.mark.parametrize("own_redactor", [False, True])
def test_the_idempotency_log_and_the_rollback_hold_no_secret(
    tmp_path: Path, own_redactor: bool
) -> None:
    """The reported route: a send's output (its anchors, a receipt) and a
    registered secret in its destination reached the log's file and the
    rollback's not_covered. The log keeps the output as the runner submits
    it, redacted, and takes the runner's registered secrets, whether it has
    the default redactor or one of its own."""
    path = tmp_path / "keys.jsonl"
    log = IdempotencyLog(
        path, redactor=Redactor() if own_redactor else DEFAULT_REDACTOR
    )
    host = SendHost(tmp_path, log)
    runner = WorkflowRunner(engine_for(tmp_path, SEND), redactor=Redactor([WEBHOOK]))
    run = runner.start(
        "send_report",
        {"to": f"https://hooks.slack.com/services/{WEBHOOK}"},
        records="actions",
        now_ms=host.now_ms(),
    )
    result = runner.drive(run, host)
    assert result.ok, result
    assert host.transmitted == 1
    blob = path.read_bytes().decode()
    for secret in (KEY_ID, PASSWORD, BEARER, WEBHOOK):
        assert secret not in blob, secret
    done = [json.loads(line) for line in blob.splitlines()][-1]
    assert done["state"] == "done"
    assert all("digest" not in a for a in done["value"]["evidence_anchors"])
    assert done["value"]["receipt"] == {"Authorization": "[REDACTED]"}
    assert done["evidence_seen"] == [
        a["ref"] for a in done["value"]["evidence_anchors"]
    ]
    # The rollback lists the send without the registered secret.
    (item,) = result.outputs["rb"]["not_covered"]
    assert item["reason"] == "transmitted" and "[REDACTED]" in item["item"]
    places = kept(run, result)
    assert holding(places, KEY_ID, PASSWORD) == []
    # The snapshot keeps the run's inputs, the destination among them, as
    # the caller gave them; nothing the run wrote repeats it.
    del places["snapshot"]
    assert holding(places, WEBHOOK) == []
    # The shared default redactor never learns the runner's values.
    assert not DEFAULT_REDACTOR.redact_text(WEBHOOK)[1]


def test_a_replay_answers_with_the_redacted_output_and_passes_as_seen(
    tmp_path: Path,
) -> None:
    """A re-delivery after a restart is answered from the file: the output
    as it was submitted, still attested (§5.20), never transmitted again."""
    path = tmp_path / "keys.jsonl"
    action = {
        "kind": "InvokeCapability",
        "capability": "send",
        "idempotency_key": "r1:3",
        "inputs": {"destination": "ops", "payload": {}},
    }
    host = SendHost(tmp_path, IdempotencyLog(path))
    first = host.send_once(action, host.transmit)
    again = IdempotencyLog(path).perform(action, host.transmit)
    assert host.transmitted == 1
    text = json.dumps(again)
    assert KEY_ID not in text and PASSWORD not in text and BEARER not in text
    assert again["evidence_seen"] == [
        a["ref"] for a in again["value"]["evidence_anchors"]
    ]
    # The runner submits the first answer and the replay alike.
    from grounded_agency.workflows._responses import redact_anchors

    submitted = redact_anchors(DEFAULT_REDACTOR, first)
    assert submitted["value"]["evidence_anchors"] == again["value"]["evidence_anchors"]
    assert submitted["evidence_seen"] == again["evidence_seen"]


def test_two_anchors_one_after_redaction_replay_as_seen_only_when_both_were(
    tmp_path: Path,
) -> None:
    """The log keeps evidence_seen as the runner rewrites it: two signed
    URLs that are one ref once redacted are listed only when the host
    listed both, so a replay lets no unlisted anchor pass as seen."""
    first = f"https://u:{PASSWORD}@x.example.com/r"
    second = "https://u:An0therPassw0rdXYZ@x.example.com/r"
    for seen, listed in (
        ([first], []),
        ([first, second], ["https://u:[REDACTED]@x.example.com/r"]),
    ):
        log = IdempotencyLog(tmp_path / f"keys-{len(seen)}.jsonl")
        action = {
            "kind": "InvokeCapability",
            "capability": "send",
            "idempotency_key": f"r{len(seen)}:1",
            "inputs": {"destination": "ops"},
        }
        response = {
            "kind": "Output",
            "value": {
                "sent": True,
                "evidence_anchors": [
                    {"ref": first, "kind": "url"},
                    {"ref": second, "kind": "url"},
                ],
            },
            "evidence_seen": seen,
        }
        log.perform(action, lambda r=response: r)
        assert log.perform(action, lambda: {})["evidence_seen"] == listed


def test_the_runner_gives_its_secrets_to_the_hosts_memory_stores(
    tmp_path: Path,
) -> None:
    """A persist of a value the runner registered is refused by the host's
    memory store, as one the store recognises is (§5.18.10, §6.7)."""
    memory = MemoryStore()
    runner_memory = MemoryStore()
    runner = WorkflowRunner(
        engine_for(tmp_path, LOOK),
        redactor=Redactor([REGISTERED]),
        memory=runner_memory,
    )
    host = TupleHost(({"ref": "file:a.txt", "kind": "file"},))
    host.memory = memory
    run = runner.start("look", {}, now_ms=1_000)
    assert runner.drive(run, host).ok
    for store in (memory, runner_memory):
        assert store.redactor is not DEFAULT_REDACTOR
        assert store.redactor.holds_credential({"note": REGISTERED})
        # The default patterns still apply.
        assert store.redactor.holds_credential({"api_key": "sk-live-0123456789abcdef"})


class RaisingHost(Host):
    """A host whose call fails with an exception quoting what it was given."""

    def __init__(self, error: Exception) -> None:
        super().__init__(None)
        self.error = error

    def now_ms(self) -> int:
        return 1_000

    def invoke_capability(self, action: dict[str, Any]) -> dict[str, Any]:
        raise self.error


APIKEY = "VnVhQ2ZHY0JDZGJrUXctN1A6dWkybGp0YjU0"
PGP_BODY = "lQOYBGVhY2sBCADKx3mYq7vT2bN9cW4pLk8sR1fJ0dE6aH3gU5iO2yM7nB4"
PEM_BODY = "MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gunVTLw"


@pytest.mark.parametrize(
    ("error", "secret"),
    [
        (
            RuntimeError(
                "401 from GET https://es.internal:9200/_search with headers "
                f"{{'Authorization': 'ApiKey {APIKEY}'}}"
            ),
            APIKEY,
        ),
        (RuntimeError(f"curl -H 'Authorization: SSWS {APIKEY}' failed"), APIKEY),
        (
            ValueError(
                "cannot import signing key: -----BEGIN PGP PRIVATE KEY BLOCK-----"
                f"\n\n{PGP_BODY}\n=AbCd\n-----END PGP PRIVATE KEY BLOCK-----"
            ),
            PGP_BODY,
        ),
        (
            ValueError(
                f"cannot import key: -----BEGIN RSA PRIVATE KEY-----\n{PEM_BODY}"
            ),
            PEM_BODY,
        ),
    ],
    ids=["apikey_header", "ssws_header_line", "pgp_block", "pem_without_end"],
)
def test_a_host_error_quoting_a_header_or_a_key_keeps_none_of_it(
    tmp_path: Path, error: Exception, secret: str
) -> None:
    """An Authorization header with a scheme other than the five, an
    OpenPGP private key block and a PEM key cut before its end line are
    redacted in the R402 message, the trace, the records and the snapshot
    (security round 4, batch 5: the credential and the key bodies were
    kept)."""
    runner = WorkflowRunner(engine_for(tmp_path, LOOK))
    run = runner.start("look", {}, records="actions", now_ms=1_000)
    result = runner.drive(run, RaisingHost(error))
    assert result.code == "R402", result
    assert "[REDACTED]" in result.message
    assert holding(kept(run, result), secret) == []
