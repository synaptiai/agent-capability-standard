"""The strict sandbox settings the plugin's setup command writes to user scope.

Claude Code's sandbox is the boundary that keeps the agent's commands from
the layer's records, the user's credentials and the network (RFC-0011).
A plugin cannot change a user's settings itself, so the ``/grounded-setup``
command runs this module: it computes the settings for a project, shows
them as a diff against the user's settings file, and, once the user agrees,
merges them in, leaving every other setting as it is.

The settings, every filesystem path literal and absolute:

- ``sandbox.enabled``, ``failIfUnavailable`` true and
  ``allowUnsandboxedCommands`` false; ``excludedCommands`` removed, since a
  command it names runs outside the sandbox;
- ``sandbox.network.allowedDomains``: the hosts the applied domain profile's
  ``allowed_destinations`` name, the package registries of the ecosystems
  whose manifests the project holds, and the hosts given with
  ``--allow-domain``; never a loopback, link-local or metadata name or an IP
  literal. ``network.strictAllowlist`` true: without it an unlisted host is
  decided by the permission mode, and ``bypassPermissions`` lets it through;
- ``permissions.deny`` rules for the layer's records (``layer_records.py``),
  for the audit key file and its directory, and against writes to the
  project's ``.claude/settings.json``, ``.claude/settings.local.json`` and
  ``.claude/hooks/`` and to the plugin's hook scripts; the same paths in
  ``sandbox.filesystem.denyWrite``;
- ``sandbox.filesystem.denyRead`` and ``sandbox.credentials.files`` deny
  entries for the keychains (macOS), ``~/.ssh``, gh's ``hosts.yml``,
  ``~/.git-credentials``, the package registries' and Docker's credential
  files (``~/.npmrc``, ``~/.pypirc``, ``~/.cargo/credentials.toml`` and the
  like), the audit key file and the git directories' ``acs`` directories,
  which hold the checkpoint key (also denied by the ``Read(...)`` rules);
- ``sandbox.credentials.envVars`` deny entries for ``GH_TOKEN``,
  ``GITHUB_TOKEN``, ``AUDIT_HMAC_KEY`` and the registries' publish tokens.

Run it with the standard library alone (Python 3.9 or later), from the
plugin's directory, with the system's interpreter by its absolute path and
an empty environment, so that the project's settings cannot choose the
interpreter (see :data:`INTERPRETER`)::

    /usr/bin/env -i /usr/bin/python3 -I \
        <plugin>/grounded_agency/sandbox_settings.py plan [--project DIR]
        [--profile FILE] [--allow-domain HOST ...]
    ... sandbox_settings.py apply --digest HEX [...]
    ... sandbox_settings.py settings [...]
    ... sandbox_settings.py check [...]

``plan`` prints the change and a digest of it and writes nothing; ``apply``
writes the change the digest names (or, in a terminal, shows it and asks),
creates the audit key file when there is none, then reads the settings file
back and checks every key against Claude Code's documented settings;
``settings`` prints the computed settings alone, as JSON (for managed
settings or ``--settings``); ``check`` reads the settings file and reports
what is missing.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import errno
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

__all__ = [
    "CREDENTIAL_ENV_VARS",
    "REGISTRIES",
    "Plan",
    "SandboxSettingsError",
    "SettingsFileError",
    "UnsupportedPlatformError",
    "apply_plan",
    "audit_key_path",
    "check_host",
    "compute_settings",
    "credential_paths",
    "destination_host",
    "ensure_audit_key",
    "main",
    "make_plan",
    "merge_settings",
    "parse_settings_text",
    "read_profile_destinations",
    "registry_hosts",
    "unknown_keys",
    "user_settings_path",
    "verify_settings",
]

MIN_PYTHON = (3, 9)

# How the command runs the script. A repository's settings can set any
# environment variable for every Bash call (an ``env`` block): ``PATH`` would
# choose which ``python3`` runs, and on macOS ``DEVELOPER_DIR`` sends the
# ``/usr/bin/python3`` stub to a program of the repository's. So the command
# names the system's interpreter by its absolute path, which no ``PATH`` and
# no exported shell function can replace (bash imports no function whose
# name holds a slash), and starts it through ``env -i`` with no inherited
# variable but ``CLAUDE_CONFIG_DIR`` when it is set. Python then takes the
# home directory from the password database, not from ``HOME``.
INTERPRETER = "/usr/bin/python3"
RUN_PREFIX: tuple[str, ...] = ("/usr/bin/env", "-i")

# The environment variables a sandboxed command would otherwise inherit and
# read: gh's and git's tokens, the audit log's key, and the tokens that
# publish to the package registries on the allowlist.
CREDENTIAL_ENV_VARS: tuple[str, ...] = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "AUDIT_HMAC_KEY",
    "NPM_TOKEN",
    "NODE_AUTH_TOKEN",
    "CARGO_REGISTRY_TOKEN",
    "GEM_HOST_API_KEY",
    "TWINE_PASSWORD",
    "UV_PUBLISH_TOKEN",
    "POETRY_PYPI_TOKEN_PYPI",
)

# Credential files under the home directory, besides the keychains and the
# audit key: ssh's keys, gh's and git's tokens, and the files that hold the
# package registries' and Docker's tokens (a sandboxed command could publish
# to a registry the allowlist names).
_HOME_CREDENTIALS: tuple[str, ...] = (
    ".ssh",
    ".config/gh/hosts.yml",
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".yarnrc.yml",
    ".pypirc",
    ".cargo/credentials",
    ".cargo/credentials.toml",
    ".gem/credentials",
    ".docker/config.json",
    ".config/composer/auth.json",
    ".m2/settings.xml",
    ".gradle/gradle.properties",
    ".pub-cache/credentials.json",
)

# What a registry's hosts allow beyond downloads, said beside them in the plan.
_REGISTRY_NOTES = {
    "Go modules": "the Go proxy fetches a module from whatever host its path "
    "names, so a request to it can carry data to any host",
}

# Each ecosystem's public registry hosts, by the manifest or lock files that
# show a project uses it. Registry addresses a project's own files configure
# (.npmrc, pip.conf, nuget.config) are not read: the repository controls
# them, and these settings apply to every project of the user.
REGISTRIES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "npm",
        (
            "package.json",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "pnpm-lock.yaml",
            "bun.lock",
            "bun.lockb",
        ),
        ("registry.npmjs.org",),
    ),
    ("Yarn", ("yarn.lock",), ("registry.yarnpkg.com", "registry.npmjs.org")),
    (
        "PyPI",
        (
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "Pipfile",
            "Pipfile.lock",
            "poetry.lock",
            "uv.lock",
            "pdm.lock",
            "requirements.txt",
        ),
        ("pypi.org", "files.pythonhosted.org"),
    ),
    (
        "crates.io",
        ("Cargo.toml", "Cargo.lock"),
        ("crates.io", "index.crates.io", "static.crates.io"),
    ),
    ("Go modules", ("go.mod",), ("proxy.golang.org", "sum.golang.org")),
    (
        "RubyGems",
        ("Gemfile", "Gemfile.lock"),
        ("rubygems.org", "index.rubygems.org"),
    ),
    (
        "Maven Central",
        ("pom.xml", "build.gradle", "build.gradle.kts"),
        ("repo.maven.apache.org", "repo1.maven.org"),
    ),
    (
        "Gradle",
        ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
        ("services.gradle.org", "plugins.gradle.org", "plugins-artifacts.gradle.org"),
    ),
    ("NuGet", ("packages.config",), ("api.nuget.org",)),
    ("Packagist", ("composer.json", "composer.lock"), ("repo.packagist.org",)),
    ("pub.dev", ("pubspec.yaml",), ("pub.dev",)),
    ("Hex", ("mix.exs",), ("hex.pm", "repo.hex.pm")),
)
# File name patterns that also show an ecosystem: requirements-dev.txt and
# the like for PyPI, a .NET project file for NuGet.
_REGISTRY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PyPI", re.compile(r"requirements[\w.-]*\.txt")),
    ("NuGet", re.compile(r"[^/]+\.(?:csproj|fsproj|vbproj)")),
)
# Directories not searched for manifests: dependencies, build output and
# hidden directories hold other projects' manifests.
_SKIPPED_DIRS = frozenset(
    {
        "node_modules",
        "target",
        "vendor",
        "venv",
        "dist",
        "build",
        "__pycache__",
        "site-packages",
        "bower_components",
    }
)
_MANIFEST_DEPTH = 3
_MANIFEST_DIR_LIMIT = 5000

# Names that resolve to loopback, link-local or a cloud metadata service,
# and the suffixes of names kept for local use. The positive grammar below
# already refuses an IP literal in any spelling and a one-label name
# (localhost, metadata, instance-data).
_REFUSED_HOSTS = frozenset(
    {
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data.ec2.internal",
    }
)
_REFUSED_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
    ".arpa",
    # Services that resolve a name to the address it spells out, dotted,
    # dashed or in hex (127.0.0.1.nip.io, 127-0-0-1.sslip.io).
    ".nip.io",
    ".sslip.io",
    ".xip.io",
)
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_TOP_LABEL = re.compile(r"[a-z]{2,63}|xn--[a-z0-9-]{1,59}")

# Characters a permission rule or a sandbox path reads as a pattern (as
# layer_records.py refuses them).
_PATTERN_CHARACTERS = frozenset("*?[]{}()\\")

# Claude Code's documented settings keys (code.claude.com/docs/en/settings-reference,
# "Sandbox settings" and "permissions"): Claude Code accepts a misspelled key
# without a word, so a typo in a safety key leaves it unset.
_KNOWN_KEYS: dict[str, frozenset[str]] = {
    "sandbox": frozenset(
        {
            "enabled",
            "failIfUnavailable",
            "autoAllowBashIfSandboxed",
            "excludedCommands",
            "allowUnsandboxedCommands",
            "enableWeakerNestedSandbox",
            "enableWeakerNetworkIsolation",
            "allowAppleEvents",
            "allowNestedUserNamespaces",
            "bwrapPath",
            "socatPath",
            "ignoreViolations",
            "ripgrep",
            "filesystem",
            "network",
            "credentials",
        }
    ),
    "sandbox.filesystem": frozenset(
        {
            "allowWrite",
            "denyWrite",
            "denyRead",
            "allowRead",
            "allowManagedReadPathsOnly",
            "disabled",
        }
    ),
    "sandbox.network": frozenset(
        {
            "allowUnixSockets",
            "allowAllUnixSockets",
            "allowLocalBinding",
            "allowMachLookup",
            "allowedDomains",
            "deniedDomains",
            "strictAllowlist",
            "allowManagedDomainsOnly",
            "httpProxyPort",
            "socksProxyPort",
            "tlsTerminate",
        }
    ),
    "sandbox.credentials": frozenset(
        {"files", "envVars", "allowPlaintextInject", "awsPairs", "sigv4"}
    ),
    "sandbox.credentials.files[]": frozenset(
        {
            "path",
            "mode",
            "extract",
            "onExtractNoMatch",
            "decode",
            "maskClaims",
            "maskDuplicates",
            "injectHosts",
        }
    ),
    "sandbox.credentials.envVars[]": frozenset(
        {
            "name",
            "mode",
            "extract",
            "onExtractNoMatch",
            "decode",
            "maskClaims",
            "injectHosts",
        }
    ),
    "permissions": frozenset(
        {
            "allow",
            "ask",
            "deny",
            "additionalDirectories",
            "blockReadsOutsideWorkingDirectories",
            "blockWritesOutsideWorkingDirectories",
            "defaultMode",
            "denyInsteadOfPrompting",
            "disableBypassPermissionsMode",
            "disableAutoMode",
        }
    ),
}

# The notes every plan ends with.
NOTES = (
    "What stops working: a sandboxed gh or git push cannot authenticate (the "
    "keychain, ~/.ssh, gh's hosts.yml, ~/.git-credentials and the token "
    "variables are denied to it), and neither can a publish to a package "
    "registry (npm, cargo, gem, twine, uv). Tools that need the keychain fail. "
    "The tools also run without ~/.npmrc, ~/.yarnrc.yml, ~/.m2/settings.xml, "
    "~/.gradle/gradle.properties and ~/.docker/config.json, which are denied "
    "too: a private registry, a mirror or a proxy set there is not used (npm "
    "then goes to the public registry), so such an install fails or fetches "
    "from elsewhere. A host not on the list is refused without a prompt. Run "
    "those commands yourself, outside Claude Code.",
    "What a repository can still do: its own .claude/settings.json or "
    ".claude/settings.local.json can turn the sandbox off, exclude commands "
    "from it or widen its write scope, and the plugin's hook then gates every "
    "Bash call. Only managed settings prevent this; an administrator can put "
    "these settings in managed settings (the 'settings' command prints them).",
    "The paths are this project's and this plugin copy's: run the command again "
    "in each project, after git worktree add or a submodule's first checkout, "
    "and after the plugin is updated. Entries for other projects stay.",
)


class SandboxSettingsError(Exception):
    """The settings cannot be computed or written."""


class SettingsFileError(SandboxSettingsError):
    """The user's settings file cannot be read as Claude Code reads it, so it
    is left as it is."""


class UnsupportedPlatformError(SandboxSettingsError):
    """Claude Code has no sandbox on this platform."""


def _check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        raise SandboxSettingsError(
            "this needs Python {}.{} or later (this is {}.{}); install a later "
            "python3".format(*MIN_PYTHON, *sys.version_info[:2])
        )


def _layer_records() -> ModuleType:
    """The sibling ``layer_records`` module, imported from the package or,
    when this file runs as a script with ``-I``, loaded by its path."""
    if __package__:
        from . import layer_records

        return layer_records
    name = "_acs_layer_records"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name("layer_records.py")
    )
    if spec is None or spec.loader is None:
        raise SandboxSettingsError("cannot load layer_records.py beside this file")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --- Platform and paths -------------------------------------------------------


def _platform_name(platform: str) -> str:
    """macOS or Linux, the platforms with a sandbox; else raise."""
    if platform == "darwin":
        return "macOS"
    if platform.startswith("linux"):
        return "Linux"
    if platform in ("win32", "cygwin", "msys"):
        raise UnsupportedPlatformError(
            "Claude Code has no sandbox on native Windows: it runs commands "
            "unsandboxed there, so nothing is written. Run Claude Code inside "
            "WSL2 and run this command there."
        )
    raise UnsupportedPlatformError(
        f"Claude Code's sandbox runs on macOS, Linux and WSL2, not on "
        f"{platform!r}, so nothing is written."
    )


def _check_literal(path: str) -> None:
    bad = sorted({c for c in path if c in _PATTERN_CHARACTERS or ord(c) < 0x20})
    if bad:
        raise SandboxSettingsError(
            f"{path!r} holds {''.join(bad)!r}, which a permission rule or a "
            "sandbox path reads as a pattern: it cannot be denied by a literal "
            "entry"
        )


def _spellings(path: str) -> list[str]:
    """``path`` made absolute and, where it differs, its physical path (every
    symbolic link resolved): a rule and a path are compared as text."""
    written = os.path.abspath(path)
    physical = os.path.realpath(written)
    out = [written] if written == physical else [written, physical]
    for p in out:
        _check_literal(p)
    return out


def user_settings_path(home: str, environ: dict[str, str] | None = None) -> str:
    """The user's settings file: ``$CLAUDE_CONFIG_DIR/settings.json`` when
    that variable is set, else ``~/.claude/settings.json``."""
    env = os.environ if environ is None else environ
    config_dir = env.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return os.path.join(os.path.abspath(config_dir), "settings.json")
    return os.path.join(home, ".claude", "settings.json")


def audit_key_path(home: str) -> str:
    """The audit key file the hooks read: ``~/.config/acs/audit.key``."""
    return os.path.join(home, ".config", "acs", "audit.key")


def credential_paths(home: str, platform: str) -> list[str]:
    """The credential files and directories denied to sandboxed commands,
    absolute: the keychains on macOS, ``~/.ssh``, gh's ``hosts.yml``,
    ``~/.git-credentials``, the registries' and Docker's credential files
    and the audit key file."""
    _platform_name(platform)
    paths: list[str] = []
    if platform == "darwin":
        paths += [os.path.join(home, "Library", "Keychains"), "/Library/Keychains"]
    paths += [os.path.join(home, *rel.split("/")) for rel in _HOME_CREDENTIALS]
    paths.append(audit_key_path(home))
    out: list[str] = []
    for p in paths:
        for s in _spellings(p):
            if s not in out:
                out.append(s)
    return out


# --- Network allowlist --------------------------------------------------------


def check_host(entry: str) -> str | None:
    """Why ``entry`` (a host, ``*.``-wildcard or ``host:port``) may not be on
    the allowlist, or None when it may. Only a DNS name whose last label is
    alphabetic is accepted, so no IP literal in any spelling (``127.1``,
    ``0x7f000001``, ``[::1]``) and no one-label name (``localhost``,
    ``metadata``) passes; loopback, link-local and metadata names and the
    suffixes kept for local use are refused too."""
    host = entry.strip()
    if host != entry or not host:
        return "it is empty or has blanks around it"
    if host.startswith("["):
        return "it is an IP literal"
    if "/" in host or "@" in host:
        return "it is a URL, not a host name"
    m = re.fullmatch(r"(.+?)(?::(\d{1,5}))?", host)
    if m is None:
        return "it is not a host name"
    host, port = m.group(1), m.group(2)
    if port is not None and not 1 <= int(port) <= 65535:
        return "its port is out of range"
    if ":" in host:
        return "it is an IP literal"
    if host.endswith("."):
        host = host[:-1]
    if host != host.lower():
        return "it is not in lower case"
    wildcard = host.startswith("*.")
    name = host[2:] if wildcard else host
    labels = name.split(".")
    if len(name) > 253 or not all(_LABEL.fullmatch(label) for label in labels):
        return "it is not a host name (letters, digits and hyphens in dotted labels)"
    if len(labels) < 2 or not _TOP_LABEL.fullmatch(labels[-1]):
        return (
            "it is an IP literal or a one-label name: only a dotted DNS name "
            "whose last label is alphabetic is listed"
        )
    if any(
        all(lb.isdigit() for lb in labels[i : i + 4]) for i in range(len(labels) - 3)
    ):
        return "it holds a dotted IP address, and such names resolve to it"
    dotted = "." + name
    if name in _REFUSED_HOSTS or any(dotted.endswith(s) for s in _REFUSED_SUFFIXES):
        return "it names a loopback, link-local or metadata host, or a local-use name"
    return None


def _refused_entry(entry: str) -> str | None:
    """Why an allowlist entry already in the user's settings is removed, or
    None when it stays: every entry :func:`check_host` does not accept,
    whatever its letter case or blanks. Claude Code's matcher reads ``*``
    as every host, so an entry whose wildcard is anything but a leading
    ``*.`` would open IP literals and metadata addresses with the rest."""
    host = entry.strip().lower()
    name = re.sub(r":[0-9]*$", "", host)
    if "*" in name and not (name.startswith("*.") and "*" not in name[2:]):
        return "it matches every host, IP literals and metadata addresses included"
    return check_host(host)


def _refused_web_fetch(rule: Any) -> str | None:
    """Why a permission rule ``WebFetch(domain:<host>)`` names a host the
    allowlist may not hold (Claude Code adds such a rule's host to the
    sandbox's allowlist), or None for any other rule."""
    m = (
        re.fullmatch(r"WebFetch\(domain:(.*)\)", rule)
        if isinstance(rule, str)
        else None
    )
    return None if m is None else _refused_entry(m.group(1))


def _valid_pattern(pattern: str) -> bool:
    """Whether ``pattern`` is a destination pattern of the Standard's
    §4.4.2 (an exact destination, ``<prefix>*`` or ``*<suffix>``)."""
    if not pattern or any(c.isspace() or not c.isprintable() for c in pattern):
        return False
    stars = pattern.count("*")
    if stars == 0:
        return True
    if stars != 1:
        return False
    if pattern.endswith("*") and len(pattern) > 1:
        prefix = pattern[:-1]
        if prefix[-1] not in "/:@.?#":
            return False
        scheme = _SCHEME.match(prefix)
        return scheme is None or any(c in prefix[scheme.end() :] for c in "/?#")
    if pattern.startswith("*"):
        suffix = pattern[1:]
        return len(suffix) >= 2 and suffix[0] in "@."
    return False


_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")


def destination_host(pattern: str) -> tuple[str | None, str]:
    """The allowlist entry a destination pattern gives, with what it covers;
    or None, with the reason it gives none.

    A URL (exact, or a prefix that names its whole authority) gives its host,
    and its port when it names one: the allowlist is by host, so a path in
    the pattern widens to the whole host. ``*.example.com`` gives itself. An
    address (``ops@example.com``, ``*@example.com``) or another destination
    that names no host gives none.

    Raises:
        SandboxSettingsError: the pattern is not one of the Standard's forms.
    """
    if not _valid_pattern(pattern):
        raise SandboxSettingsError(
            f"{pattern!r} is not a destination pattern of the Standard "
            "(§4.4.2), so the profile is refused"
        )
    if not pattern.isascii():
        return None, "not ASCII: give its host in the xn-- form with --allow-domain"
    if pattern.startswith("*"):
        if pattern[1] == "@":
            return None, "an address domain, not a host"
        entry = "*" + pattern[1:]
        return entry, "every name under it"
    body = pattern[:-1] if pattern.endswith("*") else pattern
    scheme = _SCHEME.match(body)
    if scheme is not None:
        rest = body[scheme.end() :]
        authority = re.split(r"[/?#]", rest, maxsplit=1)[0]
        if pattern.endswith("*") and authority == rest:
            return None, "a prefix that does not name a whole host"
        hostport = authority.rsplit("@", 1)[-1]
        if not hostport:
            return None, "no host"
        return hostport.lower(), "the whole host, every path"
    if pattern.endswith("*"):
        return None, "a prefix that does not name a host"
    if "@" in body or ":" in body or "/" in body:
        return None, "an address or a destination that names no host"
    return body.lower(), "the host"


# --- Reading a profile's allowed_destinations ---------------------------------

_YAML_NON_STRING = re.compile(
    r"(?:~|null|Null|NULL|true|True|TRUE|false|False|FALSE|yes|Yes|YES|no|No|NO|"
    r"on|On|ON|off|Off|OFF|[-+]?(?:0|[1-9][0-9_]*|0[0-7_]+|0x[0-9a-fA-F_]+|0b[01_]+)|"
    r"[-+]?(?:[0-9][0-9_]*)?\.[0-9_]*(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|"
    r"\.(?:nan|NaN|NAN))"
)


def _yaml_scalar(text: str, where: str, flow: bool) -> tuple[str, str]:
    """One scalar at the start of ``text``: a quoted string or a plain one.
    Returns the value and the rest of the line. Raises on any form outside
    the subset read here."""
    if text.startswith("'"):
        out, i = [], 1
        while True:
            j = text.find("'", i)
            if j < 0:
                raise SandboxSettingsError(f"{where}: an unclosed quote")
            out.append(text[i:j])
            if text.startswith("''", j):
                out.append("'")
                i = j + 2
                continue
            return "".join(out), text[j + 1 :]
    if text.startswith('"'):
        out, i = [], 1
        while i < len(text):
            c = text[i]
            if c == '"':
                return "".join(out), text[i + 1 :]
            if c == "\\":
                nxt = text[i + 1 : i + 2]
                if nxt not in ('"', "\\", "/"):
                    raise SandboxSettingsError(
                        f"{where}: an escape this reader does not take "
                        f"(\\{nxt}); write the destination without it"
                    )
                out.append(nxt)
                i += 2
                continue
            out.append(c)
            i += 1
        raise SandboxSettingsError(f"{where}: an unclosed quote")
    i = 0
    while i < len(text):
        c = text[i]
        if flow and c in ",]":
            break
        if c == "#" and i > 0 and text[i - 1] in " \t":
            break
        i += 1
    value = text[:i].rstrip()
    if not value:
        raise SandboxSettingsError(f"{where}: no value")
    if (
        value[0] in "[]{}&*!|>%@`,#"
        or value[:2] in ("- ", "? ", ": ")
        or value in ("-", "?", ":")
        or ": " in value
        or value.endswith(":")
    ):
        raise SandboxSettingsError(
            f"{where}: {value!r} is not a plain string here (an anchor, an "
            "alias such as *.example.com, a tag, a nested list or a mapping); "
            "quote it"
        )
    if _YAML_NON_STRING.fullmatch(value):
        raise SandboxSettingsError(f"{where}: {value!r} is not a string")
    return value, text[i:]


def _strip_comment(rest: str, where: str) -> None:
    rest = rest.strip()
    if rest and not rest.startswith("#"):
        raise SandboxSettingsError(f"{where}: unexpected text {rest!r}")


def _yaml_destinations(text: str, where: str) -> list[str] | None:
    """``allowed_destinations`` from a profile in YAML, read for that one
    top-level key, as a block or a one-line flow sequence of strings; None
    when the profile has no such key. Any other form is refused rather than
    guessed at."""
    lines = text.splitlines()
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("%") or s == "---":
            continue
        if s[0] in "{[":
            raise SandboxSettingsError(
                f"{where}: a profile written as a flow mapping is not read here; "
                "write it in block style or as JSON"
            )
        break
    found = [
        i for i, line in enumerate(lines) if re.match(r"allowed_destinations\s*:", line)
    ]
    if any(re.match(r"[\"'?]\s*allowed_destinations", line) for line in lines):
        raise SandboxSettingsError(
            f"{where}: allowed_destinations is written as a quoted or complex "
            "key, which this reader does not take; write it plain"
        )
    if not found:
        return None
    if len(found) > 1:
        raise SandboxSettingsError(f"{where}: allowed_destinations is given twice")
    i = found[0]
    rest = lines[i].split(":", 1)[1].strip()
    here = f"{where}, line {i + 1}"
    if rest and not rest.startswith("#"):
        if not rest.startswith("["):
            raise SandboxSettingsError(
                f"{here}: allowed_destinations must be a list of strings"
            )
        items: list[str] = []
        body = rest[1:].lstrip()
        if body.startswith("]"):
            _strip_comment(body[1:], here)
            return items
        while True:
            value, body = _yaml_scalar(body, here, flow=True)
            items.append(value)
            body = body.lstrip()
            if body.startswith(","):
                body = body[1:].lstrip()
                continue
            if body.startswith("]"):
                _strip_comment(body[1:], here)
                return items
            raise SandboxSettingsError(
                f"{here}: a flow list must close on its line; use a block list"
            )
    items = []
    indent: str | None = None
    for j in range(i + 1, len(lines)):
        line = lines[j]
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"(\s*)- (.*)$", line) or re.match(r"(\s*)-()$", line)
        if m is None:
            if line[0] in " \t":
                raise SandboxSettingsError(
                    f"{where}, line {j + 1}: allowed_destinations must be a list "
                    "of strings"
                )
            break
        if indent is None:
            indent = m.group(1)
        elif m.group(1) != indent:
            raise SandboxSettingsError(f"{where}, line {j + 1}: uneven indentation")
        if not m.group(2).strip():
            raise SandboxSettingsError(f"{where}, line {j + 1}: an empty item")
        value, after = _yaml_scalar(
            m.group(2).lstrip(), f"{where}, line {j + 1}", flow=False
        )
        _strip_comment(after, f"{where}, line {j + 1}")
        items.append(value)
    if indent is None:
        raise SandboxSettingsError(
            f"{here}: allowed_destinations has no value; give a list ([] for none)"
        )
    return items


def read_profile_destinations(path: str) -> list[str] | None:
    """A domain profile's ``allowed_destinations``, from a JSON or YAML
    profile file; None when the profile sets none.

    YAML is read for that one top-level key only, without a YAML library:
    a block list or a one-line flow list of plain or quoted strings. Any
    other form of it is refused.

    Raises:
        SandboxSettingsError: the file cannot be read, or the key is in a
            form this reader does not take, or is not a list of strings.
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise SandboxSettingsError(
            f"cannot read the profile {path!r}: {e.strerror}"
        ) from e
    except UnicodeDecodeError as e:
        raise SandboxSettingsError(f"the profile {path!r} is not UTF-8") from e
    if path.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise SandboxSettingsError(f"the profile {path!r} is not JSON: {e}") from e
        if not isinstance(data, dict):
            raise SandboxSettingsError(f"the profile {path!r} is not an object")
        value = data.get("allowed_destinations")
        if value is None and "allowed_destinations" not in data:
            return None
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SandboxSettingsError(
                f"{path}: allowed_destinations must be a list of strings"
            )
        return list(value)
    return _yaml_destinations(text, path)


# --- Package registries ---------------------------------------------------------


def registry_hosts(project: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """The registries the project uses, as (ecosystem, the manifest that
    shows it, relative to the project, its hosts), from the manifest and lock
    files in the project and its directories up to three levels down
    (hidden, dependency and build directories skipped)."""
    by_name: dict[str, list[str]] = {}
    for eco, names, _ in REGISTRIES:
        for n in names:
            by_name.setdefault(n, []).append(eco)
    found: dict[str, str] = {}
    root = os.path.abspath(project)
    visited = 0
    for dirpath, dirnames, filenames in os.walk(root):
        visited += 1
        depth = (
            0 if dirpath == root else os.path.relpath(dirpath, root).count(os.sep) + 1
        )
        dirnames[:] = sorted(
            d
            for d in dirnames
            if depth < _MANIFEST_DEPTH
            and not d.startswith(".")
            and d not in _SKIPPED_DIRS
            and visited < _MANIFEST_DIR_LIMIT
        )
        for fname in sorted(filenames):
            ecos = list(by_name.get(fname, []))
            ecos += [eco for eco, rx in _REGISTRY_PATTERNS if rx.fullmatch(fname)]
            for eco in ecos:
                if eco not in found:
                    found[eco] = os.path.relpath(os.path.join(dirpath, fname), root)
    return [(eco, found[eco], hosts) for eco, _, hosts in REGISTRIES if eco in found]


# --- The settings ---------------------------------------------------------------


@dataclass
class Computed:
    """The settings computed for a project, and what went into the
    allowlist and what did not."""

    settings: dict[str, Any]
    domains: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    profile_state: str = "no profile given"


def compute_settings(
    project: str,
    home: str,
    platform: str,
    plugin_root: str,
    profile_destinations: list[str] | None = None,
    extra_domains: tuple[str, ...] | list[str] = (),
    profile_given: bool = False,
) -> Computed:
    """The strict sandbox settings for ``project`` (see the module's
    description), every path literal and absolute.

    Raises:
        UnsupportedPlatformError: the platform has no sandbox.
        SandboxSettingsError: a path cannot be written as a literal entry, a
            destination pattern is invalid, an extra domain may not be listed,
            or git did not say which git directory is the project's.
    """
    _platform_name(platform)
    lr = _layer_records()
    try:
        records = lr.deny_settings(project)
    except lr.LayerRecordsError as e:
        raise SandboxSettingsError(str(e)) from e

    domains: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []

    def add_domain(entry: str, why: str) -> None:
        if all(entry != d for d, _ in domains):
            domains.append((entry, why))

    if profile_destinations is None:
        state = (
            "the profile sets no allowed_destinations"
            if profile_given
            else "no profile given"
        )
    elif not profile_destinations:
        state = "the profile's allowed_destinations is empty: it allows no send"
    else:
        state = f"{len(profile_destinations)} destination(s) from the profile"
    for pattern in profile_destinations or []:
        entry, what = destination_host(pattern)
        if entry is None:
            skipped.append((pattern, what))
            continue
        reason = check_host(entry)
        if reason is not None:
            skipped.append((pattern, f"refused: {reason}"))
            continue
        add_domain(entry, f"profile: {json.dumps(pattern)} ({what})")
    for eco, manifest, hosts in registry_hosts(project):
        note = _REGISTRY_NOTES.get(eco)
        for h in hosts:
            add_domain(
                h,
                f"{eco} registry ({json.dumps(manifest)})"
                + (f"; {note}" if note else ""),
            )
    for d in extra_domains:
        reason = check_host(d)
        if reason is not None:
            raise SandboxSettingsError(f"--allow-domain {d!r} is refused: {reason}")
        add_domain(d, "--allow-domain")

    creds = credential_paths(home, platform)
    key_file = audit_key_path(home)
    key_files = _spellings(key_file)
    key_dirs = _spellings(os.path.dirname(key_file))
    config_files: list[tuple[str, bool]] = []
    for base in _spellings(project):
        config_files += [
            (os.path.join(base, ".claude", "settings.json"), False),
            (os.path.join(base, ".claude", "settings.local.json"), False),
            (os.path.join(base, ".claude", "hooks"), True),
        ]
    for hooks in _spellings(os.path.join(plugin_root, "hooks")):
        config_files.append((hooks, True))

    def rule(kind: str, path: str, directory: bool) -> str:
        return f"{kind}(/{path}{'/**' if directory else ''})"

    deny: list[str] = list(records["permissions"]["deny"])
    for p in key_files:
        deny += [rule("Read", p, False), rule("Edit", p, False)]
    for d in key_dirs:
        deny.append(rule("Edit", d, True))
    for p, directory in config_files:
        deny.append(rule("Edit", p, directory))
    deny_write: list[str] = list(records["sandbox"]["filesystem"]["denyWrite"])
    deny_write += key_dirs + [p for p, _ in config_files]
    # The git directories' records hold the checkpoint key: denied to
    # sandboxed reads by the sandbox's own lists too, so that the denial
    # does not rest on Claude Code merging the Read(...) rules into them.
    deny_read = list(creds)
    for r in records["permissions"]["deny"]:
        if r.startswith("Read(/") and r.endswith(")"):
            path = r[len("Read(/") : -1]
            deny_read.append(path[:-3] if path.endswith("/**") else path)
    deny_read = _unique(deny_read)

    settings: dict[str, Any] = {
        "permissions": {"deny": _unique(deny)},
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "allowUnsandboxedCommands": False,
            "network": {
                "allowedDomains": [d for d, _ in domains],
                "strictAllowlist": True,
            },
            "filesystem": {
                "denyRead": deny_read,
                "denyWrite": _unique(deny_write),
            },
            "credentials": {
                "files": [{"path": p, "mode": "deny"} for p in deny_read],
                "envVars": [{"name": n, "mode": "deny"} for n in CREDENTIAL_ENV_VARS],
            },
        },
    }
    return Computed(settings, domains, skipped, state)


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


# --- The user's settings file ---------------------------------------------------


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise SettingsFileError(
                f"the key {k!r} appears twice in one object; Claude Code keeps "
                "one of them, and rewriting the file would drop the other"
            )
        out[k] = v
    return out


def _expect(obj: dict[str, Any], key: str, kind: type, where: str) -> Any:
    value = obj.get(key)
    if key in obj and not isinstance(value, kind):
        raise SettingsFileError(
            f"{where}.{key} is a {type(value).__name__}, not a{'n' if kind is list else ''} "
            f"{'array' if kind is list else 'object'}"
        )
    return value


def _string_list(obj: dict[str, Any] | None, key: str, where: str) -> None:
    if obj is None:
        return
    value = _expect(obj, key, list, where)
    if value is not None and not all(isinstance(v, str) for v in value):
        raise SettingsFileError(f"{where}.{key} holds an entry that is not a string")


def parse_settings_text(text: str) -> dict[str, Any]:
    """The user's settings, parsed as Claude Code parses them (strict JSON),
    with the members this module changes checked for type.

    Raises:
        SettingsFileError: the file is not strict JSON (a comment or a
            trailing comma is a syntax error to Claude Code too), repeats a
            key, is not an object, or one of those members has the wrong type.
    """
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicates)
    except json.JSONDecodeError as e:
        raise SettingsFileError(
            f"it is not valid JSON ({e.msg}, line {e.lineno} column {e.colno}); "
            "Claude Code reads settings as strict JSON, where a comment or a "
            "trailing comma is an error"
        ) from e
    if not isinstance(data, dict):
        raise SettingsFileError("it is not a JSON object")
    sandbox = _expect(data, "sandbox", dict, "settings")
    perms = _expect(data, "permissions", dict, "settings")
    _string_list(perms, "deny", "permissions")
    if sandbox is not None:
        _string_list(sandbox, "excludedCommands", "sandbox")
        net = _expect(sandbox, "network", dict, "sandbox")
        fs = _expect(sandbox, "filesystem", dict, "sandbox")
        cred = _expect(sandbox, "credentials", dict, "sandbox")
        _string_list(net, "allowedDomains", "sandbox.network")
        _string_list(fs, "denyRead", "sandbox.filesystem")
        _string_list(fs, "denyWrite", "sandbox.filesystem")
        if cred is not None:
            for key in ("files", "envVars"):
                value = _expect(cred, key, list, "sandbox.credentials")
                if value is not None and not all(isinstance(v, dict) for v in value):
                    raise SettingsFileError(
                        f"sandbox.credentials.{key} holds an entry that is not an object"
                    )
    return data


def merge_settings(
    current: dict[str, Any], computed: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """``current`` with the computed settings merged in, and a line for each
    existing entry the merge removes.

    The four switches are set; every list gains the entries it lacks, after
    the ones it has; ``sandbox.excludedCommands`` and a true
    ``sandbox.filesystem.disabled`` are removed (each takes commands or the
    filesystem rules out of the sandbox), and so is an allowlist entry that
    may not be listed. So is every setting :func:`_undoing` names: a proxy
    port, a true ``allowAllUnixSockets``, and a ``WebFetch(domain:...)``
    allow rule for a host the allowlist may not hold; the read-back fails
    on each, so leaving one would fail every run. Every other key is left
    as it is, in its place.
    """
    new = copy.deepcopy(current)
    removed: list[str] = []
    cs = computed["sandbox"]

    perms = new.setdefault("permissions", {})
    deny = perms.setdefault("deny", [])
    deny.extend(r for r in computed["permissions"]["deny"] if r not in deny)
    allow = perms.get("allow")
    if isinstance(allow, list):
        kept_allow = []
        for r in allow:
            reason = _refused_web_fetch(r)
            if reason is None:
                kept_allow.append(r)
            else:
                removed.append(f"permissions.allow {json.dumps(r)}: {reason}")
        perms["allow"] = kept_allow

    sb = new.setdefault("sandbox", {})
    for key in ("enabled", "failIfUnavailable", "allowUnsandboxedCommands"):
        sb[key] = cs[key]
    if "excludedCommands" in sb:
        removed.append(
            f"sandbox.excludedCommands {json.dumps(sb['excludedCommands'])}: a "
            "command it names runs outside the sandbox"
        )
        del sb["excludedCommands"]

    net = sb.setdefault("network", {})
    for key in ("httpProxyPort", "socksProxyPort"):
        if key in net:
            removed.append(
                f"sandbox.network.{key} {json.dumps(net[key])}: your own proxy then "
                "filters the traffic, and the allowlist stops applying"
            )
            del net[key]
    if net.get("allowAllUnixSockets") is True:
        removed.append(
            "sandbox.network.allowAllUnixSockets true: a socket such as Docker's "
            "lets a command act outside the sandbox"
        )
        del net["allowAllUnixSockets"]
    domains = net.setdefault("allowedDomains", [])
    kept = []
    for d in domains:
        reason = _refused_entry(d)
        if reason is None:
            kept.append(d)
        else:
            removed.append(f"sandbox.network.allowedDomains {json.dumps(d)}: {reason}")
    kept.extend(d for d in cs["network"]["allowedDomains"] if d not in kept)
    net["allowedDomains"] = kept
    net["strictAllowlist"] = True

    fs = sb.setdefault("filesystem", {})
    if fs.get("disabled") is True:
        removed.append(
            "sandbox.filesystem.disabled true: it turns off every filesystem "
            "rule written here"
        )
        del fs["disabled"]
    for key in ("denyRead", "denyWrite"):
        lst = fs.setdefault(key, [])
        lst.extend(p for p in cs["filesystem"][key] if p not in lst)

    cred = sb.setdefault("credentials", {})
    for key in ("files", "envVars"):
        lst = cred.setdefault(key, [])
        lst.extend(e for e in cs["credentials"][key] if e not in lst)
    return new, removed


def unknown_keys(settings: dict[str, Any]) -> list[str]:
    """The keys under ``sandbox`` and ``permissions`` that Claude Code's
    documented settings do not have."""
    out: list[str] = []

    def scan(obj: Any, where: str) -> None:
        if not isinstance(obj, dict):
            return
        known = _KNOWN_KEYS[where]
        for k, v in obj.items():
            if k not in known:
                out.append(f"{where}.{k}")
                continue
            sub = f"{where}.{k}"
            if sub in _KNOWN_KEYS:
                scan(v, sub)
            elif f"{sub}[]" in _KNOWN_KEYS and isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        for ik in item:
                            if ik not in _KNOWN_KEYS[f"{sub}[]"]:
                                out.append(f"{sub}[{i}].{ik}")

    for top in ("sandbox", "permissions"):
        scan(settings.get(top), top)
    return out


def _member(obj: Any, key: str) -> dict[str, Any]:
    """``obj[key]`` when both are objects, else an empty one."""
    value = obj.get(key) if isinstance(obj, dict) else None
    return value if isinstance(value, dict) else {}


def _undoing(settings: dict[str, Any]) -> list[str]:
    """The settings that undo what is written here: a proxy port (the
    user's proxy then filters the traffic, not the allowlist), every Unix
    socket allowed, and a ``WebFetch(domain:...)`` allow rule for a host the
    allowlist may not hold. An ``allowRead`` or ``allowWrite`` entry is not
    one: under Claude Code 2.1.332 an entry at or above a path denied here
    did not reopen it."""
    out: list[str] = []
    net = _member(_member(settings, "sandbox"), "network")
    for key in ("httpProxyPort", "socksProxyPort"):
        if key in net:
            out.append(f"sandbox.network.{key} is set: the allowlist stops applying")
    if net.get("allowAllUnixSockets") is True:
        out.append("sandbox.network.allowAllUnixSockets is true")
    allow_rules = _member(settings, "permissions").get("allow")
    for r in allow_rules if isinstance(allow_rules, list) else []:
        reason = _refused_web_fetch(r)
        if reason is not None:
            out.append(f"permissions.allow {json.dumps(r)}: {reason}")
    return out


def verify_settings(settings: dict[str, Any], computed: dict[str, Any]) -> list[str]:
    """What in ``settings`` falls short of the computed settings: a switch
    with another value, a missing entry, ``excludedCommands``, a true
    ``filesystem.disabled``, an allowlist entry that may not be listed, or a
    setting that undoes them (:func:`_undoing`); and any key of the
    computed settings that Claude Code's documented settings do not have
    (Claude Code ignores such a key without a word, so a misspelled safety
    key is unset). Empty when the settings hold all of it. Keys of the
    user's own that are not documented are reported apart
    (:func:`unknown_keys`)."""
    problems: list[str] = []
    sb = _member(settings, "sandbox")
    cs = computed["sandbox"]
    for key in ("enabled", "failIfUnavailable", "allowUnsandboxedCommands"):
        if sb.get(key) is not cs[key]:
            problems.append(f"sandbox.{key} is not {json.dumps(cs[key])}")
    if sb.get("excludedCommands"):
        problems.append("sandbox.excludedCommands is set")
    net = _member(sb, "network")
    if net.get("strictAllowlist") is not True:
        problems.append("sandbox.network.strictAllowlist is not true")
    fs = _member(sb, "filesystem")
    if fs.get("disabled") is True:
        problems.append("sandbox.filesystem.disabled is true")
    cred = _member(sb, "credentials")
    perms = _member(settings, "permissions")

    def missing(have: Any, want: list[Any], where: str) -> None:
        have = have if isinstance(have, list) else []
        for w in want:
            if w not in have:
                problems.append(f"{where} lacks {json.dumps(w)}")

    missing(perms.get("deny"), computed["permissions"]["deny"], "permissions.deny")
    missing(
        net.get("allowedDomains"),
        cs["network"]["allowedDomains"],
        "sandbox.network.allowedDomains",
    )
    for d in net.get("allowedDomains") or []:
        if isinstance(d, str) and _refused_entry(d) is not None:
            problems.append(
                f"sandbox.network.allowedDomains lists {json.dumps(d)}: {_refused_entry(d)}"
            )
    for key in ("denyRead", "denyWrite"):
        missing(fs.get(key), cs["filesystem"][key], f"sandbox.filesystem.{key}")
    for key in ("files", "envVars"):
        missing(cred.get(key), cs["credentials"][key], f"sandbox.credentials.{key}")
    problems += _undoing(settings)
    problems += [
        f"{k}, written here, is not a documented setting"
        for k in unknown_keys(computed)
    ]
    return problems


def _weakening(settings: dict[str, Any]) -> list[str]:
    """Settings left as they are that weaken what is written here."""
    out: list[str] = []
    sb = settings.get("sandbox")
    if not isinstance(sb, dict):
        return out
    net = _member(sb, "network")
    fs = _member(sb, "filesystem")
    for key in ("httpProxyPort", "socksProxyPort"):
        if key in net:
            out.append(
                f"sandbox.network.{key} is set: your own proxy then filters the "
                "traffic, and allowedDomains and strictAllowlist stop applying to it"
            )
    if net.get("allowAllUnixSockets") is True or net.get("allowUnixSockets"):
        out.append(
            "sandbox.network allows Unix sockets: a socket such as Docker's lets "
            "a command act outside the sandbox"
        )
    for key in (
        "enableWeakerNetworkIsolation",
        "enableWeakerNestedSandbox",
        "allowAppleEvents",
        "allowNestedUserNamespaces",
    ):
        if sb.get(key) is True:
            out.append(f"sandbox.{key} is true: it weakens the sandbox")
    if fs.get("allowRead") or fs.get("allowWrite"):
        out.append(
            "sandbox.filesystem.allowRead or allowWrite is set: it widens the "
            "sandbox outside the paths denied here (under Claude Code 2.1.332 an "
            "entry at or above a denied path did not reopen it)"
        )
    perms = settings.get("permissions")
    if isinstance(perms, dict):
        hosts = [
            r
            for r in perms.get("allow") or []
            if isinstance(r, str) and r.startswith("WebFetch(domain:")
        ]
        if hosts:
            out.append(
                "permissions.allow has WebFetch(domain:...) rules, which add their "
                "hosts to the sandbox's allowlist: " + ", ".join(hosts)
            )
    return out


_OVERRIDES = "it overrides user settings (shown under Claude Code 2.1.332)"
_UNTESTED = "whether it overrides user settings has not been tested"


def _project_weakening(project: str) -> list[str]:
    """What the project's own settings files do that may weaken the sandbox
    these settings set, each with whether it was shown to override user
    settings. Only key names are given: the values are the repository's.
    Three project keys are not reported, since from either file they had no
    effect under Claude Code 2.1.332: ``allowUnsandboxedCommands``,
    ``network.strictAllowlist`` and ``network.allowedDomains``."""
    out: list[str] = []
    for name in ("settings.json", "settings.local.json"):
        where = f".claude/{name}"
        path = os.path.join(project, ".claude", name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.loads(f.read())
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            out.append(f"{where} cannot be read, so it was not checked")
            continue
        if not isinstance(data, dict):
            out.append(f"{where} is not a JSON object, so it was not checked")
            continue
        sb = _member(data, "sandbox")
        fs = _member(sb, "filesystem")
        net = _member(sb, "network")
        found: list[tuple[str, str]] = []
        if sb.get("enabled") is False:
            found.append(
                ("sets sandbox.enabled false, which turns the sandbox off", _OVERRIDES)
            )
        if sb.get("excludedCommands"):
            found.append(("excludes commands from the sandbox", _OVERRIDES))
        if fs.get("allowWrite"):
            found.append(("widens the sandbox's write scope (allowWrite)", _OVERRIDES))
        if fs.get("allowRead"):
            found.append(("reopens paths to reading (allowRead)", _UNTESTED))
        if fs.get("disabled") is True:
            found.append(
                (
                    "turns off the sandbox's filesystem rules (filesystem.disabled)",
                    _UNTESTED,
                )
            )
        if sb.get("failIfUnavailable") is False:
            found.append(("sets failIfUnavailable false", _UNTESTED))
        for key in (
            "enableWeakerNetworkIsolation",
            "enableWeakerNestedSandbox",
            "allowAppleEvents",
            "allowNestedUserNamespaces",
        ):
            if sb.get(key) is True:
                found.append((f"sets sandbox.{key} true", _UNTESTED))
        if net.get("allowAllUnixSockets") is True or net.get("allowUnixSockets"):
            found.append(("allows Unix sockets", _UNTESTED))
        for key in ("httpProxyPort", "socksProxyPort"):
            if key in net:
                found.append((f"sets sandbox.network.{key}", _UNTESTED))
        allow = _member(data, "permissions").get("allow")
        if isinstance(allow, list) and any(
            isinstance(r, str) and r.startswith("WebFetch(domain:") for r in allow
        ):
            found.append(("has WebFetch(domain:...) allow rules", _UNTESTED))
        out += [f"{where} {what}: {how}" for what, how in found]
    return out


# --- The audit key file ---------------------------------------------------------


def _key_state(home: str) -> str:
    """``missing``, ``ok``, or what is wrong with the key file, from stat
    alone (its content is never read)."""
    path = audit_key_path(home)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "missing"
    except OSError as e:
        return (
            f"cannot be checked ({e.strerror}); a sandbox that denies it is one cause"
        )
    problems = []
    if not stat.S_ISREG(st.st_mode):
        problems.append("it is not a regular file")
    if st.st_mode & 0o077:
        problems.append(f"its mode is {stat.S_IMODE(st.st_mode):o}, not 600")
    if st.st_nlink != 1:
        problems.append(f"it has {st.st_nlink} links")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        problems.append("another user owns it")
    return "ok" if not problems else "refused by the hooks: " + "; ".join(problems)


def ensure_audit_key(home: str) -> str:
    """Create the audit key file when there is none: 32 random bytes as 64
    hex digits, mode 600, in a directory only the user can use (mode 700).
    An existing file is checked by stat and left as it is. Returns what was
    done; the key is never printed.

    Raises:
        SandboxSettingsError: the file or its directory cannot be made.
    """
    state = _key_state(home)
    if state != "missing":
        return f"the audit key file exists: {state}"
    path = audit_key_path(home)
    directory = os.path.dirname(path)
    try:
        os.makedirs(os.path.dirname(directory), mode=0o700, exist_ok=True)
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            pass
        st = os.lstat(directory)
        if not stat.S_ISDIR(st.st_mode):
            raise SandboxSettingsError(f"{directory} is not a directory")
        if hasattr(os, "getuid") and st.st_uid != os.getuid():
            raise SandboxSettingsError(f"another user owns {directory}")
        os.chmod(directory, 0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            os.write(fd, secrets.token_hex(32).encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        raise SandboxSettingsError(
            f"cannot create the audit key file {path}: {e.strerror}"
        ) from e
    return f"created the audit key file {path} (mode 600)"


# --- Plan and apply -------------------------------------------------------------


@dataclass
class Plan:
    """The change to the user's settings file, as shown and as written."""

    settings_path: str
    old_bytes: bytes | None
    new_text: str
    computed: Computed
    removed: list[str]
    warnings: list[str]
    key_state: str
    key_path: str
    platform_name: str

    @property
    def changes(self) -> bool:
        old = None if self.old_bytes is None else self.old_bytes.decode("utf-8")
        return old != self.new_text

    @property
    def digest(self) -> str:
        h = hashlib.sha256(b"acs-sandbox-settings\0")
        h.update(b"absent" if self.old_bytes is None else b"file:" + self.old_bytes)
        h.update(b"\0" + self.new_text.encode("utf-8") + b"\0")
        h.update(self.key_state.encode("utf-8"))
        return h.hexdigest()

    def diff(self) -> str:
        """The change to the ``permissions`` and ``sandbox`` members, the
        only ones changed, as a unified diff of their JSON. The rest of the
        file is not shown: it can hold credentials (an ``env`` block)."""

        def shown(text: str | None) -> list[str]:
            if text is None:
                return []
            data = parse_settings_text(text)
            part = {k: data[k] for k in ("permissions", "sandbox") if k in data}
            return (json.dumps(part, indent=2, ensure_ascii=False) + "\n").splitlines(
                keepends=True
            )

        old = None if self.old_bytes is None else self.old_bytes.decode("utf-8")
        return "".join(
            difflib.unified_diff(
                shown(old),
                shown(self.new_text),
                fromfile=f"{self.settings_path}: permissions and sandbox, now",
                tofile=f"{self.settings_path}: permissions and sandbox, after",
            )
        )


def _read_settings_file(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise SettingsFileError(f"cannot read {path}: {e.strerror}") from e


def make_plan(
    project: str,
    home: str,
    platform: str,
    plugin_root: str,
    settings_path: str,
    profile: str | None = None,
    extra_domains: tuple[str, ...] | list[str] = (),
) -> Plan:
    """Compute the settings and the change to ``settings_path``.

    Raises:
        UnsupportedPlatformError: the platform has no sandbox.
        SettingsFileError: the settings file cannot be read as Claude Code
            reads it; it is left as it is.
        SandboxSettingsError: the settings cannot be computed.
    """
    name = _platform_name(platform)
    destinations = read_profile_destinations(profile) if profile else None
    computed = compute_settings(
        project,
        home,
        platform,
        plugin_root,
        destinations,
        extra_domains,
        profile_given=profile is not None,
    )
    old = _read_settings_file(settings_path)
    if old is None:
        current: dict[str, Any] = {}
    else:
        try:
            text = old.decode("utf-8")
        except UnicodeDecodeError as e:
            raise SettingsFileError(f"{settings_path} is not UTF-8") from e
        try:
            current = parse_settings_text(text)
        except SettingsFileError as e:
            raise SettingsFileError(
                f"{settings_path} is left as it is: {e}. Fix it and run this again."
            ) from e
    merged, removed = merge_settings(current, computed.settings)
    new_text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if old is not None and parse_settings_text(old.decode("utf-8")) == merged:
        new_text = old.decode("utf-8")
    warnings = _weakening(merged) + _project_weakening(project)
    if name == "Linux":
        missing = [t for t in ("bwrap", "socat") if shutil.which(t) is None]
        if missing:
            warnings.append(
                f"{' and '.join(missing)} not found: the sandbox needs bubblewrap and "
                "socat on Linux, and with failIfUnavailable Claude Code will not "
                "start until they are installed"
            )
    key_dir = os.path.realpath(os.path.dirname(audit_key_path(home)))
    physical_project = os.path.realpath(project)
    if key_dir == physical_project or key_dir.startswith(
        physical_project.rstrip("/") + "/"
    ):
        warnings.append(
            f"the audit key's directory {key_dir} is inside the project, which "
            "sandboxed commands may write: the hooks do not use a key file there"
        )
    return Plan(
        settings_path,
        old,
        new_text,
        computed,
        removed,
        warnings,
        _key_state(home),
        audit_key_path(home),
        name,
    )


def apply_plan(plan: Plan, digest: str, home: str) -> list[str]:
    """Write the plan's settings file when ``digest`` is the plan's, create
    the audit key file when there is none, then read the file back and check
    it. Returns what was done; raises with what fell short.

    Raises:
        SandboxSettingsError: the digest differs (the file or the settings
            changed since they were shown), the file changed while it was
            written, a file cannot be written, or the read-back check failed.
    """
    if not secrets.compare_digest(digest, plan.digest):
        raise SandboxSettingsError(
            "the settings or the file changed since the plan was shown (the "
            "digest differs): show the plan again and confirm that one"
        )
    done: list[str] = [ensure_audit_key(home)]
    target = os.path.realpath(plan.settings_path)
    if plan.changes:
        directory = os.path.dirname(target)
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".settings.json.", dir=directory)
        except OSError as e:
            raise SandboxSettingsError(_write_refusal(target, e)) from e
        try:
            try:
                mode = stat.S_IMODE(os.stat(target).st_mode)
            except FileNotFoundError:
                mode = 0o600
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(plan.new_text)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, mode)
            if _read_settings_file(target) != plan.old_bytes:
                raise SandboxSettingsError(
                    f"{target} changed while it was being written; nothing was "
                    "written: show the plan again"
                )
            os.replace(tmp, target)
        except OSError as e:
            raise SandboxSettingsError(_write_refusal(target, e)) from e
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        done.append(f"wrote {target}")
    else:
        done.append(f"{target} already holds these settings; it was not written")
    back = _read_settings_file(target)
    if back is None:
        raise SandboxSettingsError(f"{target} is not there after it was written")
    problems = verify_settings(
        parse_settings_text(back.decode("utf-8")), plan.computed.settings
    )
    if problems:
        raise SandboxSettingsError(
            "read back, the settings fall short:\n  " + "\n  ".join(done + problems)
        )
    done.append("read back: every key written is a documented setting with its value")
    done += [
        f"note: {k} is not a documented setting, so Claude Code ignores it"
        for k in unknown_keys(parse_settings_text(back.decode("utf-8")))
    ]
    return done


def _write_refusal(target: str, e: OSError) -> str:
    # The command starts the script under env -i, so no variable says whether
    # it runs in the sandbox; a refusal of permission is the sign.
    where = (
        " Inside Claude Code, the sandbox keeps a command from writing there "
        "once it is on: run the same command from a terminal outside Claude Code."
        if e.errno in (errno.EPERM, errno.EACCES)
        else ""
    )
    return f"cannot write {target}: {e.strerror}.{where}"


# --- Command line ---------------------------------------------------------------


def _format_plan(plan: Plan, command: str, interpreter: str = "") -> str:
    """The plan as shown. Every string the repository or a profile supplies
    is printed as JSON, so none can add a line; the command to write the
    settings is the last line."""
    c = plan.computed
    out = [
        f"Settings file: {plan.settings_path}",
        f"Platform: {plan.platform_name}",
        *([f"Python: {interpreter}"] if interpreter else []),
        f"Domain profile: {c.profile_state}",
        "",
        "Hosts sandboxed commands may reach (sandbox.network.allowedDomains, "
        "with strictAllowlist true; every other host is refused):",
    ]
    out += [f"  {d}  <- {why}" for d, why in c.domains] or [
        "  none: sandboxed commands reach no host (give hosts with --allow-domain)"
    ]
    if c.skipped:
        out.append("Destinations of the profile not listed:")
        out += [f"  {json.dumps(p)}: {why}" for p, why in c.skipped]
    if plan.removed:
        out.append("Removed from your settings:")
        out += [f"  {r}" for r in plan.removed]
    if plan.warnings:
        out.append(
            "Left as they are, and weakening or possibly weakening these settings:"
        )
        out += [f"  {w}" for w in plan.warnings]
    unknown = unknown_keys(parse_settings_text(plan.new_text))
    if unknown:
        out.append("Keys Claude Code does not document, so it ignores them:")
        out += [f"  {k}" for k in unknown]
    key = plan.key_state
    out.append(
        "Audit key file: "
        + (
            f"will be created at {plan.key_path} (mode 600, in a mode 700 directory)"
            if key == "missing"
            else key
        )
    )
    out.append("")
    if plan.changes:
        out.append(
            "The change (every other setting is left as it is; the file is "
            "written with two-space indentation):"
        )
        out.append(plan.diff().rstrip("\n"))
    else:
        out.append("The settings file already holds these settings: nothing to change.")
    out.append("")
    out += list(NOTES)
    out += [
        "",
        f"Digest: {plan.digest}",
        f"To write it: {command} --digest {plan.digest}",
    ]
    return "\n".join(out)


# Variables a project's settings may not set in their ``env`` block: Claude
# Code passes that block to every Bash call, so it would choose the home
# directory (and so the paths denied) or the settings file written.
_PROJECT_ENV_REFUSED = ("HOME", "CLAUDE_CONFIG_DIR")


def _check_project_env(project: str) -> None:
    """Refuse when the project's ``.claude/settings.json`` or
    ``.claude/settings.local.json`` sets ``HOME`` or ``CLAUDE_CONFIG_DIR``
    in its ``env`` block. A file Claude Code cannot read either is left to
    :func:`_project_weakening`.

    Raises:
        SandboxSettingsError: one of them sets such a variable.
    """
    for name in ("settings.json", "settings.local.json"):
        try:
            with open(os.path.join(project, ".claude", name), encoding="utf-8") as f:
                data = json.loads(f.read())
        except (OSError, ValueError):
            continue
        env = _member(data, "env")
        named = [v for v in _PROJECT_ENV_REFUSED if v in env]
        if named:
            raise SandboxSettingsError(
                f".claude/{name} sets {' and '.join(named)} for every command "
                "Claude Code runs, which would move the settings written or the "
                "paths denied: nothing is written. Remove it from that file, or "
                "run this from a terminal outside Claude Code with --project"
            )


def _check_interpreter(project: str) -> str:
    """The physical path of the Python running this, after a check that the
    repository cannot have chosen it: not inside the project (the
    interpreter, or the environment it runs in, whose ``.pth`` files run
    code at startup), owned by root or the user, and not writable by others.

    Raises:
        SandboxSettingsError: it fails one of these checks.
    """
    exe = sys.executable
    if not exe:
        raise SandboxSettingsError("the path of the running Python is unknown")
    real = os.path.realpath(exe)
    roots = {os.path.abspath(project), os.path.realpath(project)}
    for p in {
        os.path.abspath(exe),
        real,
        os.path.abspath(sys.prefix),
        os.path.realpath(sys.prefix),
    }:
        for r in roots:
            if p == r or p.startswith(r.rstrip("/") + "/"):
                raise SandboxSettingsError(
                    f"the Python running this ({p}) is inside the project, which "
                    "the repository controls: run it with a python3 from outside "
                    "the project"
                )
    uid = os.getuid() if hasattr(os, "getuid") else None
    for p in (real, os.path.dirname(real)):
        try:
            st = os.stat(p)
        except OSError as e:
            raise SandboxSettingsError(f"cannot check {p}: {e.strerror}") from e
        if uid is not None and st.st_uid not in (0, uid):
            raise SandboxSettingsError(
                f"the Python running this is in {p}, which another user owns"
            )
        if st.st_mode & stat.S_IWOTH:
            raise SandboxSettingsError(
                f"the Python running this is in {p}, which every user can write"
            )
    return real


def main(argv: list[str] | None = None) -> int:
    """The command line (see the module's description). Exit status 0 on
    success, 1 when the settings fall short (``check``, or the read-back of
    ``apply``), 2 when nothing could be computed or written, 3 when the
    platform has no sandbox."""
    parser = argparse.ArgumentParser(
        prog="sandbox_settings.py",
        description="Compute the strict sandbox settings for a project and "
        "merge them into the user's Claude Code settings.",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="plan",
        choices=("plan", "apply", "settings", "check"),
    )
    parser.add_argument(
        "--project",
        help="the project directory (default: "
        "CLAUDE_PROJECT_DIR, else the current directory)",
    )
    parser.add_argument(
        "--profile",
        help="a domain profile file (YAML or JSON) "
        "whose allowed_destinations the allowlist follows",
    )
    parser.add_argument(
        "--allow-domain",
        action="append",
        default=[],
        metavar="HOST",
        help="another host to allow (repeatable)",
    )
    parser.add_argument("--digest", help="apply: the digest the plan printed")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        _platform_name(sys.platform)
        _check_python()
        home = os.path.expanduser("~")
        if not os.path.isabs(home):
            raise SandboxSettingsError(
                "the home directory is unknown (HOME is not set)"
            )
        project = os.path.abspath(
            args.project or os.environ.get("CLAUDE_PROJECT_DIR") or "."
        )
        if not os.path.isdir(project):
            raise SandboxSettingsError(f"{project} is not a directory")
        interpreter = _check_interpreter(project)
        _check_project_env(project)
        if args.profile is not None and any(
            ord(c) < 0x20 or ord(c) == 0x7F for c in args.profile
        ):
            raise SandboxSettingsError("the --profile path holds a control character")
        plugin_root = str(Path(__file__).resolve().parent.parent)
        settings_path = user_settings_path(home)
        if args.action == "settings":
            computed = compute_settings(
                project,
                home,
                sys.platform,
                plugin_root,
                read_profile_destinations(args.profile) if args.profile else None,
                args.allow_domain,
                profile_given=args.profile is not None,
            )
            print(json.dumps(computed.settings, indent=2))
            return 0
        plan = make_plan(
            project,
            home,
            sys.platform,
            plugin_root,
            settings_path,
            args.profile,
            args.allow_domain,
        )
        config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
        command = " ".join(
            shlex.quote(a)
            for a in [
                *RUN_PREFIX,
                *(
                    [f"CLAUDE_CONFIG_DIR={os.path.abspath(config_dir)}"]
                    if config_dir
                    else []
                ),
                INTERPRETER,
                "-I",
                str(Path(__file__).resolve()),
                "apply",
                "--project",
                project,
                *(["--profile", os.path.abspath(args.profile)] if args.profile else []),
                *[x for d in args.allow_domain for x in ("--allow-domain", d)],
            ]
        )
        if args.action == "check":
            current = (
                parse_settings_text(plan.old_bytes.decode("utf-8"))
                if plan.old_bytes
                else {}
            )
            problems = verify_settings(current, plan.computed.settings)
            problems += _project_weakening(project)
            if plan.key_state != "ok":
                problems.append(f"audit key file: {plan.key_state}")
            for p in problems:
                print(p)
            for k in unknown_keys(current):
                print(
                    f"note: {k} is not a documented setting, so Claude Code ignores it"
                )
            if not problems:
                print(
                    f"{settings_path} holds these settings, and the audit key file is in place."
                )
            return 1 if problems else 0
        if args.action == "plan":
            print(_format_plan(plan, command, interpreter))
            return 0
        digest = args.digest
        if digest is None:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise SandboxSettingsError(
                    "apply needs --digest with the digest the plan printed"
                )
            print(_format_plan(plan, command, interpreter))
            answer = input("\nWrite these settings? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("Nothing was written.")
                return 0
            digest = plan.digest
        for line in apply_plan(plan, digest, home):
            print(line)
        return 0
    except UnsupportedPlatformError as e:
        print(f"sandbox_settings: {e}", file=sys.stderr)
        return 3
    except SandboxSettingsError as e:
        print(f"sandbox_settings: {e}", file=sys.stderr)
        return 1 if str(e).startswith("read back") else 2


if __name__ == "__main__":
    sys.exit(main())
