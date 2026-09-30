"""`GET /availability` (spec section 8).

One slot per `slot_minutes` step from `opens` while
`slot + reservation_duration_minutes <= closes`, computed on the local wall
clock. Nonexistent local times (spring-forward gap) never produce a slot;
ambiguous times produce one slot resolving to the first occurrence.

`available_table_ids` holds the restaurant's tables — in fixture order — whose
capacity fits the party and that carry no overlapping confirmed reservation.
A slot with no available table still appears, with an empty list. A closed day
returns `"slots": []`.

Owned by the engineer seat.
"""
from __future__ import annotations

import re

try:
    from .errors import ApiError
    from . import timeutil
except ImportError:
    from errors import ApiError
    import timeutil

_DIGITS_RE = re.compile(r"^[0-9]+$")


def _query_int(params, name):
    """Integer query parameter: plain decimal digits only (spec 5.5)."""
    value = params.get(name)
    if value is None or not _DIGITS_RE.match(value):
        raise ApiError(422, "validation_failed",
                       f"query parameter {name} must be a non-negative integer")
    return int(value)


def handle(state, params):
    for name in ("restaurant_id", "date", "party_size"):
        if name not in params:
            raise ApiError(422, "validation_failed",
                           f"missing query parameter {name}")
    restaurant_id = params["restaurant_id"]
    day = timeutil.parse_date(params["date"])
    if day is None:
        raise ApiError(422, "validation_failed", "date must be YYYY-MM-DD")
    party_size = _query_int(params, "party_size")
    if party_size < 1:
        raise ApiError(422, "validation_failed", "party_size must be at least 1")

    with state.lock:
        restaurant = state.get_restaurant(restaurant_id)
        if restaurant is None:
            raise ApiError(404, "not_found", "no such restaurant")
        confirmed = state.confirmed_for_restaurant(restaurant_id)

        tz = timeutil.ZoneInfo(restaurant["timezone"])
        duration = restaurant["reservation_duration_minutes"]
        slots = []
        opening = timeutil.opening_for(day, restaurant["opening_hours"])
        if opening is not None:
            opens = timeutil.hhmm_to_minutes(opening["opens"])
            closes = timeutil.hhmm_to_minutes(opening["closes"])
            for minute in timeutil.slot_starts(
                    day, opens, closes, restaurant["slot_minutes"], duration):
                start = timeutil.resolve_local(day, minute, tz)
                if start is None:
                    continue  # skipped hour: the slot does not exist
                s = timeutil.epoch(start)
                e = s + duration * 60
                available = []
                for table in restaurant["tables"]:
                    if table["capacity"] < party_size:
                        continue
                    if _overlaps(confirmed, table["id"], s, e):
                        continue
                    available.append(table["id"])
                slots.append({
                    "starts_at_local": timeutil.local_string(day, minute),
                    "starts_at": timeutil.rfc3339(s, tz),
                    "available_table_ids": available,
                })

    return 200, {
        "restaurant_id": restaurant_id,
        "date": params["date"],
        "timezone": restaurant["timezone"],
        "slots": slots,
    }


def _overlaps(confirmed, table_id, start_epoch, end_epoch) -> bool:
    """True when any confirmed booking on `table_id` overlaps [s, e)."""
    for doc in confirmed:
        if table_id not in doc["table_ids"]:
            continue
        if doc["starts_epoch"] < end_epoch and start_epoch < doc["ends_epoch"]:
            return True
    return False
