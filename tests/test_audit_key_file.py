"""The audit log's key file, ``~/.config/acs/audit.key`` (#183).

The log hook (``hooks/posttooluse_log_tool.sh``) and the verifier
(``tools/verify_audit_log.py``) read the key from that file when it exists,
else from ``AUDIT_HMAC_KEY``; no key is derived from the host name. They
refuse a key file that is a symbolic link, not a regular file, readable or
writable by group or others, has more than one link (a hard link made where
a sandboxed command can read defeats a read denial: the Linux spike on
#141), sits in a directory that is a symbolic link or that group or others
can write, or whose first line is not 32 to 4096 visible ASCII characters;
the hook also refuses one whose directory is inside the project directory.
A refused file is not replaced by ``AUDIT_HMAC_KEY``. The hook builds the
HMAC from SHA-256, so the key is on no command line. Without a key, the hook writes the line unsigned (its
``hmac`` empty), leaves the head as it is, says why and exits 1; the
verifier reports every unsigned line, and with no key runs no check (exit
2).

Every key here is made in a HOME of the test's own: conftest gives every
test an empty HOME, and no test reads the person's key file.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "posttooluse_log_tool.sh"
VERIFIER = ROOT / "tools" / "verify_audit_log.py"
sys.path.insert(0, str(ROOT / "tools"))

from verify_audit_log import (  # noqa: E402
    AuditKeyError,
    get_default_hmac_key,
    verify_log,
)

KEY = "0123456789abcdef" * 4  # 64 characters, as the documented command makes
ENV_KEY = "a-key-from-the-environment"


def _bashes() -> list[str]:
    """Each bash on this machine, once: CI runs macOS /bin/bash 3.2, and
    Homebrew's or Linux's bash 5."""
    found: dict[str, str] = {}
    for candidate in ("/bin/bash", "/opt/homebrew/bin/bash", "/usr/local/bin/bash"):
        if os.access(candidate, os.X_OK):
            found.setdefault(os.path.realpath(candidate), candidate)
    return list(found.values())


pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("openssl") is None or not _bashes(),
    reason="the hook needs bash, jq and openssl",
)


def make_key(home: Path, text: str = KEY, mode: int = 0o600) -> Path:
    """The key file under ``home``, as the documented command makes it (a
    directory of mode 700, the file of mode 600)."""
    directory = home / ".config" / "acs"
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    path = directory / "audit.key"
    path.write_text(text, encoding="ascii")
    path.chmod(mode)
    return path


def log_call(
    bash: str,
    project: Path,
    home: Path,
    env_key: str | None = None,
    call_id: str = "toolu_1",
    path: str | None = None,
    tool_name: str = "Read",
    tool_input: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    """One PostToolUse call through the log hook, run by ``bash`` with -p
    (so the hook does not start another bash), HOME ``home``."""
    env = {k: v for k, v in os.environ.items() if k != "AUDIT_HMAC_KEY"}
    env.update({"HOME": str(home), "CLAUDE_PROJECT_DIR": str(project)})
    if path is not None:
        env["PATH"] = path
    if env_key is not None:
        env["AUDIT_HMAC_KEY"] = env_key
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_use_id": call_id,
        "tool_input": {"file_path": "a"} if tool_input is None else tool_input,
    }
    return subprocess.run(
        [bash, "-p", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def lines(project: Path) -> list[dict]:
    text = (project / ".claude" / "audit.log").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def cli(home: Path, project: Path, *args: str, env_key: str | None = None):
    env = {k: v for k, v in os.environ.items() if k != "AUDIT_HMAC_KEY"}
    env["HOME"] = str(home)
    if env_key is not None:
        env["AUDIT_HMAC_KEY"] = env_key
    return subprocess.run(
        [sys.executable, str(VERIFIER), *args],
        capture_output=True,
        text=True,
        cwd=project,
        env=env,
        timeout=60,
    )


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


@pytest.mark.parametrize("bash", _bashes())
class TestTheHook:
    def test_the_key_file_signs_and_the_verifier_reads_it(
        self, bash: str, home: Path, project: Path
    ) -> None:
        make_key(home)
        for call_id in ("toolu_1", "toolu_2"):
            result = log_call(bash, project, home, call_id=call_id)
            assert result.returncode == 0, result.stderr
        log = project / ".claude" / "audit.log"
        head = project / ".claude" / "audit.head"
        assert verify_log(log, KEY, head) == (2, 2, [])
        result = cli(home, project)
        assert result.returncode == 0, result.stdout
        assert "2/2 entries verified" in result.stdout

    def test_a_trailing_line_break_is_not_part_of_the_key(
        self, bash: str, home: Path, project: Path
    ) -> None:
        make_key(home, KEY + "\n")
        assert log_call(bash, project, home).returncode == 0
        log = project / ".claude" / "audit.log"
        assert verify_log(log, KEY, project / ".claude" / "audit.head") == (1, 1, [])
        assert cli(home, project).returncode == 0

    def test_the_file_wins_over_the_environment(
        self, bash: str, home: Path, project: Path
    ) -> None:
        make_key(home)
        result = log_call(bash, project, home, env_key=ENV_KEY)
        assert result.returncode == 0, result.stderr
        log = project / ".claude" / "audit.log"
        assert verify_log(log, KEY, None) == (1, 1, [])
        assert verify_log(log, ENV_KEY, None)[1] == 0
        # The verifier reads the file too, with the variable set.
        result = cli(home, project, env_key=ENV_KEY)
        assert result.returncode == 0, result.stdout

    def test_the_environment_signs_where_there_is_no_file(
        self, bash: str, home: Path, project: Path
    ) -> None:
        result = log_call(bash, project, home, env_key=ENV_KEY)
        assert result.returncode == 0, result.stderr
        assert verify_log(project / ".claude" / "audit.log", ENV_KEY, None) == (
            1,
            1,
            [],
        )
        assert cli(home, project, env_key=ENV_KEY).returncode == 0

    def test_a_name_that_holds_the_file_key_is_redacted(
        self, bash: str, home: Path, project: Path
    ) -> None:
        """The key read from the file is a credential the hook holds
        (STANDARD 1.2.0 §6.7): a tool name or a skill name that holds it is
        logged as [REDACTED], as one that holds AUDIT_HMAC_KEY is, so the
        signed log never carries the key that signs it."""
        make_key(home)
        result = log_call(bash, project, home, tool_name=f"mcp__srv__{KEY}")
        assert result.returncode == 0, result.stderr
        result = log_call(
            bash,
            project,
            home,
            call_id="toolu_2",
            tool_name="Skill",
            tool_input={"skill": f"x{KEY}"},
        )
        assert result.returncode == 0, result.stderr
        log = project / ".claude" / "audit.log"
        text = log.read_text(encoding="utf-8")
        assert KEY not in text
        first, second = lines(project)
        assert first["tool"] == "[REDACTED]"
        assert second["details"]["skill"] == "[REDACTED]"
        assert verify_log(log, KEY, project / ".claude" / "audit.head") == (2, 2, [])

    def test_without_a_key_the_line_is_unsigned_and_said(
        self, bash: str, home: Path, project: Path
    ) -> None:
        result = log_call(bash, project, home)
        assert result.returncode == 1
        assert "no audit key" in result.stderr
        assert "logged unsigned" in result.stderr
        (line,) = lines(project)
        assert line["hmac"] == "" and line["prev_hmac"] == ""
        assert line["details"]["input_sha256"] != "unavailable"
        # No head is signed with no key.
        assert not (project / ".claude" / "audit.head").exists()
        # No key derived from the host name signs anything.
        assert "grounded-agency-audit" not in HOOK.read_text(encoding="utf-8")
        assert "hostname" not in HOOK.read_text(encoding="utf-8")

    def test_an_unsigned_line_leaves_the_head_and_fails_verification(
        self, bash: str, home: Path, project: Path
    ) -> None:
        log_call(bash, project, home, env_key=ENV_KEY, call_id="toolu_1")
        head = project / ".claude" / "audit.head"
        before = head.read_text(encoding="utf-8")
        result = log_call(bash, project, home, call_id="toolu_2")
        assert result.returncode == 1
        assert head.read_text(encoding="utf-8") == before
        first, second = lines(project)
        assert second["prev_hmac"] == first["hmac"] and second["hmac"] == ""
        total, valid, errors = verify_log(
            project / ".claude" / "audit.log", ENV_KEY, head
        )
        assert (total, valid) == (2, 1)
        assert errors == [
            "Line 2: Unsigned: the hook wrote this line without a key (no key "
            "file and no AUDIT_HMAC_KEY, a key file it refused, or no openssl), "
            "so nothing shows whether it was changed"
        ]
        # A signed line after it starts a new chain, which verifies.
        result = log_call(bash, project, home, env_key=ENV_KEY, call_id="toolu_3")
        assert result.returncode == 1
        assert "starts a new chain" in result.stderr
        assert lines(project)[2]["prev_hmac"] == ""
        total, valid, errors = verify_log(
            project / ".claude" / "audit.log", ENV_KEY, head
        )
        assert (total, valid) == (3, 2) and len(errors) == 1


def _refused(kind: str, home: Path, tmp_path: Path) -> str:
    """Make a key file ``kind`` refuses under ``home``; the words the
    refusal holds."""
    if kind in ("640", "644", "604", "660", "602"):
        make_key(home, mode=int(kind, 8))
        return f"its mode is {kind}"
    if kind == "hard link":
        path = make_key(home)
        os.link(path, tmp_path / "elsewhere.key")
        return "it has 2 hard links"
    if kind == "symbolic link":
        target = make_key(tmp_path / "other-home")
        directory = home / ".config" / "acs"
        directory.mkdir(parents=True)
        directory.chmod(0o700)
        (directory / "audit.key").symlink_to(target)
        return "it is a symbolic link"
    if kind == "directory":
        directory = home / ".config" / "acs" / "audit.key"
        directory.mkdir(parents=True)
        directory.parent.chmod(0o700)
        return "it is not a regular file"
    if kind == "writable directory":
        path = make_key(home)
        path.parent.chmod(0o770)
        return "its directory's mode is 770"
    if kind == "linked directory":
        # ~/.config/acs a link to a directory that passes every other rule
        # (as a dotfile manager makes it): stat would read the link.
        target = make_key(tmp_path / "elsewhere").parent
        (home / ".config").mkdir(parents=True)
        (home / ".config" / "acs").symlink_to(target)
        return "its directory is a symbolic link"
    if kind == "linked writable directory":
        target = make_key(tmp_path / "elsewhere").parent
        target.chmod(0o770)
        (home / ".config").mkdir(parents=True)
        (home / ".config" / "acs").symlink_to(target)
        return "its directory is a symbolic link"
    if kind == "short":
        make_key(home, "a" * 31)
        return "is not a key of 32 to 4096 visible ASCII characters"
    if kind == "blank":
        make_key(home, KEY[:20] + " " + KEY[20:])
        return "is not a key of 32 to 4096 visible ASCII characters"
    if kind == "empty":
        make_key(home, "")
        return "is not a key of 32 to 4096 visible ASCII characters"
    if kind == "crlf":
        make_key(home, KEY + "\r\n")
        return "is not a key of 32 to 4096 visible ASCII characters"
    raise AssertionError(kind)


REFUSED = [
    "640",
    "644",
    "604",
    "660",
    "602",
    "hard link",
    "symbolic link",
    "directory",
    "writable directory",
    "linked directory",
    "linked writable directory",
    "short",
    "blank",
    "empty",
    "crlf",
]


@pytest.mark.parametrize("kind", REFUSED)
@pytest.mark.parametrize("bash", _bashes())
def test_the_hook_refuses_a_key_file(
    bash: str, kind: str, home: Path, project: Path, tmp_path: Path
) -> None:
    """A refused file signs nothing, and AUDIT_HMAC_KEY does not sign in
    its place: the line is unsigned, and the hook says why."""
    words = _refused(kind, home, tmp_path)
    result = log_call(bash, project, home, env_key=ENV_KEY)
    assert result.returncode == 1
    assert "is refused" in result.stderr and words in result.stderr
    assert "AUDIT_HMAC_KEY is not used in its place" in result.stderr
    assert KEY not in result.stderr and ENV_KEY not in result.stderr
    (line,) = lines(project)
    assert line["hmac"] == ""
    assert not (project / ".claude" / "audit.head").exists()


@pytest.mark.parametrize("kind", REFUSED)
def test_the_verifier_refuses_the_same_key_files(
    kind: str,
    home: Path,
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    words = _refused(kind, home, tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AUDIT_HMAC_KEY", ENV_KEY)
    with pytest.raises(AuditKeyError) as refused:
        get_default_hmac_key()
    assert words in str(refused.value)
    assert "AUDIT_HMAC_KEY is not used in its place" in str(refused.value)
    result = cli(home, project, env_key=ENV_KEY)
    assert result.returncode == 2
    assert "INTEGRITY CHECK NOT RUN" in result.stdout and words in result.stdout
    assert KEY not in result.stdout and ENV_KEY not in result.stdout


def test_the_verifier_reads_the_key_as_the_hook_does(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AUDIT_HMAC_KEY", raising=False)
    with pytest.raises(AuditKeyError, match="no audit key"):
        get_default_hmac_key()
    monkeypatch.setenv("AUDIT_HMAC_KEY", ENV_KEY)
    assert get_default_hmac_key() == ENV_KEY
    make_key(home, KEY + "\nsecond line\n", mode=0o400)
    assert get_default_hmac_key() == KEY
    monkeypatch.setenv("HOME", "relative/home")
    assert get_default_hmac_key() == ENV_KEY


def test_with_no_key_the_verifier_runs_no_check(home: Path, project: Path) -> None:
    result = cli(home, project)
    assert result.returncode == 2
    assert result.stdout.startswith("INTEGRITY CHECK NOT RUN: no audit key")
    assert "--hmac-key" in result.stdout


def test_a_log_signed_with_the_host_name_key_verifies_with_that_key(
    home: Path, project: Path, tmp_path: Path
) -> None:
    """The upgrading note's command (hooks/README.md, CHANGELOG): a log the
    earlier hook signed with the key it derived from the host name, moved
    aside with its head and its anchor, verifies with that key."""
    host = subprocess.run(
        ["hostname", "-s"], capture_output=True, text=True, check=False
    ).stdout.strip()
    # As the earlier hook made it: `hostname -s`, else "default".
    old_key = "grounded-agency-audit-" + (host or "default")
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    for call_id in ("toolu_1", "toolu_2"):
        log_call(_bashes()[0], project, home, env_key=old_key, call_id=call_id)
    anchor = project / ".git" / "acs" / "audit.head"
    assert anchor.is_file()
    moved = tmp_path / "moved"
    moved.mkdir()
    (project / ".claude" / "audit.log").rename(moved / "audit.log")
    (project / ".claude" / "audit.head").rename(moved / "audit.head")
    anchor.rename(moved / "anchor.head")
    make_key(home)
    args = (
        "--log-file",
        "moved/audit.log",
        "--head-file",
        "moved/audit.head",
        "--anchor-file",
        "moved/anchor.head",
    )
    # With the key file it fails; with the documented key it verifies.
    assert cli(home, tmp_path, *args).returncode == 1
    result = subprocess.run(
        [
            "bash",
            "-c",
            'exec "$0" "$1" --hmac-key "grounded-agency-audit-$(hostname -s)" "${@:2}"',
            sys.executable,
            str(VERIFIER),
            *args,
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "HOME": str(home)},
        timeout=60,
    )
    if host:
        assert result.returncode == 0, result.stdout
        assert "2/2 entries verified" in result.stdout
    result = cli(home, tmp_path, *args, "--hmac-key", old_key)
    assert result.returncode == 0, result.stdout


def test_the_audit_skills_records_verify_with_audit_hmac_key(
    home: Path, project: Path
) -> None:
    """The skill signs under AUDIT_HMAC_KEY only. With a key file present
    as well, its records verify with the documented --hmac-key
    "$AUDIT_HMAC_KEY", not with the default key."""
    skill = ROOT / "skills" / "audit" / "SKILL.md"
    (line,) = [
        x
        for x in skill.read_text(encoding="utf-8").splitlines()
        if x.startswith('{"action_id":')
    ]
    records = project / ".claude" / "audit" / "records.jsonl"
    records.parent.mkdir(parents=True)
    records.write_text(line + "\n", encoding="utf-8")
    make_key(home)
    args = ("--log-file", ".claude/audit/records.jsonl", "--no-head")
    result = cli(home, project, *args, env_key="example-key")
    assert result.returncode == 1 and "HMAC mismatch" in result.stdout
    result = subprocess.run(
        [
            "bash",
            "-c",
            'exec "$0" "$1" "${@:2}" --hmac-key "$AUDIT_HMAC_KEY"',
            sys.executable,
            str(VERIFIER),
            *args,
        ],
        capture_output=True,
        text=True,
        cwd=project,
        env={**os.environ, "HOME": str(home), "AUDIT_HMAC_KEY": "example-key"},
        timeout=60,
    )
    assert result.returncode == 0, result.stdout
    assert "1/1 entries verified" in result.stdout


@pytest.mark.parametrize("bash", _bashes())
@pytest.mark.parametrize("where", ["home is the project", "home in the project"])
def test_the_hook_refuses_a_key_file_in_the_project_directory(
    bash: str, where: str, tmp_path: Path
) -> None:
    """The sandbox lets the agent's commands write the project directory,
    so a key file there is refused: the line is unsigned (exit 1)."""
    if where == "home is the project":
        home = project = tmp_path / "home"
    else:
        project = tmp_path / "project"
        home = project / "home"
    home.mkdir(parents=True)
    make_key(home)
    result = log_call(bash, project, home, env_key=ENV_KEY)
    assert result.returncode == 1
    assert "its directory is inside the project directory" in result.stderr
    assert KEY not in result.stderr
    (line,) = lines(project)
    assert line["hmac"] == ""


def _fake_openssl(tmp_path: Path) -> tuple[str, Path]:
    """A PATH whose first directory holds an ``openssl`` that writes its
    arguments to a file and runs the real one; the file."""
    real = shutil.which("openssl")
    assert real is not None
    fake_dir = tmp_path / "fakebin"
    fake_dir.mkdir()
    record = tmp_path / "openssl-args"
    fake = fake_dir / "openssl"
    fake.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{record}'\nexec '{real}' \"$@\"\n",
        encoding="ascii",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return f"{fake_dir}:{os.environ.get('PATH', '')}", record


@pytest.mark.parametrize("bash", _bashes())
@pytest.mark.parametrize("source", ["file", "environment"])
def test_the_key_is_on_no_command_line(
    bash: str, source: str, home: Path, project: Path, tmp_path: Path
) -> None:
    """The hook signs the line and the head without passing the key to
    openssl as an argument, which the process list would show."""
    path, record = _fake_openssl(tmp_path)
    env_key = None
    if source == "file":
        make_key(home)
        key = KEY
    else:
        key = env_key = "e" * 40
    for call_id in ("toolu_1", "toolu_2"):
        result = log_call(
            bash, project, home, env_key=env_key, call_id=call_id, path=path
        )
        assert result.returncode == 0, result.stderr
    calls = record.read_text(encoding="ascii")
    assert "dgst" in calls  # the fake openssl was the one run
    assert key not in calls and "-hmac" not in calls
    log = project / ".claude" / "audit.log"
    assert verify_log(log, key, project / ".claude" / "audit.head") == (2, 2, [])


@pytest.mark.parametrize("bash", _bashes())
@pytest.mark.parametrize(
    "key",
    [
        "k" * 32,
        "6" * 32,  # a zero byte in every place of the inner pad
        "\\" * 64,  # a zero byte in every place of the outer pad
        "m" * 65,  # over 64 bytes: hashed first
        "%s%d" * 1024,  # 4096 bytes, printf directives in it
        "ünïcödé-" * 8,  # 72 bytes in 64 characters
    ],
    ids=["32", "inner-zeros", "outer-zeros", "65", "4096", "non-ascii"],
)
def test_the_hmac_matches_pythons(
    bash: str, key: str, home: Path, project: Path
) -> None:
    """The hook's HMAC (built from SHA-256) is the one Python's hmac
    computes, for short and long keys and keys whose pads hold zero bytes."""
    result = log_call(bash, project, home, env_key=key)
    assert result.returncode == 0, result.stderr
    raw = (project / ".claude" / "audit.log").read_text(encoding="utf-8").rstrip("\n")
    content, _, _ = raw.rpartition(',"hmac":')
    expected = hmac.new(
        key.encode("utf-8"), (content + "}").encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert lines(project)[0]["hmac"] == expected
    head = json.loads((project / ".claude" / "audit.head").read_text("utf-8"))
    assert (
        head["head_hmac"]
        == hmac.new(
            key.encode("utf-8"),
            f"acs-audit-head:1:{expected}".encode(),
            hashlib.sha256,
        ).hexdigest()
    )
