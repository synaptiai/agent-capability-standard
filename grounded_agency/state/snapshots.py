"""
File snapshots: a checkpoint's content (STANDARD v1.2 §4.4.1).

A checkpoint is a copy, kept by the host, of the state within its scope,
from which that state can be restored. :class:`FileSnapshotStore` keeps such
copies of the files under a root directory: each file's content once, by its
SHA-256 (``objects/``), and one manifest per checkpoint (``manifests/``)
naming the files it captured, what it left out, and a digest of the whole.

What a rollback never reaches (§4.4.1, "What a rollback does not restore"):
the record of what happened and the host's own records. The store never
captures, overwrites or removes

- the plugin's ``.claude/`` directory (its audit log and checkpoint marker)
  and ``.audit/`` (the audit logs its skills write),
- its own ``store_dir``,
- every path registered with :meth:`FileSnapshotStore.protect` (the
  checkpoint tracker's state and archive, the idempotency log, the memory
  store, saved runs, an audit log kept elsewhere).

That set only grows: ``exclude`` is applied on top of it, never in place of
it. Secret-bearing file names (:data:`SECRET_PATHS`) are excluded by default
(§6.7), and every copy is private: directories 0700, objects and manifests
0600, so a 0600 key file in scope never becomes a readable copy.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import posixpath
import re
import stat
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# The plugin's audit log and checkpoint marker (``.claude/``) and the audit
# logs its skills write (``.audit/``): never within a checkpoint's reach,
# whatever the caller excludes.
NEVER_DIRS: tuple[str, ...] = (".claude", ".audit")
ALWAYS_EXCLUDED: tuple[str, ...] = tuple(f"{d}/**" for d in NEVER_DIRS)

# File names that usually hold secrets (§6.7): a snapshot does not copy
# them unless the caller replaces ``exclude``. Informative defaults.
SECRET_PATHS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "**/*.pem",
    "*.key",
    "**/*.key",
    "*.p12",
    "**/*.p12",
    "*.pfx",
    "**/*.pfx",
    "id_rsa*",
    "**/id_rsa*",
    "id_ecdsa*",
    "**/id_ecdsa*",
    "id_ed25519*",
    "**/id_ed25519*",
    ".ssh/**",
    "**/.ssh/**",
    ".netrc",
    "**/.netrc",
    ".npmrc",
    "**/.npmrc",
    ".pypirc",
    "**/.pypirc",
    ".git-credentials",
    "**/.git-credentials",
    ".aws/credentials",
    "**/.aws/credentials",
    ".docker/config.json",
    "**/.docker/config.json",
)

DEFAULT_EXCLUDE: tuple[str, ...] = (".git/**", *SECRET_PATHS)

MECHANISM = "file_copy"

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_GLOB = re.compile(r"[*?\[]")
_MAX_MANIFEST_BYTES = 64 * 1024 * 1024


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Capture:
    """What a checkpoint holds (§4.4.1): the checkpoint capability's
    reporting outputs."""

    checkpoint_id: str
    mechanism: str
    captured: list[str]
    excluded: list[str]
    digest: str
    taken_at: datetime
    expires_at: datetime | None
    size: int

    def output(self) -> dict[str, Any]:
        """The ``checkpoint`` capability's output fields this capture fills."""
        out: dict[str, Any] = {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": _iso(self.taken_at),
            "mechanism": self.mechanism,
            "captured": list(self.captured),
            "excluded": list(self.excluded),
            "digest": self.digest,
            "size": self.size,
        }
        if self.expires_at is not None:
            out["expires_at"] = _iso(self.expires_at)
        return out


@dataclass(frozen=True, slots=True)
class Restore:
    """What a rollback did (§4.4.1). ``restored`` is true exactly when
    ``unrestored`` is empty."""

    restored: bool
    unrestored: list[dict[str, str]] = field(default_factory=list)
    changes_reverted: list[dict[str, str]] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)

    def output(self, not_covered: Sequence[dict[str, str]] = ()) -> dict[str, Any]:
        """The ``rollback`` capability's output, with the changes the
        checkpoint never covered (``transmitted``, ``delegated``...), which
        do not make ``restored`` false."""
        out: dict[str, Any] = {
            "restored": self.restored,
            "unrestored": list(self.unrestored),
            "changes_reverted": list(self.changes_reverted),
            "evidence_anchors": [],
        }
        if self.verification:
            out["verification"] = dict(self.verification)
        if not_covered:
            out["not_covered"] = [dict(n) for n in not_covered]
        return out


def _write_private(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically, 0600, never through a link."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        os.chmod(path, 0o700)


def _read_regular(path: Path, limit: int) -> bytes | None:
    """The bytes of a regular file, not followed through a final link;
    None when it is not one or is larger than ``limit``."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return None
        return f.read(limit + 1)


def _digest(entries: Iterable[tuple[str, str]]) -> str:
    h = hashlib.sha256()
    for path, sha in sorted(entries):
        h.update(f"{path}\0{sha}\n".encode())
    return f"sha256:{h.hexdigest()}"


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


def _subsumes(pattern: str, glob: str) -> bool:
    """Whether every path ``glob`` matches is sure to match ``pattern``: the
    same pattern, or a ``<literal>*`` pattern (``fnmatch``'s ``*`` crosses
    ``/``) whose literal ``glob`` starts with."""
    if pattern == glob:
        return True
    head = pattern[:-1]
    return pattern.endswith("*") and not _GLOB.search(head) and glob.startswith(head)


class FileSnapshotStore:
    """Content-addressed file copies for checkpoints (§4.4.1).

    ``root``: the directory whose files a checkpoint captures; a scope names
    files by their root-relative POSIX path, as ``fnmatch`` patterns
    (``*`` is everything the store can restore). ``store_dir``: where the
    copies are kept (never captured itself). ``exclude``: patterns the store
    does not copy (default: ``.git/`` and :data:`SECRET_PATHS`), listed in
    a capture's ``excluded``. ``protected``: paths no capture or restore
    ever touches, beside :data:`ALWAYS_EXCLUDED` and ``store_dir``.
    ``retention``: how long content is kept after the capture (``None``:
    until :meth:`discard`), reported as ``expires_at``.
    """

    def __init__(
        self,
        root: str | Path,
        store_dir: str | Path,
        *,
        exclude: Sequence[str] = DEFAULT_EXCLUDE,
        protected: Iterable[str | Path] = (),
        max_file_bytes: int = 50 * 2**20,
        retention: timedelta | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be more than 0")
        self._root = Path(root).resolve()
        self._store = Path(store_dir).resolve()
        self._exclude = tuple(exclude)
        self._max_file_bytes = max_file_bytes
        self._retention = retention
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._protected: set[str] = set()
        self.protect(self._store)
        for p in protected:
            self.protect(p)
        _private_dir(self._store)
        _private_dir(self._store / "objects")
        _private_dir(self._store / "manifests")

    # ------------------------------------------------------------------
    # What is never within reach
    # ------------------------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    def protect(self, path: str | Path) -> None:
        """Add a path (a file, or a directory and everything under it) that
        no capture copies and no restore overwrites or removes. It cannot be
        removed again; a path outside the root needs no protection and is
        ignored."""
        p = Path(path)
        if not p.is_absolute():
            p = Path.cwd() / p
        p = Path(os.path.realpath(p))
        try:
            rel = p.relative_to(self._root).as_posix()
        except ValueError:
            return
        self._protected.add("" if rel == "." else rel)

    @property
    def protected(self) -> frozenset[str]:
        """The root-relative paths no capture or restore touches (``""``:
        the whole root)."""
        return frozenset(self._protected)

    def _never(self, rel: str) -> bool:
        """Whether ``rel`` is never within a checkpoint's reach."""
        if _matches(rel, ALWAYS_EXCLUDED) or rel in NEVER_DIRS:
            return True
        return any(
            p == "" or rel == p or rel.startswith(p + "/") for p in self._protected
        )

    def _excluded_dir(self, rel: str) -> bool:
        """A directory ``exclude`` names whole, as ``<dir>/**`` with no
        wildcard in ``<dir>`` (``.git/**``): not walked."""
        return any(
            p.endswith("/**") and not _GLOB.search(p[:-3]) and rel == p[:-3]
            for p in self._exclude
        )

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def _check_id(self, checkpoint_id: str) -> None:
        if not isinstance(checkpoint_id, str) or not _ID.match(checkpoint_id):
            raise ValueError(
                f"checkpoint id {checkpoint_id!r} must match {_ID.pattern} "
                "(a manifest file name)"
            )

    def _manifest_path(self, checkpoint_id: str) -> Path:
        return self._store / "manifests" / f"{checkpoint_id}.json"

    def _object_path(self, sha: str) -> Path:
        return self._store / "objects" / sha

    def _item(self, item: str) -> tuple[str, bool]:
        """A scope item as a root-relative POSIX path or pattern, and
        whether it lies outside the root (where nothing can be captured).
        ``./`` and an absolute path under the root are made relative; an
        empty item or ``.`` is the whole root (``*``)."""
        s = str(item)
        if os.path.isabs(s):
            path = Path(os.path.normpath(s))
            if not _GLOB.search(s) and path.name:
                # Resolve the directories it is in, not a link it names.
                path = Path(os.path.realpath(path.parent)) / path.name
            try:
                s = path.relative_to(self._root).as_posix()
            except ValueError:
                return s, True
        while s.startswith("./"):
            s = s[2:]
        if not _GLOB.search(s):
            s = posixpath.normpath(s) if s else "."
            if s == ".." or s.startswith("../"):
                return s, True
        if s in ("", "."):
            return "*", False
        return s.rstrip("/") or "*", False

    def _expand(self, items: Sequence[str]) -> tuple[list[str], list[str]]:
        """The patterns a scope's items name (a path names a file, or a
        directory and everything under it, so ``src``, ``src/`` and
        ``./src`` each add ``src/*``), and the items outside the root."""
        patterns: list[str] = []
        outside: list[str] = []
        for item in items:
            s, out = self._item(item)
            if out:
                outside.append(str(item))
                continue
            for p in (s, f"{s}/*") if s != "*" else (s,):
                if p not in patterns:
                    patterns.append(p)
        return patterns, outside

    @staticmethod
    def _covers_dir(rel: str, scope: Sequence[str]) -> bool:
        """Whether a scope pattern could name something under ``rel``."""
        return any(
            fnmatch.fnmatchcase(rel, p)
            or fnmatch.fnmatchcase(rel + "/x", p)
            or p.startswith(rel + "/")
            for p in scope
        )

    def capture(self, checkpoint_id: str, scope: Sequence[str]) -> Capture:
        """Copy every regular file under the root that a ``scope`` item
        names: a root-relative ``fnmatch`` pattern, or a path naming a file
        or a directory (everything under it). Files ``exclude`` names, files
        over ``max_file_bytes`` and links are listed in ``excluded``, as is
        each never-within-reach directory the scope covers (once, as
        ``<dir>/``) and each item outside the root. A path the scope names
        that does not exist is captured as absent: a restore removes it."""
        self._check_id(checkpoint_id)
        patterns, outside = self._expand([str(s) for s in scope] or ["*"])
        files: dict[str, dict[str, Any]] = {}
        excluded: list[str] = list(outside)
        with self._lock:
            for dirpath, dirnames, filenames in os.walk(self._root, followlinks=False):
                here = Path(dirpath)
                base = here.relative_to(self._root).as_posix()
                prefix = "" if base == "." else base + "/"
                keep = []
                for d in sorted(dirnames):
                    rel = prefix + d
                    if self._never(rel) or self._excluded_dir(rel):
                        if self._covers_dir(rel, patterns):
                            excluded.append(rel + "/")
                        continue
                    if (here / d).is_symlink():
                        if self._covers_dir(rel, patterns):
                            excluded.append(rel + "/")
                        continue
                    keep.append(d)
                dirnames[:] = keep
                for name in sorted(filenames):
                    rel = prefix + name
                    if not _matches(rel, patterns):
                        continue
                    if self._never(rel) or _matches(rel, self._exclude):
                        excluded.append(rel)
                        continue
                    path = here / name
                    if path.is_symlink():
                        excluded.append(rel)
                        continue
                    try:
                        data = _read_regular(path, self._max_file_bytes)
                        mode = stat.S_IMODE(path.lstat().st_mode)
                    except OSError:
                        excluded.append(rel)
                        continue
                    if data is None or len(data) > self._max_file_bytes:
                        excluded.append(rel)
                        continue
                    sha = hashlib.sha256(data).hexdigest()
                    obj = self._object_path(sha)
                    if not obj.exists():
                        _write_private(obj, data)
                    files[rel] = {"sha256": sha, "mode": mode, "size": len(data)}
            taken_at = self._clock()
            expires_at = taken_at + self._retention if self._retention else None
            digest = _digest((p, e["sha256"]) for p, e in files.items())
            manifest = {
                "checkpoint_id": checkpoint_id,
                "scope": patterns,
                "files": files,
                "excluded": sorted(set(excluded)),
                "taken_at": _iso(taken_at),
                "expires_at": _iso(expires_at) if expires_at else None,
                "digest": digest,
            }
            _write_private(
                self._manifest_path(checkpoint_id),
                json.dumps(manifest, sort_keys=True).encode(),
            )
        return Capture(
            checkpoint_id=checkpoint_id,
            mechanism=MECHANISM,
            captured=sorted(files),
            excluded=sorted(set(excluded)),
            digest=digest,
            taken_at=taken_at,
            expires_at=expires_at,
            size=sum(e["size"] for e in files.values()),
        )

    def manifest(self, checkpoint_id: str) -> dict[str, Any] | None:
        """A checkpoint's manifest, or None when its content is gone."""
        self._check_id(checkpoint_id)
        path = self._manifest_path(checkpoint_id)
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as f:
            text = f.read(_MAX_MANIFEST_BYTES + 1)
        if len(text) > _MAX_MANIFEST_BYTES:
            raise ValueError(f"manifest {path} is too large")
        value = json.loads(text)
        if not isinstance(value, dict) or not isinstance(value.get("files"), dict):
            raise ValueError(f"manifest {path} is malformed")
        return value

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def _inside_root(self, path: Path) -> bool:
        real = os.path.realpath(path)
        return real == str(self._root) or real.startswith(str(self._root) + os.sep)

    def restore(
        self, checkpoint_id: str, scope: Sequence[str] | None = None
    ) -> Restore:
        """Return what the checkpoint captured, within ``scope`` (all of it
        when None; items as for :meth:`capture`), to its captured state:
        rewrite files that changed or went missing, remove files created
        since in the captured scope. An item ``scope`` names that the
        checkpoint did not capture is ``not_captured`` (a pattern that names
        no captured file included, unless the checkpoint's own scope covers
        all it names, so its absence was captured); content that is gone is
        ``discarded``."""
        self._check_id(checkpoint_id)
        with self._lock:
            manifest = self.manifest(checkpoint_id)
            if manifest is not None and manifest.get("expires_at"):
                expires = datetime.fromisoformat(
                    str(manifest["expires_at"]).replace("Z", "+00:00")
                )
                if self._clock() >= expires:
                    self._discard_locked(checkpoint_id)
                    manifest = None
            if manifest is None:
                return Restore(False, [{"item": "*", "reason": "discarded"}])
            return self._restore(manifest, list(scope) if scope else None)

    def _restore(self, manifest: dict[str, Any], scope: list[str] | None) -> Restore:
        files: dict[str, dict[str, Any]] = manifest["files"]
        patterns: list[str] = list(manifest.get("scope") or ["*"])
        listed: list[str] = list(manifest.get("excluded") or [])
        unrestored: list[dict[str, str]] = []
        reverted: list[dict[str, str]] = []

        def was_excluded(rel: str) -> bool:
            return any(
                rel == e or (e.endswith("/") and rel.startswith(e)) for e in listed
            )

        wanted: list[str] | None = None
        if scope is not None:
            wanted, outside = self._expand(scope)
            unrestored.extend({"item": o, "reason": "not_captured"} for o in outside)

        def in_scope(rel: str) -> bool:
            return wanted is None or _matches(rel, wanted)

        # Items the rollback names that the checkpoint never captured: one
        # in its `excluded` or never within reach, or one that names no
        # captured file and that the checkpoint's scope does not cover (a
        # path it covered that did not exist was captured as absent).
        for named in scope or []:
            norm, out = self._item(named)
            if out:
                continue
            names, _ = self._expand([norm])
            hits = [p for p in files if _matches(p, names)]
            excluded_hit = any(
                _matches(e.rstrip("/"), names) or e == named for e in listed
            ) or was_excluded(norm)
            covered = (
                _matches(norm, patterns)
                if not _GLOB.search(norm)
                else any(_subsumes(p, norm) for p in patterns)
            )
            if (
                self._never(norm)
                or (excluded_hit and not hits)
                or (not hits and not covered)
            ):
                unrestored.append({"item": named, "reason": "not_captured"})

        for rel in sorted(files):
            if not in_scope(rel) or self._never(rel):
                continue
            entry = files[rel]
            sha = str(entry["sha256"])
            path = self._root / rel
            if not self._inside_root(path.parent):
                unrestored.append(
                    {
                        "item": rel,
                        "reason": "failed",
                        "detail": "its directory resolves outside the root",
                    }
                )
                continue
            obj = self._object_path(sha)
            if not obj.is_file():
                unrestored.append({"item": rel, "reason": "discarded"})
                continue
            try:
                current: bytes | None
                if path.is_symlink():
                    current = None
                    existed = True
                else:
                    existed = path.exists()
                    current = (
                        _read_regular(path, self._max_file_bytes) if existed else None
                    )
                if current is not None and hashlib.sha256(current).hexdigest() == sha:
                    if stat.S_IMODE(path.lstat().st_mode) != entry["mode"]:
                        os.chmod(path, entry["mode"])
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                if not self._inside_root(path.parent):
                    raise OSError("its directory resolves outside the root")
                data = obj.read_bytes()
                tmp = path.with_name(f".{path.name}.restore.tmp")
                fd = os.open(
                    tmp,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                os.chmod(tmp, entry["mode"])
                os.replace(tmp, path)
                reverted.append(
                    {"item": rel, "operation": "modify" if existed else "delete"}
                )
            except OSError as e:
                unrestored.append({"item": rel, "reason": "failed", "detail": str(e)})

        # Files created since, in the captured scope (and the rollback's).
        for dirpath, dirnames, filenames in os.walk(self._root, followlinks=False):
            here = Path(dirpath)
            base = here.relative_to(self._root).as_posix()
            prefix = "" if base == "." else base + "/"
            dirnames[:] = [
                d
                for d in sorted(dirnames)
                if not (
                    self._never(prefix + d)
                    or self._excluded_dir(prefix + d)
                    or (here / d).is_symlink()
                )
            ]
            for name in sorted(filenames):
                rel = prefix + name
                if (
                    rel in files
                    or not _matches(rel, patterns)
                    or not in_scope(rel)
                    or self._never(rel)
                    or _matches(rel, self._exclude)
                    or was_excluded(rel)
                ):
                    continue
                try:
                    (here / name).unlink()
                    reverted.append({"item": rel, "operation": "create"})
                except OSError as e:
                    unrestored.append(
                        {"item": rel, "reason": "failed", "detail": str(e)}
                    )

        verification = self._verify(files, str(manifest.get("digest") or ""))
        return Restore(
            restored=not unrestored,
            unrestored=unrestored,
            changes_reverted=reverted,
            verification=verification,
        )

    def _verify(self, files: dict[str, dict[str, Any]], digest: str) -> dict[str, Any]:
        """The digest of what the checkpoint captured, as it is after the
        restore, computed as the capture's was, and whether it matches the
        checkpoint's ``digest`` (§4.4.1): over every captured file, so a
        restore of part of it matches only when the rest is unchanged too."""
        now: list[tuple[str, str]] = []
        for rel in files:
            try:
                data = _read_regular(self._root / rel, self._max_file_bytes)
            except OSError:
                data = None
            now.append(
                (rel, hashlib.sha256(data).hexdigest() if data is not None else "")
            )
        expected = digest or _digest(
            (rel, str(e["sha256"])) for rel, e in files.items()
        )
        current = _digest(now)
        return {"digest": current, "match": current == expected}

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    def discard(self, checkpoint_id: str) -> None:
        """Drop a checkpoint's content: its manifest, and every object no
        other manifest refers to. A later restore reports ``discarded``."""
        self._check_id(checkpoint_id)
        with self._lock:
            self._discard_locked(checkpoint_id)

    def _discard_locked(self, checkpoint_id: str) -> None:
        self._manifest_path(checkpoint_id).unlink(missing_ok=True)
        self._gc()

    def _gc(self) -> None:
        live: set[str] = set()
        for m in (self._store / "manifests").glob("*.json"):
            try:
                value = json.loads(m.read_bytes())
                live.update(str(e["sha256"]) for e in value["files"].values())
            except OSError, ValueError, KeyError, TypeError, AttributeError:
                # An unreadable manifest keeps every object.
                return
        for obj in (self._store / "objects").iterdir():
            if obj.name not in live and not obj.name.startswith("."):
                obj.unlink(missing_ok=True)
