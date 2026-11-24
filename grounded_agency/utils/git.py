"""git, as the safety layer runs it on its own behalf.

A repository's content can hold what git reads as configuration: a
directory that holds ``HEAD``, ``objects/`` and ``refs/`` is a git directory
to git (an embedded bare repository), and its ``config`` can name programs
git runs (``core.fsmonitor`` when it refreshes the index, a textconv driver
when it shows a diff) and its ``hooks/`` scripts git runs. The layer's own
git commands turn those off (:data:`SAFE_GIT_OPTIONS`) and fetch nothing
(:func:`safe_git_environment`), and :func:`git_dir_is_made` tells a git
directory git made for a work tree from one a repository may have shipped.
The plugin's hooks do the same (``hgit`` and ``git_dir_is_made`` in
``hooks/pretooluse_require_checkpoint.sh``).
"""

from __future__ import annotations

import os

__all__ = ["SAFE_GIT_OPTIONS", "git_dir_is_made", "safe_git_environment"]

# Options for every git command the layer runs: no fsmonitor program and no
# hook, whatever the repository's configuration says.
SAFE_GIT_OPTIONS: tuple[str, ...] = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
)


def safe_git_environment() -> dict[str, str]:
    """This process's environment with lazy fetching turned off
    (``GIT_NO_LAZY_FETCH``): a command the layer runs never asks a promisor
    remote for an object."""
    return {**os.environ, "GIT_NO_LAZY_FETCH": "1"}


def git_dir_is_made(git_dir: str) -> bool:
    """Whether ``git_dir``, an absolute git directory as ``git rev-parse
    --absolute-git-dir`` prints it, is one git makes for a work tree: a
    ``.git`` directory, or a linked worktree's or a submodule's under one.
    git refuses a path with a ``.git`` component in a repository, so no
    clone or checkout writes one; any other git directory may be repository
    content, whose configuration and hooks git would read and run."""
    path = git_dir.replace(os.sep, "/") if os.sep != "/" else git_dir
    return (
        path.endswith("/.git") or "/.git/worktrees/" in path or "/.git/modules/" in path
    )
