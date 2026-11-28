"""The operating-system boundary the adapter runs Bash under (STANDARD 1.2.0
section 5.18.3, RFC-0011).

Claude Code confines a Bash command with its sandbox (Seatbelt on macOS,
bubblewrap on Linux) when its settings turn the sandbox on. The adapter
passes those settings itself (``ClaudeAgentOptions.sandbox`` and
``settings``, the CLI's ``--settings`` scope), so it can turn on a strict
sandbox (:func:`strict_sandbox`) and deny rules for the layer's records
(:func:`deny_rules`), and check, before each Bash call, that the sandbox in
force has each property of the boundary (:func:`boundary_faults`). The
rules and ``denyWrite`` paths for the plugin hooks' records (the project's
``.claude/`` records and ``acs/`` in each git directory of the repository)
come from :mod:`grounded_agency.layer_records`, which the adapter calls and
passes in (:func:`boundary_paths`, ``record_rules`` and
``record_deny_write``).

The Agent SDK's ``SandboxSettings`` type lists ``enabled``,
``autoAllowBashIfSandboxed``, ``excludedCommands``,
``allowUnsandboxedCommands``, ``network`` (``allowedDomains``,
``allowUnixSockets``, ``allowAllUnixSockets``, ``allowLocalBinding``,
``allowMachLookup`` and the proxy ports), ``ignoreViolations`` and
``enableWeakerNestedSandbox``. It does not list ``failIfUnavailable``,
``network.strictAllowlist``, ``filesystem`` or ``credentials``. The SDK
passes the sandbox object to the CLI as it is given, inside the
``--settings`` JSON, so the adapter sets those keys too; the CLI's own
settings schema defines each of them.

What the CLI applies to a call comes from every settings source it reads:
managed settings, the ``--settings`` value, and the user's, the project's
and the local settings files that ``setting_sources`` names. A value in a
lower source can still widen what the ``--settings`` value sets where the
CLI merges lists (excluded commands, allowed domains, sockets, readable and
writable paths), and managed settings outrank it. :func:`source_faults`
reads each of those files and reports any sandbox value in them that could
weaken the boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..sandbox_settings import _refused_entry
from .git import SAFE_GIT_OPTIONS, safe_git_environment
from .project_settings import PROJECT_SETTINGS_FILES, _read_regular_file

__all__ = [
    "CHECKED_CLI_VERSIONS",
    "CHECKED_PERMISSION_MODES",
    "CREDENTIAL_ENV_VARS",
    "BoundaryPaths",
    "boundary_faults",
    "boundary_paths",
    "cli_faults",
    "config_dir",
    "credential_env",
    "deny_rules",
    "directory_faults",
    "env_faults",
    "environment",
    "flag_settings",
    "git_dirs",
    "git_toplevel",
    "linked_files",
    "managed_settings_files",
    "mode_faults",
    "mcp_server_lists",
    "parse_settings",
    "pattern_faults",
    "server_files",
    "source_faults",
    "source_state",
    "unread_policy_sources",
    "widening_rules",
    "strict_sandbox",
]

# The environment variables that carry a credential a sandboxed command
# must not see, whether or not they are set: the user's GitHub tokens, the
# plugin's audit key, Claude Code's own API key and login token, and the
# SSH and GPG agents' addresses. The sandbox unsets each one for the
# commands it runs (``credentials.envVars``, mode ``deny``), along with every
# variable of the CLI's environment whose name looks like a credential's
# (:func:`credential_env`).
CREDENTIAL_ENV_VARS: tuple[str, ...] = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "AUDIT_HMAC_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "SSH_AUTH_SOCK",
    "GPG_AGENT_INFO",
)

# A variable name that looks like a credential's.
CREDENTIAL_NAME = re.compile(
    r"(?i)(TOKEN|SECRET|PASSW(OR)?D|CREDENTIAL|API_?KEY|ACCESS_?KEY|"
    r"PRIVATE_?KEY|SESSION_?KEY|AUTH)"
)

# Files and directories under a home directory that hold credentials: the
# macOS keychains, SSH and GPG keys, git's and curl's stored passwords, the
# cloud and container tools' credentials, the package registries' tokens,
# and the Linux keyrings.
_HOME_CREDENTIALS: tuple[str, ...] = (
    "Library/Keychains",
    ".ssh",
    ".gnupg",
    ".git-credentials",
    ".netrc",
    ".aws",
    ".azure",
    ".config/gcloud",
    ".kube",
    ".docker/config.json",
    ".npmrc",
    ".pypirc",
    ".cargo/credentials",
    ".cargo/credentials.toml",
    ".local/share/keyrings",
    ".password-store",
)

# Characters a permission rule or the sandbox reads as a pattern or as the
# rule's own syntax: a path holding one is not read literally.
_PATTERN = re.compile(r"[*?\[\]{}()\\]")

# Allowlist entries refused besides those the setup command's host grammar
# refuses: any metadata.* name (a cloud metadata service), and any entry
# with a colon (a port, or an IPv6 literal), checked after a trailing dot is
# dropped and in lower case.
_LOCAL_HOST = re.compile(
    r"^(\*|localhost|.*\.localhost|.*\.local|metadata(\..*)?|"
    r"\[.*\]|[0-9.]+|.*:.*)$"
)


@dataclass(frozen=True)
class BoundaryPaths:
    """The absolute paths the boundary keeps from a sandboxed command.

    Attributes:
        records: The adapter's own records: neither writable nor readable
            from the sandbox or the file tools (``Edit`` and ``Read`` deny
            rules).
        protected: What code outside the sandbox runs or reads as
            configuration: the project's ``.claude/`` and ``.mcp.json``,
            the repository's git configuration and hooks and a linked
            worktree's ``.git`` file, the user's Claude Code settings,
            hooks, plugins, agents, commands and skills and its
            ``.claude.json``, and the code that runs outside the sandbox
            (the layer's and the Agent SDK's packages, the interpreter and
            its packages, the CLI, local plugins, and the files a stdio MCP
            server runs): not writable (``Edit`` deny rules).
        credential_files: Files and directories holding credentials: not
            readable from the sandbox (``credentials.files`` and
            ``filesystem.denyRead``) nor with the Read tool.
        credential_env: The variables the sandbox unsets
            (:func:`credential_env`).
        link_checked: The protected files and directories checked for a
            second hard link before each Bash call, with the records and
            the credential files (:func:`linked_files`): the settings files,
            hooks, MCP server lists and git configuration, and the files a
            stdio MCP server or the CLI runs. Package and plugin trees are
            not walked.
        link_skipped: Directories under the records that are not walked
            for hard links: a snapshot store's content objects, which the
            layer writes and checks by their digest.
        record_rules: The ``permissions.deny`` rules for the plugin hooks'
            records, as :func:`grounded_agency.layer_records.deny_settings`
            gives them: ``Edit`` of the project's records and of ``acs/`` in
            each git directory of the repository (the project's, the common
            one, each linked worktree's and each submodule's, and a
            submodule checkout's superprojects'), ``Read`` of
            the ``acs/`` directories.
        record_deny_write: The ``sandbox.filesystem.denyWrite`` paths for
            those records, from the same function. They are walked for hard
            links too.
    """

    records: tuple[str, ...]
    protected: tuple[str, ...]
    credential_files: tuple[str, ...]
    credential_env: tuple[str, ...] = CREDENTIAL_ENV_VARS
    link_checked: tuple[str, ...] = ()
    link_skipped: tuple[str, ...] = ()
    record_rules: tuple[str, ...] = ()
    record_deny_write: tuple[str, ...] = ()


def environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment the CLI runs with: this process's, with the options'
    ``env`` over it, as the Agent SDK builds it. An empty value counts as
    unset."""
    merged = {**os.environ, **{str(k): str(v) for k, v in (env or {}).items()}}
    return {k: v for k, v in merged.items() if v != ""}


def _home(merged: Mapping[str, str]) -> str:
    home = merged.get("HOME") or os.path.expanduser("~")
    return os.path.realpath(home)


def _expand(path: str, home: str) -> str:
    """``path`` with a leading ``~`` read as ``home``."""
    if path == "~":
        return home
    if path.startswith("~/"):
        return os.path.join(home, path[2:])
    return path


def _absolute(path: str | os.PathLike[str], base: str, home: str) -> str:
    """``path`` made absolute against ``base`` with every link resolved
    that exists: a deny rule names the file the CLI opens."""
    return os.path.realpath(os.path.join(base, _expand(os.fspath(path), home)))


def _both(path: str) -> list[str]:
    """``path`` and, where it differs, the path it resolves to: a deny of
    a link alone may leave its target open, and the other way round."""
    return list(dict.fromkeys([path, os.path.realpath(path)]))


def _unique(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(paths))


def config_dir(env: Mapping[str, str] | None = None) -> str:
    """Claude Code's configuration directory as the CLI finds it:
    ``CLAUDE_CONFIG_DIR`` of its environment (:func:`environment`), else
    ``.claude`` in its home directory."""
    merged = environment(env)
    home = _home(merged)
    value = merged.get("CLAUDE_CONFIG_DIR")
    if value:
        return os.path.realpath(_expand(value, home))
    return os.path.join(home, ".claude")


def _main_config(env: Mapping[str, str] | None) -> str:
    """Claude Code's state file, which holds the user's MCP servers:
    ``.claude.json`` in ``CLAUDE_CONFIG_DIR`` when that is set, else in the
    home directory."""
    merged = environment(env)
    if merged.get("CLAUDE_CONFIG_DIR"):
        return os.path.join(config_dir(env), ".claude.json")
    return os.path.join(_home(merged), ".claude.json")


def credential_env(
    env: Mapping[str, str] | None = None, extra: Iterable[str] = ()
) -> tuple[str, ...]:
    """The variables the sandbox unsets: :data:`CREDENTIAL_ENV_VARS`,
    every variable of the CLI's environment (:func:`environment`) whose
    name looks like a credential's (:data:`CREDENTIAL_NAME`), and
    ``extra``."""
    found = sorted(n for n in environment(env) if CREDENTIAL_NAME.search(n))
    return _unique([*CREDENTIAL_ENV_VARS, *found, *extra])


def boundary_paths(
    project_dir: str,
    git_dirs: Sequence[str],
    records: Sequence[str | os.PathLike[str]],
    env: Mapping[str, str] | None = None,
    *,
    toplevel: str | None = None,
    code: Sequence[str] = (),
    code_files: Sequence[str] = (),
    credential_files: Sequence[str] = (),
    credential_vars: Sequence[str] = (),
    link_skipped: Sequence[str] = (),
    record_rules: Sequence[str] = (),
    record_deny_write: Sequence[str] = (),
) -> BoundaryPaths:
    """The paths the boundary protects for a session in ``project_dir``.

    Args:
        project_dir: The CLI's working directory (the options' ``cwd``).
        git_dirs: The repository's git directory and common git directory,
            absolute, as git reports them (they differ in a linked
            worktree); empty outside a repository. Their configuration and
            hooks are protected; their records come in ``record_rules``.
        records: The adapter's own records (its checkpoint directory, audit
            log, snapshot store, evidence file), each relative to this
            process's working directory or absolute.
        env: The options' ``env``: with this process's environment, the
            CLI's (:func:`environment`), which gives the home directory,
            ``CLAUDE_CONFIG_DIR``, ``GH_CONFIG_DIR`` and ``XDG_CONFIG_HOME``.
        toplevel: The repository's top directory, whose ``.git`` is a file
            in a linked worktree.
        code: Directories and files of code that runs outside the sandbox,
            absolute: not writable.
        code_files: Files among them checked for a second hard link.
        credential_files: More credential files, each relative to the home
            directory or absolute.
        credential_vars: More variables to unset.
        link_skipped: Directories under the records not walked for hard
            links.
        record_rules: The deny rules for the plugin hooks' records
            (:attr:`BoundaryPaths.record_rules`).
        record_deny_write: Their ``denyWrite`` paths
            (:attr:`BoundaryPaths.record_deny_write`).
    """
    here = os.getcwd()
    project = os.path.realpath(project_dir)
    merged = environment(env)
    home = _home(merged)
    # The credentials of this process's home directory too, where the
    # options' env gives the CLI another one.
    homes = _unique([home, _home(environment())])
    xdg = os.path.realpath(
        _expand(merged.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), home)
    )
    gh = os.path.realpath(
        _expand(merged.get("GH_CONFIG_DIR") or os.path.join(xdg, "gh"), home)
    )
    git_config: list[str] = []
    for git_dir in git_dirs:
        real = os.path.realpath(git_dir)
        # What the layer's own git commands, run outside the sandbox, read
        # as configuration and run.
        git_config.extend(
            os.path.join(real, name) for name in ("config", "config.worktree", "hooks")
        )
    if toplevel:
        # A linked worktree's `.git` file names the git directory every git
        # command run there reads.
        dot_git = os.path.join(os.path.realpath(toplevel), ".git")
        if os.path.isfile(dot_git):
            git_config.append(dot_git)
    claude = config_dir(env)
    settings = [
        os.path.join(project, ".claude", "settings.json"),
        os.path.join(project, ".claude", "settings.local.json"),
        os.path.join(project, ".claude", "hooks"),
        os.path.join(project, ".mcp.json"),
        *git_config,
        os.path.join(claude, "settings.json"),
        os.path.join(claude, "settings.local.json"),
        os.path.join(claude, "hooks"),
        _main_config(env),
    ]
    protected = [
        os.path.join(project, ".claude"),
        os.path.join(project, ".mcp.json"),
        *git_config,
        *(
            os.path.join(claude, name)
            for name in (
                "settings.json",
                "settings.local.json",
                "hooks",
                "plugins",
                "agents",
                "commands",
                "skills",
            )
        ),
        _main_config(env),
        *code,
    ]
    credentials = [
        *(os.path.join(h, name) for h in homes for name in _HOME_CREDENTIALS),
        "/Library/Keychains",
        gh,
        os.path.join(xdg, "git", "credentials"),
        os.path.join(xdg, "acs", "audit.key"),
        *(
            os.path.join(h, ".config", sub)
            for h in homes
            for sub in ("gh", "git/credentials", "acs/audit.key")
        ),
        os.path.join(claude, ".credentials.json"),
        *(_absolute(p, home, home) for p in credential_files),
    ]
    return BoundaryPaths(
        records=_unique(_absolute(r, here, home) for r in records),
        protected=_unique(p for path in protected for p in _both(path)),
        credential_files=_unique(p for path in credentials for p in _both(path)),
        credential_env=credential_env(env, credential_vars),
        link_checked=_unique(
            p for path in (*settings, *code_files) for p in _both(path)
        ),
        link_skipped=_unique(os.path.realpath(p) for p in link_skipped),
        record_rules=_unique(record_rules),
        record_deny_write=_unique(record_deny_write),
    )


def git_dirs(project_dir: str) -> list[str]:
    """The git directory and the common git directory of the repository at
    ``project_dir``, absolute and real (one entry when they are the same),
    as git reports them, run as the layer runs it on its own behalf. Empty
    outside a repository or without git."""
    found: list[str] = []
    for option in ("--absolute-git-dir", "--git-common-dir"):
        out = _rev_parse(project_dir, option)
        if out is None:
            return []
        found.append(os.path.realpath(os.path.join(project_dir, out)))
    return list(dict.fromkeys(found))


def git_toplevel(project_dir: str) -> str | None:
    """The top directory of the repository at ``project_dir``, as git
    reports it; None outside a repository or without git."""
    out = _rev_parse(project_dir, "--show-toplevel")
    return os.path.realpath(out) if out else None


def _rev_parse(project_dir: str, option: str) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        done = subprocess.run(
            [git, *SAFE_GIT_OPTIONS, "-C", project_dir, "rev-parse", option],
            capture_output=True,
            timeout=10,
            check=False,
            env=safe_git_environment(),
        )
    except OSError, ValueError, subprocess.SubprocessError:
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", "surrogateescape").strip() or None


def server_files(
    servers: Any, project_dir: str, env: Mapping[str, str] | None = None
) -> tuple[list[str], list[str]]:
    """The files the stdio MCP servers of ``servers`` (a name-to-config
    mapping) run, which run outside the sandbox: each server's command,
    resolved as the CLI's ``PATH`` resolves it from ``project_dir`` (and,
    for each ``PATH`` directory inside the project, the command's path
    there whether or not it exists), and every argument that names an
    existing file. Returns the files and the faults: a server list or entry
    that cannot be read."""
    files: list[str] = []
    faults: list[str] = []
    if not isinstance(servers, Mapping):
        return files, ["an MCP server list is not an object"]
    merged = environment(env)
    home = _home(merged)
    project = os.path.realpath(project_dir)
    for name, server in servers.items():
        if not isinstance(server, Mapping):
            faults.append(f"MCP server {name!s} is not an object")
            continue
        if server.get("type", "stdio") != "stdio":
            continue
        command = server.get("command")
        args = server.get("args", [])
        if not isinstance(command, str) or not isinstance(args, list):
            faults.append(f"MCP server {name!s} has no readable command")
            continue
        if "/" in command:
            files.append(_absolute(command, project, home))
        else:
            for directory in merged.get("PATH", "").split(os.pathsep):
                where = _absolute(directory or ".", project, home)
                candidate = os.path.join(where, command)
                if where == project or where.startswith(project + os.sep):
                    files.append(candidate)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    files.append(os.path.realpath(candidate))
                    break
        for arg in args:
            if isinstance(arg, str) and arg:
                candidate = _absolute(arg, project, home)
                if os.path.isfile(candidate):
                    files.append(candidate)
    return list(dict.fromkeys(files)), faults


def mcp_server_lists(
    project_dir: str, env: Mapping[str, str] | None = None
) -> list[tuple[str, Any]]:
    """The MCP server lists the CLI loads from files besides the options:
    the project's ``.mcp.json`` and, in the user's ``.claude.json``, the
    user's servers and the project's entry. Each is named by where it is;
    a file that is there but cannot be read gives ``None`` in place of its
    list (:func:`server_files` reports it)."""
    project = os.path.realpath(project_dir)
    found: list[tuple[str, Any]] = []
    for path, keys in (
        (os.path.join(project, ".mcp.json"), [("mcpServers",)]),
        (
            _main_config(env),
            [("mcpServers",), ("projects", project, "mcpServers")]
            + (
                [("projects", project_dir, "mcpServers")]
                if project_dir != project
                else []
            ),
        ),
    ):
        if not os.path.lexists(path):
            continue
        try:
            document = json.loads(_read_regular_file(path).decode("utf-8"))
        except OSError, ValueError, RecursionError:
            found.append((path, None))
            continue
        for key in keys:
            present, servers = _get(document, *key)
            if present:
                found.append((f"{path} ({'.'.join(key)})", servers))
    return found


def _rule(tool: str, path: str) -> str:
    """A permission rule for an absolute path: ``//`` starts one."""
    return f"{tool}(/{path})" if path.startswith("/") else f"{tool}({path})"


def deny_rules(paths: BoundaryPaths) -> list[str]:
    """The ``permissions.deny`` rules for ``paths``: ``Edit`` and ``Read``
    of each of the adapter's records, the rules for the plugin hooks'
    records (:attr:`BoundaryPaths.record_rules`, as given), ``Edit`` of each
    protected path, ``Read`` of each credential file. Literal absolute
    paths; the only glob is the ``/**`` of a directory among the hooks'
    records. The CLI applies an ``Edit`` deny rule to sandboxed commands as
    well as to the file tools, and a ``Read`` one to both."""
    return list(
        dict.fromkeys(
            [
                *(_rule("Edit", p) for p in paths.records),
                *(_rule("Read", p) for p in paths.records),
                *paths.record_rules,
                *(_rule("Edit", p) for p in paths.protected),
                *(_rule("Read", p) for p in paths.credential_files),
            ]
        )
    )


def strict_sandbox(
    paths: BoundaryPaths, allowed_domains: Sequence[str] = ()
) -> dict[str, Any]:
    """The sandbox settings of the boundary: on, refusing to run a command
    when the sandbox cannot start, with no route outside it, a network
    limited to ``allowed_domains`` (none by default) that refuses any other
    host, the credentials of ``paths`` out of reach, and the plugin hooks'
    records of ``paths`` not writable (``filesystem.denyWrite``)."""
    return {
        "enabled": True,
        "failIfUnavailable": True,
        # A sandboxed command still goes through this layer's checks and
        # the host's permission flow: the CLI's auto-approval is off.
        "autoAllowBashIfSandboxed": False,
        "allowUnsandboxedCommands": False,
        "excludedCommands": [],
        "enableWeakerNestedSandbox": False,
        "enableWeakerNetworkIsolation": False,
        "allowNestedUserNamespaces": False,
        "allowAppleEvents": False,
        "network": {
            "allowedDomains": list(allowed_domains),
            "strictAllowlist": True,
            "allowUnixSockets": [],
            "allowAllUnixSockets": False,
            "allowLocalBinding": False,
            "allowMachLookup": [],
        },
        "filesystem": {
            "disabled": False,
            "denyRead": list(paths.credential_files),
            "denyWrite": list(paths.record_deny_write),
        },
        "credentials": {
            "files": [{"path": p, "mode": "deny"} for p in paths.credential_files],
            "envVars": [{"name": n, "mode": "deny"} for n in paths.credential_env],
        },
    }


def parse_settings(settings: str | None) -> dict[str, Any] | None:
    """The object an options' ``settings`` value holds, read as the Agent
    SDK reads it before it merges the sandbox in: inline JSON (text that
    starts with ``{`` and ends with ``}``), else the path of a JSON file.
    ``{}`` for None; None when it cannot be read as a JSON object."""
    if settings is None:
        return {}
    if not isinstance(settings, str):
        return None
    text = settings.strip()
    try:
        if text.startswith("{") and text.endswith("}"):
            document = json.loads(text)
        else:
            document = json.loads(_read_regular_file(text).decode("utf-8"))
    except OSError, ValueError, RecursionError:
        return None
    return document if isinstance(document, dict) else None


def flag_settings(options: Any) -> dict[str, Any] | None:
    """The settings ``options`` pass to the CLI's ``--settings``, as the
    Agent SDK builds them: the ``settings`` object with ``options.sandbox``,
    when set, in place of its ``sandbox`` member. None when the
    ``settings`` value cannot be read."""
    document = parse_settings(getattr(options, "settings", None))
    if document is None:
        return None
    sandbox = getattr(options, "sandbox", None)
    if sandbox is not None:
        document = {**document, "sandbox": sandbox}
    return document


def _get(document: Any, *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if not isinstance(document, dict) or key not in document:
            return False, None
        document = document[key]
    return True, document


# Each sandbox value that weakens the boundary wherever it is set: the key's
# path in the sandbox object, whether a value set there weakens it, and
# whether the ``--settings`` object must set it (the CLI's default for it
# weakens the boundary). A value absent from a lower source weakens nothing.
_WEAKENING: tuple[tuple[tuple[str, ...], Callable[[Any], bool], bool], ...] = (
    (("enabled",), lambda v: v is not True, True),
    (("failIfUnavailable",), lambda v: v is not True, True),
    # The CLI approves a sandboxed command by itself unless this is false.
    (("autoAllowBashIfSandboxed",), lambda v: v is not False, True),
    (("allowUnsandboxedCommands",), lambda v: v is not False, True),
    (("excludedCommands",), lambda v: v != [], False),
    (("enableWeakerNestedSandbox",), lambda v: v is not False, False),
    (("enableWeakerNetworkIsolation",), lambda v: v is not False, False),
    (("allowNestedUserNamespaces",), lambda v: v is not False, False),
    (("allowAppleEvents",), lambda v: v is not False, False),
    (("network", "strictAllowlist"), lambda v: v is not True, True),
    (("network", "allowUnixSockets"), lambda v: v != [], False),
    (("network", "allowAllUnixSockets"), lambda v: v is not False, False),
    (("network", "allowLocalBinding"), lambda v: v is not False, False),
    (("network", "allowMachLookup"), lambda v: v != [], False),
    (("network", "httpProxyPort"), lambda v: True, False),
    (("network", "socksProxyPort"), lambda v: True, False),
    (("filesystem", "disabled"), lambda v: v is not False, False),
    (("filesystem", "allowRead"), lambda v: v != [], False),
    (("filesystem", "allowWrite"), lambda v: v != [], False),
)


def _weakening(sandbox: Any, *, flag: bool) -> list[str]:
    """The sandbox values that weaken the boundary, named by their path.
    With ``flag``, a value the ``--settings`` object must set and does not
    counts too."""
    found: list[str] = []
    for keys, weakens, required in _WEAKENING:
        present, value = _get(sandbox, *keys)
        name = "sandbox." + ".".join(keys)
        if present and weakens(value):
            found.append(f"{name} is {json.dumps(value, default=str)}")
        elif not present and flag and required:
            found.append(f"{name} is not set")
    return found


def env_faults(document: Any, where: str) -> list[str]:
    """The ``CLAUDE_CODE_SANDBOX`` variables the ``env`` member of the
    settings object ``document`` sets for the CLI, which change how the
    sandbox starts, each named with ``where``."""
    variables = document.get("env") if isinstance(document, dict) else None
    if not isinstance(variables, dict):
        return []
    return [
        f"{where}env sets {name}"
        for name in variables
        if str(name).startswith("CLAUDE_CODE_SANDBOX")
    ]


def directory_faults(document: Any, where: str) -> list[str]:
    """A non-empty ``permissions.additionalDirectories`` of the settings
    object ``document``: the CLI lets a sandboxed command write each
    directory it adds."""
    present, value = _get(document, "permissions", "additionalDirectories")
    if present and value != []:
        return [f"{where}permissions.additionalDirectories is set"]
    return []


def mode_faults(document: Any, where: str) -> list[str]:
    """A ``permissions.defaultMode`` of the settings object ``document``
    outside :data:`CHECKED_PERMISSION_MODES`: a session may start in it,
    and a hook input that names no mode would not show it."""
    present, value = _get(document, "permissions", "defaultMode")
    if present and not (isinstance(value, str) and value in CHECKED_PERMISSION_MODES):
        return [
            f"{where}permissions.defaultMode is "
            f"{json.dumps(value, default=str)}, a mode this layer has not checked"
        ]
    return []


def pattern_faults(paths: BoundaryPaths) -> list[str]:
    """Each path of ``paths`` the CLI would not read literally in a rule
    or sandbox entry (one holding ``*``, ``?``, brackets, braces,
    parentheses or a backslash): the rule would then match other files, or
    none."""
    return [
        f"{path} holds a character a rule reads as a pattern"
        for path in _unique([*paths.records, *paths.protected, *paths.credential_files])
        if _PATTERN.search(path)
    ]


# The Claude Code versions whose settings this module checks a sandbox
# against: which sources the CLI reads, which values it honours from each,
# and the keys that may weaken the sandbox. A layer that does not know them
# for the host's version has not verified the boundary (STANDARD 1.2.0
# section 5.18.3). 2.1.321 is the CLI that claude-agent-sdk 0.2.180
# bundles: the keys are checked against its settings schema. The sources
# the CLI reads and the values it honours from each were observed under
# 2.1.332 (RFC-0011, open questions 1 and 5), and no run of the tests of
# source precedence under 2.1.321 is recorded. One run of
# tests/test_sandbox_live.py (the bundled CLI, default mode, no settings
# sources), reported on 2026-11-26 without the CLI's version, saw the
# sandbox refuse a host not on the allowlist.
# constraints.txt pins that SDK for CI.
CHECKED_CLI_VERSIONS: frozenset[str] = frozenset({"2.1.321"})

# The Claude Code permission modes in which this layer knows which settings
# sources the CLI reads and which values it honours from each (STANDARD
# 1.2.0 section 5.18.3 makes the mode part of what a layer must know). The
# boundary tests ran the routes the CLI decides itself (the escape
# argument, excluded commands, the network allowlist) in these three modes,
# under Claude Code 2.1.332 (RFC-0011, open question 5). `plan`, `auto`,
# `dontAsk` and any mode this layer does not know were not tested: in them
# a Bash call gets its worst case.
CHECKED_PERMISSION_MODES: frozenset[str] = frozenset(
    {"default", "acceptEdits", "bypassPermissions"}
)


def cli_faults(options: Any) -> list[str]:
    """Why the CLI the Agent SDK starts for ``options`` is not one whose
    settings this module checks (:data:`CHECKED_CLI_VERSIONS`): a CLI that
    ``cli_path`` names (its version is not known without running it), no
    CLI bundled with the SDK (the SDK then runs the ``claude`` on
    ``PATH``), or a bundled CLI of another version. Empty when the SDK
    starts its bundled CLI of a checked version."""
    if getattr(options, "cli_path", None):
        return ["cli_path names a CLI whose version this layer does not know"]
    try:
        import claude_agent_sdk
        from claude_agent_sdk._cli_version import __cli_version__
    except ImportError:
        return ["the Agent SDK states no version for the CLI it bundles"]
    name = "claude.exe" if sys.platform == "win32" else "claude"
    bundled = os.path.join(
        os.path.dirname(os.path.realpath(claude_agent_sdk.__file__)), "_bundled", name
    )
    if not os.path.isfile(bundled):
        return [
            "the Agent SDK bundles no CLI, so it runs the claude on PATH, "
            "whose version this layer does not know"
        ]
    if __cli_version__ not in CHECKED_CLI_VERSIONS:
        return [
            f"the Agent SDK bundles Claude Code {__cli_version__}, and this "
            f"layer checks the settings of Claude Code "
            f"{', '.join(sorted(CHECKED_CLI_VERSIONS))} only"
        ]
    return []


def boundary_faults(
    settings: dict[str, Any] | None,
    paths: BoundaryPaths,
    *,
    destination_policies: bool = False,
) -> list[str]:
    """Why the ``--settings`` object ``settings`` does not hold the
    boundary for ``paths``: one line for each property it misses, empty
    when it holds them all.

    It holds them when its sandbox is on and refuses to run a command it
    cannot sandbox, honours no argument that runs a command outside it,
    excludes no command, opens no weaker mode, socket, Mach service, Apple
    Events or proxy of its own, reads and writes no path beyond its defaults
    (no ``allowRead``, no ``allowWrite``), refuses every host not on its
    allowlist, which names only hosts the setup command would list
    (:func:`~grounded_agency.sandbox_settings.check_host`: no loopback,
    link-local, metadata or local-use name, no IP literal in any spelling,
    no one-label name, no wildcard but a leading ``*.``) and no
    ``metadata.`` name, port or IPv6 literal, keeps every credential file of ``paths`` unreadable, every variable of
    ``paths`` unset and every ``denyWrite`` path of ``paths`` in its
    ``filesystem.denyWrite``, and the ``permissions.deny`` rules hold every
    rule :func:`deny_rules` gives for ``paths``. With ``destination_policies`` (a destination
    policy is in force, STANDARD 1.2.0 section 4.4.2), the allowlist must be
    empty: a call the classifier reads as local leaves ``send`` out, and
    this layer cannot tell that every allowlisted host is one each policy
    allows."""
    if settings is None:
        return ["the options' settings cannot be read"]
    sandbox = settings.get("sandbox")
    if not isinstance(sandbox, dict):
        return ["no sandbox"]
    faults = _weakening(sandbox, flag=True)
    present, domains = _get(sandbox, "network", "allowedDomains")
    if present:
        if not isinstance(domains, list) or not all(
            isinstance(d, str) for d in domains
        ):
            faults.append("sandbox.network.allowedDomains is not a list of names")
        else:
            for domain in domains:
                # The grammar the setup command lists hosts by: a dotted DNS
                # name whose last label is alphabetic, with at most a leading
                # "*." wildcard, and no loopback, link-local, metadata or
                # local-use name. An IP literal in any spelling (hex included),
                # a one-label name (with a trailing dot too) and a wildcard that
                # is not a leading "*." fail it: they may reach this machine, the
                # instance's credentials, or every host.
                why = _refused_entry(domain)
                if why is None and _LOCAL_HOST.fullmatch(
                    domain.strip().rstrip(".").lower()
                ):
                    why = "it names a metadata host, a port or an IPv6 literal"
                if why is not None:
                    faults.append(
                        f"sandbox.network.allowedDomains names "
                        f"{json.dumps(domain, default=str)}: {why}"
                    )
            if domains and destination_policies:
                faults.append(
                    "sandbox.network.allowedDomains is not empty while a "
                    "destination policy is in force"
                )
    files = _get(sandbox, "credentials", "files")[1]
    denied_files = {
        entry.get("path")
        for entry in (files if isinstance(files, list) else [])
        if isinstance(entry, dict) and entry.get("mode") == "deny"
    }
    deny_read = _get(sandbox, "filesystem", "denyRead")[1]
    denied_files |= set(deny_read if isinstance(deny_read, list) else [])
    for path in paths.credential_files:
        if path not in denied_files:
            faults.append(f"the sandbox does not deny reading {path}")
    deny_write = _get(sandbox, "filesystem", "denyWrite")[1]
    denied_writes = set(deny_write if isinstance(deny_write, list) else [])
    for path in paths.record_deny_write:
        if path not in denied_writes:
            faults.append(f"the sandbox does not deny writing {path}")
    variables = _get(sandbox, "credentials", "envVars")[1]
    denied_vars = {
        entry.get("name")
        for entry in (variables if isinstance(variables, list) else [])
        if isinstance(entry, dict) and entry.get("mode") == "deny"
    }
    for name in paths.credential_env:
        if name not in denied_vars:
            faults.append(f"the sandbox does not unset {name}")
    rules = _get(settings, "permissions", "deny")[1]
    rules = set(rules if isinstance(rules, list) else [])
    for rule in deny_rules(paths):
        if rule not in rules:
            faults.append(f"permissions.deny has no {rule}")
    faults.extend(
        f"permissions.allow has {rule}"
        for rule in widening_rules(_get(settings, "permissions", "allow")[1])
    )
    faults.extend(directory_faults(settings, ""))
    faults.extend(env_faults(settings, "the options' settings: "))
    faults.extend(pattern_faults(paths))
    return faults


def widening_rules(rules: Any) -> list[str]:
    """The allow rules among ``rules`` that the CLI merges into the
    sandbox: a ``WebFetch`` rule into its network allowlist, an ``Edit``,
    ``Write`` or ``Read`` rule with a path into the paths it lets a
    sandboxed command write or read."""
    if not isinstance(rules, list):
        return []
    found: list[str] = []
    for rule in rules:
        if not isinstance(rule, str):
            continue
        text = rule.strip()
        if text == "WebFetch" or text.startswith("WebFetch("):
            found.append(text)
        elif text.startswith(("Edit(", "Write(", "Read(")):
            found.append(text)
    return found


def managed_settings_files() -> list[str]:
    """The managed settings files Claude Code reads on this platform: the
    file, then each ``*.json`` of the drop-in directory beside it."""
    if sys.platform == "darwin":
        base = "/Library/Application Support/ClaudeCode"
    elif sys.platform.startswith("win"):
        base = os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"), "ClaudeCode"
        )
    else:
        base = "/etc/claude-code"
    files = [os.path.join(base, "managed-settings.json")]
    drop_ins = os.path.join(base, "managed-settings.d")
    try:
        names = sorted(n for n in os.listdir(drop_ins) if n.endswith(".json"))
    except OSError:
        names = []
    files.extend(os.path.join(drop_ins, n) for n in names)
    return files


def unread_policy_sources(env: Mapping[str, str] | None = None) -> list[str]:
    """The policy sources Claude Code reads that this layer does not: on
    macOS the managed preferences profiles (``com.anthropic.claudecode``
    under ``/Library/Managed Preferences``), the server-managed settings
    Claude Code keeps in its configuration directory
    (``remote-settings.json``), and on Windows the policy registry keys.
    Each one present is listed."""
    found: list[str] = []
    candidates = [os.path.join(config_dir(env), "remote-settings.json")]
    if sys.platform == "darwin":
        try:
            user = os.getlogin()
        except OSError:
            user = os.environ.get("USER", "")
        prefs = "/Library/Managed Preferences"
        if user:
            candidates.append(
                os.path.join(prefs, user, "com.anthropic.claudecode.plist")
            )
        candidates.append(os.path.join(prefs, "com.anthropic.claudecode.plist"))
    for path in candidates:
        if os.path.lexists(path):
            found.append(f"{path} is a policy source this layer does not read")
    if sys.platform.startswith("win"):
        found.append(
            "the policy registry keys (SOFTWARE\\Policies\\ClaudeCode) are a "
            "source this layer does not read"
        )
    return found


def _source_files(
    project_dir: str,
    setting_sources: Sequence[str] | None,
    env: Mapping[str, str] | None,
) -> list[str]:
    files: list[str] = list(managed_settings_files())
    if setting_sources is None or "user" in setting_sources:
        files.append(os.path.join(config_dir(env), "settings.json"))
    for source, name in PROJECT_SETTINGS_FILES:
        if setting_sources is None or source in setting_sources:
            files.append(os.path.join(project_dir, ".claude", name))
    return files


def source_state(
    project_dir: str,
    setting_sources: Sequence[str] | None,
    env: Mapping[str, str] | None = None,
) -> tuple[tuple[str, str | None], ...]:
    """What the settings files of :func:`source_faults` hold now: each
    file's path and the SHA-256 digest of its bytes (None when there is no
    file, ``"unreadable"`` when it cannot be read). Compared with the state
    taken when the options were wrapped, it tells a file changed since."""
    state: list[tuple[str, str | None]] = []
    for path in _source_files(project_dir, setting_sources, env):
        if not os.path.lexists(path):
            state.append((path, None))
            continue
        try:
            data = _read_regular_file(path)
        except OSError:
            state.append((path, "unreadable"))
            continue
        state.append((path, hashlib.sha256(data).hexdigest()))
    return tuple(state)


def source_faults(
    project_dir: str,
    setting_sources: Sequence[str] | None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Why the settings sources the CLI reads besides ``--settings`` may
    weaken the boundary: for managed settings and for each of the user's,
    the project's and the local file ``setting_sources`` names (``None``:
    every one), each sandbox value set there that weakens it (any
    ``allowedDomains`` entry included) and each allow rule the CLI merges
    into the sandbox; each file that is there but cannot be read as a JSON
    object; each policy source this layer does not read
    (:func:`unread_policy_sources`); and each ``CLAUDE_CODE_SANDBOX``
    variable of ``env`` or this process's environment, which change how the
    sandbox starts."""
    found: list[str] = list(unread_policy_sources(env))
    for source in (env or {}, os.environ):
        found.extend(
            f"the environment sets {name}"
            for name in source
            if str(name).startswith("CLAUDE_CODE_SANDBOX")
        )
    for path in _source_files(project_dir, setting_sources, env):
        if not os.path.lexists(path):
            continue
        try:
            document = json.loads(_read_regular_file(path).decode("utf-8"))
        except OSError, ValueError, RecursionError:
            found.append(f"{path} cannot be read")
            continue
        if not isinstance(document, dict):
            found.append(f"{path} is not a JSON object")
            continue
        found.extend(
            f"{path}: permissions.allow has {rule}"
            for rule in widening_rules(_get(document, "permissions", "allow")[1])
        )
        found.extend(directory_faults(document, f"{path}: "))
        found.extend(env_faults(document, f"{path}: "))
        found.extend(mode_faults(document, f"{path}: "))
        sandbox = document.get("sandbox")
        if sandbox is None:
            continue
        if not isinstance(sandbox, dict):
            found.append(f"{path}: sandbox is not an object")
            continue
        weakening = _weakening(sandbox, flag=False)
        present, domains = _get(sandbox, "network", "allowedDomains")
        if present and domains != []:
            weakening.append("sandbox.network.allowedDomains is set")
        found.extend(f"{path}: {w}" for w in weakening)
    return list(dict.fromkeys(found))


def linked_files(paths: BoundaryPaths, limit: int = 50000) -> list[str]:
    """The files among the records (the adapter's and the plugin hooks'),
    the credential files and the link-checked paths of ``paths``
    (:attr:`BoundaryPaths.link_checked`),
    and in the directories among them, that have a hard link outside them:
    a link made outside the sandbox reaches the file under another name
    that no deny rule names (the Linux sandbox lets a command write a
    record, or read a key, through one). A file whose every name lies in
    the walked paths (a lock GnuPG makes in ``~/.gnupg``) is not reported.
    Each named path is followed through a link; what lies under it is not.
    The directories of :attr:`BoundaryPaths.link_skipped` are not walked.
    Past ``limit`` entries, the first path not walked is reported
    instead."""
    names: dict[tuple[int, int], list[str]] = {}
    links: dict[tuple[int, int], int] = {}
    seen = 0
    skipped = set(paths.link_skipped)
    walked: set[str] = set()
    tops = _unique(
        [
            *paths.records,
            *paths.record_deny_write,
            *paths.credential_files,
            *paths.link_checked,
        ]
    )
    for top in tops:
        stack = [(top, True)]
        while stack:
            path, named = stack.pop()
            if path in skipped or path in walked:
                continue
            walked.add(path)
            try:
                status = os.stat(path) if named else os.lstat(path)
            except OSError:
                continue
            seen += 1
            if seen > limit:
                return [
                    *_outside(names, links),
                    f"{path} (not checked: too many files)",
                ]
            if stat.S_ISDIR(status.st_mode):
                try:
                    stack.extend(
                        (os.path.join(path, n), False) for n in os.listdir(path)
                    )
                except OSError:
                    continue
            elif stat.S_ISREG(status.st_mode) and status.st_nlink > 1:
                key = (status.st_dev, status.st_ino)
                # By its real path: a file reached through a linked
                # directory and through its target is one name.
                names.setdefault(key, []).append(os.path.realpath(path))
                links[key] = status.st_nlink
    return _outside(names, links)


def _outside(
    names: Mapping[tuple[int, int], list[str]], links: Mapping[tuple[int, int], int]
) -> list[str]:
    """The files with more links than the names found for them."""
    return [found[0] for key, found in names.items() if links[key] > len(set(found))]
