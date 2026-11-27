"""HMAC-SHA-256 with the key on no command line (#183).

``openssl dgst -hmac KEY`` puts the key in the process list, which any
process of the user can read. The hooks that sign with a key compute the
HMAC from openssl's SHA-256 instead, passing the key and the pads through
pipes: the log hook (the audit key), the take hook (signing a checkpoint's
commit entry under the project's checkpoint key), the pre-tool-use hook and
the rollback skill's hook (checking an entry). Each copies one POSIX sh
implementation, ``hooks/hmac_sha256.sh``, verbatim (the rollback skill's
hook runs under sh, dash on Linux). The value is the one ``openssl dgst
-hmac`` gave, so commit entries written before still verify.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
SOURCE = HOOKS / "hmac_sha256.sh"
LOG = HOOKS / "posttooluse_log_tool.sh"
PRE = HOOKS / "pretooluse_require_checkpoint.sh"
TAKE = HOOKS / "posttooluse_take_checkpoint.sh"
ROLLBACK = ROOT / "skills" / "rollback" / "SKILL.md"
BEGIN = "# BEGIN hmac-sha256"
END = "# END hmac-sha256"

# A key as the take hook draws it: 32 bytes of /dev/urandom in hex, 64
# characters (od -An -tx1 | tr -d ' \n').
TAKE_KEY = "3f9c0a7d5e12b4c68e0f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

pytestmark = pytest.mark.skipif(
    shutil.which("openssl") is None or shutil.which("jq") is None,
    reason="the hooks need openssl and jq",
)


def _shells() -> list[str]:
    """sh, dash where there is one, and each bash on this machine (macOS
    /bin/bash 3.2, Homebrew's or Linux's bash 5), once each."""
    found: dict[str, str] = {}
    for candidate in (
        shutil.which("sh"),
        "/bin/dash",
        "/usr/bin/dash",
        "/bin/bash",
        "/opt/homebrew/bin/bash",
        "/usr/local/bin/bash",
        "/usr/bin/bash",
    ):
        if candidate and os.access(candidate, os.X_OK):
            found.setdefault(os.path.realpath(candidate), candidate)
    return list(found.values())


def _bashes() -> list[str]:
    return [s for s in _shells() if os.path.basename(os.path.realpath(s)) == "bash"]


def _block(text: str) -> str:
    assert text.count(BEGIN) == 1
    start = text.index(BEGIN)
    return text[start : text.index(END, start) + len(END)]


def _rollback_hook() -> str:
    text = ROLLBACK.read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---\n", 2)[1])
    commands = [
        hook["command"]
        for group in front["hooks"]["PreToolUse"]
        if group.get("matcher") == "Bash"
        for hook in group["hooks"]
        if hook["type"] == "command"
    ]
    assert len(commands) == 1
    command = commands[0]
    assert isinstance(command, str)
    return command


def _expected(key: bytes, commit: str) -> str:
    return hmac.new(
        key, f"acs-checkpoint-commit:{commit}".encode("ascii"), hashlib.sha256
    ).hexdigest()


@pytest.mark.parametrize(
    "copy",
    [LOG, PRE, TAKE, ROLLBACK],
    ids=["log", "pre-tool-use", "take", "rollback"],
)
def test_every_copy_is_the_source(copy: Path) -> None:
    """Each hook copies hooks/hmac_sha256.sh verbatim, from its BEGIN line
    to its END line, once."""
    source = SOURCE.read_text(encoding="utf-8").strip()
    assert source.startswith(BEGIN) and source.endswith(END)
    if copy == ROLLBACK:
        text = _rollback_hook()
    else:
        text = copy.read_text(encoding="utf-8")
    assert _block(text) == source


def _skill_commands() -> list[tuple[str, str]]:
    """Every command hook a skill declares, as (skill, command)."""
    found = []
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        front = yaml.safe_load(text.split("---\n", 2)[1]) or {}
        for groups in (front.get("hooks") or {}).values():
            for group in groups:
                for hook in group.get("hooks", []):
                    if hook.get("type") == "command":
                        found.append((path.parent.name, hook["command"]))
    return found


def test_no_hook_passes_a_key_to_openssl() -> None:
    """No hook script and no skill's command hook runs openssl with -hmac
    (the block's comment, which says why, aside)."""
    why = "# no command line: `openssl dgst -hmac KEY` would put the key in the process"
    texts = [(p.name, p.read_text(encoding="utf-8")) for p in HOOKS.glob("*.sh")]
    for name, text in [*texts, *_skill_commands()]:
        for line in text.splitlines():
            if "openssl" in line and "-hmac" in line:
                assert line.strip() == why, (name, line)


@pytest.mark.parametrize("shell", _shells())
@pytest.mark.parametrize(
    "key",
    [
        TAKE_KEY.encode("ascii"),  # what the take hook draws: 64 hex digits
        b"6" * 64,  # 0x36: a zero byte in every place of the inner pad
        b"\\" * 64,  # 0x5c: a zero byte in every place of the outer pad
        bytes(range(1, 65)),  # 64 bytes, control characters among them
        b"k" * 65,  # over 64 bytes: hashed first
        "ü".encode() * 33,  # 66 bytes, not ASCII
        b"k",
        b"%s%d\\n" * 20,  # printf directives and an escape
    ],
    ids=[
        "take-hook",
        "inner-zeros",
        "outer-zeros",
        "64",
        "65",
        "66-utf8",
        "1",
        "printf",
    ],
)
@pytest.mark.parametrize("commit", [COMMIT, "ab" * 32], ids=["sha1", "sha256"])
def test_the_hmac_matches_pythons(shell: str, key: bytes, commit: str) -> None:
    """The block's HMAC, for the checkpoint entry's message, is the one
    Python's hmac computes (and the one `openssl dgst -hmac` gave), under
    sh, dash and each bash."""
    block = SOURCE.read_text(encoding="utf-8")
    script = (
        f"{block}\n"
        'hmac_pads "$1" || exit 3\n'
        "printf 'acs-checkpoint-commit:%s' \"$2\" | hmac_hex\n"
    )
    done = subprocess.run(
        [shell, "-c", script, "hmac", key, commit],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode("ascii") == _expected(key, commit)


@pytest.mark.parametrize("shell", _shells())
def test_an_empty_key_and_no_openssl_give_no_value(shell: str, tmp_path: Path) -> None:
    """An empty key prepares no pads, and without openssl hmac_hex prints
    nothing and fails, so no caller takes an empty or partial value for a
    signature."""
    block = SOURCE.read_text(encoding="utf-8")
    done = subprocess.run(
        [
            shell,
            "-c",
            f'{block}\nhmac_pads "" && exit 4\nprintf x | hmac_hex && exit 5\nexit 0',
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("od", "awk", "tr", "cat"):
        found = shutil.which(tool)
        assert found is not None
        (bin_dir / tool).symlink_to(found)
    done = subprocess.run(
        [
            shell,
            "-c",
            f'{block}\nhmac_pads "$1" || exit 3\nprintf x | hmac_hex || exit 6',
            "x",
            TAKE_KEY,
        ],
        capture_output=True,
        timeout=60,
        check=False,
        env={**os.environ, "PATH": str(bin_dir)},
    )
    assert done.returncode == 6
    assert done.stdout == b""


# The hooks themselves: the take hook's entry, and the pre-tool-use and
# rollback hooks' check of an entry Python signed.


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    path = tmp_path / "project"
    path.mkdir()
    _git(path, "init", "-q")
    (path / "a.txt").write_text("a\n")
    _git(path, "add", "a.txt")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _records(repo: Path) -> Path:
    return repo / ".git" / "acs" / "checkpoints"


def _write_key(repo: Path, key: str = TAKE_KEY) -> None:
    records = _records(repo)
    (records / "commits").mkdir(parents=True, exist_ok=True)
    (records / "key").write_text(key, encoding="ascii")
    (records / "key").chmod(0o600)


def _enter(repo: Path, commit: str, key: str = TAKE_KEY) -> None:
    """An entry as the earlier take hook wrote it (openssl dgst -hmac), which
    is Python's HMAC."""
    _write_key(repo, key)
    (_records(repo) / "commits" / commit).write_text(
        _expected(key.encode("ascii"), commit), encoding="ascii"
    )


def _fake_openssl(tmp_path: Path) -> tuple[str, Path]:
    """A PATH whose first directory, outside the project, holds an
    ``openssl`` that appends its arguments to a file and runs the real one;
    the file."""
    real = shutil.which("openssl")
    assert real is not None
    fake_dir = tmp_path / "fakebin"
    fake_dir.mkdir()
    record = tmp_path / "openssl-args"
    record.write_text("", encoding="ascii")
    fake = fake_dir / "openssl"
    fake.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{record}'\nexec '{real}' \"$@\"\n",
        encoding="ascii",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return f"{fake_dir}:{os.environ.get('PATH', '')}", record


def _run_hook(
    shell: str,
    script: Path,
    payload: dict[str, Any],
    repo: Path,
    path: str | None = None,
    **env: str,
) -> subprocess.CompletedProcess[str]:
    full = {**os.environ, **GIT_ENV, "CLAUDE_PROJECT_DIR": str(repo), **env}
    if path is not None:
        full["PATH"] = path
    return subprocess.run(
        [shell, "-p", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full,
        timeout=60,
        cwd=repo,
    )


def _take(shell: str, repo: Path, path: str | None = None):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": 'git stash create "checkpoint:x"'},
        "tool_response": {"stdout": COMMIT + "\n"},
    }
    return _run_hook(shell, TAKE, payload, repo, path)


def _restore_call(commit: str) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": f"git stash apply {commit}"},
        "permission_mode": "default",
        "tool_use_id": "r1",
    }


def _pre(shell: str, repo: Path, path: str | None = None):
    return _run_hook(
        shell, PRE, _restore_call(COMMIT), repo, path, ACS_HOOK_APPROVAL="off"
    )


def _rollback(shell: str, repo: Path, path: str | None = None):
    env = {**os.environ, **GIT_ENV, "CLAUDE_PROJECT_DIR": ""}
    if path is not None:
        env["PATH"] = path
    payload = {**_restore_call(COMMIT), "cwd": str(repo)}
    return subprocess.run(
        [shell, "-c", _rollback_hook()],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
        timeout=60,
    )


@pytest.mark.parametrize("bash", _bashes())
def test_the_take_hook_signs_as_before(bash: str, repo: Path) -> None:
    """The entry the take hook writes is Python's HMAC under the key it
    drew (and under a key already there)."""
    result = _take(bash, repo)
    assert result.returncode == 0, result.stderr
    key = (_records(repo) / "key").read_text(encoding="ascii")
    assert len(key) == 64
    entry = (_records(repo) / "commits" / COMMIT).read_text(encoding="ascii")
    assert entry == _expected(key.encode("ascii"), COMMIT)
    assert key not in result.stdout + result.stderr
    (_records(repo) / "commits" / COMMIT).unlink()
    _write_key(repo)
    assert _take(bash, repo).returncode == 0
    entry = (_records(repo) / "commits" / COMMIT).read_text(encoding="ascii")
    assert entry == _expected(TAKE_KEY.encode("ascii"), COMMIT)


@pytest.mark.parametrize("bash", _bashes())
def test_the_pre_tool_use_hook_takes_an_entry_signed_before(
    bash: str, repo: Path
) -> None:
    """An entry signed as the earlier take hook signed it restores; one
    under another key does not."""
    _enter(repo, COMMIT)
    result = _pre(bash, repo)
    assert result.returncode == 0, result.stderr
    assert TAKE_KEY not in result.stdout + result.stderr
    (_records(repo) / "commits" / COMMIT).write_text(
        _expected(b"f" * 64, COMMIT), encoding="ascii"
    )
    result = _pre(bash, repo)
    assert result.returncode == 2
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: ")


@pytest.mark.parametrize("shell", _shells())
def test_the_rollback_hook_takes_an_entry_signed_before(shell: str, repo: Path) -> None:
    """The rollback skill's hook, under sh, dash and each bash, restores an
    entry signed as the earlier take hook signed it, and refuses one under
    another key."""
    _enter(repo, COMMIT)
    result = _rollback(shell, repo)
    assert result.returncode == 0, result.stderr
    assert TAKE_KEY not in result.stdout + result.stderr
    (_records(repo) / "commits" / COMMIT).write_text(
        _expected(b"f" * 64, COMMIT), encoding="ascii"
    )
    result = _rollback(shell, repo)
    assert result.returncode == 2
    assert result.stderr.startswith("F503 ROLLBACK_FAILED: ")


@pytest.mark.parametrize("bash", _bashes())
def test_the_checkpoint_key_is_on_no_command_line(
    bash: str, repo: Path, tmp_path: Path
) -> None:
    """The take hook signs, and the pre-tool-use and rollback hooks check,
    an entry without giving openssl the checkpoint key as an argument."""
    path, record = _fake_openssl(tmp_path)
    _write_key(repo)
    assert _take(bash, repo, path).returncode == 0
    assert (_records(repo) / "commits" / COMMIT).is_file()
    taken = record.read_text(encoding="ascii")
    assert _pre(bash, repo, path).returncode == 0
    checked = record.read_text(encoding="ascii")[len(taken) :]
    assert _rollback(bash, repo, path).returncode == 0
    rolled = record.read_text(encoding="ascii")[len(taken) + len(checked) :]
    for calls in (taken, checked, rolled):
        assert "dgst" in calls  # the fake openssl was the one run
    calls = record.read_text(encoding="ascii")
    assert TAKE_KEY not in calls and "-hmac" not in calls
