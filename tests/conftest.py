"""
Shared pytest fixtures for grounded_agency tests.

Provides reusable fixtures for ontology_path, adapter, and
related adapter variants.

``adapter``, ``strict_adapter`` and ``lenient_adapter`` set
``approval="off"``: the tests that use them are about the rate limit and the
checkpoint rule, and a call that passes those is then allowed outright. The
approval rule (the default, ``approval="ask"``) is tested with
``asking_adapter`` in ``tests/test_tool_call_approval.py``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# Ensure grounded_agency is importable from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

# =============================================================================
# Shared fixtures
# =============================================================================


@pytest.fixture(autouse=True, scope="session")
def _no_git_configuration_but_the_tests() -> Iterator[None]:
    """Every test, and every git, hook and adapter it runs, sees no system
    and no user git configuration (GIT_CONFIG_NOSYSTEM, and an empty
    GIT_CONFIG_GLOBAL), as on a machine where none is set: the classifiers
    read configuration in any scope (a smudge filter there, git-lfs's from
    `git lfs install`, gives a git change that writes the tree, and a
    restore, the worst case), so a test's classes would otherwise depend on
    the machine. A test that needs a user configuration sets its own
    (``GIT_CONFIG_GLOBAL``, or ``HOME`` with the variable removed)."""
    patch = pytest.MonkeyPatch()
    with tempfile.TemporaryDirectory(prefix="acs-git-config-") as where:
        empty = Path(where) / "config"
        empty.write_text("", encoding="utf-8")
        patch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        patch.setenv("GIT_CONFIG_GLOBAL", str(empty))
        patch.delenv("GIT_CONFIG_SYSTEM", raising=False)
        try:
            yield
        finally:
            patch.undo()


@pytest.fixture(autouse=True, scope="session")
def _a_home_with_no_audit_key() -> Iterator[None]:
    """Every test, and every hook and verifier it runs, sees HOME as an empty
    directory of its own, so no audit key file (``~/.config/acs/audit.key``,
    which the log hook and ``tools/verify_audit_log.py`` prefer to
    ``AUDIT_HMAC_KEY``) on the machine signs or verifies a test's log, and no
    test reads the person's key. A test that needs a key file makes one in a
    HOME of its own (``tests/test_audit_key_file.py``)."""
    patch = pytest.MonkeyPatch()
    with tempfile.TemporaryDirectory(prefix="acs-home-") as where:
        patch.setenv("HOME", where)
        try:
            yield
        finally:
            patch.undo()


# The directory of the plugin's hooks, and the repository's root.
REPO_ROOT = Path(__file__).resolve().parent.parent


def strict_sandbox_settings(
    *covered: str | os.PathLike[str], config_dir: str | os.PathLike[str]
) -> dict[str, Any]:
    """User settings holding the strict sandbox the pre-tool-use hook relaxes
    read-only Bash under (hooks/README.md, The strict sandbox), with
    ``Edit(//<dir>/**)`` and ``Read(//<dir>/**)`` deny rules for each
    directory in ``covered`` (as written and as resolved), which cover the
    records, settings files and hook scripts of every project and plugin
    copy under them, and for the user configuration directory
    ``config_dir``; with an Edit rule for ``~/.config/acs`` (the audit key and
    the remote-write record), a Read rule for the audit key file and Read rules for the
    user's credentials (~/.ssh, gh's hosts.yml, ~/.git-credentials, the
    keychains); and with envVars denials for the token variables."""
    dirs: list[str] = []
    for d in (*covered, config_dir):
        for form in (os.path.abspath(d), os.path.realpath(d)):
            if form not in dirs:
                dirs.append(form)
    home = os.path.expanduser("~")
    deny = [f"{tool}(/{d.rstrip('/')}/**)" for d in dirs for tool in ("Edit", "Read")]
    for h in dict.fromkeys((home, os.path.realpath(home))):
        k = os.path.join(h, ".config", "acs")
        deny += [f"Edit(/{k}/**)", f"Read(/{k}/audit.key)"]
        deny += [f"Read(/{h}/.ssh/**)", f"Read(/{h}/Library/Keychains/**)"]
        deny += [f"Read(/{h}/.config/gh/hosts.yml)", f"Read(/{h}/.git-credentials)"]
    deny.append("Read(//Library/Keychains/**)")
    return {
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "allowUnsandboxedCommands": False,
            "network": {"allowedDomains": ["example.com"], "strictAllowlist": True},
            "credentials": {
                "envVars": [
                    {"name": name, "mode": "deny"}
                    for name in ("AUDIT_HMAC_KEY", "GH_TOKEN", "GITHUB_TOKEN")
                ]
            },
        },
        "permissions": {"deny": deny},
    }


@pytest.fixture(autouse=True, scope="session")
def _strict_sandbox_for_the_hooks(_a_home_with_no_audit_key: None) -> Iterator[None]:
    """Every hook a test runs reads a user settings file (CLAUDE_CONFIG_DIR)
    with the strict sandbox, whose deny rules cover the temporary directory
    and this repository: the pre-tool-use hook relaxes a read-only Bash
    command only under it, and the tests of the classification assume it.
    tests/test_strict_sandbox.py tests the rule itself, with settings of its
    own. It runs after _a_home_with_no_audit_key, so the rules for the
    audit key name the HOME the hooks see."""
    import json

    patch = pytest.MonkeyPatch()
    with tempfile.TemporaryDirectory(prefix="acs-claude-config-") as where:
        settings = strict_sandbox_settings(
            tempfile.gettempdir(), REPO_ROOT, config_dir=where
        )
        Path(where, "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        patch.setenv("CLAUDE_CONFIG_DIR", where)
        try:
            yield
        finally:
            patch.undo()


@pytest.fixture
def bash_under_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every mapper, an adapter's included, classifies a Bash call as it
    does under a verified operating-system boundary: the Bash classifier
    relaxes a call only there (STANDARD 1.2.0 section 5.18.3, RFC-0011),
    and with no boundary every Bash call is its worst case. For tests of
    the classifier itself; ``tests/test_adapter_sandbox.py`` tests when the
    adapter verifies the boundary. A call that sets
    ``dangerouslyDisableSandbox``, or one in a permission mode outside
    ``CHECKED_PERMISSION_MODES``, is still the worst case."""
    from grounded_agency.capabilities.mapper import ToolCapabilityMapper
    from grounded_agency.utils.sandbox import CHECKED_PERMISSION_MODES

    monkeypatch.setattr(
        ToolCapabilityMapper,
        "boundary_holds",
        lambda self, tool_input, permission_mode=None: (
            tool_input.get("dangerouslyDisableSandbox", False) is False
            and (permission_mode is None or permission_mode in CHECKED_PERMISSION_MODES)
        ),
    )


@pytest.fixture
def ontology_path() -> str:
    """Path to the capability ontology YAML file."""
    return str(Path(__file__).parent.parent / "schemas/capability_ontology.yaml")


@pytest.fixture
def adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Pre-configured adapter with tmp checkpoint dir; asks for no approval."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            approval="off",
        )
    )


@pytest.fixture
def strict_adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Adapter with strict_mode=True; asks for no approval."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            strict_mode=True,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            approval="off",
        )
    )


@pytest.fixture
def lenient_adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Adapter with strict_mode=False; asks for no approval."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            strict_mode=False,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            approval="off",
        )
    )


@pytest.fixture
def asking_adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Adapter with the defaults: strict mode, and approval="ask"."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
        )
    )


class FakeClock:
    """A clock a test advances: pass it as ``clock=`` to a
    ``CheckpointTracker`` or a ``GroundedAgentAdapter``."""

    def __init__(self) -> None:
        from datetime import UTC, datetime

        self.now = datetime.now(UTC)

    def __call__(self) -> Any:
        return self.now

    def advance(self, **delta: float) -> None:
        from datetime import timedelta

        self.now += timedelta(**delta)


@pytest.fixture
def fake_clock() -> FakeClock:
    """A clock that stands still until the test advances it."""
    return FakeClock()


def _bash_major() -> int:
    """The major version of the bash on PATH, or 0 without one."""
    bash = shutil.which("bash")
    if bash is None:
        return 0
    out = subprocess.run(
        [bash, "-c", "echo ${BASH_VERSINFO[0]}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    ).stdout.strip()
    return int(out) if out.isdigit() else 0


BASH_4 = pytest.mark.skipif(
    _bash_major() < 4,
    reason=(
        "checks what the installed bash itself does, and bash before 4 (the "
        "/bin/bash 3.2 macOS ships) has no BASH_ALIASES, {var}> redirections "
        "or printf -v into an array element, and expands some braces as none "
        "of the hooks' readings do; the hooks read a command as bash 5 does, "
        "a gap where commands run in bash 3.2 or in zsh, macOS's login shell "
        "(spec/SECURITY.md 5.5)"
    ),
)
"""Skips a test of the installed bash's own behaviour where that bash is
older than 4."""


# The hooks' patterns run in time linear in their input with any grep, but
# BSD grep (macOS) runs them about ten times slower than GNU grep: a Write
# of 4 MB takes about 34 s there, past the hooks' 30 s limit, which blocks
# the call. So the bounds in seconds hold where grep is GNU grep, and
# elsewhere a timing test checks that the time grows linearly instead.
GNU_GREP = (
    "GNU grep"
    in subprocess.run(
        ["grep", "--version"], capture_output=True, text=True, check=False
    ).stdout
)


# The text vectors of tests/conformance/secrets/credentials.json on which
# the plugin's shell scan (hooks/secret_scan.sh and its copies) does not
# yet give the answer of the Python and TypeScript refusal rule: `sk-` read
# only where a token starts, and signed-URL signatures (#147, #148). The
# shell tests assert that the scan still gives the other answer on each, so
# the set must be emptied when the scan takes the same rule.
SHELL_SCAN_PENDING = frozenset(
    {
        "task_slug",
        "risk_slug",
        "sk_key_glued_after_a_letter",
        "s3_sigv4_signed_url",
        "gcs_signed_url",
        "azure_sas_url",
        "cloudfront_signed_url",
        "s3_sigv2_signed_url",
        "signed_url_percent_encoded",
        "signed_url_json_escaped",
        "signed_url_json_escaped_slash",
    }
)


def assert_linear(seconds_at: Any, small: Any, large: Any) -> None:
    """``seconds_at(large)`` is at most three times ``seconds_at(small)``,
    where ``large`` is twice ``small``: linear time doubles, a time that
    grows with the square of the input quadruples."""
    first = seconds_at(small)
    second = seconds_at(large)
    assert second < 3 * max(first, 0.5), (first, second)


DEEP_JSON = "[" * 100_000 + "]" * 100_000
"""JSON text nested deeper than Python's json C decoder reads on some
machines: whether ``json.loads`` raises RecursionError on it or returns the
nested lists depends on the C stack size, so on the machine and the
interpreter's build, not on the code under test."""


@pytest.fixture(params=["raises", "parses"])
def deep_json(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """:data:`DEEP_JSON`, with ``json.loads`` made to do with any text that
    holds it what one decoder or the other does: raise RecursionError
    (``raises``: as the decoder did where this code was written), or return
    what it parses to (``parses``: as the decoder of GitHub's ubuntu-latest
    runner did in November 2026), the nested lists stood in for by
    ``[[[]]]`` so that no test walks 100 000 levels of them. A test that
    takes the fixture runs both ways on every machine; other text is
    parsed by ``json.loads`` itself."""
    import json

    real = json.loads

    def loads(s: str | bytes | bytearray, *args: Any, **kw: Any) -> Any:
        text = s.decode("utf-8") if isinstance(s, bytes | bytearray) else s
        if DEEP_JSON not in text:
            return real(s, *args, **kw)
        if request.param == "raises":
            raise RecursionError(
                "maximum recursion depth exceeded while decoding a JSON array"
            )
        return real(text.replace(DEEP_JSON, "[[[]]]"), *args, **kw)

    monkeypatch.setattr(json, "loads", loads)
    return DEEP_JSON


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return done.stdout


@pytest.fixture
def partial_clone(tmp_path: Path) -> Path:
    """A partial clone (`git clone --filter=blob:none`) of a repository of
    two commits, served over file://: its remote is a promisor remote, and
    it lacks the blob of big.txt at HEAD~1 until a command reads it (git
    then fetches it from the remote, as it would from another host)."""
    if shutil.which("git") is None:
        pytest.skip("needs git")
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    for content in ("first", "second"):
        (source / "big.txt").write_text(content + "\n", encoding="utf-8")
        _git(source, "add", "big.txt")
        _git(source, "commit", "-q", "-m", content)
    _git(source, "config", "uploadpack.allowFilter", "true")
    _git(tmp_path, "clone", "-q", "--filter=blob:none", source.as_uri(), "clone")
    return tmp_path / "clone"


def missing_objects(repository: Path) -> int:
    """How many objects a partial clone lacks (git rev-list --missing)."""
    listed = _git(repository, "rev-list", "--objects", "--missing=print", "--all")
    return sum(line.startswith("?") for line in listed.splitlines())


def enter_checkpoint_commit(git_dir: Path, commit: str) -> Path:
    """Enter ``commit`` in ``git_dir`` as hooks/posttooluse_take_checkpoint.sh
    does: a file named by it in <git dir>/acs/checkpoints/commits/, holding
    the HMAC-SHA-256 of "acs-checkpoint-commit:<commit>" under the project's
    checkpoint key (<git dir>/acs/checkpoints/key, drawn here when there is
    none). Returns the entry's path."""
    import hashlib
    import hmac
    import secrets

    records = git_dir / "acs" / "checkpoints"
    (records / "commits").mkdir(parents=True, exist_ok=True)
    key_file = records / "key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="ascii")
    key = key_file.read_text(encoding="ascii")
    entry = records / "commits" / commit
    entry.write_text(
        hmac.new(
            key.encode("ascii"),
            f"acs-checkpoint-commit:{commit}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest(),
        encoding="ascii",
    )
    return entry


async def pre_tool_use(
    adapter: GroundedAgentAdapter,
    tool_name: str,
    tool_input: Any,
    call: str | None,
    **fields: Any,
) -> dict[str, Any]:
    """Run the adapter's PreToolUse safety hook on a call, as Claude Code
    does before it asks the permission callback about it: the callback
    decides only on a call the hook checked, with the input it checked
    (anything else is changed arguments, or R407 with no record).
    ``fields`` are further hook input members (``cwd``, ``session_id``,
    ``permission_mode``...). Returns the hook's output."""
    hook = adapter._make_pretooluse_safety_hook()
    payload = {"tool_name": tool_name, "tool_input": tool_input, **fields}
    result: dict[str, Any] = await hook(payload, call, None)
    return result
