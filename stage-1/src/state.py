"""State: one object, one lock, one sqlite connection (coordinator ruling R11).

Every public method acquires `self.lock` (a re-entrant lock), so any sequence
of calls wrapped in `with state.lock:` is a single critical section. That is
what makes check-and-act linearizable under the spec's 50-way concurrency:
nothing can interleave between the read and the write that depends on it.

Storage is an in-memory sqlite database; entities are stored as JSON documents
with indexed columns only where lookups need them. Disk persistence is not
required (spec section 2: state need not survive a container restart).

Reservation documents store `table_ids` (a list) internally so the stage-2
combined-table model extends without a schema change; the stage-1 API surface
still speaks `table_id`.

Owned by the engineer seat.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

try:
    from .errors import ApiError
    from . import timeutil
except ImportError:
    from errors import ApiError
    import timeutil

_SCHEMA = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL
);
CREATE TABLE restaurants (
    id TEXT PRIMARY KEY,
    ord INTEGER NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE reservations (
    id TEXT PRIMARY KEY,
    reference TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    restaurant_id TEXT NOT NULL,
    starts_epoch INTEGER NOT NULL,
    ends_epoch INTEGER NOT NULL,
    ord INTEGER NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE idempotency (
    user_id TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    ikey TEXT NOT NULL,
    request TEXT NOT NULL,
    status INTEGER NOT NULL,
    response TEXT NOT NULL,
    PRIMARY KEY (user_id, method, path, ikey)
);
"""


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _unj(text: str):
    return json.loads(text)


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.isolation_level = None  # autocommit; explicit txns where needed
        self.db.executescript(_SCHEMA)
        self._ord = 0

    # -- sequencing ---------------------------------------------------------
    def _next_ord(self) -> int:
        self._ord += 1
        return self._ord

    def now(self) -> int:
        return int(time.time())

    # -- users / tokens ------------------------------------------------------
    def insert_user(self, user_id, email, password_hash, display_name):
        doc = {"id": user_id, "email": email, "password_hash": password_hash,
               "display_name": display_name}
        with self.lock:
            try:
                self.db.execute(
                    "INSERT INTO users (id, email, doc) VALUES (?,?,?)",
                    (user_id, email, _j(doc)))
            except sqlite3.IntegrityError:
                raise ApiError(409, "email_taken", "email already registered")
        return doc

    def user_by_email(self, email):
        with self.lock:
            row = self.db.execute(
                "SELECT doc FROM users WHERE email = ?", (email,)).fetchone()
        return _unj(row[0]) if row else None

    def user_by_id(self, user_id):
        with self.lock:
            row = self.db.execute(
                "SELECT doc FROM users WHERE id = ?", (user_id,)).fetchone()
        return _unj(row[0]) if row else None

    def insert_token(self, token, user_id):
        with self.lock:
            self.db.execute(
                "INSERT INTO tokens (token, user_id) VALUES (?,?)",
                (token, user_id))

    def user_for_token(self, token):
        with self.lock:
            row = self.db.execute(
                "SELECT u.doc FROM tokens t JOIN users u ON u.id = t.user_id "
                "WHERE t.token = ?", (token,)).fetchone()
        return _unj(row[0]) if row else None

    # -- reset / fixtures ----------------------------------------------------
    def reset(self, fixture):
        """Atomically replace all state with a parsed `Fixture` (spec 3.3)."""
        with self.lock:
            restaurants = {r["id"]: r for r in fixture.restaurants}
            zones = {}
            for rid, r in restaurants.items():
                zones[rid] = timeutil.ZoneInfo(r["timezone"])

            self.db.execute("BEGIN")
            try:
                for table in ("users", "tokens", "restaurants",
                              "reservations", "idempotency"):
                    self.db.execute(f"DELETE FROM {table}")
                self._ord = 0
                for i, r in enumerate(fixture.restaurants):
                    self.db.execute(
                        "INSERT INTO restaurants (id, ord, doc) VALUES (?,?,?)",
                        (r["id"], i, _j(dict(r))))
                for u in fixture.users:
                    self.db.execute(
                        "INSERT INTO users (id, email, doc) VALUES (?,?,?)",
                        (u["id"], u["email"], _j(dict(u))))
                for r in fixture.reservations:
                    self._insert_reservation_doc(
                        self._seeded_reservation_doc(r, restaurants, zones))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def _seeded_reservation_doc(self, item, restaurants, zones):
        restaurant = restaurants[item["restaurant_id"]]
        tz = zones[item["restaurant_id"]]
        day, minute = timeutil.parse_local(item["starts_at_local"])
        start = timeutil.resolve_local_lenient(day, minute, tz)
        s = timeutil.epoch(start)
        e = s + restaurant["reservation_duration_minutes"] * 60
        return {
            "id": item["id"],
            "reference": item["reference"],
            "user_id": item["user_id"],
            "restaurant_id": item["restaurant_id"],
            "table_ids": [item["table_id"]],
            "starts_at_local": item["starts_at_local"],
            "starts_epoch": s,
            "ends_epoch": e,
            "party_size": item["party_size"],
            "status": item["status"],
            "created_at": self.now(),
        }

    def _insert_reservation_doc(self, doc):
        self.db.execute(
            "INSERT INTO reservations (id, reference, user_id, restaurant_id,"
            " starts_epoch, ends_epoch, ord, doc)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (doc["id"], doc["reference"], doc["user_id"], doc["restaurant_id"],
             doc["starts_epoch"], doc["ends_epoch"], self._next_ord(),
             _j(doc)))

    # -- restaurants ----------------------------------------------------------
    def all_restaurants(self):
        with self.lock:
            rows = self.db.execute(
                "SELECT doc FROM restaurants ORDER BY ord").fetchall()
        return [_unj(r[0]) for r in rows]

    def get_restaurant(self, restaurant_id):
        with self.lock:
            row = self.db.execute(
                "SELECT doc FROM restaurants WHERE id = ?",
                (restaurant_id,)).fetchone()
        return _unj(row[0]) if row else None

    # -- reservations ----------------------------------------------------------
    def insert_reservation(self, doc):
        with self.lock:
            self._insert_reservation_doc(doc)

    def update_reservation(self, doc):
        with self.lock:
            self.db.execute(
                "UPDATE reservations SET starts_epoch=?, ends_epoch=?, doc=?"
                " WHERE id=?",
                (doc["starts_epoch"], doc["ends_epoch"], _j(doc), doc["id"]))

    def reservation_by_reference(self, reference):
        with self.lock:
            row = self.db.execute(
                "SELECT doc FROM reservations WHERE reference = ?",
                (reference,)).fetchone()
        return _unj(row[0]) if row else None

    def reference_taken(self, reference) -> bool:
        with self.lock:
            return self.db.execute(
                "SELECT 1 FROM reservations WHERE reference = ?",
                (reference,)).fetchone() is not None

    def reservation_id_taken(self, reservation_id) -> bool:
        with self.lock:
            return self.db.execute(
                "SELECT 1 FROM reservations WHERE id = ?",
                (reservation_id,)).fetchone() is not None

    def reservations_for_user(self, user_id):
        with self.lock:
            rows = self.db.execute(
                "SELECT doc FROM reservations WHERE user_id = ? ORDER BY ord",
                (user_id,)).fetchall()
        return [_unj(r[0]) for r in rows]

    def confirmed_for_restaurant(self, restaurant_id):
        """All confirmed reservation docs of a restaurant, fixture order."""
        with self.lock:
            rows = self.db.execute(
                "SELECT doc FROM reservations WHERE restaurant_id = ?"
                " ORDER BY ord",
                (restaurant_id,)).fetchall()
        return [d for d in (_unj(r[0]) for r in rows)
                if d["status"] == "confirmed"]

    # -- idempotency ledger (spec section 7) ----------------------------------
    def idem_get(self, user_id, method, path, key):
        with self.lock:
            row = self.db.execute(
                "SELECT request, status, response FROM idempotency"
                " WHERE user_id=? AND method=? AND path=? AND ikey=?",
                (user_id, method, path, key)).fetchone()
        return tuple(row) if row else None

    def idem_put(self, user_id, method, path, key, request, status, response):
        with self.lock:
            self.db.execute(
                "INSERT INTO idempotency"
                " (user_id, method, path, ikey, request, status, response)"
                " VALUES (?,?,?,?,?,?,?)",
                (user_id, method, path, key, request, status, response))

    # -- export / import (spec section 10) -------------------------------------
    def export_state(self):
        """A consistent, JSON-serializable snapshot of the whole store."""
        with self.lock:
            users = [r[0] for r in self.db.execute(
                "SELECT doc FROM users ORDER BY rowid")]
            tokens = self.db.execute(
                "SELECT token, user_id FROM tokens ORDER BY rowid").fetchall()
            restaurants = [r[0] for r in self.db.execute(
                "SELECT doc FROM restaurants ORDER BY ord")]
            reservations = [r[0] for r in self.db.execute(
                "SELECT doc FROM reservations ORDER BY ord")]
            idem = self.db.execute(
                "SELECT user_id, method, path, ikey, request, status, response"
                " FROM idempotency ORDER BY rowid").fetchall()
        return {
            "users": [_unj(d) for d in users],
            "tokens": [{"token": t, "user_id": u} for t, u in tokens],
            "restaurants": [_unj(d) for d in restaurants],
            "reservations": [_unj(d) for d in reservations],
            "idempotency": [
                {"user_id": u, "method": m, "path": p, "key": k,
                 "request": _unj(req), "status": s, "response": _unj(resp)}
                for u, m, p, k, req, s, resp in idem
            ],
        }

    def import_state(self, state):
        """Atomically replace all state with a validated export `state` object.

        Raises ApiError(422, validation_failed) leaving state untouched when
        the payload is not well-formed.
        """
        parsed = _validate_state(state)
        with self.lock:
            self.db.execute("BEGIN")
            try:
                for table in ("users", "tokens", "restaurants",
                              "reservations", "idempotency"):
                    self.db.execute(f"DELETE FROM {table}")
                self._ord = 0
                for u in parsed["users"]:
                    self.db.execute(
                        "INSERT INTO users (id, email, doc) VALUES (?,?,?)",
                        (u["id"], u["email"], _j(u)))
                for t in parsed["tokens"]:
                    self.db.execute(
                        "INSERT INTO tokens (token, user_id) VALUES (?,?)",
                        (t["token"], t["user_id"]))
                for i, r in enumerate(parsed["restaurants"]):
                    self.db.execute(
                        "INSERT INTO restaurants (id, ord, doc) VALUES (?,?,?)",
                        (r["id"], i, _j(r)))
                max_ord = 0
                for i, doc in enumerate(parsed["reservations"]):
                    self.db.execute(
                        "INSERT INTO reservations (id, reference, user_id,"
                        " restaurant_id, starts_epoch, ends_epoch, ord, doc)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (doc["id"], doc["reference"], doc["user_id"],
                         doc["restaurant_id"], doc["starts_epoch"],
                         doc["ends_epoch"], i, _j(doc)))
                    max_ord = i + 1
                for rec in parsed["idempotency"]:
                    self.db.execute(
                        "INSERT INTO idempotency (user_id, method, path, ikey,"
                        " request, status, response) VALUES (?,?,?,?,?,?,?)",
                        (rec["user_id"], rec["method"], rec["path"],
                         rec["key"], _j(rec["request"]), rec["status"],
                         _j(rec["response"])))
                self._ord = max_ord
                self.db.execute("COMMIT")
            except sqlite3.Error:
                self.db.execute("ROLLBACK")
                raise ApiError(422, "validation_failed",
                               "state could not be applied")
            except Exception:
                self.db.execute("ROLLBACK")
                raise


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_state(state) -> dict:
    """Validate the opaque `state` member of an export; returns a normalized copy."""
    if not isinstance(state, dict):
        raise ApiError(422, "validation_failed", "state must be an object")

    def req_list(name):
        value = state.get(name)
        if not isinstance(value, list):
            raise ApiError(422, "validation_failed",
                           f"state.{name} must be a list")
        return value

    users, tokens, restaurants, reservations, idem = [], [], [], [], []
    user_ids, emails = set(), set()
    for item in req_list("users"):
        if not isinstance(item, dict) or not all(
                isinstance(item.get(k), str)
                for k in ("id", "email", "password_hash", "display_name")):
            raise ApiError(422, "validation_failed", "invalid user record")
        if item["id"] in user_ids or item["email"] in emails:
            raise ApiError(422, "validation_failed", "duplicate user record")
        user_ids.add(item["id"])
        emails.add(item["email"])
        users.append(item)
    for item in req_list("tokens"):
        if not isinstance(item, dict) or not all(
                isinstance(item.get(k), str) for k in ("token", "user_id")):
            raise ApiError(422, "validation_failed", "invalid token record")
        tokens.append(item)
    restaurant_ids = set()
    for item in req_list("restaurants"):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) \
                or not isinstance(item.get("timezone"), str) \
                or not _is_int(item.get("slot_minutes")) \
                or not _is_int(item.get("reservation_duration_minutes")) \
                or not _is_int(item.get("cancellation_cutoff_minutes")) \
                or not isinstance(item.get("opening_hours"), list) \
                or not isinstance(item.get("tables"), list):
            raise ApiError(422, "validation_failed",
                           "invalid restaurant record")
        try:
            timeutil.ZoneInfo(item["timezone"])
        except Exception:
            raise ApiError(422, "validation_failed",
                           "invalid restaurant timezone")
        restaurant_ids.add(item["id"])
        restaurants.append(item)
    references, res_ids = set(), set()
    for item in req_list("reservations"):
        if not isinstance(item, dict) \
                or not all(isinstance(item.get(k), str)
                           for k in ("id", "reference", "user_id",
                                     "restaurant_id", "starts_at_local",
                                     "status")) \
                or not isinstance(item.get("table_ids"), list) \
                or not all(isinstance(t, str) for t in item["table_ids"]) \
                or not _is_int(item.get("party_size")) \
                or not _is_int(item.get("starts_epoch")) \
                or not _is_int(item.get("ends_epoch")) \
                or not _is_int(item.get("created_at")):
            raise ApiError(422, "validation_failed",
                           "invalid reservation record")
        if item["id"] in res_ids or item["reference"] in references:
            raise ApiError(422, "validation_failed",
                           "duplicate reservation record")
        if item["restaurant_id"] not in restaurant_ids:
            raise ApiError(422, "validation_failed",
                           "reservation references unknown restaurant")
        res_ids.add(item["id"])
        references.add(item["reference"])
        reservations.append(item)
    for item in req_list("idempotency"):
        if not isinstance(item, dict) \
                or not all(isinstance(item.get(k), str)
                           for k in ("user_id", "method", "path", "key")) \
                or not _is_int(item.get("status")) \
                or "request" not in item or "response" not in item:
            raise ApiError(422, "validation_failed",
                           "invalid idempotency record")
        idem.append(item)
    return {"users": users, "tokens": tokens, "restaurants": restaurants,
            "reservations": reservations, "idempotency": idem}
