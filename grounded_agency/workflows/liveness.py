"""Watching a wait's liveness (STANDARD v1.2 §5.13, §5.19.3): the host's side.

The executor does not schedule heartbeats or probes: a wait with
``liveness`` leaves them to the host, which answers ``{"kind":
"LivenessLost"}`` to the ``AwaitEvent`` action once the source has missed
``failure_threshold`` heartbeats or probes, ``interval`` apart. The step then
fails with R406. :class:`LivenessWatcher` keeps that count for one wait:

- ``push`` (the source sends heartbeats): a heartbeat is due ``interval``
  after the last one (or after the wait began). One that has not arrived
  by then is missed; a heartbeat that arrives at its due time is in time,
  as an event at a deadline is (§5.13). Each further ``interval`` without
  one is another miss.
- ``probe`` (the host polls the source every ``interval``): each probe that
  fails or goes unanswered is a miss (:meth:`LivenessWatcher.probe_failed`).

A heartbeat, or a probe the source answers, sets the count back to zero, so
a source that misses fewer than ``failure_threshold`` in a row is never
reported lost. Once the count reaches ``failure_threshold`` the loss is kept,
with the time it happened (:meth:`LivenessWatcher.lost_at`): a heartbeat
that arrives later does not undo it, and a host that compares that time
with the wait's deadline can tell R406 from R401 (lost liveness reported
after the deadline is R401). A wait run again by a loop or a ``retry`` is a
new wait: give it a new watcher.

Times are milliseconds on the run's clock (§5.19.3), the clock of the
action's ``deadline``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .. import _core
from .protocol import LivenessLostResponse

MODES = ("push", "probe")
DEFAULT_FAILURE_THRESHOLD = 3


class LivenessWatcher:
    """The consecutive missed heartbeats or probes of one wait, and whether
    its source is lost (§5.13).

    ``liveness`` is the wait's ``liveness`` member as the ``AwaitEvent``
    action carries it: ``mode`` (``push`` or ``probe``), ``interval`` (a
    duration longer than zero) and ``failure_threshold`` (an integer of at
    least 1, default 3). ``started_ms`` is when the wait began: the first
    heartbeat or probe is due ``interval`` after it.

    Raises:
        ValueError: when ``liveness`` is not one a valid workflow holds.
    """

    def __init__(self, liveness: Mapping[str, Any], started_ms: int) -> None:
        mode = liveness.get("mode")
        if mode not in MODES:
            raise ValueError(f"liveness mode must be one of {MODES}, not {mode!r}")
        interval = liveness.get("interval")
        if not isinstance(interval, str):
            raise ValueError(f"liveness interval must be a duration, not {interval!r}")
        interval_ms = _core.duration_ms(interval)
        if interval_ms <= 0:
            raise ValueError(
                f"liveness interval must be longer than zero, not {interval!r}"
            )
        threshold = liveness.get("failure_threshold", DEFAULT_FAILURE_THRESHOLD)
        if threshold is None:
            threshold = DEFAULT_FAILURE_THRESHOLD
        if (
            not isinstance(threshold, int)
            or isinstance(threshold, bool)
            or threshold < 1
        ):
            raise ValueError(
                f"liveness failure_threshold must be an integer of at least 1, "
                f"not {threshold!r}"
            )
        _check_time(started_ms)
        self.mode: str = mode
        self.interval_ms: int = interval_ms
        self.failure_threshold: int = threshold
        # The last time the source answered (or the wait began), and the
        # probes that failed since (probe mode).
        self._last_ms = started_ms
        self._failed_probes = 0
        self._lost_at: int | None = None

    @classmethod
    def for_action(
        cls, action: Mapping[str, Any], started_ms: int
    ) -> LivenessWatcher | None:
        """A watcher for an ``AwaitEvent`` action's wait, or None when the
        wait has no ``liveness``."""
        liveness = action.get("liveness")
        if liveness is None:
            return None
        return cls(liveness, started_ms)

    def heartbeat(self, at_ms: int) -> None:
        """The source answered at ``at_ms``: a heartbeat arrived (``push``) or
        a probe succeeded (``probe``). The count of misses goes back to zero,
        and the next heartbeat or probe is due ``interval`` later. A loss
        already reached, by ``at_ms`` included, is kept."""
        self._advance(at_ms)
        self._last_ms = at_ms
        self._failed_probes = 0

    def probe_failed(self, at_ms: int) -> None:
        """A probe at ``at_ms`` failed or went unanswered (``probe`` mode
        only): one more miss.

        Raises:
            ValueError: in ``push`` mode, where misses are counted from the
                time that passed.
        """
        if self.mode != "probe":
            raise ValueError("probe_failed is for liveness mode probe")
        self._advance(at_ms)
        self._last_ms = at_ms
        self._failed_probes += 1
        if self._failed_probes >= self.failure_threshold and self._lost_at is None:
            self._lost_at = at_ms

    def misses(self, now_ms: int) -> int:
        """The consecutive misses at ``now_ms``: in ``push`` mode the
        heartbeats due before ``now_ms`` since the source last answered
        (one due at ``now_ms`` is not missed yet); in ``probe`` mode the
        probes that failed since it last answered."""
        _check_time(now_ms)
        if now_ms < self._last_ms:
            raise ValueError(
                f"time {now_ms} is before the last one recorded ({self._last_ms})"
            )
        if self.mode == "probe":
            return self._failed_probes
        if now_ms == self._last_ms:
            return 0
        return (now_ms - self._last_ms - 1) // self.interval_ms

    def lost_at(self, now_ms: int) -> int | None:
        """When the source was lost, if it was by ``now_ms``: the moment its
        ``failure_threshold``-th consecutive miss was counted; else None."""
        self._advance(now_ms)
        return self._lost_at

    def lost(self, now_ms: int) -> bool:
        """Whether the source was lost by ``now_ms``."""
        return self.lost_at(now_ms) is not None

    def next_check_ms(self, now_ms: int) -> int:
        """When to look again, after ``now_ms``: in ``probe`` mode when the
        next probe is due (``interval`` after the last one, or after the
        wait began); in ``push`` mode when the next miss is counted, 1 ms
        after the next heartbeat is due."""
        misses = self.misses(now_ms)
        if self.mode == "probe":
            return self._last_ms + self.interval_ms
        return self._last_ms + (misses + 1) * self.interval_ms + 1

    def response(self, now_ms: int) -> LivenessLostResponse | None:
        """The answer to the ``AwaitEvent`` action at ``now_ms``:
        ``{"kind": "LivenessLost"}`` once the source is lost, else None
        (keep waiting, or answer with the event or ``None`` as before)."""
        if self.lost(now_ms):
            return {"kind": "LivenessLost"}
        return None

    def _advance(self, now_ms: int) -> None:
        """Count the misses up to ``now_ms`` and keep a loss they reach."""
        misses = self.misses(now_ms)
        if self._lost_at is None and misses >= self.failure_threshold:
            if self.mode == "push":
                # The threshold-th heartbeat was missed 1 ms after it was due.
                self._lost_at = (
                    self._last_ms + self.failure_threshold * self.interval_ms + 1
                )


def _check_time(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"a time is whole milliseconds, not {value!r}")
