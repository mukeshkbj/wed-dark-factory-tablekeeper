"""Reset-fixture validation and the built-in demo seed (spec section 4).

Session record: the mandate header requested model `swe`; this session
reports its resolved model id as **SWE-2 High** (`swe-2-high`).

Contract (consumed by server.py and transfer.py, which import this
module first and fall back to `_stub_fixtures` only on ImportError):

    validate_fixture(body: dict) -> dict
        Validates the whole reset fixture and returns a parsed deep
        copy. Every failure raises FixtureError(422,
        "validation_failed") — coordinator rulings R-1/R-3/G-5: the
        reset body is caller input and fixture content errors are 422,
        never 5xx, and state stays unchanged.

    demo_seed() -> dict
        An attractive, fully synthetic demo fixture that passes
        validate_fixture: three restaurants in three timezones, human
        table labels, two demo users including the documented account
        demo@tablekeeper.test / demo-pass-123, and four seeded
        confirmed reservations.
"""

import copy
import re
from zoneinfo import ZoneInfo

try:
    import timeutil
except ImportError:
    import _stub_timeutil as timeutil

_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_REF_RE = re.compile(r"^[A-Z0-9]{6,12}$")
_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


class FixtureError(Exception):
    """Fixture validation failure carrying .status and .code."""

    def __init__(self, status, code, message=""):
        super().__init__(message or code)
        self.status = status
        self.code = code


def _fail(msg):
    raise FixtureError(422, "validation_failed", msg)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check_id(v, what):
    if not isinstance(v, str) or len(v) > 64:
        _fail("%s must be a string id of at most 64 chars" % what)
    return v


def _check_hhmm(v, what):
    if not isinstance(v, str) or not _HHMM_RE.match(v):
        _fail("%s must be HH:MM" % what)
    h, m = int(v[:2]), int(v[3:5])
    if h > 23 or m > 59:
        _fail("%s must be HH:MM" % what)
    return h * 60 + m


def _validate_users(users):
    ids, emails = set(), set()
    for u in users:
        if not isinstance(u, dict):
            _fail("each user must be an object")
        uid = _check_id(u.get("id"), "user.id")
        email = u.get("email")
        if not isinstance(email, str) or not _EMAIL_RE.match(email):
            _fail("user.email must be of the form local@domain")
        if not isinstance(u.get("password"), str):
            _fail("user.password must be a string")
        if not isinstance(u.get("display_name"), str):
            _fail("user.display_name must be a string")
        if uid in ids:
            _fail("duplicate user id %r" % uid)
        if email.lower() in emails:
            _fail("duplicate user email %r" % email)
        ids.add(uid)
        emails.add(email.lower())
    return ids


def _validate_restaurants(restaurants):
    ids = set()
    table_ids = {}
    for r in restaurants:
        if not isinstance(r, dict):
            _fail("each restaurant must be an object")
        rid = _check_id(r.get("id"), "restaurant.id")
        if rid in ids:
            _fail("duplicate restaurant id %r" % rid)
        ids.add(rid)
        if not isinstance(r.get("name"), str):
            _fail("restaurant.name must be a string")
        tz = r.get("timezone")
        if not isinstance(tz, str):
            _fail("restaurant.timezone must be a string")
        try:
            ZoneInfo(tz)
        except Exception:
            _fail("restaurant.timezone %r is not an IANA zone" % tz)
        for key in ("slot_minutes", "reservation_duration_minutes",
                    "cancellation_cutoff_minutes"):
            if not _is_int(r.get(key)) or r[key] < 1:
                _fail("restaurant.%s must be a positive integer" % key)
        oh = r.get("opening_hours")
        if not isinstance(oh, list):
            _fail("restaurant.opening_hours must be an array")
        for entry in oh:
            if not isinstance(entry, dict):
                _fail("opening_hours entries must be objects")
            if entry.get("weekday") not in _WEEKDAYS:
                _fail("opening_hours.weekday must be mon..sun")
            opens = _check_hhmm(entry.get("opens"), "opening_hours.opens")
            closes = _check_hhmm(entry.get("closes"), "opening_hours.closes")
            if closes <= opens:
                _fail("opening_hours.closes must be later than opens")
        tables = r.get("tables")
        if not isinstance(tables, list):
            _fail("restaurant.tables must be an array")
        tids = set()
        for t in tables:
            if not isinstance(t, dict):
                _fail("each table must be an object")
            tid = _check_id(t.get("id"), "table.id")
            if tid in tids:
                _fail("duplicate table id %r" % tid)
            tids.add(tid)
            if not isinstance(t.get("label"), str):
                _fail("table.label must be a string")
            if not _is_int(t.get("capacity")) or t["capacity"] < 1:
                _fail("table.capacity must be an integer >= 1")
        table_ids[rid] = tids
    return ids, table_ids


def _validate_reservations(reservations, user_ids, rest_ids, table_ids,
                           restaurants_by_id):
    ids, refs = set(), set()
    for res in reservations:
        if not isinstance(res, dict):
            _fail("each reservation must be an object")
        rid = _check_id(res.get("id"), "reservation.id")
        ref = res.get("reference")
        if not isinstance(ref, str) or not _REF_RE.match(ref):
            _fail("reservation.reference must match [A-Z0-9]{6,12}")
        if res.get("user_id") not in user_ids:
            _fail("reservation.user_id does not name a fixture user")
        rest_id = res.get("restaurant_id")
        if rest_id not in rest_ids:
            _fail("reservation.restaurant_id does not name a fixture "
                  "restaurant")
        if res.get("table_id") not in table_ids[rest_id]:
            _fail("reservation.table_id does not belong to that "
                  "restaurant")
        if not _is_int(res.get("party_size")) or res["party_size"] < 1:
            _fail("reservation.party_size must be an integer >= 1")
        local = res.get("starts_at_local")
        if not isinstance(local, str):
            _fail("reservation.starts_at_local must be a string")
        try:
            timeutil.resolve_local(
                restaurants_by_id[rest_id]["timezone"], local)
        except (timeutil.MalformedLocalTime, timeutil.InvalidLocalTime):
            _fail("reservation.starts_at_local is not a valid local time")
        status = res.get("status", "confirmed")
        if status not in ("confirmed", "cancelled"):
            _fail("reservation.status must be confirmed or cancelled")
        if rid in ids:
            _fail("duplicate reservation id %r" % rid)
        if ref in refs:
            _fail("duplicate reservation reference %r" % ref)
        ids.add(rid)
        refs.add(ref)


def validate_fixture(body):
    if not isinstance(body, dict):
        _fail("fixture must be a JSON object")
    users = body.get("users", [])
    restaurants = body.get("restaurants", [])
    reservations = body.get("reservations", [])
    if (not isinstance(users, list) or not isinstance(restaurants, list)
            or not isinstance(reservations, list)):
        _fail("users, restaurants and reservations must be arrays")

    user_ids = _validate_users(users)
    rest_ids, table_ids = _validate_restaurants(restaurants)
    restaurants_by_id = {r["id"]: r for r in restaurants}
    _validate_reservations(reservations, user_ids, rest_ids, table_ids,
                           restaurants_by_id)
    return copy.deepcopy(body)


def demo_seed():
    """Fully synthetic demo fixture — never real credentials or data."""
    return {
        "users": [
            {"id": "u_demo", "email": "demo@tablekeeper.test",
             "password": "demo-pass-123", "display_name": "Demo Diner"},
            {"id": "u_mira", "email": "mira@tablekeeper.test",
             "password": "mira-pass-456", "display_name": "Mira Solene"},
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
                    {"weekday": w, "opens": "18:00", "closes": "23:00"}
                    for w in ("tue", "wed", "thu", "fri", "sat")
                ],
                "tables": [
                    {"id": "t_window", "label": "Window Two",
                     "capacity": 2},
                    {"id": "t_counter", "label": "Chef's Counter",
                     "capacity": 4},
                    {"id": "t_alcove", "label": "Canal Alcove",
                     "capacity": 6},
                ],
            },
            {
                "id": "r_marlowe",
                "name": "The Marlowe Room",
                "timezone": "America/New_York",
                "slot_minutes": 15,
                "reservation_duration_minutes": 75,
                "cancellation_cutoff_minutes": 180,
                "opening_hours": [
                    {"weekday": w, "opens": "17:30", "closes": "22:30"}
                    for w in ("wed", "thu", "fri", "sat")
                ] + [
                    {"weekday": "sun", "opens": "16:00", "closes": "21:00"},
                ],
                "tables": [
                    {"id": "t_banquette", "label": "Velvet Banquette",
                     "capacity": 4},
                    {"id": "t_corner", "label": "Corner Two",
                     "capacity": 2},
                    {"id": "t_marble", "label": "Marble Bar",
                     "capacity": 2},
                ],
            },
            {
                "id": "r_lumen",
                "name": "Lumen Kappo",
                "timezone": "Asia/Tokyo",
                "slot_minutes": 30,
                "reservation_duration_minutes": 120,
                "cancellation_cutoff_minutes": 240,
                "opening_hours": [
                    {"weekday": w, "opens": "18:00", "closes": "22:00"}
                    for w in ("wed", "thu", "fri", "sat")
                ],
                "tables": [
                    {"id": "t_hinoki", "label": "Hinoki Counter",
                     "capacity": 4},
                    {"id": "t_garden", "label": "Garden Room",
                     "capacity": 6},
                    {"id": "t_perch", "label": "Solo Perch",
                     "capacity": 1},
                ],
            },
        ],
        "reservations": [
            {"id": "res_seed_1", "reference": "ANK3R9",
             "user_id": "u_demo", "restaurant_id": "r_anker",
             "table_id": "t_counter", "party_size": 4,
             "starts_at_local": "2026-10-02T19:30",
             "status": "confirmed"},
            {"id": "res_seed_2", "reference": "SATW1N",
             "user_id": "u_demo", "restaurant_id": "r_anker",
             "table_id": "t_window", "party_size": 2,
             "starts_at_local": "2026-10-03T20:30",
             "status": "confirmed"},
            {"id": "res_seed_3", "reference": "MRLW77",
             "user_id": "u_mira", "restaurant_id": "r_marlowe",
             "table_id": "t_banquette", "party_size": 4,
             "starts_at_local": "2026-10-04T18:45",
             "status": "confirmed"},
            {"id": "res_seed_4", "reference": "KAPP0X",
             "user_id": "u_demo", "restaurant_id": "r_lumen",
             "table_id": "t_hinoki", "party_size": 3,
             "starts_at_local": "2026-10-03T19:00",
             "status": "confirmed"},
        ],
    }
