"""Tests for audit log HMAC integrity verifier (SEC-005).

Validates that tools/verify_audit_log.py correctly verifies and rejects
HMAC chains in the audit log format.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Add tools/ to import path for the verifier module
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_audit_log import compute_hmac, verify_entry, verify_log  # noqa: E402

HMAC_KEY = "test-key-for-verification"
POSTTOOLUSE_HOOK = (
    Path(__file__).resolve().parents[1] / "hooks" / "posttooluse_log_tool.sh"
)


def sign(content_dict: dict, hmac_key: str = HMAC_KEY) -> dict:
    """Add the HMAC the hook computes: over the compact JSON of the content."""
    content = json.dumps(
        content_dict, separators=(",", ":"), sort_keys=False, ensure_ascii=False
    )
    return {**content_dict, "hmac": compute_hmac(content, hmac_key)}


def make_record_entry(
    tool: str = "Skill",
    status: str = "executed",
    prev_hmac: str = "",
    hmac_key: str = HMAC_KEY,
) -> dict:
    """An entry as the hook writes it since STANDARD v1.2: an action record
    (§6.4) with the chain fields."""
    content_dict = {
        "action_id": "toolu_1",
        "timestamp": "2026-11-15T12:00:00Z",
        "actor": "agent",
        "intent": f"{tool} call",
        "status": status,
        "tool": tool,
        "call_id": "toolu_1",
        "details": {"event": "PostToolUse", "input_sha256": "0" * 64},
        "recorded_by": {
            "name": "agent-capability-standard plugin hooks",
            "version": "2.0.0",
            "config_sha256": "0" * 64,
            "settings": {"approval": "ask", "checkpoint_max_age_s": 1800},
        },
        "prev_hmac": prev_hmac,
    }
    return sign(content_dict, hmac_key)


def make_entry(
    skill: str = "test-skill",
    tool_input: dict | None = None,
    prev_hmac: str = "",
    hmac_key: str = HMAC_KEY,
    ts: str = "2026-01-30T12:00:00Z",
) -> dict:
    """Create a valid audit log entry for a Skill call, as the hook writes it."""
    canonical = json.dumps(
        tool_input if tool_input is not None else {"skill": skill},
        sort_keys=True,
        separators=(",", ":"),
    )
    content_dict = {
        "ts": ts,
        "event": "PostToolUse",
        "tool": "Skill",
        "skill": skill,
        "input_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "prev_hmac": prev_hmac,
    }
    return sign(content_dict, hmac_key)


def make_tool_entry(
    tool: str = "Bash",
    event: str = "PostToolUse",
    prev_hmac: str = "",
    ts: str = "2026-01-30T12:00:00Z",
) -> dict:
    """Create a valid entry for a call of a tool other than Skill."""
    content_dict = {
        "ts": ts,
        "event": event,
        "tool": tool,
        "input_sha256": hashlib.sha256(b'{"command":"ls"}').hexdigest(),
        "prev_hmac": prev_hmac,
    }
    return sign(content_dict)


def make_legacy_entry(
    skill: str = "test-skill",
    args: str = "",
    prev_hmac: str = "",
    ts: str = "2026-01-30T12:00:00Z",
) -> dict:
    """An entry as the hook wrote it when it logged Skill calls only."""
    content_dict = {
        "ts": ts,
        "skill": skill,
        "args": args,
        "prev_hmac": prev_hmac,
    }
    return sign(content_dict)


def write_log(log_path: Path, entries: list[dict]) -> None:
    """Write entries as JSONL to the log file."""
    lines = [json.dumps(e, separators=(",", ":"), ensure_ascii=False) for e in entries]
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
        expected = hmac.new(b"mykey", b"mydata", hashlib.sha256).hexdigest()
        assert compute_hmac("mydata", "mykey") == expected


class TestVerifyEntry:
    """Tests for single entry verification."""

    def test_valid_entry_passes(self) -> None:
        entry = make_entry()
        errors = verify_entry(entry, "", HMAC_KEY)
        assert errors == []

    def test_tool_entry_passes(self) -> None:
        """An entry for a tool other than Skill carries no skill name."""
        entry = make_tool_entry(tool="Bash", event="PostToolUseFailure")
        assert "skill" not in entry
        assert verify_entry(entry, "", HMAC_KEY) == []

    @pytest.mark.parametrize(
        "field", ["ts", "event", "tool", "input_sha256", "prev_hmac", "hmac"]
    )
    def test_missing_field_detected(self, field: str) -> None:
        entry = make_entry()
        del entry[field]
        errors = verify_entry(entry, "", HMAC_KEY)
        assert len(errors) == 1
        assert "Missing fields" in errors[0]
        assert field in errors[0]

    def test_legacy_entry_passes(self) -> None:
        """An entry written before the hook logged every tool call verifies."""
        entry = make_legacy_entry(skill="checkpoint", args="--scope *.py")
        assert verify_entry(entry, "", HMAC_KEY) == []

    def test_legacy_entry_missing_field_detected(self) -> None:
        entry = make_legacy_entry()
        del entry["args"]
        errors = verify_entry(entry, "", HMAC_KEY)
        assert len(errors) == 1
        assert "Missing fields" in errors[0]

    def test_non_ascii_name_passes(self) -> None:
        """The hook signs names as jq prints them: non-ASCII text as is."""
        entry = make_entry(skill="prüfen")
        assert verify_entry(entry, "", HMAC_KEY) == []

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

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("tool", "Read"),
            ("event", "PostToolUseFailure"),
            ("input_sha256", "0" * 64),
            ("ts", "2026-01-31T00:00:00Z"),
        ],
    )
    def test_tampered_call_fields_detected(self, field: str, value: str) -> None:
        entry = make_tool_entry()
        entry[field] = value
        errors = verify_entry(entry, "", HMAC_KEY)
        assert any("HMAC mismatch" in e for e in errors)

    def test_added_field_detected(self) -> None:
        """Every field but hmac is signed, so an added one breaks the HMAC."""
        entry = make_tool_entry()
        tampered = {"note": "approved", **entry}
        errors = verify_entry(tampered, "", HMAC_KEY)
        assert any("HMAC mismatch" in e for e in errors)

    def test_removed_skill_name_detected(self) -> None:
        entry = make_entry(skill="send")
        del entry["skill"]
        errors = verify_entry(entry, "", HMAC_KEY)
        assert any("HMAC mismatch" in e for e in errors)


class TestVerifyLog:
    """Tests for full log verification."""

    @pytest.mark.skipif(
        shutil.which("bash") is None or shutil.which("jq") is None,
        reason="the hook needs bash and jq",
    )
    def test_line_separators_inside_a_name_verify(self, tmp_path: Path) -> None:
        """U+0085, U+2028 and U+2029 inside a logged name are not line breaks.

        jq -c writes them raw, and the hook chains on lines split at "\\n"
        only; str.splitlines() would split the entry in two.
        """
        env = {
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "AUDIT_HMAC_KEY": HMAC_KEY,
        }
        calls = [
            {"tool_name": "Read", "tool_input": {"file_path": "/work/a.md"}},
            {"tool_name": "Skill", "tool_input": {"skill": "x\u2028y\u0085z\u2029"}},
            {"tool_name": "Read", "tool_input": {"file_path": "/work/b.md"}},
        ]
        for call in calls:
            subprocess.run(
                ["bash", str(POSTTOOLUSE_HOOK)],
                input=json.dumps({"hook_event_name": "PostToolUse", **call}),
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
                check=True,
            )
        log_file = tmp_path / ".claude" / "audit.log"
        raw = log_file.read_text(encoding="utf-8")
        assert raw.count("\n") == 3
        assert "\u2028" in raw, "the name is written raw, as the test intends"
        assert verify_log(log_file, HMAC_KEY) == (3, 3, [])

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

    def test_mixed_tools_chain_passes(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        e1 = make_tool_entry(tool="Bash")
        e2 = make_entry(skill="checkpoint", prev_hmac=e1["hmac"])
        e3 = make_tool_entry(
            tool="Read", event="PostToolUseFailure", prev_hmac=e2["hmac"]
        )
        write_log(log_path, [e1, e2, e3])
        assert verify_log(log_path, HMAC_KEY) == (3, 3, [])

    def test_chain_continues_from_legacy_entries(self, tmp_path: Path) -> None:
        """A log begun in the earlier format and continued in this one verifies."""
        log_path = tmp_path / "audit.log"
        e1 = make_legacy_entry(skill="first")
        e2 = make_legacy_entry(skill="second", prev_hmac=e1["hmac"])
        e3 = make_tool_entry(tool="Bash", prev_hmac=e2["hmac"])
        e4 = make_entry(skill="verify", prev_hmac=e3["hmac"])
        write_log(log_path, [e1, e2, e3, e4])
        assert verify_log(log_path, HMAC_KEY) == (4, 4, [])

    def test_the_audit_skill_example_line_verifies(self, tmp_path: Path) -> None:
        """The record line skills/audit/SKILL.md shows verifies as a chain."""
        skill = Path(__file__).resolve().parents[1] / "skills" / "audit" / "SKILL.md"
        lines = skill.read_text(encoding="utf-8").splitlines()
        (example,) = [line for line in lines if line.startswith('{"action_id":')]
        log_path = tmp_path / "records.jsonl"
        log_path.write_text(example + "\n", encoding="utf-8")
        assert verify_log(log_path, "example-key") == (1, 1, [])

    def test_readme_example_entry_verifies(self, tmp_path: Path) -> None:
        """The entry hooks/README.md shows is one the hook would write."""
        readme = Path(__file__).resolve().parents[1] / "hooks" / "README.md"
        lines = readme.read_text(encoding="utf-8").splitlines()
        (example,) = [line for line in lines if line.startswith('{"action_id":')]
        log_path = tmp_path / "audit.log"
        log_path.write_text(example + "\n", encoding="utf-8")
        assert verify_log(log_path, "example-key") == (1, 1, [])

        entry = json.loads(example)
        canonical = json.dumps({"skill": "checkpoint"}, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        assert entry["details"]["input_sha256"] == digest

    def test_action_record_lines_verify(self, tmp_path: Path) -> None:
        """The line of STANDARD v1.2 §6.4 (an action record) verifies, also
        in a log that began with lines of the hook before it."""
        log_path = tmp_path / "audit.log"
        e1 = make_legacy_entry()
        e2 = make_entry(prev_hmac=e1["hmac"])
        e3 = make_record_entry(prev_hmac=e2["hmac"])
        e4 = make_record_entry(tool="Bash", status="failed", prev_hmac=e3["hmac"])
        write_log(log_path, [e1, e2, e3, e4])
        assert verify_log(log_path, HMAC_KEY) == (4, 4, [])

    def test_a_changed_action_record_line_breaks_the_chain(
        self, tmp_path: Path
    ) -> None:
        log_path = tmp_path / "audit.log"
        e1 = make_record_entry()
        e2 = make_record_entry(tool="Bash", prev_hmac=e1["hmac"])
        e1["status"] = "failed"
        write_log(log_path, [e1, e2])
        total, valid, errors = verify_log(log_path, HMAC_KEY)
        assert (total, valid) == (2, 1)
        assert any("HMAC mismatch" in e for e in errors)

    @pytest.mark.parametrize(
        "field", ["action_id", "timestamp", "actor", "intent", "status"]
    )
    def test_an_action_record_line_missing_a_field(self, field: str) -> None:
        entry = make_record_entry()
        del entry[field]
        errors = verify_entry(entry, "", HMAC_KEY)
        assert errors and "Missing fields" in errors[0] and field in errors[0]

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


@pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("openssl") is None,
    reason="the hook needs jq and openssl",
)
class TestRecordedBy:
    """Each line names the layer and its configuration (STANDARD 1.2.0
    §5.18.8): recorded_by, which the HMAC covers like every other field."""

    @staticmethod
    def _log(tmp_path: Path, **env: str) -> Path:
        payload = {"tool_name": "Read", "tool_input": {"file_path": "a"}}
        result = subprocess.run(
            [str(POSTTOOLUSE_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "CLAUDE_PROJECT_DIR": str(tmp_path),
                "AUDIT_HMAC_KEY": HMAC_KEY,
                **env,
            },
            timeout=30,
        )
        assert result.returncode == 0
        return tmp_path / ".claude" / "audit.log"

    def test_lines_with_recorded_by_verify(self, tmp_path: Path) -> None:
        self._log(tmp_path)
        log = self._log(tmp_path, ACS_HOOK_APPROVAL="off", ACS_CHECKPOINT_MAX_AGE="600")
        assert verify_log(log, HMAC_KEY) == (2, 2, [])
        first, second = [json.loads(line) for line in log.read_text().splitlines()]
        root = Path(__file__).resolve().parents[1]
        assert first["recorded_by"] == {
            "name": "agent-capability-standard plugin hooks",
            "version": json.loads(
                (root / ".claude-plugin" / "plugin.json").read_text()
            )["version"],
            "config_sha256": hashlib.sha256(
                (root / "hooks" / "hooks.json").read_bytes()
            ).hexdigest(),
            "settings": {"approval": "ask", "checkpoint_max_age_s": 1800},
        }
        assert second["recorded_by"]["settings"] == {
            "approval": "off",
            "checkpoint_max_age_s": 600,
        }
        assert list(first)[-3:] == ["recorded_by", "prev_hmac", "hmac"]

    @pytest.mark.parametrize(
        ("path", "value"),
        [(("config_sha256",), "0" * 64), (("settings", "approval"), "off")],
    )
    def test_tampering_with_recorded_by_breaks_the_chain(
        self, tmp_path: Path, path: tuple[str, ...], value: str
    ) -> None:
        log = self._log(tmp_path)
        entry = json.loads(log.read_text())
        target = entry["recorded_by"]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        write_log(log, [entry])
        checked, valid, errors = verify_log(log, HMAC_KEY)
        assert (checked, valid) == (1, 0)
        assert errors
