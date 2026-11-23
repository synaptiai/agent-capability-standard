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


@pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("openssl") is None,
    reason="the hook needs jq and openssl",
)
class TestHead:
    """The chain shows a changed or removed entry by the link of the entry
    after it; removing the last entries, or the whole log, breaks no link
    (security round 1, batch 8). The hook keeps the chain's end in
    .claude/audit.head, signed with the log's key, and the verifier checks
    that the log still holds that entry at its place."""

    VERIFIER = Path(__file__).resolve().parents[1] / "tools" / "verify_audit_log.py"

    @staticmethod
    def _call(
        tmp_path: Path, call_id: str, key: str = HMAC_KEY
    ) -> subprocess.CompletedProcess:
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_use_id": call_id,
            "tool_input": {"file_path": "a"},
        }
        return subprocess.run(
            [str(POSTTOOLUSE_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "CLAUDE_PROJECT_DIR": str(tmp_path),
                "AUDIT_HMAC_KEY": key,
            },
            timeout=30,
        )

    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.VERIFIER), "--hmac-key", HMAC_KEY, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _three(self, tmp_path: Path) -> tuple[Path, Path]:
        for call_id in ("toolu_1", "toolu_2", "toolu_3"):
            assert self._call(tmp_path, call_id).returncode == 0
        return tmp_path / ".claude" / "audit.log", tmp_path / ".claude" / "audit.head"

    def test_the_hook_keeps_the_chain_end_in_a_head(self, tmp_path: Path) -> None:
        log, head = self._three(tmp_path)
        last = json.loads(log.read_text().splitlines()[-1])
        kept = json.loads(head.read_text())
        assert kept["entries"] == 3 and kept["hmac"] == last["hmac"]
        assert kept["head_hmac"] == compute_hmac(
            f"acs-audit-head:3:{last['hmac']}", HMAC_KEY
        )
        assert verify_log(log, HMAC_KEY, head) == (3, 3, [])
        result = self._cli("--log-file", str(log))
        assert result.returncode == 0, result.stdout
        assert "3/3 entries verified" in result.stdout

    def test_a_log_cut_short_fails_verification(self, tmp_path: Path) -> None:
        """The verifier's report: the first two lines of three verify as a
        chain, and no longer as the log its head anchors."""
        log, head = self._three(tmp_path)
        cut = tmp_path / "trunc.log"
        cut.write_text("\n".join(log.read_text().splitlines()[:2]) + "\n")
        total, valid, errors = verify_log(cut, HMAC_KEY, head)
        assert (total, valid) == (2, 2)
        assert errors == [
            "Head: the log ends before its head: 3 entries recorded, 2 found "
            "(its last entries were removed)"
        ]
        result = self._cli("--log-file", str(cut), "--head-file", str(head))
        assert result.returncode == 1 and "ends before its head" in result.stdout
        # By default the head beside the log is read, and there is none.
        result = self._cli("--log-file", str(cut))
        assert result.returncode == 1 and "Head not found" in result.stdout
        # The chain alone, as before.
        assert self._cli("--log-file", str(cut), "--no-head").returncode == 0

    def test_the_hook_keeps_the_head_of_a_cut_log_as_evidence(
        self, tmp_path: Path
    ) -> None:
        """The last line removed, then one more call: the hook says so, and
        the line it chains onto the shortened log does not make it verify."""
        log, head = self._three(tmp_path)
        before = head.read_text()
        log.write_text("\n".join(log.read_text().splitlines()[:2]) + "\n")
        result = self._call(tmp_path, "toolu_4")
        assert result.returncode == 1
        assert "no longer holds the entry its head records" in result.stderr
        assert head.read_text() == before
        assert [
            json.loads(line)["call_id"] for line in log.read_text().splitlines()
        ] == [
            "toolu_1",
            "toolu_2",
            "toolu_4",
        ]
        total, valid, errors = verify_log(log, HMAC_KEY, head)
        assert (total, valid) == (3, 3)
        assert errors == [
            "Head: entry 3 is not the one the head records "
            "(entries were removed or replaced)"
        ]
        # And it stays so at every later call.
        assert self._call(tmp_path, "toolu_5").returncode == 1
        assert verify_log(log, HMAC_KEY, head)[2]

    def test_a_removed_log_fails_verification(self, tmp_path: Path) -> None:
        log, head = self._three(tmp_path)
        log.unlink()
        assert verify_log(log, HMAC_KEY, head)[2] == [
            "Audit log not found",
            "Audit log not found, though its head records 3 entries",
        ]
        assert self._call(tmp_path, "toolu_4").returncode == 1
        errors = verify_log(log, HMAC_KEY, head)[2]
        assert errors == [
            "Head: the log ends before its head: 3 entries recorded, 1 found "
            "(its last entries were removed)"
        ]

    def test_a_head_another_key_signed_is_not_used(self, tmp_path: Path) -> None:
        """A head for the shortened log, signed with another key (the hook's
        default one, say): the verifier refuses it, and the hook keeps it."""
        log, head = self._three(tmp_path)
        lines = log.read_text().splitlines()[:2]
        log.write_text("\n".join(lines) + "\n")
        second = json.loads(lines[1])["hmac"]
        forged = {
            "entries": 2,
            "hmac": second,
            "head_hmac": compute_hmac(f"acs-audit-head:2:{second}", "another-key"),
        }
        head.write_text(json.dumps(forged) + "\n")
        assert verify_log(log, HMAC_KEY, head)[2] == [
            "Head HMAC mismatch: the head was not signed with this key"
        ]
        assert self._call(tmp_path, "toolu_4").returncode == 1
        assert json.loads(head.read_text()) == forged

    def test_a_log_begun_before_the_head_is_anchored_from_then_on(
        self, tmp_path: Path
    ) -> None:
        log, head = self._three(tmp_path)
        head.unlink()
        result = self._call(tmp_path, "toolu_4")
        assert result.returncode == 1
        assert "had no head" in result.stderr
        assert json.loads(head.read_text())["entries"] == 4
        assert verify_log(log, HMAC_KEY, head) == (4, 4, [])
        assert self._call(tmp_path, "toolu_5").returncode == 0

    def test_a_head_behind_the_log_still_anchors_it(self, tmp_path: Path) -> None:
        """A run that appended its line and could not move the head leaves
        it on an earlier entry, which the log still holds at its place."""
        log, head = self._three(tmp_path)
        second = json.loads(log.read_text().splitlines()[1])["hmac"]
        head.write_text(
            json.dumps(
                {
                    "entries": 2,
                    "hmac": second,
                    "head_hmac": compute_hmac(f"acs-audit-head:2:{second}", HMAC_KEY),
                }
            )
            + "\n"
        )
        assert verify_log(log, HMAC_KEY, head) == (3, 3, [])
        assert self._call(tmp_path, "toolu_4").returncode == 0
        assert json.loads(head.read_text())["entries"] == 4


@pytest.mark.skipif(
    shutil.which("jq") is None
    or shutil.which("openssl") is None
    or shutil.which("git") is None,
    reason="the hook needs jq and openssl, and the anchor a git directory",
)
class TestAnchor:
    """A command that removes .claude whole (rm -rf .claude, git clean
    -fdx) removes the log with its head: the next line begins a new log
    that verifies (security round 3, batch 1, #4). The hook keeps the
    same head in the project's git directory, <git dir>/acs/audit.head,
    which such a command leaves, and the hook and the verifier both check
    the log against it."""

    VERIFIER = Path(__file__).resolve().parents[1] / "tools" / "verify_audit_log.py"

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "proj"
        project.mkdir()
        subprocess.run(
            ["git", "init", "-q"], cwd=project, check=True, capture_output=True
        )
        return project

    def _cli(self, project: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.VERIFIER), "--hmac-key", HMAC_KEY, *args],
            capture_output=True,
            text=True,
            cwd=project,
            timeout=30,
        )

    def _three(self, project: Path) -> tuple[Path, Path, Path]:
        for call_id in ("toolu_1", "toolu_2", "toolu_3"):
            assert TestHead._call(project, call_id).returncode == 0
        return (
            project / ".claude" / "audit.log",
            project / ".claude" / "audit.head",
            project / ".git" / "acs" / "audit.head",
        )

    def test_the_hook_keeps_the_anchor_beside_the_head(self, project: Path) -> None:
        log, head, anchor = self._three(project)
        assert anchor.read_text() == head.read_text()
        assert verify_log(log, HMAC_KEY, head, anchor) == (3, 3, [])
        result = self._cli(project)
        assert result.returncode == 0, result.stdout
        assert "3/3 entries verified" in result.stdout

    @pytest.mark.parametrize("how", ["rm -rf .claude", "git clean -fdx"])
    def test_a_log_removed_with_its_head_fails_verification(
        self, project: Path, how: str
    ) -> None:
        """The verifier's reproduction: three entries, one of them a git
        push --force, then .claude removed and one more call logged."""
        log, head, anchor = self._three(project)
        subprocess.run(how.split(), cwd=project, check=True, capture_output=True)
        assert not log.exists() and not head.exists() and anchor.exists()
        result = TestHead._call(project, "toolu_4")
        assert result.returncode == 1
        assert "anchor" in result.stderr
        assert not head.exists()
        assert len(log.read_text().splitlines()) == 1
        errors = verify_log(log, HMAC_KEY, head, anchor)[2]
        assert any(
            e.startswith("Anchor: the log ends before its anchor") for e in errors
        )
        for args in ((), ("--head-file", ".claude/audit.head")):
            cli = self._cli(project, *args)
            assert cli.returncode == 1, args
            assert "INTEGRITY CHECK FAILED" in cli.stdout
        # And it stays so at every later call.
        assert TestHead._call(project, "toolu_5").returncode == 1
        assert self._cli(project).returncode == 1

    def test_moving_all_three_aside_starts_a_new_log(self, project: Path) -> None:
        log, head, anchor = self._three(project)
        for path in (log, head, anchor):
            path.rename(path.with_name(path.name + ".old"))
        assert TestHead._call(project, "toolu_4").returncode == 0
        assert verify_log(log, HMAC_KEY, head, anchor) == (1, 1, [])
        assert self._cli(project).returncode == 0

    def test_an_anchor_behind_the_log_still_anchors_it(self, project: Path) -> None:
        log, head, anchor = self._three(project)
        second = json.loads(log.read_text().splitlines()[1])["hmac"]
        anchor.write_text(
            json.dumps(
                {
                    "entries": 2,
                    "hmac": second,
                    "head_hmac": compute_hmac(f"acs-audit-head:2:{second}", HMAC_KEY),
                }
            )
            + "\n"
        )
        assert verify_log(log, HMAC_KEY, head, anchor) == (3, 3, [])
        assert TestHead._call(project, "toolu_4").returncode == 0
        assert json.loads(anchor.read_text())["entries"] == 4

    def test_an_anchor_the_hook_cannot_keep_is_reported(
        self, project: Path, tmp_path: Path
    ) -> None:
        """A link at the git directory's acs/: the hook writes nothing
        through it, and says the anchor is not kept."""
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (project / ".git" / "acs").symlink_to(elsewhere)
        result = TestHead._call(project, "toolu_1")
        assert result.returncode == 1
        assert "anchor is not kept" in result.stderr
        assert not any(elsewhere.iterdir())
        assert (project / ".claude" / "audit.head").exists()

    def test_without_a_git_directory_there_is_no_anchor(self, tmp_path: Path) -> None:
        for call_id in ("toolu_1", "toolu_2"):
            assert TestHead._call(tmp_path, call_id).returncode == 0
        assert not (tmp_path / ".git").exists()
        log = tmp_path / ".claude" / "audit.log"
        assert verify_log(log, HMAC_KEY, log.with_suffix(".head"), None) == (2, 2, [])


@pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("openssl") is None,
    reason="the hook needs jq and openssl",
)
class TestTheBytesSigned:
    """A line verifies only as the bytes the hook signed (hooks/
    posttooluse_log_tool.sh: "hmac: HMAC-SHA-256 of the line without hmac,
    as written"). Without the key, a line edited so that it parses to the
    same entry (a member named twice, whose last value is the signed one;
    a blank; an escape) used to pass, while a reader that keeps the first of
    two members, or greps the text, read another status or tool."""

    KEY = "op-secret-7f3a9c"

    def _log(self, tmp_path: Path) -> Path:
        """Two lines the hook writes: a failed Bash call, a Read."""
        for event, tool, tool_input in (
            ("PostToolUseFailure", "Bash", {"command": "make deploy"}),
            ("PostToolUse", "Read", {"file_path": "a.txt"}),
        ):
            payload = {
                "hook_event_name": event,
                "tool_name": tool,
                "tool_input": tool_input,
                "tool_use_id": f"toolu_{tool}",
            }
            result = subprocess.run(
                [str(POSTTOOLUSE_HOOK)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "CLAUDE_PROJECT_DIR": str(tmp_path),
                    "AUDIT_HMAC_KEY": self.KEY,
                },
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
        log = tmp_path / ".claude" / "audit.log"
        assert verify_log(log, self.KEY, tmp_path / ".claude" / "audit.head") == (
            2,
            2,
            [],
        )
        return log

    def _edit(self, log: Path, old: str, new: str) -> None:
        """Replace ``old`` in the first line (the failed Bash call)."""
        first, rest = log.read_text(encoding="utf-8").split("\n", 1)
        assert first.count(old) == 1, old
        log.write_text(first.replace(old, new) + "\n" + rest, encoding="utf-8")

    def _fails(self, log: Path, why: str) -> None:
        total, valid, errors = verify_log(log, self.KEY, log.with_suffix(".head"))
        assert (total, valid) == (2, 1), errors
        assert any(why in e for e in errors), errors

    def test_a_member_named_twice_is_refused(self, tmp_path: Path) -> None:
        """The reported edit: the failed Bash call reads as an executed Read
        to a reader that keeps the first member."""
        log = self._log(tmp_path)
        self._edit(
            log,
            '"status":"failed","tool":"Bash"',
            '"status":"executed","status":"failed","tool":"Read","tool":"Bash"',
        )
        self._fails(log, "'status' named twice")

    @pytest.mark.parametrize(
        ("old", "new", "why"),
        [
            # A forged note before the line's own hmac.
            (
                '{"action_id"',
                '{"hmac":"reviewed: approved by security on-call","action_id"',
                "'hmac' named twice",
            ),
            # Forged details just before the real ones.
            (
                '"details":{"event":"PostToolUseFailure"',
                '"details":{"event":"PostToolUse","approved_by":"alice"},"details":{"event":"PostToolUseFailure"',
                "'details' named twice",
            ),
            # A member named twice inside a nested object.
            (
                '"details":{"event":"PostToolUseFailure"',
                '"details":{"event":"PostToolUse","event":"PostToolUseFailure"',
                "'event' named twice",
            ),
        ],
    )
    def test_forged_members_are_refused(
        self, tmp_path: Path, old: str, new: str, why: str
    ) -> None:
        log = self._log(tmp_path)
        self._edit(log, old, new)
        self._fails(log, why)

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            ('"status":"failed"', '"status": "failed"'),
            ('"status":"failed"', '"status":"f\\u0061iled"'),
            ('"tool":"Bash"', '"tool":"Bas\\u0068"'),
        ],
    )
    def test_a_blank_or_an_escape_inserted_is_refused(
        self, tmp_path: Path, old: str, new: str
    ) -> None:
        log = self._log(tmp_path)
        self._edit(log, old, new)
        self._fails(log, "not the compact JSON the hook writes")

    def test_a_line_whose_hmac_is_not_last_is_refused(self, tmp_path: Path) -> None:
        log = self._log(tmp_path)
        lines = log.read_text(encoding="utf-8").split("\n")
        entry = json.loads(lines[0])
        moved = {"hmac": entry.pop("hmac"), **entry}
        lines[0] = json.dumps(moved, separators=(",", ":"), ensure_ascii=False)
        log.write_text("\n".join(lines), encoding="utf-8")
        self._fails(log, "does not end with its hmac member")

    def test_blanks_around_a_line_are_refused(self, tmp_path: Path) -> None:
        log = self._log(tmp_path)
        text = log.read_text(encoding="utf-8")
        log.write_text(" " + text, encoding="utf-8")
        self._fails(log, "not the compact JSON the hook writes")

    def test_a_blank_line_is_reported(self, tmp_path: Path) -> None:
        """The hook writes none; the entries around it still verify."""
        log = self._log(tmp_path)
        log.write_text(
            log.read_text(encoding="utf-8").replace("\n", "\n \n", 1), encoding="utf-8"
        )
        total, valid, errors = verify_log(
            log,
            self.KEY,
            log.with_suffix(".head"),
        )
        assert (total, valid) == (3, 2)
        assert any("Line 2: a blank line" in e for e in errors), errors
