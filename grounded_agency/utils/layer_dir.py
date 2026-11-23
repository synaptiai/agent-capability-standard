"""Directories the safety layer keeps its own records in.

A repository's content can hold a symbolic link where the layer keeps its
records: git stores links, so a clone can ship ``.checkpoints``,
``.checkpoints/archive`` or ``.checkpoints/archive/pruned_checkpoints.jsonl``
as one. A layer that followed it would write its records, text a model
wrote among them, wherever the link points, outside the project, on calls
that need no checkpoint and no approval. :func:`open_layer_dir` opens such
a directory without following a link at it, nor at any directory on the
way to it when it is named by a relative path (each of those is within the
directory the process runs in, where a repository's content lies; the
directories above an absolute path are the host's), and every operation of
the :class:`LayerDir` it gives stays in that directory and follows no link
at the name it opens: through the directory's descriptor (``dir_fd``) where
the platform has it, so no check races the use; elsewhere by checking each
name with ``lstat`` first.
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
from pathlib import Path
from types import TracebackType

__all__ = ["LayerDir", "LinkedPathError", "open_layer_dir"]

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
# Descriptor-relative operations, where the platform has every one used.
_AT = bool(_NOFOLLOW and _DIRECTORY) and all(
    f in os.supports_dir_fd for f in (os.open, os.mkdir, os.unlink, os.rename, os.stat)
)
# What an open that refuses to follow a link fails with: ELOOP (Linux,
# macOS), EMLINK (FreeBSD), EFTYPE (NetBSD), ENOTDIR (Linux, a link opened
# with O_DIRECTORY).
_LINK_ERRNOS = frozenset(
    e
    for e in (
        errno.ELOOP,
        errno.EMLINK,
        errno.ENOTDIR,
        getattr(errno, "EFTYPE", None),
    )
    if e is not None
)


class LinkedPathError(OSError):
    """A directory or file the layer keeps its records at is a symbolic
    link, which the layer does not follow."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            errno.ELOOP,
            "a symbolic link where the layer keeps its records; not followed",
            str(path),
        )


class LayerDir:
    """An open directory of the layer's records (a context manager)."""

    def __init__(self, path: Path, fd: int | None) -> None:
        self.path = path
        self._fd = fd

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> LayerDir:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _is_link(self, name: str) -> bool:
        try:
            if self._fd is not None:
                st = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
            else:
                st = os.lstat(self.path / name)
        except FileNotFoundError:
            return False
        return stat.S_ISLNK(st.st_mode)

    def open(self, name: str, flags: int, mode: int = 0o600) -> int:
        """``os.open`` of ``name`` in this directory, never through a link
        at ``name`` (:class:`LinkedPathError`)."""
        if self._fd is None:
            if self._is_link(name):
                raise LinkedPathError(self.path / name)
            return os.open(self.path / name, flags | _CLOEXEC, mode)
        try:
            return os.open(name, flags | _NOFOLLOW | _CLOEXEC, mode, dir_fd=self._fd)
        except OSError as e:
            if e.errno in _LINK_ERRNOS and self._is_link(name):
                raise LinkedPathError(self.path / name) from e
            raise

    def open_regular(self, name: str, flags: int, mode: int = 0o600) -> int:
        """:meth:`open`, of a regular file only (``fstat`` on the
        descriptor; a FIFO is not waited on): ``OSError`` for anything
        else."""
        fd = self.open(name, flags | _NONBLOCK, mode)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError(errno.EINVAL, "not a regular file", str(self.path / name))
        except BaseException:
            os.close(fd)
            raise
        return fd

    def subdir(
        self, name: str, create: bool = False, mode: int = 0o777
    ) -> LayerDir | None:
        """The directory ``name`` in this one, opened without following a
        link at it (:class:`LinkedPathError`); None when there is none and
        ``create`` is false."""
        path = self.path / name
        if self._fd is None:
            if self._is_link(name):
                raise LinkedPathError(path)
            if not path.exists():
                if not create:
                    return None
                path.mkdir(mode=mode, exist_ok=True)
                if self._is_link(name):
                    raise LinkedPathError(path)
            if not path.is_dir():
                raise NotADirectoryError(errno.ENOTDIR, "not a directory", str(path))
            return LayerDir(path, None)
        try:
            return self._open_subdir(name)
        except FileNotFoundError:
            if not create:
                return None
        try:
            os.mkdir(name, mode, dir_fd=self._fd)
        except FileExistsError:
            pass
        return self._open_subdir(name)

    def _open_subdir(self, name: str) -> LayerDir:
        flags = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
        try:
            return LayerDir(self.path / name, os.open(name, flags, dir_fd=self._fd))
        except OSError as e:
            if e.errno in _LINK_ERRNOS and self._is_link(name):
                raise LinkedPathError(self.path / name) from e
            raise

    def create_temp(self, prefix: str, suffix: str) -> tuple[str, int]:
        """A new file in this directory, mode 0600: its name and a
        descriptor open for writing."""
        for _ in range(100):
            name = f"{prefix}{secrets.token_hex(8)}{suffix}"
            try:
                return name, self.open(
                    name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
            except FileExistsError:
                continue
        raise FileExistsError(errno.EEXIST, "no free temporary name", str(self.path))

    def replace(self, src: str, dst: str) -> None:
        """Rename ``src`` over ``dst``, both in this directory (a link at
        ``dst`` is replaced, not followed)."""
        if self._fd is not None:
            os.replace(src, dst, src_dir_fd=self._fd, dst_dir_fd=self._fd)
        else:
            os.replace(self.path / src, self.path / dst)

    def unlink(self, name: str) -> None:
        if self._fd is not None:
            os.unlink(name, dir_fd=self._fd)
        else:
            os.unlink(self.path / name)

    def restrict(self, mode: int = 0o700) -> None:
        """Take every permission outside ``mode`` from this directory (on
        its descriptor where there is one, so no link is followed)."""
        if self._fd is not None:
            current = stat.S_IMODE(os.fstat(self._fd).st_mode)
            if current & ~mode:
                os.fchmod(self._fd, current & mode)
        else:
            current = stat.S_IMODE(os.lstat(self.path).st_mode)
            if current & ~mode:
                os.chmod(self.path, current & mode)


def open_layer_dir(
    path: str | os.PathLike[str], create: bool = False, mode: int = 0o777
) -> LayerDir | None:
    """The directory ``path``, opened without following a symbolic link at
    it, nor, for a relative ``path``, at any directory on the way to it
    from the current one; with ``create``, the missing ones are made (and
    the parents of an absolute ``path``). None when it does not exist and
    ``create`` is false.

    Raises:
        LinkedPathError: One of those directories is a symbolic link.
        OSError: It cannot be opened or made.
    """
    p = Path(path)
    if p.is_absolute():
        start = p.parent
        names = [p.name] if p.name else []
        if create:
            start.mkdir(parents=True, exist_ok=True)
    else:
        start = Path(".")
        names = [n for n in p.parts if n not in ("", ".")]
    try:
        if _AT:
            here = LayerDir(start, os.open(start, os.O_RDONLY | _DIRECTORY | _CLOEXEC))
        else:
            here = LayerDir(start, None)
    except FileNotFoundError:
        if create:
            raise
        return None
    for name in names:
        try:
            nxt = here.subdir(name, create=create, mode=mode)
        finally:
            here.close()
        if nxt is None:
            return None
        here = nxt
    here.path = p
    return here
