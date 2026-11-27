"""The reference liveness watcher (STANDARD v1.2 §5.13, §5.19.3): a source is
reported lost only after ``failure_threshold`` consecutive misses, and a
heartbeat or an answered probe sets the count back to zero.

packages/acs-core/test/liveness.test.ts holds the same cases for the
TypeScript watcher."""

from __future__ import annotations

import pytest

from grounded_agency.workflows import LivenessWatcher

MIN = 60_000


def push(threshold: int | None = 3) -> LivenessWatcher:
    liveness = {"mode": "push", "interval": "1m"}
    if threshold is not None:
        liveness["failure_threshold"] = threshold
    return LivenessWatcher(liveness, 0)


class TestPush:
    def test_a_source_that_misses_one_heartbeat_and_recovers_is_never_lost(
        self,
    ) -> None:
        w = push()
        assert w.misses(MIN) == 0  # due at 1m: in time
        assert w.misses(MIN + 1) == 1
        assert w.response(MIN + 1) is None
        w.heartbeat(MIN + 30_000)
        assert w.misses(MIN + 30_000) == 0
        # Two more misses after it are still fewer than three.
        assert w.misses(3 * MIN + 30_000 + 1) == 2
        assert not w.lost(3 * MIN + 30_000 + 1)
        w.heartbeat(3 * MIN + 40_000)
        assert w.response(5 * MIN) is None
        assert w.lost_at(5 * MIN) is None

    def test_a_source_that_keeps_missing_is_lost_at_its_third_miss(self) -> None:
        w = push()
        assert w.misses(3 * MIN) == 2
        assert w.response(3 * MIN) is None
        assert w.misses(3 * MIN + 1) == 3
        assert w.response(3 * MIN + 1) == {"kind": "LivenessLost"}
        assert w.lost_at(5 * MIN) == 3 * MIN + 1

    def test_a_heartbeat_after_the_loss_does_not_undo_it(self) -> None:
        w = push()
        w.heartbeat(10 * MIN)
        assert w.lost(10 * MIN)
        assert w.lost_at(10 * MIN) == 3 * MIN + 1
        assert w.misses(10 * MIN) == 0

    def test_the_default_threshold_is_three(self) -> None:
        assert push(None).failure_threshold == 3
        w = LivenessWatcher(
            {"mode": "push", "interval": "1m", "failure_threshold": None}, 0
        )
        assert w.failure_threshold == 3
        assert not w.lost(3 * MIN)
        assert w.lost(3 * MIN + 1)

    def test_a_threshold_of_one_is_lost_at_the_first_miss(self) -> None:
        w = push(1)
        assert not w.lost(MIN)
        assert w.lost(MIN + 1)

    def test_next_check_is_when_the_next_miss_is_counted(self) -> None:
        w = push()
        assert w.next_check_ms(0) == MIN + 1
        assert w.next_check_ms(MIN + 1) == 2 * MIN + 1
        w.heartbeat(MIN + 500)
        assert w.next_check_ms(MIN + 500) == 2 * MIN + 501

    def test_the_wait_starts_the_count(self) -> None:
        w = LivenessWatcher({"mode": "push", "interval": "10s"}, 1_000_000)
        assert w.misses(1_010_000) == 0
        assert w.misses(1_010_001) == 1
        assert w.lost_at(1_030_001) == 1_030_001

    def test_probe_failed_is_for_probe_mode(self) -> None:
        with pytest.raises(ValueError, match="probe"):
            push().probe_failed(MIN)


class TestProbe:
    def probe(self) -> LivenessWatcher:
        return LivenessWatcher(
            {"mode": "probe", "interval": "10m", "failure_threshold": 3}, 0
        )

    def test_a_source_that_fails_one_probe_and_recovers_is_never_lost(
        self,
    ) -> None:
        w = self.probe()
        assert w.next_check_ms(0) == 10 * MIN
        w.probe_failed(10 * MIN)
        assert w.misses(10 * MIN) == 1
        w.heartbeat(20 * MIN)
        assert w.misses(20 * MIN) == 0
        w.probe_failed(30 * MIN)
        w.probe_failed(40 * MIN)
        assert w.misses(40 * MIN) == 2
        assert w.response(40 * MIN) is None
        w.heartbeat(50 * MIN)
        # Time alone counts nothing in probe mode.
        assert w.response(500 * MIN) is None

    def test_a_source_that_keeps_failing_is_lost_at_its_third_probe(self) -> None:
        w = self.probe()
        for k in (1, 2):
            w.probe_failed(k * 10 * MIN)
            assert w.response(k * 10 * MIN) is None
        assert w.next_check_ms(20 * MIN) == 30 * MIN
        w.probe_failed(30 * MIN)
        assert w.response(30 * MIN) == {"kind": "LivenessLost"}
        assert w.lost_at(30 * MIN) == 30 * MIN
        w.heartbeat(40 * MIN)
        assert w.lost(40 * MIN)

    def test_an_overdue_probe_is_due_now_never_in_the_past(self) -> None:
        w = self.probe()
        assert w.next_check_ms(25 * MIN) == 25 * MIN
        w.probe_failed(25 * MIN)
        assert w.next_check_ms(25 * MIN) == 35 * MIN
        assert w.next_check_ms(40 * MIN) == 40 * MIN


class TestConstruction:
    def test_for_action_reads_the_wait_and_none_without_liveness(self) -> None:
        action = {
            "kind": "AwaitEvent",
            "liveness": {"mode": "probe", "interval": "PT30S", "failure_threshold": 2},
        }
        w = LivenessWatcher.for_action(action, 5)
        assert w is not None
        assert (w.mode, w.interval_ms, w.failure_threshold) == ("probe", 30_000, 2)
        assert LivenessWatcher.for_action({"liveness": None}, 0) is None
        assert LivenessWatcher.for_action({}, 0) is None

    @pytest.mark.parametrize(
        "liveness",
        [
            {"mode": "poll", "interval": "1m"},
            {"interval": "1m"},
            {"mode": "push"},
            {"mode": "push", "interval": 60},
            {"mode": "push", "interval": "a minute"},
            {"mode": "push", "interval": "0s"},
            {"mode": "push", "interval": "1m", "failure_threshold": 0},
            {"mode": "push", "interval": "1m", "failure_threshold": True},
            {"mode": "push", "interval": "1m", "failure_threshold": 2.5},
        ],
    )
    def test_a_liveness_no_valid_workflow_holds_is_refused(
        self, liveness: dict
    ) -> None:
        with pytest.raises(ValueError):
            LivenessWatcher(liveness, 0)

    def test_time_must_not_go_back(self) -> None:
        w = push()
        w.heartbeat(MIN)
        with pytest.raises(ValueError, match="before"):
            w.misses(MIN - 1)
        with pytest.raises(ValueError, match="before"):
            w.heartbeat(MIN - 1)
        with pytest.raises(ValueError, match="milliseconds"):
            w.misses(1.5)  # type: ignore[arg-type]
