#!/usr/bin/env python3
"""Check the safety layer's records for invariant violations and anomalies.

Reads the plugin's log, .claude/audit.log (one action record per tool call
that ran, written by hooks/posttooluse_log_tool.sh), the checkpoint markers
the pre-tool-use hook filed under .claude/checkpoints/used/ (one per gated
call, named <checkpoint>.<call id>.<suffix>), and, with --records, the
action records the SDK adapter exports (GroundedAgentAdapter.
export_action_records, as a JSON array or one record per line). It prints a
report and exits non-zero when it finds a violation or an anomaly.

Violations (each printed with its call id):

- A call in the plugin's log that ran (status executed or failed) and that
  the pre-tool-use hook gates by its tool name, with no used marker for its
  call id: every gated call takes one checkpoint marker before it runs.
  The gated tools are every tool but the ones the hook lets pass by name
  (UNGATED_TOOLS) and Bash: Write, Edit, MultiEdit, NotebookEdit, Skill,
  Agent, Task, every MCP tool and every other tool the hook does not know
  (unbound). Bash is gated by its command, which the log does not hold, so
  a Bash call with no marker is counted, not flagged.
- An executed call in the adapter's records whose capability is mutate or
  send, that is unbound (no capability), or that is a Skill, Agent or Task
  call (whose worst case is mutate and send), with no checkpoint_id or no
  approved approval in any record of the same call id.
- A line that is not a JSON object, and, with --verify, every error
  tools/verify_audit_log.py reports for the log (the chain, the head, the
  anchor and each witness).

Anomalies (each printed with the lines or call ids it rests on):

- A line whose recorded_by.settings.approval is "off": the hook let gated
  calls run without asking a person.
- A change of recorded_by.config_sha256 between two lines: the hooks'
  configuration changed during the log.
- A refusal rate in the adapter's records (rejected over all records) above
  --max-refusal-rate (default 0.2).

Also reported, without failing: the number of lines by tool, by status and
by settings; the plugin version of the lines; Bash calls with and without a
marker; used markers no line of the log names (the person declined the
call, or it did not run); entries written before the hook wrote action
records, which are not checked; and gaps in the adapter's sequence numbers
(each execution boundary takes a number and exports no record, so a gap is
expected there).

Exit status: 0 when nothing is flagged, 1 when a violation or an anomaly is
found, 2 when the check cannot run (no input, an unreadable file, or no key
for --verify).

Usage:
    python tools/check_audit_invariants.py [--log-file PATH]
        [--used-dir PATH] [--records PATH ...] [--max-refusal-rate RATE]
        [--verify [--hmac-key KEY] [--witness PATH ...]] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The tools the pre-tool-use hook lets pass by name (UNGATED_TOOLS in
# hooks/pretooluse_require_checkpoint.sh; tests/test_check_audit_invariants.py
# keeps the two lists equal).
UNGATED_TOOLS = frozenset(
    {
        "Read",
        "Glob",
        "Grep",
        "LS",
        "WebFetch",
        "WebSearch",
        "AskUser",
        "AskUserQuestion",
        "TodoRead",
        "TodoWrite",
        "TaskList",
        "TaskGet",
        "TaskCreate",
        "TaskUpdate",
        "ToolSearch",
        "BashOutput",
        "TaskOutput",
        "ListMcpResourcesTool",
        "ReadMcpResourceTool",
        "ExitPlanMode",
    }
)
# Gated by its command, which the log does not hold.
BY_COMMAND = "Bash"
# Tools whose worst case is a gated mutate and send, whatever capability an
# adapter's record names first.
UNSEEN_TOOLS = frozenset({"Skill", "Agent", "Task"})
GATED_CAPABILITIES = frozenset({"mutate", "send"})
RAN = frozenset({"executed", "failed"})
DEFAULT_MAX_REFUSAL_RATE = 0.2

# The suffix mktemp gives the claim directory, which ends a marker's name.
_MARKER_SUFFIX = re.compile(r"\.([A-Za-z0-9]+)\Z")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def safe(text: str) -> str:
    """A name as the pre-tool-use hook keeps it in a marker's name:
    characters outside A-Z, a-z, 0-9, ``.``, ``_`` and ``-`` replaced by
    ``_``, and at most 120 characters."""
    return _UNSAFE.sub("_", text)[:120]


@dataclass
class Report:
    """What the check found."""

    lines: int = 0
    by_tool: Counter[str] = field(default_factory=Counter)
    by_status: Counter[str] = field(default_factory=Counter)
    by_settings: Counter[str] = field(default_factory=Counter)
    versions: Counter[str] = field(default_factory=Counter)
    config_transitions: list[dict[str, Any]] = field(default_factory=list)
    older_entries: int = 0
    bash_with_marker: int = 0
    bash_without_marker: int = 0
    unmatched_markers: list[str] = field(default_factory=list)
    records: int = 0
    refusals: int = 0
    seq_gaps: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    anomalies: list[dict[str, Any]] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(self.violations or self.anomalies)

    def as_json(self) -> dict[str, Any]:
        return {
            "lines": self.lines,
            "by_tool": dict(self.by_tool),
            "by_status": dict(self.by_status),
            "by_settings": dict(self.by_settings),
            "versions": dict(self.versions),
            "config_transitions": self.config_transitions,
            "older_entries": self.older_entries,
            "bash": {
                "with_marker": self.bash_with_marker,
                "without_marker": self.bash_without_marker,
            },
            "unmatched_markers": self.unmatched_markers,
            "records": self.records,
            "refusals": self.refusals,
            "seq_gaps": self.seq_gaps,
            "violations": self.violations,
            "anomalies": self.anomalies,
        }


class InputError(Exception):
    """An input cannot be read: why, in words."""


def used_markers(used_dir: Path) -> dict[str, list[str]]:
    """The used markers in ``used_dir`` by the call-id part of their name
    (as :func:`safe` keeps it): each name ``<checkpoint>.<call id>.<suffix>``
    is filed under every split of its name that leaves a non-empty
    checkpoint part, since both parts may hold dots. Missing directory:
    no markers."""
    found: dict[str, list[str]] = {}
    if not used_dir.is_dir():
        return found
    for path in sorted(used_dir.iterdir()):
        name = path.name
        if name.startswith(".") or not path.is_file():
            continue
        suffix = _MARKER_SUFFIX.search(name)
        if suffix is None:
            continue
        stem = name[: suffix.start()]
        for i, ch in enumerate(stem):
            if ch == "." and i > 0 and i < len(stem) - 1:
                found.setdefault(stem[i + 1 :], []).append(name)
    return found


def _settings_key(settings: Any) -> str:
    if not isinstance(settings, dict):
        return "(none)"
    return ", ".join(f"{k}={settings[k]}" for k in sorted(settings))


def check_log(log_path: Path, used_dir: Path, report: Report) -> None:
    """The plugin log's counts, its gated calls against the used markers,
    and its anomalies, into ``report``."""
    try:
        text = log_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise InputError(f"the log {log_path} cannot be read: {e}") from None
    markers = used_markers(used_dir)
    named: set[str] = set()
    config: str | None = None
    config_line = 0
    lines = text.removesuffix("\n").split("\n") if text.strip() else []
    for number, line in enumerate(lines, 1):
        report.lines += 1
        try:
            entry = json.loads(line)
        except ValueError:
            entry = None
        if not isinstance(entry, dict):
            report.violations.append(
                {"rule": "unreadable_line", "line": number, "call_id": None}
            )
            continue
        named_tool = entry.get("tool")
        tool = named_tool if isinstance(named_tool, str) else "(none)"
        report.by_tool[tool] += 1
        if "action_id" not in entry:
            report.older_entries += 1
            continue
        status = str(entry.get("status"))
        report.by_status[status] += 1
        recorded_by = entry.get("recorded_by")
        recorded_by = recorded_by if isinstance(recorded_by, dict) else {}
        settings = recorded_by.get("settings")
        report.by_settings[_settings_key(settings)] += 1
        report.versions[str(recorded_by.get("version"))] += 1
        call_id = (
            entry.get("call_id") if isinstance(entry.get("call_id"), str) else None
        )
        if isinstance(settings, dict) and settings.get("approval") == "off":
            report.anomalies.append(
                {"rule": "approval_off", "line": number, "call_id": call_id}
            )
        sha = recorded_by.get("config_sha256")
        if isinstance(sha, str):
            if config is not None and sha != config:
                transition = {
                    "rule": "config_changed",
                    "line": number,
                    "after_line": config_line,
                    "from": config,
                    "to": sha,
                    "call_id": call_id,
                }
                report.config_transitions.append(transition)
                report.anomalies.append(transition)
            config, config_line = sha, number
        if status not in RAN or tool in UNGATED_TOOLS:
            continue
        has_marker = call_id is not None and safe(call_id) in markers
        if has_marker:
            named.add(safe(call_id or ""))
        if tool == BY_COMMAND:
            if has_marker:
                report.bash_with_marker += 1
            else:
                report.bash_without_marker += 1
            continue
        if not has_marker:
            report.violations.append(
                {
                    "rule": "gated_call_without_checkpoint",
                    "line": number,
                    "tool": tool,
                    "status": status,
                    "call_id": call_id,
                }
            )
    every = {name for names in markers.values() for name in names}
    matched = {name for key in named for name in markers.get(key, [])}
    report.unmatched_markers = sorted(every - matched)


def read_records(path: Path) -> list[dict[str, Any]]:
    """Exported action records: a JSON array, or one record per line."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise InputError(f"the records {path} cannot be read: {e}") from None
    try:
        value = json.loads(text)
        items = value if isinstance(value, list) else [value]
    except ValueError:
        try:
            items = [json.loads(line) for line in text.splitlines() if line.strip()]
        except ValueError as e:
            raise InputError(f"the records {path} are not JSON: {e}") from None
    if not all(isinstance(item, dict) for item in items):
        raise InputError(f"the records {path} are not all JSON objects")
    return items


def _seq(action_id: Any) -> tuple[str, int] | None:
    if not isinstance(action_id, str) or "/" not in action_id:
        return None
    scope, _, number = action_id.rpartition("/")
    return (scope, int(number)) if number.isdigit() else None


def check_records(
    records: Sequence[dict[str, Any]], max_refusal_rate: float, report: Report
) -> None:
    """The adapter's exported records: each executed gated call has a
    checkpoint and an approval, the refusal rate, and the sequence gaps."""
    by_call: dict[str, list[dict[str, Any]]] = {}
    last_seq: dict[str, int] = {}
    for record in records:
        report.records += 1
        if record.get("status") == "rejected":
            report.refusals += 1
        call = record.get("call_id")
        if isinstance(call, str):
            by_call.setdefault(call, []).append(record)
        seq = _seq(record.get("action_id"))
        if seq is not None:
            scope, number = seq
            before = last_seq.get(scope)
            if before is not None and number > before + 1:
                report.seq_gaps.append(
                    {"run_id": scope, "after": before, "next": number}
                )
            last_seq[scope] = number
    for record in records:
        if record.get("status") != "executed":
            continue
        tool = record.get("tool")
        capability = record.get("capability")
        if not (
            capability is None
            or capability in GATED_CAPABILITIES
            or tool in UNSEEN_TOOLS
        ):
            continue
        call = record.get("call_id")
        related = by_call.get(call, [record]) if isinstance(call, str) else [record]
        checkpoint = any(r.get("checkpoint_id") for r in related)
        approval = any(
            isinstance(r.get("approval"), dict)
            and r["approval"].get("decision") == "approved"
            for r in related
        )
        if not (checkpoint and approval):
            missing = [
                name
                for name, present in (
                    ("checkpoint_id", checkpoint),
                    ("approval", approval),
                )
                if not present
            ]
            report.violations.append(
                {
                    "rule": "gated_record_without_checkpoint_or_approval",
                    "action_id": record.get("action_id"),
                    "tool": tool,
                    "capability": capability,
                    "missing": missing,
                    "call_id": call if isinstance(call, str) else None,
                }
            )
    if report.records and report.refusals / report.records > max_refusal_rate:
        report.anomalies.append(
            {
                "rule": "refusal_rate",
                "refusals": report.refusals,
                "records": report.records,
                "rate": round(report.refusals / report.records, 4),
                "threshold": max_refusal_rate,
                "call_id": None,
            }
        )


def check_integrity(
    log_path: Path, hmac_key: str | None, witnesses: Sequence[Path], report: Report
) -> None:
    """tools/verify_audit_log.py's check of the log, its head, its anchor and
    each witness; each error is a violation."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import verify_audit_log as verifier

    if hmac_key is None:
        try:
            hmac_key = verifier.get_default_hmac_key()
        except verifier.AuditKeyError as e:
            raise InputError(f"--verify: {e}") from None
    head = log_path.with_suffix(".head")
    try:
        witness_files = verifier.expand_witnesses(witnesses)
    except verifier.WitnessDirError as e:
        report.violations.append(
            {"rule": "integrity", "error": str(e), "call_id": None}
        )
        witness_files = []
    _, _, errors = verifier.verify_log(
        log_path, hmac_key, head, verifier.default_anchor(log_path), witness_files
    )
    for error in errors:
        report.violations.append({"rule": "integrity", "error": error, "call_id": None})


def _describe(item: dict[str, Any]) -> str:
    rule = item["rule"]
    call = item.get("call_id") or "(no call id)"
    if rule == "gated_call_without_checkpoint":
        return (
            f"call {call}: {item['tool']} {item['status']} with no used checkpoint "
            f"marker (log line {item['line']})"
        )
    if rule == "gated_record_without_checkpoint_or_approval":
        return (
            f"call {call}: {item['tool']} (capability {item['capability']}) executed "
            f"with no {' and no '.join(item['missing'])} (record {item['action_id']})"
        )
    if rule == "unreadable_line":
        return f"log line {item['line']} is not a JSON object"
    if rule == "integrity":
        return f"integrity: {item['error']}"
    if rule == "approval_off":
        return (
            f"call {call}: recorded with approval off (log line {item['line']}): "
            "gated calls ran without asking a person"
        )
    if rule == "config_changed":
        return (
            f"call {call}: the hooks' configuration changed at log line "
            f"{item['line']} (config_sha256 {item['from'][:12]} to {item['to'][:12]})"
        )
    if rule == "refusal_rate":
        return (
            f"refusal rate {item['rate']:.0%} ({item['refusals']} of "
            f"{item['records']} records) is above {item['threshold']:.0%}"
        )
    return json.dumps(item)


def print_report(report: Report) -> None:
    print(f"Log lines: {report.lines}")
    for title, counts in (
        ("By tool", report.by_tool),
        ("By status", report.by_status),
        ("By settings", report.by_settings),
        ("By plugin version", report.versions),
    ):
        if counts:
            print(f"{title}:")
            for key, n in counts.most_common():
                print(f"  {n:6d}  {key}")
    if report.older_entries:
        print(
            f"Entries written before the hook wrote action records (not checked): "
            f"{report.older_entries}"
        )
    print(
        f"Bash calls that ran: {report.bash_with_marker} with a used marker, "
        f"{report.bash_without_marker} without (a read-only command needs none; "
        "the log does not hold the command)"
    )
    if report.unmatched_markers:
        print(
            f"Used markers no log line names (declined or did not run): "
            f"{len(report.unmatched_markers)}"
        )
    if report.records:
        print(f"Adapter records: {report.records}, refused: {report.refusals}")
    for gap in report.seq_gaps:
        print(
            f"  sequence gap in {gap['run_id']}: {gap['after']} to {gap['next']} "
            "(an execution boundary takes a number and exports no record)"
        )
    for title, items in (
        ("VIOLATIONS", report.violations),
        ("ANOMALIES", report.anomalies),
    ):
        if items:
            print(f"{title}: {len(items)}")
            for item in items:
                print(f"  {_describe(item)}")
    print("INVARIANT CHECK FAILED" if report.flagged else "INVARIANT CHECK PASSED")


def run(
    log_path: Path | None,
    used_dir: Path | None,
    records: Sequence[Path] = (),
    max_refusal_rate: float = DEFAULT_MAX_REFUSAL_RATE,
    verify: bool = False,
    hmac_key: str | None = None,
    witnesses: Sequence[Path] = (),
) -> Report:
    """The report for these inputs. Raises :class:`InputError` when an input
    cannot be read."""
    report = Report()
    if log_path is not None:
        check_log(
            log_path,
            used_dir or log_path.parent / "checkpoints" / "used",
            report,
        )
        if verify:
            check_integrity(log_path, hmac_key, witnesses, report)
    exported: list[dict[str, Any]] = []
    for path in records:
        exported.extend(read_records(path))
    if records:
        check_records(exported, max_refusal_rate, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the safety layer's records for invariant violations"
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="The plugin's log (default: .claude/audit.log, when it exists or "
        "no --records is given)",
    )
    parser.add_argument(
        "--used-dir",
        type=Path,
        default=None,
        help="The used checkpoint markers (default: checkpoints/used beside the log)",
    )
    parser.add_argument(
        "--records",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help="The SDK adapter's exported action records (a JSON array or one "
        "record per line); repeatable",
    )
    parser.add_argument(
        "--max-refusal-rate",
        type=float,
        default=DEFAULT_MAX_REFUSAL_RATE,
        help="The refusal rate in the adapter's records above which it is an "
        f"anomaly (default {DEFAULT_MAX_REFUSAL_RATE})",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Also verify the log's chain, head, anchor and witnesses with "
        "tools/verify_audit_log.py",
    )
    parser.add_argument(
        "--hmac-key", default=None, help="The key for --verify (default: the hook's)"
    )
    parser.add_argument(
        "--witness",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help="A witness head, or a directory of them, for --verify; repeatable",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    args = parser.parse_args(argv)
    if not 0 <= args.max_refusal_rate <= 1:
        parser.error("--max-refusal-rate is a rate from 0 to 1")
    if (args.hmac_key or args.witness) and not args.verify:
        parser.error("--hmac-key and --witness are for --verify")
    log_path = args.log_file
    default_log = Path(".claude/audit.log")
    if log_path is None and (default_log.exists() or not args.records):
        log_path = default_log
    if log_path is not None and not log_path.exists():
        print(f"INVARIANT CHECK NOT RUN: there is no log at {log_path}")
        return 2
    try:
        report = run(
            log_path,
            args.used_dir,
            args.records,
            args.max_refusal_rate,
            args.verify,
            args.hmac_key,
            args.witness,
        )
    except InputError as e:
        print(f"INVARIANT CHECK NOT RUN: {e}")
        return 2
    if args.json:
        print(json.dumps(report.as_json(), indent=2))
    else:
        print_report(report)
    return 1 if report.flagged else 0


if __name__ == "__main__":
    sys.exit(main())
