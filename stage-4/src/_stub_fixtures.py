"""Local stub for the experience-owned `fixtures` module.

Contract (coordinator ruling):
    validate_fixture(body: dict) -> Fixture  (validated/normalized dict)
        raises FixtureError(status, code); reset failures are
        FixtureError(422, "validation_failed")
    demo_seed() -> dict   (attractive demo fixture)

When the real `stage-1/src/fixtures.py` lands, callers prefer it via
try-import and this file is ignored.
"""

import copy
import re
from zoneinfo import ZoneInfo

_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_REF_RE = re.compile(r"^[A-Z0-9]{6,12}$")
_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")


class FixtureError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(message or code)
        self.status = status
        self.code = code


def _fail(msg):
    raise FixtureError(422, "validation_failed", msg)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check_id(v, what):
    if not isinstance(v, str) or not v or len(v) > 64:
        _fail("%s must be a string id of 1..64 chars" % what)
    return v


def _check_hhmm(v, what):
    if not isinstance(v, str) or not _HHMM_RE.match(v):
        _fail("%s must be HH:MM" % what)
    h, m = int(v[:2]), int(v[3:5])
    if h > 23 or m > 59:
        _fail("%s must be HH:MM" % what)
    return h * 60 + m


def validate_fixture(body):
    if not isinstance(body, dict):
        _fail("fixture must be a JSON object")
    users = body.get("users", [])
    restaurants = body.get("restaurants", [])
    reservations = body.get("reservations", [])
    if not isinstance(users, list) or not isinstance(restaurants, list) \
            or not isinstance(reservations, list):
        _fail("users/restaurants/reservations must be arrays")

    user_ids = set()
    emails = set()
    for u in users:
        if not isinstance(u, dict):
            _fail("user must be an object")
        uid = _check_id(u.get("id"), "user.id")
        email = u.get("email")
        if not isinstance(email, str) or "@" not in email:
            _fail("user.email invalid")
        if not isinstance(u.get("password"), str):
            _fail("user.password must be a string")
        if not isinstance(u.get("display_name"), str):
            _fail("user.display_name must be a string")
        if uid in user_ids:
            _fail("duplicate user id")
        if email.lower() in emails:
            _fail("duplicate user email")
        user_ids.add(uid)
        emails.add(email.lower())

    rest_ids = set()
    for r in restaurants:
        if not isinstance(r, dict):
            _fail("restaurant must be an object")
        rid = _check_id(r.get("id"), "restaurant.id")
        if rid in rest_ids:
            _fail("duplicate restaurant id")
        rest_ids.add(rid)
        if not isinstance(r.get("name"), str):
            _fail("restaurant.name must be a string")
        tz = r.get("timezone")
        if not isinstance(tz, str):
            _fail("restaurant.timezone must be a string")
        try:
            ZoneInfo(tz)
        except Exception:
            _fail("restaurant.timezone is not an IANA zone")
        for k in ("slot_minutes", "reservation_duration_minutes"):
            if not _is_int(r.get(k)) or r[k] < 1:
                _fail("restaurant.%s must be a positive integer" % k)
        if not _is_int(r.get("cancellation_cutoff_minutes")) \
                or r["cancellation_cutoff_minutes"] < 0:
            _fail("restaurant.cancellation_cutoff_minutes must be an integer >= 0")
        oh = r.get("opening_hours")
        if not isinstance(oh, list):
            _fail("restaurant.opening_hours must be an array")
        for entry in oh:
            if not isinstance(entry, dict):
                _fail("opening_hours entry must be an object")
            if entry.get("weekday") not in _WEEKDAYS:
                _fail("opening_hours.weekday invalid")
            opens = _check_hhmm(entry.get("opens"), "opens")
            closes = _check_hhmm(entry.get("closes"), "closes")
            if closes <= opens:
                _fail("closes must be later than opens")
        tables = r.get("tables")
        if not isinstance(tables, list):
            _fail("restaurant.tables must be an array")
        tids = set()
        for t in tables:
            if not isinstance(t, dict):
                _fail("table must be an object")
            tid = _check_id(t.get("id"), "table.id")
            if tid in tids:
                _fail("duplicate table id")
            tids.add(tid)
            if not _is_int(t.get("capacity")) or t["capacity"] < 0:
                _fail("table.capacity must be an integer >= 0")
            if "label" in t and not isinstance(t["label"], str):
                _fail("table.label must be a string")

    res_ids = set()
    refs = set()
    for res in reservations:
        if not isinstance(res, dict):
            _fail("reservation must be an object")
        rid = _check_id(res.get("id"), "reservation.id")
        ref = res.get("reference")
        if not isinstance(ref, str) or not _REF_RE.match(ref):
            _fail("reservation.reference invalid")
        if res.get("user_id") not in user_ids:
            _fail("reservation.user_id unknown")
        rid_rest = res.get("restaurant_id")
        if rid_rest not in rest_ids:
            _fail("reservation.restaurant_id unknown")
        table_ok = any(
            t["id"] == res.get("table_id")
            for r in restaurants if r["id"] == rid_rest
            for t in r["tables"]
        )
        if not table_ok:
            _fail("reservation.table_id unknown")
        if not _is_int(res.get("party_size")) or res["party_size"] < 1:
            _fail("reservation.party_size invalid")
        if not isinstance(res.get("starts_at_local"), str):
            _fail("reservation.starts_at_local must be a string")
        if "status" in res and res["status"] not in ("confirmed", "cancelled"):
            _fail("reservation.status invalid")
        if rid in res_ids:
            _fail("duplicate reservation id")
        if ref in refs:
            _fail("duplicate reservation reference")
        res_ids.add(rid)
        refs.add(ref)

    return copy.deepcopy(body)


def demo_seed():
    return {
        "users": [
            {"id": "u_ada", "email": "ada@example.com",
             "password": "correct horse", "display_name": "Ada"}
        ],
        "restaurants": [
            {
                "id": "r_anker",
                "name": "Zum Anker",
                "timezone": "Europe/Berlin",
                "slot_minutes": 30,
                "reservation_duration_minutes": 90,
                "cancellation_cutoff_minutes": 120,
                "opening_hours": [
                    {"weekday": "thu", "opens": "18:00", "closes": "23:00"},
                    {"weekday": "fri", "opens": "18:00", "closes": "23:30"},
                ],
                "tables": [
                    {"id": "t_1", "label": "1", "capacity": 2},
                    {"id": "t_2", "label": "2", "capacity": 4},
                ],
            }
        ],
        "reservations": [],
    }
