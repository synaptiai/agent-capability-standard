"""The file snapshot store (STANDARD v1.2 §4.4.1): a checkpoint's content,
what a rollback restores, and what it never reaches."""

from __future__ import annotations

import filecmp
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.state.memory import MemoryContext, MemoryStore
from grounded_agency.state.snapshots import FileSnapshotStore
from grounded_agency.workflows.idempotency import IdempotencyLog
from grounded_agency.workflows.runner import Host


def write(root: Path, rel: str, text: str, mode: int | None = None) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mode is not None:
        os.chmod(path, mode)
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "work"
    write(r, "a.txt", "a0")
    write(r, "src/b.py", "b0")
    write(r, "src/c.py", "c0")
    return r


def store(root: Path, **kw: object) -> FileSnapshotStore:
    return FileSnapshotStore(root, root.parent / "store", **kw)  # type: ignore[arg-type]


def test_round_trip_modified_deleted_created(root: Path) -> None:
    s = store(root)
    cap = s.capture("cp1", ["*"])
    assert cap.mechanism == "file_copy"
    assert cap.captured == ["a.txt", "src/b.py", "src/c.py"]
    assert cap.digest.startswith("sha256:")
    write(root, "a.txt", "a1")
    (root / "src/b.py").unlink()
    write(root, "src/new.py", "n")
    r = s.restore("cp1")
    assert r.restored and r.unrestored == []
    assert (root / "a.txt").read_text() == "a0"
    assert (root / "src/b.py").read_text() == "b0"
    assert not (root / "src/new.py").exists()
    ops = {c["item"]: c["operation"] for c in r.changes_reverted}
    assert ops == {"a.txt": "modify", "src/b.py": "delete", "src/new.py": "create"}
    assert r.verification == {"digest": cap.digest, "match": True}
    out = r.output()
    assert out["restored"] is True and out["verification"]["match"] is True


def test_restore_scope_subset(root: Path) -> None:
    s = store(root)
    s.capture("cp1", ["*"])
    write(root, "a.txt", "a1")
    write(root, "src/b.py", "b1")
    r = s.restore("cp1", ["src/*"])
    assert r.restored
    assert (root / "a.txt").read_text() == "a1"
    assert (root / "src/b.py").read_text() == "b0"


def test_excluded_and_oversized_and_links(root: Path, tmp_path: Path) -> None:
    write(root, "big.bin", "x" * 100)
    write(tmp_path / "elsewhere", "t.txt", "t")
    os.symlink(tmp_path / "elsewhere" / "t.txt", root / "link.txt")
    s = store(root, max_file_bytes=50)
    cap = s.capture("cp1", ["*"])
    assert "big.bin" in cap.excluded and "link.txt" in cap.excluded
    assert "big.bin" not in cap.captured
    # A rollback does not remove what the checkpoint left out.
    assert s.restore("cp1").restored
    assert (root / "big.bin").exists() and (root / "link.txt").is_symlink()


def test_secret_paths_are_excluded_by_default(root: Path) -> None:
    write(root, ".env", "TOKEN=x")
    write(root, "deploy/key.pem", "k")
    write(root, ".ssh/id_ed25519", "k")
    s = store(root)
    cap = s.capture("cp1", ["*"])
    for p in (".env", "deploy/key.pem"):
        assert p in cap.excluded and p not in cap.captured
    # A directory excluded whole is listed once.
    assert ".ssh/" in cap.excluded and ".ssh/id_ed25519" not in cap.captured
    assert s.restore("cp1", [".ssh/id_ed25519"]).unrestored == [
        {"item": ".ssh/id_ed25519", "reason": "not_captured"}
    ]


def test_a_symlinked_parent_fails_and_nothing_is_written_outside(
    root: Path, tmp_path: Path
) -> None:
    s = store(root)
    s.capture("cp1", ["*"])
    outside = tmp_path / "outside"
    outside.mkdir()
    import shutil

    shutil.rmtree(root / "src")
    os.symlink(outside, root / "src")
    r = s.restore("cp1")
    assert not r.restored
    assert {u["item"] for u in r.unrestored if u["reason"] == "failed"} == {
        "src/b.py",
        "src/c.py",
    }
    assert list(outside.iterdir()) == []


def test_discarded_content(root: Path) -> None:
    s = store(root)
    s.capture("cp1", ["*"])
    s.discard("cp1")
    r = s.restore("cp1")
    assert not r.restored
    assert r.unrestored == [{"item": "*", "reason": "discarded"}]
    assert list((root.parent / "store" / "objects").iterdir()) == []


def test_retention_ends_content(root: Path) -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    s = store(root, retention=timedelta(minutes=5), clock=lambda: now[0])
    cap = s.capture("cp1", ["*"])
    assert cap.output()["expires_at"] == "2026-01-01T00:05:00.000Z"
    now[0] += timedelta(minutes=5)
    assert s.restore("cp1").unrestored == [{"item": "*", "reason": "discarded"}]


def test_not_captured(root: Path) -> None:
    write(root, ".env", "TOKEN=x")
    s = store(root)
    s.capture("cp1", ["a.txt"])
    write(root, "a.txt", "a1")
    # A scope item the checkpoint never captured: not restored.
    r = s.restore("cp1", ["b.txt"])
    assert not r.restored
    assert r.unrestored == [{"item": "b.txt", "reason": "not_captured"}]
    assert (root / "a.txt").read_text() == "a1"
    # An excluded secret file named by the rollback.
    s.capture("cp2", ["*"])
    r = s.restore("cp2", [".env"])
    assert r.unrestored == [{"item": ".env", "reason": "not_captured"}]


def test_a_pattern_that_names_nothing_captured_is_not_captured(
    root: Path,
) -> None:
    """A rollback scope pattern that names no captured file, and that the
    checkpoint's scope does not cover, is not_captured, as a path is: the
    rollback cannot report restored for content it never had (§4.4.1)."""
    write(root, "README.md", "r0")
    s = store(root)
    s.capture("cp1", ["*.txt"])
    write(root, "README.md", "r1")
    r = s.restore("cp1", ["*.md"])
    assert not r.restored
    assert r.unrestored == [{"item": "*.md", "reason": "not_captured"}]
    assert (root / "README.md").read_text() == "r1"
    # A pattern the checkpoint's own scope covers had its absence captured:
    # files created since that it names are removed, and it is restored.
    s.capture("cp2", ["docs/*"])
    write(root, "docs/new.md", "n")
    r = s.restore("cp2", ["docs/*.md"])
    assert r.restored and r.unrestored == []
    assert not (root / "docs/new.md").exists()
    s.capture("cp3", ["*.md"])
    write(root, "NEW.md", "n")
    assert s.restore("cp3", ["*.md"]).restored


def test_a_directory_path_names_everything_under_it(root: Path) -> None:
    """A scope item that names a directory (`src`, `src/`, `./src`) names
    everything under it, in the checkpoint and in the rollback (§4.4.1)."""
    for i, item in enumerate(["src", "src/", "./src", str(root / "src")]):
        s = store(root)
        cap = s.capture(f"cp{i}", [item])
        assert cap.captured == ["src/b.py", "src/c.py"], item
        write(root, "src/b.py", "b1")
        write(root, "src/new.py", "n")
        r = s.restore(f"cp{i}", [item])
        assert r.restored and r.unrestored == [], item
        assert (root / "src/b.py").read_text() == "b0"
        assert not (root / "src/new.py").exists()
    # An item outside the root cannot be captured: it is listed in
    # `excluded`, and a rollback that names it reports it not_captured.
    s = store(root)
    cap = s.capture("out", ["../elsewhere", "a.txt"])
    assert cap.captured == ["a.txt"] and cap.excluded == ["../elsewhere"]
    r = s.restore("out", ["../elsewhere"])
    assert r.unrestored == [{"item": "../elsewhere", "reason": "not_captured"}]


def test_verification_compares_with_the_checkpoints_digest(root: Path) -> None:
    """`verification.digest` is over everything the checkpoint captured,
    as the checkpoint's was, so it is comparable with it (§4.4.1): a
    restore of part of it matches only when the rest is unchanged."""
    s = store(root)
    cap = s.capture("cp1", ["*"])
    write(root, "src/b.py", "b1")
    r = s.restore("cp1", ["src/b.py"])
    assert r.restored
    assert r.verification == {"digest": cap.digest, "match": True}
    write(root, "a.txt", "a1")
    write(root, "src/b.py", "b1")
    r = s.restore("cp1", ["src/b.py"])
    assert r.restored and r.verification["match"] is False
    assert r.verification["digest"] != cap.digest
    r = s.restore("cp1")
    assert r.verification == {"digest": cap.digest, "match": True}


def test_a_file_created_since_in_a_pattern_scope_is_removed(root: Path) -> None:
    s = store(root)
    s.capture("cp1", ["*.txt"])
    write(root, "c.txt", "new")
    r = s.restore("cp1", ["c.txt"])
    assert r.restored
    assert not (root / "c.txt").exists()


def test_private_modes(root: Path) -> None:
    write(root, "secret.cfg", "s", mode=0o600)
    write(root, "run.sh", "#!/bin/sh", mode=0o755)
    s = store(root)
    cap = s.capture("cp1", ["*"])
    base = root.parent / "store"
    for d in (base, base / "objects", base / "manifests"):
        assert stat.S_IMODE(d.stat().st_mode) == 0o700
    for f in [*(base / "objects").iterdir(), *(base / "manifests").iterdir()]:
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert "secret.cfg" in cap.captured
    os.chmod(root / "run.sh", 0o644)
    write(root, "run.sh", "changed")
    s.restore("cp1")
    assert stat.S_IMODE((root / "run.sh").stat().st_mode) == 0o755
    assert stat.S_IMODE((root / "secret.cfg").stat().st_mode) == 0o600


def test_ids_cannot_name_paths(root: Path) -> None:
    with pytest.raises(ValueError):
        store(root).capture("../x", ["*"])


def test_never_within_reach(tmp_path: Path) -> None:
    """With scope `*`, the plugin's .claude/, the tracker's state and marker,
    the idempotency log, the memory store and a saved run are never captured,
    and a rollback leaves each byte-identical (§4.4.1)."""
    root = tmp_path / "work"
    write(root, "app.cfg", "v0")
    write(root, ".claude/audit.log", "line1\n")
    write(root, ".audit/send-operations.log", "line1\n")
    snapshots = FileSnapshotStore(root, root / ".snapshots", exclude=())
    tracker = CheckpointTracker(
        checkpoint_dir=root / ".checkpoints",
        marker_dir=root / ".claude",
        snapshots=snapshots,
    )
    memory = MemoryStore(root / "state" / "memory.json")
    log = IdempotencyLog(root / "state" / "keys.jsonl")
    saved = write(root, "runs/r1.json", "{}")
    # The host registers its records with the tracker's snapshot store.
    Host(tracker, memory=memory, idempotency=log, protected_paths=[root / "runs"])
    memory.persist({"key": "k", "data": 1}, MemoryContext(session="s"))
    log.perform(
        {
            "idempotency_key": "r1:1",
            "capability": "send",
            "inputs": {"destination": "d"},
        },
        lambda: {"kind": "Output", "value": {"sent": True}},
    )
    checkpoint_id = tracker.create_checkpoint(scope=["*"], reason="r")
    output = tracker.checkpoint_output(checkpoint_id)
    assert output["captured"] == ["app.cfg"]
    assert output["excluded"] == [
        ".audit/",
        ".claude/",
        ".snapshots/",
        "runs/",
        "state/keys.jsonl",
        "state/memory.json",
    ]
    # Once the tracker has state, a capture lists its directory too.
    later = tracker.checkpoint_output(
        tracker.create_checkpoint(scope=["*"], reason="r")
    )
    assert ".checkpoints/" in later["excluded"]
    # Change everything, and create a file next to each.
    write(root, "app.cfg", "v1")
    write(root, ".claude/audit.log", "line1\nline2\n")
    write(root, ".audit/send-operations.log", "line1\nline2\n")
    write(root, ".audit/rollback-operations.log", "line1\n")
    tracker.consume_checkpoint()
    tracker.end_validity("the turn ended")
    memory.persist({"key": "k", "data": 2}, MemoryContext(session="s"))
    log.perform(
        {
            "idempotency_key": "r1:2",
            "capability": "send",
            "inputs": {"destination": "e"},
        },
        lambda: {"kind": "Output", "value": {"sent": True}},
    )
    write(root, "runs/r1.json", '{"changed": true}')
    for d in (".claude", ".checkpoints", "runs", "state"):
        write(root, f"{d}/new.txt", "n")
    copies = tmp_path / "before"
    import shutil

    shutil.copytree(root, copies, ignore=shutil.ignore_patterns(".snapshots"))
    host_records = [
        ".claude/audit.log",
        ".audit/send-operations.log",
        ".audit/rollback-operations.log",
        ".checkpoints/tracker_state.json",
        "state/memory.json",
        "state/keys.jsonl",
        "runs/r1.json",
    ]
    r = tracker.restore_checkpoint(checkpoint_id)
    assert r.restored
    assert (root / "app.cfg").read_text() == "v0"
    for rel in host_records:
        assert filecmp.cmp(root / rel, copies / rel, shallow=False), rel
    # Directories protected whole keep everything, new files included; an
    # ordinary file created since next to the protected files is removed.
    for d in (".claude", ".audit", ".checkpoints", "runs"):
        assert sorted(p.name for p in (root / d).iterdir()) == sorted(
            p.name for p in (copies / d).iterdir()
        )
    assert not (root / "state" / "new.txt").exists()
    # The used checkpoint stays used, and its marker absent.
    assert not tracker.has_valid_checkpoint()
    assert not (root / ".claude" / "checkpoint.ok").exists()
    assert saved.read_text() == '{"changed": true}'


def test_protection_cannot_be_undone(tmp_path: Path) -> None:
    root = tmp_path / "work"
    write(root, "keep/state.json", "1")
    s = FileSnapshotStore(
        root, tmp_path / "store", exclude=(), protected=[root / "keep"]
    )
    cap = s.capture("cp1", ["*"])
    assert "keep/" in cap.excluded and cap.captured == []
    assert "keep" in s.protected


def test_the_tracker_keeps_the_capture_and_prunes_content(tmp_path: Path) -> None:
    """A tracker with snapshots records what each checkpoint captured in its
    persisted state, and pruning a checkpoint from its history discards the
    content: a later rollback to it reports discarded (§4.4.1)."""
    root = tmp_path / "work"
    write(root, "a.txt", "a0")
    snapshots = FileSnapshotStore(root, tmp_path / "store")
    tracker = CheckpointTracker(
        checkpoint_dir=tmp_path / ".checkpoints", max_history=1, snapshots=snapshots
    )
    first = tracker.create_checkpoint(scope=["*"], reason="one")
    reloaded = CheckpointTracker(checkpoint_dir=tmp_path / ".checkpoints")
    found = reloaded.get_checkpoint_by_id(first)
    assert found is not None
    capture = found.metadata["capture"]
    assert capture["mechanism"] == "file_copy" and capture["captured"] == 1
    assert capture["digest"].startswith("sha256:")
    tracker.create_checkpoint(scope=["*"], reason="two")
    tracker.create_checkpoint(scope=["*"], reason="three")  # prunes `first`
    assert tracker.find_checkpoint(first) is not None  # archived
    assert tracker.restore_checkpoint(first).unrestored == [
        {"item": "*", "reason": "discarded"}
    ]
    with pytest.raises(KeyError):
        tracker.restore_checkpoint("chk_unknown")
    plain = CheckpointTracker(checkpoint_dir=tmp_path / ".other")
    taken = plain.create_checkpoint(scope=["*"], reason="r")
    with pytest.raises(NotImplementedError):
        plain.restore_checkpoint(taken)
