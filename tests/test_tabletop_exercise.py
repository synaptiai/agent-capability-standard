"""The tabletop exercise of docs/compliance/nist-ai-rmf/tabletop_exercise_template.md,
played against the plugin's hooks: an approved Write through the plugin that
must be undone, and its injects. Each step runs the hook or the command the template names and
checks the outcome the template gives, and every code and command the steps
use is checked to appear in the template, so the template stays true."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
PRE = HOOKS / "pretooluse_require_checkpoint.sh"
TAKE = HOOKS / "posttooluse_take_checkpoint.sh"
LOG = HOOKS / "posttooluse_log_tool.sh"
STOP = HOOKS / "stop_end_checkpoints.sh"
TEMPLATE = (
    ROOT / "docs" / "compliance" / "nist-ai-rmf" / "tabletop_exercise_template.md"
)

sys.path.insert(0, str(ROOT / "tools"))
from verify_audit_log import verify_log  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None
    or shutil.which("jq") is None
    or shutil.which("git") is None,
    reason="the hooks need bash, jq and git",
)

KEY = "tabletop-exercise-key"
BEFORE = "v1\nwork in progress\n"
BAD = "overwritten by the agent\n"

# The codes and commands of the template, as it writes them.
F501 = "F501 CHECKPOINT_REQUIRED"
F502 = "F502 APPROVAL_REQUIRED"
TAKE_CHECKPOINT = 'git stash create "checkpoint: before rewrite"'
USED_NAME = "used/<checkpoint_id>.<call_id>."
AGENT_RESTORE = "git stash apply <commit>"
RESTORE_WORKTREE = "git restore --source=<commit> --worktree -- notes.txt"
RESTORE_INDEX = "git restore --source=<commit>^2 --staged -- notes.txt"
CHECK_RESTORED = "git diff --quiet <commit> -- notes.txt"
VERIFY_LOG = "python tools/verify_audit_log.py"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _hook(
    script: Path, payload: dict[str, Any], project: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(project),
            "AUDIT_HMAC_KEY": KEY,
        },
        timeout=60,
        cwd=project,
    )


def _shell(project: Path, command: str) -> subprocess.CompletedProcess[str]:
    """A command the operator runs in their own terminal, outside the hooks."""
    return subprocess.run(
        ["bash", "-c", command],
        cwd=project,
        env={**os.environ, **_GIT_ENV},
        capture_output=True,
        text=True,
        timeout=60,
    )


def _pre(
    project: Path, tool: str, tool_input: dict[str, Any], call_id: str, mode: str
) -> subprocess.CompletedProcess[str]:
    return _hook(
        PRE,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_use_id": call_id,
            "permission_mode": mode,
            "cwd": str(project),
            "tool_input": tool_input,
        },
        project,
    )


def _write_input(project: Path) -> dict[str, Any]:
    return {"file_path": str(project / "notes.txt"), "content": BAD}


def _take_checkpoint(project: Path, call_id: str) -> str:
    """Step 2: the agent's `git stash create`, through both hooks."""
    allowed = _pre(project, "Bash", {"command": TAKE_CHECKPOINT}, call_id, "default")
    assert allowed.returncode == 0, allowed.stderr
    assert "permissionDecision" not in allowed.stdout, allowed.stdout
    commit = _shell(project, TAKE_CHECKPOINT).stdout.strip()
    assert len(commit) == 40
    taken = _hook(
        TAKE,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_use_id": call_id,
            "cwd": str(project),
            "tool_input": {"command": TAKE_CHECKPOINT},
            "tool_response": {"stdout": commit + "\n", "stderr": ""},
        },
        project,
    )
    assert taken.returncode == 0, taken.stderr
    marker = json.loads((project / ".claude" / "checkpoint.ok").read_text())
    assert marker["commit"] == commit
    return commit


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """The exercise's repository: notes.txt committed, then changed and not
    yet committed, the work the agent's Write overwrites."""
    (tmp_path / "notes.txt").write_text("v1\n")
    for args in (["init", "-q"], ["add", "notes.txt"], ["commit", "-q", "-m", "init"]):
        subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            env={**os.environ, **_GIT_ENV},
            check=True,
            capture_output=True,
        )
    (tmp_path / "notes.txt").write_text(BEFORE)
    return tmp_path


def test_the_template_names_every_code_and_command_the_exercise_runs() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for expected in (
        F501,
        F502,
        TAKE_CHECKPOINT,
        USED_NAME,
        AGENT_RESTORE,
        RESTORE_WORKTREE,
        RESTORE_INDEX,
        CHECK_RESTORED,
        VERIFY_LOG,
        "bypassPermissions",
    ):
        assert expected in text, expected


def test_an_approved_write_is_traced_to_its_checkpoint_and_undone(
    project: Path,
) -> None:
    # Step 1: the Write with no checkpoint is refused, and nothing changes.
    refused = _pre(project, "Write", _write_input(project), "toolu_tt_01", "default")
    assert refused.returncode == 2
    assert refused.stderr.startswith(F501), refused.stderr
    assert (project / "notes.txt").read_text() == BEFORE

    # Step 2: the agent takes a checkpoint.
    commit = _take_checkpoint(project, "toolu_tt_02")

    # Step 3: the Write uses the checkpoint and asks the person.
    asked = _pre(project, "Write", _write_input(project), "toolu_tt_03", "default")
    assert asked.returncode == 0, asked.stderr
    decision = json.loads(asked.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "ask"
    assert decision["permissionDecisionReason"].startswith(F502)
    assert not (project / ".claude" / "checkpoint.ok").exists()
    used = sorted((project / ".claude" / "checkpoints" / "used").iterdir())
    assert [p.name.rsplit(".", 1)[0] for p in used] == [f"{commit}.toolu_tt_03"]

    # The person approves; the Write runs and the log hook records it.
    (project / "notes.txt").write_text(BAD)
    logged = _hook(
        LOG,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_use_id": "toolu_tt_03",
            "cwd": str(project),
            "tool_input": _write_input(project),
            "tool_response": {},
        },
        project,
    )
    assert logged.returncode == 0, logged.stderr

    # Step 4: from the audit line to the restore point.
    lines = [
        json.loads(line)
        for line in (project / ".claude" / "audit.log").read_text().splitlines()
    ]
    writes = [e for e in lines if e["tool"] == "Write" and e["status"] == "executed"]
    assert len(writes) == 1
    call_id = writes[0]["call_id"]
    assert call_id == "toolu_tt_03"
    (marker_file,) = (project / ".claude" / "checkpoints" / "used").glob(
        f"*.{call_id}.*"
    )
    assert marker_file.name.startswith(f"{commit}.{call_id}.")
    restore_point = json.loads(marker_file.read_text())["commit"]
    assert restore_point == commit

    # Step 5: the agent's own restore is a rollback, but git refuses it over
    # the changed file; the operator restores from their terminal.
    agent_restore = AGENT_RESTORE.replace("<commit>", commit)
    rollback = _pre(
        project, "Bash", {"command": agent_restore}, "toolu_tt_05", "default"
    )
    assert rollback.returncode == 0, rollback.stderr
    assert "permissionDecision" not in rollback.stdout, rollback.stdout
    assert _shell(project, agent_restore).returncode != 0
    assert (project / "notes.txt").read_text() == BAD
    for command in (RESTORE_WORKTREE, RESTORE_INDEX):
        done = _shell(project, command.replace("<commit>", commit))
        assert done.returncode == 0, done.stderr
    assert (project / "notes.txt").read_text() == BEFORE

    # Step 6: the restore is checked and the log verifies.
    assert _shell(project, CHECK_RESTORED.replace("<commit>", commit)).returncode == 0
    valid, total, errors = verify_log(
        project / ".claude" / "audit.log",
        KEY,
        head_path=project / ".claude" / "audit.head",
    )
    assert errors == []
    assert valid == total == 1


def test_the_same_write_is_refused_where_no_person_can_approve(project: Path) -> None:
    """Inject: the session runs in bypassPermissions mode."""
    _take_checkpoint(project, "toolu_tt_10")
    refused = _pre(
        project, "Write", _write_input(project), "toolu_tt_11", "bypassPermissions"
    )
    assert refused.returncode == 2
    assert refused.stderr.startswith(F502), refused.stderr
    assert (project / "notes.txt").read_text() == BEFORE


def test_an_expired_checkpoint_refuses_the_write_but_still_restores(
    project: Path,
) -> None:
    """Inject: the checkpoint is more than 30 minutes old."""
    commit = _take_checkpoint(project, "toolu_tt_20")
    marker = project / ".claude" / "checkpoint.ok"
    content = json.loads(marker.read_text())
    content["created_at"] -= 3600
    content["expires_at"] -= 3600
    marker.write_text(json.dumps(content))
    refused = _pre(project, "Write", _write_input(project), "toolu_tt_21", "default")
    assert refused.returncode == 2
    assert refused.stderr.startswith(F501), refused.stderr
    (project / "notes.txt").write_text(BAD)
    for command in (RESTORE_WORKTREE, RESTORE_INDEX):
        assert _shell(project, command.replace("<commit>", commit)).returncode == 0
    assert (project / "notes.txt").read_text() == BEFORE


def test_a_turn_that_ends_files_the_checkpoint_under_ended(project: Path) -> None:
    """Inject: a turn ends between steps 2 and 3."""
    _take_checkpoint(project, "toolu_tt_30")
    stopped = _hook(STOP, {"hook_event_name": "Stop"}, project)
    assert stopped.returncode == 0, stopped.stderr
    assert not (project / ".claude" / "checkpoint.ok").exists()
    assert len(list((project / ".claude" / "checkpoints" / "ended").iterdir())) == 1
    refused = _pre(project, "Write", _write_input(project), "toolu_tt_31", "default")
    assert refused.returncode == 2
    assert refused.stderr.startswith(F501), refused.stderr


def test_a_deleted_last_line_is_reported(project: Path) -> None:
    """Inject: the audit log's last line is deleted."""
    for n in range(2):
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_use_id": f"toolu_tt_4{n}",
            "cwd": str(project),
            "tool_input": {"file_path": str(project / "notes.txt")},
            "tool_response": {},
        }
        assert _hook(LOG, payload, project).returncode == 0
    log = project / ".claude" / "audit.log"
    log.write_text(log.read_text().splitlines(keepends=True)[0])
    _, _, errors = verify_log(log, KEY, head_path=project / ".claude" / "audit.head")
    assert errors
    payload["tool_use_id"] = "toolu_tt_42"
    reported = _hook(LOG, payload, project)
    assert "no longer holds the entry its head records" in reported.stderr
