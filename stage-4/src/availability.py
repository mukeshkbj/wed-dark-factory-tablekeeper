"""Public restaurant browsing and availability search (spec section 8)."""

import re
from datetime import datetime

import policies
import reservations
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


def _taken(rest_id, confirmed, table_id, start, end):
    if reservations.closure_conflict(rest_id, [table_id], start, end):
        return True
    return any(
        table_id in reservations.reservation_table_ids(r)
        and timeutil.overlaps(start, end, r["start_epoch"], r["end_epoch"])
        for r in confirmed)


def search(query):
    rid = _required_param(query, "restaurant_id")
    date = _required_param(query, "date")
    party_raw = _required_param(query, "party_size")
    explain = False
    if "explain" in query:
        if query["explain"] != "true":
            raise ApiError(422, "validation_failed",
                           "explain may only be true")
        explain = True

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
        raise ApiError(422, "validation_failed",
                       "party_size must be >= 1")

    rest = state.STATE["restaurants"].get(rid)
    if rest is None:
        raise ApiError(404, "not_found", "unknown restaurant")

    policy = policies.selected_policy(rest, date)
    policy_context = policies.context(rest, policy)
    capacities = policy["capacities"]
    confirmed = [
        r for r in state.STATE["reservations"].values()
        if r["restaurant_id"] == rid and r["status"] == "confirmed"
    ]
    pairs = reservations.combinable_pairs(rest)

    slots = []
    for slot in timeutil.slots_for_day(policy_context, date):
        start = datetime.fromisoformat(slot["starts_at"]).timestamp()
        end = slot["end_instant"].timestamp()
        explanations = []
        free = []
        options = []
        for table in rest["tables"]:
            tid = table["id"]
            capacity_ok = capacities[tid] >= party_size
            overlap_ok = not _taken(rid, confirmed, tid, start, end)
            available = capacity_ok and overlap_ok
            if explain:
                explanations.append({
                    "table_id": tid,
                    "policy_version": policy["policy_version"],
                    "available": available,
                    "rules": [
                        {"rule": "capacity", "holds": capacity_ok},
                        {"rule": "no_overlap", "holds": overlap_ok},
                    ],
                })
            if not available:
                continue
            free.append(tid)
            options.append({"table_ids": [tid], "capacity": capacities[tid]})
        for pair in pairs:
            capacity = sum(capacities[tid] for tid in pair)
            if capacity < party_size:
                continue
            if any(_taken(rid, confirmed, tid, start, end) for tid in pair):
                continue
            options.append({"table_ids": list(pair), "capacity": capacity})
        item = {
            "starts_at_local": slot["starts_at_local"],
            "starts_at": slot["starts_at"],
            "available_table_ids": free,
            "available_options": options,
        }
        if explain:
            item["explain"] = explanations
        slots.append(item)
    return {
        "restaurant_id": rid,
        "date": date,
        "timezone": rest["timezone"],
        "slots": slots,
    }
