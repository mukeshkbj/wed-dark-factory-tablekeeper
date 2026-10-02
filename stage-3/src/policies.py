"""Restaurant booking policies and policy selection."""

import copy
import re
from datetime import date

import idempotency
import state
from errors import ApiError

_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")
_REQUIRED = ("effective_from", "slot_minutes", "reservation_duration_minutes",
             "cancellation_cutoff_minutes", "opening_hours", "capacities")


def policy_zero(rest):
    """The immutable fixture policy, with capacities as a complete map."""
    return {
        "policy_version": 0,
        "slot_minutes": rest["slot_minutes"],
        "reservation_duration_minutes": rest["reservation_duration_minutes"],
        "cancellation_cutoff_minutes": rest["cancellation_cutoff_minutes"],
        "opening_hours": copy.deepcopy(rest["opening_hours"]),
        "capacities": {t["id"]: t["capacity"] for t in rest["tables"]},
    }


def accepted_terms(policy):
    return {k: copy.deepcopy(v) for k, v in policy.items()
            if k != "effective_from"}


def context(rest, policy):
    """A restaurant-shaped view whose decision fields come from `policy`."""
    ctx = dict(rest)
    ctx.update({
        "slot_minutes": policy["slot_minutes"],
        "reservation_duration_minutes": policy["reservation_duration_minutes"],
        "cancellation_cutoff_minutes": policy["cancellation_cutoff_minutes"],
        "opening_hours": copy.deepcopy(policy["opening_hours"]),
    })
    return ctx


def list_published(restaurant_id):
    return copy.deepcopy(
        state.STATE.get("policies", {}).get(restaurant_id, []))


def selected_policy(rest, local_date):
    """Greatest effective_from <= local_date; ties choose greatest version."""
    selected = policy_zero(rest)
    best = ("", 0)
    for policy in state.STATE.get("policies", {}).get(rest["id"], []):
        key = (policy["effective_from"], policy["policy_version"])
        if policy["effective_from"] <= local_date and key > best:
            best = key
            selected = policy
    return selected


def bump_restaurant_revision(restaurant_id):
    revisions = state.STATE.setdefault("restaurant_revisions", {})
    revisions[restaurant_id] = revisions.get(restaurant_id, 0) + 1


def _int_range(value, lo, hi, field):
    if (isinstance(value, bool) or not isinstance(value, int)
            or not lo <= value <= hi):
        raise ApiError(422, "validation_failed", "invalid %s" % field)


def _hhmm(value, field):
    if not isinstance(value, str) or not _HHMM_RE.match(value):
        raise ApiError(422, "validation_failed", "%s must be HH:MM" % field)
    minutes = int(value[:2]) * 60 + int(value[3:5])
    if minutes >= 24 * 60:
        raise ApiError(422, "validation_failed", "%s must be HH:MM" % field)
    return minutes


def _validate_policy(rest, body):
    for field in _REQUIRED:
        if field not in body:
            raise ApiError(422, "validation_failed", "%s is required" % field)

    effective = body["effective_from"]
    if (not isinstance(effective, str) or not _DATE_RE.match(effective)):
        raise ApiError(422, "validation_failed",
                       "effective_from must be YYYY-MM-DD")
    try:
        date.fromisoformat(effective)
    except ValueError:
        raise ApiError(422, "validation_failed", "invalid effective_from")

    _int_range(body["slot_minutes"], 1, 1440, "slot_minutes")
    _int_range(body["reservation_duration_minutes"], 1, 1440,
               "reservation_duration_minutes")
    _int_range(body["cancellation_cutoff_minutes"], 0, 10080,
               "cancellation_cutoff_minutes")

    hours = body["opening_hours"]
    if not isinstance(hours, list):
        raise ApiError(422, "validation_failed",
                       "opening_hours must be an array")
    seen = set()
    checked_hours = []
    for entry in hours:
        if not isinstance(entry, dict):
            raise ApiError(422, "validation_failed",
                           "opening_hours entries must be objects")
        weekday = entry.get("weekday")
        if weekday not in _WEEKDAYS or weekday in seen:
            raise ApiError(422, "validation_failed",
                           "invalid or duplicate opening_hours weekday")
        seen.add(weekday)
        opens = _hhmm(entry.get("opens"), "opening_hours.opens")
        closes = _hhmm(entry.get("closes"), "opening_hours.closes")
        if closes <= opens:
            raise ApiError(422, "validation_failed",
                           "opening_hours.closes must be later than opens")
        checked_hours.append({
            "weekday": weekday, "opens": entry["opens"],
            "closes": entry["closes"],
        })

    capacities = body["capacities"]
    expected_ids = [t["id"] for t in rest["tables"]]
    if (not isinstance(capacities, dict)
            or set(capacities) != set(expected_ids)):
        raise ApiError(422, "validation_failed",
                       "capacities must name every table id exactly")
    checked_capacities = {}
    for tid in expected_ids:
        value = capacities[tid]
        _int_range(value, 1, 100, "capacities.%s" % tid)
        checked_capacities[tid] = value

    return {
        "effective_from": effective,
        "slot_minutes": body["slot_minutes"],
        "reservation_duration_minutes": body["reservation_duration_minutes"],
        "cancellation_cutoff_minutes": body["cancellation_cutoff_minutes"],
        "opening_hours": checked_hours,
        "capacities": checked_capacities,
    }


def publish(user, restaurant_id, body):
    rest = state.STATE["restaurants"].get(restaurant_id)
    if rest is None:
        raise ApiError(404, "not_found", "unknown restaurant")
    if user["id"] not in (rest.get("manager_user_ids") or []):
        raise ApiError(403, "forbidden", "not a restaurant manager")

    policy = _validate_policy(rest, body)
    bucket = state.STATE.setdefault("policies", {}).setdefault(
        restaurant_id, [])
    policy["policy_version"] = max(
        [p["policy_version"] for p in bucket] or [0]) + 1
    bucket.append(policy)
    bump_restaurant_revision(restaurant_id)
    return 201, policy


def publish_idempotent(user, method, path, key, restaurant_id, body):
    return idempotency.execute(
        user["id"], method, path, key, body,
        lambda: publish(user, restaurant_id, body))


def list_response(restaurant_id):
    if restaurant_id not in state.STATE["restaurants"]:
        raise ApiError(404, "not_found", "unknown restaurant")
    return 200, {"policies": list_published(restaurant_id)}
