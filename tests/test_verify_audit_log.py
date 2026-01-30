"""Tests for audit log HMAC integrity verifier (SEC-005).

Validates that tools/verify_audit_log.py correctly verifies and rejects
HMAC chains in the audit log format.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path

# Add tools/ to import path for the verifier module
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_audit_log import compute_hmac, verify_entry, verify_log  # noqa: E402

HMAC_KEY = "test-key-for-verification"


def make_entry(
    skill: str = "test-skill",
    args: str = "",
    prev_hmac: str = "",
    hmac_key: str = HMAC_KEY,
    ts: str = "2026-01-30T12:00:00Z",
) -> dict:
    """Create a valid audit log entry with correct HMAC."""
    content_dict = {
        "ts": ts,
        "skill": skill,
        "args": args,
        "prev_hmac": prev_hmac,
    }
    content = json.dumps(content_dict, separators=(",", ":"), sort_keys=False)
    entry_hmac = compute_hmac(content, hmac_key)
    return {**content_dict, "hmac": entry_hmac}


def write_log(log_path: Path, entries: list[dict]) -> None:
    """Write entries as JSONL to the log file."""
    lines = [json.dumps(e, separators=(",", ":")) for e in entries]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestComputeHmac:
    """Tests for HMAC computation."""

    def test_deterministic_output(self) -> None:
        result1 = compute_hmac("hello", "key")
        result2 = compute_hmac("hello", "key")
        assert result1 == result2

    def test_different_content_different_hmac(self) -> None:
        assert compute_hmac("hello", "key") != compute_hmac("world", "key")

    def test_different_key_different_hmac(self) -> None:
        assert compute_hmac("hello", "key1") != compute_hmac("hello", "key2")

    def test_matches_stdlib_hmac(self) -> None:
        expected = hmac.new(
            b"mykey", b"mydata", hashlib.sha256
        ).hexdigest()
        assert compute_hmac("mydata", "mykey") == expected


class TestVerifyEntry:
    """Tests for single entry verification."""

    def test_valid_entry_passes(self) -> None:
        entry = make_entry()
        errors = verify_entry(entry, "", HMAC_KEY)
        assert errors == []

    def test_missing_field_detected(self) -> None:
        entry = make_entry()
        del entry["skill"]
        errors = verify_entry(entry, "", HMAC_KEY)
        assert len(errors) == 1
        assert "Missing fields" in errors[0]

    def test_chain_break_detected(self) -> None:
        entry = make_entry(prev_hmac="")
        errors = verify_entry(entry, "expected-different-hmac", HMAC_KEY)
        assert any("Chain break" in e for e in errors)

    def test_tampered_hmac_detected(self) -> None:
        entry = make_entry()
        entry["hmac"] = "tampered_value"
        errors = verify_entry(entry, "", HMAC_KEY)
        assert any("HMAC mismatch" in e for e in errors)

    def test_tampered_content_detected(self) -> None:
        entry = make_entry(skill="original")
        entry["skill"] = "tampered"
        errors = verify_entry(entry, "", HMAC_KEY)
        assert any("HMAC mismatch" in e for e in errors)


class TestVerifyLog:
    """Tests for full log verification."""

    def test_valid_chain_passes(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        e1 = make_entry(skill="first", ts="2026-01-30T12:00:00Z")
        e2 = make_entry(
            skill="second",
            ts="2026-01-30T12:01:00Z",
            prev_hmac=e1["hmac"],
        )
        write_log(log_path, [e1, e2])
        total, valid, errors = verify_log(log_path, HMAC_KEY)
        assert total == 2
        assert valid == 2
        assert errors == []

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        log_path = tmp_path / "nonexistent.log"
        total, valid, errors = verify_log(log_path, HMAC_KEY)
        assert total == 0
        assert "not found" in errors[0]

    def test_empty_file_returns_error(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        log_path.write_text("", encoding="utf-8")
        total, valid, errors = verify_log(log_path, HMAC_KEY)
        assert total == 0
        assert "empty" in errors[0]

    def test_invalid_json_detected(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        log_path.write_text("not valid json\n", encoding="utf-8")
        total, valid, errors = verify_log(log_path, HMAC_KEY)
        assert total == 1
        assert valid == 0
        assert any("Invalid JSON" in e for e in errors)

    def test_tampered_middle_entry_breaks_chain(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        e1 = make_entry(skill="first", ts="2026-01-30T12:00:00Z")
        e2 = make_entry(
            skill="second",
            ts="2026-01-30T12:01:00Z",
            prev_hmac=e1["hmac"],
        )
        e3 = make_entry(
            skill="third",
            ts="2026-01-30T12:02:00Z",
            prev_hmac=e2["hmac"],
        )
        # Tamper with e2
        e2["skill"] = "tampered"
        write_log(log_path, [e1, e2, e3])
        total, valid, errors = verify_log(log_path, HMAC_KEY)
        assert total == 3
        # e2 should fail (HMAC mismatch), e3 should fail (chain break)
        assert valid < 3
        assert len(errors) > 0

    def test_deleted_entry_detected(self, tmp_path: Path) -> None:
        """Deleting an entry from the middle breaks the chain."""
        log_path = tmp_path / "audit.log"
        e1 = make_entry(skill="first", ts="2026-01-30T12:00:00Z")
        e2 = make_entry(
            skill="second",
            ts="2026-01-30T12:01:00Z",
            prev_hmac=e1["hmac"],
        )
        e3 = make_entry(
            skill="third",
            ts="2026-01-30T12:02:00Z",
            prev_hmac=e2["hmac"],
        )
        # Write e1 and e3 only (e2 deleted)
        write_log(log_path, [e1, e3])
        total, valid, errors = verify_log(log_path, HMAC_KEY)
        # e3 has prev_hmac pointing to e2's hmac, but after e1, the expected
        # prev_hmac is e1's hmac — so e3 should fail chain verification
        assert any("Chain break" in e for e in errors)

    def test_wrong_key_fails_verification(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        entry = make_entry(hmac_key="correct-key")
        write_log(log_path, [entry])
        total, valid, errors = verify_log(log_path, "wrong-key")
        assert valid == 0
        assert any("HMAC mismatch" in e for e in errors)
