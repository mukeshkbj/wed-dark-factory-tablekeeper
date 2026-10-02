"""Recurring reservation series (stages 3 and 4)."""

import copy
import re
from datetime import datetime, timedelta

import idempotency
import policies
import reservations
import state
from errors import ApiError

try:
    import timeutil
except ImportError:
    import _stub_timeutil as timeutil


def _require_fields(body):
    for field in ("anchor_reference", "count", "interval_weeks"):
        if field not in body:
            raise ApiError(422, "validation_failed", "%s is required" % field)
    anchor = body["anchor_reference"]
    if not isinstance(anchor, str):
        raise ApiError(400, "malformed_request",
                       "anchor_reference must be a string")
    for field, lo, hi in (("count", 2, 12), ("interval_weeks", 1, 4)):
        value = body[field]
        if (isinstance(value, bool) or not isinstance(value, int)
                or not lo <= value <= hi):
            raise ApiError(422, "validation_failed", "invalid %s" % field)
    return anchor, body["count"], body["interval_weeks"]


def _new_series_id():
    counters = state.STATE["counters"]
    while True:
        counters["series"] = counters.get("series", 0) + 1
        sid = "ser_%d" % counters["series"]
        if sid not in state.STATE["series"]:
            return sid


def _view(ser):
    occurrences = []
    for occurrence in ser["occurrences"]:
        res = state.STATE["reservations"][occurrence["reservation_id"]]
        occurrences.append({
            "index": occurrence["index"],
            "reference": res["reference"],
            "exception": bool(occurrence["exception"]),
            "reservation": reservations._view(res),
        })
    return {
        "series_id": ser["id"],
        "revision": ser["revision"],
        "interval_weeks": ser["interval_weeks"],
        "occurrences": occurrences,
    }


def _series_local(anchor, index, interval_weeks):
    naive = reservations._parse_local_parts(anchor["starts_at_local"])
    day = naive.date() + timedelta(days=index * interval_weeks * 7)
    return "%sT%02d:%02d" % (day.isoformat(), naive.hour, naive.minute)


def _check_planned_overlap(rest_id, plans, table_ids, start, end):
    for planned in plans:
        if not set(table_ids).intersection(planned["table_ids"]):
            continue
        if timeutil.overlaps(start.timestamp(), end.timestamp(),
                             planned["start"].timestamp(),
                             planned["end"].timestamp()):
            raise ApiError(409, "table_unavailable",
                           "series occurrences overlap")


def adopt(user, body):
    anchor_ref, count, interval_weeks = _require_fields(body)
    anchor = reservations._find_reservation(anchor_ref)
    if anchor is None or anchor["user_id"] != user["id"]:
        raise ApiError(404, "not_found", "no such reservation")
    if anchor["status"] == "cancelled":
        raise ApiError(409, "reservation_cancelled",
                       "reservation is cancelled")
    if anchor.get("series_id"):
        raise ApiError(409, "already_in_series",
                       "reservation is already in a series")
    reservations._check_cutoff(anchor)

    rest = state.STATE["restaurants"][anchor["restaurant_id"]]
    anchor_ids = reservations.reservation_table_ids(anchor)
    plans = []
    for index in range(1, count):
        local = _series_local(anchor, index, interval_weeks)
        policy = policies.selected_policy(rest, local[:10])
        table_ids, start, end, policy = reservations._validate_booking(
            rest, anchor_ids, local, anchor["party_size"], set(),
            check_occupancy=False, policy=policy)
        reservations._check_overlap(rest["id"], table_ids,
                                    start.timestamp(), end.timestamp(), set())
        _check_planned_overlap(rest["id"], plans, table_ids, start, end)
        plans.append({
            "index": index,
            "table_ids": table_ids,
            "starts_at_local": local,
            "start": start,
            "end": end,
            "policy": policy,
        })

    series_id = _new_series_id()
    ser = {
        "id": series_id,
        "user_id": user["id"],
        "restaurant_id": rest["id"],
        "interval_weeks": interval_weeks,
        "revision": 1,
        "occurrences": [{
            "index": 0,
            "reservation_id": anchor["id"],
            "exception": False,
        }],
    }
    anchor["series_id"] = series_id
    anchor["series_index"] = 0

    for plan in plans:
        res = {
            "id": reservations._new_reservation_id(),
            "reference": reservations._new_reference(),
            "user_id": user["id"],
            "restaurant_id": rest["id"],
            "table_ids": plan["table_ids"],
            "party_size": anchor["party_size"],
            "status": "confirmed",
            "starts_at_local": plan["starts_at_local"],
            "starts_at": timeutil.rfc3339(plan["start"]),
            "ends_at": timeutil.rfc3339(plan["end"]),
            "start_epoch": plan["start"].timestamp(),
            "end_epoch": plan["end"].timestamp(),
            "created_at": timeutil.rfc3339(reservations._now()),
            "revision": 1,
            "accepted_terms": policies.accepted_terms(plan["policy"]),
            "series_id": series_id,
            "series_index": plan["index"],
        }
        res["history"] = [reservations.created_history_entry(res)]
        state.STATE["reservations"][res["id"]] = res
        state.STATE["reference_index"][res["reference"]] = res["id"]
        ser["occurrences"].append({
            "index": plan["index"],
            "reservation_id": res["id"],
            "exception": False,
        })

    state.STATE["series"][series_id] = ser
    policies.bump_restaurant_revision(rest["id"])
    return 201, _view(ser)


def adopt_idempotent(user, method, path, key, body):
    return idempotency.execute(
        user["id"], method, path, key, body,
        lambda: adopt(user, body))


def get(user, series_id):
    ser = state.STATE["series"].get(series_id)
    if ser is None or user is None or ser["user_id"] != user["id"]:
        raise ApiError(404, "not_found", "no such series")
    return 200, copy.deepcopy(_view(ser))


_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")


def _amend_fields(body, count):
    for field in ("expected_revision", "from_index", "local_time"):
        if field not in body:
            raise ApiError(422, "validation_failed",
                           "%s is required" % field)
    expected = body["expected_revision"]
    if (isinstance(expected, bool) or not isinstance(expected, int)
            or expected < 1):
        raise ApiError(422, "validation_failed",
                       "expected_revision must be a positive integer")
    from_index = body["from_index"]
    if (isinstance(from_index, bool) or not isinstance(from_index, int)
            or not 0 <= from_index < count):
        raise ApiError(422, "validation_failed",
                       "from_index must name an occurrence")
    local_time = body["local_time"]
    if not isinstance(local_time, str) or not _HHMM_RE.match(local_time):
        raise ApiError(422, "validation_failed",
                       "local_time must be HH:MM")
    hour, minute = int(local_time[:2]), int(local_time[3:5])
    if hour > 23 or minute > 59:
        raise ApiError(422, "validation_failed",
                       "local_time must be HH:MM")
    return expected, from_index, local_time


def amend(user, series_id, body):
    ser = state.STATE["series"].get(series_id)
    if ser is None or ser["user_id"] != user["id"]:
        raise ApiError(404, "not_found", "no such series")
    expected, from_index, local_time = _amend_fields(
        body, len(ser["occurrences"]))
    if expected != ser["revision"]:
        raise ApiError(409, "stale_revision",
                       "series revision does not match")

    rest = state.STATE["restaurants"][ser["restaurant_id"]]
    planned = []
    for occurrence in ser["occurrences"]:
        if occurrence["index"] < from_index or occurrence["exception"]:
            continue
        res = state.STATE["reservations"][occurrence["reservation_id"]]
        if res["status"] == "cancelled":
            continue
        local = "%sT%s" % (res["starts_at_local"][:10], local_time)
        if local == res["starts_at_local"]:
            continue
        plan = reservations.plan_amendment(
            res, {"starts_at_local": local}, check_occupancy=False)
        if plan["changed"]:
            planned.append(plan)

    changed_ids = {plan["reservation"]["id"] for plan in planned}
    for index, plan in enumerate(planned):
        start = plan["start"].timestamp()
        end = plan["end"].timestamp()
        reservations._check_overlap(rest["id"], plan["table_ids"],
                                    start, end, changed_ids)
        for other in planned[:index]:
            if not set(plan["table_ids"]).intersection(other["table_ids"]):
                continue
            if timeutil.overlaps(start, end,
                                 other["start"].timestamp(),
                                 other["end"].timestamp()):
                raise ApiError(409, "table_unavailable",
                               "series occurrences overlap")

    for plan in planned:
        reservations._apply_amendment(plan)
    if planned:
        ser["revision"] += 1
        policies.bump_restaurant_revision(rest["id"])
    return 201, _view(ser)


def amend_idempotent(user, method, path, key, series_id, body):
    return idempotency.execute(
        user["id"], method, path, key, body,
        lambda: amend(user, series_id, body))
