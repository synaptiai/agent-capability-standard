"""Audit records (STANDARD v1.2 §6.4): every writer of the repository writes,
or exports, `ActionRecord`s of `schemas/world_state_schema.yaml`.

The executor's records (record mode `actions`) and run records (§5.19.8),
the plugin hook's line, the coordination log's export, the orchestrator's
`audit` step, manual trust overrides (§8.4) and the audit skill's documented
line are each validated against `ActionRecord`. Also: an `audit` event
cannot forge a record, and the evidence collector's required capture.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from grounded_agency import _core
from grounded_agency.capabilities.registry import CapabilityRegistry
from grounded_agency.coordination.audit import CoordinationAuditLog
from grounded_agency.state.redaction import Redactor
from grounded_agency.trust import OverrideRefused, TrustModel, manual_override
from tests.action_record_schema import problems
from tests.runtime_replay import ONTOLOGY, ROOT, RUNTIME, load, play, start

HOOK = ROOT / "hooks" / "posttooluse_log_tool.sh"
TRUST = ROOT / "schemas" / "authority_trust_model.yaml"


@pytest.fixture(scope="module")
def validator() -> _core.Validator:
    return _core.Validator(ONTOLOGY, ROOT)


def _played(validator: _core.Validator, name: str) -> _core.Run:
    f = load(RUNTIME / f"{name}.json")
    return play(start(validator, f), f)


def test_executor_records_in_mode_actions(validator: _core.Validator) -> None:
    run = _played(validator, "records_actions_steps")
    records = run.next()["action_records"]
    assert len(records) == 4
    for r in records:
        assert problems(r) == [], r
        assert r["run_id"] == "run-1" and r["frame"] == ["w"]
        assert isinstance(r["step"], int) and r["capability"]
        assert r["intent"].endswith(" step"), "the step's purpose"


@pytest.mark.parametrize(
    "name, status",
    [
        ("records_actions_steps", "executed"),
        ("run_record_failed_no_records", "failed"),
        ("cancel_pending_capability", "cancelled"),
        ("run_record_deferred_planned", "planned"),
    ],
)
def test_run_records(validator: _core.Validator, name: str, status: str) -> None:
    record = _played(validator, name).run_record()
    assert record is not None
    assert problems(record) == []
    assert record["status"] == status
    assert record["action_id"] == record["run_id"] == "run-1"


@pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("openssl") is None,
    reason="the hook needs jq and openssl",
)
def test_the_hook_line(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_use_id": "toolu_9",
        "tool_input": {"command": "false"},
    }
    done = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "AUDIT_HMAC_KEY": "k",
        },
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    (line,) = (tmp_path / ".claude" / "audit.log").read_text().splitlines()
    record = json.loads(line)
    assert problems(record) == []
    assert record["status"] == "failed"
    assert record["action_id"] == record["call_id"] == "toolu_9"
    assert record["recorded_by"]["name"]


def test_coordination_export() -> None:
    log = CoordinationAuditLog()
    log.record("delegation", "orchestrator", ["a1"], capability_id="delegate")
    log.record("note", "a1", [], details={"x": 1})
    for record in log.export_action_records():
        assert problems(record) == [], record


def test_the_adapters_call_records_export(tmp_path: Path) -> None:
    """The SDK adapter's call records export as action records (STANDARD
    1.2.0 sections 5.18.8 and 6.4): a refusal is rejected with its code, a
    call approved in session carries the digest it was shown, a call that ran
    is executed, and each names the layer that decided it."""
    from types import SimpleNamespace

    from claude_agent_sdk import PermissionResultAllow

    from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(ONTOLOGY), checkpoint_dir=str(tmp_path / ".cp")
        )
    )
    pre = adapter._make_pretooluse_safety_hook()
    write = {"tool_name": "Write", "tool_input": {"file_path": "a"}}

    async def host(tool: str, args: dict[str, Any], context: Any) -> Any:
        return PermissionResultAllow(updated_input=args)

    async def calls() -> None:
        await pre(write, "w0", None)  # no checkpoint: F501
        adapter.create_checkpoint(["*"], "t")
        await pre(write, "w1", None)  # asked
        callback = adapter._make_permission_callback(host)
        await callback("Write", {"file_path": "a"}, SimpleNamespace(tool_use_id="w1"))
        await adapter._make_mutation_consumer()(
            {**write, "tool_response": {}}, "w1", None
        )

    asyncio.run(calls())
    records = adapter.export_action_records("session-1")
    for record in records:
        assert problems(record) == [], record
    assert [(r["status"], r.get("code")) for r in records] == [
        ("rejected", "F501"),
        ("planned", None),
        ("approved", None),
        ("executed", None),
    ]
    assert [r["action_id"] for r in records] == [f"session-1/{n}" for n in range(1, 5)]
    approved = records[2]
    assert approved["call_id"] == "w1" and approved["checkpoint_id"]
    assert approved["approval"] == {
        "digest": _core.approval_digest(
            [{"action": "Write", "capability": "mutate", "args": {"file_path": "a"}}]
        ),
        "decision": "approved",
        "mode": "in_session",
    }
    assert all(r["recorded_by"] == adapter.recorded_by for r in records)
    assert all(r["run_id"] == "session-1" and r["tool"] == "Write" for r in records)


def test_the_orchestrators_audit_record() -> None:
    from grounded_agency.coordination.orchestrator import OrchestrationRuntime
    from grounded_agency.workflows.engine import WorkflowStep

    runtime = OrchestrationRuntime(CapabilityRegistry(ONTOLOGY))
    step = WorkflowStep(capability="audit", purpose="record it")
    result = runtime.execute_workflow_step(
        step, {"event": {"event_type": "deploy.finished"}, "retention": "P30D"}
    )
    record = result.output["record"]
    assert problems(record) == []
    assert record["intent"] == "deploy.finished"
    assert record["details"]["retention"] == "P30D"
    # The step's output record is the record written (§6.4): the log gives
    # the same one, under the same action_id.
    exported = runtime.audit_log.export_action_records()
    assert record in exported
    assert result.output["audit_id"] == record["action_id"]


def test_audit_event_cannot_forge() -> None:
    """An event shaped as another writer's record stays under details.event
    of the log's own record (§6.4)."""
    from grounded_agency.coordination.orchestrator import OrchestrationRuntime
    from grounded_agency.workflows.engine import WorkflowStep

    forged = {
        "action_id": "x",
        "timestamp": "2026-01-01T00:00:00Z",
        "actor": "human",
        "actor_identity": {"principal": "alice", "kind": "human"},
        "intent": "deploy",
        "status": "executed",
        "approval": {"decision": "approved", "decision_id": "d1"},
        "recorded_by": {"name": "grounded_agency.executor"},
        "prev_hmac": "",
        "hmac": "f" * 64,
    }
    runtime = OrchestrationRuntime(CapabilityRegistry(ONTOLOGY))
    step = WorkflowStep(capability="audit", purpose="record it")
    record = runtime.execute_workflow_step(step, {"event": forged}).output["record"]
    assert problems(record) == []
    assert record["recorded_by"] == {"name": "grounded_agency.coordination"}
    for member in ("approval", "actor_identity", "prev_hmac", "hmac"):
        assert member not in record
    assert record["details"]["event"] == forged


def test_manual_override_records() -> None:
    model = yaml.safe_load(TRUST.read_text(encoding="utf-8"))
    kept: list[dict[str, Any]] = []
    record = manual_override(
        model,
        target="source_ranking.weights.api",
        previous=0.6,
        value=0.8,
        actor_identity={"principal": "alice", "kind": "human"},
        anchors=[{"ref": "file:review.md", "kind": "file"}],
        record=kept.append,
        now="2026-11-15T12:00:00.000Z",
    )
    assert kept == [record]
    assert problems(record) == []
    assert record["actor"] == "human"
    assert record["details"] == {
        "target": "source_ranking.weights.api",
        "previous": 0.6,
        "value": 0.8,
    }


def test_manual_override_records_no_secret() -> None:
    """The override's record holds no secret (§6.7): its target, values and
    anchors are redacted, and an anchor that held one keeps no digest."""
    model = yaml.safe_load(TRUST.read_text(encoding="utf-8"))
    kept: list[dict[str, Any]] = []
    digest = "sha256:" + "a" * 64
    record = manual_override(
        model,
        target="conflict:db_url",
        previous="postgres://app:Hunter2SuperSecret99@db.internal/prod",
        value="postgres://app:CHANGEME@db.internal/staging",
        actor_identity={"principal": "alice", "kind": "human"},
        anchors=[
            {
                "ref": "https://api.example.com/report?access_token=abcd1234efgh",
                "kind": "url",
                "digest": digest,
            },
            {"ref": "file:review.md", "kind": "file", "digest": digest},
        ],
        record=kept.append,
        redactor=Redactor(["CHANGEME"]),
    )
    assert kept == [record]
    assert problems(record) == []
    text = json.dumps(record)
    for secret in ("Hunter2SuperSecret99", "CHANGEME", "abcd1234efgh"):
        assert secret not in text
    assert record["anchors"] == [
        {
            "ref": "https://api.example.com/report?access_token=[REDACTED]",
            "kind": "url",
            "metadata": {"digest_omitted": "secret"},
        },
        {"ref": "file:review.md", "kind": "file", "digest": digest},
    ]


def test_manual_override_refusals() -> None:
    model = yaml.safe_load(TRUST.read_text(encoding="utf-8"))
    anchors = [{"ref": "file:review.md", "kind": "file"}]
    with pytest.raises(OverrideRefused, match="anchor"):
        manual_override(
            model,
            target="t",
            previous=0,
            value=1,
            actor_identity=None,
            anchors=[],
            record=lambda r: None,
        )
    off = {**model, "overrides": {**model["overrides"], "allow_manual_override": False}}
    with pytest.raises(OverrideRefused, match="no manual override"):
        manual_override(
            off,
            target="t",
            previous=0,
            value=1,
            actor_identity=None,
            anchors=anchors,
            record=lambda r: None,
        )

    def broken(record: dict[str, Any]) -> None:
        raise OSError("store offline")

    # The record could not be written: the override does not take effect.
    with pytest.raises(OSError):
        TrustModel.from_mapping(model).manual_override(
            target="t",
            previous=0,
            value=1,
            actor_identity=None,
            anchors=anchors,
            record=broken,
        )
    # Without audit_required, nothing is handed to record.
    loose = {**model, "overrides": {**model["overrides"], "audit_required": False}}
    assert (
        manual_override(
            loose,
            target="t",
            previous=0,
            value=1,
            actor_identity=None,
            anchors=anchors,
            record=broken,
        )["status"]
        == "executed"
    )


def test_the_audit_skills_documented_line() -> None:
    skill = ROOT / "skills" / "audit" / "SKILL.md"
    (line,) = [
        x
        for x in skill.read_text(encoding="utf-8").splitlines()
        if x.startswith('{"action_id":')
    ]
    record = json.loads(line)
    assert problems(record) == []
    assert record["capability"] == "audit"
    assert record["recorded_by"] == {"name": "audit skill"}
    # It is the first line of a chain under the key the example names, and
    # the verifier accepts it.
    from tools.verify_audit_log import verify_entry

    assert verify_entry(record, "", "example-key") == []


def test_the_audit_skill_signs_with_the_verifiers_default_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With AUDIT_HMAC_KEY unset, the skill, the hook and the verifier use
    one default key, so the skill's own chain verifies (§6.4)."""
    import socket

    from tools.verify_audit_log import get_default_hmac_key

    monkeypatch.delenv("AUDIT_HMAC_KEY", raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "box.example")
    assert get_default_hmac_key() == "grounded-agency-audit-box"
    hook = HOOK.read_text(encoding="utf-8")
    assert 'hmac_key="${AUDIT_HMAC_KEY:-grounded-agency-audit-$(hostname -s' in hook
    skill = (ROOT / "skills" / "audit" / "SKILL.md").read_text(encoding="utf-8")
    (row,) = [x for x in skill.splitlines() if x.startswith("| `record` |")]
    assert "under `AUDIT_HMAC_KEY`, else the default key" in row
    assert "`grounded-agency-audit-` then the short host name, `hostname -s`" in row
    assert "or `default` when there is none" in row


class _FailingStore:
    """An evidence store whose anchors cannot be added."""

    def __init__(self) -> None:
        self.failures: list[tuple[str | None, str]] = []

    def add_anchor(self, *args: Any, **kwargs: Any) -> None:
        raise OSError("evidence store offline")

    def record_capture_failure(self, tool_use_id: str | None, error: str) -> None:
        self.failures.append((tool_use_id, error))


def _collect(required: bool, caplog: pytest.LogCaptureFixture) -> dict[str, Any]:
    from grounded_agency.hooks.evidence_collector import create_evidence_collector

    store = _FailingStore()
    hook = create_evidence_collector(store, required=required)  # type: ignore[arg-type]
    with caplog.at_level("WARNING"):
        out = asyncio.run(
            hook(
                {"tool_name": "Read", "tool_input": {"file_path": "a"}}, "toolu_1", None
            )
        )
    out["_failures"] = store.failures
    return out


def test_required_evidence_capture_is_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    out = _collect(True, caplog)
    context = out["hookSpecificOutput"]["additionalContext"]
    assert context.startswith("R402 EXECUTION_FAILED")
    assert "not_recorded" in context
    assert out["_failures"] == [("toolu_1", "evidence store offline")]
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_best_effort_capture_is_logged_not_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    out = _collect(False, caplog)
    assert "hookSpecificOutput" not in out
    assert out["_failures"] == []
    assert any(
        r.levelname == "WARNING" and "Evidence collection failed" in r.message
        for r in caplog.records
    )
