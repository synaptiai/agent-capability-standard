"""A live session under the adapter's default sandbox (STANDARD 1.2.0
section 5.18.3, RFC-0011).

Opt-in: it starts the Claude Code CLI the Agent SDK bundles, which needs a
logged-in Claude Code or an API key, so it runs only with
``ACS_LIVE_SANDBOX=1``. ``ACS_LIVE_MODEL`` picks the model. Run it with
``pytest --noconftest``: the suite's conftest gives every test a scratch
``HOME`` and ``CLAUDE_CONFIG_DIR``, where Claude Code has no login. With
``-s`` it prints the version of the CLI the Agent SDK bundles and the
version each session reports.

Each probe is one query in a temporary git repository, with options
``GroundedAgentAdapter().wrap_options()`` built with its defaults, in the
``bypassPermissions`` permission mode, the one mode in which the adapter
relaxes Bash. A read-only command runs with no checkpoint; a
read of a credential file, a write to the home directory, a request to a
host off the allowlist and a write to the audit log are refused by the
sandbox. The probes that write take a checkpoint first, and the adapter
runs with ``approval="off"``, so that what refuses them is the sandbox,
not the adapter. The credential file is a canary the test writes and adds
with ``sandbox_deny_paths``: no real credential is read.
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ACS_LIVE_SANDBOX") != "1",
    reason="starts Claude Code with a real model: set ACS_LIVE_SANDBOX=1",
)


async def _run(
    adapter: Any, project: Path, command: str, *, checkpoint: bool = False
) -> list[tuple[str, bool]]:
    """Ask the model to run ``command`` with Bash (after ``git stash
    create`` in the same turn, with ``checkpoint``: a checkpoint taken
    before the query ends when its turn starts). Returns the text of each
    result of a Bash call of ``command`` and whether it was an error; the
    model may try a refused call again. The adapter must not be what
    refused any of them (no F or R code)."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        SystemMessage,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    options = adapter.wrap_options(
        ClaudeAgentOptions(
            cwd=str(project),
            setting_sources=[],
            permission_mode="bypassPermissions",
            max_turns=8,
            model=os.environ.get("ACS_LIVE_MODEL") or None,
        )
    )
    commands = ["git stash create", command] if checkpoint else [command]
    prompt = (
        "Run exactly these shell commands, in this order, each once and in "
        "its own Bash tool call, with no change and no other tool, then "
        "reply DONE:\n\n" + "\n".join(commands)
    )
    calls: dict[str, str] = {}
    results: list[tuple[str, str, bool]] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            # Shown with -s: the version the CLI that ran reports.
            print(f"claude_code_version {message.data.get('claude_code_version')}")
        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock) and block.name == "Bash":
                    calls[block.id] = str(block.input.get("command"))
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    content = block.content
                    text = (
                        content
                        if isinstance(content, str)
                        else " ".join(
                            str(item.get("text", ""))
                            for item in content or []
                            if isinstance(item, dict)
                        )
                    )
                    command_run = calls.get(block.tool_use_id, "")
                    results.append((command_run, text, bool(block.is_error)))
    # Shown with -s: what refused each probe.
    print(f"{commands!r} -> {results!r}")
    if checkpoint:
        assert any(c == commands[0] and not e for c, _, e in results), results
    found = [(t, e) for c, t, e in results if c == command]
    assert found, results
    for text, _ in found:
        assert not re.search(r"\b[FR]\d{3}\b", text), text
    return found


@pytest.fixture
def project(tmp_path: Path) -> Path:
    where = tmp_path / "project"
    where.mkdir()
    for args in (
        ["init", "-q"],
        [
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "start",
        ],
    ):
        subprocess.run(["git", *args], cwd=where, check=True, capture_output=True)
    (where / "a.txt").write_text("a\n")
    return where


async def test_the_default_sandbox_in_a_live_session(
    tmp_path: Path, project: Path
) -> None:
    from claude_agent_sdk._cli_version import __cli_version__

    from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

    # Shown with -s: the version of the CLI the Agent SDK bundles.
    print(f"Claude Code {__cli_version__}, bundled with the Agent SDK")
    canary = tmp_path / "data" / "notes.txt"
    canary.parent.mkdir()
    secret = f"canary-{uuid.uuid4().hex}"
    canary.write_text(secret)
    records = tmp_path / "records"
    audit = records / "audit.log"
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            checkpoint_dir=str(records / "checkpoints"),
            audit_log_path=str(audit),
            sandbox_deny_paths=[str(canary)],
            approval="off",
        )
    )

    # A read-only command runs, with no checkpoint taken.
    found = await _run(adapter, project, "ls")
    assert any(not error and "a.txt" in text for text, error in found)

    # A credential file stays unreadable.
    found = await _run(adapter, project, f"cat {canary}")
    assert all(secret not in text for text, _ in found)

    home_file = Path.home() / f"acs-canary-{uuid.uuid4().hex}"
    try:
        await _run(adapter, project, f"touch {home_file}", checkpoint=True)
        assert not home_file.exists()
    finally:
        home_file.unlink(missing_ok=True)

    found = await _run(
        adapter, project, "curl -sS -m 10 https://example.com", checkpoint=True
    )
    assert all("Example Domain" not in text for text, _ in found)

    marker = f"acs-{uuid.uuid4().hex}"
    await _run(adapter, project, f"echo {marker} >> {audit}", checkpoint=True)
    assert not audit.exists() or marker not in audit.read_text()

    # The same read and write with the path out of the command's text, so
    # that the CLI's check of the command against the deny rules cannot
    # see it and the sandbox decides.
    hidden = f'd="$(printf %s {canary.parent})"; cat "$d/notes.txt"'
    found = await _run(adapter, project, hidden, checkpoint=True)
    assert all(secret not in text for text, _ in found)
    hidden = f'd="$(printf %s {records})"; echo {marker}-2 >> "$d/audit.log"'
    await _run(adapter, project, hidden, checkpoint=True)
    assert not audit.exists() or f"{marker}-2" not in audit.read_text()

    # A write in the working directory, under the same checkpoint rule,
    # runs: the refusals above are the sandbox's.
    await _run(adapter, project, "touch b.txt", checkpoint=True)
    assert (project / "b.txt").exists()
