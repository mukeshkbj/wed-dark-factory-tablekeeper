"""Local stub for the experience-owned `timeutil` module.

Implements the coordinator-ruled contract so the engineer seat is never
blocked. When the real `stage-1/src/timeutil.py` lands, callers prefer it
(they import `timeutil` first and fall back here only on ImportError).

Contract:
    resolve_local(tz_name, local_naive) -> datetime (aware)
        bare "YYYY-MM-DDTHH:MM" only; MalformedLocalTime otherwise
        (including offset/Z suffixes and invalid calendar values);
        ambiguous -> first occurrence (fold=0); nonexistent -> InvalidLocalTime
    slots_for_day(rest, date) -> [{starts_at_local, starts_at, end_instant}]
    overlaps(a_start, a_end, b_start, b_end) -> bool  (half-open)
    rfc3339(dt) -> str with explicit offset
"""

import re
from datetime import date as _date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_BARE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$")
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class MalformedLocalTime(Exception):
    pass


class InvalidLocalTime(Exception):
    pass


def _hhmm_to_minutes(value):
    if not isinstance(value, str) or not re.match(r"^\d{2}:\d{2}$", value):
        raise ValueError("bad HH:MM")
    h, m = int(value[:2]), int(value[3:5])
    if h > 23 or m > 59:
        raise ValueError("bad HH:MM")
    return h * 60 + m


def _parse_bare(local_naive):
    if not isinstance(local_naive, str) or not _BARE_RE.match(local_naive):
        raise MalformedLocalTime(local_naive)
    try:
        return datetime.strptime(local_naive, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise MalformedLocalTime(local_naive) from exc


def _exists_in_zone(naive, tz):
    aware = naive.replace(tzinfo=tz, fold=0)
    rt = aware.astimezone(timezone.utc).astimezone(tz)
    return (
        rt.year, rt.month, rt.day, rt.hour, rt.minute
    ) == (
        naive.year, naive.month, naive.day, naive.hour, naive.minute
    )


def resolve_local(tz_name, local_naive):
    naive = _parse_bare(local_naive)
    tz = ZoneInfo(tz_name)
    if not _exists_in_zone(naive, tz):
        raise InvalidLocalTime(local_naive)
    return naive.replace(tzinfo=tz, fold=0)


def add_absolute(dt, delta):
    """dt + delta as absolute elapsed time (survives DST transitions).

    Plain `dt + delta` on an aware datetime is wall-clock arithmetic and
    would wrongly skip/repeat an hour across a transition.
    """
    return (dt.astimezone(timezone.utc) + delta).astimezone(dt.tzinfo)


def rfc3339(dt):
    return dt.isoformat(timespec="seconds")


def overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def slots_for_day(rest, date):
    """Grid slots for the local calendar `date` ("YYYY-MM-DD") at `rest`.

    Each item: {"starts_at_local": "YYYY-MM-DDTHH:MM",
                "starts_at": rfc3339 aware start,
                "end_instant": aware datetime = start + duration (absolute)}.
    Closed weekday -> []. Nonexistent locals skipped.
    """
    tz = ZoneInfo(rest["timezone"])
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
            start = resolve_local(rest["timezone"], local)
        except InvalidLocalTime:
            continue
        slots.append({
            "starts_at_local": local,
            "starts_at": rfc3339(start),
            "end_instant": add_absolute(start, timedelta(minutes=duration)),
        })
    return slots
