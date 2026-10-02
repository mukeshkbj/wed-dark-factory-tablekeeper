"""Test control endpoints: reset, export, import (spec sections 3.3, 10)."""

import copy
import json
from datetime import timedelta

import auth
import policies
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


def _normalise_manager_ids(fixture):
    """Apply the stage-3 R3-2 fixture contract without owning fixtures.py."""
    user_ids = {u["id"] for u in fixture["users"]}
    for rest in fixture["restaurants"]:
        raw = rest.get("manager_user_ids")
        if raw is None:
            rest["manager_user_ids"] = []
            continue
        if not isinstance(raw, list):
            raise fixtures.FixtureError(
                422, "validation_failed",
                "restaurant.manager_user_ids must be an array")
        seen = set()
        managers = []
        for uid in raw:
            if not isinstance(uid, str) or len(uid) > 64:
                raise fixtures.FixtureError(
                    422, "validation_failed",
                    "manager_user_ids entries must be user id strings")
            if uid not in user_ids:
                raise fixtures.FixtureError(
                    422, "validation_failed",
                    "manager_user_ids must name fixture users")
            if uid in seen:
                continue
            seen.add(uid)
            managers.append(uid)
        rest["manager_user_ids"] = managers


def reset(raw):
    body = _parse_object(raw)
    fixture = fixtures.validate_fixture(body)
    _normalise_manager_ids(fixture)

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
        policy = policies.policy_zero(rest)
        end = reservations.add_absolute(
            start,
            timedelta(minutes=policy["reservation_duration_minutes"]))
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
            "revision": 1,
            "accepted_terms": policies.accepted_terms(policy),
        }
        rec["history"] = [reservations.created_history_entry(rec)]
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
        "policies": {},
        "series": {},
        "restaurant_revisions": {rid: 0 for rid in order},
        "idempotency": {},
        "counters": {"user": 0, "reservation": 0, "series": 0},
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


def _normalise_imported_managers(out):
    user_ids = set(out["users"])
    for rest in out["restaurants"].values():
        raw = rest.get("manager_user_ids")
        if raw is None:
            rest["manager_user_ids"] = []
            continue
        if not isinstance(raw, list):
            raise ApiError(422, "validation_failed", "invalid state")
        seen = set()
        managers = []
        for uid in raw:
            if (not isinstance(uid, str) or len(uid) > 64
                    or uid not in user_ids or uid in seen):
                if uid in seen:
                    continue
                raise ApiError(422, "validation_failed", "invalid state")
            seen.add(uid)
            managers.append(uid)
        rest["manager_user_ids"] = managers


def _terms_shape_ok(terms):
    if not isinstance(terms, dict):
        return False
    required = ("policy_version", "slot_minutes",
                "reservation_duration_minutes",
                "cancellation_cutoff_minutes", "opening_hours", "capacities")
    if any(key not in terms for key in required):
        return False
    version = terms["policy_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        return False
    for key in ("slot_minutes", "reservation_duration_minutes",
                "cancellation_cutoff_minutes"):
        value = terms[key]
        if isinstance(value, bool) or not isinstance(value, int):
            return False
    return (isinstance(terms["opening_hours"], list)
            and isinstance(terms["capacities"], dict))


def _history_shape_ok(history):
    if not isinstance(history, list):
        return False
    for index, entry in enumerate(history, 1):
        if (not isinstance(entry, dict) or entry.get("seq") != index
                or entry.get("event") not in ("created", "changed", "cancelled")
                or not isinstance(entry.get("changes"), list)
                or not _terms_shape_ok(entry.get("accepted_terms"))
                or not isinstance(entry.get("at"), str)
                or not isinstance(entry.get("revision"), int)
                or isinstance(entry.get("revision"), bool)
                or entry["revision"] < 1):
            return False
    return True


def _normalise_import_state(st):
    """Accept stage-1/2/3 state and return the stage-3 shape."""
    out = copy.deepcopy(st)
    out.setdefault("policies", {})
    out.setdefault("series", {})
    out.setdefault("restaurant_revisions", {})
    if (not isinstance(out["policies"], dict)
            or not isinstance(out["series"], dict)
            or not isinstance(out["restaurant_revisions"], dict)):
        raise ApiError(422, "validation_failed", "invalid state")

    for rid, rest in out["restaurants"].items():
        if not isinstance(rest, dict):
            raise ApiError(422, "validation_failed", "invalid state")
        combinable = rest.setdefault("combinable", [])
        if not isinstance(combinable, list):
            raise ApiError(422, "validation_failed", "invalid state")
        policies_for_rest = out["policies"].get(rid, [])
        if not isinstance(policies_for_rest, list):
            raise ApiError(422, "validation_failed", "invalid state")
        normalised_policies = []
        seen_versions = set()
        for policy in policies_for_rest:
            if not isinstance(policy, dict):
                raise ApiError(422, "validation_failed", "invalid state")
            version = policy.get("policy_version")
            if (isinstance(version, bool) or not isinstance(version, int)
                    or version < 1 or version in seen_versions):
                raise ApiError(422, "validation_failed", "invalid state")
            seen_versions.add(version)
            try:
                checked = policies._validate_policy(rest, policy)
            except ApiError:
                raise ApiError(422, "validation_failed", "invalid state")
            checked["policy_version"] = version
            normalised_policies.append(checked)
        out["policies"][rid] = normalised_policies
        revision = out["restaurant_revisions"].get(rid, 0)
        if (isinstance(revision, bool) or not isinstance(revision, int)
                or revision < 0):
            raise ApiError(422, "validation_failed", "invalid state")
        out["restaurant_revisions"][rid] = revision
    if set(out["policies"]).difference(out["restaurants"]):
        raise ApiError(422, "validation_failed", "invalid state")
    if set(out["restaurant_revisions"]).difference(out["restaurants"]):
        raise ApiError(422, "validation_failed", "invalid state")
    _normalise_imported_managers(out)

    counters = out["counters"]
    for key in ("user", "reservation", "series"):
        value = counters.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ApiError(422, "validation_failed", "invalid state")
        counters[key] = value

    for sid, ser in out["series"].items():
        if (not isinstance(ser, dict)
                or not isinstance(ser.get("occurrences"), list)):
            raise ApiError(422, "validation_failed", "invalid state")

    for res in out["reservations"].values():
        if not isinstance(res, dict):
            raise ApiError(422, "validation_failed", "invalid state")
        rest = out["restaurants"].get(res.get("restaurant_id"))
        if rest is None:
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
        try:
            res["table_ids"] = reservations._canonical_table_ids(rest, ids)
        except ApiError:
            raise ApiError(422, "validation_failed", "invalid state")

        revision = res.get("revision", 1)
        if (isinstance(revision, bool) or not isinstance(revision, int)
                or revision < 1):
            raise ApiError(422, "validation_failed", "invalid state")
        res["revision"] = revision
        terms = res.get("accepted_terms")
        if terms is None:
            res["accepted_terms"] = policies.accepted_terms(
                policies.policy_zero(rest))
        elif not _terms_shape_ok(terms):
            raise ApiError(422, "validation_failed", "invalid state")
        history = res.get("history")
        if history is None:
            res["history"] = [reservations.created_history_entry(res)]
        elif not _history_shape_ok(history):
            raise ApiError(422, "validation_failed", "invalid state")

    for res in out["reservations"].values():
        sid = res.get("series_id")
        if sid is not None and sid not in out["series"]:
            raise ApiError(422, "validation_failed", "invalid state")
    for sid, ser in out["series"].items():
        if (ser.get("id") != sid or ser.get("user_id") not in out["users"]
                or ser.get("restaurant_id") not in out["restaurants"]
                or not isinstance(ser.get("revision"), int)
                or isinstance(ser.get("revision"), bool)
                or ser["revision"] < 1):
            raise ApiError(422, "validation_failed", "invalid state")
        seen_indices = set()
        for occurrence in ser["occurrences"]:
            if not isinstance(occurrence, dict):
                raise ApiError(422, "validation_failed", "invalid state")
            index = occurrence.get("index")
            reservation_id = occurrence.get("reservation_id")
            if (isinstance(index, bool) or not isinstance(index, int)
                    or index < 0 or index in seen_indices
                    or not isinstance(occurrence.get("exception"), bool)
                    or reservation_id not in out["reservations"]):
                raise ApiError(422, "validation_failed", "invalid state")
            res = out["reservations"][reservation_id]
            if (res.get("series_id") != sid
                    or res.get("series_index") != index
                    or res.get("user_id") != ser["user_id"]
                    or res.get("restaurant_id") != ser["restaurant_id"]):
                raise ApiError(422, "validation_failed", "invalid state")
            seen_indices.add(index)

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
