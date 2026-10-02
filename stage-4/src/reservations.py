"""Reservations: create, list, get, cancel, amend, history and terms.

Stage 2 stores every reservation as a canonical ``table_ids`` list. A
single-table booking is a set of one and still emits ``table_id`` in wire
views; a declared two-table combination emits only ``table_ids``.

Stage 3 snapshots the selected booking policy as ``accepted_terms`` at each
accepted revision. Cancellation uses the accepted cutoff; a real amendment
checks that cutoff first, then revalidates every resulting field under the
policy selected by the resulting local start date.

Validation precedence (coordinator ruling R-6):
    missing fields -> field type/format -> restaurant existence ->
    table existence/membership -> party_size rules -> slot grid ->
    opening hours -> local-time existence -> capacity -> occupancy.

Cutoff (R-7): an action is allowed iff now < starts_at - cutoff;
exactly at the boundary is "within" -> 409 cutoff_passed.
"""

import copy
import re
import secrets
from datetime import datetime, timedelta, timezone

import idempotency
import policies
import state
from errors import ApiError

try:
    import timeutil
except ImportError:
    import _stub_timeutil as timeutil

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_BARE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$")
_REF_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_UNSET = object()


# ---- shared helpers ---------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def reservation_table_ids(res):
    """Internal view: every reservation occupies a list of table ids."""
    ids = res.get("table_ids")
    if isinstance(ids, list):
        return list(ids)
    # Defensive read path for an un-normalised stage-1-shaped record.
    tid = res.get("table_id")
    return [tid] if isinstance(tid, str) else []


def _accepted_terms(res):
    terms = res.get("accepted_terms")
    if isinstance(terms, dict):
        return copy.deepcopy(terms)
    rest = state.STATE["restaurants"].get(res["restaurant_id"])
    if rest is None:
        return {}
    return policies.accepted_terms(policies.policy_zero(rest))


def _view(res):
    ids = reservation_table_ids(res)
    body = {
        "reservation_id": res["id"],
        "reference": res["reference"],
        "restaurant_id": res["restaurant_id"],
        "table_ids": ids,
        "party_size": res["party_size"],
        "status": res["status"],
        "starts_at_local": res["starts_at_local"],
        "starts_at": res["starts_at"],
        "ends_at": res["ends_at"],
        "created_at": res["created_at"],
        "revision": res.get("revision", 1),
        "accepted_terms": _accepted_terms(res),
    }
    if len(ids) == 1:
        body["table_id"] = ids[0]
    return body


def combinable_pairs(rest):
    """Declared pairs in first-declaration order, defensively normalised."""
    by_id = {t.get("id"): t for t in rest.get("tables") or []
             if isinstance(t, dict)}
    pairs = []
    seen = set()
    for pair in rest.get("combinable") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        a, b = pair
        if (not isinstance(a, str) or not isinstance(b, str) or a == b
                or a not in by_id or b not in by_id):
            continue
        key = frozenset((a, b))
        if key in seen:
            continue
        seen.add(key)
        pairs.append([a, b])
    return pairs


def _find_reservation(ref):
    rid = state.STATE["reference_index"].get(ref)
    return state.STATE["reservations"].get(rid) if rid else None


def _lookup_mine(user, ref):
    res = _find_reservation(ref)
    if res is None or res["user_id"] != user["id"]:
        raise ApiError(404, "not_found", "no such reservation")
    return res


def _lookup_private_read(user, ref):
    """History/decision hide existence: bad, absent or foreign auth -> 404."""
    res = _find_reservation(ref)
    if res is None or user is None or res["user_id"] != user["id"]:
        raise ApiError(404, "not_found", "no such reservation")
    return res


def _check_cutoff(res):
    terms = _accepted_terms(res)
    cutoff = timedelta(minutes=terms["cancellation_cutoff_minutes"])
    start = datetime.fromtimestamp(res["start_epoch"], timezone.utc)
    if _now() >= start - cutoff:
        raise ApiError(409, "cutoff_passed",
                       "within cancellation cutoff")


def _check_expected_revision(res, body):
    if "expected_revision" not in body:
        return
    expected = body["expected_revision"]
    if (isinstance(expected, bool) or not isinstance(expected, int)
            or expected < 1):
        raise ApiError(422, "validation_failed",
                       "expected_revision must be a positive integer")
    if expected != res.get("revision", 1):
        raise ApiError(409, "stale_revision",
                       "reservation revision does not match")


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


def _opening_entry(policy, naive):
    weekday = _WEEKDAYS[naive.weekday()]
    for entry in policy.get("opening_hours") or []:
        if entry["weekday"] == weekday:
            return entry
    return None


def _party_rules(party):
    if isinstance(party, bool) or not isinstance(party, int) or party < 1:
        raise ApiError(422, "validation_failed",
                       "party_size must be an integer >= 1")


def _table_ids_shape(value):
    if not isinstance(value, list):
        raise ApiError(400, "malformed_request",
                       "table_ids must be an array")
    if not value:
        raise ApiError(422, "validation_failed",
                       "table_ids must not be empty")
    ids = []
    for tid in value:
        if not isinstance(tid, str):
            raise ApiError(400, "malformed_request",
                           "table_ids entries must be strings")
        ids.append(tid)
    if len(set(ids)) != len(ids):
        raise ApiError(422, "validation_failed",
                       "duplicate table id in table_ids")
    if len(ids) > 2:
        raise ApiError(422, "combination_not_allowed",
                       "at most two tables may be combined")
    return ids


def _selector_ids(body, current=_UNSET):
    """Extract the request's table set; current supplies PATCH defaults."""
    has_one = "table_id" in body
    has_many = "table_ids" in body
    if has_one and has_many:
        raise ApiError(422, "validation_failed",
                       "send table_id or table_ids, not both")
    if has_one:
        tid = body["table_id"]
        if not isinstance(tid, str):
            raise ApiError(400, "malformed_request",
                           "table_id must be a string")
        return [tid]
    if has_many:
        return _table_ids_shape(body["table_ids"])
    if current is _UNSET:
        raise ApiError(422, "validation_failed",
                       "table_id or table_ids is required")
    return list(current)


def _canonical_table_ids(rest, table_ids):
    """Validate a set and return its canonical storage/wire order."""
    ids = _table_ids_shape(table_ids)
    by_id = {t.get("id"): t for t in rest.get("tables") or []
             if isinstance(t, dict)}
    if any(tid not in by_id for tid in ids):
        raise ApiError(404, "not_found", "unknown table")
    if len(ids) == 1:
        return ids
    wanted = set(ids)
    for pair in combinable_pairs(rest):
        if set(pair) == wanted:
            return list(pair)
    raise ApiError(422, "combination_not_allowed",
                   "tables are not a declared combination")


def closure_conflict(rest_id, table_ids, start_epoch, end_epoch):
    """True when an applied closure blocks any member table for the span."""
    wanted = set(table_ids)
    for closure in state.STATE.get("closures", {}).get(rest_id, []):
        if closure["table_id"] not in wanted:
            continue
        if timeutil.overlaps(start_epoch, end_epoch,
                             closure["from_epoch"], closure["to_epoch"]):
            return True
    return False


def _check_overlap(rest_id, table_ids, start_epoch, end_epoch, exclude_ids):
    wanted = set(table_ids)
    if closure_conflict(rest_id, table_ids, start_epoch, end_epoch):
        raise ApiError(409, "table_unavailable",
                       "table is closed for that interval")
    for r in state.STATE["reservations"].values():
        if r["id"] in exclude_ids or r["status"] != "confirmed":
            continue
        if r["restaurant_id"] != rest_id:
            continue
        if not wanted.intersection(reservation_table_ids(r)):
            continue
        if timeutil.overlaps(start_epoch, end_epoch,
                             r["start_epoch"], r["end_epoch"]):
            raise ApiError(409, "table_unavailable",
                           "table already booked for that interval")


def _validate_booking(rest, table_ids, local_str, party, exclude_ids,
                      check_occupancy=True, policy=None):
    """Post-presence/type phases; returns canonical ids, instants, policy."""
    ids = _canonical_table_ids(rest, table_ids)
    _party_rules(party)
    naive = _parse_local_parts(local_str)
    if policy is None:
        policy = policies.selected_policy(rest, naive.date().isoformat())

    entry = _opening_entry(policy, naive)
    if entry is None:
        raise ApiError(422, "outside_opening_hours",
                       "restaurant is closed that day")
    opens, closes = _minutes(entry["opens"]), _minutes(entry["closes"])
    start_min = naive.hour * 60 + naive.minute
    if (start_min - opens) % policy["slot_minutes"] != 0:
        raise ApiError(422, "not_on_slot_grid",
                       "start not on the slot grid")
    if (start_min < opens
            or start_min + policy["reservation_duration_minutes"] > closes):
        raise ApiError(422, "outside_opening_hours",
                       "outside opening hours")

    try:
        start = timeutil.resolve_local(rest["timezone"], local_str)
    except timeutil.InvalidLocalTime:
        raise ApiError(422, "invalid_local_time",
                       "local time does not exist")
    end = add_absolute(
        start, timedelta(minutes=policy["reservation_duration_minutes"]))

    capacity = sum(policy["capacities"][tid] for tid in ids)
    if party > capacity:
        raise ApiError(422, "party_exceeds_capacity",
                       "party_size exceeds table capacity")

    if check_occupancy:
        _check_overlap(rest["id"], ids, start.timestamp(),
                       end.timestamp(), exclude_ids)
    return ids, start, end, policy


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


def _table_change(before, after):
    """History names scalar table_id only for a single-to-single change."""
    if len(before) == 1 and len(after) == 1:
        return {"field": "table_id", "from": before[0], "to": after[0]}
    return {"field": "table_ids", "from": list(before), "to": list(after)}


def created_changes(table_ids, local, party_size):
    if len(table_ids) == 1:
        first = {"field": "table_id", "from": None, "to": table_ids[0]}
    else:
        first = {"field": "table_ids", "from": None, "to": list(table_ids)}
    return [
        first,
        {"field": "starts_at_local", "from": None, "to": local},
        {"field": "party_size", "from": None, "to": party_size},
    ]


def history_entry(seq, at, event, changes, revision, terms):
    return {
        "seq": seq,
        "at": at,
        "event": event,
        "changes": copy.deepcopy(changes),
        "revision": revision,
        "accepted_terms": copy.deepcopy(terms),
    }


def created_history_entry(res):
    return history_entry(
        1, res["created_at"], "created",
        created_changes(reservation_table_ids(res), res["starts_at_local"],
                        res["party_size"]),
        res.get("revision", 1), _accepted_terms(res))


def _append_history(res, event, changes):
    history = res.setdefault("history", [])
    history.append(history_entry(
        len(history) + 1, timeutil.rfc3339(_now()), event, changes,
        res.get("revision", 1), _accepted_terms(res)))


def append_reassigned_history(res, before_ids, after_ids, plan_id):
    """Stage-4 operator repair history: always complete table_ids."""
    history = res.setdefault("history", [])
    entry = history_entry(
        len(history) + 1, timeutil.rfc3339(_now()), "reassigned",
        [{"field": "table_ids", "from": list(before_ids),
          "to": list(after_ids)}],
        res.get("revision", 1), _accepted_terms(res))
    entry["plan_id"] = plan_id
    history.append(entry)


def _changed_plan(res, table_ids, local, party, start, end, policy):
    before_ids = reservation_table_ids(res)
    changes = []
    if table_ids != before_ids:
        changes.append(_table_change(before_ids, table_ids))
    if local != res["starts_at_local"]:
        changes.append({"field": "starts_at_local",
                        "from": res["starts_at_local"], "to": local})
    if party != res["party_size"]:
        changes.append({"field": "party_size",
                        "from": res["party_size"], "to": party})
    return {
        "reservation": res,
        "changed": True,
        "table_ids": table_ids,
        "starts_at_local": local,
        "party_size": party,
        "start": start,
        "end": end,
        "policy": policy,
        "changes": changes,
    }


def plan_amendment(res, body, check_occupancy=True):
    """Validate one PATCH/move item without mutating state.

    The return value always describes the resulting booking so collective
    moves can include unchanged listed bookings in the occupancy matrix.
    """
    if res["status"] == "cancelled":
        raise ApiError(409, "reservation_cancelled",
                       "reservation is cancelled")
    _check_expected_revision(res, body)
    _check_cutoff(res)

    rest = state.STATE["restaurants"][res["restaurant_id"]]
    current_ids = reservation_table_ids(res)
    requested_ids = _selector_ids(body, current=current_ids)
    local = res["starts_at_local"]
    party = res["party_size"]
    if "starts_at_local" in body:
        _parse_local_parts(body["starts_at_local"])
        local = body["starts_at_local"]
    if "party_size" in body:
        party = body["party_size"]

    candidate_ids = _canonical_table_ids(rest, requested_ids)
    if (candidate_ids == current_ids and local == res["starts_at_local"]
            and party == res["party_size"]):
        return {
            "reservation": res,
            "changed": False,
            "table_ids": current_ids,
            "starts_at_local": res["starts_at_local"],
            "party_size": res["party_size"],
            "start_epoch": res["start_epoch"],
            "end_epoch": res["end_epoch"],
            "changes": [],
        }

    table_ids, start, end, policy = _validate_booking(
        rest, candidate_ids, local, party, {res["id"]},
        check_occupancy=check_occupancy)
    return _changed_plan(res, table_ids, local, party, start, end, policy)


def _apply_amendment(plan):
    res = plan["reservation"]
    res.update({
        "table_ids": plan["table_ids"],
        "starts_at_local": plan["starts_at_local"],
        "party_size": plan["party_size"],
        "starts_at": timeutil.rfc3339(plan["start"]),
        "ends_at": timeutil.rfc3339(plan["end"]),
        "start_epoch": plan["start"].timestamp(),
        "end_epoch": plan["end"].timestamp(),
        "accepted_terms": policies.accepted_terms(plan["policy"]),
    })
    res.pop("table_id", None)
    res["revision"] = res.get("revision", 1) + 1
    _append_history(res, "changed", plan["changes"])


def _series_membership(res):
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


def _mark_series_exception(res):
    ser, occurrence = _series_membership(res)
    if ser is None:
        return
    if occurrence is not None:
        occurrence["exception"] = True
    ser["revision"] += 1


def _bump_series_revision(res):
    ser, _occurrence = _series_membership(res)
    if ser is not None:
        ser["revision"] += 1


# ---- endpoints --------------------------------------------------------

def create(user, body):
    for field in ("restaurant_id", "starts_at_local", "party_size"):
        if field not in body:
            raise ApiError(422, "validation_failed",
                           "%s is required" % field)
    requested_ids = _selector_ids(body)

    rid = body["restaurant_id"]
    local = body["starts_at_local"]
    if not isinstance(rid, str):
        raise ApiError(400, "malformed_request",
                       "restaurant_id must be a string")
    _parse_local_parts(local)

    rest = state.STATE["restaurants"].get(rid)
    if rest is None:
        raise ApiError(404, "not_found", "unknown restaurant")
    table_ids, start, end, policy = _validate_booking(
        rest, requested_ids, local, body["party_size"], ())

    res = {
        "id": _new_reservation_id(),
        "reference": _new_reference(),
        "user_id": user["id"],
        "restaurant_id": rid,
        "table_ids": table_ids,
        "party_size": body["party_size"],
        "status": "confirmed",
        "starts_at_local": local,
        "starts_at": timeutil.rfc3339(start),
        "ends_at": timeutil.rfc3339(end),
        "start_epoch": start.timestamp(),
        "end_epoch": end.timestamp(),
        "created_at": timeutil.rfc3339(_now()),
        "revision": 1,
        "accepted_terms": policies.accepted_terms(policy),
    }
    res["history"] = [created_history_entry(res)]
    state.STATE["reservations"][res["id"]] = res
    state.STATE["reference_index"][res["reference"]] = res["id"]
    policies.bump_restaurant_revision(rid)
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


def history(user, ref):
    res = _lookup_private_read(user, ref)
    entries = res.get("history")
    if not entries:
        entries = [created_history_entry(res)]
    return 200, {"reference": res["reference"],
                 "entries": copy.deepcopy(entries)}


def decision(user, ref):
    res = _lookup_private_read(user, ref)
    return 200, {
        "reference": res["reference"],
        "revision": res.get("revision", 1),
        "accepted_terms": _accepted_terms(res),
    }


def cancel(user, ref):
    res = _lookup_mine(user, ref)
    if res["status"] == "cancelled":
        return 200, _view(res)
    _check_cutoff(res)
    res["status"] = "cancelled"
    res["revision"] = res.get("revision", 1) + 1
    _append_history(res, "cancelled", [])
    policies.bump_restaurant_revision(res["restaurant_id"])
    _bump_series_revision(res)
    return 200, _view(res)


def patch(user, ref, body):
    res = _lookup_mine(user, ref)
    plan = plan_amendment(res, body)
    if not plan["changed"]:
        return 200, _view(res)
    _apply_amendment(plan)
    policies.bump_restaurant_revision(res["restaurant_id"])
    _mark_series_exception(res)
    return 200, _view(res)
