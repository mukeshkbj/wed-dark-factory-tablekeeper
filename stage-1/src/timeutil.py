"""IANA timezone, DST and slot-grid math for Tablekeeper stage 1.

Session record: the mandate header requested model `swe`; this session
reports its resolved model id as **SWE-2 High** (`swe-2-high`).

Contract (consumed by availability.py, reservations.py, moves.py and
transfer.py, which import this module first and fall back to
`_stub_timeutil` only on ImportError):

    resolve_local(tz_name, local_naive) -> aware datetime
        `local_naive` must be a BARE "YYYY-MM-DDTHH:MM" — anything else
        (offset suffixes, a `Z`, seconds, a space separator, invalid
        calendar values, non-strings) raises MalformedLocalTime. A local
        time that does not exist in the zone (spring-forward gap) raises
        InvalidLocalTime. An ambiguous local (the fall-back repeat hour)
        resolves to the FIRST occurrence — the one before the clocks
        change (fold=0 semantics).

    slots_for_day(rest, date) -> list[dict]
        For the weekday of `date` ("YYYY-MM-DD", local to
        rest["timezone"]) emit one entry per `slot_minutes` step from
        `opens` with `start + reservation_duration_minutes <= closes`.
        A closed weekday -> []. Nonexistent locals are skipped entirely;
        ambiguous locals are emitted once (first occurrence). The end is
        absolute elapsed time: a 90-minute booking at 01:30 on Berlin's
        fall-back night ends at local 02:00, not 03:00.

        Entry shape:
            starts_at_local   "YYYY-MM-DDTHH:MM" (bare; feeds POST
                              /reservations unchanged)
            starts_at         RFC 3339 string with explicit offset —
                              the section-8 wire shape that
                              availability.py emits verbatim
            ends_at           aware datetime, the absolute end instant
            start_instant     aware datetime (alias of the start)
            end_instant       aware datetime (same instant as ends_at;
                              stub-era key kept for the engineer)
            ends_at_rfc3339   RFC 3339 string of the end instant

    overlaps(a_start, a_end, b_start, b_end) -> bool
        Half-open [start, end): 19:00+90min vs a 20:30 start do NOT
        overlap. Works on aware datetimes or epoch floats.

    rfc3339(dt) -> str
        RFC 3339 with an explicit numeric offset: "+HH:MM" form,
        "+00:00" for UTC.

    weekday_of(tz_name, date) -> "mon".."sun"
        The weekday of the local calendar `date` in the named zone.

    add_absolute(dt, delta) -> aware datetime
        dt + delta measured in absolute elapsed time (DST-safe).
"""

import re
from datetime import date as _date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_BARE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class MalformedLocalTime(Exception):
    """`starts_at_local` is not a bare YYYY-MM-DDTHH:MM local time."""


class InvalidLocalTime(Exception):
    """The local time does not exist in the zone (spring-forward gap)."""


def _parse_bare(local_naive):
    if not isinstance(local_naive, str) or not _BARE_RE.match(local_naive):
        raise MalformedLocalTime(local_naive)
    try:
        return datetime.strptime(local_naive, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise MalformedLocalTime(local_naive) from exc


def _exists_in_zone(naive, tz):
    """True iff `naive` is a real local time in `tz`.

    Nonexistence is detected by round-tripping through UTC: a gap time
    resolves onto an instant whose wall clock reads differently.
    """
    aware = naive.replace(tzinfo=tz, fold=0)
    rt = aware.astimezone(timezone.utc).astimezone(tz)
    return rt.replace(tzinfo=None) == naive


def resolve_local(tz_name, local_naive):
    naive = _parse_bare(local_naive)
    tz = ZoneInfo(tz_name)
    if not _exists_in_zone(naive, tz):
        raise InvalidLocalTime(local_naive)
    return naive.replace(tzinfo=tz, fold=0)


def add_absolute(dt, delta):
    """dt + delta as absolute elapsed time (survives DST transitions).

    Plain `dt + delta` on an aware datetime is wall-clock arithmetic and
    would wrongly skip or repeat an hour across a transition.
    """
    return (dt.astimezone(timezone.utc) + delta).astimezone(dt.tzinfo)


def rfc3339(dt):
    return dt.isoformat(timespec="seconds")


def overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def weekday_of(tz_name, date):
    ZoneInfo(tz_name)  # invalid zone names fail loudly, like resolve_local
    return _WEEKDAYS[_date.fromisoformat(date).weekday()]


def _hhmm_to_minutes(value):
    if not isinstance(value, str) or not re.match(r"^\d{2}:\d{2}$", value):
        raise ValueError("bad HH:MM")
    h, m = int(value[:2]), int(value[3:5])
    if h > 23 or m > 59:
        raise ValueError("bad HH:MM")
    return h * 60 + m


def slots_for_day(rest, date):
    """Grid slots for the local calendar `date` ("YYYY-MM-DD") at `rest`."""
    tz_name = rest["timezone"]
    try:
        day = _date.fromisoformat(date)
    except (ValueError, TypeError):
        return []
    weekday = _WEEKDAYS[day.weekday()]
    entry = None
    for oh in rest.get("opening_hours") or []:
        if oh.get("weekday") == weekday:
            entry = oh
            break
    if entry is None:
        return []
    opens = _hhmm_to_minutes(entry["opens"])
    closes = _hhmm_to_minutes(entry["closes"])
    step = int(rest["slot_minutes"])
    duration = int(rest["reservation_duration_minutes"])
    slots = []
    seen = set()
    t = opens
    while t + duration <= closes:
        local = "%sT%02d:%02d" % (date, t // 60, t % 60)
        t += step
        if local in seen:
            continue
        seen.add(local)
        try:
            start = resolve_local(tz_name, local)
        except InvalidLocalTime:
            continue  # spring-forward gap: the local time never happens
        end = add_absolute(start, timedelta(minutes=duration))
        slots.append({
            "starts_at_local": local,
            "starts_at": rfc3339(start),
            "ends_at": end,
            "start_instant": start,
            "end_instant": end,
            "ends_at_rfc3339": rfc3339(end),
        })
    return slots
