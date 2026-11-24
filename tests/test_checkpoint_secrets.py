"""A checkpoint is the safety layer's record of the call that took it
(STANDARD 1.2.0 §5.18.8), and a bound checkpoint tool's ``reason`` and
``scope`` are text a model wrote: the tracker redacts every string it
records, so no secret its redactor recognises reaches its records in
memory, its state file or its archive (§6.7; security round 3, batch 5).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.capabilities.mapper import ToolCapabilityMapper
from grounded_agency.hooks.skill_tracker import create_checkpoint_recorder
from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.state.redaction import DEFAULT_REDACTOR, Redactor
from grounded_agency.state.snapshots import FileSnapshotStore
from grounded_agency.workflows import Host, WorkflowEngine, WorkflowRunner

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = str(ROOT / "schemas" / "capability_ontology.yaml")

TOOL = "mcp__ops__save_point"
PASSWORD = "Hunter2Hunter2xyz"
GITHUB = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
URL_PASSWORD = "S3cretPassw0rd99"
REGISTERED = "RegisteredHostSecretValue9876"
REASON = f"before rotating DB_PASSWORD={PASSWORD} and token {GITHUB}"
SCOPE = f"postgres://admin:{URL_PASSWORD}@db.internal/prod"


def _mapper() -> ToolCapabilityMapper:
    mapper = ToolCapabilityMapper()
    mapper.register_binding(
        {
            "tool": TOOL,
            "capability": "checkpoint",
            "ontology": "2.2.0",
            "standard": "1.2.0",
        }
    )
    return mapper


def _files(where: Path) -> str:
    """Every file under ``where``, as text."""
    return "\n".join(
        p.read_text(errors="replace") for p in sorted(where.rglob("*")) if p.is_file()
    )


def _holding(text: str, *secrets: str) -> list[str]:
    return [s for s in secrets if s in text]


def test_the_recorder_writes_no_secret_of_a_bound_tools_reason_or_scope(
    tmp_path: Path,
) -> None:
    """The reported probe: a bound checkpoint tool's reason holds a password
    assignment and a GitHub token, its scope a URL's password. The
    checkpoint is taken, and neither the tracker's records nor its state
    file hold them."""
    tracker = CheckpointTracker(checkpoint_dir=tmp_path / ".checkpoints")
    hook = create_checkpoint_recorder(tracker, _mapper())
    asyncio.run(
        hook(
            {
                "tool_name": TOOL,
                "tool_input": {"reason": REASON, "scope": [SCOPE, "src/*.py"]},
                "tool_response": {"content": [{"type": "text", "text": "{}"}]},
            },
            "toolu_1",
            None,
        )
    )
    assert tracker.checkpoint_count == 1
    checkpoint = tracker.get_active_checkpoint()
    assert checkpoint is not None
    assert (
        checkpoint.reason
        == "before rotating DB_PASSWORD=[REDACTED] and token [REDACTED]"
    )
    assert checkpoint.scope == [
        "postgres://admin:[REDACTED]@db.internal/prod",
        "src/*.py",
    ]
    assert checkpoint.metadata == {"source": TOOL, "tool_use_id": "toolu_1"}
    assert _holding(_files(tmp_path), PASSWORD, GITHUB, URL_PASSWORD) == []


def test_a_reason_and_scope_without_a_secret_are_kept_as_given(tmp_path: Path) -> None:
    tracker = CheckpointTracker(checkpoint_dir=tmp_path / ".checkpoints")
    hook = create_checkpoint_recorder(tracker, _mapper())
    asyncio.run(
        hook(
            {
                "tool_name": TOOL,
                "tool_input": {"reason": "before the refactor", "scope": "src/*.py"},
                "tool_response": {"content": [{"type": "text", "text": "{}"}]},
            },
            "toolu_1",
            None,
        )
    )
    checkpoint = tracker.get_active_checkpoint()
    assert checkpoint is not None
    assert (checkpoint.reason, checkpoint.scope) == (
        "before the refactor",
        ["src/*.py"],
    )
    state = json.loads((tmp_path / ".checkpoints" / "tracker_state.json").read_text())
    assert state["active"]["reason"] == "before the refactor"
    assert state["active"]["scope"] == ["src/*.py"]


async def _run_hooks(
    hooks: dict[str, Any], event: str, payload: dict[str, Any]
) -> list[Any]:
    results = []
    for matcher in hooks.get(event, []):
        for hook in matcher.hooks:
            results.append(await hook(payload, "toolu_1", {"signal": None}))
    return results


def test_the_adapter_redacts_with_the_hosts_registered_secrets(tmp_path: Path) -> None:
    """End to end through wrap_options: a registered secret, a password
    assignment, a GitHub token and a URL's password in the call's reason and
    scope reach neither the checkpoint in memory nor any file the layer
    writes, and the call still takes its checkpoint."""
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ONTOLOGY,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            audit_log_path=str(tmp_path / "audit.log"),
            secret_values=(REGISTERED,),
        )
    )
    adapter.mapper.register_binding(
        {
            "tool": TOOL,
            "capability": "checkpoint",
            "ontology": "2.2.0",
            "standard": "1.2.0",
        }
    )
    options = adapter.wrap_options(ClaudeAgentOptions(permission_mode="default"))
    tool_input = {"reason": f"{REASON} and {REGISTERED}", "scope": SCOPE}
    output = {
        "checkpoint_id": "sp-1",
        "evidence_anchors": [{"kind": "tool_output", "ref": "tool:save_point/sp-1"}],
        "mechanism": "store_snapshot",
    }
    pre = {
        "hook_event_name": "PreToolUse",
        "tool_name": TOOL,
        "tool_input": tool_input,
        "session_id": "s1",
        "cwd": str(tmp_path),
    }
    post = {
        **pre,
        "hook_event_name": "PostToolUse",
        "tool_response": {"content": [{"type": "text", "text": json.dumps(output)}]},
    }
    asyncio.run(_run_hooks(options.hooks, "PreToolUse", pre))
    asyncio.run(_run_hooks(options.hooks, "PostToolUse", post))
    assert adapter.checkpoint_tracker.checkpoint_count == 1
    checkpoint = adapter.checkpoint_tracker.get_active_checkpoint()
    assert checkpoint is not None
    secrets = (PASSWORD, GITHUB, URL_PASSWORD, REGISTERED)
    assert _holding(json.dumps(checkpoint.to_dict()), *secrets) == []
    assert checkpoint.reason.endswith("and [REDACTED]")
    assert _holding(_files(tmp_path), *secrets) == []
    assert adapter.checkpoint_tracker.redactor is adapter.redactor
    # The registered value reaches no redactor other adapters share.
    assert not DEFAULT_REDACTOR.redact_text(REGISTERED)[1]


def test_the_archive_and_the_words_that_end_or_use_a_checkpoint_are_redacted(
    tmp_path: Path,
) -> None:
    """Every string the tracker records: a checkpoint's metadata, the reason
    an execution boundary gives, the holder that used it, and the pruned
    checkpoints it archives (a tracker on the default patterns)."""
    tracker = CheckpointTracker(checkpoint_dir=tmp_path / ".checkpoints", max_history=1)
    for n in range(3):
        tracker.create_checkpoint(
            [SCOPE],
            f"{n}: {REASON}",
            metadata={"note": f"Authorization: Bearer {GITHUB}", "n": n},
        )
    # A boundary ends the held checkpoint; the hold then uses it.
    assert tracker.validate_and_reserve(f"call {GITHUB}")[0]
    tracker.end_validity(f"turn ended token={PASSWORD}")
    assert tracker.consume_if_valid(f"call {GITHUB}") is None
    tracker.create_checkpoint(["*"], "next")
    archive = tmp_path / ".checkpoints" / "archive" / "pruned_checkpoints.jsonl"
    assert archive.is_file()
    archived = tracker.get_archived_checkpoints()
    every = archived + tracker.get_history(limit=100)
    text = _files(tmp_path) + json.dumps([c.to_dict() for c in every])
    assert _holding(text, PASSWORD, GITHUB, URL_PASSWORD) == []
    assert len(archived) == 2
    assert all(
        c.metadata["note"] == "Authorization: Bearer [REDACTED]" for c in archived
    )
    assert {c.metadata.get("invalidated_by") for c in every if c.invalidated_at} == {
        "turn ended token=[REDACTED]"
    }
    assert [c.metadata["consumed_by"] for c in every if c.consumed] == [
        "ended hold of call [REDACTED]"
    ]


def test_a_snapshot_captures_what_the_scope_names_as_given(tmp_path: Path) -> None:
    """Redaction is of the record: the content store captures the files the
    scope names, a secret in the name included, and the restore still finds
    them."""
    root = tmp_path / "work"
    for name, redactor in (
        (f"token={PASSWORD}", None),
        (REGISTERED, Redactor([REGISTERED])),
    ):
        (root / name).mkdir(parents=True)
        (root / name / "a.txt").write_text("one")
        store = tmp_path / "snapshots" / str(len(name))
        tracker = CheckpointTracker(
            checkpoint_dir=tmp_path / ".checkpoints" / str(len(name)),
            snapshots=FileSnapshotStore(root, store),
            **({} if redactor is None else {"redactor": redactor}),
        )
        checkpoint_id = tracker.create_checkpoint([name], "before the change")
        checkpoint = tracker.get_checkpoint_by_id(checkpoint_id)
        assert checkpoint is not None
        assert checkpoint.scope == [tracker.redactor.redact_text(name)[0]] != [name]
        assert tracker.checkpoint_output(checkpoint_id)["captured"] == [f"{name}/a.txt"]
        (root / name / "a.txt").write_text("two")
        tracker.restore_checkpoint(checkpoint_id)
        assert (root / name / "a.txt").read_text() == "one"
        state = tmp_path / ".checkpoints" / str(len(name)) / "tracker_state.json"
        assert PASSWORD not in state.read_text() and REGISTERED not in state.read_text()


SAVE = """\
# Standard version: 1.2.0
save_state:
  goal: Save the state.
  risk: low
  inputs:
    where:
      type: string
      required: true
  steps:
  - capability: checkpoint
    purpose: Save the agent's state.
    store_as: cp
    input_bindings:
      scope: ${where}
"""


@pytest.mark.parametrize("own_redactor", [False, True])
def test_the_runner_gives_its_secrets_to_the_hosts_tracker(
    tmp_path: Path, own_redactor: bool
) -> None:
    """A checkpoint step's scope is the step's input: the tracker of the
    host the runner drives records it without the runner's registered
    secrets, whether it has the default redactor or one of its own."""
    root = tmp_path / "work"
    root.mkdir()
    (root / "a.txt").write_text("x")
    tracker = CheckpointTracker(
        checkpoint_dir=tmp_path / ".checkpoints",
        snapshots=FileSnapshotStore(root, tmp_path / "snapshots"),
        **({"redactor": Redactor()} if own_redactor else {}),
    )
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(SAVE)
    engine = WorkflowEngine(ONTOLOGY, schema_root=str(ROOT))
    engine.load_catalog(catalog)
    runner = WorkflowRunner(engine, redactor=Redactor([REGISTERED]))
    host = Host(tracker)
    run = runner.start(
        "save_state", {"where": f"notes/{REGISTERED} {SCOPE}"}, now_ms=host.now_ms()
    )
    result = runner.drive(run, host)
    assert result.ok, result
    assert tracker.checkpoint_count == 1
    state = (tmp_path / ".checkpoints" / "tracker_state.json").read_text()
    assert _holding(state, REGISTERED, URL_PASSWORD) == []
    checkpoint = tracker.get_active_checkpoint()
    assert checkpoint is not None
    assert checkpoint.scope == [
        "notes/[REDACTED]",
        "postgres://admin:[REDACTED]@db.internal/prod",
    ]
    # The shared default redactor never learns the runner's values.
    assert not DEFAULT_REDACTOR.redact_text(REGISTERED)[1]
