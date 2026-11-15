"""Generate the trigger vectors, tests/conformance/triggers/*.json (STANDARD
v1.2.0 §5.10.2, normative under §10.3).

    python scripts/gen_trigger_vectors.py          # write the vectors
    python scripts/gen_trigger_vectors.py --check  # fail if they differ (CI)

The values are computed here, independently of the reference core: fire
times with Python's zoneinfo, a five-field cron matcher of this script's own
and RFC 5545 §3.3.5's mapping of local times to instants; overlap, event and
attendance decisions with small reference functions of this script's own.
Each case also states the values the design computed with an earlier oracle,
and the script refuses to write when they differ.

fire_times.json names the IANA time zone database release it was computed
with. The vectors are normative with that release, or with any release that
agrees with it on the vectors' dates (§10.3), so --check fails on a value
that differs but not on a different release name alone.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zoneinfo
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "conformance" / "triggers"
MAX_TIME = 253_402_300_799_999
STANDARD = "1.2.0"

# ---------------------------------------------------------------------------
# The oracle: fire times (§5.10.2)
# ---------------------------------------------------------------------------

MONTHS = [
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]
WEEKDAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
FIELDS = [(0, 59, []), (0, 23, []), (1, 31, []), (1, 12, MONTHS), (0, 7, WEEKDAYS)]


def _value(text: str, lo: int, names: list[str]) -> int:
    if text.upper() in names:
        return names.index(text.upper()) + lo
    if not text.isdigit():
        raise ValueError(f"{text!r} is not a value")
    return int(text)


def parse_cron(expr: str) -> tuple[list[set[int]], bool, bool]:
    """The five fields as sets, and whether each day field is restricted (a
    field that starts with '*' is not, as in Vixie cron)."""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"{expr!r}: five fields")
    sets: list[set[int]] = []
    for part, (lo, hi, names) in zip(parts, FIELDS, strict=True):
        values: set[int] = set()
        for item in part.split(","):
            rng, _, step_text = item.partition("/")
            step = int(step_text) if step_text else 1
            if rng == "*":
                a, b = lo, hi
            elif "-" in rng:
                x, y = rng.split("-")
                a, b = _value(x, lo, names), _value(y, lo, names)
            else:
                a = _value(rng, lo, names)
                b = hi if step_text else a
            values.update(range(a, b + 1, step))
        sets.append(values)
    if 7 in sets[4]:
        sets[4] = (sets[4] - {7}) | {0}
    return sets, not parts[2].startswith("*"), not parts[4].startswith("*")


def _exists(local: datetime, tz: zoneinfo.ZoneInfo, fold: int) -> datetime | None:
    aware = local.replace(tzinfo=tz, fold=fold)
    utc = aware.astimezone(UTC)
    return utc if utc.astimezone(tz).replace(tzinfo=None) == local else None


def instant(local: datetime, tz: zoneinfo.ZoneInfo) -> datetime:
    """RFC 5545 §3.3.5: a local time that occurs twice is its first
    occurrence; one that does not occur is read with the UTC offset in
    effect before the change (that of the latest earlier local minute that
    exists)."""
    found = [u for u in (_exists(local, tz, 0), _exists(local, tz, 1)) if u is not None]
    if found:
        return min(found)
    p = local
    for _ in range(48 * 60):
        p -= timedelta(minutes=1)
        earlier = [
            (u, local_p)
            for fold in (0, 1)
            if (u := _exists(p, tz, fold)) is not None
            for local_p in [p.replace(tzinfo=tz, fold=fold)]
        ]
        if earlier:
            # The later of two occurrences is the one just before the gap.
            _, aware = max(earlier, key=lambda e: e[0])
            offset = aware.utcoffset()
            assert offset is not None
            return (local - offset).replace(tzinfo=UTC)
    raise ValueError(f"no local time before {local} in {tz}")


def ms_of(t: datetime) -> int:
    return round(t.timestamp() * 1000)


def oracle_cron(expr: str, tzname: str, after_ms: int) -> int | None:
    """The first fire time after `after_ms`, by local day."""
    if after_ms >= MAX_TIME:
        return None
    (minutes, hours, doms, months, dows), dom_r, dow_r = parse_cron(expr)
    tz = zoneinfo.ZoneInfo(tzname)
    after = datetime.fromtimestamp(after_ms / 1000, UTC)
    day = after.astimezone(tz).date() - timedelta(days=2)
    best: int | None = None
    for _ in range(3003):
        midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
        if best is not None and ms_of(midnight) - 86_400_000 > best:
            break
        dom_ok = day.day in doms
        dow_ok = day.isoweekday() % 7 in dows
        day_ok = (dom_ok or dow_ok) if (dom_r and dow_r) else (dom_ok and dow_ok)
        if day.month in months and day_ok:
            for h in sorted(hours):
                for m in sorted(minutes):
                    t = ms_of(instant(datetime(day.year, day.month, day.day, h, m), tz))
                    if t > after_ms and (best is None or t < best):
                        best = t
        day += timedelta(days=1)
    return best if best is not None and best <= MAX_TIME else None


UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def interval_ms(text: str) -> int:
    """An `every` interval in whole milliseconds, rounded up."""
    seconds: Decimal
    if m := re.fullmatch(r"(\d+)([smhd])", text):
        seconds = Decimal(m[1]) * UNITS[m[2]]
    elif m := re.fullmatch(
        r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", text
    ):
        d, h, mi, s = (Decimal(x) if x else Decimal(0) for x in m.groups())
        seconds = d * 86400 + h * 3600 + mi * 60 + s
    else:
        raise ValueError(f"{text!r}: an interval this oracle does not read")
    return math.ceil(seconds * 1000)


def oracle_every(text: str, after_ms: int) -> int | None:
    step = interval_ms(text)
    if after_ms >= MAX_TIME:
        return None
    t = (after_ms // step + 1) * step
    return t if t <= MAX_TIME else None


def oracle(schedule: dict[str, Any], after_ms: int) -> int | None:
    if "every" in schedule:
        return oracle_every(schedule["every"], after_ms)
    return oracle_cron(schedule["cron"], schedule.get("timezone", "UTC"), after_ms)


def rfc3339(ms: int) -> str:
    t = datetime.fromtimestamp(ms // 1000, UTC) + timedelta(milliseconds=ms % 1000)
    text = t.strftime("%Y-%m-%dT%H:%M:%S")
    return text + (f".{ms % 1000:03d}" if ms % 1000 else "") + "Z"


def at(text: str) -> int:
    return ms_of(datetime.fromisoformat(text.replace("Z", "+00:00")))


# ---------------------------------------------------------------------------
# The cases
# ---------------------------------------------------------------------------

# name: (schedule, after, the next fire times the design's oracle gave, note)
FIRE_TIMES: list[tuple[str, dict[str, Any], int, list[str], str]] = [
    (
        "utc_weekdays",
        {"cron": "0 6 * * MON-FRI", "timezone": "UTC"},
        at("2026-11-13T07:00:00Z"),
        ["2026-11-16T06:00:00Z", "2026-11-17T06:00:00Z"],
        "a weekday range; Friday's fire time has passed",
    ),
    (
        "strictly_after",
        {"cron": "0 6 * * *", "timezone": "UTC"},
        at("2026-11-16T06:00:00Z"),
        ["2026-11-17T06:00:00Z"],
        "'after' is exclusive",
    ),
    (
        "every_15m",
        {"every": "15m"},
        1000,
        ["1970-01-01T00:15:00Z", "1970-01-01T00:30:00Z"],
        "multiples of the interval since the Unix epoch",
    ),
    (
        "every_ignores_timezone",
        {"every": "1d", "timezone": "America/New_York"},
        at("2026-11-15T12:00:00Z"),
        ["2026-11-16T00:00:00Z"],
        "the timezone does not change an every schedule",
    ),
    (
        "every_rounds_up",
        {"every": "PT0.0005S"},
        5,
        ["1970-01-01T00:00:00.006Z", "1970-01-01T00:00:00.007Z"],
        "a sub-millisecond interval is rounded up to 1 ms",
    ),
    (
        "every_7m",
        {"every": "7m"},
        0,
        ["1970-01-01T00:07:00Z", "1970-01-01T00:14:00Z"],
        "an interval that does not divide an hour",
    ),
    (
        "step_list_range",
        {"cron": "5/20 0 1 jan,Jul *", "timezone": "UTC"},
        at("2026-01-01T00:30:00Z"),
        ["2026-01-01T00:45:00Z", "2026-07-01T00:05:00Z"],
        "a/step runs to the field's maximum; month names in any case",
    ),
    (
        "vixie_or",
        {"cron": "0 0 13 * FRI", "timezone": "UTC"},
        at("2026-11-15T00:00:00Z"),
        ["2026-11-20T00:00:00Z", "2026-11-27T00:00:00Z", "2026-12-04T00:00:00Z"],
        "both day fields restricted: the 13th or a Friday",
    ),
    (
        "leap_day",
        {"cron": "0 0 29 2 *", "timezone": "UTC"},
        at("2026-03-01T00:00:00Z"),
        ["2028-02-29T00:00:00Z"],
        "a sparse schedule",
    ),
    (
        "lisbon_spring",
        {"cron": "0 6 * * MON-FRI", "timezone": "Europe/Lisbon"},
        at("2026-03-27T12:00:00Z"),
        ["2026-03-30T05:00:00Z", "2026-03-31T05:00:00Z"],
        "the offset changes (+00:00 to +01:00) between two fire times",
    ),
    (
        "new_york_gap",
        {"cron": "30 2 * * *", "timezone": "America/New_York"},
        at("2026-03-07T12:00:00Z"),
        ["2026-03-08T07:30:00Z", "2026-03-09T06:30:00Z"],
        "02:30 does not occur on 8 March: read with the offset before the change (-05:00)",
    ),
    (
        "new_york_fold",
        {"cron": "30 1 * * *", "timezone": "America/New_York"},
        at("2026-10-31T12:00:00Z"),
        ["2026-11-01T05:30:00Z", "2026-11-02T06:30:00Z"],
        "01:30 occurs twice on 1 November: it fires once, at the first occurrence",
    ),
    (
        "new_york_gap_dedup",
        {"cron": "*/30 2-3 * * *", "timezone": "America/New_York"},
        at("2026-03-08T06:00:00Z"),
        ["2026-03-08T07:00:00Z", "2026-03-08T07:30:00Z", "2026-03-09T06:00:00Z"],
        "02:00 and 02:30 map to the instants of 03:00 and 03:30: each instant fires once",
    ),
    (
        "apia_skipped_day",
        {"cron": "0 12 * * *", "timezone": "Pacific/Apia"},
        at("2011-12-28T00:00:00Z"),
        [
            "2011-12-28T22:00:00Z",
            "2011-12-29T22:00:00Z",
            "2011-12-30T22:00:00Z",
            "2011-12-31T22:00:00Z",
        ],
        "30 December 2011 did not occur in Samoa: its noon is read with the offset before (-10:00)",
    ),
    (
        "lord_howe_half_hour",
        {"cron": "15 2 * * *", "timezone": "Australia/Lord_Howe"},
        at("2026-10-03T00:00:00Z"),
        ["2026-10-03T15:45:00Z", "2026-10-04T15:15:00Z"],
        "a 30-minute clock change: 02:15 on 4 October does not occur",
    ),
    (
        "kolkata_offset",
        {"cron": "0 9 * * *", "timezone": "Asia/Kolkata"},
        at("2026-11-15T00:00:00Z"),
        ["2026-11-15T03:30:00Z"],
        "a half-hour offset",
    ),
    (
        "none_before_max",
        {"cron": "0 0 1 1 *", "timezone": "UTC"},
        MAX_TIME,
        [],
        "nothing after the maximum time",
    ),
]

OVERLAP: dict[str, tuple[str | None, list[str], list[str]]] = {
    "skip_while_running": (
        "skip",
        ["fire", "fire", "end", "fire"],
        ["start", "skipped", "none", "start"],
    ),
    "buffer_one_holds_one": (
        "buffer_one",
        ["fire", "fire", "fire", "end", "end"],
        ["start", "buffered", "skipped", "start", "none"],
    ),
    "allow_all_starts_each": (
        "allow_all",
        ["fire", "fire", "end", "end"],
        ["start", "start", "none", "none"],
    ),
    "missed_counts_once": ("skip", ["missed"], ["start"]),
    "missed_while_running_buffers": (
        "buffer_one",
        ["fire", "missed", "end"],
        ["start", "buffered", "start"],
    ),
    "default_is_skip": (None, ["fire", "fire"], ["start", "skipped"]),
    "resumed_run_is_in_progress": (
        "skip",
        ["fire", "end", "resume", "fire", "end", "fire"],
        ["start", "none", "none", "skipped", "none", "start"],
    ),
    "resumed_run_holds_buffer": (
        "buffer_one",
        ["fire", "end", "resume", "fire", "end"],
        ["start", "none", "none", "buffered", "start"],
    ),
}

ATTENDANCE: dict[str, tuple[dict[str, Any], str | None, str]] = {
    "manual_default": ({"kind": "manual"}, None, "attended"),
    "schedule_default": (
        {"kind": "schedule", "schedule": {"every": "1h"}},
        None,
        "unattended",
    ),
    "event_default": (
        {"kind": "event", "event": {"event_type": "e", "delivers_to": "ev"}},
        None,
        "unattended",
    ),
    "invoke_follows_invoker_attended": ({"kind": "invoke"}, "attended", "attended"),
    "invoke_follows_invoker_unattended": (
        {"kind": "invoke"},
        "unattended",
        "unattended",
    ),
    "declared_overrides": (
        {"kind": "schedule", "schedule": {"every": "1h"}, "attendance": "attended"},
        None,
        "attended",
    ),
    "declared_overrides_manual": (
        {"kind": "manual", "attendance": "unattended"},
        None,
        "unattended",
    ),
    "invoke_declared_ignored": (
        {"kind": "invoke", "attendance": "unattended"},
        "attended",
        "attended",
    ),
    "invoke_declared_ignored_unattended": (
        {"kind": "invoke", "attendance": "attended"},
        "unattended",
        "unattended",
    ),
}


def event(event_id: str, event_type: str, kind: str, name: str) -> dict[str, Any]:
    """A complete canonical event (schemas/event_schema.yaml)."""
    return {
        "event_id": event_id,
        "timestamp": "2026-11-15T12:00:00Z",
        "source": {"kind": kind, "name": name},
        "event_type": event_type,
        "raw": {"status": "done"},
        "canonical": {"status": "done"},
        "anchors": [{"ref": f"log:ci/{event_id}", "kind": "log"}],
        "provenance": {"transformer": "ci", "transform_version": "1"},
    }


FINISHED = ("deploy.finished", "agent", "ci")
EVENTS: dict[str, tuple[dict[str, Any], list[tuple[str, str, str, str]], list[str]]] = {
    "type_matches": (
        {"event_type": "deploy.finished", "delivers_to": "ev"},
        [("e1", *FINISHED)],
        ["start"],
    ),
    "type_differs": (
        {"event_type": "deploy.finished", "delivers_to": "ev"},
        [("e1", "deploy.started", "agent", "ci")],
        ["no_match"],
    ),
    "source_kind_differs": (
        {"event_type": "deploy.finished", "source_kind": "agent", "delivers_to": "ev"},
        [("e1", "deploy.finished", "human", "ops")],
        ["no_match"],
    ),
    "source_kind_matches": (
        {"event_type": "deploy.finished", "source_kind": "agent", "delivers_to": "ev"},
        [("e1", *FINISHED)],
        ["start"],
    ),
    "redelivered_starts_once": (
        {"event_type": "deploy.finished", "delivers_to": "ev"},
        [("e1", *FINISHED), ("e1", *FINISHED), ("e2", *FINISHED)],
        ["start", "duplicate", "start"],
    ),
    "no_match_does_not_consume_id": (
        {"event_type": "deploy.finished", "delivers_to": "ev"},
        [("e1", "deploy.started", "agent", "ci"), ("e1", *FINISHED)],
        ["no_match", "start"],
    ),
}

# ---------------------------------------------------------------------------
# The reference decisions
# ---------------------------------------------------------------------------


def overlap_decisions(overlap: str | None, events: list[str]) -> list[str]:
    """§5.10.2 Overlap, for the runs one trigger started."""
    mode = overlap or "skip"
    running, waiting, out = 0, False, []
    for e in events:
        if e in ("fire", "missed"):
            if running == 0:
                running += 1
                out.append("start")
            elif mode == "allow_all":
                running += 1
                out.append("start")
            elif mode == "buffer_one" and not waiting:
                waiting = True
                out.append("buffered")
            else:
                out.append("skipped")
        elif e == "end":
            running -= 1
            if waiting and running == 0:
                waiting = False
                running += 1
                out.append("start")
            else:
                out.append("none")
        elif e == "resume":
            running += 1
            out.append("none")
        else:
            raise ValueError(e)
    return out


def attendance_of(trigger: dict[str, Any], invoker: str | None) -> str:
    """§5.10: an invoke trigger's run has its invoker's attendance, whatever
    the trigger declares; else the declared attendance, else the kind's
    default."""
    if trigger["kind"] == "invoke":
        return invoker or "attended"
    if "attendance" in trigger:
        return str(trigger["attendance"])
    return "attended" if trigger["kind"] == "manual" else "unattended"


def event_decisions(trigger: dict[str, Any], events: list[dict[str, Any]]) -> list[str]:
    """§5.10.2: an event the trigger matches starts a run, at most once per
    event_id."""
    seen: set[str] = set()
    out = []
    for e in events:
        matched = e["event_type"] == trigger["event_type"] and (
            "source_kind" not in trigger
            or e["source"]["kind"] == trigger["source_kind"]
        )
        if not matched:
            out.append("no_match")
        elif e["event_id"] in seen:
            out.append("duplicate")
        else:
            seen.add(e["event_id"])
            out.append("start")
    return out


# ---------------------------------------------------------------------------
# The files
# ---------------------------------------------------------------------------


def tzdata_release() -> str:
    """The IANA release zoneinfo reads: the tzdata package's when zoneinfo
    uses it, else the `# version` line of the system's tzdata.zi."""
    for base in zoneinfo.TZPATH:
        zi = Path(base) / "tzdata.zi"
        if zi.is_file():
            first = zi.read_text(encoding="utf-8").splitlines()[0]
            if first.startswith("# version "):
                return first.removeprefix("# version ").strip()
    try:
        import tzdata  # type: ignore[import-not-found]

        return str(tzdata.IANA_VERSION)
    except ImportError as e:
        raise SystemExit(
            "cannot tell which tzdata release zoneinfo uses; install the 'tzdata' package"
        ) from e


def header(description: str) -> dict[str, Any]:
    return {"description": description, "standard": STANDARD, "status": "normative"}


def fire_times() -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for name, schedule, after_ms, expected, note in FIRE_TIMES:
        nexts: list[int] = []
        t = after_ms
        for _ in range(max(len(expected), 1)):
            n = oracle(schedule, t)
            if n is None:
                break
            nexts.append(n)
            t = n
        got = [rfc3339(n) for n in nexts]
        if got != expected:
            raise SystemExit(
                f"fire_times {name}: computed {got}, the design had {expected}"
            )
        cases[name] = {
            "schedule": schedule,
            "after": rfc3339(after_ms),
            "after_ms": after_ms,
            "next": got,
            "next_ms": nexts,
            "note": note,
        }
    out = header(
        "Fire times of schedule triggers (STANDARD 1.2.0 section 5.10.2), normative under "
        "section 10.3. Each case gives a schedule, an instant 'after' (exclusive) and the "
        "next fire times, as RFC 3339 UTC and as milliseconds since the epoch: the first is "
        "the first fire time after 'after', each later one the first after the one before. "
        "Computed by scripts/gen_trigger_vectors.py with Python zoneinfo, independently of "
        "the reference core."
    )
    out["tzdata"] = tzdata_release()
    out["cases"] = cases
    return out


def overlap() -> dict[str, Any]:
    cases = {}
    for name, (mode, events, expected) in OVERLAP.items():
        got = overlap_decisions(mode, events)
        if got != expected:
            raise SystemExit(
                f"overlap {name}: computed {got}, the design had {expected}"
            )
        cases[name] = {"overlap": mode, "events": events, "expect": got}
    out = header(
        "Overlap decisions of one schedule trigger (STANDARD 1.2.0 section 5.10.2), normative "
        "under section 10.3. 'events' is a sequence: 'fire' (a fire time), 'end' (a run this "
        "trigger started ends, including one that ends deferred), 'resume' (a run this "
        "trigger started that ended deferred is resumed, section 5.14.1, and is in progress "
        "again), 'missed' (fire times passed while the host was stopped, counted together as "
        "one). 'expect' gives, per event: for 'fire' and 'missed', 'start', 'buffered' or "
        "'skipped'; for 'end', 'start' (a buffered run starts) or 'none'; for 'resume', "
        "'none'. 'overlap' null is the default, skip."
    )
    out["cases"] = cases
    return out


def attendance() -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for name, (trigger, invoker, expected) in ATTENDANCE.items():
        got = attendance_of(trigger, invoker)
        if got != expected:
            raise SystemExit(
                f"attendance {name}: computed {got}, the design had {expected}"
            )
        case: dict[str, Any] = {"trigger": trigger}
        if invoker is not None:
            case["invoker"] = invoker
        case["expect"] = got
        cases[name] = case
    out = header(
        "The attendance of a run a trigger starts (STANDARD 1.2.0 sections 5.10 and 5.10.2), "
        "normative under section 10.3: the trigger's declared attendance, else the default "
        "of its kind; an invoke trigger's run has its invoker's ('invoker'), whatever "
        "the trigger declares."
    )
    out["cases"] = cases
    return out


def events() -> dict[str, Any]:
    cases = {}
    for name, (trigger, items, expected) in EVENTS.items():
        evs = [event(*item) for item in items]
        got = event_decisions(trigger, evs)
        if got != expected:
            raise SystemExit(
                f"events {name}: computed {got}, the design had {expected}"
            )
        cases[name] = {"trigger": trigger, "events": evs, "expect": got}
    out = header(
        "Which events start a run of an event trigger (STANDARD 1.2.0 section 5.10.2), "
        "normative under section 10.3. Each case gives a trigger's 'event' block and a "
        "sequence of canonical events delivered to the host, all admitted by its sender "
        "policy (the policy is the host's and is not a vector); 'expect' gives, per event, "
        "'start' (a run starts, with the event as the input delivers_to names), 'no_match' "
        "(event_type, or source.kind against source_kind, differs) or 'duplicate' (an event "
        "with this event_id already started a run of this trigger)."
    )
    out["cases"] = cases
    return out


def render() -> dict[str, dict[str, Any]]:
    return {
        "fire_times.json": fire_times(),
        "overlap.json": overlap(),
        "attendance.json": attendance(),
        "events.json": events(),
    }


def text(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def drift(name: str, wanted: dict[str, Any], path: Path) -> str | None:
    """Why the file on disk differs from `wanted`, if it does. A different
    tzdata release name alone is not a drift when every value agrees."""
    if not path.is_file():
        return f"{name} is missing"
    have = json.loads(path.read_text(encoding="utf-8"))
    if {k: v for k, v in have.items() if k != "tzdata"} != {
        k: v for k, v in wanted.items() if k != "tzdata"
    }:
        release = (
            f" (on disk: tzdata {have.get('tzdata')}, here: {wanted.get('tzdata')})"
        )
        return f"{name} differs{release if 'tzdata' in wanted else ''}"
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the vectors differ"
    )
    args = parser.parse_args(argv)
    wanted = render()
    if args.check:
        problems = [p for n, v in wanted.items() if (p := drift(n, v, OUT / n))]
        for p in problems:
            print(f"trigger vectors: {p}; run python scripts/gen_trigger_vectors.py")
        return 1 if problems else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in wanted.items():
        (OUT / name).write_text(text(value), encoding="utf-8")
    print(f"wrote {len(wanted)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
