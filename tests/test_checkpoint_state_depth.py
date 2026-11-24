"""A state file the tracker cannot parse, or cannot write, never cuts a
transition short (STANDARD 1.2.0 sections 5.18.5, 5.18.6, 5.18.8).

Security round 4, batch 2, defect 4: `json.loads` on about 100 KB of nested
`[` raises RecursionError, which is no ValueError. The tracker's load and
the merge each write does caught neither, and the merge read even a state
file git tracks (which the load refuses). So with a crafted file in the
repository:

- every persist raised, after the change it persisted was made in memory;
- the PreToolUse hook recorded a call's hold, then failed (R407) before it
  knew it held one, so the refused call kept the checkpoint;
- the Stop hook resolved that hold, which raised, so it never ended the
  checkpoints' validity, and a call of the next turn ran on a checkpoint
  taken before the boundary;
- an untracked file made the adapter's construction raise.

Now the state file's parse error is a ValueError (a file that does not
parse), a persist never raises, the merge skips a state file git tracks
unless it is the one the tracker wrote last, the boundary ends validity
whatever resolving the holds did, and the hook releases whatever the call
holds when its check fails.

Whether the decoder raises RecursionError on that text depends on the C
stack size: on GitHub's ubuntu-latest runner of November 2026 it returned
the nested lists, and the archive reader, which handed whatever a line
parsed to to `Checkpoint.from_dict`, raised AttributeError on a list. A
line or entry that parses to anything but an object is now read as one
that does not parse, and the tests that read the deep text take the
`deep_json` fixture (tests/conftest.py), which runs each both ways on any
machine.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from tests.conftest import DEEP_JSON, pre_tool_use

WRITE = {"file_path": "x.txt", "content": "y"}


def _git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=path,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        },
        check=True,
        capture_output=True,
        timeout=30,
    )


def _shipped(repo: Path, text: str) -> Path:
    """A repository whose `.checkpoints/tracker_state.json` git tracks."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo.mkdir()
    _git(repo, "init", "-q")
    state = repo / ".checkpoints" / "tracker_state.json"
    state.parent.mkdir()
    state.write_text(text, encoding="utf-8")
    _git(repo, "add", "-f", ".checkpoints/tracker_state.json")
    _git(repo, "commit", "-q", "-m", "state")
    return state.parent


def _adapter(checkpoint_dir: Path, **kw: Any) -> GroundedAgentAdapter:
    return GroundedAgentAdapter(
        GroundedAgentConfig(checkpoint_dir=str(checkpoint_dir), **kw)
    )


def _decision(result: dict[str, Any]) -> tuple[str | None, str]:
    out = result.get("hookSpecificOutput") or {}
    return out.get("permissionDecision"), str(out.get("permissionDecisionReason"))


def test_the_premise_is_one_of_the_two_readings() -> None:
    """The decoder installed here either raises RecursionError on the deep
    text, which no `except ValueError` catches, or returns the nested
    lists, which are no object: the two readings `deep_json` gives, and
    the code must read either as text that does not parse."""
    try:
        value = json.loads(DEEP_JSON)
    except RecursionError:
        pass
    else:
        assert isinstance(value, list)
    assert not issubclass(RecursionError, ValueError)


class TestTheTracker:
    @pytest.mark.parametrize("wrap", ["{}", '{{"history": {}}}'])
    def test_an_untracked_deep_file_starts_fresh(
        self, tmp_path: Path, wrap: str, deep_json: str
    ) -> None:
        """The construction raised RecursionError; every persist after it
        too."""
        (tmp_path / "tracker_state.json").write_text(
            wrap.format(deep_json), encoding="utf-8"
        )
        tracker = CheckpointTracker(checkpoint_dir=tmp_path)
        assert tracker.checkpoint_count == 0
        checkpoint = tracker.create_checkpoint(scope=["*"], reason="t")
        # The unreadable file was replaced by one the tracker can read.
        state = json.loads((tmp_path / "tracker_state.json").read_text("utf-8"))
        assert state["active"]["id"] == checkpoint

    def test_the_adapter_starts(self, tmp_path: Path, deep_json: str) -> None:
        (tmp_path / "tracker_state.json").write_text(
            '{"history": ' + deep_json + "}", encoding="utf-8"
        )
        adapter = _adapter(tmp_path)
        assert not adapter.has_valid_checkpoint()

    def test_a_tracked_deep_file_cuts_no_transition_short(
        self, tmp_path: Path, deep_json: str
    ) -> None:
        """Each of these raised RecursionError at its persist, after the
        change was made in memory."""
        tracker = CheckpointTracker(checkpoint_dir=_shipped(tmp_path / "r", deep_json))
        checkpoint = tracker.create_checkpoint(scope=["*"], reason="t")
        assert tracker.validate_and_reserve("c1", scope=("s", None)) == (
            True,
            checkpoint,
        )
        assert tracker.resolve_holds_in_scope(("s", None)) == ["c1"]
        tracker.create_checkpoint(scope=["*"], reason="t2")
        assert tracker.end_validity("turn ended")
        assert not tracker.has_valid_checkpoint()

    def test_the_merge_skips_a_state_file_git_tracks(self, tmp_path: Path) -> None:
        """The merge kept the checkpoints and holds of a shipped file in
        every file the tracker wrote."""
        shipped = {
            "active": None,
            "history": [
                {
                    "id": "chk_20260101_000000_shipped",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "scope": ["*"],
                    "reason": "shipped",
                }
            ],
            "reservations": [
                {"checkpoint_id": "chk_20260101_000000_shipped", "holder": "x"}
            ],
        }
        where = _shipped(tmp_path / "r", json.dumps(shipped))
        tracker = CheckpointTracker(checkpoint_dir=where)
        own = tracker.create_checkpoint(scope=["*"], reason="own")
        tracker.create_checkpoint(scope=["*"], reason="own again")
        state = json.loads((where / "tracker_state.json").read_text("utf-8"))
        ids = [c["id"] for c in state["history"]] + [state["active"]["id"]]
        assert own in ids and "chk_20260101_000000_shipped" not in ids
        assert state["reservations"] == []

    def test_a_tracker_still_merges_another_trackers_untracked_writes(
        self, tmp_path: Path
    ) -> None:
        """The control: two trackers on one directory outside git."""
        first = CheckpointTracker(checkpoint_dir=tmp_path)
        second = CheckpointTracker(checkpoint_dir=tmp_path)
        a = first.create_checkpoint(scope=["*"], reason="a")
        b = second.create_checkpoint(scope=["*"], reason="b")
        first.create_checkpoint(scope=["*"], reason="c")
        state = json.loads((tmp_path / "tracker_state.json").read_text("utf-8"))
        ids = [c["id"] for c in state["history"]] + [state["active"]["id"]]
        assert a in ids and b in ids

    def test_a_persist_never_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tracker = CheckpointTracker(checkpoint_dir=tmp_path)

        def boom(*_: Any) -> Any:
            raise RecursionError("deep")

        monkeypatch.setattr(CheckpointTracker, "_merged_state", boom)
        checkpoint = tracker.create_checkpoint(scope=["*"], reason="t")
        assert tracker.validate_and_reserve("c1") == (True, checkpoint)
        assert tracker.release_reservation("c1")
        assert tracker.end_validity("boundary") == [checkpoint]

    def test_a_deep_archive_line_is_skipped(
        self, tmp_path: Path, deep_json: str
    ) -> None:
        self._an_archive_line_is_skipped(tmp_path, deep_json)

    @pytest.mark.parametrize(
        "line", ["[1]", "3", '"x"', "null", "true", "{}", '{"id": "c"}']
    )
    def test_an_archive_line_that_is_no_checkpoint_is_skipped(
        self, tmp_path: Path, line: str
    ) -> None:
        """A line that parses to a list, a number, a string or null was
        handed to `Checkpoint.from_dict`, which raised AttributeError, which
        the reader did not catch: the archive could not be read at all."""
        self._an_archive_line_is_skipped(tmp_path, line)

    @staticmethod
    def _an_archive_line_is_skipped(tmp_path: Path, line: str) -> None:
        tracker = CheckpointTracker(checkpoint_dir=tmp_path, max_history=1)
        for n in range(3):
            tracker.create_checkpoint(scope=["*"], reason=f"t{n}")
        archive = tmp_path / "archive" / "pruned_checkpoints.jsonl"
        kept = [c.id for c in tracker.get_archived_checkpoints()]
        assert kept
        with archive.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        assert [c.id for c in tracker.get_archived_checkpoints()] == kept
        # A line after it is read too.
        tracker.create_checkpoint(scope=["*"], reason="t3")
        after = [c.id for c in tracker.get_archived_checkpoints()]
        assert after[: len(kept)] == kept and len(after) == len(kept) + 1


class TestTheAdapter:
    @pytest.mark.asyncio
    async def test_the_reported_route(self, tmp_path: Path, deep_json: str) -> None:
        """A tracked deep file: the Write of turn 1 was R407 and kept its
        hold, the Stop left every checkpoint valid, and once the file was
        gone a Write of turn 2 ran on a checkpoint from before the Stop."""
        where = _shipped(tmp_path / "r", deep_json)
        adapter = _adapter(where, approval="off")
        adapter.create_checkpoint(["*"], "t")
        adapter.create_checkpoint(["*"], "t2")
        decision, why = _decision(
            await pre_tool_use(adapter, "Write", WRITE, "c1", session_id="s1")
        )
        assert decision is None, why
        await adapter._make_boundary()({"session_id": "s1"}, None, None)
        assert not adapter.has_valid_checkpoint()
        (where / "tracker_state.json").unlink()
        decision, why = _decision(
            await pre_tool_use(adapter, "Write", WRITE, "c2", session_id="s1")
        )
        assert decision == "deny" and why.startswith("F501 CHECKPOINT_REQUIRED:")

    @pytest.mark.asyncio
    async def test_a_failed_check_releases_the_hold_it_made(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """validate_and_reserve recorded the hold, then raised: `held` was
        never set, so the R407 left the hold in place."""
        adapter = _adapter(tmp_path / "c", approval="off")
        tracker = adapter.checkpoint_tracker
        adapter.create_checkpoint(["*"], "t")
        reserve = tracker.validate_and_reserve

        def reserve_then_fail(*args: Any, **kw: Any) -> Any:
            reserve(*args, **kw)
            raise RuntimeError("after the hold")

        monkeypatch.setattr(tracker, "validate_and_reserve", reserve_then_fail)
        decision, why = _decision(await pre_tool_use(adapter, "Write", WRITE, "c1"))
        assert decision == "deny" and why.startswith("R407 SAFETY_CHECK_FAILED:")
        assert tracker.held_by("c1") is None
        monkeypatch.undo()
        # The checkpoint is still there for the next call.
        decision, why = _decision(await pre_tool_use(adapter, "Write", WRITE, "c2"))
        assert decision is None, why

    @pytest.mark.asyncio
    async def test_the_boundary_ends_validity_whatever_resolving_did(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _adapter(tmp_path / "c", approval="off")
        tracker = adapter.checkpoint_tracker
        adapter.create_checkpoint(["*"], "t")

        def fail(*_: Any, **__: Any) -> Any:
            raise RuntimeError("resolving failed")

        monkeypatch.setattr(tracker, "resolve_holds_in_scope", fail)
        await adapter._make_boundary()({"session_id": "s1"}, None, None)
        assert not adapter.has_valid_checkpoint()
