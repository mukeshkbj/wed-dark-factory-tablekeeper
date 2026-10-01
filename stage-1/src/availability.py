"""Public restaurant browsing and availability search (spec section 8)."""

import re
from datetime import datetime

import state
from errors import ApiError

try:
    import timeutil
except ImportError:
    import _stub_timeutil as timeutil

_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DIGITS_RE = re.compile(r"^[0-9]+$")


def list_restaurants():
    return {"restaurants": [
        {"id": r["id"], "name": r["name"], "timezone": r["timezone"]}
        for r in (state.STATE["restaurants"][rid]
                  for rid in state.STATE["restaurant_order"])
    ]}


def get_restaurant(rid):
    rest = state.STATE["restaurants"].get(rid)
    if rest is None:
        raise ApiError(404, "not_found", "unknown restaurant")
    return rest


def _required_param(query, name):
    raw = query.get(name)
    if raw is None or raw == "":
        raise ApiError(422, "validation_failed", "%s is required" % name)
    return raw


def search(query):
    rid = _required_param(query, "restaurant_id")
    date = _required_param(query, "date")
    party_raw = _required_param(query, "party_size")

    if not _DATE_RE.match(date):
        raise ApiError(422, "validation_failed", "date must be YYYY-MM-DD")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ApiError(422, "validation_failed", "invalid date")
    if not _DIGITS_RE.match(party_raw):
        raise ApiError(422, "validation_failed",
                       "party_size must be decimal digits")
    party_size = int(party_raw)
    if party_size < 1:
        raise ApiError(422, "validation_failed", "party_size must be >= 1")

    rest = state.STATE["restaurants"].get(rid)
    if rest is None:
        raise ApiError(404, "not_found", "unknown restaurant")

    confirmed = [
        r for r in state.STATE["reservations"].values()
        if r["restaurant_id"] == rid and r["status"] == "confirmed"
    ]
    slots = []
    for slot in timeutil.slots_for_day(rest, date):
        start = datetime.fromisoformat(slot["starts_at"]).timestamp()
        end = slot["end_instant"].timestamp()
        free = []
        for t in rest["tables"]:
            if t["capacity"] < party_size:
                continue
            taken = any(
                timeutil.overlaps(start, end, r["start_epoch"], r["end_epoch"])
                for r in confirmed if r["table_id"] == t["id"])
            if not taken:
                free.append(t["id"])
        slots.append({
            "starts_at_local": slot["starts_at_local"],
            "starts_at": slot["starts_at"],
            "available_table_ids": free,
        })
    return {
        "restaurant_id": rid,
        "date": date,
        "timezone": rest["timezone"],
        "slots": slots,
    }
