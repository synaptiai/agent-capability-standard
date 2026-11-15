"""Holds per checkpoint, the newest valid checkpoint first, lapsed and
unresolved holds, and the adapter's one scope (STANDARD 1.2.0 sections
5.18.5 and 5.18.6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig
from grounded_agency.hooks.skill_tracker import create_checkpoint_recorder
from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from tests.conftest import FakeClock


@pytest.fixture
def tracker(tmp_path: Path, fake_clock: FakeClock) -> CheckpointTracker:
    return CheckpointTracker(checkpoint_dir=str(tmp_path), clock=fake_clock)


def _adapter(ontology_path: str, tmp_path: Path, **config: Any) -> GroundedAgentAdapter:
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".cp"),
            approval="off",
            **config,
        )
    )


def _decision(result: dict[str, Any]) -> str:
    return result.get("hookSpecificOutput", {}).get("permissionDecision", "allow")


def _reason(result: dict[str, Any]) -> str:
    return str(result["hookSpecificOutput"]["permissionDecisionReason"])


class TestTrackerHolds:
    def test_holds_are_per_checkpoint(self, tracker: CheckpointTracker) -> None:
        c1 = tracker.create_checkpoint(["*"], "one")
        assert tracker.validate_and_reserve("A") == (True, c1)
        c2 = tracker.create_checkpoint(["*"], "two")
        assert tracker.validate_and_reserve("B") == (True, c2)
        assert tracker.consume_checkpoint("A") == c1
        assert tracker.held_by("B") == c2
        assert tracker.consume_if_valid("B") == c2

    def test_the_newest_valid_checkpoint_first_then_an_earlier_one(
        self, tracker: CheckpointTracker
    ) -> None:
        c1 = tracker.create_checkpoint(["*"], "one")
        c2 = tracker.create_checkpoint(["*"], "two")
        assert tracker.validate_and_reserve("A") == (True, c2)
        assert tracker.consume_if_valid("A") == c2
        assert tracker.validate_and_reserve("B") == (True, c1)
        assert tracker.consume_if_valid("B") == c1
        assert tracker.validate_and_reserve("C") == (False, None)

    def test_every_valid_checkpoint_held_names_the_newest(
        self, tracker: CheckpointTracker
    ) -> None:
        c1 = tracker.create_checkpoint(["*"], "one")
        c2 = tracker.create_checkpoint(["*"], "two")
        tracker.validate_and_reserve("A")
        tracker.validate_and_reserve("B")
        assert tracker.validate_and_reserve("C") == (False, c2)
        assert {tracker.held_by("A"), tracker.held_by("B")} == {c1, c2}

    def test_a_hold_that_lapses_with_its_checkpoint_counts_as_used(
        self, tracker: CheckpointTracker, fake_clock: FakeClock
    ) -> None:
        c1 = tracker.create_checkpoint(["*"], "one")
        tracker.validate_and_reserve("A")
        fake_clock.advance(minutes=31)
        assert tracker.validate_and_reserve("B") == (False, None)
        used = tracker.get_checkpoint_by_id(c1)
        assert used is not None and used.consumed
        assert tracker.consume_if_valid("A") is None

    def test_consume_if_valid_after_a_boundary_uses_the_checkpoint(
        self, tracker: CheckpointTracker
    ) -> None:
        c1 = tracker.create_checkpoint(["*"], "one")
        tracker.validate_and_reserve("A")
        assert tracker.end_validity("turn ended") == [c1]
        assert tracker.consume_if_valid("A") is None
        ended = tracker.get_checkpoint_by_id(c1)
        assert ended is not None and ended.consumed and ended.invalidated_at is not None
        assert ended.metadata["invalidated_by"] == "turn ended"

    def test_holds_persist_and_are_used_on_reload(
        self, tmp_path: Path, tracker: CheckpointTracker
    ) -> None:
        c1 = tracker.create_checkpoint(["*"], "one")
        c2 = tracker.create_checkpoint(["*"], "two")
        tracker.validate_and_reserve("A")
        reloaded = CheckpointTracker(checkpoint_dir=str(tmp_path))
        # c2 was held: unresolved, used. c1 is free and valid.
        assert reloaded.validate_and_reserve("B") == (True, c1)
        held = reloaded.get_checkpoint_by_id(c2)
        assert held is not None and held.consumed

    def test_has_taken_since_survives_pruning(
        self, tmp_path: Path, fake_clock: FakeClock
    ) -> None:
        tracker = CheckpointTracker(checkpoint_dir=str(tmp_path), clock=fake_clock)
        start = fake_clock()
        tracker.create_checkpoint(["*"], "one")
        fake_clock.advance(minutes=31)
        tracker.clear_expired()
        assert tracker.checkpoint_count == 0
        assert tracker.has_taken_since(start)

    @pytest.mark.parametrize("minutes", [0, -1, 31])
    def test_the_maximum_age_is_capped(
        self, tracker: CheckpointTracker, minutes: int
    ) -> None:
        with pytest.raises(ValueError, match="30 minutes"):
            tracker.create_checkpoint(["*"], "x", expiry_minutes=minutes)

    def test_invalidated_at_round_trips(self, tmp_path: Path) -> None:
        tracker = CheckpointTracker(checkpoint_dir=str(tmp_path))
        c1 = tracker.create_checkpoint(["*"], "one")
        tracker.end_validity("boundary")
        reloaded = CheckpointTracker(checkpoint_dir=str(tmp_path))
        checkpoint = reloaded.get_checkpoint_by_id(c1)
        assert checkpoint is not None and checkpoint.invalidated_at is not None
        assert not reloaded.has_valid_checkpoint()


class TestAdapterScope:
    @pytest.mark.asyncio
    async def test_two_checkpoints_authorise_two_calls(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        adapter = _adapter(ontology_path, tmp_path)
        adapter.create_checkpoint(["*"], "one")
        adapter.create_checkpoint(["*"], "two")
        callback = adapter._make_permission_callback()
        from types import SimpleNamespace

        for call in ("w1", "w2"):
            result = await callback(
                "Write", {"file_path": call}, SimpleNamespace(tool_use_id=call)
            )
            assert result.behavior == "allow"
        third = await callback(
            "Write", {"file_path": "w3"}, SimpleNamespace(tool_use_id="w3")
        )
        assert third.message.startswith("F501 CHECKPOINT_REQUIRED:")

    @pytest.mark.asyncio
    async def test_overlapping_prompt_tool_calls_on_one_checkpoint(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path, checkpoint_dir=str(tmp_path / ".cp")
            )
        )
        options = adapter.wrap_options(
            ClaudeAgentOptions(permission_prompt_tool_name="mcp__approvals__prompt")
        )
        adapter.create_checkpoint(["*"], "one")
        (pre,) = options.hooks["PreToolUse"][-1].hooks
        call = {
            "tool_name": "Write",
            "tool_input": {"file_path": "a"},
            "session_id": "s1",
        }

        assert _decision(await pre(call, "w1", None)) == "ask"
        second = await pre(call, "w2", None)
        assert _reason(second).startswith("F501 CHECKPOINT_REQUIRED:")

        # Neither reports back; the turn ends: the hold counts as used.
        for entry in options.hooks["Stop"]:
            for hook in entry.hooks:
                await hook({"hook_event_name": "Stop", "session_id": "s1"}, None, None)
        assert not adapter.has_valid_checkpoint()
        assert adapter.checkpoint_tracker.held_by("w1") is None

    @pytest.mark.asyncio
    async def test_two_sessions_on_one_adapter_share_boundaries(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        adapter = _adapter(ontology_path, tmp_path)
        options = adapter.wrap_options(ClaudeAgentOptions())
        adapter.create_checkpoint(["*"], "session A's")
        for entry in options.hooks["Stop"]:
            for hook in entry.hooks:
                await hook({"hook_event_name": "Stop", "session_id": "B"}, None, None)
        (pre,) = options.hooks["PreToolUse"][-1].hooks
        result = await pre(
            {"tool_name": "Write", "tool_input": {}, "session_id": "A"}, "a1", None
        )
        assert _reason(result).startswith("F501 CHECKPOINT_REQUIRED:")
        assert adapter.call_records[-2]["decision"] == "boundary"


class TestRecorder:
    @pytest.mark.asyncio
    async def test_the_recorder_ignores_skills(
        self, tracker: CheckpointTracker
    ) -> None:
        """Neither Skill(checkpoint) takes a checkpoint nor Skill(rollback)
        ends one: rollback uses none (STANDARD 1.2.0 §5.2.2)."""
        c1 = tracker.create_checkpoint(["*"], "one")
        recorder = create_checkpoint_recorder(tracker)
        for skill in ("checkpoint", "rollback"):
            await recorder(
                {
                    "tool_name": "Skill",
                    "tool_input": {"skill": skill},
                    "tool_response": {},
                },
                "s1",
                None,
            )
        assert tracker.checkpoint_count == 1
        assert tracker.get_active_checkpoint_id() == c1
