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


class TestMaximumAge:
    """The layer's maximum age (``expiry_minutes``) bounds every checkpoint,
    however it was taken (STANDARD 1.2.0 section 5.18.6)."""

    @pytest.mark.asyncio
    async def test_a_checkpoint_taken_through_the_tracker_obeys_the_layer(
        self, ontology_path: str, tmp_path: Path, fake_clock: FakeClock
    ) -> None:
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".cp"),
                approval="off",
                expiry_minutes=5,
            ),
            clock=fake_clock,
        )
        # The tracker's own API, which defaults to the tracker's maximum age.
        adapter.checkpoint_tracker.create_checkpoint(["*"], "host")
        fake_clock.advance(minutes=20)
        hook = adapter._make_pretooluse_safety_hook()
        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": "a"}}, "w1", None
        )
        assert _decision(result) == "deny"
        assert _reason(result).startswith("F501 CHECKPOINT_REQUIRED: ")

    def test_an_explicit_longer_expiry_is_cut_to_the_maximum_age(
        self, tmp_path: Path, fake_clock: FakeClock
    ) -> None:
        tracker = CheckpointTracker(
            checkpoint_dir=str(tmp_path), clock=fake_clock, max_age_minutes=5
        )
        checkpoint_id = tracker.create_checkpoint(["*"], "x", expiry_minutes=30)
        checkpoint = tracker.get_checkpoint_by_id(checkpoint_id)
        assert checkpoint is not None and checkpoint.expires_at is not None
        assert (checkpoint.expires_at - checkpoint.created_at).total_seconds() == 300
        fake_clock.advance(minutes=4)
        assert tracker.has_valid_checkpoint()
        fake_clock.advance(minutes=2)
        assert not tracker.has_valid_checkpoint()

    def test_a_checkpoint_read_back_from_state_obeys_the_maximum_age(
        self, tmp_path: Path, fake_clock: FakeClock
    ) -> None:
        CheckpointTracker(
            checkpoint_dir=str(tmp_path), clock=fake_clock
        ).create_checkpoint(["*"], "thirty minutes")
        later = CheckpointTracker(
            checkpoint_dir=str(tmp_path), clock=fake_clock, max_age_minutes=5
        )
        fake_clock.advance(minutes=6)
        assert later.validate_and_reserve("A") == (False, None)

    @pytest.mark.parametrize("minutes", [0, -1, 31, True, "5"])
    def test_a_maximum_age_beyond_the_cap_is_refused(
        self, tmp_path: Path, minutes: Any
    ) -> None:
        with pytest.raises(ValueError, match="max_age_minutes"):
            CheckpointTracker(checkpoint_dir=str(tmp_path), max_age_minutes=minutes)


class TestCheckpointLookups:
    def test_valid_checkpoint_id_is_what_a_hold_would_take(
        self, tracker: CheckpointTracker
    ) -> None:
        assert tracker.valid_checkpoint_id() is None
        c1 = tracker.create_checkpoint(["*"], "one")
        c2 = tracker.create_checkpoint(["*"], "two")
        assert tracker.valid_checkpoint_id() == c2
        assert tracker.validate_and_reserve("A") == (True, c2)
        assert tracker.valid_checkpoint_id() == c1
        assert tracker.validate_and_reserve("B") == (True, c1)
        assert tracker.valid_checkpoint_id() is None

    def test_has_commit_reads_any_checkpoint_of_the_scope(
        self, tracker: CheckpointTracker, fake_clock: FakeClock
    ) -> None:
        sha = "a" * 40
        start = fake_clock()
        tracker.create_checkpoint(["*"], "stash", metadata={"commit": sha})
        tracker.validate_and_reserve("A")
        tracker.consume_checkpoint("A")
        # Used, then expired: still the restore point it recorded.
        fake_clock.advance(minutes=60)
        assert tracker.has_commit(sha)
        assert tracker.has_commit(sha, since=start)
        fake_clock.advance(seconds=1)
        assert not tracker.has_commit(sha, since=fake_clock())
        assert not tracker.has_commit("b" * 40)


def test_the_engine_reuses_a_valid_checkpoint_from_the_history(
    ontology_path: str, tmp_path: Path, fake_clock: FakeClock
) -> None:
    """ensure_checkpoint_before_step returns the checkpoint a mutation step
    can use, not None, when the only valid one is in the history."""
    from grounded_agency.workflows.engine import WorkflowEngine, WorkflowStep

    tracker = CheckpointTracker(checkpoint_dir=str(tmp_path), clock=fake_clock)
    engine = WorkflowEngine(ontology_path=ontology_path, checkpoint_tracker=tracker)
    first = tracker.create_checkpoint(["*"], "A")
    tracker.create_checkpoint(["*"], "B")
    tracker.consume_checkpoint()  # B, the active one
    assert tracker.get_active_checkpoint_id() is None
    step = WorkflowStep(capability="mutate", purpose="x")
    assert engine.ensure_checkpoint_before_step(step, "wf") == first
    # With every valid checkpoint held, a new one is taken.
    assert tracker.validate_and_reserve("A") == (True, first)
    created = engine.ensure_checkpoint_before_step(step, "wf")
    assert created not in (None, first)
