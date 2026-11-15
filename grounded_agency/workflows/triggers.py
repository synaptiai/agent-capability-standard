"""Evaluating triggers (STANDARD v1.2 §5.10.2): the host's side.

The executor never reads a workflow's triggers; the host evaluates them.
This module holds what a host needs to do it as the Standard says:

- :func:`trigger_attendance`: the attendance of the runs a trigger starts;
- :func:`next_fire`: a schedule's next fire time, from the core (one
  function for every binding: RFC 5545 for clock changes, ``every`` anchored
  at the Unix epoch);
- :class:`OverlapGate`: whether a fire time starts a run, by the trigger's
  ``overlap`` and the runs it started that are in progress;
- :class:`EventGate`: whether an event starts a run of an event trigger: it
  matches, the host's sender policy admits it, and no run of the trigger
  started for its ``event_id`` yet.

``tests/conformance/triggers/*.json`` are the normative vectors (§10.3).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableSet
from typing import Any, Literal

from .. import _core

ATTENDANCES = ("attended", "unattended")
OVERLAPS = ("skip", "buffer_one", "allow_all")


def trigger_attendance(trigger: Mapping[str, Any], invoker: str | None = None) -> str:
    """The attendance of a run ``trigger`` starts (§5.10): for ``invoke``,
    always the invoker's (attended when ``invoker`` is not given), whatever
    the trigger declares, as the executor applies it; else its declared
    ``attendance``, else the default of its kind: ``manual`` attended,
    ``schedule`` and ``event`` unattended."""
    declared = trigger.get("attendance")
    if declared is not None and declared not in ATTENDANCES:
        raise ValueError(f"attendance must be one of {ATTENDANCES}, not {declared!r}")
    kind = trigger.get("kind")
    if kind == "invoke":
        return invoker or "attended"
    if kind not in ("manual", "schedule", "event"):
        raise ValueError(f"unknown trigger kind {kind!r}")
    if declared is not None:
        return str(declared)
    return "attended" if kind == "manual" else "unattended"


def next_fire(schedule: Mapping[str, Any], after_ms: int) -> int | None:
    """The first fire time of ``schedule`` (a validated ``triggers[].schedule``)
    strictly after ``after_ms``, in milliseconds since the Unix epoch, or
    None when there is none (§5.10.2)."""
    return _core.next_fire(dict(schedule), after_ms)


class OverlapGate:
    """The overlap decisions of one schedule trigger (§5.10.2), for the runs
    it started. Call :meth:`fire` at each fire time, :meth:`missed` when the
    host resumes after fire times passed while it was stopped (they count,
    together, as one), :meth:`ended` when a run it started ends (a run that
    ends ``deferred`` included) and :meth:`resumed` when such a run is
    resumed (§5.14.1): it is in progress again."""

    def __init__(self, overlap: str | None = None) -> None:
        mode = overlap or "skip"
        if mode not in OVERLAPS:
            raise ValueError(f"overlap must be one of {OVERLAPS}, not {overlap!r}")
        self.overlap = mode
        self.in_progress = 0
        self.waiting = False

    def fire(self) -> Literal["start", "buffered", "skipped"]:
        """A fire time: ``start`` a run now, hold it (``buffered``, for
        ``buffer_one``) or drop it (``skipped``)."""
        if self.in_progress == 0 or self.overlap == "allow_all":
            self.in_progress += 1
            return "start"
        if self.overlap == "buffer_one" and not self.waiting:
            self.waiting = True
            return "buffered"
        return "skipped"

    def missed(self) -> Literal["start", "buffered", "skipped"]:
        """Fire times passed while the host was not evaluating the trigger:
        together, one fire time now."""
        return self.fire()

    def ended(self) -> Literal["start", "none"]:
        """A run this trigger started ended: ``start`` when the buffered run
        starts now."""
        if self.in_progress == 0:
            raise ValueError("no run of this trigger is in progress")
        self.in_progress -= 1
        if self.waiting and self.in_progress == 0:
            self.waiting = False
            self.in_progress += 1
            return "start"
        return "none"

    def resumed(self) -> Literal["none"]:
        """A run this trigger started that ended ``deferred`` was resumed: it
        is in progress again. A buffered fire still waits until no run is."""
        self.in_progress += 1
        return "none"


def matches_event(trigger: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    """Whether ``event`` matches an event trigger's ``event`` block: a
    canonical event (a string ``event_id``) whose ``event_type`` equals the
    trigger's and whose ``source.kind`` equals its ``source_kind`` when it
    names one."""
    if not isinstance(event.get("event_id"), str):
        return False
    if event.get("event_type") != trigger.get("event_type"):
        return False
    kind = trigger.get("source_kind")
    source = event.get("source")
    return kind is None or (isinstance(source, Mapping) and source.get("kind") == kind)


class EventGate:
    """Which events start a run of one event trigger (§5.10.2): one run per
    event the host accepts, at most one per ``event_id``.

    ``trigger`` is the trigger's ``event`` block (``event_type``,
    ``source_kind``, ``delivers_to``). ``accept`` is the host's sender
    policy (where the workflow declares ``identity@1``, the §5.17 checks of
    a sender it authenticated); an event it refuses is ``refused``, and the
    host should keep an audit record of the drop. ``seen`` holds the
    ``event_id``s that started runs: an in-memory set by default; pass a
    store the host persists to deduplicate across restarts.
    """

    def __init__(
        self,
        trigger: Mapping[str, Any],
        *,
        accept: Callable[[Mapping[str, Any]], bool] | None = None,
        seen: MutableSet[str] | None = None,
    ) -> None:
        self.trigger = dict(trigger)
        self.accept = accept
        self.seen: MutableSet[str] = set() if seen is None else seen

    def check(
        self, event: Mapping[str, Any]
    ) -> Literal["start", "no_match", "refused", "duplicate"]:
        """The decision for ``event``, without recording it."""
        if not matches_event(self.trigger, event):
            return "no_match"
        if self.accept is not None and not self.accept(event):
            return "refused"
        if event["event_id"] in self.seen:
            return "duplicate"
        return "start"

    def commit(self, event: Mapping[str, Any]) -> None:
        """A run started for ``event``: its ``event_id`` starts no other."""
        self.seen.add(str(event["event_id"]))

    def offer(
        self, event: Mapping[str, Any]
    ) -> Literal["start", "no_match", "refused", "duplicate"]:
        """:meth:`check`, then :meth:`commit` when the event starts a run.
        An event that does not match, or that the policy refuses, does not
        consume its ``event_id``."""
        decision = self.check(event)
        if decision == "start":
            self.commit(event)
        return decision
