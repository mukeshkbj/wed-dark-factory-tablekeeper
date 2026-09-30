"""Atomic reservation moves (spec section 11).

`POST /reservation-moves` changes several of the caller's bookings in one
all-or-nothing request. Order of business, per the spec and matrix R15:

  1. Shape: `moves` is a list of 1..8 objects with distinct string
     references -> 422 validation_failed.
  2. Every reference resolves to a booking of the caller -> 404 not_found
     (input order).
  3. All bookings sit in the same restaurant -> 422 validation_failed.
  4. Per item, in input order: cancelled -> 409 reservation_cancelled;
     cutoff -> 409 cutoff_passed; then ordinary PATCH field and domain
     validation of the resulting booking (without occupancy).
  5. One global occupancy check across the resulting bookings and every
     unlisted confirmed booking -> 409 table_unavailable.
  6. Commit everything, or nothing at all — including the retry ledger.

Owned by the engineer seat.
"""
from __future__ import annotations

try:
    from .errors import ApiError
    from . import reservations
    from . import idempotency
except ImportError:
    from errors import ApiError
    import reservations
    import idempotency


def handle(state, user, body, key):
    return idempotency.run(state, user["id"], "POST", "/reservation-moves",
                           key, body, lambda: _apply(state, user, body))


def _apply(state, user, body):
    moves = body.get("moves")
    if moves is None:
        raise ApiError(422, "validation_failed", "missing field: moves")
    if not isinstance(moves, list):
        raise ApiError(400, "malformed_request", "moves must be a list")
    if not 1 <= len(moves) <= 8:
        raise ApiError(422, "validation_failed",
                       "moves must contain 1 to 8 items")

    references = []
    for item in moves:
        if not isinstance(item, dict):
            raise ApiError(422, "validation_failed",
                           "each move must be an object")
        reference = item.get("reference")
        if not isinstance(reference, str) or not reference:
            raise ApiError(422, "validation_failed",
                           "each move needs a string reference")
        if reference in references:
            raise ApiError(422, "validation_failed",
                           "duplicate reference in moves")
        references.append(reference)

    docs = []
    for reference in references:  # input order
        doc = state.reservation_by_reference(reference)
        if doc is None or doc["user_id"] != user["id"]:
            raise ApiError(404, "not_found", "no such reservation")
        docs.append(doc)

    restaurant_ids = {d["restaurant_id"] for d in docs}
    if len(restaurant_ids) != 1:
        raise ApiError(422, "validation_failed",
                       "moves must target one restaurant")
    restaurant = state.get_restaurant(docs[0]["restaurant_id"])

    resulting = []
    for item, doc in zip(moves, docs):
        if doc["status"] == "cancelled":
            raise ApiError(409, "reservation_cancelled",
                           "a cancelled booking cannot be moved")
        if reservations.cutoff_passed(state, doc, restaurant):
            raise ApiError(409, "cutoff_passed",
                           "the cancellation cutoff has passed")
        merged = reservations.merged_doc(
            state, doc, restaurant, item, check_overlap=False)
        resulting.append(merged if merged is not None else doc)

    # One global occupancy check: resulting bookings against each other and
    # against every confirmed booking not in the batch (any owner — a table
    # is physical). Unchanged listed bookings still occupy their slots.
    confirmed = state.confirmed_for_restaurant(restaurant["id"])
    listed = {d["id"] for d in docs}
    obstacles = [d for d in confirmed if d["id"] not in listed]
    for i, doc in enumerate(resulting):
        if overlaps_any(obstacles + resulting[:i] + resulting[i + 1:],
                        doc):
            raise ApiError(409, "table_unavailable",
                           "the requested moves would overlap a booking")

    for doc in resulting:
        state.update_reservation(doc)
    return 201, {"reservations": [reservations.serialize(state, d)
                                  for d in resulting]}


def overlaps_any(others, doc) -> bool:
    mine = set(doc["table_ids"])
    for other in others:
        if other["id"] == doc["id"]:
            continue
        if not mine & set(other["table_ids"]):
            continue
        if other["starts_epoch"] < doc["ends_epoch"] \
                and doc["starts_epoch"] < other["ends_epoch"]:
            return True
    return False
