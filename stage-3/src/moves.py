"""Atomic multi-booking amendment (spec section 11).

All-or-nothing: per-booking errors are resolved in input order with the
cutoff check preceding field errors for each booking; occupancy is a
batch-level check afterwards. Nothing mutates until every move has
passed, so failure leaves occupancy, records and retry keys untouched.

Stage 2 accepts ``table_id`` (a singleton set) or ``table_ids`` (one or a
declared pair) in every move item.
"""

import idempotency
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

    # Per-booking checks in input order: cancelled, cutoff, then the
    # ordinary amendment field validations (occupancy deferred to the
    # batch check below).
    planned = []
    for item, res in items:
        if res["status"] == "cancelled":
            raise ApiError(409, "reservation_cancelled",
                           "reservation is cancelled")
        reservations._check_cutoff(res)

        requested_ids = reservations._selector_ids(
            item, current=reservations.reservation_table_ids(res))
        local, party = res["starts_at_local"], res["party_size"]
        if "starts_at_local" in item:
            reservations._parse_local_parts(item["starts_at_local"])
            local = item["starts_at_local"]
        if "party_size" in item:
            party = item["party_size"]

        table_ids, start, end = reservations._validate_booking(
            rest, requested_ids, local, party, set(),
            check_occupancy=False)
        planned.append((res, table_ids, local, party, start, end))

    # Batch occupancy: resulting intervals must not collide with each
    # other or with unlisted confirmed bookings on any member table.
    listed = {res["id"] for _item, res in items}
    for i, (_res, table_ids, _local, _party, start, end) in enumerate(planned):
        s, e = start.timestamp(), end.timestamp()
        members = set(table_ids)
        for res2, table_ids2, _l2, _p2, st2, en2 in planned[i + 1:]:
            if not members.intersection(table_ids2):
                continue
            if timeutil.overlaps(s, e, st2.timestamp(), en2.timestamp()):
                raise ApiError(409, "table_unavailable",
                               "moves overlap each other")
        for r in state.STATE["reservations"].values():
            if r["id"] in listed or r["status"] != "confirmed":
                continue
            if r["restaurant_id"] != rest_id:
                continue
            if not members.intersection(
                    reservations.reservation_table_ids(r)):
                continue
            if timeutil.overlaps(s, e, r["start_epoch"], r["end_epoch"]):
                raise ApiError(409, "table_unavailable",
                               "table already booked for that interval")

    # Commit: nothing above mutated state, so the batch is atomic.
    for res, table_ids, local, party, start, end in planned:
        res.update({
            "table_ids": table_ids,
            "starts_at_local": local,
            "party_size": party,
            "starts_at": timeutil.rfc3339(start),
            "ends_at": timeutil.rfc3339(end),
            "start_epoch": start.timestamp(),
            "end_epoch": end.timestamp(),
        })
        res.pop("table_id", None)
    return 201, {"reservations": [reservations._view(res)
                                  for res, _t, _l, _p, _s, _e in planned]}


def apply_idempotent(user, method, path, key, body):
    return idempotency.execute(
        user["id"], method, path, key, body,
        lambda: apply_moves(user, body))
