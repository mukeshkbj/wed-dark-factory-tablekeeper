"""Reservations: create, list, get, cancel, amend (spec sections 8-9).

Validation precedence (coordinator ruling R-6):
    missing fields -> field type/format -> restaurant existence ->
    table existence/membership -> party_size rules -> slot grid ->
    opening hours -> local-time existence -> capacity -> occupancy.

Cutoff (R-7): an action is allowed iff now < starts_at - cutoff;
exactly at the boundary is "within" -> 409 cutoff_passed.
"""

import re
import secrets
from datetime import datetime, timedelta, timezone

import idempotency
import state
from errors import ApiError

try:
    import timeutil
except ImportError:
    import _stub_timeutil as timeutil

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_BARE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$")
_REF_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


# ---- shared helpers ---------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _view(res):
    return {
        "reservation_id": res["id"],
        "reference": res["reference"],
        "restaurant_id": res["restaurant_id"],
        "table_id": res["table_id"],
        "party_size": res["party_size"],
        "status": res["status"],
        "starts_at_local": res["starts_at_local"],
        "starts_at": res["starts_at"],
        "ends_at": res["ends_at"],
        "created_at": res["created_at"],
    }


def _find_reservation(ref):
    rid = state.STATE["reference_index"].get(ref)
    return state.STATE["reservations"].get(rid) if rid else None


def _lookup_mine(user, ref):
    res = _find_reservation(ref)
    if res is None or res["user_id"] != user["id"]:
        raise ApiError(404, "not_found", "no such reservation")
    return res


def _check_cutoff(res):
    rest = state.STATE["restaurants"][res["restaurant_id"]]
    cutoff = timedelta(minutes=rest["cancellation_cutoff_minutes"])
    start = datetime.fromtimestamp(res["start_epoch"], timezone.utc)
    if _now() >= start - cutoff:
        raise ApiError(409, "cutoff_passed",
                       "within cancellation cutoff")


def _parse_local_parts(value):
    """Phase-2 check: bare YYYY-MM-DDTHH:MM shape + valid calendar values."""
    if not isinstance(value, str):
        raise ApiError(400, "malformed_request",
                       "starts_at_local must be a string")
    if not _BARE_RE.match(value):
        raise ApiError(422, "validation_failed",
                       "starts_at_local must be bare YYYY-MM-DDTHH:MM")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ApiError(422, "validation_failed", "invalid local date/time")


def _minutes(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def add_absolute(dt, delta):
    """dt + delta as absolute elapsed time (DST-safe: aware-datetime
    arithmetic is wall-clock and would skip/repeat an hour)."""
    return (dt.astimezone(timezone.utc) + delta).astimezone(dt.tzinfo)


def _opening_entry(rest, naive):
    weekday = _WEEKDAYS[naive.weekday()]
    for entry in rest.get("opening_hours") or []:
        if entry["weekday"] == weekday:
            return entry
    return None


def _party_rules(party):
    if isinstance(party, bool) or not isinstance(party, int) or party < 1:
        raise ApiError(422, "validation_failed",
                       "party_size must be an integer >= 1")


def _check_overlap(rest_id, table_id, start_epoch, end_epoch, exclude_ids):
    for r in state.STATE["reservations"].values():
        if r["id"] in exclude_ids or r["status"] != "confirmed":
            continue
        if r["restaurant_id"] != rest_id or r["table_id"] != table_id:
            continue
        if timeutil.overlaps(start_epoch, end_epoch,
                             r["start_epoch"], r["end_epoch"]):
            raise ApiError(409, "table_unavailable",
                           "table already booked for that interval")


def _validate_booking(rest, table_id, local_str, party, exclude_ids,
                      check_occupancy=True):
    """Post-presence/type phases; returns (table, start_dt, end_dt)."""
    table = None
    for t in rest["tables"]:
        if t["id"] == table_id:
            table = t
            break
    if table is None:
        raise ApiError(404, "not_found", "unknown table")

    _party_rules(party)

    naive = _parse_local_parts(local_str)
    entry = _opening_entry(rest, naive)
    if entry is None:
        raise ApiError(422, "outside_opening_hours",
                       "restaurant is closed that day")
    opens, closes = _minutes(entry["opens"]), _minutes(entry["closes"])
    start_min = naive.hour * 60 + naive.minute
    if (start_min - opens) % rest["slot_minutes"] != 0:
        raise ApiError(422, "not_on_slot_grid",
                       "start not on the slot grid")
    if start_min < opens or start_min + rest["reservation_duration_minutes"] > closes:
        raise ApiError(422, "outside_opening_hours",
                       "outside opening hours")

    try:
        start = timeutil.resolve_local(rest["timezone"], local_str)
    except timeutil.InvalidLocalTime:
        raise ApiError(422, "invalid_local_time",
                       "local time does not exist")
    end = add_absolute(
        start, timedelta(minutes=rest["reservation_duration_minutes"]))

    if party > table["capacity"]:
        raise ApiError(422, "party_exceeds_capacity",
                       "party_size exceeds table capacity")

    if check_occupancy:
        _check_overlap(rest["id"], table_id, start.timestamp(),
                       end.timestamp(), exclude_ids)
    return table, start, end


def _new_reference():
    while True:
        ref = "".join(secrets.choice(_REF_ALPHABET) for _ in range(8))
        if ref not in state.STATE["reference_index"]:
            return ref


def _new_reservation_id():
    counters = state.STATE["counters"]
    while True:
        counters["reservation"] += 1
        rid = "res_%d" % counters["reservation"]
        if rid not in state.STATE["reservations"]:
            return rid


# ---- endpoints --------------------------------------------------------

def create(user, body):
    for field in ("restaurant_id", "table_id", "starts_at_local",
                  "party_size"):
        if field not in body:
            raise ApiError(422, "validation_failed",
                           "%s is required" % field)

    rid = body["restaurant_id"]
    tid = body["table_id"]
    local = body["starts_at_local"]
    if not isinstance(rid, str):
        raise ApiError(400, "malformed_request",
                       "restaurant_id must be a string")
    if not isinstance(tid, str):
        raise ApiError(400, "malformed_request",
                       "table_id must be a string")
    _parse_local_parts(local)

    rest = state.STATE["restaurants"].get(rid)
    if rest is None:
        raise ApiError(404, "not_found", "unknown restaurant")
    table, start, end = _validate_booking(rest, tid, local,
                                          body["party_size"], ())

    res = {
        "id": _new_reservation_id(),
        "reference": _new_reference(),
        "user_id": user["id"],
        "restaurant_id": rid,
        "table_id": tid,
        "party_size": body["party_size"],
        "status": "confirmed",
        "starts_at_local": local,
        "starts_at": timeutil.rfc3339(start),
        "ends_at": timeutil.rfc3339(end),
        "start_epoch": start.timestamp(),
        "end_epoch": end.timestamp(),
        "created_at": timeutil.rfc3339(_now()),
    }
    state.STATE["reservations"][res["id"]] = res
    state.STATE["reference_index"][res["reference"]] = res["id"]
    return 201, _view(res)


def create_idempotent(user, method, path, key, body):
    return idempotency.execute(
        user["id"], method, path, key, body,
        lambda: create(user, body))


def list_mine(user):
    mine = [r for r in state.STATE["reservations"].values()
            if r["user_id"] == user["id"]]
    mine.sort(key=lambda r: -r["start_epoch"])
    return 200, {"reservations": [_view(r) for r in mine]}


def get_one(user, ref):
    return 200, _view(_lookup_mine(user, ref))


def cancel(user, ref):
    res = _lookup_mine(user, ref)
    if res["status"] == "cancelled":
        return 200, _view(res)
    _check_cutoff(res)
    res["status"] = "cancelled"
    return 200, _view(res)


def patch(user, ref, body):
    res = _lookup_mine(user, ref)
    if res["status"] == "cancelled":
        raise ApiError(409, "reservation_cancelled",
                       "reservation is cancelled")
    _check_cutoff(res)

    rest = state.STATE["restaurants"][res["restaurant_id"]]
    tid = res["table_id"]
    local = res["starts_at_local"]
    party = res["party_size"]
    if "table_id" in body:
        if not isinstance(body["table_id"], str):
            raise ApiError(400, "malformed_request",
                           "table_id must be a string")
        tid = body["table_id"]
    if "starts_at_local" in body:
        _parse_local_parts(body["starts_at_local"])
        local = body["starts_at_local"]
    if "party_size" in body:
        party = body["party_size"]

    _table, start, end = _validate_booking(
        rest, tid, local, party, {res["id"]})

    res.update({
        "table_id": tid,
        "starts_at_local": local,
        "party_size": party,
        "starts_at": timeutil.rfc3339(start),
        "ends_at": timeutil.rfc3339(end),
        "start_epoch": start.timestamp(),
        "end_epoch": end.timestamp(),
    })
    return 200, _view(res)
