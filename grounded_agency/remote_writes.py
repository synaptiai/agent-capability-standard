"""Typed remote writes: the plugin's MCP server for pushes, pull requests, releases and issues.

Under the strict sandbox (hooks/README.md), the agent's commands run in
Claude Code's sandbox with git's and gh's credentials denied to them: the
keychains, ``~/.ssh``, gh's ``hosts.yml`` and the token variables. A plugin's
MCP server runs outside that sandbox, with the user's own gh login and
network, so remote writes go through the tools this server offers, one
action per call:

==================  ==========================================================
``push``            push one local branch to the same branch of the origin
``tag_push``        push one local tag to the origin (never replaces a tag)
``pr_create``       open one pull request
``pr_merge``        merge one pull request by number, with a fixed method
``release_create``  create one release for a tag that already exists there
``issue_create``    open one issue
``issue_assign``    add one assignee to one issue
==================  ==========================================================

Claude Code names them ``mcp__plugin_agent-capability-standard_remote__<tool>``.
Each is bound (STANDARD 1.2.0 section 5.18.1) as a gated ``mutate``
(:func:`binding_records`): the plugin's pre-tool-use hook asks for a
checkpoint and a person's approval for every call, and the approval request
names the call's target.

The server is trusted code that runs unconfined, so it treats every input
as untrusted:

- **No repository field.** The target is the origin a person recorded with
  ``record`` (below), in ``~/.config/acs/remotes.json``, in a directory the
  strict sandbox denies writes to, for the agent's commands and the file
  tools; the pre-tool-use hook also refuses any call that names the record.
  The repository's own ``.git/config``, which the agent can write, never
  chooses the target. With no record for the project, every tool
  refuses. A local origin (a path) must lie outside the project and the
  temporary directories, since the receiving side of a local push runs
  that repository's own hooks and configuration.
- **No shell.** git and gh are started by argument list. Every option takes
  its value in the same argument (``--title=...``), and no value can start
  an option.
- **No configuration of the repository.** git pushes from an empty bare
  repository this server makes for the one call, which reads the project's
  objects through ``objects/info/alternates``; so no setting of the
  project's ``.git/config`` (``url.*.insteadOf``, ``core.sshCommand``,
  ``credential.helper``, ``remote.*.pushurl``) and none of its hooks take
  part in a push. git also runs with ``core.hooksPath=/dev/null``,
  ``core.fsmonitor=false`` and only the https, ssh and file protocols. gh
  runs in an empty directory, with ``--repo`` from the record.
- **Strict arguments.** Branch and tag names follow ``git check-ref-format``
  (checked here and by git), numbers are integers, methods come from a fixed
  set, and a member the tool does not declare is refused.
- **A known environment.** git and gh are the programs the record names,
  found on the person's PATH when they recorded the origin; the server's own
  PATH is not searched. A program that now lies in the project, a temporary
  directory or Claude Code's plugins directory is refused. The children's
  PATH holds the directories of those two programs and the system's
  ``/usr/bin:/bin:/usr/sbin:/sbin``. The home directory comes from the
  password database, not from ``HOME``, and a project directory that holds
  the home directory is refused. The children get only the variables they
  need (no ``GIT_*``, ``GH_REPO``, ``GH_HOST``, ``DEVELOPER_DIR`` or
  ``SDKROOT``), and each call works in a new directory under
  ``~/.config/acs/work/``, not in the environment's ``TMPDIR``.

The module uses the standard library alone and the syntax of Python 3.9, so
it runs from a plugin checkout under the system's ``python3``, started
with ``DEVELOPER_DIR``, ``TOOLCHAINS`` and ``SDKROOT`` removed (on macOS
``/usr/bin/python3`` is a shim that runs the interpreter those variables
choose)::

    /usr/bin/env -u DEVELOPER_DIR -u TOOLCHAINS -u SDKROOT /usr/bin/python3 -I <plugin>/grounded_agency/remote_writes.py record [--project DIR]
    /usr/bin/env ... /usr/bin/python3 -I <plugin>/grounded_agency/remote_writes.py serve
    /usr/bin/env ... /usr/bin/python3 -I <plugin>/grounded_agency/remote_writes.py bindings [--prefix P]

``record`` shows the project's ``remote.origin.url`` (or ``--url``) and the
git and gh it found on the person's PATH and, once the person agrees,
records them; a person runs it in a terminal outside
Claude Code, since the sandbox and the deny rules keep the agent from
writing the record. ``serve`` is the MCP server the plugin's ``plugin.json``
starts. ``bindings`` prints the tool binding records as JSON.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

__all__ = [
    "PLUGIN_TOOL_PREFIX",
    "TOOLS",
    "Context",
    "RemoteWriteError",
    "binding_records",
    "call_tool",
    "main",
    "parse_origin",
    "validate_ref_name",
]

SERVER_NAME = "remote"
PLUGIN_NAME = "agent-capability-standard"
# The name Claude Code gives a plugin MCP server's tool:
# mcp__plugin_<plugin>_<server>__<tool>.
PLUGIN_TOOL_PREFIX = f"mcp__plugin_{PLUGIN_NAME}_{SERVER_NAME}__"
SERVER_VERSION = "1.0.0"
ONTOLOGY_VERSION = "2.2.0"
STANDARD_VERSION = "1.2.0"

# grounded_agency.utils.git.SAFE_GIT_OPTIONS, repeated here so that this file
# imports nothing from the package (a test keeps the two equal).
_SAFE_GIT_OPTIONS: tuple[str, ...] = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
)
# The transports a push may use: no ext::, fd:: or other helper.
_PROTOCOL_OPTIONS: tuple[str, ...] = (
    "-c",
    "protocol.allow=never",
    "-c",
    "protocol.https.allow=always",
    "-c",
    "protocol.ssh.allow=always",
    "-c",
    "protocol.file.allow=always",
)
# git push pushes the one refspec given: no tag it follows, no submodule,
# and no pre-push hook (core.hooksPath=/dev/null stops it as well).
_PUSH_OPTIONS: tuple[str, ...] = (
    "--porcelain",
    "--no-follow-tags",
    "--recurse-submodules=no",
    "--no-verify",
)
_GIT_TIMEOUT = 10.0
_REMOTE_TIMEOUT = 120.0
_OUTPUT_LIMIT = 4000

RECORD_VERSION = 1

_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


class RemoteWriteError(Exception):
    """A call or a record that is refused, with the reason a person reads."""


# ---------------------------------------------------------------------------
# Argument validation


# The characters of a branch or tag name. The pre-tool-use hook shows a
# value in an approval request only when it matches this class (a test keeps
# the two equal), and refuses a call with a value of this class that looks
# like a credential, which it would not show; so every target the server
# acts on is shown.
REF_CHARACTERS = r"[A-Za-z0-9._/@+-]+"


def validate_ref_name(name: Any, what: str) -> str:
    """``name`` when it is a branch or tag name ``git check-ref-format``
    accepts under ``refs/heads/`` or ``refs/tags/``, kept to 1 to 200 ASCII
    letters, digits and ``. _ / @ + -`` (:data:`REF_CHARACTERS`, the values the
    pre-tool-use hook shows in an approval request), not starting with ``-``
    and not ``HEAD``; else RemoteWriteError. git checks it again
    (:func:`_git_checks_ref`)."""
    if not isinstance(name, str):
        raise RemoteWriteError(f"{what} must be a string")
    if not 1 <= len(name) <= 200:
        raise RemoteWriteError(f"{what} must be 1 to 200 characters")
    if not re.fullmatch(REF_CHARACTERS, name):
        raise RemoteWriteError(
            f"{what} may hold only ASCII letters, digits and . _ / @ + -"
        )
    if name.startswith("-"):
        raise RemoteWriteError(f"{what} may not start with '-'")
    if name == "HEAD" or name == "@":
        raise RemoteWriteError(f"{what} may not be {name!r}")
    if ".." in name or "@{" in name or "//" in name:
        raise RemoteWriteError(f"{what} may not hold '..', '@{{' or '//'")
    if name.startswith("/") or name.endswith("/") or name.endswith("."):
        raise RemoteWriteError(f"{what} may not start or end with '/' or end with '.'")
    for part in name.split("/"):
        if part.startswith(".") or part.endswith(".lock"):
            raise RemoteWriteError(
                f"{what}: no component may start with '.' or end with '.lock'"
            )
    return name


def _integer(value: Any, what: str) -> int:
    # bool is an int in Python: refused, as is a float such as 3.0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise RemoteWriteError(f"{what} must be an integer")
    if not 1 <= value <= 2_147_483_647:
        raise RemoteWriteError(f"{what} must be from 1 to 2147483647")
    return value


def _text(value: Any, what: str, limit: int, line: bool) -> str:
    if not isinstance(value, str):
        raise RemoteWriteError(f"{what} must be a string")
    if not value.strip():
        raise RemoteWriteError(f"{what} may not be empty")
    if len(value) > limit:
        raise RemoteWriteError(f"{what} may be at most {limit} characters")
    allowed_controls = "" if line else "\n\t"
    if any((ord(c) < 32 and c not in allowed_controls) or ord(c) == 127 for c in value):
        raise RemoteWriteError(
            f"{what} may not hold control characters"
            + ("" if line else " other than newline and tab")
        )
    return value


def _object_id(value: Any, what: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", value
    ):
        raise RemoteWriteError(
            f"{what} must be a full object id: 40 or 64 lowercase hexadecimal digits"
        )
    return value


def _flag(value: Any, what: str) -> bool:
    if not isinstance(value, bool):
        raise RemoteWriteError(f"{what} must be true or false")
    return value


def _login(value: Any, what: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}", value
    ):
        raise RemoteWriteError(
            f"{what} must be a GitHub login: 1 to 39 letters, digits or single "
            "hyphens, not starting or ending with a hyphen"
        )
    return value


MERGE_METHODS = ("merge", "squash", "rebase")


def _method(value: Any, what: str) -> str:
    if not isinstance(value, str) or value not in MERGE_METHODS:
        raise RemoteWriteError(f"{what} must be one of {', '.join(MERGE_METHODS)}")
    return value


# ---------------------------------------------------------------------------
# Tools


@dataclass(frozen=True)
class Field:
    """One argument: its JSON Schema, whether it is required, and the
    validator that returns its value or raises RemoteWriteError."""

    schema: dict[str, Any]
    required: bool
    check: Callable[[Any, str], Any]


@dataclass(frozen=True)
class Tool:
    """One tool: its name, what it does, its domain id and its arguments."""

    name: str
    description: str
    domain: str
    fields: dict[str, Field]

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {k: f.schema for k, f in self.fields.items()},
            "required": [k for k, f in self.fields.items() if f.required],
            "additionalProperties": False,
        }


_REF_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 200}


def _ref_field(description: str) -> Field:
    return Field({**_REF_SCHEMA, "description": description}, True, validate_ref_name)


def _number_field(description: str) -> Field:
    return Field(
        {
            "type": "integer",
            "minimum": 1,
            "maximum": 2147483647,
            "description": description,
        },
        True,
        _integer,
    )


def _title_field(description: str) -> Field:
    return Field(
        {
            "type": "string",
            "minLength": 1,
            "maxLength": 256,
            "description": description,
        },
        True,
        lambda v, w: _text(v, w, 256, True),
    )


def _body_field(description: str) -> Field:
    return Field(
        {
            "type": "string",
            "minLength": 1,
            "maxLength": 65536,
            "description": description,
        },
        True,
        lambda v, w: _text(v, w, 65536, False),
    )


def _bool_field(description: str) -> Field:
    return Field({"type": "boolean", "description": description}, False, _flag)


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "push",
            "Push one local branch to the branch of the same name on the origin "
            "recorded for this project. Without force_with_lease the push must "
            "fast-forward; with it, the remote branch is replaced only while it "
            "still points at that object id.",
            "git.branch",
            {
                "branch": _ref_field("The local branch to push (refs/heads/<branch>)."),
                "force_with_lease": Field(
                    {
                        "type": "string",
                        "pattern": "^([0-9a-f]{40}|[0-9a-f]{64})$",
                        "description": "Replace the remote branch only while it points "
                        "at this full object id (a forced push with a lease).",
                    },
                    False,
                    _object_id,
                ),
            },
        ),
        Tool(
            "tag_push",
            "Push one local tag to the origin recorded for this project. A tag "
            "that already exists there is never replaced.",
            "git.tag",
            {"tag": _ref_field("The local tag to push (refs/tags/<tag>).")},
        ),
        Tool(
            "pr_create",
            "Open one pull request on the origin's GitHub repository, from a "
            "branch already pushed there.",
            "github.pull_request",
            {
                "head": _ref_field("The branch that holds the changes."),
                "base": _ref_field("The branch to merge into."),
                "title": _title_field("The pull request's title."),
                "body": _body_field("The pull request's description."),
                "draft": _bool_field("Open it as a draft."),
            },
        ),
        Tool(
            "pr_merge",
            "Merge one pull request of the origin's GitHub repository.",
            "github.pull_request",
            {
                "number": _number_field("The pull request's number."),
                "method": Field(
                    {
                        "type": "string",
                        "enum": list(MERGE_METHODS),
                        "description": "How to merge: a merge commit, a squash or a rebase.",
                    },
                    True,
                    _method,
                ),
                "match_head_commit": Field(
                    {
                        "type": "string",
                        "pattern": "^([0-9a-f]{40}|[0-9a-f]{64})$",
                        "description": "Merge only while the pull request's head is "
                        "this full commit id.",
                    },
                    False,
                    _object_id,
                ),
            },
        ),
        Tool(
            "release_create",
            "Create one release on the origin's GitHub repository for a tag that "
            "already exists there (push it first with tag_push).",
            "github.release",
            {
                "tag": _ref_field("The existing tag the release is for."),
                "title": _title_field("The release's title."),
                "notes": _body_field("The release notes."),
                "draft": _bool_field("Create it as a draft."),
                "prerelease": _bool_field("Mark it as a pre-release."),
            },
        ),
        Tool(
            "issue_create",
            "Open one issue on the origin's GitHub repository.",
            "github.issue",
            {
                "title": _title_field("The issue's title."),
                "body": _body_field("The issue's description."),
            },
        ),
        Tool(
            "issue_assign",
            "Add one assignee to one issue of the origin's GitHub repository.",
            "github.issue",
            {
                "number": _number_field("The issue's number."),
                "assignee": Field(
                    {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 39,
                        "description": "The GitHub login to assign.",
                    },
                    True,
                    _login,
                ),
            },
        ),
    )
}


def binding_records(prefix: str = PLUGIN_TOOL_PREFIX) -> list[dict[str, Any]]:
    """The tool binding records (STANDARD 1.2.0 section 5.18.1) of the
    server's tools, named ``<prefix><tool>``: Claude Code's plugin prefix by
    default; a host that offers the server under another name passes its
    own prefix (``mcp__remote__`` for a server it calls ``remote``).

    Each is a ``mutate`` (section 5.18.3: a pushed branch, a pull request,
    a release and an issue are resources that can be read back), with the
    ontology's flags: a checkpoint and a person's approval for every call.
    None performs ``send``: the target is fixed by the record, so no
    argument holds a destination."""
    return [
        {
            "tool": prefix + t.name,
            "ontology": ONTOLOGY_VERSION,
            "standard": STANDARD_VERSION,
            "capability": "mutate",
            "domain": t.domain,
            "flags": {
                "risk": "high",
                "mutation": True,
                "requires_checkpoint": True,
                "requires_approval": True,
            },
        }
        for t in TOOLS.values()
    ]


def validate_arguments(tool: Tool, arguments: Any) -> dict[str, Any]:
    """The call's arguments, each checked; RemoteWriteError for a member
    the tool does not declare, a missing required one or a bad value."""
    if not isinstance(arguments, dict):
        raise RemoteWriteError("the arguments must be an object")
    unknown = sorted(k for k in arguments if k not in tool.fields)
    if unknown:
        shown = ", ".join(repr(k)[:60] for k in unknown[:5])
        raise RemoteWriteError(f"{tool.name} takes no argument {shown}")
    values: dict[str, Any] = {}
    for key, f in tool.fields.items():
        if key not in arguments:
            if f.required:
                raise RemoteWriteError(f"{tool.name} needs {key}")
            continue
        values[key] = f.check(arguments[key], key)
    return values


# ---------------------------------------------------------------------------
# The origin record


def parse_origin(url: Any) -> tuple[str, str | None]:
    """``(url, github)`` for a URL a push may go to, where ``github`` is
    ``HOST/OWNER/REPO`` for gh's ``--repo`` when the URL names a repository
    that way (None for a local path); RemoteWriteError for any other URL.

    Accepted: ``https://host/owner/repo[.git]``,
    ``ssh://[user@]host[:port]/owner/repo[.git]``,
    ``user@host:owner/repo[.git]``, and an absolute local path or
    ``file:///path`` (a local remote). Refused: a URL holding a password
    (``user:secret@``), a transport helper (``ext::``), plain http, an
    option (``-...``), control characters and spaces."""
    if not isinstance(url, str) or not 1 <= len(url) <= 1024:
        raise RemoteWriteError(
            "the origin URL must be a string of 1 to 1024 characters"
        )
    if not re.fullmatch(r"[\x21-\x7e]+", url):
        raise RemoteWriteError(
            "the origin URL may hold only printable ASCII characters other than space"
        )
    if url.startswith("-") or "::" in url:
        raise RemoteWriteError(
            "the origin URL may not start with '-' or name a transport helper ('::')"
        )
    name = r"[A-Za-z0-9._-]+"
    host = r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?"
    m = re.fullmatch(rf"https://({host})(?::[0-9]{{1,5}})?/({name})/({name})/?", url)
    if m is None:
        m = re.fullmatch(
            rf"ssh://(?:[A-Za-z0-9._-]+@)?({host})(?::[0-9]{{1,5}})?/({name})/({name})/?",
            url,
        )
    if m is None:
        m = re.fullmatch(rf"[A-Za-z0-9._-]+@({host}):({name})/({name})/?", url)
    if m is not None:
        owner, repo = m.group(2), m.group(3)
        if repo.endswith(".git"):
            repo = repo[: -len(".git")]
        for part in (owner, repo):
            if part in (".", "..") or part.startswith("-") or not part:
                raise RemoteWriteError(
                    "the origin URL's owner or repository name is not valid"
                )
        return url, f"{m.group(1).lower()}/{owner}/{repo}"
    if "@" in url.split("/")[2 if url.startswith(("https://", "ssh://")) else 0]:
        raise RemoteWriteError("the origin URL may not hold a user name and password")
    path = url[len("file://") :] if url.startswith("file://") else url
    if path.startswith("/") and "/../" not in path + "/" and "/./" not in path + "/":
        if not re.fullmatch(r"/[A-Za-z0-9._/+-]*", path):
            raise RemoteWriteError(
                "a local origin path may hold only letters, digits and . _ / + -"
            )
        return url, None
    raise RemoteWriteError(
        "the origin URL must be https://host/owner/repo, ssh://host/owner/repo, "
        "user@host:owner/repo or an absolute local path"
    )


def _home_directory() -> str:
    """The user's home directory as the password database gives it: not
    HOME, which a project's settings can set for every process Claude Code
    starts."""
    import pwd

    return pwd.getpwuid(os.getuid()).pw_dir


def record_path(home: str) -> str:
    """The origin record: ``~/.config/acs/remotes.json``, in the directory
    of the audit key, which the strict sandbox denies to the agent's
    commands and to the file tools for writing."""
    return os.path.join(home, ".config", "acs", "remotes.json")


# An entry of the record: the project's directory and common git directory,
# the origin's URL, the GitHub repository gh acts on (None: from the URL),
# the absolute paths of git and gh (None: no gh) and when it was recorded.
_ENTRY_KEYS = {"project", "git_dir", "url", "github", "git", "gh", "recorded_at"}


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise RemoteWriteError(f"the origin record repeats the key {k!r}")
        out[k] = v
    return out


def read_records(home: str) -> list[dict[str, Any]]:
    """The entries of the origin record; [] when there is no record file.
    RemoteWriteError when the file is not a regular file of this user that
    only this user can write, or not the record's form."""
    path = record_path(home)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return []
    except OSError as e:
        raise RemoteWriteError(
            f"cannot read the origin record {path}: {e.strerror}"
        ) from e
    if not stat.S_ISREG(st.st_mode):
        raise RemoteWriteError(f"the origin record {path} is not a regular file")
    if st.st_uid != os.getuid() or st.st_mode & 0o022:
        raise RemoteWriteError(
            f"the origin record {path} must belong to this user and be writable by no one else"
        )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.loads(f.read(1_000_001), object_pairs_hook=_reject_duplicates)
    except (OSError, ValueError) as e:
        raise RemoteWriteError(
            f"the origin record {path} is not valid JSON: {e}"
        ) from e
    if (
        not isinstance(data, dict)
        or set(data) != {"version", "repositories"}
        or data["version"] != RECORD_VERSION
        or not isinstance(data["repositories"], list)
    ):
        raise RemoteWriteError(
            f"the origin record {path} is not of version {RECORD_VERSION}'s form"
        )
    entries = []
    for entry in data["repositories"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != _ENTRY_KEYS
            or not all(
                isinstance(entry[k], str)
                for k in ("project", "git_dir", "url", "git", "recorded_at")
            )
            or not all(
                entry[k] is None or isinstance(entry[k], str) for k in ("github", "gh")
            )
            or not all(
                os.path.isabs(entry[k])
                for k in ("project", "git_dir", "git", "gh")
                if entry[k] is not None
            )
        ):
            raise RemoteWriteError(
                f"the origin record {path} holds an entry of another form"
            )
        url, derived = parse_origin(entry["url"])
        if entry["github"] is not None and not re.fullmatch(
            r"[A-Za-z0-9.-]+/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", entry["github"]
        ):
            raise RemoteWriteError(
                f"the origin record {path} holds a github value of another form"
            )
        entries.append(entry)
    return entries


def write_record(home: str, entry: dict[str, Any]) -> str:
    """Add ``entry`` to the origin record, replacing the entry for the same
    project, and return the record's path. The directory is created with
    mode 700 and the file written with mode 600, through a rename."""
    path = record_path(home)
    entries = [e for e in read_records(home) if e["project"] != entry["project"]]
    entries.append(entry)
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".remotes.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": RECORD_VERSION, "repositories": entries}, f, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


# ---------------------------------------------------------------------------
# The context a call runs in


def _temporary_roots() -> tuple[str, ...]:
    """The system's temporary directories, which a sandboxed command can
    write."""
    roots = {"/tmp", "/var/tmp", "/var/folders", tempfile.gettempdir()}
    return tuple(sorted({os.path.realpath(r) for r in roots}))


def _plugin_roots(home: str) -> tuple[str, ...]:
    """Claude Code's plugins directories (``~/.claude/plugins``, and
    ``$CLAUDE_CONFIG_DIR/plugins`` when that is set): in a session, PATH can
    begin with another plugin's shims there, which would run with the
    user's gh login in place of git and gh."""
    roots = {os.path.join(home, ".claude", "plugins")}
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    if config and os.path.isabs(config):
        roots.add(os.path.join(config, "plugins"))
    return tuple(sorted({os.path.realpath(r) for r in roots}))


def untrusted_roots(project: str, home: str) -> tuple[str, ...]:
    """The directories no program, PATH entry or local origin may lie in:
    the project's (a sandboxed command writes there), the temporary
    directories and Claude Code's plugins directories."""
    return (
        os.path.realpath(project),
        *_temporary_roots(),
        *_plugin_roots(home),
    )


@dataclass(frozen=True)
class Context:
    """Where a call runs: the project directory (the server's working
    directory, where Claude Code starts it), the user's home directory (from
    the password database), the PATH the ``record`` command finds git and gh
    on (the person's, in a terminal; the server does not search its own) and
    the directories no program or local origin may lie in
    (:func:`untrusted_roots`)."""

    project: str
    home: str
    path: str
    untrusted: tuple[str, ...] = ()

    @classmethod
    def from_process(cls, home: str | None = None) -> Context:
        project = os.getcwd()
        home = _home_directory() if home is None else home
        return cls(
            project,
            home,
            os.environ.get("PATH", ""),
            untrusted_roots(project, home),
        )


_PASSED_VARIABLES = (
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "SSH_AUTH_SOCK",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "NO_PROXY",
    "no_proxy",
)

# The system's directories, after the recorded programs' own, on the
# children's PATH: ssh and the like come from there.
_SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def _within(path: str, root: str) -> bool:
    root = root.rstrip(os.sep)
    return path == root or path.startswith(root + os.sep)


def _untrusted(path: str, ctx: Context) -> bool:
    real = os.path.realpath(path)
    return any(_within(real, root) for root in ctx.untrusted)


def check_project(ctx: Context) -> None:
    """RemoteWriteError when the project directory is the home directory or
    holds it: the sandbox can then write every directory under home, and no
    program or origin there can be trusted."""
    if _within(os.path.realpath(ctx.home), os.path.realpath(ctx.project)):
        raise RemoteWriteError(
            f"the project directory {ctx.project} contains the home directory; "
            "start Claude Code in the repository's own directory"
        )


def _search_path(ctx: Context) -> list[str]:
    """The entries of ``ctx.path`` the ``record`` command finds git and gh
    on: the absolute ones whose directory, links followed, is not in or
    under an untrusted root (:func:`untrusted_roots`)."""
    entries = []
    for entry in ctx.path.split(os.pathsep):
        if not os.path.isabs(entry) or _untrusted(entry, ctx):
            continue
        if entry not in entries:
            entries.append(entry)
    return entries


def find_program(name: str, ctx: Context) -> str:
    """The program ``name`` as found on ``ctx.path`` (:func:`_search_path`):
    the path of the first executable file of that name, as found (a package
    manager's link keeps working across upgrades). Refused when it lies,
    links followed, in an untrusted root."""
    for entry in _search_path(ctx):
        candidate = os.path.join(entry, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            if _untrusted(candidate, ctx):
                raise RemoteWriteError(
                    f"the {name} found on PATH links into the project, a temporary "
                    f"directory or the plugins directory ({os.path.realpath(candidate)})"
                )
            return candidate
    raise RemoteWriteError(f"{name} was not found on PATH")


def recorded_program(path: Any, name: str, ctx: Context) -> str:
    """The program the record names, links followed; RemoteWriteError when
    there is none, it is not an executable file, or it now lies in an
    untrusted root."""
    if not isinstance(path, str) or not os.path.isabs(path):
        raise RemoteWriteError(
            f"the origin record names no {name}; record the origin again"
        )
    real = os.path.realpath(path)
    if _untrusted(real, ctx):
        raise RemoteWriteError(
            f"the recorded {name} ({real}) lies in the project, a temporary "
            "directory or the plugins directory"
        )
    if not (os.path.isfile(real) and os.access(real, os.X_OK)):
        raise RemoteWriteError(
            f"the recorded {name} ({path}) is not an executable file; record the "
            "origin again"
        )
    return real


def work_directory(home: str) -> str:
    """``~/.config/acs/work``, made with mode 700: the directory each call's
    own working directory is made in. It lies in the directory the setup
    command's settings deny to the agent, so no sandboxed command can change
    the bare repository a push is made from, or what gh reads, while a call
    runs. The environment's TMPDIR, which a project's settings can point at
    a directory the sandbox writes, is not used. RemoteWriteError when it or
    ``~/.config/acs`` is a link, belongs to another user or is writable by
    others."""
    base = os.path.dirname(record_path(home))
    work = os.path.join(base, "work")
    for directory in (base, work):
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            st = os.lstat(directory)
        except OSError as e:
            raise RemoteWriteError(f"cannot make {directory}: {e.strerror}") from e
        if (
            not stat.S_ISDIR(st.st_mode)
            or st.st_uid != os.getuid()
            or st.st_mode & 0o022
        ):
            raise RemoteWriteError(
                f"{directory} must be a directory of this user that no one else "
                "can write, not a link"
            )
    return work


def child_environment(
    ctx: Context, workdir: str, programs: tuple[str, ...]
) -> dict[str, str]:
    """The environment git and gh run with: the variables they need from
    this process's (credentials and locale; no ``GIT_*``, ``GH_REPO``,
    ``GH_HOST``, ``GH_CONFIG_DIR``, ``XDG_CONFIG_HOME``, ``DEVELOPER_DIR``
    or ``SDKROOT``, which would choose another configuration, target or
    program), the home directory from the password database, a PATH of the
    directories of ``programs`` and the system's, ``workdir`` as the
    temporary directory, and no prompt. ``workdir`` also bounds git's search
    for a repository."""
    import pwd

    env = {k: os.environ[k] for k in _PASSED_VARIABLES if k in os.environ}
    try:
        user = pwd.getpwuid(os.getuid()).pw_name
        env["USER"] = env["LOGNAME"] = user
    except KeyError:
        pass
    path: list[str] = []
    for directory in [os.path.dirname(p) for p in programs] + list(_SYSTEM_PATH):
        if directory not in path and not _untrusted(directory, ctx):
            path.append(directory)
    env.update(
        {
            "HOME": ctx.home,
            "PATH": os.pathsep.join(path),
            "TMPDIR": workdir,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_CEILING_DIRECTORIES": os.path.dirname(workdir),
            "GH_PROMPT_DISABLED": "1",
            "GH_NO_UPDATE_NOTIFIER": "1",
            "GH_SPINNER_DISABLED": "1",
            "NO_COLOR": "1",
        }
    )
    return env


def _run(
    argv: list[str], env: dict[str, str], cwd: str, timeout: float
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=env,
            cwd=cwd,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise RemoteWriteError(
            f"{os.path.basename(argv[0])} did not finish within {int(timeout)} seconds"
        ) from e
    except OSError as e:
        raise RemoteWriteError(
            f"cannot run {os.path.basename(argv[0])}: {e.strerror}"
        ) from e


def _git_line(git: str, ctx: Context, workdir: str, *args: str) -> str | None:
    """git's one-line answer for ``git <args>`` run in the project, or None
    when git answers with a failure."""
    done = _run(
        [git, *_SAFE_GIT_OPTIONS, "-C", ctx.project, *args],
        child_environment(ctx, workdir, (git,)),
        workdir,
        _GIT_TIMEOUT,
    )
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", "replace").strip()


def git_dir_is_made(git_dir: str) -> bool:
    """grounded_agency.utils.git.git_dir_is_made, repeated here: a ``.git``
    directory, or a linked worktree's or a submodule's under one."""
    path = git_dir.replace(os.sep, "/") if os.sep != "/" else git_dir
    return (
        path.endswith("/.git") or "/.git/worktrees/" in path or "/.git/modules/" in path
    )


@dataclass(frozen=True)
class Repository:
    """The project's repository as git names it."""

    top: str
    git_dir: str
    common_dir: str
    object_format: str


def find_repository(git: str, ctx: Context, workdir: str) -> Repository:
    """The project's repository; RemoteWriteError when the project is in
    none, or its git directory is not one git made for a work tree (a
    repository's content can hold a git directory, whose configuration git
    would read)."""
    top = _git_line(git, ctx, workdir, "rev-parse", "--show-toplevel")
    git_dir = _git_line(git, ctx, workdir, "rev-parse", "--absolute-git-dir")
    common = _git_line(
        git, ctx, workdir, "rev-parse", "--path-format=absolute", "--git-common-dir"
    )
    fmt = _git_line(git, ctx, workdir, "rev-parse", "--show-object-format")
    if not top or not git_dir or not common or fmt not in ("sha1", "sha256"):
        raise RemoteWriteError(
            f"the project {ctx.project} is not in a git repository with a work tree"
        )
    if not git_dir_is_made(git_dir):
        raise RemoteWriteError(
            f"the project's git directory {git_dir} is not one git made for a work tree"
        )
    return Repository(
        os.path.realpath(top), os.path.realpath(git_dir), os.path.realpath(common), fmt
    )


def _record_hint(project: str) -> str:
    return (
        "A person records it in a terminal outside Claude Code: /usr/bin/python3 -I "
        f"{os.path.abspath(__file__)} record --project {project}"
    )


def find_entry(ctx: Context) -> dict[str, Any]:
    """The record's entry for the project directory: the one whose project
    holds it, the innermost when several do. Nothing runs to find it; the
    recorded git then confirms it (:func:`confirm_entry`)."""
    here = os.path.realpath(ctx.project)
    best: dict[str, Any] | None = None
    for entry in read_records(ctx.home):
        if _within(here, entry["project"]) and (
            best is None or len(entry["project"]) > len(best["project"])
        ):
            best = entry
    if best is None:
        raise RemoteWriteError(
            f"no origin is recorded for {ctx.project}. " + _record_hint(ctx.project)
        )
    return best


def confirm_entry(entry: dict[str, Any], repo: Repository) -> None:
    """RemoteWriteError unless the entry's project directory and common git
    directory are both the repository's now."""
    if entry["project"] != repo.top:
        raise RemoteWriteError(
            f"no origin is recorded for {repo.top}. " + _record_hint(repo.top)
        )
    if entry["git_dir"] != repo.common_dir:
        raise RemoteWriteError(
            f"the origin recorded for {repo.top} was recorded for the git "
            f"directory {entry['git_dir']}, and the project's is now "
            f"{repo.common_dir}; record it again"
        )


def check_local_origin(url: str, ctx: Context) -> None:
    """RemoteWriteError when ``url`` is a local path in an untrusted root:
    git's local transport runs the receiving repository's own hooks and
    configuration (``core.hooksPath=/dev/null`` does not reach that side),
    so a repository the sandbox can write would run its code outside the
    sandbox on the next push."""
    path = url[len("file://") :] if url.startswith("file://") else url
    if path.startswith("/") and _untrusted(path, ctx):
        raise RemoteWriteError(
            f"the local origin {path} lies in the project, a temporary directory or "
            "the plugins directory, where the agent's commands can change the "
            "hooks its pushes run"
        )


def _git_checks_ref(git: str, ctx: Context, workdir: str, ref: str) -> None:
    done = _run(
        [git, "check-ref-format", ref],
        child_environment(ctx, workdir, (git,)),
        workdir,
        _GIT_TIMEOUT,
    )
    if done.returncode != 0:
        raise RemoteWriteError(f"git check-ref-format refuses {ref}")


def _shown(done: subprocess.CompletedProcess[bytes]) -> str:
    out = (done.stdout or b"").decode("utf-8", "replace").strip()
    err = (done.stderr or b"").decode("utf-8", "replace").strip()
    text = "\n".join(p for p in (out, err) if p)
    if len(text) > _OUTPUT_LIMIT:
        text = text[: _OUTPUT_LIMIT // 2] + "\n[...]\n" + text[-_OUTPUT_LIMIT // 2 :]
    return text


# ---------------------------------------------------------------------------
# The actions


def _push(
    ctx: Context,
    workdir: str,
    git: str,
    repo: Repository,
    url: str,
    source: str,
    target: str,
    lease: str | None,
) -> str:
    """Push the object ``source`` to the ref ``target`` of ``url`` from an
    empty bare repository that reads the project's objects through
    ``objects/info/alternates``: the project's configuration and hooks take
    no part."""
    env = child_environment(ctx, workdir, (git,))
    bare = os.path.join(workdir, "push.git")
    done = _run(
        [
            git,
            *_SAFE_GIT_OPTIONS,
            "init",
            "--bare",
            "--quiet",
            "--template=",
            f"--object-format={repo.object_format}",
            bare,
        ],
        env,
        workdir,
        _GIT_TIMEOUT,
    )
    if done.returncode != 0:
        raise RemoteWriteError(
            "git could not make the repository it pushes from:\n" + _shown(done)
        )
    with open(
        os.path.join(bare, "objects", "info", "alternates"), "w", encoding="utf-8"
    ) as f:
        f.write(os.path.join(repo.common_dir, "objects") + "\n")
    argv = [
        git,
        *_SAFE_GIT_OPTIONS,
        *_PROTOCOL_OPTIONS,
        f"--git-dir={bare}",
        "push",
        *_PUSH_OPTIONS,
    ]
    if lease is not None:
        argv.append(f"--force-with-lease={target}:{lease}")
    argv += ["--", url, f"{source}:{target}"]
    done = _run(argv, env, workdir, _REMOTE_TIMEOUT)
    if done.returncode != 0:
        raise RemoteWriteError("git push failed:\n" + _shown(done))
    return _shown(done)


def _resolve(git: str, ctx: Context, workdir: str, ref: str, peel: str) -> str:
    oid = _git_line(
        git,
        ctx,
        workdir,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        ref + peel,
    )
    if not oid or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid):
        raise RemoteWriteError(f"the project has no {ref}")
    return oid


def _gh(
    ctx: Context,
    workdir: str,
    entry: dict[str, Any],
    github: str | None,
    args: list[str],
) -> str:
    if github is None:
        raise RemoteWriteError(
            "the recorded origin is not a GitHub repository URL, so gh cannot act on it"
        )
    gh = recorded_program(entry["gh"], "gh", ctx)
    done = _run(
        [gh, *args, f"--repo={github}"],
        child_environment(ctx, workdir, (entry["gh"], entry["git"])),
        workdir,
        _REMOTE_TIMEOUT,
    )
    if done.returncode != 0:
        raise RemoteWriteError("gh failed:\n" + _shown(done))
    return _shown(done)


def call_tool(name: str, arguments: Any, ctx: Context) -> str:
    """Perform one call of the tool ``name`` and return what git or gh
    printed; RemoteWriteError when it is refused or fails.

    Before any program runs: the arguments are checked, a project that
    holds the home directory is refused, the record's entry for the project
    is read, its git (and, for a gh tool, its gh) must lie outside the
    untrusted roots, and so must a local origin. Then the recorded git
    checks the names and confirms that the project's repository is the one
    recorded."""
    tool = TOOLS.get(name)
    if tool is None:
        raise RemoteWriteError("no such tool")
    values = validate_arguments(tool, arguments)
    check_project(ctx)
    entry = find_entry(ctx)
    git = recorded_program(entry["git"], "git", ctx)
    url, derived = parse_origin(entry["url"])
    check_local_origin(url, ctx)
    github = entry["github"] if entry["github"] is not None else derived
    workdir = tempfile.mkdtemp(prefix="acs-remote-", dir=work_directory(ctx.home))
    try:
        for key in ("branch", "head", "base"):
            if key in values:
                _git_checks_ref(git, ctx, workdir, "refs/heads/" + values[key])
        if "tag" in values:
            _git_checks_ref(git, ctx, workdir, "refs/tags/" + values["tag"])
        repo = find_repository(git, ctx, workdir)
        confirm_entry(entry, repo)
        if name == "push":
            ref = "refs/heads/" + values["branch"]
            oid = _resolve(git, ctx, workdir, ref, "^{commit}")
            return _push(
                ctx, workdir, git, repo, url, oid, ref, values.get("force_with_lease")
            )
        if name == "tag_push":
            ref = "refs/tags/" + values["tag"]
            oid = _resolve(git, ctx, workdir, ref, "")
            return _push(ctx, workdir, git, repo, url, oid, ref, None)
        if name == "pr_create":
            args = [
                "pr",
                "create",
                f"--head={values['head']}",
                f"--base={values['base']}",
                f"--title={values['title']}",
                f"--body={values['body']}",
            ]
            if values.get("draft"):
                args.append("--draft")
            return _gh(ctx, workdir, entry, github, args)
        if name == "pr_merge":
            args = ["pr", "merge", str(values["number"]), f"--{values['method']}"]
            if "match_head_commit" in values:
                args.append(f"--match-head-commit={values['match_head_commit']}")
            return _gh(ctx, workdir, entry, github, args)
        if name == "release_create":
            args = [
                "release",
                "create",
                values["tag"],
                "--verify-tag",
                f"--title={values['title']}",
                f"--notes={values['notes']}",
            ]
            if values.get("draft"):
                args.append("--draft")
            if values.get("prerelease"):
                args.append("--prerelease")
            return _gh(ctx, workdir, entry, github, args)
        if name == "issue_create":
            return _gh(
                ctx,
                workdir,
                entry,
                github,
                [
                    "issue",
                    "create",
                    f"--title={values['title']}",
                    f"--body={values['body']}",
                ],
            )
        if name == "issue_assign":
            return _gh(
                ctx,
                workdir,
                entry,
                github,
                [
                    "issue",
                    "edit",
                    str(values["number"]),
                    f"--add-assignee={values['assignee']}",
                ],
            )
        raise RemoteWriteError("no such tool")  # pragma: no cover
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# The MCP server (JSON-RPC 2.0, one message per line on stdin and stdout)


def _tool_list() -> list[dict[str, Any]]:
    records = {r["tool"][len(PLUGIN_TOOL_PREFIX) :]: r for r in binding_records()}
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.input_schema(),
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": t.name in ("push", "pr_merge"),
                "idempotentHint": False,
                "openWorldHint": True,
            },
            # The tool's binding record, in a carrier (section 5.18.1).
            "_meta": {"acs/tool_binding": records[t.name]},
        }
        for t in TOOLS.values()
    ]


def handle(message: Any, ctx_factory: Callable[[], Context]) -> dict[str, Any] | None:
    """The response to one JSON-RPC message, or None for a notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "invalid request"},
        }
    mid = message.get("id")
    method = message.get("method")
    if "id" not in message:
        return None
    if not (mid is None or isinstance(mid, (str, int))) or isinstance(mid, bool):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "invalid id"},
        }
    params = message.get("params") or {}
    if method == "initialize":
        asked = params.get("protocolVersion") if isinstance(params, dict) else None
        version = asked if asked in _PROTOCOL_VERSIONS else _PROTOCOL_VERSIONS[0]
        result: dict[str, Any] = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": "Remote writes to the origin recorded for this project: "
            "one push, tag, pull request, merge, release or issue per call.",
        }
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": _tool_list()}}
    if method == "tools/call":
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32602, "message": "invalid params"},
            }
        if params["name"] not in TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32602, "message": "unknown tool"},
            }
        try:
            text = call_tool(params["name"], params.get("arguments", {}), ctx_factory())
            error = False
        except RemoteWriteError as e:
            text, error = f"Refused or failed: {e}", True
        except Exception as e:  # noqa: BLE001 - the server answers every call
            text, error = f"Failed: {type(e).__name__}", True
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "content": [{"type": "text", "text": text or "done"}],
                "isError": error,
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": mid,
        "error": {"code": -32601, "message": "method not found"},
    }


def serve(
    ctx_factory: Callable[[], Context], stdin: Any = None, stdout: Any = None
) -> int:
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            response = handle(message, ctx_factory)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# Command line


def _record_command(args: list[str], home: str) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="remote_writes.py record")
    parser.add_argument("--project", default=os.getcwd())
    parser.add_argument(
        "--url", help="the origin URL (default: the project's remote.origin.url)"
    )
    parser.add_argument(
        "--github", help="HOST/OWNER/REPO for gh, when the URL does not give it"
    )
    parser.add_argument("--yes", action="store_true", help="record without asking")
    opts = parser.parse_args(args)
    project = os.path.abspath(opts.project)
    ctx = Context(
        project, home, os.environ.get("PATH", ""), untrusted_roots(project, home)
    )
    check_project(ctx)
    git = find_program("git", ctx)
    try:
        gh: str | None = find_program("gh", ctx)
    except RemoteWriteError:
        gh = None
    workdir = tempfile.mkdtemp(prefix="acs-remote-", dir=work_directory(home))
    try:
        repo = find_repository(git, ctx, workdir)
        url = opts.url
        if url is None:
            url = _git_line(git, ctx, workdir, "config", "--get", "remote.origin.url")
            if not url:
                raise RemoteWriteError(
                    "the project has no remote.origin.url; give --url"
                )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    url, derived = parse_origin(url)
    check_local_origin(url, ctx)
    github = opts.github
    if github is not None and not re.fullmatch(
        r"[A-Za-z0-9.-]+/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", github
    ):
        raise RemoteWriteError("--github must be HOST/OWNER/REPO")
    github = github or derived
    print(f"Project:            {repo.top}")
    print(f"Git directory:      {repo.common_dir}")
    print(f"Origin URL:         {url}")
    print(
        f"GitHub repository:  {github or '(none: pull requests, releases and issues are refused)'}"
    )
    print(f"git:                {git}")
    print(
        f"gh:                 {gh or '(none found: pull requests, releases and issues are refused)'}"
    )
    print(f"Record:             {record_path(home)}")
    if not opts.yes:
        if not sys.stdin.isatty():
            raise RemoteWriteError("not asked: run it in a terminal, or pass --yes")
        answer = input(
            "Record this origin, and these git and gh, for the remote-write tools? [y/N] "
        )
        if answer.strip().lower() not in ("y", "yes"):
            print("Nothing was recorded.")
            return 1
    entry = {
        "project": repo.top,
        "git_dir": repo.common_dir,
        "url": url,
        "github": opts.github,
        "git": git,
        "gh": gh,
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    print(f"Recorded in {write_record(home, entry)}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # --home is for tests: the plugin's plugin.json passes none.
    home: str | None = None
    if len(args) >= 2 and args[0] == "--home":
        home = os.path.abspath(args[1])
        args = args[2:]
    command = args[0] if args else ""
    try:
        if command == "serve" and len(args) == 1:
            return serve(lambda: Context.from_process(home))
        if command == "record":
            return _record_command(
                args[1:], _home_directory() if home is None else home
            )
        if command == "bindings":
            prefix = PLUGIN_TOOL_PREFIX
            if len(args) == 3 and args[1] == "--prefix":
                prefix = args[2]
            elif len(args) != 1:
                raise RemoteWriteError("usage: bindings [--prefix PREFIX]")
            print(json.dumps(binding_records(prefix), indent=2))
            return 0
    except RemoteWriteError as e:
        print(f"remote_writes.py: {e}", file=sys.stderr)
        return 2
    print(
        "usage: remote_writes.py [--home DIR] serve | record [--project DIR] [--url URL] "
        "[--github HOST/OWNER/REPO] [--yes] | bindings [--prefix PREFIX]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
