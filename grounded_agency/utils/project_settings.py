"""What a project's own settings files put in the environment of the
commands Claude Code runs.

Claude Code applies the ``env`` of a project's ``.claude/settings.json``
(the ``project`` setting source) and ``.claude/settings.local.json``
(``local``), which are repository content, to its own process, and so to
every Bash command, hook and MCP server it starts, over the host's
environment and ``options.env``. A variable there changes what a command
the layer classifies does: ``BASH_ENV`` runs a repository's script before
every bash command (``ls`` included), ``SHELLOPTS`` and ``BASHOPTS`` change
how bash runs it, ``GIT_CONFIG_COUNT`` with ``GIT_CONFIG_KEY_0`` and
``GIT_CONFIG_VALUE_0`` (git's command scope, as are
``GIT_CONFIG_PARAMETERS``, ``GIT_CONFIG_GLOBAL``, ``HOME`` and
``XDG_CONFIG_HOME``) make `git status` run a program the repository ships,
``PATH`` puts a repository's program in place of a listed one,
``LD_PRELOAD`` loads one into every program, and a proxy variable sends a
request to another host. The layer cannot tell what such a command does,
so while either file the CLI loads sets a variable in ``env`` that is not
on :data:`ALLOWED_PROJECT_ENV`, or cannot be read, the adapter refuses
every call (R407, STANDARD 1.2.0 sections 5.18.3, 5.18.8).

:data:`ALLOWED_PROJECT_ENV` holds only Claude Code's own settings that no
program the plugin's hooks run, and no command the layer lets pass, reads.
The plugin's hooks hold the same list (``project_layer_settings`` in
``hooks/pretooluse_require_checkpoint.sh``); a test keeps the two equal.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence

__all__ = ["ALLOWED_PROJECT_ENV", "PROJECT_SETTINGS_FILES", "refused_project_env"]

# The variables a project's settings may set in ``env``, as a full match:
# Claude Code's own settings (its API client's, telemetry's, timeouts and
# output limits). Names are matched as written: a name in another letter
# case is another variable on most systems and the same one on Windows, so
# it is refused.
ALLOWED_PROJECT_ENV = re.compile(
    r"ANTHROPIC_[A-Z0-9_]+|OTEL_[A-Z0-9_]+"
    r"|CLAUDE_CODE_(?:ENABLE_TELEMETRY|MAX_OUTPUT_TOKENS|USE_BEDROCK|USE_VERTEX"
    r"|DISABLE_NONESSENTIAL_TRAFFIC)"
    r"|DISABLE_(?:TELEMETRY|ERROR_REPORTING|AUTOUPDATER)"
    r"|MAX_THINKING_TOKENS|MAX_MCP_OUTPUT_TOKENS|MCP_TIMEOUT|MCP_TOOL_TIMEOUT"
    r"|BASH_DEFAULT_TIMEOUT_MS|BASH_MAX_TIMEOUT_MS|BASH_MAX_OUTPUT_LENGTH"
)

# Each setting source the CLI loads from the project directory, and its file
# there.
PROJECT_SETTINGS_FILES: tuple[tuple[str, str], ...] = (
    ("project", "settings.json"),
    ("local", "settings.local.json"),
)


def refused_project_env(
    project_dir: str | os.PathLike[str], setting_sources: Sequence[str] | None
) -> list[str]:
    """The variables the project's settings files set in ``env`` that are
    not on :data:`ALLOWED_PROJECT_ENV`, in the order the files give them,
    and ``.claude/<file> (unreadable)`` for a file that is there (a link
    included) but cannot be read as JSON.

    ``setting_sources`` is the one the CLI is given: ``None`` loads every
    source (the CLI's default), a list only those it names, so a host that
    passes ``[]`` or ``["user"]`` loads neither file and nothing is
    refused. An ``env`` that is not an object, or a file that is not one,
    sets nothing (as the plugin's hooks read it)."""
    found: list[str] = []
    for source, name in PROJECT_SETTINGS_FILES:
        if setting_sources is not None and source not in setting_sources:
            continue
        path = os.path.join(os.fspath(project_dir), ".claude", name)
        if not os.path.lexists(path):
            continue
        try:
            with open(path, "rb") as handle:
                # UTF-8 only, as jq reads it.
                document = json.loads(handle.read().decode("utf-8"))
        except OSError, ValueError, RecursionError:
            found.append(f".claude/{name} (unreadable)")
            continue
        env = document.get("env") if isinstance(document, dict) else None
        if isinstance(env, dict):
            found.extend(
                key for key in env if not ALLOWED_PROJECT_ENV.fullmatch(str(key))
            )
    return found
