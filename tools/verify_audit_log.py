#!/usr/bin/env python3
"""Verify audit log integrity via HMAC chain validation.

Reads .claude/audit.log and verifies that:
1. Each entry is valid JSON with required fields
2. Each entry's HMAC matches its content
3. Each entry's prev_hmac matches the previous entry's HMAC (chain integrity)
4. The log still holds the entry its head records, at its place: the head,
   .claude/audit.head, is the chain's end as the hook last wrote it (the
   number of entries and the last one's hmac, signed with the same key).

The chain alone shows a changed or removed entry by the link of the entry
after it; removing the last entries, or the whole log, breaks no link, and
the head shows it. A log begun before the hook kept a head, and a chain no
head anchors (the audit skill's .claude/audit/records.jsonl), are verified
with --no-head, which checks the chain alone.

The log is written by hooks/posttooluse_log_tool.sh, one entry per tool call.
Three generations of entry verify, in any mix, because the HMAC is taken over
every field but ``hmac`` in the order recorded:

- an action record (STANDARD v1.2 §6.4), with the chain fields: the hook
  writes action_id, timestamp, actor, intent, status, tool, call_id (when
  the call has one), details, recorded_by (the layer and its configuration:
  name, version, config_sha256 and settings; STANDARD 1.2.0 section 5.18.8),
  prev_hmac, hmac, and the audit skill's own chain
  (.claude/audit/records.jsonl) holds records of the same form;
- before Standard 1.2: ts, event, tool, skill (on a Skill call),
  input_sha256, prev_hmac, hmac;
- before the hook logged every tool call: ts, skill, args, prev_hmac, hmac,
  for Skill calls only.

Usage:
    python tools/verify_audit_log.py [--log-file PATH] [--hmac-key KEY]
        [--head-file PATH | --no-head]

SEC-005: Audit log integrity verification.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import socket
import sys
from pathlib import Path

# Every entry carries the chain fields, and the fields of one generation: an
# action record (what the hook writes), a tool call of the hook before
# Standard 1.2, or, in a log begun before the hook logged every tool call, a
# skill and its arguments.
CHAIN_FIELDS = {"prev_hmac", "hmac"}
GENERATIONS = (
    {"action_id", "timestamp", "actor", "intent", "status"},
    {"ts", "event", "tool", "input_sha256"},
    {"ts", "skill", "args"},
)


def get_default_hmac_key() -> str:
    """Derive the default HMAC key matching the shell hook's logic."""
    key = os.environ.get("AUDIT_HMAC_KEY")
    if key:
        return key
    try:
        hostname = socket.gethostname().split(".")[0]
    except OSError:
        hostname = "default"
    return f"grounded-agency-audit-{hostname}"


def compute_hmac(content: str, key: str) -> str:
    """Compute HMAC-SHA256 matching the shell hook's openssl output."""
    return hmac.new(
        key.encode("utf-8"),
        content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_entry(entry: dict, expected_prev_hmac: str, hmac_key: str) -> list[str]:
    """Verify a single audit log entry. Returns list of error messages."""
    errors: list[str] = []

    # Check required fields: the chain's, and those of the generation the
    # entry is closest to (the first, when it fits none)
    keys = set(entry.keys())
    missing = CHAIN_FIELDS - keys
    if all(fields - keys for fields in GENERATIONS):
        missing |= min((fields - keys for fields in GENERATIONS), key=len)
    if missing:
        errors.append(f"Missing fields: {sorted(missing)}")
        return errors

    # Check chain linkage
    if entry["prev_hmac"] != expected_prev_hmac:
        errors.append(
            f"Chain break: prev_hmac={entry['prev_hmac']!r} "
            f"but expected={expected_prev_hmac!r}"
        )

    # Reconstruct the content the hook signed: every field but `hmac`, in the
    # order recorded, as jq -c prints it: compact, non-ASCII text as is, and
    # DEL (U+007F) escaped, which json.dumps leaves as is
    content_dict = {key: value for key, value in entry.items() if key != "hmac"}
    content = json.dumps(
        content_dict, separators=(",", ":"), sort_keys=False, ensure_ascii=False
    ).replace("\x7f", "\\u007f")

    # Verify HMAC
    expected_hmac = compute_hmac(content, hmac_key)
    if entry["hmac"] != expected_hmac:
        errors.append(f"HMAC mismatch: recorded={entry['hmac']!r}")

    return errors


def head_hmac(entries: int, last_hmac: str, key: str) -> str:
    """The signature of a head: the hook's HMAC of
    ``acs-audit-head:<entries>:<hmac>``."""
    return compute_hmac(f"acs-audit-head:{entries}:{last_hmac}", key)


def read_head(head_path: Path, hmac_key: str) -> tuple[int, str] | str:
    """The head at ``head_path`` as (entries, hmac), or why it cannot be
    used."""
    try:
        with head_path.open(encoding="utf-8") as f:
            line = f.readline(4096)
    except FileNotFoundError:
        return (
            f"Head not found: {head_path} (the hook keeps one beside the log; "
            "a log begun before it did, or a chain no head anchors, is "
            "verified with --no-head)"
        )
    except (OSError, UnicodeDecodeError) as e:
        return f"Head unreadable: {e}"
    try:
        head = json.loads(line)
    except json.JSONDecodeError:
        return "Head is not JSON"
    entries = head.get("entries") if isinstance(head, dict) else None
    last = head.get("hmac") if isinstance(head, dict) else None
    sig = head.get("head_hmac") if isinstance(head, dict) else None
    if not (
        isinstance(entries, int)
        and not isinstance(entries, bool)
        and entries >= 1
        and isinstance(last, str)
        and isinstance(sig, str)
    ):
        return "Head lacks entries, hmac or head_hmac"
    if not hmac.compare_digest(sig, head_hmac(entries, last, hmac_key)):
        return "Head HMAC mismatch: the head was not signed with this key"
    return entries, last


def verify_log(
    log_path: Path, hmac_key: str, head_path: Path | None = None
) -> tuple[int, int, list[str]]:
    """Verify the entire audit log, and, given ``head_path``, that the log
    still holds the entry its head records, at its place (so that its last
    entries were not removed).

    Returns:
        (total_entries, valid_entries, all_errors)
    """
    head = read_head(head_path, hmac_key) if head_path is not None else None
    head_errors = [head] if isinstance(head, str) else []
    if not log_path.exists():
        if isinstance(head, tuple):
            head_errors.append(
                f"Audit log not found, though its head records {head[0]} entries"
            )
        return 0, 0, ["Audit log not found", *head_errors]

    # One entry per "\n": the hook writes no other line break between
    # entries, and str.splitlines() would also split at U+0085, U+2028 and
    # U+2029, which jq -c writes raw inside a JSON string.
    text = log_path.read_text(encoding="utf-8").strip()
    lines = text.split("\n") if text else []
    if not lines:
        return 0, 0, ["Audit log is empty", *head_errors]

    total = len(lines)
    valid = 0
    all_errors: list[str] = list(head_errors)
    prev_hmac = ""
    if isinstance(head, tuple):
        entries, last = head
        held: object = None
        if total >= entries:
            try:
                held = json.loads(lines[entries - 1]).get("hmac")
            except json.JSONDecodeError, AttributeError:
                held = None
        if total < entries:
            all_errors.append(
                f"Head: the log ends before its head: {entries} entries "
                f"recorded, {total} found (its last entries were removed)"
            )
        elif held != last:
            all_errors.append(
                f"Head: entry {entries} is not the one the head records "
                "(entries were removed or replaced)"
            )

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            all_errors.append(f"Line {i}: Invalid JSON: {e}")
            prev_hmac = ""  # Chain is broken
            continue

        errors = verify_entry(entry, prev_hmac, hmac_key)
        if errors:
            for err in errors:
                all_errors.append(f"Line {i}: {err}")
        else:
            valid += 1

        prev_hmac = entry.get("hmac", "")

    return total, valid, all_errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify audit log HMAC integrity")
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path(".claude/audit.log"),
        help="Path to audit log file (default: .claude/audit.log)",
    )
    parser.add_argument(
        "--hmac-key",
        default=None,
        help="HMAC key (default: derived from hostname, matching shell hook)",
    )
    head = parser.add_mutually_exclusive_group()
    head.add_argument(
        "--head-file",
        type=Path,
        default=None,
        help="The log's head (default: the log's path with the suffix .head, "
        "as the hook writes .claude/audit.head)",
    )
    head.add_argument(
        "--no-head",
        action="store_true",
        help="Check the chain alone: a log begun before the hook kept a head, "
        "or a chain no head anchors (removing its last entries is not seen)",
    )
    args = parser.parse_args()

    hmac_key = args.hmac_key or get_default_hmac_key()
    head_path = (
        None if args.no_head else (args.head_file or args.log_file.with_suffix(".head"))
    )
    total, valid, errors = verify_log(args.log_file, hmac_key, head_path)

    if errors:
        print(f"INTEGRITY CHECK FAILED: {len(errors)} error(s) in {total} entries\n")
        for err in errors:
            print(f"  ERROR: {err}")
        sys.exit(1)
    else:
        print(f"INTEGRITY CHECK PASSED: {valid}/{total} entries verified")
        sys.exit(0)


if __name__ == "__main__":
    main()
