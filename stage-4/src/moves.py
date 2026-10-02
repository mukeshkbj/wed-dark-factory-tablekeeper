"""Atomic multi-booking amendment (spec section 11).

All-or-nothing: per-booking errors are resolved in input order with the
revision, cutoff and amendment checks used by an individual PATCH;
occupancy is a batch-level check afterwards. Nothing mutates until every
move has passed, so failure leaves occupancy, records, histories, series
state and retry keys untouched.

Stage 2 accepts ``table_id`` (a singleton set) or ``table_ids`` (one or a
declared pair) in every move item. Stage 3 additionally accepts optional
``expected_revision`` per item.
"""

import idempotency
import policies
import reservations
import state
from errors import ApiError

try:
    import timeutil
except ImportError:
    import _stub_timeutil as timeutil


def _validate_shape(body):
    # Ruling G-3: `moves` of the wrong JSON type -> 400 malformed_request;
    # a correctly-typed array with invalid structure (size, non-object
    # items, dup/non-string refs) -> 422 validation_failed.
    if "moves" not in body:
        raise ApiError(422, "validation_failed", "moves is required")
    mv = body["moves"]
    if not isinstance(mv, list):
        raise ApiError(400, "malformed_request", "moves must be an array")
    if not 1 <= len(mv) <= 8:
        raise ApiError(422, "validation_failed",
                       "moves must contain 1..8 items")
    seen = set()
    for item in mv:
        if not isinstance(item, dict):
            raise ApiError(422, "validation_failed",
                           "move items must be objects")
        ref = item.get("reference")
        if not isinstance(ref, str):
            raise ApiError(422, "validation_failed",
                           "move reference must be a string")
        if ref in seen:
            raise ApiError(422, "validation_failed",
                           "duplicate reference in moves")
        seen.add(ref)
    return mv


def _series_member(res):
    sid = res.get("series_id")
    if not sid:
        return None, None
    ser = state.STATE.get("series", {}).get(sid)
    if ser is None:
        return None, None
    for occurrence in ser["occurrences"]:
        if occurrence["reservation_id"] == res["id"]:
            return ser, occurrence
    return ser, None


def apply_moves(user, body):
    mv = _validate_shape(body)

    # Resolve references in input order: unknown or foreign -> 404.
    items = []
    for item in mv:
        res = reservations._find_reservation(item["reference"])
        if res is None or res["user_id"] != user["id"]:
            raise ApiError(404, "not_found", "no such reservation")
        items.append((item, res))

    # All bookings must share one restaurant.
    rest_id = items[0][1]["restaurant_id"]
    if any(res["restaurant_id"] != rest_id for _item, res in items):
        raise ApiError(422, "validation_failed",
                       "all moves must be in one restaurant")
    rest = state.STATE["restaurants"][rest_id]

    # Per-booking checks in input order use individual PATCH semantics.
    # Occupancy remains deferred to the batch-level check below.
    planned = []
    for item, res in items:
        planned.append(reservations.plan_amendment(
            res, item, check_occupancy=False))

    # Batch occupancy: resulting intervals must not collide with each
    # other or with unlisted confirmed bookings on any member table.
    listed = {res["id"] for _item, res in items}
    for i, plan in enumerate(planned):
        start = plan.get("start_epoch")
        end = plan.get("end_epoch")
        if start is None:
            start = plan["start"].timestamp()
            end = plan["end"].timestamp()
        members = set(plan["table_ids"])
        for other in planned[i + 1:]:
            other_start = other.get("start_epoch")
            other_end = other.get("end_epoch")
            if other_start is None:
                other_start = other["start"].timestamp()
                other_end = other["end"].timestamp()
            if not members.intersection(other["table_ids"]):
                continue
            if timeutil.overlaps(start, end, other_start, other_end):
                raise ApiError(409, "table_unavailable",
                               "moves overlap each other")
        for res2 in state.STATE["reservations"].values():
            if res2["id"] in listed or res2["status"] != "confirmed":
                continue
            if res2["restaurant_id"] != rest_id:
                continue
            if not members.intersection(
                    reservations.reservation_table_ids(res2)):
                continue
            if timeutil.overlaps(start, end, res2["start_epoch"],
                                 res2["end_epoch"]):
                raise ApiError(409, "table_unavailable",
                               "table already booked for that interval")

    # Commit: nothing above mutated state, so the batch is atomic.
    changed = [plan for plan in planned if plan["changed"]]
    affected_series = set()
    for plan in changed:
        reservations._apply_amendment(plan)
        ser, occurrence = _series_member(plan["reservation"])
        if ser is not None:
            if occurrence is not None:
                occurrence["exception"] = True
            affected_series.add(ser["id"])
    for sid in affected_series:
        state.STATE["series"][sid]["revision"] += 1
    if changed:
        policies.bump_restaurant_revision(rest["id"])
    return 201, {"reservations": [reservations._view(plan["reservation"])
                                  for plan in planned]}


def apply_idempotent(user, method, path, key, body):
    return idempotency.execute(
        user["id"], method, path, key, body,
        lambda: apply_moves(user, body))
