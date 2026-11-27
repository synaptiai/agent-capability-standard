"""The invariant monitor, tools/check_audit_invariants.py (issue #172, part
A), on fixture logs: each gated call that ran with no used checkpoint
marker, and each executed mutate or send in the adapter's records without a
checkpoint and an approval, is printed with its call id and fails the
check; approval off, a configuration change and a high refusal rate are
anomalies."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.adapter import call_action_record

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_audit_invariants as monitor  # noqa: E402

TOOL = ROOT / "tools" / "check_audit_invariants.py"
POSTTOOLUSE_HOOK = ROOT / "hooks" / "posttooluse_log_tool.sh"
PRETOOLUSE_HOOK = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
KEY = "test-key-for-the-invariant-monitor"
CONFIG = "a" * 64


def line(
    tool: str,
    call_id: str | None,
    status: str = "executed",
    approval: str = "ask",
    config: str = CONFIG,
) -> dict[str, Any]:
    """A log line as the hook writes it (chain fields left empty: the
    monitor does not verify the chain unless asked)."""
    entry: dict[str, Any] = {
        "action_id": call_id or "1764200000-123-abcdef01",
        "timestamp": "2026-11-27T10:00:00Z",
        "actor": "agent",
        "intent": f"{tool} call",
        "status": status,
        "tool": tool,
    }
    if call_id is not None:
        entry["call_id"] = call_id
    entry["details"] = {"event": "PostToolUse", "input_sha256": "0" * 64}
    entry["recorded_by"] = {
        "name": "agent-capability-standard plugin hooks",
        "version": "3.0.0",
        "config_sha256": config,
        "settings": {"approval": approval, "checkpoint_max_age_s": 1800},
    }
    entry["prev_hmac"] = ""
    entry["hmac"] = ""
    return entry


def project_with(
    tmp_path: Path, lines: list[dict[str, Any]], markers: list[str] = ()
) -> Path:
    claude = tmp_path / ".claude"
    used = claude / "checkpoints" / "used"
    used.mkdir(parents=True)
    log = claude / "audit.log"
    log.write_text(
        "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in lines),
        encoding="utf-8",
    )
    for name in markers:
        (used / name).write_text("{}\n")
    return log


def cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=60,
    )


class TestThePluginLog:
    def test_every_gated_call_with_a_marker_passes(self, tmp_path: Path) -> None:
        log = project_with(
            tmp_path,
            [
                line("Read", "toolu_r"),
                line("Write", "toolu_w"),
                line("Edit", "toolu_e", status="failed"),
                line("mcp__github__create_issue", "toolu_m"),
                line("Skill", "toolu_s"),
                line("Bash", "toolu_b1"),
                line("Bash", "toolu_b2"),
            ],
            [
                "cp_1.toolu_w.Ab12Cd",
                "cp.2.toolu_e.XyZ987",
                "cp_3.toolu_m.q1w2e3",
                "cp_4.toolu_s.r4t5y6",
                "cp_5.toolu_b1.u7i8o9",
            ],
        )
        report = monitor.run(log, None)
        assert report.violations == [] and report.anomalies == []
        assert (report.bash_with_marker, report.bash_without_marker) == (1, 1)
        assert report.by_tool["Bash"] == 2
        assert report.by_status == {"executed": 6, "failed": 1}
        assert report.by_settings == {"approval=ask, checkpoint_max_age_s=1800": 7}
        result = cli("--log-file", str(log))
        assert result.returncode == 0, result.stdout
        assert "INVARIANT CHECK PASSED" in result.stdout

    def test_a_gated_call_with_no_marker_is_printed_with_its_call_id(
        self, tmp_path: Path
    ) -> None:
        log = project_with(
            tmp_path,
            [
                line("Write", "toolu_ok"),
                line("Write", "toolu_unchecked"),
                line("mcp__slack__post", "toolu_mcp"),
                line("[REDACTED]", "toolu_unbound", status="failed"),
                line("NotebookEdit", None),
            ],
            # A marker for another call does not count, nor one whose
            # call id only begins the same way.
            ["cp_1.toolu_ok.Ab12Cd", "cp_2.toolu_unchecked_x.Ab12Cd"],
        )
        report = monitor.run(log, None)
        flagged = [
            (v["tool"], v["call_id"])
            for v in report.violations
            if v["rule"] == "gated_call_without_checkpoint"
        ]
        assert flagged == [
            ("Write", "toolu_unchecked"),
            ("mcp__slack__post", "toolu_mcp"),
            ("[REDACTED]", "toolu_unbound"),
            ("NotebookEdit", None),
        ]
        assert report.unmatched_markers == ["cp_2.toolu_unchecked_x.Ab12Cd"]
        result = cli("--log-file", str(log))
        assert result.returncode == 1
        for call in ("toolu_unchecked", "toolu_mcp", "toolu_unbound"):
            assert f"call {call}: " in result.stdout
        assert "call (no call id): NotebookEdit executed" in result.stdout
        assert "INVARIANT CHECK FAILED" in result.stdout

    def test_a_call_id_the_hook_kept_safe_is_matched(self, tmp_path: Path) -> None:
        call = "toolu/with:odd chars"
        log = project_with(
            tmp_path, [line("Write", call)], [f"cp.{monitor.safe(call)}.Ab12Cd"]
        )
        assert monitor.run(log, None).violations == []

    def test_approval_off_and_a_configuration_change_are_anomalies(
        self, tmp_path: Path
    ) -> None:
        log = project_with(
            tmp_path,
            [
                line("Read", "toolu_1"),
                line("Read", "toolu_2", config="b" * 64),
                line("Write", "toolu_3", approval="off", config="b" * 64),
            ],
            ["cp.toolu_3.Ab12Cd"],
        )
        report = monitor.run(log, None)
        assert report.violations == []
        assert [(a["rule"], a["call_id"]) for a in report.anomalies] == [
            ("config_changed", "toolu_2"),
            ("approval_off", "toolu_3"),
        ]
        assert report.config_transitions[0]["after_line"] == 1
        assert report.config_transitions[0]["line"] == 2
        result = cli("--log-file", str(log), "--json")
        assert result.returncode == 1
        assert len(json.loads(result.stdout)["anomalies"]) == 2

    def test_an_unreadable_line_is_a_violation_and_older_entries_are_counted(
        self, tmp_path: Path
    ) -> None:
        log = project_with(tmp_path, [line("Read", "toolu_1")])
        with log.open("a", encoding="utf-8") as f:
            f.write(
                '{"ts":"2026-01-30T12:00:00Z","event":"PostToolUse","tool":"Write"}\n'
            )
            f.write("not json\n")
        report = monitor.run(log, None)
        assert report.older_entries == 1
        assert [v["rule"] for v in report.violations] == ["unreadable_line"]

    def test_no_log_is_not_run(self, tmp_path: Path) -> None:
        result = cli("--log-file", str(tmp_path / "audit.log"))
        assert result.returncode == 2
        assert "INVARIANT CHECK NOT RUN" in result.stdout


def call_record(
    seq: int,
    tool: str,
    capability: str | None,
    decision: str,
    call: str,
    **extra: Any,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "seq": seq,
        "at": "2026-11-27T10:00:00Z",
        "tool": tool,
        "capability": capability,
        "call": call,
        "decision": decision,
        "recorded_by": {"name": "grounded-agency", "version": "1.0.0"},
        **extra,
    }
    record = call_action_record(entry, "session-1")
    assert record is not None
    return record


class TestTheAdaptersRecords:
    def write(self, tmp_path: Path, records: list[dict[str, Any]]) -> Path:
        path = tmp_path / "records.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        return path

    def test_a_checked_and_approved_mutate_passes(self, tmp_path: Path) -> None:
        records = [
            call_record(
                1,
                "Write",
                "mutate",
                "allowed",
                "toolu_1",
                checkpoint_id="chk_1",
                approvers=["in_session"],
                digest="d" * 64,
            ),
            call_record(2, "Write", "mutate", "ran", "toolu_1", checkpoint_id="chk_1"),
            call_record(3, "Read", "retrieve", "allowed", "toolu_2"),
            call_record(4, "Read", "retrieve", "ran", "toolu_2"),
        ]
        report = monitor.run(None, None, [self.write(tmp_path, records)])
        assert report.violations == [] and report.anomalies == []
        assert report.records == 4 and report.seq_gaps == []

    def test_an_executed_gated_call_without_a_checkpoint_or_approval_fails(
        self, tmp_path: Path
    ) -> None:
        records = [
            call_record(1, "Write", "mutate", "ran", "toolu_1", checkpoint_id="chk_1"),
            call_record(2, "Bash", "send", "ran", "toolu_2"),
            call_record(3, "mcp__x__y", None, "ran", "toolu_3"),
            call_record(4, "Skill", "invoke", "ran", "toolu_4"),
            call_record(6, "Bash", "observe", "ran", "toolu_5"),
        ]
        path = self.write(tmp_path, records)
        report = monitor.run(None, None, [path])
        assert [(v["call_id"], v["missing"]) for v in report.violations] == [
            ("toolu_1", ["approval"]),
            ("toolu_2", ["checkpoint_id", "approval"]),
            ("toolu_3", ["checkpoint_id", "approval"]),
            ("toolu_4", ["checkpoint_id", "approval"]),
        ]
        assert report.seq_gaps == [{"run_id": "session-1", "after": 4, "next": 6}]
        result = cli("--records", str(path))
        assert result.returncode == 1
        assert (
            "call toolu_2: Bash (capability send) executed with no checkpoint_id and no approval"
            in result.stdout
        )

    def test_a_refusal_rate_above_the_threshold_is_an_anomaly(
        self, tmp_path: Path
    ) -> None:
        records = [
            call_record(1, "Write", "mutate", "refused", "toolu_1"),
            call_record(2, "Read", "retrieve", "allowed", "toolu_2"),
            call_record(3, "Read", "retrieve", "ran", "toolu_2"),
        ]
        path = self.write(tmp_path, records)
        report = monitor.run(None, None, [path])
        assert [a["rule"] for a in report.anomalies] == ["refusal_rate"]
        assert monitor.run(None, None, [path], max_refusal_rate=0.5).anomalies == []
        # One record per line reads the same.
        lines = tmp_path / "records.jsonl"
        lines.write_text("".join(json.dumps(r) + "\n" for r in records))
        assert monitor.run(None, None, [lines]).refusals == 1

    def test_records_that_are_not_json_are_not_run(self, tmp_path: Path) -> None:
        path = tmp_path / "records.json"
        path.write_text("[not json")
        result = cli("--records", str(path))
        assert result.returncode == 2


def test_the_ungated_tools_are_the_pretooluse_hooks() -> None:
    """The monitor's list of the tools the hook lets pass by name is the
    hook's own."""
    text = PRETOOLUSE_HOOK.read_text(encoding="utf-8")
    match = re.search(r"^UNGATED_TOOLS=\(([^)]*)\)", text, re.MULTILINE)
    assert match is not None
    assert set(match.group(1).split()) == monitor.UNGATED_TOOLS


@pytest.mark.parametrize(
    "call_id",
    ["toolu_01AbC", "toolu/with:odd chars", "toolu_é_ü", "x" * 130, "a.b-c_d"],
)
def test_a_call_id_is_kept_safe_as_the_hook_keeps_it(call_id: str) -> None:
    """The monitor's safe() gives the name the hook's own safe() gives a
    call id in a used marker's name (as the hook substitutes it), run from
    the hook's source with the locale the hook sets (LC_ALL=C, byte by
    byte)."""
    text = PRETOOLUSE_HOOK.read_text(encoding="utf-8")
    match = re.search(r"^safe\(\) \{\n.*?^\}\n", text, re.MULTILINE | re.DOTALL)
    assert match is not None
    result = subprocess.run(
        [
            "bash",
            "-c",
            match.group(0) + 'printf "%s" "$(safe "$1")"',
            "safe",
            call_id,
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    assert result.stdout == monitor.safe(call_id)


@pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("openssl") is None,
    reason="the hook needs jq and openssl",
)
def test_lines_the_hook_writes_are_read_and_verified(tmp_path: Path) -> None:
    """Lines the log hook writes itself: a Write with a marker passes, one
    without is flagged, and --verify checks the chain and the head."""
    for call_id, tool in (
        ("toolu_1", "Write"),
        ("toolu_2", "Write"),
        ("toolu_3", "Read"),
    ):
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": tool,
            "tool_use_id": call_id,
            "tool_input": {"file_path": "a"},
        }
        result = subprocess.run(
            [str(POSTTOOLUSE_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "CLAUDE_PROJECT_DIR": str(tmp_path),
                "AUDIT_HMAC_KEY": KEY,
            },
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
    used = tmp_path / ".claude" / "checkpoints" / "used"
    used.mkdir(parents=True)
    (used / "chk_1764200000.toolu_1.Ab12Cd").write_text("{}\n")
    log = tmp_path / ".claude" / "audit.log"
    result = cli("--log-file", str(log), "--verify", "--hmac-key", KEY)
    assert result.returncode == 1, result.stdout
    assert (
        "call toolu_2: Write executed with no used checkpoint marker" in result.stdout
    )
    assert "integrity" not in result.stdout
    (used / "chk_1764200001.toolu_2.Ef34Gh").write_text("{}\n")
    result = cli("--log-file", str(log), "--verify", "--hmac-key", KEY)
    assert result.returncode == 0, result.stdout
    # A cut the head shows is a violation.
    log.write_text("\n".join(log.read_text().splitlines()[:2]) + "\n")
    result = cli("--log-file", str(log), "--verify", "--hmac-key", KEY)
    assert result.returncode == 1
    assert "integrity: Head: the log ends before its head" in result.stdout
