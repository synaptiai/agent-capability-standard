#!/usr/bin/env python3
"""Export the audit log's head as a witness to a destination directory.

Copies the project's head, .claude/audit.head, and its anchor,
<git dir>/acs/audit.head, where there is one, into the destination
directory, each as a new file named by the time and the session:
<UTC time>-<session>-head.head and <UTC time>-<session>-anchor.head. A copy
never replaces another: a name already taken gets a number (-2, -3, ...).
tools/verify_audit_log.py --witness <destination> then checks the log
against every witness kept there, and names the witness a cut log fails.

A witness shows only a cut of the entries before it: a log checked against
the witnesses taken at each session's end shows any cut of an earlier
session, and not one made in the current session after its last witness.

The destination is --dest, else the environment variable
ACS_AUDIT_WITNESS_DIR. It must be an existing directory outside the project
directory and outside the project's git directory, which the agent's
commands write. A destination taken from the environment is refused when the
project's own settings files (.claude/settings.json or
.claude/settings.local.json) set ACS_AUDIT_WITNESS_DIR in their env: Claude
Code applies that env, which is repository content, over the person's, so
the repository would choose where its witnesses go.

A local directory the user can write is a test destination only: the agent
runs as the same user, so its commands can remove or replace what is there.
A witness counts when the destination keeps it out of the agent's reach: a
mount the user can add files to but not delete or overwrite them in (an
append-only or write-once store), or a copy taken off the machine to an
account whose credential the agent's commands cannot read. See the witness
section of hooks/README.md and spec/SECURITY.md section 5.5.

Exit status: 0 when every copy was written, 1 when the export failed (the
reason on stderr), 2 when it was not run (no destination set).

Usage:
    python tools/export_audit_witness.py [--project DIR] [--dest DIR]
        [--session ID]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_audit_log import default_anchor  # noqa: E402

SETTING = "ACS_AUDIT_WITNESS_DIR"
PROJECT_SETTINGS = ("settings.json", "settings.local.json")
# A head is one line of JSON well under this; a larger file is not a head.
MAX_HEAD_BYTES = 4096
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


class ExportError(Exception):
    """The export cannot be done: why, in words."""


def safe_name(text: str) -> str:
    """``text`` as part of a file name: characters outside A-Z, a-z, 0-9,
    ``.``, ``_`` and ``-`` replaced by ``_``, at most 64 characters, and
    ``session`` when nothing is left."""
    return _UNSAFE.sub("_", text)[:64].strip(".") or "session"


def project_sets_destination(project: Path) -> list[str]:
    """The project's settings files that set :data:`SETTING` in their env,
    or that are there and cannot be read as JSON (either could set it)."""
    found: list[str] = []
    for name in PROJECT_SETTINGS:
        path = project / ".claude" / name
        if not (path.exists() or path.is_symlink()):
            continue
        try:
            if not path.is_file():
                raise OSError("not a regular file")
            document = json.loads(path.read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, ValueError, RecursionError:
            found.append(f".claude/{name} (unreadable)")
            continue
        env = document.get("env") if isinstance(document, dict) else None
        if isinstance(env, dict) and SETTING in env:
            found.append(f".claude/{name}")
    return found


def _within(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def destination(project: Path, dest: str | None) -> Path:
    """The destination directory, checked: from ``dest``, else from the
    environment (refused when the project's settings set it)."""
    if dest is None:
        dest = os.environ.get(SETTING) or None
        if dest is None:
            raise LookupError(f"no destination: give --dest or set {SETTING}")
        named = project_sets_destination(project)
        if named:
            raise ExportError(
                f"{SETTING} is not used: the project's settings files set it, or "
                f"cannot be read ({', '.join(named)}); Claude Code applies a "
                "project's env, which is repository content, over yours"
            )
    path = Path(dest)
    if not path.is_absolute():
        raise ExportError(f"the destination {dest} is not an absolute path")
    if not path.is_dir():
        raise ExportError(f"the destination {dest} is not an existing directory")
    real = path.resolve()
    project_real = project.resolve()
    if _within(real, project_real):
        raise ExportError(
            f"the destination {dest} is inside the project directory "
            f"{project_real}, which the agent's commands write"
        )
    anchor = default_anchor(project / ".claude" / "audit.log")
    if anchor is not None:
        git_dir = anchor.parent.parent.resolve()
        if _within(real, git_dir):
            raise ExportError(
                f"the destination {dest} is inside the project's git directory "
                f"{git_dir}, which the agent's commands write"
            )
    return real


def _read_head(path: Path) -> bytes:
    try:
        with path.open("rb") as f:
            data = f.read(MAX_HEAD_BYTES + 1)
    except OSError as e:
        raise ExportError(f"{path} cannot be read: {e.strerror}") from None
    if len(data) > MAX_HEAD_BYTES:
        raise ExportError(f"{path} is larger than a head ({MAX_HEAD_BYTES} bytes)")
    return data


def _write_new(directory: Path, stem: str, data: bytes) -> Path:
    """Write ``data`` to a new file ``<stem>.head`` in ``directory``, or
    ``<stem>-<n>.head`` when that name is taken; never over a file."""
    for n in range(1, 1000):
        name = f"{stem}.head" if n == 1 else f"{stem}-{n}.head"
        target = directory / name
        try:
            fd = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o444,
            )
        except FileExistsError:
            continue
        except OSError as e:
            raise ExportError(f"{target} cannot be written: {e.strerror}") from None
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            raise ExportError(f"{target} cannot be written: {e.strerror}") from None
        return target
    raise ExportError(f"every name for {stem} in {directory} is taken")


def export(
    project: Path, dest: str | None, session: str, now: float | None = None
) -> list[Path]:
    """Copy the head, and the anchor where there is one, into the
    destination; returns the files written. Raises :class:`LookupError`
    when no destination is set, :class:`ExportError` when the export
    cannot be done."""
    directory = destination(project, dest)
    head = project / ".claude" / "audit.head"
    if not head.is_file():
        raise ExportError(
            f"there is no head to export at {head} (the log hook writes it with "
            "the first line it signs)"
        )
    sources = [("head", _read_head(head))]
    anchor = default_anchor(project / ".claude" / "audit.log")
    if anchor is not None and anchor.is_file():
        sources.append(("anchor", _read_head(anchor)))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    return [
        _write_new(directory, f"{stamp}-{safe_name(session)}-{kind}", data)
        for kind, data in sources
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the audit log's head as a witness"
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="The project directory (default: CLAUDE_PROJECT_DIR, else the "
        "current directory)",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help=f"The destination directory (default: {SETTING})",
    )
    parser.add_argument(
        "--session",
        default="session",
        help="The session the witness is taken at, part of each file's name",
    )
    args = parser.parse_args(argv)
    project = args.project or Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    try:
        written = export(project.absolute(), args.dest, args.session)
    except LookupError as e:
        print(f"WITNESS NOT EXPORTED: {e.args[0]}", file=sys.stderr)
        return 2
    except ExportError as e:
        print(f"WITNESS EXPORT FAILED: {e}", file=sys.stderr)
        return 1
    for path in written:
        print(f"WITNESS EXPORTED: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
