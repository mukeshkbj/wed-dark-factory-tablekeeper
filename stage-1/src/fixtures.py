"""Fixture parsing and `POST /_test/reset` handling (spec sections 3.3 and 4).

Owned by the experience seat. Interface contract (fixed by coordinator):

    parse_fixture(body) -> Fixture
    handle_reset(state, body) -> None     # server answers 204

Validation split (spec section 5):
  - body does not parse / field of the wrong JSON type -> 400 malformed_request
  - required field missing, or a stated rule violated -> 422 validation_failed
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

try:
    from .errors import ApiError
    from . import auth
except ImportError:
    from errors import ApiError
    import auth

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python always ships zoneinfo in 3.9+
    ZoneInfo = None

_MAX_ID_LEN = 64
_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_HHMM_RE = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
_LOCAL_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T([01][0-9]|2[0-3]):([0-5][0-9])$")
_REFERENCE_RE = re.compile(r"^[A-Z0-9]{6,12}$")


@dataclass
class Fixture:
    """A validated reset fixture, normalized for `state.reset`."""
    users: list = field(default_factory=list)
    restaurants: list = field(default_factory=list)
    reservations: list = field(default_factory=list)


def _bad(message: str):
    raise ApiError(400, "malformed_request", message)


def _invalid(message: str):
    raise ApiError(422, "validation_failed", message)


def _req_obj(value, what: str) -> dict:
    if not isinstance(value, dict):
        _bad(f"{what} must be an object")
    return value


def _req_str(obj: dict, name: str, what: str) -> str:
    if name not in obj:
        _invalid(f"{what}: missing field {name}")
    value = obj[name]
    if not isinstance(value, str):
        _bad(f"{what}: {name} must be a string")
    return value


def _req_id(obj: dict, name: str, what: str) -> str:
    value = _req_str(obj, name, what)
    if not value or len(value) > _MAX_ID_LEN:
        _invalid(f"{what}: {name} must be 1..64 characters")
    return value


def _req_int(obj: dict, name: str, what: str, lo: int, hi: int | None = None) -> int:
    if name not in obj:
        _invalid(f"{what}: missing field {name}")
    value = obj[name]
    if isinstance(value, bool):
        _invalid(f"{what}: {name} must be an integer")
    if not isinstance(value, int):
        _bad(f"{what}: {name} must be an integer")
    if value < lo or (hi is not None and value > hi):
        _invalid(f"{what}: {name} out of range")
    return value


def _req_list(obj: dict, name: str, what: str) -> list:
    if name not in obj:
        _invalid(f"{what}: missing field {name}")
    value = obj[name]
    if not isinstance(value, list):
        _bad(f"{what}: {name} must be a list")
    return value


def _valid_timezone(name: str) -> bool:
    if ZoneInfo is None:
        return True
    try:
        ZoneInfo("UTC")
    except Exception:
        return True  # no tz database installed at all; cannot verify names
    try:
        ZoneInfo(name)
    except Exception:
        return False
    return True


def _hhmm(value: str, closes: bool = False) -> int:
    """Minutes-since-midnight for `HH:MM`; `24:00` allowed for closes only."""
    m = _HHMM_RE.match(value)
    if not m:
        if closes and value == "24:00":
            return 24 * 60
        _invalid(f"invalid HH:MM time: {value!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def _valid_local_time(value: str) -> bool:
    m = _LOCAL_RE.match(value)
    if not m:
        return False
    import datetime as dt
    try:
        dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return False
    return True


def _parse_users(raw: list) -> list:
    users, ids, emails = [], set(), set()
    for item in raw:
        item = _req_obj(item, "user")
        uid = _req_id(item, "id", "user")
        email = _req_str(item, "email", "user")
        password = _req_str(item, "password", "user")
        display_name = _req_str(item, "display_name", "user")
        if not re.match(r"^[^@\s]+@[^@\s]+$", email):
            _invalid(f"user {uid}: email must be local@domain")
        if uid in ids:
            _invalid(f"duplicate user id: {uid}")
        if email in emails:
            _invalid(f"duplicate user email: {email}")
        ids.add(uid)
        emails.add(email)
        users.append({
            "id": uid,
            "email": email,
            "password_hash": auth.hash_password(password),
            "display_name": display_name,
        })
    return users


def _parse_opening_hours(raw: list, rid: str) -> list:
    hours, seen = [], set()
    for item in raw:
        item = _req_obj(item, f"restaurant {rid}: opening_hours entry")
        weekday = _req_str(item, "weekday", f"restaurant {rid} opening_hours")
        opens = _req_str(item, "opens", f"restaurant {rid} opening_hours")
        closes = _req_str(item, "closes", f"restaurant {rid} opening_hours")
        if weekday not in _WEEKDAYS:
            _invalid(f"restaurant {rid}: bad weekday {weekday!r}")
        if weekday in seen:
            _invalid(f"restaurant {rid}: duplicate weekday {weekday}")
        seen.add(weekday)
        if not _hhmm(opens) < _hhmm(closes, closes=True):
            _invalid(f"restaurant {rid}: closes must be later than opens")
        hours.append({"weekday": weekday, "opens": opens, "closes": closes})
    return hours


def _parse_tables(raw: list, rid: str) -> list:
    tables, ids = [], set()
    for item in raw:
        item = _req_obj(item, f"restaurant {rid}: table")
        tid = _req_id(item, "id", f"restaurant {rid} table")
        label = _req_str(item, "label", f"restaurant {rid} table")
        capacity = _req_int(item, "capacity", f"restaurant {rid} table", 1)
        if tid in ids:
            _invalid(f"restaurant {rid}: duplicate table id {tid}")
        ids.add(tid)
        tables.append({"id": tid, "label": label, "capacity": capacity})
    return tables


def _parse_restaurants(raw: list) -> list:
    restaurants, ids = [], set()
    for item in raw:
        item = _req_obj(item, "restaurant")
        rid = _req_id(item, "id", "restaurant")
        name = _req_str(item, "name", "restaurant")
        timezone = _req_str(item, "timezone", "restaurant")
        slot_minutes = _req_int(item, "slot_minutes", "restaurant", 1)
        duration = _req_int(item, "reservation_duration_minutes", "restaurant", 1)
        cutoff = _req_int(item, "cancellation_cutoff_minutes", "restaurant", 0)
        hours_raw = _req_list(item, "opening_hours", "restaurant")
        tables_raw = _req_list(item, "tables", "restaurant")
        if not _valid_timezone(timezone):
            _invalid(f"restaurant {rid}: unknown timezone {timezone!r}")
        if rid in ids:
            _invalid(f"duplicate restaurant id: {rid}")
        ids.add(rid)
        restaurants.append({
            "id": rid,
            "name": name,
            "timezone": timezone,
            "slot_minutes": slot_minutes,
            "reservation_duration_minutes": duration,
            "cancellation_cutoff_minutes": cutoff,
            "opening_hours": _parse_opening_hours(hours_raw, rid),
            "tables": _parse_tables(tables_raw, rid),
        })
    return restaurants


def _parse_reservations(raw: list, user_ids: set, restaurants: list) -> list:
    by_id = {r["id"]: r for r in restaurants}
    reservations, ids, refs = [], set(), set()
    for item in raw:
        item = _req_obj(item, "reservation")
        rid = _req_id(item, "id", "reservation")
        reference = _req_id(item, "reference", "reservation")
        user_id = _req_id(item, "user_id", "reservation")
        restaurant_id = _req_str(item, "restaurant_id", "reservation")
        table_id = _req_str(item, "table_id", "reservation")
        starts_at_local = _req_str(item, "starts_at_local", "reservation")
        if "party_size" not in item:
            _invalid("reservation: missing field party_size")
        party_size = item["party_size"]
        status = item.get("status", "confirmed")
        if not _REFERENCE_RE.match(reference):
            _invalid(f"reservation {rid}: bad reference {reference!r}")
        if not _valid_local_time(starts_at_local):
            _invalid(f"reservation {rid}: bad starts_at_local {starts_at_local!r}")
        if isinstance(party_size, bool) or not isinstance(party_size, int) or party_size < 1:
            _invalid(f"reservation {rid}: bad party_size")
        if not isinstance(status, str):
            _bad("reservation: status must be a string")
        if status not in ("confirmed", "cancelled"):
            _invalid(f"reservation {rid}: bad status {status!r}")
        if user_id not in user_ids:
            _invalid(f"reservation {rid}: unknown user_id {user_id!r}")
        restaurant = by_id.get(restaurant_id)
        if restaurant is None:
            _invalid(f"reservation {rid}: unknown restaurant {restaurant_id!r}")
        if table_id not in {t["id"] for t in restaurant["tables"]}:
            _invalid(f"reservation {rid}: unknown table {table_id!r}")
        if rid in ids:
            _invalid(f"duplicate reservation id: {rid}")
        if reference in refs:
            _invalid(f"duplicate reservation reference: {reference}")
        ids.add(rid)
        refs.add(reference)
        reservations.append({
            "id": rid,
            "reference": reference,
            "user_id": user_id,
            "restaurant_id": restaurant_id,
            "table_id": table_id,
            "starts_at_local": starts_at_local,
            "party_size": party_size,
            "status": status,
        })
    return reservations


def parse_fixture(body) -> Fixture:
    """Validate a `POST /_test/reset` body and return a normalized Fixture."""
    if not isinstance(body, dict):
        _bad("fixture must be a JSON object")

    def _opt_list(name):
        value = body.get(name, [])
        if not isinstance(value, list):
            _bad(f"fixture field {name} must be a list")
        return value

    users = _parse_users(_opt_list("users"))
    restaurants = _parse_restaurants(_opt_list("restaurants"))
    reservations = _parse_reservations(
        _opt_list("reservations"), {u["id"] for u in users}, restaurants)
    return Fixture(users=users, restaurants=restaurants, reservations=reservations)


def handle_reset(state, body) -> None:
    """`POST /_test/reset`: atomically replace all state with the fixture."""
    fixture = parse_fixture(body)
    state.reset(fixture)
    return None
