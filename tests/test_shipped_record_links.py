"""A repository ships a symbolic link where the layer keeps its records
(spec/SECURITY.md section 5.5).

git stores links, so a clone can ship ``.checkpoints``,
``.checkpoints/archive`` or ``.checkpoints/archive/pruned_checkpoints.jsonl``
as one, and ``.snapshots`` (the snapshot store the SDK guide names). The
tracker writes its state there on every checkpoint and appends to the
archive when it prunes the history, after 100 checkpoints; a checkpoint
costs the model one call that needs no checkpoint and no approval (``git
stash create``, a bound ``checkpoint`` tool), and a bound tool's ``reason``
and ``scope`` are text the model writes. These tests check that nothing is
written or read through such a link, that an archive git tracks is neither
read nor written, that the prune is logged, and that the tracker keeps
working in memory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.state.snapshots import FileSnapshotStore

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}
RC = "# user's bashrc\n"
ARCHIVE = Path(".checkpoints") / "archive" / "pruned_checkpoints.jsonl"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **ENV},
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def ship(project: Path, rel: Path | str, target: Path) -> None:
    """Commit a link at ``project/rel`` to ``target``, as a clone ships it."""
    link = project / rel
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "ship")
    assert git(project, "ls-files", "-s", "--", str(rel)).startswith("120000 ")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q")
    (path / "app.txt").write_text("app\n")
    git(path, "add", "app.txt")
    git(path, "commit", "-q", "-m", "init")
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    (path / ".bashrc").write_text(RC)
    return path


def tracker_in(
    project: Path, relative: bool, monkeypatch: pytest.MonkeyPatch, **kw: Any
) -> CheckpointTracker:
    """A tracker on the project's ``.checkpoints``: the default relative
    path from the project, as the adapter runs there, or the absolute one."""
    if relative:
        monkeypatch.chdir(project)
        return CheckpointTracker(**kw)
    return CheckpointTracker(checkpoint_dir=project / ".checkpoints", **kw)


def take(tracker: CheckpointTracker, n: int, reason: str = "r") -> list[str]:
    return [tracker.create_checkpoint(scope=["*"], reason=reason) for _ in range(n)]


@pytest.mark.parametrize("relative", [True, False], ids=["relative", "absolute"])
class TestTheTrackerFollowsNoShippedLink:
    def test_the_archive_file(
        self,
        project: Path,
        home: Path,
        relative: bool,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        ship(project, ARCHIVE, home / ".bashrc")
        tracker = tracker_in(project, relative, monkeypatch, max_history=2)
        with caplog.at_level(logging.WARNING):
            ids = take(tracker, 5, reason="$(touch RAN)")
        assert (home / ".bashrc").read_text() == RC
        # The prune happened, and was logged with the ids it dropped.
        assert tracker.checkpoint_count == 3
        assert "without archiving" in caplog.text
        assert ids[0] in caplog.text
        # The tracker still authorises its calls.
        assert tracker.validate_and_reserve("call")[0]

    def test_the_archive_directory(
        self,
        project: Path,
        home: Path,
        relative: bool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ship(project, ARCHIVE.parent, home)
        before = sorted(os.listdir(home))
        tracker = tracker_in(project, relative, monkeypatch, max_history=2)
        take(tracker, 5)
        assert sorted(os.listdir(home)) == before
        assert tracker.get_archived_checkpoints() == []

    def test_the_checkpoint_directory(
        self,
        project: Path,
        home: Path,
        relative: bool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The link's target already holds a state file: it is not read.
        outside = CheckpointTracker(checkpoint_dir=home)
        planted = outside.create_checkpoint(scope=["*"], reason="planted")
        before = {p.name: p.read_bytes() for p in home.iterdir() if p.is_file()}
        ship(project, ".checkpoints", home)
        tracker = tracker_in(project, relative, monkeypatch, max_history=2)
        assert tracker.find_checkpoint(planted) is None
        take(tracker, 5)
        after = {p.name: p.read_bytes() for p in home.iterdir() if p.is_file()}
        assert after == before
        assert not (home / "archive").exists()
        assert tracker.validate_and_reserve("call")[0]

    def test_a_linked_archive_is_not_read(
        self,
        project: Path,
        home: Path,
        relative: bool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        elsewhere = CheckpointTracker(checkpoint_dir=home / "state", max_history=1)
        first = take(elsewhere, 3)[0]
        archived = home / "state" / "archive" / "pruned_checkpoints.jsonl"
        assert first in archived.read_text()
        ship(project, ARCHIVE, archived)
        tracker = tracker_in(project, relative, monkeypatch)
        assert tracker.get_archived_checkpoints() == []
        assert tracker.find_checkpoint(first) is None


def test_a_tracked_archive_is_neither_read_nor_written(
    project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    source = CheckpointTracker(checkpoint_dir=project.parent / "src", max_history=1)
    shipped_id = take(source, 3)[0]
    shipped = (
        project.parent / "src" / "archive" / "pruned_checkpoints.jsonl"
    ).read_text()
    (project / ARCHIVE).parent.mkdir(parents=True)
    (project / ARCHIVE).write_text(shipped)
    git(project, "add", "-f", str(ARCHIVE))
    git(project, "commit", "-q", "-m", "ship")
    monkeypatch.chdir(project)
    tracker = CheckpointTracker(max_history=2)
    assert tracker.get_archived_checkpoints() == []
    assert tracker.find_checkpoint(shipped_id) is None
    with caplog.at_level(logging.WARNING):
        take(tracker, 5)
    assert (project / ARCHIVE).read_text() == shipped
    assert "git tracks" in caplog.text


class TestControls:
    def test_an_ordinary_archive_is_written_and_read(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        tracker = CheckpointTracker(max_history=2)
        ids = take(tracker, 5)
        archived = tracker.get_archived_checkpoints()
        assert [c.id for c in archived] == ids[:2]
        assert tracker.find_checkpoint(ids[0]) is not None
        mode = stat.S_IMODE((project / ARCHIVE).stat().st_mode)
        assert mode == 0o600

    def test_a_linked_parent_of_an_absolute_directory_is_the_hosts(
        self, tmp_path: Path
    ) -> None:
        real = tmp_path / "real"
        real.mkdir()
        (tmp_path / "alias").symlink_to(real)
        tracker = CheckpointTracker(
            checkpoint_dir=tmp_path / "alias" / ".checkpoints", max_history=1
        )
        ids = take(tracker, 3)
        assert (real / ".checkpoints" / "tracker_state.json").is_file()
        assert [c.id for c in tracker.get_archived_checkpoints()] == ids[:1]
        assert CheckpointTracker(
            checkpoint_dir=tmp_path / "alias" / ".checkpoints"
        ).find_checkpoint(ids[-1])


class TestTheSnapshotStoreFollowsNoShippedLink:
    def test_a_linked_store_directory(
        self, project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        os.chmod(home, 0o755)
        ship(project, ".snapshots", home)
        monkeypatch.chdir(project)
        with pytest.raises(ValueError, match="symbolic link"):
            FileSnapshotStore(".", ".snapshots")
        with pytest.raises(ValueError, match="symbolic link"):
            FileSnapshotStore(project, project / ".snapshots")
        assert sorted(os.listdir(home)) == [".bashrc"]
        assert stat.S_IMODE(home.stat().st_mode) == 0o755

    @pytest.mark.parametrize("name", ["objects", "manifests"])
    def test_a_linked_directory_inside_it(
        self, project: Path, home: Path, name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ship(project, Path(".snapshots") / name, home)
        monkeypatch.chdir(project)
        with pytest.raises(ValueError, match="symbolic link"):
            FileSnapshotStore(".", ".snapshots")
        assert sorted(os.listdir(home)) == [".bashrc"]

    def test_an_ordinary_store_still_works(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        store = FileSnapshotStore(".", ".snapshots")
        assert stat.S_IMODE((project / ".snapshots").stat().st_mode) == 0o700
        store.capture("chk_1", ["app.txt"])
        (project / "app.txt").write_text("changed\n")
        store.restore("chk_1", None)
        assert (project / "app.txt").read_text() == "app\n"


def test_the_adapter_writes_nothing_through_the_link(
    project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reproduction: the adapter in a clone that ships the archive as a
    link, its default checkpoint_dir, 102 calls of a bound checkpoint tool
    whose reason and scope the model writes, each through the hooks
    wrap_options installs. The 102nd prunes the history."""
    from claude_agent_sdk import ClaudeAgentOptions

    from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

    ship(project, ARCHIVE, home / ".bashrc")
    monkeypatch.chdir(project)
    adapter = GroundedAgentAdapter(GroundedAgentConfig())
    adapter.mapper.register_mcp_tool("mcp__ops__snapshot", capability_id="checkpoint")
    options = adapter.wrap_options(ClaudeAgentOptions())
    pre = [h for e in options.hooks["PreToolUse"] for h in e.hooks]
    post = [h for e in options.hooks["PostToolUse"] for h in e.hooks]
    payload = "$(touch RAN)"
    output = json.dumps(
        {
            "checkpoint_id": "x",
            "timestamp": "2026-11-23T12:00:00Z",
            "evidence_anchors": [],
        }
    )

    async def run() -> None:
        for i in range(102):
            call = {
                "tool_name": "mcp__ops__snapshot",
                "tool_input": {"reason": payload, "scope": [payload]},
                "tool_use_id": f"c{i}",
                "cwd": str(project),
                "session_id": "s",
                "permission_mode": "default",
            }
            for hook in pre:
                out = await hook(call, f"c{i}", None)
                decision = (out or {}).get("hookSpecificOutput", {})
                assert decision.get("permissionDecision") in (None, "allow"), decision
            result = {**call, "tool_response": [{"type": "text", "text": output}]}
            for hook in post:
                await hook(result, f"c{i}", None)

    asyncio.run(run())
    assert adapter.checkpoint_tracker.checkpoint_count == 101
    assert (home / ".bashrc").read_text() == RC
