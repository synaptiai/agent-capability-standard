"""The safety layer's records, and the settings that keep the agent's commands from them.

The plugin's hooks keep their records in files any process of the user can
write: the checkpoint marker (``.claude/checkpoint.ok``), the marker history
(``.claude/checkpoints/``), the audit log and its head (``.claude/audit.log``,
``.claude/audit.head``) and, in the repository's git directory, the
checkpoint key, the entered commits and the head's anchor (``<git dir>/acs/``).
The boundary that keeps the agent from writing them is Claude Code's
``permissions.deny`` rules: ``Edit(...)`` rules refuse the file tools and,
under the sandbox, every route a sandboxed command takes (a symbolic or hard
link made inside the session, a rename of the file or of a directory above
it, an interpreter). ``Read(...)`` rules refuse reading the git directory's
records, which hold the checkpoint key; the project's records hold no
secret, and the audit skill cites the audit log as evidence, so they stay
readable. The sandbox's own ``filesystem.denyWrite`` list covers sandboxed
commands only; it is returned as well, for a sandbox configured from that
list.

:func:`deny_settings` gives those rules for a project as a settings fragment,
every path literal and absolute (a glob such as ``audit.log*`` is skipped by
the Linux sandbox runtime): ::

    {
      "permissions": {"deny": ["Edit(//<abs>/.claude/checkpoint.ok)", ...,
                               "Edit(//<abs>/.git/acs/**)", ...,
                               "Read(//<abs>/.git/acs/**)", ...]},
      "sandbox": {"filesystem": {"denyWrite": ["/<abs>/.claude/checkpoint.ok",
                                               "/<abs>/.claude/checkpoints", ...]}}
    }

A directory is denied as a whole: ``dir/**`` in a permission rule, the plain
directory in ``denyWrite``. The git directory is the one git names for the
project (``git rev-parse --absolute-git-dir``), so a linked worktree's records
are denied in ``.git/worktrees/<name>/acs``, where the hooks keep them. The
``acs`` of every other git directory of the repository is denied as well:
the common git directory's, each linked worktree's
(``<common>/worktrees/<name>``) and each submodule's
(``<common>/modules/<path>``, nested ones included), since a session in one
checkout can otherwise reach another's key and commit entries. In a
submodule checkout, whose common git directory is its own
``modules/<path>``, the superproject's git directories are added the same
way (``git rev-parse --show-superproject-working-tree``), up to the
outermost superproject. A rule names
the git directories that exist when it is made: the settings are made again
after ``git worktree add`` or a submodule's first checkout.

The module uses the standard library alone and the syntax of Python 3.9, so
it also runs from a plugin checkout with no compiled extension, under the
system's ``python3`` (3.9 or newer)::

    python3 -I <plugin>/grounded_agency/layer_records.py [PROJECT_DIR]

prints the fragment as JSON (``-I`` keeps the script's own directory off the
module path). The plugin's pre-tool-use hook holds the same list of records
(``LAYER_RECORDS`` and ``GIT_DIR_RECORDS``); a test keeps the two equal.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

__all__ = [
    "GIT_DIR_RECORDS",
    "PROJECT_RECORDS",
    "LayerRecord",
    "LayerRecordsError",
    "deny_settings",
    "layer_records",
    "main",
]

# The records the hooks keep in the project directory, as (path relative to
# it, whether it is a directory). The audit log is not rotated: a person who
# starts a new log moves audit.log and audit.head aside under names of their
# choosing.
PROJECT_RECORDS: tuple[tuple[str, bool], ...] = (
    (".claude/checkpoint.ok", False),
    (".claude/checkpoints", True),
    (".claude/audit.log", False),
    (".claude/audit.head", False),
)

# The records the hooks keep in the project's git directory: acs/ holds the
# checkpoint key, the entered commits and the audit head's anchor. These are
# denied to reads as well as to writes.
GIT_DIR_RECORDS: tuple[tuple[str, bool], ...] = (("acs", True),)

# grounded_agency.utils.git.SAFE_GIT_OPTIONS, repeated here so that this file
# imports nothing from the package (a test keeps the two equal).
_SAFE_GIT_OPTIONS: tuple[str, ...] = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
)
_GIT_TIMEOUT = 5.0

# Characters a permission rule reads as a pattern, or as the end of the
# rule: a path holding one cannot be written as a literal rule.
_PATTERN_CHARACTERS = frozenset("*?[]{}()\\")


class LayerRecordsError(Exception):
    """The records' paths cannot be given: git did not say which git
    directory is the project's, or a path cannot be written as a literal
    rule."""


@dataclass(frozen=True)
class LayerRecord:
    """One record: an absolute path, whether it is a directory, and whether
    it is in a git directory (it holds the checkpoint key, so reads of it
    are denied too)."""

    path: str
    directory: bool
    in_git_dir: bool = False


def _git_line(project: str, option: str, empty: bool = False) -> str | None:
    """git's one-line answer to ``git rev-parse <option>`` in ``project``,
    or None when the project is in no repository (or, with ``empty``, when
    git answers with nothing)."""
    try:
        result = subprocess.run(
            [
                "git",
                *_SAFE_GIT_OPTIONS,
                "-C",
                project,
                "rev-parse",
                option,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as e:
        raise LayerRecordsError(
            "git is not installed, so the project's git directory is unknown"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise LayerRecordsError(
            f"git did not say within {_GIT_TIMEOUT:g} seconds which git "
            "directory is the project's"
        ) from e
    if result.returncode == 128:
        return None
    out = os.fsdecode(result.stdout)
    if empty and result.returncode == 0 and out == "":
        return None
    if result.returncode != 0 or not out.endswith("\n") or len(out) < 2:
        raise LayerRecordsError(
            f"git could not say which git directory is the project's "
            f"(exit {result.returncode})"
        )
    # Exactly git's line: a directory's name may itself end in a line break.
    return out[:-1]


def _subdirectories(path: str) -> list[str]:
    """The directories in ``path`` (no symbolic link followed), by name; none
    when ``path`` is no directory."""
    if os.path.islink(path) or not os.path.isdir(path):
        return []
    try:
        with os.scandir(path) as entries:
            return sorted(e.path for e in entries if e.is_dir(follow_symlinks=False))
    # Two clauses: the bare list of PEP 758 is a syntax error before Python
    # 3.14, and the file runs under the system's python3 (3.9 on macOS).
    except FileNotFoundError:
        return []
    except NotADirectoryError:
        return []
    except OSError as e:
        raise LayerRecordsError(f"cannot list {path!r}: {e.strerror}") from e


def _is_git_dir(path: str) -> bool:
    head = os.path.join(path, "HEAD")
    return os.path.isfile(head) and not os.path.islink(head)


def _linked_git_dirs(git_dir: str) -> list[str]:
    """The git directories git keeps in ``git_dir``: each linked worktree's
    (``worktrees/<name>``) and each submodule's (``modules/<path>``, where a
    path may have several names, and a submodule's own worktrees and
    submodules in turn)."""
    found: list[str] = []

    def modules(directory: str) -> None:
        for d in _subdirectories(directory):
            if _is_git_dir(d):
                found.append(d)
                linked(d)
            else:
                modules(d)

    def linked(g: str) -> None:
        found.extend(_subdirectories(os.path.join(g, "worktrees")))
        modules(os.path.join(g, "modules"))

    linked(git_dir)
    return found


def _repository_git_dirs(physical: str) -> list[str]:
    """The git directories of the repository the checkout at ``physical``
    belongs to: its own git directory, its common git directory and the
    linked worktrees' and submodules' git directories in it; then, for a
    submodule checkout, the same for its superproject, and for that one's
    superproject, up to the top. Empty outside a repository."""
    git_dirs: list[str] = []
    seen: set[str] = set()
    checkout: str | None = physical
    while checkout is not None and checkout not in seen:
        seen.add(checkout)
        git_dir = _git_line(checkout, "--absolute-git-dir")
        if git_dir is None:
            break
        git_dirs.append(git_dir)
        common = _git_line(checkout, "--git-common-dir")
        if common is not None:
            # Relative to the directory git ran in, from a git before 2.31
            # (which has no --path-format), or for the main checkout.
            common = os.path.realpath(os.path.join(checkout, common))
            git_dirs.append(common)
            git_dirs.extend(_linked_git_dirs(common))
        # A submodule's common git directory is its own modules/<path>:
        # the superproject's records (its acs/, which holds its checkpoint
        # key) are reached only from the superproject's checkout.
        superproject = _git_line(
            checkout, "--show-superproject-working-tree", empty=True
        )
        checkout = (
            os.path.realpath(superproject)
            if superproject is not None and os.path.isabs(superproject)
            else None
        )
    return list(dict.fromkeys(git_dirs))


def _check_literal(path: str) -> None:
    bad = sorted({c for c in path if c in _PATTERN_CHARACTERS or ord(c) < 0x20})
    if bad:
        raise LayerRecordsError(
            f"{path!r} holds {''.join(bad)!r}, which a permission rule reads "
            "as a pattern: it cannot be denied by a literal rule"
        )


def layer_records(project_dir: str | os.PathLike[str]) -> list[LayerRecord]:
    """The layer's records for the project at ``project_dir``, as absolute
    paths.

    Each project record is given under the project directory as written
    (made absolute) and, where that differs, under its physical path (with
    every symbolic link resolved: ``/var`` and ``/private/var`` on macOS),
    since a rule and a path are compared as text. The git directory's
    records are given under git's answer, which is physical, and, for a git
    directory inside the project, under the written project path too; then
    those of the repository's other git directories (the common one, linked
    worktrees', submodules', and a submodule checkout's superprojects'), as
    they exist now.

    Raises:
        LayerRecordsError: git did not answer, or a path holds a character a
            permission rule reads as a pattern.
    """
    written = os.path.abspath(os.fspath(project_dir))
    physical = os.path.realpath(written)
    bases = [written] if written == physical else [written, physical]
    records: list[LayerRecord] = []

    def add(path: str, directory: bool, in_git_dir: bool) -> None:
        _check_literal(path)
        record = LayerRecord(path, directory, in_git_dir)
        if record not in records:
            records.append(record)

    for base in bases:
        for rel, directory in PROJECT_RECORDS:
            add(f"{base.rstrip('/')}/{rel}", directory, False)
    git_dirs = _repository_git_dirs(physical)
    if git_dirs:
        prefix = physical.rstrip("/") + "/"
        for gd in git_dirs:
            git_bases = [gd]
            if written != physical and gd.startswith(prefix):
                git_bases.append(written.rstrip("/") + "/" + gd[len(prefix) :])
            for base in git_bases:
                for rel, directory in GIT_DIR_RECORDS:
                    add(f"{base.rstrip('/')}/{rel}", directory, True)
    return records


def deny_settings(project_dir: str | os.PathLike[str]) -> dict[str, Any]:
    """The settings fragment that denies the layer's records to the agent:
    ``permissions.deny`` ``Edit(...)`` rules for every record, then
    ``Read(...)`` rules for the git directories' records, and
    ``sandbox.filesystem.denyWrite``, for the project at ``project_dir``
    (see the module's description)."""
    records = layer_records(project_dir)

    def rule_path(r: LayerRecord) -> str:
        return "/" + r.path + ("/**" if r.directory else "")

    return {
        "permissions": {
            "deny": [f"Edit({rule_path(r)})" for r in records]
            + [f"Read({rule_path(r)})" for r in records if r.in_git_dir]
        },
        "sandbox": {"filesystem": {"denyWrite": [r.path for r in records]}},
    }


def main(argv: list[str] | None = None) -> int:
    """Print :func:`deny_settings` for the project named by the first
    argument (else ``CLAUDE_PROJECT_DIR``, else the current directory) as
    JSON. Status 2 when the records' paths cannot be given."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1 or (args and args[0] in ("-h", "--help")):
        print(
            "usage: layer_records.py [PROJECT_DIR]\n"
            "Print the settings that deny the safety layer's records to the "
            "agent's commands and file tools.",
            file=sys.stderr,
        )
        return 0 if args and args[0] in ("-h", "--help") else 2
    project = args[0] if args else os.environ.get("CLAUDE_PROJECT_DIR") or "."
    try:
        settings = deny_settings(project)
    except LayerRecordsError as e:
        print(f"layer_records: {e}", file=sys.stderr)
        return 2
    print(json.dumps(settings, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
