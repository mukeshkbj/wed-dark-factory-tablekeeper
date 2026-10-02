"""Stage-4 closure replans: deterministic preview and atomic apply."""

import re
from datetime import datetime, timezone

import idempotency
import policies
import reservations
import state
from errors import ApiError

try:
    import timeutil
except ImportError:
    import _stub_timeutil as timeutil

_INSTANT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2})$")


def _manager_rest(user, restaurant_id):
    rest = state.STATE["restaurants"].get(restaurant_id)
    if rest is None:
        raise ApiError(404, "not_found", "unknown restaurant")
    if user["id"] not in (rest.get("manager_user_ids") or []):
        raise ApiError(403, "forbidden", "not a restaurant manager")
    return rest


def _parse_instant(value, field):
    if not isinstance(value, str) or not _INSTANT_RE.match(value):
        raise ApiError(422, "validation_failed",
                       "%s must be an RFC3339 instant" % field)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        instant = datetime.fromisoformat(text)
    except ValueError:
        raise ApiError(422, "validation_failed", "invalid %s" % field)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ApiError(422, "validation_failed",
                       "%s must include an offset" % field)
    return instant.astimezone(timezone.utc).timestamp()


def _parse_closure(body):
    for field in ("table_id", "from", "to"):
        if field not in body:
            raise ApiError(422, "validation_failed",
                           "%s is required" % field)
    if not isinstance(body["table_id"], str):
        raise ApiError(400, "malformed_request",
                       "table_id must be a string")
    start = _parse_instant(body["from"], "from")
    end = _parse_instant(body["to"], "to")
    if not start < end:
        raise ApiError(422, "validation_failed", "from must precede to")
    return body["table_id"], start, end


def _new_plan_id():
    counters = state.STATE["counters"]
    while True:
        counters["plan"] = counters.get("plan", 0) + 1
        plan_id = "plan_%d" % counters["plan"]
        if plan_id not in state.STATE["plans"]:
            return plan_id


def _candidate_options(rest):
    singles = [[table["id"]] for table in rest["tables"]]
    return singles + [list(pair) for pair in
                      reservations.combinable_pairs(rest)]


def _terms_capacity(res, table_ids):
    capacities = reservations._accepted_terms(res).get("capacities", {})
    return sum(capacities.get(tid, 0) for tid in table_ids)


def _proposed_closure_conflict(closure, table_ids, start, end):
    return (closure["table_id"] in table_ids
            and timeutil.overlaps(start, end,
                                  closure["from_epoch"],
                                  closure["to_epoch"]))


def _fixed_conflict(rest_id, fixed, table_ids, start, end):
    wanted = set(table_ids)
    for res in fixed:
        if not wanted.intersection(reservations.reservation_table_ids(res)):
            continue
        if timeutil.overlaps(start, end,
                             res["start_epoch"], res["end_epoch"]):
            return True
    return False


def _search(rest, closure, considered):
    """Depth-first search for the spec's lexicographically minimal plan."""
    rest_id = rest["id"]
    considered_ids = {res["id"] for res in considered}
    fixed = [res for res in state.STATE["reservations"].values()
             if res["restaurant_id"] == rest_id
             and res["status"] == "confirmed"
             and res["id"] not in considered_ids]
    options = _candidate_options(rest)
    allowed = []
    for res in considered:
        row = []
        for option in options:
            ok = (_terms_capacity(res, option) >= res["party_size"]
                  and not _proposed_closure_conflict(
                      closure, option, res["start_epoch"], res["end_epoch"])
                  and not reservations.closure_conflict(
                      rest_id, option, res["start_epoch"], res["end_epoch"])
                  and not _fixed_conflict(
                      rest_id, fixed, option,
                      res["start_epoch"], res["end_epoch"]))
            row.append(ok)
        allowed.append(row)

    chosen = [None] * len(considered)
    best = {"plan": None, "key": None}

    def conflicts_chosen(index, option):
        start, end = (considered[index]["start_epoch"],
                      considered[index]["end_epoch"])
        wanted = set(option)
        for other_index, other_option in enumerate(chosen[:index]):
            if other_option is None or not wanted.intersection(other_option):
                continue
            other = considered[other_index]
            if timeutil.overlaps(start, end,
                                 other["start_epoch"], other["end_epoch"]):
                return True
        return False

    def search(index, moved, unused, ranks):
        if best["key"] is not None:
            best_moved, best_unused, best_ranks = best["key"]
            if moved > best_moved:
                return
            if (moved == best_moved and unused > best_unused):
                return
            if (moved == best_moved and unused == best_unused
                    and tuple(ranks) > best_ranks[:len(ranks)]):
                return
        if index == len(considered):
            key = (moved, unused, tuple(ranks))
            if best["key"] is None or key < best["key"]:
                best["key"] = key
                best["plan"] = list(chosen)
            return
        res = considered[index]
        current_ids = reservations.reservation_table_ids(res)
        for rank, option in enumerate(options):
            if not allowed[index][rank] or conflicts_chosen(index, option):
                continue
            chosen[index] = option
            search(index + 1,
                   moved + (option != current_ids),
                   unused + _terms_capacity(res, option) - res["party_size"],
                   ranks + [rank])
            chosen[index] = None

    search(0, 0, 0, [])
    return options, best["plan"], best["key"]


def preview(user, restaurant_id, body):
    rest = _manager_rest(user, restaurant_id)
    table_id, start, end = _parse_closure(body)
    if table_id not in {t["id"] for t in rest["tables"]}:
        raise ApiError(404, "not_found", "unknown table")

    pairs = reservations.combinable_pairs(rest)
    considered = [res for res in state.STATE["reservations"].values()
                  if res["restaurant_id"] == restaurant_id
                  and res["status"] == "confirmed"
                  and timeutil.overlaps(res["start_epoch"], res["end_epoch"],
                                        start, end)]
    considered.sort(key=lambda res: res["reference"])
    if (len(rest["tables"]) > 6 or len(pairs) > 4
            or len(considered) > 6):
        raise ApiError(422, "planning_limit",
                       "replan input exceeds deterministic limits")

    closure = {
        "table_id": table_id,
        "from": body["from"],
        "to": body["to"],
        "from_epoch": start,
        "to_epoch": end,
    }
    options, chosen, key = _search(rest, closure, considered)
    if chosen is None:
        raise ApiError(409, "no_feasible_plan", "no feasible seating plan")

    plan_id = _new_plan_id()
    revision = state.STATE["restaurant_revisions"].get(restaurant_id, 0)
    assignments = []
    stored_assignments = []
    for res, option in zip(considered, chosen):
        current_ids = reservations.reservation_table_ids(res)
        changed = option != current_ids
        assignments.append({
            "reference": res["reference"],
            "table_ids": list(option),
            "changed": changed,
        })
        stored_assignments.append({
            "reservation_id": res["id"],
            "reference": res["reference"],
            "before_table_ids": current_ids,
            "table_ids": list(option),
            "changed": changed,
        })
    plan = {
        "id": plan_id,
        "restaurant_id": restaurant_id,
        "restaurant_revision": revision,
        "status": "pending",
        "closure": closure,
        "assignments": stored_assignments,
    }
    state.STATE["plans"][plan_id] = plan
    moved_count, unused_seats, _ranks = key
    return 201, {
        "plan_id": plan_id,
        "restaurant_revision": revision,
        "closure": {"table_id": table_id,
                    "from": body["from"], "to": body["to"]},
        "assignments": assignments,
        "moved_count": moved_count,
        "unused_seats": unused_seats,
    }


def preview_idempotent(user, method, path, key, restaurant_id, body):
    return idempotency.execute(
        user["id"], method, path, key, body,
        lambda: preview(user, restaurant_id, body))


def _apply_assignment(plan, assignment):
    res = state.STATE["reservations"].get(assignment["reservation_id"])
    if (res is None or res["status"] != "confirmed"
            or res["restaurant_id"] != plan["restaurant_id"]
            or reservations.reservation_table_ids(res)
            != assignment["before_table_ids"]):
        raise ApiError(409, "stale_plan", "plan no longer matches state")
    return res


def apply(user, restaurant_id, plan_id, body):
    _manager_rest(user, restaurant_id)
    plan = state.STATE["plans"].get(plan_id)
    if plan is None or plan["restaurant_id"] != restaurant_id:
        raise ApiError(404, "not_found", "no such plan")
    if plan["status"] == "applied":
        raise ApiError(409, "plan_already_applied",
                       "plan has already been applied")
    current_revision = state.STATE["restaurant_revisions"].get(
        restaurant_id, 0)
    if plan["restaurant_revision"] != current_revision:
        raise ApiError(409, "stale_plan", "restaurant changed after preview")

    rows = [_apply_assignment(plan, assignment)
            for assignment in plan["assignments"]]
    closure = {
        "id": plan_id,
        "table_id": plan["closure"]["table_id"],
        "from": plan["closure"]["from"],
        "to": plan["closure"]["to"],
        "from_epoch": plan["closure"]["from_epoch"],
        "to_epoch": plan["closure"]["to_epoch"],
    }
    state.STATE["closures"].setdefault(restaurant_id, []).append(closure)

    affected_series = set()
    for res, assignment in zip(rows, plan["assignments"]):
        if not assignment["changed"]:
            continue
        before = reservations.reservation_table_ids(res)
        res["table_ids"] = list(assignment["table_ids"])
        res.pop("table_id", None)
        res["revision"] = res.get("revision", 1) + 1
        reservations.append_reassigned_history(
            res, before, assignment["table_ids"], plan_id)
        ser, _occurrence = reservations._series_membership(res)
        if ser is not None:
            affected_series.add(ser["id"])
    for series_id in affected_series:
        state.STATE["series"][series_id]["revision"] += 1
    plan["status"] = "applied"
    policies.bump_restaurant_revision(restaurant_id)
    return 201, {
        "plan_id": plan_id,
        "restaurant_revision": current_revision + 1,
        "reservations": [reservations._view(res) for res in rows],
    }


def apply_idempotent(user, method, path, key, restaurant_id, plan_id, body):
    return idempotency.execute(
        user["id"], method, path, key, body,
        lambda: apply(user, restaurant_id, plan_id, body))
