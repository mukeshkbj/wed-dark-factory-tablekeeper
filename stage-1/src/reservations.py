"""Reservation endpoints (spec section 8).

Validation order for creates and amendments (matrix R1/R2):

  field of wrong JSON type      -> 400 malformed_request
      (`party_size` is endpoint-exempt: strings/booleans are 422 too)
  required field missing        -> 422 validation_failed
  field format / range          -> 422 validation_failed
  restaurant / table existence  -> 404 not_found
  `starts_at_local` resolves in the restaurant timezone -> invalid_local_time
  on the slot grid              -> not_on_slot_grid
  within opening hours          -> outside_opening_hours
  fits table capacity           -> party_exceeds_capacity
  table free for the interval   -> table_unavailable (409, last)

Every occupancy decision happens inside the state lock, so check-and-act is
one critical section (spec section 1.2).

Owned by the engineer seat.
"""
from __future__ import annotations

import secrets

try:
    from .errors import ApiError
    from . import timeutil
    from . import idempotency
except ImportError:
    from errors import ApiError
    import timeutil
    import idempotency

_REFERENCE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


# ---------------------------------------------------------------- fields

def _check_types(body: dict):
    """Phase 1: wrong-JSON-type fields -> 400 (party_size stays 422)."""
    for field in ("restaurant_id", "table_id", "starts_at_local"):
        if field in body and not isinstance(body[field], str):
            raise ApiError(400, "malformed_request",
                           f"field {field} must be a string")
    if "party_size" in body and (isinstance(body["party_size"], bool)
                                 or not isinstance(body["party_size"], int)):
        raise ApiError(422, "validation_failed", "invalid party_size")


def _req_field(body: dict, field: str) -> str:
    if field not in body:
        raise ApiError(422, "validation_failed", f"missing field: {field}")
    return body[field]


def _req_party_size(body: dict) -> int:
    if "party_size" not in body:
        raise ApiError(422, "validation_failed", "missing field: party_size")
    value = body["party_size"]
    if value < 1:
        raise ApiError(422, "validation_failed", "invalid party_size")
    return value


def _parse_local_field(value: str):
    """Format phase: bare `YYYY-MM-DDTHH:MM`, valid calendar date -> 422."""
    parsed = timeutil.parse_local(value)
    if parsed is None:
        raise ApiError(422, "validation_failed",
                       "starts_at_local must be YYYY-MM-DDTHH:MM")
    return parsed  # (date, minute_of_day)


def _check_party_size_value(value) -> int:
    """Format phase for an already-typed party_size."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ApiError(422, "validation_failed", "invalid party_size")
    return value


# ------------------------------------------------------------- validation

def _resolve_slot(restaurant, parsed_local):
    """Domain phase: resolve, grid, hours. Returns (start_epoch, end_epoch)."""
    day, minute = parsed_local
    tz = timeutil.ZoneInfo(restaurant["timezone"])
    start = timeutil.resolve_local(day, minute, tz)
    if start is None:
        raise ApiError(422, "invalid_local_time",
                       "this local time does not exist")

    duration = restaurant["reservation_duration_minutes"]
    opening = timeutil.opening_for(day, restaurant["opening_hours"])
    if opening is None:
        raise ApiError(422, "outside_opening_hours", "the day is closed")
    opens = timeutil.hhmm_to_minutes(opening["opens"])
    closes = timeutil.hhmm_to_minutes(opening["closes"])
    if (minute - opens) % restaurant["slot_minutes"] != 0:
        raise ApiError(422, "not_on_slot_grid", "start is not on the slot grid")
    if minute < opens or minute + duration > closes:
        raise ApiError(422, "outside_opening_hours",
                       "slot outside opening hours")
    s = timeutil.epoch(start)
    return s, s + duration * 60


def find_table(restaurant, table_id):
    for table in restaurant["tables"]:
        if table["id"] == table_id:
            return table
    return None


def overlaps(confirmed, table_ids, s, e, exclude_ids=()):
    """First confirmed doc sharing a table and overlapping [s, e), or None."""
    wanted = set(table_ids)
    for doc in confirmed:
        if doc["id"] in exclude_ids:
            continue
        if not wanted & set(doc["table_ids"]):
            continue
        if doc["starts_epoch"] < e and s < doc["ends_epoch"]:
            return doc
    return None


def validate_booking(state, restaurant, table_ids, parsed_local, party_size,
                     exclude_ids=(), check_overlap=True):
    """Domain phase shared by create/patch/moves.

    Assumes format-phase checks already ran. Returns (s_epoch, e_epoch).
    Raises the domain errors in R2 order, ending with 409 table_unavailable.
    `check_overlap=False` lets a batch defer occupancy to one global check.
    """
    for table_id in table_ids:
        if find_table(restaurant, table_id) is None:
            raise ApiError(404, "not_found", "no such table")
    s, e = _resolve_slot(restaurant, parsed_local)
    capacity = sum(find_table(restaurant, t)["capacity"] for t in table_ids)
    if party_size > capacity:
        raise ApiError(422, "party_exceeds_capacity",
                       "party_size exceeds table capacity")
    if check_overlap and overlaps(
            state.confirmed_for_restaurant(restaurant["id"]),
            table_ids, s, e, exclude_ids):
        raise ApiError(409, "table_unavailable",
                       "the table is already booked for that interval")
    return s, e


def serialize(state, doc):
    """The public reservation shape (spec 8.7)."""
    restaurant = state.get_restaurant(doc["restaurant_id"])
    tz = timeutil.ZoneInfo(restaurant["timezone"])
    return {
        "reservation_id": doc["id"],
        "reference": doc["reference"],
        "restaurant_id": doc["restaurant_id"],
        "table_id": doc["table_ids"][0],
        "party_size": doc["party_size"],
        "status": doc["status"],
        "starts_at_local": doc["starts_at_local"],
        "starts_at": timeutil.rfc3339(doc["starts_epoch"], tz),
        "ends_at": timeutil.rfc3339(doc["ends_epoch"], tz),
        "created_at": timeutil.rfc3339_utc(doc["created_at"]),
    }


def _mint_reference(state) -> str:
    while True:
        ref = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(8))
        if not state.reference_taken(ref):
            return ref


def _mint_reservation_id(state) -> str:
    while True:
        rid = "res_" + secrets.token_hex(8)
        if not state.reservation_id_taken(rid):
            return rid


def cutoff_passed(state, doc, restaurant) -> bool:
    """True when now is within cutoff of the booking's CURRENT start (R10)."""
    cutoff_at = doc["starts_epoch"] - \
        restaurant["cancellation_cutoff_minutes"] * 60
    return state.now() >= cutoff_at


# -------------------------------------------------------------- endpoints

def create(state, user, body, key):
    """POST /reservations — idempotent write (spec 7, 8)."""
    return idempotency.run(state, user["id"], "POST", "/reservations", key,
                           body, lambda: _create(state, user, body))


def _create(state, user, body):
    _check_types(body)
    restaurant_id = _req_field(body, "restaurant_id")
    table_id = _req_field(body, "table_id")
    starts_at_local = _req_field(body, "starts_at_local")
    party_size = _req_party_size(body)
    parsed_local = _parse_local_field(starts_at_local)

    restaurant = state.get_restaurant(restaurant_id)
    if restaurant is None:
        raise ApiError(404, "not_found", "no such restaurant")
    s, e = validate_booking(state, restaurant, [table_id], parsed_local,
                            party_size)

    doc = {
        "id": _mint_reservation_id(state),
        "reference": _mint_reference(state),
        "user_id": user["id"],
        "restaurant_id": restaurant_id,
        "table_ids": [table_id],
        "starts_at_local": starts_at_local,
        "starts_epoch": s,
        "ends_epoch": e,
        "party_size": party_size,
        "status": "confirmed",
        "created_at": state.now(),
    }
    state.insert_reservation(doc)
    return 201, serialize(state, doc)


def list_mine(state, user):
    """GET /reservations — the caller's bookings, starts_at descending."""
    with state.lock:
        docs = state.reservations_for_user(user["id"])
        docs.sort(key=lambda d: (d["starts_epoch"], d.get("created_at", 0)),
                  reverse=True)
        return 200, {"reservations": [serialize(state, d) for d in docs]}


def get_one(state, user, reference):
    """GET /reservations/{reference} — 404 for other people's bookings."""
    with state.lock:
        doc = state.reservation_by_reference(reference)
        if doc is None or doc["user_id"] != user["id"]:
            raise ApiError(404, "not_found", "no such reservation")
        return 200, serialize(state, doc)


def cancel(state, user, reference):
    """POST /reservations/{reference}/cancel — repeat cancel is not an error."""
    with state.lock:
        doc = state.reservation_by_reference(reference)
        if doc is None or doc["user_id"] != user["id"]:
            raise ApiError(404, "not_found", "no such reservation")
        if doc["status"] == "cancelled":
            return 200, serialize(state, doc)
        restaurant = state.get_restaurant(doc["restaurant_id"])
        if cutoff_passed(state, doc, restaurant):
            raise ApiError(409, "cutoff_passed",
                           "the cancellation cutoff has passed")
        doc["status"] = "cancelled"
        state.update_reservation(doc)
        return 200, serialize(state, doc)


def patch(state, user, reference, body):
    """PATCH /reservations/{reference} — atomic release-and-reserve."""
    with state.lock:
        doc = state.reservation_by_reference(reference)
        if doc is None or doc["user_id"] != user["id"]:
            raise ApiError(404, "not_found", "no such reservation")
        if doc["status"] == "cancelled":
            raise ApiError(409, "reservation_cancelled",
                           "a cancelled booking cannot be amended")
        restaurant = state.get_restaurant(doc["restaurant_id"])
        if cutoff_passed(state, doc, restaurant):
            raise ApiError(409, "cutoff_passed",
                           "the cancellation cutoff has passed")

        merged = merged_doc(state, doc, restaurant, body)
        if merged is None:
            return 200, serialize(state, doc)
        state.update_reservation(merged)
        return 200, serialize(state, merged)


def merged_doc(state, doc, restaurant, body, exclude_ids=None,
               check_overlap=True):
    """Validate a patch-shaped body against the resulting booking.

    Returns the updated doc, or None when nothing actually changes (a PATCH
    that sets a field to its current value is a no-op, not an error). Runs
    the full field/domain validation of POST on the resulting values.
    `exclude_ids` defaults to the patched booking itself for the occupancy
    check; callers with a larger atomic unit (moves) pass their own set and
    `check_overlap=False` to defer occupancy to one batch-level check.
    """
    _check_types(body)
    new_table_id = body.get("table_id", doc["table_ids"][0])
    new_local = body.get("starts_at_local", doc["starts_at_local"])
    new_party = _check_party_size_value(
        body.get("party_size", doc["party_size"]))
    parsed_local = _parse_local_field(new_local)

    s, e = validate_booking(
        state, restaurant, [new_table_id], parsed_local, new_party,
        exclude_ids={doc["id"]} if exclude_ids is None else exclude_ids,
        check_overlap=check_overlap)

    if (new_table_id == doc["table_ids"][0]
            and new_local == doc["starts_at_local"]
            and new_party == doc["party_size"]):
        return None
    merged = dict(doc)
    merged["table_ids"] = [new_table_id]
    merged["starts_at_local"] = new_local
    merged["starts_epoch"] = s
    merged["ends_epoch"] = e
    merged["party_size"] = new_party
    return merged
