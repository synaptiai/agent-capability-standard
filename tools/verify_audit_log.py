#!/usr/bin/env python3
"""Verify audit log integrity via HMAC chain validation.

Reads .claude/audit.log and verifies that:
1. Each entry is valid JSON with required fields
2. Each entry's HMAC matches its content
3. Each entry's prev_hmac matches the previous entry's HMAC (chain integrity)

Usage:
    python tools/verify_audit_log.py [--log-file PATH] [--hmac-key KEY]

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

REQUIRED_FIELDS = {"ts", "skill", "args", "prev_hmac", "hmac"}


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

    # Check required fields
    missing = REQUIRED_FIELDS - set(entry.keys())
    if missing:
        errors.append(f"Missing fields: {missing}")
        return errors

    # Check chain linkage
    if entry["prev_hmac"] != expected_prev_hmac:
        errors.append(
            f"Chain break: prev_hmac={entry['prev_hmac']!r} "
            f"but expected={expected_prev_hmac!r}"
        )

    # Reconstruct content in compact format matching jq -c output
    content_dict = {
        "ts": entry["ts"],
        "skill": entry["skill"],
        "args": entry["args"],
        "prev_hmac": entry["prev_hmac"],
    }
    content = json.dumps(content_dict, separators=(",", ":"), sort_keys=False)

    # Verify HMAC
    expected_hmac = compute_hmac(content, hmac_key)
    if entry["hmac"] != expected_hmac:
        errors.append(f"HMAC mismatch: recorded={entry['hmac']!r}")

    return errors


def verify_log(log_path: Path, hmac_key: str) -> tuple[int, int, list[str]]:
    """Verify the entire audit log.

    Returns:
        (total_entries, valid_entries, all_errors)
    """
    if not log_path.exists():
        return 0, 0, ["Audit log not found"]

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return 0, 0, ["Audit log is empty"]

    total = len(lines)
    valid = 0
    all_errors: list[str] = []
    prev_hmac = ""

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
    args = parser.parse_args()

    hmac_key = args.hmac_key or get_default_hmac_key()
    total, valid, errors = verify_log(args.log_file, hmac_key)

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
