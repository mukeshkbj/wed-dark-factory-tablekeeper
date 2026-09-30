"""Local-time resolution, slot grids and RFC 3339 output (spec section 9).

Rules implemented here — the single chokepoint for time semantics:

- `starts_at_local` is a bare `YYYY-MM-DDTHH:MM` wall-clock string at the
  restaurant's `timezone`; no offset, no `Z`.
- Spring-forward gap: a nonexistent local time resolves to nothing; callers
  turn that into 422 `invalid_local_time`, and availability never lists it.
- Fall-back fold: an ambiguous local time resolves to its FIRST occurrence —
  the earlier instant, before the clocks change.
- Durations are absolute elapsed seconds: `ends = starts + duration` in real
  time, never wall-clock arithmetic.

Owned by the engineer seat.
"""
from __future__ import annotations

import datetime as dt
import re

from zoneinfo import ZoneInfo

LOCAL_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T([01][0-9]|2[0-3]):([0-5][0-9])$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
UTC = dt.timezone.utc


def parse_local(value):
    """Parse a bare `YYYY-MM-DDTHH:MM` string.

    Returns `(date, minute_of_day)` or `None` when the format or the
    calendar date is invalid.
    """
    if not isinstance(value, str):
        return None
    m = LOCAL_RE.match(value)
    if not m:
        return None
    try:
        day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return day, int(m.group(4)) * 60 + int(m.group(5))


def parse_date(value):
    """Parse `YYYY-MM-DD` to a `date`, or `None` if invalid."""
    if not isinstance(value, str):
        return None
    m = DATE_RE.match(value)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def resolve_local(day: dt.date, minute_of_day: int, tz: ZoneInfo):
    """Resolve a wall-clock local time to an aware datetime in `tz`.

    Returns `None` when the local time does not exist (spring-forward gap).
    Ambiguous (fall-back) times resolve to the first occurrence — the
    earlier instant.
    """
    naive = dt.datetime.combine(day, dt.time(minute_of_day // 60,
                                           minute_of_day % 60))
    candidates = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=fold)
        instant = aware.astimezone(UTC)
        if instant.astimezone(tz).replace(tzinfo=None) == naive:
            candidates.append(instant)
    if not candidates:
        return None
    return min(candidates).astimezone(tz)


def resolve_local_lenient(day: dt.date, minute_of_day: int, tz: ZoneInfo):
    """Resolve like `resolve_local`, but never return `None`.

    Used only for fixture-seeded reservations, which the spec treats as
    authoritative: a nonexistent local time maps to the post-gap reading
    (the fold=0 interpretation) rather than failing the reset.
    """
    resolved = resolve_local(day, minute_of_day, tz)
    if resolved is not None:
        return resolved
    naive = dt.datetime.combine(day, dt.time(minute_of_day // 60,
                                           minute_of_day % 60))
    return naive.replace(tzinfo=tz, fold=0).astimezone(UTC).astimezone(tz)


def epoch(aware: dt.datetime) -> int:
    return int(aware.timestamp())


def rfc3339(epoch_seconds: int, tz: ZoneInfo) -> str:
    """Format an instant as RFC 3339 with explicit offset in `tz`."""
    return dt.datetime.fromtimestamp(epoch_seconds, UTC).astimezone(tz) \
        .isoformat(timespec="seconds")


def rfc3339_utc(epoch_seconds: int) -> str:
    return dt.datetime.fromtimestamp(epoch_seconds, UTC) \
        .isoformat(timespec="seconds")


def opening_for(day: dt.date, opening_hours: list):
    """The `{weekday, opens, closes}` entry for `day`, or None if closed."""
    weekday = WEEKDAYS[day.weekday()]
    for entry in opening_hours:
        if entry["weekday"] == weekday:
            return entry
    return None


def hhmm_to_minutes(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def local_string(day: dt.date, minute_of_day: int) -> str:
    return f"{day.isoformat()}T{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def slot_starts(day: dt.date, opens_min: int, closes_min: int,
                slot_minutes: int, duration_minutes: int):
    """Yield `minute_of_day` grid starts satisfying `start + duration <= closes`."""
    start = opens_min
    while start + duration_minutes <= closes_min:
        yield start
        start += slot_minutes
