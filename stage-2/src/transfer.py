"""Test control endpoints: reset, export, import (spec sections 3.3, 10)."""

import copy
import json
from datetime import timedelta

import auth
import reservations
import state
from errors import ApiError

try:
    import fixtures
except ImportError:
    import _stub_fixtures as fixtures
try:
    import timeutil
except ImportError:
    import _stub_timeutil as timeutil


def _parse_object(raw):
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError(400, "malformed_request", "body is not JSON")
    if not isinstance(obj, dict):
        raise ApiError(400, "malformed_request",
                       "body must be a JSON object")
    return obj


# ---- reset -------------------------------------------------------------

def _seed_table_ids(rest, seed):
    """Normalise a seeded reservation to the internal table_ids list."""
    has_one = "table_id" in seed
    has_many = "table_ids" in seed
    if has_one == has_many:
        raise fixtures.FixtureError(
            422, "validation_failed",
            "seeded reservation needs table_id or table_ids")
    selector = {"table_id": seed["table_id"]} if has_one else {
        "table_ids": seed["table_ids"]}
    try:
        raw_ids = reservations._selector_ids(selector)
        return reservations._canonical_table_ids(rest, raw_ids)
    except ApiError as exc:
        raise fixtures.FixtureError(
            422, "validation_failed", exc.message)


def reset(raw):
    body = _parse_object(raw)
    fixture = fixtures.validate_fixture(body)

    users, email_index = {}, {}
    for u in fixture["users"]:
        users[u["id"]] = {
            "id": u["id"],
            "email": u["email"],
            "display_name": u["display_name"],
            "password_hash": auth._hash_password(u["password"]),
        }
        email_index[u["email"].lower()] = u["id"]

    restaurants_by_id, order = {}, []
    for r in fixture["restaurants"]:
        restaurants_by_id[r["id"]] = copy.deepcopy(r)
        order.append(r["id"])

    records, ref_index = {}, {}
    now = reservations._now()
    for s in fixture["reservations"]:
        rest = restaurants_by_id[s["restaurant_id"]]
        local = s["starts_at_local"]
        try:
            start = timeutil.resolve_local(rest["timezone"], local)
        except (timeutil.InvalidLocalTime, timeutil.MalformedLocalTime):
            raise fixtures.FixtureError(422, "validation_failed",
                                      "reservation.starts_at_local invalid")
        end = reservations.add_absolute(
            start, timedelta(minutes=rest["reservation_duration_minutes"]))
        rec = {
            "id": s["id"],
            "reference": s["reference"],
            "user_id": s["user_id"],
            "restaurant_id": s["restaurant_id"],
            "table_ids": _seed_table_ids(rest, s),
            "party_size": s["party_size"],
            "status": s.get("status", "confirmed"),
            "starts_at_local": local,
            "starts_at": timeutil.rfc3339(start),
            "ends_at": timeutil.rfc3339(end),
            "start_epoch": start.timestamp(),
            "end_epoch": end.timestamp(),
            "created_at": timeutil.rfc3339(now),
        }
        records[rec["id"]] = rec
        ref_index[rec["reference"]] = rec["id"]

    state.STATE.update({
        "users": users,
        "email_index": email_index,
        "tokens": {},
        "restaurants": restaurants_by_id,
        "restaurant_order": order,
        "reservations": records,
        "reference_index": ref_index,
        "idempotency": {},
        "counters": {"user": 0, "reservation": 0},
    })
    return 204, None


# ---- export / import -----------------------------------------------------

def export():
    return 200, {
        "track": "tablekeeper",
        "format_version": 1,
        "state": state.export_state(),
    }

_STATE_DICT_KEYS = ("users", "email_index", "tokens", "restaurants",
                    "reservations", "reference_index", "idempotency",
                    "counters")


def _state_shape_ok(st):
    if not isinstance(st, dict):
        return False
    if not all(isinstance(st.get(k), dict) for k in _STATE_DICT_KEYS):
        return False
    return isinstance(st.get("restaurant_order"), list)


def _normalise_import_state(st):
    """Accept stage-1 and stage-2 state; return the stage-2 shape."""
    out = copy.deepcopy(st)
    for rest in out["restaurants"].values():
        if not isinstance(rest, dict):
            raise ApiError(422, "validation_failed", "invalid state")
        combinable = rest.setdefault("combinable", [])
        if not isinstance(combinable, list):
            raise ApiError(422, "validation_failed", "invalid state")
    for res in out["reservations"].values():
        if not isinstance(res, dict):
            raise ApiError(422, "validation_failed", "invalid state")
        if "table_ids" not in res:
            tid = res.get("table_id")
            if not isinstance(tid, str):
                raise ApiError(422, "validation_failed", "invalid state")
            res["table_ids"] = [tid]
        res.pop("table_id", None)
        ids = res["table_ids"]
        if (not isinstance(ids, list) or not ids
                or any(not isinstance(tid, str) for tid in ids)):
            raise ApiError(422, "validation_failed", "invalid state")
    return out


def do_import(raw):
    obj = _parse_object(raw)
    if obj.get("track") != "tablekeeper" or obj.get("format_version") != 1:
        raise ApiError(422, "validation_failed",
                       "unrecognized export format")
    st = obj.get("state")
    if not _state_shape_ok(st):
        raise ApiError(422, "validation_failed", "invalid state")
    state.import_state(_normalise_import_state(st))
    return 204, None
